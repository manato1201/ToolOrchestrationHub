"""hub/tool_state.py(ツールの状態判定。UI改善 U1/U2)のテスト。"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from hub.alert_aggregator import AlertRecord, Severity, health_check_alert_id
from hub.registry import ToolCategory, ToolEntry, TransportKind
from hub.tool_state import ToolState, derive_tool_state, state_glyph, state_label, state_rank


def _entry(category: ToolCategory = ToolCategory.MONITORED, tool_id: str = "dev_rag_environment") -> ToolEntry:
    return ToolEntry(
        tool_id=tool_id,
        display_name=tool_id,
        transport=TransportKind.HTTP_BRIDGE,
        endpoint=None,
        health_check="http_bridge_check",
        category=category,
    )


def _alert(alert_id: str, severity: Severity = Severity.WARN, tool_id: str = "dev_rag_environment") -> AlertRecord:
    return AlertRecord(
        alert_id=alert_id,
        source_tool_id=tool_id,
        severity=severity,
        message="m",
        first_seen_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
    )


def test_up_without_alerts_is_ok():
    assert derive_tool_state(_entry(), is_up=True, open_alerts=[]) is ToolState.OK


def test_down_result_is_down_even_without_alerts_yet():
    assert derive_tool_state(_entry(), is_up=False, open_alerts=[]) is ToolState.DOWN


def test_open_liveness_alert_is_down_when_no_fresh_result():
    liveness = _alert(health_check_alert_id("dev_rag_environment"), Severity.CRITICAL)
    assert derive_tool_state(_entry(), is_up=None, open_alerts=[liveness]) is ToolState.DOWN


def test_fresh_up_result_wins_over_a_stale_liveness_alert():
    """復旧直後、解消待ちの古いliveness alertが残っていても、新しい結果(up)を信じる。"""
    liveness = _alert(health_check_alert_id("dev_rag_environment"), Severity.CRITICAL)
    assert derive_tool_state(_entry(), is_up=True, open_alerts=[liveness]) is ToolState.OK


def test_other_open_alert_makes_a_live_tool_warn_even_when_critical():
    """視覚回帰の失敗(critical)のようにツールは動いている場合、「停止」ではなく「警告」にする。"""
    failure = _alert("dev_rag_environment:abcd", Severity.CRITICAL)
    assert derive_tool_state(_entry(), is_up=True, open_alerts=[failure]) is ToolState.WARN


def test_no_signal_and_no_alerts_is_unknown():
    assert derive_tool_state(_entry(), is_up=None, open_alerts=[]) is ToolState.UNKNOWN


def test_excluded_category_is_always_excluded():
    entry = _entry(ToolCategory.EXCLUDED)
    assert derive_tool_state(entry, is_up=None, open_alerts=[_alert("x:1")]) is ToolState.EXCLUDED


def test_history_mode_treats_no_open_alerts_as_ok():
    """履歴の再現では死活監視の結果が残っていないため、未解消アラートが無ければ正常とみなす。"""
    state = derive_tool_state(_entry(), is_up=None, open_alerts=[], assume_ok_without_alerts=True)
    assert state is ToolState.OK


def test_history_mode_still_reports_open_alerts():
    liveness = _alert(health_check_alert_id("dev_rag_environment"), Severity.CRITICAL)
    assert (
        derive_tool_state(_entry(), is_up=None, open_alerts=[liveness], assume_ok_without_alerts=True)
        is ToolState.DOWN
    )


@pytest.mark.parametrize("state", list(ToolState))
def test_every_state_has_a_text_label_and_a_glyph_so_color_is_never_the_only_cue(state):
    """色を消しても状態が分かる(設計書の検証チェックリスト)。ラベルと記号が全状態に定義されている。"""
    assert state_label(state)
    assert state_glyph(state)
    assert not state_label(state).isascii()  # 日本語ラベル


def test_state_glyphs_are_all_distinct_and_problems_sort_first():
    glyphs = [state_glyph(s) for s in ToolState]
    assert len(set(glyphs)) == len(glyphs)
    assert state_rank(ToolState.DOWN) < state_rank(ToolState.WARN) < state_rank(ToolState.OK)
