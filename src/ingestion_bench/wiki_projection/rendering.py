"""Stage 7C.0: deterministic rendering of W0 pages for owner review.

Rendering is byte-deterministic: the same projection and the same eligible
revision set always produce the same Markdown, with no timestamp, run id or
other run-scoped value in the output.

Two rules this module enforces and states on every page it renders:

  1. Source-authoritative and model-derived content are rendered in SEPARATE
     LABELLED BLOCKS, and `model_derived_text` is never merged into the source
     block (Revision 6 SS4.7). At 7C.0 the model-derived block is always empty --
     there is no compiler yet -- and the page says so rather than hiding it.

  2. An `exact_anchor` link means ONLY "this same source-backed identity occurs
     there". No direction, no relationship type, no lineage. The renderer never
     produces a sentence that could be read as an inferred relationship
     (Revision 6 SS2.4).

NOTE ON MODULE PLACEMENT (recorded, not hidden). Revision 6 SS10.1 lists page
rendering under `assembly.py` at Stage 7C.1, while SS11 requires rendering as a
Stage 7C.0 deliverable. Implementing W0 rendering inside `assembly.py` now
would mean creating the 7C.1 module early, which the stage's scope rules
forbid. This small dedicated 7C.0 module is the minimal-surface resolution;
`assembly.py` remains unwritten and keeps its 7C.1 payload-composition role.
"""

from __future__ import annotations

from collections import defaultdict

from ingestion_bench.wiki_projection.model import WikiProjection

EXACT_ANCHOR_MEANING = "this same source-backed identity occurs there"


def render_page(
    projection: WikiProjection, page_key: str, *, eligible_revision_ids: list[str],
    revision_symbol_by_id: dict[str, str] | None = None,
) -> str:
    """Render one page hub, authority-scoped. Authority filtering is applied
    BEFORE rendering: an ineligible revision's facet is never rendered, and
    the page reports how many facets were hidden rather than silently
    omitting them."""
    symbols = revision_symbol_by_id or {}
    eligible = set(eligible_revision_ids)

    page = next((p for p in projection.page_identities if p.page_key == page_key), None)
    if page is None:
        raise KeyError(f"no page identity {page_key!r} in this projection")

    section_by_chunk = {s.chunk_id: s for s in projection.sections}
    revision_page_by_id = {p.document_revision_id: p for p in projection.revision_pages}
    anchor_by_id = {a.anchor_id: a for a in projection.anchors}
    postings_by_hash = {p.posting_hash: p for p in projection.postings}
    anchor = anchor_by_id[page.anchor_id]

    all_facets = [f for f in projection.facets if f.page_key == page_key]
    facets = [f for f in all_facets if f.document_revision_id in eligible]
    hidden = len(all_facets) - len(facets)

    lines: list[str] = []
    lines.append(f"# {page.display_title}")
    lines.append("")
    lines.append(f"- **page_key**: `{page.page_key}`")
    lines.append(f"- **page_type**: `{page.page_type}` (deterministic, from anchor kind `{anchor.anchor_kind}`)")
    lines.append(f"- **display_title**: verbatim source surface form (never re-worded, never generated)")
    lines.append(f"- **identity_confidence**: `{page.identity_confidence}`")
    lines.append(f"- **anchor_id**: `{anchor.anchor_id[:16]}...`")
    if anchor.is_ambiguous:
        lines.append(f"- **AMBIGUOUS**: one key with several display forms {anchor.display_variants} -- never silently merged")
    if anchor.has_disjoint_identifier_context:
        lines.append(
            "- **DISJOINT IDENTIFIER CONTEXT**: this phrase posts into sections with pairwise-disjoint "
            "identifier sets; its exact-anchor links are downgraded to **advisory**"
        )
    lines.append("")
    lines.append(f"**Authority visibility**: {len(facets)} of {len(all_facets)} revision-scoped facets are eligible "
                 f"under the current query scope; {hidden} hidden. Authority is resolved at query time and is not stored.")
    lines.append("")

    lines.append("## Revision-scoped source facets")
    lines.append("")
    if not facets:
        lines.append("_No facet of this page is eligible under the current authority scope._")
        lines.append("")
    for facet in facets:
        revision_page = revision_page_by_id[facet.document_revision_id]
        symbol = symbols.get(facet.document_revision_id, facet.document_revision_id[:12])
        lines.append(f"### Facet — {facet.logical_document_id} / {symbol}")
        lines.append("")
        lines.append(f"- **document_revision_id**: `{facet.document_revision_id[:16]}...`")
        lines.append(f"- **revision_number**: {revision_page.revision_number}")
        lines.append(f"- **membership_hash**: `{facet.membership_hash[:16]}...`")
        lines.append(
            "- **membership basis**: this page's identity occurs in this revision's source material "
            f"({len(facet.posting_hashes)} anchor posting(s)) — membership is independent of any model output"
        )
        lines.append("")
        for chunk_id in facet.chunk_ids:
            section = section_by_chunk[chunk_id]
            lines.append(f"#### Source section `{section.section_id[:16]}...`")
            lines.append("")
            lines.append(f"- **heading_path**: {' > '.join(section.heading_path) or '(none)'}")
            lines.append(f"- **chunk_id**: `{section.chunk_id[:16]}...`")
            lines.append(f"- **content_sha256**: `{section.content_sha256[:16]}...`")
            lines.append(f"- **source_refs**: `{section.source_refs}`")
            lines.append("")
            lines.append("**A — source-authoritative content** (verbatim `CanonicalChunk.source_text`):")
            lines.append("")
            lines.append("> " + section.source_text.replace("\n", "\n> "))
            lines.append("")
            lines.append("**B — model-derived content**:")
            lines.append("")
            if section.model_derived_text:
                lines.append("> " + section.model_derived_text.replace("\n", "\n> "))
            else:
                lines.append("_None. Stage 7C.0 makes zero LLM calls; no claim, alias or summary exists yet._")
            lines.append("")

            own = [postings_by_hash[h] for h in facet.posting_hashes if postings_by_hash[h].chunk_id == chunk_id]
            lines.append("**Anchor occurrences in this section** (occurrence evidence, never a relationship):")
            lines.append("")
            for posting in own:
                lines.append(
                    f"- `{posting.surface_text}` at {posting.field}[{posting.start_char}:{posting.end_char}] "
                    f"— posting `{posting.posting_hash[:12]}...`"
                )
            lines.append("")

    lines.append("## Navigation")
    lines.append("")
    lines.append(f"_An `exact_anchor` link means only: **{EXACT_ANCHOR_MEANING}**. "
                 "It carries no direction, no relationship type and no lineage. "
                 "A `structural` link expresses only the source hierarchy._")
    lines.append("")

    facet_chunk_ids = {cid for f in facets for cid in f.chunk_ids}
    facet_section_ids = {section_by_chunk[cid].section_id for cid in facet_chunk_ids}
    outgoing = [
        link
        for link in projection.links
        if link.from_section_id in facet_section_ids
        and link.from_document_revision_id in eligible
        and link.to_document_revision_id in eligible
    ]

    by_type: dict[str, list] = defaultdict(list)
    for link in outgoing:
        by_type[link.link_type].append(link)

    for link_type in sorted(by_type):
        lines.append(f"### {link_type} links ({len(by_type[link_type])})")
        lines.append("")
        for link in sorted(by_type[link_type], key=lambda link_: link_.link_id):
            target_revision = symbols.get(link.to_document_revision_id, link.to_document_revision_id[:12])
            if link.link_type == "exact_anchor":
                via = anchor_by_id[link.anchor_id]
                advisory = " **[advisory]**" if link.is_advisory else ""
                lines.append(
                    f"- via anchor `{via.display_text}` → {link.to_logical_document_id} / {target_revision}{advisory} "
                    f"— *{EXACT_ANCHOR_MEANING}*"
                )
            else:
                lines.append(f"- `{link.structural_relation}` → {link.to_logical_document_id} / {target_revision}")
        lines.append("")

    if not outgoing:
        lines.append("_No eligible outgoing link under the current authority scope._")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "_Stage 7C.0 deterministic W0 projection. Zero LLM calls. No claim, alias, summary, "
        "adjudication verdict or facet embedding exists. `is_authoritative_lineage` is False on every link._"
    )
    return "\n".join(lines) + "\n"


def render_revision_page(
    projection: WikiProjection, document_revision_id: str, *, eligible_revision_ids: list[str]
) -> str:
    """Render one revision page view (the derived `WikiRevisionPage`)."""
    page = next((p for p in projection.revision_pages if p.document_revision_id == document_revision_id), None)
    if page is None:
        raise KeyError(f"no revision page {document_revision_id!r}")
    eligible = document_revision_id in set(eligible_revision_ids)
    section_by_id = {s.section_id: s for s in projection.sections}

    lines = [
        f"# {page.logical_document_id} — revision {page.revision_number}",
        "",
        f"- **document_revision_id**: `{page.document_revision_id[:16]}...`",
        f"- **source_document_sha256**: `{page.source_document_sha256[:16]}...`",
        f"- **eligible under current authority scope**: {eligible}",
        "- **stored currency flag**: none — authority is resolved at query time, never stored",
        "",
        "## Heading structure",
        "",
    ]
    for heading in page.heading_structure:
        lines.append(f"- {' > '.join(heading)}")
    lines.append("")
    lines.append("## Sections")
    lines.append("")
    for section_id in page.section_ids:
        section = section_by_id[section_id]
        lines.append(f"### `{section_id[:16]}...`")
        lines.append("")
        lines.append("**A — source-authoritative content**:")
        lines.append("")
        lines.append("> " + section.source_text.replace("\n", "\n> "))
        lines.append("")
        lines.append(f"**Anchors present**: {len(section.anchor_ids)}")
        lines.append("")
    return "\n".join(lines) + "\n"
