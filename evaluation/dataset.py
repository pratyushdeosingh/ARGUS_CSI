"""Synthetic controls, mule/scam positives and payroll hard negatives.

No third-party customer data. Splits have separate accounts, seeds and dates.
This generator is evaluation input, not a claim of representative banking data.
"""

from datetime import datetime, timedelta, timezone
import random


def generate_split(split, seed, cases_per_segment=8):
    rng = random.Random(seed)
    day = {"validation": 20, "test": 21}[split]
    cases = []
    for segment in ["normal", "mule", "scam", "payroll_control"]:
        for index in range(cases_per_segment):
            prefix = f"{split}-{seed}-{segment}-{index}"
            currency = "INR" if index % 2 == 0 else "USD"
            amount = rng.uniform(500, 1800) if currency == "INR" else rng.uniform(8, 30)
            base = datetime(2026, 10, day, 12, tzinfo=timezone.utc)
            def tx(identifier, source, destination, amount, seconds):
                return {"transaction_id": prefix + "-" + identifier,
                        "timestamp": (base + timedelta(seconds=seconds)).isoformat(),
                        "source_account": prefix + source, "destination_account": prefix + destination,
                        "amount": round(amount, 2), "currency": currency,
                        "device_id": prefix + "-known-device", "ip_address": "198.51.100.10",
                        "status": "completed"}
            baseline = [tx(f"BASE-{n}", "-A", f"-PAYEE-{n}", amount * rng.uniform(0.8, 1.2), -86400 - n * 3600)
                        for n in range(6)]
            if segment == "normal":
                current = [tx(f"PAY-{n}", "-A", "-PAYEE-0", amount * rng.uniform(0.8, 1.2), n * 900) for n in range(3)]
            elif segment == "mule":
                initial = amount * rng.uniform(30, 60)
                current = [tx(f"PAY-{n}", f"-NODE-{n}", f"-NODE-{n+1}", initial * 0.96 ** n, n * 35) for n in range(4)]
            elif segment == "scam":
                current = [tx(f"PAY-{n}", "-A", f"-UNKNOWN-{n}", amount * 9, n * 20) for n in range(5)]
            else:
                # Payroll is legitimate by construction but resembles scam fan-out.
                current = [tx(f"PAY-{n}", "-A", f"-PAYEE-{n}", amount, n * 20) for n in range(5)]
            cases.append({"sample_id": prefix, "split": split, "segment": segment,
                          "label": int(segment in {"mule", "scam"}),
                          "transactions": current, "baseline_transactions": baseline})
    return cases
