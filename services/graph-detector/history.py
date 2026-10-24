"""Modular state and history tracking layer for transaction anomaly detection.

Maintains sliding-window customer behavioral profiles, recent transaction history,
counterparty relationships, and subgraphs for real-time scoring.
"""

from abc import ABC, abstractmethod
from collections import defaultdict, deque
from datetime import datetime, timedelta
import statistics
from typing import Any, Iterable
from threading import RLock
from functools import wraps

import networkx as nx

from graph_models import Transaction, TransactionStatus


def synchronized(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapped


class BaseHistoryStore(ABC):
    """Abstract interface for customer transaction history storage.

    Allows in-memory prototype implementation to be swapped with
    PostgreSQL, Redis, or Cassandra in production environments.
    """

    @abstractmethod
    def add_transaction(self, transaction: Transaction) -> None:
        """Record a validated transaction into state."""

    @abstractmethod
    def get_account_incoming(
        self, account: str, window_seconds: float | None = None, *, as_of: datetime | None = None
    ) -> list[Transaction]:
        """Return incoming transactions for account within optional time window."""

    @abstractmethod
    def get_account_outgoing(
        self, account: str, window_seconds: float | None = None, *, as_of: datetime | None = None
    ) -> list[Transaction]:
        """Return outgoing transactions for account within optional time window."""

    @abstractmethod
    def get_account_transactions(
        self, account: str, window_seconds: float | None = None, *, as_of: datetime | None = None
    ) -> list[Transaction]:
        """Return all transactions involving account within optional time window."""

    @abstractmethod
    def get_recent_transactions(
        self, window_seconds: float | None = None, limit: int | None = None, *, as_of: datetime | None = None
    ) -> list[Transaction]:
        """Return recent global transactions in chronological order."""

    @abstractmethod
    def get_subgraph_transactions(
        self, accounts: Iterable[str], hops: int = 1, window_seconds: float | None = None, *, as_of: datetime | None = None
    ) -> list[Transaction]:
        """Extract transactions in the local neighborhood graph around given accounts."""

    @abstractmethod
    def get_account_profile(
        self, account: str, window_seconds: float | None = None, *, as_of: datetime | None = None
    ) -> dict[str, Any]:
        """Compute aggregated behavioral metrics for a specific account."""

    @abstractmethod
    def reset(self) -> None:
        """Clear all stored history (useful for deterministic tests and demos)."""

    @abstractmethod
    def seed(self, transactions: Iterable[Transaction]) -> None:
        """Pre-populate the store with a list of transactions."""


class InMemoryHistoryStore(BaseHistoryStore):
    """Thread-safe, in-memory implementation of the transaction history layer."""

    def __init__(self, max_history_size: int = 10000, default_window_seconds: float = 3600.0):
        self._lock = RLock()
        self.max_history_size = max_history_size
        self.default_window_seconds = default_window_seconds
        self._transactions: deque[Transaction] = deque(maxlen=max_history_size)
        self._incoming_by_account: dict[str, list[Transaction]] = defaultdict(list)
        self._outgoing_by_account: dict[str, list[Transaction]] = defaultdict(list)
        self._graph: nx.MultiDiGraph = nx.MultiDiGraph()

    @synchronized
    def add_transaction(self, transaction: Transaction) -> None:
        """Add transaction and update index mappings and relationship graph."""
        existing = next((tx for tx in self._transactions if tx.transaction_id == transaction.transaction_id), None)
        if existing is not None:
            if existing != transaction:
                raise ValueError("Transaction ID already exists with different data")
            return
        if len(self._transactions) == self.max_history_size:
            expired = self._transactions.popleft()
            self._outgoing_by_account[expired.source_account].remove(expired)
            self._incoming_by_account[expired.destination_account].remove(expired)
            if self._graph.has_edge(expired.source_account, expired.destination_account, expired.transaction_id):
                self._graph.remove_edge(expired.source_account, expired.destination_account, expired.transaction_id)
            self._graph.remove_nodes_from(list(nx.isolates(self._graph)))
        self._transactions.append(transaction)
        self._outgoing_by_account[transaction.source_account].append(transaction)
        self._incoming_by_account[transaction.destination_account].append(transaction)

        if transaction.status != TransactionStatus.CANCELLED:
            self._graph.add_node(transaction.source_account)
            self._graph.add_node(transaction.destination_account)
            self._graph.add_edge(
                transaction.source_account,
                transaction.destination_account,
                key=transaction.transaction_id,
                transaction=transaction,
                amount=transaction.amount,
                currency=transaction.currency,
                timestamp=transaction.timestamp,
            )

    def _filter_by_window(
        self, transactions: list[Transaction], window_seconds: float | None, as_of: datetime | None = None
    ) -> list[Transaction]:
        if as_of is not None:
            transactions = [tx for tx in transactions if tx.timestamp <= as_of]
        if not transactions:
            return []
        if window_seconds is None:
            return list(transactions)

        latest_time = as_of or max(tx.timestamp for tx in transactions)
        cutoff = latest_time - timedelta(seconds=window_seconds)
        return [tx for tx in transactions if tx.timestamp >= cutoff]

    @synchronized
    def get_account_incoming(
        self, account: str, window_seconds: float | None = None, *, as_of: datetime | None = None
    ) -> list[Transaction]:
        txs = self._incoming_by_account.get(account, [])
        return self._filter_by_window(txs, window_seconds, as_of)

    @synchronized
    def get_account_outgoing(
        self, account: str, window_seconds: float | None = None, *, as_of: datetime | None = None
    ) -> list[Transaction]:
        txs = self._outgoing_by_account.get(account, [])
        return self._filter_by_window(txs, window_seconds, as_of)

    @synchronized
    def get_account_transactions(
        self, account: str, window_seconds: float | None = None, *, as_of: datetime | None = None
    ) -> list[Transaction]:
        in_txs = self.get_account_incoming(account, window_seconds, as_of=as_of)
        out_txs = self.get_account_outgoing(account, window_seconds, as_of=as_of)
        combined = {tx.transaction_id: tx for tx in in_txs + out_txs}
        return sorted(combined.values(), key=lambda t: (t.timestamp, t.transaction_id))

    @synchronized
    def get_recent_transactions(
        self, window_seconds: float | None = None, limit: int | None = None, *, as_of: datetime | None = None
    ) -> list[Transaction]:
        all_txs = list(self._transactions)
        filtered = self._filter_by_window(all_txs, window_seconds, as_of)
        ordered = sorted(filtered, key=lambda t: (t.timestamp, t.transaction_id))
        if limit is not None:
            return ordered[-limit:]
        return ordered

    @synchronized
    def get_subgraph_transactions(
        self, accounts: Iterable[str], hops: int = 1, window_seconds: float | None = None, *, as_of: datetime | None = None
    ) -> list[Transaction]:
        target_accounts = set(accounts)
        if not target_accounts:
            return []

        expanded_nodes = set(target_accounts)
        for _ in range(hops):
            neighbors = set()
            for node in expanded_nodes:
                if self._graph.has_node(node):
                    neighbors.update(self._graph.predecessors(node))
                    neighbors.update(self._graph.successors(node))
            expanded_nodes.update(neighbors)

        matched_txs: dict[str, Transaction] = {}
        for node in expanded_nodes:
            for tx in self.get_account_transactions(node, window_seconds, as_of=as_of):
                if tx.source_account in expanded_nodes and tx.destination_account in expanded_nodes:
                    matched_txs[tx.transaction_id] = tx

        return sorted(matched_txs.values(), key=lambda t: (t.timestamp, t.transaction_id))

    @synchronized
    def get_account_profile(
        self, account: str, window_seconds: float | None = None, *, as_of: datetime | None = None
    ) -> dict[str, Any]:
        """Calculate detailed behavioral metrics for an account."""
        incoming = self.get_account_incoming(account, window_seconds, as_of=as_of)
        outgoing = self.get_account_outgoing(account, window_seconds, as_of=as_of)

        in_amounts = [t.amount for t in incoming if t.status != TransactionStatus.CANCELLED]
        out_amounts = [t.amount for t in outgoing if t.status != TransactionStatus.CANCELLED]

        distinct_senders = {t.source_account for t in incoming}
        distinct_receivers = {t.destination_account for t in outgoing}
        all_counterparties = distinct_senders | distinct_receivers

        total_in = sum(in_amounts)
        total_out = sum(out_amounts)

        median_out = statistics.median(out_amounts) if out_amounts else 0.0
        mean_out = statistics.mean(out_amounts) if out_amounts else 0.0

        latest_in_time = max((t.timestamp for t in incoming), default=None)
        latest_out_time = max((t.timestamp for t in outgoing), default=None)

        forwarding_delay: float | None = None
        if latest_in_time and latest_out_time and latest_out_time >= latest_in_time:
            forwarding_delay = (latest_out_time - latest_in_time).total_seconds()

        # Turnover and retention metrics
        turnover_ratio = min(total_in, total_out) / max(total_in, total_out, 1.0)
        retention_ratio = max(0.0, total_in - total_out) / max(total_in, 1.0)
        pass_through_ratio = total_out / max(total_in, 1.0) if total_in > 0 else 0.0

        return {
            "account": account,
            "incoming_count": len(incoming),
            "outgoing_count": len(outgoing),
            "total_transactions": len(incoming) + len(outgoing),
            "incoming_volume": total_in,
            "outgoing_volume": total_out,
            "distinct_senders": distinct_senders,
            "distinct_receivers": distinct_receivers,
            "all_counterparties": all_counterparties,
            "median_outgoing_amount": median_out,
            "mean_outgoing_amount": mean_out,
            "latest_incoming_time": latest_in_time,
            "latest_outgoing_time": latest_out_time,
            "forwarding_delay_seconds": forwarding_delay,
            "turnover_ratio": turnover_ratio,
            "retention_ratio": retention_ratio,
            "pass_through_ratio": pass_through_ratio,
        }

    @synchronized
    def reset(self) -> None:
        self._transactions.clear()
        self._incoming_by_account.clear()
        self._outgoing_by_account.clear()
        self._graph.clear()

    @synchronized
    def seed(self, transactions: Iterable[Transaction]) -> None:
        for tx in sorted(transactions, key=lambda t: (t.timestamp, t.transaction_id)):
            self.add_transaction(tx)