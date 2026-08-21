"""Explainable temporal and graph feature extraction."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
from statistics import median

import networkx as nx

from graph_builder import TemporalPath, active_transactions, find_temporal_paths
from graph_models import Transaction


@dataclass
class Evidence:
    score_by_feature: dict[str, float] = field(default_factory=dict)
    accounts: set[str] = field(default_factory=set)
    transactions: set[str] = field(default_factory=set)
    ips: set[str] = field(default_factory=set)
    reasons: list[str] = field(default_factory=list)
    paths: list[TemporalPath] = field(default_factory=list)


def _amount_baselines(transactions: list[Transaction]) -> dict[str, float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for transaction in active_transactions(transactions):
        grouped[transaction.currency].append(transaction.amount)
    return {currency: median(amounts) for currency, amounts in grouped.items()}


def extract_evidence(
    transactions: list[Transaction],
    baseline_transactions: list[Transaction],
    graph: nx.MultiDiGraph,
) -> Evidence:
    active = active_transactions(transactions)
    evidence = Evidence()
    if not active:
        return evidence

    baseline_active = active_transactions(baseline_transactions)
    known_devices: dict[str, set[str]] = defaultdict(set)
    known_ips: dict[str, set[str]] = defaultdict(set)
    known_beneficiaries: dict[str, set[str]] = defaultdict(set)
    for transaction in baseline_active:
        known_devices[transaction.source_account].add(transaction.device_id)
        known_ips[transaction.source_account].add(transaction.ip_address)
        known_beneficiaries[transaction.source_account].add(transaction.destination_account)

    # Device/IP change is meaningful only when a previous profile exists.
    identity_hits = [
        item
        for item in active
        if item.source_account in known_devices
        and (item.device_id not in known_devices[item.source_account] or item.ip_address not in known_ips[item.source_account])
    ]
    if identity_hits:
        evidence.score_by_feature["identity_change"] = min(1.0, 0.7 + 0.1 * (len(identity_hits) - 1))
        evidence.accounts.update(item.source_account for item in identity_hits)
        evidence.transactions.update(item.transaction_id for item in identity_hits)
        evidence.ips.update(item.ip_address for item in identity_hits)
        item = identity_hits[0]
        evidence.reasons.append(
            f"{item.source_account} used a previously unseen device or IP ({item.device_id}, {item.ip_address})."
        )

    amount_reference = _amount_baselines(baseline_active or active)
    amount_hits: list[tuple[Transaction, float]] = []
    for item in active:
        reference = amount_reference.get(item.currency, item.amount)
        ratio = item.amount / max(reference, 1.0)
        if ratio >= 5:
            amount_hits.append((item, ratio))
    if amount_hits:
        max_ratio = max(ratio for _, ratio in amount_hits)
        evidence.score_by_feature["unusual_amount"] = min(1.0, 0.45 + 0.15 * (max_ratio ** 0.25))
        evidence.accounts.update(item.source_account for item, _ in amount_hits)
        evidence.accounts.update(item.destination_account for item, _ in amount_hits)
        evidence.transactions.update(item.transaction_id for item, _ in amount_hits)
        item, ratio = max(amount_hits, key=lambda value: value[1])
        evidence.reasons.append(
            f"{item.transaction_id} transferred {item.amount:,.0f} {item.currency}, {ratio:.1f}x the normal median."
        )

    new_relationships = [
        item
        for item in active
        if item.source_account in known_beneficiaries
        and item.destination_account not in known_beneficiaries[item.source_account]
    ]
    if new_relationships:
        evidence.score_by_feature["new_beneficiary"] = min(1.0, 0.55 + 0.15 * len(new_relationships))
        evidence.accounts.update(item.source_account for item in new_relationships)
        evidence.accounts.update(item.destination_account for item in new_relationships)
        evidence.transactions.update(item.transaction_id for item in new_relationships)
        evidence.reasons.append(
            f"{len(new_relationships)} transfer(s) used beneficiary relationships absent from the behavioral baseline."
        )

    account_events: dict[str, list[Transaction]] = defaultdict(list)
    for item in active:
        account_events[item.source_account].append(item)
        account_events[item.destination_account].append(item)
    velocity_accounts: set[str] = set()
    velocity_transactions: set[str] = set()
    for account, events in account_events.items():
        ordered = sorted(events, key=lambda item: item.timestamp)
        for left, right in zip(ordered, ordered[1:]):
            if right.timestamp - left.timestamp <= timedelta(minutes=2):
                velocity_accounts.add(account)
                velocity_transactions.update((left.transaction_id, right.transaction_id))
    if velocity_accounts:
        evidence.score_by_feature["velocity"] = min(1.0, 0.4 + 0.2 * len(velocity_accounts))
        evidence.accounts.update(velocity_accounts)
        evidence.transactions.update(velocity_transactions)
        evidence.reasons.append(
            f"{len(velocity_accounts)} account(s) sent or received linked transfers within two minutes."
        )

    evidence.paths = find_temporal_paths(active)
    if evidence.paths:
        longest = evidence.paths[0]
        hop_count = len(longest.transactions)
        evidence.score_by_feature["rapid_multi_hop"] = min(1.0, 0.55 + 0.2 * (hop_count - 1))
        evidence.score_by_feature["funds_forwarded"] = sum(longest.forwarded_ratios) / len(longest.forwarded_ratios)
        evidence.accounts.update(longest.accounts)
        evidence.transactions.update(item.transaction_id for item in longest.transactions)
        evidence.ips.update(item.ip_address for item in longest.transactions)
        average_forwarded = 100 * sum(longest.forwarded_ratios) / len(longest.forwarded_ratios)
        evidence.reasons.append(
            f"Funds crossed {hop_count} transfers and {len(longest.accounts)} accounts in "
            f"{longest.duration_seconds:.0f} seconds."
        )
        evidence.reasons.append(
            f"Intermediate accounts forwarded an average of {average_forwarded:.1f}% of received funds."
        )

    high_degree = {
        node
        for node in graph.nodes
        if graph.in_degree(node) >= 3 or graph.out_degree(node) >= 3
    }
    if high_degree:
        max_degree = max(max(graph.in_degree(node), graph.out_degree(node)) for node in high_degree)
        evidence.score_by_feature["fan_in_out"] = min(1.0, 0.5 + 0.1 * max_degree)
        evidence.accounts.update(high_degree)
        for source, target, data in graph.edges(data=True):
            if source in high_degree or target in high_degree:
                evidence.transactions.add(data["transaction"].transaction_id)
        evidence.reasons.append(
            f"{', '.join(sorted(high_degree))} showed fan-in or fan-out of at least three transfers."
        )

    # Include IPs only for transactions that contributed to the final finding.
    suspicious_ids = evidence.transactions
    evidence.ips.update(item.ip_address for item in active if item.transaction_id in suspicious_ids)
    return evidence
