"""Stage 7B.2a: the isolated authority-aware vector candidate store for
Vector-derived graph seeds.

Holds the frozen chunk embeddings; `search_eligible` returns the top
candidate chunks for a query with the eligibility restriction applied
BEFORE similarity ranking + LIMIT (a SQL `document_revision_id IN (...)`
for Postgres; a pre-filter for the in-memory store). An empty eligible
set yields no candidates. This is a SEED source only -- the final Vector
ranking (mode V) is the frozen Stage 7B.0 result, never this store.
"""

from __future__ import annotations

from typing import Protocol

from ingestion_bench.revision_search_benchmark.store import RevisionVectorRecord, cosine_similarity


class VectorCandidateStore(Protocol):
    def search_eligible(self, *, query_vector: list[float], eligible_revision_ids: list[str], pool_size: int) -> list[tuple[str, float]]:
        """(chunk_id, similarity) for the top pool_size AUTHORITY-ELIGIBLE
        chunks, eligibility applied before ranking. Empty eligible -> []."""
        ...


class InMemoryVectorCandidateStore:
    def __init__(self, records: list[RevisionVectorRecord]) -> None:
        self._records = records

    def search_eligible(self, *, query_vector: list[float], eligible_revision_ids: list[str], pool_size: int) -> list[tuple[str, float]]:
        if not eligible_revision_ids:
            return []
        eligible = set(eligible_revision_ids)
        pool = [r for r in self._records if r.document_revision_id in eligible]
        scored = [(r.chunk_id, cosine_similarity(query_vector, r.embedding)) for r in pool]
        scored.sort(key=lambda pair: (-pair[1], pair[0]))
        return scored[:pool_size]


class PgVectorCandidateStoreUnavailable(RuntimeError):
    pass


class PgVectorCandidateStore:
    """Real, persisted authority-aware candidate store -- Postgres +
    pgvector, isolated table. The eligibility restriction is a SQL
    `document_revision_id IN (...)` in the SAME query as the
    `ORDER BY embedding <=> ... LIMIT ...`."""

    def __init__(self, embedding_dimension: int, table_name: str, database_url: str | None = None) -> None:
        from ingestion_bench.hybrid_retrieval_benchmark.config import DATABASE_URL

        self._database_url = database_url or DATABASE_URL
        if not self._database_url:
            raise PgVectorCandidateStoreUnavailable("DATABASE_URL is not set -- pass database_url= explicitly")
        self._table = table_name
        self._dimension = embedding_dimension
        self._engine = None

    def _ensure(self):
        from sqlalchemy import create_engine, text

        if self._engine is None:
            try:
                engine = create_engine(self._database_url, future=True)
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
            except Exception as exc:  # noqa: BLE001
                raise PgVectorCandidateStoreUnavailable(f"could not connect: {type(exc).__name__}: {exc}") from exc
            with engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.execute(text(f"DROP TABLE IF EXISTS {self._table} CASCADE"))
                conn.execute(text(f"""
                    CREATE TABLE {self._table} (
                        chunk_id TEXT PRIMARY KEY,
                        document_revision_id TEXT NOT NULL,
                        embedding VECTOR({self._dimension}) NOT NULL
                    )
                """))
                conn.execute(text(f"CREATE INDEX {self._table}_rev_idx ON {self._table} (document_revision_id)"))
                conn.commit()
            self._engine = engine
        return self._engine

    def load(self, records: list[RevisionVectorRecord]) -> None:
        from sqlalchemy import text

        engine = self._ensure()
        with engine.connect() as conn:
            for r in records:
                literal = "[" + ",".join(f"{v:.8f}" for v in r.embedding) + "]"
                conn.execute(
                    text(f"INSERT INTO {self._table} (chunk_id, document_revision_id, embedding) "
                         "VALUES (:c, :rev, CAST(:emb AS vector)) ON CONFLICT (chunk_id) DO NOTHING"),
                    {"c": r.chunk_id, "rev": r.document_revision_id, "emb": literal},
                )
            conn.commit()

    def search_eligible(self, *, query_vector: list[float], eligible_revision_ids: list[str], pool_size: int) -> list[tuple[str, float]]:
        if not eligible_revision_ids:
            return []
        from sqlalchemy import bindparam, text

        engine = self._ensure()
        literal = "[" + ",".join(f"{v:.8f}" for v in query_vector) + "]"
        stmt = text(
            f"SELECT chunk_id, 1 - (embedding <=> CAST(:q AS vector)) AS score FROM {self._table} "
            "WHERE document_revision_id IN :ids ORDER BY embedding <=> CAST(:q AS vector), chunk_id ASC LIMIT :n"
        ).bindparams(bindparam("ids", expanding=True))
        with engine.connect() as conn:
            rows = conn.execute(stmt, {"q": literal, "ids": list(eligible_revision_ids), "n": pool_size}).mappings()
            return [(row["chunk_id"], float(row["score"])) for row in rows]
