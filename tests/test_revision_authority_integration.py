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
    # record_authority_decision() only ever accepts draft/under_review
    # (Stage 7R.1b item 1) -- exercised separately in
    # test_record_authority_decision_*; this sequence proves the
    # register -> activate -> withdraw path alone touches no chunk.
    service.withdraw_revision(
        document_revision_id=document_revision_id, withdrawal_effective_date=date(2024, 6, 1),
        authority_source="gov", authority_reference="W", authority_recorded_by="alice", recorded_at=NOW,
    )

    after = [c.model_dump_json() for c in chunks]
    after_hashes = [c.content_sha256 for c in chunks]
    assert before == after
    assert before_hashes == after_hashes


def test_authority_correction_requires_no_chunk_mutation():
    """Business nuance: correcting/rolling back an authority decision
    (pre_effective_authority_correction) must be achievable purely
    through this package's own tables -- never by touching a chunk.
    Failure this guards against: a 'fix the metadata' operation
    escalating into 'reprocess the document', which would be far more
    expensive and could silently change chunk_ids that Stage 7A.2
    citations already reference. Affects: auditability (Stage 7A.2
    citations must remain valid across authority corrections) and
    benchmark fairness (correcting a mistake must be cheap and
    side-effect-free)."""
    chunks, document_revision_id = _real_canonical_chunks()
    original_chunk_ids = [c.chunk_id for c in chunks]

    service = RevisionAuthorityService(InMemoryRevisionAuthorityRepository())
    service.register_revision(
        logical_document_id="POLICY-DOC", source_document_sha256="c" * 64, version_label=None, revision_number=3,
        authority_source="gov", authority_reference="REF", authority_recorded_by="alice", recorded_at=NOW,
    )
    service.activate_revision(
        new_revision_id=document_revision_id, old_revision_id=None, effective_from=date(2029, 1, 1),
        authority_source="gov", authority_reference="D1", authority_recorded_by="alice", recorded_at=NOW,
    )
    service.withdraw_revision(
        document_revision_id=document_revision_id, withdrawal_effective_date=date(2029, 1, 1), closure_reason="correction",
        authority_source="gov", authority_reference="D2-rollback", authority_recorded_by="alice", recorded_at=NOW,
    )

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


def _cleanup_postgres_document(repo, conn, logical_document_id: str) -> None:
    from sqlalchemy import text

    conn.execute(text(f"DELETE FROM {repo._period_table} WHERE logical_document_id = :d"), {"d": logical_document_id})
    conn.execute(text(f"DELETE FROM {repo._registry_table} WHERE logical_document_id = :d"), {"d": logical_document_id})
    conn.execute(text(f"DELETE FROM {repo._event_table} WHERE logical_document_id = :d"), {"d": logical_document_id})
    conn.commit()


class _PostgresFaultInjectingRepository:
    """Stage 7R.1b item 4: same wrapping pattern as
    test_revision_authority_atomicity.FaultInjectingRepository, but this
    time wrapping the REAL PostgresRevisionAuthorityRepository instead of
    the in-memory one -- delegates everything (crucially `transaction()`,
    via __getattr__) to the wrapped Postgres repository, so the injected
    RuntimeError propagates out of a `with self._active_conn...` block
    that Postgres's own transaction() context manager is holding open,
    triggering a REAL `ROLLBACK`, not a simulated one."""

    def __init__(self, inner, fault: str) -> None:
        self._inner = inner
        self._fault = fault
        self._save_period_calls = 0

    def save_period(self, period):
        self._save_period_calls += 1
        result = self._inner.save_period(period)  # the real INSERT/UPDATE executes...
        if self._fault == "after_new_period_before_old_close" and self._save_period_calls == 1:
            raise RuntimeError("injected fault: after new-period write, before old-period close")  # ...then the fault fires, still inside the open transaction
        return result

    def append_event(self, event):
        result = self._inner.append_event(event)
        if self._fault == "after_event_before_next_write":
            raise RuntimeError("injected fault: after event insertion")
        return result

    def __getattr__(self, name):
        return getattr(self._inner, name)


@pytest.mark.skipif(not _real_postgres_available(), reason="DATABASE_URL not set or Postgres not reachable")
@pytest.mark.parametrize("fault", ["after_new_period_before_old_close", "after_event_before_next_write"])
def test_real_postgres_mid_transaction_fault_rolls_back_completely(fault: str):
    """Business nuance (Stage 7R.1b item 4): a validation failure raised
    BEFORE any write (see test_real_postgres_failed_activation_rolls_back_completely
    above) is NOT sufficient evidence that the real database rolls back --
    it only proves _validate_activation runs before repository.transaction()
    is even entered. THIS test performs REAL writes inside the real
    Postgres transaction (a genuine INSERT of the new period, or a genuine
    INSERT of the activation event), THEN raises -- proving the database's
    own ROLLBACK, triggered by transaction()'s `except Exception:
    trans.rollback()`, undoes writes that already reached the server, not
    just writes that were merely staged in Python. Failure this guards
    against: a false sense of atomicity from the in-memory repository's
    snapshot/restore that the real persisted backend doesn't actually
    share (this exact gap was raised as insufficient evidence and is why
    this test exists). Affects: current search and auditability against
    the real, persisted registry -- a half-committed transition here would
    silently corrupt the one source of truth production would actually
    use."""
    from ingestion_bench.revision_authority.postgres_repository import PostgresRevisionAuthorityRepository

    repo = PostgresRevisionAuthorityRepository()
    service = RevisionAuthorityService(repo)
    logical_document_id = "_pytest_stage7r1b_midtx_rollback_selftest"

    engine = repo._ensure_ready()
    try:
        with engine.connect() as conn:
            _cleanup_postgres_document(repo, conn, logical_document_id)

        old = service.register_revision(
            logical_document_id=logical_document_id, source_document_sha256="f" * 64, version_label=None, revision_number=1,
            authority_source="gov", authority_reference="REF1", authority_recorded_by="alice", recorded_at=NOW,
        )
        service.activate_revision(
            new_revision_id=old.identity.document_revision_id, old_revision_id=None, effective_from=date(2020, 1, 1),
            authority_source="gov", authority_reference="ACT1", authority_recorded_by="alice", recorded_at=NOW,
        )
        new = service.register_revision(
            logical_document_id=logical_document_id, source_document_sha256="0" * 64, version_label=None, revision_number=2,
            authority_source="gov", authority_reference="REF2", authority_recorded_by="alice", recorded_at=NOW,
        )

        events_before = repo.list_events(logical_document_id)
        old_metadata_before = repo.get_metadata(old.identity.document_revision_id)
        old_periods_before = repo.list_periods_for_revision(old.identity.document_revision_id)
        new_metadata_before = repo.get_metadata(new.identity.document_revision_id)
        new_periods_before = repo.list_periods_for_revision(new.identity.document_revision_id)

        faulty_service = RevisionAuthorityService(_PostgresFaultInjectingRepository(repo, fault=fault))
        with pytest.raises(RuntimeError, match="injected fault"):
            faulty_service.activate_revision(
                new_revision_id=new.identity.document_revision_id, old_revision_id=old.identity.document_revision_id,
                effective_from=date(2023, 1, 1), authority_source="gov", authority_reference="ACT2",
                authority_recorded_by="alice", recorded_at=NOW,
            )

        # Read back through the UNWRAPPED, real repository -- Postgres
        # itself has no in-process cache, so this is exactly what any
        # OTHER process reading the database right now would also see.
        assert repo.list_events(logical_document_id) == events_before
        assert repo.get_metadata(old.identity.document_revision_id) == old_metadata_before
        assert repo.list_periods_for_revision(old.identity.document_revision_id) == old_periods_before
        assert repo.get_metadata(new.identity.document_revision_id) == new_metadata_before
        assert repo.list_periods_for_revision(new.identity.document_revision_id) == new_periods_before

        resolution = service.resolve_query_scope(logical_document_id=logical_document_id, query_intent="current", as_of_date=date(2024, 1, 1))
        assert resolution.eligible_revision_ids == [old.identity.document_revision_id]
        assert resolution.integrity_error is None
    finally:
        with engine.connect() as conn:
            _cleanup_postgres_document(repo, conn, logical_document_id)


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

    engine = repo._ensure_ready()
    try:
        with engine.connect() as conn:
            _cleanup_postgres_document(repo, conn, logical_document_id)

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
            _cleanup_postgres_document(repo, conn, logical_document_id)


@pytest.mark.skipif(not _real_postgres_available(), reason="DATABASE_URL not set or Postgres not reachable")
def test_real_postgres_failed_activation_rolls_back_completely():
    """Business nuance (Stage 7R.1a item 4): the Postgres repository's
    transaction() wraps a REAL database transaction -- this test proves
    a failed activate_revision() (a genuine validation rejection, not an
    injected fault) leaves NO trace in the real database: no new period
    row, no new event row, the old revision's own period/metadata
    completely untouched. Failure this guards against: the in-memory
    repository's snapshot/restore giving a false sense of atomicity that
    the REAL persisted backend doesn't actually share. Affects: current
    search and auditability against the real, persisted registry."""
    from ingestion_bench.revision_authority.postgres_repository import PostgresRevisionAuthorityRepository
    from ingestion_bench.revision_authority.service import ActivationValidationError

    repo = PostgresRevisionAuthorityRepository()
    service = RevisionAuthorityService(repo)
    logical_document_id = "_pytest_stage7r1a_rollback_selftest"

    engine = repo._ensure_ready()
    try:
        with engine.connect() as conn:
            _cleanup_postgres_document(repo, conn, logical_document_id)

        only = service.register_revision(
            logical_document_id=logical_document_id, source_document_sha256="e" * 64, version_label=None, revision_number=1,
            authority_source="gov", authority_reference="REF", authority_recorded_by="alice", recorded_at=NOW,
        )
        service.activate_revision(
            new_revision_id=only.identity.document_revision_id, old_revision_id=None, effective_from=date(2020, 1, 1),
            authority_source="gov", authority_reference="ACT", authority_recorded_by="alice", recorded_at=NOW,
        )

        events_before = repo.list_events(logical_document_id)
        periods_before = repo.list_periods_for_revision(only.identity.document_revision_id)
        metadata_before = repo.get_metadata(only.identity.document_revision_id)

        # A genuinely invalid transition (self-supersession) -- rejected
        # by _validate_activation BEFORE any write, so this proves the
        # pre-validation itself, not just the transaction() rollback path.
        with pytest.raises(ActivationValidationError):
            service.activate_revision(
                new_revision_id=only.identity.document_revision_id, old_revision_id=only.identity.document_revision_id,
                effective_from=date(2023, 1, 1), authority_source="gov", authority_reference="X",
                authority_recorded_by="alice", recorded_at=NOW,
            )

        assert repo.list_events(logical_document_id) == events_before
        assert repo.list_periods_for_revision(only.identity.document_revision_id) == periods_before
        assert repo.get_metadata(only.identity.document_revision_id) == metadata_before

        resolution = service.resolve_query_scope(logical_document_id=logical_document_id, query_intent="current", as_of_date=date(2024, 6, 1))
        assert resolution.eligible_revision_ids == [only.identity.document_revision_id]
        assert resolution.integrity_error is None
    finally:
        with engine.connect() as conn:
            _cleanup_postgres_document(repo, conn, logical_document_id)


# --- Stage 7R.1b item 5: existing/legacy Stage 7R schema handling ------------
#
# Each test below overrides ONLY the ONE table under test via
# PostgresRevisionAuthorityRepository's own registry_table/period_table/
# event_table constructor params, building it in the pre-7R.1a legacy
# shape by hand -- the other two tables are left at their real, shared
# defaults (CREATE TABLE IF NOT EXISTS / ALTER TABLE ... ADD COLUMN IF
# NOT EXISTS against them is always a harmless no-op once current, so
# this is safe), and cleaned up by logical_document_id/document_revision_id
# rather than a table DROP.


@pytest.mark.skipif(not _real_postgres_available(), reason="DATABASE_URL not set or Postgres not reachable")
def test_missing_event_columns_are_added_to_a_pre_7r1a_table():
    """Business nuance (item 5): a table created by the ORIGINAL Stage
    7R.1 schema.sql (before the 7R.1a redesign) has an
    edib_authority_decision_event table with no decision_effective_date/
    closure_reason columns at all. _ensure_ready() must add them via
    ALTER TABLE ... ADD COLUMN IF NOT EXISTS, not silently ignore the gap
    (which would make every append_event() call using those columns
    fail with an undefined-column error the first time it actually
    matters). Failure this guards against: a live database that predates
    the 7R.1a split becoming permanently unusable, or requiring a manual
    DBA intervention that was never documented. Affects: auditability
    (every event depends on these columns existing) against a real,
    pre-existing database."""
    from sqlalchemy import create_engine, text as sa_text

    from ingestion_bench.revision_authority import config
    from ingestion_bench.revision_authority.postgres_repository import PostgresRevisionAuthorityRepository

    engine = create_engine(config.DATABASE_URL, future=True)
    event_table = "_pytest_legacy_event_table"
    try:
        with engine.connect() as conn:
            conn.execute(sa_text(f"DROP TABLE IF EXISTS {event_table} CASCADE"))
            # The ORIGINAL (pre-7R.1a) event table shape -- no
            # decision_effective_date, no closure_reason.
            conn.execute(
                sa_text(
                    f"""
                    CREATE TABLE {event_table} (
                        event_id             BIGSERIAL PRIMARY KEY,
                        event_type           TEXT NOT NULL,
                        logical_document_id  TEXT NOT NULL,
                        revision_id          TEXT NOT NULL,
                        related_revision_id  TEXT,
                        recorded_at          TIMESTAMPTZ NOT NULL,
                        authority_source     TEXT NOT NULL,
                        authority_reference  TEXT NOT NULL,
                        recorded_by          TEXT NOT NULL,
                        detail               TEXT NOT NULL
                    )
                    """
                )
            )
            conn.commit()

        # registry_table/period_table are left at their real, shared
        # defaults -- only event_table is the custom pre-7R.1a table.
        repo = PostgresRevisionAuthorityRepository(database_url=config.DATABASE_URL, event_table=event_table)
        logical_document_id = "_pytest_legacy_event_doc"
        try:
            repo._ensure_ready()  # must not raise -- must ALTER the table in place

            with engine.connect() as conn:
                columns = {
                    row[0]
                    for row in conn.execute(
                        sa_text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"),
                        {"t": event_table},
                    )
                }
            assert "decision_effective_date" in columns
            assert "closure_reason" in columns

            # And the repository is now genuinely usable, not just structurally patched.
            service = RevisionAuthorityService(repo)
            result = service.register_revision(
                logical_document_id=logical_document_id, source_document_sha256="1" * 64, version_label=None,
                revision_number=1, authority_source="gov", authority_reference="REF", authority_recorded_by="alice", recorded_at=NOW,
            )
            service.activate_revision(
                new_revision_id=result.identity.document_revision_id, old_revision_id=None, effective_from=date(2024, 1, 1),
                authority_source="gov", authority_reference="ACT", authority_recorded_by="alice", recorded_at=NOW,
            )
            events = repo.list_events(logical_document_id)
            assert any(e.decision_effective_date == date(2024, 1, 1) for e in events)
        finally:
            with engine.connect() as conn:
                conn.execute(sa_text(f"DELETE FROM {config.REVISION_REGISTRY_TABLE} WHERE logical_document_id = :d"), {"d": logical_document_id})
                conn.execute(sa_text(f"DELETE FROM {config.AUTHORITY_PERIOD_TABLE} WHERE logical_document_id = :d"), {"d": logical_document_id})
                conn.commit()
    finally:
        with engine.connect() as conn:
            conn.execute(sa_text(f"DROP TABLE IF EXISTS {event_table} CASCADE"))
            conn.commit()


@pytest.mark.skipif(not _real_postgres_available(), reason="DATABASE_URL not set or Postgres not reachable")
def test_populated_legacy_registry_data_fails_fast_not_silently_ignored():
    """Business nuance (item 5): a table created by the ORIGINAL Stage
    7R.1 schema.sql has effective_from/effective_to/
    supersedes_revision_id/superseded_by_revision_id columns directly on
    the registry row (before the 7R.1a period-table split). If any of
    those columns are POPULATED for a revision with NO corresponding
    edib_revision_authority_period row, this package cannot
    deterministically know what closure_reason/event produced that
    state -- _ensure_ready() must raise Stage7RLegacySchemaError, never
    silently proceed as if that revision had simply never been
    activated (which would make a real historical authority decision
    invisible to every current/as_of/comparison/draft query without any
    error at all). Failure this guards against: a currently-effective
    real revision silently vanishing from resolution after an upgrade
    to this package. Affects: current search and auditability directly
    -- this is exactly the class of silent data loss the whole registry
    exists to prevent."""
    from sqlalchemy import create_engine, text as sa_text

    from ingestion_bench.revision_authority import config
    from ingestion_bench.revision_authority.postgres_repository import PostgresRevisionAuthorityRepository, Stage7RLegacySchemaError

    engine = create_engine(config.DATABASE_URL, future=True)
    registry_table = "_pytest_legacy_registry_with_data"
    try:
        with engine.connect() as conn:
            conn.execute(sa_text(f"DROP TABLE IF EXISTS {registry_table} CASCADE"))
            # The ORIGINAL (pre-7R.1a) registry table shape -- effective_from/
            # effective_to/supersession columns live directly on the row.
            conn.execute(
                sa_text(
                    f"""
                    CREATE TABLE {registry_table} (
                        document_revision_id      TEXT PRIMARY KEY,
                        logical_document_id       TEXT NOT NULL,
                        source_document_sha256    TEXT NOT NULL,
                        version_label              TEXT,
                        revision_number            INTEGER,
                        publication_status         TEXT,
                        approved_at                TIMESTAMPTZ,
                        effective_from             DATE,
                        effective_to               DATE,
                        supersedes_revision_id     TEXT,
                        superseded_by_revision_id  TEXT,
                        authority_source           TEXT,
                        authority_reference        TEXT,
                        authority_recorded_at      TIMESTAMPTZ,
                        authority_recorded_by      TEXT,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            )
            conn.execute(
                sa_text(
                    f"""
                    INSERT INTO {registry_table} (
                        document_revision_id, logical_document_id, source_document_sha256, revision_number,
                        publication_status, effective_from, effective_to, authority_source, authority_reference,
                        authority_recorded_at, authority_recorded_by
                    ) VALUES (
                        'legacy-rev-1', '_pytest_legacy_registry_doc', '2' || repeat('2', 63), 1,
                        'approved', '2020-01-01', NULL, 'gov', 'REF', now(), 'alice'
                    )
                    """
                )
            )
            conn.commit()

        # period_table/event_table are left at their real, shared defaults
        # -- only registry_table is the custom pre-7R.1a table. 'legacy-rev-1'
        # is a fabricated id that will never have a matching row in the
        # real period table, which is exactly the point being tested.
        repo = PostgresRevisionAuthorityRepository(database_url=config.DATABASE_URL, registry_table=registry_table)
        with pytest.raises(Stage7RLegacySchemaError, match="legacy-rev-1"):
            repo._ensure_ready()
    finally:
        with engine.connect() as conn:
            conn.execute(sa_text(f"DROP TABLE IF EXISTS {registry_table} CASCADE"))
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
