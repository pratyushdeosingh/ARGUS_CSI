"""Reproducible offline TGNN training; never trains inside a request/startup."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/graph-detector"))


def train(normal_path, attack_path, output, epochs=60, learning_rate=0.02):
    import torch
    from graph_models import Transaction
    from tgnn import TGNN, train_tgnn

    if output.resolve() == (ROOT / "services/graph-detector/tgnn_weights.pt").resolve():
        raise ValueError("Train to an experimental output; evaluate and review before replacing the bundled checkpoint")
    normal_data, attack_data = normal_path.read_bytes(), attack_path.read_bytes()
    normal = [Transaction.model_validate(tx) for tx in json.loads(normal_data)]
    attack = [Transaction.model_validate(tx) for tx in json.loads(attack_data)]
    if not normal or not attack:
        raise ValueError("Both labelled training classes must be non-empty")
    if {tx.transaction_id for tx in normal} & {tx.transaction_id for tx in attack}:
        raise ValueError("Training classes contain overlapping transaction IDs")
    model = TGNN()
    train_tgnn(model, normal, attack, epochs=epochs, lr=learning_rate)
    output.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), output)
    manifest = {
        "model": "ARGUS TGNN", "feature_schema": "tgnn-log-volume-count-v1", "seed": 42,
        "epochs": epochs, "learning_rate": learning_rate, "torch_version": str(torch.__version__),
        "normal_sha256": sha256(normal_data).hexdigest(), "attack_sha256": sha256(attack_data).hexdigest(),
        "checkpoint_sha256": sha256(output.read_bytes()).hexdigest(),
        "validation_status": "not_evaluated", "deployment_status": "experimental_not_deployed",
        "note": "Training fit is not held-out evaluation. Keep independent validation/test data separate.",
    }
    output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--normal", type=Path, default=ROOT / "data/normal/transactions.json")
    parser.add_argument("--attack", type=Path, default=ROOT / "data/attack/transactions.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--learning-rate", type=float, default=0.02)
    args = parser.parse_args()
    if not 1 <= args.epochs <= 10000 or not 0 < args.learning_rate <= 1:
        parser.error("epochs must be 1–10000 and learning-rate in (0, 1]")
    print(json.dumps(train(args.normal, args.attack, args.output, args.epochs, args.learning_rate), indent=2))
