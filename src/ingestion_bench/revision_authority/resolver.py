"""Stage 7R.1/7R.1a/7R.1b: deterministic effective-knowledge resolver.

Exactly four query intents (current, as_of, comparison, draft) -- never
a generic query DSL. The pure resolver function below NEVER defaults
`as_of_date` to today; every caller (service.py included) must supply it
explicitly. "current" and "as_of" are mechanically IDENTICAL resolution
(the only difference is which date the OUTER caller happens to pass --
today vs. an explicit historical date) -- kept as separate intents only
to preserve the caller's stated purpose in the result for audit
readability, never duplicated logic.

Stage 7R.1b item 3: ALL FOUR intents now run the SAME central
`integrity.validate_document_integrity` check before eligibility
selection -- never four separately-maintained validation passes. The
CONSEQUENCE still differs by intent, by design:

- current/as_of "pick" exactly one revision, so ANY problem (revision-
  scoped or document-scoped) fails the WHOLE query closed -- never
  silently choosing one conflicting revision.
- comparison/draft never "pick" anything (the caller names exact ids).
  A DOCUMENT-scoped problem (the shared timeline itself is structurally
  broken -- an orphaned period, a missing predecessor, periods from two
  revisions overlapping, a supersession with no/ambiguous successor)
  still fails the WHOLE query closed, even for these two intents,
  because there is nothing trustworthy left to compare or browse. A
  REVISION-scoped problem (this one record's own periods overlap, or it
  is draft/under_review with a real period, or withdrawn with an open
  one) excludes ONLY that one requested revision, with the problem as
  its exclusion reason -- never aborting the whole query. The absence of
  any effective revision is never a hard error for these two intents.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ingestion_bench.revision_authority.integrity import DocumentIntegrityReport, validate_document_integrity
from ingestion_bench.revision_authority.model import (
    AuthorityMetadata,
    AuthorityPeriod,
    DerivedAuthorityState,
    PublicationStatus,
    derive_authority_state,
)
from ingestion_bench.revision_authority.repository import RevisionAuthorityRepository

QueryIntent = Literal["current", "as_of", "comparison", "draft"]


class RevisionAuthorityLabel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision_id: str
    publication_status: PublicationStatus | None = None
    derived_state: DerivedAuthorityState | None = None
    period_count: int = 0
    # Populated when EITHER derive_authority_state's own check OR the
    # central document-integrity validator found a problem specific to
    # this revision -- None does not mean "no error occurred elsewhere
    # in the query", see QueryResolutionResult.integrity_error for that.
    error: str | None = None


class ExclusionReason(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision_id: str
    reason_code: str
    detail: str


class QueryResolutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    logical_document_id: str
    query_intent: QueryIntent
    as_of_date: date
    requested_revision_ids: list[str]

    eligible_revision_ids: list[str]
    excluded: list[ExclusionReason]
    authority_labels: dict[str, RevisionAuthorityLabel]

    resolution_explanation: str
    registry_snapshot_hash: str
    integrity_error: str | None = None
    integrity_error_code: str | None = None


def _registry_snapshot_hash(
    logical_document_id: str,
    metadata_by_id: dict[str, AuthorityMetadata | None],
    periods_by_id: dict[str, list[AuthorityPeriod]],
) -> str:
    """SHA-256 over a canonical JSON dump of every revision_id + its
    CURRENT AuthorityMetadata + ALL of its AuthorityPeriods for this
    logical document, sorted by revision_id -- changes whenever ANY
    authority fact for this document changes (new revision, decision,
    activation, withdrawal, reinstatement, correction), never when
    canonical chunk content changes (this registry never reads chunk
    content)."""
    payload = {
        "logical_document_id": logical_document_id,
        "revisions": {
            revision_id: {
                "metadata": metadata_by_id[revision_id].model_dump(mode="json") if metadata_by_id.get(revision_id) else None,
                "periods": [p.model_dump(mode="json") for p in sorted(periods_by_id.get(revision_id, []), key=lambda p: p.authority_period_id)],
            }
            for revision_id in sorted(metadata_by_id)
        },
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _label_for(
    revision_id: str,
    metadata: AuthorityMetadata | None,
    periods: list[AuthorityPeriod],
    as_of_date: date,
    integrity_report: DocumentIntegrityReport,
) -> RevisionAuthorityLabel:
    if metadata is None:
        return RevisionAuthorityLabel(revision_id=revision_id, period_count=len(periods), error="revision has no authority metadata recorded")

    state, derive_error = derive_authority_state(metadata.publication_status, periods, as_of_date)
    central_problems = integrity_report.revision_problems.get(revision_id, [])
    # Combine both signals -- derive_authority_state's own check is a
    # defensive fallback; the central validator is the primary source of
    # truth used consistently across all four intents.
    error_parts = [p.message for p in central_problems]
    if derive_error is not None and derive_error not in error_parts:
        error_parts.append(derive_error)
    combined_error = "; ".join(error_parts) if error_parts else None

    return RevisionAuthorityLabel(
        revision_id=revision_id,
        publication_status=metadata.publication_status,
        derived_state=state if not combined_error else None,
        period_count=len(periods),
        error=combined_error,
    )


def resolve_query_scope(
    repository: RevisionAuthorityRepository,
    logical_document_id: str,
    query_intent: QueryIntent,
    as_of_date: date,
    requested_revision_ids: list[str] | None = None,
) -> QueryResolutionResult:
    if not isinstance(as_of_date, date):
        raise ValueError("as_of_date must be supplied explicitly by the caller -- this resolver never defaults it")

    identities = repository.list_revisions_for_document(logical_document_id)
    metadata_by_id: dict[str, AuthorityMetadata | None] = {i.document_revision_id: repository.get_metadata(i.document_revision_id) for i in identities}
    all_periods = repository.list_periods_for_document(logical_document_id)
    periods_by_id: dict[str, list[AuthorityPeriod]] = {i.document_revision_id: [] for i in identities}
    for period in all_periods:
        periods_by_id.setdefault(period.document_revision_id, []).append(period)

    snapshot_hash = _registry_snapshot_hash(logical_document_id, metadata_by_id, periods_by_id)

    # Stage 7R.1b item 3: ONE central integrity pass, before eligibility
    # selection, shared by all four intents.
    integrity_report = validate_document_integrity(logical_document_id, identities, metadata_by_id, periods_by_id, all_periods)

    labels = {
        rid: _label_for(rid, metadata_by_id.get(rid), periods_by_id.get(rid, []), as_of_date, integrity_report)
        for rid in metadata_by_id
    }

    if query_intent in ("current", "as_of"):
        return _resolve_current_or_as_of(logical_document_id, query_intent, as_of_date, labels, integrity_report, snapshot_hash)
    if query_intent == "comparison":
        return _resolve_explicit(
            logical_document_id, "comparison", as_of_date, requested_revision_ids or [], labels, integrity_report, snapshot_hash,
            allowed_states=("effective", "superseded", "approved_future", "draft", "under_review", "withdrawn"),
        )
    if query_intent == "draft":
        return _resolve_explicit(
            logical_document_id, "draft", as_of_date, requested_revision_ids or [], labels, integrity_report, snapshot_hash,
            allowed_states=("draft", "under_review"),
        )
    raise ValueError(f"unknown query_intent: {query_intent!r}")


def _resolve_current_or_as_of(
    logical_document_id: str,
    query_intent: QueryIntent,
    as_of_date: date,
    labels: dict[str, "RevisionAuthorityLabel"],
    integrity_report: DocumentIntegrityReport,
    snapshot_hash: str,
) -> QueryResolutionResult:
    def _fail(message: str, code: str) -> QueryResolutionResult:
        return QueryResolutionResult(
            logical_document_id=logical_document_id, query_intent=query_intent, as_of_date=as_of_date,
            requested_revision_ids=[], eligible_revision_ids=[], excluded=[], authority_labels=labels,
            resolution_explanation=message, registry_snapshot_hash=snapshot_hash,
            integrity_error=message, integrity_error_code=code,
        )

    if not labels:
        return _fail(f"logical_document_id={logical_document_id!r} has no registered revisions at all", "no_revisions_registered")

    # current/as_of "pick" exactly one revision -- ANY problem (document-
    # or revision-scoped) makes the whole timeline untrustworthy for that
    # purpose, so it fails the whole query closed. The reported code is
    # the SPECIFIC problem type (e.g. "cross_revision_period_overlap",
    # "missing_successor") rather than a single generic bucket --
    # document-scoped problems take priority (they invalidate the whole
    # timeline, not just one revision), first-found order otherwise.
    if integrity_report.has_any_problem:
        all_problems = integrity_report.all_problems()
        leading_problem = integrity_report.document_problems[0] if integrity_report.document_problems else all_problems[0]
        return _fail(
            "revision authority data is internally inconsistent -- " + "; ".join(p.message for p in all_problems),
            leading_problem.code,
        )

    effective_ids = [rid for rid, label in labels.items() if label.derived_state == "effective"]
    if len(effective_ids) > 1:
        return _fail(
            f"{len(effective_ids)} revisions of {logical_document_id!r} are simultaneously effective as of "
            f"{as_of_date}: {sorted(effective_ids)} -- refusing to silently choose one",
            "overlapping_effective_revisions",
        )
    if not effective_ids:
        return _fail(
            f"logical_document_id={logical_document_id!r} has no authoritative effective revision as of {as_of_date}",
            "no_effective_revision",
        )

    eligible = effective_ids
    excluded = [
        ExclusionReason(revision_id=rid, reason_code=f"not_effective_{label.derived_state}", detail=_exclusion_detail(label, as_of_date))
        for rid, label in labels.items()
        if rid not in eligible
    ]
    explanation = (
        f"{query_intent} query for {logical_document_id!r} as of {as_of_date}: 1 of {len(labels)} "
        f"revision(s) effective -- {eligible[0]}"
    )
    return QueryResolutionResult(
        logical_document_id=logical_document_id, query_intent=query_intent, as_of_date=as_of_date,
        requested_revision_ids=[], eligible_revision_ids=eligible, excluded=excluded, authority_labels=labels,
        resolution_explanation=explanation, registry_snapshot_hash=snapshot_hash,
        integrity_error=None, integrity_error_code=None,
    )


def _exclusion_detail(label: RevisionAuthorityLabel, as_of_date: date) -> str:
    if label.derived_state == "approved_future":
        return f"has a future authority period not yet effective as of as_of_date={as_of_date}"
    if label.derived_state == "superseded":
        return f"authority period(s) closed on or before as_of_date={as_of_date}"
    if label.derived_state in ("draft", "under_review", "withdrawn"):
        return f"derived_state={label.derived_state} is never eligible for current/as_of intent"
    return f"derived_state={label.derived_state}"


def _resolve_explicit(
    logical_document_id: str,
    query_intent: QueryIntent,
    as_of_date: date,
    requested_revision_ids: list[str],
    labels: dict[str, RevisionAuthorityLabel],
    integrity_report: DocumentIntegrityReport,
    snapshot_hash: str,
    allowed_states: tuple[str, ...],
) -> QueryResolutionResult:
    if not requested_revision_ids:
        raise ValueError(f"{query_intent} intent requires at least one requested_revision_ids entry")

    # Stage 7R.1b item 3: a DOCUMENT-scoped problem makes the whole
    # shared timeline untrustworthy -- even comparison/draft (which never
    # "pick" a single revision) fail the whole query closed, since there
    # is nothing meaningful left to compare or browse.
    if integrity_report.document_problems:
        message = "document-wide authority timeline is internally inconsistent -- " + "; ".join(
            p.message for p in integrity_report.document_problems
        )
        return QueryResolutionResult(
            logical_document_id=logical_document_id, query_intent=query_intent, as_of_date=as_of_date,
            requested_revision_ids=requested_revision_ids, eligible_revision_ids=[], excluded=[],
            authority_labels=labels, resolution_explanation=message, registry_snapshot_hash=snapshot_hash,
            integrity_error=message, integrity_error_code=integrity_report.document_problems[0].code,
        )

    eligible: list[str] = []
    excluded: list[ExclusionReason] = []
    result_labels: dict[str, RevisionAuthorityLabel] = {}
    seen: set[str] = set()

    for rid in requested_revision_ids:
        if rid in seen:
            excluded.append(
                ExclusionReason(revision_id=rid, reason_code="duplicate_request", detail=f"{rid!r} was requested more than once -- only the first occurrence is considered")
            )
            continue
        seen.add(rid)

        label = labels.get(rid)
        if label is None:
            excluded.append(ExclusionReason(revision_id=rid, reason_code="revision_not_found", detail=f"{rid!r} is not a registered revision of {logical_document_id!r}"))
            result_labels[rid] = RevisionAuthorityLabel(revision_id=rid, error="revision not found")
            continue
        result_labels[rid] = label

        if label.error is not None:
            # A REVISION-scoped problem -- excluded individually, never
            # returned as eligible, never enough to abort the whole
            # comparison/draft query (item 3/6).
            excluded.append(ExclusionReason(revision_id=rid, reason_code="malformed_authority_record", detail=label.error))
            continue

        if label.derived_state not in allowed_states:
            excluded.append(
                ExclusionReason(
                    revision_id=rid, reason_code=f"not_eligible_for_{query_intent}_intent",
                    detail=f"derived_state={label.derived_state!r} is not permitted under {query_intent} intent",
                )
            )
            continue

        eligible.append(rid)

    explanation = (
        f"{query_intent} query for {logical_document_id!r}: {len(eligible)} of {len(requested_revision_ids)} "
        f"requested revision(s) eligible"
    )
    return QueryResolutionResult(
        logical_document_id=logical_document_id, query_intent=query_intent, as_of_date=as_of_date,
        requested_revision_ids=requested_revision_ids, eligible_revision_ids=eligible, excluded=excluded,
        authority_labels=result_labels, resolution_explanation=explanation, registry_snapshot_hash=snapshot_hash,
        integrity_error=None, integrity_error_code=None,
    )
