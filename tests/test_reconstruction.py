import networkx as nx

from elspr.graph import reconstruct_sccs, tie_quotient_graph


def unequal_cycle_graph() -> nx.DiGraph:
    return nx.DiGraph(
        [
            ("a", "b"),
            ("b", "c"),
            ("c", "a"),
            ("d", "a"),
            ("b", "d"),
            ("d", "c"),
        ]
    )


def test_case_e_reconstruction_ranks_original_global_indegree() -> None:
    graph = unequal_cycle_graph()

    result = reconstruct_sccs(graph)

    assert result.original_in_degree == {"a": 2, "b": 1, "c": 2, "d": 1}
    assert set(result.graph.edges) == {
        ("a", "c"),
        ("c", "a"),
        ("b", "d"),
        ("d", "b"),
        ("b", "a"),
        ("b", "c"),
        ("d", "a"),
        ("d", "c"),
    }
    assert result.tie_classes == (("a", "c"), ("b", "d"))
    assert set(result.quotient_graph.edges) == {(("b", "d"), ("a", "c"))}
    assert nx.is_directed_acyclic_graph(result.quotient_graph)


def test_equal_indegree_cycle_becomes_one_tie_class() -> None:
    graph = nx.DiGraph([("a", "b"), ("b", "c"), ("c", "a")])

    result = reconstruct_sccs(graph)

    assert result.tie_classes == (("a", "b", "c"),)
    assert result.quotient_graph.number_of_edges() == 0
    assert all(
        result.graph.has_edge(left, right)
        for left in graph
        for right in graph
        if left != right
    )


def test_inter_scc_edges_are_preserved() -> None:
    graph = nx.DiGraph([("c", "b"), ("c", "a"), ("b", "a")])

    result = reconstruct_sccs(graph)

    assert set(result.graph.edges) == set(graph.edges)
    assert result.original_components == (("a",), ("b",), ("c",))
    assert nx.is_directed_acyclic_graph(result.quotient_graph)


def test_reconstruction_does_not_mutate_original() -> None:
    graph = unequal_cycle_graph()
    original_edges = set(graph.edges)
    original_attributes = {
        (source, target): dict(attributes)
        for source, target, attributes in graph.edges(data=True)
    }

    reconstruct_sccs(graph)

    assert set(graph.edges) == original_edges
    assert {
        (source, target): dict(attributes)
        for source, target, attributes in graph.edges(data=True)
    } == original_attributes


def test_tie_quotient_preserves_isolated_nodes() -> None:
    graph = nx.DiGraph()
    graph.add_nodes_from(["a", "b"])

    classes, quotient = tie_quotient_graph(graph)

    assert classes == (("a",), ("b",))
    assert set(quotient.nodes) == {("a",), ("b",)}
    assert quotient.number_of_edges() == 0


def test_reconstructed_edges_are_auditable() -> None:
    result = reconstruct_sccs(unequal_cycle_graph())

    assert all(data["reconstructed"] for *_, data in result.graph.edges(data=True))
    assert {data["relation"] for *_, data in result.graph.edges(data=True)} == {
        "reconstructed",
        "tie",
    }
