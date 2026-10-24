"""Smoke-test the running demo stack with real HTTP and WebSocket boundaries.

Run against a fresh synthetic/demo stack, never a production payment service.
"""

import asyncio
import json
from pathlib import Path
from urllib.request import Request, urlopen
from uuid import uuid4

import websockets


ROOT = Path(__file__).resolve().parents[1]


def request(url, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = Request(url, data=body, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=30) as response:
        return json.load(response)


async def main():
    for port in [8000, 8001, 8002]:
        assert request(f"http://127.0.0.1:{port}/health")["status"] == "ok"

    attack = json.loads((ROOT / "data/attack/transactions.json").read_text())
    baseline = json.loads((ROOT / "data/normal/transactions.json").read_text())
    result = request("http://127.0.0.1:8000/api/analyze", {
        "transactions": attack,
        "baseline_transactions": baseline,
        "correlate_with_latest_system": True,
    })
    assert result["graph_signal"]["risk_score"] >= 0.7
    assert result["detector_status"]["graph"]["origin"] == "service"
    assert result["incident"] is not None
    incident_id = result["incident"]["incident_id"]
    assert request(f"http://127.0.0.1:8000/api/incidents/{incident_id}")["incident_id"] == incident_id

    session = f"SMOKE-{uuid4().hex[:8]}"
    tx = dict(attack[0], transaction_id=f"{session}-1")
    async with websockets.connect("ws://127.0.0.1:8000/ws/transactions") as socket:
        welcome = json.loads(await asyncio.wait_for(socket.recv(), timeout=30))
        assert welcome["event_type"] == "connection.established"
        received = await asyncio.to_thread(request, f"http://127.0.0.1:8000/api/transactions?session_id={session}", tx)
        assert received["status"] == "created"
        for event_type in ["transaction.received", "transaction.scored"]:
            event = json.loads(await asyncio.wait_for(socket.recv(), timeout=30))
            assert event["event_type"] == event_type, event
            assert event["data"]["transaction_id"] == tx["transaction_id"]
    duplicate = request(f"http://127.0.0.1:8000/api/transactions?session_id={session}", tx)
    assert duplicate["status"] == "already_received"

    specialist = request("http://127.0.0.1:8001/score-transaction", tx)
    assert 0 <= specialist["risk_score"] <= 100
    assert set(specialist["detectors"]) == {"rules", "tgnn", "mule", "scam"}
    print("STACK SMOKE PASSED: real detector calls, durable case, WebSocket scoring, idempotency, specialist API")


if __name__ == "__main__":
    asyncio.run(main())
