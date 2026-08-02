"""Stage 7R.1/7R.1a: the ONE real, persisted repository implementation --
Postgres, using this package's own isolated tables (schema.sql).

Connection string comes from `DATABASE_URL`, an environment variable --
never hardcoded, never logged, and never written to any report or
artifact this module produces. Never imports src/db.py or src/config.py
(the separate GraphRAG POC's own code) -- an independent connection to
the SAME database instance, against this package's own tables only.

The default unit-test suite never depends on this module -- see
`repository.InMemoryRevisionAuthorityRepository` for that.

`transaction()` wraps a REAL Postgres transaction (BEGIN/COMMIT/
ROLLBACK) -- any exception raised inside the `with` block rolls back
every write performed since it opened, giving the exact same
"no partial mutation" guarantee `service.activate_revision`'s multi-step
write relies on, backed by the database engine itself rather than an
in-process snapshot.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator

from sqlalchemy import Connection, Engine, create_engine, text

from ingestion_bench.revision_authority import config
from ingestion_bench.revision_authority.model import (
    AuthorityDecisionEvent,
    AuthorityMetadata,
    AuthorityPeriod,
    RevisionIdentity,
)

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


class RevisionAuthorityRepositoryUnavailable(RuntimeError):
    """Raised when DATABASE_URL is not configured, or the database is not
    reachable. Callers (e.g. the integration test) catch this to skip
    gracefully -- never to silently fall back to a different store."""


def _to_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    raise TypeError(f"expected date, got {type(value)!r}")


def _to_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value
    raise TypeError(f"expected datetime, got {type(value)!r}")


class PostgresRevisionAuthorityRepository:
    """The one real, persisted repository implementation configured for
    Stage 7R.1/7R.1a."""

    def __init__(
        self,
        database_url: str | None = None,
        registry_table: str | None = None,
        period_table: str | None = None,
        event_table: str | None = None,
    ) -> None:
        self._database_url = database_url or config.DATABASE_URL
        if not self._database_url:
            raise RevisionAuthorityRepositoryUnavailable(
                "DATABASE_URL is not set -- copy .env.example to .env and set it, or pass database_url= explicitly"
            )
        self._registry_table = registry_table or config.REVISION_REGISTRY_TABLE
        self._period_table = period_table or config.AUTHORITY_PERIOD_TABLE
        self._event_table = event_table or config.AUTHORITY_EVENT_TABLE
        self._engine: Engine | None = None
        self._schema_ready = False
        self._active_conn: Connection | None = None

    def _ensure_ready(self) -> Engine:
        if self._engine is None:
            try:
                engine = create_engine(self._database_url, future=True)
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
            except Exception as exc:  # noqa: BLE001
                raise RevisionAuthorityRepositoryUnavailable(
                    f"could not connect to the configured database: {type(exc).__name__}: {exc}"
                ) from exc
            self._engine = engine
        if not self._schema_ready:
            self._create_schema_if_needed()
            self._schema_ready = True
        return self._engine

    def _create_schema_if_needed(self) -> None:
        """Applies schema.sql idempotently (CREATE TABLE/INDEX IF NOT
        EXISTS) -- never DROPs, never touches any other table (including
        any Stage 7R.1-era columns already present in an existing
        edib_document_revision_registry table from before this stage's
        period-table split -- no migration framework, those columns
        simply go unused going forward, harmlessly). Comment LINES are
        stripped entirely before splitting on ';' -- splitting first and
        filtering chunks that merely START with '--' is not enough,
        since a '--' comment line can itself contain a literal ';'."""
        assert self._engine is not None
        raw = _SCHEMA_PATH.read_text(encoding="utf-8")
        without_comments = "\n".join(
            line for line in raw.splitlines() if not line.strip().startswith("--")
        )
        statements = [s.strip() for s in without_comments.split(";") if s.strip()]
        with self._engine.connect() as conn:
            for statement in statements:
                conn.execute(text(statement))
            conn.commit()

    @contextmanager
    def _conn_scope(self) -> Iterator[Connection]:
        """Reuses the ACTIVE transaction's connection (never committing
        early) when inside `transaction()`; otherwise opens and commits
        its own short-lived connection -- same per-call-commits-by-default
        pattern as retrieval_baseline/pgvector_store.py."""
        engine = self._ensure_ready()
        if self._active_conn is not None:
            yield self._active_conn
            return
        with engine.connect() as conn:
            yield conn
            conn.commit()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        engine = self._ensure_ready()
        with engine.connect() as conn:
            trans = conn.begin()
            previous = self._active_conn
            self._active_conn = conn
            try:
                yield
                trans.commit()
            except Exception:
                trans.rollback()
                raise
            finally:
                self._active_conn = previous

    def get_identity(self, document_revision_id: str) -> RevisionIdentity | None:
        with self._conn_scope() as conn:
            row = conn.execute(
                text(
                    f"SELECT logical_document_id, document_revision_id, source_document_sha256, "
                    f"version_label, revision_number FROM {self._registry_table} WHERE document_revision_id = :id"
                ),
                {"id": document_revision_id},
            ).mappings().first()
        if row is None:
            return None
        return RevisionIdentity(
            logical_document_id=row["logical_document_id"],
            document_revision_id=row["document_revision_id"],
            source_document_sha256=row["source_document_sha256"],
            version_label=row["version_label"],
            revision_number=row["revision_number"],
        )

    def find_identity_by_components(
        self,
        logical_document_id: str,
        source_document_sha256: str,
        version_label: str | None,
        revision_number: int | None,
    ) -> RevisionIdentity | None:
        with self._conn_scope() as conn:
            row = conn.execute(
                text(
                    f"SELECT logical_document_id, document_revision_id, source_document_sha256, "
                    f"version_label, revision_number FROM {self._registry_table} "
                    "WHERE logical_document_id = :ldid AND source_document_sha256 = :sha "
                    "AND version_label IS NOT DISTINCT FROM :vl AND revision_number IS NOT DISTINCT FROM :rn"
                ),
                {"ldid": logical_document_id, "sha": source_document_sha256, "vl": version_label, "rn": revision_number},
            ).mappings().first()
        if row is None:
            return None
        return RevisionIdentity(
            logical_document_id=row["logical_document_id"],
            document_revision_id=row["document_revision_id"],
            source_document_sha256=row["source_document_sha256"],
            version_label=row["version_label"],
            revision_number=row["revision_number"],
        )

    def save_identity(self, identity: RevisionIdentity) -> None:
        with self._conn_scope() as conn:
            conn.execute(
                text(
                    f"""
                    INSERT INTO {self._registry_table} (
                        document_revision_id, logical_document_id, source_document_sha256,
                        version_label, revision_number
                    ) VALUES (:id, :ldid, :sha, :vl, :rn)
                    ON CONFLICT (document_revision_id) DO NOTHING
                    """
                ),
                {
                    "id": identity.document_revision_id,
                    "ldid": identity.logical_document_id,
                    "sha": identity.source_document_sha256,
                    "vl": identity.version_label,
                    "rn": identity.revision_number,
                },
            )

    def get_metadata(self, document_revision_id: str) -> AuthorityMetadata | None:
        with self._conn_scope() as conn:
            row = conn.execute(
                text(
                    f"SELECT publication_status, approved_at, authority_source, "
                    f"authority_reference, authority_recorded_at, authority_recorded_by "
                    f"FROM {self._registry_table} WHERE document_revision_id = :id"
                ),
                {"id": document_revision_id},
            ).mappings().first()
        if row is None or row["publication_status"] is None:
            return None
        return AuthorityMetadata(
            publication_status=row["publication_status"],
            approved_at=_to_datetime(row["approved_at"]),
            authority_source=row["authority_source"],
            authority_reference=row["authority_reference"],
            authority_recorded_at=_to_datetime(row["authority_recorded_at"]),
            authority_recorded_by=row["authority_recorded_by"],
        )

    def save_metadata(self, document_revision_id: str, metadata: AuthorityMetadata) -> None:
        with self._conn_scope() as conn:
            result = conn.execute(
                text(
                    f"""
                    UPDATE {self._registry_table} SET
                        publication_status = :publication_status,
                        approved_at = :approved_at,
                        authority_source = :authority_source,
                        authority_reference = :authority_reference,
                        authority_recorded_at = :authority_recorded_at,
                        authority_recorded_by = :authority_recorded_by,
                        updated_at = now()
                    WHERE document_revision_id = :id
                    """
                ),
                {
                    "id": document_revision_id,
                    "publication_status": metadata.publication_status,
                    "approved_at": metadata.approved_at,
                    "authority_source": metadata.authority_source,
                    "authority_reference": metadata.authority_reference,
                    "authority_recorded_at": metadata.authority_recorded_at,
                    "authority_recorded_by": metadata.authority_recorded_by,
                },
            )
        if result.rowcount == 0:
            raise ValueError(
                f"save_metadata: no registered revision row for document_revision_id={document_revision_id!r} "
                "-- register_revision() must be called before save_metadata()"
            )

    def list_revisions_for_document(self, logical_document_id: str) -> list[RevisionIdentity]:
        with self._conn_scope() as conn:
            rows = conn.execute(
                text(
                    f"SELECT logical_document_id, document_revision_id, source_document_sha256, "
                    f"version_label, revision_number FROM {self._registry_table} "
                    "WHERE logical_document_id = :ldid ORDER BY document_revision_id ASC"
                ),
                {"ldid": logical_document_id},
            ).mappings()
            return [
                RevisionIdentity(
                    logical_document_id=row["logical_document_id"],
                    document_revision_id=row["document_revision_id"],
                    source_document_sha256=row["source_document_sha256"],
                    version_label=row["version_label"],
                    revision_number=row["revision_number"],
                )
                for row in rows
            ]

    def save_period(self, period: AuthorityPeriod) -> AuthorityPeriod:
        with self._conn_scope() as conn:
            if period.authority_period_id == 0:
                row = conn.execute(
                    text(
                        f"""
                        INSERT INTO {self._period_table} (
                            logical_document_id, document_revision_id, effective_from, effective_to,
                            predecessor_revision_id, opening_event_id, closing_event_id, closure_reason,
                            authority_source, authority_reference, recorded_at, recorded_by
                        ) VALUES (
                            :ldid, :rid, :ef, :et, :pred, :open_ev, :close_ev, :reason,
                            :src, :ref, :rec_at, :rec_by
                        ) RETURNING authority_period_id
                        """
                    ),
                    {
                        "ldid": period.logical_document_id, "rid": period.document_revision_id,
                        "ef": period.effective_from, "et": period.effective_to,
                        "pred": period.predecessor_revision_id, "open_ev": period.opening_event_id,
                        "close_ev": period.closing_event_id, "reason": period.closure_reason,
                        "src": period.authority_source, "ref": period.authority_reference,
                        "rec_at": period.recorded_at, "rec_by": period.recorded_by,
                    },
                ).mappings().first()
                return period.model_copy(update={"authority_period_id": row["authority_period_id"]})

            conn.execute(
                text(
                    f"""
                    UPDATE {self._period_table} SET
                        effective_to = :et, closing_event_id = :close_ev, closure_reason = :reason
                    WHERE authority_period_id = :pid
                    """
                ),
                {
                    "pid": period.authority_period_id, "et": period.effective_to,
                    "close_ev": period.closing_event_id, "reason": period.closure_reason,
                },
            )
            return period

    def list_periods_for_revision(self, document_revision_id: str) -> list[AuthorityPeriod]:
        with self._conn_scope() as conn:
            rows = conn.execute(
                text(f"SELECT * FROM {self._period_table} WHERE document_revision_id = :rid ORDER BY effective_from ASC"),
                {"rid": document_revision_id},
            ).mappings()
            return [self._period_from_row(row) for row in rows]

    def list_periods_for_document(self, logical_document_id: str) -> list[AuthorityPeriod]:
        with self._conn_scope() as conn:
            rows = conn.execute(
                text(
                    f"SELECT * FROM {self._period_table} WHERE logical_document_id = :ldid "
                    "ORDER BY document_revision_id ASC, effective_from ASC"
                ),
                {"ldid": logical_document_id},
            ).mappings()
            return [self._period_from_row(row) for row in rows]

    @staticmethod
    def _period_from_row(row) -> AuthorityPeriod:
        return AuthorityPeriod(
            authority_period_id=row["authority_period_id"],
            logical_document_id=row["logical_document_id"],
            document_revision_id=row["document_revision_id"],
            effective_from=_to_date(row["effective_from"]),
            effective_to=_to_date(row["effective_to"]),
            predecessor_revision_id=row["predecessor_revision_id"],
            opening_event_id=row["opening_event_id"],
            closing_event_id=row["closing_event_id"],
            closure_reason=row["closure_reason"],
            authority_source=row["authority_source"],
            authority_reference=row["authority_reference"],
            recorded_at=_to_datetime(row["recorded_at"]),
            recorded_by=row["recorded_by"],
        )

    def append_event(self, event: AuthorityDecisionEvent) -> AuthorityDecisionEvent:
        with self._conn_scope() as conn:
            row = conn.execute(
                text(
                    f"""
                    INSERT INTO {self._event_table} (
                        event_type, logical_document_id, revision_id, related_revision_id,
                        decision_effective_date, closure_reason,
                        recorded_at, authority_source, authority_reference, recorded_by, detail
                    ) VALUES (
                        :event_type, :logical_document_id, :revision_id, :related_revision_id,
                        :decision_effective_date, :closure_reason,
                        :recorded_at, :authority_source, :authority_reference, :recorded_by, :detail
                    ) RETURNING event_id
                    """
                ),
                {
                    "event_type": event.event_type,
                    "logical_document_id": event.logical_document_id,
                    "revision_id": event.revision_id,
                    "related_revision_id": event.related_revision_id,
                    "decision_effective_date": event.decision_effective_date,
                    "closure_reason": event.closure_reason,
                    "recorded_at": event.recorded_at,
                    "authority_source": event.authority_source,
                    "authority_reference": event.authority_reference,
                    "recorded_by": event.recorded_by,
                    "detail": event.detail,
                },
            ).mappings().first()
        return event.model_copy(update={"event_id": row["event_id"]})

    def list_events(self, logical_document_id: str | None = None) -> list[AuthorityDecisionEvent]:
        with self._conn_scope() as conn:
            if logical_document_id is not None:
                rows = conn.execute(
                    text(f"SELECT * FROM {self._event_table} WHERE logical_document_id = :ldid ORDER BY event_id ASC"),
                    {"ldid": logical_document_id},
                ).mappings()
            else:
                rows = conn.execute(text(f"SELECT * FROM {self._event_table} ORDER BY event_id ASC")).mappings()
            return [
                AuthorityDecisionEvent(
                    event_id=row["event_id"],
                    event_type=row["event_type"],
                    logical_document_id=row["logical_document_id"],
                    revision_id=row["revision_id"],
                    related_revision_id=row["related_revision_id"],
                    decision_effective_date=_to_date(row["decision_effective_date"]),
                    closure_reason=row["closure_reason"],
                    recorded_at=_to_datetime(row["recorded_at"]),
                    authority_source=row["authority_source"],
                    authority_reference=row["authority_reference"],
                    recorded_by=row["recorded_by"],
                    detail=row["detail"],
                )
                for row in rows
            ]
