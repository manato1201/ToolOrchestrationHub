"""hub/alert_store.py

Phase3拡張: AlertRecordの永続化。

これまでAlertAggregatorはメモリ上のリストしか持たず、Hubプロセスを再起動すると
アラート履歴が全て消え、resolved分もプロセスが生きている限り無限にメモリへ溜まり続けていた。
このモジュールはSQLiteへの単純な永続化(save/load_all/delete)のみを提供する。

v2スキーマ(2026-10): 1行 = 1つのopen→resolveライフサイクル。
旧スキーマはalert_idだけを主キーにしていたため、同じalert_idが再発(resolve後に再open)すると
過去のresolved行が上書きされ、「いつ・どれだけ止まっていたか」の履歴が再起動のたびに潰れていた
(開始時刻も古いまま残る)。アラート履歴スライダー(過去の時刻の状態を再現する機能)は
この履歴が正確であることに依存するため、(alert_id, first_seen_at)を主キーにして
ライフサイクルごとに行を分け、旧DBは初回起動時に自動で移行する。

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
    alert_id TEXT NOT NULL,
    source_tool_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    resolved_at TEXT,
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (alert_id, first_seen_at)
)
"""


class SqliteAlertStore:
    """AlertRecordをSQLiteへ永続化する。AlertAggregatorのAlertStore Protocolを満たす。"""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._migrate_legacy_schema()
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def _migrate_legacy_schema(self) -> None:
        """alert_idのみを主キーにしていた旧スキーマ(occurrence_count列が無い)を移行する。

        旧DBは1 alert_idにつき1行しか持てず、過去のライフサイクルは既に失われているため、
        残っている行をそのまま1ライフサイクルとして引き継ぐ(発生回数は不明なので1)。
        """
        columns = [row[1] for row in self._conn.execute("PRAGMA table_info(alerts)").fetchall()]
        if not columns or "occurrence_count" in columns:
            return
        # sqliteのPython実装はDDLの前にトランザクションを自動開始しないため、明示的にBEGINして
        # 「リネーム後・コピー前」にクラッシュしても旧データがalerts_legacyに取り残されないようにする。
        self._conn.execute("BEGIN")
        try:
            self._conn.execute("ALTER TABLE alerts RENAME TO alerts_legacy")
            self._conn.execute(_SCHEMA)
            self._conn.execute(
                "INSERT INTO alerts (alert_id, source_tool_id, severity, message, first_seen_at, resolved_at, occurrence_count) "
                "SELECT alert_id, source_tool_id, severity, message, first_seen_at, resolved_at, 1 FROM alerts_legacy"
            )
            self._conn.execute("DROP TABLE alerts_legacy")
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def save(self, alert: AlertRecord) -> None:
        """(alert_id, first_seen_at)で upsert する。同一ライフサイクルなら更新、再発なら別行を追加する。"""
        self._conn.execute(
            """
            INSERT INTO alerts (alert_id, source_tool_id, severity, message, first_seen_at, resolved_at, occurrence_count)
            VALUES (:alert_id, :source_tool_id, :severity, :message, :first_seen_at, :resolved_at, :occurrence_count)
            ON CONFLICT(alert_id, first_seen_at) DO UPDATE SET
                severity = excluded.severity,
                message = excluded.message,
                resolved_at = excluded.resolved_at,
                occurrence_count = excluded.occurrence_count
            """,
            {
                "alert_id": alert.alert_id,
                "source_tool_id": alert.source_tool_id,
                "severity": alert.severity.value,
                "message": alert.message,
                "first_seen_at": alert.first_seen_at.isoformat(),
                "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
                "occurrence_count": alert.occurrence_count,
            },
        )
        self._conn.commit()

    def load_all(self) -> list[AlertRecord]:
        cursor = self._conn.execute(
            "SELECT alert_id, source_tool_id, severity, message, first_seen_at, resolved_at, occurrence_count "
            "FROM alerts ORDER BY first_seen_at ASC"
        )
        return [self._row_to_record(row) for row in cursor.fetchall()]

    def delete(self, alert: AlertRecord) -> None:
        """指定したライフサイクル1件だけを削除する(同じalert_idの他のライフサイクルは残す)。"""
        self._conn.execute(
            "DELETE FROM alerts WHERE alert_id = ? AND first_seen_at = ?",
            (alert.alert_id, alert.first_seen_at.isoformat()),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _row_to_record(row: tuple) -> AlertRecord:
        alert_id, source_tool_id, severity, message, first_seen_at, resolved_at, occurrence_count = row
        return AlertRecord(
            alert_id=alert_id,
            source_tool_id=source_tool_id,
            severity=Severity(severity),
            message=message,
            first_seen_at=datetime.fromisoformat(first_seen_at),
            resolved_at=datetime.fromisoformat(resolved_at) if resolved_at else None,
            occurrence_count=occurrence_count,
        )
