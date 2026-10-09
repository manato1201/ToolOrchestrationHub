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
from typing import Any, Callable, Optional

from ..alert_aggregator import AlertAggregator, AlertRecord
from ..health.runner import LivenessMonitor
from ..overview import SEVERITY_GLYPH, SEVERITY_LABEL_JA, lifecycle_key
from ..registry import ToolRegistry
from ..tool_identity import color_for, identity_for_unregistered, symbol_for


def load_registry_status(registry: ToolRegistry, monitor: Optional[LivenessMonitor] = None) -> list[dict]:
    """Phase1のregistry.yaml + Phase2のliveness結果をそのまま表示用に整形するのみ。"""
    rows = []
    for entry in registry.all():
        result = monitor.last_result(entry.tool_id) if monitor is not None else None
        rows.append(
            {
                "tool_id": entry.tool_id,
                "display_name": entry.display_name,
                "symbol": symbol_for(entry),
                "color": color_for(entry),
                "transport": entry.transport.value,
                "category": entry.category.value,
                "endpoint": entry.endpoint,
                "health_check": entry.health_check,
                "isolation": entry.isolation.value if entry.isolation else None,
                "owner_rules": list(entry.owner_rules),
                "is_up": result.is_up if result is not None else None,
                "latency_ms": result.latency_ms if result is not None else None,
            }
        )
    return rows


def load_alert_summary(
    aggregator: AlertAggregator,
    *,
    registry: Optional[ToolRegistry] = None,
    decorate: Optional[Callable[[AlertRecord], dict]] = None,
) -> list[dict]:
    """Phase3のAlertRecord一覧を表示用に整形するのみ。新規判定はしない。

    並び順は表示のための整列だけ: 未解消が上(見る順番の目安 → 新しい順)、解消済みは下(解消が新しい順)。
    decorateが渡されたときは、優先度の目安・運用手順などの表示専用の項目を各行へ足す
    (hub/alert_view.py。これらはAlertAggregatorの状態にも通知にも影響しない)。
    """
    rows = []
    for alert in aggregator.all():
        snoozed_until = aggregator.snoozed_until(alert.alert_id)
        entry = registry.get(alert.source_tool_id) if registry is not None else None
        if entry is not None:
            symbol, color, source_name = symbol_for(entry), color_for(entry), entry.display_name
        else:
            symbol, color = identity_for_unregistered(alert.source_tool_id)
            source_name = alert.source_tool_id
        row = {
            "alert_id": alert.alert_id,
            "source_tool_id": alert.source_tool_id,
            "source_name": source_name,
            "symbol": symbol,
            "color": color,
            "severity": alert.severity.value,
            "severity_label": SEVERITY_LABEL_JA[alert.severity.value],
            "severity_glyph": SEVERITY_GLYPH[alert.severity.value],
            "message": alert.message,
            "first_seen_at": alert.first_seen_at.isoformat(),
            "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
            "status": "resolved" if alert.resolved_at else "open",
            "status_label": "解消済" if alert.resolved_at else "未解消",
            "occurrence_count": alert.occurrence_count,
            "snoozed_until": snoozed_until.isoformat() if snoozed_until else None,
            "lifecycle_key": lifecycle_key(alert),
            # 並べ替え専用(JSONには出すが、画面では使わない)
            "_sort": (
                0 if alert.is_open else 1,
                0,
                -(alert.first_seen_at.timestamp() if alert.is_open else alert.resolved_at.timestamp()),
            ),
        }
        if decorate is not None:
            row.update(decorate(alert))
            if alert.is_open:
                row["_sort"] = (0, row.get("priority_rank", 0), row["_sort"][2])
        rows.append(row)

    rows.sort(key=lambda r: r["_sort"])
    for row in rows:
        del row["_sort"]
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
