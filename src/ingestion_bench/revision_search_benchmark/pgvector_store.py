"""Stage 7R.2/7R.2a: the ONE real, persisted revision-search vector-store
implementation -- Postgres + pgvector, using its OWN isolated table
(`ingestion_bench_stage7r2_vectors` by default -- see config.py). Never
Stage 7A.1's own frozen `ingestion_bench_stage7a_vectors` table/code
(retrieval_baseline/pgvector_store.py, read-only reference only), never
document_chunks/documents/kg_* (the separate, frozen ER GraphRAG POC).

Every query below carries an explicit `logical_document_id = :logical_document_id`
predicate (Stage 7R.2a item 6) -- never implied solely by embedding_model.
The eligibility restriction for search_eligible() is expressed as a SQL
`document_revision_id IN (...)` clause INSIDE the SAME query that does
`ORDER BY embedding <=> ... LIMIT ...` -- never a separate unfiltered
query followed by Python-side filtering.
"""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import Engine, bindparam, create_engine, text

from ingestion_bench.revision_search_benchmark.config import DATABASE_URL, VECTOR_TABLE_NAME
from ingestion_bench.revision_search_benchmark.store import (
    RevisionVectorRecord,
    SearchHit,
    UpsertResult,
    compute_embedding_payload_hash,
    compute_index_hash,
)


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


class PgVectorRevisionStore:
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
        assert self._engine is not None
        with self._engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.execute(
                text(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self._table_name} (
                        embedding_model TEXT NOT NULL,
                        chunk_id TEXT NOT NULL,
                        content_sha256 TEXT NOT NULL,
                        retrieval_text TEXT NOT NULL,
                        logical_document_id TEXT NOT NULL,
                        document_revision_id TEXT NOT NULL,
                        version_label TEXT,
                        revision_number INTEGER,
                        source_document_sha256 TEXT NOT NULL,
                        source_relative_path TEXT NOT NULL,
                        chunk_type TEXT NOT NULL,
                        unit_indices TEXT NOT NULL,
                        heading_path TEXT NOT NULL,
                        source_element_ids TEXT NOT NULL,
                        source_refs TEXT NOT NULL,
                        embedding VECTOR({self._dimension}) NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (chunk_id, embedding_model)
                    )
                    """
                )
            )
            conn.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS {self._table_name}_logical_document_revision_idx "
                    f"ON {self._table_name} (logical_document_id, document_revision_id)"
                )
            )
            conn.commit()

    def existing_content_hashes(self, logical_document_id: str, embedding_model: str) -> dict[str, str]:
        engine = self._ensure_ready()
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"SELECT chunk_id, content_sha256 FROM {self._table_name} "
                    "WHERE logical_document_id = :logical_document_id AND embedding_model = :em"
                ),
                {"logical_document_id": logical_document_id, "em": embedding_model},
            )
            return {row.chunk_id: row.content_sha256 for row in rows}

    def upsert(self, records: list[RevisionVectorRecord]) -> UpsertResult:
        if not records:
            return UpsertResult(written_count=0)
        engine = self._ensure_ready()
        with engine.connect() as conn:
            for record in records:
                conn.execute(
                    text(
                        f"""
                        INSERT INTO {self._table_name} (
                            embedding_model, chunk_id, content_sha256, retrieval_text,
                            logical_document_id, document_revision_id, version_label, revision_number,
                            source_document_sha256, source_relative_path, chunk_type, unit_indices,
                            heading_path, source_element_ids, source_refs,
                            embedding, updated_at
                        ) VALUES (
                            :embedding_model, :chunk_id, :content_sha256, :retrieval_text,
                            :logical_document_id, :document_revision_id, :version_label, :revision_number,
                            :source_document_sha256, :source_relative_path, :chunk_type, :unit_indices,
                            :heading_path, :source_element_ids, :source_refs,
                            CAST(:embedding AS vector), CURRENT_TIMESTAMP
                        )
                        ON CONFLICT (chunk_id, embedding_model) DO UPDATE SET
                            content_sha256 = EXCLUDED.content_sha256,
                            retrieval_text = EXCLUDED.retrieval_text,
                            logical_document_id = EXCLUDED.logical_document_id,
                            document_revision_id = EXCLUDED.document_revision_id,
                            version_label = EXCLUDED.version_label,
                            revision_number = EXCLUDED.revision_number,
                            source_document_sha256 = EXCLUDED.source_document_sha256,
                            source_relative_path = EXCLUDED.source_relative_path,
                            chunk_type = EXCLUDED.chunk_type,
                            unit_indices = EXCLUDED.unit_indices,
                            heading_path = EXCLUDED.heading_path,
                            source_element_ids = EXCLUDED.source_element_ids,
                            source_refs = EXCLUDED.source_refs,
                            embedding = EXCLUDED.embedding,
                            updated_at = CURRENT_TIMESTAMP
                        """
                    ),
                    {
                        "embedding_model": record.embedding_model,
                        "chunk_id": record.chunk_id,
                        "content_sha256": record.content_sha256,
                        "retrieval_text": record.retrieval_text,
                        "logical_document_id": record.logical_document_id,
                        "document_revision_id": record.document_revision_id,
                        "version_label": record.version_label,
                        "revision_number": record.revision_number,
                        "source_document_sha256": record.source_document_sha256,
                        "source_relative_path": record.source_relative_path,
                        "chunk_type": record.chunk_type,
                        "unit_indices": json.dumps(record.unit_indices),
                        "heading_path": json.dumps(record.heading_path),
                        "source_element_ids": json.dumps(record.source_element_ids),
                        "source_refs": json.dumps(record.source_refs),
                        "embedding": _to_vector_literal(record.embedding),
                    },
                )
            conn.commit()
        return UpsertResult(written_count=len(records))

    def _row_to_hit(self, row, score: float) -> SearchHit:
        record = RevisionVectorRecord(
            embedding_model=row["embedding_model"],
            logical_document_id=row["logical_document_id"],
            document_revision_id=row["document_revision_id"],
            version_label=row["version_label"],
            revision_number=row["revision_number"],
            source_document_sha256=row["source_document_sha256"],
            source_relative_path=row["source_relative_path"],
            chunk_id=row["chunk_id"],
            content_sha256=row["content_sha256"],
            retrieval_text=row["retrieval_text"],
            chunk_type=row["chunk_type"],
            unit_indices=json.loads(row["unit_indices"]),
            heading_path=json.loads(row["heading_path"]),
            source_element_ids=json.loads(row["source_element_ids"]),
            source_refs=json.loads(row["source_refs"]),
            embedding=_parse_vector_literal(row["embedding"]),
        )
        return SearchHit(record=record, score=score)

    def search_eligible(
        self,
        *,
        logical_document_id: str,
        embedding_model: str,
        query_vector: list[float],
        eligible_revision_ids: list[str],
        top_k: int,
    ) -> list[SearchHit]:
        if not eligible_revision_ids:
            return []
        engine = self._ensure_ready()
        # The eligibility restriction (document_revision_id IN :ids) AND
        # the logical_document_id scope live in the SAME query as
        # ORDER BY .../LIMIT -- never a separate, broader query filtered
        # afterward in Python.
        stmt = text(
            f"""
            SELECT *, 1 - (embedding <=> CAST(:query_embedding AS vector)) AS score
            FROM {self._table_name}
            WHERE logical_document_id = :logical_document_id AND embedding_model = :em
                AND document_revision_id IN :ids
            ORDER BY embedding <=> CAST(:query_embedding AS vector), chunk_id ASC
            LIMIT :top_k
            """
        ).bindparams(bindparam("ids", expanding=True))
        with engine.connect() as conn:
            rows = conn.execute(
                stmt,
                {
                    "query_embedding": _to_vector_literal(query_vector),
                    "logical_document_id": logical_document_id,
                    "em": embedding_model,
                    "ids": list(eligible_revision_ids),
                    "top_k": top_k,
                },
            ).mappings()
            return [self._row_to_hit(row, float(row["score"])) for row in rows]

    def search_unfiltered(
        self, *, logical_document_id: str, embedding_model: str, query_vector: list[float], top_k: int
    ) -> list[SearchHit]:
        engine = self._ensure_ready()
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT *, 1 - (embedding <=> CAST(:query_embedding AS vector)) AS score
                    FROM {self._table_name}
                    WHERE logical_document_id = :logical_document_id AND embedding_model = :em
                    ORDER BY embedding <=> CAST(:query_embedding AS vector), chunk_id ASC
                    LIMIT :top_k
                    """
                ),
                {
                    "query_embedding": _to_vector_literal(query_vector),
                    "logical_document_id": logical_document_id,
                    "em": embedding_model,
                    "top_k": top_k,
                },
            ).mappings()
            return [self._row_to_hit(row, float(row["score"])) for row in rows]

    def record_count(self, logical_document_id: str, embedding_model: str) -> int:
        engine = self._ensure_ready()
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    f"SELECT COUNT(*) FROM {self._table_name} "
                    "WHERE logical_document_id = :logical_document_id AND embedding_model = :em"
                ),
                {"logical_document_id": logical_document_id, "em": embedding_model},
            )
            return int(result.scalar_one())

    def all_chunk_ids(self, logical_document_id: str, embedding_model: str) -> set[str]:
        engine = self._ensure_ready()
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"SELECT chunk_id FROM {self._table_name} "
                    "WHERE logical_document_id = :logical_document_id AND embedding_model = :em"
                ),
                {"logical_document_id": logical_document_id, "em": embedding_model},
            )
            return {row.chunk_id for row in rows}

    def index_hash(self, logical_document_id: str, embedding_model: str) -> str:
        engine = self._ensure_ready()
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"SELECT chunk_id, content_sha256 FROM {self._table_name} "
                    "WHERE logical_document_id = :logical_document_id AND embedding_model = :em"
                ),
                {"logical_document_id": logical_document_id, "em": embedding_model},
            )
            pairs = [(row.chunk_id, row.content_sha256) for row in rows]
        return compute_index_hash(pairs)

    def embedding_payload_sha256(self, logical_document_id: str, embedding_model: str) -> str:
        engine = self._ensure_ready()
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"SELECT chunk_id, content_sha256, retrieval_text, embedding FROM {self._table_name} "
                    "WHERE logical_document_id = :logical_document_id AND embedding_model = :em"
                ),
                {"logical_document_id": logical_document_id, "em": embedding_model},
            ).mappings()
            # The vector is read back and re-serialized through the SAME
            # fixed-precision literal format used to WRITE it -- this is
            # the ACTUAL persisted representation, round-tripped through
            # Postgres, not the in-process Python floats.
            payload_rows = [
                (
                    row["chunk_id"],
                    row["content_sha256"],
                    hashlib.sha256(row["retrieval_text"].encode("utf-8")).hexdigest(),
                    _to_vector_literal(_parse_vector_literal(row["embedding"])),
                )
                for row in rows
            ]
        return compute_embedding_payload_hash(payload_rows)
