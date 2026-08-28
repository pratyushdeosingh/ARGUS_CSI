"""Tests for the TGNN model behavior, including neighborhood aggregation and temporal ordering."""

from datetime import datetime, UTC
import pytest
import torch

from models import Transaction, TransactionStatus
from tgnn import TGNN


def test_tgnn_instantiation():
    """Verify that the TGNN model can be successfully instantiated and has the expected layers."""
    model = TGNN()
    assert model is not None
    assert isinstance(model.proj, torch.nn.Linear)
    assert isinstance(model.gru_cell, torch.nn.GRUCell)
    assert isinstance(model.risk_fc, torch.nn.Linear)


def test_tgnn_forward_pass_empty():
    """Verify that an empty list of transactions returns zero risk score and empty details."""
    model = TGNN()
    score, node_scores = model([])
    assert score.item() == 0.0
    assert node_scores == {}


def test_tgnn_forward_pass_nonempty(normal_transactions):
    """Verify that the forward pass runs on transactions, returning valid risk scores in [0, 1]."""
    model = TGNN()
    score, node_scores = model(normal_transactions)
    assert isinstance(score.item(), float)
    assert 0.0 <= score.item() <= 1.0
    assert len(node_scores) > 0
    for node, val in node_scores.items():
        assert 0.0 <= val <= 1.0


def test_tgnn_neighborhood_influence():
    """Verify that changing a node's neighbor graph structure affects its risk score."""
    model = TGNN()
    model.eval()

    t1 = datetime(2026, 8, 17, 15, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 8, 17, 15, 1, 0, tzinfo=UTC)

    # Transaction Set 1: Just A -> B
    tx1 = Transaction(
        transaction_id="TX-1",
        timestamp=t1,
        source_account="ACC-A",
        destination_account="ACC-B",
        amount=1000.0,
        currency="INR",
        device_id="DEV-1",
        ip_address="127.0.0.1",
        status=TransactionStatus.COMPLETED,
    )

    # Transaction Set 2: A -> B and C -> B
    tx2 = Transaction(
        transaction_id="TX-2",
        timestamp=t2,
        source_account="ACC-C",
        destination_account="ACC-B",
        amount=5000.0,
        currency="INR",
        device_id="DEV-2",
        ip_address="127.0.0.2",
        status=TransactionStatus.COMPLETED,
    )

    with torch.no_grad():
        _, scores1 = model([tx1])
        _, scores2 = model([tx1, tx2])

    assert "ACC-B" in scores1
    assert "ACC-B" in scores2
    # The score of ACC-B must change when its neighborhood structure changes
    assert scores1["ACC-B"] != scores2["ACC-B"]


def test_tgnn_temporal_ordering_influence():
    """Verify that changing the temporal ordering/sequence of transactions affects the risk output."""
    model = TGNN()
    model.eval()

    t1 = datetime(2026, 8, 17, 15, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 8, 17, 15, 5, 0, tzinfo=UTC)

    # Sequence 1: tx1 (t1) happens before tx2 (t2)
    tx1 = Transaction(
        transaction_id="TX-1",
        timestamp=t1,
        source_account="ACC-A",
        destination_account="ACC-B",
        amount=1000.0,
        currency="INR",
        device_id="DEV-1",
        ip_address="127.0.0.1",
        status=TransactionStatus.COMPLETED,
    )

    tx2 = Transaction(
        transaction_id="TX-2",
        timestamp=t2,
        source_account="ACC-B",
        destination_account="ACC-C",
        amount=1000.0,
        currency="INR",
        device_id="DEV-2",
        ip_address="127.0.0.2",
        status=TransactionStatus.COMPLETED,
    )

    # Sequence 2: tx2 (t1) happens before tx1 (t2) [reversed temporal flow]
    tx2_reversed = Transaction(
        transaction_id="TX-2",
        timestamp=t1,
        source_account="ACC-B",
        destination_account="ACC-C",
        amount=1000.0,
        currency="INR",
        device_id="DEV-2",
        ip_address="127.0.0.2",
        status=TransactionStatus.COMPLETED,
    )

    tx1_reversed = Transaction(
        transaction_id="TX-1",
        timestamp=t2,
        source_account="ACC-A",
        destination_account="ACC-B",
        amount=1000.0,
        currency="INR",
        device_id="DEV-1",
        ip_address="127.0.0.1",
        status=TransactionStatus.COMPLETED,
    )

    with torch.no_grad():
        _, scores1 = model([tx1, tx2])
        _, scores2 = model([tx2_reversed, tx1_reversed])

    assert "ACC-B" in scores1
    assert "ACC-B" in scores2
    # The score of ACC-B must change when the temporal order of transactions changes
    assert scores1["ACC-B"] != scores2["ACC-B"]
