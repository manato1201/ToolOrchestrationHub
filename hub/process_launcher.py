"""hub/process_launcher.py

ユーザー追加要件「個別に起動できるようにしたい」の実装。

Hubは「起動ボタンを押したら、そのツール用のコマンドを新しいコンソールウィンドウで
実行する」という、人間が手動でターミナルを開いてコマンドを打つのと同じ操作を代行する
だけに留める。起動後のプロセスのライフサイクル管理(停止・再起動・ログ収集・出力の
監視等)はスコープ外とし、開いたコンソールウィンドウ自体をユーザーが直接操作する前提
とする(Hubは監視・中継のみ、各ツールの権限は奪わないという設計原則の延長 — Hubが
裏でプロセスを握り続けて制御するのではなく、起動した後は完全にユーザーの手に渡す)。

コマンド文字列はHTTPリクエストから受け取らず、hub/repos.yamlに定義済みの固定値
(LaunchTarget.command)のみを実行する。ユーザー入力をシェルコマンドへ直接連結する
経路は無い。
"""
from __future__ import annotations

import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .repo_sync import LaunchTarget, RepoEntry

CREATE_NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)


@dataclass
class LaunchResult:
    ok: bool
    message: str
    pid: Optional[int] = None


def launch(
    entry: RepoEntry,
    target: LaunchTarget,
    repo_root: Path,
    *,
    popen: Callable[..., subprocess.Popen] = subprocess.Popen,
) -> LaunchResult:
    """target.commandを新しいコンソールウィンドウで起動する(Windows)。

    Hubプロセスの標準入出力は継承しない(起動対象自身のログは新規コンソールに出る)。
    Popenは子プロセスを起動して即座に戻るため、Hubのイベントループをブロックしない。
    `popen`はテスト時に実プロセスを起動させないための差し替え口。
    """
    local_path = entry.resolve_path(repo_root)
    cwd = (local_path / target.cwd).resolve()
    if not cwd.exists():
        return LaunchResult(ok=False, message=f"作業ディレクトリが存在しません: {cwd}")

    kwargs: dict = {"cwd": str(cwd), "shell": True}
    if sys.platform == "win32":
        kwargs["creationflags"] = CREATE_NEW_CONSOLE

    try:
        proc = popen(target.command, **kwargs)
    except OSError as exc:
        return LaunchResult(ok=False, message=str(exc))

    return LaunchResult(ok=True, message=f"起動しました: {target.command}", pid=getattr(proc, "pid", None))


def open_folder(
    entry: RepoEntry,
    repo_root: Path,
    *,
    popen: Callable[..., subprocess.Popen] = subprocess.Popen,
) -> LaunchResult:
    """OSのファイルマネージャでリポジトリのローカルフォルダを開く。

    起動コマンドを持たない対象(ビルドが要る/IDE拡張等)でも、少なくともフォルダは
    開けるようにする(全リポジトリ共通の最低限のアクション)。
    """
    local_path = entry.resolve_path(repo_root)
    if not local_path.exists():
        return LaunchResult(ok=False, message=f"フォルダが存在しません: {local_path}")

    try:
        if sys.platform == "win32":
            popen(["explorer", str(local_path)])
        else:
            popen(["xdg-open", str(local_path)])
    except OSError as exc:
        return LaunchResult(ok=False, message=str(exc))
    return LaunchResult(ok=True, message=f"開きました: {local_path}")


def check_target_reachable(target: LaunchTarget, timeout_s: float = 0.5) -> Optional[bool]:
    """target.urlへの疎通確認(既に起動済みかどうかの簡易判定)。urlが無ければNone。"""
    if not target.url:
        return None
    try:
        with urllib.request.urlopen(target.url, timeout=timeout_s):
            return True
    except (urllib.error.URLError, OSError):
        return False
