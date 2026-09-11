"""Phase1 検証チェックリスト: GpuTimestampQueryのbegin/end/try_resolve。"""
from __future__ import annotations

from profiling_tool.core.gpu_timestamp_query import GpuTimestampQuery, SimulatedGpuBackend


def test_begin_end_do_not_block_and_try_resolve_returns_none_until_ready():
    query = GpuTimestampQuery(SimulatedGpuBackend(resolve_after_polls=2))
    handle = query.begin("gi_probe_update_frame0")
    query.end(handle)

    # begin/endはコマンドリスト発行のみで即時ブロックしない(=すぐ戻ってくる)ので、
    # 発行直後のtry_resolveはまだ結果が無くNoneを返す
    assert query.try_resolve(handle) is None
    assert query.try_resolve(handle) is not None  # 2回目のpollで解決される


def test_try_resolve_returns_gpu_span_with_matching_label():
    query = GpuTimestampQuery(SimulatedGpuBackend(resolve_after_polls=1))
    handle = query.begin("gi_ssgi_frame3")
    query.end(handle)

    gpu_span = query.try_resolve(handle)
    assert gpu_span is not None
    assert gpu_span.name == "gi_ssgi_frame3"
    assert gpu_span.end_us >= gpu_span.start_us


def test_try_resolve_is_idempotent_after_resolution():
    query = GpuTimestampQuery(SimulatedGpuBackend(resolve_after_polls=1))
    handle = query.begin("stage")
    query.end(handle)

    first = query.try_resolve(handle)
    second = query.try_resolve(handle)
    assert first is not None
    assert second is None  # 一度解決したhandleは再度resolveされない(pending管理から除去済み)


def test_unknown_handle_returns_none():
    query = GpuTimestampQuery(SimulatedGpuBackend())
    assert query.try_resolve(999) is None
