from copy import deepcopy

from fastapi.testclient import TestClient

from app import app
from detector import GraphDetector
from financial import assess_financial
from graph_models import Transaction
from graph_models import TransactionStatus


def test_unified_contract_reproducible_and_request_scoped(normal_transactions, attack_transactions):
    detector = GraphDetector(normal_transactions)
    batch = assess_financial(detector, attack_transactions)
    assess_financial(detector, normal_transactions)
    repeated = assess_financial(detector, list(reversed(attack_transactions)))
    assert repeated == batch
    assert batch.risk_score >= 0.70
    assert all(0 <= value <= 1 for score in batch.transaction_scores for value in score.detectors.model_dump().values())
    assert len(batch.model.checkpoint_sha256) == 64
    assert detector.baseline_transactions == normal_transactions
    prefix = assess_financial(detector, attack_transactions[:2])
    assert prefix.transaction_scores == batch.transaction_scores[:2]


def test_cancelled_payments_and_unsupported_model_promotions_are_excluded(normal_transactions, attack_transactions, monkeypatch):
    import torch

    detector = GraphDetector(normal_transactions)
    monkeypatch.setattr(detector.tgnn, "forward", lambda txs: (torch.tensor(0.999), {}))
    from datetime import timedelta
    historical = [tx.model_copy(update={"timestamp": tx.timestamp - timedelta(days=1)}) for tx in normal_transactions]
    clean = assess_financial(detector, normal_transactions, historical)
    assert clean.risk_score < 0.70
    assert all(not score.ml_used for score in clean.transaction_scores)
    cancelled = [tx.model_copy(update={"status": TransactionStatus.CANCELLED}) for tx in attack_transactions]
    result = assess_financial(detector, cancelled)
    assert result.risk_score == 0
    assert result.suspicious_accounts == []


def test_financial_endpoint_validates_duplicate_ids_and_contract(normal_payload, attack_payload):
    client = TestClient(app)
    payload = {"transactions": attack_payload, "baseline_transactions": normal_payload}
    response = client.post("/assess-financial", json=payload)
    assert response.status_code == 200
    assert response.json()["schema_version"] == "financial.v1"
    payload["transactions"] = [attack_payload[0], deepcopy(attack_payload[0])]
    assert client.post("/assess-financial", json=payload).status_code == 422


def test_payroll_hard_negative_does_not_trigger_scam_case():
    from evaluation.dataset import generate_split
    case = next(case for case in generate_split("test", 987, 1) if case["segment"] == "payroll_control")
    result = assess_financial(GraphDetector([]), [Transaction.model_validate(tx) for tx in case["transactions"]],
                              [Transaction.model_validate(tx) for tx in case["baseline_transactions"]])
    assert result.risk_score < 0.70
    assert all(score.detectors.scam == 0 for score in result.transaction_scores)
    assert any(score.raw_scam_score > 0.70 for score in result.transaction_scores)
