"""Stage 6B: deterministic fact-to-chunk resolver.

Maps a benchmark question's `required_fact_ids` (or any fact id) to the
`matched_chunk_ids` available in a SUPPLIED Stage 6A `EvidenceAlignment`
catalog for ONE ingestion lane (one fixture/format) -- never a
hardcoded, lane-specific gold answer. The catalog itself (produced by
`ingestion_bench.evaluation`, read-only here) is the only source of
truth; this module adds no new judgment about what a fact IS, only about
what STATE it is in for the supplied lane.

No embeddings, no pgvector, no retrieval execution, no LLM, no network
call exists anywhere in this module. None of the four resolution states
below describes retrieval quality -- no retrieval layer exists yet
(Stage 7A+); they describe ingestion-side availability only.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ingestion_bench.evaluation.model import EvidenceAlignment

FactResolutionStatus = Literal[
    "available_with_chunks",
    "ingested_without_chunks",
    "missing_from_ingestion",
    "not_applicable",
]


class FactResolution(BaseModel):
    """One fact id's resolution state for ONE ingestion lane (one
    EvidenceAlignment catalog, already scoped to a single fixture)."""

    model_config = ConfigDict(extra="forbid")

    fact_id: str
    status: FactResolutionStatus
    matched_chunk_ids: list[str] = Field(default_factory=list)


def _index_catalog_by_fact_id(catalog: list[EvidenceAlignment]) -> dict[str, EvidenceAlignment]:
    """Builds a fact_id -> EvidenceAlignment lookup. Raises ValueError on
    a duplicate fact_id, which only happens if the caller mixed entries
    from more than one fixture together (fact_ids like "P_001" repeat
    identically, by design, across PARITY_001's three formats) -- the
    resolver requires an already-single-lane catalog, and this is the
    guardrail that enforces it."""
    index: dict[str, EvidenceAlignment] = {}
    for alignment in catalog:
        if alignment.fact_id in index:
            raise ValueError(
                f"duplicate fact_id {alignment.fact_id!r} in the supplied catalog -- "
                f"resolve_question_facts requires a catalog already scoped to ONE fixture "
                f"(found entries for both {index[alignment.fact_id].fixture!r} and {alignment.fixture!r})"
            )
        index[alignment.fact_id] = alignment
    return index


def resolve_fact(fact_id: str, catalog_index: dict[str, EvidenceAlignment]) -> FactResolution:
    """Deterministic, pure function of (fact_id, catalog_index) -- no
    randomness, no wall-clock dependency. Raises KeyError if `fact_id` is
    not present in the catalog at all: this fact was never declared for
    this ingestion lane at all (a benchmark-authoring or wrong-catalog
    error), which is never silently mapped to one of the four real
    resolution states below -- those four describe a fact the catalog
    DOES know about, distinguished only by its ingestion outcome:

      "available_with_chunks"   -- matched or partial, AND at least one
        matched_chunk_id -- the fact reached CanonicalDocument and is
        reachable through at least one CanonicalChunk.
      "ingested_without_chunks" -- matched or partial, but zero
        matched_chunk_ids -- the fact reached CanonicalDocument but no
        chunk currently carries it (a chunk_projection_loss, per Stage
        6A.1 item 9).
      "missing_from_ingestion"  -- the manifest expected this fact and
        Stage 5A never produced it at all (EvidenceAlignment.match_status
        == "missing").
      "not_applicable"          -- this fact is structurally not
        applicable to this ingestion lane (e.g. a visual fact under path
        A, which has no VisionEnricher at all).
    """
    if fact_id not in catalog_index:
        raise KeyError(
            f"fact_id {fact_id!r} is not present in the supplied EvidenceAlignment catalog -- "
            "this fact was never declared for this ingestion lane (wrong fact_id, or the catalog "
            "was not scoped to the fixture this question expects)"
        )
    alignment = catalog_index[fact_id]
    if alignment.match_status == "not_applicable":
        return FactResolution(fact_id=fact_id, status="not_applicable", matched_chunk_ids=[])
    if alignment.match_status == "missing":
        return FactResolution(fact_id=fact_id, status="missing_from_ingestion", matched_chunk_ids=[])
    # "matched" or "partial"
    if alignment.matched_chunk_ids:
        return FactResolution(
            fact_id=fact_id, status="available_with_chunks", matched_chunk_ids=sorted(alignment.matched_chunk_ids)
        )
    return FactResolution(fact_id=fact_id, status="ingested_without_chunks", matched_chunk_ids=[])


def resolve_question_facts(fact_ids: list[str], catalog: list[EvidenceAlignment]) -> dict[str, FactResolution]:
    """Resolves every id in `fact_ids` against `catalog`. `catalog` must
    already be scoped to ONE ingestion lane (one fixture) -- callers
    filter the full evidence-alignment catalog to one fixture before
    calling this (e.g. `[a for a in catalog if a.fixture == fixture]`).

    Deterministic: identical inputs always produce an identical output
    dict, keyed in the SAME ORDER as `fact_ids` (Python dict insertion
    order is preserved regardless of hash values), with
    `matched_chunk_ids` always sorted. No step here depends on raw `set`
    iteration order, wall-clock time, or any external state."""
    catalog_index = _index_catalog_by_fact_id(catalog)
    return {fact_id: resolve_fact(fact_id, catalog_index) for fact_id in fact_ids}
