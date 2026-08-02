"""Stage 7R.1/7R.1a: authority transition service.

Explicit, narrow operations only -- never a generic plug-in framework or
a rule engine. Every mutation appends an append-only audit event.

This service never touches `CanonicalDocument`/`CanonicalChunk`/
`chunk_document()` in any way: it only ever reads a caller-supplied
`RevisionIdentity` (itself just `ingestion_bench.chunking.DocumentRevisionContext`,
reused, never recomputed here from raw chunks) and writes to this
package's own registry/period/event tables. Registering a revision,
recording a decision, activating/reinstating a period, or withdrawing a
revision never mutates, deletes, rechunks, or re-embeds any canonical
chunk.

Stage 7R.1a: `activate_revision`/`reinstate_revision` now run FULL
structural validation (existence, same logical document, no
self-supersession, exactly one open period to close, no period overlap,
valid transition date) BEFORE performing any write -- a failed
validation raises before the repository's `transaction()` context is
even entered, so it is structurally impossible for a failed activation
to leave a partial mutation or an orphaned event.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from pydantic import BaseModel, ConfigDict

from ingestion_bench.revision_authority import resolver
from ingestion_bench.revision_authority.model import (
    AuthorityDecisionEvent,
    AuthorityMetadata,
    AuthorityPeriod,
    ClosureReason,
    PublicationStatus,
    RevisionIdentity,
    compute_document_revision_id,
    intervals_overlap,
    validate_own_periods_non_overlapping,
)
from ingestion_bench.revision_authority.repository import RevisionAuthorityRepository
from ingestion_bench.revision_authority.resolver import QueryIntent, QueryResolutionResult


class RegisterRevisionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity: RevisionIdentity
    is_new_revision: bool
    event: AuthorityDecisionEvent


class ActivationValidationError(ValueError):
    """Raised by activate_revision()/reinstate_revision()'s
    pre-validation. ALWAYS raised before any repository write -- see
    `RevisionAuthorityService._validate_activation`."""


class RevisionAuthorityService:
    def __init__(self, repository: RevisionAuthorityRepository) -> None:
        self._repository = repository

    # --- registration ---------------------------------------------------

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
        """Exact-duplicate behavior: document_revision_id is ALWAYS
        `compute_document_revision_id(...)` -- the SAME deterministic
        hash `chunk_document()`'s own `DocumentRevisionContext` uses. A
        second registration with identical components always computes
        the identical id, so "reuse the existing document_revision_id"
        falls out of this function doing nothing more than a lookup by
        that id. Never triggers chunking/embedding -- this service has
        no dependency on either."""
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
        # New revisions start as an unreviewed draft, with NO authority
        # period -- authority is NEVER inferred from registration itself.
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

    # --- pure status changes (never touch periods) ----------------------

    def record_authority_decision(
        self,
        *,
        document_revision_id: str,
        publication_status: PublicationStatus,
        approved_at: datetime | None = None,
        authority_source: str,
        authority_reference: str,
        authority_recorded_by: str,
        recorded_at: datetime,
    ) -> AuthorityMetadata:
        """A pure GOVERNANCE-status change (e.g. draft -> under_review) --
        NEVER schedules, opens, or retracts an authority period. Stage
        7R.1a: AuthorityMetadata carries no effective dates at all;
        scheduling an effective window (even a future one) always goes
        through `activate_revision`/`reinstate_revision`, and retracting
        one always goes through `withdraw_revision` -- there is exactly
        one authoritative path to any effective interval, never two."""
        current = self._repository.get_metadata(document_revision_id)
        if current is None:
            raise ValueError(f"no registered revision with document_revision_id={document_revision_id!r}")

        updated = AuthorityMetadata(
            publication_status=publication_status,
            approved_at=approved_at,
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
                detail=f"publication_status={publication_status!r}",
            )
        )
        return updated

    # --- activation / reinstatement (period-opening transitions) --------

    def _validate_activation(
        self, new_revision_id: str, old_revision_id: str | None, effective_from: date
    ) -> tuple[RevisionIdentity, AuthorityPeriod | None]:
        """Every structural check happens here, BEFORE any write. Raises
        ActivationValidationError (never a bare AssertionError/KeyError)
        with a specific, actionable message on any failure."""
        new_identity = self._repository.get_identity(new_revision_id)
        if new_identity is None:
            raise ActivationValidationError(f"new revision {new_revision_id!r} is not registered")

        old_open_period: AuthorityPeriod | None = None
        if old_revision_id is not None:
            if old_revision_id == new_revision_id:
                raise ActivationValidationError(
                    f"revision {new_revision_id!r} cannot supersede itself (old_revision_id == new_revision_id)"
                )
            old_identity = self._repository.get_identity(old_revision_id)
            if old_identity is None:
                raise ActivationValidationError(f"old revision {old_revision_id!r} is not registered")
            if old_identity.logical_document_id != new_identity.logical_document_id:
                raise ActivationValidationError(
                    f"cannot activate {new_revision_id!r} (logical_document_id={new_identity.logical_document_id!r}) "
                    f"to supersede {old_revision_id!r} (logical_document_id={old_identity.logical_document_id!r}) "
                    "-- a revision may only be superseded by a revision of the SAME logical document"
                )
            old_open_periods = [p for p in self._repository.list_periods_for_revision(old_revision_id) if p.is_open]
            if len(old_open_periods) != 1:
                raise ActivationValidationError(
                    f"old revision {old_revision_id!r} has {len(old_open_periods)} open authority period(s) "
                    "(expected exactly 1 to close)"
                )
            old_open_period = old_open_periods[0]
            if effective_from < old_open_period.effective_from:
                raise ActivationValidationError(
                    f"transition date {effective_from} is before old revision {old_revision_id!r}'s own "
                    f"period start {old_open_period.effective_from}"
                )

        # Overlap validation: the new [effective_from, None) period must
        # not conflict with ANY other revision's period of the SAME
        # logical document (excluding the one being closed as part of
        # THIS same transition) or with the new revision's OWN prior
        # periods (a reinstatement must not double-book a window it
        # already held).
        document_periods = self._repository.list_periods_for_document(new_identity.logical_document_id)
        old_open_period_id = old_open_period.authority_period_id if old_open_period is not None else None
        for period in document_periods:
            if period.document_revision_id == old_revision_id and period.authority_period_id == old_open_period_id:
                continue  # being closed as part of this same transition
            if period.document_revision_id == new_revision_id:
                continue  # checked separately below, against a full non-overlap scan of the new revision's own periods
            if intervals_overlap(period.effective_from, period.effective_to, effective_from, None):
                raise ActivationValidationError(
                    f"new period starting {effective_from} would overlap revision "
                    f"{period.document_revision_id!r}'s own period [{period.effective_from}, {period.effective_to})"
                )

        new_own_periods = self._repository.list_periods_for_revision(new_revision_id)
        prospective = AuthorityPeriod(
            authority_period_id=0,
            logical_document_id=new_identity.logical_document_id,
            document_revision_id=new_revision_id,
            effective_from=effective_from,
            effective_to=None,
            predecessor_revision_id=old_revision_id,
            opening_event_id=1,
            authority_source="_validation_only",
            authority_reference="_validation_only",
            recorded_at=datetime.now(timezone.utc),
            recorded_by="_validation_only",
        )
        prospective_overlap = validate_own_periods_non_overlapping([*new_own_periods, prospective])
        if prospective_overlap is not None:
            raise ActivationValidationError(prospective_overlap)

        return new_identity, old_open_period

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
        closure_reason_for_old: ClosureReason = "superseded",
    ) -> None:
        """ONE atomic transition. `old_revision_id` is None only for the
        very first period ever opened for a logical document. Never
        mutates, deletes, rechunks, or re-embeds any canonical chunk of
        either revision -- this method writes only to this package's own
        registry/period/event tables. Write order (relied on by the
        fault-injection tests): (1) new revision's own metadata, (2) the
        ONE event covering this whole transition, (3) the new period
        (referencing that event as its opening_event_id), (4) the old
        period's closure (referencing the SAME event as its
        closing_event_id) -- so an exception raised between (3) and (4)
        is exactly the "new-period write happened, old-period close did
        not" fault the tests inject and prove gets rolled back."""
        new_identity, old_open_period = self._validate_activation(new_revision_id, old_revision_id, effective_from)

        with self._repository.transaction():
            self._repository.save_metadata(
                new_revision_id,
                AuthorityMetadata(
                    publication_status="approved",
                    approved_at=recorded_at,
                    authority_source=authority_source,
                    authority_reference=authority_reference,
                    authority_recorded_at=recorded_at,
                    authority_recorded_by=authority_recorded_by,
                ),
            )

            event = self._repository.append_event(
                AuthorityDecisionEvent(
                    event_id=0,
                    event_type="revision_activated",
                    logical_document_id=new_identity.logical_document_id,
                    revision_id=new_revision_id,
                    related_revision_id=old_revision_id,
                    decision_effective_date=effective_from,
                    closure_reason=(closure_reason_for_old if old_open_period is not None else None),
                    recorded_at=recorded_at,
                    authority_source=authority_source,
                    authority_reference=authority_reference,
                    recorded_by=authority_recorded_by,
                    detail=(
                        f"activated {new_revision_id} effective {effective_from}"
                        + (
                            f", {closure_reason_for_old} {old_revision_id}"
                            if old_revision_id is not None
                            else " (first effective period for this document)"
                        )
                    ),
                )
            )

            self._repository.save_period(
                AuthorityPeriod(
                    authority_period_id=0,
                    logical_document_id=new_identity.logical_document_id,
                    document_revision_id=new_revision_id,
                    effective_from=effective_from,
                    effective_to=None,
                    predecessor_revision_id=old_revision_id,
                    opening_event_id=event.event_id,
                    authority_source=authority_source,
                    authority_reference=authority_reference,
                    recorded_at=recorded_at,
                    recorded_by=authority_recorded_by,
                )
            )

            if old_open_period is not None:
                self._repository.save_period(
                    old_open_period.model_copy(
                        update={
                            "effective_to": effective_from,
                            "closing_event_id": event.event_id,
                            "closure_reason": closure_reason_for_old,
                        }
                    )
                )

    def reinstate_revision(
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
        """Opens ANOTHER period for a revision that already has prior
        history (already-closed periods) -- e.g. rolling back a
        currently-effective revision to reinstate an earlier one (Stage
        7R.1a post-effective rollback/reinstatement scenario). Shares
        the EXACT SAME validated, atomic machinery as
        `activate_revision` -- the only difference is
        `closure_reason_for_old` defaults to "rollback" instead of
        "superseded", for audit clarity. Never overwrites or destroys
        `new_revision_id`'s own earlier (already-closed) periods -- this
        only ever APPENDS a new period row."""
        self.activate_revision(
            new_revision_id=new_revision_id,
            old_revision_id=old_revision_id,
            effective_from=effective_from,
            authority_source=authority_source,
            authority_reference=authority_reference,
            authority_recorded_by=authority_recorded_by,
            recorded_at=recorded_at,
            closure_reason_for_old="rollback",
        )

    # --- withdrawal / correction (period-closing-only transitions) ------

    def withdraw_revision(
        self,
        *,
        document_revision_id: str,
        withdrawal_effective_date: date,
        closure_reason: ClosureReason = "withdrawn",
        authority_source: str,
        authority_reference: str,
        authority_recorded_by: str,
        recorded_at: datetime,
    ) -> None:
        """Closes the revision's OPEN authority period at
        `withdrawal_effective_date` -- NEVER `recorded_at` (Stage 7R.1a
        item 2's core fix: the two are different concepts and must never
        be conflated). Never auto-selects a replacement -- a logical
        document may legitimately have NO effective revision after this
        until a separate `activate_revision`/`reinstate_revision` call
        (Scenario K).

        Pass `closure_reason="correction"` with `withdrawal_effective_date`
        equal to the open period's own `effective_from` to retract a
        period BEFORE it ever took effect (a zero-width period --
        `pre_effective_authority_correction`) -- publication_status
        reverts to "draft" in that case, rather than "withdrawn"."""
        identity = self._repository.get_identity(document_revision_id)
        if identity is None:
            raise ValueError(f"no registered revision with document_revision_id={document_revision_id!r}")
        open_periods = [p for p in self._repository.list_periods_for_revision(document_revision_id) if p.is_open]
        if len(open_periods) != 1:
            raise ValueError(
                f"revision {document_revision_id!r} has {len(open_periods)} open authority period(s) "
                "(expected exactly 1 to close)"
            )
        open_period = open_periods[0]
        if withdrawal_effective_date < open_period.effective_from:
            raise ValueError(
                f"withdrawal_effective_date {withdrawal_effective_date} is before the open period's own "
                f"start {open_period.effective_from}"
            )

        new_status: PublicationStatus = "draft" if closure_reason == "correction" else "withdrawn"

        with self._repository.transaction():
            event = self._repository.append_event(
                AuthorityDecisionEvent(
                    event_id=0,
                    event_type="revision_withdrawn",
                    logical_document_id=identity.logical_document_id,
                    revision_id=document_revision_id,
                    decision_effective_date=withdrawal_effective_date,
                    closure_reason=closure_reason,
                    recorded_at=recorded_at,
                    authority_source=authority_source,
                    authority_reference=authority_reference,
                    recorded_by=authority_recorded_by,
                    detail=f"closed open period at {withdrawal_effective_date} (closure_reason={closure_reason})",
                )
            )
            self._repository.save_period(
                open_period.model_copy(
                    update={
                        "effective_to": withdrawal_effective_date,
                        "closing_event_id": event.event_id,
                        "closure_reason": closure_reason,
                    }
                )
            )
            current_metadata = self._repository.get_metadata(document_revision_id)
            self._repository.save_metadata(
                document_revision_id,
                AuthorityMetadata(
                    publication_status=new_status,
                    approved_at=current_metadata.approved_at if current_metadata is not None else None,
                    authority_source=authority_source,
                    authority_reference=authority_reference,
                    authority_recorded_at=recorded_at,
                    authority_recorded_by=authority_recorded_by,
                ),
            )

    # --- resolution -------------------------------------------------------

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
