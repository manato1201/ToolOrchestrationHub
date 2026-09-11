"""hub/health/rpc_check.py

Sound Middleware Phase3で確定するハートビート/再接続契約を直接再利用する。
LoreDesktopAndWebSystem(QLocalSocket)・LearningQt・DynamicGIMiddlewareのRPC系についても
同じハートビート待受パターンを踏襲する。

ただしcategoryがobserved_onlyの対象へは能動的に接続を開始せず、
相手からのハートビート信号を受動的に監視するのみ(Hub側からRPC接続は一切開かない)。
"""

from __future__ import annotations

import time

from .base import HealthResult


def rpc_check(
    tool_id: str, last_heartbeat_at: float, heartbeat_interval_s: float
) -> HealthResult:
    """Sound Middleware Phase3のハートビート/再接続契約を踏襲する。

    Hub側から能動的にRPC接続を開くのではなく、各ツールが定期送出するハートビートの
    受信タイムスタンプが interval の2倍を超えて途絶していないかで生死判定する。
    """
    elapsed = time.monotonic() - last_heartbeat_at
    return HealthResult(is_up=elapsed < heartbeat_interval_s * 2, latency_ms=None)
