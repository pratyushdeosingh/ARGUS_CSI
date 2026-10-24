#!/usr/bin/env python3
"""ARGUS Phase 3 — Transaction Replay Script.

Replays synthetic transaction batches generated during Phase 1 by submitting
them individually and sequentially to the ARGUS Phase 2/3 Ingestion API.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request
from typing import Any


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay financial transactions sequentially to the ARGUS Ingestion API."
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        type=Path,
        help="Path to the JSON transaction dataset (e.g., data/generated/normal.json).",
    )
    parser.add_argument(
        "--url",
        "-u",
        default="http://localhost:8000/api/transactions",
        help="Target API endpoint URL (default: http://localhost:8000/api/transactions).",
    )
    parser.add_argument(
        "--interval",
        default=1.0,
        type=float,
        help="Delay in seconds between transaction submissions (default: 1.0).",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        type=str,
        help="Optional run ID to namespace transaction IDs and prevent duplicate collisions.",
    )
    return parser.parse_args()


def load_dataset(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Transaction dataset file not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"Expected a JSON list of transactions in {path}, got {type(raw).__name__}")

    # Ensure chronological order by timestamp, then transaction_id
    def _sort_key(tx: dict[str, Any]) -> tuple[str, str]:
        return str(tx.get("timestamp", "")), str(tx.get("transaction_id", ""))

    return sorted(raw, key=_sort_key)


def apply_run_id(transaction: dict[str, Any], run_id: str | None) -> dict[str, Any]:
    if not run_id:
        return dict(transaction)

    tx = dict(transaction)
    raw_id = str(tx.get("transaction_id", ""))
    parts = raw_id.rsplit("-", 1)
    if len(parts) == 2:
        tx["transaction_id"] = f"{parts[0]}-{run_id}-{parts[1]}"
    else:
        tx["transaction_id"] = f"{raw_id}-{run_id}"
    return tx


def send_transaction(
    url: str,
    transaction: dict[str, Any],
    session_id: str | None = None,
) -> tuple[int, dict[str, Any] | str]:
    payload = json.dumps(transaction).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if session_id:
        headers["X-Session-ID"] = session_id

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status_code = resp.status
            body = resp.read().decode("utf-8")
            try:
                return status_code, json.loads(body)
            except Exception:
                return status_code, body
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8")
        try:
            return error.code, json.loads(body)
        except Exception:
            return error.code, body
    except urllib.error.URLError as error:
        return 0, f"Connection error: {error.reason}"
    except Exception as error:
        return 0, f"Unexpected error: {error}"


def main() -> None:
    args = parse_arguments()

    try:
        transactions = load_dataset(args.input)
    except Exception as error:
        print(f"[ERROR] Failed to load dataset: {error}", file=sys.stderr)
        sys.exit(1)

    total = len(transactions)
    print("=" * 70)
    print(f"ARGUS Phase 3 — Transaction Replay Pipeline")
    print(f"Dataset:       {args.input} ({total} transactions)")
    print(f"Target URL:    {args.url}")
    print(f"Interval:      {args.interval}s")
    print(f"Run ID:        {args.run_id or 'None (using original IDs)'}")
    print("=" * 70)

    success_count = 0
    duplicate_count = 0
    conflict_count = 0
    error_count = 0

    try:
        for idx, original_tx in enumerate(transactions, start=1):
            tx = apply_run_id(original_tx, args.run_id)
            tx_id = tx["transaction_id"]
            amount = tx.get("amount", 0)
            currency = tx.get("currency", "INR")
            src = tx.get("source_account", "???")
            dst = tx.get("destination_account", "???")

            session_id = None
            if args.run_id:
                parts = tx_id.rsplit("-", 1)
                session_id = parts[0] if len(parts) == 2 else args.run_id

            status_code, response_data = send_transaction(
                args.url, tx, session_id=session_id
            )

            status_label = "UNKNOWN"
            if status_code == 201:
                status_label = "CREATED"
                success_count += 1
            elif status_code == 200:
                status_label = "ALREADY_RECEIVED"
                duplicate_count += 1
            elif status_code == 409:
                status_label = "CONFLICT"
                conflict_count += 1
            elif status_code == 422:
                status_label = "VALIDATION_FAILED"
                error_count += 1
            else:
                status_label = f"HTTP_{status_code}"
                error_count += 1

            detail = ""
            if isinstance(response_data, dict):
                detail = response_data.get("message") or response_data.get("detail", "")
            else:
                detail = str(response_data)

            print(
                f"[{idx:03d}/{total:03d}] {tx_id:25s} | {amount:10.2f} {currency:3s} | "
                f"{src} -> {dst} | HTTP {status_code} [{status_label}] {detail}"
            )

            if idx < total and args.interval > 0:
                time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\n[!] Replay interrupted by user (Ctrl+C).")

    print("-" * 70)
    print(
        f"Summary: {total} total, {success_count} created, "
        f"{duplicate_count} already received, {conflict_count} conflicts, {error_count} errors"
    )
    print("=" * 70)


if __name__ == "__main__":
    main()
