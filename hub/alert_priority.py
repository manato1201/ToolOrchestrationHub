"""hub/alert_priority.py

アラートの見る順番を付ける補助(IMPROVEMENT_PLAN_2026-10 H2)。ラベルは 緊急 / 通常 / 情報不足 の3つ。

**補助に限る**(計画書の方針)。このモジュールの結果は、ダッシュボードのアラート一覧の
「並び順」と「バッジ表示」にだけ使う。通知(Windowsトースト/Slack)・dedup・resolveの
判断には一切使わず、AlertAggregator/notifyからこのモジュールを参照することもない
(分類補助を外しても、アラートは従来どおり通知される)。

実装はルールベース。計画書は「入力: アラート本文・発生回数・対象ツール、出力: ラベル + 確率」と
していたが、いまのルールが出すscoreは較正された確率ではなく「目安」にすぎない。確率に見せかけると
誤解を招くため、確率とは呼ばずscore(0〜1の目安)と、そう判断した理由(reasons)を返す。
LLMや学習済みモデルによる分類へ差し替えたくなったときは、AlertPriorityClassifierを満たす
別の実装を渡せばよい(精度・コスト・外部送信の可否は、導入するときに自データで確認する)。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol

from .alert_aggregator import AlertRecord, Severity, health_check_alert_id
from .registry import ToolCategory


class AlertPriority(str, Enum):
    URGENT = "urgent"
    NORMAL = "normal"
    INSUFFICIENT = "insufficient_info"


PRIORITY_LABEL_JA: dict[AlertPriority, str] = {
    AlertPriority.URGENT: "緊急",
    AlertPriority.NORMAL: "通常",
    AlertPriority.INSUFFICIENT: "情報不足",
}

# 見る順番(小さいほど先)。計画書の並びどおり 緊急 → 通常 → 情報不足。
PRIORITY_RANK: dict[AlertPriority, int] = {
    AlertPriority.URGENT: 0,
    AlertPriority.NORMAL: 1,
    AlertPriority.INSUFFICIENT: 2,
}


@dataclass(frozen=True)
class PriorityAssessment:
    priority: AlertPriority
    score: float  # 0〜1の目安。較正された確率ではない
    reasons: tuple[str, ...]

    @property
    def label(self) -> str:
        return PRIORITY_LABEL_JA[self.priority]


class AlertPriorityClassifier(Protocol):
    def assess(self, alert: AlertRecord, *, tool_category: Optional[ToolCategory] = None) -> PriorityAssessment: ...


_SEVERITY_BASE = {Severity.INFO: 0.10, Severity.WARN: 0.40, Severity.CRITICAL: 0.70}
_URGENT_THRESHOLD = 0.70
# normalize_from_*の既定メッセージ("profiling alert: unknown"等)は原因の手掛かりを含まない短文になる
_PLACEHOLDER_MAX_LEN = 40


class RuleBasedPriorityClassifier:
    """重大度・発生回数・停止かどうか・指標の直接/間接から目安のscoreを作り、ラベルへ落とす。"""

    def assess(self, alert: AlertRecord, *, tool_category: Optional[ToolCategory] = None) -> PriorityAssessment:
        message = (alert.message or "").strip()
        base = _SEVERITY_BASE[alert.severity]
        reasons = [f"重大度: {alert.severity.value}"]

        is_liveness = alert.alert_id == health_check_alert_id(alert.source_tool_id)
        score = base

        if is_liveness:
            score += 0.10
            reasons.append("死活監視で停止を検知")
        if alert.occurrence_count >= 3:
            score += 0.15
            reasons.append(f"再発 {alert.occurrence_count}回目")
        elif alert.occurrence_count == 2:
            score += 0.10
            reasons.append("再発 2回目")
        if not is_liveness and tool_category in (ToolCategory.OBSERVED_ONLY, ToolCategory.EXCLUDED):
            score -= 0.15
            reasons.append("他ツール経由の間接的な指標")

        score = round(min(1.0, max(0.0, score)), 2)

        if self._lacks_information(message):
            return PriorityAssessment(
                AlertPriority.INSUFFICIENT, score, (*reasons, "メッセージに原因の手掛かりが無い")
            )
        priority = AlertPriority.URGENT if score >= _URGENT_THRESHOLD else AlertPriority.NORMAL
        return PriorityAssessment(priority, score, tuple(reasons))

    @staticmethod
    def _lacks_information(message: str) -> bool:
        if len(message) < 6:
            return True
        return "unknown" in message.lower() and len(message) < _PLACEHOLDER_MAX_LEN
