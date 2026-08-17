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
