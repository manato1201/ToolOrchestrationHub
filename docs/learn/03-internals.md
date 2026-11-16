# 3. 内側のしくみ

講義(第 1〜5 回)で扱った核のほかに、**保存・通知・git 同期・起動**の中身を説明します。

## 1. アラートの保存(`alert_store.py`)

`AlertAggregator` は、保存の実装を**知りません**。`AlertStore` という **`Protocol`**(`save`・`load_all`・`delete`)を満たすものを渡されるだけです。依存の向きは `alert_store.py → alert_aggregator.py` の**一方向**で、循環 import を避けています。

**表の形**(1 行 = 1 回の「発生 → 解消」):

```text
alerts(alert_id, source_tool_id, severity, message, first_seen_at, resolved_at, occurrence_count)
PRIMARY KEY (alert_id, first_seen_at)
```

```python
# 引用: hub/alert_store.py::SqliteAlertStore.save
def save(self, alert: AlertRecord) -> None:
    """(alert_id, first_seen_at)で upsert する。同一ライフサイクルなら更新、再発なら別行を追加する。"""
    self._conn.execute(
        """
        INSERT INTO alerts (alert_id, source_tool_id, severity, message, first_seen_at, resolved_at, occurrence_count)
        VALUES (:alert_id, :source_tool_id, :severity, :message, :first_seen_at, :resolved_at, :occurrence_count)
        ON CONFLICT(alert_id, first_seen_at) DO UPDATE SET
            severity = excluded.severity,
            message = excluded.message,
            resolved_at = excluded.resolved_at,
            occurrence_count = excluded.occurrence_count
        """,
        {
            "alert_id": alert.alert_id,
            "source_tool_id": alert.source_tool_id,
            "severity": alert.severity.value,
            "message": alert.message,
            "first_seen_at": alert.first_seen_at.isoformat(),
            "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
            "occurrence_count": alert.occurrence_count,
        },
    )
    self._conn.commit()
```

- **主キーが `(alert_id, first_seen_at)`**: 同じ異常が再発したら、`first_seen_at` が違うので**別の行**になる。以前は `alert_id` だけが主キーで、再発のたびに過去の行が**上書き**され、「いつからいつまで止まっていたか」が失われていた(v2.5 で修正)。
- **`ON CONFLICT ... DO UPDATE`(upsert)**: 同じライフサイクルの更新(解消の時刻・メッセージ)は、行を更新する。
- **名前付きパラメータ(`:alert_id`)**: SQL に値を**文字列連結しない**ので、SQL インジェクションにならない。
- **旧スキーマの移行**(`_migrate_legacy_schema`): `occurrence_count` 列が無い旧 DB を、初回起動時に、**1 つのトランザクション**(`BEGIN` … `COMMIT`/`ROLLBACK`)で新しい表へ移す。途中で失敗しても、旧データが失われない。
- **時刻は ISO 8601 の文字列**(`isoformat()`)で保存し、`fromisoformat` で戻す。タイムゾーン付き(UTC)。
- **接続**は `check_same_thread=False`(FastAPI の別スレッドから使うため)。**書き込みのたびに `commit`**(件数が少ないので単純さを取る)。

## 2. 通知(`notify.py`)

`NotificationSink` という `Protocol`(`notify_opened`・`notify_resolved`)を満たす実装が、複数あります。

| 実装 | 動く条件 |
|---|---|
| `WindowsToastSink` | Windows かつ `winotify` が入っている。既定で重大度 `warn` 以上 |
| `SlackWebhookSink` | 環境変数 `HUB_SLACK_WEBHOOK_URL` がある |
| `NullSink` | 上のどれも使えない(何もしない) |
| `CompositeSink` | 複数をまとめる(下) |

```python
# 引用: hub/notify.py::CompositeSink
class CompositeSink:
    """複数のNotificationSinkへ独立にfan-outする。

    1つのsinkの配信失敗(例外)が他のsinkの配信を止めないよう、各sink呼び出しを
    個別にtry/exceptで囲む(WindowsToastSink自身も内部で握りつぶしているが、
    将来追加されるsink実装が同じ規律を守るとは限らないための二重の安全網)。
    """

    def __init__(self, sinks: list[NotificationSink]) -> None:
        self._sinks = sinks

    def notify_opened(self, alert: AlertRecord) -> None:
        for sink in self._sinks:
            try:
                sink.notify_opened(alert)
            except Exception:
                logger.exception("NotificationSink.notify_openedの呼び出しに失敗しました")

    def notify_resolved(self, alert: AlertRecord) -> None:
        for sink in self._sinks:
            try:
                sink.notify_resolved(alert)
            except Exception:
                logger.exception("NotificationSink.notify_resolvedの呼び出しに失敗しました")
```

**1 つの通知先が失敗しても、他の通知先を止めない**よう、1 件ずつ `try/except` で囲んでいます(「二重の安全網」: 各実装も内部で握りつぶす)。失敗は `logger.exception` で**ログに残す**(握りつぶしたまま消さない)。
`default_sink()` が、使える通知先を集めて、**0 個なら `NullSink`・1 個ならそのもの・2 個以上なら `CompositeSink`** を返します。

> 通知の**種類(トースト・Slack)の追加**は、`NotificationSink` を満たすクラスを足して、`default_sink()` に条件を足すだけ([4 拡張](04-extend.md) レシピ 4)。`AlertAggregator` は変えません。

## 3. リポジトリの同期(`repo_sync.py`)

`repos.yaml` に載せた 13 リポジトリを、2 段階の**安全の方針**で扱います。

| 操作 | いつ | 何をするか | 作業ツリー |
|---|---|---|---|
| **差分の検知**(`check`) | **自動**(30 分ごと)・「Check all」 | `git fetch origin <branch>` → `rev-list --left-right --count HEAD...origin/<branch>` で**遅れ・進み**を数える → `status --porcelain` で未コミットの有無 | **変えない** |
| **取り込み**(`sync`) | **人が `/admin` の Sync を押したときだけ**(admin) | `git pull --ff-only origin <branch>` | 更新する |

```python
# 引用: hub/repo_sync.py::RepoSyncManager.sync
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
```

**拒否する条件**(他のプロジェクトの作業を壊さないため): ①ローカルに**未コミットの変更**がある ②**fast-forward できない**(ローカルにだけあるコミットがある → `--ff-only` が失敗)③ローカルにクローンが無い ④検知でエラー。**既に最新**なら何もしない。

- **`asyncio.Lock` を `repo_id` ごとに**持つ: 同じリポジトリへの `git` 操作(バックグラウンドの検知と手動の同期)が**同時に走らない**(`index.lock` の衝突を避ける)。別のリポジトリ同士は**並行**に走る(13 個分の `git fetch` を直列にすると遅いため)。
- **`sync` の中で `check()` でなく `_check_locked` を呼ぶ**: `asyncio.Lock` は**再入できない**ので、`check()` を呼ぶと、同じタスクが同じロックを二度取ろうとして**デッドロック**する(コメントが警告している)。
- **`GIT_TIMEOUT_S = 20`**: `git` が固まっても、Hub が待ち続けない。

## 4. 起動(`process_launcher.py`)

「Start」ボタンは、**人が手でターミナルを開いてコマンドを打つ操作を、代行するだけ**です。

```python
# 引用: hub/process_launcher.py::launch
def launch(
    entry: RepoEntry,
    target: LaunchTarget,
    repo_root: Path,
    *,
    popen: Callable[..., subprocess.Popen] = subprocess.Popen,
    is_command_available: Callable[[str], Optional[bool]] = check_command_available,
) -> LaunchResult:
    """target.commandを新しいコンソールウィンドウで起動する(Windows)。

    Hubプロセスの標準入出力は継承しない(起動対象自身のログは新規コンソールに出る)。
    Popenは子プロセスを起動して即座に戻るため、Hubのイベントループをブロックしない。
    `popen`はテスト時に実プロセスを起動させないための差し替え口。`is_command_available`は
    実行環境のPATH状態に依存させたくないテストのための差し替え口(既定は本物のshutil.which)。
    """
    local_path = entry.resolve_path(repo_root)
    cwd = (local_path / target.cwd).resolve()
    if not cwd.exists():
        return LaunchResult(ok=False, message=f"作業ディレクトリが存在しません: {cwd}")

    if is_command_available(target.command) is False:
        exe = required_executable(target.command)
        return LaunchResult(
            ok=False,
            message=f"コマンド '{exe}' がPATH上に見つかりません。インストール状況を確認してください: {target.command}",
        )

    kwargs: dict = {"cwd": str(cwd), "shell": True}
    if sys.platform == "win32":
        kwargs["creationflags"] = CREATE_NEW_CONSOLE
    else:
        kwargs["start_new_session"] = True  # stop() がプロセスグループごと止められるように

    try:
        proc = popen(target.command, **kwargs)
    except OSError as exc:
        return LaunchResult(ok=False, message=str(exc))

    return LaunchResult(ok=True, message=f"起動しました: {target.command}", pid=getattr(proc, "pid", None))
```

- **実行するコマンドは、HTTP のリクエストからでなく、`repos.yaml` の固定値だけ**。リクエストで受け取るのは `repo_id` と **`target_index`(番号)**だけなので、任意のコマンドを注入する経路は**ありません**。
- **`shell=True`**: `repos.yaml` のコマンドを、シェルとして実行する。**だから、`repos.yaml` は「コードを実行できるファイル」**として、書き換えられる人を**信頼できる人だけ**に限る(信頼の境界)。Hub が `repos.yaml` を**書き換える**機能は持たない。
- **`CREATE_NEW_CONSOLE`**: 新しいコンソール窓で起動し、Hub の標準入出力を**継承しない**。起動後の管理(停止・再起動・ログ)は**しない**(開いた窓を、人が直接操作する)。
- **差し替え口**(`popen`・`is_command_available`): テストで**本物のプロセスを起動しない**ため。
- **事前確認**(`shutil.which`): `npm`・`uv`・`docker` が PATH に無いと、「見つかりません」と**具体的に**返す(窓が一瞬開いて閉じるだけ、にならない)。
- 「running」の表示は、`launch.url` への**疎通確認だけ**(プロセスの識別はしない)。**複数のリポジトリが同じ既定ポート**(Vite の 5173 など)を使うと、**別のリポジトリが動いているのに「running」と誤表示**することがある(確認済みの制約。画面にも注記)。

## 5. 画面用の概況(`overview.py`)

`build_overview(entries, alerts=..., results=..., ages=..., checked=..., at=..., decorate_alert=...)` は、**純関数**で、画面に出す辞書を組み立てます。

- `at` を渡さなければ**ライブ**(いま open のアラート)、渡せば**履歴の再現**(`is_open_at(at)`)。
- 各ツールの状態は `derive_tool_state`(講義第 4 回)。**一覧・オフィス・サマリで同じ関数**。
- 「**波及の見込み**」: 停止しているツールを `depends_on` で**使っているツール**の木(`tree()`)。台帳の記述から読み取れる関係だけで、**実測ではない**(画面にもそう書く)。`seen`(通った印)で、循環があっても止まる(台帳の読み込み時にも弾いている二重の安全網)。
- `decorate_alert`: 各アラートに、**見る順番(優先度)**と**運用手順**を足す。**表示専用**。

## 6. 入口の守り(Host・Origin・認証・監査)

講義[第 5 回](../lecture/05-security-and-auth.md)の内容を、**配線の順**でまとめます。`create_app` は、ミドルウェアを入れる順番に意味があります。

1. **監査**(`install_audit`)を**外側**に: ガードの 403 も記録するため。
2. **リクエストガード**(`install_request_guard`): Host の許可リスト、変更操作の Origin。
3. **ルートごとの役割**(`dependencies=[auth.viewer / operator / admin]`)。`HUB_AUTH=off` なら全員が `ANONYMOUS`(admin 扱い)。
4. **ログイン**(`auth_routes.py`): API キーを **HttpOnly・SameSite=Strict のクッキー**にする(スクリプトから読めず、別サイトからは送られない)。
5. **`/admin` の分離**: `admin.js` を `/static` の**外**に置き、**admin にしか配らない**(viewer・operator には、JavaScript の中身も見せない)。

### ユーザーの管理(CLI)

```bash
uv run python -m hub.auth add --name alice --role admin       # キーは 1 度だけ表示される
uv run python -m hub.auth add --name profiler --role operator # 各ツールが送るためのキー
uv run python -m hub.auth list
uv run python -m hub.auth remove --name alice                 # そのキーはすぐ使えなくなる
```

保存先は `~/.tool_orchestration_hub/auth_users.json`(`HUB_AUTH_FILE` で変更)。`save_users` は、**一時ファイルに書いてから置き換える**(`tmp.replace(path)`)ので、書き込み中に落ちても、**半端なファイルが残らない**(アトミックな置き換え)。
