import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from detector import GraphDetector


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_attack_signal_validates_against_shared_json_schema(normal_transactions, attack_transactions):
    schema = json.loads((REPOSITORY_ROOT / "contracts/graph-signal.schema.json").read_text(encoding="utf-8"))
    signal = GraphDetector(normal_transactions).analyze(attack_transactions)
    payload = json.loads(signal.model_dump_json())

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
