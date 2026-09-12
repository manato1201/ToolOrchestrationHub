"""hub/notify.py

Phase3拡張: AlertAggregatorが検知したアラートをローカル通知チャネルへ配信する。

DESIGN.md Phase3では「通知ルーティング先(Issue作成、Slack、ローカル通知等)はHubのスコープ外とし、
v1はAlertRecordの状態をダッシュボードに表示するのみに留める」としていたが、ダッシュボードを
開いていないと異常に気づけないというギャップがあったためv1.1として追加する。

v1.1時点ではWindowsトースト通知のみだったが、PCの前にいないと気づけないという同種のギャップが
残っていたため、v2.3としてSlack Incoming Webhook(相当のJSON webhook)への通知を追加する。
WindowsToastSink/SlackWebhookSinkは互いを知らず、CompositeSinkが両方へ独立にfan-outする
(片方の配信失敗がもう片方に波及しない)。

AlertAggregator自体はこのモジュールを知らない(NotificationSinkの構造的インターフェースに
依存するのみ)。循環importを避けるため、依存の向きは notify.py -> alert_aggregator.py の一方向。
"""
from __future__ import annotations

import json
import logging
import os
import sys
import urllib.error
import urllib.request
from typing import Optional, Protocol

from .alert_aggregator import AlertRecord, Severity

logger = logging.getLogger(__name__)

# Slack Incoming Webhook(または同形式のJSON webhookを受けられるサービス)のURL。
# registry.yaml等の静的ファイルには置かず、認証情報に類する値として環境変数から読む。
SLACK_WEBHOOK_URL_ENV = "HUB_SLACK_WEBHOOK_URL"

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


class SlackWebhookSink:
    """サービス連携(利便性向上のための追加): Slack Incoming Webhookへの通知配信。

    WindowsToastSinkと同じくmin_severity未満は通知しない。通知配信の失敗でHub本体を
    落とさないよう例外は握りつぶし、ログにのみ残す(profiling_tool側のWebhookSinkと同じ方針)。
    """

    def __init__(
        self, webhook_url: str, min_severity: Severity = Severity.WARN, timeout_s: float = 3.0
    ) -> None:
        self._webhook_url = webhook_url
        self._min_severity = min_severity
        self._timeout_s = timeout_s

    def _should_notify(self, alert: AlertRecord) -> bool:
        return _SEVERITY_ORDER[alert.severity] >= _SEVERITY_ORDER[self._min_severity]

    def notify_opened(self, alert: AlertRecord) -> None:
        if not self._should_notify(alert):
            return
        self._send(f"[{alert.severity.value.upper()}] {alert.source_tool_id}: {alert.message}")

    def notify_resolved(self, alert: AlertRecord) -> None:
        if not self._should_notify(alert):
            return
        self._send(f"[resolved] {alert.source_tool_id}: {alert.message}")

    def _send(self, text: str) -> None:
        body = json.dumps({"text": text}).encode("utf-8")
        req = urllib.request.Request(
            self._webhook_url, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            urllib.request.urlopen(req, timeout=self._timeout_s)
        except (urllib.error.URLError, OSError):
            logger.warning("Slack webhookへの通知送出に失敗しました(Hub本体は継続動作します)")


class CompositeSink:
    """複数のNotificationSinkへ独立にfan-outする。

    1つのsinkの配信失敗(例外)が他のsinkの配信を止めないよう、各sink呼び出しを
    個別にtry/exceptで囲む(WindowsToastSink自身も内部で握りつぶしているが、
    将来追加されるsink実装が同じ規律を守るとは限らないための二重の安全網)。
    """

    def __init__(self, sinks: list[NotificationSink]) -> None:
        self._sinks = sinks

    def notify_opened(self, alert: AlertRecord) -> None:
        for sink in self._sinks:
            try:
                sink.notify_opened(alert)
            except Exception:
                logger.exception("NotificationSink.notify_openedの呼び出しに失敗しました")

    def notify_resolved(self, alert: AlertRecord) -> None:
        for sink in self._sinks:
            try:
                sink.notify_resolved(alert)
            except Exception:
                logger.exception("NotificationSink.notify_resolvedの呼び出しに失敗しました")


def default_sink(min_severity: Severity = Severity.WARN) -> NotificationSink:
    """プラットフォームに応じた既定のNotificationSinkを返す。

    有効なチャネルが複数あれば(Windowsトースト + Slack webhook等)CompositeSinkで束ね、
    1つも無ければNullSink(no-op)を返す。
    """
    sinks: list[NotificationSink] = []

    if sys.platform == "win32":
        toast = WindowsToastSink(min_severity=min_severity)
        if toast.is_enabled:
            sinks.append(toast)

    webhook_url = os.environ.get(SLACK_WEBHOOK_URL_ENV)
    if webhook_url:
        sinks.append(SlackWebhookSink(webhook_url, min_severity=min_severity))

    if not sinks:
        return NullSink()
    if len(sinks) == 1:
        return sinks[0]
    return CompositeSink(sinks)
