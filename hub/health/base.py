"""3種のヘルスチェック(http_bridge_check/rpc_check/ci_pipeline_check)が共通で返す型。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class HealthResult:
    is_up: bool
    latency_ms: Optional[float] = None
