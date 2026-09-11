"""hub/health/http_bridge_check.py

DevelopmentRAGEnvironmentの`rag_local_bridge.py`が既に持つ未認証`/health`エンドポイントを
直接再利用する。新規エンドポイントの追加要求は行わない。
"""

from __future__ import annotations

import time

import httpx

from .base import HealthResult


async def http_bridge_check(endpoint: str, timeout_s: float = 3.0) -> HealthResult:
    """rag_local_bridge.pyの/health等、未認証で公開済みの/healthをそのまま叩く。

    X-API-Keyヘッダは/health自体には不要
    (rag_local_bridge.py `_require_auth()` の除外対象と同じ前提)。

    レイテンシは`httpx.Response.elapsed`ではなく自前でmonotonic計測する。
    `elapsed`はレスポンスがtiming拡張を持つ場合のみ有効で、MockTransport等では
    未設定のままRuntimeErrorになるため。
    """
    started_at = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.get(endpoint)
            latency_ms = (time.monotonic() - started_at) * 1000
            return HealthResult(is_up=resp.status_code == 200, latency_ms=latency_ms)
    except httpx.RequestError:
        return HealthResult(is_up=False, latency_ms=None)
