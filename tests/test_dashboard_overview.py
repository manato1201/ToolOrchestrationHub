"""2026-10 UI改善(IMPROVEMENT_DESIGN / IMPROVEMENT_PLAN)のHTTPレイヤーのテスト。

概況(左=ツール一覧 / 中央=詳細・オフィス / 右=サマリ)、アラート履歴スライダー用のAPIと断片、
アラート一覧の並び・発生回数・優先度の補助・運用手順、404ページ、日本語化・状態表示の決めごと。
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import hub.dashboard.app as app_module
from hub.alert_aggregator import AlertRecord, Severity
from hub.alert_store import SqliteAlertStore
from hub.health.base import HealthResult

pytestmark = pytest.mark.usefixtures("no_real_repo_sync")

_REGISTRY = """
tools:
  - tool_id: tool_up
    display_name: "ToolUp"
    symbol: "Up"
    color: "#406d4b"
    transport: http_bridge
    endpoint: "http://127.0.0.1:1/health"
    health_check: http_bridge_check
    category: monitored
    isolation: container
    owner_rules:
      - "Hubは観察のみ"
    poll_interval_s: 3600
  - tool_id: tool_down
    display_name: "ToolDown"
    transport: http_bridge
    endpoint: "http://127.0.0.1:1/health"
    health_check: http_bridge_check
    category: monitored
    poll_interval_s: 3600
  - tool_id: profiling_tool
    display_name: "ProfilingTool"
    transport: http_bridge
    endpoint: "http://127.0.0.1:1/health"
    health_check: http_bridge_check
    category: monitored
    poll_interval_s: 3600
  - tool_id: tool_off
    display_name: "ToolOff"
    transport: static_site
    endpoint: null
    health_check: null
    category: excluded
"""


def _make_app(tmp_path, *, registry: str = _REGISTRY, **kwargs):
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(registry, encoding="utf-8")
    app = app_module.create_app(
        registry_path=str(registry_path),
        db_path=str(tmp_path / "hub_state.sqlite3"),
        profiling_traces_dir=str(tmp_path / "traces"),
        **kwargs,
    )
    return app


def _set_results(app, **results):
    for tool_id, result in results.items():
        app.state.monitor._results[tool_id] = result


def _post_alert(client, signature="gpu_budget", severity="critical", message="frame budget exceeded: 21.4ms"):
    res = client.post(
        "/api/alerts/profiling-tool",
        json={"signature": signature, "severity": severity, "message": message},
    )
    assert res.status_code == 200
    return res.json()["alert_id"]


def _rows_by_id(client):
    return {t["tool_id"]: t for t in client.get("/api/overview").json()["tools"]}


# ---------------------------------------------------------------- 概況(ライブ)

def test_overview_shows_state_with_glyph_and_japanese_label_not_color_alone(tmp_path):
    """設計書の検証: 色を消しても状態が分かる(記号 + 文字)。"""
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        _set_results(app, tool_up=HealthResult(is_up=True, latency_ms=42.0), tool_down=HealthResult(is_up=False))
        _post_alert(client, severity="warn", message="threshold crossed on profiling")
        html = client.get("/").text

    assert re.search(r'state-pill state-ok"><span class="state-glyph" aria-hidden="true">✓</span>正常', html)
    assert re.search(r'state-pill state-down"><span class="state-glyph" aria-hidden="true">■</span>停止', html)
    assert re.search(r'state-pill state-warn"><span class="state-glyph" aria-hidden="true">▲</span>警告', html)
    assert "対象外" in html


def test_overview_states_follow_health_results_and_alerts(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        _set_results(app, tool_up=HealthResult(is_up=True, latency_ms=42.0), tool_down=HealthResult(is_up=False), profiling_tool=HealthResult(is_up=True, latency_ms=3.0))
        _post_alert(client, severity="critical")
        rows = _rows_by_id(client)

    assert rows["tool_up"]["state"] == "ok"
    assert rows["tool_up"]["latency_text"] == "42 ms"
    assert rows["tool_down"]["state"] == "down"
    assert rows["profiling_tool"]["state"] == "warn"  # 生きているが、未解消のアラートがある
    assert rows["tool_off"]["state"] == "excluded"


def test_header_summary_and_default_selection_point_at_the_tool_needing_attention(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        _set_results(app, tool_up=HealthResult(is_up=True, latency_ms=1.0), tool_down=HealthResult(is_up=False), profiling_tool=HealthResult(is_up=True, latency_ms=1.0))
        overview = client.get("/api/overview").json()
        html = client.get("/").text

    assert overview["default_tool_id"] == "tool_down"  # 問題があるものを最初に開く
    assert 'data-default-tool="tool_down"' in html
    assert [(h["label"], h["count"]) for h in overview["summary"]["headline"]] == [("稼働", 2), ("停止", 1), ("対象外", 1)]


def test_tool_list_rows_use_the_shared_symbol_and_fixed_color(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        html = client.get("/").text
    assert 'style="--symbol-color: #406d4b" aria-hidden="true">Up</span>' in html


def test_detail_card_shows_isolation_owner_rules_and_connection_info(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        html = client.get("/").text
    assert "実行の隔離" in html and "コンテナ" in html
    assert "守ること" in html and "Hubは観察のみ" in html
    assert "http://127.0.0.1:1/health" in html


def test_office_view_has_one_desk_per_tool_with_text_state(tmp_path):
    """オフィス表示の状態が死活監視の結果と一致し、文字でも出ている(設計書の検証)。"""
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        _set_results(app, tool_up=HealthResult(is_up=True, latency_ms=1.0), tool_down=HealthResult(is_up=False))
        html = client.get("/").text

    assert html.count('class="office-tile"') == 4
    assert 'class="office-svg office-ok"' in html
    assert 'class="office-svg office-down"' in html
    assert 'class="office-svg office-excluded"' in html
    assert 'aria-label="ToolDown: 停止"' in html


# ---------------------------------------------------------------- アラート履歴スライダー用のAPI

def test_history_fragment_reconstructs_state_from_alert_history(tmp_path):
    """設計書の検証: スライダーで過去の時刻に動かしたとき、状態が当時のアラート履歴と一致する。"""
    now = datetime.now(timezone.utc)
    store = SqliteAlertStore(tmp_path / "hub_state.sqlite3")
    store.save(
        AlertRecord(
            alert_id="profiling_tool:old",
            source_tool_id="profiling_tool",
            severity=Severity.CRITICAL,
            message="gpu frame budget exceeded: 21.4ms",
            first_seen_at=now - timedelta(hours=3),
            resolved_at=now - timedelta(hours=1),
        )
    )
    store.close()
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        during = (now - timedelta(hours=2)).isoformat()
        after = (now - timedelta(minutes=30)).isoformat()
        before = (now - timedelta(hours=4)).isoformat()

        def state_at(at):
            tools = client.get("/api/overview", params={"at": at}).json()["tools"]
            return {t["tool_id"]: t["state"] for t in tools}["profiling_tool"]

        assert state_at(before) == "ok"
        assert state_at(during) == "warn"
        assert state_at(after) == "ok"
        assert client.get("/api/overview").json()["mode"] == "live"

        fragment = client.get("/fragments/overview", params={"at": during}).text
    assert "過去の再現" in fragment
    assert "アラート履歴からの再現です" in fragment  # 誠実な注記(P9)
    assert 'data-mode="history"' in fragment


def test_live_fragment_is_the_same_markup_as_the_page_overview(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        fragment = client.get("/fragments/overview")
        page = client.get("/").text
    assert fragment.status_code == 200
    assert 'data-mode="live"' in fragment.text
    assert 'id="overview-card"' in page and 'id="overview-card"' in fragment.text


@pytest.mark.parametrize("path", ["/api/overview", "/fragments/overview"])
def test_history_endpoints_reject_an_unparsable_time(tmp_path, path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        assert client.get(path, params={"at": "not-a-time"}).status_code == 400


def test_timeline_endpoint_reports_range_and_events(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/history/timeline").json()["start"] is None  # 履歴なし
        alert_id = _post_alert(client)
        time.sleep(0.01)
        client.post("/api/alerts/profiling-tool", json={"signature": "gpu_budget", "severity": "info", "message": "ok"})
        timeline = client.get("/api/history/timeline").json()

    assert timeline["start"] is not None
    assert [(e["kind"], e["alert_id"]) for e in timeline["events"]] == [("opened", alert_id), ("resolved", alert_id)]


def test_page_embeds_the_slider_with_its_timeline(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        empty = client.get("/").text
        _post_alert(client)
        with_history = client.get("/").text
    assert 'id="history-range"' in empty and "disabled" in empty
    assert "アラートの履歴がまだありません" in empty
    assert "スライダーを動かすと" in with_history


# ---------------------------------------------------------------- アラート一覧(2段表示・並び・補助)

def test_alert_rows_show_occurrence_count_and_open_alerts_come_first(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        first = _post_alert(client, signature="a", message="first problem is explained here")
        client.post("/api/alerts/profiling-tool", json={"signature": "a", "severity": "info", "message": "recovered"})
        _post_alert(client, signature="a", message="first problem is explained here")  # 再発
        _post_alert(client, signature="b", severity="warn", message="second problem is explained here")
        rows = client.get("/api/alerts").json()

    assert [r["status"] for r in rows] == ["open", "open", "resolved"]  # 解消済みは下
    recurrence = next(r for r in rows if r["alert_id"] == first and r["status"] == "open")
    assert recurrence["occurrence_count"] == 2
    resolved = next(r for r in rows if r["status"] == "resolved")
    assert resolved["occurrence_count"] == 1


def test_open_alerts_are_ordered_by_priority_then_newest(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        _post_alert(client, signature="warn_first", severity="warn", message="warning level message here")
        _post_alert(client, signature="crit_later", severity="critical", message="critical level message here")
        rows = client.get("/api/alerts").json()

    assert [r["priority"] for r in rows] == ["urgent", "normal"]
    assert rows[0]["priority_label"] == "緊急"
    assert rows[0]["priority_reasons"]


def test_alert_rows_carry_a_runbook_with_do_dont_deliverable(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        _post_alert(client)
        row = client.get("/api/alerts").json()[0]
        html = client.get("/").text

    assert row["runbook_kind"] == "profiling_threshold"
    assert set(row["runbook"]) >= {"title", "do", "dont", "deliverable"}
    assert "対応手順" in html and "やること" in html and "やらないこと" in html and "成果物" in html


def test_runbook_toggle_uses_down_arrow_when_closed_and_up_when_open(tmp_path):
    """開閉の矢印は下向き、開くと上向き(決めごと表 P1)。"""
    css = (app_module.BASE_DIR / "static" / "style.css").read_text(encoding="utf-8")
    assert re.search(r'\.runbook \.chev::after\s*\{\s*content: "▾";', css)
    assert re.search(r'\.runbook\[open\] \.chev::after\s*\{\s*content: "▴";', css)


class _ExplodingClassifier:
    def assess(self, alert, *, tool_category=None):
        raise RuntimeError("classifier is broken")


def test_priority_assist_failure_never_blocks_alerts_or_notifications(tmp_path, monkeypatch):
    """設計書の検証: 分類補助を外しても(壊れていても)、アラートは従来どおり通知される。"""
    opened = []

    class _Recorder:
        def notify_opened(self, alert):
            opened.append(alert.alert_id)

        def notify_resolved(self, alert):
            pass

    monkeypatch.setattr(app_module, "default_sink", lambda: _Recorder())
    app = _make_app(tmp_path, classifier=_ExplodingClassifier())
    with TestClient(app) as client:
        alert_id = _post_alert(client)
        rows = client.get("/api/alerts").json()
        page = client.get("/")

    assert opened == [alert_id]  # 通知は出ている
    assert rows[0]["priority"] is None  # 目安だけが付かない
    assert page.status_code == 200


def test_priority_assist_is_not_wired_into_the_notification_path():
    """通知(notify)・dedup/resolve(alert_aggregator)は、分類補助や手順書を一切importしない。"""
    import hub.alert_aggregator as aggregator_module
    import hub.notify as notify_module

    for module in (aggregator_module, notify_module):
        source = open(module.__file__, encoding="utf-8").read()
        assert "alert_priority" not in source
        assert "runbooks" not in source


def test_broken_runbooks_file_does_not_stop_the_hub(tmp_path):
    broken = tmp_path / "runbooks.yaml"
    broken.write_text("runbooks: [unclosed", encoding="utf-8")
    app = _make_app(tmp_path, runbooks_path=str(broken))
    with TestClient(app) as client:
        _post_alert(client)
        row = client.get("/api/alerts").json()[0]
        assert client.get("/").status_code == 200
    assert row["runbook"] is None


def test_resolved_rows_are_marked_so_they_can_be_greyed_out(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        _post_alert(client)
        client.post("/api/alerts/profiling-tool", json={"signature": "gpu_budget", "severity": "info", "message": "ok"})
        html = client.get("/").text
    assert 'class="alert-row is-resolved"' in html


# ---------------------------------------------------------------- 決めごと表(言語・記号・操作)

def test_headings_are_japanese_not_a_mix_of_english_and_japanese(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        html = client.get("/").text
    for heading in ("ツール一覧と死活監視", "アラート", "リポジトリ", "プロファイリング", "成果物"):
        assert f"<h2>{heading}</h2>" in html
    for old in ("Tool Registry &amp; Liveness", "Open &amp; Resolved Alerts", "<h2>Repositories</h2>", "<h2>Profiling</h2>", "<h2>Artifacts</h2>"):
        assert old not in html


def test_status_marks_use_one_glyph_set_and_no_emoji(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        _post_alert(client)
        html = client.get("/").text
    for emoji in ("🔕", "⚠", "🟢", "🔴", "✅", "❌"):
        assert emoji not in html


def test_resolved_notice_uses_calm_state_only_when_no_alert_is_open(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        calm = client.get("/").text
        _post_alert(client)
        busy = client.get("/").text
    assert 'class="calm"' in calm and "現在アラートはありません。" in calm
    assert 'class="calm"' not in busy


def test_page_wires_assets_with_cache_busting_and_a_noscript_refresh_fallback(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        html = client.get("/").text
        js = client.get("/static/app.js")
        css = client.get("/static/style.css")
    assert re.search(r'<script src="/static/app\.js\?v=\d+" defer></script>', html)
    assert re.search(r'<link rel="stylesheet" href="/static/style\.css\?v=\d+">', html)
    assert '<noscript><meta http-equiv="refresh" content="20"></noscript>' in html
    assert js.status_code == 200 and css.status_code == 200
    assert 'id="theme-toggle"' in html


def test_sync_button_carries_what_the_confirmation_dialog_needs(tmp_path):
    """設計書の検証: 破壊的な操作(同期)に確認が入る。確認文に使う情報がボタンに載っている。"""
    js = (app_module.BASE_DIR / "static" / "app.js").read_text(encoding="utf-8")
    assert "window.confirm(" in js
    sync_handler = js[js.index('$$(".repo-sync-btn")'): js.index('$$(".repo-launch-btn")')]
    assert sync_handler.index("window.confirm(") < sync_handler.index("fetch(")  # 確認してから初めて叩く


# ---------------------------------------------------------------- 404

def test_browser_404_gets_the_playful_page_but_the_api_keeps_json(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        page = client.get("/no-such-page", headers={"accept": "text/html,application/xhtml+xml"})
        api = client.get("/api/no-such-endpoint", headers={"accept": "text/html"})
        plain = client.get("/no-such-page")

    assert page.status_code == 404
    assert "この席には、誰もいません" in page.text
    assert 'href="/"' in page.text
    assert api.status_code == 404 and api.headers["content-type"].startswith("application/json")
    assert plain.status_code == 404 and plain.headers["content-type"].startswith("application/json")


def test_404_animation_stops_for_reduced_motion():
    css = (app_module.BASE_DIR / "static" / "style.css").read_text(encoding="utf-8")
    reduced = css[css.index("@media (prefers-reduced-motion: reduce)"):]
    for selector in (".office-svg *", ".calm-ring", ".confetti-piece", ".wanderer"):
        assert selector in reduced


# ---------------------------------------------------------------- 20ツールでも崩れない

def test_twenty_tools_render_in_list_office_and_summary(tmp_path):
    tools = "\n".join(
        f"""  - tool_id: tool_{i:02d}
    display_name: "Tool {i:02d}"
    transport: static_site
    endpoint: null
    health_check: null
    category: observed_only
    isolation: none"""
        for i in range(20)
    )
    app = _make_app(tmp_path, registry=f"tools:\n{tools}\n")
    with TestClient(app) as client:
        html = client.get("/").text
        overview = client.get("/api/overview").json()

    assert html.count('class="tool-row"') == 20
    assert html.count('class="office-tile"') == 20
    assert overview["summary"]["total"] == 20
    assert "max-height" in (app_module.BASE_DIR / "static" / "style.css").read_text(encoding="utf-8")  # 一覧は中でスクロール


# ---------------------------------------------------------------- 操作ボタンの順序

def test_repo_operations_are_ordered_from_lowest_risk_and_sync_is_kept_apart(tmp_path):
    from tests.test_dashboard_app import (
        _init_git_remote_and_clone,
        _write_repos_yaml_with_two_launch_targets,
    )

    remote, _local = _init_git_remote_and_clone(tmp_path, "sample")
    repos_path = _write_repos_yaml_with_two_launch_targets(tmp_path, "sample_local", remote)
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_REGISTRY, encoding="utf-8")
    app = app_module.create_app(
        registry_path=str(registry_path),
        db_path=str(tmp_path / "hub_state.sqlite3"),
        profiling_traces_dir=str(tmp_path / "traces"),
        repos_path=repos_path,
    )
    with TestClient(app) as client:
        html = client.get("/").text

    open_folder = html.index("Open folder")
    start_one = html.index("Start: Backend")
    start_all = html.index("Start all (2)")
    assert open_folder < start_one < start_all  # フォルダを開く → 起動 → まとめて起動
    assert '<td class="op-sync-cell">' in html  # 同期は別の列(視覚的にも離す)


# ---------------------------------------------------------------- ブラウザ側JSの落とし穴(回帰)

def test_overview_js_does_not_reuse_the_chip_attribute_names_on_the_card():
    """回帰: カードに data-view を付けると、表示切替ボタン判定の closest("[data-view]") が
    カード自身に一致し、ツール行・オフィスのタイルのクリックが全て横取りされて選択できなくなった。
    (実ブラウザで発見。JSはpytestでは動かないため、原因になった書き方を静的に禁じる。)
    """
    js = (app_module.BASE_DIR / "static" / "app.js").read_text(encoding="utf-8")
    assert "card.dataset.view" not in js
    assert 'closest("button[data-sort], button[data-filter], button[data-view]")' in js


def test_main_grid_column_can_shrink_so_the_page_never_scrolls_sideways():
    """回帰: mainのグリッド列が minmax(0, 1fr) でないと、列の最小幅が幅広の表の最小幅になり、
    狭い画面(390px)でページ全体が横にはみ出した(実際の狭い幅で確認して発見)。
    """
    css = (app_module.BASE_DIR / "static" / "style.css").read_text(encoding="utf-8")
    main_rule = css[css.index("\nmain {"): css.index("}", css.index("\nmain {"))]
    assert "grid-template-columns: minmax(0, 1fr)" in main_rule
    assert "overflow-x: auto" in css[css.index(".card-base {"): css.index("}", css.index(".card-base {"))]
