"""Phase1/Final Phase 検証チェックリスト: Counter.record()の非機能要件。"""
from __future__ import annotations

import gc
import threading
import time

from profiling_tool.core.counter import Counter


def test_record_and_flush_round_trip():
    counter = Counter("active_voices", capacity=16)
    counter.record(1.0, 100)
    counter.record(2.0, 200)

    samples = counter.flush()
    assert [(s.value, s.timestamp_us) for s in samples] == [(1.0, 100), (2.0, 200)]
    # flush後は同じサンプルを再度返さない
    assert counter.flush() == []


def test_flush_drops_oldest_samples_when_ring_overruns_capacity():
    counter = Counter("x", capacity=4)
    for i in range(6):
        counter.record(float(i), i)
    samples = counter.flush()
    # capacity=4のリングを6件書いたので、最新4件のみ残る
    assert [s.value for s in samples] == [2.0, 3.0, 4.0, 5.0]


def test_record_allocates_no_new_objects():
    """Sound Middleware非機能要件: record()がヒープアロケーションを行わないことを
    (Pythonで完全に検証はできないため)gcの世代0カウントで近似的に確認する。
    record()呼び出し前後でオブジェクト生成が実質ゼロであることを見る。
    """
    counter = Counter("voice_count", capacity=1024)
    counter.record(0.0, 0)  # ウォームアップ

    gc.collect()
    before = len(gc.get_objects())
    for i in range(1000):
        counter.record(float(i), i)
    after = len(gc.get_objects())

    # record()自体は新規オブジェクトを一切作らない設計のため、1000回呼んでも
    # 生存オブジェクト数はほぼ増えない(多少のインタプリタ内部揺れのみ許容する)
    assert after - before < 50


def test_record_does_not_acquire_a_lock():
    """record()が明示的なLockを取得しないこと(=別スレッドのflush()と衝突してブロックしないこと)を、
    タイムアウト付きで別スレッドから同時に呼び出して確認する。
    """
    counter = Counter("x", capacity=256)
    stop = threading.Event()

    def writer():
        while not stop.is_set():
            counter.record(1.0, 0)

    t = threading.Thread(target=writer, daemon=True)
    t.start()
    try:
        start = time.perf_counter()
        for _ in range(100):
            counter.flush()
        elapsed = time.perf_counter() - start
        # writer()が休みなくrecord()し続けていても、flush()が明示ロック待ちで
        # 長時間ブロックされないこと(数秒未満で完了する)
        assert elapsed < 2.0
    finally:
        stop.set()
        t.join()
