"""Stage 7B.0: the declarative cross-document benchmark runner.

Reads contracts/cross_document_relationship_benchmark_v1.json and:
  1. loads every source fixture (frozen adapter + chunker), verifying
     tracked bytes against generation_manifest.json;
  2. replays each document's authority setup through Stage 7R.1's own
     unmodified contract_runner._run_registry_setup + service;
  3. builds the ONE isolated cross-document index;
  4. computes an EVIDENCE ALIGNMENT (fact_id -> the chunk that supports
     it), derived purely from the fixtures -- never from retrieval;
  5. for every question, runs the cross-document authority-aware
     retriever AND its unfiltered comparison, then EVALUATES the result
     against the contract's held-out truth (required/forbidden facts,
     expected chain) to produce coverage@K, all-required@K, MRR, nDCG,
     authority-leakage, evidence diversity, and a vector outcome
     classification.

The clean separation the fairness contract demands: the RETRIEVER (step
5a) is handed only query text/vector, intent, as_of, requested revisions,
and top-K. The EVALUATOR (step 5b, the `_evaluate_question` function
here) is the only place that ever reads required_fact_ids,
forbidden_fact_ids, or expected_relationship_chain.
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from ingestion_bench.cross_document_benchmark.fixtures import RevisionFixture, load_all_revision_fixtures
from ingestion_bench.cross_document_benchmark.indexer import IndexBuildResult, build_index
from ingestion_bench.cross_document_benchmark.retriever import CrossDocumentSearchResult, cross_document_search
from ingestion_bench.cross_document_benchmark.store import CrossDocumentVectorStore
from ingestion_bench.retrieval_baseline.embeddings import EmbeddingProvider
from ingestion_bench.revision_authority.contract_runner import _run_registry_setup
from ingestion_bench.revision_authority.repository import RevisionAuthorityRepository
from ingestion_bench.revision_authority.service import RevisionAuthorityService


def load_contract(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# --- evidence alignment (fact -> supporting chunk), from fixtures only ------


class EvidenceAlignmentError(RuntimeError):
    """Raised when a contract fact's expected_supporting_passage cannot be
    located in exactly one chunk of its supporting revision -- the
    contract and the fixtures have drifted and must be reconciled."""


class FactEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_id: str
    subject: str
    predicate: str
    object: str
    temporal_classification: str
    distractor_status: str
    supporting_logical_document_id: str
    supporting_revision_symbol: str
    supporting_document_revision_id: str
    supporting_chunk_id: str
    supporting_content_sha256: str
    expected_supporting_passage: str


def build_evidence_alignment(
    contract: dict[str, Any], fixtures: dict[str, RevisionFixture]
) -> dict[str, FactEvidence]:
    alignment: dict[str, FactEvidence] = {}
    for fact in contract["facts"]:
        symbol = fact["supporting_revision_symbol"]
        fixture = fixtures[symbol]
        passage = fact["expected_supporting_passage"]
        matches = [c for c in fixture.chunks if passage in c.retrieval_text]
        if len(matches) != 1:
            raise EvidenceAlignmentError(
                f"fact {fact['fact_id']!r}: expected_supporting_passage {passage!r} matched {len(matches)} chunk(s) "
                f"in revision {symbol!r} (expected exactly 1)"
            )
        chunk = matches[0]
        alignment[fact["fact_id"]] = FactEvidence(
            fact_id=fact["fact_id"], subject=fact["subject"], predicate=fact["predicate"], object=fact["object"],
            temporal_classification=fact["temporal_classification"], distractor_status=fact["distractor_status"],
            supporting_logical_document_id=fact["supporting_logical_document_id"],
            supporting_revision_symbol=symbol, supporting_document_revision_id=fixture.document_revision_id,
            supporting_chunk_id=chunk.chunk_id, supporting_content_sha256=chunk.content_sha256,
            expected_supporting_passage=passage,
        )
    return alignment


# --- per-question evaluation -------------------------------------------------


class QuestionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    question_type: str
    query: str
    query_intent: str
    as_of_date: date
    top_k: int

    eligible_revision_symbols: list[str]
    required_fact_ids: list[str]
    forbidden_fact_ids: list[str]

    authority_aware_hit_chunk_ids: list[str]
    authority_aware_hit_documents: list[str]
    unfiltered_hit_chunk_ids: list[str]
    unfiltered_hit_documents: list[str]

    required_fact_coverage_at_k: float
    all_required_facts_retrieved_at_k: bool
    complete_chain_represented: bool
    mrr: float
    ndcg_at_k: float

    authority_leakage_count: int
    forbidden_fact_hit_ids: list[str]
    unfiltered_ineligible_hit_count: int
    evidence_document_diversity: int

    vector_outcome: str  # "solved" | "partial" | "failed"
    authority_correct: bool
    failure_reasons: list[str]

    resolver_latency_seconds: float
    authority_aware_vector_search_latency_seconds: float
    unfiltered_vector_search_latency_seconds: float
    total_latency_seconds: float

    # Complete held-nothing-back retrieval evidence -- the full
    # cross-document search result (per-document resolutions, union,
    # ranked authority-aware AND unfiltered hits with full provenance).
    result: CrossDocumentSearchResult


def _dcg(relevances: list[float]) -> float:
    return sum(rel / math.log2(rank + 1) for rank, rel in enumerate(relevances, start=1))


def _evaluate_question(
    question: dict[str, Any],
    result: CrossDocumentSearchResult,
    evidence: dict[str, FactEvidence],
    id_to_symbol: dict[str, str],
) -> QuestionResult:
    top_k = question["top_k"]
    required_fact_ids = question["required_fact_ids"]
    forbidden_fact_ids = question["forbidden_fact_ids"]
    expected_chain = question["expected_relationship_chain"]

    required_chunk_ids = {evidence[f].supporting_chunk_id for f in required_fact_ids}
    forbidden_chunk_ids = {evidence[f].supporting_chunk_id: f for f in forbidden_fact_ids}
    chain_chunk_ids = {evidence[f].supporting_chunk_id for f in expected_chain}

    aware_chunk_ids = [h.chunk_id for h in result.hits]
    aware_documents = [h.logical_document_id for h in result.hits]
    unfiltered_chunk_ids = [h.chunk_id for h in result.unfiltered_hits]
    unfiltered_documents = [h.logical_document_id for h in result.unfiltered_hits]

    retrieved_required = required_chunk_ids & set(aware_chunk_ids)
    coverage = len(retrieved_required) / len(required_chunk_ids) if required_chunk_ids else 1.0
    all_required = retrieved_required == required_chunk_ids
    complete_chain = chain_chunk_ids <= set(aware_chunk_ids)

    # MRR: reciprocal rank of the first required-fact chunk.
    mrr = 0.0
    for rank, chunk_id in enumerate(aware_chunk_ids, start=1):
        if chunk_id in required_chunk_ids:
            mrr = 1.0 / rank
            break

    relevances = [1.0 if chunk_id in required_chunk_ids else 0.0 for chunk_id in aware_chunk_ids]
    ideal = _dcg([1.0] * min(len(required_chunk_ids), top_k))
    ndcg = (_dcg(relevances[:top_k]) / ideal) if ideal > 0 else 0.0

    eligible_union = set(result.eligible_revision_ids_union)
    authority_leakage = sum(1 for h in result.hits if h.document_revision_id not in eligible_union)
    forbidden_hits = sorted({forbidden_chunk_ids[c] for c in aware_chunk_ids if c in forbidden_chunk_ids})
    unfiltered_ineligible = sum(1 for h in result.unfiltered_hits if h.document_revision_id not in eligible_union)
    diversity = len(set(aware_documents))

    if not aware_chunk_ids:
        outcome = "failed"
    elif all_required:
        outcome = "solved"
    elif retrieved_required:
        outcome = "partial"
    else:
        outcome = "failed"

    failure_reasons: list[str] = []
    if authority_leakage != 0:
        failure_reasons.append(f"authority leakage: {authority_leakage} authority-aware hit(s) belong to an ineligible revision")
    # A forbidden fact whose supporting revision is authority-INELIGIBLE
    # (historical/draft under a current query) must NEVER appear in
    # authority-aware hits -- that is an authority failure. A forbidden
    # fact that is authority-eligible (an adjacent-domain lexical
    # distractor) appearing is NOT an authority failure, only a
    # vector-precision observation.
    for f in forbidden_hits:
        ev = evidence[f]
        if ev.supporting_document_revision_id not in eligible_union:
            failure_reasons.append(f"forbidden ineligible fact {f!r} ({ev.temporal_classification}) leaked into authority-aware hits")
    authority_correct = not failure_reasons

    return QuestionResult(
        question_id=question["question_id"], question_type=question["question_type"], query=question["query"],
        query_intent=question["query_intent"], as_of_date=date.fromisoformat(question["as_of_date"]), top_k=top_k,
        eligible_revision_symbols=sorted(id_to_symbol.get(r, r) for r in result.eligible_revision_ids_union),
        required_fact_ids=required_fact_ids, forbidden_fact_ids=forbidden_fact_ids,
        authority_aware_hit_chunk_ids=aware_chunk_ids, authority_aware_hit_documents=aware_documents,
        unfiltered_hit_chunk_ids=unfiltered_chunk_ids, unfiltered_hit_documents=unfiltered_documents,
        required_fact_coverage_at_k=coverage, all_required_facts_retrieved_at_k=all_required,
        complete_chain_represented=complete_chain, mrr=mrr, ndcg_at_k=ndcg,
        authority_leakage_count=authority_leakage, forbidden_fact_hit_ids=forbidden_hits,
        unfiltered_ineligible_hit_count=unfiltered_ineligible, evidence_document_diversity=diversity,
        vector_outcome=outcome, authority_correct=authority_correct, failure_reasons=failure_reasons,
        resolver_latency_seconds=result.resolver_latency_seconds,
        authority_aware_vector_search_latency_seconds=result.authority_aware_vector_search_latency_seconds,
        unfiltered_vector_search_latency_seconds=result.unfiltered_vector_search_latency_seconds,
        total_latency_seconds=(
            result.resolver_latency_seconds
            + result.authority_aware_vector_search_latency_seconds
            + result.unfiltered_vector_search_latency_seconds
        ),
        result=result,
    )


# --- fixture / fact / question inventories ----------------------------------


class FixtureInventoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    logical_document_id: str
    source_relative_path: str
    source_document_sha256: str
    document_revision_id: str
    revision_number: int
    chunk_count: int
    chunk_ids: list[str]


class BenchmarkRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str
    generated_at: str
    corpus_id: str
    embedding_model: str

    fixture_inventory: list[FixtureInventoryEntry]
    fact_evidence: list[FactEvidence]
    question_type_counts: dict[str, int]
    index_build: IndexBuildResult

    question_results: list[QuestionResult]

    authority_correct_count: int
    questions_total: int
    vector_solved_count: int
    vector_partial_count: int
    vector_failed_count: int

    all_authority_correct: bool


def _requested_by_document(
    question: dict[str, Any], fixtures: dict[str, RevisionFixture], symbol_to_id: dict[str, str]
) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for symbol in question.get("requested_revision_symbols", []):
        logical_document_id = fixtures[symbol].logical_document_id
        out.setdefault(logical_document_id, []).append(symbol_to_id[symbol])
    return out


def run_benchmark(
    contract_path: Path,
    repository: RevisionAuthorityRepository,
    embedding_provider: EmbeddingProvider,
    store: CrossDocumentVectorStore,
) -> tuple[BenchmarkRunResult, dict[str, str], dict[str, FactEvidence]]:
    contract = load_contract(contract_path)
    fixtures = load_all_revision_fixtures(contract["fixtures"])
    corpus_logical_document_ids = sorted({fx.logical_document_id for fx in fixtures.values()})

    # --- authority setup: one _run_registry_setup call per document ---
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

    evidence = build_evidence_alignment(contract, fixtures)
    index_result = build_index(fixtures, embedding_provider, store)

    question_results: list[QuestionResult] = []
    for question in contract["questions"]:
        query_vector = embedding_provider.embed([question["query"]]).vectors[0]
        requested = _requested_by_document(question, fixtures, symbol_to_id)
        search_result = cross_document_search(
            service=service, store=store, corpus_logical_document_ids=corpus_logical_document_ids,
            query_intent=question["query_intent"], as_of_date=date.fromisoformat(question["as_of_date"]),
            requested_revision_ids_by_document=requested,
            query_vector=query_vector, embedding_model=embedding_provider.model_identity, top_k=question["top_k"],
        )
        question_results.append(_evaluate_question(question, search_result, evidence, id_to_symbol))

    question_type_counts: dict[str, int] = {}
    for q in contract["questions"]:
        question_type_counts[q["question_type"]] = question_type_counts.get(q["question_type"], 0) + 1

    fixture_inventory = [
        FixtureInventoryEntry(
            symbol=symbol, logical_document_id=fx.logical_document_id, source_relative_path=fx.source_relative_path,
            source_document_sha256=fx.source_document_sha256, document_revision_id=fx.document_revision_id,
            revision_number=fx.revision_number, chunk_count=len(fx.chunks), chunk_ids=[c.chunk_id for c in fx.chunks],
        )
        for symbol, fx in sorted(fixtures.items())
    ]

    authority_correct_count = sum(1 for q in question_results if q.authority_correct)
    result = BenchmarkRunResult(
        contract_version=contract["contract_version"],
        generated_at=datetime.now(timezone.utc).isoformat(),
        corpus_id=contract["corpus_id"],
        embedding_model=embedding_provider.model_identity,
        fixture_inventory=fixture_inventory,
        fact_evidence=[evidence[f["fact_id"]] for f in contract["facts"]],
        question_type_counts=question_type_counts,
        index_build=index_result,
        question_results=question_results,
        authority_correct_count=authority_correct_count,
        questions_total=len(question_results),
        vector_solved_count=sum(1 for q in question_results if q.vector_outcome == "solved"),
        vector_partial_count=sum(1 for q in question_results if q.vector_outcome == "partial"),
        vector_failed_count=sum(1 for q in question_results if q.vector_outcome == "failed"),
        all_authority_correct=(authority_correct_count == len(question_results)),
    )
    return result, id_to_symbol, evidence
