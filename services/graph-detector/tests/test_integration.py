import json
from pathlib import Path

from backend.app.correlation import correlate
from backend.app.models import CorrelationRequest, GraphSignal as BackendGraphSignal, Severity, SystemSignal

from detector import GraphDetector


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_real_graph_signal_correlates_with_argus(normal_transactions, attack_transactions):
    graph_signal = GraphDetector(normal_transactions).analyze(attack_transactions)
    system_payload = json.loads(
        (REPOSITORY_ROOT / "data/attack/mock-system-signal.json").read_text(encoding="utf-8")
    )
    request = CorrelationRequest(
        graph_signal=BackendGraphSignal.model_validate(graph_signal.model_dump()),
        system_signal=SystemSignal.model_validate(system_payload),
    )

    incident = correlate(request)

    assert incident.severity is Severity.CRITICAL
    assert incident.confidence >= 0.90
    assert incident.financial_signal_id == graph_signal.signal_id
    assert any("185.220.101.10" in item for item in incident.evidence)
