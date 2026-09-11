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
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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
from ..alert_store import DEFAULT_DB_PATH, SqliteAlertStore
from ..health.runner import LivenessMonitor
from ..notify import default_sink
from ..registry import RegistryError, ToolRegistry
from ..repo_sync import RepoRegistry, RepoSyncManager

# profiling_toolはHubのサブ機能(同一リポジトリ内の別トップレベルパッケージ)なので
# 絶対importで参照する。Hub自身のRegistry/AlertAggregator等とは独立した1機能として扱い、
# ここではdata_sources経由の読み取りのみを行う(Hubの他コードからprofiling_toolの
# 内部実装へ踏み込まない)。
from profiling_tool.dashboard import data_sources as profiling_data_sources

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

BASE_DIR = Path(__file__).parent
PROJECT_ROOT = Path(__file__).parent.parent.parent


def _static_asset_version() -> str:
    """style.cssのmtimeをキャッシュバスティング用のクエリ値として使う。

    StaticFilesはCache-Controlを付けないため、ブラウザが古いCSSを再検証なしに
    キャッシュし続けることがある。<link>のURLにこの値を付与し、ファイルを
    更新するたびにURL自体を変えることで確実に新しいCSSを取得させる。
    """
    css_path = BASE_DIR / "static" / "style.css"
    try:
        return str(int(css_path.stat().st_mtime))
    except FileNotFoundError:
        return "0"

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

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        poll_task = asyncio.create_task(_poll_loop())
        watch_task = asyncio.create_task(_registry_watch_loop())
        prune_task = asyncio.create_task(_prune_loop())
        repo_check_task = asyncio.create_task(_repo_check_loop())
        try:
            yield
        finally:
            poll_task.cancel()
            watch_task.cancel()
            prune_task.cancel()
            repo_check_task.cancel()
            store.close()

    app = FastAPI(title="ToolOrchestrationHub Dashboard", lifespan=_lifespan)
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
    templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
    # Jinja2の`tojson`は既定でensure_ascii=True相当のため、日本語等の非ASCII文字を含む
    # アーティファクト(report_manifest.json等)が\uXXXXエスケープのまま表示されてしまう。
    # ProfilingTool実装時に発見したのと同じ問題で、ensure_ascii=Falseに変更する。
    templates.env.policies["json.dumps_kwargs"] = {"sort_keys": True, "ensure_ascii": False}

    app.state.registry = registry
    app.state.monitor = monitor
    app.state.aggregator = aggregator
    app.state.repo_registry = repo_registry
    app.state.repo_sync_manager = repo_sync_manager

    def _load_repo_rows() -> list[dict]:
        statuses = repo_sync_manager.all_statuses()
        rows = []
        for entry in repo_registry.all():
            status = statuses.get(entry.repo_id)
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
                }
            )
        return rows

    def _load_dashboard_context(refresh_interval_s: int) -> dict:
        context = {
            "registry_rows": data_sources.load_registry_status(registry, monitor),
            "registry_source_path": str(registry.source_path) if registry.source_path else "—",
            "alert_rows": data_sources.load_alert_summary(aggregator),
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

        profiling_toolはあくまでサブ機能であり、その不具合でHub本体のダッシュボードが
        落ちないよう例外を握りつぶす(非機能要件「Hub自体が単一障害点にならない」)。
        """
        try:
            traces_dir = Path(profiling_traces_dir) if profiling_traces_dir else profiling_data_sources.DEFAULT_TRACES_DIR
            runs = profiling_data_sources.list_runs(traces_dir)
            selected = runs[0] if runs else None
            latency: dict = {}
            usage: dict = {}
            if selected is not None:
                events = profiling_data_sources.load_trace_events(selected["target"], selected["run_id"], traces_dir)
                latency = profiling_data_sources.latency_summary(events)
                usage = profiling_data_sources.usage_summary(events)
            return {"profiling_runs": runs, "profiling_selected": selected, "profiling_latency": latency, "profiling_usage": usage}
        except Exception:
            return {"profiling_runs": [], "profiling_selected": None, "profiling_latency": {}, "profiling_usage": {}}

    @app.get("/")
    async def dashboard(request: Request, refresh: int = DEFAULT_REFRESH_INTERVAL_S):
        # 常時表示しておく監視画面向けに既定でmeta refreshする。?refresh=0で無効化できる。
        return templates.TemplateResponse(
            request, "index.html", _load_dashboard_context(refresh)
        )

    @app.get("/api/registry")
    async def api_registry() -> list[dict]:
        return data_sources.load_registry_status(registry, monitor)

    @app.get("/api/alerts")
    async def api_alerts() -> list[dict]:
        return data_sources.load_alert_summary(aggregator)

    @app.post("/api/registry/reload")
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

    @app.post("/api/heartbeat/{tool_id}")
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

    @app.post("/api/ci-success/{tool_id}")
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

        if alert.severity is Severity.INFO:
            aggregator.resolve_by_id(alert.alert_id)
            action = "resolved"
        else:
            aggregator.ingest(alert)
            action = "ingested"
        return {"alert_id": alert.alert_id, "severity": alert.severity.value, "action": action}

    @app.post("/api/alerts/profiling-tool")
    async def api_alert_profiling_tool(payload: dict) -> dict:
        """Profiling Tool(Phase4のメトリクス/アラート発行契約、AlertAggregatorの主経路)から
        届く生アラートの受信口。"""
        return _normalize_and_ingest(normalize_from_profiling_tool, payload)

    @app.post("/api/alerts/visual-regression-qa")
    async def api_alert_visual_regression_qa(payload: dict) -> dict:
        """Visual Regression QA Tool(Phase5の差し替え可能アラートsink)の1実装としての受信口。

        payloadは1件のEvaluationResult相当({"case_id", "passed", "message"})を想定する。
        """
        return _normalize_and_ingest(normalize_from_visual_regression_qa, payload)

    @app.post("/api/alerts/asset-data-insight")
    async def api_alert_asset_data_insight(payload: dict) -> dict:
        """Asset Data Insight Suiteのreport_manifest.json 1エントリ分の受信口。"""
        return _normalize_and_ingest(normalize_from_asset_data_insight, payload)

    @app.get("/api/repos")
    async def api_repos() -> list[dict]:
        return _load_repo_rows()

    @app.post("/api/repos/check")
    async def api_repos_check() -> list[dict]:
        """13リポジトリ全件のgit fetch(差分検知)を即座に実行する。ワーキングツリーは変更しない。"""
        await repo_sync_manager.check_all()
        return _load_repo_rows()

    @app.post("/api/repos/{repo_id}/sync")
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

    return app


app = create_app()
