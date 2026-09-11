"""adapters/vlm_adapter.py — VLM Auto-Replay Tool

対象文書で確定済みのStepLog{stepIndex, timestamp, todoId, observationRef, reasoning,
actionTaken, resultObservationSummary}をSpan+Eventにマッピングする。1ステップ=1span、
reasoningは長文になり得るためStructuredEventのpayloadとして別出しする。

StepLogのフィールド名を知っているのはこのアダプタだけであり、profiling/コアは
一切関知しない。
"""

from __future__ import annotations

from profiling_tool.core.chrome_trace import event, span

from .checkpoint import CheckpointStore, diff_new_step_logs

TARGET = "vlm_auto_replay"


def to_trace(step_log: dict) -> list[dict]:
    step_span = span(
        name=f"step_{step_log['stepIndex']}",
        ts=step_log["timestamp"],
        tags={"todoId": step_log["todoId"]},
    )
    return [
        step_span,
        event(
            name="reasoning_trace",
            ts=step_log["timestamp"],
            payload={
                "reasoning": step_log["reasoning"],
                "actionTaken": step_log["actionTaken"],
                "resultObservationSummary": step_log["resultObservationSummary"],
            },
        ),
    ]


def to_trace_incremental(
    step_logs: list[dict], checkpoint_store: CheckpointStore, target: str = TARGET
) -> list[dict]:
    """差分アップデート: 前回処理済みのstepIndexをcheckpoint_storeから読み、
    新規stepLogのみをトレースイベントへ変換する。
    """
    last_step_index = checkpoint_store.load(target)
    new_logs = diff_new_step_logs(step_logs, last_step_index)
    if not new_logs:
        return []
    events: list[dict] = []
    for step_log in new_logs:
        events.extend(to_trace(step_log))
    checkpoint_store.save(target, new_logs[-1]["stepIndex"])
    return events
