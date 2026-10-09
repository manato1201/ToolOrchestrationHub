"""hub/overview.py

ダッシュボードの「左=ツール一覧 / 中央=詳細・オフィス / 右=サマリ」に出す概況を組み立てる純関数
(IMPROVEMENT_DESIGN_2026-10 §4.1)。

同じ関数を2通りの入力で使う:
- ライブ: 死活監視の最新結果(results/ages) + いま未解消のアラート
- 履歴(スライダー): atを指定し、その時刻に未解消だったアラートだけから状態を再構成する。
  アラート履歴に残っているのは「アラートの発生・解消」だけで、死活監視の結果そのものは残らない
  (設計書 §6 のリスク)。そのため履歴では「未解消のアラートが無い = 正常」とみなす近似になり、
  当時Hubが止まっていた期間までは再現できない。画面にもその旨を注記する。

ここでも集計の元データは増やさない(アラートはAlertAggregator、死活監視はLivenessMonitorが正)。
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Callable, Iterable, Mapping, Optional

from .alert_aggregator import AlertRecord, Severity
from .health.base import HealthResult
from .registry import IsolationKind, ToolCategory, ToolEntry
from .tool_identity import color_for, identity_for_unregistered, symbol_for
from .tool_state import ToolState, derive_tool_state, state_glyph, state_label, state_rank

ISOLATION_LABEL_JA: dict[Optional[IsolationKind], str] = {
    None: "未設定",
    IsolationKind.NONE: "なし(ホストで直接実行)",
    IsolationKind.SANDBOX_BASH: "サンドボックス",
    IsolationKind.CONTAINER: "コンテナ",
    IsolationKind.VM: "仮想マシン(使い捨てCI含む)",
}

CATEGORY_LABEL_JA: dict[ToolCategory, str] = {
    ToolCategory.MONITORED: "能動監視",
    ToolCategory.OBSERVED_ONLY: "受動監視",
    ToolCategory.EXCLUDED: "対象外",
}

SEVERITY_LABEL_JA: dict[str, str] = {"critical": "重大", "warn": "警告", "info": "情報"}
SEVERITY_GLYPH: dict[str, str] = {"critical": "■", "warn": "▲", "info": "○"}

_SEVERITY_ORDER = {Severity.CRITICAL: 0, Severity.WARN: 1, Severity.INFO: 2}
# 積み上げバーは「問題があるものが左」。見出し(稼働 11 · 警告 1 …)の順は 稼働 → 警告 → 停止 → …
_BAR_ORDER = (ToolState.DOWN, ToolState.WARN, ToolState.UNKNOWN, ToolState.OK, ToolState.EXCLUDED)
_HEADLINE_ORDER = (ToolState.OK, ToolState.WARN, ToolState.DOWN, ToolState.UNKNOWN, ToolState.EXCLUDED)
RECENT_ALERT_LIMIT = 3


def format_age_ja(seconds: float) -> str:
    """経過秒を「3分前」のような相対表現にする。"""
    s = max(0, int(seconds))
    if s < 10:
        return "たった今"
    if s < 60:
        return f"{s}秒前"
    minutes = s // 60
    if minutes < 60:
        return f"{minutes}分前"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}時間前"
    return f"{hours // 24}日前"


def format_latency_ms(latency_ms: Optional[float]) -> Optional[str]:
    if latency_ms is None:
        return None
    return f"{latency_ms:.1f} ms" if latency_ms < 10 else f"{latency_ms:.0f} ms"


def _alert_payload(alert: AlertRecord, decorate: Optional[Callable[[AlertRecord], dict]] = None) -> dict:
    payload = {
        "alert_id": alert.alert_id,
        "severity": alert.severity.value,
        "severity_label": SEVERITY_LABEL_JA[alert.severity.value],
        "severity_glyph": SEVERITY_GLYPH[alert.severity.value],
        "message": alert.message,
        "first_seen_at": alert.first_seen_at.isoformat(),
        "occurrence_count": alert.occurrence_count,
    }
    if decorate is not None:
        payload.update(decorate(alert))
    return payload


def lifecycle_key(alert: AlertRecord) -> str:
    """1つのopen→resolveライフサイクルを一意に表すキー(同じalert_idの再発を区別する)。"""
    return f"{alert.alert_id}@{alert.first_seen_at.isoformat()}"


def build_overview(
    entries: Iterable[ToolEntry],
    *,
    alerts: Iterable[AlertRecord],
    results: Optional[Mapping[str, Optional[HealthResult]]] = None,
    ages: Optional[Mapping[str, Optional[float]]] = None,
    at: Optional[datetime] = None,
    decorate_alert: Optional[Callable[[AlertRecord], dict]] = None,
) -> dict:
    """ツール一覧・サマリ・直近アラートをまとめた辞書を返す。at未指定ならライブ、指定なら履歴の再現。

    decorate_alertを渡すと、各アラートの辞書に追加の項目(優先度の目安・運用手順など、表示専用)を足す。
    """
    entries = list(entries)
    alerts = list(alerts)
    results = results or {}
    ages = ages or {}
    historical = at is not None

    if historical:
        open_alerts = [a for a in alerts if a.is_open_at(at)]
        seen_alerts = [a for a in alerts if a.first_seen_at <= at]
    else:
        open_alerts = [a for a in alerts if a.is_open]
        seen_alerts = alerts

    open_by_tool: dict[str, list[AlertRecord]] = defaultdict(list)
    for alert in open_alerts:
        open_by_tool[alert.source_tool_id].append(alert)

    identities = {e.tool_id: (symbol_for(e), color_for(e)) for e in entries}

    rows = []
    for entry in entries:
        # 履歴では死活監視の結果そのものが残っていないため、結果もageも使わない
        result = None if historical else results.get(entry.tool_id)
        tool_alerts = sorted(
            open_by_tool.get(entry.tool_id, []),
            key=lambda a: (_SEVERITY_ORDER[a.severity], -a.first_seen_at.timestamp()),
        )
        state = derive_tool_state(
            entry,
            is_up=result.is_up if result is not None else None,
            open_alerts=tool_alerts,
            assume_ok_without_alerts=historical,
        )
        age = None if historical else ages.get(entry.tool_id)
        latency_ms = result.latency_ms if result is not None else None
        symbol, color = identities[entry.tool_id]
        rows.append(
            {
                "tool_id": entry.tool_id,
                "display_name": entry.display_name,
                "symbol": symbol,
                "color": color,
                "category": entry.category.value,
                "category_label": CATEGORY_LABEL_JA[entry.category],
                "transport": entry.transport.value,
                "endpoint": entry.endpoint,
                "health_check": entry.health_check,
                "isolation": entry.isolation.value if entry.isolation else None,
                "isolation_label": ISOLATION_LABEL_JA[entry.isolation],
                "owner_rules": list(entry.owner_rules),
                "state": state.value,
                "state_label": state_label(state),
                "state_glyph": state_glyph(state),
                "state_rank": state_rank(state),
                "latency_ms": latency_ms,
                "latency_text": format_latency_ms(latency_ms),
                "last_signal_ago": format_age_ja(age) if age is not None else None,
                "last_signal_text": f"最終応答 {format_age_ja(age)}" if age is not None else None,
                "alerts": [_alert_payload(a, decorate_alert) for a in tool_alerts],
                "search": f"{entry.display_name} {entry.tool_id} {entry.category.value} {entry.transport.value}".lower(),
            }
        )

    counts = {s.value: 0 for s in ToolState}
    for row in rows:
        counts[row["state"]] += 1
    total = len(rows)

    def _item(state: ToolState, label: Optional[str] = None) -> dict:
        n = counts[state.value]
        return {
            "state": state.value,
            "label": label or state_label(state),
            "glyph": state_glyph(state),
            "count": n,
            "percent": round(n / total * 100, 1) if total else 0.0,
        }

    segments = [_item(s) for s in _BAR_ORDER if counts[s.value] > 0]
    headline = [_item(ToolState.OK, "稼働")] + [
        _item(s) for s in _HEADLINE_ORDER[1:] if counts[s.value] > 0
    ]

    recent_alerts = []
    for alert in sorted(seen_alerts, key=lambda a: a.first_seen_at, reverse=True)[:RECENT_ALERT_LIMIT]:
        symbol, color = identities.get(alert.source_tool_id) or identity_for_unregistered(alert.source_tool_id)
        still_open = alert.is_open_at(at) if historical else alert.is_open
        recent_alerts.append(
            {
                **_alert_payload(alert, decorate_alert),
                "source_tool_id": alert.source_tool_id,
                "symbol": symbol,
                "color": color,
                "status": "open" if still_open else "resolved",
                "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
            }
        )

    default_tool_id = min(rows, key=lambda r: r["state_rank"])["tool_id"] if rows else None

    return {
        "mode": "history" if historical else "live",
        "at": at.isoformat() if historical else None,
        "tools": rows,
        "default_tool_id": default_tool_id,
        "summary": {"total": total, "counts": counts, "segments": segments, "headline": headline},
        "recent_alerts": recent_alerts,
        "open_alert_keys": sorted({lifecycle_key(a) for a in open_alerts}),
        "all_normal": total > 0 and counts[ToolState.WARN.value] == 0 and counts[ToolState.DOWN.value] == 0 and not open_alerts,
    }
