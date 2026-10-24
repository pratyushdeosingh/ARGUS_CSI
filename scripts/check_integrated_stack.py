"""Smoke-test the running demo stack with real HTTP and WebSocket boundaries.

Run against a fresh synthetic/demo stack, never a production payment service.
"""

import asyncio
import argparse
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import websockets


ROOT = Path(__file__).resolve().parents[1]


def request(url, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = Request(url, data=body, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=30) as response:
        return json.load(response)


def expect_status(url, payload, expected):
    try:
        request(url, payload)
    except HTTPError as error:
        assert error.code == expected, error
    else:
        raise AssertionError(f"Expected HTTP {expected} from {url}")


async def main(args):
    if args.check_persistence:
        saved = json.loads(args.state_file.read_text())
        case = request(f"http://127.0.0.1:8000/api/incidents/{saved['incident']['incident_id']}")
        assert case == saved["incident"]
        assert request(f"http://127.0.0.1:8000/api/transactions/{saved['transaction']['transaction_id']}") == saved["transaction"]
        assert request(f"http://127.0.0.1:8000/api/audit?incident_id={case['incident_id']}") == saved["audit"]
        replay = request("http://127.0.0.1:8000/api/analyze", saved["analysis_payload"])
        assert replay["incident"] == case
        expect_status(f"http://127.0.0.1:8000/api/incidents/{case['incident_id']}/approve", {}, 409)
        print("RESTART CHECK PASSED: stored payment, contained case, audit and replay remain consistent")
        return

    attack = json.loads((ROOT / "data/attack/transactions.json").read_text())
    baseline = json.loads((ROOT / "data/normal/transactions.json").read_text())
    run_id = uuid4().hex[:8]
    attack = [dict(tx, transaction_id=f"CHECK-{run_id}-{index}") for index, tx in enumerate(attack)]
    if args.check_detector_failure:
        expect_status("http://127.0.0.1:8000/api/analyze", {"transactions": attack}, 503)
        tx = dict(attack[0], transaction_id=f"OUTAGE-{uuid4().hex[:8]}-1")
        async with websockets.connect("ws://127.0.0.1:8000/ws/transactions") as socket:
            await asyncio.wait_for(socket.recv(), timeout=30)
            stored = await asyncio.to_thread(request, "http://127.0.0.1:8000/api/transactions?session_id=OUTAGE", tx)
            assert stored["status"] == "created"
            for expected in ["transaction.received", "transaction.analysis_failed"]:
                event = json.loads(await asyncio.wait_for(socket.recv(), timeout=30))
                assert event["event_type"] == expected, event
        assert request(f"http://127.0.0.1:8000/api/transactions/{tx['transaction_id']}")["transaction_id"] == tx["transaction_id"]
        print("OUTAGE CHECK PASSED: batch fails visibly; streamed payment persists with analysis failure event")
        return

    for port in [8000, 8001, 8002]:
        assert request(f"http://127.0.0.1:{port}/health")["status"] == "ok"

    graph_only = request("http://127.0.0.1:8000/api/analyze", {
        "transactions": attack, "baseline_transactions": baseline,
    })
    assert graph_only["system_signal"] is None
    assert graph_only["incident"] is None  # Explicitly verify this remaining fintech gap.
    analysis_payload = {
        "transactions": attack,
        "baseline_transactions": baseline,
        "correlate_with_latest_system": True,
    }
    result = request("http://127.0.0.1:8000/api/analyze", analysis_payload)
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
        # Specialist output must be real, validated and explicitly normalized.
        specialist_event = json.loads(await asyncio.wait_for(socket.recv(), timeout=30))
        if specialist_event["event_type"] == "alert.created":
            specialist_event = json.loads(await asyncio.wait_for(socket.recv(), timeout=30))
        assert specialist_event["event_type"] == "transaction.scam_scored", specialist_event
        data = specialist_event["data"]
        assert data["transaction_id"] == tx["transaction_id"]
        assert 0 <= data["scam_score"] <= 100
        assert data["normalized_scam_score"] == round(data["scam_score"] / 100, 3)
    duplicate = request(f"http://127.0.0.1:8000/api/transactions?session_id={session}", tx)
    assert duplicate["status"] == "already_received"
    expect_status("http://127.0.0.1:8000/api/transactions", dict(tx, amount=tx["amount"] + 1), 409)
    expect_status("http://127.0.0.1:8000/api/transactions", dict(tx, amount=-1), 422)

    specialist = request("http://127.0.0.1:8001/score-transaction", tx)
    assert 0 <= specialist["risk_score"] <= 100
    assert set(specialist["detectors"]) == {"rules", "tgnn", "mule", "scam"}
    for scenario in request("http://127.0.0.1:8001/api/scenarios"):
        scored = request(f"http://127.0.0.1:8001/api/scenarios/{scenario['id']}/run", {})["score_result"]
        assert scored["risk_band"] == scenario["expected_band"]
        assert scored["decision"] == scenario["expected_decision"]

    approved = request(f"http://127.0.0.1:8000/api/incidents/{incident_id}/approve", {})["incident"]
    assert approved["status"] == "contained"
    replay = request("http://127.0.0.1:8000/api/analyze", analysis_payload)
    assert replay["incident"] == approved
    expect_status(f"http://127.0.0.1:8000/api/incidents/{incident_id}/approve", {}, 409)
    audit = request(f"http://127.0.0.1:8000/api/audit?incident_id={incident_id}")
    assert len(audit) == len(approved["recommended_actions"])
    if args.state_file:
        args.state_file.write_text(json.dumps({
            "incident": approved, "transaction": received["transaction"],
            "audit": audit, "analysis_payload": analysis_payload,
        }))
    print("STACK SMOKE PASSED: real detector calls, durable case, WebSocket scoring, idempotency, specialist API")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-file", type=Path)
    parser.add_argument("--check-persistence", action="store_true")
    parser.add_argument("--check-detector-failure", action="store_true")
    args = parser.parse_args()
    if args.check_persistence and args.state_file is None:
        parser.error("--check-persistence requires --state-file")
    asyncio.run(main(args))
