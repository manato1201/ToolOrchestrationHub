"""profiling/span.py

Phase1: span — 区間計測(CPU)。開始・終了を持つ区間を、RAII相当のSpanGuard
(Pythonでは`with`文)でネスト計測する。子spanは親のthread_id内で自動的に
親子付けされる。
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional


def now_us() -> int:
    return time.perf_counter_ns() // 1000


@dataclass
class Span:
    name: str
    start_us: int
    end_us: int = 0  # 0の間は未終了
    thread_id: int = 0
    tags: dict = field(default_factory=dict)
    parent: Optional["Span"] = None

    @property
    def is_open(self) -> bool:
        return self.end_us == 0

    @property
    def duration_us(self) -> int:
        return max(0, self.end_us - self.start_us)


class SpanRecorder:
    """スレッド毎に開いているspanのスタックを持ち、SpanGuardの入れ子から
    親子関係を自動導出する。完了したspanはdrain()で取り出すまで内部に保持する。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._local = threading.local()
        self._completed: list[Span] = []

    def _stack(self) -> list[Span]:
        if not hasattr(self._local, "stack"):
            self._local.stack = []
        return self._local.stack

    def begin(self, name: str, tags: Optional[dict] = None, at_us: Optional[int] = None) -> Span:
        stack = self._stack()
        parent = stack[-1] if stack else None
        span = Span(
            name=name,
            start_us=at_us if at_us is not None else now_us(),
            thread_id=threading.get_ident(),
            tags=dict(tags or {}),
            parent=parent,
        )
        stack.append(span)
        return span

    def end(self, span: Span, at_us: Optional[int] = None) -> None:
        span.end_us = at_us if at_us is not None else now_us()
        stack = self._stack()
        if stack and stack[-1] is span:
            stack.pop()
        with self._lock:
            self._completed.append(span)

    def drain(self) -> list[Span]:
        """記録済みspanを取り出してクリアする(recorder.pyのflushから呼ぶ)。"""
        with self._lock:
            completed, self._completed = self._completed, []
        return completed


class SpanGuard:
    """RAII相当のネスト計測。`with SpanGuard(recorder, "name") as span:` で使う。
    子SpanGuardは親のスレッドローカルスタックにより自動的に親子付けされる。
    """

    __slots__ = ("_recorder", "_span")

    def __init__(self, recorder: SpanRecorder, name: str, tags: Optional[dict] = None) -> None:
        self._recorder = recorder
        self._span = recorder.begin(name, tags)

    def __enter__(self) -> Span:
        return self._span

    def __exit__(self, exc_type, exc, tb) -> None:
        self._recorder.end(self._span)
        return False
