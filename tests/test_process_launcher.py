"""hub/process_launcher.py のテスト。

ユーザー追加要件「個別に起動できるようにしたい」の実装検証。
実際にコンソールウィンドウ/プロセスを立ち上げないよう、popen差し替え口を使う。
"""

from __future__ import annotations

from pathlib import Path

from hub.process_launcher import CREATE_NEW_CONSOLE, launch, open_folder
from hub.repo_sync import LaunchTarget, RepoEntry


class _FakeProc:
    def __init__(self, pid: int = 4242) -> None:
        self.pid = pid


def test_launch_spawns_configured_command_in_resolved_cwd(tmp_path):
    local_path = tmp_path / "sample_repo"
    (local_path / "frontend").mkdir(parents=True)

    entry = RepoEntry(
        repo_id="sample",
        display_name="Sample",
        local_path="sample_repo",
        remote_url="unused",
    )
    target = LaunchTarget(
        name="Frontend",
        command="npm run dev",
        cwd="frontend",
        url="http://localhost:5173",
    )

    calls = []

    def fake_popen(command, **kwargs):
        calls.append((command, kwargs))
        return _FakeProc(pid=1234)

    result = launch(
        entry,
        target,
        repo_root=tmp_path,
        popen=fake_popen,
        is_command_available=lambda cmd: True,
    )

    assert result.ok is True
    assert result.pid == 1234
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command == "npm run dev"
    assert kwargs["cwd"] == str((local_path / "frontend").resolve())
    assert kwargs["shell"] is True


def test_launch_fails_gracefully_when_cwd_missing(tmp_path):
    entry = RepoEntry(
        repo_id="sample",
        display_name="Sample",
        local_path="does_not_exist",
        remote_url="unused",
    )
    target = LaunchTarget(name="X", command="echo hi")

    result = launch(
        entry, target, repo_root=tmp_path, popen=lambda *a, **k: _FakeProc()
    )

    assert result.ok is False
    assert "存在しません" in result.message


def test_launch_reports_oserror_without_raising(tmp_path):
    local_path = tmp_path / "sample_repo"
    local_path.mkdir()
    entry = RepoEntry(
        repo_id="sample",
        display_name="Sample",
        local_path="sample_repo",
        remote_url="unused",
    )
    target = LaunchTarget(name="X", command="not-a-real-command")

    def failing_popen(*args, **kwargs):
        raise OSError("command not found")

    result = launch(
        entry,
        target,
        repo_root=tmp_path,
        popen=failing_popen,
        is_command_available=lambda cmd: True,
    )

    assert result.ok is False
    assert "command not found" in result.message


def test_launch_rejects_command_when_executable_not_on_path(tmp_path):
    """ユーザー追加要件「起動コマンドの健全性チェック」。PATH上に無い実行ファイルは
    Popenを試みる前に分かりやすいメッセージで拒否する。
    """
    local_path = tmp_path / "sample_repo"
    local_path.mkdir()
    entry = RepoEntry(
        repo_id="sample",
        display_name="Sample",
        local_path="sample_repo",
        remote_url="unused",
    )
    target = LaunchTarget(name="X", command="not-a-real-command --flag")

    calls = []

    def should_not_be_called(*args, **kwargs):
        calls.append(1)
        return _FakeProc()

    result = launch(
        entry,
        target,
        repo_root=tmp_path,
        popen=should_not_be_called,
        is_command_available=lambda cmd: False,
    )

    assert result.ok is False
    assert "not-a-real-command" in result.message
    assert calls == []


def test_open_folder_spawns_explorer_with_resolved_path(tmp_path):
    local_path = tmp_path / "sample_repo"
    local_path.mkdir()
    entry = RepoEntry(
        repo_id="sample",
        display_name="Sample",
        local_path="sample_repo",
        remote_url="unused",
    )

    calls = []

    def fake_popen(args, **kwargs):
        calls.append(args)
        return _FakeProc()

    result = open_folder(entry, repo_root=tmp_path, popen=fake_popen)

    assert result.ok is True
    assert len(calls) == 1
    assert str(local_path.resolve()) in calls[0]


def test_open_folder_fails_when_path_missing(tmp_path):
    entry = RepoEntry(
        repo_id="sample",
        display_name="Sample",
        local_path="does_not_exist",
        remote_url="unused",
    )

    result = open_folder(entry, repo_root=tmp_path, popen=lambda *a, **k: _FakeProc())

    assert result.ok is False


def test_repo_entry_parses_launch_targets_from_dict():
    entry = RepoEntry.from_dict(
        {
            "repo_id": "x",
            "display_name": "X",
            "local_path": "../x",
            "remote_url": "https://example.com/x.git",
            "launch": [
                {
                    "name": "Backend",
                    "command": "uv run uvicorn app.main:app --port 8000",
                    "cwd": "backend",
                    "url": "http://localhost:8000",
                },
                {"name": "Frontend", "command": "npm run dev", "cwd": "frontend"},
            ],
        }
    )
    assert len(entry.launch_targets) == 2
    assert entry.launch_targets[0].name == "Backend"
    assert entry.launch_targets[0].url == "http://localhost:8000"
    assert entry.launch_targets[1].url is None


def test_repo_entry_without_launch_key_has_no_targets():
    entry = RepoEntry.from_dict(
        {
            "repo_id": "x",
            "display_name": "X",
            "local_path": "../x",
            "remote_url": "https://example.com/x.git",
        }
    )
    assert entry.launch_targets == ()


def test_create_new_console_flag_is_platform_appropriate():
    # win32以外ではプラットフォーム固有フラグを持たないため0にフォールバックする
    assert isinstance(CREATE_NEW_CONSOLE, int)


def test_check_target_reachable_returns_none_without_url():
    from hub.process_launcher import check_target_reachable

    target = LaunchTarget(name="X", command="echo hi")
    assert check_target_reachable(target) is None


def test_check_target_reachable_returns_false_when_nothing_listening():
    from hub.process_launcher import check_target_reachable

    target = LaunchTarget(name="X", command="echo hi", url="http://127.0.0.1:1")
    assert check_target_reachable(target) is False


def test_check_target_reachable_returns_false_for_malformed_url_instead_of_raising():
    """再監査で発見: urlopen()はスキーム無し等の不正なurlに対してURLError/OSErrorではなく
    ValueErrorを送出する。repos.yaml側の設定ミス1件がバックグラウンド更新ループ全体を
    巻き込んで止めないよう、呼び出し元へ例外を伝播させずFalseを返す。
    """
    from hub.process_launcher import check_target_reachable

    target = LaunchTarget(name="X", command="echo hi", url="not-a-valid-url")
    assert check_target_reachable(target) is False


def test_required_executable_extracts_first_token():
    from hub.process_launcher import required_executable

    assert required_executable("npm run dev") == "npm"
    assert required_executable("uv run uvicorn app.main:app --port 8000") == "uv"
    assert required_executable("  docker compose up  ") == "docker"
    assert required_executable("") is None


def test_check_command_available_returns_true_for_a_real_executable():
    from hub.process_launcher import check_command_available

    # python(uvが動いているPython実行環境そのもの)は常にPATH上に存在するはず。
    import sys

    assert check_command_available(f"{Path(sys.executable).name} --version") is True


def test_check_command_available_returns_false_for_a_fake_executable():
    from hub.process_launcher import check_command_available

    assert (
        check_command_available("definitely-not-a-real-executable-xyz --flag") is False
    )


def test_check_command_available_returns_none_for_empty_command():
    from hub.process_launcher import check_command_available

    assert check_command_available("") is None
