"""Phase4/Final Phase 検証チェックリスト: threshold_alert.py。"""
from __future__ import annotations

from profiling_tool.alerting.threshold_alert import (
    ConsoleSink,
    FileSink,
    ThresholdAlertEngine,
    ThresholdRule,
)


class _RecordingSink:
    def __init__(self) -> None:
        self.emitted: list[dict] = []

    def emit(self, alert: dict) -> None:
        self.emitted.append(alert)


def test_alert_fires_only_for_the_breaching_target_and_metric():
    """しきい値超過が検出された対象・メトリクスのみアラートが発火し、他対象への誤爆がない。"""
    sink = _RecordingSink()
    engine = ThresholdAlertEngine(
        rules=[ThresholdRule(target="sound_middleware", metric="underrun_count", threshold=0)],
        sinks=[sink],
    )

    engine.check("dynamic_gi", "composite_span_p95_ms", value=999, run_id="r1")
    assert sink.emitted == []

    engine.check("sound_middleware", "underrun_count", value=1, run_id="r1")
    assert len(sink.emitted) == 1
    assert sink.emitted[0]["target"] == "sound_middleware"


def test_repeated_breaches_fire_only_once_until_resolved():
    """同一事象に対してアラートが重複なく1回だけ発報される(連続超過フレームの再発火抑制)。"""
    sink = _RecordingSink()
    engine = ThresholdAlertEngine(
        rules=[ThresholdRule(target="dynamic_gi", metric="composite_span_p95_ms", threshold=16.0)],
        sinks=[sink],
    )

    for _ in range(5):  # 5フレーム連続で超過
        engine.check("dynamic_gi", "composite_span_p95_ms", value=20.0)
    assert len(sink.emitted) == 1

    # 解消(非超過に戻る)
    engine.check("dynamic_gi", "composite_span_p95_ms", value=10.0)
    # 再度超過したら、次は改めて発火する
    engine.check("dynamic_gi", "composite_span_p95_ms", value=25.0)
    assert len(sink.emitted) == 2


def test_console_and_file_sink_are_swappable_without_changing_engine_logic(tmp_path):
    """AlertSink実装をConsoleSinkからFileSinkへ差し替えても、しきい値判定ロジック側の
    コード変更が不要であることを確認する。
    """
    log_path = tmp_path / "alerts.log"
    for sink in (ConsoleSink(), FileSink(log_path)):
        engine = ThresholdAlertEngine(
            rules=[ThresholdRule(target="x", metric="y", threshold=0)], sinks=[sink]
        )
        fired = engine.check("x", "y", value=1)
        assert fired is not None

    assert log_path.exists()
    assert log_path.read_text(encoding="utf-8").strip() != ""


def test_lt_comparison_rule():
    sink = _RecordingSink()
    engine = ThresholdAlertEngine(
        rules=[ThresholdRule(target="x", metric="fps", threshold=30.0, comparison="lt")],
        sinks=[sink],
    )
    engine.check("x", "fps", value=60.0)
    assert sink.emitted == []
    engine.check("x", "fps", value=15.0)
    assert len(sink.emitted) == 1
