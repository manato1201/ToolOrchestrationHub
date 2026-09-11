"""profiling_tool/adapters/checkpoint.py

ユーザー追加要件「システムのダウンロード・変更があった際は差分アップデートを行う」の
実装(=トレースデータの差分保存)。

各アダプタの入力(StepLogストリーム、manifest.jsonのpipeline配列等)は実行の度に
増分することがある。最後に処理した位置(カーソル)をtarget単位で永続化し、次回は
その続きだけを差分として処理することで、巨大な履歴に対しても毎回フルスキャンの
再処理にならないようにする。カーソルの意味はアダプタ依存(StepLogならstepIndex、
manifest.jsonならpipelineエントリの処理済み件数)で、ここではJSON化可能な任意値として
扱う共通の永続化機構のみを提供する。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

# ToolOrchestrationHub/profiling_tool/adapters/checkpoint.py -> リポジトリルートは3階層上
DEFAULT_CHECKPOINT_DIR = Path(__file__).parent.parent.parent / ".profiling_state" / "checkpoints"


class CheckpointStore:
    def __init__(self, checkpoint_dir: Path | str = DEFAULT_CHECKPOINT_DIR) -> None:
        self._dir = Path(checkpoint_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, target: str) -> Path:
        return self._dir / f"{target}.json"

    def load(self, target: str) -> Optional[Any]:
        path = self._path(target)
        if not path.exists():
            return None
        with path.open(encoding="utf-8") as f:
            return json.load(f).get("cursor")

    def save(self, target: str, cursor: Any) -> None:
        with self._path(target).open("w", encoding="utf-8") as f:
            json.dump({"cursor": cursor}, f, ensure_ascii=False)


def diff_new_step_logs(step_logs: list[dict], last_step_index: Optional[int]) -> list[dict]:
    """VLMのStepLogをstepIndexで差分抽出する。last_step_index以降のみを新規分として返す。"""
    if last_step_index is None:
        return list(step_logs)
    return [s for s in step_logs if s["stepIndex"] > last_step_index]


def diff_new_pipeline_entries(pipeline: list[dict], last_processed_count: Optional[int]) -> list[dict]:
    """VideoFactoryのmanifest.json pipeline配列は逐次追記されるため、
    既に処理済みの件数以降のみを新規分として返す。
    """
    if last_processed_count is None:
        return list(pipeline)
    return pipeline[last_processed_count:]
