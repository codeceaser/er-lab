"""Seed the `documents` and `document_chunks` tables with the sample corpus.

Each document is treated as a single chunk for this POC.

Run: python src/seed_documents.py
"""

from rich.console import Console
from sqlalchemy import text

from db import embed_text, get_connection, to_vector_literal

console = Console()

DOCUMENTS = [
    {
        "document_id": "DOC_001",
        "title": "CRA Application Declaration",
        "document_type": "ApplicationDeclaration",
        "chunk_text": (
            "Application CRA-176046 supports the Compliance Risk Assessment service. "
            "CRA-176046 is in scope for Regulatory Obligation O-22."
        ),
    },
    {
        "document_id": "DOC_002",
        "title": "Regulatory Control Mapping",
        "document_type": "RegulatoryMapping",
        "chunk_text": (
            "Regulatory Obligation O-22 is satisfied by Control C-77. "
            "O-22 requires continuity controls for critical compliance risk assessment services."
        ),
    },
    {
        "document_id": "DOC_003",
        "title": "BCP Policy 2026",
        "document_type": "BCPPolicy",
        "chunk_text": (
            "Control C-77 mandates BCP Procedure P-100 for critical compliance applications. "
            "Procedure P-100 requires manual recovery steps and continuity validation before "
            "business restoration."
        ),
    },
    {
        "document_id": "DOC_004",
        "title": "Structured Process Record",
        "document_type": "StructuredProcessRecord",
        "chunk_text": (
            "Compliance Risk Assessment is a critical business service owned by the Compliance "
            "Risk Team. The service operates in APAC and has an RTO of 4 hours."
        ),
    },
]


def seed_documents() -> None:
    with get_connection() as conn:
        for doc in DOCUMENTS:
            conn.execute(
                text(
                    """
                    INSERT INTO documents (document_id, title, document_type)
                    VALUES (:document_id, :title, :document_type)
                    """
                ),
                {
                    "document_id": doc["document_id"],
                    "title": doc["title"],
                    "document_type": doc["document_type"],
                },
            )

            chunk_id = f"CHUNK_{doc['document_id']}_001"
            embedding = embed_text(doc["chunk_text"])
            conn.execute(
                text(
                    """
                    INSERT INTO document_chunks
                        (chunk_id, document_id, chunk_index, chunk_text, embedding)
                    VALUES
                        (:chunk_id, :document_id, 0, :chunk_text, CAST(:embedding AS vector))
                    """
                ),
                {
                    "chunk_id": chunk_id,
                    "document_id": doc["document_id"],
                    "chunk_text": doc["chunk_text"],
                    "embedding": to_vector_literal(embedding),
                },
            )
            console.print(f"  inserted {doc['document_id']} -> {chunk_id}")

        conn.commit()


if __name__ == "__main__":
    try:
        seed_documents()
        console.print("[bold green]Documents and chunks seeded successfully.[/bold green]")
    except Exception as exc:  # noqa: BLE001
        console.print(f"[bold red]Seeding documents failed:[/bold red] {exc}")
        raise
