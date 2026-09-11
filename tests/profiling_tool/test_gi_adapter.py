"""Phase2 検証チェックリスト: gi_adapterの3段階が個別に区別できること。"""
from __future__ import annotations

from profiling_tool.adapters.gi_adapter import GI_STAGES, instrument_frame, resolve_frame
from profiling_tool.core.gpu_timestamp_query import GpuTimestampQuery, SimulatedGpuBackend


def test_instrument_frame_issues_one_query_per_stage():
    query = GpuTimestampQuery(SimulatedGpuBackend(resolve_after_polls=1))
    handles = instrument_frame(query, frame_index=0)

    assert set(handles.keys()) == set(GI_STAGES)
    assert len(set(handles.values())) == 3  # 3段階のhandleが互いに異なる


def test_resolve_frame_returns_gpu_spans_distinguishable_by_stage():
    query = GpuTimestampQuery(SimulatedGpuBackend(resolve_after_polls=1))
    handles = instrument_frame(query, frame_index=2)

    resolved = resolve_frame(query, handles)

    assert set(resolved.keys()) == {"probe_update", "ssgi", "composite"}
    for stage, gpu_span in resolved.items():
        assert gpu_span.name == f"gi_{stage}_frame2"


def test_resolve_frame_omits_unresolved_stages_without_blocking():
    query = GpuTimestampQuery(SimulatedGpuBackend(resolve_after_polls=5))
    handles = instrument_frame(query, frame_index=0)

    # 1回のpollでは閾値(5)に満たないので、まだ何も解決されない
    resolved = resolve_frame(query, handles)
    assert resolved == {}
