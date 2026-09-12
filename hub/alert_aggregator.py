"""hub/alert_aggregator.py

Phase3: 複数ソースから届くアラートを単一のライフサイクルモデルへ正規化し、
重複を1件に集約、解消時に自動でresolve状態へ遷移させる。

dedup/resolveのライフサイクルは新規発明しない。Research-Collectorが既に実装・実機検証済みの
「同一ラベル(auth-expired/refresh-soon)でのIssue自動作成→open中Issueの重複防止チェック→
解消時のgh issue close」パターンを直接の前例として引用し、AlertRecord.alert_idをIssueの
ラベル+検索キーに相当するdedupキーとして同型に扱う。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable, Optional, Protocol

from .health.base import HealthResult


class Severity(str, Enum):
    INFO = "info"
    WARN = "warn"
    CRITICAL = "critical"


@dataclass
class AlertRecord:
    alert_id: str  # sourceToolId + 正規化した障害シグネチャのハッシュ。dedupキー
    source_tool_id: str
    severity: Severity
    message: str
    first_seen_at: datetime
    resolved_at: Optional[datetime] = None  # Noneの間はopen。resolve検知でタイムスタンプを刻む

    @property
    def is_open(self) -> bool:
        return self.resolved_at is None


class AlertStore(Protocol):
    """AlertAggregatorが要求する永続化ストアの構造的インターフェース。

    hub/alert_store.pyのSqliteAlertStoreがこれを満たすが、AlertAggregator側は
    実装を一切知らない(依存の向きはalert_store.py -> alert_aggregator.pyの一方向で、
    循環importを避けるためここではProtocolのみを定義する)。
    """

    def save(self, alert: AlertRecord) -> None: ...

    def load_all(self) -> list[AlertRecord]: ...

    def delete(self, alert_id: str) -> None: ...


def _make_alert_id(source_tool_id: str, signature: str) -> str:
    """sourceToolId + 正規化した障害シグネチャのハッシュ。"""
    digest = hashlib.sha256(signature.encode("utf-8")).hexdigest()[:16]
    return f"{source_tool_id}:{digest}"


def normalize_from_profiling_tool(raw_alert: dict) -> AlertRecord:
    """Profiling Tool Phase4のメトリクス/アラート発行契約をそのまま正規化するのみ。"""
    tool_id = "profiling_tool"
    signature = raw_alert.get("signature") or raw_alert.get("metric_name", "unknown")
    severity = Severity(raw_alert.get("severity", "warn"))
    return AlertRecord(
        alert_id=_make_alert_id(tool_id, str(signature)),
        source_tool_id=tool_id,
        severity=severity,
        message=raw_alert.get("message", f"profiling alert: {signature}"),
        first_seen_at=datetime.now(timezone.utc),
    )


def normalize_from_visual_regression_qa(raw_evaluation: dict) -> AlertRecord:
    """Visual Regression QA Tool Phase5の差し替え可能アラートsinkの1実装として正規化する。"""
    tool_id = "visual_regression_qa_tool"
    signature = raw_evaluation.get("case_id", "unknown")
    is_failure = not raw_evaluation.get("passed", True)
    severity = Severity.CRITICAL if is_failure else Severity.INFO
    message = raw_evaluation.get(
        "message", f"visual regression case {signature}: {'failed' if is_failure else 'passed'}"
    )
    return AlertRecord(
        alert_id=_make_alert_id(tool_id, str(signature)),
        source_tool_id=tool_id,
        severity=severity,
        message=message,
        first_seen_at=datetime.now(timezone.utc),
    )


def normalize_from_asset_data_insight(raw_manifest_entry: dict) -> AlertRecord:
    """Asset Data Insight Suiteのreport_manifest.jsonエントリをそのまま正規化するのみ。"""
    tool_id = "asset_data_insight_suite"
    signature = raw_manifest_entry.get("asset_id", "unknown")
    severity = Severity(raw_manifest_entry.get("severity", "warn"))
    message = raw_manifest_entry.get("message", f"asset insight flagged: {signature}")
    return AlertRecord(
        alert_id=_make_alert_id(tool_id, str(signature)),
        source_tool_id=tool_id,
        severity=severity,
        message=message,
        first_seen_at=datetime.now(timezone.utc),
    )


def health_check_alert_id(tool_id: str) -> str:
    """normalize_from_health_checkが生成するalert_idを、AlertRecordを構築せずに算出する。

    ポーリングループが「upに戻った」ケースでresolve_by_idするためだけに
    使い捨てのAlertRecordを組み立てる無駄を避けるための公開ヘルパー。
    """
    return _make_alert_id(tool_id, "liveness_down")


def normalize_from_health_check(tool_id: str, result: HealthResult) -> AlertRecord:
    """Hub自身のヘルスチェック(Phase2)由来のdown検知を正規化する。"""
    severity = Severity.CRITICAL if not result.is_up else Severity.INFO
    message = f"{tool_id} liveness check: {'down' if not result.is_up else 'up'}"
    return AlertRecord(
        alert_id=health_check_alert_id(tool_id),
        source_tool_id=tool_id,
        severity=severity,
        message=message,
        first_seen_at=datetime.now(timezone.utc),
    )


def upsert_alert(new_alert: AlertRecord, existing: list[AlertRecord]) -> AlertRecord:
    """Research-Collector `refresh_auth.ps1` の
    「openなラベル一致Issueがあれば新規作成せず、解消時にcloseする」パターンを踏襲する。

    alert_idが一致するopenレコードがあれば新規作成せず、firstSeenAtは据え置いてそれを返す。
    一致するopenレコードが無ければ新規AlertRecordをそのまま返す(呼び出し側がexistingへ追加する)。
    """
    for existing_alert in existing:
        if existing_alert.alert_id == new_alert.alert_id and existing_alert.resolved_at is None:
            return existing_alert  # 重複作成しない(Research-Collectorの重複防止チェックと同型)
    return new_alert


def resolve_alert(alert: AlertRecord) -> AlertRecord:
    """該当ソースからのアラート解消を検知した時点でresolvedAtを刻む。

    Research-Collectorの自動クローズ(refresh_auth.ps1)と同型のライフサイクル遷移。
    """
    alert.resolved_at = datetime.now(timezone.utc)
    return alert


class AlertAggregator:
    """Profiling Tool(主経路)/Visual Regression QA Tool/Asset Data Insight Suite/
    Hub自身のヘルスチェックの4ソースからのAlertRecordを保持し、upsert/resolveする。

    on_open/on_resolveは新規open・resolve確定のタイミングで1回だけ呼ばれるコールバックで、
    hub/notify.pyの通知チャネル(Windowsトースト等)を疎結合に差し込むための拡張点。
    storeを渡すとAlertRecordをSQLite等へ永続化し、Hub再起動後もアラート履歴を保持する
    (hub/alert_store.py参照)。いずれもAlertAggregator自身は実装を一切知らない。
    """

    def __init__(
        self,
        store: Optional[AlertStore] = None,
        on_open: Optional[Callable[[AlertRecord], None]] = None,
        on_resolve: Optional[Callable[[AlertRecord], None]] = None,
    ) -> None:
        self._store = store
        self._on_open = on_open
        self._on_resolve = on_resolve
        self._alerts: list[AlertRecord] = list(store.load_all()) if store is not None else []
        # alert_id -> スヌーズ解除時刻。使いやすさ改善(フラッピング対策): 同一アラートが
        # 短時間でopen/resolveを繰り返す場合に通知だけを一時的に抑制する。アラート自体の
        # open/resolved状態・dedupには一切影響しない(表示は通常通り)。永続化はせず
        # Hubプロセスのメモリ上にのみ持つ(launch_historyと同じく軽量な一時状態の扱い)。
        self._snoozed_until: dict[str, datetime] = {}

    def snooze(self, alert_id: str, until: datetime) -> None:
        """指定アラートの通知(on_open/on_resolve)をuntilまで抑制する。"""
        self._snoozed_until[alert_id] = until

    def unsnooze(self, alert_id: str) -> None:
        self._snoozed_until.pop(alert_id, None)

    def snoozed_until(self, alert_id: str, *, now: Optional[datetime] = None) -> Optional[datetime]:
        """スヌーズ中ならその解除時刻を返す。期限切れなら自動でクリアしてNoneを返す。"""
        until = self._snoozed_until.get(alert_id)
        if until is None:
            return None
        now = now if now is not None else datetime.now(timezone.utc)
        if now >= until:
            del self._snoozed_until[alert_id]
            return None
        return until

    def is_snoozed(self, alert_id: str, *, now: Optional[datetime] = None) -> bool:
        return self.snoozed_until(alert_id, now=now) is not None

    def ingest(self, new_alert: AlertRecord) -> AlertRecord:
        """新規アラートをdedupしつつ取り込む。既存openレコードがあればそれを返す。"""
        upserted = upsert_alert(new_alert, self._alerts)
        if upserted is new_alert:
            self._alerts.append(new_alert)
            if self._store is not None:
                self._store.save(new_alert)
            if self._on_open is not None and not self.is_snoozed(new_alert.alert_id):
                self._on_open(new_alert)
        return upserted

    def resolve_by_id(self, alert_id: str) -> Optional[AlertRecord]:
        for alert in self._alerts:
            if alert.alert_id == alert_id and alert.is_open:
                resolved = resolve_alert(alert)
                if self._store is not None:
                    self._store.save(resolved)
                if self._on_resolve is not None and not self.is_snoozed(alert_id):
                    self._on_resolve(resolved)
                return resolved
        return None

    def prune_resolved(self, retention: timedelta) -> list[AlertRecord]:
        """resolved_atがretentionより古いレコードをメモリ・永続化ストアの両方から削除する。

        storeを持たない(メモリのみの)構成だとAlertAggregatorはresolved分も無限に
        溜め続けてしまうため、長時間稼働するHubプロセス向けの安全弁として用意する。
        """
        cutoff = datetime.now(timezone.utc) - retention
        to_prune = [a for a in self._alerts if a.resolved_at is not None and a.resolved_at < cutoff]
        if not to_prune:
            return []
        pruned_ids = {a.alert_id for a in to_prune}
        self._alerts = [a for a in self._alerts if a.alert_id not in pruned_ids]
        if self._store is not None:
            for alert in to_prune:
                self._store.delete(alert.alert_id)
        return to_prune

    def open_alerts(self) -> list[AlertRecord]:
        return [a for a in self._alerts if a.is_open]

    def resolved_alerts(self) -> list[AlertRecord]:
        return [a for a in self._alerts if not a.is_open]

    def all(self) -> list[AlertRecord]:
        return list(self._alerts)
