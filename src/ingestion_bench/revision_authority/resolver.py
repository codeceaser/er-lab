"""Stage 7R.1/7R.1a: deterministic effective-knowledge resolver.

Exactly four query intents (current, as_of, comparison, draft) -- never
a generic query DSL. The pure resolver function below NEVER defaults
`as_of_date` to today; every caller (service.py included) must supply it
explicitly. "current" and "as_of" are mechanically IDENTICAL resolution
(the only difference is which date the OUTER caller happens to pass --
today vs. an explicit historical date) -- kept as separate intents only
to preserve the caller's stated purpose in the result for audit
readability, never duplicated logic.

Stage 7R.1a: integrity validation (per-record metadata/period
self-consistency, authority-period overlap, cross-document transition
consistency, period/link consistency) now applies to ALL FOUR intents,
not just current/as_of -- but the CONSEQUENCE differs by intent.
current/as_of "pick" exactly one revision, so a registry-wide integrity
problem (or the absence of any effective revision at all) fails the
WHOLE query closed -- never silently choosing one conflicting revision.
comparison/draft never "pick" anything (the caller names exact ids), so
a malformed record is EXCLUDED individually (with the integrity error as
its exclusion reason) rather than aborting the whole query -- the
absence of any effective revision is never a hard error for these two
intents.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

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
    # Populated only when this single record's own derivation failed
    # (e.g. a non-approved revision with a period recorded, or a
    # revision's own periods overlap each other) -- None does not mean
    # "no error occurred elsewhere in the query", see
    # QueryResolutionResult.integrity_error for that.
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


def _label_for(revision_id: str, metadata: AuthorityMetadata | None, periods: list[AuthorityPeriod], as_of_date: date) -> RevisionAuthorityLabel:
    if metadata is None:
        return RevisionAuthorityLabel(revision_id=revision_id, period_count=len(periods), error="revision has no authority metadata recorded")
    state, error = derive_authority_state(metadata.publication_status, periods, as_of_date)
    return RevisionAuthorityLabel(
        revision_id=revision_id,
        publication_status=metadata.publication_status,
        derived_state=state,
        period_count=len(periods),
        error=error,
    )


def _period_link_inconsistencies(periods: list[AuthorityPeriod]) -> list[str]:
    """Cross-revision structural check: every period CLOSED with
    closure_reason in (superseded, rollback) -- meaning "some other
    revision's period picked up where this one left off" -- must have a
    matching successor period (predecessor_revision_id pointing back at
    THIS revision, effective_from equal to THIS period's own
    effective_to) somewhere in the same document's period set. A period
    closed for withdrawn/correction has no such requirement (nothing
    picks up after a genuine withdrawal/correction)."""
    problems: list[str] = []
    for period in periods:
        if period.closure_reason not in ("superseded", "rollback"):
            continue
        successor_exists = any(
            other.predecessor_revision_id == period.document_revision_id and other.effective_from == period.effective_to
            for other in periods
            if other.authority_period_id != period.authority_period_id
        )
        if not successor_exists:
            problems.append(
                f"period {period.authority_period_id} (revision {period.document_revision_id!r}, closed "
                f"{period.closure_reason!r} at {period.effective_to}) has no matching successor period"
            )
    return problems


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
    labels = {
        rid: _label_for(rid, metadata_by_id.get(rid), periods_by_id.get(rid, []), as_of_date) for rid in metadata_by_id
    }

    if query_intent in ("current", "as_of"):
        return _resolve_current_or_as_of(logical_document_id, query_intent, as_of_date, labels, all_periods, snapshot_hash)
    if query_intent == "comparison":
        return _resolve_explicit(
            logical_document_id, "comparison", as_of_date, requested_revision_ids or [], labels, snapshot_hash,
            allowed_states=("effective", "superseded", "approved_future", "draft", "under_review", "withdrawn"),
        )
    if query_intent == "draft":
        return _resolve_explicit(
            logical_document_id, "draft", as_of_date, requested_revision_ids or [], labels, snapshot_hash,
            allowed_states=("draft", "under_review"),
        )
    raise ValueError(f"unknown query_intent: {query_intent!r}")


def _resolve_current_or_as_of(
    logical_document_id: str,
    query_intent: QueryIntent,
    as_of_date: date,
    labels: dict[str, "RevisionAuthorityLabel"],
    all_periods: list[AuthorityPeriod],
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

    per_record_errors = [f"{rid}: {label.error}" for rid, label in labels.items() if label.error is not None]
    if per_record_errors:
        return _fail(
            "revision authority data is internally inconsistent -- " + "; ".join(per_record_errors),
            "malformed_authority_record",
        )

    link_problems = _period_link_inconsistencies(all_periods)
    if link_problems:
        return _fail("inconsistent supersession/rollback link(s): " + "; ".join(link_problems), "inconsistent_period_link")

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
    snapshot_hash: str,
    allowed_states: tuple[str, ...],
) -> QueryResolutionResult:
    if not requested_revision_ids:
        raise ValueError(f"{query_intent} intent requires at least one requested_revision_ids entry")

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
            # Never returned as eligible -- a label containing an
            # integrity error is excluded individually, never silently
            # included and never enough to abort the whole
            # comparison/draft query (item 6).
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
