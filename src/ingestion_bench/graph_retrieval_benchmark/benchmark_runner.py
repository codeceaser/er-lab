"""Stage 7B.1: the graph build + retrieval + comparison runner.

Ties the pieces together for ONE run:
  1. load Stage 7B.0 fixtures and VERIFY frozen-input identity (fail
     before any graph work if inputs differ);
  2. replay each document's authority setup through Stage 7R.1's own
     unmodified service (identical to Stage 7B.0);
  3. build the graph (extractor + chunk embeddings), persist it;
  4. evaluate graph-build accuracy against the Stage 7B.0 facts (a
     SEPARATE step, after construction);
  5. for every one of the frozen 12 questions, run the authority-aware
     graph retriever and score it with the FROZEN Stage 7B.0 scorer;
  6. compare against the frozen Stage 7B.0 Vector results (loaded, never
     rerun or rescored).

Graph construction (steps 1-3) never reads evaluation truth; only the
evaluator (steps 4-6) does.
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from ingestion_bench.cross_document_benchmark.benchmark_runner import FactEvidence, build_evidence_alignment
from ingestion_bench.graph_retrieval_benchmark import config
from ingestion_bench.graph_retrieval_benchmark.builder import GraphProjection, build_graph, load_fixtures_and_verify
from ingestion_bench.graph_retrieval_benchmark.builder import FrozenInputVerification
from ingestion_bench.graph_retrieval_benchmark.evaluator import (
    GraphBuildEvaluation,
    GraphQuestionMetrics,
    QuestionComparison,
    compare_vector_and_graph,
    evaluate_graph_build,
    evaluate_graph_question,
)
from ingestion_bench.graph_retrieval_benchmark.extractor import RelationshipExtractor
from ingestion_bench.graph_retrieval_benchmark.model import ExtractionRun
from ingestion_bench.graph_retrieval_benchmark.retriever import graph_search
from ingestion_bench.graph_retrieval_benchmark.store import GraphBuildManifest, GraphStore, build_manifest
from ingestion_bench.retrieval_baseline.embeddings import EmbeddingProvider
from ingestion_bench.revision_authority.contract_runner import _run_registry_setup
from ingestion_bench.revision_authority.repository import RevisionAuthorityRepository
from ingestion_bench.revision_authority.service import RevisionAuthorityService


def load_contract(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _requested_by_document(question: dict[str, Any], fixtures, symbol_to_id: dict[str, str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for symbol in question.get("requested_revision_symbols", []):
        out.setdefault(fixtures[symbol].logical_document_id, []).append(symbol_to_id[symbol])
    return out


class GraphBenchmarkRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str
    generated_at: str
    corpus_id: str
    embedding_model: str

    frozen_input_verification: FrozenInputVerification
    extraction_run: ExtractionRun
    build_manifest: GraphBuildManifest
    build_evaluation: GraphBuildEvaluation

    graph_question_metrics: list[GraphQuestionMetrics]
    comparisons: list[QuestionComparison]

    questions_total: int
    graph_authority_correct_count: int
    graph_all_authority_correct: bool
    improved_question_ids: list[str]
    unchanged_question_ids: list[str]
    regressed_question_ids: list[str]


def run_benchmark(
    contract_path: Path,
    repository: RevisionAuthorityRepository,
    extractor: RelationshipExtractor,
    embedding_provider: EmbeddingProvider,
    store: GraphStore,
) -> tuple[GraphBenchmarkRunResult, GraphProjection, dict[str, FactEvidence]]:
    contract = load_contract(contract_path)

    # 1. frozen-input identity
    fixtures, verification = load_fixtures_and_verify(contract)
    corpus_logical_document_ids = sorted({fx.logical_document_id for fx in fixtures.values()})

    # 2. authority setup (identical to Stage 7B.0)
    service = RevisionAuthorityService(repository)
    revision_by_symbol = {
        symbol: {"source_document_sha256": fx.source_document_sha256, "version_label": fx.version_label, "revision_number": fx.revision_number}
        for symbol, fx in fixtures.items()
    }
    symbol_to_id: dict[str, str] = {}
    id_to_symbol: dict[str, str] = {}
    registration_checks: list = []
    transition_checks: list = []
    for document in contract["authority_setup"]["documents"]:
        _run_registry_setup(repository, service, document, revision_by_symbol, symbol_to_id, id_to_symbol, registration_checks, transition_checks)

    # 3. build graph
    build_start = time.perf_counter()
    projection = build_graph(fixtures, extractor, embedding_provider)
    store.save(list(projection.nodes.values()), projection.edge_assertions, projection.extraction_run)
    manifest = build_manifest(list(projection.nodes.values()), projection.edge_assertions, projection.extraction_run, time.perf_counter() - build_start)

    # 4. evaluate build vs facts (separate, after construction)
    evidence = build_evidence_alignment(contract, fixtures)
    valid_chunk_ids = {c.chunk_id for fx in fixtures.values() for c in fx.chunks}
    build_evaluation = evaluate_graph_build(projection, contract, evidence, valid_chunk_ids)

    # 5. retrieve + score every frozen question
    graph_metrics: list[GraphQuestionMetrics] = []
    for question in contract["questions"]:
        query_vector = embedding_provider.embed([question["query"]]).vectors[0]
        requested = _requested_by_document(question, fixtures, symbol_to_id)
        graph_result = graph_search(
            service=service, store=store, projection=projection, corpus_logical_document_ids=corpus_logical_document_ids,
            query=question["query"], query_intent=question["query_intent"], as_of_date=date.fromisoformat(question["as_of_date"]),
            requested_revision_ids_by_document=requested, query_vector=query_vector, top_k=question["top_k"],
            max_hops=config.MAX_HOP_LIMIT,
        )
        graph_metrics.append(evaluate_graph_question(question, graph_result, evidence, id_to_symbol))

    # 6. compare against frozen Vector results (loaded, never rerun)
    vector_results = json.loads(config.STAGE7B0_VECTOR_RESULTS_PATH.read_text(encoding="utf-8"))
    comparisons = compare_vector_and_graph(vector_results, graph_metrics)

    authority_correct = sum(1 for g in graph_metrics if g.authority_correct)
    result = GraphBenchmarkRunResult(
        contract_version=contract["contract_version"], generated_at=datetime.now(timezone.utc).isoformat(),
        corpus_id=contract["corpus_id"], embedding_model=embedding_provider.model_identity,
        frozen_input_verification=verification, extraction_run=projection.extraction_run, build_manifest=manifest,
        build_evaluation=build_evaluation, graph_question_metrics=graph_metrics, comparisons=comparisons,
        questions_total=len(graph_metrics), graph_authority_correct_count=authority_correct,
        graph_all_authority_correct=(authority_correct == len(graph_metrics)),
        improved_question_ids=[c.question_id for c in comparisons if c.outcome_change == "improved"],
        unchanged_question_ids=[c.question_id for c in comparisons if c.outcome_change == "unchanged"],
        regressed_question_ids=[c.question_id for c in comparisons if c.outcome_change == "regressed"],
    )
    return result, projection, evidence
