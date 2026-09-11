"""Phase2 検証チェックリスト: vlm_adapter。"""
from __future__ import annotations

from profiling_tool.adapters.checkpoint import CheckpointStore
from profiling_tool.adapters.vlm_adapter import to_trace, to_trace_incremental

STEP_LOG = {
    "stepIndex": 3,
    "timestamp": 5000,
    "todoId": "todo-42",
    "observationRef": "obs-7",
    "reasoning": "画面右上のボタンを押す必要がある",
    "actionTaken": "click(button_id=save)",
    "resultObservationSummary": "保存完了ダイアログが表示された",
}


def test_to_trace_maps_one_step_to_one_span_and_one_event():
    events = to_trace(STEP_LOG)
    assert len(events) == 2

    step_span, reasoning_event = events
    assert step_span["ph"] == "X"
    assert step_span["name"] == "step_3"
    assert step_span["args"]["todoId"] == "todo-42"

    assert reasoning_event["ph"] == "i"
    assert reasoning_event["args"]["payload"]["reasoning"] == STEP_LOG["reasoning"]
    assert reasoning_event["args"]["payload"]["actionTaken"] == STEP_LOG["actionTaken"]


def test_to_trace_does_not_require_field_name_changes():
    """StepLogのフィールド名変更なしに変換できることを、設計書のスキーマそのままの
    辞書で確認する(フィールド名を書き換えないと動かない実装だと検知される)。
    """
    events = to_trace(STEP_LOG)
    assert events  # 例外なく変換できる


def test_to_trace_incremental_processes_only_new_step_logs(tmp_path):
    store = CheckpointStore(tmp_path)
    step_logs = [{**STEP_LOG, "stepIndex": i, "timestamp": i * 1000} for i in range(3)]

    first_batch = to_trace_incremental(step_logs, store)
    assert len(first_batch) == 6  # 3ステップ x (span+event)

    # 同じstep_logsを再度渡しても、差分が無いので空
    second_batch = to_trace_incremental(step_logs, store)
    assert second_batch == []

    # 新規ステップが増えたら、その分だけが差分として処理される
    step_logs.append({**STEP_LOG, "stepIndex": 3, "timestamp": 3000})
    third_batch = to_trace_incremental(step_logs, store)
    assert len(third_batch) == 2
    assert third_batch[0]["name"] == "step_3"
