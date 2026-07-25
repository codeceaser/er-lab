"""Stage 7A.1: the ONE real, persisted vector-store implementation --
Postgres + pgvector.

Uses its OWN table (never document_chunks/documents/kg_* -- those belong
to the separate, frozen ER GraphRAG POC also in this repository; see
docs/POC_ARCHITECTURE.md rule C -- "the two are not wired together").
Connection string comes from DATABASE_URL, an environment variable --
never hardcoded, never logged, and never written to any report or
artifact this module produces (only the table name and index metadata
are ever recorded).

This module never imports src/db.py or src/config.py (the GraphRAG
POC's own code) -- an independent connection to the SAME database
instance, against its own table only.
"""

from __future__ import annotations

import json

from sqlalchemy import Engine, create_engine, text

from ingestion_bench.retrieval_baseline.config import DATABASE_URL, VECTOR_TABLE_NAME
from ingestion_bench.retrieval_baseline.vector_store import SearchHit, UpsertResult, VectorRecord, compute_index_hash


class PgVectorStoreUnavailable(RuntimeError):
    """Raised when DATABASE_URL is not configured, or the database is not
    reachable. Callers (e.g. the integration test) catch this to skip
    gracefully -- never to silently fall back to a different store."""


def _to_vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in embedding) + "]"


def _parse_vector_literal(value: object) -> list[float]:
    if isinstance(value, str):
        return [float(x) for x in value.strip("[]").split(",") if x]
    return [float(x) for x in value]  # type: ignore[union-attr]


class PgVectorStore:
    """The one real, persisted vector-store implementation configured for
    this stage."""

    def __init__(self, embedding_dimension: int, table_name: str | None = None, database_url: str | None = None) -> None:
        self._database_url = database_url or DATABASE_URL
        if not self._database_url:
            raise PgVectorStoreUnavailable(
                "DATABASE_URL is not set -- copy .env.example to .env and set it, or pass database_url= explicitly"
            )
        self._table_name = table_name or VECTOR_TABLE_NAME
        self._dimension = embedding_dimension
        self._engine: Engine | None = None
        self._schema_ready = False

    def _ensure_ready(self) -> Engine:
        if self._engine is None:
            try:
                engine = create_engine(self._database_url, future=True)
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
            except Exception as exc:  # noqa: BLE001
                raise PgVectorStoreUnavailable(
                    f"could not connect to the configured database: {type(exc).__name__}: {exc}"
                ) from exc
            self._engine = engine
        if not self._schema_ready:
            self._create_schema_if_needed()
            self._schema_ready = True
        return self._engine

    def _create_schema_if_needed(self) -> None:
        """Creates this store's OWN table if it does not already exist --
        never DROPs, never touches any other table. Idempotent."""
        assert self._engine is not None
        with self._engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.execute(
                text(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self._table_name} (
                        corpus_profile TEXT NOT NULL,
                        embedding_model TEXT NOT NULL,
                        chunk_id TEXT NOT NULL,
                        content_sha256 TEXT NOT NULL,
                        retrieval_text TEXT NOT NULL,
                        fixture TEXT NOT NULL,
                        doc_id TEXT NOT NULL,
                        source_format TEXT NOT NULL,
                        source_element_ids TEXT NOT NULL,
                        heading_source_element_ids TEXT NOT NULL,
                        annotation_ids TEXT NOT NULL,
                        unit_indices TEXT NOT NULL,
                        source_refs TEXT NOT NULL,
                        heading_path TEXT NOT NULL,
                        contains_model_derived BOOLEAN NOT NULL,
                        embedding VECTOR({self._dimension}) NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (corpus_profile, chunk_id, embedding_model)
                    )
                    """
                )
            )
            conn.commit()

    def existing_content_hashes(self, corpus_profile: str, embedding_model: str) -> dict[str, str]:
        engine = self._ensure_ready()
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"SELECT chunk_id, content_sha256 FROM {self._table_name} "
                    "WHERE corpus_profile = :cp AND embedding_model = :em"
                ),
                {"cp": corpus_profile, "em": embedding_model},
            )
            return {row.chunk_id: row.content_sha256 for row in rows}

    def upsert(self, records: list[VectorRecord]) -> UpsertResult:
        if not records:
            return UpsertResult(written_count=0)
        engine = self._ensure_ready()
        with engine.connect() as conn:
            for record in records:
                conn.execute(
                    text(
                        f"""
                        INSERT INTO {self._table_name} (
                            corpus_profile, embedding_model, chunk_id, content_sha256, retrieval_text,
                            fixture, doc_id, source_format, source_element_ids, heading_source_element_ids,
                            annotation_ids, unit_indices, source_refs, heading_path, contains_model_derived,
                            embedding, updated_at
                        ) VALUES (
                            :corpus_profile, :embedding_model, :chunk_id, :content_sha256, :retrieval_text,
                            :fixture, :doc_id, :source_format, :source_element_ids, :heading_source_element_ids,
                            :annotation_ids, :unit_indices, :source_refs, :heading_path, :contains_model_derived,
                            CAST(:embedding AS vector), CURRENT_TIMESTAMP
                        )
                        ON CONFLICT (corpus_profile, chunk_id, embedding_model) DO UPDATE SET
                            content_sha256 = EXCLUDED.content_sha256,
                            retrieval_text = EXCLUDED.retrieval_text,
                            fixture = EXCLUDED.fixture,
                            doc_id = EXCLUDED.doc_id,
                            source_format = EXCLUDED.source_format,
                            source_element_ids = EXCLUDED.source_element_ids,
                            heading_source_element_ids = EXCLUDED.heading_source_element_ids,
                            annotation_ids = EXCLUDED.annotation_ids,
                            unit_indices = EXCLUDED.unit_indices,
                            source_refs = EXCLUDED.source_refs,
                            heading_path = EXCLUDED.heading_path,
                            contains_model_derived = EXCLUDED.contains_model_derived,
                            embedding = EXCLUDED.embedding,
                            updated_at = CURRENT_TIMESTAMP
                        """
                    ),
                    {
                        "corpus_profile": record.corpus_profile,
                        "embedding_model": record.embedding_model,
                        "chunk_id": record.chunk_id,
                        "content_sha256": record.content_sha256,
                        "retrieval_text": record.retrieval_text,
                        "fixture": record.fixture,
                        "doc_id": record.doc_id,
                        "source_format": record.source_format,
                        "source_element_ids": json.dumps(record.source_element_ids),
                        "heading_source_element_ids": json.dumps(record.heading_source_element_ids),
                        "annotation_ids": json.dumps(record.annotation_ids),
                        "unit_indices": json.dumps(record.unit_indices),
                        "source_refs": json.dumps(record.source_refs),
                        "heading_path": json.dumps(record.heading_path),
                        "contains_model_derived": record.contains_model_derived,
                        "embedding": _to_vector_literal(record.embedding),
                    },
                )
            conn.commit()
        return UpsertResult(written_count=len(records))

    def search(
        self, corpus_profile: str, embedding_model: str, query_vector: list[float], top_k: int
    ) -> list[SearchHit]:
        engine = self._ensure_ready()
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT *, 1 - (embedding <=> CAST(:query_embedding AS vector)) AS score
                    FROM {self._table_name}
                    WHERE corpus_profile = :cp AND embedding_model = :em
                    ORDER BY embedding <=> CAST(:query_embedding AS vector), chunk_id ASC
                    LIMIT :top_k
                    """
                ),
                {
                    "query_embedding": _to_vector_literal(query_vector),
                    "cp": corpus_profile,
                    "em": embedding_model,
                    "top_k": top_k,
                },
            ).mappings()
            hits = []
            for row in rows:
                record = VectorRecord(
                    corpus_profile=row["corpus_profile"],
                    embedding_model=row["embedding_model"],
                    chunk_id=row["chunk_id"],
                    content_sha256=row["content_sha256"],
                    retrieval_text=row["retrieval_text"],
                    fixture=row["fixture"],
                    doc_id=row["doc_id"],
                    source_format=row["source_format"],
                    source_element_ids=json.loads(row["source_element_ids"]),
                    heading_source_element_ids=json.loads(row["heading_source_element_ids"]),
                    annotation_ids=json.loads(row["annotation_ids"]),
                    unit_indices=json.loads(row["unit_indices"]),
                    source_refs=json.loads(row["source_refs"]),
                    heading_path=json.loads(row["heading_path"]),
                    contains_model_derived=row["contains_model_derived"],
                    embedding=_parse_vector_literal(row["embedding"]),
                )
                hits.append(SearchHit(record=record, score=float(row["score"])))
            return hits

    def record_count(self, corpus_profile: str, embedding_model: str) -> int:
        engine = self._ensure_ready()
        with engine.connect() as conn:
            result = conn.execute(
                text(f"SELECT COUNT(*) FROM {self._table_name} WHERE corpus_profile = :cp AND embedding_model = :em"),
                {"cp": corpus_profile, "em": embedding_model},
            )
            return int(result.scalar_one())

    def all_chunk_ids(self, corpus_profile: str, embedding_model: str) -> set[str]:
        engine = self._ensure_ready()
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"SELECT chunk_id FROM {self._table_name} WHERE corpus_profile = :cp AND embedding_model = :em"
                ),
                {"cp": corpus_profile, "em": embedding_model},
            )
            return {row.chunk_id for row in rows}

    def index_hash(self, corpus_profile: str, embedding_model: str) -> str:
        engine = self._ensure_ready()
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"SELECT chunk_id, content_sha256 FROM {self._table_name} "
                    "WHERE corpus_profile = :cp AND embedding_model = :em"
                ),
                {"cp": corpus_profile, "em": embedding_model},
            )
            pairs = [(row.chunk_id, row.content_sha256) for row in rows]
        return compute_index_hash(pairs)
