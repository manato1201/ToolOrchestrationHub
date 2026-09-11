"""adapters/gi_adapter.py — Dynamic GI Middleware

段階別GPUコスト(プローブ更新/SSGI/合成)をGpuTimestampQuery spanにマッピングする。
フレーム単位でbegin/endを発行し、数フレーム遅延でのポーリング結果をそのままGPU
タイムラインのspanとして出力する。各段階のGPUコマンド発行自体はGIミドルウェア側の
既存コードのまま(アダプタは計測タグを差し込むだけ)。
"""

from __future__ import annotations

from profiling_tool.core.gpu_timestamp_query import GpuSpan, GpuTimestampQuery

GI_STAGES = ["probe_update", "ssgi", "composite"]


def instrument_frame(gpu_query: GpuTimestampQuery, frame_index: int) -> dict[str, int]:
    """各段階のGPUタイムスタンプクエリを発行する。戻り値はステージ名→クエリハンドルの
    対応で、後段でtry_resolveする際に使う。
    """
    handles: dict[str, int] = {}
    for stage in GI_STAGES:
        handle = gpu_query.begin(f"gi_{stage}_frame{frame_index}")
        gpu_query.end(handle)
        handles[stage] = handle
    return handles


def resolve_frame(
    gpu_query: GpuTimestampQuery, handles: dict[str, int]
) -> dict[str, GpuSpan]:
    """まだ解決していないhandleは結果に含めない(ここでブロックしない)。
    呼び出し側は未解決のステージを次フレーム以降で再度try_resolveすること。
    """
    resolved: dict[str, GpuSpan] = {}
    for stage, handle in handles.items():
        gpu_span = gpu_query.try_resolve(handle)
        if gpu_span is not None:
            resolved[stage] = gpu_span
    return resolved
