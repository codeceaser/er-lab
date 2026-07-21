"""Vector-only retrieval: searches document_chunks by embedding cosine similarity.

This is the baseline retriever. It has no knowledge of the graph and only ever
searches document_chunks (fairness constraint #7).

Run standalone: python src/vector_retriever.py "some question"
"""

import sys

from rich.console import Console
from rich.table import Table
from sqlalchemy import text

from config import VECTOR_TOP_K
from db import embed_text, get_connection, to_vector_literal

console = Console()


def retrieve(query: str, top_k: int = VECTOR_TOP_K) -> list[dict]:
    """Return the top_k document_chunks most similar to `query`.

    Each result dict has: chunk_id, document_id, title, chunk_text, score
    (score is cosine similarity in [-1, 1], higher is more similar).
    """
    query_embedding = to_vector_literal(embed_text(query))

    with get_connection() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    c.chunk_id,
                    c.document_id,
                    d.title,
                    c.chunk_text,
                    1 - (c.embedding <=> CAST(:query_embedding AS vector)) AS score
                FROM document_chunks c
                JOIN documents d ON d.document_id = c.document_id
                ORDER BY c.embedding <=> CAST(:query_embedding AS vector)
                LIMIT :top_k
                """
            ),
            {"query_embedding": query_embedding, "top_k": top_k},
        ).mappings()
        return [dict(row) for row in rows]


def _print_results(query: str, results: list[dict]) -> None:
    table = Table(title=f"Vector-only retrieval: {query!r}")
    table.add_column("Score", justify="right")
    table.add_column("Document")
    table.add_column("Chunk text")
    for row in results:
        table.add_row(f"{row['score']:.4f}", row["title"], row["chunk_text"])
    console.print(table)


if __name__ == "__main__":
    query_arg = " ".join(sys.argv[1:]) or "What is the BCP impact of CRA-176046 going down?"
    _print_results(query_arg, retrieve(query_arg))
