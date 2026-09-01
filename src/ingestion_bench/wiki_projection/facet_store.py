"""Stage 7C.1 persistence: the three Revision 6 SS10.3 tables.

    edib_stage7c_facet             the compilation record (final, post-pass-3)
    edib_stage7c_facet_embedding   the frozen facet vectors + provenance
    edib_stage7c_compilation_audit SS8A/SS8E evidence and Gate-Q inputs

Deliberately SEPARATE from `pg_store.py`, which owns the Stage 7C.0
projection-only surface (`anchor`, `anchor_posting`). Stage 7C.0's persistence
responsibilities are frozen, and mixing a 7C.1 representation into that module
would blur a boundary the whole experiment depends on.

Two invariants this module holds:

* **No authority state is ever stored.** Authority is query-time and dynamic
  (SS5.1); the read path takes `eligible_revision_ids` as a parameter and applies
  it in the SAME statement as ranking/LIMIT, never afterwards.
* **This is storage, not retrieval.** `search_eligible_facets` exists so Stage
  7C.2 can later load the frozen vectors without rebuilding them; it performs no
  hub expansion, no traversal, and no final-K policy. The 7C.2 pipeline is not
  implemented here.
"""

from __future__ import annotations

import json
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class FacetRecord(BaseModel):
    """One final, post-pass-3 compilation record. `compiled` carries the
    validated + adjudicated representation and the surviving derived links."""

    model_config = ConfigDict(extra="forbid")

    page_key: str
    document_revision_id: str
    validation_state: str
    facet_membership_hash: str
    facet_hash: str
    run_id: int
    compiled: dict


class FacetEmbeddingRow(BaseModel):
    """One frozen facet vector with the provenance SS6.2 requires."""

    model_config = ConfigDict(extra="forbid")

    page_key: str
    document_revision_id: str
    embedding: list[float]
    embedding_dimension: int
    embedding_sha256: str
    payload_sha256: str
    payload_text: str
    component_manifest: list[dict]
    verdict_set_sha256: str
    projection_hash: str
    embedding_model: str
    compiler_model_identity: str
    prompt_version: str
    prompt_sha256: str
    run_id: int
    source_chunk_ids: list[str]


class CompilationAuditRow(BaseModel):
    """Run-1 mechanical + owner-derived audit evidence for one facet."""

    model_config = ConfigDict(extra="forbid")

    page_key: str
    document_revision_id: str
    run_id: int

    rejected_claims: list[dict] = Field(default_factory=list)
    out_of_page_scope_claims: list[dict] = Field(default_factory=list)
    uncertain_claims: list[dict] = Field(default_factory=list)
    unlinkable_claim_endpoints: list[dict] = Field(default_factory=list)
    unresolved_identity_mentions: list[str] = Field(default_factory=list)

    adjudication_verdicts: dict[str, str] = Field(default_factory=dict)
    adjudication_reasons: dict[str, str] = Field(default_factory=dict)
    withdrawn_claim_ids: list[str] = Field(default_factory=list)
    withdrawn_summary_ids: list[str] = Field(default_factory=list)
    withdrawn_alias_ids: list[str] = Field(default_factory=list)
    demoted_to_out_of_page_scope: list[str] = Field(default_factory=list)

    payload_truncated_components: list[int] = Field(default_factory=list)
    summary_payload_dedup_count: int = 0

    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None
    latency_seconds: float = 0.0
    model_identity: str = ""
    prompt_version: str = ""
    prompt_sha256: str = ""
    ceiling_breaches: list[str] = Field(default_factory=list)
    generation_failed: bool = False
    generation_error: str | None = None


class Stage7C1Store(Protocol):
    def upsert_facets(self, records: list[FacetRecord]) -> int: ...

    def upsert_facet_embeddings(self, rows: list[FacetEmbeddingRow]) -> int: ...

    def upsert_compilation_audit(self, rows: list[CompilationAuditRow]) -> int: ...

    def facet_count(self) -> int: ...

    def facet_embedding_count(self) -> int: ...

    def compilation_audit_count(self) -> int: ...

    def all_facet_embeddings(self) -> list[FacetEmbeddingRow]: ...

    def search_eligible_facets(
        self, *, query_vector: list[float], eligible_revision_ids: list[str], top_k: int
    ) -> list[tuple[FacetEmbeddingRow, float]]:
        """Authority-first facet vector search: candidates are restricted to
        `eligible_revision_ids` BEFORE ranking/limiting, never after. An empty
        eligible set yields [] -- never 'search everything'.

        Provided so Stage 7C.2 can load and rank the FROZEN vectors without
        recomputing them. It is a primitive, not the 7C.2 pipeline.
        """
        ...


def cosine_similarity(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = sum(a * a for a in left) ** 0.5
    right_norm = sum(b * b for b in right) ** 0.5
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


class InMemoryStage7C1Store:
    """Pure-Python reference implementation -- no database. Keyed by
    (page_key, document_revision_id), so re-upserting an unchanged closure is a
    no-op rather than a duplicate."""

    def __init__(self) -> None:
        self._facets: dict[tuple[str, str], FacetRecord] = {}
        self._embeddings: dict[tuple[str, str], FacetEmbeddingRow] = {}
        self._audit: dict[tuple[str, str], CompilationAuditRow] = {}

    @staticmethod
    def _key(record) -> tuple[str, str]:
        return (record.page_key, record.document_revision_id)

    def upsert_facets(self, records: list[FacetRecord]) -> int:
        for record in records:
            self._facets[self._key(record)] = record
        return len(records)

    def upsert_facet_embeddings(self, rows: list[FacetEmbeddingRow]) -> int:
        for row in rows:
            self._embeddings[self._key(row)] = row
        return len(rows)

    def upsert_compilation_audit(self, rows: list[CompilationAuditRow]) -> int:
        for row in rows:
            self._audit[self._key(row)] = row
        return len(rows)

    def facet_count(self) -> int:
        return len(self._facets)

    def facet_embedding_count(self) -> int:
        return len(self._embeddings)

    def compilation_audit_count(self) -> int:
        return len(self._audit)

    def all_facet_embeddings(self) -> list[FacetEmbeddingRow]:
        return [self._embeddings[key] for key in sorted(self._embeddings)]

    def get_facet(self, page_key: str, document_revision_id: str) -> FacetRecord | None:
        return self._facets.get((page_key, document_revision_id))

    def search_eligible_facets(
        self, *, query_vector: list[float], eligible_revision_ids: list[str], top_k: int
    ) -> list[tuple[FacetEmbeddingRow, float]]:
        if not eligible_revision_ids:
            return []
        eligible = set(eligible_revision_ids)
        # Restriction happens HERE, before scoring/sorting/slicing.
        pool = [row for row in self._embeddings.values() if row.document_revision_id in eligible]
        scored = [(row, cosine_similarity(query_vector, row.embedding)) for row in pool]
        scored.sort(key=lambda pair: (-pair[1], pair[0].page_key, pair[0].document_revision_id))
        return scored[:top_k]


class PgStage7C1Store:
    """Isolated Postgres implementation of the three SS10.3 Stage 7C.1 tables.

    Mirrors the Stage 7B.2a / 7C.0 pattern: this stage's OWN tables only, and
    authority filtering expressed as `document_revision_id = ANY(:eligible)` in
    the SAME statement that ranks and limits.
    """

    def __init__(
        self,
        *,
        database_url: str | None = None,
        embedding_dimension: int = 384,
        facet_table: str = "edib_stage7c_facet",
        embedding_table: str = "edib_stage7c_facet_embedding",
        audit_table: str = "edib_stage7c_compilation_audit",
    ) -> None:
        from ingestion_bench.wiki_projection import config

        self._database_url = database_url or config.DATABASE_URL
        self._dimension = embedding_dimension
        self._facet_table = facet_table
        self._embedding_table = embedding_table
        self._audit_table = audit_table
        self._engine = None

    def _ensure_ready(self):
        if self._engine is not None:
            return self._engine
        from sqlalchemy import create_engine, text

        engine = create_engine(self._database_url)
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.execute(
                text(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self._facet_table} (
                        page_key TEXT NOT NULL,
                        document_revision_id TEXT NOT NULL,
                        validation_state TEXT NOT NULL,
                        facet_membership_hash TEXT NOT NULL,
                        facet_hash TEXT NOT NULL,
                        run_id INTEGER NOT NULL,
                        compiled JSONB NOT NULL,
                        PRIMARY KEY (page_key, document_revision_id)
                    )
                    """
                )
            )
            conn.execute(
                text(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self._embedding_table} (
                        page_key TEXT NOT NULL,
                        document_revision_id TEXT NOT NULL,
                        embedding VECTOR({self._dimension}) NOT NULL,
                        embedding_dimension INTEGER NOT NULL,
                        embedding_sha256 TEXT NOT NULL,
                        payload_sha256 TEXT NOT NULL,
                        payload_text TEXT NOT NULL,
                        component_manifest JSONB NOT NULL,
                        verdict_set_sha256 TEXT NOT NULL,
                        projection_hash TEXT NOT NULL,
                        embedding_model TEXT NOT NULL,
                        compiler_model_identity TEXT NOT NULL,
                        prompt_version TEXT NOT NULL,
                        prompt_sha256 TEXT NOT NULL,
                        run_id INTEGER NOT NULL,
                        source_chunk_ids JSONB NOT NULL,
                        PRIMARY KEY (page_key, document_revision_id)
                    )
                    """
                )
            )
            conn.execute(
                text(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self._audit_table} (
                        page_key TEXT NOT NULL,
                        document_revision_id TEXT NOT NULL,
                        run_id INTEGER NOT NULL,
                        audit JSONB NOT NULL,
                        PRIMARY KEY (page_key, document_revision_id)
                    )
                    """
                )
            )
            # SS10.3: indexed on document_revision_id, the column every
            # authority-filtered read uses.
            conn.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS {self._embedding_table}_revision_idx "
                    f"ON {self._embedding_table} (document_revision_id)"
                )
            )
            conn.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS {self._facet_table}_page_idx "
                    f"ON {self._facet_table} (page_key, document_revision_id)"
                )
            )
            conn.commit()
        self._engine = engine
        return engine

    def upsert_facets(self, records: list[FacetRecord]) -> int:
        from sqlalchemy import text

        engine = self._ensure_ready()
        with engine.connect() as conn:
            for record in records:
                conn.execute(
                    text(
                        f"""
                        INSERT INTO {self._facet_table}
                            (page_key, document_revision_id, validation_state, facet_membership_hash,
                             facet_hash, run_id, compiled)
                        VALUES (:page_key, :revision, :state, :membership, :facet_hash, :run_id,
                                CAST(:compiled AS JSONB))
                        ON CONFLICT (page_key, document_revision_id) DO UPDATE SET
                            validation_state = EXCLUDED.validation_state,
                            facet_hash = EXCLUDED.facet_hash,
                            compiled = EXCLUDED.compiled
                        """
                    ),
                    {
                        "page_key": record.page_key, "revision": record.document_revision_id,
                        "state": record.validation_state, "membership": record.facet_membership_hash,
                        "facet_hash": record.facet_hash, "run_id": record.run_id,
                        "compiled": json.dumps(record.compiled),
                    },
                )
            conn.commit()
        return len(records)

    def upsert_facet_embeddings(self, rows: list[FacetEmbeddingRow]) -> int:
        from sqlalchemy import text

        engine = self._ensure_ready()
        with engine.connect() as conn:
            for row in rows:
                conn.execute(
                    text(
                        f"""
                        INSERT INTO {self._embedding_table}
                            (page_key, document_revision_id, embedding, embedding_dimension,
                             embedding_sha256, payload_sha256, payload_text, component_manifest,
                             verdict_set_sha256, projection_hash, embedding_model,
                             compiler_model_identity, prompt_version, prompt_sha256, run_id,
                             source_chunk_ids)
                        VALUES (:page_key, :revision, :embedding, :dim, :embedding_sha, :payload_sha,
                                :payload_text, CAST(:manifest AS JSONB), :verdict_sha, :projection,
                                :embedding_model, :compiler_model, :prompt_version, :prompt_sha,
                                :run_id, CAST(:chunks AS JSONB))
                        ON CONFLICT (page_key, document_revision_id) DO UPDATE SET
                            embedding = EXCLUDED.embedding,
                            embedding_sha256 = EXCLUDED.embedding_sha256,
                            payload_sha256 = EXCLUDED.payload_sha256,
                            payload_text = EXCLUDED.payload_text
                        """
                    ),
                    {
                        "page_key": row.page_key, "revision": row.document_revision_id,
                        "embedding": json.dumps(row.embedding), "dim": row.embedding_dimension,
                        "embedding_sha": row.embedding_sha256, "payload_sha": row.payload_sha256,
                        "payload_text": row.payload_text,
                        "manifest": json.dumps(row.component_manifest),
                        "verdict_sha": row.verdict_set_sha256, "projection": row.projection_hash,
                        "embedding_model": row.embedding_model,
                        "compiler_model": row.compiler_model_identity,
                        "prompt_version": row.prompt_version, "prompt_sha": row.prompt_sha256,
                        "run_id": row.run_id, "chunks": json.dumps(row.source_chunk_ids),
                    },
                )
            conn.commit()
        return len(rows)

    def upsert_compilation_audit(self, rows: list[CompilationAuditRow]) -> int:
        from sqlalchemy import text

        engine = self._ensure_ready()
        with engine.connect() as conn:
            for row in rows:
                conn.execute(
                    text(
                        f"""
                        INSERT INTO {self._audit_table} (page_key, document_revision_id, run_id, audit)
                        VALUES (:page_key, :revision, :run_id, CAST(:audit AS JSONB))
                        ON CONFLICT (page_key, document_revision_id) DO UPDATE SET
                            audit = EXCLUDED.audit
                        """
                    ),
                    {
                        "page_key": row.page_key, "revision": row.document_revision_id,
                        "run_id": row.run_id, "audit": row.model_dump_json(),
                    },
                )
            conn.commit()
        return len(rows)

    def _count(self, table: str) -> int:
        from sqlalchemy import text

        engine = self._ensure_ready()
        with engine.connect() as conn:
            return int(conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0)

    def facet_count(self) -> int:
        return self._count(self._facet_table)

    def facet_embedding_count(self) -> int:
        return self._count(self._embedding_table)

    def compilation_audit_count(self) -> int:
        return self._count(self._audit_table)

    def _row(self, mapping) -> FacetEmbeddingRow:
        embedding = mapping["embedding"]
        if isinstance(embedding, str):
            embedding = json.loads(embedding)
        return FacetEmbeddingRow(
            page_key=mapping["page_key"], document_revision_id=mapping["document_revision_id"],
            embedding=list(embedding), embedding_dimension=mapping["embedding_dimension"],
            embedding_sha256=mapping["embedding_sha256"], payload_sha256=mapping["payload_sha256"],
            payload_text=mapping["payload_text"], component_manifest=list(mapping["component_manifest"]),
            verdict_set_sha256=mapping["verdict_set_sha256"], projection_hash=mapping["projection_hash"],
            embedding_model=mapping["embedding_model"],
            compiler_model_identity=mapping["compiler_model_identity"],
            prompt_version=mapping["prompt_version"], prompt_sha256=mapping["prompt_sha256"],
            run_id=mapping["run_id"], source_chunk_ids=list(mapping["source_chunk_ids"]),
        )

    def all_facet_embeddings(self) -> list[FacetEmbeddingRow]:
        from sqlalchemy import text

        engine = self._ensure_ready()
        with engine.connect() as conn:
            rows = conn.execute(
                text(f"SELECT * FROM {self._embedding_table} ORDER BY page_key, document_revision_id")
            ).mappings().all()
        return [self._row(r) for r in rows]

    def search_eligible_facets(
        self, *, query_vector: list[float], eligible_revision_ids: list[str], top_k: int
    ) -> list[tuple[FacetEmbeddingRow, float]]:
        """Authority restriction and ranking in ONE statement (SS0 pattern).
        Empty eligible set -> []."""
        from sqlalchemy import text

        if not eligible_revision_ids:
            return []
        engine = self._ensure_ready()
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT *, 1 - (embedding <=> CAST(:q AS VECTOR)) AS similarity
                    FROM {self._embedding_table}
                    WHERE document_revision_id = ANY(:eligible)
                    ORDER BY embedding <=> CAST(:q AS VECTOR), page_key, document_revision_id
                    LIMIT :k
                    """
                ),
                {"q": json.dumps(query_vector), "eligible": list(eligible_revision_ids), "k": top_k},
            ).mappings().all()
        return [(self._row(r), float(r["similarity"])) for r in rows]
