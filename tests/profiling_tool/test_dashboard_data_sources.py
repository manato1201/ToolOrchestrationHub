"""dashboard/data_sources.py のテスト。"""
from __future__ import annotations

import json

from profiling_tool.dashboard import data_sources
from profiling_tool.core import chrome_trace
from profiling_tool.core.recorder import TraceWriter


def test_list_runs_finds_files_newest_first(tmp_path):
    a = TraceWriter(target="vlm_auto_replay", run_id="run_a", traces_dir=tmp_path)
    a.append([chrome_trace.span("x", ts=0, dur=1)])
    import time

    time.sleep(0.02)
    b = TraceWriter(target="videofactory", run_id="run_b", traces_dir=tmp_path)
    b.append([chrome_trace.span("y", ts=0, dur=1)])

    runs = data_sources.list_runs(tmp_path)
    assert [r["run_id"] for r in runs] == ["run_b", "run_a"]
    assert runs[0]["target"] == "videofactory"
    assert runs[0]["size_bytes"] > 0


def test_list_runs_on_missing_directory_returns_empty(tmp_path):
    assert data_sources.list_runs(tmp_path / "does_not_exist") == []


def test_load_trace_events_round_trips(tmp_path):
    writer = TraceWriter(target="vlm_auto_replay", run_id="run001", traces_dir=tmp_path)
    writer.append([chrome_trace.span("step_0", ts=0, dur=100)])

    events = data_sources.load_trace_events("vlm_auto_replay", "run001", traces_dir=tmp_path)
    assert len(events) == 1
    assert events[0]["name"] == "step_0"


def test_latency_summary_and_usage_summary_are_disjoint():
    events = [
        chrome_trace.span("Narrate", ts=0, dur=100),
        chrome_trace.counter("active_voices", value=4, ts=0),
    ]
    latency = data_sources.latency_summary(events)
    usage = data_sources.usage_summary(events)

    assert "Narrate" in latency
    assert "Narrate" not in usage
    assert "active_voices" in usage
    assert "active_voices" not in latency


def test_captured_data_sample_returns_real_payload_values_unmasked():
    events = [
        chrome_trace.event("reasoning_trace", ts=0, payload={"reasoning": "実際の推論テキスト"}),
    ]
    sample = data_sources.captured_data_sample(events)
    assert sample[0]["payload"]["reasoning"] == "実際の推論テキスト"


def test_captured_data_sample_respects_limit_and_keeps_latest():
    events = [chrome_trace.event(f"e{i}", ts=i, payload={"i": i}) for i in range(10)]
    sample = data_sources.captured_data_sample(events, limit=3)
    assert [s["name"] for s in sample] == ["e7", "e8", "e9"]


def test_backend_info_reports_local_file_backends_no_database(tmp_path):
    traces_dir = tmp_path / "traces"
    checkpoint_dir = tmp_path / "checkpoints"
    traces_dir.mkdir()

    info = data_sources.backend_info(traces_dir=traces_dir, checkpoint_dir=checkpoint_dir)

    assert info["trace_store"]["exists"] is True
    assert info["checkpoint_store"]["exists"] is False
    assert "データベースは使用しない" in info["trace_store"]["kind"]


def test_read_alert_log_tail(tmp_path):
    log_path = tmp_path / "alerts.log"
    entries = [{"target": "x", "metric": "y", "value": i} for i in range(5)]
    log_path.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")

    tail = data_sources.read_alert_log_tail(log_path, limit=2)
    assert [e["value"] for e in tail] == [3, 4]


def test_read_alert_log_tail_missing_file_returns_empty(tmp_path):
    assert data_sources.read_alert_log_tail(tmp_path / "missing.log") == []
    assert data_sources.read_alert_log_tail(None) == []


def test_find_previous_run_returns_the_next_older_run_for_same_target(tmp_path):
    """使いやすさ改善「run間比較」: 同一target内でのみ直前runを探す(別targetは無視する)。"""
    import time

    TraceWriter(target="vlm_auto_replay", run_id="run_a", traces_dir=tmp_path).append(
        [chrome_trace.span("x", ts=0, dur=1)]
    )
    time.sleep(0.02)
    TraceWriter(target="videofactory", run_id="run_other", traces_dir=tmp_path).append(
        [chrome_trace.span("x", ts=0, dur=1)]
    )
    time.sleep(0.02)
    TraceWriter(target="vlm_auto_replay", run_id="run_b", traces_dir=tmp_path).append(
        [chrome_trace.span("x", ts=0, dur=1)]
    )

    runs = data_sources.list_runs(tmp_path)
    previous = data_sources.find_previous_run(runs, "vlm_auto_replay", "run_b")

    assert previous["run_id"] == "run_a"


def test_find_previous_run_returns_none_when_no_older_run_exists(tmp_path):
    TraceWriter(target="vlm_auto_replay", run_id="run_a", traces_dir=tmp_path).append(
        [chrome_trace.span("x", ts=0, dur=1)]
    )
    runs = data_sources.list_runs(tmp_path)
    assert data_sources.find_previous_run(runs, "vlm_auto_replay", "run_a") is None


def test_find_previous_run_returns_none_for_unknown_run_id(tmp_path):
    TraceWriter(target="vlm_auto_replay", run_id="run_a", traces_dir=tmp_path).append(
        [chrome_trace.span("x", ts=0, dur=1)]
    )
    runs = data_sources.list_runs(tmp_path)
    assert data_sources.find_previous_run(runs, "vlm_auto_replay", "does_not_exist") is None
