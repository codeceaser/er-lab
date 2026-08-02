"""Stage 7R.1/7R.1a: revision-identity reuse, authority metadata,
authority periods, and derived authority-state rules.

This is NOT a document-management/version-control system: it never
stores or edits document binaries, provides check-in/check-out, manages
approval workflows, or infers authority from filenames/upload time/
document text. It persists authoritative revision metadata supplied by
a consumer or governance source and uses it to resolve which
already-ingested document revisions are eligible for a query.

Revision IDENTITY is reused verbatim from `ingestion_bench.chunking`,
never reinvented: `DocumentRevisionContext` (Stage 4.1) is already
"Identity of one revision of one logical document, supplied explicitly
by the caller of chunk_document()" and its own docstring already
anticipates this exact package.

Stage 7R.1a change: a single effective_from/effective_to pair on the
revision itself could not represent a historical revision before a
later withdrawal, a revision reinstated after a rollback, or multiple
disjoint effective periods for the same revision. `AuthorityPeriod` is
now the SOLE authoritative source for effective-date resolution --
`AuthorityMetadata` retains only publication/governance status
(never effective dates, never supersession links), so there is exactly
ONE authoritative copy of any effective interval, never two competing
ones.

Canonical chunks never receive mutable superseded/current flags of any
kind -- this whole package writes only to its own two tables
(`edib_document_revision_registry`, `edib_revision_authority_period`,
plus the append-only `edib_authority_decision_event` log). Historical
evidence (a chunk's own content and hash) never changes as authority
periods open, close, or get corrected.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ingestion_bench.chunking import DocumentRevisionContext, compute_document_revision_id

# Re-exported under this package's own vocabulary -- see module docstring
# for why this is REUSE, not a parallel reinvention.
RevisionIdentity = DocumentRevisionContext

__all__ = [
    "RevisionIdentity",
    "compute_document_revision_id",
    "PublicationStatus",
    "DirectlyAssignableStatus",
    "DerivedAuthorityState",
    "ClosureReason",
    "WithdrawalClosureReason",
    "AuthorityMetadata",
    "AuthorityPeriod",
    "AuthorityDecisionEvent",
    "AuthorityEventType",
    "derive_authority_state",
    "validate_own_periods_non_overlapping",
]

# The only facts a governance source may assert directly about a
# revision's own status. Never "superseded" or "effective" -- those are
# always DERIVED at query time from AuthorityPeriod (see
# derive_authority_state below), never stored as if they were an
# independent fact an old revision's row gets rewritten to.
PublicationStatus = Literal["draft", "under_review", "approved", "withdrawn"]

# Stage 7R.1b item 1: record_authority_decision() -- a PURE status
# change with no period involved -- may only ever set one of these two
# pre-approval states. "approved" (which always requires a real period
# backing it) is producible ONLY by activate_revision()/
# reinstate_revision(); "withdrawn" (which always closes a real period)
# is producible ONLY by withdraw_revision(). Restricting the TYPE alone
# is not enforcement -- service.py's own record_authority_decision()
# additionally raises at runtime if a caller passes anything else.
DirectlyAssignableStatus = Literal["draft", "under_review"]

# Stage 7R.1b item 2: withdraw_revision() may close a period only for
# one of these two reasons -- "superseded" and "rollback" are producible
# ONLY by activate_revision()/reinstate_revision() respectively, never
# passed in by a withdraw_revision() caller. There is no public,
# generic closure_reason parameter anywhere that would let a caller
# construct a semantically contradictory transition (e.g. "withdraw...
# but call it a supersession").
WithdrawalClosureReason = Literal["withdrawn", "correction"]

# Computed, never stored. An old revision may remain historically
# "approved" (publication_status) forever while its derived CURRENT
# authority state is "superseded" -- these are deliberately different
# things.
DerivedAuthorityState = Literal[
    "draft", "under_review", "approved_future", "effective", "superseded", "withdrawn"
]

# Why an authority period was closed. "superseded" = a newer revision
# took over (the common forward-progress case); "withdrawn" = authority
# was pulled with no replacement; "rollback" = an operational reversal
# of a revision that WAS genuinely effective (see reinstate_revision);
# "correction" = a period is being retracted before it ever took effect
# (a zero-width period, effective_to == effective_from) -- see
# pre_effective_authority_correction in the scenario contract.
ClosureReason = Literal["superseded", "withdrawn", "rollback", "correction"]


class AuthorityMetadata(BaseModel):
    """Mutable GOVERNANCE facts for ONE revision (keyed externally by
    that revision's `document_revision_id`) -- never an effective date,
    never a supersession link (Stage 7R.1a: both moved to
    `AuthorityPeriod`, the sole authoritative source for effective-date
    resolution). `is_latest` is deliberately NOT a field here."""

    model_config = ConfigDict(extra="forbid")

    publication_status: PublicationStatus
    approved_at: datetime | None = None

    # Governance provenance -- WHO/WHERE this authority fact came from,
    # never inferred.
    authority_source: str
    authority_reference: str
    authority_recorded_at: datetime
    authority_recorded_by: str


class AuthorityPeriod(BaseModel):
    """One effective interval for ONE revision. The SOLE authoritative
    source for effective-date resolution -- AuthorityMetadata carries no
    competing copy of effective_from/effective_to. A revision may have
    MULTIPLE, non-overlapping periods over time (a historical period,
    later closed by withdrawal or supersession; a later period from a
    rollback/reinstatement) -- see REVISION_AUTHORITY_SCENARIOS.md
    Scenario post-effective rollback for a worked example.

    Effective interval convention: effective_from <= as_of_date <
    effective_to. effective_to == None means open-ended (still the
    currently active period, if any).
    """

    model_config = ConfigDict(extra="forbid")

    authority_period_id: int = Field(ge=0)  # 0 is a construction-time-only "not yet persisted" sentinel, like AuthorityDecisionEvent.event_id
    logical_document_id: str
    document_revision_id: str

    effective_from: date
    effective_to: date | None = None

    # The revision this period's OPENING superseded/followed, if any --
    # None for a document's very first-ever period.
    predecessor_revision_id: str | None = None

    # Links back to the append-only event log -- never a free-text
    # reference alone, so a period's provenance is always traceable to
    # exactly one recorded decision. closing_event_id is None while the
    # period remains open.
    opening_event_id: int = Field(ge=1)
    closing_event_id: int | None = None
    closure_reason: ClosureReason | None = None

    authority_source: str
    authority_reference: str
    recorded_at: datetime
    recorded_by: str

    @model_validator(mode="after")
    def _validate_interval_ordering(self) -> "AuthorityPeriod":
        """effective_to must be AT LEAST effective_from (>=, not
        strictly >) -- a zero-width period (effective_to == effective_from)
        is a deliberate, valid representation of "approved then
        immediately corrected before ever taking effect"
        (pre_effective_authority_correction): the interval
        effective_from <= as_of_date < effective_to then matches NO
        as_of_date at all, which is exactly the desired "this never
        actually became effective" behavior. Only a genuinely INVERTED
        interval (effective_to < effective_from) is rejected."""
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError(
                f"effective_to ({self.effective_to}) must not be before effective_from ({self.effective_from})"
            )
        if self.closure_reason is not None and self.closing_event_id is None:
            raise ValueError("closure_reason is set but closing_event_id is None")
        if self.closing_event_id is not None and self.closure_reason is None:
            raise ValueError("closing_event_id is set but closure_reason is None")
        if self.effective_to is None and self.closure_reason is not None:
            raise ValueError("an open period (effective_to=None) must not have a closure_reason")
        return self

    @property
    def is_open(self) -> bool:
        return self.effective_to is None


AuthorityEventType = Literal[
    "revision_registered",
    "duplicate_registration_attempt",
    "authority_decision_recorded",
    "revision_activated",
    "revision_withdrawn",
]


class AuthorityDecisionEvent(BaseModel):
    """One append-only audit record. Never updated or deleted by normal
    application operations -- see repository.py's Protocol, which
    exposes no update/delete method for events at all.

    `recorded_at` means when the decision was RECORDED (audit
    timestamp). `decision_effective_date` means when the authority
    change TAKES EFFECT -- these are deliberately different fields;
    reconstructing an effective date by parsing `detail`'s free text is
    never required or supported."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # 0 is a construction-time-only sentinel meaning "not yet persisted"
    # -- callers always construct with event_id=0 and let
    # repository.append_event() assign the real (>=1) id.
    event_id: int = Field(ge=0)
    event_type: AuthorityEventType
    logical_document_id: str
    revision_id: str
    related_revision_id: str | None = None
    decision_effective_date: date | None = None
    closure_reason: ClosureReason | None = None
    recorded_at: datetime
    authority_source: str
    authority_reference: str
    recorded_by: str
    detail: str


def intervals_overlap(
    from_a: date, to_a: date | None, from_b: date, to_b: date | None
) -> bool:
    """Whether [from_a, to_a) and [from_b, to_b) overlap, under the
    effective_from <= as_of_date < effective_to convention (None == open
    -ended). Shared by validate_own_periods_non_overlapping below and
    service.py's cross-revision pre-activation overlap check, so there
    is exactly one implementation of "do these two intervals conflict"
    anywhere in this package."""
    left_ok = to_b is None or from_a < to_b
    right_ok = to_a is None or from_b < to_a
    return left_ok and right_ok


def validate_own_periods_non_overlapping(periods: list[AuthorityPeriod]) -> str | None:
    """Per-record structural check: one revision's OWN periods must be
    mutually non-overlapping (multiple periods for the same revision are
    explicitly PERMITTED -- item 1 -- but never overlapping ones).
    Returns an error string, or None when consistent. O(n^2) is fine --
    a single revision realistically has a handful of periods, never
    thousands."""
    ordered = sorted(periods, key=lambda p: p.effective_from)
    for earlier, later in zip(ordered, ordered[1:]):
        if intervals_overlap(earlier.effective_from, earlier.effective_to, later.effective_from, later.effective_to):
            return (
                f"revision has overlapping authority periods: "
                f"[{earlier.effective_from}, {earlier.effective_to}) and "
                f"[{later.effective_from}, {later.effective_to})"
            )
    return None


def derive_authority_state(
    publication_status: PublicationStatus, periods: list[AuthorityPeriod], as_of_date: date
) -> tuple[DerivedAuthorityState | None, str | None]:
    """Computes the query-time authority state for ONE revision as of
    ONE date, from its OWN publication_status + ALL of its own periods
    (no cross-revision context -- the resolver layers cross-revision
    integrity checks, e.g. "two revisions simultaneously effective", on
    top of this). Returns (state, None) normally, or (None,
    error_message) when this single record is internally inconsistent
    -- never silently guesses.

    Stage 7R.1a correction: withdrawal is now PERIOD-AWARE, not a status
    short-circuit. A withdrawn revision's HISTORICAL periods (before the
    withdrawal date) still correctly resolve "effective" for an as_of
    date within them -- only dates on/after the closing date resolve
    "withdrawn". This is the exact behavior Stage 7R.1's original
    "withdrawn always short-circuits regardless of date" rule got wrong.
    """
    if publication_status in ("draft", "under_review"):
        # A ZERO-WIDTH period (effective_to == effective_from) is a
        # legitimate historical artifact of pre_effective_authority_correction
        # -- it can never match any as_of_date by construction (the
        # effective_from <= as_of_date < effective_to interval is empty),
        # so it grants no authority and is never itself an inconsistency.
        # Only a REAL (non-empty) period on a draft/under_review record
        # is the genuine "effective revision is not approved" violation.
        real_periods = [p for p in periods if p.effective_to is None or p.effective_to > p.effective_from]
        if real_periods:
            return None, (
                f"{publication_status} revision has {len(real_periods)} non-empty authority period(s) recorded "
                "(effective revision is not approved) -- a draft/under_review revision must never have a real "
                "(non-zero-width) period"
            )
        return publication_status, None

    overlap_error = validate_own_periods_non_overlapping(periods)
    if overlap_error is not None:
        return None, overlap_error

    # publication_status in ("approved", "withdrawn"): check whether
    # as_of_date falls within ANY of this revision's own periods --
    # this is what makes a withdrawn/superseded revision's history
    # still correctly resolve "effective" for dates before its closure.
    for period in periods:
        if period.effective_from <= as_of_date and (period.effective_to is None or as_of_date < period.effective_to):
            return "effective", None

    if not periods:
        # approved (or withdrawn with all history erased, which should
        # never happen) but never actually activated -- there is no
        # period to derive a state from at all.
        return None, f"{publication_status} revision has no authority period recorded -- cannot derive an authority state"

    future_periods = [p for p in periods if as_of_date < p.effective_from]
    if future_periods:
        return "approved_future", None

    # as_of_date is after every period's own effective_to.
    if publication_status == "withdrawn":
        return "withdrawn", None
    return "superseded", None
