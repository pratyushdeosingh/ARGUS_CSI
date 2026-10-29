from hashlib import sha256
from pathlib import Path

import torch

from scripts.train_tgnn import train
from tgnn import TGNN


def test_offline_training_writes_reviewable_checkpoint_and_provenance(tmp_path, normal_transactions):
    root = Path(__file__).resolve().parents[3]
    output = tmp_path / "experiment.pt"
    manifest = train(root / "data/normal/transactions.json", root / "data/attack/transactions.json", output, epochs=2)
    assert manifest["checkpoint_sha256"] == sha256(output.read_bytes()).hexdigest()
    assert manifest["validation_status"] == "not_evaluated"
    trained = TGNN()
    trained.load_state_dict(torch.load(output, weights_only=True))
    untrained = TGNN()
    assert any(not torch.equal(trained.state_dict()[key], value) for key, value in untrained.state_dict().items())
    with torch.no_grad():
        assert 0 <= trained(normal_transactions)[0].item() <= 1
    assert output.with_suffix(".manifest.json").is_file()
