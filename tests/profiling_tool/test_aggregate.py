"""Phase3/Final Phase 検証チェックリスト: aggregate.py。"""
from __future__ import annotations

import statistics

from profiling_tool.aggregate import counter_summary, percentile_by_span_name, summarize_trace
from profiling_tool.core import chrome_trace


def test_percentile_matches_hand_computed_value_on_known_distribution():
    """既知分布の合成データでp50/p95/p99が手計算値と一致することを確認する(Final Phase)。"""
    durations = list(range(1, 101))  # 1..100の一様分布
    traces = [chrome_trace.span("stage", ts=i, dur=d) for i, d in enumerate(durations)]

    p50 = percentile_by_span_name(traces, "stage", 0.50)
    p95 = percentile_by_span_name(traces, "stage", 0.95)
    p99 = percentile_by_span_name(traces, "stage", 0.99)

    sorted_durations = sorted(durations)
    assert p50 == sorted_durations[int(len(sorted_durations) * 0.50)]
    assert p95 == sorted_durations[int(len(sorted_durations) * 0.95)]
    assert p99 == sorted_durations[int(len(sorted_durations) * 0.99)]


def test_percentile_on_normal_distribution_is_close_to_expected_quantile():
    import random

    random.seed(42)
    durations = [max(1, int(random.gauss(100, 15))) for _ in range(5000)]
    traces = [chrome_trace.span("stage", ts=i, dur=d) for i, d in enumerate(durations)]

    p50 = percentile_by_span_name(traces, "stage", 0.50)
    expected_p50 = statistics.median(durations)
    assert abs(p50 - expected_p50) < 5  # サンプリング誤差の範囲


def test_percentile_raises_for_unknown_span_name():
    import pytest

    with pytest.raises(ValueError):
        percentile_by_span_name([chrome_trace.span("a", ts=0, dur=1)], "b", 0.5)


def test_counter_summary_reports_usage_statistics():
    """ユーザー追加要件「使用率や使用量の可視化」向けの統計値。"""
    traces = [chrome_trace.counter("active_voices", value=v, ts=i) for i, v in enumerate([2, 8, 4, 10, 6])]
    summary = counter_summary(traces, "active_voices")
    assert summary == {"count": 5, "min": 2, "max": 10, "avg": 6, "latest": 6}


def test_counter_summary_empty_for_missing_counter():
    summary = counter_summary([], "nonexistent")
    assert summary["count"] == 0
    assert summary["latest"] is None


def test_summarize_trace_covers_both_spans_and_counters_without_span_names_arg():
    traces = [
        chrome_trace.span("Narrate", ts=0, dur=100),
        chrome_trace.span("Narrate", ts=100, dur=200),
        chrome_trace.counter("active_voices", value=5, ts=0),
    ]
    summary = summarize_trace(traces)
    assert summary["spans"]["Narrate"]["count"] == 2
    assert summary["counters"]["active_voices"]["latest"] == 5
