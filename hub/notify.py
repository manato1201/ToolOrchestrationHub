"""hub/notify.py

Phase3拡張: AlertAggregatorが検知したアラートをローカル通知チャネルへ配信する。

DESIGN.md Phase3では「通知ルーティング先(Issue作成、Slack、ローカル通知等)はHubのスコープ外とし、
v1はAlertRecordの状態をダッシュボードに表示するのみに留める」としていたが、ダッシュボードを
開いていないと異常に気づけないというギャップがあったためv1.1として追加する。
Slack等の外部通知は引き続き将来課題として、まずはローカルのWindowsトースト通知のみ実装する。

AlertAggregator自体はこのモジュールを知らない(NotificationSinkの構造的インターフェースに
依存するのみ)。循環importを避けるため、依存の向きは notify.py -> alert_aggregator.py の一方向。
"""
from __future__ import annotations

import logging
import sys
from typing import Optional, Protocol

from .alert_aggregator import AlertRecord, Severity

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {Severity.INFO: 0, Severity.WARN: 1, Severity.CRITICAL: 2}


class NotificationSink(Protocol):
    def notify_opened(self, alert: AlertRecord) -> None: ...

    def notify_resolved(self, alert: AlertRecord) -> None: ...


class NullSink:
    """通知先が使えない環境(非Windows、winotify未インストール等)向けのno-op実装。"""

    def notify_opened(self, alert: AlertRecord) -> None:
        pass

    def notify_resolved(self, alert: AlertRecord) -> None:
        pass


class WindowsToastSink:
    """winotifyを使ったWindowsトースト通知。

    min_severity未満のアラートは通知しない(既定はWARN以上。INFOで毎回鳴らすと
    ノイズになるため)。通知配信自体の失敗でHub本体を落とさないよう、
    例外は握りつぶしてログにのみ残す。
    """

    def __init__(self, min_severity: Severity = Severity.WARN, app_id: str = "ToolOrchestrationHub") -> None:
        self._min_severity = min_severity
        self._app_id = app_id
        self._notification_cls = None
        if sys.platform == "win32":
            try:
                from winotify import Notification

                self._notification_cls = Notification
            except ImportError:
                logger.warning("winotifyが見つかりません。トースト通知は無効化されます。")

    @property
    def is_enabled(self) -> bool:
        return self._notification_cls is not None

    def _should_notify(self, alert: AlertRecord) -> bool:
        return _SEVERITY_ORDER[alert.severity] >= _SEVERITY_ORDER[self._min_severity]

    def notify_opened(self, alert: AlertRecord) -> None:
        if not self._should_notify(alert):
            return
        self._send(f"[{alert.severity.value.upper()}] {alert.source_tool_id}", alert.message)

    def notify_resolved(self, alert: AlertRecord) -> None:
        if not self._should_notify(alert):
            return
        self._send(f"[resolved] {alert.source_tool_id}", alert.message)

    def _send(self, title: str, message: str) -> None:
        if self._notification_cls is None:
            return
        try:
            toast = self._notification_cls(
                app_id=self._app_id,
                title=title,
                msg=message,
                duration="short",
            )
            toast.show()
        except Exception:
            logger.exception("トースト通知の送出に失敗しました(Hub本体は継続動作します)")


def default_sink(min_severity: Severity = Severity.WARN) -> NotificationSink:
    """プラットフォームに応じた既定のNotificationSinkを返す。"""
    if sys.platform == "win32":
        sink = WindowsToastSink(min_severity=min_severity)
        if sink.is_enabled:
            return sink
    return NullSink()
