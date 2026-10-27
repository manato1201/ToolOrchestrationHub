"""台帳の「手の台帳」項目(説明・懸念・やり残し・依存先)と、障害の波及(原因の木)のテスト。

IMPROVEMENT_DESIGN_2026-10 の追補(Z16 / X13)。依存は台帳の記述から読み取れる関係だけで、実測ではない。
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from hub.alert_aggregator import AlertRecord, Severity
from hub.health.base import HealthResult
from hub.health.runner import LivenessMonitor
from hub.overview import build_overview
from hub.registry import RegistryError, ToolCategory, ToolEntry, ToolRegistry, TransportKind


def _raw(tool_id, **extra):
    base = {
        "tool_id": tool_id,
        "display_name": tool_id,
        "transport": "static_site",
        "health_check": None,
        "category": "excluded",
    }
    base.update(extra)
    return base


def _registry(*raws):
    return ToolRegistry([ToolEntry.from_dict(r) for r in raws])


def _entry(tool_id, depends_on=(), category=ToolCategory.MONITORED):
    return ToolEntry(
        tool_id=tool_id,
        display_name=tool_id,
        transport=TransportKind.HTTP_BRIDGE,
        endpoint=None,
        health_check="http_bridge_check",
        category=category,
        depends_on=tuple(depends_on),
    )


# ---------------------------------------------------------------- 項目の検証

def test_new_ledger_fields_are_optional_and_default_to_empty():
    entry = ToolEntry.from_dict(_raw("a"))
    assert entry.description is None
    assert entry.concerns == () and entry.todo == () and entry.depends_on == ()


def test_ledger_fields_are_parsed():
    entry = ToolEntry.from_dict(
        _raw("a", description="説明", concerns=["懸念1"], todo=["やること1", "やること2"], depends_on=["b"])
    )
    assert entry.description == "説明"
    assert entry.concerns == ("懸念1",)
    assert entry.todo == ("やること1", "やること2")
    assert entry.depends_on == ("b",)


@pytest.mark.parametrize("key", ["concerns", "todo", "depends_on"])
@pytest.mark.parametrize("value", ["not a list", [1, 2], {"a": 1}])
def test_list_fields_must_be_lists_of_strings(key, value):
    with pytest.raises(RegistryError, match=key):
        ToolEntry.from_dict(_raw("a", **{key: value}))


def test_description_must_be_a_string():
    with pytest.raises(RegistryError, match="description"):
        ToolEntry.from_dict(_raw("a", description=["x"]))


# ---------------------------------------------------------------- 依存関係の検証

def test_depends_on_must_point_at_a_registered_tool():
    with pytest.raises(RegistryError, match="台帳にありません"):
        _registry(_raw("a", depends_on=["ghost"]))


def test_a_tool_cannot_depend_on_itself():
    with pytest.raises(RegistryError, match="自分自身"):
        _registry(_raw("a", depends_on=["a"]))


def test_dependency_cycles_are_rejected_with_the_cycle_shown():
    with pytest.raises(RegistryError, match="循環") as excinfo:
        _registry(_raw("a", depends_on=["b"]), _raw("b", depends_on=["c"]), _raw("c", depends_on=["a"]))
    assert "a -> b -> c -> a" in str(excinfo.value) or "b -> c -> a -> b" in str(excinfo.value) or "c -> a -> b -> c" in str(excinfo.value)


def test_diamond_dependencies_are_not_mistaken_for_cycles():
    registry = _registry(
        _raw("top", depends_on=["left", "right"]),
        _raw("left", depends_on=["base"]),
        _raw("right", depends_on=["base"]),
        _raw("base"),
    )
    assert len(registry.all()) == 4


def test_hot_reload_rejects_a_broken_dependency_and_keeps_the_previous_registry(tmp_path):
    path = tmp_path / "registry.yaml"
    good = """
tools:
  - {tool_id: a, display_name: A, transport: static_site, health_check: null, category: excluded}
  - {tool_id: b, display_name: B, transport: static_site, health_check: null, category: excluded, depends_on: [a]}
"""
    path.write_text(good, encoding="utf-8")
    registry = ToolRegistry.load(path)

    path.write_text(good.replace("depends_on: [a]", "depends_on: [zzz]"), encoding="utf-8")
    with pytest.raises(RegistryError):
        registry.reload()

    assert registry.get("b").depends_on == ("a",)  # 壊れた台帳に置き換わらない


# ---------------------------------------------------------------- 同梱の台帳

def test_shipped_registry_describes_every_tool():
    registry = ToolRegistry.load()
    assert [e.tool_id for e in registry.all() if not e.description] == []


def test_shipped_dependencies_are_the_documented_ones_and_acyclic():
    registry = ToolRegistry.load()  # 読み込めた時点で、存在・自己参照・循環の検証を通っている
    edges = {e.tool_id: set(e.depends_on) for e in registry.all() if e.depends_on}
    assert edges == {
        "lore_desktop_and_web_system": {"dev_rag_environment"},
        "vlm_auto_replay_tool": {"dev_rag_environment", "profiling_tool"},
        "dynamic_gi_middleware": {"profiling_tool"},
    }


def test_provisional_notes_in_comments_are_structured_as_todo():
    registry = ToolRegistry.load()
    assert any("暫定" in t for t in registry.get("dev_rag_environment").todo)
    assert any("要判断" in c for c in registry.get("vlm_auto_replay_tool").concerns)


# ---------------------------------------------------------------- 原因の木

def _down(tool_id):
    return {tool_id: HealthResult(is_up=False)}


def test_impact_tree_lists_tools_that_depend_on_a_stopped_tool():
    entries = [_entry("base"), _entry("mid", ["base"]), _entry("leaf", ["mid"]), _entry("other")]
    overview = build_overview(entries, alerts=[], results={**_down("base"), "mid": HealthResult(is_up=True), "leaf": HealthResult(is_up=True), "other": HealthResult(is_up=True)})

    (tree,) = overview["impact_trees"]
    assert tree["root"]["tool_id"] == "base"
    assert [c["tool"]["tool_id"] for c in tree["children"]] == ["mid"]
    assert [c["tool"]["tool_id"] for c in tree["children"][0]["children"]] == ["leaf"]


def test_the_root_is_the_stopped_tool_that_does_not_itself_depend_on_a_stopped_one():
    entries = [_entry("base"), _entry("mid", ["base"])]
    overview = build_overview(entries, alerts=[], results={**_down("base"), **_down("mid")})

    assert [t["root"]["tool_id"] for t in overview["impact_trees"]] == ["base"]  # midは根ではなく、baseの木の中


def test_no_tree_without_a_stopped_tool_or_without_dependents():
    entries = [_entry("base"), _entry("mid", ["base"]), _entry("solo")]
    healthy = {e.tool_id: HealthResult(is_up=True) for e in entries}
    assert build_overview(entries, alerts=[], results=healthy)["impact_trees"] == []
    # 停止していても、依存しているツールが無ければ木にならない
    assert build_overview(entries, alerts=[], results={**healthy, **_down("solo")})["impact_trees"] == []


def test_impact_tree_depth_is_limited():
    entries = [_entry("t0")] + [_entry(f"t{i}", [f"t{i - 1}"]) for i in range(1, 7)]
    overview = build_overview(entries, alerts=[], results={"t0": HealthResult(is_up=False)})

    node, depth = overview["impact_trees"][0], 0
    while node["children"]:
        node = node["children"][0]
        depth += 1
    assert depth == 3


def test_rows_carry_dependency_refs_with_current_states_for_the_detail_card():
    entries = [_entry("base"), _entry("user", ["base"])]
    overview = build_overview(entries, alerts=[], results={**_down("base"), "user": HealthResult(is_up=True)})
    rows = {r["tool_id"]: r for r in overview["tools"]}

    assert [d["tool_id"] for d in rows["user"]["depends_on"]] == ["base"]
    assert rows["user"]["depends_on"][0]["state_label"] == "停止"
    assert [d["tool_id"] for d in rows["base"]["dependents"]] == ["user"]


def test_history_mode_also_builds_the_tree_from_the_alert_history():
    from hub.alert_aggregator import health_check_alert_id

    entries = [_entry("base"), _entry("user", ["base"])]
    opened = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    alert = AlertRecord(health_check_alert_id("base"), "base", Severity.CRITICAL, "base liveness check: down", opened)

    before = build_overview(entries, alerts=[alert], at=datetime(2026, 10, 1, 11, 0, tzinfo=timezone.utc))
    during = build_overview(entries, alerts=[alert], at=datetime(2026, 10, 1, 13, 0, tzinfo=timezone.utc))
    assert before["impact_trees"] == []
    assert [t["root"]["tool_id"] for t in during["impact_trees"]] == ["base"]


# ---------------------------------------------------------------- 「確認中」(スケルトン)

def test_monitored_tool_not_yet_checked_is_shown_as_checking_not_unknown():
    entries = [_entry("web"), _entry("passive", category=ToolCategory.OBSERVED_ONLY)]
    overview = build_overview(entries, alerts=[], results={}, checked={"web": False, "passive": False})
    rows = {r["tool_id"]: r for r in overview["tools"]}

    assert rows["web"]["checking"] is True
    assert rows["web"]["state"] == "unknown"  # 状態そのものは「未確認」のまま(正常とは言わない)
    assert rows["passive"]["checking"] is False  # 受動監視は、確認しに行く相手がいない


def test_checking_ends_once_the_tool_has_been_checked_and_is_off_without_the_info():
    entries = [_entry("web")]
    assert build_overview(entries, alerts=[], results={}, checked={"web": True})["tools"][0]["checking"] is False
    assert build_overview(entries, alerts=[], results={})["tools"][0]["checking"] is False  # checked未指定


def test_history_mode_never_shows_checking():
    entries = [_entry("web")]
    overview = build_overview(entries, alerts=[], checked={"web": False}, at=datetime(2026, 10, 1, tzinfo=timezone.utc))
    assert overview["tools"][0]["checking"] is False


@pytest.mark.asyncio
async def test_monitor_reports_checked_after_the_first_poll():
    registry = ToolRegistry.load()
    monitor = LivenessMonitor(registry)
    entry = registry.get("sound_middleware")  # 受動監視

    assert monitor.has_checked("sound_middleware") is False
    monitor.record_heartbeat("sound_middleware")
    await monitor.check_once(entry)
    assert monitor.has_checked("sound_middleware") is True


# ---------------------------------------------------------------- アプリ内通知・タブ名のバッジ用

def test_overview_exposes_a_brief_of_open_alerts_for_toasts_and_the_tab_badge():
    entries = [_entry("a")]
    opened = datetime(2026, 10, 1, tzinfo=timezone.utc)
    alerts = [
        AlertRecord("a:1", "a", Severity.CRITICAL, "m" * 500, opened),
        AlertRecord("a:2", "a", Severity.WARN, "resolved one", opened, resolved_at=opened),
    ]
    brief = build_overview(entries, alerts=alerts)["open_alerts"]

    assert [b["severity"] for b in brief] == ["critical"]  # 未解消だけ
    assert len(brief[0]["message"]) == 120  # 長い本文は切る
    assert brief[0]["source"] == "a" and brief[0]["severity_glyph"] == "■" and brief[0]["key"].startswith("a:1@")


def test_recent_alerts_tell_whether_the_source_tool_has_a_detail_card():
    entries = [_entry("known")]
    opened = datetime(2026, 10, 1, tzinfo=timezone.utc)
    alerts = [AlertRecord("known:1", "known", Severity.WARN, "m", opened), AlertRecord("ext:1", "external", Severity.WARN, "m", opened)]
    recent = {r["source_tool_id"]: r["has_detail"] for r in build_overview(entries, alerts=alerts)["recent_alerts"]}
    assert recent == {"known": True, "external": False}
