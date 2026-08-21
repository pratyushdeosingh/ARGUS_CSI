from datetime import timedelta

from graph_builder import build_graph, find_temporal_paths


def test_builds_directed_multigraph(attack_transactions):
    graph = build_graph(attack_transactions)

    assert graph.number_of_nodes() == 4
    assert graph.number_of_edges() == 3
    assert graph.has_edge("ACC-101", "ACC-202", key="TX-1001")


def test_finds_rapid_maximal_path(attack_transactions):
    paths = find_temporal_paths(attack_transactions, max_gap=timedelta(minutes=5))

    assert len(paths) == 1
    assert [item.transaction_id for item in paths[0].transactions] == ["TX-1001", "TX-1002", "TX-1003"]
    assert paths[0].accounts == ("ACC-101", "ACC-202", "ACC-303", "ACC-404")
    assert paths[0].duration_seconds == 70
