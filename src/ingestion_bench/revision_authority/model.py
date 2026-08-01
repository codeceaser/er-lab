"""Stage 7R.1: revision-identity reuse, authority metadata, and derived
authority-state rules.

This is NOT a document-management/version-control system: it never
stores or edits document binaries, provides check-in/check-out, manages
approval workflows, or infers authority from filenames/upload time/
document text. It persists authoritative revision metadata supplied by a
consumer or governance source and uses it to resolve which
already-ingested document revisions are eligible for a query.

Revision IDENTITY is reused verbatim from `ingestion_bench.chunking`,
never reinvented: `DocumentRevisionContext` (Stage 4.1) is already
"Identity of one revision of one logical document, supplied explicitly
by the caller of chunk_document()" and its own docstring already
anticipates this exact package ("A future document-revision registry
... is expected to be the authoritative source of these values").
`document_revision_id` is ALWAYS the deterministic
`compute_document_revision_id(logical_document_id,
source_document_sha256, version_label, revision_number)` hash -- never
freely chosen -- which is exactly what makes "exact duplicate reuses the
existing document_revision_id" true by construction: two registration
attempts with identical identity components always compute the SAME id,
so there is nothing else to deduplicate on.

Authority/effective-period/supersession metadata is MUTABLE and belongs
here, in this new registry -- never on `CanonicalChunk`, which stays
exactly as Stage 4/4.1 left it (immutable, content-hashed, no mutable
retrieval/index state).
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
    "DerivedAuthorityState",
    "AuthorityMetadata",
    "AuthorityDecisionEvent",
    "AuthorityEventType",
    "derive_authority_state",
]

# The only facts a governance source may assert directly. Never
# "superseded" or "effective" -- those are always DERIVED at query time
# (see derive_authority_state below), never stored as if they were an
# independent fact an old revision's row gets rewritten to.
PublicationStatus = Literal["draft", "under_review", "approved", "withdrawn"]

# Computed, never stored. An old revision may remain historically
# "approved" (publication_status) forever while its derived CURRENT
# authority state is "superseded" -- these are deliberately different
# things.
DerivedAuthorityState = Literal[
    "draft", "under_review", "approved_future", "effective", "superseded", "withdrawn"
]


class AuthorityMetadata(BaseModel):
    """Mutable authority facts for ONE revision (keyed externally by that
    revision's `document_revision_id`) -- never mutates the revision's
    own identity or its canonical chunks. `is_latest` is deliberately NOT
    a field here: "latest" is a highest-revision-number/most-recent-
    upload notion, and this registry never treats either as authority
    (see derive_authority_state's own rules and D-note in
    REVISION_AUTHORITY_SCENARIOS.md)."""

    model_config = ConfigDict(extra="forbid")

    publication_status: PublicationStatus
    approved_at: datetime | None = None

    # Effective interval convention: effective_from <= as_of_date <
    # effective_to. effective_to == None means no declared upper bound.
    # Date granularity (not datetime) -- effective-dating in this domain
    # is a calendar-day concept (matches "as_of_date" throughout this
    # package), while authority AUDIT timestamps (below) stay
    # full-precision for forensic ordering.
    effective_from: date | None = None
    effective_to: date | None = None

    # Supersession links -- both sides populated together, atomically, by
    # AuthorityTransitionService.activate_revision(); never independently
    # edited.
    supersedes_revision_id: str | None = None
    superseded_by_revision_id: str | None = None

    # Governance provenance -- WHO/WHERE this authority fact came from,
    # never inferred.
    authority_source: str
    authority_reference: str
    authority_recorded_at: datetime
    authority_recorded_by: str

    @model_validator(mode="after")
    def _validate_effective_interval_ordering(self) -> "AuthorityMetadata":
        """A single-record structural check (never depends on other
        revisions) -- effective_to must be strictly after effective_from
        when both are populated. Enforced at construction time so this
        specific integrity violation can never even enter the registry,
        fail-closed by simply being unconstructable."""
        if self.effective_from is not None and self.effective_to is not None:
            if self.effective_to <= self.effective_from:
                raise ValueError(
                    f"effective_to ({self.effective_to}) must be strictly after "
                    f"effective_from ({self.effective_from})"
                )
        return self


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
    exposes no update/delete method for events at all."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # 0 is a construction-time-only sentinel meaning "not yet persisted"
    # -- callers always construct with event_id=0 and let
    # repository.append_event() assign the real (>=1) id; every event
    # actually returned by list_events()/append_event() has event_id>=1.
    event_id: int = Field(ge=0)
    event_type: AuthorityEventType
    logical_document_id: str
    revision_id: str
    related_revision_id: str | None = None
    recorded_at: datetime
    authority_source: str
    authority_reference: str
    recorded_by: str
    detail: str


def derive_authority_state(metadata: AuthorityMetadata, as_of_date: date) -> tuple[DerivedAuthorityState | None, str | None]:
    """Computes the query-time authority state for ONE revision as of ONE
    date, from ITS OWN metadata only (no cross-revision context -- the
    resolver layers cross-revision integrity checks, e.g. "two
    simultaneously effective revisions", on top of this). Returns
    (state, None) normally, or (None, error_message) when this single
    record is internally inconsistent -- never silently guesses a state
    for inconsistent data.

    publication_status is checked FIRST and short-circuits: a
    draft/under_review/withdrawn revision is never "effective" no matter
    what its effective_from/effective_to say -- populating effective
    dates on a non-approved revision is itself the "effective revision is
    not approved" integrity violation, caught here explicitly rather than
    silently coerced into some other state.
    """
    if metadata.publication_status == "withdrawn":
        return "withdrawn", None

    if metadata.publication_status in ("draft", "under_review"):
        if metadata.effective_from is not None:
            return None, (
                f"{metadata.publication_status} revision must not have effective_from populated "
                f"(effective revision is not approved): got effective_from={metadata.effective_from}"
            )
        return metadata.publication_status, None

    # publication_status == "approved"
    if metadata.effective_from is None:
        return None, "approved revision is missing effective_from -- cannot derive an authority state"

    if as_of_date < metadata.effective_from:
        return "approved_future", None
    if metadata.effective_to is not None and as_of_date >= metadata.effective_to:
        return "superseded", None
    return "effective", None
