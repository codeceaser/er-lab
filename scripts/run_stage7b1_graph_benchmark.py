"""Stage 7B.1 runner: builds an evidence-backed graph projection from the
frozen Stage 7B.0 chunks (real OpenAI relationship extraction, real
Postgres graph tables, real sentence-transformers embeddings), runs the
authority-aware graph retriever over the frozen 12 questions, and
compares against the frozen Stage 7B.0 Vector baseline -- writing the
build/retrieval reports, the Vector-vs-Graph scorecard, and the artifacts
from that ONE execution.

Retrieval and comparison only -- NO answer generation. Never modifies any
frozen stage. Postgres only (no Neo4j).

Usage (from the repo root, venv active, DATABASE_URL + OPENAI_API_KEY set):
    python scripts/run_stage7b1_graph_benchmark.py
    # deterministic, no-network variant (fake extractor + in-memory stores):
    python scripts/run_stage7b1_graph_benchmark.py --fake
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "fixtures"))

from sqlalchemy import text  # noqa: E402

from ingestion_bench.graph_retrieval_benchmark import config  # noqa: E402
from ingestion_bench.graph_retrieval_benchmark.benchmark_runner import run_benchmark  # noqa: E402
from ingestion_bench.graph_retrieval_benchmark.extractor import FakeRelationshipExtractor, OpenAIRelationshipExtractor  # noqa: E402
from ingestion_bench.graph_retrieval_benchmark.postgres_store import PgGraphStore  # noqa: E402
from ingestion_bench.graph_retrieval_benchmark.report import (  # noqa: E402
    recommend,
    render_build_results_json,
    render_retrieval_results_json,
    render_scorecard_markdown,
)
from ingestion_bench.graph_retrieval_benchmark.store import InMemoryGraphStore  # noqa: E402
from ingestion_bench.retrieval_baseline.embeddings import FakeEmbeddingProvider, SentenceTransformerEmbeddingProvider  # noqa: E402
from ingestion_bench.revision_authority.postgres_repository import PostgresRevisionAuthorityRepository  # noqa: E402
from ingestion_bench.revision_authority.repository import InMemoryRevisionAuthorityRepository  # noqa: E402


def _cleanup_prior_run(repository: PostgresRevisionAuthorityRepository, store: PgGraphStore, corpus_logical_document_ids: list[str]) -> None:
    """Makes the script safely re-runnable against the SAME real database:
    deletes any prior registry/period/event rows for THIS benchmark's own
    corpus logical documents (the shared Stage 7R registry tables, scoped
    by logical_document_id -- never any other document), and DROPS this
    benchmark's OWN isolated graph tables outright."""
    engine = repository._ensure_ready()
    with engine.connect() as conn:
        for logical_document_id in corpus_logical_document_ids:
            conn.execute(text(f"DELETE FROM {repository._period_table} WHERE logical_document_id = :d"), {"d": logical_document_id})
            conn.execute(text(f"DELETE FROM {repository._registry_table} WHERE logical_document_id = :d"), {"d": logical_document_id})
            conn.execute(text(f"DELETE FROM {repository._event_table} WHERE logical_document_id = :d"), {"d": logical_document_id})
        conn.commit()
    graph_engine = store._ensure_ready()
    with graph_engine.connect() as conn:
        for tbl in (store._edge_table, store._node_table, store._run_table):
            conn.execute(text(f"DROP TABLE IF EXISTS {tbl} CASCADE"))
        conn.commit()
    # The graph tables were just dropped; force the store to recreate its
    # schema on next use (its _schema_ready flag is now stale).
    store._schema_ready = False


def main() -> None:
    fake = "--fake" in sys.argv[1:]
    contract = json.loads(config.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH.read_text(encoding="utf-8"))
    corpus_logical_document_ids = sorted({f["logical_document_id"] for f in contract["fixtures"]})

    if fake:
        repository = InMemoryRevisionAuthorityRepository()
        extractor = FakeRelationshipExtractor()
        embedding_provider = FakeEmbeddingProvider()
        store = InMemoryGraphStore()
        print("Mode: FAKE (deterministic, no network)")
    else:
        repository = PostgresRevisionAuthorityRepository()
        extractor = OpenAIRelationshipExtractor()
        embedding_provider = SentenceTransformerEmbeddingProvider()
        store = PgGraphStore()
        print(f"Mode: REAL (extractor {extractor.extractor_identity}, embedding {embedding_provider.model_identity})")
        print(f"Graph tables: {store._node_table}/{store._edge_table}/{store._run_table} (isolated)")
        _cleanup_prior_run(repository, store, corpus_logical_document_ids)

    result, projection, _evidence = run_benchmark(
        config.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH, repository, extractor, embedding_provider, store
    )

    config.ARTIFACTS_ROOT.mkdir(parents=True, exist_ok=True)
    (config.ARTIFACTS_ROOT / "extraction_runs").mkdir(parents=True, exist_ok=True)
    (config.ARTIFACTS_ROOT / "query_results").mkdir(parents=True, exist_ok=True)

    (config.ARTIFACTS_ROOT / "graph_manifest.json").write_text(result.build_manifest.model_dump_json(indent=2), encoding="utf-8")
    (config.ARTIFACTS_ROOT / "graph_nodes.json").write_text(
        json.dumps([json.loads(n.model_dump_json()) for n in projection.nodes.values()], indent=2), encoding="utf-8")
    (config.ARTIFACTS_ROOT / "graph_edge_assertions.json").write_text(
        json.dumps([json.loads(e.model_dump_json()) for e in projection.edge_assertions], indent=2), encoding="utf-8")
    (config.ARTIFACTS_ROOT / "extraction_runs" / f"{result.extraction_run.extraction_run_id}.json").write_text(
        result.extraction_run.model_dump_json(indent=2), encoding="utf-8")
    (config.ARTIFACTS_ROOT / "comparison.json").write_text(
        json.dumps([json.loads(c.model_dump_json()) for c in result.comparisons], indent=2), encoding="utf-8")
    for g in result.graph_question_metrics:
        (config.ARTIFACTS_ROOT / "query_results" / f"{g.question_id}.json").write_text(g.model_dump_json(indent=2), encoding="utf-8")

    config.REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    (config.REPORTS_ROOT / "stage7b1_graph_build_results.json").write_text(render_build_results_json(result, projection), encoding="utf-8")
    (config.REPORTS_ROOT / "stage7b1_graph_retrieval_results.json").write_text(render_retrieval_results_json(result), encoding="utf-8")
    (config.REPORTS_ROOT / "stage7b1_vector_vs_graph_scorecard.md").write_text(render_scorecard_markdown(result), encoding="utf-8")

    be = result.build_evaluation
    print(f"\nFrozen input verified: {result.frozen_input_verification.index_hash_matches}")
    print(f"Graph build: {be.node_count} nodes, {be.edge_assertion_count} edges, recall={be.expected_fact_edge_recall:.2f} "
          f"precision={be.extracted_edge_precision:.2f} unsupported={be.unsupported_extracted_edge_count} collisions={be.entity_normalization_collision_count}")
    print(f"Extraction: {result.extraction_run.input_tokens}/{result.extraction_run.output_tokens} tokens, "
          f"cost={result.extraction_run.estimated_cost_usd}, failures={result.extraction_run.extraction_failure_count}")
    print(f"Graph authority correct: {result.graph_authority_correct_count}/{result.questions_total}")
    print(f"Improved:  {result.improved_question_ids}")
    print(f"Unchanged: {result.unchanged_question_ids}")
    print(f"Regressed: {result.regressed_question_ids}")
    rec, reason = recommend(result)
    print(f"\nRecommendation: {rec}\n  {reason}")
    print(f"\nReports: {config.REPORTS_ROOT}/stage7b1_*")
    print(f"Artifacts: {config.ARTIFACTS_ROOT}")

    if not result.graph_all_authority_correct:
        # Authority correctness is the ONE hard gate (graph value is not).
        sys.exit(1)


if __name__ == "__main__":
    main()
