"""hub/notify.py の通知チャネル(v1.1: Windowsトースト通知、v2.3: Slack webhook)テスト。

実際のトースト表示(toast.show())や本物のHTTPリクエストは環境依存かつ副作用が大きいため、
`_notification_cls`や`urllib.request.urlopen`をフェイクに差し替えて「何が呼ばれたか」のみを検証する。
"""

from __future__ import annotations

from datetime import datetime, timezone

import hub.notify as notify_module
from hub.alert_aggregator import AlertRecord, Severity
from hub.notify import (
    CompositeSink,
    NullSink,
    SlackWebhookSink,
    WindowsToastSink,
    default_sink,
)


def _alert(severity: Severity) -> AlertRecord:
    return AlertRecord(
        alert_id="dev_rag_environment:deadbeef",
        source_tool_id="dev_rag_environment",
        severity=severity,
        message="liveness down",
        first_seen_at=datetime.now(timezone.utc),
    )


class _FakeToast:
    sent: list[tuple[str, str, str]] = []

    def __init__(self, app_id: str, title: str, msg: str, duration: str) -> None:
        self.app_id = app_id
        self.title = title
        self.msg = msg
        self.duration = duration

    def show(self) -> None:
        _FakeToast.sent.append((self.app_id, self.title, self.msg))


def _fake_sink(min_severity: Severity = Severity.WARN) -> WindowsToastSink:
    sink = WindowsToastSink(min_severity=min_severity)
    sink._notification_cls = _FakeToast  # type: ignore[attr-defined]
    _FakeToast.sent = []
    return sink


def test_null_sink_never_raises():
    sink = NullSink()
    sink.notify_opened(_alert(Severity.CRITICAL))
    sink.notify_resolved(_alert(Severity.CRITICAL))


def test_windows_toast_sink_notifies_on_critical_open():
    sink = _fake_sink(min_severity=Severity.WARN)
    sink.notify_opened(_alert(Severity.CRITICAL))
    assert len(_FakeToast.sent) == 1
    assert "CRITICAL" in _FakeToast.sent[0][1]


def test_windows_toast_sink_suppresses_below_min_severity():
    sink = _fake_sink(min_severity=Severity.WARN)
    sink.notify_opened(_alert(Severity.INFO))
    assert len(_FakeToast.sent) == 0


def test_windows_toast_sink_notifies_on_resolve():
    sink = _fake_sink(min_severity=Severity.WARN)
    sink.notify_resolved(_alert(Severity.CRITICAL))
    assert len(_FakeToast.sent) == 1
    assert "resolved" in _FakeToast.sent[0][1]


def test_windows_toast_sink_send_failure_does_not_raise():
    sink = _fake_sink(min_severity=Severity.WARN)

    class _RaisingToast:
        def __init__(self, **kwargs):
            raise RuntimeError("boom")

    sink._notification_cls = _RaisingToast  # type: ignore[attr-defined]
    sink.notify_opened(_alert(Severity.CRITICAL))  # 例外を外に漏らさないこと


def test_default_sink_returns_a_sink_matching_the_platform(monkeypatch):
    """実際にトーストを送出すると開発機のデスクトップに本物の通知が出てしまうため、
    ここでは戻り値の型のみを検証し、show()の呼び出しは行わない。
    HUB_SLACK_WEBHOOK_URLが開発機の環境に設定されている可能性を排除するため未設定にする。
    """
    monkeypatch.delenv(notify_module.SLACK_WEBHOOK_URL_ENV, raising=False)
    sink = default_sink()
    assert isinstance(sink, (NullSink, WindowsToastSink))


def _fake_slack_sink(monkeypatch, min_severity: Severity = Severity.WARN) -> tuple[SlackWebhookSink, list]:
    sent: list = []

    def fake_urlopen(req, timeout=None):
        sent.append((req.full_url, req.data))

    monkeypatch.setattr(notify_module.urllib.request, "urlopen", fake_urlopen)
    sink = SlackWebhookSink("https://hooks.example.test/services/x", min_severity=min_severity)
    return sink, sent


def test_slack_webhook_sink_notifies_on_critical_open(monkeypatch):
    sink, sent = _fake_slack_sink(monkeypatch)
    sink.notify_opened(_alert(Severity.CRITICAL))
    assert len(sent) == 1
    url, body = sent[0]
    assert url == "https://hooks.example.test/services/x"
    assert b"CRITICAL" in body


def test_slack_webhook_sink_suppresses_below_min_severity(monkeypatch):
    sink, sent = _fake_slack_sink(monkeypatch, min_severity=Severity.WARN)
    sink.notify_opened(_alert(Severity.INFO))
    assert len(sent) == 0


def test_slack_webhook_sink_notifies_on_resolve(monkeypatch):
    sink, sent = _fake_slack_sink(monkeypatch)
    sink.notify_resolved(_alert(Severity.CRITICAL))
    assert len(sent) == 1
    assert b"resolved" in sent[0][1]


def test_slack_webhook_sink_send_failure_does_not_raise(monkeypatch):
    def raising_urlopen(req, timeout=None):
        raise OSError("boom")

    monkeypatch.setattr(notify_module.urllib.request, "urlopen", raising_urlopen)
    sink = SlackWebhookSink("https://hooks.example.test/services/x")
    sink.notify_opened(_alert(Severity.CRITICAL))  # 例外を外に漏らさないこと


def test_composite_sink_fans_out_to_all_sinks():
    calls: list[str] = []

    class _Recorder:
        def __init__(self, name: str) -> None:
            self._name = name

        def notify_opened(self, alert: AlertRecord) -> None:
            calls.append(f"{self._name}:opened")

        def notify_resolved(self, alert: AlertRecord) -> None:
            calls.append(f"{self._name}:resolved")

    composite = CompositeSink([_Recorder("a"), _Recorder("b")])
    composite.notify_opened(_alert(Severity.CRITICAL))
    composite.notify_resolved(_alert(Severity.CRITICAL))
    assert calls == ["a:opened", "b:opened", "a:resolved", "b:resolved"]


def test_composite_sink_one_failing_sink_does_not_block_others():
    calls: list[str] = []

    class _Raising:
        def notify_opened(self, alert: AlertRecord) -> None:
            raise RuntimeError("boom")

        def notify_resolved(self, alert: AlertRecord) -> None:
            raise RuntimeError("boom")

    class _Recorder:
        def notify_opened(self, alert: AlertRecord) -> None:
            calls.append("recorded")

        def notify_resolved(self, alert: AlertRecord) -> None:
            calls.append("recorded")

    composite = CompositeSink([_Raising(), _Recorder()])
    composite.notify_opened(_alert(Severity.CRITICAL))
    assert calls == ["recorded"]


def test_default_sink_includes_slack_when_env_var_set(monkeypatch):
    monkeypatch.setenv(notify_module.SLACK_WEBHOOK_URL_ENV, "https://hooks.example.test/services/x")
    sink = default_sink()
    if isinstance(sink, CompositeSink):
        assert any(isinstance(s, SlackWebhookSink) for s in sink._sinks)
    else:
        assert isinstance(sink, SlackWebhookSink)
