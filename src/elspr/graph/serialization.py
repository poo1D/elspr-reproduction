"""Stable graph JSON serialization."""

import json
from pathlib import Path

import networkx as nx

from elspr.schemas import GraphEdge, GraphRecord


def graph_to_record(graph: nx.DiGraph, *, question_id: str) -> GraphRecord:
    """Convert a graph to a sorted, validated record."""

    edges = [
        GraphEdge(
            source=source,
            target=target,
            relation=str(attributes.get("relation", "preference")),
            reconstructed=bool(attributes.get("reconstructed", False)),
        )
        for source, target, attributes in sorted(graph.edges(data=True))
    ]
    return GraphRecord(
        question_id=question_id,
        nodes=sorted(graph.nodes),
        edges=edges,
    )


def record_to_graph(record: GraphRecord) -> nx.DiGraph:
    """Rebuild a NetworkX graph from a validated record."""

    graph = nx.DiGraph(question_id=record.question_id, complete=True)
    graph.add_nodes_from(record.nodes)
    for edge in record.edges:
        graph.add_edge(
            edge.source,
            edge.target,
            relation=edge.relation,
            reconstructed=edge.reconstructed,
        )
    return graph


def write_graph(path: Path, graph: nx.DiGraph, *, question_id: str) -> None:
    """Write one graph as deterministic JSON."""

    record = graph_to_record(graph, question_id=question_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            record.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def read_graph(path: Path) -> tuple[str, nx.DiGraph]:
    """Read one validated graph JSON file."""

    record = GraphRecord.model_validate_json(path.read_text(encoding="utf-8"))
    return record.question_id, record_to_graph(record)
