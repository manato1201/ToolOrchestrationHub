"""Phase2/Final Phase 検証チェックリスト: videofactory_adapter。"""
from __future__ import annotations

from profiling_tool.adapters.checkpoint import CheckpointStore
from profiling_tool.adapters.videofactory_adapter import to_trace, to_trace_incremental

MANIFEST = {
    "pipeline": [
        {"stage": "Narrate", "label": "narration", "status": "success", "duration_sec": 12.5},
        {"stage": "AssembleAndRender", "label": "assemble", "status": "success", "duration_sec": 42.0},
        {"stage": "Encode", "label": "encode", "status": "skipped", "duration_sec": 0},
    ]
}


def test_to_trace_does_not_mutate_input_manifest():
    """既存manifest.jsonサンプルを1行も書き換えずに読み取り専用で処理できることを確認する。"""
    import copy

    original = copy.deepcopy(MANIFEST)
    to_trace(MANIFEST, run_id="run001")
    assert MANIFEST == original


def test_to_trace_produces_non_overlapping_sequential_spans():
    """GPU厳密逐次リース(Narrate→AssembleAndRender→Encode)の非重複性が、
    span列がタイムライン上で重ならないことで表れることを確認する(Final Phase)。
    """
    spans = to_trace(MANIFEST, run_id="run001")
    assert [s["name"] for s in spans] == ["Narrate", "AssembleAndRender", "Encode"]

    for prev, cur in zip(spans, spans[1:]):
        prev_end = prev["ts"] + prev["dur"]
        assert prev_end <= cur["ts"]  # 前段の終了 <= 後段の開始(重ならない)


def test_zero_duration_entry_produces_zero_width_span_not_omitted():
    """duration_sec=0のエントリ(未計測・スキップ)はゼロ幅spanとして出力し、欠測を隠さない。"""
    spans = to_trace(MANIFEST, run_id="run001")
    encode_span = next(s for s in spans if s["name"] == "Encode")
    assert encode_span["dur"] == 0
    assert encode_span["args"]["status"] == "skipped"


def test_to_trace_incremental_processes_only_new_pipeline_entries(tmp_path):
    store = CheckpointStore(tmp_path)

    partial_manifest = {"pipeline": MANIFEST["pipeline"][:1]}
    first_batch = to_trace_incremental(partial_manifest, run_id="run001", checkpoint_store=store)
    assert [s["name"] for s in first_batch] == ["Narrate"]

    # 同じmanifestを再度渡しても差分は無い
    assert to_trace_incremental(partial_manifest, run_id="run001", checkpoint_store=store) == []

    # pipelineが増分した(ジョブが進んだ)ことを模す
    full_batch = to_trace_incremental(MANIFEST, run_id="run001", checkpoint_store=store)
    assert [s["name"] for s in full_batch] == ["AssembleAndRender", "Encode"]
    # 新規分のtsは、既に処理済みのNarrateの直後から始まる
    assert full_batch[0]["ts"] == int(MANIFEST["pipeline"][0]["duration_sec"] * 1_000_000)
