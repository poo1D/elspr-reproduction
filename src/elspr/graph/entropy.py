"""Two-dimensional directed structural entropy from the ELSPR paper."""

import math
import warnings
from collections.abc import Iterable
from dataclasses import dataclass

import networkx as nx

from elspr.graph.scc import tarjan_scc


@dataclass(frozen=True, slots=True)
class EntropyComponent:
    """Auditable terms for one SCC."""

    nodes: tuple[str, ...]
    volume: int
    incoming_external_edges: int
    partition_term: float
    internal_term: float


@dataclass(frozen=True, slots=True)
class EntropyAnalysis:
    """Structural entropy result for one question graph."""

    h2: float
    tau: float
    graph_volume: int
    node_count: int
    components: tuple[EntropyComponent, ...]


def _x_log2_x(value: float) -> float:
    return value * math.log2(value) if value > 0 else 0.0


def structural_entropy(graph: nx.DiGraph) -> EntropyAnalysis:
    """Compute paper Equations 4 and 5 with explicit zero conventions."""

    components = tarjan_scc(graph)
    component_index = {
        node: index for index, component in enumerate(components) for node in component
    }
    graph_volume = sum(degree for _, degree in graph.in_degree())
    node_count = graph.number_of_nodes()

    details: list[EntropyComponent] = []
    h2 = 0.0
    for component in components:
        volume = sum(graph.in_degree(node) for node in component)
        incoming = 0
        for source, target in graph.edges:
            if target not in component or source in component:
                continue
            source_component = components[component_index[source]]
            if len(source_component) == 1 and len(component) == 1:
                continue
            incoming += 1

        partition_term = 0.0
        internal_term = 0.0
        if graph_volume > 0 and volume > 0:
            partition_term = -(
                incoming / graph_volume * math.log2(volume / graph_volume)
            )
            internal_entropy = -sum(
                _x_log2_x(graph.in_degree(node) / volume) for node in component
            )
            internal_term = volume / graph_volume * internal_entropy
        h2 += partition_term + internal_term
        details.append(
            EntropyComponent(
                nodes=component,
                volume=volume,
                incoming_external_edges=incoming,
                partition_term=partition_term,
                internal_term=internal_term,
            )
        )

    tau = 0.0
    if node_count > 1 and graph_volume > 0:
        tau = h2 / math.log2(node_count)
    if tau < -1e-12 or tau > 1 + 1e-12:
        warnings.warn(
            f"normalized structural entropy outside [0, 1]: tau={tau}",
            RuntimeWarning,
            stacklevel=2,
        )

    return EntropyAnalysis(
        h2=h2,
        tau=tau,
        graph_volume=graph_volume,
        node_count=node_count,
        components=tuple(details),
    )


def average_structural_entropy(graphs: Iterable[nx.DiGraph]) -> float:
    """Compute the unweighted mean of per-question normalized entropy."""

    values = [structural_entropy(graph).tau for graph in graphs]
    return sum(values) / len(values) if values else 0.0
