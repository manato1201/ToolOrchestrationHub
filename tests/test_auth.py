"""hub/auth.py + hub/audit.py: API キー+役割、Cloudflare Access、fail-closed、ログイン(クッキー)、監査ログ。"""
from __future__ import annotations

import json
import time
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from hub import audit, auth
from hub.dashboard import app as app_module
from hub.repo_sync import RepoRegistry

REGISTRY = """
tools:
  - tool_id: tool_a
    display_name: "A"
    transport: static_site
    endpoint: null
    health_check: null
    category: excluded
"""


@pytest.fixture(autouse=True)
def _no_real_repo_sync(monkeypatch):
    original_load = RepoRegistry.load.__func__

    def _load(cls, path=None):
        return original_load(cls, path) if path is not None else cls([])

    monkeypatch.setattr(RepoRegistry, "load", classmethod(_load))


@pytest.fixture()
def make_client(tmp_path):
    registry = tmp_path / "registry.yaml"
    registry.write_text(REGISTRY, encoding="utf-8")

    def _make():
        app = app_module.create_app(registry_path=str(registry), db_path=str(tmp_path / "hub_state.sqlite3"))
        return TestClient(app)

    return _make


@pytest.fixture()
def keys(make_client, monkeypatch):
    made = {role: auth.add_user(role, role) for role in auth.ROLES}
    monkeypatch.setenv("HUB_AUTH", "required")
    with make_client() as client:
        yield client, made


def h(key: str) -> dict:
    return {"X-API-Key": key}


def entries() -> list[dict]:
    p = audit.audit_path()
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


# ---- off(既定)と fail-closed
def test_off_is_the_default(make_client):
    with make_client() as client:
        assert client.get("/api/registry").status_code == 200
        me = client.get("/api/auth/me").json()
        assert me["mode"] == "off" and me["role"] == "admin"
        assert client.get("/", follow_redirects=False).status_code == 200


def test_required_without_users_refuses_to_start(make_client, monkeypatch):
    monkeypatch.setenv("HUB_AUTH", "required")
    with pytest.raises(RuntimeError, match="ユーザーが 1 人もいません"):
        with make_client():
            pass


# ---- 役割
def test_api_requires_a_key_but_login_state_is_open(keys):
    client, _ = keys
    assert client.get("/api/registry").status_code == 401
    assert client.get("/api/registry", headers=h("hub_wrong")).status_code == 401
    assert client.get("/api/auth/me").json()["authenticated"] is False


def test_viewer_reads_but_cannot_operate(keys):
    client, k = keys
    for path in ("/api/registry", "/api/alerts", "/api/overview", "/api/repos", "/fragments/overview"):
        assert client.get(path, headers=h(k["viewer"])).status_code == 200, path
    assert client.post("/api/alerts/x/snooze", json={"minutes": 5}, headers=h(k["viewer"])).status_code == 403
    assert client.post("/api/repos/check", headers=h(k["viewer"])).status_code == 403
    assert client.post("/api/repos/r/launch/0", headers=h(k["viewer"])).status_code == 403
    assert client.post("/api/heartbeat/tool_a", headers=h(k["viewer"])).status_code == 403


def test_operator_can_operate_but_not_reload_or_sync(keys):
    client, k = keys
    op = h(k["operator"])
    # 認証は通る(中身が無い・見つからない、などの 404 / 400 は、ここでは問わない)
    assert client.post("/api/alerts/x/snooze", json={"minutes": 5}, headers=op).status_code not in (401, 403)
    assert client.post("/api/alerts/x/unsnooze", headers=op).status_code not in (401, 403)
    assert client.post("/api/repos/check", headers=op).status_code not in (401, 403)
    assert client.post("/api/repos/nope/launch/0", headers=op).status_code not in (401, 403)
    assert client.post("/api/repos/nope/open-folder", headers=op).status_code not in (401, 403)
    assert client.post("/api/heartbeat/tool_a", headers=op).status_code not in (401, 403)
    assert client.post("/api/registry/reload", headers=op).status_code == 403
    assert client.post("/api/repos/nope/sync", headers=op).status_code == 403


def test_admin_can_reload_and_sync(keys):
    client, k = keys
    ad = h(k["admin"])
    assert client.post("/api/registry/reload", headers=ad).status_code == 200
    assert client.post("/api/repos/nope/sync", headers=ad).status_code not in (401, 403)


def test_machine_endpoints_accept_an_operator_key_and_reject_none(keys):
    client, k = keys
    for path in ("/api/alerts/profiling-tool", "/api/alerts/visual-regression-qa", "/api/alerts/asset-data-insight"):
        assert client.post(path, json={}, headers=h(k["operator"])).status_code not in (401, 403), path
        assert client.post(path, json={}).status_code == 401, path


# ---- ダッシュボード(HTML)とログインのページ
def test_dashboard_redirects_to_login_when_not_logged_in(keys):
    client, k = keys
    r = client.get("/", follow_redirects=False)
    assert (r.status_code, r.headers["location"]) == (303, "/login")
    page = client.get("/login")
    assert page.status_code == 200 and "API キー" in page.text
    assert client.get("/", headers=h(k["viewer"]), follow_redirects=False).status_code == 200


def test_login_page_redirects_home_once_logged_in(keys):
    client, k = keys
    client.post("/api/auth/login", json={"api_key": k["viewer"]})
    assert client.get("/login", follow_redirects=False).headers["location"] == "/"
    assert client.get("/", follow_redirects=False).status_code == 200


def test_static_assets_and_auth_script_are_public(keys):
    client, _ = keys
    assert client.get("/static/auth.js").status_code == 200
    assert "/static/auth.js" in client.get("/", headers=h(keys[1]["viewer"])).text


# ---- ログイン(クッキー)
def test_login_cookie_is_httponly_strict_and_works_without_header(keys):
    client, k = keys
    r = client.post("/api/auth/login", json={"api_key": k["operator"]})
    assert r.status_code == 200 and r.json()["role"] == "operator"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert client.get("/api/registry").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/registry").status_code == 401


def test_login_with_wrong_key_and_from_another_site(keys):
    client, k = keys
    assert client.post("/api/auth/login", json={"api_key": "nope"}).status_code == 401
    assert client.post("/api/auth/login", json={"api_key": k["viewer"]}, headers={"Origin": "http://evil.example"}).status_code == 403


def test_removed_user_loses_access_and_only_hash_is_stored(keys):
    client, k = keys
    text = auth.auth_file().read_text(encoding="utf-8")
    assert all(key not in text for key in k.values()) and auth.hash_key(k["admin"]) in text
    assert auth.remove_user("viewer")
    assert client.get("/api/registry", headers=h(k["viewer"])).status_code == 401


# ---- Cloudflare Access
TEAM, AUD = "myteam.cloudflareaccess.com", "aud-123"


@pytest.fixture()
def access(make_client, monkeypatch):
    auth.add_user("carol", "operator", email="carol@example.com", with_key=False)
    auth.add_user("root", "admin")
    monkeypatch.setenv("HUB_AUTH", "required")
    monkeypatch.setenv(auth.TEAM_DOMAIN_ENV, f"https://{TEAM}/")
    monkeypatch.setenv(auth.AUD_ENV, AUD)
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(auth, "_signing_key", lambda token: private.public_key())

    def token(**over):
        now = int(time.time())
        claims = {"email": "carol@example.com", "aud": AUD, "iss": f"https://{TEAM}", "iat": now, "exp": now + 300}
        claims.update(over)
        return jwt.encode(claims, private, algorithm="RS256")

    with make_client() as client:
        yield client, token


def acc(t: str) -> dict:
    return {"Cf-Access-Jwt-Assertion": t}


def test_access_maps_email_to_role(access):
    client, token = access
    assert client.get("/api/registry", headers=acc(token())).status_code == 200
    assert client.post("/api/repos/check", headers=acc(token())).status_code not in (401, 403)
    assert client.post("/api/registry/reload", headers=acc(token())).status_code == 403


def test_access_rejects_unregistered_wrong_aud_issuer_expired_and_bad_algs(access):
    client, token = access
    assert client.get("/api/registry", headers=acc(token(email="stranger@example.com"))).status_code == 403
    assert client.get("/api/registry", headers=acc(token(aud="other"))).status_code == 401
    assert client.get("/api/registry", headers=acc(token(iss="https://evil.example"))).status_code == 401
    assert client.get("/api/registry", headers=acc(token(exp=int(time.time()) - 10))).status_code == 401
    now = int(time.time())
    claims = {"email": "carol@example.com", "aud": AUD, "iss": f"https://{TEAM}", "iat": now, "exp": now + 300}
    assert client.get("/api/registry", headers=acc(jwt.encode(claims, "secret" * 8, algorithm="HS256"))).status_code == 401
    assert client.get("/api/registry", headers=acc(jwt.encode(claims, key=None, algorithm="none"))).status_code == 401


# ---- 監査ログ
def test_writes_and_denials_are_audited_with_who_and_nothing_secret(keys):
    client, k = keys
    client.post("/api/auth/login", json={"api_key": k["admin"]})
    client.post("/api/registry/reload", headers=h(k["admin"]))
    client.post("/api/repos/x/sync", headers=h(k["operator"]))  # 403
    client.cookies.clear()  # ログイン済みのクッキーを捨てて、匿名にする
    client.get("/api/registry")  # 401 は、読み取りでも記録
    client.get("/api/registry", headers=h(k["viewer"]))  # 成功した読み取りは記録しない
    es = entries()
    got = [(e["event"], e["actor"], e["status"], e["path"]) for e in es]
    assert ("login", "admin", 200, "/api/auth/login") in got
    assert ("http", "admin", 200, "/api/registry/reload") in got
    assert ("denied", "operator", 403, "/api/repos/x/sync") in got
    assert ("denied", "anonymous", 401, "/api/registry") in got
    assert len(got) == 4
    text = audit.audit_path().read_text(encoding="utf-8")
    assert all(key not in text for key in k.values())


def test_audit_endpoint_is_admin_only_newest_first(keys):
    client, k = keys
    client.post("/api/repos/check", headers=h(k["operator"]))
    client.post("/api/repos/check", headers=h(k["operator"]))
    assert client.get("/api/auth/audit", headers=h(k["viewer"])).status_code == 403
    assert client.get("/api/auth/audit", headers=h(k["operator"])).status_code == 403
    assert client.get("/api/auth/audit").status_code == 401
    es = client.get("/api/auth/audit?limit=2", headers=h(k["admin"])).json()["entries"]
    assert len(es) == 2 and es[0]["ts"] >= es[1]["ts"]


def test_audit_write_failure_does_not_break_requests(keys, monkeypatch):
    client, k = keys
    monkeypatch.setenv("HUB_AUDIT_LOG", str(audit.audit_path().parent))  # ディレクトリ = 書けない
    assert client.post("/api/repos/check", headers=h(k["operator"])).status_code not in (401, 403, 500)


def test_off_mode_still_audits_writes_as_anonymous(make_client):
    with make_client() as client:
        client.post("/api/registry/reload")
    e = entries()[-1]
    assert (e["actor"], e["role"], e["source"], e["path"]) == ("anonymous", "admin", "anonymous", "/api/registry/reload")


# ---- CLI
def test_cli_add_list_remove(capsys):
    assert auth._cli(["add", "--name", "dave", "--role", "viewer"]) == 0
    assert "hub_" in capsys.readouterr().out
    assert auth._cli(["list"]) == 0
    assert "hub_" not in capsys.readouterr().out
    assert auth._cli(["remove", "--name", "dave"]) == 0
    assert auth._cli(["remove", "--name", "dave"]) == 1
