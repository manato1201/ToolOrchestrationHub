"""hub/overview.py と hub/alert_history.py のテスト。

設計書(IMPROVEMENT_DESIGN_2026-10)の検証チェックリスト
「スライダーで過去の時刻に動かしたとき、状態が当時のアラート履歴と一致する」「20件でも崩れない」を
純関数のレベルで確認する。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from hub.alert_aggregator import AlertRecord, Severity, health_check_alert_id
from hub.alert_history import build_timeline, parse_at
from hub.health.base import HealthResult
from hub.overview import build_overview, format_age_ja, format_latency_ms
from hub.registry import ToolCategory, ToolEntry, ToolRegistry, TransportKind

T0 = datetime(2026, 10, 6, 18, 0, tzinfo=timezone.utc)


def _entry(tool_id: str, category: ToolCategory = ToolCategory.MONITORED) -> ToolEntry:
    return ToolEntry(
        tool_id=tool_id,
        display_name=tool_id,
        transport=TransportKind.HTTP_BRIDGE,
        endpoint=None,
        health_check="http_bridge_check",
        category=category,
    )


def _alert(tool_id: str, *, opened, resolved=None, alert_id=None, severity=Severity.WARN, count=1) -> AlertRecord:
    return AlertRecord(
        alert_id=alert_id or f"{tool_id}:sig",
        source_tool_id=tool_id,
        severity=severity,
        message=f"{tool_id} alert",
        first_seen_at=opened,
        resolved_at=resolved,
        occurrence_count=count,
    )


def _states(overview: dict) -> dict[str, str]:
    return {t["tool_id"]: t["state"] for t in overview["tools"]}


def test_live_overview_combines_health_results_and_open_alerts():
    entries = [_entry("a"), _entry("b"), _entry("c"), _entry("d", ToolCategory.EXCLUDED)]
    results = {"a": HealthResult(is_up=True, latency_ms=42.0), "b": HealthResult(is_up=True, latency_ms=5.0), "c": HealthResult(is_up=False)}
    alerts = [_alert("b", opened=T0, severity=Severity.WARN)]

    overview = build_overview(entries, alerts=alerts, results=results, ages={"a": 3.0, "c": 200.0})

    assert overview["mode"] == "live"
    assert _states(overview) == {"a": "ok", "b": "warn", "c": "down", "d": "excluded"}
    by_id = {t["tool_id"]: t for t in overview["tools"]}
    assert by_id["a"]["latency_text"] == "42 ms"
    assert by_id["b"]["latency_text"] == "5.0 ms"
    assert by_id["a"]["last_signal_text"] == "最終応答 たった今"
    assert by_id["c"]["last_signal_text"] == "最終応答 3分前"
    assert by_id["d"]["last_signal_text"] is None


def test_summary_counts_headline_and_bar_segments():
    entries = [_entry(f"t{i}") for i in range(12)]
    results = {f"t{i}": HealthResult(is_up=True, latency_ms=1.0) for i in range(12)}
    alerts = [_alert("t0", opened=T0)]

    summary = build_overview(entries, alerts=alerts, results=results)["summary"]

    assert summary["total"] == 12
    assert summary["counts"]["ok"] == 11
    assert summary["counts"]["warn"] == 1
    # 設計書の見出し例「稼働 11 · 警告 1」。0件の状態は出さない
    assert [(h["label"], h["count"]) for h in summary["headline"]] == [("稼働", 11), ("警告", 1)]
    # 積み上げバーは「問題があるものが左」。割合の合計はおよそ100
    assert [s["state"] for s in summary["segments"]] == ["warn", "ok"]
    assert sum(s["percent"] for s in summary["segments"]) == pytest.approx(100.0, abs=0.2)


def test_tools_without_any_signal_are_reported_as_unknown_not_ok():
    overview = build_overview([_entry("a")], alerts=[], results={})
    assert _states(overview) == {"a": "unknown"}
    assert overview["all_normal"] is True  # 「異常は検知されていない」であり、全て健全という主張ではない


def test_recent_alerts_are_newest_first_and_limited_to_three():
    entries = [_entry("a")]
    alerts = [
        _alert("a", opened=T0 + timedelta(minutes=i), resolved=(T0 + timedelta(minutes=i, seconds=30)) if i < 2 else None, alert_id=f"a:{i}")
        for i in range(5)
    ]
    recent = build_overview(entries, alerts=alerts, results={})["recent_alerts"]

    assert [r["alert_id"] for r in recent] == ["a:4", "a:3", "a:2"]
    assert all(r["status"] == "open" for r in recent)
    assert recent[0]["symbol"]  # 記号と色が付く(他の場所と同じ表現)


def test_overview_exposes_lifecycle_keys_so_a_recurrence_is_distinguishable():
    first = _alert("a", opened=T0, resolved=T0 + timedelta(minutes=5), alert_id="a:x")
    recurrence = _alert("a", opened=T0 + timedelta(minutes=10), alert_id="a:x", count=2)
    overview = build_overview([_entry("a")], alerts=[first, recurrence], results={})
    assert overview["open_alert_keys"] == [f"a:x@{recurrence.first_seen_at.isoformat()}"]


# ---- 履歴(スライダー)の再現 ----

def _history_fixture():
    """a: 18:10に停止 → 18:40に復旧、b: 18:30から警告(まだ未解消)。"""
    entries = [_entry("a"), _entry("b"), _entry("c")]
    alerts = [
        _alert("a", opened=T0 + timedelta(minutes=10), resolved=T0 + timedelta(minutes=40), alert_id=health_check_alert_id("a"), severity=Severity.CRITICAL),
        _alert("b", opened=T0 + timedelta(minutes=30), alert_id="b:thr"),
    ]
    return entries, alerts


def test_history_reproduces_the_state_at_each_moment_from_alert_history():
    entries, alerts = _history_fixture()

    def at(minutes):
        return _states(build_overview(entries, alerts=alerts, at=T0 + timedelta(minutes=minutes)))

    assert at(5) == {"a": "ok", "b": "ok", "c": "ok"}  # 何も起きる前
    assert at(15) == {"a": "down", "b": "ok", "c": "ok"}  # aが停止中
    assert at(35) == {"a": "down", "b": "warn", "c": "ok"}  # bの警告も加わる
    assert at(45) == {"a": "ok", "b": "warn", "c": "ok"}  # aは復旧、bは継続


def test_history_boundaries_follow_the_half_open_interval():
    entries, alerts = _history_fixture()
    opened = T0 + timedelta(minutes=10)
    resolved = T0 + timedelta(minutes=40)

    assert _states(build_overview(entries, alerts=alerts, at=opened))["a"] == "down"
    assert _states(build_overview(entries, alerts=alerts, at=opened - timedelta(microseconds=1)))["a"] == "ok"
    assert _states(build_overview(entries, alerts=alerts, at=resolved))["a"] == "ok"
    assert _states(build_overview(entries, alerts=alerts, at=resolved - timedelta(microseconds=1)))["a"] == "down"


def test_history_ignores_live_health_results_and_ages():
    entries, alerts = _history_fixture()
    results = {"a": HealthResult(is_up=False), "b": HealthResult(is_up=True, latency_ms=9.0), "c": HealthResult(is_up=True, latency_ms=1.0)}
    overview = build_overview(entries, alerts=alerts, results=results, ages={"a": 1.0}, at=T0 + timedelta(minutes=5))

    assert overview["mode"] == "history"
    assert overview["at"] == (T0 + timedelta(minutes=5)).isoformat()
    assert _states(overview) == {"a": "ok", "b": "ok", "c": "ok"}  # ライブの結果は混ぜない
    assert all(t["latency_text"] is None and t["last_signal_text"] is None for t in overview["tools"])


def test_history_recent_alerts_only_include_alerts_seen_by_then_with_status_at_that_time():
    entries, alerts = _history_fixture()
    recent = build_overview(entries, alerts=alerts, at=T0 + timedelta(minutes=45))["recent_alerts"]

    by_id = {r["alert_id"]: r["status"] for r in recent}
    assert by_id[health_check_alert_id("a")] == "resolved"  # 18:45時点では解消済み
    assert by_id["b:thr"] == "open"

    early = build_overview(entries, alerts=alerts, at=T0 + timedelta(minutes=15))["recent_alerts"]
    assert [r["alert_id"] for r in early] == [health_check_alert_id("a")]  # bの発生(18:30)はまだ先


def test_overview_scales_to_twenty_tools_without_changing_shape():
    """12ツールが増えても崩れない(設計書の検証: 20件で確認)。"""
    entries = [_entry(f"tool_{i:02d}") for i in range(20)]
    results = {e.tool_id: HealthResult(is_up=True, latency_ms=float(i)) for i, e in enumerate(entries)}
    overview = build_overview(entries, alerts=[_alert("tool_03", opened=T0)], results=results)

    assert len(overview["tools"]) == 20
    assert overview["summary"]["total"] == 20
    assert all(1 <= len(t["symbol"]) <= 2 for t in overview["tools"])
    assert all(t["color"].startswith("#") for t in overview["tools"])


def test_shipped_registry_builds_an_overview_for_all_12_tools_with_isolation_labels():
    registry = ToolRegistry.load()
    overview = build_overview(registry.all(), alerts=[], results={})
    assert len(overview["tools"]) == 12
    assert all(t["isolation_label"] != "未設定" for t in overview["tools"])


# ---- 表示用の整形 ----

@pytest.mark.parametrize(
    "seconds,expected",
    [(0, "たった今"), (9, "たった今"), (10, "10秒前"), (59, "59秒前"), (60, "1分前"), (3599, "59分前"), (3600, "1時間前"), (86399, "23時間前"), (86400, "1日前"), (-5, "たった今")],
)
def test_format_age_ja(seconds, expected):
    assert format_age_ja(seconds) == expected


def test_format_latency_ms():
    assert format_latency_ms(None) is None
    assert format_latency_ms(4.26) == "4.3 ms"
    assert format_latency_ms(42.4) == "42 ms"


# ---- hub/alert_history.py ----

def test_parse_at_accepts_z_suffix_offsets_and_naive_values():
    assert parse_at("2026-10-06T18:00:00Z") == T0
    assert parse_at("2026-10-07T03:00:00+09:00") == T0
    assert parse_at("2026-10-06T18:00:00") == T0  # タイムゾーン無しはUTC
    with pytest.raises(ValueError):
        parse_at("not-a-time")


def test_timeline_range_and_events_are_ordered():
    _, alerts = _history_fixture()
    now = T0 + timedelta(hours=2)
    timeline = build_timeline(alerts, now=now)

    assert timeline["start"] == (T0 + timedelta(minutes=10)).isoformat()
    assert timeline["end"] == now.isoformat()
    assert [(e["kind"], e["alert_id"]) for e in timeline["events"]] == [
        ("opened", health_check_alert_id("a")),
        ("opened", "b:thr"),
        ("resolved", health_check_alert_id("a")),
    ]
    assert timeline["truncated"] is False


def test_timeline_without_history_has_no_start():
    timeline = build_timeline([], now=T0)
    assert timeline["start"] is None
    assert timeline["events"] == []


def test_timeline_is_capped_to_the_newest_events():
    alerts = [_alert("a", opened=T0 + timedelta(minutes=i), resolved=T0 + timedelta(minutes=i, seconds=30), alert_id=f"a:{i}") for i in range(10)]
    timeline = build_timeline(alerts, now=T0 + timedelta(hours=1), limit=6)

    assert len(timeline["events"]) == 6
    assert timeline["truncated"] is True
    assert timeline["start"] == timeline["events"][0]["at"]
