"""Temporal Graph Neural Network for financial transaction anomaly detection."""

import logging
from datetime import datetime
import numpy as np
import torch
import torch.nn as nn

from graph_builder import active_transactions, build_graph
from models import Transaction

logger = logging.getLogger(__name__)


class TGNN(nn.Module):
    """A lightweight Temporal Graph Neural Network (TGNN).

    Performs:
    1. Node feature construction from batch transaction volume.
    2. Linear projection of node features.
    3. Neighbor aggregation (message passing) over the transaction graph.
    4. Combine self + neighbor features with a non-linear activation (ReLU).
    5. Chronological temporal update of node states using a GRUCell and time-deltas.
    6. Sigmoid projection to individual node anomaly risk scores.
    """

    def __init__(self, input_dim: int = 4, hidden_dim: int = 8):
        super().__init__()
        # Set manual seed for reproducibility of initial weights
        torch.manual_seed(42)
        self.hidden_dim = hidden_dim

        # 1. Linear projection layer
        self.proj = nn.Linear(input_dim, hidden_dim)

        # 2. Layer to combine self representation and neighbor message
        self.combine_fc = nn.Linear(hidden_dim * 2, hidden_dim)

        # 3. Recurrent state for temporal update
        # Inputs: counterpart hidden state (hidden_dim), transaction amount log (1), time delta log (1)
        self.gru_cell = nn.GRUCell(input_size=hidden_dim + 2, hidden_size=hidden_dim)

        # 4. Final output layer to compute node risk score
        self.risk_fc = nn.Linear(hidden_dim, 1)

    def forward(self, transactions: list[Transaction]) -> tuple[torch.Tensor, dict[str, float]]:
        """Run the TGNN forward pass on a batch of transactions.

        Args:
            transactions: List of input Transaction models.

        Returns:
            A tuple of (batch_risk_score, node_risk_scores_dict)
        """
        active = active_transactions(transactions)
        if not active:
            return torch.tensor(0.0, dtype=torch.float32), {}

        # 1. Map unique accounts to deterministic node indices
        nodes = sorted(list(set(t.source_account for t in active) | set(t.destination_account for t in active)))
        node_to_idx = {node: i for i, node in enumerate(nodes)}
        num_nodes = len(nodes)

        # 2. Extract initial node features from transaction batch
        X_list = []
        for node in nodes:
            sent_amounts = [t.amount for t in active if t.source_account == node]
            recv_amounts = [t.amount for t in active if t.destination_account == node]
            X_list.append([
                np.log1p(sum(sent_amounts)),
                np.log1p(sum(recv_amounts)),
                float(len(sent_amounts)),
                float(len(recv_amounts))
            ])
        X = torch.tensor(X_list, dtype=torch.float32)

        # 3. Project node features
        h = self.proj(X)

        # 4. Message passing: aggregate neighbors (both incoming and outgoing)
        graph = build_graph(active)
        m_list = []
        for i, node in enumerate(nodes):
            nbrs = list(graph.predecessors(node)) + list(graph.successors(node))
            if nbrs:
                nbr_indices = [node_to_idx[nbr] for nbr in nbrs]
                m_list.append(h[nbr_indices].mean(dim=0))
            else:
                m_list.append(torch.zeros(self.hidden_dim, dtype=torch.float32, device=h.device))
        m = torch.stack(m_list, dim=0)

        # 5. Combine self representation and neighbor messages
        combined = torch.cat([h, m], dim=-1)
        a = torch.relu(self.combine_fc(combined))

        # 6. Chronological temporal update of node states
        # Convert initial states to a dict of individual tensors to avoid in-place tensor modification errors
        h_dict = {i: a[i] for i in range(num_nodes)}

        prev_time = active[0].timestamp
        for tx in active:
            u_idx = node_to_idx[tx.source_account]
            v_idx = node_to_idx[tx.destination_account]

            # Compute time-delta since the previous transaction in the batch
            dt = (tx.timestamp - prev_time).total_seconds()
            prev_time = tx.timestamp

            time_feat = torch.tensor([np.log1p(max(0.0, dt))], dtype=torch.float32)
            amount_feat = torch.tensor([np.log1p(tx.amount)], dtype=torch.float32)

            # Update source node state: receives input from destination node state
            input_u = torch.cat([h_dict[v_idx], amount_feat, time_feat]).unsqueeze(0)
            next_u = self.gru_cell(input_u, h_dict[u_idx].unsqueeze(0)).squeeze(0)

            # Update destination node state: receives input from source node state
            input_v = torch.cat([h_dict[u_idx], amount_feat, time_feat]).unsqueeze(0)
            next_v = self.gru_cell(input_v, h_dict[v_idx].unsqueeze(0)).squeeze(0)

            h_dict[u_idx] = next_u
            h_dict[v_idx] = next_v

        # Stack states to get final node representations
        h_state = torch.stack([h_dict[i] for i in range(num_nodes)], dim=0)

        # 7. Compute individual node risk scores
        node_logits = self.risk_fc(h_state)
        node_risks = torch.sigmoid(node_logits).squeeze(-1)

        # Ensure correct tensor shape for single node edge cases
        if num_nodes == 1:
            node_risks = node_risks.unsqueeze(0)

        # 8. Batch anomaly score is the maximum of individual node risk scores
        batch_risk_score = torch.max(node_risks)

        node_risk_dict = {nodes[i]: float(node_risks[i].item()) for i in range(num_nodes)}
        return batch_risk_score, node_risk_dict


def train_tgnn(
    model: TGNN,
    normal_txs: list[Transaction],
    attack_txs: list[Transaction],
    epochs: int = 60,
    lr: float = 0.02
) -> None:
    """Train the TGNN model to distinguish between normal and attack transactions.

    Uses binary cross-entropy loss and Adam optimizer to update model parameters.
    """
    # Ensure deterministic training behavior
    torch.manual_seed(42)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.BCELoss()

    model.train()
    for epoch in range(epochs):
        optimizer.zero_grad()

        normal_score, _ = model(normal_txs)
        attack_score, _ = model(attack_txs)

        # Target normal: 0.0, Target attack: 1.0
        loss = criterion(normal_score, torch.tensor(0.0, dtype=torch.float32)) + \
               criterion(attack_score, torch.tensor(1.0, dtype=torch.float32))

        loss.backward()
        optimizer.step()

    model.eval()
    logger.info("TGNN model successfully trained on normal and attack batch canonical scenarios.")
