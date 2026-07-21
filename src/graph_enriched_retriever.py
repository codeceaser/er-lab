"""Graph-enriched retrieval.

Pipeline:
  1. Embed the query and search graph_artifacts (entity + single-edge artifacts
     only) by cosine similarity -> "seed" entities and edges.
  2. Expand the graph outward from the seed entities, up to
     GRAPH_EXPANSION_MAX_DEPTH hops, following kg_edges in either direction.
     This is where multi-hop lineage is *discovered*, at query time -- no
     precomputed path summary exists anywhere in graph_artifacts.
  3. Attach kg_evidence to every edge that was discovered.
  4. Independently run the same vector-only document_chunks search as the
     baseline retriever (fairness constraint #8: graph results never filter
     the document vector search).

Run standalone: python src/graph_enriched_retriever.py "some question"
"""

import sys
from collections import deque

from rich.console import Console
from rich.table import Table
from sqlalchemy import text

from config import GRAPH_ARTIFACT_TOP_K, GRAPH_EXPANSION_MAX_DEPTH, VECTOR_TOP_K
from db import embed_text, get_connection, to_vector_literal
from vector_retriever import retrieve as vector_retrieve

console = Console()


def search_graph_artifacts(conn, query_embedding: str, top_k: int) -> list[dict]:
    rows = conn.execute(
        text(
            """
            SELECT
                artifact_id,
                artifact_type,
                entity_id,
                edge_id,
                artifact_text,
                1 - (embedding <=> CAST(:query_embedding AS vector)) AS score
            FROM graph_artifacts
            ORDER BY embedding <=> CAST(:query_embedding AS vector)
            LIMIT :top_k
            """
        ),
        {"query_embedding": query_embedding, "top_k": top_k},
    ).mappings()
    return [dict(row) for row in rows]


def load_all_edges(conn) -> list[dict]:
    rows = conn.execute(
        text(
            "SELECT edge_id, source_entity_id, relationship_type, target_entity_id FROM kg_edges"
        )
    ).mappings()
    return [dict(row) for row in rows]


def load_entity_names(conn) -> dict[str, str]:
    rows = conn.execute(text("SELECT entity_id, canonical_name FROM kg_entities")).mappings()
    return {row["entity_id"]: row["canonical_name"] for row in rows}


def load_evidence_for_edges(conn, edge_ids: set[str]) -> dict[str, list[dict]]:
    if not edge_ids:
        return {}
    rows = conn.execute(
        text(
            """
            SELECT evidence_id, edge_id, document_id, chunk_id, evidence_text
            FROM kg_evidence
            WHERE edge_id = ANY(:edge_ids)
            """
        ),
        {"edge_ids": list(edge_ids)},
    ).mappings()
    evidence_by_edge: dict[str, list[dict]] = {}
    for row in rows:
        evidence_by_edge.setdefault(row["edge_id"], []).append(dict(row))
    return evidence_by_edge


def extract_seeds(conn, artifact_matches: list[dict]) -> tuple[set[str], set[str]]:
    """From matched graph_artifacts, determine seed entity IDs and seed edge IDs."""
    seed_entity_ids: set[str] = set()
    seed_edge_ids: set[str] = set()

    edge_ids_to_resolve = [
        row["edge_id"] for row in artifact_matches if row["artifact_type"] == "single_edge"
    ]
    edge_endpoints: dict[str, tuple[str, str]] = {}
    if edge_ids_to_resolve:
        rows = conn.execute(
            text(
                """
                SELECT edge_id, source_entity_id, target_entity_id
                FROM kg_edges
                WHERE edge_id = ANY(:edge_ids)
                """
            ),
            {"edge_ids": edge_ids_to_resolve},
        ).mappings()
        edge_endpoints = {
            row["edge_id"]: (row["source_entity_id"], row["target_entity_id"]) for row in rows
        }

    for row in artifact_matches:
        if row["artifact_type"] == "entity" and row["entity_id"]:
            seed_entity_ids.add(row["entity_id"])
        elif row["artifact_type"] == "single_edge" and row["edge_id"]:
            seed_edge_ids.add(row["edge_id"])
            source_id, target_id = edge_endpoints[row["edge_id"]]
            seed_entity_ids.add(source_id)
            seed_entity_ids.add(target_id)

    return seed_entity_ids, seed_edge_ids


def build_adjacency(edges: list[dict]) -> dict[str, list[tuple[dict, str, str]]]:
    """entity_id -> list of (edge, other_entity_id, direction)."""
    adjacency: dict[str, list[tuple[dict, str, str]]] = {}
    for edge in edges:
        adjacency.setdefault(edge["source_entity_id"], []).append(
            (edge, edge["target_entity_id"], "forward")
        )
        adjacency.setdefault(edge["target_entity_id"], []).append(
            (edge, edge["source_entity_id"], "backward")
        )
    return adjacency


def bfs_from_seed(seed: str, adjacency: dict, max_depth: int) -> dict[str, tuple]:
    """BFS from `seed` up to max_depth hops. Returns {entity_id: (parent_entity_id, edge, direction)}."""
    parent: dict[str, tuple | None] = {seed: None}
    depth = {seed: 0}
    queue = deque([seed])

    while queue:
        current = queue.popleft()
        if depth[current] >= max_depth:
            continue
        for edge, other, direction in adjacency.get(current, []):
            if other in parent:
                continue
            parent[other] = (current, edge, direction)
            depth[other] = depth[current] + 1
            queue.append(other)

    return parent


def reconstruct_path(node: str, parent: dict) -> list[dict]:
    """Walk parent pointers back to the seed, returning an ordered list of edge steps."""
    steps = []
    while parent[node] is not None:
        prev, edge, direction = parent[node]
        steps.append({"edge": edge, "from_entity_id": prev, "to_entity_id": node, "direction": direction})
        node = prev
    steps.reverse()
    return steps


def expand_from_seeds(seed_entity_ids: set[str], edges: list[dict], max_depth: int) -> list[list[dict]]:
    """Expand the graph from each seed entity and return maximal discovered paths.

    A path is "maximal" if it is not a strict prefix of a longer discovered
    path from the same seed (i.e. it ends at a leaf of the BFS tree).
    """
    adjacency = build_adjacency(edges)
    discovered_paths: list[list[dict]] = []

    for seed in seed_entity_ids:
        parent = bfs_from_seed(seed, adjacency, max_depth)
        has_children = {p[0] for node, p in parent.items() if p is not None}
        leaves = [node for node in parent if node != seed and node not in has_children]
        for leaf in leaves:
            discovered_paths.append(reconstruct_path(leaf, parent))

    return discovered_paths


def format_path(path: list[dict], entity_names: dict[str, str]) -> str:
    if not path:
        return ""
    first_from = entity_names.get(path[0]["from_entity_id"], path[0]["from_entity_id"])
    parts = [first_from]
    for step in path:
        parts.append(f"--[{step['edge']['relationship_type']}]-->")
        parts.append(entity_names.get(step["to_entity_id"], step["to_entity_id"]))
    return " ".join(parts)


def retrieve(
    query: str,
    artifact_top_k: int = GRAPH_ARTIFACT_TOP_K,
    max_depth: int = GRAPH_EXPANSION_MAX_DEPTH,
    vector_top_k: int = VECTOR_TOP_K,
) -> dict:
    query_embedding = to_vector_literal(embed_text(query))

    with get_connection() as conn:
        artifact_matches = search_graph_artifacts(conn, query_embedding, artifact_top_k)
        seed_entity_ids, seed_edge_ids = extract_seeds(conn, artifact_matches)
        edges = load_all_edges(conn)
        entity_names = load_entity_names(conn)

        discovered_paths = expand_from_seeds(seed_entity_ids, edges, max_depth)

        discovered_edge_ids = set(seed_edge_ids)
        for path in discovered_paths:
            for step in path:
                discovered_edge_ids.add(step["edge"]["edge_id"])

        evidence_by_edge = load_evidence_for_edges(conn, discovered_edge_ids)

    # Independent, unfiltered vector search over document_chunks (fairness constraint #8).
    vector_chunks = vector_retrieve(query, top_k=vector_top_k)

    return {
        "query": query,
        "artifact_matches": artifact_matches,
        "seed_entity_ids": seed_entity_ids,
        "seed_edge_ids": seed_edge_ids,
        "discovered_paths": discovered_paths,
        "discovered_edge_ids": discovered_edge_ids,
        "evidence_by_edge": evidence_by_edge,
        "entity_names": entity_names,
        "vector_chunks": vector_chunks,
    }


def _print_results(result: dict) -> None:
    table = Table(title=f"Graph artifact matches: {result['query']!r}")
    table.add_column("Score", justify="right")
    table.add_column("Type")
    table.add_column("Artifact text")
    for row in result["artifact_matches"]:
        table.add_row(f"{row['score']:.4f}", row["artifact_type"], row["artifact_text"])
    console.print(table)

    console.print("\n[bold]Discovered lineage paths:[/bold]")
    for path in result["discovered_paths"]:
        console.print(f"  {format_path(path, result['entity_names'])}")


if __name__ == "__main__":
    query_arg = " ".join(sys.argv[1:]) or "What is the BCP impact of CRA-176046 going down?"
    _print_results(retrieve(query_arg))
