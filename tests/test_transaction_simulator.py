"""Automated tests for the ARGUS synthetic transaction simulator."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

from jsonschema import Draft202012Validator, FormatChecker
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "services" / "graph-detector"))
sys.path.insert(0, str(REPO_ROOT))

from detector import GraphDetector
from graph_models import Transaction as GraphTransaction
from transaction_simulator import TransactionSimulator, main, parse_args


class TestTransactionSimulator(unittest.TestCase):
    """Test suite verifying schema validity, determinism, and detector compatibility."""

    @classmethod
    def setUpClass(cls) -> None:
        schema_path = REPO_ROOT / "contracts" / "transaction.schema.json"
        cls.schema = json.loads(schema_path.read_text(encoding="utf-8"))
        cls.validator = Draft202012Validator(cls.schema, format_checker=FormatChecker())

    def test_schema_conformance_for_normal_scenario(self) -> None:
        """Every normal transaction must satisfy the shared JSON schema and Pydantic model."""
        sim = TransactionSimulator(seed=101)
        batch = sim.generate_normal_transactions(count=25)

        self.assertEqual(len(batch), 25)
        for item in batch:
            # Validate against contracts/transaction.schema.json
            self.validator.validate(item)
            # Validate against services/graph-detector/graph_models.py
            model = GraphTransaction.model_validate(item)
            self.assertEqual(model.currency, "INR")
            self.assertGreater(model.amount, 0)

    def test_schema_conformance_for_mule_scenario(self) -> None:
        """Every mule transaction must satisfy the shared JSON schema and Pydantic model."""
        sim = TransactionSimulator(seed=202)
        batch = sim.generate_mule_transactions(count=20)

        self.assertEqual(len(batch), 20)
        for item in batch:
            self.validator.validate(item)
            model = GraphTransaction.model_validate(item)
            self.assertEqual(model.currency, "INR")
            self.assertGreater(model.amount, 0)

    def test_unique_transaction_ids(self) -> None:
        """Transaction IDs within any generated batch must be strictly unique and scenario-specific."""
        sim = TransactionSimulator(seed=303)
        normal_batch = sim.generate_normal_transactions(count=50)
        mule_batch = sim.generate_mule_transactions(count=50)

        normal_ids = [tx["transaction_id"] for tx in normal_batch]
        mule_ids = [tx["transaction_id"] for tx in mule_batch]

        # Unique within each scenario
        self.assertEqual(len(normal_ids), len(set(normal_ids)))
        self.assertEqual(len(mule_ids), len(set(mule_ids)))

        # Scenario-specific prefixes
        self.assertTrue(all(tx_id.startswith("NORM-") for tx_id in normal_ids))
        self.assertTrue(all(tx_id.startswith("MULE-") for tx_id in mule_ids))

        # Disjoint across scenarios
        self.assertTrue(set(normal_ids).isdisjoint(set(mule_ids)))

    def test_scenarios_produce_different_signal_ids(self) -> None:
        """Normal and mule scenarios must produce different graph detector signal IDs."""
        sim = TransactionSimulator(seed=42)
        normal_batch = sim.generate("normal", count=20)
        mule_batch = sim.generate("mule", count=20)

        normal_txs = [GraphTransaction.model_validate(tx) for tx in normal_batch]
        mule_txs = [GraphTransaction.model_validate(tx) for tx in mule_batch]

        detector = GraphDetector()
        normal_signal = detector.analyze(normal_txs)
        mule_signal = detector.analyze(mule_txs)

        self.assertNotEqual(
            normal_signal.signal_id,
            mule_signal.signal_id,
            "Normal and mule scenarios must produce distinct signal IDs",
        )
        self.assertTrue(normal_signal.signal_id.startswith("GRAPH-"))
        self.assertTrue(mule_signal.signal_id.startswith("GRAPH-"))


    def test_utc_timestamps_and_chronological_ordering(self) -> None:
        """Timestamps must be ISO 8601 UTC with 'Z' and monotonically advancing."""
        sim = TransactionSimulator(seed=404)

        for scenario in ("normal", "mule"):
            batch = sim.generate(scenario=scenario, count=15)
            timestamps: list[datetime] = []

            for item in batch:
                ts_str = item["timestamp"]
                self.assertTrue(ts_str.endswith("Z"), f"Timestamp {ts_str} must end with Z")
                # Parse to ensure it is valid UTC date-time
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                self.assertEqual(dt.tzinfo, timezone.utc)
                self.assertEqual(dt.utcoffset().total_seconds(), 0)
                timestamps.append(dt)

            for prev_dt, next_dt in zip(timestamps, timestamps[1:]):
                self.assertLessEqual(
                    prev_dt,
                    next_dt,
                    f"Timestamps must be chronological: {prev_dt} <= {next_dt}",
                )

    def test_positive_amounts(self) -> None:
        """All transaction amounts must be strictly greater than 0."""
        sim = TransactionSimulator(seed=505)
        for scenario in ("normal", "mule"):
            batch = sim.generate(scenario=scenario, count=20)
            for item in batch:
                self.assertGreater(item["amount"], 0.0)

    def test_no_self_transfers(self) -> None:
        """Source and destination accounts must never be identical."""
        sim = TransactionSimulator(seed=606)
        for scenario in ("normal", "mule"):
            batch = sim.generate(scenario=scenario, count=30)
            for item in batch:
                self.assertNotEqual(
                    item["source_account"],
                    item["destination_account"],
                    f"Self-transfer detected in {item['transaction_id']}",
                )

    def test_deterministic_results_with_fixed_seed(self) -> None:
        """Identical seeds must yield identical transaction batches."""
        sim1 = TransactionSimulator(seed=777)
        sim2 = TransactionSimulator(seed=777)

        batch1 = sim1.generate("normal", count=15)
        batch2 = sim2.generate("normal", count=15)
        self.assertEqual(batch1, batch2)

        mule1 = sim1.generate("mule", count=12)
        mule2 = sim2.generate("mule", count=12)
        self.assertEqual(mule1, mule2)

    def test_different_seeds_yield_distinct_results(self) -> None:
        """Different seeds must produce different transaction patterns."""
        sim1 = TransactionSimulator(seed=111)
        sim2 = TransactionSimulator(seed=222)

        batch1 = sim1.generate("normal", count=10)
        batch2 = sim2.generate("normal", count=10)
        self.assertNotEqual(batch1, batch2)

    def test_normal_scenario_risk_score(self) -> None:
        """Normal scenario transactions must evaluate to low/zero risk in GraphDetector."""
        sim = TransactionSimulator(seed=808)
        batch = sim.generate("normal", count=20)
        transactions = [GraphTransaction.model_validate(tx) for tx in batch]

        detector = GraphDetector()
        signal = detector.analyze(transactions)

        self.assertLessEqual(signal.risk_score, 0.15)
        self.assertIn(
            signal.anomaly_type,
            ("no_suspicious_activity", "low_risk_activity"),
        )
        self.assertEqual(signal.suspicious_accounts, [])

    def test_mule_scenario_triggers_graph_detector(self) -> None:
        """Mule scenario must trigger rapid_mule_fund_movement in GraphDetector."""
        sim = TransactionSimulator(seed=909)
        batch = sim.generate("mule", count=20)
        transactions = [GraphTransaction.model_validate(tx) for tx in batch]

        detector = GraphDetector()
        signal = detector.analyze(transactions)

        self.assertGreaterEqual(signal.risk_score, 0.70)
        self.assertEqual(signal.anomaly_type, "rapid_mule_fund_movement")
        self.assertTrue(any("ACC-MULE" in acc for acc in signal.suspicious_accounts))
        self.assertTrue(any("crossed" in r for r in signal.reasons))

    def test_mule_minimum_count_boundary(self) -> None:
        """Mule scenario supports count=2 and count=3 minimum sequences."""
        sim = TransactionSimulator(seed=12)
        batch_2 = sim.generate("mule", count=2)
        self.assertEqual(len(batch_2), 2)
        self.assertEqual(batch_2[0]["destination_account"], batch_2[1]["source_account"])

        batch_3 = sim.generate("mule", count=3)
        self.assertEqual(len(batch_3), 3)

    def test_invalid_cli_arguments(self) -> None:
        """CLI argument parser must reject invalid scenarios, counts, or missing arguments."""
        # Non-positive count
        with self.assertRaises(SystemExit):
            parse_args(["--scenario", "normal", "--count", "0", "--output", "out.json"])

        # Negative count
        with self.assertRaises(SystemExit):
            parse_args(["--scenario", "normal", "--count", "-5", "--output", "out.json"])

        # Mule scenario with count < 2
        with self.assertRaises(SystemExit):
            parse_args(["--scenario", "mule", "--count", "1", "--output", "out.json"])

        # Invalid scenario
        with self.assertRaises(SystemExit):
            parse_args(["--scenario", "unknown", "--count", "10", "--output", "out.json"])

        # Missing required parameter
        with self.assertRaises(SystemExit):
            parse_args(["--count", "10", "--output", "out.json"])

    def test_cli_end_to_end_file_generation(self) -> None:
        """CLI main() must write valid JSON and create parent directories if missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "nested" / "dir" / "test_output.json"
            exit_code = main([
                "--scenario",
                "normal",
                "--count",
                "8",
                "--output",
                str(out_file),
                "--seed",
                "42",
            ])
            self.assertEqual(exit_code, 0)
            self.assertTrue(out_file.exists())

            data = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertEqual(len(data), 8)
            for item in data:
                self.validator.validate(item)


if __name__ == "__main__":
    unittest.main()
