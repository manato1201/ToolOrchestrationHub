"""hub/repo_sync.py

ユーザー追加要件: 「gitの最新の状態を反映・差分ダウンロードという形で管理」。

登録された各リポジトリ(hub/repos.yaml)について、ローカルクローンとGitHubリモートの
差分を検出する。安全性の方針は以下の2段階に明確に分ける:

- check(): `git fetch`のみ(リモート追跡ブランチの更新に留まり、ワーキングツリーは
  一切変更しない読み取り専用操作)。バックグラウンドで定期的に自動実行してよい
- sync(): `git pull --ff-only`(実際にワーキングツリーへ差分を取り込む)。
  Hubが無人で他プロジェクトのファイルを書き換えることはせず、人間がダッシュボードの
  「Sync」ボタンを明示的に押したときのみ実行する。ローカルに未コミットの変更がある
  場合や、fast-forwardできない(ローカル側にも別のコミットがある)場合は拒否する

これはToolOrchestrationHub全体の設計原則(Hubは監視のみ、各ツールの権限は奪わない)を
「他リポジトリのワーキングツリーを勝手に書き換えない」という形で具体化したものである。
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

DEFAULT_REPOS_PATH = Path(__file__).parent / "repos.yaml"
GIT_TIMEOUT_S = 20.0


class RepoRegistryError(Exception):
    """repos.yamlのパース/スキーマ検証に失敗した場合に送出する。"""


@dataclass(frozen=True)
class LaunchTarget:
    """ユーザー追加要件「個別に起動できるようにしたい」に対応する起動コマンド1件。

    13リポジトリは技術スタックが大きく異なり(Next.js/Vite/Python/Docker Compose等)、
    かつWeatherGeoBridge・VisualRegressionQATool・LoreDesktopAndWebSystemのように
    複数プロセスの起動が要る対象もあるため、1リポジトリが複数のLaunchTargetを
    持てるようにする(例: 「Backend」「Frontend」を別ボタンにする)。
    """

    name: str
    command: str  # シェルで実行するコマンド文字列(repos.yaml側で定義済みの固定値のみ)
    cwd: str = "."  # local_pathからの相対パス
    url: Optional[str] = None  # 起動確認(疎通チェック)に使うURL。無ければ確認しない


@dataclass(frozen=True)
class RepoEntry:
    repo_id: str
    display_name: str
    local_path: str  # Hub(このリポジトリ)のルートからの相対パス、または絶対パス
    remote_url: str
    branch: str = "main"
    launch_targets: tuple[LaunchTarget, ...] = ()
    launch_note: Optional[str] = None  # 起動コマンドが無い対象向けの説明(ビルド要/IDE拡張等)

    @classmethod
    def from_dict(cls, raw: dict) -> "RepoEntry":
        required = {"repo_id", "display_name", "local_path", "remote_url"}
        missing = required - raw.keys()
        if missing:
            raise RepoRegistryError(f"RepoEntryに必須フィールドが不足しています: {missing} (raw={raw})")
        launch_raw = raw.get("launch") or []
        launch_targets = tuple(
            LaunchTarget(
                name=lt["name"],
                command=lt["command"],
                cwd=lt.get("cwd", "."),
                url=lt.get("url"),
            )
            for lt in launch_raw
        )
        return cls(
            repo_id=raw["repo_id"],
            display_name=raw["display_name"],
            local_path=raw["local_path"],
            remote_url=raw["remote_url"],
            branch=raw.get("branch", "main"),
            launch_targets=launch_targets,
            launch_note=raw.get("launch_note"),
        )

    def resolve_path(self, repo_root: Path) -> Path:
        p = Path(self.local_path)
        return p if p.is_absolute() else (repo_root / p).resolve()


class RepoRegistry:
    def __init__(self, entries: list[RepoEntry]) -> None:
        self._by_id: dict[str, RepoEntry] = {}
        for e in entries:
            if e.repo_id in self._by_id:
                raise RepoRegistryError(f"repo_idが重複しています: {e.repo_id}")
            self._by_id[e.repo_id] = e

    @classmethod
    def load(cls, path: Path | str = DEFAULT_REPOS_PATH) -> "RepoRegistry":
        path = Path(path)
        try:
            with path.open(encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
        except yaml.YAMLError as exc:
            raise RepoRegistryError(f"{path} のYAMLパースに失敗しました: {exc}") from exc
        repos_raw = raw.get("repos")
        if repos_raw is None:
            raise RepoRegistryError(f"{path} に 'repos' キーがありません")
        return cls([RepoEntry.from_dict(r) for r in repos_raw])

    def all(self) -> list[RepoEntry]:
        return list(self._by_id.values())

    def get(self, repo_id: str) -> Optional[RepoEntry]:
        return self._by_id.get(repo_id)


@dataclass
class RepoStatus:
    repo_id: str
    checked_at: Optional[str] = None
    exists_locally: bool = False
    commits_behind: Optional[int] = None
    commits_ahead: Optional[int] = None
    has_local_changes: Optional[bool] = None
    error: Optional[str] = None

    @property
    def is_up_to_date(self) -> Optional[bool]:
        if self.commits_behind is None:
            return None
        return self.commits_behind == 0

    @property
    def can_sync(self) -> bool:
        return bool(
            self.exists_locally
            and self.error is None
            and self.commits_behind
            and self.commits_behind > 0
            and self.has_local_changes is False
        )


@dataclass
class RepoSyncResult:
    repo_id: str
    ok: bool
    message: str


async def _run_git(args: list[str], cwd: Path, timeout_s: float = GIT_TIMEOUT_S) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return proc.returncode, stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")


class RepoSyncManager:
    def __init__(self, registry: RepoRegistry, repo_root: Path) -> None:
        self._registry = registry
        self._repo_root = repo_root
        self._statuses: dict[str, RepoStatus] = {}
        # 同一リポジトリに対するgit操作(バックグラウンドのcheck_all()ループと、
        # ダッシュボードからの手動check/sync)が同時に走ると、両方が.gitへ触れて
        # index.lock競合等を起こしうる。repo_id単位でロックし直列化する。
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, repo_id: str) -> asyncio.Lock:
        lock = self._locks.get(repo_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[repo_id] = lock
        return lock

    def last_status(self, repo_id: str) -> Optional[RepoStatus]:
        return self._statuses.get(repo_id)

    def all_statuses(self) -> dict[str, RepoStatus]:
        return dict(self._statuses)

    async def check(self, entry: RepoEntry) -> RepoStatus:
        """git fetchのみ実行する読み取り専用チェック。ワーキングツリーは変更しない。"""
        async with self._lock_for(entry.repo_id):
            return await self._check_locked(entry)

    async def _check_locked(self, entry: RepoEntry) -> RepoStatus:
        local_path = entry.resolve_path(self._repo_root)
        now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

        if not (local_path / ".git").exists():
            status = RepoStatus(repo_id=entry.repo_id, checked_at=now, exists_locally=False, error="ローカルにクローンがありません")
            self._statuses[entry.repo_id] = status
            return status

        try:
            rc, _out, err = await _run_git(["fetch", "origin", entry.branch], cwd=local_path)
            if rc != 0:
                status = RepoStatus(
                    repo_id=entry.repo_id, checked_at=now, exists_locally=True, error=f"git fetch failed: {err.strip()[:200]}"
                )
                self._statuses[entry.repo_id] = status
                return status

            rc, out, err = await _run_git(
                ["rev-list", "--left-right", "--count", f"HEAD...origin/{entry.branch}"], cwd=local_path
            )
            if rc != 0:
                status = RepoStatus(
                    repo_id=entry.repo_id, checked_at=now, exists_locally=True, error=f"git rev-list failed: {err.strip()[:200]}"
                )
                self._statuses[entry.repo_id] = status
                return status
            ahead_str, behind_str = out.split()
            ahead, behind = int(ahead_str), int(behind_str)

            rc, out, _err = await _run_git(["status", "--porcelain"], cwd=local_path)
            has_local_changes = bool(out.strip())

            status = RepoStatus(
                repo_id=entry.repo_id,
                checked_at=now,
                exists_locally=True,
                commits_behind=behind,
                commits_ahead=ahead,
                has_local_changes=has_local_changes,
            )
            self._statuses[entry.repo_id] = status
            return status
        except asyncio.TimeoutError:
            status = RepoStatus(repo_id=entry.repo_id, checked_at=now, exists_locally=True, error="git操作がタイムアウトしました")
            self._statuses[entry.repo_id] = status
            return status
        except Exception as exc:  # noqa: BLE001 - 1リポジトリの異常で他に波及させない
            status = RepoStatus(repo_id=entry.repo_id, checked_at=now, exists_locally=True, error=str(exc)[:200])
            self._statuses[entry.repo_id] = status
            return status

    async def check_all(self) -> dict[str, RepoStatus]:
        for entry in self._registry.all():
            await self.check(entry)
        return self.all_statuses()

    async def sync(self, entry: RepoEntry) -> RepoSyncResult:
        """差分を実際に取り込む(git pull --ff-only)。人間の明示トリガでのみ呼ぶこと。

        - ローカルに未コミットの変更がある場合は拒否する(他プロジェクトの作業を破壊しない)
        - fast-forwardできない場合(ローカル側にもリモートに無いコミットがある)は拒否する
          (--ff-onlyにより、pull自体がマージコミットを作らず安全に失敗する)

        check()と同じロックを使って一連の操作(再チェック→pull→再チェック)を直列化する。
        asyncio.Lockは非再入のため、内部ではロック済みの_check_lockedを直接呼ぶ
        (check()を呼ぶと同じタスク内で二重取得しデッドロックする)。
        """
        async with self._lock_for(entry.repo_id):
            status = await self._check_locked(entry)
            if status.error is not None:
                return RepoSyncResult(repo_id=entry.repo_id, ok=False, message=status.error)
            if not status.exists_locally:
                return RepoSyncResult(repo_id=entry.repo_id, ok=False, message="ローカルにクローンがありません")
            if status.has_local_changes:
                return RepoSyncResult(
                    repo_id=entry.repo_id, ok=False, message="ローカルに未コミットの変更があるため同期しません"
                )
            if status.commits_behind == 0:
                return RepoSyncResult(repo_id=entry.repo_id, ok=True, message="既に最新です")

            local_path = entry.resolve_path(self._repo_root)
            try:
                rc, out, err = await _run_git(["pull", "--ff-only", "origin", entry.branch], cwd=local_path)
            except asyncio.TimeoutError:
                return RepoSyncResult(repo_id=entry.repo_id, ok=False, message="git pullがタイムアウトしました")
            if rc != 0:
                return RepoSyncResult(repo_id=entry.repo_id, ok=False, message=f"git pull failed: {err.strip()[:200]}")

            await self._check_locked(entry)
            return RepoSyncResult(repo_id=entry.repo_id, ok=True, message=out.strip()[:200] or "同期しました")
