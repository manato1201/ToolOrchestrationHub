"""Phase4 検証チェックリスト対応テスト。"""
from __future__ import annotations

import json

from hub.alert_aggregator import AlertAggregator, normalize_from_health_check
from hub.dashboard import data_sources
from hub.health.base import HealthResult
from hub.health.runner import LivenessMonitor
from hub.registry import ToolRegistry


def test_load_registry_status_mirrors_all_entries_without_recomputation():
    registry = ToolRegistry.load()
    rows = data_sources.load_registry_status(registry)
    assert len(rows) == 12
    for row in rows:
        assert row["is_up"] is None  # monitorなしなら未取得のまま。ここで新規判定はしない


def test_load_registry_status_reflects_monitor_snapshot():
    registry = ToolRegistry.load()
    monitor = LivenessMonitor(registry)
    monitor._results["dev_rag_environment"] = HealthResult(is_up=True, latency_ms=5.0)

    rows = data_sources.load_registry_status(registry, monitor)
    row = next(r for r in rows if r["tool_id"] == "dev_rag_environment")
    assert row["is_up"] is True
    assert row["latency_ms"] == 5.0


def test_load_alert_summary_reflects_aggregator_state():
    aggregator = AlertAggregator()
    aggregator.ingest(normalize_from_health_check("profiling_tool", HealthResult(is_up=False)))

    rows = data_sources.load_alert_summary(aggregator)
    assert len(rows) == 1
    assert rows[0]["status"] == "open"
    assert rows[0]["source_tool_id"] == "profiling_tool"


def test_load_asset_insight_manifest_reads_existing_file_without_recalculation(tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_content = {"entries": [{"asset_id": "x", "severity": "warn"}]}
    manifest_path.write_text(json.dumps(manifest_content), encoding="utf-8")

    result = data_sources.load_asset_insight_manifest(str(manifest_path))
    assert result["available"] is True
    assert result["data"] == manifest_content  # 加工せずそのまま
    assert result["source"] == str(manifest_path)
    # 画面にそのまま出す前提のため、生のUNIX epoch floatではなく人間可読な文字列であること
    assert isinstance(result["loaded_at"], str)
    assert result["loaded_at"]


def test_load_asset_insight_manifest_missing_file_does_not_raise(tmp_path):
    missing_path = tmp_path / "does_not_exist.json"
    result = data_sources.load_asset_insight_manifest(str(missing_path))
    assert result["available"] is False
    assert result["data"] is None


def test_sample_artifacts_shipped_with_repo_are_readable():
    """registry.yamlのcheck_paramsが指すサンプルアーティファクトが実際に読み込めることを確認する。"""
    from pathlib import Path

    project_root = Path(__file__).parent.parent
    registry = ToolRegistry.load()

    manifest_rel = registry.get("asset_data_insight_suite").check_params["report_manifest_path"]
    vrqa_rel = registry.get("visual_regression_qa_tool").check_params["evaluation_result_path"]
    trace_rel = registry.get("profiling_tool").check_params["trace_summary_path"]

    manifest = data_sources.load_asset_insight_manifest(str(project_root / manifest_rel))
    vrqa = data_sources.load_visual_regression_evaluation_history(str(project_root / vrqa_rel))
    trace = data_sources.load_profiling_trace_summary(str(project_root / trace_rel))

    assert manifest["available"] is True
    assert vrqa["available"] is True
    assert trace["available"] is True
