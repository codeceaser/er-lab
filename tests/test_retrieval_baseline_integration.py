"""Stage 7A.1: integration and isolation tests.

- An explicit integration test for the ONE real, configured embedding
  model (sentence-transformers) and the ONE real, configured vector
  store (Postgres + pgvector) -- skipped gracefully when either is
  unavailable, never required for the normal unit-test suite.
- Isolation proofs: this stage never modifies Stage 5A/6A/6B code, and
  never introduces a network/LLM/vector-database-framework/Graph-RAG/
  wiki/vision/ADK/answer-generation dependency beyond the one configured
  embedding+store pair.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RETRIEVAL_BASELINE_ROOT = REPO_ROOT / "src" / "ingestion_bench" / "retrieval_baseline"


# --- real embedding + real vector store integration (skip if unavailable) ---


def _real_embedding_available() -> bool:
    try:
        from ingestion_bench.retrieval_baseline.embeddings import SentenceTransformerEmbeddingProvider

        provider = SentenceTransformerEmbeddingProvider()
        provider.embed(["ping"])
        return True
    except Exception:  # noqa: BLE001
        return False


def _real_pgvector_available() -> bool:
    """A lightweight, table-agnostic connectivity check -- deliberately
    never goes through PgVectorStore's own table-creation path (which is
    parameterized by embedding dimension): a probe using one dimension
    would otherwise create the real test's table with the WRONG
    dimension if it ran first, exactly the class of bug this stage hit
    twice against the real database during development."""
    try:
        from ingestion_bench.retrieval_baseline.config import DATABASE_URL

        if not DATABASE_URL:
            return False
        import psycopg

        conn = psycopg.connect(DATABASE_URL.replace("postgresql+psycopg://", "postgresql://"), connect_timeout=5)
        conn.close()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _real_embedding_available(), reason="real sentence-transformers model not available (no network/cache)")
@pytest.mark.skipif(not _real_pgvector_available(), reason="DATABASE_URL not set or Postgres/pgvector not reachable")
def test_real_embedding_and_real_pgvector_end_to_end():
    """Proves the ACTUAL configured stack (not a fake) works: real
    embeddings, real Postgres+pgvector persistence, idempotent upsert,
    and real cosine-similarity search -- using a throwaway
    corpus_profile/table so it never collides with real reported data."""
    from ingestion_bench.retrieval_baseline.embeddings import SentenceTransformerEmbeddingProvider
    from ingestion_bench.retrieval_baseline.pgvector_store import PgVectorStore
    from ingestion_bench.retrieval_baseline.vector_store import VectorRecord

    provider = SentenceTransformerEmbeddingProvider()
    store = PgVectorStore(embedding_dimension=provider.dimension, table_name="ingestion_bench_stage7a_vectors_selftest")
    profile = "_pytest_integration_selftest"
    engine = store._ensure_ready()

    try:
        embed_result = provider.embed(["Application APP-224510 supports the Payment Settlement business service."])
        record = VectorRecord(
            corpus_profile=profile, embedding_model=provider.model_identity, chunk_id="c1",
            content_sha256="a" * 64, retrieval_text="Application APP-224510 supports the Payment Settlement business service.",
            fixture="parity/PARITY_001.pdf", doc_id="PARITY_001", source_format="pdf",
            contains_model_derived=False, embedding=embed_result.vectors[0],
        )
        store.upsert([record])
        store.upsert([record])  # idempotency: must not duplicate
        assert store.record_count(profile, provider.model_identity) == 1

        query_vec = provider.embed(["APP-224510"]).vectors[0]
        hits = store.search(profile, provider.model_identity, query_vec, top_k=1)
        assert len(hits) == 1
        assert hits[0].record.chunk_id == "c1"
        assert hits[0].score > 0.0
    finally:
        from sqlalchemy import text

        with engine.connect() as conn:
            conn.execute(text(f"DELETE FROM {store._table_name} WHERE corpus_profile = :p"), {"p": profile})
            conn.commit()


# --- isolation: Stage 5A/6A/6B never modified by this stage ------------------


def test_stage5a_stage6a_stage6b_source_never_references_retrieval_baseline():
    """A weak but real guard against accidental cross-editing: none of
    the frozen upstream packages should ever mention this stage's own
    package/module names."""
    forbidden_mentions = ("retrieval_baseline", "pgvector_store", "stage7a")
    checked = 0
    for package in ("adapters", "canonical", "chunking", "evaluation"):
        for path in (REPO_ROOT / "src" / "ingestion_bench" / package).rglob("*.py"):
            checked += 1
            source = path.read_text(encoding="utf-8")
            for mention in forbidden_mentions:
                assert mention not in source, f"{path} references {mention!r}"
    retrieval_benchmark_root = REPO_ROOT / "src" / "ingestion_bench" / "retrieval_benchmark"
    for path in retrieval_benchmark_root.rglob("*.py"):
        checked += 1
        source = path.read_text(encoding="utf-8")
        for mention in forbidden_mentions:
            assert mention not in source, f"{path} references {mention!r}"
    assert checked > 0


def test_reference_manifest_json_content_byte_identical_to_git_head():
    """Stage 7A must not modify the frozen manifest -- confirmed by
    diffing the working tree against HEAD (skips cleanly if git or the
    file is unavailable in this environment, never a hard failure for an
    unrelated environment issue)."""
    manifest_path = REPO_ROOT / "fixtures" / "reference_manifest.json"
    if not manifest_path.exists():
        pytest.skip("fixtures/reference_manifest.json not present")
    result = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", "fixtures/reference_manifest.json"],
        cwd=REPO_ROOT, capture_output=True,
    )
    if result.returncode not in (0, 1):
        pytest.skip("git diff could not be evaluated in this environment")
    assert result.returncode == 0, "fixtures/reference_manifest.json has uncommitted changes"


def test_contract_files_stage6b_never_modified_by_this_stage():
    result = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", "contracts/retrieval_benchmark_v1.json"],
        cwd=REPO_ROOT, capture_output=True,
    )
    if result.returncode not in (0, 1):
        pytest.skip("git diff could not be evaluated in this environment")
    assert result.returncode == 0, "contracts/retrieval_benchmark_v1.json has uncommitted changes"


# --- isolation: no forbidden dependency of any kind --------------------------


def _source_has_import(path: Path, module_substring: str) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(module_substring in alias.name for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom) and node.module:
            if module_substring in node.module:
                return True
    return False


def test_retrieval_baseline_has_no_graph_wiki_vision_adk_or_answer_generation_dependency():
    forbidden = (
        "networkx", "neo4j", "graphrag", "wiki", "adk",
        "docling",  # ingestion is frozen -- this stage reads chunk artifacts only, never re-parses documents
        "anthropic",  # no answer generation / LLM-judge dependency
    )
    checked = 0
    for path in RETRIEVAL_BASELINE_ROOT.rglob("*.py"):
        checked += 1
        for module in forbidden:
            assert not _source_has_import(path, module), f"{path} imports forbidden module containing {module!r}"
    assert checked > 0


def test_retrieval_baseline_llm_usage_is_confined_to_embedding_not_answer_generation():
    """openai is not used at all (the configured embedding model is
    local sentence-transformers); if this ever changes, it must never be
    used for anything beyond embedding calls -- this test pins that
    boundary explicitly rather than allowing a silent LLM-judge or
    answer-generation dependency to slip in."""
    for path in RETRIEVAL_BASELINE_ROOT.rglob("*.py"):
        assert not _source_has_import(path, "openai"), path


def _docstring_node_ids(tree: ast.AST) -> set[int]:
    """Module/class/function docstrings -- excluded from the CODE-level
    scans below, since this stage's own docstrings routinely explain
    that it does NOT touch the GraphRAG POC's tables (that prose must
    never itself trip the check). Mirrors
    tests/test_stage6a_integration.py's own `_docstring_node_ids`."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                ids.add(id(body[0].value))
    return ids


def _code_level_string_constants(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstring_ids = _docstring_node_ids(tree)
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstring_ids
    ]


def test_retrieval_baseline_only_touches_its_own_database_table_name():
    """Never references document_chunks/documents/kg_* in actual CODE
    (SQL strings, table-name literals) -- the separate, frozen ER
    GraphRAG POC's own tables (docs/POC_ARCHITECTURE.md rule C: "the two
    are not wired together"). Docstrings that merely EXPLAIN this
    boundary in prose are excluded from the scan."""
    forbidden_tables = ("document_chunks", "kg_entities", "kg_edges", "kg_evidence", "graph_artifacts")
    for path in RETRIEVAL_BASELINE_ROOT.rglob("*.py"):
        constants = _code_level_string_constants(path)
        for table in forbidden_tables:
            assert not any(table in c for c in constants), f"{path} references {table!r} in code"


def test_retrieval_baseline_never_imports_the_graphrag_poc_own_modules():
    """Never imports src/db.py, src/config.py, or any other root-level
    GraphRAG POC module -- an independent connection to the same
    database instance, never a reuse of that POC's own code."""
    for path in RETRIEVAL_BASELINE_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name not in ("db", "config", "vector_retriever"), f"{path} imports {alias.name!r}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module not in ("db", "config", "vector_retriever"), f"{path} imports from {node.module!r}"
