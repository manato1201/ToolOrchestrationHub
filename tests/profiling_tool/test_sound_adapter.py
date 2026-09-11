"""Phase2 検証チェックリスト: sound_adapter。

「コールバックスレッド外でのみdownsample/flushを実行する」というスレッドアフィニティ
要件自体は、sound_adapter.to_trace()がオフライン(コールバックスレッド外)で
DebugSnapshotのストリームを処理するジェネレータであり、record()相当のホット
パス(Counter.record())とは別モジュール(tests/test_counter.py)で検証済みのため、
ここではダウンサンプル/underrun非間引きの振る舞いを検証する。
"""

from __future__ import annotations

from profiling_tool.adapters.sound_adapter import DOWNSAMPLE_INTERVAL_MS, to_trace


def _snapshot(ts_ms: int, underrun: int = 0) -> dict:
    return {
        "activeVoices": 12,
        "busGraph": {"master": {"gain": 1.0}},
        "memoryUsage": 1024 * 1024,
        "streamingQueueDepth": 3,
        "underrunCount": underrun,
        "timestamp": ts_ms * 1000,
    }


def test_counters_are_downsampled_to_interval():
    # 1msおきに20件 -> DOWNSAMPLE_INTERVAL_MS(10ms)間隔なので2-3件程度に間引かれる
    stream = (_snapshot(ts) for ts in range(0, 20))
    events = list(to_trace(stream))

    counter_events = [
        e for e in events if e["ph"] == "C" and e["name"] == "active_voices"
    ]
    assert len(counter_events) <= 3
    assert len(counter_events) >= 1


def test_underrun_is_never_downsampled_even_between_ticks():
    """underrunCountは間引かず全件イベント化する(Phase2 sound_adapter要件)。
    ダウンサンプルのtickに乗らないタイミングのunderrunも取りこぼさないことを確認する。
    """
    stream = []
    for ts_ms in range(0, 30):
        # DOWNSAMPLE_INTERVAL_MS間隔の"谷"にあたるタイミングでunderrunを発生させる
        underrun = (
            1 if ts_ms % DOWNSAMPLE_INTERVAL_MS == (DOWNSAMPLE_INTERVAL_MS // 2) else 0
        )
        stream.append(_snapshot(ts_ms, underrun=underrun))

    events = list(to_trace(iter(stream)))
    underrun_events = [e for e in events if e["name"] == "underrun"]

    # 30msの間に3回underrunが発生する想定(ts=5,15,25)なので、全件拾えていること
    assert len(underrun_events) == 3


def test_no_underrun_events_when_underrun_count_is_zero():
    stream = (_snapshot(ts) for ts in range(0, 5))
    events = list(to_trace(stream))
    assert not any(e["name"] == "underrun" for e in events)
