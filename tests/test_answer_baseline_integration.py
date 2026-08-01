"""Stage 7A.2: integration and isolation tests.

- An explicit, skippable real-model integration test for the ONE real,
  configured answer model (OpenAI) -- skipped gracefully when
  OPENAI_API_KEY is unavailable, never required for the normal
  unit-test suite.
- Isolation proofs: this stage never modifies Stage 5A/6A/6B/7A.1 code
  or artifacts, and never introduces a Graph RAG/wiki/vision/
  reranking/hybrid-retrieval/query-decomposition/ADK/LLM-judge
  dependency.
"""

from __future__ import annotations

import ast
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ANSWER_BASELINE_ROOT = REPO_ROOT / "src" / "ingestion_bench" / "answer_baseline"


# --- real OpenAI answer-model integration (explicit, skippable) -------------


def _real_openai_answer_model_available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


@pytest.mark.skipif(not _real_openai_answer_model_available(), reason="OPENAI_API_KEY not set")
def test_real_openai_answer_generator_end_to_end():
    """Proves the ACTUAL configured answer model works against a small,
    hand-built retrieval context -- not a fake. Uses a throwaway
    question_id, never touches reports/ or artifacts/."""
    from ingestion_bench.answer_baseline.answer_generator import OpenAIAnswerGenerator
    from ingestion_bench.answer_baseline.model import AnswerResult
    from ingestion_bench.retrieval_baseline.retrieval import RetrievalResult

    retrieved = [
        RetrievalResult(
            rank=1, score=0.9, chunk_id="c1", content_sha256="a" * 64,
            retrieval_text="The Recovery Time Objective (RTO) for APP-224510 is 4 hours, per Control C-88.",
            fixture="parity/PARITY_001.pdf", doc_id="PARITY_001", source_format="pdf",
            unit_indices=[0], source_element_ids=[], heading_source_element_ids=[],
            annotation_ids=[], source_refs=[], heading_path=["Recovery Objectives"],
        )
    ]
    generator = OpenAIAnswerGenerator()
    result = generator.generate("_pytest_integration_selftest", "What is the RTO for APP-224510?", retrieved)

    assert isinstance(result, AnswerResult)
    assert result.model_identity == generator.model_identity
    assert result.retrieved_chunk_ids == ["c1"]
    assert set(result.cited_chunks) <= {"c1"}
    assert result.answer_latency_seconds > 0
    assert result.input_tokens is not None and result.input_tokens > 0
    assert result.output_tokens is not None and result.output_tokens > 0


# --- isolation: Stage 5A/6A/6B/7A.1 never modified by this stage ------------


def test_stage5a_6a_6b_7a1_source_never_references_answer_baseline():
    forbidden_mentions = ("answer_baseline", "stage7a2", "AnswerResult", "ClaimCitation")
    checked = 0
    for package in ("adapters", "canonical", "chunking", "evaluation", "retrieval_baseline", "retrieval_benchmark"):
        package_root = REPO_ROOT / "src" / "ingestion_bench" / package
        if not package_root.exists():
            continue
        for path in package_root.rglob("*.py"):
            checked += 1
            source = path.read_text(encoding="utf-8")
            for mention in forbidden_mentions:
                assert mention not in source, f"{path} references {mention!r}"
    assert checked > 0


def test_stage7a1_committed_reports_never_modified_by_this_stage():
    result = subprocess.run(
        [
            "git", "diff", "--quiet", "HEAD", "--",
            "reports/stage7a_vector_retrieval_results.json",
            "reports/stage7a_vector_retrieval_scorecard.md",
            "src/ingestion_bench/retrieval_baseline",
            "src/ingestion_bench/retrieval_benchmark",
            "contracts/retrieval_benchmark_v1.json",
        ],
        cwd=REPO_ROOT, capture_output=True,
    )
    if result.returncode not in (0, 1):
        pytest.skip("git diff could not be evaluated in this environment")
    assert result.returncode == 0, "a Stage 7A.1/6B frozen file has uncommitted changes"


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


def test_answer_baseline_has_no_graph_wiki_vision_rerank_hybrid_decomposition_adk_dependency():
    forbidden = (
        "networkx", "neo4j", "graphrag", "wiki", "adk",
        "docling",  # ingestion is frozen -- this stage reads Stage 7A.1's own results.json only
        "sentence_transformers",  # never re-embeds or reranks -- retrieval itself is frozen and reused verbatim
        "anthropic",  # exactly one configured answer model (OpenAI), never a second LLM as judge
    )
    checked = 0
    for path in ANSWER_BASELINE_ROOT.rglob("*.py"):
        checked += 1
        for module in forbidden:
            assert not _source_has_import(path, module), f"{path} imports forbidden module containing {module!r}"
    assert checked > 0


def test_answer_baseline_never_builds_or_queries_a_vector_index():
    """This package must never construct its own embedding
    provider/vector_store/pgvector_store/indexer -- the ONLY permitted
    retrieval-context input is the already-computed
    reports/stage7a_vector_retrieval_results.json. Importing
    retrieval_baseline.retrieval / retrieval_baseline.evaluation / .gold
    for their pydantic DATA TYPES (RetrievalResult, RetrievalEvaluationRun,
    ScopedFactEvidence, gold_chunk_ids) is legitimate reuse, not a
    re-run of retrieval -- so those are deliberately not forbidden here."""
    forbidden_modules = ("retrieval_baseline.indexer", "retrieval_baseline.vector_store", "retrieval_baseline.pgvector_store", "retrieval_baseline.embeddings")
    for path in ANSWER_BASELINE_ROOT.rglob("*.py"):
        for module in forbidden_modules:
            assert not _source_has_import(path, module), f"{path} imports {module!r} -- retrieval must never be re-run"


def test_answer_baseline_never_calls_search_function():
    """A weaker but real guard: `search(` (the retrieval_baseline.retrieval
    entry point) must never appear as a call anywhere in this package's
    code."""
    for path in ANSWER_BASELINE_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id != "search", f"{path} calls search() -- retrieval must never be re-run"


def test_answer_baseline_source_never_hardcodes_an_api_key():
    """Credentials must come only from environment variables, never a
    literal secret in source -- a shallow but real guard: no long
    alphanumeric literal resembling an OpenAI-style secret key anywhere
    in this package's code (docstrings excluded, since they may
    legitimately reference the ENV VAR NAME, not a value)."""
    import re

    key_like = re.compile(r"sk-[A-Za-z0-9_-]{16,}")
    for path in ANSWER_BASELINE_ROOT.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert not key_like.search(source), f"{path} appears to contain a hardcoded API-key-shaped literal"
