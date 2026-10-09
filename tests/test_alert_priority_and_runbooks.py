"""hub/alert_priority.py(H2: 見る順番の補助)と hub/runbooks.py(H6: 運用手順書)のテスト。"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from hub.alert_aggregator import AlertRecord, Severity, health_check_alert_id
from hub.alert_priority import AlertPriority, RuleBasedPriorityClassifier
from hub.registry import ToolCategory
from hub.runbooks import (
    ALL_KINDS,
    KIND_ASSET_INSIGHT_FLAG,
    KIND_GENERIC,
    KIND_LIVENESS_DOWN,
    KIND_PROFILING_THRESHOLD,
    KIND_VISUAL_REGRESSION_FAILURE,
    RunbookCatalog,
    RunbookError,
    kind_for,
)

NOW = datetime(2026, 10, 7, tzinfo=timezone.utc)


def _alert(
    *,
    tool_id="profiling_tool",
    alert_id=None,
    severity=Severity.CRITICAL,
    message="gpu frame budget exceeded: 21.4ms",
    count=1,
) -> AlertRecord:
    return AlertRecord(
        alert_id=alert_id or f"{tool_id}:sig",
        source_tool_id=tool_id,
        severity=severity,
        message=message,
        first_seen_at=NOW,
        occurrence_count=count,
    )


# ---- 優先度の補助(H2) ----

def test_critical_alert_with_a_clear_message_is_urgent():
    result = RuleBasedPriorityClassifier().assess(_alert(severity=Severity.CRITICAL), tool_category=ToolCategory.MONITORED)
    assert result.priority is AlertPriority.URGENT
    assert result.label == "緊急"
    assert result.score >= 0.7
    assert any("重大度" in r for r in result.reasons)


def test_warn_alert_is_normal():
    result = RuleBasedPriorityClassifier().assess(_alert(severity=Severity.WARN))
    assert result.priority is AlertPriority.NORMAL
    assert result.label == "通常"


def test_message_without_a_clue_is_insufficient_information():
    for message in ("", "down", "profiling alert: unknown"):
        result = RuleBasedPriorityClassifier().assess(_alert(message=message))
        assert result.priority is AlertPriority.INSUFFICIENT, message
        assert result.label == "情報不足"


def test_recurrence_raises_the_score():
    classifier = RuleBasedPriorityClassifier()
    once = classifier.assess(_alert(severity=Severity.WARN, count=1))
    third = classifier.assess(_alert(severity=Severity.WARN, count=3))
    assert third.score > once.score
    assert any("再発" in r for r in third.reasons)


def test_indirect_metric_from_observed_only_tool_is_ranked_lower():
    classifier = RuleBasedPriorityClassifier()
    direct = classifier.assess(_alert(severity=Severity.CRITICAL), tool_category=ToolCategory.MONITORED)
    indirect = classifier.assess(_alert(severity=Severity.CRITICAL), tool_category=ToolCategory.OBSERVED_ONLY)
    assert indirect.score < direct.score
    assert indirect.priority is AlertPriority.NORMAL  # 間接指標のcriticalは「緊急」までは上げない


def test_liveness_down_is_not_downgraded_for_observed_only_tools():
    liveness = _alert(tool_id="learning_qt", alert_id=health_check_alert_id("learning_qt"), message="learning_qt liveness check: down")
    result = RuleBasedPriorityClassifier().assess(liveness, tool_category=ToolCategory.OBSERVED_ONLY)
    assert result.priority is AlertPriority.URGENT


def test_score_is_clamped_and_is_a_hint_not_a_probability():
    result = RuleBasedPriorityClassifier().assess(
        _alert(severity=Severity.CRITICAL, count=9, alert_id=health_check_alert_id("profiling_tool"))
    )
    assert 0.0 <= result.score <= 1.0


# ---- 運用手順書(H6) ----

def test_shipped_runbooks_cover_every_alert_kind_with_all_three_sections():
    catalog = RunbookCatalog.load()
    assert set(ALL_KINDS) <= set(catalog.kinds())
    for kind in ALL_KINDS:
        runbook = catalog.get(kind)
        assert runbook.title
        assert runbook.do and runbook.dont and runbook.deliverable  # やること / やらないこと / 成果物


def test_kind_is_decided_from_the_alert_alone():
    assert kind_for(_alert(tool_id="dev_rag_environment", alert_id=health_check_alert_id("dev_rag_environment"))) == KIND_LIVENESS_DOWN
    assert kind_for(_alert(tool_id="profiling_tool", alert_id="profiling_tool:abc")) == KIND_PROFILING_THRESHOLD
    assert kind_for(_alert(tool_id="visual_regression_qa_tool", alert_id="visual_regression_qa_tool:abc")) == KIND_VISUAL_REGRESSION_FAILURE
    assert kind_for(_alert(tool_id="asset_data_insight_suite", alert_id="asset_data_insight_suite:abc")) == KIND_ASSET_INSIGHT_FLAG
    assert kind_for(_alert(tool_id="something_else", alert_id="something_else:abc")) == KIND_GENERIC


def test_liveness_alert_of_profiling_tool_uses_the_liveness_runbook_not_the_threshold_one():
    alert = _alert(tool_id="profiling_tool", alert_id=health_check_alert_id("profiling_tool"))
    assert RunbookCatalog.load().for_alert(alert).kind == KIND_LIVENESS_DOWN


def test_liveness_runbook_keeps_the_hub_monitoring_only_principle():
    runbook = RunbookCatalog.load().get(KIND_LIVENESS_DOWN)
    assert any("Hubから" in line and "試みない" in line for line in runbook.dont)


def test_unknown_kind_falls_back_to_generic_and_empty_catalog_returns_none():
    assert RunbookCatalog.load().for_alert(_alert(tool_id="x", alert_id="x:1")).kind == KIND_GENERIC
    assert RunbookCatalog.empty().for_alert(_alert()) is None


@pytest.mark.parametrize(
    "body",
    [
        "runbooks: []",
        "runbooks:\n  a: {title: '', do: [x], dont: [y], deliverable: [z]}",
        "runbooks:\n  a: {title: t, do: [], dont: [y], deliverable: [z]}",
        "runbooks:\n  a: {title: t, do: [x], dont: [y]}",
        "runbooks:\n  a: {title: t, do: [1], dont: [y], deliverable: [z]}",
    ],
)
def test_invalid_runbooks_file_is_rejected_with_a_clear_error(tmp_path, body):
    path = tmp_path / "runbooks.yaml"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(RunbookError):
        RunbookCatalog.load(path)


def test_broken_yaml_is_wrapped_in_runbook_error(tmp_path):
    path = tmp_path / "runbooks.yaml"
    path.write_text("runbooks: [unclosed", encoding="utf-8")
    with pytest.raises(RunbookError):
        RunbookCatalog.load(path)
