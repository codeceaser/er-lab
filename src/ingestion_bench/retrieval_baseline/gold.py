"""Stage 7A.1: corpus-level gold-evidence resolution.

Stage 6B's own resolver (ingestion_bench.retrieval_benchmark.resolver)
is scoped to ONE fixture, and requires a catalog already filtered to
that fixture -- fact ids like "P_001" are NOT globally unique across the
PARITY_001 PDF/DOCX/PPTX variants, so a corpus that spans multiple
fixtures needs a SCOPED identity: fixture + fact_id + chunk_id.

This module adds that corpus-level resolution ALONGSIDE Stage 6B's
resolver -- it never modifies contracts/retrieval_benchmark_v1.json or
src/ingestion_bench/retrieval_benchmark/resolver.py, and it reuses that
module's own FactResolutionStatus vocabulary unchanged, so "available/
missing/not_applicable/ingested-without-chunks" mean exactly the same
thing at both scopes.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ingestion_bench.evaluation.model import EvidenceAlignment
from ingestion_bench.retrieval_benchmark.resolver import FactResolutionStatus


class ScopedFactEvidence(BaseModel):
    """One (fixture, fact_id) pair's resolution state, scoped additionally
    by which of its matched_chunk_ids are actually present in a GIVEN
    corpus profile's built vector index -- the "fixture + fact_id +
    chunk_id" scoped identity the corpus-level resolver requires, since
    fact_id alone is not globally unique across the parity format
    variants."""

    model_config = ConfigDict(extra="forbid")

    fixture: str
    fact_id: str
    status: FactResolutionStatus
    # Only populated when status == "available_with_chunks" -- the
    # matched_chunk_ids that are BOTH real (per Stage 6A) AND actually
    # present in this corpus profile's built index.
    chunk_ids: list[str] = Field(default_factory=list)


def _resolve_corpus_fact(
    fixture: str, fact_id: str, alignment: EvidenceAlignment, indexed_chunk_ids: set[str]
) -> ScopedFactEvidence:
    if alignment.match_status == "not_applicable":
        return ScopedFactEvidence(fixture=fixture, fact_id=fact_id, status="not_applicable")
    if alignment.match_status == "missing":
        return ScopedFactEvidence(fixture=fixture, fact_id=fact_id, status="missing_from_ingestion")
    # "matched" or "partial" per Stage 6A -- but only chunk ids actually
    # present in THIS corpus's index count as retrievable here. A chunk id
    # Stage 6A/5A produced but that belongs to a fixture excluded from
    # this corpus profile (or a genuine chunk_projection_loss) both
    # collapse into the same outcome from a retrieval standpoint: nothing
    # in this corpus can satisfy the fact.
    present = sorted(cid for cid in alignment.matched_chunk_ids if cid in indexed_chunk_ids)
    if present:
        return ScopedFactEvidence(fixture=fixture, fact_id=fact_id, status="available_with_chunks", chunk_ids=present)
    return ScopedFactEvidence(fixture=fixture, fact_id=fact_id, status="ingested_without_chunks")


def resolve_corpus_gold_evidence(
    fact_ids: list[str],
    fixtures: list[str],
    catalog: list[EvidenceAlignment],
    indexed_chunk_ids: set[str],
) -> dict[str, list[ScopedFactEvidence]]:
    """Resolves every id in `fact_ids` against every fixture in
    `fixtures` that the Stage 6A catalog actually declares it for. A
    fact_id not declared for a given fixture at all (e.g. a parity fact
    checked against a stress-only fixture) is simply absent from that
    fixture's contribution -- a corpus legitimately mixes suites, so this
    is normal, never an error (unlike Stage 6B's single-fixture resolver,
    which raises on an unknown fact_id because there absence is always a
    caller/benchmark-authoring mistake).

    Deterministic: iterates `fact_ids` and `fixtures` in the exact order
    given; the returned dict preserves `fact_ids` order (Python dict
    insertion order), and each fact_id's own list preserves `fixtures`
    order."""
    catalog_index: dict[tuple[str, str], EvidenceAlignment] = {(a.fixture, a.fact_id): a for a in catalog}
    result: dict[str, list[ScopedFactEvidence]] = {}
    for fact_id in fact_ids:
        entries: list[ScopedFactEvidence] = []
        for fixture in fixtures:
            alignment = catalog_index.get((fixture, fact_id))
            if alignment is not None:
                entries.append(_resolve_corpus_fact(fixture, fact_id, alignment, indexed_chunk_ids))
        result[fact_id] = entries
    return result


def gold_chunk_ids(entries: list[ScopedFactEvidence]) -> set[str]:
    """The union of every chunk_id from entries with status
    "available_with_chunks" -- the actual "relevant" set for
    recall/coverage purposes. Facts that are missing_from_ingestion,
    not_applicable, or ingested_without_chunks contribute NOTHING here
    (by design -- they are excluded from retrieval scoring entirely,
    never silently counted as a retrieval miss)."""
    return {cid for entry in entries if entry.status == "available_with_chunks" for cid in entry.chunk_ids}
