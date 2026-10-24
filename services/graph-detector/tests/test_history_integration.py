from datetime import datetime, timedelta, timezone

from graph_models import Transaction
from history import InMemoryHistoryStore
from mule_detector import MuleDetector


def payment(identifier, seconds=0, **changes):
    data = dict(
        transaction_id=identifier,
        timestamp=datetime(2026, 10, 24, tzinfo=timezone.utc) + timedelta(seconds=seconds),
        source_account="A", destination_account="B", amount=1000,
        currency="INR", device_id="device", ip_address="127.0.0.1", status="completed",
    )
    data.update(changes)
    return Transaction(**data)


def test_history_eviction_removes_account_and_graph_indices():
    history = InMemoryHistoryStore(max_history_size=2)
    history.add_transaction(payment("OLD", source_account="OLD-A", destination_account="OLD-B"))
    history.add_transaction(payment("NEW-1", 1))
    history.add_transaction(payment("NEW-2", 2))
    assert history.get_account_outgoing("OLD-A") == []
    assert history.get_subgraph_transactions(["OLD-A"], hops=2) == []
    assert "OLD-A" not in history._graph


def test_history_window_is_anchored_to_payment_not_stale_account_activity():
    history = InMemoryHistoryStore()
    history.add_transaction(payment("OLD"))
    history.add_transaction(payment("FUTURE", 10000))
    assert history.get_account_outgoing(
        "A", 3600, as_of=payment("CURRENT", 5000).timestamp
    ) == []


def test_duplicate_delivery_does_not_inflate_history():
    history = InMemoryHistoryStore()
    tx = payment("ONCE")
    history.add_transaction(tx)
    history.add_transaction(tx)
    assert history.get_account_outgoing("A") == [tx]


def test_different_currencies_do_not_create_mule_forwarding():
    history = InMemoryHistoryStore()
    history.add_transaction(payment("IN", destination_account="MULE"))
    tx = payment("OUT", 30, source_account="MULE", destination_account="EXIT", currency="USD")
    result = MuleDetector(history).evaluate_account("MULE", tx)
    assert result.forwarding_speed_score == 0
    assert result.turnover_score == 0
