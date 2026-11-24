"""hub/dashboard/app.py

Phase4: 統合ダッシュボード(可視化)。

表示対象は4種類。いずれも既存ツールが既に生成しているアーティファクトを
そのまま読み込むだけで、Hub側での加工・再計算は行わない
(hub/dashboard/data_sources.py参照)。

バックグラウンドの`_poll_loop`はPhase2のLivenessMonitorを定期的に叩くが、
実際のネットワーク呼び出しは各ToolEntryのpoll_interval_sでレート制限されるため、
このループ自体の頻度(POLL_LOOP_INTERVAL_S)は「非hot-path原則」に抵触しない。

v1.1で以下を追加した(DESIGN.mdのPhase0-4確定後の実利用フィードバックによる拡張。
Hub自身の内部アーキテクチャ(Registry/Relay/AlertAggregatorの3層構成)は変更していない):
- hub/notify.py: 新規/解消アラートのWindowsトースト通知
- registry.yamlのホットリロード(自動監視 + POST /api/registry/reload)
- hub/alert_store.py: アラート履歴のSQLite永続化 + 古いresolved分の自動prune
- ダッシュボードの自動更新(meta refresh)
- POST /api/heartbeat/{tool_id}, POST /api/ci-success/{tool_id}:
  observed_only/cli_batch系ツールからの受動的なliveness信号の受信口

v1.2: Phase3は「Profiling Tool(主経路)/Visual Regression QA Tool/Asset Data Insight
Suite/Hub自身のヘルスチェックの4ソースをAlertRecordへ正規化する」としていたが、
normalize_from_profiling_tool/normalize_from_visual_regression_qa/
normalize_from_asset_data_insightの3関数はhub/alert_aggregator.pyに定義済みのまま
呼び出し口が無く、実際にAlertAggregatorへ届くのはHub自身のヘルスチェック由来のみだった。
POST /api/alerts/{profiling-tool,visual-regression-qa,asset-data-insight}を追加し、
4ソース全てが実際にAlertAggregatorへ到達するようにした(Hubが能動的に取得しにいくのではなく、
各ツール側からPOSTしてもらう受動受信の設計はheartbeat/ci-successと同じ)。

v2.0: 「ToolOrchestrationHubが主軸、ProfilingToolはサブ機能」という方針のもと、
別リポジトリだったProfilingToolを`profiling_tool/`サブパッケージとして本リポジトリに
統合した。このダッシュボードの「Profiling」セクションがprofiling_tool/dashboard/
data_sources.pyを直接(同一プロセス内で)呼び出し、最新runのlatency/usageサマリを表示する。
profiling_tool自身のスタンドアロン版ダッシュボード(`uv run profiling-dashboard`)は
詳細に掘り下げたいときのオプション画面として引き続き使える。

v2.1: ユーザー追加要件「gitの最新の状態を反映・差分ダウンロードという形で管理」に対応する
hub/repo_sync.pyを追加した。13個の外部リポジトリ(hub/repos.yaml)に対して、自動で行うのは
`git fetch`による差分検知のみ(ワーキングツリー非破壊、REPO_CHECK_INTERVAL_S間隔)。実際の
取り込み(`git pull --ff-only`)はダッシュボードの「Sync」ボタンによる人間の明示トリガでのみ
行う — Hubが無人で他プロジェクトのファイルを書き換えることはしない。

v2.2: ユーザー追加要件「個別に起動できるようにしたい」に対応するhub/process_launcher.pyを
追加した。13リポジトリはNext.js/Vite/Python/Docker Compose/C++ビルド等スタックが大きく
異なるため、hub/repos.yamlのlaunch:に各リポジトリの実際の起動コマンドを暫定設定し、
ダッシュボードの「Start」ボタンで新しいコンソールウィンドウにそのコマンドを起動する。
Hubは起動を代行するだけで、起動後のプロセス管理(停止・ログ監視等)は行わない
(監視のみ、各ツールの権限は奪わないという設計原則の延長)。起動コマンドを持たない
対象(ビルド必須/IDE拡張等)には代わりに「Open folder」のみを提示する。

v2.3: リファクタリング・再監査で見つけた不整合の修正 + 使いやすさ改善5点。
- launch.urlの疎通確認とrepo git fetchの並行実行化(非hot-path原則への準拠。詳細はREADME参照)
- アラートのフィルタ/検索、JSON/CSVエクスポート(いずれもクライアント側のみ、Hubは再計算しない)
- Slack Webhook通知(hub/notify.pyのSlackWebhookSink/CompositeSink)
- 起動操作の「時刻・OSユーザー名・成否」の軽量記録(メモリのみ、プロセス管理はしない)
- 起動コマンドの実行ファイルがPATH上にあるかの事前健全性チェック(process_launcher.py)

v2.4: 再監査で見つけた不備の修正(check_target_reachableの例外捕捉漏れ) + 使いやすさ改善4点。
- 複数プロセス構成リポジトリの一括起動ボタン(Start all)
- アラートのスヌーズ/ミュート(AlertAggregator.snooze/unsnooze。通知のみ抑制、状態は不変)
- Registry & Liveness / Repositoriesテーブルの横断検索(クライアント側のみ)
- プロファイリングのrun間比較(profiling_tool.aggregate.diff_span_summary/diff_counter_summary)

v2.5: IMPROVEMENT_DESIGN_2026-10 / IMPROVEMENT_PLAN_2026-10 に沿ったUI・運用の改善(詳細はREADME)。
- 画面を「左=ツール一覧 / 中央=詳細・オフィス / 右=サマリ + 下=アラート履歴スライダー」へ再構成。
  概況はpartials/overview.htmlの1つのテンプレートで、ライブ(/)と過去の時刻の再現(/fragments/overview?at=)の
  両方を描く。状態判定はhub/tool_state.py、組み立てはhub/overview.py(どちらも純関数)
- GET /api/overview?at=, GET /api/history/timeline, GET /fragments/overview?at=(履歴スライダー用)
- アラートに発生回数・見る順番の補助(hub/alert_priority.py)・運用手順(hub/runbooks.yaml)を添える。
  どちらも表示専用で、通知・dedup・resolveの経路には繋がない(hub/alert_view.py)
- ブラウザでの404のみ遊びのあるページを返す(APIは従来どおりJSON)

v2.6: 設計書の追補(UIパーツ・動きの予算・キー操作)とセキュリティ点検(README・docs/SECURITY_REVIEW_2026-10.md参照)。
- hub/security.py: Hostの許可リスト(DNS rebinding)と、変更操作のOriginの検査(CSRF)。認証の無いローカルAPIを守る
- 台帳のdescription/concerns/todo/depends_on、停止の波及の木(overview.impact_trees)、確認中(スケルトン)
- バッジ・ドロワー・トースト・トグルスイッチ・ステップインジケーター(static/parts.css, app.js)。動きは2種類まで
"""

from __future__ import annotations

import asyncio
import getpass
import logging
import math
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import data_sources
from ..alert_aggregator import (
    AlertAggregator,
    AlertRecord,
    Severity,
    health_check_alert_id,
    normalize_from_asset_data_insight,
    normalize_from_health_check,
    normalize_from_profiling_tool,
    normalize_from_visual_regression_qa,
)
from ..alert_history import build_timeline, parse_at
from ..alert_priority import AlertPriorityClassifier, RuleBasedPriorityClassifier
from ..alert_store import DEFAULT_DB_PATH, SqliteAlertStore
from ..alert_view import make_alert_decorator
from ..health.runner import LivenessMonitor
from ..notify import default_sink
from ..overview import build_overview, shorten
from ..process_launcher import check_command_available, check_target_reachable, is_alive, launch, open_folder, stop
from ..registry import RegistryError, ToolRegistry
from ..repo_sync import RepoRegistry, RepoSyncManager
from ..runbooks import DEFAULT_RUNBOOKS_PATH, RunbookCatalog, RunbookError
from .. import audit, auth, auth_routes
from ..security import install_request_guard, resolve_allowed_hosts

# profiling_toolはHubのサブ機能(同一リポジトリ内の別トップレベルパッケージ)なので
# 絶対importで参照する。Hub自身のRegistry/AlertAggregator等とは独立した1機能として扱い、
# ここではdata_sources経由の読み取りのみを行う(Hubの他コードからprofiling_toolの
# 内部実装へ踏み込まない)。
from profiling_tool.aggregate import diff_counter_summary, diff_span_summary
from profiling_tool.dashboard import data_sources as profiling_data_sources

logger = logging.getLogger(__name__)

# スヌーズの上限(分)。無制限だと実質「永久に通知しない」設定を誤ってAPIから入れられてしまう。
MAX_SNOOZE_MINUTES = 7 * 24 * 60

# 外部から届くアラート本文の上限。認証の無いローカルAPIなので、巨大な本文でメモリ・SQLite・画面を
# 膨らませられないようにする(通常のメッセージは数十〜数百文字)。
MAX_ALERT_MESSAGE_LEN = 1000

# LivenessMonitor.check_all()を呼び出す頻度。実際のネットワーク呼び出しは各ToolEntryの
# poll_interval_sでレート制限されるため、このループ自体の頻度は「非hot-path原則」に抵触しない。
POLL_LOOP_INTERVAL_S = 5

# registry.yamlの更新検知に使うポーリング間隔。ファイルのstat()のみで実処理は伴わないため、
# ここは「非hot-path原則」(対象ツール自身の間隔を超えない)の対象外(Hub自身のローカルファイル監視)。
REGISTRY_WATCH_INTERVAL_S = 5

# resolved済みアラートの保持期間とprune実行間隔。メモリ・永続化ストア双方の無限増大を防ぐ。
ALERT_RETENTION = timedelta(days=30)
ALERT_PRUNE_INTERVAL_S = 3600

# 常時表示しておく監視画面として使えるよう、既定でmeta refreshする間隔(秒)。
# ?refresh=0でユーザーが個別に無効化できる。
DEFAULT_REFRESH_INTERVAL_S = 20

# 13リポジトリのgit fetch(差分検知)を自動実行する間隔。実ネットワーク越しにGitHubへ
# アクセスするため、対象ツール自身の更新頻度より高頻度にしない「非hot-path原則」に
# 倣い長めに取る(手動チェックは別途 POST /api/repos/check で即時トリガできる)。
REPO_CHECK_INTERVAL_S = 1800

# 起動済みlaunch_targetの疎通確認(check_target_reachable)を自動実行する間隔。
# ローカルloopbackへの低コストな接続確認のみなので短めでよいが、ダッシュボードの
# 描画リクエスト(既定20秒毎のmeta refresh)のたびに毎回実行するのは他機能で徹底している
# 「バックグラウンドでキャッシュし、リクエスト自体はキャッシュを読むだけ」という
# 非hot-path原則から外れるため、repo_check同様に独立したバックグラウンドループへ切り出す。
LAUNCH_CHECK_INTERVAL_S = 10

BASE_DIR = Path(__file__).parent
PROJECT_ROOT = Path(__file__).parent.parent.parent


def _static_asset_version() -> str:
    """style.css / parts.css / app.js のmtime(いちばん新しいもの)をキャッシュバスティング用のクエリ値として使う。

    StaticFilesはCache-Controlを付けないため、ブラウザが古いCSS/JSを再検証なしに
    キャッシュし続けることがある。<link>/<script>のURLにこの値を付与し、ファイルを
    更新するたびにURL自体を変えることで確実に新しい版を取得させる。
    """
    mtimes = []
    for name in ("style.css", "parts.css", "app.js"):
        try:
            mtimes.append(int((BASE_DIR / "static" / name).stat().st_mtime))
        except FileNotFoundError:
            continue
    return str(max(mtimes)) if mtimes else "0"

# Phase4で表示する3種のファイルアーティファクト。(表示ラベル, registry.yamlのcheck_paramsが
# 持つtool_id/キー, 未設定時のフォールバックパス, data_sourcesの読み込み関数)を1箇所にまとめ、
# _load_dashboard_contextでの重複を避ける。
_ARTIFACT_SPECS = (
    (
        "manifest",
        "asset_data_insight_suite",
        "report_manifest_path",
        "data/asset_data_insight/report_manifest.json",
        data_sources.load_asset_insight_manifest,
    ),
    (
        "vrqa",
        "visual_regression_qa_tool",
        "evaluation_result_path",
        "data/visual_regression_qa/evaluation_result.json",
        data_sources.load_visual_regression_evaluation_history,
    ),
    (
        "trace",
        "profiling_tool",
        "trace_summary_path",
        "data/profiling_tool/trace_summary.json",
        data_sources.load_profiling_trace_summary,
    ),
)


def _artifact_path(
    registry: ToolRegistry, tool_id: str, key: str, fallback: str
) -> Path:
    """registry.yamlのcheck_paramsに記載されたアーティファクトパスを取得元とする。

    ダッシュボードが二次的な正にならないよう、パスの定義自体もRegistry(Phase1)に
    一元化し、data_sources.pyやテンプレート側でハードコードしない。
    """
    entry = registry.get(tool_id)
    rel = entry.check_params.get(key) if entry is not None else None
    p = Path(rel) if rel else Path(fallback)
    return p if p.is_absolute() else PROJECT_ROOT / p


def create_app(
    registry_path: Optional[str] = None,
    db_path: Optional[str] = None,
    profiling_traces_dir: Optional[str] = None,
    repos_path: Optional[str] = None,
    runbooks_path: Optional[str] = None,
    classifier: Optional[AlertPriorityClassifier] = None,
    allowed_hosts: Optional[Iterable[str]] = None,
) -> FastAPI:
    registry = (
        ToolRegistry.load(registry_path) if registry_path else ToolRegistry.load()
    )
    monitor = LivenessMonitor(registry)
    sink = default_sink()
    store = SqliteAlertStore(db_path if db_path is not None else DEFAULT_DB_PATH)
    repo_registry = RepoRegistry.load(repos_path) if repos_path else RepoRegistry.load()
    repo_sync_manager = RepoSyncManager(repo_registry, repo_root=PROJECT_ROOT)
    aggregator = AlertAggregator(
        store=store, on_open=sink.notify_opened, on_resolve=sink.notify_resolved
    )
    # 運用手順書(H6)と見る順番の補助(H2)。どちらも表示専用で、通知・dedup・resolveの経路には
    # 繋がない。手順書のファイルが壊れていても、Hub本体は手順書なしで起動し続ける。
    try:
        runbooks = RunbookCatalog.load(runbooks_path or DEFAULT_RUNBOOKS_PATH)
    except (RunbookError, OSError):
        logger.exception("runbooks.yamlを読み込めませんでした。運用手順なしで起動します")
        runbooks = RunbookCatalog.empty()
    decorate_alert = make_alert_decorator(
        registry, classifier if classifier is not None else RuleBasedPriorityClassifier(), runbooks
    )
    # repo_id -> (target_indexに対応する)reachable値のリスト。_launch_check_loopが
    # 定期更新し、リクエストハンドラ側は読むだけにする(ネットワークI/Oをリクエスト経路から追い出す)。
    launch_reachability: dict[str, list[Optional[bool]]] = {}
    # repo_id -> {target_index: {"launched_at", "launched_by", "ok", "message"}}。
    # 「いつ・誰が起動ボタンを押したか」の軽量な記録(v2.2の「起動後のプロセス管理はしない」
    # という設計原則には踏み込まず、単に直近の起動操作を記録するだけ)。Hubプロセスの
    # メモリ上にのみ持ち、再起動で失われる(アラート履歴のようなSQLite永続化はしない —
    # 事故防止のための軽い手掛かりであり、監査ログとしての永続性までは要求されていない)。
    launch_history: dict[str, dict[int, dict]] = {}

    async def _poll_loop() -> None:
        while True:
            try:
                results = await monitor.check_all()
                for tool_id, result in results.items():
                    if result.is_up:
                        aggregator.resolve_by_id(health_check_alert_id(tool_id))
                    else:
                        aggregator.ingest(normalize_from_health_check(tool_id, result))
            except asyncio.CancelledError:
                raise
            except Exception:
                # Hub自身の監視ループが1ツールの異常で全体停止しないようにする。
                # (非機能要件: Hub自体がどのツールの単一障害点にもならないこと)
                pass
            await asyncio.sleep(POLL_LOOP_INTERVAL_S)

    async def _registry_watch_loop() -> None:
        """registry.yamlのmtimeを監視し、変更があれば自動でホットリロードする。

        Phase1「Registryのエントリ追加・削除はHubの再起動なしで反映できることが望ましい」を
        実装するための最小構成。手動リロード(POST /api/registry/reload)も別途用意する。
        """
        while True:
            try:
                if registry.has_changed_on_disk():
                    registry.reload()
            except asyncio.CancelledError:
                raise
            except RegistryError:
                # 書き換え途中の不正なYAML等。既存のregistryはそのまま維持し、
                # 次回の監視サイクルで再試行する(Hub自身が単一障害点にならないようにする)。
                pass
            await asyncio.sleep(REGISTRY_WATCH_INTERVAL_S)

    async def _prune_loop() -> None:
        """resolved済みアラートのうちALERT_RETENTIONより古いものを定期的に破棄する。"""
        while True:
            try:
                aggregator.prune_resolved(ALERT_RETENTION)
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            await asyncio.sleep(ALERT_PRUNE_INTERVAL_S)

    async def _repo_check_loop() -> None:
        """13リポジトリのgit fetch(差分検知のみ、ワーキングツリー非破壊)を定期実行する。

        実際の取り込み(git pull)はここでは一切行わない。ダッシュボードのSyncボタン
        (POST /api/repos/{repo_id}/sync)による人間の明示トリガでのみ行う。
        """
        while True:
            try:
                await repo_sync_manager.check_all()
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            await asyncio.sleep(REPO_CHECK_INTERVAL_S)

    async def _launch_check_loop() -> None:
        """各repoのlaunch_targetの疎通確認をバックグラウンドでキャッシュ更新する。

        以前はダッシュボード描画のたびに(既定20秒毎のmeta refresh含め)urlopenしていたが、
        他の全チェック(repo git fetch, liveness poll)と同じくバックグラウンドでキャッシュし、
        リクエスト経路からネットワークI/Oを追い出す。
        """
        async def _one(target) -> Optional[bool]:
            if not target.url:
                return None
            return await asyncio.to_thread(check_target_reachable, target)

        async def _one_repo(entry) -> None:
            # 1リポジトリ分の疎通確認失敗(想定外の例外)が他リポジトリの更新を
            # 巻き込んで止めないよう、repo_sync_manager.check_all()と同様にリポジトリ単位で
            # 例外を隔離する(check_target_reachable自体はほぼ例外を出さないが、二重の安全網)。
            try:
                launch_reachability[entry.repo_id] = await asyncio.gather(
                    *(_one(t) for t in entry.launch_targets)
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                pass

        while True:
            await asyncio.gather(*(_one_repo(entry) for entry in repo_registry.all()))
            await asyncio.sleep(LAUNCH_CHECK_INTERVAL_S)

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        auth.ensure_auth_configured()  # HUB_AUTH=required でユーザーが居なければ、ここで起動を止める(fail-closed)
        poll_task = asyncio.create_task(_poll_loop())
        watch_task = asyncio.create_task(_registry_watch_loop())
        prune_task = asyncio.create_task(_prune_loop())
        repo_check_task = asyncio.create_task(_repo_check_loop())
        launch_check_task = asyncio.create_task(_launch_check_loop())
        try:
            yield
        finally:
            poll_task.cancel()
            watch_task.cancel()
            prune_task.cancel()
            repo_check_task.cancel()
            launch_check_task.cancel()
            store.close()

    app = FastAPI(title="ToolOrchestrationHub Dashboard", lifespan=_lifespan)
    # 認証の無いローカルAPIを、別サイトのページ(CSRF)やDNS rebindingから守る(hub/security.py)
    install_request_guard(app, allowed_hosts=resolve_allowed_hosts(allowed_hosts))
    # 監査ログ(hub/audit.py): 変更系と、認証・権限の失敗を記録する。ガードの外側に入れて、ガードの 403 も残す
    audit.install_audit(app)
    # 認証と役割(hub/auth.py)。既定は off(従来どおり)。HUB_AUTH=required で、API は viewer 以上を要求する。
    # 操作(スヌーズ・起動・各ツールからの送信)は operator、registry の再読み込みと git pull(同期)は admin。
    app.include_router(auth_routes.router)
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
    templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
    # Jinja2の`tojson`は既定でensure_ascii=True相当のため、日本語等の非ASCII文字を含む
    # アーティファクト(report_manifest.json等)が\uXXXXエスケープのまま表示されてしまう。
    # ProfilingTool実装時に発見したのと同じ問題で、ensure_ascii=Falseに変更する。
    templates.env.policies["json.dumps_kwargs"] = {"sort_keys": True, "ensure_ascii": False}

    def _localtime(value: Optional[str]) -> str:
        """ISO 8601(UTC)の時刻を、Hubを動かしているマシンのローカル時刻「10/09 12:17:55」にする(表示専用)。"""
        if not value:
            return "—"
        try:
            return datetime.fromisoformat(value).astimezone().strftime("%m/%d %H:%M:%S")
        except ValueError:
            return value

    templates.env.filters["localtime"] = _localtime

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(request: Request, exc: StarletteHTTPException):
        """ブラウザで存在しないページを開いたときだけ、遊びのある404ページを返す(IMPROVEMENT H7 / 原則 P8)。

        APIや静的ファイルへのリクエスト(Acceptにtext/htmlが無い、または/api/配下)は従来どおりJSONの
        エラー応答のまま。通常画面は静かに保ち、遊びごころは404に集める。
        """
        wants_html = "text/html" in request.headers.get("accept", "")
        if exc.status_code == 404 and wants_html and not request.url.path.startswith("/api/"):
            return templates.TemplateResponse(
                request, "404.html", {"asset_version": _static_asset_version()}, status_code=404
            )
        return await http_exception_handler(request, exc)

    app.state.registry = registry
    app.state.monitor = monitor
    app.state.aggregator = aggregator
    app.state.repo_registry = repo_registry
    app.state.repo_sync_manager = repo_sync_manager

    def _launch_message_for_display(message: Optional[str]) -> Optional[str]:
        """画面とAPI(viewerも読める)へ出す起動失敗の理由。作業ディレクトリの絶対パスは出さない。"""
        if message and message.startswith("作業ディレクトリが存在しません"):
            return "作業ディレクトリが存在しません"
        return message

    def _is_http_url(url: Optional[str]) -> bool:
        return bool(url) and url.lower().startswith(("http://", "https://"))

    def _load_launch_rows(entry) -> list[dict]:
        """ユーザー追加要件「個別に起動できるようにしたい」向け。各LaunchTargetの疎通確認結果を
        _launch_check_loopが更新したキャッシュから読むだけ(リクエスト経路でのI/Oを避ける)。
        起動直後などまだ一度もチェックが回っていない場合はreachable=Noneのまま表示する。
        """
        cached = launch_reachability.get(entry.repo_id)
        history = launch_history.get(entry.repo_id, {})
        rows = []
        for i, target in enumerate(entry.launch_targets):
            reachable = cached[i] if cached is not None else None
            record = history.get(i, {})
            # このHubが起動して、まだ生きているプロセスだけ「止められる」(PIDは画面へ出さない)
            can_stop = bool(record.get("ok")) and not record.get("stopped_at") and is_alive(record.get("pid"))
            # 3値の状態: running(URLに届く) / starting(Hubが起動した・まだ届かない) / stopped
            if reachable:
                state = "running"
            elif can_stop:
                state = "starting"
            else:
                state = "stopped"
            rows.append(
                {
                    "name": target.name,
                    "url": target.url,
                    # 画面へリンクとして出すURL。http(s)だけ(repos.yamlの書き間違いで javascript: 等が出ないように)
                    "link_url": target.url if _is_http_url(target.url) else None,
                    # 起動後にブラウザの新しいタブで自動で開くか(Web GUIだけ。APIやヘルスチェックは表示のみ)
                    "auto_open": bool(target.open and _is_http_url(target.url)),
                    "state": state,
                    "can_stop": can_stop,
                    "reachable": reachable,
                    "last_launched_at": history.get(i, {}).get("launched_at"),
                    "last_launched_by": history.get(i, {}).get("launched_by"),
                    "last_launch_ok": history.get(i, {}).get("ok"),
                    "last_launch_message": _launch_message_for_display(record.get("message")),
                    # ローカルPATH参照のみ(ネットワークI/O無し)のため、キャッシュせずリクエスト
                    # 毎に確認して問題ない(既存のurlopenベースreachable判定とは事情が異なる)。
                    "command_available": check_command_available(target.command),
                }
            )
        return rows

    def _repo_last_failure(launch_rows: list[dict], sync_error: Optional[str], checked_at: Optional[str]) -> Optional[dict]:
        """リポジトリ行の「最後の失敗」1行。新しい記録は作らず、launch_history(起動失敗)と同期の結果(エラー)から選ぶ。

        起動に失敗した記録があれば(その後に起動し直して成功すると記録が置き換わるので消える)それを出し、
        無ければ、git fetch のエラーを出す。何も無ければNone(=画面には何も出さない)。
        """
        failed = [r for r in launch_rows if r["last_launch_ok"] is False]
        if failed:
            r = max(failed, key=lambda row: row["last_launched_at"] or "")
            return {
                "kind": "起動失敗",
                "text": f"{r['name']}: {shorten(r['last_launch_message'] or '理由は記録されていません', 72)}",
                "at": r["last_launched_at"],
            }
        if sync_error:
            return {"kind": "取得失敗", "text": shorten(sync_error, 72), "at": checked_at}
        return None

    def _load_repo_rows() -> list[dict]:
        statuses = repo_sync_manager.all_statuses()
        rows = []
        for entry in repo_registry.all():
            status = statuses.get(entry.repo_id)
            launch_rows = _load_launch_rows(entry)
            rows.append(
                {
                    "repo_id": entry.repo_id,
                    "display_name": entry.display_name,
                    "branch": entry.branch,
                    "remote_url": entry.remote_url,
                    "checked_at": status.checked_at if status else None,
                    "is_up_to_date": status.is_up_to_date if status else None,
                    "commits_behind": status.commits_behind if status else None,
                    "commits_ahead": status.commits_ahead if status else None,
                    "has_local_changes": status.has_local_changes if status else None,
                    "error": status.error if status else None,
                    "can_sync": status.can_sync if status else False,
                    "launch_targets": launch_rows,
                    "launch_note": entry.launch_note,
                    "last_failure": _repo_last_failure(launch_rows, status.error if status else None, status.checked_at if status else None),
                }
            )
        return rows

    def _alert_rows() -> list[dict]:
        return data_sources.load_alert_summary(aggregator, registry=registry, decorate=decorate_alert)

    def _live_overview() -> dict:
        entries = registry.all()
        return build_overview(
            entries,
            alerts=aggregator.all(),
            results={e.tool_id: monitor.last_result(e.tool_id) for e in entries},
            ages={e.tool_id: monitor.last_signal_age_s(e.tool_id) for e in entries},
            checked={e.tool_id: monitor.has_checked(e.tool_id) for e in entries},
            decorate_alert=decorate_alert,
        )

    def _history_overview(at: datetime) -> dict:
        """スライダーで選んだ時刻の状態を、アラート履歴だけから再構成する(死活監視の結果は混ぜない)。"""
        overview = build_overview(registry.all(), alerts=aggregator.all(), at=at, decorate_alert=decorate_alert)
        overview["at_local_text"] = at.astimezone().strftime("%m/%d %H:%M:%S")
        return overview

    def _parse_at_or_400(at: Optional[str]) -> Optional[datetime]:
        if at is None or at.strip() == "":
            return None
        try:
            return parse_at(at)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"atはISO 8601の時刻で指定してください: {at!r}") from exc

    async def _load_dashboard_context(refresh_interval_s: int) -> dict:
        context = {
            "registry_source_path": str(registry.source_path) if registry.source_path else "—",
            "overview": _live_overview(),
            "timeline": build_timeline(aggregator.all()),
            "alert_rows": _alert_rows(),
            "repo_rows": _load_repo_rows(),
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "refresh_interval_s": refresh_interval_s,
            "asset_version": _static_asset_version(),
        }
        for context_key, tool_id, path_key, fallback, loader in _ARTIFACT_SPECS:
            path = _artifact_path(registry, tool_id, path_key, fallback)
            context[context_key] = loader(str(path))
        context.update(_load_profiling_context())
        return context

    def _load_profiling_context() -> dict:
        """サブ機能profiling_toolの直近runをそのまま整形するのみ。集計・再計算は
        profiling_tool.aggregate側の純関数に委譲する(Hub Phase4の原則を踏襲)。

        使いやすさ改善「run間比較」: 選択中run(同一targetの最新run)と、同一target内で
        その直前にあたるrunとの差分(p50/p95/p99/count、min/max/avg/latest)も併せて計算する。
        比較対象となる過去runが無いtargetはNoneのままにする(比較を強行しない)。

        profiling_toolはあくまでサブ機能であり、その不具合でHub本体のダッシュボードが
        落ちないよう例外を握りつぶす(非機能要件「Hub自体が単一障害点にならない」)。
        """
        try:
            traces_dir = Path(profiling_traces_dir) if profiling_traces_dir else profiling_data_sources.DEFAULT_TRACES_DIR
            runs = profiling_data_sources.list_runs(traces_dir)
            selected = runs[0] if runs else None
            latency: dict = {}
            usage: dict = {}
            latency_diff: Optional[dict] = None
            usage_diff: Optional[dict] = None
            previous_run: Optional[dict] = None
            if selected is not None:
                events = profiling_data_sources.load_trace_events(selected["target"], selected["run_id"], traces_dir)
                latency = profiling_data_sources.latency_summary(events)
                usage = profiling_data_sources.usage_summary(events)
                previous_run = profiling_data_sources.find_previous_run(runs, selected["target"], selected["run_id"])
                if previous_run is not None:
                    previous_events = profiling_data_sources.load_trace_events(
                        previous_run["target"], previous_run["run_id"], traces_dir
                    )
                    latency_diff = diff_span_summary(latency, profiling_data_sources.latency_summary(previous_events))
                    usage_diff = diff_counter_summary(usage, profiling_data_sources.usage_summary(previous_events))
            return {
                "profiling_runs": runs,
                "profiling_selected": selected,
                "profiling_latency": latency,
                "profiling_usage": usage,
                "profiling_previous_run": previous_run,
                "profiling_latency_diff": latency_diff,
                "profiling_usage_diff": usage_diff,
            }
        except Exception:
            return {
                "profiling_runs": [],
                "profiling_selected": None,
                "profiling_latency": {},
                "profiling_usage": {},
                "profiling_previous_run": None,
                "profiling_latency_diff": None,
                "profiling_usage_diff": None,
            }

    @app.get("/")
    async def dashboard(request: Request, refresh: int = DEFAULT_REFRESH_INTERVAL_S):
        # 認証が required で、まだログインしていなければ、ログインのページへ(API は 401 を返すが、HTML は画面に回す)
        if auth.auth_mode() == "required":
            try:
                principal = auth.current_principal(request)
            except HTTPException:
                principal = None
            if principal is None:
                return RedirectResponse("/login", status_code=303)
        # 常時表示しておく監視画面向けに既定でmeta refreshする。?refresh=0で無効化できる。
        return templates.TemplateResponse(
            request, "index.html", await _load_dashboard_context(refresh)
        )

    # 管理画面(registry.yaml の再読み込み・リポジトリの同期=git pull)。ダッシュボードとは別のページ・別のスクリプト(/admin.js。
    # /static の外)にして、サーバーが admin に限る。viewer / operator には、この画面のコードを配らない。
    @app.get("/admin")
    async def admin_page(request: Request):
        if auth.auth_mode() == "required":
            try:
                principal = auth.current_principal(request)
            except HTTPException:
                principal = None
            if principal is None:
                return RedirectResponse("/login", status_code=303)
        auth.require_role("admin")(request)  # 足りなければ 403(誰が試したかは、判定の前に監査ログへ載る)
        return templates.TemplateResponse(
            request,
            "admin.html",
            {
                "registry_source_path": str(registry.source_path) if registry.source_path else "—",
                "repo_rows": _load_repo_rows(),
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                "asset_version": _static_asset_version(),
            },
        )

    @app.get("/admin.js", dependencies=[auth.admin], include_in_schema=False)
    async def admin_script() -> FileResponse:
        return FileResponse(BASE_DIR / "admin" / "admin.js", media_type="text/javascript")

    @app.get("/api/registry", dependencies=[auth.viewer])
    async def api_registry() -> list[dict]:
        return data_sources.load_registry_status(registry, monitor)

    @app.get("/api/alerts", dependencies=[auth.viewer])
    async def api_alerts() -> list[dict]:
        return _alert_rows()

    @app.get("/api/overview", dependencies=[auth.viewer])
    async def api_overview(at: Optional[str] = None) -> dict:
        """ツール一覧・サマリ・直近アラート。atを付けると、その時刻のアラート履歴から状態を再構成する。"""
        at_dt = _parse_at_or_400(at)
        return _history_overview(at_dt) if at_dt is not None else _live_overview()

    @app.get("/api/history/timeline", dependencies=[auth.viewer])
    async def api_history_timeline() -> dict:
        """アラート履歴スライダーの範囲と目盛り(発生・解消の時刻)。"""
        return build_timeline(aggregator.all())

    @app.get("/fragments/overview", dependencies=[auth.viewer])
    async def fragment_overview(request: Request, at: Optional[str] = None):
        """概況(左=ツール一覧 / 中央=詳細・オフィス / 右=サマリ)のHTML断片。

        スライダーで過去の時刻を選んだときに、ブラウザがこの断片を取得して差し替える。
        ライブ表示と同じテンプレート(partials/overview.html)を使うため、見た目の定義は1か所のみ。
        """
        at_dt = _parse_at_or_400(at)
        overview = _history_overview(at_dt) if at_dt is not None else _live_overview()
        return templates.TemplateResponse(request, "partials/overview.html", {"overview": overview})

    @app.post("/api/alerts/{alert_id}/snooze", dependencies=[auth.operator])
    async def api_alert_snooze(alert_id: str, payload: Optional[dict] = Body(default=None)) -> dict:
        """使いやすさ改善: 同一アラートが短時間でopen/resolveを繰り返す(フラッピング)場合に、
        通知(Windowsトースト/Slack)だけを一時的に抑制する。アラート自体の状態は変えない。

        payloadの{"minutes": N}で抑制時間を指定する(省略時60分)。メモリ上にのみ持つため
        Hub再起動で解除される(launch_historyと同じ軽量な一時状態の扱い)。
        """
        if not any(a.alert_id == alert_id for a in aggregator.all()):
            raise HTTPException(status_code=404, detail=f"unknown alert_id: {alert_id}")
        minutes = (payload or {}).get("minutes", 60)
        try:
            minutes = float(minutes)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="minutes must be a number") from None
        # nan/infや巨大な値はtimedeltaの計算で例外になり500を返してしまうため、ここで弾く
        if not math.isfinite(minutes) or minutes <= 0:
            raise HTTPException(status_code=400, detail="minutes must be a positive, finite number")
        if minutes > MAX_SNOOZE_MINUTES:
            raise HTTPException(status_code=400, detail=f"minutes must be at most {MAX_SNOOZE_MINUTES}")
        until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        aggregator.snooze(alert_id, until)
        return {"alert_id": alert_id, "snoozed_until": until.isoformat()}

    @app.post("/api/alerts/{alert_id}/unsnooze", dependencies=[auth.operator])
    async def api_alert_unsnooze(alert_id: str) -> dict:
        aggregator.unsnooze(alert_id)
        return {"alert_id": alert_id, "snoozed_until": None}

    @app.post("/api/registry/reload", dependencies=[auth.admin])
    async def api_registry_reload() -> dict:
        """registry.yamlを即座に再読込する(自動監視の待ち時間を挟まない手動トリガ)。"""
        try:
            registry.reload()
        except RegistryError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "reloaded": True,
            "tool_count": len(registry.all()),
            "source_path": str(registry.source_path) if registry.source_path else None,
        }

    def _require_tool_with_health_check(tool_id: str, expected_health_check: str):
        """heartbeat/ci-success受信エンドポイントの共通バリデーション。

        Hubはここで対象ツールへ何も送り返さない(監視のみ、各ツールの権限は奪わない
        というDESIGN.mdの原則通り、受信して記録するだけの受動エンドポイント)。
        """
        entry = registry.get(tool_id)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"unknown tool_id: {tool_id}")
        if entry.health_check != expected_health_check:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{tool_id} はhealth_check={entry.health_check!r}であり、"
                    f"{expected_health_check!r}向けのこのエンドポイントの対象ではありません"
                ),
            )
        return entry

    @app.post("/api/heartbeat/{tool_id}", dependencies=[auth.operator])
    async def api_heartbeat(tool_id: str) -> dict:
        """rpc系ツール(observed_only/monitoredのrpc_check対象)からのハートビート受信口。

        Hub側から能動的に接続を開くのではなく、各ツールがこのエンドポイントへ
        定期的にPOSTしてくる契約(hub/health/rpc_checkが前提とするハートビート/
        再接続契約)を受動的に受け取るだけ。応答は受信確認のみで、対象ツールの
        動作には一切介入しない。
        """
        _require_tool_with_health_check(tool_id, "rpc_check")
        monitor.record_heartbeat(tool_id)
        return {"tool_id": tool_id, "recorded": True}

    @app.post("/api/ci-success/{tool_id}", dependencies=[auth.operator])
    async def api_ci_success(tool_id: str) -> dict:
        """CI/cron系ツール(ci_pipeline_check対象)からの最終成功run通知の受信口。

        Research-CollectorのGitHub Actions cronのような、対象ツール側のCI成功時に
        1回POSTしてもらう契約を想定する。Hub側からはCIの実行結果を取得しにいかない。
        """
        _require_tool_with_health_check(tool_id, "ci_pipeline_check")
        monitor.record_ci_success(tool_id)
        return {"tool_id": tool_id, "recorded": True}

    def _normalize_and_ingest(normalize_fn, payload: dict) -> dict:
        """Profiling Tool/VRQA/ADISの生アラートを正規化し、AlertAggregatorへ反映する。

        severity="info"は「この障害シグネチャは解消した」という信号として扱い、
        該当するopenアラートをresolveする(Research-Collectorの自動close相当)。
        それ以外(warn/critical)はingestし、既存openレコードがあればdedupされる。
        """
        try:
            alert: AlertRecord = normalize_fn(payload)
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(status_code=400, detail=f"invalid payload: {exc}") from exc
        alert.message = str(alert.message)[:MAX_ALERT_MESSAGE_LEN]

        if alert.severity is Severity.INFO:
            aggregator.resolve_by_id(alert.alert_id)
            action = "resolved"
        else:
            aggregator.ingest(alert)
            action = "ingested"
        return {"alert_id": alert.alert_id, "severity": alert.severity.value, "action": action}

    @app.post("/api/alerts/profiling-tool", dependencies=[auth.operator])
    async def api_alert_profiling_tool(payload: dict) -> dict:
        """Profiling Tool(Phase4のメトリクス/アラート発行契約、AlertAggregatorの主経路)から
        届く生アラートの受信口。"""
        return _normalize_and_ingest(normalize_from_profiling_tool, payload)

    @app.post("/api/alerts/visual-regression-qa", dependencies=[auth.operator])
    async def api_alert_visual_regression_qa(payload: dict) -> dict:
        """Visual Regression QA Tool(Phase5の差し替え可能アラートsink)の1実装としての受信口。

        payloadは1件のEvaluationResult相当({"case_id", "passed", "message"})を想定する。
        """
        return _normalize_and_ingest(normalize_from_visual_regression_qa, payload)

    @app.post("/api/alerts/asset-data-insight", dependencies=[auth.operator])
    async def api_alert_asset_data_insight(payload: dict) -> dict:
        """Asset Data Insight Suiteのreport_manifest.json 1エントリ分の受信口。"""
        return _normalize_and_ingest(normalize_from_asset_data_insight, payload)

    @app.get("/api/repos", dependencies=[auth.viewer])
    async def api_repos() -> list[dict]:
        return _load_repo_rows()

    @app.post("/api/repos/check", dependencies=[auth.operator])
    async def api_repos_check() -> list[dict]:
        """13リポジトリ全件のgit fetch(差分検知)を即座に実行する。ワーキングツリーは変更しない。"""
        await repo_sync_manager.check_all()
        return _load_repo_rows()

    @app.post("/api/repos/{repo_id}/sync", dependencies=[auth.admin])
    async def api_repo_sync(repo_id: str) -> dict:
        """指定リポジトリの差分を実際に取り込む(git pull --ff-only)。

        未コミットの変更がある場合やfast-forwardできない場合は拒否する
        (hub/repo_sync.pyのRepoSyncManager.sync()参照)。
        """
        entry = repo_registry.get(repo_id)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"unknown repo_id: {repo_id}")
        result = await repo_sync_manager.sync(entry)
        if not result.ok:
            raise HTTPException(status_code=409, detail=result.message)
        return {"repo_id": result.repo_id, "ok": result.ok, "message": result.message}

    @app.post("/api/repos/{repo_id}/launch/{target_index}", dependencies=[auth.operator])
    async def api_repo_launch(repo_id: str, target_index: int) -> dict:
        """ユーザー追加要件「個別に起動できるようにしたい」の受け口。

        target_indexはhub/repos.yamlのlaunch:配列の順序に対応する(HTTPリクエストから
        任意のシェルコマンドは一切受け取らない。repos.yamlに定義済みの固定コマンドのみ実行する)。
        """
        entry = repo_registry.get(repo_id)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"unknown repo_id: {repo_id}")
        if not (0 <= target_index < len(entry.launch_targets)):
            raise HTTPException(status_code=404, detail=f"unknown launch target index: {target_index}")
        result = await asyncio.to_thread(launch, entry, entry.launch_targets[target_index], PROJECT_ROOT)
        launch_history.setdefault(repo_id, {})[target_index] = {
            "launched_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "launched_by": getpass.getuser(),
            "ok": result.ok,
            "message": result.message,
            "pid": result.pid if result.ok else None,  # 停止のため、メモリ上にだけ持つ(画面・APIの応答へは出さない)
        }
        if not result.ok:
            raise HTTPException(status_code=500, detail=result.message)
        return {"repo_id": repo_id, "ok": result.ok, "message": result.message, "pid": result.pid}

    @app.get("/api/repos/{repo_id}/launch/{target_index}/reachable", dependencies=[auth.viewer])
    async def api_repo_launch_reachable(repo_id: str, target_index: int) -> dict:
        """起動したあと、画面が「URLに届いたら新しいタブで開く」ために、その場で1回だけ疎通を確かめる。

        URLはrepos.yamlの固定値だけ(リクエストからは受け取らない)。10秒おきのキャッシュではなく、
        起動直後の待ちに使うので、毎回確かめる(0.5秒で打ち切る)。urlが無ければ reachable は null。
        """
        entry = repo_registry.get(repo_id)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"unknown repo_id: {repo_id}")
        if not (0 <= target_index < len(entry.launch_targets)):
            raise HTTPException(status_code=404, detail=f"unknown launch target index: {target_index}")
        reachable = await asyncio.to_thread(check_target_reachable, entry.launch_targets[target_index])
        return {"reachable": reachable}

    @app.post("/api/repos/{repo_id}/stop/{target_index}", dependencies=[auth.operator])
    async def api_repo_stop(repo_id: str, target_index: int) -> dict:
        """2026-11-17(本人の要望)「各システムの起動・終了の操作」。**このHubが起動したプロセスだけ**を止める。

        PIDはHTTPリクエストから受け取らず、Hubの起動記録(launch_history)から引く。
        記録が無い(Hubの外で起動した)・すでに止まっている・PIDが別のプロセスに使い回されている場合は、
        何も止めずに409で理由を返す。
        """
        entry = repo_registry.get(repo_id)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"unknown repo_id: {repo_id}")
        if not (0 <= target_index < len(entry.launch_targets)):
            raise HTTPException(status_code=404, detail=f"unknown launch target index: {target_index}")
        record = launch_history.get(repo_id, {}).get(target_index) or {}
        pid = record.get("pid") if record.get("ok") and not record.get("stopped_at") else None
        result = await asyncio.to_thread(stop, pid)
        if not result.ok:
            raise HTTPException(status_code=409, detail=result.message)
        record["stopped_at"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        record["stopped_by"] = getpass.getuser()
        return {"repo_id": repo_id, "ok": True, "message": result.message}

    @app.post("/api/repos/{repo_id}/open-folder", dependencies=[auth.operator])
    async def api_repo_open_folder(repo_id: str) -> dict:
        """リポジトリのローカルフォルダをエクスプローラで開く(全リポジトリ共通の最低限のアクション)。"""
        entry = repo_registry.get(repo_id)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"unknown repo_id: {repo_id}")
        result = await asyncio.to_thread(open_folder, entry, PROJECT_ROOT)
        if not result.ok:
            raise HTTPException(status_code=500, detail=result.message)
        return {"repo_id": repo_id, "ok": result.ok, "message": result.message}

    return app


app = create_app()
