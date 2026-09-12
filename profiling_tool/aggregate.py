"""aggregate.py

Phase3: 集計はJSON→JSONの純関数として実装し、可視化層(dashboard/)から独立して
単体テストできる状態に保つ(AssetDataInsightSuite Phase3と同一の
「計算とレンダリングの分離」原則を踏襲)。

ユーザー追加要件「使用率や使用量の可視化」向けに、counter_summary()を追加している
(p50/p95/p99に加えて、ph:"C"カウンタの min/max/avg/最新値を返す)。
"""
from __future__ import annotations

from typing import Optional


def percentile_by_span_name(traces: list[dict], span_name: str, p: float) -> float:
    durations = sorted(t["dur"] for t in traces if t.get("ph") == "X" and t["name"] == span_name)
    if not durations:
        raise ValueError(f"span_name={span_name!r} に該当するspanイベントがありません")
    idx = min(int(len(durations) * p), len(durations) - 1)
    return durations[idx]


def counter_summary(traces: list[dict], counter_name: str) -> dict:
    """使用率・使用量の可視化向けの基本統計。ph:"C"のイベントのみを対象に
    件数・最小・最大・平均・最新値を返す。該当が無ければcount=0の空サマリを返す
    (例外にしない。ダッシュボード側が存在しないカウンタを気軽に問い合わせられるように)。
    """
    values = [t["args"]["value"] for t in traces if t.get("ph") == "C" and t["name"] == counter_name]
    if not values:
        return {"count": 0, "min": None, "max": None, "avg": None, "latest": None}
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "avg": sum(values) / len(values),
        "latest": values[-1],
    }


def list_span_names(traces: list[dict]) -> list[str]:
    seen: dict[str, None] = {}
    for t in traces:
        if t.get("ph") == "X":
            seen.setdefault(t["name"], None)
    return list(seen.keys())


def list_counter_names(traces: list[dict]) -> list[str]:
    seen: dict[str, None] = {}
    for t in traces:
        if t.get("ph") == "C":
            seen.setdefault(t["name"], None)
    return list(seen.keys())


def summarize_trace(traces: list[dict], span_names: Optional[list[str]] = None, counter_names: Optional[list[str]] = None) -> dict:
    """runId単位のsummary.json生成。省略時はトレース内に登場する全span/counter名を対象にする。"""
    span_names = span_names if span_names is not None else list_span_names(traces)
    counter_names = counter_names if counter_names is not None else list_counter_names(traces)

    summary: dict = {"spans": {}, "counters": {}}
    for name in span_names:
        matching = [t for t in traces if t.get("ph") == "X" and t["name"] == name]
        if not matching:
            continue
        summary["spans"][name] = {
            "count": len(matching),
            "p50": percentile_by_span_name(traces, name, 0.50),
            "p95": percentile_by_span_name(traces, name, 0.95),
            "p99": percentile_by_span_name(traces, name, 0.99),
        }
    for name in counter_names:
        summary["counters"][name] = counter_summary(traces, name)
    return summary


def _diff_metric(current: Optional[float], previous: Optional[float]) -> dict:
    """使いやすさ改善「run間比較」向け。1指標分のcurrent/previous/delta/pct_changeを返す。

    どちらかがNone(該当run側にそのspan/counterが存在しない)ならdelta/pct_changeは
    Noneのままにする(比較不能を「0」として偽装しない)。
    """
    delta = current - previous if current is not None and previous is not None else None
    pct_change = (
        (delta / previous * 100.0) if delta is not None and previous not in (None, 0) else None
    )
    return {"current": current, "previous": previous, "delta": delta, "pct_change": pct_change}


def diff_span_summary(current: dict, previous: dict) -> dict:
    """summarize_trace()の"spans"パート同士を比較する(p50/p95/p99/countの前run比)。

    どちらかのrunにしか登場しないspan名も両方の一覧に含め、無い側はNone扱いにする
    (「消えたspan」「新規に増えたspan」もそのまま見えるようにする)。
    """
    names = sorted(set(current) | set(previous))
    result: dict = {}
    for name in names:
        cur = current.get(name, {})
        prev = previous.get(name, {})
        result[name] = {
            key: _diff_metric(cur.get(key), prev.get(key))
            for key in ("count", "p50", "p95", "p99")
        }
    return result


def diff_counter_summary(current: dict, previous: dict) -> dict:
    """summarize_trace()の"counters"パート同士を比較する(min/max/avg/latest/countの前run比)。"""
    names = sorted(set(current) | set(previous))
    result: dict = {}
    for name in names:
        cur = current.get(name, {})
        prev = previous.get(name, {})
        result[name] = {
            key: _diff_metric(cur.get(key), prev.get(key))
            for key in ("count", "min", "max", "avg", "latest")
        }
    return result
