"""Stage 7B.0: the cross-document vector store contract.

Reuses the FROZEN Stage 7R.2 provenance-rich record schema
(`RevisionVectorRecord`, `SearchHit`, `cosine_similarity`,
`compute_index_hash`) by read-only import -- this is exactly the "same
provenance schema" the fairness contract (item 6) requires, guaranteed by
literal identity rather than a hand-copied duplicate.

The crucial difference from Stage 7R.2's store: retrieval here spans the
WHOLE corpus (all six logical documents), never one logical document. The
authority-aware primitive filters candidates to a CROSS-DOCUMENT UNION of
eligible `document_revision_id`s -- computed per document by the Stage 7R
resolver, then unioned -- BEFORE ranking/limiting, never after. An empty
eligible set always yields zero hits, never "search everything". The
isolated table itself IS the corpus scope; records are keyed by
(chunk_id, embedding_model).
"""

from __future__ import annotations

import hashlib
from typing import Protocol

# Read-only reuse of the FROZEN Stage 7R.2 schema + helpers -- never modified.
from ingestion_bench.revision_search_benchmark.store import (  # noqa: F401
    RevisionVectorRecord,
    SearchHit,
    UpsertResult,
    compute_index_hash,
    cosine_similarity,
)


class CrossDocumentVectorStore(Protocol):
    def existing_content_hashes(self, embedding_model: str) -> dict[str, str]:
        """chunk_id -> content_sha256 for every record under
        embedding_model (the whole corpus) -- lets the indexer skip
        re-embedding unchanged chunks."""
        ...

    def upsert(self, records: list[RevisionVectorRecord]) -> UpsertResult: ...

    def search_eligible(
        self, *, embedding_model: str, query_vector: list[float], eligible_revision_ids: list[str], top_k: int
    ) -> list[SearchHit]:
        """THE authority-aware cross-document primitive: candidates across
        ALL logical documents are restricted to `eligible_revision_ids`
        (the cross-document union) BEFORE ranking/limiting, never after.
        Empty eligible set -> []. Ranked by similarity descending; ties
        broken by chunk_id ascending for determinism."""
        ...

    def search_unfiltered(self, *, embedding_model: str, query_vector: list[float], top_k: int) -> list[SearchHit]:
        """No revision restriction at all -- the unfiltered comparison
        baseline, never an authority-aware result."""
        ...

    def record_count(self, embedding_model: str) -> int: ...

    def all_chunk_ids(self, embedding_model: str) -> set[str]: ...

    def index_hash(self, embedding_model: str) -> str: ...


class InMemoryCrossDocumentVectorStore:
    """Pure-Python reference implementation -- no external database. Used
    by the default (fake-embedding) test suite; never used to produce this
    stage's real reported results."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], RevisionVectorRecord] = {}

    def _candidates(self, embedding_model: str) -> list[RevisionVectorRecord]:
        return [record for (model, _chunk_id), record in self._records.items() if model == embedding_model]

    def existing_content_hashes(self, embedding_model: str) -> dict[str, str]:
        return {r.chunk_id: r.content_sha256 for r in self._candidates(embedding_model)}

    def upsert(self, records: list[RevisionVectorRecord]) -> UpsertResult:
        for record in records:
            self._records[(record.embedding_model, record.chunk_id)] = record
        return UpsertResult(written_count=len(records))

    def search_eligible(
        self, *, embedding_model: str, query_vector: list[float], eligible_revision_ids: list[str], top_k: int
    ) -> list[SearchHit]:
        if not eligible_revision_ids:
            return []
        eligible = set(eligible_revision_ids)
        # Restriction happens HERE, before scoring/sorting/slicing --
        # never "score the whole corpus, then drop ineligible hits."
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
