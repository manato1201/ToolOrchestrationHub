"""Phase3/Final Phase 検証チェックリスト: aggregate.py。"""
from __future__ import annotations

import statistics

from profiling_tool.aggregate import (
    counter_summary,
    diff_counter_summary,
    diff_span_summary,
    percentile_by_span_name,
    summarize_trace,
)
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


def test_diff_span_summary_computes_delta_and_pct_change():
    """使いやすさ改善「run間比較」: p50/p95/p99/countが前runと比べてどう変化したか。"""
    current = {"Narrate": {"count": 10, "p50": 120, "p95": 200, "p99": 250}}
    previous = {"Narrate": {"count": 8, "p50": 100, "p95": 180, "p99": 240}}

    diff = diff_span_summary(current, previous)

    assert diff["Narrate"]["p50"] == {"current": 120, "previous": 100, "delta": 20, "pct_change": 20.0}
    assert diff["Narrate"]["count"]["delta"] == 2


def test_diff_span_summary_handles_span_missing_from_one_side():
    """前runに無かった新規spanや、今回消えたspanもNoneのまま両方に含める(隠さない)。"""
    current = {"NewStage": {"count": 3, "p50": 10, "p95": 20, "p99": 30}}
    previous = {"OldStage": {"count": 5, "p50": 40, "p95": 50, "p99": 60}}

    diff = diff_span_summary(current, previous)

    assert set(diff.keys()) == {"NewStage", "OldStage"}
    assert diff["NewStage"]["p50"] == {"current": 10, "previous": None, "delta": None, "pct_change": None}
    assert diff["OldStage"]["p50"] == {"current": None, "previous": 40, "delta": None, "pct_change": None}


def test_diff_counter_summary_computes_delta_for_avg_and_latest():
    current = {"active_voices": {"count": 5, "min": 2, "max": 10, "avg": 6.0, "latest": 8}}
    previous = {"active_voices": {"count": 5, "min": 1, "max": 9, "avg": 5.0, "latest": 4}}

    diff = diff_counter_summary(current, previous)

    assert diff["active_voices"]["avg"]["delta"] == 1.0
    assert diff["active_voices"]["latest"]["delta"] == 4


def test_diff_metric_does_not_divide_by_zero_previous():
    current = {"x": {"count": 1, "min": 0, "max": 0, "avg": 5.0, "latest": 5.0}}
    previous = {"x": {"count": 1, "min": 0, "max": 0, "avg": 0.0, "latest": 0.0}}

    diff = diff_counter_summary(current, previous)

    assert diff["x"]["avg"]["delta"] == 5.0
    assert diff["x"]["avg"]["pct_change"] is None  # 0からの変化率は定義しない(ZeroDivisionErrorにしない)
