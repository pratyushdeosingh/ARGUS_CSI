from copy import deepcopy

from detector import GraphDetector
from graph_models import Transaction


def test_attack_scores_clearly_above_normal(normal_transactions, attack_transactions):
    detector = GraphDetector(normal_transactions)

    normal = detector.analyze(normal_transactions)
    attack = detector.analyze(attack_transactions)

    assert normal.risk_score <= 0.15
    assert attack.risk_score >= 0.80
    assert attack.risk_score >= normal.risk_score + 0.65
    assert attack.anomaly_type == "rapid_mule_fund_movement"
    assert attack.suspicious_accounts == ["ACC-101", "ACC-202", "ACC-303", "ACC-404"]
    assert attack.suspicious_transactions == ["TX-1001", "TX-1002", "TX-1003"]
    assert "185.220.101.10" in attack.related_ips
    assert any("70 seconds" in reason for reason in attack.reasons)
    assert any("previously unseen device or IP" in reason for reason in attack.reasons)


def test_analysis_is_deterministic_and_input_order_independent(normal_transactions, attack_transactions):
    detector = GraphDetector(normal_transactions)

    forward = detector.analyze(attack_transactions)
    reverse = detector.analyze(list(reversed(attack_transactions)))

    assert forward == reverse
    assert forward.signal_id.startswith("GRAPH-")
    assert len(forward.signal_id) == len("GRAPH-") + 12


def test_cancelled_transfers_do_not_create_risk(normal_transactions, attack_payload):
    cancelled_payload = deepcopy(attack_payload)
    for item in cancelled_payload:
        item["status"] = "cancelled"
    transactions = [Transaction.model_validate(item) for item in cancelled_payload]

    signal = GraphDetector(normal_transactions).analyze(transactions)

    assert signal.risk_score == 0
    assert signal.anomaly_type == "no_suspicious_activity"
    assert signal.suspicious_accounts == []
    assert signal.suspicious_transactions == []


def test_different_currencies_do_not_form_a_money_flow_path(normal_transactions, attack_payload):
    payload = deepcopy(attack_payload)
    payload[1]["currency"] = "USD"
    transactions = [Transaction.model_validate(item) for item in payload]

    signal = GraphDetector(normal_transactions).analyze(transactions)

    assert not any("crossed 3 transfers" in reason for reason in signal.reasons)


def test_empty_batch_returns_valid_low_risk_signal(normal_transactions):
    signal = GraphDetector(normal_transactions).analyze([])

    assert signal.risk_score == 0
    assert signal.anomaly_type == "no_suspicious_activity"
    assert signal.signal_id == "GRAPH-E3B0C44298FC"


def test_prototype_model_alone_cannot_raise_normal_payment_risk(normal_transactions, monkeypatch):
    import torch

    detector = GraphDetector(normal_transactions)
    monkeypatch.setattr(detector.tgnn, "forward", lambda txs: (
        torch.tensor(0.999), {normal_transactions[0].source_account: 0.999}
    ))
    signal = detector.analyze(normal_transactions)
    assert signal.risk_score <= 0.15
    assert signal.anomaly_type == "no_suspicious_activity"
    assert signal.suspicious_accounts == []


def test_signal_identity_changes_with_payload_or_baseline(normal_transactions, attack_transactions):
    detector = GraphDetector(normal_transactions)
    original = detector.analyze(attack_transactions)
    changed = list(attack_transactions)
    changed[0] = changed[0].model_copy(update={"amount": changed[0].amount + 1})
    assert detector.analyze(changed).signal_id != original.signal_id
    baseline = list(normal_transactions)
    baseline[0] = baseline[0].model_copy(update={"amount": baseline[0].amount + 1})
    assert detector.analyze(attack_transactions, baseline).signal_id != original.signal_id
