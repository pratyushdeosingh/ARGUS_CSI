#!/usr/bin/env python3
"""ARGUS Phase 1 — Synthetic Transaction Simulator.

Generates realistic synthetic financial transactions adhering to ARGUS's
contracts and Pydantic schemas. Supports deterministic normal transaction
generation and multi-hop mule account fraud scenarios designed to trigger
temporal graph detection rules.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import sys
from typing import Any


@dataclass(frozen=True)
class Transaction:
    """Represents a financial transaction conforming to contracts/transaction.schema.json."""

    transaction_id: str
    timestamp: str
    source_account: str
    destination_account: str
    amount: float
    currency: str
    device_id: str
    ip_address: str
    status: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary matching the ARGUS Transaction JSON schema."""
        return {
            "transaction_id": self.transaction_id,
            "timestamp": self.timestamp,
            "source_account": self.source_account,
            "destination_account": self.destination_account,
            "amount": self.amount,
            "currency": self.currency,
            "device_id": self.device_id,
            "ip_address": self.ip_address,
            "status": self.status,
        }


class TransactionSimulator:
    """Generates synthetic transaction batches for normal and mule fraud scenarios."""

    DEFAULT_BASE_TIME = datetime(2026, 10, 23, 10, 0, 0, tzinfo=timezone.utc)

    def __init__(
        self,
        seed: int | None = None,
        base_time: datetime | None = None,
    ) -> None:
        """Initialize simulator with an optional random seed and base timestamp."""
        self.seed = seed
        self._rng = random.Random(seed)
        self.base_time = (
            base_time.astimezone(timezone.utc)
            if base_time is not None
            else self.DEFAULT_BASE_TIME
        )
        self._account_pool = self._init_account_pool(count=120)

    def _init_account_pool(self, count: int) -> list[dict[str, str]]:
        """Initialize synthetic customer profiles with stable devices and IPs.

        Account numbers start at ACC-1001 to prevent collisions with pre-existing
        static baseline fixtures (e.g. ACC-101, ACC-050).
        """
        pool: list[dict[str, str]] = []
        for i in range(1, count + 1):
            acc_id = f"ACC-{1000 + i}"
            dev_id = f"DEV-{1000 + i}"
            # Standard RFC 5737 documentation test IP addresses
            ip_addr = f"203.0.113.{(i % 240) + 1}"
            pool.append({
                "account": acc_id,
                "device": dev_id,
                "ip": ip_addr,
            })
        return pool

    @staticmethod
    def _format_timestamp(dt: datetime) -> str:
        """Format datetime as UTC ISO 8601 string ending with 'Z'."""
        utc_dt = dt.astimezone(timezone.utc)
        return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _generate_normal_amount(self) -> float:
        """Generate realistic retail/P2P transaction amounts in INR.

        Keeps typical transactions between 300 and 2,400 INR so that legitimate
        traffic does not trigger the 5x median outlier rule.
        """
        tier = self._rng.random()
        if tier < 0.50:
            amount = self._rng.uniform(300.0, 900.0)
        elif tier < 0.85:
            amount = self._rng.uniform(900.0, 1800.0)
        else:
            amount = self._rng.uniform(1800.0, 2400.0)
        return round(amount, 2)

    def generate_normal_transactions(
        self, count: int, prefix: str = "NORM"
    ) -> list[dict[str, Any]]:
        """Generate a chronological sequence of normal peer-to-peer transactions.

        Properties:
        - Strict positive amounts with realistic retail distribution.
        - Source and destination accounts are distinct (no self-transfers).
        - Accounts transact through their registered device and IP.
        - Timestamps advance chronologically in timezone-aware UTC.
        - Transaction IDs are unique.
        - Avoids rapid chaining, fan-in/fan-out, or velocity anomalies.
        """
        if count < 1:
            raise ValueError(f"Count must be >= 1, received {count}")

        transactions: list[dict[str, Any]] = []
        current_time = self.base_time
        account_count = len(self._account_pool)

        in_degree: dict[str, int] = defaultdict(int)
        out_degree: dict[str, int] = defaultdict(int)
        last_seen_time: dict[str, float] = {}

        for i in range(count):
            tx_id = f"{prefix}-{100001 + i}"

            # Step forward in time (20s to 60s between transactions)
            if i > 0:
                current_time = current_time.fromtimestamp(
                    current_time.timestamp() + self._rng.randint(20, 60),
                    tz=timezone.utc,
                )

            # Pick source and destination accounts avoiding self-transfers,
            # high degree nodes (>= 3), and repeat velocity within 2 minutes.
            attempts = 0
            src_idx = self._rng.randrange(account_count)
            dst_idx = (src_idx + self._rng.randint(1, account_count - 1)) % account_count

            while attempts < 100:
                src_acc = self._account_pool[src_idx]["account"]
                dst_acc = self._account_pool[dst_idx]["account"]

                src_cool = (
                    current_time.timestamp() - last_seen_time.get(src_acc, 0) > 130
                )
                dst_cool = (
                    current_time.timestamp() - last_seen_time.get(dst_acc, 0) > 130
                )
                degree_ok = out_degree[src_acc] < 2 and in_degree[dst_acc] < 2

                if src_acc != dst_acc and degree_ok and src_cool and dst_cool:
                    break

                src_idx = self._rng.randrange(account_count)
                dst_idx = (src_idx + self._rng.randint(1, account_count - 1)) % account_count
                attempts += 1

            src_profile = self._account_pool[src_idx]
            dst_profile = self._account_pool[dst_idx]

            in_degree[dst_profile["account"]] += 1
            out_degree[src_profile["account"]] += 1
            last_seen_time[src_profile["account"]] = current_time.timestamp()
            last_seen_time[dst_profile["account"]] = current_time.timestamp()

            amount = self._generate_normal_amount()
            status = "completed" if self._rng.random() < 0.98 else "pending"

            tx = Transaction(
                transaction_id=tx_id,
                timestamp=self._format_timestamp(current_time),
                source_account=src_profile["account"],
                destination_account=dst_profile["account"],
                amount=amount,
                currency="INR",
                device_id=src_profile["device"],
                ip_address=src_profile["ip"],
                status=status,
            )
            transactions.append(tx.to_dict())

        return transactions

    def generate_mule_transactions(
        self, count: int, prefix: str = "MULE"
    ) -> list[dict[str, Any]]:
        """Generate normal transactions followed by a rapid multi-hop mule sequence.

        Properties:
        - Normal transactions establish baseline traffic and median amounts.
        - A suspicious rapid multi-hop sequence follows chronologically.
        - Intermediate mule accounts forward 95%-98% of received funds within seconds.
        - Consecutive transactions occur within < 2 minutes (triggering velocity)
          and < 5 minutes (triggering rapid multi-hop graph paths).
        - Anomaly type detected by ARGUS graph detector: 'rapid_mule_fund_movement'.
        """
        if count < 2:
            raise ValueError(f"Mule scenario requires at least 2 transactions, received {count}")

        # Determine split between normal background and mule sequence:
        # A multi-hop chain needs at least 2 hops (3 accounts).
        # We target a 3-hop or 4-hop chain (ARGUS find_temporal_paths max_depth is 4).
        if count == 2:
            normal_count = 0
            mule_hops = 2
        elif count == 3:
            normal_count = 0
            mule_hops = 3
        elif count == 4:
            normal_count = 1
            mule_hops = 3
        else:
            mule_hops = 4 if count >= 8 else 3
            normal_count = count - mule_hops

        transactions: list[dict[str, Any]] = []
        current_time = self.base_time

        # 1. Normal background transactions
        if normal_count > 0:
            normal_batch = self.generate_normal_transactions(normal_count, prefix=prefix)
            transactions.extend(normal_batch)
            last_dt = datetime.fromisoformat(normal_batch[-1]["timestamp"].replace("Z", "+00:00"))
            current_time = last_dt.fromtimestamp(
                last_dt.timestamp() + self._rng.randint(30, 60),
                tz=timezone.utc,
            )

        # 2. Mule sequence
        # Originator -> Mule 1 -> Mule 2 -> Mule 3 -> Mule 4 (Cashout/Off-ramp)
        mule_accounts = [
            f"ACC-MULE-{idx:02d}" for idx in range(mule_hops + 1)
        ]
        mule_devices = [
            f"DEV-MULE-{idx:02d}" for idx in range(mule_hops + 1)
        ]
        mule_ips = [
            f"185.220.101.{(idx * 17) % 200 + 10}" for idx in range(mule_hops + 1)
        ]

        # Initial suspicious large transfer
        # Typically 75,000 to 95,000 INR (well above the normal ~1,000 INR median)
        current_amount = round(self._rng.uniform(80000.0, 95000.0), 2)

        start_tx_idx = normal_count
        for hop in range(mule_hops):
            tx_id = f"{prefix}-{100001 + start_tx_idx + hop}"
            src = mule_accounts[hop]
            dst = mule_accounts[hop + 1]

            # Fast forwarding: 30 to 45 seconds between hops
            if hop > 0:
                current_time = current_time.fromtimestamp(
                    current_time.timestamp() + self._rng.randint(30, 45),
                    tz=timezone.utc,
                )
                # Forward 95% - 98% of received funds (retaining mule cut)
                forward_ratio = self._rng.uniform(0.95, 0.98)
                current_amount = round(current_amount * forward_ratio, 2)

            status = "completed"

            tx = Transaction(
                transaction_id=tx_id,
                timestamp=self._format_timestamp(current_time),
                source_account=src,
                destination_account=dst,
                amount=current_amount,
                currency="INR",
                device_id=mule_devices[hop],
                ip_address=mule_ips[hop],
                status=status,
            )
            transactions.append(tx.to_dict())

        return transactions

    def generate(self, scenario: str, count: int) -> list[dict[str, Any]]:
        """Generate transactions for the requested scenario."""
        if scenario == "normal":
            return self.generate_normal_transactions(count)
        elif scenario == "mule":
            return self.generate_mule_transactions(count)
        else:
            raise ValueError(f"Unknown scenario '{scenario}'. Allowed: 'normal', 'mule'")


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    """Parse and validate command line arguments."""
    parser = argparse.ArgumentParser(
        description="ARGUS Synthetic Transaction Simulator (Phase 1)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--scenario",
        choices=["normal", "mule"],
        required=True,
        help="Transaction scenario to generate ('normal' or 'mule')",
    )
    parser.add_argument(
        "--count",
        type=int,
        required=True,
        help="Number of transactions to generate (>= 1 for normal, >= 2 for mule)",
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Target output JSON file path",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional random seed for reproducible generation",
    )

    parsed = parser.parse_args(args)

    if parsed.count < 1:
        parser.error("--count must be greater than or equal to 1")

    if parsed.scenario == "mule" and parsed.count < 2:
        parser.error("--count must be at least 2 for the 'mule' scenario")

    return parsed


def main(args: list[str] | None = None) -> int:
    """CLI entry point for transaction simulation."""
    parsed = parse_args(args)

    simulator = TransactionSimulator(seed=parsed.seed)
    transactions = simulator.generate(scenario=parsed.scenario, count=parsed.count)

    out_path = Path(parsed.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(transactions, f, indent=2)
        f.write("\n")

    print(
        f"[ARGUS Simulator] Successfully generated {len(transactions)} {parsed.scenario} "
        f"transactions -> {out_path} (seed={parsed.seed})",
        file=sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
