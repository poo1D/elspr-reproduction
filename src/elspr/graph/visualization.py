"""Dependency-free deterministic SVG rendering for ELSPR graphs."""

from __future__ import annotations

import math
from html import escape
from pathlib import Path

import networkx as nx

_WIDTH = 720
_HEIGHT = 720
_CENTER_X = _WIDTH / 2
_CENTER_Y = 330.0
_LAYOUT_RADIUS = 245.0
_NODE_RADIUS = 30.0


def _positions(nodes: list[str]) -> dict[str, tuple[float, float]]:
    if not nodes:
        return {}
    if len(nodes) == 1:
        return {nodes[0]: (_CENTER_X, _CENTER_Y)}
    return {
        node: (
            _CENTER_X
            + _LAYOUT_RADIUS
            * math.cos(-math.pi / 2 + 2 * math.pi * index / len(nodes)),
            _CENTER_Y
            + _LAYOUT_RADIUS
            * math.sin(-math.pi / 2 + 2 * math.pi * index / len(nodes)),
        )
        for index, node in enumerate(nodes)
    }


def _edge_endpoints(
    source: tuple[float, float],
    target: tuple[float, float],
) -> tuple[float, float, float, float]:
    delta_x = target[0] - source[0]
    delta_y = target[1] - source[1]
    length = math.hypot(delta_x, delta_y)
    if length == 0:
        return (*source, *target)
    unit_x = delta_x / length
    unit_y = delta_y / length
    return (
        source[0] + _NODE_RADIUS * unit_x,
        source[1] + _NODE_RADIUS * unit_y,
        target[0] - _NODE_RADIUS * unit_x,
        target[1] - _NODE_RADIUS * unit_y,
    )


def _short_label(value: str, *, limit: int = 18) -> str:
    return value if len(value) <= limit else f"{value[: limit - 1]}…"


def graph_to_svg(
    graph: nx.DiGraph,
    *,
    title: str,
) -> str:
    """Render a graph as stable SVG with preference and tie arrows.

    A single arrow points from the worse response to the better response.
    Reciprocal edges are rendered once with arrowheads at both ends.
    """

    nodes = sorted(str(node) for node in graph.nodes)
    positions = _positions(nodes)
    escaped_title = escape(title)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{_WIDTH}" '
            f'height="{_HEIGHT}" viewBox="0 0 {_WIDTH} {_HEIGHT}" '
            'role="img" aria-labelledby="graph-title graph-description">'
        ),
        f'  <title id="graph-title">{escaped_title}</title>',
        (
            '  <desc id="graph-description">Arrows point from worse to better; '
            "two arrowheads denote a tie.</desc>"
        ),
        "  <defs>",
        (
            '    <marker id="arrow-preference" viewBox="0 0 10 10" refX="9" '
            'refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        ),
        '      <path d="M 0 0 L 10 5 L 0 10 z" fill="#2563eb"/>',
        "    </marker>",
        (
            '    <marker id="arrow-tie" viewBox="0 0 10 10" refX="9" '
            'refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        ),
        '      <path d="M 0 0 L 10 5 L 0 10 z" fill="#d97706"/>',
        "    </marker>",
        "  </defs>",
        f'  <rect width="{_WIDTH}" height="{_HEIGHT}" fill="#ffffff"/>',
        (
            f'  <text x="{_CENTER_X:.1f}" y="36" text-anchor="middle" '
            'font-family="system-ui, sans-serif" font-size="22" '
            f'font-weight="700" fill="#111827">{escaped_title}</text>'
        ),
        '  <g id="edges" fill="none" stroke-linecap="round">',
    ]

    handled_ties: set[frozenset[str]] = set()
    for source, target in sorted((str(u), str(v)) for u, v in graph.edges):
        reciprocal = graph.has_edge(target, source)
        tie_key = frozenset((source, target))
        if reciprocal and tie_key in handled_ties:
            continue
        x1, y1, x2, y2 = _edge_endpoints(positions[source], positions[target])
        if reciprocal:
            handled_ties.add(tie_key)
            lines.append(
                f'    <line class="edge tie" x1="{x1:.2f}" y1="{y1:.2f}" '
                f'x2="{x2:.2f}" y2="{y2:.2f}" stroke="#d97706" '
                'stroke-width="3" marker-start="url(#arrow-tie)" '
                'marker-end="url(#arrow-tie)"/>'
            )
        else:
            lines.append(
                f'    <line class="edge preference" x1="{x1:.2f}" '
                f'y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
                'stroke="#2563eb" stroke-width="3" '
                'marker-end="url(#arrow-preference)"/>'
            )
    lines.extend(["  </g>", '  <g id="nodes">'])

    for node in nodes:
        x, y = positions[node]
        escaped_node = escape(node)
        escaped_label = escape(_short_label(node))
        lines.extend(
            [
                f'    <g class="node" data-node="{escape(node, quote=True)}">',
                f"      <title>{escaped_node}</title>",
                (
                    f'      <circle cx="{x:.2f}" cy="{y:.2f}" '
                    f'r="{_NODE_RADIUS:.2f}" fill="#f8fafc" '
                    'stroke="#111827" stroke-width="2"/>'
                ),
                (
                    f'      <text x="{x:.2f}" y="{y + 5:.2f}" '
                    'text-anchor="middle" font-family="system-ui, sans-serif" '
                    f'font-size="13" fill="#111827">{escaped_label}</text>'
                ),
                "    </g>",
            ]
        )

    lines.extend(
        [
            "  </g>",
            '  <g id="legend" font-family="system-ui, sans-serif" font-size="14">',
            (
                '    <line x1="185" y1="665" x2="245" y2="665" '
                'stroke="#2563eb" stroke-width="3" '
                'marker-end="url(#arrow-preference)"/>'
            ),
            '    <text x="260" y="670" fill="#111827">worse → better</text>',
            (
                '    <line x1="430" y1="665" x2="490" y2="665" '
                'stroke="#d97706" stroke-width="3" '
                'marker-start="url(#arrow-tie)" marker-end="url(#arrow-tie)"/>'
            ),
            '    <text x="505" y="670" fill="#111827">tie</text>',
            "  </g>",
            "</svg>",
            "",
        ]
    )
    return "\n".join(lines)


def write_graph_svg(
    path: Path,
    graph: nx.DiGraph,
    *,
    title: str,
) -> None:
    """Write a deterministic graph visualization."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(graph_to_svg(graph, title=title), encoding="utf-8")
