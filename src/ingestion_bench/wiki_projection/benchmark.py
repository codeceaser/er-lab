"""Stage 7C.0: the W0 semantic CONTROL and the projection qualification run.

The W0 semantic control (Revision 6 SS2.3):

    query -> existing query embedding
          -> authority-aware search over the EXISTING chunk embeddings
          -> WikiSection / chunk mapping
          -> dedupe preserving order
          -> same final K as V
          -> the FROZEN Stage 7B.0 evaluator

`_evaluate_question` is imported BY IDENTITY from the frozen Stage 7B.0
`cross_document_benchmark.benchmark_runner`; it is never copied, wrapped or
re-implemented. V and W0 are scored by the same function object.

> W0 semantic retrieval is EXPECTED to equal V, because a W0 section is 1:1
> with a chunk and reuses that chunk's existing embedding. W0 ~ V is a
> SUCCESSFUL control outcome, not a failure, and no retrieval-improvement gate
> is applied to it.

This module does NOT implement D0. D0 is a Stage 7C.2 arm: it adds anchor-
derived seeding, deterministic hub expansion and traversal on top of chunk
semantic retrieval. Nothing here expands a hub or traverses a link.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from ingestion_bench.cross_document_benchmark.benchmark_runner import (
    FactEvidence,
    QuestionResult,
    _evaluate_question,  # FROZEN Stage 7B.0 evaluator, imported by identity
    build_evidence_alignment,
    load_contract,
)
from ingestion_bench.cross_document_benchmark.fixtures import RevisionFixture, load_all_revision_fixtures
from ingestion_bench.cross_document_benchmark.indexer import IndexBuildResult, build_index
from ingestion_bench.cross_document_benchmark.retriever import CrossDocumentSearchResult, cross_document_search
from ingestion_bench.cross_document_benchmark.store import CrossDocumentVectorStore
from ingestion_bench.retrieval_baseline.embeddings import EmbeddingProvider
from ingestion_bench.revision_authority.contract_runner import _run_registry_setup
from ingestion_bench.revision_authority.repository import RevisionAuthorityRepository
from ingestion_bench.revision_authority.service import RevisionAuthorityService
from ingestion_bench.wiki_projection.model import WikiProjection
from ingestion_bench.wiki_projection.projection import build_projection


class W0SectionMappingError(RuntimeError):
    """Raised when a retrieved chunk has no `WikiSection`, or a section does
    not map back to its own chunk -- the 1:1 view would be broken and the
    control would no longer be a control."""


def w0_result_from_vector_result(
    projection: WikiProjection, vector_result: CrossDocumentSearchResult, top_k: int
) -> tuple[CrossDocumentSearchResult, dict[str, Any]]:
    """Map a V search result through the W0 section view, exactly as SS2.3
    specifies: section -> originating chunk_id, dedupe preserving order,
    truncate to the same final K.

    The mapping goes THROUGH the projection (chunk -> section -> chunk) rather
    than passing chunk ids straight through, so a broken 1:1 view fails loudly
    instead of silently reproducing V.
    """
    section_by_chunk = {s.chunk_id: s for s in projection.sections}

    mapped: list = []
    seen: set[str] = set()
    section_ids: list[str] = []
    for hit in vector_result.hits:
        section = section_by_chunk.get(hit.chunk_id)
        if section is None:
            raise W0SectionMappingError(
                f"retrieved chunk {hit.chunk_id!r} has no WikiSection -- the 1:1 section view is incomplete"
            )
        if section.chunk_id != hit.chunk_id:
            raise W0SectionMappingError(
                f"section {section.section_id!r} maps back to chunk {section.chunk_id!r}, not {hit.chunk_id!r}"
            )
        if hit.chunk_id in seen:
            continue
        seen.add(hit.chunk_id)
        section_ids.append(section.section_id)
        mapped.append(hit)

    truncated = mapped[:top_k]
    reranked = [hit.model_copy(update={"rank": rank}) for rank, hit in enumerate(truncated, start=1)]

    w0_result = vector_result.model_copy(update={"hits": reranked})
    diagnostics = {
        "section_ids": section_ids[:top_k],
        "deduped_count": len(mapped) - len(seen) if len(mapped) != len(seen) else 0,
        "dropped_by_dedupe": len(vector_result.hits) - len(mapped),
        "truncated_count": max(0, len(mapped) - top_k),
    }
    return w0_result, diagnostics


class W0ControlQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    top_k: int
    v_hit_chunk_ids: list[str]
    w0_hit_chunk_ids: list[str]
    identical_to_v: bool
    v_outcome: str
    w0_outcome: str
    v_coverage_at_k: float
    w0_coverage_at_k: float
    v_complete_chain: bool
    w0_complete_chain: bool
    v_authority_leakage: int
    w0_authority_leakage: int
    w0_section_ids: list[str]
    dropped_by_dedupe: int
    truncated_count: int


class W0ControlResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    embedding_model: str
    evaluator_identity: str
    questions: list[W0ControlQuestion]
    questions_total: int
    identical_to_v_count: int
    w0_equals_v: bool
    v_outcome_counts: dict[str, int]
    w0_outcome_counts: dict[str, int]
    total_authority_leakage: int


class Stage7C0Result(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str
    generated_at: str
    corpus_id: str

    projection: WikiProjection
    index_build: IndexBuildResult
    w0_control: W0ControlResult

    revision_symbol_by_id: dict[str, str]
    build_latency_seconds: float


def _requested_by_document(
    question: dict[str, Any], fixtures: dict[str, RevisionFixture], symbol_to_id: dict[str, str]
) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for symbol in question.get("requested_revision_symbols", []):
        out.setdefault(fixtures[symbol].logical_document_id, []).append(symbol_to_id[symbol])
    return out


def run_stage7c0(
    contract_path: Path,
    repository: RevisionAuthorityRepository,
    embedding_provider: EmbeddingProvider,
    store: CrossDocumentVectorStore,
) -> Stage7C0Result:
    """Build the deterministic projection and run the W0 semantic control.

    Runs NO D0 seeding, NO hub expansion, NO traversal, NO W1 compilation and
    NO facet embedding -- those belong to Stage 7C.1 / 7C.2.
    """
    start = time.perf_counter()
    contract = load_contract(contract_path)
    fixtures = load_all_revision_fixtures(contract["fixtures"])
    corpus_logical_document_ids = sorted({fx.logical_document_id for fx in fixtures.values()})

    # --- the deterministic projection: no authority read, no LLM call ---
    projection = build_projection(fixtures)

    # --- authority setup, replayed through Stage 7R.1's own unmodified code ---
    service = RevisionAuthorityService(repository)
    revision_by_symbol = {
        symbol: {
            "source_document_sha256": fx.source_document_sha256,
            "version_label": fx.version_label,
            "revision_number": fx.revision_number,
        }
        for symbol, fx in fixtures.items()
    }
    symbol_to_id: dict[str, str] = {}
    id_to_symbol: dict[str, str] = {}
    registration_checks: list = []
    transition_checks: list = []
    for document in contract["authority_setup"]["documents"]:
        _run_registry_setup(
            repository, service, document, revision_by_symbol, symbol_to_id, id_to_symbol,
            registration_checks, transition_checks,
        )

    evidence: dict[str, FactEvidence] = build_evidence_alignment(contract, fixtures)
    index_result = build_index(fixtures, embedding_provider, store)

    control_questions: list[W0ControlQuestion] = []
    v_outcomes: dict[str, int] = {}
    w0_outcomes: dict[str, int] = {}
    total_leakage = 0

    for question in contract["questions"]:
        query_vector = embedding_provider.embed([question["query"]]).vectors[0]
        requested = _requested_by_document(question, fixtures, symbol_to_id)
        v_result = cross_document_search(
            service=service, store=store, corpus_logical_document_ids=corpus_logical_document_ids,
            query_intent=question["query_intent"], as_of_date=date.fromisoformat(question["as_of_date"]),
            requested_revision_ids_by_document=requested, query_vector=query_vector,
            embedding_model=embedding_provider.model_identity, top_k=question["top_k"],
        )
        w0_result, diagnostics = w0_result_from_vector_result(projection, v_result, question["top_k"])

        v_evaluated: QuestionResult = _evaluate_question(question, v_result, evidence, id_to_symbol)
        w0_evaluated: QuestionResult = _evaluate_question(question, w0_result, evidence, id_to_symbol)

        v_outcomes[v_evaluated.vector_outcome] = v_outcomes.get(v_evaluated.vector_outcome, 0) + 1
        w0_outcomes[w0_evaluated.vector_outcome] = w0_outcomes.get(w0_evaluated.vector_outcome, 0) + 1
        total_leakage += v_evaluated.authority_leakage_count + w0_evaluated.authority_leakage_count

        control_questions.append(
            W0ControlQuestion(
                question_id=question["question_id"], top_k=question["top_k"],
                v_hit_chunk_ids=v_evaluated.authority_aware_hit_chunk_ids,
                w0_hit_chunk_ids=w0_evaluated.authority_aware_hit_chunk_ids,
                identical_to_v=(
                    v_evaluated.authority_aware_hit_chunk_ids == w0_evaluated.authority_aware_hit_chunk_ids
                ),
                v_outcome=v_evaluated.vector_outcome, w0_outcome=w0_evaluated.vector_outcome,
                v_coverage_at_k=v_evaluated.required_fact_coverage_at_k,
                w0_coverage_at_k=w0_evaluated.required_fact_coverage_at_k,
                v_complete_chain=v_evaluated.complete_chain_represented,
                w0_complete_chain=w0_evaluated.complete_chain_represented,
                v_authority_leakage=v_evaluated.authority_leakage_count,
                w0_authority_leakage=w0_evaluated.authority_leakage_count,
                w0_section_ids=diagnostics["section_ids"],
                dropped_by_dedupe=diagnostics["dropped_by_dedupe"],
                truncated_count=diagnostics["truncated_count"],
            )
        )

    control = W0ControlResult(
        embedding_model=embedding_provider.model_identity,
        evaluator_identity=f"{_evaluate_question.__module__}.{_evaluate_question.__qualname__}",
        questions=control_questions,
        questions_total=len(control_questions),
        identical_to_v_count=sum(1 for q in control_questions if q.identical_to_v),
        w0_equals_v=all(q.identical_to_v for q in control_questions),
        v_outcome_counts=dict(sorted(v_outcomes.items())),
        w0_outcome_counts=dict(sorted(w0_outcomes.items())),
        total_authority_leakage=total_leakage,
    )

    return Stage7C0Result(
        contract_version=projection.contract_version,
        generated_at=datetime.now(timezone.utc).isoformat(),
        corpus_id=contract["corpus_id"],
        projection=projection,
        index_build=index_result,
        w0_control=control,
        revision_symbol_by_id=id_to_symbol,
        build_latency_seconds=time.perf_counter() - start,
    )
