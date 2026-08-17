"""Loads the canonical normal and attack fixtures used by the demo."""

import json
from pathlib import Path

from .models import GraphSignal, SystemSignal, Transaction


ROOT = Path(__file__).resolve().parents[2]


def _load_json(relative_path: str) -> object:
    with (ROOT / relative_path).open(encoding="utf-8") as source:
        return json.load(source)


def load_normal_transactions() -> list[Transaction]:
    return [
        Transaction.model_validate(item)
        for item in _load_json("data/normal/transactions.json")
    ]


def load_attack_transactions() -> list[Transaction]:
    return [
        Transaction.model_validate(item)
        for item in _load_json("data/attack/transactions.json")
    ]


def load_mock_signals() -> tuple[GraphSignal, SystemSignal]:
    graph = GraphSignal.model_validate(
        _load_json("data/attack/mock-graph-signal.json")
    )
    system = SystemSignal.model_validate(
        _load_json("data/attack/mock-system-signal.json")
    )
    return graph, system
