"""Portable collector for deterministic, sanitized telemetry replay."""

import json
from pathlib import Path

from models import RawEvent


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def collect_replay(scenario: str = "attack") -> list[RawEvent]:
    fixture = FIXTURES / f"replay_{scenario}.json"
    if scenario not in {"attack", "normal"} or not fixture.is_file():
        raise ValueError("scenario must be 'attack' or 'normal'")
    with fixture.open(encoding="utf-8") as source:
        payload = json.load(source)
    return [RawEvent.model_validate(item) for item in payload]
