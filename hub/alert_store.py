"""hub/alert_store.py

Phase3拡張: AlertRecordの永続化。

これまでAlertAggregatorはメモリ上のリストしか持たず、Hubプロセスを再起動すると
アラート履歴が全て消え、resolved分もプロセスが生きている限り無限にメモリへ溜まり続けていた。
このモジュールはSQLiteへの単純な永続化(upsert/load_all/delete)のみを提供する。

AlertAggregator/AlertRecord自体はこのモジュールを知らない(alert_aggregator.pyで定義した
構造的なAlertStore Protocolを満たすだけ)。依存の向きは alert_store.py -> alert_aggregator.py
の一方向で、循環importは発生しない。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from .alert_aggregator import AlertRecord, Severity

# data/配下はサンプルアーティファクト(report_manifest.json等)などコミット対象のfixtureであり、
# 実行時にHubが生成する状態はそれと混在させず.hub_state/配下に置く(.gitignore対象)。
DEFAULT_DB_PATH = Path(__file__).parent.parent / ".hub_state" / "alerts.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    alert_id TEXT PRIMARY KEY,
    source_tool_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    resolved_at TEXT
)
"""


class SqliteAlertStore:
    """AlertRecordをSQLiteへ永続化する。AlertAggregatorのAlertStore Protocolを満たす。"""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def save(self, alert: AlertRecord) -> None:
        """alert_idで upsert する(新規insert or 既存レコードの更新)。"""
        self._conn.execute(
            """
            INSERT INTO alerts (alert_id, source_tool_id, severity, message, first_seen_at, resolved_at)
            VALUES (:alert_id, :source_tool_id, :severity, :message, :first_seen_at, :resolved_at)
            ON CONFLICT(alert_id) DO UPDATE SET
                severity = excluded.severity,
                message = excluded.message,
                resolved_at = excluded.resolved_at
            """,
            {
                "alert_id": alert.alert_id,
                "source_tool_id": alert.source_tool_id,
                "severity": alert.severity.value,
                "message": alert.message,
                "first_seen_at": alert.first_seen_at.isoformat(),
                "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
            },
        )
        self._conn.commit()

    def load_all(self) -> list[AlertRecord]:
        cursor = self._conn.execute(
            "SELECT alert_id, source_tool_id, severity, message, first_seen_at, resolved_at "
            "FROM alerts ORDER BY first_seen_at ASC"
        )
        return [self._row_to_record(row) for row in cursor.fetchall()]

    def delete(self, alert_id: str) -> None:
        self._conn.execute("DELETE FROM alerts WHERE alert_id = ?", (alert_id,))
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _row_to_record(row: tuple) -> AlertRecord:
        alert_id, source_tool_id, severity, message, first_seen_at, resolved_at = row
        return AlertRecord(
            alert_id=alert_id,
            source_tool_id=source_tool_id,
            severity=Severity(severity),
            message=message,
            first_seen_at=datetime.fromisoformat(first_seen_at),
            resolved_at=datetime.fromisoformat(resolved_at) if resolved_at else None,
        )
