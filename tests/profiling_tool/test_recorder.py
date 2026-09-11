"""Phase3 検証チェックリスト: 追記専用トレースストア。"""
from __future__ import annotations

from profiling_tool.core import chrome_trace
from profiling_tool.core.recorder import TraceWriter


def test_append_creates_file_under_target_run_id_path(tmp_path):
    writer = TraceWriter(target="videofactory", run_id="run001", traces_dir=tmp_path)
    writer.append([chrome_trace.span("Narrate", ts=0, dur=100)])

    assert writer.path == tmp_path / "videofactory" / "run001.json"
    assert writer.path.exists()


def test_second_write_to_same_run_id_appends_rather_than_overwrites(tmp_path):
    writer = TraceWriter(target="videofactory", run_id="run001", traces_dir=tmp_path)
    writer.append([chrome_trace.span("Narrate", ts=0, dur=100)])
    writer.append([chrome_trace.span("AssembleAndRender", ts=100, dur=200)])

    events = writer.read_events()
    assert [e["name"] for e in events] == ["Narrate", "AssembleAndRender"]


def test_different_run_ids_are_independent_files(tmp_path):
    a = TraceWriter(target="vlm", run_id="runA", traces_dir=tmp_path)
    b = TraceWriter(target="vlm", run_id="runB", traces_dir=tmp_path)
    a.append([chrome_trace.span("a", ts=0, dur=1)])
    b.append([chrome_trace.span("b", ts=0, dur=1)])

    assert [e["name"] for e in a.read_events()] == ["a"]
    assert [e["name"] for e in b.read_events()] == ["b"]


def test_append_with_no_events_does_not_touch_existing_file(tmp_path):
    writer = TraceWriter(target="vlm", run_id="run001", traces_dir=tmp_path)
    writer.append([chrome_trace.span("a", ts=0, dur=1)])
    before = writer.path.read_text(encoding="utf-8")

    writer.append([])

    assert writer.path.read_text(encoding="utf-8") == before
