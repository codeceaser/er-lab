"""Create (or recreate) the database schema for the ER GraphRAG POC.

Run: python src/create_schema.py
"""

from rich.console import Console
from sqlalchemy import text

from db import get_connection

console = Console()

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

DROP TABLE IF EXISTS graph_artifacts;
DROP TABLE IF EXISTS kg_evidence;
DROP TABLE IF EXISTS kg_edges;
DROP TABLE IF EXISTS kg_entities;
DROP TABLE IF EXISTS document_chunks;
DROP TABLE IF EXISTS documents;

CREATE TABLE documents (
    document_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    document_type TEXT NOT NULL,
    source_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE document_chunks (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id),
    chunk_index INT NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding VECTOR(384),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE kg_entities (
    entity_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    aliases TEXT[],
    source_system TEXT,
    source_key TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE kg_edges (
    edge_id TEXT PRIMARY KEY,
    source_entity_id TEXT NOT NULL REFERENCES kg_entities(entity_id),
    relationship_type TEXT NOT NULL,
    target_entity_id TEXT NOT NULL REFERENCES kg_entities(entity_id),
    confidence NUMERIC(5,4) DEFAULT 1.0,
    approval_status TEXT DEFAULT 'approved',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE kg_evidence (
    evidence_id TEXT PRIMARY KEY,
    edge_id TEXT NOT NULL REFERENCES kg_edges(edge_id),
    document_id TEXT NOT NULL REFERENCES documents(document_id),
    chunk_id TEXT NOT NULL REFERENCES document_chunks(chunk_id),
    evidence_text TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE graph_artifacts (
    artifact_id TEXT PRIMARY KEY,
    artifact_type TEXT NOT NULL,
    entity_id TEXT REFERENCES kg_entities(entity_id),
    edge_id TEXT REFERENCES kg_edges(edge_id),
    artifact_text TEXT NOT NULL,
    embedding VECTOR(384),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def create_schema() -> None:
    with get_connection() as conn:
        conn.execute(text(SCHEMA_SQL))
        conn.commit()


if __name__ == "__main__":
    try:
        create_schema()
        console.print("[bold green]Schema created successfully.[/bold green]")
    except Exception as exc:  # noqa: BLE001
        console.print(f"[bold red]Schema creation failed:[/bold red] {exc}")
        raise
