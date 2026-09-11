"""profiling/event.py

Phase1: event — 構造化ログ1件。対象側のスキーマ(例: VLMのStepLog)をそのまま
json_payloadとして格納する。コアは対象のフィールド名を一切知らない。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StructuredEvent:
    name: str
    timestamp_us: int
    json_payload: str

    @classmethod
    def from_payload(
        cls, name: str, timestamp_us: int, payload: dict[str, Any]
    ) -> "StructuredEvent":
        return cls(
            name=name,
            timestamp_us=timestamp_us,
            json_payload=json.dumps(payload, ensure_ascii=False),
        )

    def payload(self) -> dict[str, Any]:
        return json.loads(self.json_payload)
