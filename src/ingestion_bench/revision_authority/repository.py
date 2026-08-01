"""Stage 7R.1: repository protocol + deterministic in-memory implementation.

The in-memory repository is what the DEFAULT unit-test suite uses --
never requires Postgres. It also deliberately exposes low-level
`save_identity`/`save_metadata` writes (not just the higher-level
business operations in `service.py`) so tests can construct a
deliberately INCONSISTENT registry state (e.g. two overlapping
"effective" revisions, a broken supersession link) to prove the resolver
actually catches it -- a real corrupted-data scenario, not just "the
service never does that".
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Protocol

from ingestion_bench.revision_authority.model import AuthorityDecisionEvent, AuthorityMetadata, RevisionIdentity


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

    def append_event(self, event: AuthorityDecisionEvent) -> AuthorityDecisionEvent:
        """Assigns event_id and stores it. There is deliberately no
        update/delete method for events anywhere on this Protocol --
        append-only by API-surface absence, not just by convention."""
        ...

    def list_events(self, logical_document_id: str | None = None) -> list[AuthorityDecisionEvent]: ...

    def transaction(self) -> Iterator[None]:
        """A context manager so callers (service.py's atomic
        activate_revision) can group multiple writes -- a real
        transaction for the Postgres implementation, a no-op for the
        in-memory one (a single process has no partial-write visibility
        to protect against here)."""
        ...


class InMemoryRevisionAuthorityRepository:
    """Deterministic, in-process implementation -- the ONLY repository
    the default unit-test suite depends on."""

    def __init__(self) -> None:
        self._identities: dict[str, RevisionIdentity] = {}
        self._metadata: dict[str, AuthorityMetadata] = {}
        self._events: list[AuthorityDecisionEvent] = []
        self._next_event_id = 1

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
        yield
