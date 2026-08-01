"""Stage 7R.1: authority transition service.

Explicit, narrow operations only -- never a generic plug-in framework or
a rule engine. Every mutation appends an append-only audit event.

This service never touches `CanonicalDocument`/`CanonicalChunk`/
`chunk_document()` in any way: it only ever reads a caller-supplied
`RevisionIdentity` (itself just `ingestion_bench.chunking.DocumentRevisionContext`,
reused, never recomputed here from raw chunks) and writes to this
package's own registry tables. Registering a revision, recording a
decision, activating a supersession, or withdrawing a revision never
mutates, deletes, rechunks, or re-embeds any canonical chunk.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from ingestion_bench.revision_authority import resolver
from ingestion_bench.revision_authority.model import (
    AuthorityDecisionEvent,
    AuthorityMetadata,
    PublicationStatus,
    RevisionIdentity,
    compute_document_revision_id,
)
from ingestion_bench.revision_authority.repository import RevisionAuthorityRepository
from ingestion_bench.revision_authority.resolver import QueryIntent, QueryResolutionResult


class RegisterRevisionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity: RevisionIdentity
    is_new_revision: bool
    event: AuthorityDecisionEvent


class RevisionAuthorityService:
    def __init__(self, repository: RevisionAuthorityRepository) -> None:
        self._repository = repository

    def register_revision(
        self,
        *,
        logical_document_id: str,
        source_document_sha256: str,
        version_label: str | None,
        revision_number: int | None,
        authority_source: str,
        authority_reference: str,
        authority_recorded_by: str,
        recorded_at: datetime,
    ) -> RegisterRevisionResult:
        """Exact-duplicate behavior (Stage 7R.1 item 6): document_revision_id
        is ALWAYS `compute_document_revision_id(logical_document_id,
        source_document_sha256, version_label, revision_number)` -- the
        SAME deterministic hash `chunk_document()`'s own
        `DocumentRevisionContext` uses. A second registration with
        identical components always computes the identical id, so
        "reuse the existing document_revision_id" falls out of this
        function doing nothing more than a lookup by that id -- no
        separate content-diffing or duplicate-detection heuristic exists
        anywhere in this method. Never triggers chunking/embedding --
        this service has no dependency on either."""
        document_revision_id = compute_document_revision_id(
            logical_document_id=logical_document_id,
            source_document_sha256=source_document_sha256,
            version_label=version_label,
            revision_number=revision_number,
        )
        existing = self._repository.get_identity(document_revision_id)
        if existing is not None:
            event = self._repository.append_event(
                AuthorityDecisionEvent(
                    event_id=0,
                    event_type="duplicate_registration_attempt",
                    logical_document_id=logical_document_id,
                    revision_id=document_revision_id,
                    recorded_at=recorded_at,
                    authority_source=authority_source,
                    authority_reference=authority_reference,
                    recorded_by=authority_recorded_by,
                    detail=(
                        "exact duplicate registration attempt (same logical_document_id + "
                        "source_document_sha256 + version_label + revision_number) -- reused existing "
                        "document_revision_id, no new revision row created"
                    ),
                )
            )
            return RegisterRevisionResult(identity=existing, is_new_revision=False, event=event)

        identity = RevisionIdentity(
            logical_document_id=logical_document_id,
            document_revision_id=document_revision_id,
            source_document_sha256=source_document_sha256,
            version_label=version_label,
            revision_number=revision_number,
        )
        self._repository.save_identity(identity)
        # New revisions start as an unreviewed draft -- authority is
        # NEVER inferred from registration itself (never upload time,
        # never "this is now current"). A separate, explicit
        # record_authority_decision()/activate_revision() call is always
        # required to grant any authority.
        self._repository.save_metadata(
            document_revision_id,
            AuthorityMetadata(
                publication_status="draft",
                authority_source=authority_source,
                authority_reference=authority_reference,
                authority_recorded_at=recorded_at,
                authority_recorded_by=authority_recorded_by,
            ),
        )
        event = self._repository.append_event(
            AuthorityDecisionEvent(
                event_id=0,
                event_type="revision_registered",
                logical_document_id=logical_document_id,
                revision_id=document_revision_id,
                recorded_at=recorded_at,
                authority_source=authority_source,
                authority_reference=authority_reference,
                recorded_by=authority_recorded_by,
                detail="new revision candidate registered as draft",
            )
        )
        return RegisterRevisionResult(identity=identity, is_new_revision=True, event=event)

    def record_authority_decision(
        self,
        *,
        document_revision_id: str,
        publication_status: PublicationStatus,
        effective_from: date | None = None,
        effective_to: date | None = None,
        approved_at: datetime | None = None,
        authority_source: str,
        authority_reference: str,
        authority_recorded_by: str,
        recorded_at: datetime,
    ) -> AuthorityMetadata:
        """Updates ONE revision's own mutable authority facts. Never
        touches supersession links (`supersedes_revision_id`/
        `superseded_by_revision_id`) -- those are set ONLY by
        `activate_revision`'s atomic transition."""
        current = self._repository.get_metadata(document_revision_id)
        if current is None:
            raise ValueError(f"no registered revision with document_revision_id={document_revision_id!r}")

        updated = AuthorityMetadata(
            publication_status=publication_status,
            approved_at=approved_at,
            effective_from=effective_from,
            effective_to=effective_to,
            supersedes_revision_id=current.supersedes_revision_id,
            superseded_by_revision_id=current.superseded_by_revision_id,
            authority_source=authority_source,
            authority_reference=authority_reference,
            authority_recorded_at=recorded_at,
            authority_recorded_by=authority_recorded_by,
        )
        self._repository.save_metadata(document_revision_id, updated)

        identity = self._repository.get_identity(document_revision_id)
        logical_document_id = identity.logical_document_id if identity is not None else "unknown"
        self._repository.append_event(
            AuthorityDecisionEvent(
                event_id=0,
                event_type="authority_decision_recorded",
                logical_document_id=logical_document_id,
                revision_id=document_revision_id,
                recorded_at=recorded_at,
                authority_source=authority_source,
                authority_reference=authority_reference,
                recorded_by=authority_recorded_by,
                detail=f"publication_status={publication_status!r} effective_from={effective_from} effective_to={effective_to}",
            )
        )
        return updated

    def activate_revision(
        self,
        *,
        new_revision_id: str,
        old_revision_id: str | None,
        effective_from: date,
        authority_source: str,
        authority_reference: str,
        authority_recorded_by: str,
        recorded_at: datetime,
    ) -> None:
        """ONE atomic transition (Stage 7R.1 item 4). `old_revision_id`
        is None only for the very first activation of a logical document
        (nothing to supersede yet). Never mutates, deletes, rechunks, or
        re-embeds any canonical chunk of either revision -- this method
        writes only to this package's own registry tables."""
        new_identity = self._repository.get_identity(new_revision_id)
        if new_identity is None:
            raise ValueError(f"no registered revision with document_revision_id={new_revision_id!r}")

        with self._repository.transaction():
            new_metadata = self._repository.get_metadata(new_revision_id)
            self._repository.save_metadata(
                new_revision_id,
                AuthorityMetadata(
                    publication_status="approved",
                    approved_at=recorded_at,
                    effective_from=effective_from,
                    effective_to=new_metadata.effective_to if new_metadata is not None else None,
                    supersedes_revision_id=old_revision_id,
                    superseded_by_revision_id=new_metadata.superseded_by_revision_id if new_metadata is not None else None,
                    authority_source=authority_source,
                    authority_reference=authority_reference,
                    authority_recorded_at=recorded_at,
                    authority_recorded_by=authority_recorded_by,
                ),
            )

            if old_revision_id is not None:
                old_metadata = self._repository.get_metadata(old_revision_id)
                if old_metadata is None:
                    raise ValueError(f"no registered revision with document_revision_id={old_revision_id!r}")
                self._repository.save_metadata(
                    old_revision_id,
                    AuthorityMetadata(
                        publication_status=old_metadata.publication_status,
                        approved_at=old_metadata.approved_at,
                        effective_from=old_metadata.effective_from,
                        effective_to=effective_from,
                        supersedes_revision_id=old_metadata.supersedes_revision_id,
                        superseded_by_revision_id=new_revision_id,
                        authority_source=authority_source,
                        authority_reference=authority_reference,
                        authority_recorded_at=recorded_at,
                        authority_recorded_by=authority_recorded_by,
                    ),
                )

            self._repository.append_event(
                AuthorityDecisionEvent(
                    event_id=0,
                    event_type="revision_activated",
                    logical_document_id=new_identity.logical_document_id,
                    revision_id=new_revision_id,
                    related_revision_id=old_revision_id,
                    recorded_at=recorded_at,
                    authority_source=authority_source,
                    authority_reference=authority_reference,
                    recorded_by=authority_recorded_by,
                    detail=(
                        f"activated {new_revision_id} effective {effective_from}"
                        + (f", superseding {old_revision_id}" if old_revision_id is not None else " (first effective revision)")
                    ),
                )
            )

    def withdraw_revision(
        self,
        *,
        document_revision_id: str,
        authority_source: str,
        authority_reference: str,
        authority_recorded_by: str,
        recorded_at: datetime,
    ) -> None:
        """Marks a revision withdrawn. Never auto-selects a replacement
        -- a logical document may legitimately have NO effective
        revision after this until a separate activate_revision() call
        (Stage 7R.1 scenario K)."""
        current = self._repository.get_metadata(document_revision_id)
        if current is None:
            raise ValueError(f"no registered revision with document_revision_id={document_revision_id!r}")
        identity = self._repository.get_identity(document_revision_id)
        if identity is None:
            raise ValueError(f"no registered revision with document_revision_id={document_revision_id!r}")

        updated = AuthorityMetadata(
            publication_status="withdrawn",
            approved_at=current.approved_at,
            effective_from=current.effective_from,
            effective_to=current.effective_to,
            supersedes_revision_id=current.supersedes_revision_id,
            superseded_by_revision_id=current.superseded_by_revision_id,
            authority_source=authority_source,
            authority_reference=authority_reference,
            authority_recorded_at=recorded_at,
            authority_recorded_by=authority_recorded_by,
        )
        self._repository.save_metadata(document_revision_id, updated)
        self._repository.append_event(
            AuthorityDecisionEvent(
                event_id=0,
                event_type="revision_withdrawn",
                logical_document_id=identity.logical_document_id,
                revision_id=document_revision_id,
                recorded_at=recorded_at,
                authority_source=authority_source,
                authority_reference=authority_reference,
                recorded_by=authority_recorded_by,
                detail="revision withdrawn -- no replacement selected automatically",
            )
        )

    def resolve_query_scope(
        self,
        *,
        logical_document_id: str,
        query_intent: QueryIntent,
        as_of_date: date,
        requested_revision_ids: list[str] | None = None,
    ) -> QueryResolutionResult:
        """Thin delegation to the pure resolver -- `as_of_date` is still
        always required and explicit here too; this service never
        defaults it to today (Stage 7R.1 item 5)."""
        return resolver.resolve_query_scope(
            self._repository, logical_document_id, query_intent, as_of_date, requested_revision_ids
        )
