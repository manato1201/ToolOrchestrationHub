"""profiling/counter.py

Phase1: counter — 数値ゲージの時系列。

非機能要件(Phase0、唯一の「絶対」制約): Sound Middlewareのオーディオコールバック
スレッドから呼ばれるrecord()は、ロック取得・メモリ確保を行わないこと。

Pythonでは真の意味でのロックフリー/アロケーションフリーは実現できないが、その
精神を可能な限り踏襲する:
- record()は固定長の事前確保済みリングバッファへの単純代入のみを行う
  (新規オブジェクト生成・list.append等の再確保を伴う操作をしない)
- 単一プロデューサ(コールバックスレッド)/単一コンシューマ(flushする側)を前提に、
  record()側からは明示的なLock取得を行わない
flush()は必ずコールバックスレッド外で呼ぶこと(record()と同時に走らせない)。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CounterSample:
    value: float
    timestamp_us: int


class Counter:
    def __init__(self, name: str, capacity: int = 4096) -> None:
        self.name = name
        self._capacity = capacity
        self._values = [0.0] * capacity
        self._timestamps = [0] * capacity
        self._write_index = 0
        self._read_index = 0

    def record(self, value: float, timestamp_us: int) -> None:
        """コールバックスレッドから呼んでよい唯一のメソッド。

        新規オブジェクト生成・ロック取得を一切行わない。
        """
        idx = self._write_index % self._capacity
        self._values[idx] = value
        self._timestamps[idx] = timestamp_us
        self._write_index += 1

    def flush(self) -> list[CounterSample]:
        """コールバックスレッド外で呼ぶこと。未読み出し分をリストとして取り出す。

        flushが遅れてリングを一周されていた場合、古いサンプルは失われている
        (リングバッファである以上、無限に保持はできない)。
        """
        available = self._write_index - self._read_index
        if available > self._capacity:
            self._read_index = self._write_index - self._capacity
            available = self._capacity
        samples = []
        for i in range(available):
            idx = (self._read_index + i) % self._capacity
            samples.append(
                CounterSample(
                    value=self._values[idx], timestamp_us=self._timestamps[idx]
                )
            )
        self._read_index += available
        return samples
