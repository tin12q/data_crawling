#!/usr/bin/env python3
"""Builds a citation graph from `articles.json` and saves it as a PNG image.

The script matches citation titles against article titles (case-insensitive,
non-alphanumeric characters stripped) and draws a directed graph that highlights
which papers reference each other within the dataset.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

import matplotlib.pyplot as plt
import networkx as nx


def normalize_title(title: str) -> str:
    """Return a normalized representation of a title for matching."""
    if not title:
        return ""
    normalized = re.sub(r"[^0-9a-z]+", " ", title.lower())
    return " ".join(normalized.split())


def build_title_index(articles: Iterable[dict]) -> Dict[str, Set[str]]:
    """Map normalized titles to the PMCIDs of matching articles."""
    index: Dict[str, Set[str]] = defaultdict(set)
    for article in articles:
        pmcid = article["pmcid"]
        for key in ("original_title", "title"):
            title = article.get(key)
            norm = normalize_title(title)
            if norm:
                index[norm].add(pmcid)
    return index


def build_graph(articles: List[dict]) -> Tuple[nx.DiGraph, Counter]:
    """Return the citation graph and a counter of unmatched citation titles."""
    graph = nx.DiGraph()
    title_index = build_title_index(articles)
    unmatched_titles: Counter = Counter()
    edge_weights: Counter = Counter()

    for article in articles:
        pmcid = article["pmcid"]
        graph.add_node(
            pmcid,
            pmcid=pmcid,
            title=article.get("title") or article.get("original_title"),
        )

        for citation in article.get("citations", []):
            citation_title = citation.get("title", "")
            norm_title = normalize_title(citation_title)
            if not norm_title:
                continue
            targets = title_index.get(norm_title)
            if not targets:
                unmatched_titles[norm_title] += 1
                continue

            for target in targets:
                if target == pmcid:
                    continue  # ignore self-references inside the dataset
                edge_weights[(pmcid, target)] += 1

    for (source, target), weight in edge_weights.items():
        graph.add_edge(source, target, weight=weight)

    return graph, unmatched_titles


def draw_graph(graph: nx.DiGraph, output_path: Path, max_labels: int = 30) -> None:
    """Render the citation graph to a PNG file."""
    if graph.number_of_edges() == 0:
        raise ValueError("No edges found after matching citations; nothing to draw.")

    connected_nodes = set()
    connected_nodes.update(*(edge[:2] for edge in graph.edges()))
    subgraph = graph.subgraph(connected_nodes).copy()

    pos = nx.spring_layout(subgraph, k=0.4, seed=7)

    in_degrees = dict(subgraph.in_degree())
    out_degrees = dict(subgraph.out_degree())
    total_degrees = {
        node: in_degrees.get(node, 0) + out_degrees.get(node, 0)
        for node in subgraph.nodes()
    }

    node_sizes = [300 + total_degrees[node] * 120 for node in subgraph.nodes()]
    node_colors = [in_degrees.get(node, 0) for node in subgraph.nodes()]
    edge_widths = [0.4 + subgraph.edges[edge]["weight"] * 0.2 for edge in subgraph.edges()]

    plt.figure(figsize=(14, 14))
    nx.draw_networkx_nodes(
        subgraph,
        pos,
        node_size=node_sizes,
        node_color=node_colors,
        cmap=plt.cm.viridis,
        alpha=0.85,
    )
    nx.draw_networkx_edges(
        subgraph,
        pos,
        width=edge_widths,
        alpha=0.25,
        arrows=True,
        arrowstyle="-|>",
        arrowsize=10,
    )

    label_candidates = sorted(
        total_degrees.items(), key=lambda item: item[1], reverse=True
    )
    labels = {}
    for pmcid, _ in label_candidates[:max_labels]:
        labels[pmcid] = subgraph.nodes[pmcid]["title"] or pmcid

    nx.draw_networkx_labels(
        subgraph,
        pos,
        labels=labels,
        font_size=8,
        font_color="black",
        bbox=dict(facecolor="white", alpha=0.6, edgecolor="none", pad=1.5),
    )

    plt.title("Citation Graph Between PMC Articles", fontsize=16)
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()


def export_graph_json(graph: nx.DiGraph, output_path: Path) -> None:
    """Serialise the graph to JSON with adjacency lists per node."""
    payload = []
    for node, attrs in sorted(graph.nodes(data=True), key=lambda item: item[0]):
        cited = sorted(graph.successors(node))
        cited_by = sorted(graph.predecessors(node))
        payload.append(
            {
                "id": node,
                "title": attrs.get("title"),
                "cited": cited,
                "cited_by": cited_by,
            }
        )

    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


def export_graph_sqlite(graph: nx.DiGraph, output_path: Path) -> None:
    """Persist the graph into a SQLite database with nodes and edges tables."""
    if output_path.exists():
        output_path.unlink()

    with sqlite3.connect(output_path) as conn:
        conn.execute(
            """
            CREATE TABLE nodes (
                id TEXT PRIMARY KEY,
                pmcid TEXT,
                title TEXT
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE edges (
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                weight INTEGER NOT NULL,
                FOREIGN KEY(source) REFERENCES nodes(id),
                FOREIGN KEY(target) REFERENCES nodes(id)
            )
            """
        )

        node_rows = [
            (node, attrs.get("pmcid", node), attrs.get("title"))
            for node, attrs in graph.nodes(data=True)
        ]
        conn.executemany(
            "INSERT INTO nodes (id, pmcid, title) VALUES (?, ?, ?)", node_rows
        )

        edge_rows = [
            (source, target, data.get("weight", 1))
            for source, target, data in graph.edges(data=True)
        ]
        conn.executemany(
            "INSERT INTO edges (source, target, weight) VALUES (?, ?, ?)", edge_rows
        )

        conn.execute("CREATE INDEX idx_edges_source ON edges(source)")
        conn.execute("CREATE INDEX idx_edges_target ON edges(target)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input",
        type=Path,
        nargs="?",
        default=Path("articles.json"),
        help="Path to the articles JSON file (default: articles.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("references_graph.png"),
        help="Path of the PNG file to save the graph image.",
    )
    parser.add_argument(
        "--max-labels",
        type=int,
        default=30,
        help="Maximum number of high-degree nodes to label in the visualization.",
    )
    parser.add_argument(
        "--graphml",
        type=Path,
        help="Optional path to export the graph structure as GraphML.",
    )
    parser.add_argument(
        "--json",
        type=Path,
        help="Optional path to export the graph as JSON (default: references_graph.json).",
    )
    parser.add_argument(
        "--sqlite",
        type=Path,
        help="Optional path to export the graph as a SQLite database (default: references_graph.db).",
    )

    args = parser.parse_args()

    with args.input.open("r", encoding="utf-8") as fh:
        articles = json.load(fh)

    graph, unmatched = build_graph(articles)

    connected_edges = graph.number_of_edges()
    if connected_edges == 0:
        print("No mutual matches were found – unable to generate a citation graph")
        return

    draw_graph(graph, args.output, max_labels=args.max_labels)
    print(f"Saved citation graph with {graph.number_of_nodes()} nodes and "
          f"{connected_edges} edges to {args.output}.")

    if args.graphml:
        nx.write_graphml(graph, args.graphml)
        print(f"GraphML export written to {args.graphml}.")

    json_output = args.json or args.output.with_suffix(".json")
    export_graph_json(graph, json_output)
    print(f"JSON export written to {json_output}.")

    sqlite_output = args.sqlite or args.output.with_suffix(".db")
    export_graph_sqlite(graph, sqlite_output)
    print(f"SQLite export written to {sqlite_output}.")

    unmatched_total = sum(unmatched.values())
    if unmatched_total:
        top_unmatched = ", ".join(
            f"{title[:50]}… ({count})" if len(title) > 50 else f"{title} ({count})"
            for title, count in unmatched.most_common(10)
        )
        print(
            "Unmatched citation titles remain: "
            f"{unmatched_total} citations not in dataset. Top examples: {top_unmatched}"
        )


if __name__ == "__main__":
    main()
