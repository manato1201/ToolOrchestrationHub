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
