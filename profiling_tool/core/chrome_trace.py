"""profiling/chrome_trace.py

Phase1: Chrome Trace Event Format(JSON)への変換。独自形式は発明しない。
`chrome://tracing`およびPerfetto UI(ui.perfetto.dev)がそのまま読み込める。

ph:"X" = 完結区間(span/GpuSpan)、ph:"C" = カウンタ(counter)、
ph:"i" = 瞬間イベント(structured event)。

アダプタ層(adapters/*.py)は既存の構造化ログ(StepLog、manifest.json等)を
事後変換するため、ここで定義するspan()/counter()/event()ビルダー関数を直接使う。
ライブ計装(SpanRecorder/Counter/StructuredEvent)側もrecorder.py経由で同じ
ビルダーに収束させ、出力形式を二重実装しない。
"""

from __future__ import annotations

from typing import Any, Optional

_CPU_PID = 1
_GPU_PID = 2  # CPU spanと視覚的に並べて比較できるよう、GPUキューは別pidに分離する


def span(
    name: str,
    ts: int,
    dur: int = 0,
    tags: Optional[dict[str, Any]] = None,
    tid: int = 1,
) -> dict[str, Any]:
    return {
        "name": name,
        "ph": "X",
        "ts": ts,
        "dur": dur,
        "pid": _CPU_PID,
        "tid": tid,
        "args": dict(tags or {}),
    }


def gpu_span(
    name: str, ts: int, dur: int, queue: str = "gpu", tid: int = 1
) -> dict[str, Any]:
    return {
        "name": name,
        "ph": "X",
        "ts": ts,
        "dur": dur,
        "pid": _GPU_PID,
        "tid": tid,
        "args": {"queue": queue},
    }


def counter(name: str, value: float, ts: int, tid: int = 1) -> dict[str, Any]:
    return {
        "name": name,
        "ph": "C",
        "ts": ts,
        "pid": _CPU_PID,
        "tid": tid,
        "args": {"value": value},
    }


def event(name: str, ts: int, payload: dict[str, Any], tid: int = 1) -> dict[str, Any]:
    return {
        "name": name,
        "ph": "i",
        "ts": ts,
        "pid": _CPU_PID,
        "tid": tid,
        "s": "t",
        "args": {"payload": payload},
    }


def build_trace(events: list[dict[str, Any]]) -> dict[str, Any]:
    return {"traceEvents": events}
