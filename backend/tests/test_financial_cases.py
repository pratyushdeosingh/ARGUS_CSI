from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from backend.app.financial import financial_incident
from backend.app.main import app
from backend.app.detectors import get_detector_gateway
from backend.app.models import CorrelationRequest
from backend.app.correlation import correlate
from backend.app.simulator import load_attack_transactions, load_mock_signals
from backend.app.storage import ArgusStore, IngestionConflictError, get_argus_store
from backend.tests.financial_fixtures import assessment_for


def test_financial_case_without_infrastructure_and_clean_control():
    graph, _ = load_mock_signals()
    assessment = assessment_for(load_attack_transactions(), graph)
    case = financial_incident(assessment)
    assert case.case_type == "financial"
    assert case.infrastructure_signal_id is None
    assert case.financial_assessment_id == assessment.assessment_id
    assert case.status.value == "awaiting_approval"
    assert financial_incident(assessment.model_copy(update={"risk_score": 0.10})) is None


def test_atomic_approval_across_connections(tmp_path):
    path = tmp_path / "case.db"
    first, second = ArgusStore(path), ArgusStore(path)
    graph, system = load_mock_signals()
    case = correlate(CorrelationRequest(graph_signal=graph, system_signal=system))
    first.save_incident(case)
    def attempt(store):
        try:
            store.approve_incident(case.incident_id, "analyst")
            return "approved"
        except ValueError:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, [first, second]))
    assert sorted(outcomes) == ["approved", "conflict"]
    assert len(first.list_audit_events(case.incident_id)) == len(case.recommended_actions)


def test_batch_ledger_rejects_conflicts_atomically_and_preserves_stream_group(tmp_path):
    store = ArgusStore(tmp_path / "ledger.db")
    txs = load_attack_transactions()
    store.ingest_transaction(txs[0], "stream")
    store.save_transactions("batch", [txs[0]])
    assert len(store.get_recent_transactions_window(txs[0].timestamp, batch_id="stream")) == 1
    conflicting = txs[0].model_copy(update={"amount": txs[0].amount + 1})
    with pytest.raises(IngestionConflictError):
        store.save_transactions("bad", [txs[1], conflicting])
    assert store.get_transaction(txs[1].transaction_id) is None
    assert store.get_transaction(txs[0].transaction_id) == txs[0]


def test_investigation_revision_history_and_draft_report_survive_restart(tmp_path):
    store = ArgusStore(tmp_path / "investigation.db")
    app.dependency_overrides[get_argus_store] = lambda: store
    graph, _ = load_mock_signals()
    assessment = assessment_for(load_attack_transactions(), graph)
    case = financial_incident(assessment)
    store.save_transactions("financial", load_attack_transactions())
    store.save_assessment(assessment)
    store.save_incident(case)
    client = TestClient(app)
    base = f"/api/incidents/{case.incident_id}"
    assert client.get(base + "/investigation").json()["revision"] == 0
    update = {"actor": "Pratyush", "expected_revision": 0, "assigned_to": "analyst-1",
              "status": "investigating", "note": "Reviewed source transactions; synthetic mule evidence."}
    result = client.patch(base + "/investigation", json=update)
    assert result.status_code == 200
    assert result.json()["revision"] == 1
    assert client.patch(base + "/investigation", json=update).status_code == 409
    assert client.patch(base + "/investigation", json={"actor": "a", "expected_revision": 1}).status_code == 422
    app.dependency_overrides[get_argus_store] = lambda: ArgusStore(store.path)
    draft = client.get(base + "/report").json()
    assert draft["status"] == "DRAFT_NOT_FILED"
    assert draft["investigation"]["assigned_to"] == "analyst-1"
    assert draft["investigation_history"][0]["actor"] == "Pratyush"
    assert len(draft["transactions"]) == 3
    assert draft["financial_assessment"]["model"]["validation_status"] == "synthetic_only"


def test_unknown_case_workflow_returns_404():
    client = TestClient(app)
    assert client.get("/api/incidents/absent/investigation").status_code == 404
    assert client.get("/api/incidents/absent/report").status_code == 404


def test_batch_financial_assessment_creates_case_and_is_persisted():
    txs = load_attack_transactions()
    graph, _ = load_mock_signals()
    assessment = assessment_for(txs, graph)
    class Gateway:
        async def assess_financial(self, *args, **kwargs):
            return assessment
        async def analyze_payload(self, *args, **kwargs):
            from backend.app.financial import assessment_signal
            from backend.app.models import DetectorStatus, DetectorComponentStatus
            return assessment_signal(assessment), None, DetectorStatus(
                graph=DetectorComponentStatus(availability="online", origin="service", detail="test"),
                system=DetectorComponentStatus(availability="offline", origin="none", detail="optional"))
    app.dependency_overrides[get_detector_gateway] = lambda: Gateway()
    client = TestClient(app)
    result = client.post("/api/analyze", json={"transactions": [tx.model_dump(mode="json") for tx in txs]})
    assert result.status_code == 200
    body = result.json()
    assert body["incident"]["case_type"] == "financial"
    assert body["system_signal"] is None
    saved = client.get(f"/api/financial-assessments/{assessment.assessment_id}").json()
    assert saved == body["financial_assessment"]
    assert client.get(f"/api/incidents/{body['incident']['incident_id']}/report").status_code == 200


def test_currency_totals_are_not_summed_into_fake_portfolio_value(tmp_path):
    store = ArgusStore(tmp_path / "currency.db")
    tx = load_attack_transactions()[0]
    store.save_transactions("mixed", [tx, tx.model_copy(update={"transaction_id": "USD-1", "currency": "USD", "amount": 10})])
    metrics = store.metrics()
    assert metrics.total_value_observed is None
    assert metrics.value_by_currency == {"INR": tx.amount, "USD": 10}
