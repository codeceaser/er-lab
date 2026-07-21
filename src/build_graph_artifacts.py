"""Build graph_artifacts from kg_entities and kg_edges.

Fairness constraints (see README):
  - Only two artifact types are produced: `entity` and `single_edge`.
  - No multi-hop path summaries and no community summaries are created here.
  - No artifact directly answers the evaluation question; each artifact only
    restates a single entity or a single edge plus its evidence text.

Run: python src/build_graph_artifacts.py
"""

from rich.console import Console
from sqlalchemy import text

from db import embed_text, get_connection, to_vector_literal

console = Console()


def fetch_entities(conn):
    rows = conn.execute(
        text("SELECT entity_id, entity_type, canonical_name, aliases FROM kg_entities")
    ).mappings()
    return list(rows)


def fetch_edges_with_evidence(conn):
    # DISTINCT ON picks a single (first, by evidence_id) evidence row per edge,
    # since a single-edge artifact only needs one representative evidence quote.
    rows = conn.execute(
        text(
            """
            SELECT DISTINCT ON (e.edge_id)
                e.edge_id,
                e.relationship_type,
                se.entity_type AS source_type,
                se.canonical_name AS source_name,
                te.canonical_name AS target_name,
                ev.evidence_text
            FROM kg_edges e
            JOIN kg_entities se ON se.entity_id = e.source_entity_id
            JOIN kg_entities te ON te.entity_id = e.target_entity_id
            LEFT JOIN kg_evidence ev ON ev.edge_id = e.edge_id
            ORDER BY e.edge_id, ev.evidence_id
            """
        )
    ).mappings()
    return list(rows)


def build_entity_artifact_text(entity) -> str:
    aliases = entity["aliases"] or []
    return f"{entity['entity_type']} {entity['canonical_name']}. Aliases: {', '.join(aliases)}."


def build_edge_artifact_text(edge) -> str:
    return (
        f"{edge['source_type']} {edge['source_name']} {edge['relationship_type']} "
        f"{edge['target_name']}. Evidence: {edge['evidence_text']}"
    )


def build_graph_artifacts() -> None:
    with get_connection() as conn:
        entities = fetch_entities(conn)
        edges = fetch_edges_with_evidence(conn)

        for entity in entities:
            artifact_text = build_entity_artifact_text(entity)
            embedding = embed_text(artifact_text)
            conn.execute(
                text(
                    """
                    INSERT INTO graph_artifacts
                        (artifact_id, artifact_type, entity_id, edge_id, artifact_text, embedding)
                    VALUES
                        (:artifact_id, 'entity', :entity_id, NULL, :artifact_text,
                         CAST(:embedding AS vector))
                    """
                ),
                {
                    "artifact_id": f"ART_ENTITY_{entity['entity_id']}",
                    "entity_id": entity["entity_id"],
                    "artifact_text": artifact_text,
                    "embedding": to_vector_literal(embedding),
                },
            )
            console.print(f"  entity artifact -> {entity['entity_id']}")

        for edge in edges:
            artifact_text = build_edge_artifact_text(edge)
            embedding = embed_text(artifact_text)
            conn.execute(
                text(
                    """
                    INSERT INTO graph_artifacts
                        (artifact_id, artifact_type, entity_id, edge_id, artifact_text, embedding)
                    VALUES
                        (:artifact_id, 'single_edge', NULL, :edge_id, :artifact_text,
                         CAST(:embedding AS vector))
                    """
                ),
                {
                    "artifact_id": f"ART_EDGE_{edge['edge_id']}",
                    "edge_id": edge["edge_id"],
                    "artifact_text": artifact_text,
                    "embedding": to_vector_literal(embedding),
                },
            )
            console.print(f"  edge artifact   -> {edge['edge_id']}")

        conn.commit()


if __name__ == "__main__":
    try:
        build_graph_artifacts()
        console.print("[bold green]Graph artifacts built successfully.[/bold green]")
    except Exception as exc:  # noqa: BLE001
        console.print(f"[bold red]Building graph artifacts failed:[/bold red] {exc}")
        raise
