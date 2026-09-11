"""hub/alert_store.py (SQLite永続化) のテスト。"""
from __future__ import annotations

from datetime import datetime, timezone

from hub.alert_aggregator import AlertRecord, Severity
from hub.alert_store import SqliteAlertStore


def _alert(alert_id: str = "profiling_tool:abc123", resolved: bool = False) -> AlertRecord:
    return AlertRecord(
        alert_id=alert_id,
        source_tool_id="profiling_tool",
        severity=Severity.CRITICAL,
        message="liveness down",
        first_seen_at=datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc),
        resolved_at=datetime(2026, 9, 4, 13, 0, 0, tzinfo=timezone.utc) if resolved else None,
    )


def test_save_and_load_all_round_trip(tmp_path):
    store = SqliteAlertStore(tmp_path / "hub_state.sqlite3")
    store.save(_alert())

    loaded = store.load_all()
    assert len(loaded) == 1
    assert loaded[0].alert_id == "profiling_tool:abc123"
    assert loaded[0].severity is Severity.CRITICAL
    assert loaded[0].resolved_at is None


def test_save_upserts_by_alert_id_without_duplicating(tmp_path):
    store = SqliteAlertStore(tmp_path / "hub_state.sqlite3")
    store.save(_alert(resolved=False))
    store.save(_alert(resolved=True))  # 同一alert_id -> resolved_atが更新されるだけ

    loaded = store.load_all()
    assert len(loaded) == 1
    assert loaded[0].resolved_at is not None
    # first_seen_atは初回保存時のまま(据え置き)であること
    assert loaded[0].first_seen_at == datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)


def test_delete_removes_record(tmp_path):
    store = SqliteAlertStore(tmp_path / "hub_state.sqlite3")
    store.save(_alert())
    store.delete("profiling_tool:abc123")
    assert store.load_all() == []


def test_state_persists_across_store_instances(tmp_path):
    """Hubプロセス再起動を模して、同じdbファイルを別インスタンスで開いても読めることを確認する。"""
    db_path = tmp_path / "hub_state.sqlite3"
    SqliteAlertStore(db_path).save(_alert())

    reopened = SqliteAlertStore(db_path)
    assert len(reopened.load_all()) == 1
