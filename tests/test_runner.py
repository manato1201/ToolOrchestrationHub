"""hub/health/runner.py の非機能要件・アンチパターン対応テスト。"""
from __future__ import annotations

import time

import pytest

from hub.health.runner import LivenessMonitor
from hub.registry import ToolCategory, ToolRegistry


@pytest.mark.asyncio
async def test_excluded_tool_is_never_checked():
    registry = ToolRegistry.load()
    monitor = LivenessMonitor(registry)
    entry = registry.get("color_encyclopedia")
    result = await monitor.check_once(entry)
    assert result is None
    assert monitor.last_result("color_encyclopedia") is None


@pytest.mark.asyncio
async def test_observed_only_rpc_tool_never_opens_active_connection(monkeypatch):
    """observed_onlyのSoundMiddlewareに対し、Hubがhttpxクライアント等の能動接続を
    1件も開始しないことを確認する(Phase1/Phase2検証チェックリスト)。
    """
    import httpx

    called = {"count": 0}
    original_init = httpx.AsyncClient.__init__

    def spy_init(self, *args, **kwargs):
        called["count"] += 1
        return original_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", spy_init)

    registry = ToolRegistry.load()
    monitor = LivenessMonitor(registry)
    entry = registry.get("sound_middleware")
    monitor.record_heartbeat("sound_middleware")

    result = await monitor.check_once(entry)

    assert result is not None
    assert called["count"] == 0


@pytest.mark.asyncio
async def test_no_active_connection_for_any_observed_only_or_excluded_tool(monkeypatch):
    """Final Phase統合検証: 「category: observed_only/excludedのツール
    (LoreDesktopAndWebSystem・LearningQt・SoundMiddleware・ColorEncyclopedia等)に対して
    Hubが能動的な接続・介入を一切行っていないこと」を、registry.yamlの該当エントリ
    全件について確認する(1件だけの抜き取りではなく)。
    """
    import httpx

    called = {"count": 0}
    original_init = httpx.AsyncClient.__init__

    def spy_init(self, *args, **kwargs):
        called["count"] += 1
        return original_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", spy_init)

    registry = ToolRegistry.load()
    monitor = LivenessMonitor(registry)

    non_monitored = [
        e
        for e in registry.all()
        if e.category in (ToolCategory.OBSERVED_ONLY, ToolCategory.EXCLUDED)
    ]
    # registry.yamlの12エントリのうち該当は6件(observed_only 5件 + excluded 1件)。
    # 対象が空のまま「呼ばれなかった」だけでテストが空虚に通ってしまわないことを保証する。
    assert len(non_monitored) == 6

    for entry in non_monitored:
        if entry.health_check == "rpc_check":
            monitor.record_heartbeat(entry.tool_id)
        await monitor.check_once(entry)

    assert called["count"] == 0


@pytest.mark.asyncio
async def test_all_monitored_entries_enforce_poll_interval_floor(monkeypatch):
    """Final Phase統合検証: 「各ツール自身のヘルスチェック/cron間隔より高頻度でHubが
    ポーリングしていないこと」を、monitoredな全エントリについて確認する。

    poll_interval_sが未設定だとLivenessMonitor側のレート制限自体が効かないため、
    まずそれが全monitoredエントリに設定されていることを前提として検証する。
    http_bridge_check対象は実ネットワークに触れないようモックする(存在しない
    127.0.0.1:8766/8767への接続試行に依存させない)。
    """
    from hub.health.base import HealthResult

    async def fake_http_bridge_check(endpoint, timeout_s=3.0):
        return HealthResult(is_up=True, latency_ms=1.0)

    monkeypatch.setattr("hub.health.runner.http_bridge_check", fake_http_bridge_check)

    registry = ToolRegistry.load()
    monitor = LivenessMonitor(registry)

    monitored = registry.monitored()
    assert len(monitored) > 0

    for entry in monitored:
        assert entry.poll_interval_s is not None and entry.poll_interval_s > 0, (
            f"{entry.tool_id} はmonitoredだがpoll_interval_sが未設定/0であり、"
            "非hot-path原則を実装レベルで守れない"
        )

        now = time.monotonic()
        await monitor.check_once(entry, now=now)
        polled_at = monitor._last_polled_at.get(entry.tool_id)
        if polled_at is None:
            continue
        # poll_interval_s未満の経過では、内部の最終ポーリング時刻が更新されない
        # (=再チェックが発生しない)ことを確認する。
        await monitor.check_once(entry, now=now + entry.poll_interval_s / 2)
        assert monitor._last_polled_at[entry.tool_id] == polled_at


@pytest.mark.asyncio
async def test_monitored_tool_polling_respects_poll_interval_floor(monkeypatch):
    """非hot-path原則: registry.yamlのpoll_interval_sより高頻度に能動チェックを
    発生させないことを確認する。
    """
    from hub.health.base import HealthResult

    call_count = {"n": 0}

    async def fake_http_bridge_check(endpoint, timeout_s=3.0):
        call_count["n"] += 1
        return HealthResult(is_up=True, latency_ms=1.0)

    monkeypatch.setattr("hub.health.runner.http_bridge_check", fake_http_bridge_check)

    registry = ToolRegistry.load()
    monitor = LivenessMonitor(registry)
    entry = registry.get("dev_rag_environment")
    assert entry.poll_interval_s == 60

    now = time.monotonic()
    await monitor.check_once(entry, now=now)
    await monitor.check_once(entry, now=now + 1)  # poll_interval_s未満 -> 再チェックしない
    await monitor.check_once(entry, now=now + entry.poll_interval_s + 1)  # 経過後は再チェックする

    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_ci_pipeline_tool_is_unknown_until_first_ci_success_recorded():
    """起動直後、まだrecord_ci_successを一度も受け取っていないmonitoredツールを
    「up」と誤判定しない(nowをlast_success_atのフォールバックにしない)ことを確認する。
    """
    registry = ToolRegistry.load()
    monitor = LivenessMonitor(registry)
    entry = registry.get("research_collector")

    result = await monitor.check_once(entry)
    assert result is None
    assert monitor.last_result("research_collector") is None

    monitor.record_ci_success("research_collector")
    result = await monitor.check_once(entry, now=time.monotonic() + entry.poll_interval_s + 1)
    assert result is not None
    assert result.is_up is True


@pytest.mark.asyncio
async def test_observed_only_rpc_tool_is_unknown_until_first_heartbeat_recorded():
    """observed_onlyのツールも同様に、ハートビートを一度も受信していない間は
    「up」と誤判定せずNone(未取得)を返すことを確認する。
    """
    registry = ToolRegistry.load()
    monitor = LivenessMonitor(registry)
    entry = registry.get("sound_middleware")

    result = await monitor.check_once(entry)
    assert result is None

    monitor.record_heartbeat("sound_middleware")
    result = await monitor.check_once(entry)
    assert result is not None
    assert result.is_up is True
