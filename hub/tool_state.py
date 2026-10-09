"""hub/tool_state.py

ツール1件の「いまの状態」(正常 / 警告 / 停止 / 未確認 / 対象外)を決める純関数(UI改善 U1/U2)。

ライブ表示(死活監視の最新結果 + いま未解消のアラート)と、アラート履歴スライダーによる
過去の時刻の再現(その時刻に未解消だったアラートのみ)の両方で、同じ規則を使うために
ダッシュボードから切り離してある。

状態の意味:
- 停止    : 死活監視がdownを返している、または死活監視由来のアラート(liveness down)が未解消
- 警告    : 生きてはいるが、別のアラート(しきい値超過・視覚回帰の失敗など)が未解消
- 正常    : 死活監視がupで、未解消のアラートが無い
- 未確認  : 死活監視の信号がまだ一度も無く(ハートビート未受信など)、アラートも無い
- 対象外  : registryでcategory: excluded(監視対象にしていない)

警告を「重大度がwarn」ではなく「停止ではない未解消アラートがある」で決めているのは、
視覚回帰の失敗(critical)のようにツールは動いているが問題がある状態を、
「停止(■)」と誤って見せないため。重大度そのものは各アラートの行に別途表示する。
"""
from __future__ import annotations

from enum import Enum
from typing import Iterable, Optional

from .alert_aggregator import AlertRecord, health_check_alert_id
from .registry import ToolCategory, ToolEntry


class ToolState(str, Enum):
    OK = "ok"
    WARN = "warn"
    DOWN = "down"
    UNKNOWN = "unknown"
    EXCLUDED = "excluded"


# (日本語ラベル, 記号, 並べ替えの順位)。色だけに頼らず、記号と文字を必ず併記する(原則 P1)。
# 記号は文字記号のみ(絵文字は使わない)。順位は「状態順」の並べ替え用(問題があるものが先)。
STATE_META: dict[ToolState, tuple[str, str, int]] = {
    ToolState.DOWN: ("停止", "■", 0),
    ToolState.WARN: ("警告", "▲", 1),
    ToolState.UNKNOWN: ("未確認", "○", 2),
    ToolState.OK: ("正常", "✓", 3),
    ToolState.EXCLUDED: ("対象外", "–", 4),
}


def state_label(state: ToolState) -> str:
    return STATE_META[state][0]


def state_glyph(state: ToolState) -> str:
    return STATE_META[state][1]


def state_rank(state: ToolState) -> int:
    return STATE_META[state][2]


def derive_tool_state(
    entry: ToolEntry,
    *,
    is_up: Optional[bool],
    open_alerts: Iterable[AlertRecord],
    assume_ok_without_alerts: bool = False,
) -> ToolState:
    """死活監視の最新結果(is_up)と、そのツールの未解消アラートから状態を決める。

    is_upがNoneなのは「まだ死活監視の信号が無い」か、過去の時刻の再現で死活監視の結果そのものが
    残っていない場合。後者ではassume_ok_without_alerts=Trueにして、未解消のアラートが無いことを
    「正常」とみなす(履歴にはアラートの発生・解消しか残らないため、これが再現できる限界)。
    """
    if entry.category is ToolCategory.EXCLUDED:
        return ToolState.EXCLUDED

    liveness_id = health_check_alert_id(entry.tool_id)
    alerts = list(open_alerts)
    liveness_alert_open = any(a.alert_id == liveness_id for a in alerts)
    other_alert_open = any(a.alert_id != liveness_id for a in alerts)

    # 最新の死活監視がupなら、解消待ちの古いliveness alertより新しい結果を信じる
    if is_up is False or (is_up is None and liveness_alert_open):
        return ToolState.DOWN
    if other_alert_open:
        return ToolState.WARN
    if is_up is True or assume_ok_without_alerts:
        return ToolState.OK
    return ToolState.UNKNOWN
