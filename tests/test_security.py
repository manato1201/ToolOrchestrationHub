"""hub/security.py と、2026-10のセキュリティ点検(docs/SECURITY_REVIEW_2026-10.md)で直した項目のテスト。

CSRF・DNS rebinding・スヌーズの入力・本文の長さは、修正前のコードで実際に再現(別サイトからのPOSTで起動が
実行される、など)してから直した。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import hub.dashboard.app as app_module
from hub.process_launcher import LaunchResult
from hub.security import (
    ALLOWED_HOSTS_ENV,
    extend_allowed_hosts_env,
    host_only,
    is_loopback_host,
    is_same_origin,
    resolve_allowed_hosts,
)

pytestmark = pytest.mark.usefixtures("no_real_repo_sync")

_REGISTRY = """
tools:
  - tool_id: profiling_tool
    display_name: "ProfilingTool"
    transport: static_site
    endpoint: null
    health_check: null
    category: excluded
"""


def _make_app(tmp_path, monkeypatch, *, with_repo=False):
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_REGISTRY, encoding="utf-8")
    kwargs = {}
    if with_repo:
        repos_path = tmp_path / "repos.yaml"
        repos_path.write_text(
            f"""
repos:
  - repo_id: sample
    display_name: Sample
    local_path: "{tmp_path.as_posix()}"
    remote_url: unused
    launch:
      - {{name: Dev, command: "npm run dev"}}
""",
            encoding="utf-8",
        )
        kwargs["repos_path"] = str(repos_path)
    launched: list[str] = []

    def fake_launch(entry, target, root):
        launched.append(entry.repo_id)
        return LaunchResult(ok=True, message="started", pid=1)

    monkeypatch.setattr(app_module, "launch", fake_launch)
    app = app_module.create_app(registry_path=str(registry_path), db_path=str(tmp_path / "hub.sqlite3"), **kwargs)
    return app, launched


def _post_alert(client, signature="s", severity="critical", message="something broke here"):
    return client.post(
        "/api/alerts/profiling-tool", json={"signature": signature, "severity": severity, "message": message}
    )


# ---------------------------------------------------------------- 別サイトからの変更操作(CSRF)

def test_cross_site_post_is_rejected_and_nothing_is_executed(tmp_path, monkeypatch):
    """別サイトのページ(Origin: https://evil.example)からの起動は、実行されずに403になる。"""
    app, launched = _make_app(tmp_path, monkeypatch, with_repo=True)
    with TestClient(app) as client:
        res = client.post("/api/repos/sample/launch/0", headers={"origin": "https://evil.example"})
    assert res.status_code == 403
    assert launched == []


def test_other_local_page_on_a_different_port_is_a_different_origin(tmp_path, monkeypatch):
    """同じlocalhostでも別ポートのページ(開発サーバー等)は別オリジン。Hostのポートまで比べる。"""
    app, launched = _make_app(tmp_path, monkeypatch, with_repo=True)
    with TestClient(app, base_url="http://127.0.0.1:8790") as client:
        res = client.post("/api/repos/sample/launch/0", headers={"origin": "http://127.0.0.1:3000"})
    assert res.status_code == 403
    assert launched == []


def test_null_origin_is_rejected(tmp_path, monkeypatch):
    app, launched = _make_app(tmp_path, monkeypatch, with_repo=True)
    with TestClient(app) as client:
        assert client.post("/api/repos/sample/launch/0", headers={"origin": "null"}).status_code == 403
    assert launched == []


def test_same_origin_post_from_the_dashboard_itself_still_works(tmp_path, monkeypatch):
    app, launched = _make_app(tmp_path, monkeypatch, with_repo=True)
    with TestClient(app, base_url="http://127.0.0.1:8790") as client:
        res = client.post("/api/repos/sample/launch/0", headers={"origin": "http://127.0.0.1:8790"})
    assert res.status_code == 200
    assert launched == ["sample"]


def test_clients_without_an_origin_header_are_not_browsers_and_still_work(tmp_path, monkeypatch):
    """curl・各ツールからのheartbeat/アラート送信・ProfilingToolのSinkはOriginを付けない。"""
    app, _ = _make_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        assert _post_alert(client, severity="warn", message="threshold crossed here").status_code == 200


def test_reads_are_not_blocked_by_a_foreign_origin(tmp_path, monkeypatch):
    """GETはブラウザのCORS(応答を読ませない)に任せ、Originでは弾かない。"""
    app, _ = _make_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        assert client.get("/api/overview", headers={"origin": "https://other.example"}).status_code == 200


# ---------------------------------------------------------------- DNS rebinding(Hostの許可リスト)

@pytest.mark.parametrize("method,path", [("get", "/"), ("get", "/api/alerts"), ("post", "/api/registry/reload")])
def test_unknown_host_is_rejected_for_every_route(tmp_path, monkeypatch, method, path):
    app, _ = _make_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        res = getattr(client, method)(path, headers={"host": "rebind.evil.example:8790"})
    assert res.status_code == 403
    assert ALLOWED_HOSTS_ENV in res.json()["detail"]  # 直し方が分かる


@pytest.mark.parametrize("host", ["127.0.0.1:8790", "localhost:8790", "localhost", "[::1]:8790"])
def test_loopback_hosts_are_allowed(tmp_path, monkeypatch, host):
    app, _ = _make_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        assert client.get("/api/overview", headers={"host": host}).status_code == 200


def test_extra_hosts_can_be_allowed_by_environment(tmp_path, monkeypatch):
    monkeypatch.setenv(ALLOWED_HOSTS_ENV, "testserver, hub.lan")
    app, _ = _make_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        assert client.get("/api/overview", headers={"host": "hub.lan:8790"}).status_code == 200
        assert client.get("/api/overview", headers={"host": "other.lan:8790"}).status_code == 403


def test_extra_hosts_can_be_allowed_by_argument(tmp_path):
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_REGISTRY, encoding="utf-8")
    app = app_module.create_app(
        registry_path=str(registry_path), db_path=str(tmp_path / "hub.sqlite3"), allowed_hosts=["hub.example"]
    )
    with TestClient(app) as client:
        assert client.get("/api/overview", headers={"host": "hub.example"}).status_code == 200


# ---------------------------------------------------------------- 純関数

@pytest.mark.parametrize(
    "header,expected",
    [("127.0.0.1:8790", "127.0.0.1"), ("LocalHost", "localhost"), ("[::1]:8790", "::1"), ("[::1]", "::1"), ("hub.lan:80", "hub.lan"), ("", "")],
)
def test_host_only(header, expected):
    assert host_only(header) == expected


@pytest.mark.parametrize(
    "origin,host,expected",
    [
        ("http://127.0.0.1:8790", "127.0.0.1:8790", True),
        ("https://127.0.0.1:8790", "127.0.0.1:8790", True),  # スキームは見ない
        ("http://127.0.0.1:3000", "127.0.0.1:8790", False),
        ("http://localhost:8790", "127.0.0.1:8790", False),  # 名前が違えば別オリジン
        ("null", "127.0.0.1:8790", False),
        ("https://evil.example", "127.0.0.1:8790", False),
    ],
)
def test_is_same_origin(origin, host, expected):
    assert is_same_origin(origin, host) is expected


def test_loopback_detection_and_env_extension(monkeypatch):
    monkeypatch.delenv(ALLOWED_HOSTS_ENV, raising=False)
    assert is_loopback_host("127.0.0.1") and is_loopback_host("localhost")
    assert not is_loopback_host("192.168.0.5")

    assert extend_allowed_hosts_env("192.168.0.5") is True
    assert "192.168.0.5" in resolve_allowed_hosts()
    # ワイルドカードやループバックは足さない(0.0.0.0は「どのHostでもよい」ではない)
    assert extend_allowed_hosts_env("0.0.0.0") is False
    assert extend_allowed_hosts_env("127.0.0.1") is False


# ---------------------------------------------------------------- 入力の検証(500にならない / 巨大にならない)

@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-1", "0", "1000000000000", str(7 * 24 * 60 + 1), '"abc"'])
def test_snooze_rejects_unusable_durations_with_400_not_500(tmp_path, monkeypatch, literal):
    """NaN/InfinityはPythonのjsonが受け付けるリテラルなので、生のJSONで送る(httpxのjson=では作れない)。"""
    app, _ = _make_app(tmp_path, monkeypatch)
    with TestClient(app, raise_server_exceptions=False) as client:
        alert_id = _post_alert(client).json()["alert_id"]
        res = client.post(
            f"/api/alerts/{alert_id}/snooze",
            content='{"minutes": ' + literal + "}",
            headers={"content-type": "application/json"},
        )
    assert res.status_code == 400


def test_snooze_accepts_the_maximum_duration(tmp_path, monkeypatch):
    app, _ = _make_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        alert_id = _post_alert(client).json()["alert_id"]
        res = client.post(f"/api/alerts/{alert_id}/snooze", json={"minutes": app_module.MAX_SNOOZE_MINUTES})
    assert res.status_code == 200


def test_oversized_or_non_string_alert_messages_are_capped(tmp_path, monkeypatch):
    app, _ = _make_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        _post_alert(client, signature="big", message="x" * 50_000)
        _post_alert(client, signature="num", severity="warn", message=12345)
        messages = [r["message"] for r in client.get("/api/alerts").json()]
    assert max(len(m) for m in messages) == app_module.MAX_ALERT_MESSAGE_LEN
    assert "12345" in messages


# ---------------------------------------------------------------- CSV / パストラバーサル

def test_csv_export_neutralises_spreadsheet_formulas():
    """アラート本文は外部から届く値。= + - @ で始まるセルは、表計算ソフトが数式として実行しないよう ' を付ける。"""
    js = (app_module.BASE_DIR / "static" / "app.js").read_text(encoding="utf-8")
    assert "CSVインジェクション" in js
    assert "/^[=+\\-@\\t\\r]/.test(text)" in js


def test_trace_loader_cannot_read_outside_the_traces_directory(tmp_path):
    from profiling_tool.dashboard.data_sources import load_trace_events

    traces = tmp_path / "traces"
    (traces / "tool").mkdir(parents=True)
    (traces / "tool" / "run1.json").write_text('{"traceEvents": [{"name": "ok"}]}', encoding="utf-8")
    (tmp_path / "secret.json").write_text('{"traceEvents": [{"name": "leaked"}]}', encoding="utf-8")

    assert load_trace_events("tool", "run1", traces) == [{"name": "ok"}]
    assert load_trace_events("..", "secret", traces) == []  # traces/../secret.json
    assert load_trace_events("tool", "../../secret", traces) == []


# ---------------------------------------------------------------- 点検で「却下」した項目の根拠

def test_alert_text_from_outside_is_escaped_in_page_fragment_and_attributes(tmp_path, monkeypatch):
    """XSS(却下): アラート本文は外部から届くが、テンプレートの自動エスケープで文字として表示される。"""
    app, _ = _make_app(tmp_path, monkeypatch)
    payload = "<script>window.__pwned = 1</script><img src=x onerror=alert(1)>" + '"' + "'>"
    with TestClient(app) as client:
        _post_alert(client, message=payload)
        page = client.get("/").text
        fragment = client.get("/fragments/overview").text
    for html in (page, fragment):
        assert "<script>window.__pwned" not in html
        assert "<img src=x" not in html
        assert "&lt;script&gt;" in html
