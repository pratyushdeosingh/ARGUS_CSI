import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from collector.replay import collect_replay
from models import RawEvent
from normalizer import CANONICAL_SUSPICIOUS_IP, normalize_event, normalize_events
from scorer import score_events
from signal_builder import build_signal

ROOT = Path(__file__).resolve().parents[3]


def test_raw_events_normalize_to_explainable_evidence() -> None:
    process = normalize_event(RawEvent.model_validate({
        "timestamp": "2026-08-17T15:31:16Z", "event_type": "process_exec",
        "process": "payment-worker", "details": {"unexpected_child": True},
    }))
    network = normalize_event(RawEvent.model_validate({
        "timestamp": "2026-08-17T15:31:18Z", "event_type": "network_connect",
        "process": "payment-worker", "details": {"suspicious_destination": True},
    }))
    assert process.indicator == "Unexpected child process"
    assert network.related_ip == CANONICAL_SUSPICIOUS_IP


def test_attack_scores_much_higher_than_normal_activity() -> None:
    attack = normalize_events(collect_replay("attack"))
    normal = normalize_events(collect_replay("normal"))
    assert score_events(attack) == 0.87
    assert score_events(normal) == 0.03
    assert score_events(attack) - score_events(normal) >= 0.70


def test_duplicate_records_do_not_inflate_risk() -> None:
    events = normalize_events(collect_replay("attack"))
    assert score_events(events + events) == score_events(events)


def test_attack_signal_matches_shared_json_schema() -> None:
    signal = build_signal(normalize_events(collect_replay("attack")))
    schema = json.loads((ROOT / "contracts" / "system-signal.schema.json").read_text(encoding="utf-8"))
    payload = signal.model_dump(mode="json")
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    assert payload["signal_id"] == "EBPF-001"
    assert payload["host"] == "payment-node-01"
    assert payload["service"] == "payment-api"
    assert payload["process"] == "payment-worker"
    assert payload["related_ips"] == [CANONICAL_SUSPICIOUS_IP]
    assert payload["timestamp"] == "2026-08-17T15:31:18Z"
