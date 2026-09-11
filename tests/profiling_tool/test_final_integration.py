"""Final Phase: 統合検証。

実対象(VLM/Sound/GI/VideoFactory)を使わない合成プログラム(ダミー計装コード)で、
コアSDK・アダプタ・集計・アラートを一通り通してChrome Trace Event Format JSONを
出力し、Perfetto UIが読み込める妥当な形になっていることを確認する。
"""
from __future__ import annotations

import time

from profiling_tool.adapters import gi_adapter, sound_adapter, videofactory_adapter, vlm_adapter
from profiling_tool.aggregate import percentile_by_span_name
from profiling_tool.alerting.threshold_alert import ThresholdAlertEngine, ThresholdRule
from profiling_tool.core import chrome_trace
from profiling_tool.core.counter import Counter
from profiling_tool.core.gpu_timestamp_query import GpuTimestampQuery, SimulatedGpuBackend
from profiling_tool.core.recorder import TraceWriter
from profiling_tool.core.span import SpanGuard, SpanRecorder


def test_synthetic_program_produces_valid_chrome_trace_json_across_all_components(tmp_path):
    """4対象それぞれのダミーデータを流し込み、1本のtraceEvents配列として妥当な
    Chrome Trace Event Format JSONになることを確認する(Final Phase 1項目目)。
    """
    all_events: list[dict] = []

    # VideoFactory: 既存manifest.json相当を変換するだけ
    manifest = {
        "pipeline": [
            {"stage": "Narrate", "label": "narration", "status": "success", "duration_sec": 1.0},
            {"stage": "AssembleAndRender", "label": "assemble", "status": "success", "duration_sec": 2.0},
        ]
    }
    all_events.extend(videofactory_adapter.to_trace(manifest, run_id="synthetic"))

    # VLM: StepLog 3件
    for i in range(3):
        step_log = {
            "stepIndex": i,
            "timestamp": i * 1000,
            "todoId": f"todo-{i}",
            "observationRef": f"obs-{i}",
            "reasoning": f"dummy reasoning {i}",
            "actionTaken": "noop",
            "resultObservationSummary": "ok",
        }
        all_events.extend(vlm_adapter.to_trace(step_log))

    # Sound: DebugSnapshotストリーム(underrun 1件含む)
    def snapshot_stream():
        for ts_ms in range(0, 40, 5):
            yield {
                "activeVoices": 10,
                "busGraph": {},
                "memoryUsage": 2048,
                "streamingQueueDepth": 2,
                "underrunCount": 1 if ts_ms == 20 else 0,
                "timestamp": ts_ms * 1000,
            }

    all_events.extend(sound_adapter.to_trace(snapshot_stream()))

    # Dynamic GI: GpuTimestampQueryのフレーム計装
    gpu_query = GpuTimestampQuery(SimulatedGpuBackend(resolve_after_polls=1))
    handles = gi_adapter.instrument_frame(gpu_query, frame_index=0)
    resolved = gi_adapter.resolve_frame(gpu_query, handles)
    for stage, gpu_span in resolved.items():
        all_events.append(
            chrome_trace.gpu_span(name=gpu_span.name, ts=gpu_span.start_us, dur=max(0, gpu_span.end_us - gpu_span.start_us))
        )

    # 追記専用トレースストアへ書き出す(Phase3)
    writer = TraceWriter(target="synthetic", run_id="final_phase", traces_dir=tmp_path)
    writer.append(all_events)

    written = writer.read_events()
    assert len(written) == len(all_events)
    for evt in written:
        assert {"name", "ph", "ts", "pid", "tid"}.issubset(evt.keys())
        assert evt["ph"] in ("X", "C", "i")


def test_span_nesting_round_trips_three_levels(tmp_path):
    """span親子ネスト(SpanGuardの入れ子)がネスト3階層のケースで往復することを確認する。"""
    recorder = SpanRecorder()
    with SpanGuard(recorder, "job"):
        with SpanGuard(recorder, "stage"):
            with SpanGuard(recorder, "substep"):
                pass

    events = [chrome_trace.span(name=s.name, ts=s.start_us, dur=s.duration_us) for s in recorder.drain()]
    by_name = {e["name"]: e for e in events}
    job, stage, substep = by_name["job"], by_name["stage"], by_name["substep"]
    assert job["ts"] <= stage["ts"] <= substep["ts"]
    assert (substep["ts"] + substep["dur"]) <= (stage["ts"] + stage["dur"]) <= (job["ts"] + job["dur"])


def test_videofactory_spans_are_visually_non_overlapping_on_timeline():
    """VideoFactoryアダプタの出力がNarrate/AssembleAndRenderの非重複spanとして
    タイムライン上に表れる(GPU厳密逐次リース制約=strict-sequential制約の実証)。
    """
    manifest = {
        "pipeline": [
            {"stage": "Narrate", "label": "n", "status": "success", "duration_sec": 3.0},
            {"stage": "AssembleAndRender", "label": "a", "status": "success", "duration_sec": 5.0},
            {"stage": "Encode", "label": "e", "status": "success", "duration_sec": 2.0},
        ]
    }
    spans = videofactory_adapter.to_trace(manifest, run_id="r")
    intervals = [(s["ts"], s["ts"] + s["dur"]) for s in spans]
    for (start_a, end_a), (start_b, end_b) in zip(intervals, intervals[1:]):
        assert end_a <= start_b  # 重ならない


def test_aggregate_p95_matches_expected_value_on_synthetic_distribution():
    durations = list(range(1, 201))
    traces = [chrome_trace.span("stage", ts=i, dur=d) for i, d in enumerate(durations)]
    p95 = percentile_by_span_name(traces, "stage", 0.95)
    assert p95 == sorted(durations)[int(len(durations) * 0.95)]


def test_threshold_alert_fires_exactly_once_for_repeated_breaching_frames():
    fired = []
    engine = ThresholdAlertEngine(
        rules=[ThresholdRule(target="dynamic_gi", metric="composite_span_p95_ms", threshold=16.0)],
        sinks=[type("Sink", (), {"emit": staticmethod(lambda a: fired.append(a))})()],
    )
    for _ in range(10):  # 連続超過フレーム
        engine.check("dynamic_gi", "composite_span_p95_ms", value=33.0)
    assert len(fired) == 1


def test_counter_record_overhead_is_negligible_versus_dummy_callback_work():
    """Sound Middleware想定のダミーコールバックループにCounter.record()を組み込み、
    ロック・アロケーションによるレイテンシ増加が計測誤差レベル(既存コールバック処理
    時間比で無視できる範囲)に収まることを確認する。
    """

    def dummy_audio_work(n: int) -> float:
        # 実際のオーディオコールバックが行うであろう演算量を模した軽い浮動小数点計算
        acc = 0.0
        for i in range(n):
            acc += (i * 0.0001) ** 0.5
        return acc

    iterations = 2000
    work_n = 200

    baseline_start = time.perf_counter()
    for _ in range(iterations):
        dummy_audio_work(work_n)
    baseline_elapsed = time.perf_counter() - baseline_start

    counter = Counter("voice_count", capacity=4096)
    instrumented_start = time.perf_counter()
    for i in range(iterations):
        dummy_audio_work(work_n)
        counter.record(float(i), i)
    instrumented_elapsed = time.perf_counter() - instrumented_start

    overhead_ratio = (instrumented_elapsed - baseline_elapsed) / baseline_elapsed
    # record()呼び出しが加わったことによる相対的なオーバーヘッドが50%を超えないこと
    # (厳密な絶対値でのus単位計測はCI環境のノイズに弱いため、比率で緩く検証する)
    assert overhead_ratio < 0.5, f"overhead_ratio={overhead_ratio:.2f} は許容範囲を超えている"
