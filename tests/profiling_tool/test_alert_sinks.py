"""ユーザー追加要件「サービスの連携」: WebhookSink / ToolOrchestrationHubSink。

実ネットワークに触れないよう`urllib.request.urlopen`をモックして、送信先URL・
ペイロードの組み立てのみを検証する。
"""
from __future__ import annotations

import json

from profiling_tool.alerting.threshold_alert import ToolOrchestrationHubSink, WebhookSink

_ALERT = {
    "target": "sound_middleware",
    "metric": "underrun_count",
    "value": 3,
    "threshold": 0,
    "severity": "critical",
    "timestamp_us": 1_000_000,
    "run_id": "run001",
}


def test_webhook_sink_posts_alert_as_is(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode("utf-8"))
        captured["headers"] = dict(req.header_items())

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    sink = WebhookSink("https://hooks.example.com/incoming/abc")
    sink.emit(_ALERT)

    assert captured["url"] == "https://hooks.example.com/incoming/abc"
    assert captured["body"] == _ALERT


def test_webhook_sink_swallows_network_errors(monkeypatch):
    import urllib.error

    def fake_urlopen(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    sink = WebhookSink("https://hooks.example.com/incoming/abc")
    sink.emit(_ALERT)  # 例外を外に漏らさないこと(プロファイリング自体を止めない)


def test_tool_orchestration_hub_sink_posts_to_profiling_tool_endpoint(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode("utf-8"))

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    sink = ToolOrchestrationHubSink(hub_base_url="http://127.0.0.1:8790")
    sink.emit(_ALERT)

    assert captured["url"] == "http://127.0.0.1:8790/api/alerts/profiling-tool"
    # ToolOrchestrationHub側のnormalize_from_profiling_toolが期待する形に変換されていること
    assert captured["body"]["signature"] == "sound_middleware:underrun_count"
    assert captured["body"]["severity"] == "critical"
    assert "message" in captured["body"]


def test_tool_orchestration_hub_sink_maps_warning_severity_to_warn(monkeypatch):
    """契約スキーマのseverityは"warning"だが、Hub側のSeverity enumは"warn"であるため変換する。"""
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["body"] = json.loads(req.data.decode("utf-8"))

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    sink = ToolOrchestrationHubSink()
    sink.emit({**_ALERT, "severity": "warning"})

    assert captured["body"]["severity"] == "warn"
