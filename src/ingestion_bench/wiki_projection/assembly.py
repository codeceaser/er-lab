"""Stage 7C.1: facet payload composition and W1 page previews.

**Nothing in this module may be treated as the final W1 retrieval
representation at the owner-adjudication checkpoint.** Two of the SS6.2
payload's seven components are owner-dependent -- validated supported aliases
adjudicated CORRECT (component 2) and owner-adjudicated-CORRECT summary
sentences (component 7) -- so the payload cannot be composed, and facet
embeddings cannot be written, until adjudication returns (SS4.6 "facet
embeddings are written only after pass 3").

`compose_payload_preview` therefore emits a PREVIEW with every owner-dependent
component clearly marked pending, and refuses to be mistaken for the real
thing: `is_final` is always False and `pending_components` is always populated
when owner-dependent material is present.

The SS6.2 composition ORDER, the component-5 selection rule, the exact-match
dedupe and the `PAY_max` drop order are implemented here exactly as frozen, so
that after adjudication the final payload is a re-run of this same code with
verdicts supplied -- not a different code path.
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ingestion_bench.wiki_projection import identity
from ingestion_bench.wiki_projection.compiler import PAY_MAX_PAYLOAD_CHARACTERS
from ingestion_bench.wiki_projection.model import Facet, PageIdentity, WikiSection
from ingestion_bench.wiki_projection.validation import FacetValidationResult, normalize_whitespace

# SS6.2 component 5 -- the deterministic selection rule, frozen.
IDENTITY_PASSAGE_MAX_SENTENCES = 2
IDENTITY_PASSAGE_MAX_CHARS = 400

# SS6.2 PAY_max drop order: components are dropped WHOLE, in this fixed order.
# Components 1, 3 and 4 are NEVER dropped -- they are the page's identity and
# are what makes the facet findable at all.
PAY_MAX_DROP_ORDER: tuple[int, ...] = (7, 6, 5, 2)
NEVER_DROPPED_COMPONENTS: frozenset[int] = frozenset({1, 3, 4})


class PayloadComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: int
    name: str
    label: Literal["source_derived", "model_derived"]
    text: str
    # True when this component's content cannot be settled without an owner
    # semantic verdict (SS3.5, SS4.5, SS4.6).
    pending_owner_adjudication: bool = False
    provenance: list[str] = Field(default_factory=list)


class FacetPayloadPreview(BaseModel):
    """A PREVIEW of what the SS6.2 payload would look like. Never final, never
    embedded, never stored as a retrieval representation."""

    model_config = ConfigDict(extra="forbid")

    page_key: str
    document_revision_id: str
    components: list[PayloadComponent]
    preview_text: str
    preview_sha256: str
    pending_components: list[int]
    payload_truncated_components: list[int]
    summary_payload_dedup_count: int
    is_final: Literal[False] = False
    not_final_reason: str


def select_identity_bearing_passage(
    facet: Facet, page: PageIdentity, sections_by_chunk: dict[str, WikiSection], postings_by_chunk: dict[str, list]
) -> tuple[str, list[str]]:
    """SS6.2 component 5, the deterministic selection rule:

    1. this facet's input chunks in ascending (chunk_index, chunk_id);
    2. split source_text on the FROZEN Stage 7C.0 sentence boundary rule;
    3. keep sentences containing an occurrence of this page's identity, matched
       by anchor posting `char_span` -- not by re-searching text, so the match
       is the SAME one that created membership (SS2.2);
    4. take the first 2 such sentences in document order, each capped at 400
       characters, truncated at a word boundary with an explicit ellipsis.
    """
    ordered = sorted(
        (sections_by_chunk[cid] for cid in facet.chunk_ids if cid in sections_by_chunk),
        key=lambda s: (s.chunk_index, s.chunk_id),
    )
    kept: list[str] = []
    provenance: list[str] = []
    for section in ordered:
        spans = [
            (p.start_char, p.end_char)
            for p in postings_by_chunk.get(section.chunk_id, [])
            if p.anchor_id == page.anchor_id and p.field == "source_text"
        ]
        for sentence in identity.split_sentences(section.source_text):
            if len(kept) >= IDENTITY_PASSAGE_MAX_SENTENCES:
                break
            covers = any(sentence.start_char <= start and end <= sentence.end_char for start, end in spans)
            if not covers:
                continue
            text = sentence.surface
            if len(text) > IDENTITY_PASSAGE_MAX_CHARS:
                cut = text[:IDENTITY_PASSAGE_MAX_CHARS].rsplit(" ", 1)[0]
                text = f"{cut} ..."
            kept.append(text)
            provenance.append(f"{section.chunk_id}[{sentence.start_char}:{sentence.end_char}]")
        if len(kept) >= IDENTITY_PASSAGE_MAX_SENTENCES:
            break
    return "\n".join(kept), provenance


def compose_payload_preview(
    validation: FacetValidationResult,
    *,
    facet: Facet,
    page: PageIdentity,
    sections_by_chunk: dict[str, WikiSection],
    postings_by_chunk: dict[str, list],
) -> FacetPayloadPreview:
    """Compose the SS6.2 payload PREVIEW in the frozen component order.

    Components 2 and 7 are owner-dependent. At this checkpoint they are
    included but MARKED PENDING, so the owner can see what their verdicts will
    decide -- they are never silently treated as settled.
    """
    sections = sorted(
        (sections_by_chunk[cid] for cid in facet.chunk_ids if cid in sections_by_chunk),
        key=lambda s: (s.chunk_index, s.chunk_id),
    )

    # 1 -- display_title (source_derived, deterministic)
    components = [
        PayloadComponent(number=1, name="display_title", label="source_derived", text=page.display_title,
                         provenance=[f"page_identity:{page.page_key}"])
    ]

    # 2 -- validated supported aliases, PENDING owner semantic adjudication
    pending_aliases = sorted({a.alias for a in validation.aliases if a.status == "supported"})
    components.append(
        PayloadComponent(
            number=2, name="validated_supported_aliases", label="model_derived",
            text="\n".join(pending_aliases),
            pending_owner_adjudication=bool(pending_aliases),
            provenance=[a.alias_id for a in validation.aliases if a.status == "supported"],
        )
    )

    # 3 -- revision headings (source_derived)
    headings: list[str] = []
    for section in sections:
        rendered = " > ".join(section.heading_path)
        if rendered and rendered not in headings:
            headings.append(rendered)
    components.append(
        PayloadComponent(number=3, name="revision_headings", label="source_derived", text="\n".join(headings),
                         provenance=[s.chunk_id for s in sections])
    )

    # 4 -- stable source identifiers occurring in this facet (source_derived)
    identifiers: set[str] = set()
    for section in sections:
        identifiers |= identity.identifiers_in(section.source_text)
    components.append(
        PayloadComponent(number=4, name="source_identifiers", label="source_derived",
                         text="\n".join(sorted(identifiers)), provenance=[s.chunk_id for s in sections])
    )

    # 5 -- identity-bearing source passage (source_derived, deterministic)
    passage, passage_provenance = select_identity_bearing_passage(facet, page, sections_by_chunk, postings_by_chunk)
    components.append(
        PayloadComponent(number=5, name="identity_bearing_source_passage", label="source_derived",
                         text=passage, provenance=passage_provenance)
    )

    # 6 -- accepted claim_texts, sorted by claim_id (model_derived, settled
    #      mechanically -- but a claim resting solely on an alias stays pending)
    accepted = sorted(
        (c for c in validation.claims if c.validation_status == "accepted"), key=lambda c: c.claim_id
    )
    claim_texts = [c.claim_text for c in accepted]
    components.append(
        PayloadComponent(
            number=6, name="accepted_claim_texts", label="model_derived", text="\n".join(claim_texts),
            pending_owner_adjudication=any(c.pending_alias_adjudication for c in accepted),
            provenance=[c.claim_id for c in accepted],
        )
    )

    # 7 -- owner-adjudicated-CORRECT summary sentences. NONE are adjudicated
    #      yet, so every reference-valid sentence is shown as PENDING.
    pending_summaries = sorted(
        (s for s in validation.summary_sentences if s.reference_valid), key=lambda s: s.sentence_id
    )
    normalized_claims = {normalize_whitespace(t).casefold() for t in claim_texts}
    deduped: list[str] = []
    dedup_count = 0
    for sentence in pending_summaries:
        if normalize_whitespace(sentence.text).casefold() in normalized_claims:
            dedup_count += 1  # SS6.2 component-7 exact-match dedupe
            continue
        deduped.append(sentence.text)
    components.append(
        PayloadComponent(
            number=7, name="owner_adjudicated_summary_sentences", label="model_derived",
            text="\n".join(deduped), pending_owner_adjudication=bool(deduped),
            provenance=[s.sentence_id for s in pending_summaries],
        )
    )

    # PAY_max drop order -- components dropped WHOLE, 7 then 6 then 5 then 2.
    def render(active: list[PayloadComponent]) -> str:
        return "\n".join(c.text for c in active if c.text)

    active = list(components)
    dropped: list[int] = []
    for number in PAY_MAX_DROP_ORDER:
        if len(render(active)) <= PAY_MAX_PAYLOAD_CHARACTERS:
            break
        assert number not in NEVER_DROPPED_COMPONENTS
        active = [c for c in active if c.number != number]
        dropped.append(number)

    preview_text = render(active)
    pending = sorted(c.number for c in active if c.pending_owner_adjudication)

    return FacetPayloadPreview(
        page_key=validation.page_key, document_revision_id=validation.document_revision_id,
        components=components, preview_text=preview_text,
        preview_sha256=hashlib.sha256(preview_text.encode("utf-8")).hexdigest(),
        pending_components=pending, payload_truncated_components=dropped,
        summary_payload_dedup_count=dedup_count,
        not_final_reason=(
            "PREVIEW ONLY. SS6.2 components 2 (validated supported aliases) and 7 (summary sentences) "
            "require owner semantic verdicts, and SS4.6 writes facet embeddings only after adjudication "
            "pass 3. No facet embedding exists and none may be created from this preview."
        ),
    )


# --- W1 page preview rendering ----------------------------------------------


def render_w1_page_preview(
    page: PageIdentity,
    *,
    facets: list[Facet],
    validations: dict[str, FacetValidationResult],
    sections_by_chunk: dict[str, WikiSection],
    postings_by_chunk: dict[str, list],
    deterministic_links: list,
    eligible_revision_ids: list[str],
    revision_symbol_by_id: dict[str, str],
    payload_previews: dict[str, FacetPayloadPreview],
) -> str:
    """An owner-comprehension preview, NOT a final W1 page and NOT a scored
    artifact. Source-backed/deterministic material and model-derived material
    pending adjudication are rendered in visibly separate blocks, and every
    advisory item keeps its source citation."""
    eligible = set(eligible_revision_ids)
    own = [f for f in facets if f.page_key == page.page_key and f.document_revision_id in eligible]

    lines: list[str] = [
        f"# {page.display_title} — W1 PREVIEW (pending owner adjudication)",
        "",
        "> **This is a PREVIEW for owner comprehension and adjudication, not a final W1 page and not a "
        "benchmark result.** No page-quality score is computed. No facet embedding exists. Every "
        "model-derived item below is an unadjudicated PROPOSAL.",
        "",
        f"- **page_key**: `{page.page_key}`  |  **page_type**: `{page.page_type}`",
        f"- **eligible facets under this scope**: {len(own)}",
        "",
    ]

    for facet in sorted(own, key=lambda f: f.document_revision_id):
        symbol = revision_symbol_by_id.get(facet.document_revision_id, facet.document_revision_id[:12])
        validation = validations.get(f"{page.page_key}|{facet.document_revision_id}")
        lines.append(f"## Facet — {facet.logical_document_id} / {symbol}")
        lines.append("")

        lines.append("### BLOCK A — SOURCE-BACKED / DETERMINISTIC (Stage 7C.0, frozen)")
        lines.append("")
        lines.append(f"- **document_revision_id**: `{facet.document_revision_id[:16]}...`")
        lines.append(f"- **membership_hash**: `{facet.membership_hash[:16]}...` "
                     "(unchanged by anything in Block B)")
        for chunk_id in facet.chunk_ids:
            section = sections_by_chunk[chunk_id]
            lines.append(f"- **heading**: {' > '.join(section.heading_path) or '(none)'}")
            lines.append(f"- **chunk_id**: `{chunk_id[:16]}...`  |  **content_sha256**: "
                         f"`{section.content_sha256[:16]}...`")
            lines.append("")
            lines.append("**Original source passage (verbatim, authoritative evidence):**")
            lines.append("")
            lines.append("> " + section.source_text.replace("\n", "\n> "))
            lines.append("")
            anchors = [p for p in postings_by_chunk.get(chunk_id, []) if p.anchor_id == page.anchor_id]
            lines.append(f"**Deterministic anchors for this identity**: {len(anchors)} posting(s) — "
                         + ", ".join(f"`{p.surface_text}`@[{p.start_char}:{p.end_char}]" for p in anchors))
            lines.append("")
        structural = [
            link for link in deterministic_links
            if link.from_document_revision_id == facet.document_revision_id
            and link.to_document_revision_id in eligible
            and link.from_section_id in {sections_by_chunk[c].section_id for c in facet.chunk_ids}
        ]
        lines.append(f"**Deterministic navigation available without any claim**: "
                     f"{sum(1 for link in structural if link.link_type == 'exact_anchor')} exact-anchor, "
                     f"{sum(1 for link in structural if link.link_type == 'structural')} structural")
        lines.append("")

        lines.append("### BLOCK B — MODEL-DERIVED / PENDING OWNER ADJUDICATION")
        lines.append("")
        if validation is None or validation.generation_failed:
            lines.append("_No compiler output for this facet"
                         + (f" (generation failed: {validation.generation_error})" if validation else "")
                         + ". Block A above is unaffected — the facet, its chunks, its anchors and its "
                         "deterministic navigation all remain._")
            lines.append("")
            continue

        lines.append("**Proposed aliases** (advisory; span-validity is mechanical, meaning is the owner's):")
        lines.append("")
        if not validation.aliases:
            lines.append("_none proposed_")
        for alias in validation.aliases:
            lines.append(f"- `{alias.alias}` — status `{alias.status}`, span_valid={alias.span_valid}"
                         f" — cites {', '.join(f'`{c[:12]}...`' for c in alias.supporting_chunk_ids) or '(none)'}"
                         f" — quote(s): {alias.supporting_quotes or '(none)'}"
                         " — **OWNER VERDICT: pending**")
        lines.append("")

        lines.append("**Proposed claims** (advisory; a claim NEVER creates membership or connectivity):")
        lines.append("")
        if not validation.claims:
            lines.append("_none proposed_")
        for claim in validation.claims:
            lines.append(f"- **{claim.claim_id}** [`{claim.validation_status}`] "
                         f"{claim.subject} — *{claim.predicate}* → {claim.object}")
            lines.append(f"  - claim_text: {claim.claim_text}")
            lines.append(f"  - cites: {', '.join(f'`{c[:12]}...`' for c in claim.supporting_chunk_ids) or '(none)'}")
            lines.append(f"  - exact quote(s): {claim.supporting_quotes or '(none)'}")
            lines.append(f"  - citation_valid (mechanical): {claim.citation_valid}"
                         f" | coherence: {claim.coherence_basis}"
                         + (" | **depends on an alias verdict**" if claim.depends_on_alias else ""))
            if claim.rejection_reasons:
                lines.append(f"  - reasons: {claim.rejection_reasons}")
            lines.append("  - **OWNER VERDICT: pending** (mechanical validity is not claim correctness)")
        lines.append("")

        lines.append("**Proposed summary sentences** (advisory; never evidence, never an answer):")
        lines.append("")
        if not validation.summary_sentences:
            lines.append("_none proposed_")
        for sentence in validation.summary_sentences:
            lines.append(f"- **{sentence.sentence_id}**: {sentence.text}")
            lines.append(f"  - references: {sentence.supported_claim_ids} "
                         f"| reference_valid (mechanical): {sentence.reference_valid}")
            if sentence.rejection_reasons:
                lines.append(f"  - reasons: {sentence.rejection_reasons}")
            lines.append("  - **OWNER VERDICT: pending** (reference validity is not summary correctness)")
        lines.append("")

        lines.append("**Proposed claim-derived links** (advisory routing only; they add no connectivity "
                     "that Block A does not already provide):")
        lines.append("")
        if not validation.derived_links:
            lines.append("_none derived_")
        for link in sorted(validation.derived_links, key=lambda link_: link_.link_id):
            arrow = "→" if link.traversal_direction == "forward" else "← (inverse traversal)"
            lines.append(f"- `{link.subject_page_key}` {arrow} `{link.object_page_key}` "
                         f"— predicate *{link.predicate}* (verbatim; no inverse predicate is fabricated) "
                         f"— from {link.claim_id} — is_authoritative_lineage=False")
        lines.append("")

        preview = payload_previews.get(f"{page.page_key}|{facet.document_revision_id}")
        if preview is not None:
            lines.append(f"**Payload composition preview** — {len(preview.preview_text)} chars, "
                         f"components pending owner verdicts: {preview.pending_components or 'none'}, "
                         f"dropped by PAY_max: {preview.payload_truncated_components or 'none'}. "
                         "**Not a final representation; no embedding is created from it.**")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("_Stage 7C.1 owner-adjudication checkpoint. Block A is frozen Stage 7C.0 output and is "
                 "unaffected by anything in Block B. If every Block B item were deleted, every facet, "
                 "chunk, anchor and deterministic link above would remain exactly as shown._")
    return "\n".join(lines) + "\n"
