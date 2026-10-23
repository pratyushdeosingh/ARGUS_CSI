#!/usr/bin/env python3
"""ARGUS Phase 3 — Terminal WebSocket Live Event Watcher.

Connects to ws://localhost:8000/ws/transactions and streams live transaction
events, graph fraud risk scores, and security alerts in real time.

Dependencies:
    pip install websockets
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
import json
import sys
from typing import Any

try:
    import websockets
except ImportError:
    print(
        "[ERROR] 'websockets' library is required to run watch_transactions.py.\n"
        "Install it via:\n"
        "    pip install websockets\n",
        file=sys.stderr,
    )
    sys.exit(1)


# ANSI Color Codes
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def format_event(raw_event: str) -> str:
    """Format an incoming JSON event envelope into an operator-friendly string."""
    try:
        event = json.loads(raw_event)
    except json.JSONDecodeError:
        return f"{DIM}[RAW]{RESET} {raw_event}"

    event_id = event.get("event_id", "???")
    event_type = event.get("event_type", "unknown")
    timestamp = event.get("timestamp", "")
    data = event.get("data", {})

    if event_type == "connection.established":
        msg = data.get("message", "Connected")
        status = data.get("status", "online")
        return (
            f"{GREEN}{BOLD}● [CONNECTED]{RESET} {DIM}{timestamp}{RESET} "
            f"({event_id}) - {msg} [status={status}]"
        )

    if event_type == "transaction.received":
        tx_id = data.get("transaction_id", "???")
        amt = data.get("amount", 0)
        curr = data.get("currency", "INR")
        src = data.get("source_account", "???")
        dst = data.get("destination_account", "???")
        st = data.get("status", "???")
        return (
            f"{CYAN}📥 [RECEIVED]{RESET} {DIM}{timestamp}{RESET} "
            f"Tx: {BOLD}{tx_id}{RESET} | {amt:10.2f} {curr} | {src} -> {dst} | [{st}]"
        )

    if event_type == "transaction.scored":
        tx_id = data.get("transaction_id", "???")
        sig_id = data.get("signal_id", "???")
        score = float(data.get("risk_score", 0.0))
        anomaly = data.get("anomaly_type", "normal")
        accounts = data.get("suspicious_accounts", [])
        reasons = data.get("reasons", [])

        # Color-code score
        if score >= 0.70:
            score_str = f"{RED}{BOLD}{score:.3f}{RESET}"
        elif score >= 0.30:
            score_str = f"{YELLOW}{score:.3f}{RESET}"
        else:
            score_str = f"{GREEN}{score:.3f}{RESET}"

        summary = (
            f"{YELLOW}⚖️  [SCORED]  {RESET} {DIM}{timestamp}{RESET} "
            f"Tx: {BOLD}{tx_id}{RESET} | Score: {score_str} | Anomaly: {anomaly} "
            f"| Signal: {sig_id}"
        )
        if accounts:
            summary += f"\n       {DIM}Accounts flagged: {', '.join(accounts)}{RESET}"
        if reasons:
            for reason in reasons[:2]:
                summary += f"\n       {DIM}• {reason}{RESET}"
        return summary

    if event_type == "alert.created":
        alt_id = data.get("alert_id", "???")
        tx_id = data.get("transaction_id", "???")
        score = float(data.get("risk_score", 0.0))
        anomaly = data.get("anomaly_type", "unknown")
        severity = data.get("severity", "high").upper()
        evidence = data.get("supporting_evidence", [])
        accounts = data.get("suspicious_accounts", [])

        banner = (
            f"\n{RED}{BOLD}🚨 [ALERT CREATED] {alt_id} ({severity}) - Risk Score: {score:.3f}{RESET}\n"
            f"   Triggered by: {BOLD}{tx_id}{RESET} | Anomaly: {anomaly}\n"
            f"   Flagged Accounts: {', '.join(accounts)}"
        )
        for ev in evidence:
            banner += f"\n   ⚠️  {ev}"
        banner += f"\n{DIM}{'-' * 70}{RESET}"
        return banner

    if event_type == "transaction.analysis_failed":
        tx_id = data.get("transaction_id", "???")
        err = data.get("error", "Unknown error")
        return f"{RED}⚠️  [ANALYSIS FAILED]{RESET} Tx: {tx_id} - Error: {err}"

    return f"{DIM}[EVENT:{event_type}]{RESET} {event_id}: {json.dumps(data)}"


async def watch(url: str) -> None:
    print("=" * 70)
    print(f"ARGUS Phase 3 — Live WebSocket Transaction Stream")
    print(f"Connecting to: {url}")
    print("Press Ctrl+C to disconnect and exit.")
    print("=" * 70)

    retry_delay = 1.0
    while True:
        try:
            async with websockets.connect(url) as ws:
                retry_delay = 1.0
                while True:
                    raw_msg = await ws.recv()
                    output = format_event(str(raw_msg))
                    print(output)
        except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError, OSError) as error:
            print(
                f"{DIM}[INFO] Connection closed ({error}). Reconnecting in {retry_delay:.1f}s...{RESET}"
            )
            await asyncio.sleep(retry_delay)
            retry_delay = min(10.0, retry_delay * 1.5)
        except asyncio.CancelledError:
            break


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stream real-time financial transaction and fraud alert events."
    )
    parser.add_argument(
        "--url",
        default="ws://localhost:8000/ws/transactions",
        help="WebSocket URL (default: ws://localhost:8000/ws/transactions).",
    )
    args = parser.parse_args()

    try:
        asyncio.run(watch(args.url))
    except KeyboardInterrupt:
        print(f"\n{DIM}[!] Stream closed by user.{RESET}")


if __name__ == "__main__":
    main()
