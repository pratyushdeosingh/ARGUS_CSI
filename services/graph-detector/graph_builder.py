"""Build transaction graphs and find short-lived money-flow structures."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta

import networkx as nx

from models import Transaction, TransactionStatus


@dataclass(frozen=True)
class TemporalPath:
    transactions: tuple[Transaction, ...]
    forwarded_ratios: tuple[float, ...]

    @property
    def accounts(self) -> tuple[str, ...]:
        first, *rest = self.transactions
        return (first.source_account, *(item.destination_account for item in (first, *rest)))

    @property
    def duration_seconds(self) -> float:
        return (self.transactions[-1].timestamp - self.transactions[0].timestamp).total_seconds()


def active_transactions(transactions: Iterable[Transaction]) -> list[Transaction]:
    """Cancelled transfers never contribute to money-flow risk."""

    return sorted(
        (transaction for transaction in transactions if transaction.status != TransactionStatus.CANCELLED),
        key=lambda item: (item.timestamp, item.transaction_id),
    )


def build_graph(transactions: Iterable[Transaction]) -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    for transaction in active_transactions(transactions):
        graph.add_node(transaction.source_account)
        graph.add_node(transaction.destination_account)
        graph.add_edge(
            transaction.source_account,
            transaction.destination_account,
            key=transaction.transaction_id,
            transaction=transaction,
            amount=transaction.amount,
            currency=transaction.currency,
            timestamp=transaction.timestamp,
        )
    return graph


def find_temporal_paths(
    transactions: Iterable[Transaction],
    *,
    max_gap: timedelta = timedelta(minutes=5),
    max_depth: int = 4,
    minimum_forwarded_ratio: float = 0.5,
) -> list[TemporalPath]:
    """Find time-respecting paths without allowing cycles or currency mixing."""

    ordered = active_transactions(transactions)
    by_source: dict[str, list[Transaction]] = {}
    for transaction in ordered:
        by_source.setdefault(transaction.source_account, []).append(transaction)

    paths: list[TemporalPath] = []

    def extend(current: tuple[Transaction, ...], ratios: tuple[float, ...]) -> None:
        last = current[-1]
        visited = {current[0].source_account, *(item.destination_account for item in current)}
        if len(current) >= max_depth:
            return
        for candidate in by_source.get(last.destination_account, []):
            gap = candidate.timestamp - last.timestamp
            if gap < timedelta(0) or gap > max_gap:
                continue
            if candidate.currency != last.currency or candidate.destination_account in visited:
                continue
            ratio = candidate.amount / last.amount
            if ratio < minimum_forwarded_ratio or ratio > 1.25:
                continue
            extended = (*current, candidate)
            extended_ratios = (*ratios, min(ratio, 1.0))
            if len(extended) >= 2:
                paths.append(TemporalPath(extended, extended_ratios))
            extend(extended, extended_ratios)

    for transaction in ordered:
        extend((transaction,), ())

    # Keep maximal, unique transaction sequences. A three-hop chain should not
    # be presented as three separate explanations.
    unique = {tuple(item.transaction_id for item in path.transactions): path for path in paths}
    maximal: list[TemporalPath] = []
    for ids, path in unique.items():
        if any(
            len(other) > len(ids)
            and any(other[index : index + len(ids)] == ids for index in range(len(other) - len(ids) + 1))
            for other in unique
        ):
            continue
        maximal.append(path)
    return sorted(maximal, key=lambda path: (-len(path.transactions), path.transactions[0].timestamp))
