"""Durable local storage for investigations, signals, and transaction history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
from threading import RLock
from contracts.financial_models import FinancialAssessment
from .policy import approve_containment
from .models import IncidentStatus

from .models import (
    AuditEvent,
    GraphSignal,
    Incident,
    IngestionStatus,
    PlatformMetrics,
    SystemSignal,
    Transaction,
)


class IngestionConflictError(Exception):
    """Raised when an ingested transaction has an existing ID but conflicting data."""


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
                CREATE INDEX IF NOT EXISTS ix_transactions_timestamp_id
                    ON transaction_events(timestamp DESC, transaction_id DESC);

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
                CREATE TABLE IF NOT EXISTS financial_assessments (
                    assessment_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS investigations (
                    incident_id TEXT PRIMARY KEY REFERENCES incidents(incident_id),
                    revision INTEGER NOT NULL DEFAULT 0,
                    assigned_to TEXT,
                    status TEXT NOT NULL DEFAULT 'open'
                );
                CREATE TABLE IF NOT EXISTS investigation_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    incident_id TEXT NOT NULL REFERENCES incidents(incident_id),
                    timestamp TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    payload TEXT NOT NULL
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
            connection.execute("BEGIN IMMEDIATE")
            seen = {}
            for tx in transactions:
                previous = seen.get(tx.transaction_id)
                row = connection.execute("SELECT payload FROM transaction_events WHERE transaction_id = ?",
                                         (tx.transaction_id,)).fetchone()
                stored = Transaction.model_validate_json(row["payload"]) if row else previous
                if stored is not None and stored != tx:
                    raise IngestionConflictError(f"Transaction '{tx.transaction_id}' already exists with different transaction data")
                seen[tx.transaction_id] = tx
            connection.executemany(
                """
                INSERT INTO transaction_events (
                    transaction_id, batch_id, timestamp, source_account,
                    destination_account, amount, currency, device_id,
                    ip_address, status, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(transaction_id) DO NOTHING
                """,
                rows,
            )

    def save_assessment(self, assessment: FinancialAssessment) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("INSERT OR IGNORE INTO financial_assessments VALUES (?, ?, ?)",
                               (assessment.assessment_id, assessment.timestamp.isoformat(), assessment.model_dump_json()))

    def get_assessment(self, assessment_id: str) -> FinancialAssessment | None:
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT payload FROM financial_assessments WHERE assessment_id = ?",
                                     (assessment_id,)).fetchone()
        return FinancialAssessment.model_validate_json(row["payload"]) if row else None

    def approve_incident(self, incident_id: str, actor: str) -> tuple[Incident, list[AuditEvent]]:
        """One SQL transaction owns the status transition and append-only action audit."""
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT payload FROM incidents WHERE incident_id = ?", (incident_id,)).fetchone()
            if row is None:
                raise KeyError(incident_id)
            incident = Incident.model_validate_json(row["payload"])
            if incident.status != IncidentStatus.AWAITING_APPROVAL:
                raise ValueError(f"Incident cannot be approved while {incident.status.value}")
            incident, audit = approve_containment(incident, actor)
            connection.execute("UPDATE incidents SET status = ?, payload = ? WHERE incident_id = ?",
                               (incident.status.value, incident.model_dump_json(), incident_id))
            connection.executemany("INSERT INTO audit_events (incident_id, timestamp, payload) VALUES (?, ?, ?)",
                                   [(incident_id, event.timestamp.isoformat(), event.model_dump_json()) for event in audit])
        return incident, audit

    def get_investigation(self, incident_id: str) -> dict:
        with self._lock, self._connect() as connection:
            if not connection.execute("SELECT 1 FROM incidents WHERE incident_id = ?", (incident_id,)).fetchone():
                raise KeyError(incident_id)
            row = connection.execute("SELECT * FROM investigations WHERE incident_id = ?", (incident_id,)).fetchone()
            events = connection.execute("SELECT * FROM investigation_events WHERE incident_id = ? ORDER BY id",
                                        (incident_id,)).fetchall()
        return {"incident_id": incident_id, "revision": row["revision"] if row else 0,
                "assigned_to": row["assigned_to"] if row else None, "status": row["status"] if row else "open",
                "history": [{"id": event["id"], "timestamp": event["timestamp"], "actor": event["actor"],
                             "revision": event["revision"], "changes": json.loads(event["payload"])} for event in events]}

    def update_investigation(self, incident_id: str, actor: str, expected_revision: int, changes: dict) -> dict:
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if not connection.execute("SELECT 1 FROM incidents WHERE incident_id = ?", (incident_id,)).fetchone():
                raise KeyError(incident_id)
            connection.execute("INSERT OR IGNORE INTO investigations (incident_id) VALUES (?)", (incident_id,))
            row = connection.execute("SELECT * FROM investigations WHERE incident_id = ?", (incident_id,)).fetchone()
            if row["revision"] != expected_revision:
                raise ValueError("Investigation changed; reload its current revision before saving")
            revision = expected_revision + 1
            connection.execute("UPDATE investigations SET revision = ?, assigned_to = ?, status = ? WHERE incident_id = ?",
                               (revision, changes.get("assigned_to", row["assigned_to"]), changes.get("status", row["status"]), incident_id))
            connection.execute("INSERT INTO investigation_events (incident_id, timestamp, actor, revision, payload) VALUES (?, ?, ?, ?, ?)",
                               (incident_id, datetime.now(timezone.utc).isoformat(), actor, revision, json.dumps(changes)))
        return self.get_investigation(incident_id)

    def report_snapshot(self, incident_id: str) -> dict:
        """Read report evidence in one SQLite snapshot, including its immutable history."""
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN")
            row = connection.execute("SELECT payload FROM incidents WHERE incident_id = ?", (incident_id,)).fetchone()
            if row is None:
                raise KeyError(incident_id)
            incident = Incident.model_validate_json(row["payload"])
            investigation = connection.execute("SELECT * FROM investigations WHERE incident_id = ?", (incident_id,)).fetchone()
            history = connection.execute("SELECT * FROM investigation_events WHERE incident_id = ? ORDER BY id", (incident_id,)).fetchall()
            audit = connection.execute("SELECT payload FROM audit_events WHERE incident_id = ? ORDER BY id", (incident_id,)).fetchall()
            assessment = connection.execute("SELECT payload FROM financial_assessments WHERE assessment_id = ?",
                                            (incident.financial_assessment_id,)).fetchone()
            transactions = []
            for identifier in incident.transaction_ids:
                tx = connection.execute("SELECT payload FROM transaction_events WHERE transaction_id = ?", (identifier,)).fetchone()
                if tx:
                    transactions.append(json.loads(tx["payload"]))
        return {
            "case": incident.model_dump(mode="json"),
            "investigation": {"revision": investigation["revision"] if investigation else 0,
                              "assigned_to": investigation["assigned_to"] if investigation else None,
                              "status": investigation["status"] if investigation else "open"},
            "investigation_history": [{"id": event["id"], "timestamp": event["timestamp"],
                                       "actor": event["actor"], "revision": event["revision"],
                                       "changes": json.loads(event["payload"])} for event in history],
            "transactions": transactions,
            "financial_assessment": json.loads(assessment["payload"]) if assessment else None,
            "containment_audit": [json.loads(event["payload"]) for event in audit],
        }

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

    def save_incident(self, incident: Incident) -> Incident:
        """Persist a case without reopening an already contained investigation."""
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
                WHERE incidents.status != 'contained'
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
            row = connection.execute(
                "SELECT payload FROM incidents WHERE incident_id = ?", (incident.incident_id,)
            ).fetchone()
        return Incident.model_validate_json(row["payload"])

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
            value_rows = connection.execute("SELECT currency, SUM(amount) AS total FROM transaction_events GROUP BY currency").fetchall()
        values = {row["currency"]: round(row["total"], 2) for row in value_rows}
        return PlatformMetrics(
            transactions_ingested=transactions["count"],
            signals_analyzed=signal_count,
            incidents_total=incident_summary["count"],
            incidents_open=incident_summary["open_count"] or 0,
            critical_incidents=incident_summary["critical_count"] or 0,
            accounts_observed=account_count,
            total_value_observed=round(transactions["total"], 2) if len(values) <= 1 else None,
            value_by_currency=values,
            average_confidence=round(incident_summary["average"], 3),
            severity_counts={row["severity"]: row["count"] for row in severity_rows},
        )

    def ingest_transaction(
        self, item: Transaction, batch_id: str | None = None
    ) -> IngestionStatus:
        if batch_id is None:
            effective_batch = (
                item.transaction_id.rsplit("-", 1)[0]
                if "-" in item.transaction_id
                else "INGESTED"
            )
        else:
            effective_batch = batch_id

        ts_str = item.timestamp.astimezone(timezone.utc).isoformat()

        with self._lock, self._connect() as connection:
            existing = connection.execute(
                "SELECT payload FROM transaction_events WHERE transaction_id = ?",
                (item.transaction_id,),
            ).fetchone()
            if existing is not None:
                stored = Transaction.model_validate_json(existing["payload"])
                if stored == item:
                    return IngestionStatus.ALREADY_RECEIVED
                raise IngestionConflictError(
                    f"Transaction '{item.transaction_id}' already exists with different transaction data"
                )

            try:
                connection.execute(
                    """
                    INSERT INTO transaction_events (
                        transaction_id, batch_id, timestamp, source_account,
                        destination_account, amount, currency, device_id,
                        ip_address, status, payload
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.transaction_id,
                        effective_batch,
                        ts_str,
                        item.source_account,
                        item.destination_account,
                        item.amount,
                        item.currency,
                        item.device_id,
                        item.ip_address,
                        item.status.value,
                        item.model_dump_json(),
                    ),
                )
                return IngestionStatus.CREATED
            except sqlite3.IntegrityError:
                row = connection.execute(
                    "SELECT payload FROM transaction_events WHERE transaction_id = ?",
                    (item.transaction_id,),
                ).fetchone()
                if row is not None:
                    stored = Transaction.model_validate_json(row["payload"])
                    if stored == item:
                        return IngestionStatus.ALREADY_RECEIVED
                raise IngestionConflictError(
                    f"Transaction '{item.transaction_id}' already exists with different transaction data"
                )

    def get_recent_transactions_window(
        self,
        end_timestamp: datetime,
        window_minutes: int = 15,
        max_count: int = 100,
        batch_id: str | None = None,
    ) -> list[Transaction]:
        """Retrieve recent transactions within a bounded time window up to end_timestamp.

        Sorted chronologically (timestamp ASC, transaction_id ASC).
        """
        start_timestamp = end_timestamp - timedelta(minutes=window_minutes)
        start_str = start_timestamp.astimezone(timezone.utc).isoformat()
        end_str = end_timestamp.astimezone(timezone.utc).isoformat()

        query = """
            SELECT payload FROM transaction_events
            WHERE julianday(timestamp) >= julianday(?) AND julianday(timestamp) <= julianday(?)
        """
        params: list[object] = [start_str, end_str]
        if batch_id is not None:
            query += " AND batch_id = ?"
            params.append(batch_id)

        query += " ORDER BY julianday(timestamp) DESC, transaction_id DESC LIMIT ?"
        params.append(max_count)

        with self._lock, self._connect() as connection:
            rows = connection.execute(query, params).fetchall()

        return [Transaction.model_validate_json(row["payload"]) for row in reversed(rows)]


    def get_transaction(self, transaction_id: str) -> Transaction | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM transaction_events WHERE transaction_id = ?",
                (transaction_id,),
            ).fetchone()
        return Transaction.model_validate_json(row["payload"]) if row else None

    def list_transactions(self, limit: int = 50, offset: int = 0) -> list[Transaction]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload FROM transaction_events
                ORDER BY timestamp DESC, transaction_id DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [Transaction.model_validate_json(row["payload"]) for row in rows]


argus_store = ArgusStore()


def get_argus_store() -> ArgusStore:
    return argus_store
