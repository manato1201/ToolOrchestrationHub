"""Phase4検証チェックリスト: alerting/contract.schema.jsonの妥当性。"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

SCHEMA_PATH = Path(__file__).parent.parent.parent / "profiling_tool" / "alerting" / "contract.schema.json"


@pytest.fixture()
def schema() -> dict:
    with SCHEMA_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def test_schema_itself_is_valid_json_schema(schema):
    jsonschema.Draft7Validator.check_schema(schema)


def test_threshold_alert_engine_output_conforms_to_contract_schema(schema):
    from profiling_tool.alerting.threshold_alert import ThresholdAlertEngine, ThresholdRule

    engine = ThresholdAlertEngine(
        rules=[ThresholdRule(target="sound_middleware", metric="underrun_count", threshold=0)],
        sinks=[],
    )
    alert = engine.check("sound_middleware", "underrun_count", value=1, run_id="run001")

    jsonschema.validate(alert, schema)


def test_invalid_target_is_rejected(schema):
    invalid = {
        "target": "not_a_real_target",
        "metric": "x",
        "value": 1,
        "threshold": 0,
        "severity": "critical",
        "timestamp_us": 0,
        "run_id": "r",
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(invalid, schema)
