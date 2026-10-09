"""hub/alert_view.py

アラート1件に「見る順番の目安」(H2)と「運用手順」(H6)を添えて、画面用の辞書にする。

アラート一覧の表、ツール詳細カード、概況の直近アラートが同じ内容を出せるよう、
添える処理をここの1か所にまとめている。**表示専用**: 通知・dedup・resolveの経路からは
呼ばない(分類補助や手順書が壊れても、アラートは従来どおり通知される)。
このモジュールの中の失敗は握りつぶして、該当項目をNoneにするだけで画面は出し続ける。
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from .alert_aggregator import AlertRecord
from .alert_priority import AlertPriority, AlertPriorityClassifier, PRIORITY_RANK
from .registry import ToolRegistry
from .runbooks import RunbookCatalog, kind_for

logger = logging.getLogger(__name__)

AlertDecorator = Callable[[AlertRecord], dict]

# 分類補助が無い/失敗したアラートの順位。「通常」と同じ位置に置く(勝手に緊急・情報不足へ寄せない)。
PRIORITY_RANK_UNKNOWN = PRIORITY_RANK[AlertPriority.NORMAL]


def make_alert_decorator(
    registry: ToolRegistry,
    classifier: Optional[AlertPriorityClassifier],
    runbooks: RunbookCatalog,
) -> AlertDecorator:
    """AlertRecord -> {priority*, runbook*} を返す関数を作る。registryは台帳の最新状態を毎回引く。"""

    def decorate(alert: AlertRecord) -> dict:
        priority = priority_label = score = None
        reasons: list[str] = []
        priority_rank = PRIORITY_RANK_UNKNOWN
        if classifier is not None:
            try:
                entry = registry.get(alert.source_tool_id)
                assessment = classifier.assess(alert, tool_category=entry.category if entry else None)
                priority = assessment.priority.value
                priority_label = assessment.label
                score = assessment.score
                reasons = list(assessment.reasons)
                priority_rank = PRIORITY_RANK[assessment.priority]
            except Exception:  # noqa: BLE001 - 表示専用の補助。壊れても画面とアラート処理は止めない
                logger.exception("アラートの優先度補助に失敗しました(表示のみに影響します)")

        runbook = None
        runbook_kind = kind_for(alert)
        try:
            found = runbooks.for_alert(alert)
            if found is not None:
                runbook = {
                    "kind": found.kind,
                    "title": found.title,
                    "do": list(found.do),
                    "dont": list(found.dont),
                    "deliverable": list(found.deliverable),
                }
        except Exception:  # noqa: BLE001
            logger.exception("運用手順書の取得に失敗しました(表示のみに影響します)")

        return {
            "priority": priority,
            "priority_label": priority_label,
            "priority_score": score,
            "priority_reasons": reasons,
            "priority_rank": priority_rank,
            "runbook_kind": runbook_kind,
            "runbook": runbook,
        }

    return decorate
