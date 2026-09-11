"""adapters/sound_adapter.py — Sound Middleware

DebugSnapshot{activeVoices, busGraph, memoryUsage, streamingQueueDepth, underrunCount}と
リアルタイムメーターストリームをCounterにマッピングする。Phase0のオーバーヘッド制約に
従い、コールバックスレッドでは値をリングバッファに積むだけとし、間引きサンプリング
(10ms間隔)してから別スレッドでflushする想定(実際のダウンサンプルはこのアダプタが
オフライン/別スレッドで行う)。underrunCountは間引かず全件イベント化する(発生頻度が
低く、かつ最も重要な信号のため)。

NOTE: ダウンサンプル判定(周期的なactive_voices/streaming_queue_depth)とunderrun検知は
独立させている。両方を同じ「間引き後のストリーム」に対して行うと、ダウンサンプルで
間引かれたスナップショットに含まれるunderrunイベントごと消えてしまい
「underrunCountは間引かない」という要件に反するため、underrunは元のストリーム全件を
対象に判定する。
"""
from __future__ import annotations

from typing import Iterator

from profiling_tool.core.chrome_trace import counter, event

DOWNSAMPLE_INTERVAL_MS = 10


def downsample(snapshot_stream: Iterator[dict], interval_ms: int) -> Iterator[dict]:
    """周期的なカウンタ値のみを対象にした間引き。underrun検知には使わない。"""
    last_emitted_ts = None
    for snapshot in snapshot_stream:
        ts = snapshot["timestamp"]
        if last_emitted_ts is None or (ts - last_emitted_ts) >= interval_ms * 1000:
            last_emitted_ts = ts
            yield snapshot


def to_trace(snapshot_stream: Iterator[dict]) -> Iterator[dict]:
    last_emitted_ts = None
    for snapshot in snapshot_stream:
        ts = snapshot["timestamp"]
        should_emit_counters = last_emitted_ts is None or (ts - last_emitted_ts) >= DOWNSAMPLE_INTERVAL_MS * 1000
        if should_emit_counters:
            last_emitted_ts = ts
            yield counter(name="active_voices", value=snapshot["activeVoices"], ts=ts)
            yield counter(name="streaming_queue_depth", value=snapshot["streamingQueueDepth"], ts=ts)
            yield counter(name="memory_usage_bytes", value=snapshot["memoryUsage"], ts=ts)
        if snapshot["underrunCount"] > 0:
            yield event(name="underrun", ts=ts, payload=snapshot)  # 間引かない(全件)
