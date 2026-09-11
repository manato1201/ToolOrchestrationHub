"""profiling/gpu_timestamp_query.py

Phase1: GpuTimestampQuery — GPUタイムスタンプクエリラッパー(CPU spanと明確に区別)。
CPU側のspanとGPU側のタイムスタンプは同一APIで扱わない。GPU計測は「発行」と
「結果取得」が非同期に分離するため、PIX/RenderDoc/Unity ProfilerMarkerのGPU
タイムスタンプクエリと同型の二段階(発行→ポーリング)モデルを名指しで前例として踏襲する。

実グラフィクスAPI(D3D12/Vulkan等)への接続はGpuBackend Protocolの実装差し替えで
行う想定。このワークスペースには実対象(DynamicGIMiddleware)がまだ存在しないため、
テスト・検証用にSimulatedGpuBackendを同梱する(Final Phase「合成プログラムでの検証」に対応)。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Protocol


def _now_us() -> int:
    return time.perf_counter_ns() // 1000


@dataclass(frozen=True)
class GpuSpan:
    name: str
    start_us: int
    end_us: int
    queue: str = "gpu"


class GpuBackend(Protocol):
    """実グラフィクスAPI側が実装するプロトコル。"""

    def issue_begin(self, label: str) -> int: ...

    def issue_end(self, handle: int) -> None: ...

    def poll(self, handle: int) -> Optional[tuple[int, int]]:
        """(start_us, end_us)。まだ結果が出ていなければNone(ここでブロックしない)。"""
        ...


class GpuTimestampQuery:
    def __init__(self, backend: GpuBackend) -> None:
        self._backend = backend
        self._pending: dict[int, str] = {}

    def begin(self, label: str) -> int:
        """タイムスタンプクエリを発行する(コマンドリスト発行のみで即時ブロックしない)。"""
        handle = self._backend.issue_begin(label)
        self._pending[handle] = label
        return handle

    def end(self, handle: int) -> None:
        self._backend.issue_end(handle)

    def try_resolve(self, handle: int) -> Optional[GpuSpan]:
        """数フレーム後にポーリングで結果取得。まだなければNone(CPU側でブロックしない)。"""
        label = self._pending.get(handle)
        if label is None:
            return None
        result = self._backend.poll(handle)
        if result is None:
            return None
        start_us, end_us = result
        del self._pending[handle]
        return GpuSpan(name=label, start_us=start_us, end_us=end_us)


class SimulatedGpuBackend:
    """テスト/検証用のGPUバックエンド。issue_beginから指定回数pollされた後に
    結果を返すことで、実バックエンドの非同期性(即時解決しない)を模倣する。
    """

    def __init__(self, resolve_after_polls: int = 2) -> None:
        self._resolve_after_polls = resolve_after_polls
        self._next_handle = 1
        self._issued: dict[int, dict] = {}

    def issue_begin(self, label: str) -> int:
        handle = self._next_handle
        self._next_handle += 1
        self._issued[handle] = {"label": label, "polls": 0, "start_us": _now_us(), "end_us": None}
        return handle

    def issue_end(self, handle: int) -> None:
        self._issued[handle]["end_us"] = _now_us()

    def poll(self, handle: int) -> Optional[tuple[int, int]]:
        entry = self._issued.get(handle)
        if entry is None or entry["end_us"] is None:
            return None
        entry["polls"] += 1
        if entry["polls"] < self._resolve_after_polls:
            return None
        del self._issued[handle]
        return entry["start_us"], entry["end_us"]
