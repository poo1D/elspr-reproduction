from pathlib import Path
from xml.etree import ElementTree

import networkx as nx

from elspr.graph import graph_to_svg, write_graph_svg

SVG = {"svg": "http://www.w3.org/2000/svg"}


def test_svg_renders_preference_and_bidirectional_tie_once() -> None:
    graph = nx.DiGraph()
    graph.add_edges_from([("A", "B"), ("B", "A"), ("B", "C")])

    svg = graph_to_svg(graph, title="Question <1>")
    root = ElementTree.fromstring(svg)

    assert root.find("svg:title", SVG).text == "Question <1>"
    assert len(root.findall(".//svg:g[@class='node']", SVG)) == 3
    assert len(root.findall(".//svg:line[@class='edge tie']", SVG)) == 1
    assert len(root.findall(".//svg:line[@class='edge preference']", SVG)) == 1
    tie = root.find(".//svg:line[@class='edge tie']", SVG)
    assert tie is not None
    assert tie.attrib["marker-start"] == "url(#arrow-tie)"
    assert tie.attrib["marker-end"] == "url(#arrow-tie)"


def test_svg_is_deterministic_across_insertion_order() -> None:
    first = nx.DiGraph()
    first.add_edges_from([("C", "A"), ("B", "A"), ("C", "B")])
    second = nx.DiGraph()
    second.add_edges_from([("C", "B"), ("B", "A"), ("C", "A")])

    assert graph_to_svg(first, title="linear") == graph_to_svg(
        second,
        title="linear",
    )


def test_svg_handles_empty_singleton_and_special_labels(tmp_path: Path) -> None:
    empty = nx.DiGraph()
    singleton = nx.DiGraph()
    singleton.add_node('model<&"')
    output = tmp_path / "graph.svg"

    assert ElementTree.fromstring(graph_to_svg(empty, title="empty")).tag.endswith(
        "svg"
    )
    write_graph_svg(output, singleton, title="singleton")
    root = ElementTree.parse(output).getroot()

    node = root.find(".//svg:g[@class='node']", SVG)
    assert node is not None
    assert node.attrib["data-node"] == 'model<&"'
