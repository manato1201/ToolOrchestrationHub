"""profiling_tool/scripts/generate_demo_traces.py

実対象(VLM/Sound/GI/VideoFactory)を使わない合成プログラム(ダミー計装コード)で
.profiling_state/traces/ 以下にデモ用のトレースを生成する。Final Phase統合検証の
「合成プログラム」をそのまま流用し、初回起動してもRunsが空にならないようにする。

使い方: uv run python profiling_tool/scripts/generate_demo_traces.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# ToolOrchestrationHub/profiling_tool/scripts/generate_demo_traces.py -> リポジトリルートは3階層上
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from profiling_tool.adapters import gi_adapter, sound_adapter, videofactory_adapter, vlm_adapter  # noqa: E402
from profiling_tool.core import chrome_trace  # noqa: E402
from profiling_tool.core.gpu_timestamp_query import GpuTimestampQuery, SimulatedGpuBackend  # noqa: E402
from profiling_tool.core.recorder import TraceWriter  # noqa: E402

RUN_ID = "demo_run"


def _videofactory_events() -> list[dict]:
    manifest = {
        "pipeline": [
            {"stage": "Narrate", "label": "narration", "status": "success", "duration_sec": 12.5},
            {"stage": "AssembleAndRender", "label": "assemble", "status": "success", "duration_sec": 41.8},
            {"stage": "Encode", "label": "encode", "status": "success", "duration_sec": 6.2},
        ]
    }
    return videofactory_adapter.to_trace(manifest, run_id=RUN_ID)


def _vlm_events() -> list[dict]:
    events: list[dict] = []
    reasonings = [
        "画面右上のダイアログを確認し、保存ボタンを押す必要がある",
        "保存完了を確認できたので次のTODOに進む",
        "次のTODOはメニューを開いて設定画面へ遷移すること",
    ]
    for i, reasoning in enumerate(reasonings):
        step_log = {
            "stepIndex": i,
            "timestamp": i * 2_000_000,
            "todoId": f"todo-{i}",
            "observationRef": f"obs-{i}",
            "reasoning": reasoning,
            "actionTaken": "click(button_id=save)" if i == 0 else "noop",
            "resultObservationSummary": "保存完了ダイアログが表示された" if i == 0 else "変化なし",
        }
        events.extend(vlm_adapter.to_trace(step_log))
    return events


def _sound_events() -> list[dict]:
    def snapshot_stream():
        for ts_ms in range(0, 200, 2):
            yield {
                "activeVoices": 8 + (ts_ms % 16),
                "busGraph": {"master": {"gain": 1.0}},
                "memoryUsage": 4_500_000 + ts_ms * 100,
                "streamingQueueDepth": 2 + (ts_ms % 3),
                "underrunCount": 1 if ts_ms in (60, 140) else 0,
                "timestamp": ts_ms * 1000,
            }

    return list(sound_adapter.to_trace(snapshot_stream()))


def _gi_events() -> list[dict]:
    events: list[dict] = []
    gpu_query = GpuTimestampQuery(SimulatedGpuBackend(resolve_after_polls=1))
    for frame in range(3):
        handles = gi_adapter.instrument_frame(gpu_query, frame_index=frame)
        resolved = gi_adapter.resolve_frame(gpu_query, handles)
        for gpu_span in resolved.values():
            events.append(
                chrome_trace.gpu_span(
                    name=gpu_span.name, ts=gpu_span.start_us, dur=max(0, gpu_span.end_us - gpu_span.start_us)
                )
            )
    return events


def main() -> None:
    targets = {
        "videofactory": _videofactory_events(),
        "vlm_auto_replay": _vlm_events(),
        "sound_middleware": _sound_events(),
        "dynamic_gi": _gi_events(),
    }
    for target, events in targets.items():
        writer = TraceWriter(target=target, run_id=RUN_ID)
        writer.append(events)
        print(f"wrote {len(events)} events -> {writer.path}")


if __name__ == "__main__":
    main()
