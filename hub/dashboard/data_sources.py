"""hub/dashboard/data_sources.py

Phase4: 各ツールが自律的に生成するアーティファクトを読み取り専用で整形するだけの層。
ここでは集計・再計算・新規判定を一切行わない(Phase0のアンチパターン「ダッシュボードを
二次的な正となる状態源にしない」を実装レベルで守る)。

各data_sourceは必ず取得元パス(source)とタイムスタンプ(loaded_at)を結果へ併記し、
「これはミラーであり最新の正はここではない」ことを画面側が常時示せるようにする。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

from ..alert_aggregator import AlertAggregator
from ..health.runner import LivenessMonitor
from ..registry import ToolRegistry


def load_registry_status(registry: ToolRegistry, monitor: Optional[LivenessMonitor] = None) -> list[dict]:
    """Phase1のregistry.yaml + Phase2のliveness結果をそのまま表示用に整形するのみ。"""
    rows = []
    for entry in registry.all():
        result = monitor.last_result(entry.tool_id) if monitor is not None else None
        rows.append(
            {
                "tool_id": entry.tool_id,
                "display_name": entry.display_name,
                "transport": entry.transport.value,
                "category": entry.category.value,
                "endpoint": entry.endpoint,
                "health_check": entry.health_check,
                "is_up": result.is_up if result is not None else None,
                "latency_ms": result.latency_ms if result is not None else None,
            }
        )
    return rows


def load_alert_summary(aggregator: AlertAggregator) -> list[dict]:
    """Phase3のAlertRecord一覧をopen/resolved別に整形するのみ。新規判定はしない。"""
    rows = []
    for alert in aggregator.all():
        snoozed_until = aggregator.snoozed_until(alert.alert_id)
        rows.append(
            {
                "alert_id": alert.alert_id,
                "source_tool_id": alert.source_tool_id,
                "severity": alert.severity.value,
                "message": alert.message,
                "first_seen_at": alert.first_seen_at.isoformat(),
                "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
                "status": "resolved" if alert.resolved_at else "open",
                "snoozed_until": snoozed_until.isoformat() if snoozed_until else None,
            }
        )
    return rows


def _load_json_artifact(path: str) -> dict[str, Any]:
    """任意のJSONアーティファクトをそのまま読み込み、取得元とタイムスタンプを併記する。

    ファイルが存在しない場合は例外にせず、その旨を表示用データとして返す
    (対象ツールが未実行/未連携でもダッシュボード自体は落ちない)。
    """
    p = Path(path)
    if not p.exists():
        return {
            "source": str(p),
            "loaded_at": None,
            "available": False,
            "data": None,
        }
    with p.open(encoding="utf-8") as f:
        data = json.load(f)
    return {
        "source": str(p),
        # 画面にそのまま出す前提のため、生のUNIX epochではなく人間可読な文字列で持つ。
        "loaded_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "available": True,
        "data": data,
    }


def load_asset_insight_manifest(path: str) -> dict[str, Any]:
    """Asset Data Insight Suiteのreport_manifest.jsonをそのまま読み込むのみ。

    Hub側でスコア再計算等は行わない。
    """
    return _load_json_artifact(path)


def load_visual_regression_evaluation_history(path: str) -> dict[str, Any]:
    """Visual Regression QA ToolのEvaluationResult履歴をそのまま読み込むのみ。"""
    return _load_json_artifact(path)


def load_profiling_trace_summary(path: str) -> dict[str, Any]:
    """Profiling Toolが出力したPerfettoトレースのサマリをそのまま読み込むのみ。

    トレース本体のビューアはProfiling Tool側の責務であり、Hubはサマリ表示に留める。
    """
    return _load_json_artifact(path)
