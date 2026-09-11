"""Phase1 検証チェックリスト対応テスト。"""
from __future__ import annotations

import pytest

from hub.registry import RegistryError, ToolCategory, ToolRegistry, TransportKind


def test_all_12_entries_load_without_error():
    registry = ToolRegistry.load()
    assert len(registry.all()) == 12


def test_transport_matches_inventory_table():
    registry = ToolRegistry.load()
    expected_transport = {
        "lore_desktop_and_web_system": TransportKind.RPC,
        "the_algorithm_illustrated": TransportKind.STATIC_SITE,
        "research_collector": TransportKind.CI_BATCH,
        "dev_rag_environment": TransportKind.HTTP_BRIDGE,
        "learning_qt": TransportKind.RPC,
        "asset_data_insight_suite": TransportKind.CI_BATCH,
        "sound_middleware": TransportKind.RPC,
        "visual_regression_qa_tool": TransportKind.CI_BATCH,
        "color_encyclopedia": TransportKind.STATIC_SITE,
        "vlm_auto_replay_tool": TransportKind.HTTP_BRIDGE,
        "dynamic_gi_middleware": TransportKind.RPC,
        "profiling_tool": TransportKind.HTTP_BRIDGE,
    }
    for tool_id, transport in expected_transport.items():
        entry = registry.get(tool_id)
        assert entry is not None, f"{tool_id} が見つかりません"
        assert entry.transport is transport


def test_excluded_tool_is_not_in_monitored_loop():
    registry = ToolRegistry.load()
    monitored_ids = {e.tool_id for e in registry.monitored()}
    assert "color_encyclopedia" not in monitored_ids
    assert registry.get("color_encyclopedia").category is ToolCategory.EXCLUDED


def test_observed_only_tools_are_not_in_monitored_loop():
    registry = ToolRegistry.load()
    monitored_ids = {e.tool_id for e in registry.monitored()}
    for tool_id in ("lore_desktop_and_web_system", "learning_qt", "sound_middleware"):
        assert tool_id not in monitored_ids
        assert registry.get(tool_id).category is ToolCategory.OBSERVED_ONLY


def test_reload_reflects_registry_changes(tmp_path):
    original = ToolRegistry.load()
    path = tmp_path / "registry.yaml"
    path.write_text(
        """
tools:
  - tool_id: sample_tool
    display_name: "Sample"
    transport: http_bridge
    endpoint: "http://127.0.0.1:9999/health"
    health_check: http_bridge_check
    category: monitored
""",
        encoding="utf-8",
    )
    original.reload(path)
    assert [e.tool_id for e in original.all()] == ["sample_tool"]


def test_reload_without_explicit_path_uses_original_source_path(tmp_path):
    path = tmp_path / "registry.yaml"
    path.write_text(
        """
tools:
  - tool_id: tool_a
    display_name: "A"
    transport: static_site
    endpoint: null
    health_check: null
    category: excluded
""",
        encoding="utf-8",
    )
    registry = ToolRegistry.load(path)
    assert registry.source_path == path

    path.write_text(
        """
tools:
  - tool_id: tool_b
    display_name: "B"
    transport: static_site
    endpoint: null
    health_check: null
    category: excluded
""",
        encoding="utf-8",
    )
    registry.reload()  # pathを省略 -> source_pathを再読込する
    assert [e.tool_id for e in registry.all()] == ["tool_b"]


def test_has_changed_on_disk_detects_mtime_change(tmp_path):
    import time

    path = tmp_path / "registry.yaml"
    content = """
tools:
  - tool_id: tool_a
    display_name: "A"
    transport: static_site
    endpoint: null
    health_check: null
    category: excluded
"""
    path.write_text(content, encoding="utf-8")
    registry = ToolRegistry.load(path)
    assert registry.has_changed_on_disk() is False

    time.sleep(0.05)
    path.write_text(content, encoding="utf-8")  # 内容は同じでもmtimeは更新される
    assert registry.has_changed_on_disk() is True

    registry.reload()
    assert registry.has_changed_on_disk() is False


def test_load_wraps_yaml_syntax_error_as_registry_error(tmp_path):
    """書き換え途中の不正なYAML(構文エラー)もRegistryErrorに統一されることを確認する。

    呼び出し側(ホットリロードのwatchループ/reloadエンドポイント)がRegistryErrorだけを
    捕まえればよいようにするための契約。
    """
    path = tmp_path / "registry.yaml"
    path.write_text("not: [valid, yaml, syntax", encoding="utf-8")
    with pytest.raises(RegistryError):
        ToolRegistry.load(path)
