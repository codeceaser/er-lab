"""Stage 7C.1: the OWNER ADJUDICATION PACKET for Run 1.

**Claude is not the adjudicator.** Revision 6 SS4.3/SS4.4/SS4.5 make three
judgements the owner's alone, and this module exists to hand them over
undecided:

  - a source-cited claim is NOT thereby semantically correct;
  - a summary whose claim ids resolve is NOT thereby faithful to them;
  - an alias whose string occurs in source does NOT thereby name this entity.

Every verdict field this module emits is literally `null` / blank, and no
recommendation, score, confidence, ordering-by-likelihood or hint appears
beside it. Items are ordered by stable identifier only, so even the ORDER
carries no suggestion.

The packet covers RUN 1 ONLY (SS8F: run 1 is the primary representation
candidate, designated before execution).
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ingestion_bench.wiki_projection.model import Facet, PageIdentity, WikiSection
from ingestion_bench.wiki_projection.validation import FacetValidationResult

OWNER_VERDICT_VALUES = ("CORRECT", "INCORRECT", "UNVERIFIABLE")

_CONTEXT_WINDOW_CHARS = 600


class OwnerVerdictSlot(BaseModel):
    """A deliberately empty verdict. `owner_verdict` and `owner_reason` are the
    ONLY fields the owner fills, and nothing else in the packet pre-empts
    them."""

    model_config = ConfigDict(extra="forbid")

    allowed_values: list[str] = Field(default_factory=lambda: list(OWNER_VERDICT_VALUES))
    owner_verdict: None = None
    owner_reason: str = ""


class ClaimAdjudicationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adjudication_item_id: str
    item_type: Literal["claim"] = "claim"
    page_key: str
    document_revision_id: str
    facet_identity: str
    display_title: str
    logical_document_id: str
    revision_symbol: str | None

    subject: str
    predicate: str
    object: str
    claim_text: str

    supporting_chunk_ids: list[str]
    supporting_quotes: list[str]
    surrounding_source_text: dict[str, str]
    full_source_text: dict[str, str]
    source_refs: dict[str, list]

    mechanical_validation_status: str
    mechanical_citation_valid: bool
    mechanical_rejection_reasons: list[str]
    mechanical_coherence_basis: str | None

    acceptance_depends_on_alias: bool
    alias_dependency_ids: list[str]
    alias_dependency_text: list[str]

    derived_link_if_accepted: list[dict]

    owner: OwnerVerdictSlot = Field(default_factory=OwnerVerdictSlot)


class AliasAdjudicationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adjudication_item_id: str
    item_type: Literal["alias"] = "alias"
    page_key: str
    document_revision_id: str
    page_identity: str
    display_title: str
    revision_symbol: str | None

    alias_text: str
    supporting_chunk_ids: list[str]
    exact_source_occurrences: list[dict]
    surrounding_source_text: dict[str, str]

    mechanical_status: str
    mechanical_span_valid: bool
    mechanical_rejection_reasons: list[str]

    claims_whose_coherence_depends_on_this_alias: list[dict]

    owner: OwnerVerdictSlot = Field(default_factory=OwnerVerdictSlot)


class SummaryAdjudicationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adjudication_item_id: str
    item_type: Literal["summary_sentence"] = "summary_sentence"
    page_key: str
    document_revision_id: str
    display_title: str
    revision_symbol: str | None

    summary_text: str
    referenced_claim_ids: list[str]
    referenced_claims_readable: list[dict]
    referenced_claim_exact_quotes: list[str]
    full_source_text: dict[str, str]

    mechanical_reference_valid: bool
    mechanical_rejection_reasons: list[str]

    owner: OwnerVerdictSlot = Field(default_factory=OwnerVerdictSlot)


class AdjudicationPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: int
    projection_hash: str
    model_identity: str
    prompt_version: str
    prompt_sha256: str

    claims: list[ClaimAdjudicationItem]
    aliases: list[AliasAdjudicationItem]
    summary_sentences: list[SummaryAdjudicationItem]

    claim_item_count: int
    alias_item_count: int
    summary_item_count: int
    total_item_count: int

    packet_sha256: str
    instructions: list[str]


def _window(text: str, quote: str) -> str:
    """Enough surrounding source text to judge meaning. When the quote is not
    locatable, the whole passage is returned rather than nothing."""
    index = text.find(quote)
    if index < 0 or not quote:
        return text
    start = max(0, index - _CONTEXT_WINDOW_CHARS // 2)
    end = min(len(text), index + len(quote) + _CONTEXT_WINDOW_CHARS // 2)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{text[start:end]}{suffix}"


def build_adjudication_packet(
    *,
    run_id: int,
    validations: dict[str, FacetValidationResult],
    projection_hash: str,
    facets_by_key: dict[str, Facet],
    pages_by_key: dict[str, PageIdentity],
    sections_by_chunk: dict[str, WikiSection],
    revision_symbol_by_id: dict[str, str],
    model_identity: str,
    prompt_version: str,
    prompt_sha256_value: str,
) -> AdjudicationPacket:
    """Build the Run-1 packet.

    "Mechanically eligible" means the item survived deterministic validation
    far enough that its MEANING is now the deciding question. Rejected items
    are excluded from adjudication (their defect is mechanical and already
    settled) but remain in the audit record, which SS4.2 requires.
    """
    claim_items: list[ClaimAdjudicationItem] = []
    alias_items: list[AliasAdjudicationItem] = []
    summary_items: list[SummaryAdjudicationItem] = []

    for facet_key in sorted(validations):
        validation = validations[facet_key]
        page = pages_by_key[validation.page_key]
        facet = facets_by_key[facet_key]
        symbol = revision_symbol_by_id.get(validation.document_revision_id)
        facet_source = {cid: sections_by_chunk[cid].source_text for cid in facet.chunk_ids}
        facet_refs = {cid: sections_by_chunk[cid].source_refs for cid in facet.chunk_ids}
        alias_by_id = {a.alias_id: a for a in validation.aliases}

        # --- claims: every ACCEPTED claim is owner-adjudicated (SS4.6) ------
        for claim in sorted(validation.claims, key=lambda c: c.claim_id):
            if claim.validation_status != "accepted":
                continue
            derived = [
                {
                    "subject_page_key": link.subject_page_key,
                    "predicate": link.predicate,
                    "object_page_key": link.object_page_key,
                    "traversal_direction": link.traversal_direction,
                    "is_authoritative_lineage": False,
                }
                for link in validation.derived_links
                if link.claim_id == claim.claim_id
            ]
            claim_items.append(
                ClaimAdjudicationItem(
                    adjudication_item_id=f"CLAIM::{facet_key}::{claim.claim_id}",
                    page_key=validation.page_key, document_revision_id=validation.document_revision_id,
                    facet_identity=facet_key, display_title=page.display_title,
                    logical_document_id=facet.logical_document_id, revision_symbol=symbol,
                    subject=claim.subject, predicate=claim.predicate, object=claim.object,
                    claim_text=claim.claim_text,
                    supporting_chunk_ids=list(claim.supporting_chunk_ids),
                    supporting_quotes=list(claim.supporting_quotes),
                    surrounding_source_text={
                        cid: _window(facet_source.get(cid, ""), claim.supporting_quotes[0] if claim.supporting_quotes else "")
                        for cid in claim.supporting_chunk_ids
                        if cid in facet_source
                    },
                    full_source_text=facet_source,
                    source_refs={cid: facet_refs.get(cid, []) for cid in claim.supporting_chunk_ids if cid in facet_refs},
                    mechanical_validation_status=claim.validation_status,
                    mechanical_citation_valid=claim.citation_valid,
                    mechanical_rejection_reasons=list(claim.rejection_reasons),
                    mechanical_coherence_basis=claim.coherence_basis,
                    acceptance_depends_on_alias=claim.depends_on_alias,
                    alias_dependency_ids=list(claim.alias_dependency_ids),
                    alias_dependency_text=[
                        alias_by_id[aid].alias for aid in claim.alias_dependency_ids if aid in alias_by_id
                    ],
                    derived_link_if_accepted=derived,
                )
            )

        # --- aliases: every SUPPORTED alias is owner-adjudicated (SS4.6) ----
        for alias in sorted(validation.aliases, key=lambda a: a.alias_id):
            if alias.status != "supported":
                continue
            occurrences = []
            for chunk_id in alias.supporting_chunk_ids:
                text = facet_source.get(chunk_id, "")
                start = text.find(alias.alias)
                if start >= 0:
                    occurrences.append(
                        {"chunk_id": chunk_id, "start_char": start, "end_char": start + len(alias.alias),
                         "exact_text": text[start : start + len(alias.alias)]}
                    )
            dependents = [
                {
                    "claim_id": claim.claim_id, "claim_text": claim.claim_text,
                    "coherence_basis": claim.coherence_basis,
                    "note": "this claim is on this page ONLY because the alias above is treated as naming "
                            "this page's entity; an INCORRECT verdict makes it out_of_page_scope",
                }
                for claim in validation.claims
                if alias.alias_id in claim.alias_dependency_ids
            ]
            alias_items.append(
                AliasAdjudicationItem(
                    adjudication_item_id=f"ALIAS::{facet_key}::{alias.alias_id.rsplit('|', 1)[-1]}",
                    page_key=validation.page_key, document_revision_id=validation.document_revision_id,
                    page_identity=page.normalized_identity, display_title=page.display_title,
                    revision_symbol=symbol,
                    alias_text=alias.alias, supporting_chunk_ids=list(alias.supporting_chunk_ids),
                    exact_source_occurrences=occurrences,
                    surrounding_source_text={
                        cid: _window(facet_source.get(cid, ""), alias.alias)
                        for cid in alias.supporting_chunk_ids
                        if cid in facet_source
                    },
                    mechanical_status=alias.status, mechanical_span_valid=alias.span_valid,
                    mechanical_rejection_reasons=list(alias.rejection_reasons),
                    claims_whose_coherence_depends_on_this_alias=dependents,
                )
            )

        # --- summary sentences: EVERY sentence is owner-adjudicated (SS4.6) -
        claims_by_id = {c.claim_id: c for c in validation.claims}
        for sentence in sorted(validation.summary_sentences, key=lambda s: s.sentence_id):
            readable = [
                {
                    "claim_id": cid,
                    "subject": claims_by_id[cid].subject,
                    "predicate": claims_by_id[cid].predicate,
                    "object": claims_by_id[cid].object,
                    "claim_text": claims_by_id[cid].claim_text,
                    "validation_status": claims_by_id[cid].validation_status,
                }
                for cid in sentence.supported_claim_ids
                if cid in claims_by_id
            ]
            quotes = [q for cid in sentence.supported_claim_ids if cid in claims_by_id
                      for q in claims_by_id[cid].supporting_quotes]
            summary_items.append(
                SummaryAdjudicationItem(
                    adjudication_item_id=f"SUMMARY::{facet_key}::{sentence.sentence_id}",
                    page_key=validation.page_key, document_revision_id=validation.document_revision_id,
                    display_title=page.display_title, revision_symbol=symbol,
                    summary_text=sentence.text, referenced_claim_ids=list(sentence.supported_claim_ids),
                    referenced_claims_readable=readable, referenced_claim_exact_quotes=quotes,
                    full_source_text=facet_source,
                    mechanical_reference_valid=sentence.reference_valid,
                    mechanical_rejection_reasons=list(sentence.rejection_reasons),
                )
            )

    packet = AdjudicationPacket(
        run_id=run_id, projection_hash=projection_hash, model_identity=model_identity,
        prompt_version=prompt_version, prompt_sha256=prompt_sha256_value,
        claims=claim_items, aliases=alias_items, summary_sentences=summary_items,
        claim_item_count=len(claim_items), alias_item_count=len(alias_items),
        summary_item_count=len(summary_items),
        total_item_count=len(claim_items) + len(alias_items) + len(summary_items),
        packet_sha256="",
        instructions=[
            "Fill ONLY `owner_verdict` (CORRECT / INCORRECT / UNVERIFIABLE) and `owner_reason` on each item.",
            "CLAIM: does (subject, predicate, object) faithfully represent the cited passage? A valid exact "
            "citation proves the passage exists and contains the quote -- it does NOT prove the inferred "
            "predicate represents it (Revision 6 SS4.3).",
            "ALIAS: does this alias genuinely denote THIS facet's page identity -- not a related, broader, "
            "narrower or adjacent entity? A verbatim occurrence proves the string is there, not that it "
            "names this entity (SS4.5).",
            "SUMMARY: does the sentence faithfully represent EXACTLY the claims it references -- no addition, "
            "overstatement, merge error, direction inversion, dropped qualification or temporal/status "
            "distortion? Valid claim-id references prove only that it points at accepted claims (SS4.4).",
            "An INCORRECT alias verdict also demotes every claim listed under "
            "`claims_whose_coherence_depends_on_this_alias` to out_of_page_scope (SS4.6 pass 3).",
            "Nothing here is pre-filled and no recommendation is offered: these three judgements are yours "
            "alone, and the representation cannot be built without them.",
        ],
    )
    packet.packet_sha256 = hashlib.sha256(
        json.dumps(packet.model_dump(mode="json"), sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return packet


def render_packet_markdown(packet: AdjudicationPacket) -> str:
    """The readable companion to the JSON packet. Same items, same order, same
    empty verdicts."""
    lines: list[str] = [
        "# Stage 7C.1 — OWNER ADJUDICATION PACKET (Run 1)",
        "",
        "> **You are the only semantic adjudicator.** Mechanical validation has already run; what remains "
        "are three judgements no deterministic rule can make. No verdict below is pre-filled and no "
        "recommendation is offered.",
        "",
        f"- Run: **{packet.run_id}** (the primary representation candidate, designated before execution)",
        f"- Compiler model: `{packet.model_identity}`",
        f"- Prompt: `{packet.prompt_version}` / `{packet.prompt_sha256[:16]}...`",
        f"- Frozen projection: `{packet.projection_hash[:16]}...`",
        f"- Packet SHA-256: `{packet.packet_sha256[:16]}...`",
        "",
        f"**Items awaiting your verdict: {packet.total_item_count}** "
        f"({packet.claim_item_count} claims, {packet.alias_item_count} aliases, "
        f"{packet.summary_item_count} summary sentences)",
        "",
        "## How to record a verdict",
        "",
    ]
    lines.extend(f"{index}. {text}" for index, text in enumerate(packet.instructions, start=1))
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## A. CLAIMS")
    lines.append("")
    lines.append("_Citation validity is not claim correctness (SS4.3)._")
    lines.append("")
    if not packet.claims:
        lines.append("_No mechanically eligible claim in Run 1._")
        lines.append("")
    for item in packet.claims:
        lines.append(f"### `{item.adjudication_item_id}`")
        lines.append("")
        lines.append(f"- **page**: {item.display_title} (`{item.page_key}`)")
        lines.append(f"- **facet**: `{item.facet_identity}` — {item.logical_document_id} / {item.revision_symbol}")
        lines.append(f"- **subject**: {item.subject}")
        lines.append(f"- **predicate**: {item.predicate}")
        lines.append(f"- **object**: {item.object}")
        lines.append(f"- **claim_text**: {item.claim_text}")
        lines.append(f"- **cites**: {', '.join(f'`{c}`' for c in item.supporting_chunk_ids)}")
        lines.append(f"- **exact supporting quote(s)**: {item.supporting_quotes}")
        lines.append(f"- **source_refs**: `{item.source_refs}`")
        lines.append("")
        lines.append("**Source passage (enough context to judge meaning):**")
        lines.append("")
        for chunk_id, text in item.surrounding_source_text.items():
            lines.append(f"- `{chunk_id[:16]}...`:")
            lines.append("")
            lines.append("  > " + text.replace("\n", "\n  > "))
            lines.append("")
        lines.append(f"- **mechanical validation**: status=`{item.mechanical_validation_status}`, "
                     f"citation_valid={item.mechanical_citation_valid}, "
                     f"coherence={item.mechanical_coherence_basis}")
        if item.mechanical_rejection_reasons:
            lines.append(f"- **mechanical notes**: {item.mechanical_rejection_reasons}")
        lines.append(f"- **acceptance depends on an alias**: {item.acceptance_depends_on_alias}"
                     + (f" → {item.alias_dependency_text}" if item.acceptance_depends_on_alias else ""))
        if item.derived_link_if_accepted:
            lines.append("- **derived link that would result if accepted**:")
            for link in item.derived_link_if_accepted:
                lines.append(f"  - `{link['subject_page_key']}` —*{link['predicate']}*→ "
                             f"`{link['object_page_key']}` ({link['traversal_direction']})")
        else:
            lines.append("- **derived link that would result if accepted**: none "
                         "(an endpoint resolves to no existing page key)")
        lines.append("")
        lines.append("```")
        lines.append("OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):")
        lines.append("OWNER REASON:")
        lines.append("```")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## B. SUPPORTED ALIASES")
    lines.append("")
    lines.append("_Alias span validity is not alias semantic correctness (SS4.5)._")
    lines.append("")
    if not packet.aliases:
        lines.append("_No supported alias in Run 1._")
        lines.append("")
    for item in packet.aliases:
        lines.append(f"### `{item.adjudication_item_id}`")
        lines.append("")
        lines.append(f"- **page identity**: {item.display_title} (`{item.page_identity}`)")
        lines.append(f"- **revision**: {item.revision_symbol}")
        lines.append(f"- **alias text**: `{item.alias_text}`")
        lines.append(f"- **exact source occurrence(s)**: {item.exact_source_occurrences}")
        lines.append("")
        for chunk_id, text in item.surrounding_source_text.items():
            lines.append(f"- context in `{chunk_id[:16]}...`:")
            lines.append("")
            lines.append("  > " + text.replace("\n", "\n  > "))
            lines.append("")
        lines.append(f"- **mechanical span validity**: {item.mechanical_span_valid} "
                     f"(status=`{item.mechanical_status}`)")
        if item.mechanical_rejection_reasons:
            lines.append(f"- **mechanical notes**: {item.mechanical_rejection_reasons}")
        if item.claims_whose_coherence_depends_on_this_alias:
            lines.append("- **claims whose page-coherence acceptance depends on this alias** "
                         "(an INCORRECT verdict demotes each to out_of_page_scope):")
            for dependent in item.claims_whose_coherence_depends_on_this_alias:
                lines.append(f"  - `{dependent['claim_id']}`: {dependent['claim_text']}")
        else:
            lines.append("- **claims depending on this alias**: none")
        lines.append("")
        lines.append("```")
        lines.append("OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):")
        lines.append("OWNER REASON:")
        lines.append("```")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## C. SUMMARY SENTENCES")
    lines.append("")
    lines.append("_Summary reference validity is not summary correctness (SS4.4). Look specifically for "
                 "overstatement, direction inversion, unsupported composition, dropped qualification, and "
                 "temporal/status distortion._")
    lines.append("")
    if not packet.summary_sentences:
        lines.append("_No summary sentence in Run 1._")
        lines.append("")
    for item in packet.summary_sentences:
        lines.append(f"### `{item.adjudication_item_id}`")
        lines.append("")
        lines.append(f"- **page**: {item.display_title} (`{item.page_key}`) — {item.revision_symbol}")
        lines.append(f"- **summary text**: {item.summary_text}")
        lines.append(f"- **referenced claim ids**: {item.referenced_claim_ids}")
        lines.append("- **referenced claims, in readable form**:")
        for claim in item.referenced_claims_readable:
            lines.append(f"  - `{claim['claim_id']}` [{claim['validation_status']}]: "
                         f"{claim['subject']} — *{claim['predicate']}* → {claim['object']}")
        lines.append(f"- **their exact source quotes**: {item.referenced_claim_exact_quotes}")
        lines.append("")
        lines.append("**Full facet source text:**")
        lines.append("")
        for chunk_id, text in item.full_source_text.items():
            lines.append(f"- `{chunk_id[:16]}...`:")
            lines.append("")
            lines.append("  > " + text.replace("\n", "\n  > "))
            lines.append("")
        lines.append(f"- **mechanical reference validity**: {item.mechanical_reference_valid}")
        if item.mechanical_rejection_reasons:
            lines.append(f"- **mechanical notes**: {item.mechanical_rejection_reasons}")
        lines.append("")
        lines.append("```")
        lines.append("OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):")
        lines.append("OWNER REASON:")
        lines.append("```")
        lines.append("")

    return "\n".join(lines)
