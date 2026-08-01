"""Stage 7R.1: deterministic effective-knowledge resolver.

Exactly four query intents (current, as_of, comparison, draft) -- never
a generic query DSL. The pure resolver function below NEVER defaults
`as_of_date` to today; every caller (service.py included) must supply it
explicitly. "current" and "as_of" are mechanically IDENTICAL resolution
(the only difference is which date the OUTER caller happens to pass --
today vs. an explicit historical date) -- kept as separate intents only
to preserve the caller's stated purpose in the result for audit
readability, never duplicated logic.

Never silently chooses one conflicting revision: every fail-closed
condition below returns a result with `integrity_error` populated and
`eligible_revision_ids == []`, rather than guessing or raising -- so a
caller (and the Stage 7R.1 scenario report) can inspect WHY, the same
"report findings as data, never crash the whole run" discipline used
throughout this project.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ingestion_bench.revision_authority.model import (
    AuthorityMetadata,
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
    effective_from: date | None = None
    effective_to: date | None = None
    # Populated only when this single record's own derivation failed
    # (e.g. a non-approved revision with effective_from populated) --
    # None does not mean "no error occurred elsewhere in the query", see
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


def _registry_snapshot_hash(
    logical_document_id: str, revisions: list[tuple[str, AuthorityMetadata | None]]
) -> str:
    """SHA-256 over a canonical JSON dump of every revision_id + its
    CURRENT AuthorityMetadata for this logical document, sorted by
    revision_id -- changes whenever ANY authority fact for this document
    changes (new revision, decision, activation, withdrawal, correction),
    never when canonical chunk content changes (this registry never reads
    chunk content)."""
    payload = {
        "logical_document_id": logical_document_id,
        "revisions": {
            revision_id: (metadata.model_dump(mode="json") if metadata is not None else None)
            for revision_id, metadata in sorted(revisions, key=lambda pair: pair[0])
        },
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _label_for(revision_id: str, metadata: AuthorityMetadata | None, as_of_date: date) -> RevisionAuthorityLabel:
    if metadata is None:
        return RevisionAuthorityLabel(revision_id=revision_id, error="revision has no authority metadata recorded")
    state, error = derive_authority_state(metadata, as_of_date)
    return RevisionAuthorityLabel(
        revision_id=revision_id,
        publication_status=metadata.publication_status,
        derived_state=state,
        effective_from=metadata.effective_from,
        effective_to=metadata.effective_to,
        error=error,
    )


def _supersession_inconsistencies(
    identities_and_metadata: list[tuple[str, AuthorityMetadata]],
) -> list[str]:
    """Cross-revision structural check: every supersedes/superseded_by
    link must be mutual and point at a revision that actually exists in
    this document's revision set."""
    by_id = {revision_id: metadata for revision_id, metadata in identities_and_metadata}
    problems: list[str] = []
    for revision_id, metadata in identities_and_metadata:
        if metadata.superseded_by_revision_id is not None:
            target = by_id.get(metadata.superseded_by_revision_id)
            if target is None:
                problems.append(
                    f"{revision_id}.superseded_by_revision_id={metadata.superseded_by_revision_id!r} "
                    "does not exist in this document's revision set"
                )
            elif target.supersedes_revision_id != revision_id:
                problems.append(
                    f"{revision_id}.superseded_by_revision_id={metadata.superseded_by_revision_id!r} but "
                    f"that revision's supersedes_revision_id={target.supersedes_revision_id!r} does not point back"
                )
        if metadata.supersedes_revision_id is not None:
            target = by_id.get(metadata.supersedes_revision_id)
            if target is None:
                problems.append(
                    f"{revision_id}.supersedes_revision_id={metadata.supersedes_revision_id!r} "
                    "does not exist in this document's revision set"
                )
            elif target.superseded_by_revision_id != revision_id:
                problems.append(
                    f"{revision_id}.supersedes_revision_id={metadata.supersedes_revision_id!r} but "
                    f"that revision's superseded_by_revision_id={target.superseded_by_revision_id!r} does not point back"
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
    metadata_by_id = {i.document_revision_id: repository.get_metadata(i.document_revision_id) for i in identities}
    snapshot_hash = _registry_snapshot_hash(logical_document_id, list(metadata_by_id.items()))

    if query_intent in ("current", "as_of"):
        return _resolve_current_or_as_of(
            logical_document_id, query_intent, as_of_date, identities, metadata_by_id, snapshot_hash
        )
    if query_intent == "comparison":
        return _resolve_comparison(
            logical_document_id, as_of_date, requested_revision_ids or [], metadata_by_id, snapshot_hash
        )
    if query_intent == "draft":
        return _resolve_draft(
            logical_document_id, as_of_date, requested_revision_ids or [], metadata_by_id, snapshot_hash
        )
    raise ValueError(f"unknown query_intent: {query_intent!r}")


def _resolve_current_or_as_of(
    logical_document_id: str,
    query_intent: QueryIntent,
    as_of_date: date,
    identities,
    metadata_by_id: dict[str, AuthorityMetadata | None],
    snapshot_hash: str,
) -> QueryResolutionResult:
    all_ids = [i.document_revision_id for i in identities]
    labels = {rid: _label_for(rid, metadata_by_id[rid], as_of_date) for rid in all_ids}

    def _fail(message: str) -> QueryResolutionResult:
        return QueryResolutionResult(
            logical_document_id=logical_document_id, query_intent=query_intent, as_of_date=as_of_date,
            requested_revision_ids=[], eligible_revision_ids=[], excluded=[], authority_labels=labels,
            resolution_explanation=message, registry_snapshot_hash=snapshot_hash, integrity_error=message,
        )

    if not all_ids:
        return _fail(f"logical_document_id={logical_document_id!r} has no registered revisions at all")

    per_record_errors = [f"{rid}: {label.error}" for rid, label in labels.items() if label.error is not None]
    if per_record_errors:
        return _fail("revision authority data is internally inconsistent -- " + "; ".join(per_record_errors))

    present = [(rid, metadata_by_id[rid]) for rid in all_ids if metadata_by_id[rid] is not None]
    inconsistencies = _supersession_inconsistencies(present)
    if inconsistencies:
        return _fail("inconsistent supersession link(s): " + "; ".join(inconsistencies))

    effective_ids = [rid for rid, label in labels.items() if label.derived_state == "effective"]
    if len(effective_ids) > 1:
        return _fail(
            f"{len(effective_ids)} revisions of {logical_document_id!r} are simultaneously effective as of "
            f"{as_of_date}: {sorted(effective_ids)} -- refusing to silently choose one"
        )
    if not effective_ids:
        return _fail(
            f"logical_document_id={logical_document_id!r} has no authoritative effective revision as of {as_of_date}"
        )

    eligible = effective_ids
    excluded = [
        ExclusionReason(revision_id=rid, reason_code=f"not_effective_{label.derived_state}", detail=_exclusion_detail(label, as_of_date))
        for rid, label in labels.items()
        if rid not in eligible
    ]
    explanation = (
        f"{query_intent} query for {logical_document_id!r} as of {as_of_date}: 1 of {len(all_ids)} "
        f"revision(s) effective -- {eligible[0]}"
    )
    return QueryResolutionResult(
        logical_document_id=logical_document_id, query_intent=query_intent, as_of_date=as_of_date,
        requested_revision_ids=[], eligible_revision_ids=eligible, excluded=excluded, authority_labels=labels,
        resolution_explanation=explanation, registry_snapshot_hash=snapshot_hash, integrity_error=None,
    )


def _exclusion_detail(label: RevisionAuthorityLabel, as_of_date: date) -> str:
    if label.derived_state == "approved_future":
        return f"effective_from={label.effective_from} is after as_of_date={as_of_date}"
    if label.derived_state == "superseded":
        return f"effective_to={label.effective_to} is on or before as_of_date={as_of_date}"
    if label.derived_state in ("draft", "under_review", "withdrawn"):
        return f"publication_status={label.derived_state} is never eligible for current/as_of intent"
    return f"derived_state={label.derived_state}"


def _resolve_comparison(
    logical_document_id: str,
    as_of_date: date,
    requested_revision_ids: list[str],
    metadata_by_id: dict[str, AuthorityMetadata | None],
    snapshot_hash: str,
) -> QueryResolutionResult:
    if not requested_revision_ids:
        raise ValueError("comparison intent requires at least one requested_revision_ids entry")

    eligible: list[str] = []
    excluded: list[ExclusionReason] = []
    labels: dict[str, RevisionAuthorityLabel] = {}
    for rid in requested_revision_ids:
        if rid not in metadata_by_id:
            excluded.append(ExclusionReason(revision_id=rid, reason_code="revision_not_found", detail=f"{rid!r} is not a registered revision of {logical_document_id!r}"))
            labels[rid] = RevisionAuthorityLabel(revision_id=rid, error="revision not found")
            continue
        label = _label_for(rid, metadata_by_id[rid], as_of_date)
        labels[rid] = label
        # Comparison PERMITS superseded/draft/under_review/withdrawn --
        # every explicitly requested, existing revision is eligible,
        # retaining its own authority label (never silently coerced).
        eligible.append(rid)

    explanation = (
        f"comparison query for {logical_document_id!r}: {len(eligible)} of {len(requested_revision_ids)} "
        f"requested revision(s) found and returned with their own authority labels"
    )
    return QueryResolutionResult(
        logical_document_id=logical_document_id, query_intent="comparison", as_of_date=as_of_date,
        requested_revision_ids=requested_revision_ids, eligible_revision_ids=eligible, excluded=excluded,
        authority_labels=labels, resolution_explanation=explanation, registry_snapshot_hash=snapshot_hash,
        integrity_error=None,
    )


def _resolve_draft(
    logical_document_id: str,
    as_of_date: date,
    requested_revision_ids: list[str],
    metadata_by_id: dict[str, AuthorityMetadata | None],
    snapshot_hash: str,
) -> QueryResolutionResult:
    if not requested_revision_ids:
        raise ValueError("draft intent requires at least one requested_revision_ids entry")

    eligible: list[str] = []
    excluded: list[ExclusionReason] = []
    labels: dict[str, RevisionAuthorityLabel] = {}
    for rid in requested_revision_ids:
        if rid not in metadata_by_id:
            excluded.append(ExclusionReason(revision_id=rid, reason_code="revision_not_found", detail=f"{rid!r} is not a registered revision of {logical_document_id!r}"))
            labels[rid] = RevisionAuthorityLabel(revision_id=rid, error="revision not found")
            continue
        label = _label_for(rid, metadata_by_id[rid], as_of_date)
        labels[rid] = label
        if label.derived_state in ("draft", "under_review"):
            eligible.append(rid)
        else:
            excluded.append(
                ExclusionReason(
                    revision_id=rid, reason_code="not_draft_or_under_review",
                    detail=f"derived_state={label.derived_state!r} -- draft intent never mixes non-draft revisions in",
                )
            )

    explanation = (
        f"draft query for {logical_document_id!r}: {len(eligible)} of {len(requested_revision_ids)} requested "
        f"revision(s) are draft/under_review and eligible"
    )
    return QueryResolutionResult(
        logical_document_id=logical_document_id, query_intent="draft", as_of_date=as_of_date,
        requested_revision_ids=requested_revision_ids, eligible_revision_ids=eligible, excluded=excluded,
        authority_labels=labels, resolution_explanation=explanation, registry_snapshot_hash=snapshot_hash,
        integrity_error=None,
    )
