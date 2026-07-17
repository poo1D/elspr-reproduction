"""Reconstruct SCC internals from original global in-degree rankings."""

from dataclasses import dataclass
from itertools import combinations

import networkx as nx

from elspr.graph.scc import tarjan_scc

TieClass = tuple[str, ...]


class ReconstructionError(ValueError):
    """Raised when reconstruction violates its quotient-DAG invariant."""


@dataclass(frozen=True, slots=True)
class ReconstructionResult:
    """Reconstructed graph and its audit evidence."""

    graph: nx.DiGraph
    original_in_degree: dict[str, int]
    original_components: tuple[tuple[str, ...], ...]
    tie_classes: tuple[TieClass, ...]
    quotient_graph: nx.DiGraph


def tie_quotient_graph(
    graph: nx.DiGraph,
) -> tuple[tuple[TieClass, ...], nx.DiGraph]:
    """Contract reciprocal-edge equivalence classes into quotient nodes."""

    reciprocal = nx.Graph()
    reciprocal.add_nodes_from(graph.nodes)
    reciprocal.add_edges_from(
        (source, target)
        for source, target in graph.edges
        if source != target and graph.has_edge(target, source)
    )
    tie_classes = tuple(
        sorted(
            (
                tuple(sorted(component))
                for component in nx.connected_components(reciprocal)
            ),
            key=lambda item: (item[0], len(item), item),
        )
    )
    class_by_node = {node: tie_class for tie_class in tie_classes for node in tie_class}

    quotient = nx.DiGraph()
    quotient.add_nodes_from(tie_classes)
    for source, target in graph.edges:
        source_class = class_by_node[source]
        target_class = class_by_node[target]
        if source_class != target_class:
            quotient.add_edge(source_class, target_class)
    return tie_classes, quotient


def reconstruct_sccs(graph: nx.DiGraph) -> ReconstructionResult:
    """Replace every SCC's internal edges using original global in-degree."""

    reconstructed = graph.copy()
    original_in_degree = dict(graph.in_degree())
    components = tarjan_scc(graph)

    for component in components:
        internal_edges = [
            (source, target)
            for source, target in reconstructed.edges
            if source in component and target in component
        ]
        reconstructed.remove_edges_from(internal_edges)

        for left, right in combinations(component, 2):
            left_degree = original_in_degree[left]
            right_degree = original_in_degree[right]
            if left_degree > right_degree:
                reconstructed.add_edge(
                    right,
                    left,
                    relation="reconstructed",
                    reconstructed=True,
                )
            elif left_degree < right_degree:
                reconstructed.add_edge(
                    left,
                    right,
                    relation="reconstructed",
                    reconstructed=True,
                )
            else:
                reconstructed.add_edge(
                    left,
                    right,
                    relation="tie",
                    reconstructed=True,
                )
                reconstructed.add_edge(
                    right,
                    left,
                    relation="tie",
                    reconstructed=True,
                )

    tie_classes, quotient = tie_quotient_graph(reconstructed)
    if not nx.is_directed_acyclic_graph(quotient):
        raise ReconstructionError("tie-contracted quotient graph is not a DAG")

    return ReconstructionResult(
        graph=reconstructed,
        original_in_degree=original_in_degree,
        original_components=components,
        tie_classes=tie_classes,
        quotient_graph=quotient,
    )
