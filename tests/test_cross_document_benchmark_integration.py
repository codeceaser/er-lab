"""Stage 7B.0: end-to-end cross-document benchmark integration tests.

Runs the REAL contract through the REAL Stage 5A adapter + Stage 4/4.1
chunker (real Docling conversion of the tracked DOCX fixtures) with a
deterministic FAKE embedding provider and in-memory store/registry. One
additional test is skippable and uses the REAL sentence-transformers
model + REAL Postgres/pgvector.

Assertions target AUTHORITY correctness and evidence DISTRIBUTION (both
embedding-independent and deterministic), never the vector ranking
outcome (which depends on the embedding model and is only meaningful in
the real run) -- the spec's point is to REPORT vector behavior honestly,
not to force any particular outcome.
"""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

import pytest

from ingestion_bench.cross_document_benchmark import config
from ingestion_bench.cross_document_benchmark.benchmark_runner import build_evidence_alignment, load_contract, run_benchmark
from ingestion_bench.cross_document_benchmark.fixtures import load_all_revision_fixtures
from ingestion_bench.cross_document_benchmark.store import InMemoryCrossDocumentVectorStore
from ingestion_bench.retrieval_baseline.embeddings import FakeEmbeddingProvider
from ingestion_bench.revision_authority.repository import InMemoryRevisionAuthorityRepository

REPO_ROOT = Path(__file__).resolve().parent.parent
CROSS_DOC_ROOT = REPO_ROOT / "src" / "ingestion_bench" / "cross_document_benchmark"
MULTI_HOP_TYPES = {"distributed_two_hop_lookup", "distributed_multi_hop_lookup", "relationship_consolidation", "historical_comparison"}


@pytest.fixture(scope="module")
def contract():
    return load_contract(config.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH)


@pytest.fixture(scope="module")
def benchmark_result():
    """ONE real run (real Docling x11, real chunker, fake embeddings,
    in-memory store/registry) shared by every test in this module."""
    repository = InMemoryRevisionAuthorityRepository()
    provider = FakeEmbeddingProvider()
    store = InMemoryCrossDocumentVectorStore()
    return run_benchmark(config.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH, repository, provider, store)


def _q(result, question_id):
    return next(q for q in result.question_results if q.question_id == question_id)


# --- evidence distribution / holdout structure ------------------------------


def test_every_expected_fact_has_independent_single_chunk_evidence(contract):
    """Every contract fact resolves to EXACTLY ONE supporting chunk in
    its own supporting revision -- independent source evidence, never
    ambiguous, never absent."""
    fixtures = load_all_revision_fixtures(contract["fixtures"])
    evidence = build_evidence_alignment(contract, fixtures)
    assert len(evidence) == len(contract["facts"])
    for fact_id, ev in evidence.items():
        assert ev.supporting_chunk_id
        assert len(ev.supporting_content_sha256) == 64


def test_multi_hop_facts_are_distributed_across_documents_and_chunks(contract, benchmark_result):
    """For every multi-hop question, the required facts must be spread
    across MORE THAN ONE logical document and MORE THAN ONE chunk --
    otherwise the question is not genuinely distributed."""
    fixtures = load_all_revision_fixtures(contract["fixtures"])
    evidence = build_evidence_alignment(contract, fixtures)
    for question in contract["questions"]:
        if question["question_type"] not in MULTI_HOP_TYPES:
            continue
        if len(question["required_fact_ids"]) < 2:
            continue
        docs = {evidence[f].supporting_logical_document_id for f in question["required_fact_ids"]}
        chunks = {evidence[f].supporting_chunk_id for f in question["required_fact_ids"]}
        assert len(docs) >= 2, f"{question['question_id']}: required facts not distributed across documents ({docs})"
        assert len(chunks) == len(question["required_fact_ids"]), f"{question['question_id']}: required facts share a chunk"


def test_no_single_chunk_contains_a_preassembled_multi_hop_answer(contract):
    """The core holdout property: for every multi-hop question, NO single
    chunk in the whole corpus contains the source passages of ALL its
    required facts. A chunk that did would let Vector 'cheat' the chain
    in one hop. Deterministic, embedding-independent."""
    fixtures = load_all_revision_fixtures(contract["fixtures"])
    all_chunks = [c for fx in fixtures.values() for c in fx.chunks]
    passage_by_fact = {f["fact_id"]: f["expected_supporting_passage"] for f in contract["facts"]}
    for question in contract["questions"]:
        required = question["required_fact_ids"]
        if len(required) < 2:
            continue
        for chunk in all_chunks:
            contained = [f for f in required if passage_by_fact[f] in chunk.retrieval_text]
            assert len(contained) < len(required), (
                f"{question['question_id']}: chunk {chunk.chunk_id} contains ALL required facts {required} "
                "-- the multi-hop answer is pre-assembled in one chunk"
            )


def test_distractor_revisions_registered_and_excluded_under_current(benchmark_result):
    """The historical/draft/adjacent distractor revisions exist and, for
    current-intent questions, the historical (app_rev1, obl_rev1,
    ctl_rev1, prc_rev1) and draft (ctl_rev3) revisions are NEVER in the
    eligible union -- authority registration is correct."""
    result, _id_to_symbol, _evidence = benchmark_result
    q = _q(result, "Q06_four_hop_procedure_of_app")  # current intent, resolves all documents
    eligible = set(q.eligible_revision_symbols)
    assert {"app_rev2", "svc_rev1", "obl_rev2", "ctl_rev2", "prc_rev2", "adj_rev1"} == eligible
    for historical_or_draft in ("app_rev1", "obl_rev1", "ctl_rev1", "prc_rev1", "ctl_rev3"):
        assert historical_or_draft not in eligible


def test_current_queries_exclude_historical_and_draft_relations(benchmark_result):
    """Every current-intent question's authority-aware hits belong only to
    currently-effective revisions -- zero authority leakage."""
    result, _id_to_symbol, _evidence = benchmark_result
    current_eligible = {"app_rev2", "svc_rev1", "obl_rev2", "ctl_rev2", "prc_rev2", "adj_rev1"}
    for q in result.question_results:
        if q.query_intent != "current":
            continue
        assert q.authority_leakage_count == 0, q.question_id
        assert set(q.eligible_revision_symbols) == current_eligible, q.question_id


def test_historical_queries_recover_historical_relations(benchmark_result):
    """as_of-2021 questions resolve the historical (rev1) revisions, never
    the current rev2 successors -- historical recovery works."""
    result, _id_to_symbol, _evidence = benchmark_result
    historical_eligible = {"app_rev1", "svc_rev1", "obl_rev1", "ctl_rev1", "prc_rev1", "adj_rev1"}
    for q in result.question_results:
        if q.query_intent != "as_of":
            continue
        assert set(q.eligible_revision_symbols) == historical_eligible, q.question_id
        assert q.authority_leakage_count == 0, q.question_id


def test_draft_query_isolates_the_requested_draft_revision(benchmark_result):
    result, _id_to_symbol, _evidence = benchmark_result
    q = _q(result, "Q12_draft_proposed_control")
    assert q.eligible_revision_symbols == ["ctl_rev3"]
    assert q.authority_leakage_count == 0


def test_all_questions_authority_correct(benchmark_result):
    """The real pass condition: authority filtering is correct on EVERY
    question (no ineligible/forbidden-by-authority fact ever leaks into
    authority-aware hits). Vector recall outcome is reported separately,
    never a pass/fail gate."""
    result, _id_to_symbol, _evidence = benchmark_result
    for q in result.question_results:
        assert q.authority_correct, f"{q.question_id}: {q.failure_reasons}"
    assert result.all_authority_correct is True


def test_every_retrieval_hit_has_complete_provenance(benchmark_result):
    result, _id_to_symbol, _evidence = benchmark_result
    for q in result.question_results:
        for hit in q.result.hits + q.result.unfiltered_hits:
            assert hit.logical_document_id
            assert len(hit.document_revision_id) == 64
            assert len(hit.content_sha256) == 64
            assert len(hit.source_document_sha256) == 64
            assert hit.source_relative_path
            assert hit.chunk_type
            assert isinstance(hit.source_refs, list) and len(hit.source_refs) > 0


def test_authority_aware_hits_carry_a_resolver_authority_label(benchmark_result):
    """Every authority-aware hit carries the resolver's own label for its
    revision (never a bare score) -- the provenance a future graph
    comparison must also provide."""
    result, _id_to_symbol, _evidence = benchmark_result
    for q in result.question_results:
        for hit in q.result.hits:
            assert hit.authority_label is not None
            assert hit.authority_label.derived_state is not None


def test_question_inventory_covers_all_required_types(contract):
    types = {q["question_type"] for q in contract["questions"]}
    required = {
        "direct_semantic_lookup", "one_hop_relationship_lookup", "distributed_two_hop_lookup",
        "distributed_multi_hop_lookup", "relationship_consolidation", "distractor_resistance",
        "current_authority_relationship_lookup", "historical_comparison", "draft_lookup",
    }
    assert required <= types
    assert 10 <= len(contract["questions"]) <= 12


# --- holdout enforcement: retrieval never consumes evaluation truth ---------


def test_retriever_and_store_never_read_evaluation_truth():
    """The retriever and store modules must never READ evaluation truth
    (required_fact_ids / forbidden_fact_ids / expected_relationship_chain)
    -- those are consumed only by the evaluator
    (benchmark_runner._evaluate_question). Checked at the AST level for
    actual subscript-key or attribute reads, so an explanatory DOCSTRING
    that merely NAMES these fields (to state it does not read them) does
    not trip the test."""
    forbidden_names = {"required_fact_ids", "forbidden_fact_ids", "expected_relationship_chain"}
    for module in ("retriever.py", "store.py", "indexer.py", "pgvector_store.py"):
        tree = ast.parse((CROSS_DOC_ROOT / module).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            # d["required_fact_ids"] -- a Subscript with a constant string slice.
            if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                assert node.slice.value not in forbidden_names, f"{module} reads evaluation truth key {node.slice.value!r}"
            # obj.required_fact_ids -- an attribute access.
            if isinstance(node, ast.Attribute):
                assert node.attr not in forbidden_names, f"{module} reads evaluation truth attribute {node.attr!r}"


def test_reports_and_artifacts_use_the_same_run_object(benchmark_result):
    """The JSON report, Markdown scorecard, and per-question artifacts all
    derive from ONE BenchmarkRunResult -- proven here by rendering both
    from the same object and confirming they agree on the headline
    counts (there is only one object to render from)."""
    from ingestion_bench.cross_document_benchmark.report import render_results_json, render_scorecard_markdown

    result, _id_to_symbol, _evidence = benchmark_result
    results_json = json.loads(render_results_json(result))
    scorecard = render_scorecard_markdown(result)
    assert results_json["all_authority_correct"] is result.all_authority_correct
    assert f"{result.authority_correct_count}/{result.questions_total}" in scorecard
    assert len(results_json["question_results"]) == len(result.question_results)


# --- isolation ---------------------------------------------------------------


def test_no_forbidden_dependency_anywhere_in_cross_document_benchmark():
    """No Graph RAG, wiki, ADK, answer-generation, or vision-enrichment
    dependency anywhere in this package -- matched against '.'-separated
    module path segments ('revision_authority' legitimately contains the
    substring 'vision')."""
    forbidden = ("graph_rag", "wiki", "adk", "answer_baseline", "vision", "reranker", "rerank", "traversal", "graph_builder")
    for path in CROSS_DOC_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                segments = node.module.lower().split(".")
                for name in forbidden:
                    assert name not in segments, f"{path} imports {node.module!r} (forbidden: {name!r})"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    segments = alias.name.lower().split(".")
                    for name in forbidden:
                        assert name not in segments, f"{path} imports {alias.name!r} (forbidden: {name!r})"


def test_frozen_stage_own_files_never_modified_by_stage7b0():
    """Stage 7A.1, Stage 7R.1, Stage 7R.2, canonical, chunking,
    evaluation, adapters own files must remain byte-identical -- Stage
    7B.0 uses its OWN isolated package/table and only READ-only imports
    the frozen ones."""
    result = subprocess.run(
        [
            "git", "diff", "--quiet", "HEAD", "--",
            "src/ingestion_bench/retrieval_baseline", "src/ingestion_bench/revision_authority",
            "src/ingestion_bench/revision_search_benchmark", "src/ingestion_bench/canonical",
            "src/ingestion_bench/chunking", "src/ingestion_bench/evaluation", "src/ingestion_bench/adapters",
            "src/ingestion_bench/answer_baseline", "src/ingestion_bench/demo", "src/ingestion_bench/retrieval_benchmark",
            "contracts/revision_authority_scenarios_v2.json", "contracts/revision_search_benchmark_v1.json",
            "contracts/retrieval_benchmark_v1.json", "contracts/corpus_profiles_v1.json",
        ],
        cwd=REPO_ROOT, capture_output=True,
    )
    if result.returncode not in (0, 1):
        pytest.skip(f"git diff check unavailable: {result.stderr.decode(errors='replace')}")
    assert result.returncode == 0, "a frozen Stage 7A.1/7R.1/7R.2/canonical/chunking file was modified"


# --- real Postgres + real sentence-transformers (skippable) -----------------


def _real_infra_available() -> bool:
    try:
        if not config.DATABASE_URL:
            return False
        import psycopg

        conn = psycopg.connect(config.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://"), connect_timeout=5)
        conn.close()
        import sentence_transformers  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _real_infra_available(), reason="DATABASE_URL not set/Postgres unreachable, or sentence-transformers not installed")
def test_real_sentence_transformers_and_pgvector_end_to_end():
    """Proves the ACTUAL embedding model + ACTUAL Postgres/pgvector work
    end to end for this benchmark -- not a mock. Uses a throwaway table
    and cleans up the benchmark's own logical documents afterward."""
    from sqlalchemy import text as sa_text

    from ingestion_bench.cross_document_benchmark.pgvector_store import PgVectorCrossDocumentStore
    from ingestion_bench.retrieval_baseline.embeddings import SentenceTransformerEmbeddingProvider
    from ingestion_bench.revision_authority.postgres_repository import PostgresRevisionAuthorityRepository

    contract = load_contract(config.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH)
    corpus_docs = sorted({f["logical_document_id"] for f in contract["fixtures"]})
    provider = SentenceTransformerEmbeddingProvider()
    repository = PostgresRevisionAuthorityRepository()
    store = PgVectorCrossDocumentStore(embedding_dimension=provider.dimension, table_name="_pytest_stage7b0_vectors")

    engine = repository._ensure_ready()

    def _cleanup():
        with engine.connect() as conn:
            for d in corpus_docs:
                conn.execute(sa_text(f"DELETE FROM {repository._period_table} WHERE logical_document_id = :d"), {"d": d})
                conn.execute(sa_text(f"DELETE FROM {repository._registry_table} WHERE logical_document_id = :d"), {"d": d})
                conn.execute(sa_text(f"DELETE FROM {repository._event_table} WHERE logical_document_id = :d"), {"d": d})
            conn.execute(sa_text("DROP TABLE IF EXISTS _pytest_stage7b0_vectors CASCADE"))
            conn.commit()

    _cleanup()
    try:
        result, _id_to_symbol, _evidence = run_benchmark(
            config.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH, repository, provider, store
        )
        assert result.all_authority_correct is True
        assert result.index_build.total_record_count == 11
    finally:
        _cleanup()
