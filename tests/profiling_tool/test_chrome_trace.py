"""Phase1 検証チェックリスト: Chrome Trace Event Format出力の妥当性。"""
from __future__ import annotations

import json

from profiling_tool.core import chrome_trace


def test_span_produces_ph_x_completed_event():
    evt = chrome_trace.span(name="AssembleAndRender", ts=1000, dur=4200, tags={"stage": "assemble"})
    assert evt["ph"] == "X"
    assert evt["ts"] == 1000
    assert evt["dur"] == 4200
    assert evt["args"] == {"stage": "assemble"}


def test_counter_produces_ph_c_event():
    evt = chrome_trace.counter(name="voice_count", value=12, ts=1000)
    assert evt["ph"] == "C"
    assert evt["args"] == {"value": 12}


def test_gpu_span_uses_separate_pid_from_cpu_span():
    cpu_evt = chrome_trace.span(name="cpu_work", ts=0, dur=100)
    gpu_evt = chrome_trace.gpu_span(name="gpu_work", ts=0, dur=100)
    assert cpu_evt["pid"] != gpu_evt["pid"]  # CPU spanと並べて比較できるよう別pidに分離


def test_build_trace_wraps_events_in_trace_events_key():
    trace = chrome_trace.build_trace([chrome_trace.span("a", ts=0, dur=1)])
    assert list(trace.keys()) == ["traceEvents"]
    assert len(trace["traceEvents"]) == 1


def test_build_trace_output_is_json_serializable_and_perfetto_compatible_shape():
    """Perfetto UI/chrome://tracingが読み込める最小限の形(traceEvents配列、各要素が
    name/ph/ts/pid/tidを持つ)であることを構造的に確認する。実際のPerfetto取り込みは
    Final Phaseの手動検証チェックリスト項目。
    """
    trace = chrome_trace.build_trace(
        [
            chrome_trace.span("step_1", ts=0, dur=10),
            chrome_trace.counter("active_voices", value=4, ts=0),
            chrome_trace.event("underrun", ts=5, payload={"activeVoices": 4}),
        ]
    )
    serialized = json.dumps(trace)
    reloaded = json.loads(serialized)
    for evt in reloaded["traceEvents"]:
        assert {"name", "ph", "ts", "pid", "tid"}.issubset(evt.keys())
