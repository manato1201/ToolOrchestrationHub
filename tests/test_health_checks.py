"""Phase2 検証チェックリスト対応テスト。"""
from __future__ import annotations

import time

import httpx
import pytest

from hub.health import ci_pipeline_check, http_bridge_check, rpc_check
from hub.registry import ToolRegistry


@pytest.mark.asyncio
async def test_http_bridge_check_up_without_api_key_header(monkeypatch):
    """rag_local_bridge.pyの/healthはX-API-Keyなしで200を返す既存仕様と一致することを確認する。"""

    def handler(request: httpx.Request) -> httpx.Response:
        assert "x-api-key" not in {k.lower() for k in request.headers}
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient

    class PatchedClient(original_client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", PatchedClient)

    result = await http_bridge_check("http://127.0.0.1:8766/health")
    assert result.is_up is True
    assert result.latency_ms is not None


@pytest.mark.asyncio
async def test_http_bridge_check_down_on_request_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient

    class PatchedClient(original_client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", PatchedClient)

    result = await http_bridge_check("http://127.0.0.1:8766/health")
    assert result.is_up is False
    assert result.latency_ms is None


def test_rpc_check_detects_down_after_double_interval():
    heartbeat_interval_s = 10.0
    stale_heartbeat_at = time.monotonic() - (heartbeat_interval_s * 2 + 1)
    result = rpc_check("sound_middleware", stale_heartbeat_at, heartbeat_interval_s)
    assert result.is_up is False


def test_rpc_check_up_within_double_interval():
    heartbeat_interval_s = 10.0
    fresh_heartbeat_at = time.monotonic() - 1.0
    result = rpc_check("sound_middleware", fresh_heartbeat_at, heartbeat_interval_s)
    assert result.is_up is True


def test_ci_pipeline_check_uses_research_collector_actual_cron_interval():
    registry = ToolRegistry.load()
    entry = registry.get("research_collector")
    expected_interval_s = entry.check_params["expected_interval_s"]
    assert expected_interval_s == 21600  # 6時間おき

    grace_multiplier = entry.check_params["grace_multiplier"]
    just_within = time.monotonic() - (expected_interval_s * grace_multiplier - 1)
    just_over = time.monotonic() - (expected_interval_s * grace_multiplier + 1)

    assert ci_pipeline_check(just_within, expected_interval_s, grace_multiplier).is_up is True
    assert ci_pipeline_check(just_over, expected_interval_s, grace_multiplier).is_up is False
