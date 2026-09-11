"""profiling_tool/dashboard/app.py

ProfilingToolはToolOrchestrationHubのサブ機能として統合されている。日常的な利用は
Hub側ダッシュボード(hub/dashboard/、既定ポート8790)の「Profiling」セクションが主であり、
このスタンドアロン版はトレースを詳細に掘り下げたいときのオプション画面という位置づけ。

Phase3後半の「タイムラインビューア」はPerfetto UI(ui.perfetto.dev)への委譲がMVPであり
(独自ビューアは作らない)、このダッシュボードはユーザー追加要件に対応する読み取り専用の
補助パネルを提供する:
- 使用率・使用量の可視化(counter統計)
- 使っているバックエンド・データの簡易表示(ローカルファイルのみ、DB不使用の明示 + 実データサンプル)
- サービス連携状況(ToolOrchestrationHub / Webhookの設定・疎通確認)

集計・再計算ロジックはここに置かない(aggregate.py/data_sources.pyへ委譲)。

環境変数(いずれも未設定で動作する):
- PROFILING_HUB_URL: ToolOrchestrationHubのベースURL(既定 http://127.0.0.1:8790)
- PROFILING_WEBHOOK_URL: Webhook(Slack Incoming Webhook等)のURL(未設定なら「未設定」表示)
- PROFILING_ALERT_LOG_PATH: FileSinkの出力先(既定 .profiling_state/alerts.log)
"""

from __future__ import annotations

import asyncio
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from profiling_tool.adapters.checkpoint import DEFAULT_CHECKPOINT_DIR
from profiling_tool.core.recorder import DEFAULT_TRACES_DIR

from . import data_sources

BASE_DIR = Path(__file__).parent
# ToolOrchestrationHub/profiling_tool/dashboard/app.py -> リポジトリルートは3階層上
REPO_ROOT = Path(__file__).parent.parent.parent
DEFAULT_ALERT_LOG_PATH = REPO_ROOT / ".profiling_state" / "alerts.log"


def _static_asset_version() -> str:
    css_path = BASE_DIR / "static" / "style.css"
    try:
        return str(int(css_path.stat().st_mtime))
    except FileNotFoundError:
        return "0"


def _hub_url() -> str:
    return os.environ.get("PROFILING_HUB_URL", "http://127.0.0.1:8790")


def _webhook_url() -> Optional[str]:
    return os.environ.get("PROFILING_WEBHOOK_URL") or None


def _alert_log_path() -> Path:
    return Path(os.environ.get("PROFILING_ALERT_LOG_PATH", str(DEFAULT_ALERT_LOG_PATH)))


def _check_reachable(url: str, timeout_s: float = 0.5) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout_s):
            return True
    except (urllib.error.URLError, OSError):
        return False


def create_app(
    traces_dir: Optional[str] = None, checkpoint_dir: Optional[str] = None
) -> FastAPI:
    traces_dir_path = Path(traces_dir) if traces_dir else DEFAULT_TRACES_DIR
    checkpoint_dir_path = (
        Path(checkpoint_dir) if checkpoint_dir else DEFAULT_CHECKPOINT_DIR
    )

    app = FastAPI(title="ProfilingTool Dashboard")
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
    templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
    # Jinja2の`tojson`は既定でensure_ascii=True相当のため、日本語等の非ASCII文字が
    # \uXXXXエスケープのまま画面に出てしまう(バックエンド・データ表示パネルで
    # 実データ値をそのまま見せる要件と衝突する)。ensure_ascii=Falseに変更する。
    templates.env.policies["json.dumps_kwargs"] = {"sort_keys": True, "ensure_ascii": False}

    async def _build_context(target: Optional[str], run_id: Optional[str]) -> dict:
        runs = data_sources.list_runs(traces_dir_path)
        selected = None
        if target and run_id:
            selected = next(
                (r for r in runs if r["target"] == target and r["run_id"] == run_id),
                None,
            )
        elif runs:
            selected = runs[0]

        events: list[dict] = []
        latency: dict = {}
        usage: dict = {}
        sample: list[dict] = []
        if selected is not None:
            events = data_sources.load_trace_events(
                selected["target"], selected["run_id"], traces_dir_path
            )
            latency = data_sources.latency_summary(events)
            usage = data_sources.usage_summary(events)
            sample = data_sources.captured_data_sample(events)

        alert_log_path = _alert_log_path()
        backend = data_sources.backend_info(
            traces_dir_path, checkpoint_dir_path, alert_log_path
        )
        alerts = data_sources.read_alert_log_tail(alert_log_path)

        hub_url = _hub_url()
        webhook_url = _webhook_url()
        # ブロッキングI/OなのでイベントループをふさがないようToThreadに逃がす
        hub_reachable = await asyncio.to_thread(_check_reachable, hub_url)

        return {
            "runs": runs,
            "selected": selected,
            "latency": latency,
            "usage": usage,
            "sample": sample,
            "backend": backend,
            "alerts": alerts,
            "hub_url": hub_url,
            "hub_reachable": hub_reachable,
            "webhook_configured": webhook_url is not None,
            "webhook_url": webhook_url,
            "asset_version": _static_asset_version(),
        }

    @app.get("/")
    async def dashboard(
        request: Request, target: Optional[str] = None, run_id: Optional[str] = None
    ):
        context = await _build_context(target, run_id)
        return templates.TemplateResponse(request, "index.html", context)

    @app.get("/api/runs")
    async def api_runs() -> list[dict]:
        return data_sources.list_runs(traces_dir_path)

    @app.get("/api/runs/{target}/{run_id}/summary")
    async def api_run_summary(target: str, run_id: str) -> dict:
        events = data_sources.load_trace_events(target, run_id, traces_dir_path)
        return {
            "latency": data_sources.latency_summary(events),
            "usage": data_sources.usage_summary(events),
        }

    @app.get("/api/backend")
    async def api_backend() -> dict:
        return data_sources.backend_info(
            traces_dir_path, checkpoint_dir_path, _alert_log_path()
        )

    return app


app = create_app()
