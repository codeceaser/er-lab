"""Stage 7A.3: isolation tests.

- No frozen package (Stage 5A/6A/6B/7A.1/7A.2/7A.2a) is modified by this
  stage.
- No Graph RAG/wiki/vision/ADK/reranking/hybrid-retrieval/query-
  decomposition/new-embeddings/pgvector dependency is introduced.
- The demo never performs live retrieval or live answer generation --
  it is a read-only viewer over the already-committed Stage 7A.2/7A.2a
  answer run.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_ROOT = REPO_ROOT / "src" / "ingestion_bench" / "demo"


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


def test_frozen_packages_never_modified_by_this_stage():
    result = subprocess.run(
        [
            "git", "diff", "--quiet", "HEAD", "--",
            "src/ingestion_bench/retrieval_baseline",
            "src/ingestion_bench/retrieval_benchmark",
            "src/ingestion_bench/evaluation",
            "src/ingestion_bench/adapters",
            "src/ingestion_bench/canonical",
            "src/ingestion_bench/chunking",
            "contracts/retrieval_benchmark_v1.json",
            "reports/stage7a_vector_retrieval_results.json",
            "reports/stage7a_vector_retrieval_scorecard.md",
        ],
        cwd=REPO_ROOT, capture_output=True,
    )
    if result.returncode not in (0, 1):
        pytest.skip("git diff could not be evaluated in this environment")
    assert result.returncode == 0, "a frozen Stage 5A/6A/6B/7A.1 file has uncommitted changes"


def test_demo_package_has_no_graph_wiki_vision_adk_or_new_retrieval_dependency():
    forbidden = (
        "networkx", "neo4j", "graphrag", "wiki", "adk",
        "docling",  # ingestion is frozen -- reads already-computed answer results only
        "sentence_transformers",  # never re-embeds
        "openai",  # never re-invokes the answer model -- this is a read-only viewer
        "anthropic",
        "flask", "fastapi", "django", "streamlit", "gradio",  # no enterprise/heavy web framework
    )
    checked = 0
    for path in DEMO_ROOT.rglob("*.py"):
        checked += 1
        for module in forbidden:
            assert not _source_has_import(path, module), f"{path} imports forbidden module containing {module!r}"
    assert checked > 0


def test_demo_package_never_imports_retrieval_or_answer_generation_entry_points():
    """A read-only viewer: it may import the FROZEN pydantic DATA MODELS
    (AnswerResult, QuestionAnswerResult, RetrievalResult, etc.) but must
    never import retrieval_baseline.retrieval.search or
    answer_baseline.answer_generator -- there is no live-inference path
    anywhere in this package."""
    forbidden_modules = (
        "retrieval_baseline.retrieval",
        "retrieval_baseline.indexer",
        "retrieval_baseline.vector_store",
        "retrieval_baseline.pgvector_store",
        "retrieval_baseline.embeddings",
        "answer_baseline.answer_generator",
        "answer_baseline.prompt",
    )
    for path in DEMO_ROOT.rglob("*.py"):
        for module in forbidden_modules:
            assert not _source_has_import(path, module), f"{path} imports {module!r} -- no live inference allowed"


def test_demo_package_never_calls_search_or_generate():
    for path in DEMO_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in ("generate",), f"{path} calls .generate() -- no live inference allowed"
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id != "search", f"{path} calls search() -- no live retrieval allowed"


def test_demo_source_never_hardcodes_an_api_key():
    import re

    key_like = re.compile(r"sk-[A-Za-z0-9_-]{16,}")
    for path in DEMO_ROOT.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert not key_like.search(source), f"{path} appears to contain a hardcoded API-key-shaped literal"
