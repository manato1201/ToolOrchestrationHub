"""hub/notify.py の通知チャネル(v1.1: Windowsトースト通知)テスト。

実際のトースト表示(toast.show())は環境依存かつ副作用が大きいため、
`_notification_cls`をフェイクに差し替えて「何が呼ばれたか」のみを検証する。
"""

from __future__ import annotations

from datetime import datetime, timezone

from hub.alert_aggregator import AlertRecord, Severity
from hub.notify import NullSink, WindowsToastSink, default_sink


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


def test_default_sink_returns_a_sink_matching_the_platform():
    """実際にトーストを送出すると開発機のデスクトップに本物の通知が出てしまうため、
    ここでは戻り値の型のみを検証し、show()の呼び出しは行わない。
    """
    sink = default_sink()
    assert isinstance(sink, (NullSink, WindowsToastSink))
