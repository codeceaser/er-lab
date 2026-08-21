"""Stage 7C.1: the deterministic validator (Revision 6 SS4) and the
deterministic claim-derived link derivation (SS3.7).

Two absolute rules govern this module.

**SS4.0 -- validation governs claims, never membership.** No validation
outcome may remove or alter a facet's deterministic membership, its source
chunks, its anchors, or its anchor postings. This module therefore never
returns, mutates or even accepts a projection record; it only classifies model
output. That is a structural guarantee, not a promise.

**SS4.3 / SS4.4 / SS4.5 -- mechanical validity is NOT semantic correctness.**
Citation validity proves a quoted span exists; it does not prove the inferred
predicate represents the passage. Summary reference validity proves a sentence
points at accepted claims; it does not prove it represents them. Alias span
validity proves a string occurs; it does not prove it names this entity. Those
three judgements belong to the OWNER and are never made here -- nothing in this
module writes a semantic verdict.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ingestion_bench.wiki_projection import compiler as compiler_module
from ingestion_bench.wiki_projection import identity
from ingestion_bench.wiki_projection.compiler import FacetCompilationOutput
from ingestion_bench.wiki_projection.model import Facet, PageIdentity, WikiSection

ValidationStatus = Literal["accepted", "rejected", "uncertain", "out_of_page_scope"]
AliasStatus = Literal["supported", "uncertain", "rejected"]

# SS4.1.11 -- the CLOSED status lexicon. Never extended per corpus or per run.
# Rejected in a predicate / claim_text / summary text UNLESS the term appears
# inside an exact quoted source span.
STATUS_LEXICON: tuple[str, ...] = (
    "current", "currently", "effective", "in force", "active", "latest", "now applies",
    "supersedes", "superseded", "up to date", "up-to-date", "presently", "at present",
)

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_whitespace(text: str) -> str:
    """The ONE declared whitespace normalization used for exact-substring
    citation checks (SS4.1.3)."""
    return _WHITESPACE_RE.sub(" ", text).strip()


def normalize_triple_part(text: str) -> str:
    """Normalization used for duplicate/contradiction detection and for page
    coherence. Uses the SAME identity normalization that produced page keys
    (SS3.2), so `C-88` and `C-88A` can never satisfy each other's comparison."""
    identifiers = identity.identifiers_in(text)
    if len(identifiers) == 1:
        return next(iter(identifiers))
    return identity.normalize_phrase(text)


def resolve_page_key(text: str, page_keys: set[str]) -> str | None:
    """Resolve a claim endpoint to an EXISTING page key, or None.

    Strict by design (SS3.2): a single contained identifier resolves to its
    identifier page; otherwise the exact normalized phrase must already be a
    page key. Nothing is invented, and an endpoint that resolves to no page
    emits no link and is counted as `unlinkable_claim_endpoint` (SS3.7).
    """
    identifiers = identity.identifiers_in(text)
    if len(identifiers) == 1:
        candidate = f"IDENT:{next(iter(identifiers))}"
        if candidate in page_keys:
            return candidate
        return None
    if len(identifiers) > 1:
        return None  # ambiguous endpoint -- never guess which entity is meant
    candidate = f"PHRASE:{identity.normalize_phrase(text)}"
    return candidate if candidate in page_keys else None


# --- validated records -------------------------------------------------------


class ValidatedAlias(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alias_id: str
    page_key: str
    document_revision_id: str
    alias: str
    supporting_chunk_ids: list[str]
    supporting_quotes: list[str]
    # MECHANICAL span validity only. Never semantic correctness (SS4.5).
    status: AliasStatus
    span_valid: bool
    rejection_reasons: list[str] = Field(default_factory=list)
    derivation: Literal["model_derived"] = "model_derived"
    # Filled by the OWNER, never here. None == not yet adjudicated.
    owner_semantic_verdict: None = None


class ValidatedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    page_key: str
    document_revision_id: str
    subject: str
    predicate: str
    object: str
    claim_text: str
    supporting_chunk_ids: list[str]
    supporting_quotes: list[str]
    derivation: Literal["model_derived"] = "model_derived"

    # Assigned by THIS deterministic validator, never by the model (SS3.4).
    validation_status: ValidationStatus
    rejection_reasons: list[str] = Field(default_factory=list)

    citation_valid: bool = False
    # SS4.1.15 page coherence, and whether it rested on an alias.
    coherence_basis: str | None = None
    depends_on_alias: bool = False
    alias_dependency_ids: list[str] = Field(default_factory=list)
    # Set when the claim is only provisionally accepted pending the owner's
    # alias verdict (SS4.6 pass 3 cannot run before adjudication).
    pending_alias_adjudication: bool = False

    duplicate_of: str | None = None
    contradicts_claim_ids: list[str] = Field(default_factory=list)
    # Filled by the OWNER, never here.
    owner_semantic_verdict: None = None


class ValidatedSummarySentence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sentence_id: str
    page_key: str
    document_revision_id: str
    text: str
    supported_claim_ids: list[str]
    derivation: Literal["model_derived"] = "model_derived"
    # MECHANICAL reference validity only. Never summary correctness (SS4.4).
    reference_valid: bool
    rejection_reasons: list[str] = Field(default_factory=list)
    # Filled by the OWNER, never here.
    owner_semantic_verdict: None = None


class DerivedLink(BaseModel):
    """A claim-derived link (SS3.7). It may supply type, direction, routing
    priority, explanation and citations. It may NEVER create the underlying
    facet or page membership."""

    model_config = ConfigDict(extra="forbid")

    link_id: str
    claim_id: str
    subject_page_key: str
    predicate: str
    object_page_key: str
    source_citations: dict
    document_revision_id: str
    traversal_direction: Literal["forward", "inverse"]
    is_authoritative_lineage: Literal[False] = False


class FacetValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_key: str
    document_revision_id: str
    run_id: int

    aliases: list[ValidatedAlias]
    claims: list[ValidatedClaim]
    summary_sentences: list[ValidatedSummarySentence]
    derived_links: list[DerivedLink]

    unlinkable_claim_endpoints: list[dict] = Field(default_factory=list)
    unresolved_identity_mentions: list[str] = Field(default_factory=list)

    ceiling_breaches: list[str] = Field(default_factory=list)
    facet_failed: bool = False
    generation_failed: bool = False
    generation_error: str | None = None

    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None
    latency_seconds: float = 0.0
    model_identity: str = ""
    prompt_version: str = ""
    prompt_sha256: str = ""


def _link_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _status_terms_outside_quotes(text: str, quotes: list[str]) -> list[str]:
    """SS4.1.11: a status term is permitted ONLY when it sits inside an exact
    quoted source span. Returns the terms that do not."""
    lowered = text.casefold()
    quoted = " ".join(q.casefold() for q in quotes)
    offenders: list[str] = []
    for term in STATUS_LEXICON:
        if re.search(rf"\b{re.escape(term)}\b", lowered) and not re.search(rf"\b{re.escape(term)}\b", quoted):
            offenders.append(term)
    return sorted(set(offenders))


def validate_facet(
    output: FacetCompilationOutput,
    *,
    facet: Facet,
    page: PageIdentity,
    sections_by_chunk: dict[str, WikiSection],
    all_page_keys: set[str],
) -> FacetValidationResult:
    """Run every deterministic Revision 6 SS4.1 rule over ONE facet's model
    output, then derive links from accepted claims (SS3.7).

    Makes NO semantic judgement and writes NO owner verdict. Nothing is
    discarded silently: every rejection carries its reason (SS4.1.14).
    """
    result_kwargs = dict(
        page_key=output.page_key, document_revision_id=output.document_revision_id, run_id=output.run_id,
        input_tokens=output.input_tokens, output_tokens=output.output_tokens,
        estimated_cost_usd=output.estimated_cost_usd, latency_seconds=output.latency_seconds,
        model_identity=output.model_identity, prompt_version=output.prompt_version,
        prompt_sha256=output.prompt_sha256,
    )

    if output.generation_failed:
        return FacetValidationResult(
            **result_kwargs, aliases=[], claims=[], summary_sentences=[], derived_links=[],
            facet_failed=True, generation_failed=True, generation_error=output.generation_error,
        )

    declared_chunks = set(facet.chunk_ids)
    normalized_identity = normalize_triple_part(page.normalized_identity)
    ceiling_breaches: list[str] = []

    # --- SS3.9 ceilings ----------------------------------------------------
    if len(output.aliases) > compiler_module.MAX_ALIASES_PER_FACET:
        ceiling_breaches.append(f"aliases {len(output.aliases)} > {compiler_module.MAX_ALIASES_PER_FACET}")
    if len(output.summary_sentences) > compiler_module.MAX_SUMMARY_SENTENCES_PER_FACET:
        ceiling_breaches.append(
            f"summary_sentences {len(output.summary_sentences)} > {compiler_module.MAX_SUMMARY_SENTENCES_PER_FACET}"
        )
    if output.input_tokens is not None and output.input_tokens > compiler_module.MAX_INPUT_TOKENS_PER_FACET:
        ceiling_breaches.append(f"input_tokens {output.input_tokens} > {compiler_module.MAX_INPUT_TOKENS_PER_FACET}")
    if output.output_tokens is not None and output.output_tokens > compiler_module.MAX_OUTPUT_TOKENS_PER_FACET:
        ceiling_breaches.append(f"output_tokens {output.output_tokens} > {compiler_module.MAX_OUTPUT_TOKENS_PER_FACET}")

    # --- aliases: SPAN validity only (SS4.5) -------------------------------
    validated_aliases: list[ValidatedAlias] = []
    for index, raw in enumerate(output.aliases):
        reasons: list[str] = []
        for chunk_id in raw.supporting_chunk_ids:
            if chunk_id not in sections_by_chunk:
                reasons.append(f"cited chunk {chunk_id!r} does not exist")
            elif chunk_id not in declared_chunks:
                reasons.append(f"cited chunk {chunk_id!r} is outside this facet's declared input set")
        span_valid = bool(raw.supporting_quotes) and not reasons
        for quote in raw.supporting_quotes:
            found = any(
                normalize_whitespace(quote) in normalize_whitespace(sections_by_chunk[cid].source_text)
                for cid in raw.supporting_chunk_ids
                if cid in sections_by_chunk
            )
            if not found:
                span_valid = False
                reasons.append(f"alias quote {quote!r} is not an exact substring of a cited chunk")
        # An alias must also actually contain the alias string it claims.
        if span_valid and not any(
            normalize_whitespace(raw.alias) in normalize_whitespace(sections_by_chunk[cid].source_text)
            for cid in raw.supporting_chunk_ids
            if cid in sections_by_chunk
        ):
            span_valid = False
            reasons.append(f"alias string {raw.alias!r} does not occur in a cited chunk")

        # SS3.3 / SS4.1.7: an alias may never bridge two distinct identifiers.
        alias_identifiers = identity.identifiers_in(raw.alias)
        page_identifiers = identity.identifiers_in(page.normalized_identity)
        if alias_identifiers and page_identifiers and alias_identifiers != page_identifiers:
            span_valid = False
            reasons.append(
                f"alias identifiers {sorted(alias_identifiers)} != page identifiers {sorted(page_identifiers)} "
                "-- distinct identifiers are never merged"
            )

        status: AliasStatus = "supported" if (raw.status == "supported" and span_valid) else "uncertain"
        if reasons and raw.status == "supported":
            status = "rejected" if not span_valid else status

        validated_aliases.append(
            ValidatedAlias(
                alias_id=f"{output.page_key}|{output.document_revision_id}|alias|{index}",
                page_key=output.page_key, document_revision_id=output.document_revision_id,
                alias=raw.alias, supporting_chunk_ids=list(raw.supporting_chunk_ids),
                supporting_quotes=list(raw.supporting_quotes),
                status=status, span_valid=span_valid, rejection_reasons=sorted(set(reasons)),
            )
        )

    # Aliases usable for identifier grounding / page-identity matching in
    # PASS 1 (SS4.6): span-valid `supported` only. Semantic adjudication is the
    # owner's, and until it returns, any claim resting solely on one of these
    # is marked pending rather than settled.
    pass1_alias_by_norm: dict[str, ValidatedAlias] = {
        normalize_triple_part(a.alias): a for a in validated_aliases if a.status == "supported"
    }

    # --- claims -------------------------------------------------------------
    validated_claims: list[ValidatedClaim] = []
    seen_triples: dict[tuple[str, str, str], str] = {}
    subject_predicate: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)

    for raw in output.claims:
        reasons: list[str] = []

        # SS4.1.1 / SS4.1.2 / SS4.1.4 -- existence and REVISION SCOPE.
        for chunk_id in raw.supporting_chunk_ids:
            if chunk_id not in sections_by_chunk:
                reasons.append(f"cited chunk {chunk_id!r} does not exist")
            elif chunk_id not in declared_chunks:
                reasons.append(
                    f"cited chunk {chunk_id!r} is outside this facet's declared input set "
                    "(revision-scope contamination)"
                )
            elif sections_by_chunk[chunk_id].document_revision_id != output.document_revision_id:
                reasons.append(f"cited chunk {chunk_id!r} belongs to another revision")
        if not raw.supporting_chunk_ids:
            reasons.append("claim cites no chunk")

        # SS4.1.3 -- EXACT substring citation.
        citation_valid = bool(raw.supporting_quotes) and not reasons
        for quote in raw.supporting_quotes:
            found = any(
                normalize_whitespace(quote) in normalize_whitespace(sections_by_chunk[cid].source_text)
                for cid in raw.supporting_chunk_ids
                if cid in sections_by_chunk
            )
            if not found:
                citation_valid = False
                reasons.append(f"supporting quote {quote!r} is not an exact substring of a cited chunk")
        if not raw.supporting_quotes:
            citation_valid = False
            reasons.append("claim supplies no supporting quote")

        # SS4.1.5 -- source_refs resolve (via the section view).
        for chunk_id in raw.supporting_chunk_ids:
            if chunk_id in sections_by_chunk and not sections_by_chunk[chunk_id].source_refs:
                reasons.append(f"cited chunk {chunk_id!r} has no resolvable source_ref")

        # SS4.1.6 -- hallucinated-identifier guard.
        cited_text = " ".join(
            sections_by_chunk[cid].source_text for cid in raw.supporting_chunk_ids if cid in sections_by_chunk
        )
        evidence_identifiers = identity.identifiers_in(cited_text)
        mentioned = identity.identifiers_in(" ".join([raw.claim_text, raw.subject, raw.object]))
        alias_identifiers: set[str] = set()
        for alias in pass1_alias_by_norm.values():
            alias_identifiers |= identity.identifiers_in(alias.alias)
        for identifier in sorted(mentioned - evidence_identifiers - alias_identifiers):
            reasons.append(f"identifier {identifier!r} does not occur in the cited evidence")

        # SS4.1.11 -- no timeless status.
        offenders = _status_terms_outside_quotes(
            " ".join([raw.predicate, raw.claim_text]), raw.supporting_quotes
        )
        for term in offenders:
            reasons.append(f"status term {term!r} used outside an exact quoted source span")

        # SS4.1.15 -- PAGE COHERENCE.
        subject_norm = normalize_triple_part(raw.subject)
        object_norm = normalize_triple_part(raw.object)
        coherence_basis: str | None = None
        depends_on_alias = False
        alias_dependency_ids: list[str] = []
        if subject_norm == normalized_identity:
            coherence_basis = "identity_subject"
        elif object_norm == normalized_identity:
            coherence_basis = "identity_object"
        elif subject_norm in pass1_alias_by_norm:
            coherence_basis = "alias_subject"
            depends_on_alias = True
            alias_dependency_ids = [pass1_alias_by_norm[subject_norm].alias_id]
        elif object_norm in pass1_alias_by_norm:
            coherence_basis = "alias_object"
            depends_on_alias = True
            alias_dependency_ids = [pass1_alias_by_norm[object_norm].alias_id]

        status: ValidationStatus
        if coherence_basis is None:
            status = "out_of_page_scope"
            reasons.append(
                f"neither subject {raw.subject!r} nor object {raw.object!r} is this page's identity "
                f"({page.normalized_identity!r}) or a supported alias of it"
            )
        elif reasons:
            status = "rejected"
        else:
            status = "accepted"

        validated_claims.append(
            ValidatedClaim(
                claim_id=raw.claim_id, page_key=output.page_key,
                document_revision_id=output.document_revision_id,
                subject=raw.subject, predicate=raw.predicate, object=raw.object, claim_text=raw.claim_text,
                supporting_chunk_ids=list(raw.supporting_chunk_ids),
                supporting_quotes=list(raw.supporting_quotes),
                validation_status=status, rejection_reasons=sorted(set(reasons)),
                citation_valid=citation_valid, coherence_basis=coherence_basis,
                depends_on_alias=depends_on_alias, alias_dependency_ids=alias_dependency_ids,
                pending_alias_adjudication=(status == "accepted" and depends_on_alias),
            )
        )

    # SS4.1.12 -- duplicates and contradictions, WITHIN this facet.
    for claim in validated_claims:
        if claim.validation_status != "accepted":
            continue
        triple = (normalize_triple_part(claim.subject), claim.predicate.strip().casefold(),
                  normalize_triple_part(claim.object))
        if triple in seen_triples:
            claim.duplicate_of = seen_triples[triple]
            # Citations of BOTH are retained; the duplicate is not silently dropped.
            original = next(c for c in validated_claims if c.claim_id == seen_triples[triple])
            for chunk_id in claim.supporting_chunk_ids:
                if chunk_id not in original.supporting_chunk_ids:
                    original.supporting_chunk_ids.append(chunk_id)
            for quote in claim.supporting_quotes:
                if quote not in original.supporting_quotes:
                    original.supporting_quotes.append(quote)
        else:
            seen_triples[triple] = claim.claim_id
        subject_predicate[(triple[0], triple[1])].append((claim.claim_id, triple[2]))

    for (_subject, _predicate), entries in subject_predicate.items():
        objects = {obj for _cid, obj in entries}
        if len(objects) > 1:
            ids = sorted(cid for cid, _obj in entries)
            for claim in validated_claims:
                if claim.claim_id in ids and claim.validation_status == "accepted":
                    claim.validation_status = "uncertain"
                    claim.contradicts_claim_ids = [c for c in ids if c != claim.claim_id]
                    claim.rejection_reasons = sorted(
                        set(claim.rejection_reasons)
                        | {"contradictory: same (subject, predicate) with a different object within this facet"}
                    )

    accepted_and_uncertain = [c for c in validated_claims if c.validation_status in ("accepted", "uncertain")]
    if len(accepted_and_uncertain) > compiler_module.MAX_CLAIMS_PER_FACET:
        ceiling_breaches.append(
            f"accepted+uncertain claims {len(accepted_and_uncertain)} > {compiler_module.MAX_CLAIMS_PER_FACET}"
        )

    accepted_ids = {c.claim_id for c in validated_claims if c.validation_status == "accepted"}

    # --- summary sentences: REFERENCE validity only (SS4.1.8, SS4.4) -------
    validated_summaries: list[ValidatedSummarySentence] = []
    for raw in output.summary_sentences:
        reasons = []
        referenced_here = [cid for cid in raw.supported_claim_ids if cid in accepted_ids]
        if not referenced_here:
            reasons.append("references no accepted claim on this facet")
        for claim_id in raw.supported_claim_ids:
            if claim_id not in {c.claim_id for c in validated_claims}:
                reasons.append(f"references unknown claim {claim_id!r}")
        offenders = _status_terms_outside_quotes(
            raw.text,
            [q for c in validated_claims if c.claim_id in raw.supported_claim_ids for q in c.supporting_quotes],
        )
        for term in offenders:
            reasons.append(f"status term {term!r} used outside an exact quoted source span")
        validated_summaries.append(
            ValidatedSummarySentence(
                sentence_id=raw.sentence_id, page_key=output.page_key,
                document_revision_id=output.document_revision_id,
                text=raw.text, supported_claim_ids=list(raw.supported_claim_ids),
                reference_valid=not reasons, rejection_reasons=sorted(set(reasons)),
            )
        )

    # --- SS3.7 deterministic link derivation, from ACCEPTED claims only ----
    derived_links: list[DerivedLink] = []
    unlinkable: list[dict] = []
    unresolved_mentions: list[str] = []
    for claim in validated_claims:
        if claim.validation_status != "accepted":
            continue
        subject_page = resolve_page_key(claim.subject, all_page_keys)
        object_page = resolve_page_key(claim.object, all_page_keys)
        for role, value, resolved in (("subject", claim.subject, subject_page), ("object", claim.object, object_page)):
            if resolved is None:
                unlinkable.append({"claim_id": claim.claim_id, "endpoint_role": role, "endpoint_text": value})
                unresolved_mentions.append(value)
        if subject_page is None or object_page is None:
            continue
        citations = {
            "supporting_chunk_ids": list(claim.supporting_chunk_ids),
            "supporting_quotes": list(claim.supporting_quotes),
        }
        for direction in ("forward", "inverse"):
            derived_links.append(
                DerivedLink(
                    link_id=_link_id("claim_derived", claim.claim_id, subject_page, object_page, direction),
                    claim_id=claim.claim_id, subject_page_key=subject_page,
                    predicate=claim.predicate,  # VERBATIM; an inverse predicate is never fabricated
                    object_page_key=object_page, source_citations=citations,
                    document_revision_id=output.document_revision_id,
                    traversal_direction=direction,  # type: ignore[arg-type]
                )
            )

    return FacetValidationResult(
        **result_kwargs,
        aliases=validated_aliases, claims=validated_claims, summary_sentences=validated_summaries,
        derived_links=sorted(derived_links, key=lambda link: link.link_id),
        unlinkable_claim_endpoints=unlinkable,
        unresolved_identity_mentions=sorted(set(unresolved_mentions)),
        ceiling_breaches=sorted(set(ceiling_breaches)),
        facet_failed=bool(ceiling_breaches),
    )


def assert_membership_unchanged(before: list[Facet], after: list[Facet]) -> None:
    """SS4.0 / SS2.2 hard guard: prove that running the compiler and the
    validator changed no facet membership at all. Raises rather than reports,
    because a violation invalidates the entire stage."""
    before_map = {(f.page_key, f.document_revision_id): f.membership_hash for f in before}
    after_map = {(f.page_key, f.document_revision_id): f.membership_hash for f in after}
    if before_map != after_map:
        added = sorted(set(after_map) - set(before_map))
        removed = sorted(set(before_map) - set(after_map))
        changed = sorted(k for k in set(before_map) & set(after_map) if before_map[k] != after_map[k])
        raise AssertionError(
            "MEMBERSHIP INDEPENDENCE VIOLATED (Revision 6 SS2.2/SS4.0): "
            f"added={added} removed={removed} changed={changed}"
        )
