"""Stage 7A.1: the vector-record model and the vector-store contract.

Exactly ONE real, persisted vector-store implementation is configured
for this stage (Postgres + pgvector -- see pgvector_store.py), never a
provider/plugin framework. `InMemoryVectorStore` here exists ONLY for
the unit-test suite (and as the shared reference implementation of the
idempotency/search contract every store must satisfy) -- it requires no
external database and is never used to produce this stage's real,
reported results.

CanonicalChunk is never modified to add vector-specific fields; every
field below is either copied verbatim from a CanonicalChunk (via
corpus.TaggedChunk) or is genuinely new information this stage adds
(corpus_profile, embedding_model, embedding).
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


class VectorRecord(BaseModel):
    """One indexed chunk, for one corpus profile, under one embedding
    model. Every provenance field a retrieval result must later expose
    is carried here, copied from the source CanonicalChunk (never
    re-derived, never guessed)."""

    model_config = ConfigDict(extra="forbid")

    corpus_profile: str
    embedding_model: str

    chunk_id: str
    content_sha256: str
    retrieval_text: str

    fixture: str
    doc_id: str
    source_format: str

    source_element_ids: list[str] = Field(default_factory=list)
    heading_source_element_ids: list[str] = Field(default_factory=list)
    annotation_ids: list[str] = Field(default_factory=list)
    unit_indices: list[int] = Field(default_factory=list)
    source_refs: list[dict] = Field(default_factory=list)
    heading_path: list[str] = Field(default_factory=list)
    contains_model_derived: bool

    embedding: list[float]


class UpsertResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    written_count: int


class SearchHit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record: VectorRecord
    score: float


class VectorStore(Protocol):
    def existing_content_hashes(self, corpus_profile: str, embedding_model: str) -> dict[str, str]:
        """chunk_id -> content_sha256 for every record already stored
        under (corpus_profile, embedding_model). Used by the indexer to
        decide which chunks can skip re-embedding entirely."""
        ...

    def upsert(self, records: list[VectorRecord]) -> UpsertResult:
        """Idempotent: the same (corpus_profile, chunk_id, embedding_model)
        key is NEVER duplicated -- a repeat upsert with the same key
        replaces the prior row (e.g. if content_sha256 changed), never
        adds a second one."""
        ...

    def search(
        self, corpus_profile: str, embedding_model: str, query_vector: list[float], top_k: int
    ) -> list[SearchHit]:
        """Ranked by cosine similarity descending; ties broken by
        chunk_id ascending, so results are deterministic and reproducible
        for a fixed corpus + query vector."""
        ...

    def record_count(self, corpus_profile: str, embedding_model: str) -> int: ...

    def all_chunk_ids(self, corpus_profile: str, embedding_model: str) -> set[str]:
        """Every chunk_id actually present in this index -- used to scope
        gold-evidence resolution to "what this corpus profile can
        actually retrieve," never via a similarity search (cosine
        distance/similarity against an all-zero or otherwise degenerate
        query vector is undefined for some backends, e.g. pgvector's
        `<=>` operator)."""
        ...

    def index_hash(self, corpus_profile: str, embedding_model: str) -> str:
        """Deterministic SHA-256 over the sorted (chunk_id, content_sha256)
        identity of every record in this index -- never over the raw
        floating-point embedding values, which would make the hash
        needlessly sensitive to embedding-library floating-point
        reproducibility across platforms."""
        ...


def compute_index_hash(records: list[tuple[str, str]]) -> str:
    """records: (chunk_id, content_sha256) pairs. Shared by every
    VectorStore implementation so index_hash is defined identically
    everywhere."""
    payload = sorted(records)
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


class InMemoryVectorStore:
    """Pure-Python, in-process reference implementation -- no external
    database, no filesystem persistence. Used by the unit-test suite
    (and by any caller that explicitly wants a disposable, hermetic
    store); never used to produce this stage's real reported results."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str], VectorRecord] = {}

    def existing_content_hashes(self, corpus_profile: str, embedding_model: str) -> dict[str, str]:
        return {
            chunk_id: record.content_sha256
            for (profile, model, chunk_id), record in self._records.items()
            if profile == corpus_profile and model == embedding_model
        }

    def upsert(self, records: list[VectorRecord]) -> UpsertResult:
        for record in records:
            key = (record.corpus_profile, record.embedding_model, record.chunk_id)
            self._records[key] = record
        return UpsertResult(written_count=len(records))

    def search(
        self, corpus_profile: str, embedding_model: str, query_vector: list[float], top_k: int
    ) -> list[SearchHit]:
        candidates = [
            (record, cosine_similarity(query_vector, record.embedding))
            for (profile, model, _chunk_id), record in self._records.items()
            if profile == corpus_profile and model == embedding_model
        ]
        candidates.sort(key=lambda pair: (-pair[1], pair[0].chunk_id))
        return [SearchHit(record=record, score=score) for record, score in candidates[:top_k]]

    def record_count(self, corpus_profile: str, embedding_model: str) -> int:
        return sum(
            1 for (profile, model, _chunk_id) in self._records if profile == corpus_profile and model == embedding_model
        )

    def all_chunk_ids(self, corpus_profile: str, embedding_model: str) -> set[str]:
        return {
            chunk_id
            for (profile, model, chunk_id) in self._records
            if profile == corpus_profile and model == embedding_model
        }

    def index_hash(self, corpus_profile: str, embedding_model: str) -> str:
        pairs = [
            (record.chunk_id, record.content_sha256)
            for (profile, model, _chunk_id), record in self._records.items()
            if profile == corpus_profile and model == embedding_model
        ]
        return compute_index_hash(pairs)
