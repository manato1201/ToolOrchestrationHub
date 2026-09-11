"""alerting/threshold_alert.py

Phase4: しきい値ベースアラート。AlertSinkは差し替え可能な設計とし、別文書
「VisualRegressionQATool設計書」Phase5と同じ「差し替え可能なsink」原則を再利用する。

ConsoleSink/FileSinkはPhase4本来のスコープ(MVP/運用初期)。WebhookSink/
ToolOrchestrationHubSinkはユーザー追加要件「サービスの連携」に対応する拡張で、
Phase4が本来「Hub側の実装はここでは行わない、契約定義のみ」としていたスコープを
明示的に超える(ユーザーの明示的な指示による)。ThresholdAlertEngine自体は
sinkの実装を一切知らないため、この拡張もsink実装の追加のみで完結し、しきい値判定
ロジック側の変更は不要(Final Phase検証項目)。
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol


class AlertSink(Protocol):
    def emit(self, alert: dict) -> None: ...


class ConsoleSink:
    """MVP。"""

    def emit(self, alert: dict) -> None:
        print(f"[ProfilingTool ALERT] {alert}")


class FileSink:
    """運用初期。追記専用。"""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, alert: dict) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(alert, ensure_ascii=False) + "\n")


class WebhookSink:
    """サービス連携(ユーザー追加要件): 任意のWebhook URL(Slack Incoming Webhook等)へPOSTする。

    通知配信の失敗でプロファイリング自体を止めないよう、例外は握りつぶす。
    """

    def __init__(self, url: str, timeout_s: float = 3.0) -> None:
        self._url = url
        self._timeout_s = timeout_s

    def emit(self, alert: dict) -> None:
        body = json.dumps(alert).encode("utf-8")
        req = urllib.request.Request(
            self._url, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            urllib.request.urlopen(req, timeout=self._timeout_s)
        except (urllib.error.URLError, OSError):
            pass


class ToolOrchestrationHubSink:
    """サービス連携(ユーザー追加要件): alerting/contract.schema.jsonのアラートを
    ToolOrchestrationHubの `POST /api/alerts/profiling-tool` へ送信する。

    Hub側のnormalize_from_profiling_tool()が期待する形({"signature","severity","message"})
    へこのSink内で変換する。Hub側のコードは一切変更しない(Hub自身のスキーマ/実装は
    ToolOrchestrationHub側のドキュメントの責務であり、本ツールはその契約に従うだけ)。
    """

    def __init__(self, hub_base_url: str = "http://127.0.0.1:8790", timeout_s: float = 3.0) -> None:
        self._url = hub_base_url.rstrip("/") + "/api/alerts/profiling-tool"
        self._timeout_s = timeout_s

    def emit(self, alert: dict) -> None:
        severity = "warn" if alert["severity"] == "warning" else alert["severity"]
        payload = {
            "signature": f"{alert['target']}:{alert['metric']}",
            "severity": severity,
            "message": f"{alert['target']}.{alert['metric']}={alert['value']} (threshold={alert['threshold']})",
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._url, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            urllib.request.urlopen(req, timeout=self._timeout_s)
        except (urllib.error.URLError, OSError):
            pass


@dataclass(frozen=True)
class ThresholdRule:
    target: str
    metric: str
    threshold: float
    comparison: str = "gt"  # "gt" | "lt"
    severity: str = "warning"


class ThresholdAlertEngine:
    """しきい値超過を検出し、AlertSinkへ発火する。

    Final Phase検証項目: 「しきい値超過が発生した際、同一事象に対してアラートが
    重複なく1回だけ発報される(連続超過フレームの再発火抑制ロジックを含む)」ため、
    target+metric単位で「現在超過中かどうか」の状態を持ち、非超過→超過の遷移時のみ
    発火する(edge-trigger)。解消(超過→非超過)を検知したら状態をリセットし、
    再度超過したときにまた発火できるようにする。
    """

    def __init__(self, rules: list[ThresholdRule], sinks: list[AlertSink]) -> None:
        self._rules = rules
        self._sinks = sinks
        self._breaching: set[tuple[str, str]] = set()

    def check(self, target: str, metric: str, value: float, run_id: str = "") -> Optional[dict]:
        fired: Optional[dict] = None
        for rule in self._rules:
            if rule.target != target or rule.metric != metric:
                continue
            is_breach = value > rule.threshold if rule.comparison == "gt" else value < rule.threshold
            key = (target, metric)
            if is_breach and key not in self._breaching:
                self._breaching.add(key)
                alert = {
                    "target": target,
                    "metric": metric,
                    "value": value,
                    "threshold": rule.threshold,
                    "severity": rule.severity,
                    "timestamp_us": int(time.time() * 1_000_000),
                    "run_id": run_id,
                }
                for sink in self._sinks:
                    sink.emit(alert)
                fired = alert
            elif not is_breach and key in self._breaching:
                self._breaching.discard(key)
        return fired
