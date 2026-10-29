"""Verify the deployed Nginx HTTP/WebSocket boundary against a running stack."""
import argparse
import asyncio
import json
from urllib.request import urlopen

import websockets


async def check(origin: str) -> None:
    origin = origin.rstrip("/")
    with urlopen(origin, timeout=30) as response:
        assert b'<div id="root">' in response.read(), "Dashboard HTML missing"
    with urlopen(origin + "/api/platform/metrics", timeout=30) as response:
        assert "transactions_ingested" in json.load(response), "API proxy missing"
    ws_origin = origin.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
    async with websockets.connect(ws_origin + "/ws/transactions") as socket:
        event = json.loads(await asyncio.wait_for(socket.recv(), timeout=10))
        assert event["event_type"] == "connection.established", event
    print("DASHBOARD PROXY PASSED: frontend HTML, same-origin API and WebSocket")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", default="http://127.0.0.1:5173")
    asyncio.run(check(parser.parse_args().origin))
