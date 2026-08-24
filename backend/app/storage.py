"""Durable local storage for investigations, signals, and transaction history."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from threading import RLock

from .models import AuditEvent, GraphSignal, Incident, PlatformMetrics, SystemSignal, Transaction


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = ROOT / "data" / "argus.db"


class ArgusStore:
    def __init__(self, path: str | Path | None = None) -> None:
        configured = path or os.getenv("ARGUS_DB_PATH") or DEFAULT_DB_PATH
        self.path = Path(configured)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS transaction_events (
                    transaction_id TEXT PRIMARY KEY,
                    batch_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    source_account TEXT NOT NULL,
                    destination_account TEXT NOT NULL,
                    amount REAL NOT NULL,
                    currency TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    ip_address TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_transactions_batch
                    ON transaction_events(batch_id);
                CREATE INDEX IF NOT EXISTS ix_transactions_source
                    ON transaction_events(source_account);

                CREATE TABLE IF NOT EXISTS detector_signals (
                    signal_id TEXT PRIMARY KEY,
                    signal_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    risk_score REAL NOT NULL,
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS incidents (
                    incident_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL,
                    verdict TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_incidents_status
                    ON incidents(status, timestamp DESC);

                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    incident_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    FOREIGN KEY(incident_id) REFERENCES incidents(incident_id)
                );
                """
            )

    def save_transactions(self, batch_id: str, transactions: list[Transaction]) -> None:
        rows = [
            (
                item.transaction_id,
                batch_id,
                item.timestamp.isoformat(),
                item.source_account,
                item.destination_account,
                item.amount,
                item.currency,
                item.device_id,
                item.ip_address,
                item.status.value,
                item.model_dump_json(),
            )
            for item in transactions
        ]
        with self._lock, self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO transaction_events (
                    transaction_id, batch_id, timestamp, source_account,
                    destination_account, amount, currency, device_id,
                    ip_address, status, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(transaction_id) DO UPDATE SET
                    batch_id=excluded.batch_id,
                    timestamp=excluded.timestamp,
                    source_account=excluded.source_account,
                    destination_account=excluded.destination_account,
                    amount=excluded.amount,
                    currency=excluded.currency,
                    device_id=excluded.device_id,
                    ip_address=excluded.ip_address,
                    status=excluded.status,
                    payload=excluded.payload
                """,
                rows,
            )

    def save_signal(self, signal: GraphSignal | SystemSignal) -> None:
        signal_type = "graph" if isinstance(signal, GraphSignal) else "system"
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO detector_signals (
                    signal_id, signal_type, timestamp, risk_score, payload
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(signal_id) DO UPDATE SET
                    signal_type=excluded.signal_type,
                    timestamp=excluded.timestamp,
                    risk_score=excluded.risk_score,
                    payload=excluded.payload
                """,
                (
                    signal.signal_id,
                    signal_type,
                    signal.timestamp.isoformat(),
                    signal.risk_score,
                    signal.model_dump_json(),
                ),
            )

    def save_incident(self, incident: Incident) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO incidents (
                    incident_id, timestamp, severity, confidence, status, verdict, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(incident_id) DO UPDATE SET
                    timestamp=excluded.timestamp,
                    severity=excluded.severity,
                    confidence=excluded.confidence,
                    status=excluded.status,
                    verdict=excluded.verdict,
                    payload=excluded.payload
                """,
                (
                    incident.incident_id,
                    incident.timestamp.isoformat(),
                    incident.severity.value,
                    incident.confidence,
                    incident.status.value,
                    incident.verdict,
                    incident.model_dump_json(),
                ),
            )

    def get_incident(self, incident_id: str) -> Incident | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM incidents WHERE incident_id = ?", (incident_id,)
            ).fetchone()
        return Incident.model_validate_json(row["payload"]) if row else None

    def list_incidents(self, limit: int = 50) -> list[Incident]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM incidents ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        return [Incident.model_validate_json(row["payload"]) for row in rows]

    def save_audit_events(
        self, incident_id: str, events: list[AuditEvent]
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "DELETE FROM audit_events WHERE incident_id = ?", (incident_id,)
            )
            connection.executemany(
                "INSERT INTO audit_events (incident_id, timestamp, payload) VALUES (?, ?, ?)",
                [
                    (incident_id, event.timestamp.isoformat(), event.model_dump_json())
                    for event in events
                ],
            )

    def list_audit_events(self, incident_id: str | None = None) -> list[AuditEvent]:
        query = "SELECT payload FROM audit_events"
        parameters: tuple[object, ...] = ()
        if incident_id is not None:
            query += " WHERE incident_id = ?"
            parameters = (incident_id,)
        query += " ORDER BY timestamp DESC"
        with self._lock, self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [AuditEvent.model_validate_json(row["payload"]) for row in rows]

    def latest_system_signal(self) -> SystemSignal | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload FROM detector_signals
                WHERE signal_type = 'system'
                ORDER BY timestamp DESC LIMIT 1
                """
            ).fetchone()
        return SystemSignal.model_validate_json(row["payload"]) if row else None

    def metrics(self) -> PlatformMetrics:
        with self._lock, self._connect() as connection:
            transactions = connection.execute(
                """
                SELECT COUNT(*) AS count,
                       COALESCE(SUM(amount), 0) AS total
                FROM transaction_events
                """
            ).fetchone()
            account_count = connection.execute(
                """
                SELECT COUNT(*) AS count FROM (
                    SELECT source_account AS account FROM transaction_events
                    UNION
                    SELECT destination_account AS account FROM transaction_events
                )
                """
            ).fetchone()["count"]
            signal_count = connection.execute(
                "SELECT COUNT(*) AS count FROM detector_signals"
            ).fetchone()["count"]
            incident_summary = connection.execute(
                """
                SELECT COUNT(*) AS count,
                       COALESCE(AVG(confidence), 0) AS average,
                       SUM(CASE WHEN status != 'contained' THEN 1 ELSE 0 END) AS open_count,
                       SUM(CASE WHEN severity = 'critical' THEN 1 ELSE 0 END) AS critical_count
                FROM incidents
                """
            ).fetchone()
            severity_rows = connection.execute(
                "SELECT severity, COUNT(*) AS count FROM incidents GROUP BY severity"
            ).fetchall()
        return PlatformMetrics(
            transactions_ingested=transactions["count"],
            signals_analyzed=signal_count,
            incidents_total=incident_summary["count"],
            incidents_open=incident_summary["open_count"] or 0,
            critical_incidents=incident_summary["critical_count"] or 0,
            accounts_observed=account_count,
            total_value_observed=round(transactions["total"], 2),
            average_confidence=round(incident_summary["average"], 3),
            severity_counts={row["severity"]: row["count"] for row in severity_rows},
        )


argus_store = ArgusStore()
