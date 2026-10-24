from backend.app.models import CorrelationRequest
from backend.app.correlation import correlate
from backend.app.simulator import load_attack_transactions, load_mock_signals
from backend.app.storage import ArgusStore


def test_store_persists_investigation_history_and_metrics(tmp_path) -> None:
    store = ArgusStore(tmp_path / "argus-test.db")
    transactions = load_attack_transactions()
    graph, system = load_mock_signals()
    incident = correlate(CorrelationRequest(graph_signal=graph, system_signal=system))

    store.save_transactions("BATCH-001", transactions)
    store.save_signal(graph)
    store.save_signal(system)
    store.save_incident(incident)

    restored = store.get_incident(incident.incident_id)
    metrics = store.metrics()

    assert restored == incident
    assert metrics.transactions_ingested == 3
    assert metrics.signals_analyzed == 2
    assert metrics.incidents_total == 1
    assert metrics.accounts_observed == 4
    assert metrics.total_value_observed == 247500


def test_reanalysis_preserves_containment_and_audit_after_store_restart(tmp_path):
    from backend.app.policy import approve_containment

    path = tmp_path / "reanalysis.db"
    store = ArgusStore(path)
    graph, system = load_mock_signals()
    request = CorrelationRequest(graph_signal=graph, system_signal=system)
    pending = correlate(request)
    store.save_incident(pending)
    contained, audit = approve_containment(pending, "test-analyst")
    store.save_incident(contained)
    store.save_audit_events(contained.incident_id, audit)

    restarted = ArgusStore(path)
    replayed = restarted.save_incident(correlate(request))
    assert replayed == contained
    assert restarted.get_incident(contained.incident_id) == contained
    assert restarted.list_audit_events(contained.incident_id) == sorted(audit, key=lambda event: event.timestamp, reverse=True)
