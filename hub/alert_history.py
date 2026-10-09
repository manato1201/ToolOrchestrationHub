"""hub/alert_history.py

アラート履歴スライダー(IMPROVEMENT_DESIGN_2026-10 Phase 3)の下ごしらえ。

スライダーが動かす範囲(いちばん古い発生 〜 いま)と、目盛りにする「発生・解消」の時刻を返す。
過去の時刻の状態そのものは hub/overview.py の build_overview(at=...) が、
AlertRecord.is_open_at() を使って再構成する。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

from .alert_aggregator import AlertRecord

# 異常が頻繁に出入りする(フラッピング)状態が何週間も続くと、イベントが際限なく増える。
# スライダーの目盛りはブラウザへ丸ごと送るため、新しい側からこの件数までに絞る。
DEFAULT_EVENT_LIMIT = 2000


def parse_at(value: str) -> datetime:
    """クエリで受け取った時刻(ISO 8601)をタイムゾーン付きのdatetimeにする。

    末尾Zは+00:00として扱い、タイムゾーンの無い値はUTCとみなす。解釈できなければValueError。
    """
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def build_timeline(
    alerts: Iterable[AlertRecord],
    *,
    now: Optional[datetime] = None,
    limit: int = DEFAULT_EVENT_LIMIT,
) -> dict:
    """スライダーの範囲と目盛り。履歴がまだ無ければstartはNone(スライダーは無効にする)。"""
    now = now if now is not None else datetime.now(timezone.utc)
    events: list[dict] = []
    for alert in alerts:
        events.append(
            {
                "at": alert.first_seen_at.isoformat(),
                "kind": "opened",
                "alert_id": alert.alert_id,
                "source_tool_id": alert.source_tool_id,
                "severity": alert.severity.value,
            }
        )
        if alert.resolved_at is not None:
            events.append(
                {
                    "at": alert.resolved_at.isoformat(),
                    "kind": "resolved",
                    "alert_id": alert.alert_id,
                    "source_tool_id": alert.source_tool_id,
                    "severity": alert.severity.value,
                }
            )
    # isoformatの文字列は同じタイムゾーン(UTC)同士なら時刻順に並ぶが、念のため実時刻で並べる
    events.sort(key=lambda e: datetime.fromisoformat(e["at"]))
    truncated = len(events) > limit
    if truncated:
        events = events[-limit:]
    return {
        "start": events[0]["at"] if events else None,
        "end": now.isoformat(),
        "events": events,
        "truncated": truncated,
    }
