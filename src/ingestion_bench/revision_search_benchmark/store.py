"""Stage 7R.2: the revision-search vector-record model and store
contract -- an ISOLATED index/table, never Stage 7A.1's own frozen
`ingestion_bench_stage7a_vectors` table or code (see
retrieval_baseline/vector_store.py, read-only reference only, never
imported or modified here).

The defining property of every `search_eligible` implementation below:
the eligible-revision-id restriction happens INSIDE the ranking query
(SQL WHERE ... before ORDER BY/LIMIT for Postgres; a pre-filter of the
candidate list before sort/slice for the in-memory reference store) --
never "fetch top-K unfiltered, then discard ineligible hits after the
fact." An empty `eligible_revision_ids` always yields zero hits, never
falls back to "search everything."
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"vector dimension mismatch: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class RevisionVectorRecord(BaseModel):
    """One indexed chunk of one revision of POLICY-RETENTION-001. Every
    field a provenance-rich authority-aware result must expose is carried
    here, copied verbatim from the source CanonicalChunk / its
    DocumentRevisionContext lineage fields -- never re-derived, never
    guessed. Carries no authority label of any kind -- that comes
    exclusively from Stage 7R.1's resolver at query time."""

    model_config = ConfigDict(extra="forbid")

    embedding_model: str

    logical_document_id: str
    document_revision_id: str
    version_label: str | None = None
    revision_number: int | None = None
    source_document_sha256: str

    chunk_id: str
    content_sha256: str
    retrieval_text: str
    chunk_type: str
    heading_path: list[str] = Field(default_factory=list)
    source_element_ids: list[str] = Field(default_factory=list)

    embedding: list[float]


class UpsertResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    written_count: int


class SearchHit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record: RevisionVectorRecord
    score: float


def compute_index_hash(records: list[tuple[str, str]]) -> str:
    """records: (chunk_id, content_sha256) pairs -- never over raw
    floating-point embedding values (platform-sensitive); shared
    definition so index_hash means the same thing in every store impl."""
    payload = sorted(records)
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


class RevisionVectorStore(Protocol):
    def existing_content_hashes(self, embedding_model: str) -> dict[str, str]:
        """chunk_id -> content_sha256 for every record already stored
        under this embedding_model -- lets the indexer skip re-embedding
        unchanged chunks entirely."""
        ...

    def upsert(self, records: list[RevisionVectorRecord]) -> UpsertResult:
        """Idempotent: the same (chunk_id, embedding_model) key is never
        duplicated -- a repeat upsert replaces the prior row."""
        ...

    def search_eligible(
        self, *, embedding_model: str, query_vector: list[float], eligible_revision_ids: list[str], top_k: int
    ) -> list[SearchHit]:
        """THE authority-aware search primitive: candidates are
        restricted to `eligible_revision_ids` BEFORE ranking/limiting,
        never after. An empty eligible_revision_ids list always returns
        []. Ranked by similarity descending; ties broken by chunk_id
        ascending, for deterministic, reproducible results."""
        ...

    def search_unfiltered(self, *, embedding_model: str, query_vector: list[float], top_k: int) -> list[SearchHit]:
        """No revision restriction at all -- used ONLY for the item 5
        unfiltered-vs-authority-aware comparison, never for an actual
        authority-aware result."""
        ...

    def record_count(self, embedding_model: str) -> int: ...

    def all_chunk_ids(self, embedding_model: str) -> set[str]: ...

    def index_hash(self, embedding_model: str) -> str: ...


class InMemoryRevisionVectorStore:
    """Pure-Python reference implementation -- no external database. Used
    by the default (fake-embedding) test suite; never used to produce
    this stage's real reported results."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], RevisionVectorRecord] = {}

    def existing_content_hashes(self, embedding_model: str) -> dict[str, str]:
        return {
            chunk_id: record.content_sha256
            for (model, chunk_id), record in self._records.items()
            if model == embedding_model
        }

    def upsert(self, records: list[RevisionVectorRecord]) -> UpsertResult:
        for record in records:
            self._records[(record.embedding_model, record.chunk_id)] = record
        return UpsertResult(written_count=len(records))

    def _candidates(self, embedding_model: str) -> list[RevisionVectorRecord]:
        return [record for (model, _chunk_id), record in self._records.items() if model == embedding_model]

    def search_eligible(
        self, *, embedding_model: str, query_vector: list[float], eligible_revision_ids: list[str], top_k: int
    ) -> list[SearchHit]:
        if not eligible_revision_ids:
            return []
        eligible = set(eligible_revision_ids)
        # Restriction happens HERE, before scoring/sorting/slicing --
        # never "score everything, then drop ineligible hits."
        pool = [r for r in self._candidates(embedding_model) if r.document_revision_id in eligible]
        scored = [(r, cosine_similarity(query_vector, r.embedding)) for r in pool]
        scored.sort(key=lambda pair: (-pair[1], pair[0].chunk_id))
        return [SearchHit(record=r, score=s) for r, s in scored[:top_k]]

    def search_unfiltered(self, *, embedding_model: str, query_vector: list[float], top_k: int) -> list[SearchHit]:
        scored = [(r, cosine_similarity(query_vector, r.embedding)) for r in self._candidates(embedding_model)]
        scored.sort(key=lambda pair: (-pair[1], pair[0].chunk_id))
        return [SearchHit(record=r, score=s) for r, s in scored[:top_k]]

    def record_count(self, embedding_model: str) -> int:
        return len(self._candidates(embedding_model))

    def all_chunk_ids(self, embedding_model: str) -> set[str]:
        return {r.chunk_id for r in self._candidates(embedding_model)}

    def index_hash(self, embedding_model: str) -> str:
        return compute_index_hash([(r.chunk_id, r.content_sha256) for r in self._candidates(embedding_model)])
