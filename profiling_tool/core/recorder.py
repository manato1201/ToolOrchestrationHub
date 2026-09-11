"""profiling_tool/core/recorder.py

Phase1/Phase3: SpanRecorder/Counter/StructuredEventの記録結果をChrome Trace Event
Format JSONへ変換し、追記専用トレースストア(.profiling_state/traces/<target>/<runId>.json)
へ書き出す。

別文書(AssetDataInsightSuite/VisualRegressionQATool)と同系の追記専用履歴パターンを
再利用するだけで、新規に発明しない(Phase3)。

ToolOrchestrationHubのサブ機能として統合されたため、出力先はHub自身のランタイム状態
(.hub_state/)と同じ流儀で、リポジトリルート直下の.profiling_state/にまとめている。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from . import chrome_trace
from .counter import CounterSample
from .event import StructuredEvent
from .gpu_timestamp_query import GpuSpan
from .span import Span

# ToolOrchestrationHub/profiling_tool/core/recorder.py -> リポジトリルートは3階層上
DEFAULT_TRACES_DIR = Path(__file__).parent.parent.parent / ".profiling_state" / "traces"


def spans_to_events(spans: Iterable[Span]) -> list[dict]:
    return [
        chrome_trace.span(
            name=s.name, ts=s.start_us, dur=s.duration_us, tags=s.tags, tid=s.thread_id
        )
        for s in spans
    ]


def gpu_spans_to_events(gpu_spans: Iterable[GpuSpan]) -> list[dict]:
    return [
        chrome_trace.gpu_span(
            name=g.name, ts=g.start_us, dur=max(0, g.end_us - g.start_us), queue=g.queue
        )
        for g in gpu_spans
    ]


def counter_samples_to_events(
    name: str, samples: Iterable[CounterSample]
) -> list[dict]:
    return [
        chrome_trace.counter(name=name, value=s.value, ts=s.timestamp_us)
        for s in samples
    ]


def structured_events_to_events(events: Iterable[StructuredEvent]) -> list[dict]:
    return [
        chrome_trace.event(name=e.name, ts=e.timestamp_us, payload=e.payload())
        for e in events
    ]


class TraceWriter:
    """target/runId単位でファイルを分離し、追記専用で書き出す。

    Phase3検証チェックリスト: 「同一runIdに対する2回目の書き込みが既存ファイルを
    上書きせず追記になる」を満たすため、既存traceEventsを読み込んでから連結する。
    runId単位でファイルが独立するため、並行実行するツール間でファイルロック競合が
    起きない(Phase3)。
    """

    def __init__(
        self, target: str, run_id: str, traces_dir: Path | str = DEFAULT_TRACES_DIR
    ) -> None:
        self.target = target
        self.run_id = run_id
        self._path = Path(traces_dir) / target / f"{run_id}.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def append(self, events: Iterable[dict]) -> int:
        """events(Chrome Trace Event Format準拠の辞書)を既存ファイルへ追記する。
        返り値は追記後の総イベント数。
        """
        events = list(events)
        existing = self.read_events()
        if not events:
            return len(existing)
        existing.extend(events)
        with self._path.open("w", encoding="utf-8") as f:
            json.dump(chrome_trace.build_trace(existing), f, ensure_ascii=False)
        return len(existing)

    def read_events(self) -> list[dict]:
        if not self._path.exists():
            return []
        with self._path.open(encoding="utf-8") as f:
            data = json.load(f)
        return list(data.get("traceEvents", []))
