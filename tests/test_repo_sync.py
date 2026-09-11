"""hub/repo_sync.py のテスト。

ユーザー追加要件「gitの最新の状態を反映・差分ダウンロードという形で管理」の実装検証。
実際のGitHubには触れず、ローカルの一時git repoを「remote」役に見立てて検証する。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hub.repo_sync import RepoEntry, RepoRegistry, RepoRegistryError, RepoSyncManager


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


def _init_remote_and_clone(tmp_path: Path, name: str = "sample") -> tuple[Path, Path]:
    remote = tmp_path / f"{name}_remote"
    remote.mkdir()
    _git(["init", "-b", "main"], remote)
    _git(["config", "user.email", "test@example.com"], remote)
    _git(["config", "user.name", "Test"], remote)
    (remote / "file.txt").write_text("v1", encoding="utf-8")
    _git(["add", "file.txt"], remote)
    _git(["commit", "-m", "initial"], remote)

    local = tmp_path / f"{name}_local"
    _git(["clone", str(remote), str(local)], tmp_path)
    _git(["config", "user.email", "test@example.com"], local)
    _git(["config", "user.name", "Test"], local)
    return remote, local


def _commit_new_change(repo: Path, content: str = "v2") -> None:
    (repo / "file.txt").write_text(content, encoding="utf-8")
    _git(["add", "file.txt"], repo)
    _git(["commit", "-m", "update"], repo)


def test_repo_registry_loads_all_13_entries():
    registry = RepoRegistry.load()
    entries = registry.all()
    assert len(entries) == 13
    for e in entries:
        assert e.remote_url.startswith("https://github.com/manato1201/")
        assert e.branch == "main"


def test_repo_registry_rejects_duplicate_repo_id():
    with pytest.raises(RepoRegistryError):
        RepoRegistry(
            [
                RepoEntry("a", "A", "./a", "https://example.com/a.git"),
                RepoEntry("a", "A2", "./a2", "https://example.com/a2.git"),
            ]
        )


@pytest.mark.asyncio
async def test_check_reports_up_to_date_when_no_new_commits(tmp_path):
    _remote, local = _init_remote_and_clone(tmp_path)
    entry = RepoEntry("sample", "Sample", "sample_local", "unused", branch="main")
    manager = RepoSyncManager(RepoRegistry([entry]), repo_root=tmp_path)

    status = await manager.check(entry)

    assert status.exists_locally is True
    assert status.error is None
    assert status.commits_behind == 0
    assert status.is_up_to_date is True
    assert status.has_local_changes is False


@pytest.mark.asyncio
async def test_check_detects_commits_behind_without_mutating_working_tree(tmp_path):
    remote, local = _init_remote_and_clone(tmp_path)
    _commit_new_change(remote)

    entry = RepoEntry("sample", "Sample", "sample_local", "unused", branch="main")
    manager = RepoSyncManager(RepoRegistry([entry]), repo_root=tmp_path)

    status = await manager.check(entry)

    assert status.commits_behind == 1
    assert status.is_up_to_date is False
    # check()はfetchのみで、ワーキングツリーのfile.txtはv1のまま変化しない
    assert (local / "file.txt").read_text(encoding="utf-8") == "v1"


@pytest.mark.asyncio
async def test_check_detects_uncommitted_local_changes(tmp_path):
    _remote, local = _init_remote_and_clone(tmp_path)
    (local / "file.txt").write_text("locally edited, not committed", encoding="utf-8")

    entry = RepoEntry("sample", "Sample", "sample_local", "unused", branch="main")
    manager = RepoSyncManager(RepoRegistry([entry]), repo_root=tmp_path)

    status = await manager.check(entry)

    assert status.has_local_changes is True


@pytest.mark.asyncio
async def test_check_reports_error_when_local_clone_is_missing(tmp_path):
    entry = RepoEntry("ghost", "Ghost", "does_not_exist", "unused", branch="main")
    manager = RepoSyncManager(RepoRegistry([entry]), repo_root=tmp_path)

    status = await manager.check(entry)

    assert status.exists_locally is False
    assert status.error is not None


@pytest.mark.asyncio
async def test_sync_pulls_new_commits_when_clean_and_behind(tmp_path):
    remote, local = _init_remote_and_clone(tmp_path)
    _commit_new_change(remote, content="v2-from-remote")

    entry = RepoEntry("sample", "Sample", "sample_local", "unused", branch="main")
    manager = RepoSyncManager(RepoRegistry([entry]), repo_root=tmp_path)

    result = await manager.sync(entry)

    assert result.ok is True
    assert (local / "file.txt").read_text(encoding="utf-8") == "v2-from-remote"

    status_after = manager.last_status("sample")
    assert status_after.commits_behind == 0


@pytest.mark.asyncio
async def test_sync_refuses_when_working_tree_is_dirty(tmp_path):
    remote, local = _init_remote_and_clone(tmp_path)
    _commit_new_change(remote)
    (local / "file.txt").write_text("uncommitted local edit", encoding="utf-8")

    entry = RepoEntry("sample", "Sample", "sample_local", "unused", branch="main")
    manager = RepoSyncManager(RepoRegistry([entry]), repo_root=tmp_path)

    result = await manager.sync(entry)

    assert result.ok is False
    # 拒否されたので、ローカルの未コミット編集はそのまま残っている(破壊されていない)
    assert (local / "file.txt").read_text(encoding="utf-8") == "uncommitted local edit"


@pytest.mark.asyncio
async def test_sync_refuses_when_not_fast_forwardable(tmp_path):
    """ローカルにもリモートに無いコミットがある(履歴が分岐している)場合、
    --ff-onlyにより安全に失敗し、マージコミットを作らないことを確認する。
    """
    remote, local = _init_remote_and_clone(tmp_path)
    _commit_new_change(remote, content="v2-from-remote")
    # ローカル側にも別のコミットを作り、履歴を分岐させる
    (local / "another_file.txt").write_text("local-only commit", encoding="utf-8")
    _git(["add", "another_file.txt"], local)
    _git(["commit", "-m", "local divergent commit"], local)

    entry = RepoEntry("sample", "Sample", "sample_local", "unused", branch="main")
    manager = RepoSyncManager(RepoRegistry([entry]), repo_root=tmp_path)

    result = await manager.sync(entry)

    assert result.ok is False
    # file.txtはリモートの新しい内容に書き換わっていない(pullが拒否されたため)
    assert (local / "file.txt").read_text(encoding="utf-8") == "v1"


@pytest.mark.asyncio
async def test_sync_is_noop_when_already_up_to_date(tmp_path):
    _remote, _local = _init_remote_and_clone(tmp_path)
    entry = RepoEntry("sample", "Sample", "sample_local", "unused", branch="main")
    manager = RepoSyncManager(RepoRegistry([entry]), repo_root=tmp_path)

    result = await manager.sync(entry)

    assert result.ok is True


@pytest.mark.asyncio
async def test_check_all_covers_every_registered_entry(tmp_path):
    remote_a, _local_a = _init_remote_and_clone(tmp_path, name="a")
    remote_b, _local_b = _init_remote_and_clone(tmp_path, name="b")

    entries = [
        RepoEntry("a", "A", "a_local", "unused", branch="main"),
        RepoEntry("b", "B", "b_local", "unused", branch="main"),
    ]
    manager = RepoSyncManager(RepoRegistry(entries), repo_root=tmp_path)

    statuses = await manager.check_all()

    assert set(statuses.keys()) == {"a", "b"}
    assert all(s.error is None for s in statuses.values())
