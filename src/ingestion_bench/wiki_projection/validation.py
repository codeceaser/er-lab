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
import json
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


def derive_links(
    claims: list[ValidatedClaim], *, document_revision_id: str, all_page_keys: set[str]
) -> tuple[list[DerivedLink], list[dict], list[str]]:
    """SS3.7 deterministic link derivation over a set of ELIGIBLE claims.

    Factored out of `validate_facet` so that pass 3 (SS4.6) re-derives links with
    exactly this code after owner withdrawals, rather than filtering the pass-1
    link set with a second, divergent implementation.

    The caller decides which claims are eligible. Pass 1 passes mechanically
    accepted claims; pass 3 passes accepted claims that also survived owner
    adjudication.
    """
    links: list[DerivedLink] = []
    unlinkable: list[dict] = []
    unresolved: list[str] = []

    for claim in claims:
        subject_page = resolve_page_key(claim.subject, all_page_keys)
        object_page = resolve_page_key(claim.object, all_page_keys)
        for role, value, resolved in (
            ("subject", claim.subject, subject_page),
            ("object", claim.object, object_page),
        ):
            if resolved is None:
                unlinkable.append({"claim_id": claim.claim_id, "endpoint_role": role, "endpoint_text": value})
                unresolved.append(value)
        if subject_page is None or object_page is None:
            continue
        citations = {
            "supporting_chunk_ids": list(claim.supporting_chunk_ids),
            "supporting_quotes": list(claim.supporting_quotes),
        }
        for direction in ("forward", "inverse"):
            links.append(
                DerivedLink(
                    link_id=_link_id("claim_derived", claim.claim_id, subject_page, object_page, direction),
                    claim_id=claim.claim_id, subject_page_key=subject_page,
                    predicate=claim.predicate,  # VERBATIM; an inverse predicate is never fabricated
                    object_page_key=object_page, source_citations=citations,
                    document_revision_id=document_revision_id,
                    traversal_direction=direction,  # type: ignore[arg-type]
                )
            )
    return sorted(links, key=lambda link: link.link_id), unlinkable, sorted(set(unresolved))


# --- adjudication item identity (shared, single source of truth) -------------
#
# These produce the EXACT ids already present in the committed Run-1 packet, so
# the owner's filled packet keys back onto the same items. `adjudication.py`
# builds the packet with them and pass 3 resolves verdicts with them; a test
# pins both against the committed packet.


def claim_item_id(facet_key: str, claim_id: str) -> str:
    return f"CLAIM::{facet_key}::{claim_id}"


def alias_item_id(facet_key: str, alias_id: str) -> str:
    return f"ALIAS::{facet_key}::{alias_id.rsplit('|', 1)[-1]}"


def summary_item_id(facet_key: str, sentence_id: str) -> str:
    return f"SUMMARY::{facet_key}::{sentence_id}"


def facet_key_of(page_key: str, document_revision_id: str) -> str:
    return f"{page_key}|{document_revision_id}"


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
    derived_links, unlinkable, unresolved_mentions = derive_links(
        [c for c in validated_claims if c.validation_status == "accepted"],
        document_revision_id=output.document_revision_id, all_page_keys=all_page_keys,
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


# =============================================================================
# PASS 3 -- deterministic re-validation after owner adjudication (SS4.6)
# =============================================================================
#
# SS4.6 enumerates the alias cascade and summary withdrawal, and then states the
# binding invariant that governs all three adjudicated object types:
#
#     "Facet embeddings are written only after pass 3. Nothing that failed
#      adjudication reaches a vector, a summary, or a derived link."
#
# Those three consequences are exactly the three privileges SS4.2 grants to an
# `accepted` claim ("eligible for the embedding payload, for supporting a
# summary sentence, and for deriving links"), so a claim that failed
# adjudication loses all three. The enumeration in SS4.6 does not spell that out
# for claims; the invariant does, and it controls.
#
# A withdrawn claim KEEPS its mechanical `validation_status`. Mechanical status
# records a mechanical fact and SS4.2 requires it to stay in the audit record;
# withdrawal is a separate, owner-originated outcome, tracked separately so
# neither erases the other.
#
# Membership is untouched by all three passes (SS4.0) -- nothing in this section
# reads or returns a projection record.

OwnerVerdict = Literal["CORRECT", "INCORRECT", "UNVERIFIABLE"]
_PASSING_VERDICT: OwnerVerdict = "CORRECT"


class AdjudicationVerdictSet(BaseModel):
    """The owner's verdicts, keyed by `adjudication_item_id`.

    An item with no recorded verdict is treated as NOT adjudicated, which is not
    the same as failing: `is_complete_for` reports what is still outstanding so a
    caller can refuse to build a final representation from a partial set.
    """

    model_config = ConfigDict(extra="forbid")

    verdicts: dict[str, OwnerVerdict] = Field(default_factory=dict)
    reasons: dict[str, str] = Field(default_factory=dict)

    def verdict_for(self, item_id: str) -> OwnerVerdict | None:
        return self.verdicts.get(item_id)

    def passes(self, item_id: str) -> bool:
        """True only for an explicit CORRECT. An absent verdict is not a pass."""
        return self.verdicts.get(item_id) == _PASSING_VERDICT

    def failed(self, item_id: str) -> bool:
        """INCORRECT or UNVERIFIABLE -- SS3.3/SS3.5 treat both as failing."""
        verdict = self.verdicts.get(item_id)
        return verdict is not None and verdict != _PASSING_VERDICT

    def verdict_set_sha256(self) -> str:
        """The verdict-set hash SS5.1/SS6.2 fold into the facet hash and record
        with every embedding."""
        blob = json.dumps({"verdicts": self.verdicts}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def missing_items(self, required_item_ids: list[str]) -> list[str]:
        return sorted(i for i in required_item_ids if i not in self.verdicts)


class Pass3FacetResult(BaseModel):
    """One facet's state after pass 3. Purely derived; stores no projection
    record and no embedding."""

    model_config = ConfigDict(extra="forbid")

    page_key: str
    document_revision_id: str
    facet_key: str

    withdrawn_alias_ids: list[str] = Field(default_factory=list)
    withdrawn_claim_ids: list[str] = Field(default_factory=list)
    withdrawn_summary_ids: list[str] = Field(default_factory=list)
    demoted_to_out_of_page_scope: list[str] = Field(default_factory=list)
    demoted_ungrounded_identifier: list[str] = Field(default_factory=list)
    withdrawal_reasons: dict[str, str] = Field(default_factory=dict)

    payload_eligible_alias_texts: list[str] = Field(default_factory=list)
    surviving_accepted_claim_ids: list[str] = Field(default_factory=list)
    surviving_summary_sentence_ids: list[str] = Field(default_factory=list)
    derived_links: list[DerivedLink] = Field(default_factory=list)

    counts_before: dict[str, int] = Field(default_factory=dict)
    counts_after: dict[str, int] = Field(default_factory=dict)


def apply_pass3(
    validation: FacetValidationResult,
    *,
    page: PageIdentity,
    sections_by_chunk: dict[str, WikiSection],
    all_page_keys: set[str],
    verdicts: AdjudicationVerdictSet,
) -> Pass3FacetResult:
    """Deterministic re-validation of ONE facet after owner adjudication.

    Order matters, because the steps cascade:
      1. withdraw aliases that failed adjudication;
      2. re-apply SS4.1.15 page coherence without them -- a claim whose coherence
         rested SOLELY on a withdrawn alias becomes `out_of_page_scope`;
      3. re-apply SS4.1.6 identifier grounding without them -- a claim whose
         grounding rested solely on one is demoted per SS4.2;
      4. withdraw claims whose OWN verdict failed (the invariant above);
      5. withdraw summary sentences whose own verdict failed, AND any sentence
         left with no surviving accepted claim to reference (SS4.1.8) -- a
         CORRECT verdict does not rescue a sentence whose support was withdrawn;
      6. re-derive claim-derived links from the surviving claims only.

    Makes no semantic judgement of its own: every decision is either a rule from
    SS4 or a verdict the owner supplied.
    """
    facet_key = facet_key_of(validation.page_key, validation.document_revision_id)
    reasons: dict[str, str] = {}

    accepted_before = [c for c in validation.claims if c.validation_status == "accepted"]
    supported_aliases = [a for a in validation.aliases if a.status == "supported"]
    reference_valid_summaries = [s for s in validation.summary_sentences if s.reference_valid]

    # --- 1. alias withdrawal -------------------------------------------------
    withdrawn_alias_ids: list[str] = []
    surviving_aliases: list[ValidatedAlias] = []
    for alias in supported_aliases:
        item_id = alias_item_id(facet_key, alias.alias_id)
        if verdicts.passes(item_id):
            surviving_aliases.append(alias)
        else:
            withdrawn_alias_ids.append(alias.alias_id)
            verdict = verdicts.verdict_for(item_id)
            reasons[alias.alias_id] = (
                f"alias withdrawn: owner verdict {verdict or 'ABSENT'} "
                "(SS4.5 -- a supported alias that fails semantic adjudication may not enter the "
                "payload or participate in page-identity matching)"
            )
    withdrawn_alias_id_set = set(withdrawn_alias_ids)
    surviving_alias_norms = {normalize_triple_part(a.alias) for a in surviving_aliases}
    surviving_alias_identifiers: set[str] = set()
    for alias in surviving_aliases:
        surviving_alias_identifiers |= identity.identifiers_in(alias.alias)

    normalized_identity = normalize_triple_part(page.normalized_identity)

    demoted_scope: list[str] = []
    demoted_grounding: list[str] = []
    withdrawn_claim_ids: list[str] = []
    surviving_claims: list[ValidatedClaim] = []

    for claim in accepted_before:
        # --- 2. re-apply page coherence without withdrawn aliases -----------
        if claim.depends_on_alias and set(claim.alias_dependency_ids) <= withdrawn_alias_id_set:
            subject_norm = normalize_triple_part(claim.subject)
            object_norm = normalize_triple_part(claim.object)
            still_coherent = (
                subject_norm == normalized_identity
                or object_norm == normalized_identity
                or subject_norm in surviving_alias_norms
                or object_norm in surviving_alias_norms
            )
            if not still_coherent:
                demoted_scope.append(claim.claim_id)
                reasons[claim.claim_id] = (
                    "demoted to out_of_page_scope: its SS4.1.15 page coherence rested solely on an "
                    "alias the owner withdrew"
                )
                continue

        # --- 3. re-apply identifier grounding without withdrawn aliases -----
        cited_text = " ".join(
            sections_by_chunk[cid].source_text for cid in claim.supporting_chunk_ids if cid in sections_by_chunk
        )
        evidence_identifiers = identity.identifiers_in(cited_text)
        mentioned = identity.identifiers_in(" ".join([claim.claim_text, claim.subject, claim.object]))
        ungrounded = sorted(mentioned - evidence_identifiers - surviving_alias_identifiers)
        if ungrounded:
            demoted_grounding.append(claim.claim_id)
            reasons[claim.claim_id] = (
                f"demoted per SS4.2: identifier(s) {ungrounded} were grounded only by an alias the owner "
                "withdrew (SS4.1.6)"
            )
            continue

        # --- 4. withdraw claims whose OWN verdict failed --------------------
        item_id = claim_item_id(facet_key, claim.claim_id)
        if not verdicts.passes(item_id):
            withdrawn_claim_ids.append(claim.claim_id)
            verdict = verdicts.verdict_for(item_id)
            reasons[claim.claim_id] = (
                f"claim withdrawn: owner verdict {verdict or 'ABSENT'} "
                "(SS4.6 -- nothing that failed adjudication reaches a vector, a summary, or a derived link)"
            )
            continue

        surviving_claims.append(claim)

    surviving_claim_ids = {c.claim_id for c in surviving_claims}

    # --- 5. summary withdrawal ----------------------------------------------
    withdrawn_summary_ids: list[str] = []
    surviving_summaries: list[ValidatedSummarySentence] = []
    for sentence in reference_valid_summaries:
        item_id = summary_item_id(facet_key, sentence.sentence_id)
        if not verdicts.passes(item_id):
            withdrawn_summary_ids.append(sentence.sentence_id)
            verdict = verdicts.verdict_for(item_id)
            reasons[sentence.sentence_id] = (
                f"summary withdrawn: owner verdict {verdict or 'ABSENT'} (SS3.5 -- only a sentence "
                "adjudicated `correct` may enter the payload)"
            )
            continue
        # SS4.1.8 re-applied: a CORRECT sentence still needs >= 1 SURVIVING
        # accepted claim on this facet. Its own verdict does not rescue it.
        if not (set(sentence.supported_claim_ids) & surviving_claim_ids):
            withdrawn_summary_ids.append(sentence.sentence_id)
            reasons[sentence.sentence_id] = (
                "summary withdrawn: adjudicated CORRECT, but every claim it references was withdrawn, so "
                "SS4.1.8 reference validity no longer holds"
            )
            continue
        surviving_summaries.append(sentence)

    # --- 6. re-derive links from the SURVIVING claims only -------------------
    derived_links, _unlinkable, _unresolved = derive_links(
        surviving_claims, document_revision_id=validation.document_revision_id, all_page_keys=all_page_keys,
    )

    return Pass3FacetResult(
        page_key=validation.page_key, document_revision_id=validation.document_revision_id, facet_key=facet_key,
        withdrawn_alias_ids=sorted(withdrawn_alias_ids),
        withdrawn_claim_ids=sorted(withdrawn_claim_ids),
        withdrawn_summary_ids=sorted(withdrawn_summary_ids),
        demoted_to_out_of_page_scope=sorted(demoted_scope),
        demoted_ungrounded_identifier=sorted(demoted_grounding),
        withdrawal_reasons=dict(sorted(reasons.items())),
        payload_eligible_alias_texts=sorted(a.alias for a in surviving_aliases),
        surviving_accepted_claim_ids=sorted(surviving_claim_ids),
        surviving_summary_sentence_ids=sorted(s.sentence_id for s in surviving_summaries),
        derived_links=derived_links,
        counts_before={
            "supported_aliases": len(supported_aliases),
            "accepted_claims": len(accepted_before),
            "reference_valid_summary_sentences": len(reference_valid_summaries),
            "derived_links": len(validation.derived_links),
        },
        counts_after={
            "supported_aliases": len(surviving_aliases),
            "accepted_claims": len(surviving_claims),
            "reference_valid_summary_sentences": len(surviving_summaries),
            "derived_links": len(derived_links),
        },
    )


def required_adjudication_item_ids(validation: FacetValidationResult) -> list[str]:
    """Every item SS4.6 requires the owner to adjudicate on this facet."""
    facet_key = facet_key_of(validation.page_key, validation.document_revision_id)
    return sorted(
        [claim_item_id(facet_key, c.claim_id) for c in validation.claims if c.validation_status == "accepted"]
        + [alias_item_id(facet_key, a.alias_id) for a in validation.aliases if a.status == "supported"]
        + [summary_item_id(facet_key, s.sentence_id) for s in validation.summary_sentences]
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
