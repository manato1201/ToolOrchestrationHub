"""管理画面の分離(QL6): registry の再読み込みとリポジトリの同期は、別のページ・別のスクリプト(/admin・/admin.js)にあり、
サーバーが admin に限る。ダッシュボード(/・/static/app.js)には、管理操作のコードを載せない。

- off(ローカルの単独利用): 従来どおり使える(全員 admin 扱い)
- required: 未認証は /login へ(ページ)・401(スクリプト)、viewer / operator は 403、admin だけ 200
- ダッシュボード側は、読み取りと operator の操作だけ(管理操作の部品も、API の呼び出しも持たない)
"""

from __future__ import annotations

import json

import pytest

from hub import audit, auth
from hub.dashboard import app as app_module
from hub.repo_sync import RepoRegistry
from fastapi.testclient import TestClient

REGISTRY = """
tools:
  - tool_id: tool_a
    display_name: "A"
    transport: static_site
    endpoint: null
    health_check: null
    category: excluded
"""
ADMIN_MARKERS = (
    "reload-registry-btn",
    "repo-sync-btn",
    "/api/registry/reload",
    "/sync",
)


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
        return TestClient(
            app_module.create_app(
                registry_path=str(registry), db_path=str(tmp_path / "hub_state.sqlite3")
            )
        )

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
    return (
        [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()]
        if p.exists()
        else []
    )


# ---- off
def test_off_keeps_the_admin_page_available(make_client):
    with make_client() as client:
        page = client.get("/admin")
        assert page.status_code == 200
        assert "reload-registry-btn" in page.text
        script = client.get("/admin.js")
        assert script.status_code == 200 and "/api/registry/reload" in script.text


# ---- required: 役割で守る
def test_admin_pages_are_admin_only(keys):
    client, k = keys
    # ページ: 未認証はログインへ。足りない役割は 403
    r = client.get("/admin", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert client.get("/admin", headers=h(k["viewer"])).status_code == 403
    assert client.get("/admin", headers=h(k["operator"])).status_code == 403
    assert client.get("/admin", headers=h(k["admin"])).status_code == 200
    # スクリプト
    assert client.get("/admin.js").status_code == 401
    assert client.get("/admin.js", headers=h(k["viewer"])).status_code == 403
    assert client.get("/admin.js", headers=h(k["operator"])).status_code == 403
    assert client.get("/admin.js", headers=h(k["admin"])).status_code == 200


def test_denied_admin_attempts_are_audited(keys):
    client, k = keys
    client.get("/admin", headers=h(k["viewer"]))
    client.get("/admin.js")
    got = [(e["event"], e["actor"], e["path"], e["status"]) for e in entries()]
    assert ("denied", "viewer", "/admin", 403) in got
    assert ("denied", "anonymous", "/admin.js", 401) in got


def test_the_admin_api_stays_admin_only(keys):
    client, k = keys
    assert (
        client.post("/api/registry/reload", headers=h(k["operator"])).status_code == 403
    )
    assert client.post("/api/repos/x/sync", headers=h(k["operator"])).status_code == 403


# ---- ダッシュボードは管理操作のコードを載せない
def test_the_dashboard_carries_no_admin_code(make_client):
    with make_client() as client:
        html = client.get("/").text
        js = client.get("/static/app.js").text
        for marker in ADMIN_MARKERS:
            assert marker not in html, f"/ に管理操作の目印 {marker!r} が残っている"
            assert marker not in js, (
                f"/static/app.js に管理操作の目印 {marker!r} が残っている"
            )
        assert 'href="/admin"' in html


def test_the_admin_script_is_not_under_public_static(make_client):
    # /static に置くと、役割に関係なく誰にでも配られる
    with make_client() as client:
        assert client.get("/static/admin.js").status_code == 404
        assert client.get("/static/admin/admin.js").status_code == 404


def test_the_admin_link_is_hidden_from_non_admins(make_client):
    with make_client() as client:
        script = client.get("/static/auth.js").text
        assert 'me.role !== "admin"' in script and ".admin-link" in script
        assert "reload-registry-btn" not in script and "repo-sync-btn" not in script
