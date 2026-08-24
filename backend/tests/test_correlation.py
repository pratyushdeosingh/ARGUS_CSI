from backend.app.correlation import correlate
from backend.app.models import CorrelationRequest, IncidentStatus, Severity
from backend.app.simulator import load_mock_signals


def test_mock_attack_correlates_to_critical_incident() -> None:
    graph, system = load_mock_signals()
    incident = correlate(CorrelationRequest(graph_signal=graph, system_signal=system))

    assert incident.severity is Severity.CRITICAL
    assert incident.status is IncidentStatus.AWAITING_APPROVAL
    assert incident.confidence >= 0.85
    assert incident.verdict == "coordinated_financial_attack"


def test_incident_identity_is_derived_from_signal_content() -> None:
    graph, system = load_mock_signals()
    first = correlate(CorrelationRequest(graph_signal=graph, system_signal=system))
    changed = system.model_copy(update={"signal_id": "EBPF-CHANGED"})
    second = correlate(CorrelationRequest(graph_signal=graph, system_signal=changed))

    assert first.incident_id.startswith("INC-")
    assert first.incident_id != "INC-001"
    assert first.incident_id != second.incident_id
    assert len(first.affected_accounts) == 4
