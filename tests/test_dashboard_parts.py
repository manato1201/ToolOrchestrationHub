"""IMPROVEMENT_DESIGN_2026-10 追補のUIパーツ・動き・キー操作のテスト。

バッジ(23)・ドロワー(02)・トースト(08)・トグルスイッチ(11)・ステップインジケーター(20)・
スケルトン(21)・スタッガー(03)、T6 キー操作、T10 表示の復元、ASCII蜂の巣、動きの予算(2種類まで)。
JS自体はpytestでは動かないため、HTMLの形と、JSの取り決め(キーの割り当て・動きの種類)を確かめる。
実際の動作は実ブラウザで確認した。
"""
from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

import hub.dashboard.app as app_module
from hub.health.base import HealthResult

pytestmark = pytest.mark.usefixtures("no_real_repo_sync")

STATIC = app_module.BASE_DIR / "static"
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")
STYLE_CSS = (STATIC / "style.css").read_text(encoding="utf-8")
PARTS_CSS = (STATIC / "parts.css").read_text(encoding="utf-8")

_REGISTRY = """
tools:
  - tool_id: base_tool
    display_name: "BaseTool"
    description: "土台になるツールの説明です。"
    transport: http_bridge
    endpoint: "http://127.0.0.1:1/health"
    health_check: http_bridge_check
    category: monitored
    isolation: container
    todo:
      - "poll_interval_sは暫定"
    poll_interval_s: 3600
  - tool_id: user_tool
    display_name: "UserTool"
    transport: http_bridge
    endpoint: "http://127.0.0.1:1/health"
    health_check: http_bridge_check
    category: monitored
    concerns:
      - "隔離するかは要判断"
    depends_on:
      - base_tool
    poll_interval_s: 3600
  - tool_id: profiling_tool
    display_name: "ProfilingTool"
    transport: static_site
    endpoint: null
    health_check: null
    category: excluded
"""


def _make_app(tmp_path):
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_REGISTRY, encoding="utf-8")
    return app_module.create_app(registry_path=str(registry_path), db_path=str(tmp_path / "hub.sqlite3"))


def _post_alert(client, signature="s", severity="critical", message="something broke in profiling"):
    res = client.post("/api/alerts/profiling-tool", json={"signature": signature, "severity": severity, "message": message})
    assert res.status_code == 200
    return res.json()["alert_id"]


# ---------------------------------------------------------------- 動きの予算(2種類まで)

def test_only_the_two_budgeted_keyframes_exist_plus_the_404_walker():
    """設計書: 1画面で使う動きは2種類まで。ダッシュボードの@keyframesは 出入り と 脈動 だけ(404は別画面)。"""
    names = set(re.findall(r"@keyframes\s+([\w-]+)", STYLE_CSS + PARTS_CSS))
    assert names == {"hub-enter", "hub-pulse", "wander"}


@pytest.mark.parametrize("retired", ["confetti", "office-type", "office-wave", "calm-draw", "calm-breathe", "calm-ring", "calm-check"])
def test_retired_motions_are_gone_from_css_and_js(retired):
    """紙吹雪・人物のタイプ/手を振る・空状態のチェックの描画/呼吸は、動きの種類が2を超えるため取り下げた。"""
    assert retired not in STYLE_CSS + PARTS_CSS + APP_JS


def test_pulse_is_used_only_for_attention_states_and_waiting():
    """脈動は、要対応(警告・停止)の記号と、確認中(スケルトン)だけ。正常・未確認・対象外は静か。"""
    block = PARTS_CSS[PARTS_CSS.index("/* 脈動:"): PARTS_CSS.index("/* 出入り: 初回表示")]
    selectors = block[: block.index("{")]
    assert "state-warn" in selectors and "state-down" in selectors and ".skeleton" in selectors
    for quiet in ("state-ok", "state-unknown", "state-excluded", "office-ok"):
        assert quiet not in selectors


def test_stagger_runs_once_per_tab_and_is_skipped_for_reduced_motion():
    assert 'session.get("hub.staggered")' in APP_JS
    stagger = APP_JS[APP_JS.index("function staggerOnce"): APP_JS.index("applyOverviewState();\n  renderRestoreButton();")]
    assert "reducedMotion()" in stagger
    assert "is-staggering" in PARTS_CSS


# ---------------------------------------------------------------- バッジ(23): アラート件数

def test_alert_count_badge_shows_open_count_with_text_and_severity(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        none = client.get("/").text
        _post_alert(client, signature="a", severity="warn", message="warning level message here")
        warn_only = client.get("/").text
        _post_alert(client, signature="b", severity="critical", message="critical level message here")
        both = client.get("/").text

    assert "count-badge" not in none.split("<script", 1)[0]
    assert re.search(r'count-badge is-warn" aria-label="未解消 1件"><span class="num">1</span>', warn_only)
    assert re.search(r'count-badge is-critical" aria-label="未解消 2件"><span class="num">2</span>', both)
    assert "<h2>アラート</h2>" in both  # 見出しの文字は変えず、横にバッジを置く


def test_tab_title_badge_is_set_from_the_open_alert_count():
    assert "(${openCount}) ${BASE_TITLE}" in APP_JS


# ---------------------------------------------------------------- トグルスイッチ(11)

def test_snooze_control_is_an_accessible_switch(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        alert_id = _post_alert(client)
        off = client.get("/").text
        client.post(f"/api/alerts/{alert_id}/snooze", json={"minutes": 30})
        on = client.get("/").text

    assert re.search(r'<button type="button" class="switch alert-snooze-btn" role="switch" aria-checked="false"', off)
    assert re.search(r'<button type="button" class="switch alert-unsnooze-btn" role="switch" aria-checked="true"', on)
    assert "switch-track" in off and "switch-thumb" in off
    assert "スヌーズ中" in on  # オンは、つまみの位置 + 横の文字(色だけにしない)


# ---------------------------------------------------------------- ドロワー(02)・トースト(08)

def test_drawer_and_toast_regions_exist_once_outside_the_swapped_fragment(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        page = client.get("/").text
        fragment = client.get("/fragments/overview").text

    for html_id in ('id="drawer"', 'id="drawer-backdrop"', 'id="drawer-close"', 'id="toasts"'):
        assert page.count(html_id) == 1
        assert html_id not in fragment  # 履歴スライダーで差し替わっても消えない(ページ側に1つだけ)
    assert 'role="dialog" aria-modal="false"' in page  # 非モーダル: 一覧を見たまま操作できる
    assert 'aria-live="polite"' in page


def test_recent_alerts_open_the_drawer_only_for_registered_tools(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        _post_alert(client)  # profiling_tool は台帳にある
        client.post("/api/alerts/visual-regression-qa", json={"case_id": "c", "passed": False, "message": "pixel diff 3%"})  # 台帳に無い
        html = client.get("/fragments/overview").text

    assert 'data-open-drawer="profiling_tool"' in html
    assert 'data-open-drawer="visual_regression_qa_tool"' not in html
    assert 'class="recent-alert-body"' in html  # 台帳に無い発生元は、押せない通常の表示


def test_overview_card_carries_the_open_alerts_for_toasts(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        _post_alert(client, message="gpu frame budget exceeded: 21ms")
        html = client.get("/").text

    raw = re.search(r'data-open-alerts="([^"]*)"', html).group(1)
    alerts = json.loads(raw.replace("&#34;", '"'))
    assert [(a["severity"], a["source"]) for a in alerts] == [("critical", "ProfilingTool")]
    assert alerts[0]["message"].startswith("gpu frame budget")


def test_toasts_are_built_with_text_content_never_html(tmp_path):
    """外部から届くアラート本文をトーストに出すので、innerHTMLではなくtextContentで作る(XSS対策)。"""
    toast = APP_JS[APP_JS.index("function showToast"): APP_JS.index("function updateTitleBadge")]
    assert "textContent" in toast
    assert "innerHTML" not in toast


def test_first_visit_shows_no_toast_and_only_changes_do():
    announce = APP_JS[APP_JS.index("announceAlertChanges"): APP_JS.index("初回表示のスタッガー")]
    assert "if (!Array.isArray(previous)) return;" in announce
    assert "新規" in announce and "解消" in announce


# ---------------------------------------------------------------- 詳細カード(依存・懸念・やり残し)・原因の木

def test_detail_card_shows_description_dependencies_concerns_and_todo(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        html = client.get("/").text

    assert "土台になるツールの説明です。" in html
    assert "台帳上の依存" in html and "実測ではありません" in html
    assert 'data-select-tool="base_tool"' in html  # 依存先へ移れる
    assert "懸念" in html and "隔離するかは要判断" in html
    assert "やり残し" in html and "poll_interval_sは暫定" in html


def test_impact_tree_appears_only_when_a_tool_with_dependents_is_stopped(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        app.state.monitor._results["base_tool"] = HealthResult(is_up=True, latency_ms=1.0)
        healthy = client.get("/fragments/overview").text
        app.state.monitor._results["base_tool"] = HealthResult(is_up=False)
        stopped = client.get("/fragments/overview").text

    assert 'class="impact-tree"' not in healthy
    assert 'class="impact-tree"' in stopped
    assert "波及の見込み" in stopped and "実測ではありません" in stopped
    tree = stopped[stopped.index('class="impact-tree"'):]
    assert 'data-select-tool="base_tool"' in tree and 'data-select-tool="user_tool"' in tree


# ---------------------------------------------------------------- スケルトン(21): 確認中

def test_not_yet_checked_tool_shows_a_text_labelled_skeleton(tmp_path, monkeypatch):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        monkeypatch.setattr(app.state.monitor, "has_checked", lambda tool_id: False)
        html = client.get("/fragments/overview").text

    assert 'class="skeleton skeleton-pill" role="status">確認中</span>' in html  # 動きだけでなく文字でも出す
    assert 'class="skeleton skeleton-line"' in html
    assert "確認中" in re.search(r'aria-label="BaseTool: ([^"]*)"', html).group(0)


def test_checked_tool_shows_its_real_state_not_the_skeleton(tmp_path, monkeypatch):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        app.state.monitor._results["base_tool"] = HealthResult(is_up=True, latency_ms=4.0)
        monkeypatch.setattr(app.state.monitor, "has_checked", lambda tool_id: True)
        html = client.get("/fragments/overview").text
    assert "skeleton-pill" not in html


# ---------------------------------------------------------------- ステップインジケーター(20)

def test_launch_buttons_carry_the_names_shown_in_the_step_indicator(tmp_path):
    from tests.test_dashboard_app import _init_git_remote_and_clone, _write_repos_yaml_with_two_launch_targets

    remote, _ = _init_git_remote_and_clone(tmp_path, "sample")
    repos_path = _write_repos_yaml_with_two_launch_targets(tmp_path, "sample_local", remote)
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_REGISTRY, encoding="utf-8")
    app = app_module.create_app(registry_path=str(registry_path), db_path=str(tmp_path / "hub.sqlite3"), repos_path=repos_path)
    with TestClient(app) as client:
        html = client.get("/").text

    assert 'data-target-name="Backend"' in html and 'data-target-name="Frontend"' in html


def test_step_indicator_uses_glyph_and_text_for_every_step_state():
    states = re.search(r"const STEP_STATES = \{(.*?)\n  \};", APP_JS, re.S).group(1)
    for glyph, label in (("○", "待機"), ("▸", "実行中"), ("✓", "完了"), ("■", "失敗")):
        assert f'glyph: "{glyph}", label: "{label}"' in states
    assert 'window.alert' not in APP_JS[APP_JS.index("失敗は、ステップに残したまま"): APP_JS.index("repo-open-folder-btn")]


# ---------------------------------------------------------------- T6 キー操作 / T10 表示の復元

def test_keyboard_shortcuts_in_the_hint_match_the_handler(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        html = client.get("/").text

    hint = re.search(r'<p class="kbd-hint[^>]*>(.*?)</p>', html, re.S).group(1)
    shown = re.findall(r"<kbd>([^<]+)</kbd>", hint)
    assert shown == ["/", "a", "o", "Esc"]
    for key in ("/", "a", "o"):
        assert f'event.key === "{key}"' in APP_JS
    assert 'event.key === "Escape"' in APP_JS


def test_keyboard_handler_does_not_hijack_typing_or_browser_shortcuts():
    handler = APP_JS[APP_JS.index('document.addEventListener("keydown"'): APP_JS.index("トースト(新しく出た")]
    for guard in ("event.isComposing", "event.ctrlKey", "event.metaKey", "event.altKey", "isContentEditable", '"INPUT", "TEXTAREA", "SELECT"'):
        assert guard in handler
    assert handler.index("if (typing) return;") < handler.index('event.key === "/"')


def test_restore_button_starts_disabled_and_covers_only_display_settings(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        html = client.get("/").text
    assert re.search(r'<button type="button" id="restore-view" class="btn-reload btn-small" disabled', html)
    assert "前回の表示に戻す" in html
    snapshot = APP_JS[APP_JS.index("const displaySnapshot"): APP_JS.index("function renderRestoreButton")]
    # 並び順・絞り込み・表示・テーマ。選択中のツールや検索語は含めない(その場の操作のため)
    assert "sort: ui.sort, filter: ui.filter, view: ui.view, theme: currentTheme()" in snapshot
    assert "selected" not in snapshot and "query" not in snapshot


def test_filter_chip_is_labelled_attention_only_to_match_the_shortcut(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        html = client.get("/fragments/overview").text
    assert 'data-filter="attention">要対応のみ</button>' in html


# ---------------------------------------------------------------- ASCII蜂の巣(空状態)

def test_hive_is_shown_only_in_the_empty_state_with_counts_from_the_tool_states(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        app.state.monitor._results["base_tool"] = HealthResult(is_up=True, latency_ms=1.0)
        calm = client.get("/").text
        _post_alert(client)
        busy = client.get("/").text

    assert re.search(r'<pre class="hive" id="hive" aria-hidden="true" data-flying="1" data-resting="\d+"></pre>', calm)
    assert 'id="hive"' not in busy.split("<script", 1)[0]  # アラートがあるあいだは出さない(動きは空・待機のときだけ)


def test_hive_follows_the_motif_rules():
    """ASCII_MOTIF_MAPの検証項目: 既存の色だけ / 画面外で止まる / 動きを減らす設定で静止画1枚 / 本文に出さない。"""
    hive = APP_JS[APP_JS.index("function setupHive"): APP_JS.index("function setupHistorySlider")]
    assert "IntersectionObserver" in hive and "document.hidden" in hive  # 画面外・裏のタブでは描画を止める
    assert "reducedMotion() || flying === 0" in hive  # 静止画1枚で終わる
    css = PARTS_CSS[PARTS_CSS.index(".hive {"):]
    assert "var(--motif-comb)" in css and "var(--state-ok-text)" in css
    assert "--motif-comb: #185849" in STYLE_CSS  # 既存の深い緑(#185849)のみ。新色は足さない
    assert STYLE_CSS.count("--motif-comb:") == 1  # ダーク/ライトで同じ値を使う


# ---------------------------------------------------------------- 一覧 ↔ オフィスの押し出し(Y2 #137)

def test_view_switch_pushes_the_newly_shown_side_in_with_the_shared_enter_motion():
    assert "pushIn(ui.view === \"office\" ? office : $(\"#tool-details\", card))" in APP_JS
    assert ".is-entering" in PARTS_CSS and "animation: hub-enter" in PARTS_CSS[PARTS_CSS.index(".is-entering"):]


def test_drawer_pauses_auto_refresh_and_closes_with_escape():
    assert "historyMode || drawerToolId !== null" in APP_JS
    assert re.search(r'event\.key === "Escape"[\s\S]{0,200}closeDrawer\(\)', APP_JS)
