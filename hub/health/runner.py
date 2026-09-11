"""hub/health/runner.py

Phase2の3種のヘルスチェック関数(http_bridge_check/rpc_check/ci_pipeline_check)を
Registryの`ToolEntry`に紐づけて定期実行し、liveness状態を保持するランナー。

非機能要件「ヘルスチェックのポーリング頻度は各ツール自身のヘルスチェック間隔より
高頻度にしない」を`ToolEntry.poll_interval_s`で具体化する。

category別の扱い:
- monitored     : `poll_interval_s`でレート制限した能動チェック(http_bridge_check/ci_pipeline_check)
- observed_only : 能動的な接続は一切開かない。rpc_checkのみ、他ツールから届いた
                  ハートビート受信タイムスタンプ(record_heartbeat)に対する純粋な計算として評価する
- excluded      : 一切チェックしない
"""
from __future__ import annotations

import time
from typing import Optional

from ..registry import ToolCategory, ToolEntry, ToolRegistry
from .base import HealthResult
from .ci_pipeline_check import ci_pipeline_check
from .http_bridge_check import http_bridge_check
from .rpc_check import rpc_check


class LivenessMonitor:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry
        self._heartbeats: dict[str, float] = {}
        self._ci_success: dict[str, float] = {}
        self._last_polled_at: dict[str, float] = {}
        self._results: dict[str, HealthResult] = {}

    def record_heartbeat(self, tool_id: str, at: Optional[float] = None) -> None:
        """rpc系ツールから届いたハートビートの受信を記録する(受動監視。接続は開かない)。"""
        self._heartbeats[tool_id] = at if at is not None else time.monotonic()

    def record_ci_success(self, tool_id: str, at: Optional[float] = None) -> None:
        """CI/cronの最終成功run通知を記録する。"""
        self._ci_success[tool_id] = at if at is not None else time.monotonic()

    def last_result(self, tool_id: str) -> Optional[HealthResult]:
        return self._results.get(tool_id)

    async def check_once(self, entry: ToolEntry, *, now: Optional[float] = None) -> Optional[HealthResult]:
        """1ツール分のliveness評価を行う。categoryに応じて能動/受動/スキップを切り替える。"""
        now = now if now is not None else time.monotonic()

        if entry.category is ToolCategory.EXCLUDED:
            return None
        if entry.health_check is None:
            return None

        if entry.category is ToolCategory.OBSERVED_ONLY:
            # 受動監視のみ。record_heartbeatで既に受信済みのタイムスタンプに対する
            # ローカル計算であり、対象ツールへの能動的な接続は一切発生しない。
            if entry.health_check != "rpc_check":
                return None
            result = self._eval_rpc_check(entry, now)
            if result is not None:
                self._results[entry.tool_id] = result
            return result

        # category is monitored: 能動チェック。poll_interval_sでレート制限する。
        last_polled = self._last_polled_at.get(entry.tool_id)
        if entry.poll_interval_s is not None and last_polled is not None:
            if now - last_polled < entry.poll_interval_s:
                return self._results.get(entry.tool_id)

        result = await self._dispatch_active(entry, now)
        self._last_polled_at[entry.tool_id] = now
        if result is not None:
            self._results[entry.tool_id] = result
        return result

    async def _dispatch_active(self, entry: ToolEntry, now: float) -> Optional[HealthResult]:
        if entry.health_check == "http_bridge_check":
            # 能動的にHTTPを叩く実測なので、シグナル有無に関わらず常に確定した結果が得られる。
            timeout_s = entry.check_params.get("timeout_s", 3.0)
            return await http_bridge_check(entry.endpoint, timeout_s=timeout_s)
        if entry.health_check == "ci_pipeline_check":
            if entry.tool_id not in self._ci_success:
                # まだ一度もCI成功通知(record_ci_success)を受け取っていない。
                # ここでnowをlast_success_atの代わりに使うと「起動直後は常にup」という
                # 誤った判定になるため、判定不能(未取得のまま)としてNoneを返す。
                return None
            expected_interval_s = entry.check_params.get(
                "expected_interval_s", entry.poll_interval_s or 86400.0
            )
            grace_multiplier = entry.check_params.get("grace_multiplier", 1.5)
            last_success_at = self._ci_success[entry.tool_id]
            return ci_pipeline_check(last_success_at, expected_interval_s, grace_multiplier)
        if entry.health_check == "rpc_check":
            return self._eval_rpc_check(entry, now)
        raise ValueError(f"未知のhealth_checkです: {entry.health_check}")

    def _eval_rpc_check(self, entry: ToolEntry, now: float) -> Optional[HealthResult]:
        if entry.tool_id not in self._heartbeats:
            # まだ一度もハートビートを受信していない。ci_pipeline_check同様、
            # nowにフォールバックして「起動直後は常にup」と誤判定しないようNoneを返す。
            return None
        heartbeat_interval_s = entry.check_params.get("heartbeat_interval_s", 10.0)
        last_heartbeat_at = self._heartbeats[entry.tool_id]
        return rpc_check(entry.tool_id, last_heartbeat_at, heartbeat_interval_s)

    async def check_all(self) -> dict[str, HealthResult]:
        """excluded以外の全エントリを評価する(monitoredは能動・observed_onlyは受動)。"""
        now = time.monotonic()
        results: dict[str, HealthResult] = {}
        for entry in self._registry.all():
            r = await self.check_once(entry, now=now)
            if r is not None:
                results[entry.tool_id] = r
        return results
