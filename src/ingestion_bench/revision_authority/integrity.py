"""Stage 7R.1b item 3: central document-integrity validation.

ONE narrow function (`validate_document_integrity`), used by ALL FOUR
query intents (current, as_of, comparison, draft) before eligibility
selection -- never duplicated per-intent logic, never a generic rule
engine.

Every problem found is classified as either:

- **revision-scoped** -- attributable to exactly ONE revision's own
  record (its own periods overlap each other, it is draft/under_review
  but has a real period, it is withdrawn but still has an open period).
  `comparison`/`draft` intents exclude just that ONE revision, never
  aborting the whole query.
- **document-scoped** -- inherently about the RELATIONSHIP between two
  or more revisions' periods (an orphaned period, a period claiming the
  wrong logical_document_id, a missing/duplicate predecessor, periods
  from different revisions overlapping ANYWHERE in history, a
  superseded/rollback closure with no matching successor, or more than
  one candidate successor). These make the document's whole timeline
  untrustworthy, so they are a HARD integrity error for every intent,
  including `comparison`/`draft` -- there is nothing meaningful left to
  compare or browse if the timeline itself is broken.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ingestion_bench.revision_authority.model import (
    AuthorityMetadata,
    AuthorityPeriod,
    RevisionIdentity,
    intervals_overlap,
    validate_own_periods_non_overlapping,
)


@dataclass(frozen=True)
class IntegrityProblem:
    scope: str  # "revision" | "document"
    revision_id: str | None
    code: str
    message: str


@dataclass(frozen=True)
class DocumentIntegrityReport:
    revision_problems: dict[str, list[IntegrityProblem]]
    document_problems: list[IntegrityProblem]

    @property
    def has_any_problem(self) -> bool:
        return bool(self.document_problems) or any(self.revision_problems.values())

    def all_problems(self) -> list[IntegrityProblem]:
        combined = list(self.document_problems)
        for problems in self.revision_problems.values():
            combined.extend(problems)
        return combined


def validate_document_integrity(
    logical_document_id: str,
    identities: list[RevisionIdentity],
    metadata_by_id: dict[str, AuthorityMetadata | None],
    periods_by_id: dict[str, list[AuthorityPeriod]],
    all_periods: list[AuthorityPeriod],
) -> DocumentIntegrityReport:
    known_ids = {i.document_revision_id for i in identities}
    revision_problems: dict[str, list[IntegrityProblem]] = {rid: [] for rid in known_ids}
    document_problems: list[IntegrityProblem] = []

    def add_revision(rid: str, code: str, message: str) -> None:
        revision_problems.setdefault(rid, []).append(IntegrityProblem("revision", rid, code, message))

    def add_document(code: str, message: str) -> None:
        document_problems.append(IntegrityProblem("document", None, code, message))

    # 1. every authority period references a registered revision.
    for period in all_periods:
        if period.document_revision_id not in known_ids:
            add_document(
                "orphaned_period",
                f"period {period.authority_period_id} references unregistered revision "
                f"{period.document_revision_id!r}",
            )

    # 2. the period's own logical_document_id matches the queried document
    #    (and therefore the revision's own identity, since periods are
    #    always fetched scoped to ONE logical_document_id).
    for period in all_periods:
        if period.logical_document_id != logical_document_id:
            add_document(
                "period_document_mismatch",
                f"period {period.authority_period_id} (revision {period.document_revision_id!r}) claims "
                f"logical_document_id={period.logical_document_id!r}, expected {logical_document_id!r}",
            )

    # 3. predecessor_revision_id exists in the same logical document.
    for period in all_periods:
        if period.predecessor_revision_id is not None and period.predecessor_revision_id not in known_ids:
            add_document(
                "missing_predecessor",
                f"period {period.authority_period_id} (revision {period.document_revision_id!r}) has "
                f"predecessor_revision_id={period.predecessor_revision_id!r}, not a registered revision of "
                f"{logical_document_id!r}",
            )

    # 4. periods across DIFFERENT revisions never overlap ANYWHERE in the
    #    document's authority history (not just "at as_of_date" -- a
    #    genuinely structural, date-independent invariant).
    revision_ids_sorted = sorted(periods_by_id)
    for i, rid_a in enumerate(revision_ids_sorted):
        for rid_b in revision_ids_sorted[i + 1 :]:
            for period_a in periods_by_id[rid_a]:
                for period_b in periods_by_id[rid_b]:
                    if intervals_overlap(period_a.effective_from, period_a.effective_to, period_b.effective_from, period_b.effective_to):
                        add_document(
                            "cross_revision_period_overlap",
                            f"revision {rid_a!r} period [{period_a.effective_from}, {period_a.effective_to}) overlaps "
                            f"revision {rid_b!r} period [{period_b.effective_from}, {period_b.effective_to})",
                        )

    # 5. each revision's own periods do not overlap each other.
    for rid, periods in periods_by_id.items():
        error = validate_own_periods_non_overlapping(periods)
        if error is not None:
            add_revision(rid, "own_periods_overlap", error)

    # 6/7. every superseded/rollback closure has EXACTLY ONE matching
    #      successor at the same boundary, and that linkage is reciprocal
    #      by construction of the match itself (the successor's own
    #      predecessor_revision_id must equal the closed period's revision).
    for period in all_periods:
        if period.closure_reason not in ("superseded", "rollback"):
            continue
        matches = [
            other
            for other in all_periods
            if other.authority_period_id != period.authority_period_id
            and other.predecessor_revision_id == period.document_revision_id
            and other.effective_from == period.effective_to
        ]
        if len(matches) == 0:
            add_document(
                "missing_successor",
                f"period {period.authority_period_id} (revision {period.document_revision_id!r}, closed "
                f"{period.closure_reason!r} at {period.effective_to}) has no matching successor period",
            )
        elif len(matches) > 1:
            add_document(
                "ambiguous_successor",
                f"period {period.authority_period_id} (revision {period.document_revision_id!r}) has "
                f"{len(matches)} candidate successor periods starting {period.effective_to} -- expected exactly 1",
            )

    # 8. a withdrawn revision has no open period.
    for rid in known_ids:
        metadata = metadata_by_id.get(rid)
        if metadata is not None and metadata.publication_status == "withdrawn":
            if any(p.is_open for p in periods_by_id.get(rid, [])):
                add_revision(rid, "withdrawn_with_open_period", f"revision {rid!r} is withdrawn but still has an open authority period")

    # 9. draft/under_review has no non-zero-width (real) period.
    for rid in known_ids:
        metadata = metadata_by_id.get(rid)
        if metadata is not None and metadata.publication_status in ("draft", "under_review"):
            real_periods = [p for p in periods_by_id.get(rid, []) if p.effective_to is None or p.effective_to > p.effective_from]
            if real_periods:
                add_revision(
                    rid, "unapproved_with_real_period",
                    f"revision {rid!r} is {metadata.publication_status!r} but has {len(real_periods)} "
                    "non-zero-width authority period(s) -- effective revision is not approved",
                )

    return DocumentIntegrityReport(revision_problems=revision_problems, document_problems=document_problems)
