"""adapters/videofactory_adapter.py — LearningQt(VideoFactory)

4アダプタの中で最も書きやすい。LearningQtのmanifest.jsonは既に実在するスキーマであり、
ManifestWriterが唯一のプロデューサーとしてpipeline配列({stage, label, status,
duration_sec})を書き出している。このアダプタは新規計測コードを一切必要とせず、既存の
manifest.jsonをジョブ完了後に読み取ってSpanへほぼ1:1マッピングするだけで完結する。

duration_secが0のエントリ(未計測・スキップ)はゼロ幅spanとして出力し、欠測を隠さない。
GPU厳密逐次リース(Narrate→AssembleAndRender→Encode)の非重複性は、このアダプタが
出力するspan列がタイムライン上で重ならないことで自動的に視覚化される(Final Phase)。
"""

from __future__ import annotations

from profiling_tool.core.chrome_trace import span

from .checkpoint import CheckpointStore, diff_new_pipeline_entries

TARGET = "videofactory"


def to_trace(manifest_json: dict, run_id: str, start_cursor_ts: int = 0) -> list[dict]:
    spans = []
    cursor_ts = start_cursor_ts
    for entry in manifest_json["pipeline"]:  # {stage, label, status, duration_sec}
        dur_us = int(entry["duration_sec"] * 1_000_000)
        spans.append(
            span(
                name=entry["stage"],
                ts=cursor_ts,
                dur=dur_us,
                tags={
                    "label": entry["label"],
                    "status": entry["status"],
                    "run_id": run_id,
                },
            )
        )
        cursor_ts += dur_us  # 厳密逐次(Narrate→AssembleAndRender→Encode)実行順をそのままタイムライン化
    return spans


def to_trace_incremental(
    manifest_json: dict,
    run_id: str,
    checkpoint_store: CheckpointStore,
    target: str = TARGET,
) -> list[dict]:
    """差分アップデート: 前回処理済みのpipelineエントリ件数をcheckpoint_storeから読み、
    新規追加分のみをSpanへ変換する。manifest.json自体は(ManifestWriterが書き出す唯一の
    ソースであり部分読み込みAPIが無いため)毎回全件読み込むが、トレースへの反映は
    新規分のみに絞ることで、既存traces/*.jsonへの重複追記を避ける。
    """
    pipeline = manifest_json["pipeline"]
    last_count = checkpoint_store.load(target)
    new_entries = diff_new_pipeline_entries(pipeline, last_count)
    if not new_entries:
        return []

    already_processed = pipeline[: len(pipeline) - len(new_entries)]
    cursor_ts = sum(int(e["duration_sec"] * 1_000_000) for e in already_processed)

    spans = []
    for entry in new_entries:
        dur_us = int(entry["duration_sec"] * 1_000_000)
        spans.append(
            span(
                name=entry["stage"],
                ts=cursor_ts,
                dur=dur_us,
                tags={
                    "label": entry["label"],
                    "status": entry["status"],
                    "run_id": run_id,
                },
            )
        )
        cursor_ts += dur_us

    checkpoint_store.save(target, len(pipeline))
    return spans
