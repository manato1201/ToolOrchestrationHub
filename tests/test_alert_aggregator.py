"""Phase3 検証チェックリスト対応テスト。"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from hub.alert_aggregator import (
    AlertAggregator,
    AlertRecord,
    Severity,
    normalize_from_health_check,
    normalize_from_profiling_tool,
    resolve_alert,
    upsert_alert,
)
from hub.alert_store import SqliteAlertStore
from hub.health.base import HealthResult


def test_upsert_alert_does_not_overwrite_first_seen_at():
    aggregator = AlertAggregator()
    first = aggregator.ingest(normalize_from_health_check("profiling_tool", HealthResult(is_up=False)))
    time.sleep(0.01)
    second_raw = normalize_from_health_check("profiling_tool", HealthResult(is_up=False))
    second = upsert_alert(second_raw, aggregator.all())
    assert second is first
    assert second.first_seen_at == first.first_seen_at
    assert len(aggregator.all()) == 1


def test_resolve_alert_sets_resolved_at():
    alert = normalize_from_health_check("dev_rag_environment", HealthResult(is_up=False))
    assert alert.resolved_at is None
    resolved = resolve_alert(alert)
    assert resolved.resolved_at is not None
    assert resolved.is_open is False


def test_aggregator_resolve_by_id_lifecycle():
    aggregator = AlertAggregator()
    alert = aggregator.ingest(normalize_from_health_check("profiling_tool", HealthResult(is_up=False)))
    assert alert in aggregator.open_alerts()

    resolved = aggregator.resolve_by_id(alert.alert_id)
    assert resolved is alert
    assert alert in aggregator.resolved_alerts()
    assert alert not in aggregator.open_alerts()

    # 既にresolve済みのalert_idを再度resolveしても新規には何も起きない
    assert aggregator.resolve_by_id(alert.alert_id) is None


def test_on_open_callback_fires_once_per_new_alert_not_on_dedup():
    opened = []
    aggregator = AlertAggregator(on_open=opened.append)

    aggregator.ingest(normalize_from_health_check("profiling_tool", HealthResult(is_up=False)))
    aggregator.ingest(normalize_from_health_check("profiling_tool", HealthResult(is_up=False)))  # dedup

    assert len(opened) == 1


def test_on_resolve_callback_fires_on_resolve():
    resolved = []
    aggregator = AlertAggregator(on_resolve=resolved.append)
    alert = aggregator.ingest(normalize_from_health_check("profiling_tool", HealthResult(is_up=False)))

    aggregator.resolve_by_id(alert.alert_id)

    assert len(resolved) == 1
    assert resolved[0].alert_id == alert.alert_id


def test_aggregator_with_store_persists_on_ingest_and_resolve(tmp_path):
    store = SqliteAlertStore(tmp_path / "hub_state.sqlite3")
    aggregator = AlertAggregator(store=store)

    alert = aggregator.ingest(normalize_from_health_check("profiling_tool", HealthResult(is_up=False)))
    assert len(store.load_all()) == 1
    assert store.load_all()[0].resolved_at is None

    aggregator.resolve_by_id(alert.alert_id)
    assert store.load_all()[0].resolved_at is not None


def test_aggregator_loads_persisted_alerts_on_construction(tmp_path):
    """Hubプロセス再起動を模して、既存のstoreを渡すとそこからアラート履歴を復元することを確認する。"""
    db_path = tmp_path / "hub_state.sqlite3"
    seed_store = SqliteAlertStore(db_path)
    seed_store.save(normalize_from_health_check("profiling_tool", HealthResult(is_up=False)))

    restarted = AlertAggregator(store=SqliteAlertStore(db_path))
    assert len(restarted.all()) == 1
    assert restarted.all()[0].source_tool_id == "profiling_tool"


def test_prune_resolved_removes_old_resolved_alerts_from_memory_and_store(tmp_path):
    store = SqliteAlertStore(tmp_path / "hub_state.sqlite3")
    aggregator = AlertAggregator(store=store)

    old_alert = AlertRecord(
        alert_id="old:1",
        source_tool_id="profiling_tool",
        severity=Severity.CRITICAL,
        message="old",
        first_seen_at=datetime.now(timezone.utc) - timedelta(days=40),
        resolved_at=datetime.now(timezone.utc) - timedelta(days=35),
    )
    recent_alert = AlertRecord(
        alert_id="recent:1",
        source_tool_id="profiling_tool",
        severity=Severity.CRITICAL,
        message="recent",
        first_seen_at=datetime.now(timezone.utc) - timedelta(hours=2),
        resolved_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    # 既にresolved_atを持つAlertRecordをそのままingestする(過去の永続化データを
    # 想定したセットアップであり、resolve_by_idを経由する必要はない)。
    aggregator.ingest(old_alert)
    aggregator.ingest(recent_alert)

    pruned = aggregator.prune_resolved(retention=timedelta(days=30))

    assert [a.alert_id for a in pruned] == ["old:1"]
    assert {a.alert_id for a in aggregator.all()} == {"recent:1"}
    assert {a.alert_id for a in store.load_all()} == {"recent:1"}


def test_prune_resolved_does_not_remove_open_alerts():
    aggregator = AlertAggregator()
    alert = AlertRecord(
        alert_id="open:1",
        source_tool_id="profiling_tool",
        severity=Severity.CRITICAL,
        message="still open",
        first_seen_at=datetime.now(timezone.utc) - timedelta(days=90),
    )
    aggregator.ingest(alert)

    pruned = aggregator.prune_resolved(retention=timedelta(days=30))

    assert pruned == []
    assert alert in aggregator.all()


def test_same_failure_from_two_sources_merges_into_one_record():
    """Profiling Toolからのアラートとヘルスチェック由来のアラートが同一障害を指す場合、
    alert_idが一致し1件のAlertRecordに集約されることを確認する
    (Phase3検証チェックリスト / Final Phase 統合検証)。
    """
    aggregator = AlertAggregator()

    from_health_check = normalize_from_health_check("profiling_tool", HealthResult(is_up=False))
    from_profiling_tool = normalize_from_profiling_tool(
        {"signature": "liveness_down", "severity": "critical", "message": "profiling_tool unreachable"}
    )

    assert from_health_check.alert_id == from_profiling_tool.alert_id

    first = aggregator.ingest(from_health_check)
    second = aggregator.ingest(from_profiling_tool)

    assert first is second
    assert len(aggregator.all()) == 1
