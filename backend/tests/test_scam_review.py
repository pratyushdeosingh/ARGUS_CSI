import asyncio
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.detectors import DetectorGateway, DetectorUnavailable
from backend.app.simulator import load_attack_transactions


def test_fixture_mode_does_not_fabricate_clean_specialist_score():
    gateway = DetectorGateway(Settings("fixture", "http://graph", "http://system", 1))
    with pytest.raises(DetectorUnavailable, match="fixture mode cannot score"):
        asyncio.run(gateway.score_transaction(load_attack_transactions()[0], []))


@pytest.mark.parametrize("score,wrong_id", [(101, False), (-1, False), (10, True)])
def test_invalid_or_mismatched_specialist_output_is_rejected(score, wrong_id):
    tx = load_attack_transactions()[0]
    body = dict(transaction_id="WRONG" if wrong_id else tx.transaction_id,
                sender=tx.source_account, receiver=tx.destination_account,
                amount=tx.amount, currency=tx.currency, timestamp=tx.timestamp.isoformat(),
                risk_score=score, risk_band="LOW", decision="ALLOW",
                detectors=dict(rules=0, tgnn=0, mule=0, scam=0), explanation="test")
    gateway = DetectorGateway(Settings("required", "http://graph", "http://system", 1),
                              transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)))
    with pytest.raises(DetectorUnavailable):
        asyncio.run(gateway.score_transaction(tx, []))


def test_context_endpoint_does_not_leak_history_and_excludes_cancelled_or_future_events():
    from app import app as graph_app
    client = TestClient(graph_app)
    tx = load_attack_transactions()[0].model_copy(update={"transaction_id": "CTX-CURRENT", "amount": 1000})
    history = [tx.model_copy(update={"transaction_id": f"CTX-{index}",
                                   "destination_account": f"PAYEE-{index}",
                                   "timestamp": tx.timestamp - timedelta(seconds=30 * (index + 1))})
               for index in range(4)]
    def score(current, previous):
        response = client.post("/score-transaction-context", json={
            "transaction": current.model_dump(mode="json"),
            "history": [item.model_dump(mode="json") for item in previous],
        })
        assert response.status_code == 200
        return response.json()
    clean = score(tx, [])
    assert score(tx, history)["detectors"]["scam"] >= 70
    assert score(tx, []) == clean
    future = [item.model_copy(update={"timestamp": tx.timestamp + timedelta(seconds=60)}) for item in history]
    assert score(tx, future) == clean
    from backend.app.models import TransactionStatus
    cancelled = tx.model_copy(update={"status": TransactionStatus.CANCELLED})
    assert score(cancelled, history)["risk_score"] == 0
