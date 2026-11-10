"""テスト共通のフィクスチャ。"""
from __future__ import annotations

import pytest

from hub.repo_sync import RepoRegistry


@pytest.fixture
def no_real_repo_sync(monkeypatch):
    """repos_pathを渡さないappが、実際のGitHub上の13リポジトリへgit fetchしないようにする。

    create_app()はlifespan起動時にRepoSyncManager.check_all()を即座に1回実行するため、何もしないと
    本物のfetchが走ってしまう(遅い・ネットワーク依存・実マシンのフォルダ構成に依存する)。
    repos_pathを明示的に渡したテストは通常どおり読み込み、省略時だけ空のレジストリにする。
    tests/test_dashboard_app.py は同じ内容を自前のautouseフィクスチャで持っている。
    """
    original_load = RepoRegistry.load.__func__

    def _load(cls, path=None):
        if path is not None:
            return original_load(cls, path)
        return cls([])

    monkeypatch.setattr(RepoRegistry, "load", classmethod(_load))


@pytest.fixture(autouse=True)
def _allow_testserver_host(monkeypatch):
    """TestClientは Host: testserver で送る。Hostの許可リスト(hub/security.py)に足しておく。
    許可リストの挙動そのものを調べるテスト(tests/test_security.py)は、このフィクスチャの上書き/削除で行う。
    """
    monkeypatch.setenv("HUB_ALLOWED_HOSTS", "testserver")


@pytest.fixture(autouse=True)
def _isolate_auth_and_audit(tmp_path, monkeypatch):
    """認証(hub/auth.py)と監査ログ(hub/audit.py)を、テストごとの一時ファイルに向ける(本物の ~/.tool_orchestration_hub に書かない)。
    既定は認証 off(従来どおり)。認証のテストは tests/test_auth.py・tests/test_audit.py で required にする。"""
    monkeypatch.setenv("HUB_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("HUB_AUTH_FILE", str(tmp_path / "auth_users.json"))
    for name in ("HUB_AUTH", "HUB_CF_ACCESS_TEAM_DOMAIN", "HUB_CF_ACCESS_AUD"):
        monkeypatch.delenv(name, raising=False)
