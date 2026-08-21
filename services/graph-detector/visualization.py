"""Convert a transaction graph into Cytoscape-compatible elements."""

from graph_builder import build_graph
from graph_models import (
    Transaction,
    VisualizationEdge,
    VisualizationEdgeData,
    VisualizationNode,
    VisualizationNodeData,
    VisualizationResponse,
)


def to_cytoscape(
    transactions: list[Transaction],
    *,
    suspicious_accounts: set[str] | None = None,
    suspicious_transactions: set[str] | None = None,
) -> VisualizationResponse:
    suspicious_accounts = suspicious_accounts or set()
    suspicious_transactions = suspicious_transactions or set()
    graph = build_graph(transactions)
    nodes = []
    for account in sorted(graph.nodes):
        total_in = sum(data["amount"] for _, _, data in graph.in_edges(account, data=True))
        total_out = sum(data["amount"] for _, _, data in graph.out_edges(account, data=True))
        nodes.append(
            VisualizationNode(
                data=VisualizationNodeData(
                    id=account,
                    label=account,
                    suspicious=account in suspicious_accounts,
                    total_in=total_in,
                    total_out=total_out,
                )
            )
        )

    edges = []
    for source, target, key, data in sorted(
        graph.edges(keys=True, data=True), key=lambda item: (item[3]["timestamp"], item[2])
    ):
        transaction = data["transaction"]
        edges.append(
            VisualizationEdge(
                data=VisualizationEdgeData(
                    id=key,
                    source=source,
                    target=target,
                    transaction_id=transaction.transaction_id,
                    amount=transaction.amount,
                    currency=transaction.currency,
                    timestamp=transaction.timestamp,
                    suspicious=transaction.transaction_id in suspicious_transactions,
                )
            )
        )
    return VisualizationResponse(nodes=nodes, edges=edges)
