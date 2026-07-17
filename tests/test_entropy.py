import math

import networkx as nx
import pytest

from elspr.graph import average_structural_entropy, structural_entropy


def linear_graph() -> nx.DiGraph:
    return nx.DiGraph([("c", "b"), ("c", "a"), ("b", "a")])


def cycle_graph() -> nx.DiGraph:
    return nx.DiGraph([("a", "b"), ("b", "c"), ("c", "a")])


def all_tie_graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    for left, right in [("a", "b"), ("a", "c"), ("b", "c")]:
        graph.add_edge(left, right)
        graph.add_edge(right, left)
    return graph


def test_linear_singleton_scc_edges_are_excluded() -> None:
    result = structural_entropy(linear_graph())

    assert result.graph_volume == 3
    assert result.h2 == 0.0
    assert result.tau == 0.0
    assert all(item.incoming_external_edges == 0 for item in result.components)


def test_three_cycle_has_maximal_internal_entropy() -> None:
    result = structural_entropy(cycle_graph())

    assert result.h2 == pytest.approx(math.log2(3))
    assert result.tau == pytest.approx(1.0)
    assert result.components[0].volume == 3
    assert result.components[0].incoming_external_edges == 0


def test_all_tie_has_maximal_internal_entropy() -> None:
    result = structural_entropy(all_tie_graph())

    assert result.graph_volume == 6
    assert result.h2 == pytest.approx(math.log2(3))
    assert result.tau == pytest.approx(1.0)


def test_multi_to_singleton_edge_is_retained_in_g() -> None:
    graph = nx.DiGraph([("a", "b"), ("b", "a"), ("a", "c")])

    result = structural_entropy(graph)
    by_nodes = {item.nodes: item for item in result.components}

    assert by_nodes[("c",)].incoming_external_edges == 1
    assert by_nodes[("a", "b")].incoming_external_edges == 0
    expected_h2 = 2 / 3 + math.log2(3) / 3
    assert result.h2 == pytest.approx(expected_h2)
    assert result.tau == pytest.approx(expected_h2 / math.log2(3))


def test_singleton_to_multi_edge_is_retained_in_g() -> None:
    graph = nx.DiGraph([("a", "b"), ("b", "a"), ("c", "a")])

    result = structural_entropy(graph)
    by_nodes = {item.nodes: item for item in result.components}

    assert by_nodes[("a", "b")].incoming_external_edges == 1
    assert by_nodes[("c",)].incoming_external_edges == 0


@pytest.mark.parametrize(
    "graph",
    [
        nx.DiGraph(),
        nx.DiGraph([(1, 1)]),
    ],
)
def test_empty_or_single_node_tau_is_zero(graph: nx.DiGraph) -> None:
    if graph.number_of_nodes() == 1:
        graph.remove_edges_from(list(graph.edges))
        graph = nx.relabel_nodes(graph, {1: "a"})

    result = structural_entropy(graph)

    assert result.tau == 0.0


def test_zero_volume_multi_node_graph_is_zero() -> None:
    graph = nx.DiGraph()
    graph.add_nodes_from(["a", "b", "c"])

    result = structural_entropy(graph)

    assert result.graph_volume == 0
    assert result.h2 == 0.0
    assert result.tau == 0.0


def test_average_tau_is_unweighted_by_graph_size() -> None:
    average = average_structural_entropy([linear_graph(), cycle_graph()])

    assert average == pytest.approx(0.5)


def test_empty_dataset_average_is_zero() -> None:
    assert average_structural_entropy([]) == 0.0
