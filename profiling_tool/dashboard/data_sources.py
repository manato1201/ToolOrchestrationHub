"""dashboard/data_sources.py

可視化層。ここでは集計・再計算ロジックを持たず、aggregate.pyが計算した結果と
traces/以下のファイルをそのまま整形して返すだけに徹する
(Phase3「計算とレンダリングの分離」原則、ToolOrchestrationHub Phase4の
「ダッシュボードを二次的な正にしない」原則も踏襲する)。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from profiling_tool.adapters.checkpoint import DEFAULT_CHECKPOINT_DIR
from profiling_tool.aggregate import summarize_trace
from profiling_tool.core.recorder import DEFAULT_TRACES_DIR


def list_runs(traces_dir: Path | str = DEFAULT_TRACES_DIR) -> list[dict]:
    """traces/<target>/<runId>.jsonを走査し、新しい順に一覧化する。"""
    traces_dir = Path(traces_dir)
    if not traces_dir.exists():
        return []
    runs = []
    for target_dir in sorted(p for p in traces_dir.iterdir() if p.is_dir()):
        for run_file in sorted(target_dir.glob("*.json")):
            stat = run_file.stat()
            runs.append(
                {
                    "target": target_dir.name,
                    "run_id": run_file.stem,
                    "path": str(run_file),
                    "size_bytes": stat.st_size,
                    "modified_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
                    "mtime": stat.st_mtime,
                }
            )
    runs.sort(key=lambda r: r["mtime"], reverse=True)
    return runs


def find_previous_run(runs: list[dict], target: str, run_id: str) -> Optional[dict]:
    """使いやすさ改善「run間比較」向け。同一target内で指定run_idの直前(mtime順で1つ古い)runを返す。

    runsは`list_runs()`の返り値(mtime降順)をそのまま渡す想定。過去runが無い/現在runが
    見つからない場合はNone(呼び出し側は「比較対象なし」として扱う。差分計算を強行しない)。
    """
    same_target = [r for r in runs if r["target"] == target]
    for i, r in enumerate(same_target):
        if r["run_id"] == run_id and i + 1 < len(same_target):
            return same_target[i + 1]
    return None


def load_trace_events(target: str, run_id: str, traces_dir: Path | str = DEFAULT_TRACES_DIR) -> list[dict]:
    path = Path(traces_dir) / target / f"{run_id}.json"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return list(data.get("traceEvents", []))


def latency_summary(events: list[dict]) -> dict:
    """使用率とは別に、span latency(p50/p95/p99)のみを取り出す。"""
    return summarize_trace(events).get("spans", {})


def usage_summary(events: list[dict]) -> dict:
    """使用率・使用量の可視化(ユーザー追加要件)。counter統計をそのまま返す。"""
    return summarize_trace(events).get("counters", {})


def captured_data_sample(events: list[dict], limit: int = 5) -> list[dict]:
    """バックエンド・機密情報等の個人データの簡易表示(ユーザー追加要件)。

    structured event(ph:"i")の実際のpayload値をそのまま返す(要約・マスキングしない)。
    ProfilingToolが計装対象から実際に取り込んだ生データそのものであり、これを隠すと
    プロファイラとしての目的(何を計測・記録しているかの可視化)を果たせないため、
    ユーザーの明示的な指示により実データ値を表示する。
    """
    structured = [e for e in events if e.get("ph") == "i"]
    return [{"name": e["name"], "ts": e["ts"], "payload": e["args"]["payload"]} for e in structured[-limit:]]


def backend_info(
    traces_dir: Path | str = DEFAULT_TRACES_DIR,
    checkpoint_dir: Path | str = DEFAULT_CHECKPOINT_DIR,
    alert_log_path: Optional[Path | str] = None,
) -> dict:
    """使っているバックエンドの簡易表示(ユーザー追加要件)。

    ProfilingToolはデータベースを一切使わず、全て追記専用のローカルファイル
    (JSON/JSON Lines)に保存する。「どこに何が保存されているか」を明示するのが
    本パネルの目的で、外部送信は一切行わない(サービス連携=アラートのみ、生トレースは送らない)。
    """
    traces_dir = Path(traces_dir)
    checkpoint_dir = Path(checkpoint_dir)
    return {
        "trace_store": {
            "kind": "ローカルファイル(追記専用JSON)。データベースは使用しない",
            "path": str(traces_dir),
            "exists": traces_dir.exists(),
        },
        "checkpoint_store": {
            "kind": "ローカルファイル(差分アップデート用カーソル、target毎のJSON)",
            "path": str(checkpoint_dir),
            "exists": checkpoint_dir.exists(),
        },
        "alert_log": {
            "kind": "ローカルファイル(FileSink、JSON Lines追記)",
            "path": str(alert_log_path) if alert_log_path else "(未設定。デフォルトはConsoleSinkのみ)",
            "exists": bool(alert_log_path) and Path(alert_log_path).exists(),
        },
    }


def read_alert_log_tail(alert_log_path: Optional[Path | str], limit: int = 10) -> list[dict]:
    if not alert_log_path:
        return []
    path = Path(alert_log_path)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines[-limit:]]
