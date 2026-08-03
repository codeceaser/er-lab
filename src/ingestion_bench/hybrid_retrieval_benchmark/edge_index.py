"""Stage 7B.2: the isolated edge-semantic index.

Embeds each existing GraphEdgeAssertion by a representation derived ONLY
from its own already-extracted content -- canonical subject + predicate +
canonical object + supporting_text -- never from the query or any
evaluation truth, and never inferring/repairing/normalizing a new
relationship. Semantic edge search returns only AUTHORITY-ELIGIBLE edges:
the eligibility restriction is applied in the store predicate BEFORE
similarity ranking and LIMIT (a SQL `document_revision_id IN (...)` for
Postgres; a pre-filter of the candidate list for the in-memory store).
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from ingestion_bench.graph_retrieval_benchmark.model import GraphEdgeAssertion, GraphNode
from ingestion_bench.hybrid_retrieval_benchmark.model import EdgeEmbeddingRecord
from ingestion_bench.retrieval_baseline.embeddings import EmbeddingProvider
from ingestion_bench.revision_search_benchmark.store import cosine_similarity


class EdgeIndexManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    embedding_model: str
    edge_count: int
    payload_sha256: str
    build_latency_seconds: float
    storage_estimate_bytes: int
    query_embedding_calls: int


def build_edge_representation(edge: GraphEdgeAssertion, node_by_id: dict[str, GraphNode]) -> str:
    subj = node_by_id[edge.subject_node_id].canonical_name if edge.subject_node_id in node_by_id else edge.subject_node_id
    obj = node_by_id[edge.object_node_id].canonical_name if edge.object_node_id in node_by_id else edge.object_node_id
    return f"{subj} {edge.predicate} {obj}. {edge.supporting_text}"


def _edge_payload_hash(records: list[EdgeEmbeddingRecord]) -> str:
    payload = sorted((r.edge_assertion_id, r.representation) for r in records)
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def build_edge_embedding_records(
    edges: list[GraphEdgeAssertion], node_by_id: dict[str, GraphNode], embedding_provider: EmbeddingProvider
) -> tuple[list[EdgeEmbeddingRecord], EdgeIndexManifest]:
    start = time.perf_counter()
    reprs = [build_edge_representation(e, node_by_id) for e in edges]
    embeddings = embedding_provider.embed(reprs).vectors if edges else []
    records: list[EdgeEmbeddingRecord] = []
    for edge, representation, vector in zip(edges, reprs, embeddings):
        records.append(EdgeEmbeddingRecord(
            edge_assertion_id=edge.edge_assertion_id, subject_node_id=edge.subject_node_id,
            subject_canonical_name=node_by_id[edge.subject_node_id].canonical_name if edge.subject_node_id in node_by_id else edge.subject_node_id,
            object_node_id=edge.object_node_id,
            object_canonical_name=node_by_id[edge.object_node_id].canonical_name if edge.object_node_id in node_by_id else edge.object_node_id,
            predicate=edge.predicate, logical_document_id=edge.logical_document_id, document_revision_id=edge.document_revision_id,
            supporting_chunk_id=edge.supporting_chunk_id, supporting_content_sha256=edge.supporting_content_sha256,
            supporting_text=edge.supporting_text, source_relative_path=edge.source_relative_path,
            source_document_sha256=edge.source_document_sha256, unit_indices=list(edge.unit_indices),
            heading_path=list(edge.heading_path), source_element_ids=list(edge.source_element_ids),
            source_refs=list(edge.source_refs), representation=representation, embedding=vector,
        ))
    manifest = EdgeIndexManifest(
        embedding_model=embedding_provider.model_identity, edge_count=len(records), payload_sha256=_edge_payload_hash(records),
        build_latency_seconds=time.perf_counter() - start,
        storage_estimate_bytes=sum(len(r.model_dump_json()) for r in records), query_embedding_calls=1 if edges else 0,
    )
    return records, manifest


class EdgeSemanticIndex(Protocol):
    def semantic_search_eligible(self, *, query_vector: list[float], eligible_revision_ids: list[str], top_n: int) -> list[tuple[EdgeEmbeddingRecord, float]]:
        """Authority-eligible edges only, ranked by cosine similarity
        descending, ties by edge_assertion_id. Empty eligible set -> []."""
        ...


class InMemoryEdgeSemanticIndex:
    def __init__(self, records: list[EdgeEmbeddingRecord]) -> None:
        self._records = records

    def semantic_search_eligible(self, *, query_vector: list[float], eligible_revision_ids: list[str], top_n: int) -> list[tuple[EdgeEmbeddingRecord, float]]:
        if not eligible_revision_ids:
            return []
        eligible = set(eligible_revision_ids)
        # Eligibility restriction BEFORE ranking.
        pool = [r for r in self._records if r.document_revision_id in eligible]
        scored = [(r, cosine_similarity(query_vector, r.embedding)) for r in pool]
        scored.sort(key=lambda pair: (-pair[1], pair[0].edge_assertion_id))
        return scored[:top_n]


class PgEdgeSemanticIndexUnavailable(RuntimeError):
    """Raised when DATABASE_URL is not configured or unreachable."""


class PgEdgeSemanticIndex:
    """The real, persisted edge-semantic index -- Postgres + pgvector,
    isolated table. The eligibility restriction is a SQL
    `document_revision_id IN (...)` clause in the SAME query as the
    `ORDER BY embedding <=> ... LIMIT ...`."""

    def __init__(self, embedding_dimension: int, table_name: str | None = None, database_url: str | None = None) -> None:
        from ingestion_bench.hybrid_retrieval_benchmark.config import DATABASE_URL, EDGE_EMBEDDING_TABLE

        self._database_url = database_url or DATABASE_URL
        if not self._database_url:
            raise PgEdgeSemanticIndexUnavailable("DATABASE_URL is not set -- pass database_url= explicitly")
        self._table = table_name or EDGE_EMBEDDING_TABLE
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
                raise PgEdgeSemanticIndexUnavailable(f"could not connect: {type(exc).__name__}: {exc}") from exc
            with engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.execute(text(f"DROP TABLE IF EXISTS {self._table} CASCADE"))
                conn.execute(text(f"""
                    CREATE TABLE {self._table} (
                        edge_assertion_id TEXT PRIMARY KEY,
                        document_revision_id TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        embedding VECTOR({self._dimension}) NOT NULL
                    )
                """))
                conn.execute(text(f"CREATE INDEX {self._table}_rev_idx ON {self._table} (document_revision_id)"))
                conn.commit()
            self._engine = engine
        return self._engine

    def load(self, records: list[EdgeEmbeddingRecord]) -> None:
        from sqlalchemy import text

        engine = self._ensure()
        with engine.connect() as conn:
            for r in records:
                literal = "[" + ",".join(f"{v:.8f}" for v in r.embedding) + "]"
                conn.execute(
                    text(f"INSERT INTO {self._table} (edge_assertion_id, document_revision_id, payload, embedding) "
                         "VALUES (:id, :rev, :p, CAST(:emb AS vector)) ON CONFLICT (edge_assertion_id) DO NOTHING"),
                    {"id": r.edge_assertion_id, "rev": r.document_revision_id, "p": r.model_dump_json(), "emb": literal},
                )
            conn.commit()

    def semantic_search_eligible(self, *, query_vector: list[float], eligible_revision_ids: list[str], top_n: int) -> list[tuple[EdgeEmbeddingRecord, float]]:
        if not eligible_revision_ids:
            return []
        from sqlalchemy import bindparam, text

        engine = self._ensure()
        literal = "[" + ",".join(f"{v:.8f}" for v in query_vector) + "]"
        stmt = text(
            f"SELECT payload, 1 - (embedding <=> CAST(:q AS vector)) AS score FROM {self._table} "
            "WHERE document_revision_id IN :ids ORDER BY embedding <=> CAST(:q AS vector), edge_assertion_id ASC LIMIT :n"
        ).bindparams(bindparam("ids", expanding=True))
        with engine.connect() as conn:
            rows = conn.execute(stmt, {"q": literal, "ids": list(eligible_revision_ids), "n": top_n}).mappings()
            return [(EdgeEmbeddingRecord.model_validate_json(row["payload"]), float(row["score"])) for row in rows]
