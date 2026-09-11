"""Phase1 検証チェックリスト: SpanGuardのネストと親子付け。"""
from __future__ import annotations

from profiling_tool.core.recorder import spans_to_events
from profiling_tool.core.span import SpanGuard, SpanRecorder


def test_span_guard_records_duration():
    recorder = SpanRecorder()
    with SpanGuard(recorder, "outer") as span:
        pass
    assert span.end_us >= span.start_us
    assert span.duration_us >= 0

    completed = recorder.drain()
    assert len(completed) == 1
    assert completed[0].name == "outer"


def test_span_guard_nesting_sets_correct_parent_child_relationship():
    """SpanGuardの入れ子(親span内で子SpanGuardを生成)が正しい親子関係を持つことを確認する。"""
    recorder = SpanRecorder()
    with SpanGuard(recorder, "parent") as parent_span:
        with SpanGuard(recorder, "child") as child_span:
            with SpanGuard(recorder, "grandchild") as grandchild_span:
                pass

    assert child_span.parent is parent_span
    assert grandchild_span.parent is child_span
    assert parent_span.parent is None

    completed = {s.name: s for s in recorder.drain()}
    assert len(completed) == 3
    # ネストは時間的にも入れ子(祖先のstart <= 子のstart, 子のend <= 祖先のend)であること
    assert completed["parent"].start_us <= completed["child"].start_us
    assert completed["child"].end_us <= completed["parent"].end_us


def test_span_guard_nesting_round_trips_through_chrome_trace_json():
    """出力JSON上で親子関係(タイムライン上の包含関係)が往復することを確認する
    (Final Phase「ネスト3階層のケース」)。
    """
    recorder = SpanRecorder()
    with SpanGuard(recorder, "a"):
        with SpanGuard(recorder, "b"):
            with SpanGuard(recorder, "c"):
                pass

    events = spans_to_events(recorder.drain())
    by_name = {e["name"]: e for e in events}
    assert len(events) == 3

    a, b, c = by_name["a"], by_name["b"], by_name["c"]
    assert a["ts"] <= b["ts"] <= c["ts"]
    assert (c["ts"] + c["dur"]) <= (b["ts"] + b["dur"]) <= (a["ts"] + a["dur"])


def test_span_recorder_is_thread_local_for_stack():
    """異なるスレッドのspanが互いの親子関係に影響しないことを確認する。"""
    import threading

    recorder = SpanRecorder()
    results = {}

    def worker(tid: str) -> None:
        with SpanGuard(recorder, f"{tid}_span") as span:
            results[tid] = span

    threads = [threading.Thread(target=worker, args=(f"t{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    for span in results.values():
        assert span.parent is None  # 各スレッドのトップレベルspanは互いに独立
