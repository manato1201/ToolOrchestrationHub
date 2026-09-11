"""hub/health/ci_pipeline_check.py

The-Algorithm-Illustrated、Research-Collector、AssetDataInsightSuite、
Visual Regression QA Toolなど、CI/CD cronベースのツール向け。
「最終成功runからの経過時間」のみを見る(それ以上の詳細判定はCI側の責務としてHubは持ち込まない)。
"""
from __future__ import annotations

import time

from .base import HealthResult


def ci_pipeline_check(
    last_success_at: float, expected_interval_s: float, grace_multiplier: float = 1.5
) -> HealthResult:
    """CI最終成功runからの経過時間のみで判定する。Runログの内容解析はしない。"""
    elapsed = time.monotonic() - last_success_at
    return HealthResult(is_up=elapsed < expected_interval_s * grace_multiplier, latency_ms=None)
