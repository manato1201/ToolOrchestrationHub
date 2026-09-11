"""profiling/event.py のテスト。"""
from __future__ import annotations

from profiling_tool.core.event import StructuredEvent


def test_from_payload_round_trips_json():
    evt = StructuredEvent.from_payload(
        name="reasoning_trace", timestamp_us=1000, payload={"reasoning": "検討中", "actionTaken": "move_forward"}
    )
    assert evt.name == "reasoning_trace"
    assert evt.timestamp_us == 1000
    assert evt.payload() == {"reasoning": "検討中", "actionTaken": "move_forward"}
