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


# ---- 停止(2026-11-17) ----
import subprocess  # noqa: E402

from hub.process_launcher import StopResult, is_alive, stop  # noqa: E402


def test_stop_without_a_recorded_pid_does_nothing():
    calls = []
    res = stop(None, run=lambda *a, **k: calls.append(a))
    assert res.ok is False and "記録" in res.message and calls == []


def test_stop_refuses_when_the_process_is_gone_or_reused():
    calls = []
    res = stop(4242, run=lambda *a, **k: calls.append(a), alive=lambda pid: False)
    assert res.ok is False and "止まっています" in res.message
    assert calls == []  # 別のプロセスにPIDが使い回されていても、止めない


def test_stop_kills_the_process_tree_of_the_recorded_pid(monkeypatch):
    monkeypatch.setattr("hub.process_launcher.sys.platform", "win32")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    res = stop(4242, run=fake_run, alive=lambda pid: True)
    assert res.ok is True
    assert calls == [["taskkill", "/PID", "4242", "/T", "/F"]]  # 木ごと(/T)・そのPIDだけ


def test_stop_reports_taskkill_failure_without_claiming_success(monkeypatch):
    monkeypatch.setattr("hub.process_launcher.sys.platform", "win32")
    res = stop(4242, run=lambda cmd, **k: subprocess.CompletedProcess(cmd, 128, "", "x"), alive=lambda pid: True)
    assert res.ok is False


def test_is_alive_needs_the_same_kind_of_process_that_was_launched(monkeypatch):
    monkeypatch.setattr("hub.process_launcher.sys.platform", "win32")
    assert is_alive(10, image_name=lambda pid: "cmd.exe") is True
    assert is_alive(10, image_name=lambda pid: "chrome.exe") is False  # PIDが別のプロセスに使い回された
    assert is_alive(10, image_name=lambda pid: None) is False
    assert is_alive(None) is False


def test_launch_target_opens_the_url_by_default_and_can_opt_out():
    """open は Web GUI なら既定で true(起動後に自動で開く)。API・ヘルスチェックだけなら open: false。"""
    entry = RepoEntry.from_dict(
        {
            "repo_id": "x",
            "display_name": "X",
            "local_path": "../x",
            "remote_url": "https://example.com/x.git",
            "launch": [
                {"name": "GUI", "command": "npm run dev", "url": "http://localhost:3000"},
                {"name": "API", "command": "uv run api", "url": "http://localhost:8000/health", "open": False},
            ],
        }
    )
    assert entry.launch_targets[0].open is True
    assert entry.launch_targets[1].open is False


def test_repos_yaml_opens_only_web_screens_and_has_chapterlens():
    """本物の repos.yaml: 画面の無い対象(ヘルスチェック・API)は自動で開かない。ChapterLens のエンジンを起動・停止できる。"""
    from hub.repo_sync import RepoRegistry

    registry = RepoRegistry.load()
    chapterlens = registry.get("chapterlens")
    assert chapterlens is not None
    (engine,) = chapterlens.launch_targets
    assert engine.cwd == "engine" and engine.command.startswith("uv run python -m chapterlens serve")
    # 拡張(固定の ID)だけを許す。全許可(*)にはしない
    assert "--allow-origin chrome-extension://" in engine.command and "*" not in engine.command
    assert engine.url == "http://127.0.0.1:8787/health" and engine.open is False

    for entry in registry.all():
        for target in entry.launch_targets:
            if target.url and target.url.rstrip("/").endswith(("/health", "/api/health")):
                assert target.open is False, f"{entry.repo_id}/{target.name}"
