"""hub/runbooks.py

アラート種別ごとの運用手順書(やること / やらないこと / 成果物)。IMPROVEMENT_PLAN_2026-10 H6。

対応の抜けを防ぐため、手順はアラートの種別ごとに固定し、hub/runbooks.yaml に書く
(コードを触らずに運用側で書き換えられる)。ダッシュボードのアラート行から開ける。

種別はAlertRecordだけから決める(Hubは対象ツールに問い合わせない):
- 死活監視由来(alert_idがhealth_check_alert_idと一致) → liveness_down
- ProfilingTool / VisualRegressionQATool / AssetDataInsightSuite 由来 → それぞれの種別
- それ以外 → generic
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from .alert_aggregator import AlertRecord, health_check_alert_id

DEFAULT_RUNBOOKS_PATH = Path(__file__).parent / "runbooks.yaml"

KIND_LIVENESS_DOWN = "liveness_down"
KIND_PROFILING_THRESHOLD = "profiling_threshold"
KIND_VISUAL_REGRESSION_FAILURE = "visual_regression_failure"
KIND_ASSET_INSIGHT_FLAG = "asset_insight_flag"
KIND_GENERIC = "generic"

ALL_KINDS = (
    KIND_LIVENESS_DOWN,
    KIND_PROFILING_THRESHOLD,
    KIND_VISUAL_REGRESSION_FAILURE,
    KIND_ASSET_INSIGHT_FLAG,
    KIND_GENERIC,
)

_KIND_BY_SOURCE = {
    "profiling_tool": KIND_PROFILING_THRESHOLD,
    "visual_regression_qa_tool": KIND_VISUAL_REGRESSION_FAILURE,
    "asset_data_insight_suite": KIND_ASSET_INSIGHT_FLAG,
}


class RunbookError(Exception):
    """runbooks.yamlのパース/スキーマ検証に失敗した場合に送出する。"""


@dataclass(frozen=True)
class Runbook:
    kind: str
    title: str
    do: tuple[str, ...]
    dont: tuple[str, ...]
    deliverable: tuple[str, ...]


def kind_for(alert: AlertRecord) -> str:
    if alert.alert_id == health_check_alert_id(alert.source_tool_id):
        return KIND_LIVENESS_DOWN
    return _KIND_BY_SOURCE.get(alert.source_tool_id, KIND_GENERIC)


class RunbookCatalog:
    def __init__(self, runbooks: dict[str, Runbook]) -> None:
        self._runbooks = runbooks

    @classmethod
    def empty(cls) -> "RunbookCatalog":
        return cls({})

    @classmethod
    def load(cls, path: Path | str = DEFAULT_RUNBOOKS_PATH) -> "RunbookCatalog":
        path = Path(path)
        try:
            with path.open(encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
        except yaml.YAMLError as exc:
            raise RunbookError(f"{path} のYAMLパースに失敗しました: {exc}") from exc
        entries = raw.get("runbooks")
        if not isinstance(entries, dict):
            raise RunbookError(f"{path} に 'runbooks' マップがありません")

        runbooks: dict[str, Runbook] = {}
        for kind, body in entries.items():
            if not isinstance(body, dict):
                raise RunbookError(f"runbooks.{kind} はマップで指定してください")
            title = body.get("title")
            if not isinstance(title, str) or not title.strip():
                raise RunbookError(f"runbooks.{kind}.title が空です")
            runbooks[kind] = Runbook(
                kind=kind,
                title=title,
                do=_string_list(kind, body, "do"),
                dont=_string_list(kind, body, "dont"),
                deliverable=_string_list(kind, body, "deliverable"),
            )
        return cls(runbooks)

    def get(self, kind: str) -> Optional[Runbook]:
        return self._runbooks.get(kind)

    def for_alert(self, alert: AlertRecord) -> Optional[Runbook]:
        """アラートに対応する手順書。種別専用の手順が無ければgenericに落とす(それも無ければNone)。"""
        return self._runbooks.get(kind_for(alert)) or self._runbooks.get(KIND_GENERIC)

    def kinds(self) -> list[str]:
        return list(self._runbooks)


def _string_list(kind: str, body: dict, key: str) -> tuple[str, ...]:
    value = body.get(key)
    if not isinstance(value, list) or not value or not all(isinstance(v, str) and v.strip() for v in value):
        raise RunbookError(f"runbooks.{kind}.{key} は空でない文字列のリストで指定してください")
    return tuple(value)
