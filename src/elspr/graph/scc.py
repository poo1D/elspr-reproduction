"""Deterministic Tarjan SCC analysis and non-transitivity metrics."""

from collections.abc import Iterable
from dataclasses import dataclass
from itertools import combinations

import networkx as nx


@dataclass(frozen=True, slots=True)
class SCCAnalysis:
    """Per-question SCC and non-transitivity summary."""

    components: tuple[tuple[str, ...], ...]
    non_transitive_components: tuple[tuple[str, ...], ...]
    total_nodes: int
    non_transitive_nodes: int
    rho_non_trans: float
    max_scc_size: int


def tarjan_scc(graph: nx.DiGraph) -> tuple[tuple[str, ...], ...]:
    """Return strongly connected components using Tarjan's algorithm.

    Nodes and outgoing neighbors must be strings. Sorting traversal inputs and
    outputs makes saved analysis stable across runs.
    """

    if any(not isinstance(node, str) for node in graph):
        raise TypeError("Tarjan SCC nodes must be strings")

    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[tuple[str, ...]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)

        for neighbor in sorted(graph.successors(node)):
            if neighbor not in indices:
                visit(neighbor)
                lowlinks[node] = min(lowlinks[node], lowlinks[neighbor])
            elif neighbor in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[neighbor])

        if lowlinks[node] != indices[node]:
            return

        component: list[str] = []
        while True:
            member = stack.pop()
            on_stack.remove(member)
            component.append(member)
            if member == node:
                break
        components.append(tuple(sorted(component)))

    for node in sorted(graph.nodes):
        if node not in indices:
            visit(node)

    return tuple(sorted(components, key=lambda item: (item[0], len(item), item)))


def is_non_transitive_component(
    graph: nx.DiGraph,
    component: Iterable[str],
) -> bool:
    """Return whether an SCC meets the paper's non-transitive definition."""

    nodes = tuple(sorted(component))
    if len(nodes) <= 2:
        return False
    return any(
        not (graph.has_edge(left, right) and graph.has_edge(right, left))
        for left, right in combinations(nodes, 2)
    )


def analyze_scc(graph: nx.DiGraph) -> SCCAnalysis:
    """Analyze one question graph."""

    components = tarjan_scc(graph)
    non_transitive = tuple(
        component
        for component in components
        if is_non_transitive_component(graph, component)
    )
    total_nodes = graph.number_of_nodes()
    non_transitive_nodes = sum(len(component) for component in non_transitive)
    rho = non_transitive_nodes / total_nodes if total_nodes else 0.0
    max_scc_size = max((len(component) for component in components), default=0)
    return SCCAnalysis(
        components=components,
        non_transitive_components=non_transitive,
        total_nodes=total_nodes,
        non_transitive_nodes=non_transitive_nodes,
        rho_non_trans=rho,
        max_scc_size=max_scc_size,
    )


def dataset_non_transitivity(graphs: Iterable[nx.DiGraph]) -> float:
    """Compute the vertex-weighted non-transitivity ratio over questions."""

    total_nodes = 0
    non_transitive_nodes = 0
    for graph in graphs:
        analysis = analyze_scc(graph)
        total_nodes += analysis.total_nodes
        non_transitive_nodes += analysis.non_transitive_nodes
    return non_transitive_nodes / total_nodes if total_nodes else 0.0
