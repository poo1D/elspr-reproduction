import networkx as nx
import pytest

from elspr.graph import analyze_scc, dataset_non_transitivity, tarjan_scc


def linear_graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_edges_from([("c", "b"), ("c", "a"), ("b", "a")])
    return graph


def cycle_graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_edges_from([("a", "b"), ("b", "c"), ("c", "a")])
    return graph


def all_tie_graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    for left, right in [("a", "b"), ("a", "c"), ("b", "c")]:
        graph.add_edge(left, right)
        graph.add_edge(right, left)
    return graph


def test_case_a_strict_linear_preference() -> None:
    analysis = analyze_scc(linear_graph())

    assert analysis.components == (("a",), ("b",), ("c",))
    assert analysis.non_transitive_components == ()
    assert analysis.rho_non_trans == 0.0
    assert analysis.max_scc_size == 1


def test_case_b_three_node_cycle() -> None:
    analysis = analyze_scc(cycle_graph())

    assert analysis.components == (("a", "b", "c"),)
    assert analysis.non_transitive_components == (("a", "b", "c"),)
    assert analysis.non_transitive_nodes == 3
    assert analysis.rho_non_trans == 1.0


def test_case_c_all_tie_is_not_non_transitive() -> None:
    analysis = analyze_scc(all_tie_graph())

    assert analysis.components == (("a", "b", "c"),)
    assert analysis.non_transitive_components == ()
    assert analysis.rho_non_trans == 0.0


def test_two_node_cycle_is_not_non_transitive() -> None:
    graph = nx.DiGraph([("a", "b"), ("b", "a")])

    analysis = analyze_scc(graph)

    assert analysis.components == (("a", "b"),)
    assert analysis.non_transitive_components == ()


def test_position_bias_tie_inside_cycle_remains_non_transitive() -> None:
    graph = cycle_graph()
    graph.add_edge("b", "a")

    analysis = analyze_scc(graph)

    assert analysis.non_transitive_components == (("a", "b", "c"),)


def test_dataset_ratio_is_vertex_weighted_not_question_average() -> None:
    two_node_linear = nx.DiGraph([("b", "a")])

    ratio = dataset_non_transitivity([cycle_graph(), two_node_linear])

    assert ratio == pytest.approx(3 / 5)


def test_empty_graph_and_dataset_have_zero_ratio() -> None:
    analysis = analyze_scc(nx.DiGraph())

    assert analysis.rho_non_trans == 0.0
    assert analysis.max_scc_size == 0
    assert dataset_non_transitivity([]) == 0.0


def test_tarjan_matches_networkx_partition() -> None:
    graph = nx.DiGraph(
        [
            ("a", "b"),
            ("b", "a"),
            ("b", "c"),
            ("c", "d"),
            ("d", "c"),
            ("d", "e"),
        ]
    )

    ours = {frozenset(component) for component in tarjan_scc(graph)}
    reference = {
        frozenset(component) for component in nx.strongly_connected_components(graph)
    }

    assert ours == reference


def test_tarjan_rejects_non_string_nodes() -> None:
    graph = nx.DiGraph([(1, 2)])

    with pytest.raises(TypeError, match="must be strings"):
        tarjan_scc(graph)
