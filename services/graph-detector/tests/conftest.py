import json
import sys
from pathlib import Path

import pytest


SERVICE_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = SERVICE_DIR.parent.parent
sys.path.insert(0, str(SERVICE_DIR))


@pytest.fixture
def normal_payload() -> list[dict]:
    return json.loads((REPOSITORY_ROOT / "data/normal/transactions.json").read_text(encoding="utf-8"))


@pytest.fixture
def attack_payload() -> list[dict]:
    return json.loads((REPOSITORY_ROOT / "data/attack/transactions.json").read_text(encoding="utf-8"))


@pytest.fixture
def normal_transactions(normal_payload):
    from graph_models import Transaction

    return [Transaction.model_validate(item) for item in normal_payload]


@pytest.fixture
def attack_transactions(attack_payload):
    from graph_models import Transaction

    return [Transaction.model_validate(item) for item in attack_payload]
