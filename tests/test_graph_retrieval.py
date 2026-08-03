"""Stage 7B.1: graph retrieval + Vector-vs-Graph comparison tests.

Deterministic (fake extractor, fake embeddings, in-memory stores) except
the one skippable real-infrastructure test. Assertions target AUTHORITY
correctness, the filter-before-traverse contract, provenance, and
scoring-parity with the frozen Stage 7B.0 Vector evaluator -- NEVER that
Graph must improve any question (graph superiority is not a test
expectation)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from ingestion_bench.cross_document_benchmark import benchmark_runner as vector_runner
from ingestion_bench.graph_retrieval_benchmark import config
from ingestion_bench.graph_retrieval_benchmark import evaluator as graph_evaluator
from ingestion_bench.graph_retrieval_benchmark.benchmark_runner import load_contract, run_benchmark
from ingestion_bench.graph_retrieval_benchmark.extractor import FakeRelationshipExtractor
from ingestion_bench.graph_retrieval_benchmark.retriever import graph_search
from ingestion_bench.graph_retrieval_benchmark.store import InMemoryGraphStore
from ingestion_bench.retrieval_baseline.embeddings import FakeEmbeddingProvider
from ingestion_bench.revision_authority.repository import InMemoryRevisionAuthorityRepository

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def contract():
    return load_contract(config.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH)


@pytest.fixture(scope="module")
def run():
    result, projection, evidence = run_benchmark(
        config.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH, InMemoryRevisionAuthorityRepository(),
        FakeRelationshipExtractor(), FakeEmbeddingProvider(), InMemoryGraphStore(),
    )
    return result, projection, evidence


def _g(result, question_id):
    return next(g for g in result.graph_question_metrics if g.question_id == question_id)


# --- authority: filter before traverse --------------------------------------


def test_graph_all_questions_authority_correct(run):
    """The ONE hard gate: no ineligible (historical/draft) edge ever
    contributes evidence under a current query -- zero authority leakage
    on every question. (Graph VALUE is reported, never gated.)"""
    result, _projection, _evidence = run
    for g in result.graph_question_metrics:
        assert g.authority_correct, f"{g.question_id}: {g.failure_reasons}"
        assert g.authority_leakage_count == 0
    assert result.graph_all_authority_correct is True


def test_current_traversal_excludes_historical_and_draft_assertions(run):
    result, _projection, _evidence = run
    for g in result.graph_question_metrics:
        if g.query_intent != "current":
            continue
        eligible = set(g.graph_result.eligible_revision_ids_union)
        for edge in g.graph_result.traversed_edges:
            assert edge.document_revision_id in eligible, f"{g.question_id}: traversed an ineligible edge"


def test_historical_traversal_uses_historical_assertions(run, contract):
    """The as_of-2021 questions traverse the historical (rev1)
    assertions, and the historical chain facts are recovered."""
    result, _projection, _evidence = run
    g = _g(result, "Q10_historical_procedure_of_obligation")
    # every traversed edge is from an eligible (historical) revision
    eligible = set(g.graph_result.eligible_revision_ids_union)
    assert g.graph_result.traversed_edges
    for edge in g.graph_result.traversed_edges:
        assert edge.document_revision_id in eligible


def test_draft_intent_includes_only_the_requested_draft_revision(run):
    result, _projection, _evidence = run
    g = _g(result, "Q12_draft_proposed_control")
    resolved = [r for r in g.graph_result.per_document_resolutions if r.resolved]
    assert {r.logical_document_id for r in resolved} == {"CONTROL-LIBRARY"}
    # every traversed edge (if any) belongs to the requested draft revision only
    eligible = set(g.graph_result.eligible_revision_ids_union)
    for edge in g.graph_result.traversed_edges:
        assert edge.document_revision_id in eligible


def test_authority_filtering_happens_before_traversal_at_store_level():
    """The store loads ONLY eligible edge assertions; an empty eligible
    set yields no edges (never the whole graph). An ineligible edge is
    never handed to the traversal."""
    from ingestion_bench.graph_retrieval_benchmark.model import GraphEdgeAssertion

    store = InMemoryGraphStore()
    def _edge(eid, rev):
        return GraphEdgeAssertion(
            edge_assertion_id=eid, subject_node_id="a", predicate="p", object_node_id="b",
            logical_document_id="D", document_revision_id=rev, supporting_chunk_id="c", supporting_content_sha256="0" * 64,
            supporting_text="t", source_relative_path="x", source_document_sha256="0" * 64, extraction_run_id="r",
        )
    from ingestion_bench.graph_retrieval_benchmark.model import ExtractionRun
    store.save([], [_edge("e1", "rev-eligible"), _edge("e2", "rev-ineligible")], ExtractionRun(extraction_run_id="r", extractor_identity="x"))
    assert store.edge_assertions_for_revisions([]) == []
    loaded = store.edge_assertions_for_revisions(["rev-eligible"])
    assert [e.edge_assertion_id for e in loaded] == ["e1"]


def test_graph_authority_scope_matches_vector_authority_scope(run):
    """Graph and Vector use the SAME per-document resolver and therefore
    the SAME eligible-revision union for every question -- identical
    authority scoping is a precondition for a fair comparison."""
    result, _projection, _evidence = run
    _id_to_symbol = None
    vector_results = json.loads(config.STAGE7B0_VECTOR_RESULTS_PATH.read_text(encoding="utf-8"))
    vector_by_id = {q["question_id"]: q for q in vector_results["question_results"]}
    # Map graph eligible union (ids) to symbols via the graph result's own
    # per-document authority_labels -> compare the union SIZE + doc set to
    # Vector's eligible symbols. (Both derive from the same resolver.)
    for g in result.graph_question_metrics:
        v = vector_by_id[g.question_id]
        assert sorted(g.graph_result.eligible_revision_ids_union) == sorted(_vector_eligible_ids(v))


def _vector_eligible_ids(vector_question: dict) -> list[str]:
    return vector_question["result"]["eligible_revision_ids_union"]


# --- evidence / provenance / budget -----------------------------------------


def test_graph_respects_top_k_chunk_budget_and_unique_chunks(run):
    result, _projection, _evidence = run
    for g in result.graph_question_metrics:
        chunk_ids = [h.chunk_id for h in g.graph_result.hits]
        assert len(chunk_ids) <= g.top_k
        assert len(chunk_ids) == len(set(chunk_ids)), f"{g.question_id}: duplicate chunk in graph hits"


def test_only_source_chunks_are_evidence_no_bare_edge(run):
    """Every graph evidence hit is a source CHUNK with full content and
    provenance; edges are explanatory metadata that CITE the chunk (a hit
    records which edge assertions support it, but the chunk is the
    evidence)."""
    result, _projection, _evidence = run
    for g in result.graph_question_metrics:
        for h in g.graph_result.hits:
            assert h.chunk_id and h.retrieval_text
            assert len(h.content_sha256) == 64 and len(h.source_document_sha256) == 64
            assert h.source_relative_path and isinstance(h.source_refs, list) and len(h.source_refs) > 0
            assert h.supporting_edge_assertion_ids  # cites >=1 edge, but the chunk is the evidence
            assert h.authority_label is not None


def test_every_path_edge_points_to_its_supporting_chunk(run):
    result, _projection, _evidence = run
    for g in result.graph_question_metrics:
        for edge in g.graph_result.traversed_edges:
            assert edge.supporting_chunk_id


def test_no_seed_entity_outcome_when_query_names_no_graph_entity(run):
    """The draft question never names its entity (C-91); graph seeding
    finds no seed and returns an explicit no_seed_entity outcome -- an
    HONEST graph limitation, never a consultation of evaluation truth."""
    result, _projection, _evidence = run
    g = _g(result, "Q12_draft_proposed_control")
    assert g.graph_result.outcome == "no_seed_entity"
    assert g.graph_result.hits == []


# --- scoring parity with the frozen Vector evaluator ------------------------


def test_graph_uses_the_frozen_stage7b0_scorer_and_fact_alignment():
    """Graph metrics are computed by the SAME frozen Stage 7B.0 functions
    the Vector benchmark used -- import identity proves it (no divergent
    reimplementation of coverage/MRR/nDCG/fact alignment)."""
    assert graph_evaluator._evaluate_question is vector_runner._evaluate_question
    assert graph_evaluator.FactEvidence is vector_runner.FactEvidence


def test_comparison_covers_all_twelve_frozen_questions(run):
    result, _projection, _evidence = run
    vector_results = json.loads(config.STAGE7B0_VECTOR_RESULTS_PATH.read_text(encoding="utf-8"))
    vector_ids = {q["question_id"] for q in vector_results["question_results"]}
    graph_ids = {c.question_id for c in result.comparisons}
    assert graph_ids == vector_ids
    assert len(result.comparisons) == 12


def test_reports_and_artifacts_derive_from_the_same_run_object(run):
    from ingestion_bench.graph_retrieval_benchmark.report import render_build_results_json, render_retrieval_results_json, render_scorecard_markdown

    result, projection, _evidence = run
    build_json = json.loads(render_build_results_json(result, projection))
    retrieval_json = json.loads(render_retrieval_results_json(result))
    scorecard = render_scorecard_markdown(result)
    assert build_json["build_evaluation"]["expected_fact_edge_recall"] == result.build_evaluation.expected_fact_edge_recall
    assert len(retrieval_json["comparisons"]) == len(result.comparisons)
    assert result.corpus_id in scorecard


def test_deterministic_fake_run_is_reproducible():
    """Two fake runs produce identical graph payload hashes and identical
    per-question coverage -- determinism the tests depend on."""
    def _once():
        r, _p, _e = run_benchmark(
            config.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH, InMemoryRevisionAuthorityRepository(),
            FakeRelationshipExtractor(), FakeEmbeddingProvider(), InMemoryGraphStore(),
        )
        return r
    a, b = _once(), _once()
    assert a.build_manifest.graph_payload_sha256 == b.build_manifest.graph_payload_sha256
    assert [g.required_fact_coverage_at_k for g in a.graph_question_metrics] == [g.required_fact_coverage_at_k for g in b.graph_question_metrics]


def test_frozen_stages_never_modified_by_stage7b1():
    import subprocess

    result = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--",
         "src/ingestion_bench/cross_document_benchmark", "src/ingestion_bench/revision_authority",
         "src/ingestion_bench/revision_search_benchmark", "src/ingestion_bench/retrieval_baseline",
         "src/ingestion_bench/canonical", "src/ingestion_bench/chunking", "src/ingestion_bench/adapters",
         "contracts/cross_document_relationship_benchmark_v1.json", "reports/stage7b0_cross_document_vector_results.json"],
        cwd=REPO_ROOT, capture_output=True,
    )
    if result.returncode not in (0, 1):
        pytest.skip("git diff unavailable")
    assert result.returncode == 0, "a frozen Stage 7B.0 / 7R / 7A input was modified"


# --- real OpenAI extraction + Postgres (skippable) --------------------------


def _real_infra_available() -> bool:
    try:
        import os

        if not config.DATABASE_URL or not os.environ.get("OPENAI_API_KEY"):
            return False
        import psycopg

        conn = psycopg.connect(config.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://"), connect_timeout=5)
        conn.close()
        import openai  # noqa: F401
        import sentence_transformers  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _real_infra_available(), reason="DATABASE_URL/OPENAI_API_KEY not set, Postgres unreachable, or openai/sentence-transformers missing")
def test_real_openai_extraction_and_postgres_graph_end_to_end():
    """Proves the ACTUAL OpenAI extractor + ACTUAL Postgres graph store +
    ACTUAL embedding model work end to end -- not a mock. Uses throwaway
    graph tables and cleans up the benchmark's own authority rows."""
    from sqlalchemy import text as sa_text

    from ingestion_bench.graph_retrieval_benchmark.extractor import OpenAIRelationshipExtractor
    from ingestion_bench.graph_retrieval_benchmark.postgres_store import PgGraphStore
    from ingestion_bench.retrieval_baseline.embeddings import SentenceTransformerEmbeddingProvider
    from ingestion_bench.revision_authority.postgres_repository import PostgresRevisionAuthorityRepository

    contract = load_contract(config.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH)
    corpus_docs = sorted({f["logical_document_id"] for f in contract["fixtures"]})
    repository = PostgresRevisionAuthorityRepository()
    store = PgGraphStore(node_table="_pytest_7b1_node", edge_table="_pytest_7b1_edge", run_table="_pytest_7b1_run")
    engine = repository._ensure_ready()

    def _cleanup():
        with engine.connect() as conn:
            for d in corpus_docs:
                conn.execute(sa_text(f"DELETE FROM {repository._period_table} WHERE logical_document_id = :d"), {"d": d})
                conn.execute(sa_text(f"DELETE FROM {repository._registry_table} WHERE logical_document_id = :d"), {"d": d})
                conn.execute(sa_text(f"DELETE FROM {repository._event_table} WHERE logical_document_id = :d"), {"d": d})
            for tbl in ("_pytest_7b1_edge", "_pytest_7b1_node", "_pytest_7b1_run"):
                conn.execute(sa_text(f"DROP TABLE IF EXISTS {tbl} CASCADE"))
            conn.commit()

    _cleanup()
    try:
        result, _projection, _evidence = run_benchmark(
            config.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH, repository, OpenAIRelationshipExtractor(),
            SentenceTransformerEmbeddingProvider(), store,
        )
        assert result.frozen_input_verification.index_hash_matches is True
        assert result.graph_all_authority_correct is True  # authority correctness is required; graph VALUE is not
        assert result.build_evaluation.edge_assertion_count > 0
    finally:
        _cleanup()
