"""Stage 7R.1/7R.1a: repository protocol + deterministic in-memory
implementation.

The in-memory repository is what the DEFAULT unit-test suite uses --
never requires Postgres. It also deliberately exposes low-level
`save_identity`/`save_metadata`/`save_period` writes (not just the
higher-level business operations in `service.py`) so tests can construct
a deliberately INCONSISTENT registry state to prove the resolver
actually catches it.

Stage 7R.1a: `transaction()` on the in-memory repository now performs a
REAL snapshot-and-restore around its body -- any exception raised inside
the `with` block (whether from mid-write validation or a deliberately
injected fault) leaves the repository in EXACTLY its pre-transaction
state, never a partially-applied one. This is what
`activate_revision`'s multi-step write (new metadata, new period, old
period close, event append) relies on for atomicity in-process; the
Postgres implementation gets the same guarantee from a real database
transaction instead.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Protocol

from ingestion_bench.revision_authority.model import AuthorityDecisionEvent, AuthorityMetadata, AuthorityPeriod, RevisionIdentity


class RevisionAuthorityRepository(Protocol):
    def get_identity(self, document_revision_id: str) -> RevisionIdentity | None: ...

    def find_identity_by_components(
        self,
        logical_document_id: str,
        source_document_sha256: str,
        version_label: str | None,
        revision_number: int | None,
    ) -> RevisionIdentity | None: ...

    def save_identity(self, identity: RevisionIdentity) -> None: ...

    def get_metadata(self, document_revision_id: str) -> AuthorityMetadata | None: ...

    def save_metadata(self, document_revision_id: str, metadata: AuthorityMetadata) -> None: ...

    def list_revisions_for_document(self, logical_document_id: str) -> list[RevisionIdentity]: ...

    def save_period(self, period: AuthorityPeriod) -> AuthorityPeriod:
        """Upserts by `authority_period_id` -- a NEW period (id==0) is
        assigned a real id and inserted; an EXISTING period (id already
        assigned) is replaced wholesale (the only legitimate use: CLOSING
        an already-open period by re-saving it with effective_to/
        closure_reason/closing_event_id populated -- never used to alter
        a DIFFERENT, already-closed historical period)."""
        ...

    def list_periods_for_revision(self, document_revision_id: str) -> list[AuthorityPeriod]: ...

    def list_periods_for_document(self, logical_document_id: str) -> list[AuthorityPeriod]: ...

    def append_event(self, event: AuthorityDecisionEvent) -> AuthorityDecisionEvent:
        """Assigns event_id and stores it. There is deliberately no
        update/delete method for events anywhere on this Protocol --
        append-only by API-surface absence, not just by convention."""
        ...

    def list_events(self, logical_document_id: str | None = None) -> list[AuthorityDecisionEvent]: ...

    def transaction(self) -> Iterator[None]:
        """A context manager grouping multiple writes atomically -- a
        real transaction for the Postgres implementation; for the
        in-memory one, a snapshot-and-restore around the body so an
        exception raised anywhere inside leaves NO partial mutation."""
        ...


class InMemoryRevisionAuthorityRepository:
    """Deterministic, in-process implementation -- the ONLY repository
    the default unit-test suite depends on."""

    def __init__(self) -> None:
        self._identities: dict[str, RevisionIdentity] = {}
        self._metadata: dict[str, AuthorityMetadata] = {}
        self._periods: dict[int, AuthorityPeriod] = {}
        self._events: list[AuthorityDecisionEvent] = []
        self._next_event_id = 1
        self._next_period_id = 1

    def get_identity(self, document_revision_id: str) -> RevisionIdentity | None:
        return self._identities.get(document_revision_id)

    def find_identity_by_components(
        self,
        logical_document_id: str,
        source_document_sha256: str,
        version_label: str | None,
        revision_number: int | None,
    ) -> RevisionIdentity | None:
        for identity in self._identities.values():
            if (
                identity.logical_document_id == logical_document_id
                and identity.source_document_sha256 == source_document_sha256
                and identity.version_label == version_label
                and identity.revision_number == revision_number
            ):
                return identity
        return None

    def save_identity(self, identity: RevisionIdentity) -> None:
        self._identities[identity.document_revision_id] = identity

    def get_metadata(self, document_revision_id: str) -> AuthorityMetadata | None:
        return self._metadata.get(document_revision_id)

    def save_metadata(self, document_revision_id: str, metadata: AuthorityMetadata) -> None:
        self._metadata[document_revision_id] = metadata

    def list_revisions_for_document(self, logical_document_id: str) -> list[RevisionIdentity]:
        return sorted(
            (i for i in self._identities.values() if i.logical_document_id == logical_document_id),
            key=lambda i: i.document_revision_id,
        )

    def save_period(self, period: AuthorityPeriod) -> AuthorityPeriod:
        if period.authority_period_id == 0:
            stamped = period.model_copy(update={"authority_period_id": self._next_period_id})
            self._next_period_id += 1
        else:
            stamped = period
        self._periods[stamped.authority_period_id] = stamped
        return stamped

    def list_periods_for_revision(self, document_revision_id: str) -> list[AuthorityPeriod]:
        return sorted(
            (p for p in self._periods.values() if p.document_revision_id == document_revision_id),
            key=lambda p: p.effective_from,
        )

    def list_periods_for_document(self, logical_document_id: str) -> list[AuthorityPeriod]:
        return sorted(
            (p for p in self._periods.values() if p.logical_document_id == logical_document_id),
            key=lambda p: (p.document_revision_id, p.effective_from),
        )

    def append_event(self, event: AuthorityDecisionEvent) -> AuthorityDecisionEvent:
        stamped = event.model_copy(update={"event_id": self._next_event_id})
        self._next_event_id += 1
        self._events.append(stamped)
        return stamped

    def list_events(self, logical_document_id: str | None = None) -> list[AuthorityDecisionEvent]:
        events = list(self._events)
        if logical_document_id is not None:
            events = [e for e in events if e.logical_document_id == logical_document_id]
        return events

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Real snapshot-and-restore: every container this repository
        owns is shallow-copied before the body runs. Values inside
        (pydantic model instances) are never mutated in place anywhere
        in this class -- every write REPLACES a dict entry wholesale --
        so restoring the shallow-copied container references is a
        complete, correct undo of every write performed inside the
        `with` block, regardless of where an exception was raised."""
        identities_snapshot = dict(self._identities)
        metadata_snapshot = dict(self._metadata)
        periods_snapshot = dict(self._periods)
        events_snapshot = list(self._events)
        next_event_id_snapshot = self._next_event_id
        next_period_id_snapshot = self._next_period_id
        try:
            yield
        except Exception:
            self._identities = identities_snapshot
            self._metadata = metadata_snapshot
            self._periods = periods_snapshot
            self._events = events_snapshot
            self._next_event_id = next_event_id_snapshot
            self._next_period_id = next_period_id_snapshot
            raise
