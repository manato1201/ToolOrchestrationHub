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
    alert = _alert()
    store.save(alert)
    store.delete(alert)
    assert store.load_all() == []


def test_recurrence_of_same_alert_id_is_kept_as_a_separate_lifecycle(tmp_path):
    """再発(resolve後に同じalert_idが再open)しても、過去の解消済みライフサイクルを上書きしない。

    旧スキーマはalert_idだけが主キーで、再発すると過去のresolved行が潰れ、
    アラート履歴(スライダーで過去の時刻を再現する機能の元データ)が失われていた。
    """
    store = SqliteAlertStore(tmp_path / "hub_state.sqlite3")
    first = _alert(resolved=True)
    recurrence = AlertRecord(
        alert_id=first.alert_id,
        source_tool_id=first.source_tool_id,
        severity=Severity.CRITICAL,
        message="liveness down (again)",
        first_seen_at=datetime(2026, 9, 5, 9, 0, 0, tzinfo=timezone.utc),
        occurrence_count=2,
    )
    store.save(first)
    store.save(recurrence)

    loaded = store.load_all()
    assert [(a.first_seen_at.day, a.is_open, a.occurrence_count) for a in loaded] == [(4, False, 1), (5, True, 2)]


def test_delete_removes_only_the_given_lifecycle(tmp_path):
    store = SqliteAlertStore(tmp_path / "hub_state.sqlite3")
    old = _alert(resolved=True)
    recurrence = AlertRecord(
        alert_id=old.alert_id,
        source_tool_id=old.source_tool_id,
        severity=Severity.CRITICAL,
        message="again",
        first_seen_at=datetime(2026, 9, 5, 9, 0, 0, tzinfo=timezone.utc),
    )
    store.save(old)
    store.save(recurrence)

    store.delete(old)

    assert [a.message for a in store.load_all()] == ["again"]


def test_legacy_schema_database_is_migrated_in_place(tmp_path):
    """alert_idのみが主キーだった旧DBを開くと、データを保ったままv2スキーマへ移行される。"""
    import sqlite3

    db_path = tmp_path / "legacy.sqlite3"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE alerts (
            alert_id TEXT PRIMARY KEY,
            source_tool_id TEXT NOT NULL,
            severity TEXT NOT NULL,
            message TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            resolved_at TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO alerts VALUES (?, ?, ?, ?, ?, ?)",
        ("dev_rag_environment:aaaa", "dev_rag_environment", "critical", "down", "2026-09-01T00:00:00+00:00", None),
    )
    conn.commit()
    conn.close()

    store = SqliteAlertStore(db_path)
    loaded = store.load_all()

    assert len(loaded) == 1
    assert loaded[0].alert_id == "dev_rag_environment:aaaa"
    assert loaded[0].occurrence_count == 1
    assert loaded[0].is_open

    # 移行後は再発を別ライフサイクルとして保存できる
    store.save(
        AlertRecord(
            alert_id="dev_rag_environment:aaaa",
            source_tool_id="dev_rag_environment",
            severity=Severity.CRITICAL,
            message="again",
            first_seen_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
        )
    )
    assert len(store.load_all()) == 2


def test_opening_an_already_migrated_database_is_a_noop(tmp_path):
    db_path = tmp_path / "hub_state.sqlite3"
    SqliteAlertStore(db_path).save(_alert())
    reopened = SqliteAlertStore(db_path)
    assert len(reopened.load_all()) == 1


def test_state_persists_across_store_instances(tmp_path):
    """Hubプロセス再起動を模して、同じdbファイルを別インスタンスで開いても読めることを確認する。"""
    db_path = tmp_path / "hub_state.sqlite3"
    SqliteAlertStore(db_path).save(_alert())

    reopened = SqliteAlertStore(db_path)
    assert len(reopened.load_all()) == 1
