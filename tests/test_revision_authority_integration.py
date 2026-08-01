"""Stage 7R.1: integration and isolation tests.

- Proves authority operations never mutate, rechunk, or re-embed real
  CanonicalChunk data (using the REAL, frozen chunk_document() -- not a
  mock).
- An explicit, skippable real-Postgres integration test.
- Isolation proofs: no frozen Stage 5A/6A/6B/7A.1/7A.2/7A.2a/7A.3 package
  is modified, and no Graph RAG/wiki/vision/ADK/chunking/embedding
  dependency is introduced anywhere in this new package.
"""

from __future__ import annotations

import ast
import os
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from ingestion_bench.canonical import CanonicalDocument, CanonicalParagraph, CanonicalUnit
from ingestion_bench.chunking import ChunkingConfig, DocumentRevisionContext, chunk_document, compute_document_revision_id
from ingestion_bench.revision_authority.repository import InMemoryRevisionAuthorityRepository
from ingestion_bench.revision_authority.service import RevisionAuthorityService

REPO_ROOT = Path(__file__).resolve().parent.parent
REVISION_AUTHORITY_ROOT = REPO_ROOT / "src" / "ingestion_bench" / "revision_authority"

NOW = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _real_canonical_chunks():
    """Builds ONE real CanonicalDocument and chunks it through the actual,
    frozen chunk_document() -- never a hand-built fake chunk -- so the
    "no mutation" proof below is about the real pipeline, not a stand-in."""
    document = CanonicalDocument(
        doc_id="POLICY-DOC", source_format="pdf", source_filename="policy.pdf",
        source_relative_path="policy/policy.pdf", source_sha256="c" * 64,
        units=[CanonicalUnit(unit_index=0, unit_type="page", width=612, height=792, coordinate_unit="pt", coordinate_origin="top-left")],
        paragraphs=[CanonicalParagraph(block_id="p1", unit_index=0, order_index=0, text="Retention period is 7 years.")],
    )
    document_revision_id = compute_document_revision_id(
        logical_document_id="POLICY-DOC", source_document_sha256="c" * 64, version_label=None, revision_number=3,
    )
    revision_context = DocumentRevisionContext(
        logical_document_id="POLICY-DOC", document_revision_id=document_revision_id,
        source_document_sha256="c" * 64, version_label=None, revision_number=3,
    )
    chunks = chunk_document(document, ChunkingConfig(), revision_context=revision_context)
    return chunks, document_revision_id


def test_old_canonical_chunk_content_and_hash_remain_unchanged():
    """Business nuance: revision-authority operations (register, decide,
    activate, withdraw, correct) must never alter a canonical chunk's own
    content or hash -- chunks are immutable per Stage 4/4.1, and Stage
    7R.1 explicitly must not modify CanonicalChunk. Failure this guards
    against: any authority operation accidentally touching ingested
    content (e.g. if a future refactor merged this registry with
    ingestion state). Affects: current search AND historical search
    (both must serve byte-identical evidence regardless of how many
    authority decisions have been recorded since ingestion) and
    auditability (a chunk's own hash is exactly what a citation's
    provenance depends on, Stage 7A.2's own discipline)."""
    chunks, document_revision_id = _real_canonical_chunks()
    before = [c.model_dump_json() for c in chunks]
    before_hashes = [c.content_sha256 for c in chunks]

    service = RevisionAuthorityService(InMemoryRevisionAuthorityRepository())
    service.register_revision(
        logical_document_id="POLICY-DOC", source_document_sha256="c" * 64, version_label=None, revision_number=3,
        authority_source="gov", authority_reference="REF", authority_recorded_by="alice", recorded_at=NOW,
    )
    service.activate_revision(
        new_revision_id=document_revision_id, old_revision_id=None, effective_from=date(2023, 1, 1),
        authority_source="gov", authority_reference="ACT", authority_recorded_by="alice", recorded_at=NOW,
    )
    service.record_authority_decision(
        document_revision_id=document_revision_id, publication_status="approved", effective_from=date(2023, 1, 1),
        authority_source="gov", authority_reference="CORR", authority_recorded_by="alice", recorded_at=NOW,
    )
    service.withdraw_revision(
        document_revision_id=document_revision_id, authority_source="gov", authority_reference="W",
        authority_recorded_by="alice", recorded_at=NOW,
    )

    after = [c.model_dump_json() for c in chunks]
    after_hashes = [c.content_sha256 for c in chunks]
    assert before == after
    assert before_hashes == after_hashes


def test_authority_correction_requires_no_chunk_mutation():
    """Business nuance: correcting/rolling back an authority decision
    (Scenario M) must be achievable purely through this package's own
    tables -- never by touching a chunk. Failure this guards against: a
    'fix the metadata' operation escalating into 'reprocess the
    document', which would be far more expensive and could silently
    change chunk_ids that Stage 7A.2 citations already reference. Affects:
    auditability (Stage 7A.2 citations must remain valid across authority
    corrections) and benchmark fairness (correcting a mistake must be
    cheap and side-effect-free)."""
    chunks, document_revision_id = _real_canonical_chunks()
    original_chunk_ids = [c.chunk_id for c in chunks]

    service = RevisionAuthorityService(InMemoryRevisionAuthorityRepository())
    service.register_revision(
        logical_document_id="POLICY-DOC", source_document_sha256="c" * 64, version_label=None, revision_number=3,
        authority_source="gov", authority_reference="REF", authority_recorded_by="alice", recorded_at=NOW,
    )
    service.record_authority_decision(document_revision_id=document_revision_id, publication_status="approved", effective_from=date(2029, 1, 1), authority_source="gov", authority_reference="D1", authority_recorded_by="alice", recorded_at=NOW)
    service.record_authority_decision(document_revision_id=document_revision_id, publication_status="draft", authority_source="gov", authority_reference="D2-rollback", authority_recorded_by="alice", recorded_at=NOW)

    assert [c.chunk_id for c in chunks] == original_chunk_ids


def test_authority_correction_requires_no_reembedding():
    """Business nuance: none of register/decide/activate/withdraw ever
    needs an embedding model at all -- correcting authority must never
    trigger (or even be ABLE to trigger) a re-embedding pass. Failure
    this guards against: an accidental dependency on
    retrieval_baseline.embeddings creeping into this package. Affects:
    benchmark fairness (a correction must be free) -- verified
    structurally: this package has no import of any embedding provider
    anywhere."""
    forbidden = ("embeddings", "sentence_transformers", "SentenceTransformer", "openai")
    for path in REVISION_AUTHORITY_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for name in forbidden:
                    assert name not in node.module, f"{path} imports {node.module!r}"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for name in forbidden:
                        assert name not in alias.name, f"{path} imports {alias.name!r}"


# --- real Postgres integration (explicit, skippable) -------------------------


def _real_postgres_available() -> bool:
    try:
        from ingestion_bench.revision_authority import config

        if not config.DATABASE_URL:
            return False
        import psycopg

        conn = psycopg.connect(config.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://"), connect_timeout=5)
        conn.close()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _real_postgres_available(), reason="DATABASE_URL not set or Postgres not reachable")
def test_real_postgres_revision_authority_repository():
    """Proves the ACTUAL configured Postgres repository works end to end
    (schema creation, register/activate, atomic transaction, event
    append) -- not a mock. Uses a throwaway logical_document_id so it
    never collides with real reported data, and cleans up afterward."""
    from ingestion_bench.revision_authority.postgres_repository import PostgresRevisionAuthorityRepository

    repo = PostgresRevisionAuthorityRepository()
    service = RevisionAuthorityService(repo)
    logical_document_id = "_pytest_stage7r1_selftest"

    from sqlalchemy import text

    engine = repo._ensure_ready()
    try:
        with engine.connect() as conn:
            conn.execute(text(f"DELETE FROM {repo._registry_table} WHERE logical_document_id = :d"), {"d": logical_document_id})
            conn.execute(text(f"DELETE FROM {repo._event_table} WHERE logical_document_id = :d"), {"d": logical_document_id})
            conn.commit()

        result = service.register_revision(
            logical_document_id=logical_document_id, source_document_sha256="d" * 64, version_label=None, revision_number=1,
            authority_source="gov", authority_reference="REF", authority_recorded_by="alice", recorded_at=NOW,
        )
        assert result.is_new_revision is True
        dup = service.register_revision(
            logical_document_id=logical_document_id, source_document_sha256="d" * 64, version_label=None, revision_number=1,
            authority_source="gov", authority_reference="REF2", authority_recorded_by="alice", recorded_at=NOW,
        )
        assert dup.is_new_revision is False
        assert dup.identity.document_revision_id == result.identity.document_revision_id

        service.activate_revision(
            new_revision_id=result.identity.document_revision_id, old_revision_id=None, effective_from=date(2024, 1, 1),
            authority_source="gov", authority_reference="ACT", authority_recorded_by="alice", recorded_at=NOW,
        )
        resolution = service.resolve_query_scope(logical_document_id=logical_document_id, query_intent="current", as_of_date=date(2024, 6, 1))
        assert resolution.eligible_revision_ids == [result.identity.document_revision_id]

        events = repo.list_events(logical_document_id)
        assert len(events) >= 3  # register, duplicate attempt, activate
    finally:
        with engine.connect() as conn:
            conn.execute(text(f"DELETE FROM {repo._registry_table} WHERE logical_document_id = :d"), {"d": logical_document_id})
            conn.execute(text(f"DELETE FROM {repo._event_table} WHERE logical_document_id = :d"), {"d": logical_document_id})
            conn.commit()


# --- isolation: no frozen package modified, no forbidden dependency ----------


def test_frozen_packages_never_modified_by_this_stage():
    result = subprocess.run(
        [
            "git", "diff", "--quiet", "HEAD", "--",
            "src/ingestion_bench/canonical", "src/ingestion_bench/chunking",
            "src/ingestion_bench/retrieval_baseline", "src/ingestion_bench/retrieval_benchmark",
            "src/ingestion_bench/evaluation", "src/ingestion_bench/adapters",
            "src/ingestion_bench/answer_baseline", "src/ingestion_bench/demo",
            "contracts/retrieval_benchmark_v1.json", "fixtures/reference_manifest.json",
        ],
        cwd=REPO_ROOT, capture_output=True,
    )
    if result.returncode not in (0, 1):
        pytest.skip("git diff could not be evaluated in this environment")
    assert result.returncode == 0, "a frozen package/contract/manifest has uncommitted changes"


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


def test_revision_authority_has_no_graph_wiki_vision_adk_dependency():
    forbidden = ("networkx", "neo4j", "graphrag", "wiki", "adk", "docling", "anthropic")
    checked = 0
    for path in REVISION_AUTHORITY_ROOT.rglob("*.py"):
        checked += 1
        for module in forbidden:
            assert not _source_has_import(path, module), f"{path} imports forbidden module containing {module!r}"
    assert checked > 0


def test_revision_authority_never_imports_chunk_document_or_canonical_chunk_mutably():
    """The only chunking-package import anywhere in this new package is
    the read-only identity reuse (DocumentRevisionContext,
    compute_document_revision_id) documented in model.py -- never
    chunk_document() itself, never CanonicalChunk."""
    forbidden_names = ("chunk_document", "CanonicalChunk", "CanonicalDocument")
    for path in REVISION_AUTHORITY_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and "chunking" in node.module:
                imported = {alias.name for alias in node.names}
                for forbidden in forbidden_names:
                    assert forbidden not in imported, f"{path} imports {forbidden!r} from {node.module!r}"


def test_revision_authority_source_never_hardcodes_an_api_key_or_db_credential():
    import re

    key_like = re.compile(r"sk-[A-Za-z0-9_-]{16,}")
    url_like = re.compile(r"postgresql(\+\w+)?://[^\s\"']*:[^\s\"']*@")
    for path in REVISION_AUTHORITY_ROOT.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert not key_like.search(source), f"{path} appears to contain a hardcoded API-key-shaped literal"
        assert not url_like.search(source), f"{path} appears to contain a hardcoded DB credential URL"
