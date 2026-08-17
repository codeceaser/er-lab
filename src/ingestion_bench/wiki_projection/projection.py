"""Stage 7C.0: the deterministic W0 projection build, authority-scoped views,
and the frozen D0 seed / prioritizer contract primitives.

Build order (all deterministic, ZERO LLM calls, zero authority reads):

    frozen CanonicalChunks
      -> WikiSection (1:1 view)  +  WikiRevisionPage (view)
      -> Lane 1 / Lane 2 / Lane 3 anchors
      -> AnchorPostings (occurrence evidence, exact char spans)
      -> deterministic page identities
      -> deterministic facet membership          <-- the structural capital
      -> structural + exact-anchor links
      -> M_max, projection hash

Build time NEVER calls the resolver and stores NO authority state; an
authority change alters only `authority_scoped_view`'s output, never a
record or a hash (Revision 6 SS2.1 "Build vs query time", SS4/SS11 hard tests).
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict

from pydantic import BaseModel, ConfigDict

from ingestion_bench.chunking.model import CanonicalChunk
from ingestion_bench.cross_document_benchmark.fixtures import RevisionFixture
from ingestion_bench.wiki_projection import PROJECTION_CONTRACT_VERSION, identity
from ingestion_bench.wiki_projection.model import (
    AnchorPosting,
    Facet,
    PageIdentity,
    ProjectionCounts,
    WikiAnchor,
    WikiLink,
    WikiProjection,
    WikiRevisionPage,
    WikiSection,
)

EXTRACTION_METHOD_LANE1 = "wiki_lane1_identifier_regex_v1"
EXTRACTION_METHOD_LANE2 = "wiki_lane2_repeated_phrase_v1"
EXTRACTION_METHOD_LANE3 = "wiki_lane3_heading_title_v1"


# --- internal: one raw occurrence before anchors are qualified ---------------


class _RawOccurrence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anchor_kind: str
    normalized_value: str
    surface: str
    chunk_id: str
    document_revision_id: str
    logical_document_id: str
    field: str
    start_char: int
    end_char: int
    source_ref: dict


def _canonical_json(payload) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _primary_source_ref(chunk: CanonicalChunk) -> dict:
    refs = [ref.model_dump(mode="json") for ref in chunk.source_refs]
    return refs[0] if refs else {}


# --- sections and revision pages (derived views) -----------------------------


def _build_sections(fixtures: dict[str, RevisionFixture]) -> list[WikiSection]:
    sections: list[WikiSection] = []
    for fixture in fixtures.values():
        for chunk in fixture.chunks:
            sections.append(
                WikiSection(
                    section_id=identity.compute_section_id(chunk.document_revision_id, chunk.chunk_id),
                    chunk_id=chunk.chunk_id,
                    document_revision_id=chunk.document_revision_id,
                    logical_document_id=chunk.logical_document_id,
                    chunk_index=chunk.chunk_index,
                    chunk_type=chunk.chunk_type,
                    heading_path=list(chunk.heading_path),
                    source_text=chunk.source_text,
                    model_derived_text=chunk.model_derived_text,
                    content_sha256=chunk.content_sha256,
                    source_refs=[ref.model_dump(mode="json") for ref in chunk.source_refs],
                    anchor_ids=[],
                )
            )
    return sorted(sections, key=lambda s: (s.document_revision_id, s.chunk_index, s.chunk_id))


def _build_revision_pages(fixtures: dict[str, RevisionFixture], sections: list[WikiSection]) -> list[WikiRevisionPage]:
    by_revision: dict[str, list[WikiSection]] = defaultdict(list)
    for section in sections:
        by_revision[section.document_revision_id].append(section)

    pages: list[WikiRevisionPage] = []
    for fixture in fixtures.values():
        own = by_revision.get(fixture.document_revision_id, [])
        heading_structure: list[list[str]] = []
        for section in own:
            if section.heading_path and section.heading_path not in heading_structure:
                heading_structure.append(list(section.heading_path))
        pages.append(
            WikiRevisionPage(
                document_revision_id=fixture.document_revision_id,
                logical_document_id=fixture.logical_document_id,
                version_label=fixture.version_label,
                revision_number=fixture.revision_number,
                source_document_sha256=fixture.source_document_sha256,
                heading_structure=heading_structure,
                section_ids=[s.section_id for s in own],
            )
        )
    return sorted(pages, key=lambda p: (p.logical_document_id, p.revision_number or 0, p.document_revision_id))


# --- anchor lanes ------------------------------------------------------------


def _lane1_and_lane3_occurrences(sections: list[WikiSection], chunk_by_id: dict[str, CanonicalChunk]) -> list[_RawOccurrence]:
    """Lane 1 (identifier) over source_text AND heading_path, plus Lane 3
    (heading_title) over heading_path elements.

    Lane 1 note on `IdentifierAnnotation`: Revision 6 SS2.1 specifies
    `IdentifierAnnotation`s with `derivation == "extracted"` PLUS the lifted
    regex "for defense-in-depth". The frozen Stage 5A adapter emits no
    identifier annotations for this corpus (every chunk's `annotation_ids` is
    empty), so on these inputs the regex lane is the whole of Lane 1. Any
    annotation that later exists is additive, never subtractive: the regex
    already finds every span an annotation could contribute here.
    """
    out: list[_RawOccurrence] = []
    for section in sections:
        chunk = chunk_by_id[section.chunk_id]
        source_ref = _primary_source_ref(chunk)

        for occurrence in identity.identifier_occurrences(section.source_text):
            out.append(
                _RawOccurrence(
                    anchor_kind=identity.ANCHOR_KIND_IDENTIFIER, normalized_value=occurrence.normalized,
                    surface=occurrence.surface, chunk_id=section.chunk_id,
                    document_revision_id=section.document_revision_id,
                    logical_document_id=section.logical_document_id, field="source_text",
                    start_char=occurrence.start_char, end_char=occurrence.end_char, source_ref=source_ref,
                )
            )

        # heading_path is a list; spans are relative to each element, and the
        # element index is recorded in the posting's source_ref so the span is
        # unambiguous.
        for index, heading in enumerate(section.heading_path):
            heading_ref = dict(source_ref)
            heading_ref["heading_path_index"] = index
            for occurrence in identity.identifier_occurrences(heading):
                out.append(
                    _RawOccurrence(
                        anchor_kind=identity.ANCHOR_KIND_IDENTIFIER, normalized_value=occurrence.normalized,
                        surface=occurrence.surface, chunk_id=section.chunk_id,
                        document_revision_id=section.document_revision_id,
                        logical_document_id=section.logical_document_id, field="heading_path",
                        start_char=occurrence.start_char, end_char=occurrence.end_char, source_ref=heading_ref,
                    )
                )
            out.append(
                _RawOccurrence(
                    anchor_kind=identity.ANCHOR_KIND_HEADING_TITLE,
                    normalized_value=identity.normalize_phrase(heading), surface=heading,
                    chunk_id=section.chunk_id, document_revision_id=section.document_revision_id,
                    logical_document_id=section.logical_document_id, field="heading_path",
                    start_char=0, end_char=len(heading), source_ref=heading_ref,
                )
            )
    return out


def _lane2_occurrences(
    sections: list[WikiSection], chunk_by_id: dict[str, CanonicalChunk]
) -> tuple[list[_RawOccurrence], list[dict]]:
    """Lane 2: conservative repeated-phrase anchors.

    Two passes, because the qualifying rule is corpus-level: collect every
    candidate with its span, then keep only those whose normalized key occurs
    in >= 2 distinct chunks AND >= 2 distinct logical documents, and which do
    not collide with an identifier key.
    """
    candidates: list[_RawOccurrence] = []
    for section in sections:
        chunk = chunk_by_id[section.chunk_id]
        source_ref = _primary_source_ref(chunk)
        for occurrence in identity.phrase_candidates(section.source_text):
            candidates.append(
                _RawOccurrence(
                    anchor_kind=identity.ANCHOR_KIND_PHRASE, normalized_value=occurrence.normalized,
                    surface=occurrence.surface, chunk_id=section.chunk_id,
                    document_revision_id=section.document_revision_id,
                    logical_document_id=section.logical_document_id, field="source_text",
                    start_char=occurrence.start_char, end_char=occurrence.end_char, source_ref=source_ref,
                )
            )
        for index, heading in enumerate(section.heading_path):
            heading_ref = dict(source_ref)
            heading_ref["heading_path_index"] = index
            for occurrence in identity.phrase_candidates(heading):
                candidates.append(
                    _RawOccurrence(
                        anchor_kind=identity.ANCHOR_KIND_PHRASE, normalized_value=occurrence.normalized,
                        surface=occurrence.surface, chunk_id=section.chunk_id,
                        document_revision_id=section.document_revision_id,
                        logical_document_id=section.logical_document_id, field="heading_path",
                        start_char=occurrence.start_char, end_char=occurrence.end_char, source_ref=heading_ref,
                    )
                )

    chunks_by_key: dict[str, set[str]] = defaultdict(set)
    documents_by_key: dict[str, set[str]] = defaultdict(set)
    for candidate in candidates:
        chunks_by_key[candidate.normalized_value].add(candidate.chunk_id)
        documents_by_key[candidate.normalized_value].add(candidate.logical_document_id)

    kept: list[_RawOccurrence] = []
    ledger: list[dict] = []
    for key in sorted(chunks_by_key):
        distinct_chunks = len(chunks_by_key[key])
        distinct_documents = len(documents_by_key[key])
        if identity.phrase_candidate_is_identifier_colliding(key):
            reason = "identifier_collision"
        elif distinct_chunks < identity.PHRASE_MIN_DISTINCT_CHUNKS:
            reason = "below_min_distinct_chunks"
        elif distinct_documents < identity.PHRASE_MIN_DISTINCT_LOGICAL_DOCUMENTS:
            reason = "below_min_distinct_logical_documents"
        else:
            reason = None
        ledger.append(
            {
                "normalized_phrase": key, "distinct_chunks": distinct_chunks,
                "distinct_logical_documents": distinct_documents,
                "accepted": reason is None, "rejection_reason": reason,
            }
        )
        if reason is None:
            kept.extend(c for c in candidates if c.normalized_value == key)
    return kept, ledger


# --- anchors, postings, identities, membership -------------------------------


def _posting_sort_key(posting: AnchorPosting) -> tuple:
    return (posting.document_revision_id, posting.chunk_id, posting.start_char, posting.end_char, posting.field)


def _build_anchors_and_postings(
    occurrences: list[_RawOccurrence],
) -> tuple[list[WikiAnchor], list[AnchorPosting]]:
    by_anchor: dict[tuple[str, str], list[_RawOccurrence]] = defaultdict(list)
    for occurrence in occurrences:
        by_anchor[(occurrence.anchor_kind, occurrence.normalized_value)].append(occurrence)

    anchors: list[WikiAnchor] = []
    postings: list[AnchorPosting] = []

    for (anchor_kind, normalized_value), group in sorted(by_anchor.items()):
        anchor_id = identity.compute_anchor_id(anchor_kind, normalized_value)
        group_postings = [
            AnchorPosting(
                posting_hash=identity.compute_posting_hash(
                    anchor_id=anchor_id, chunk_id=o.chunk_id, document_revision_id=o.document_revision_id,
                    field=o.field, start_char=o.start_char, end_char=o.end_char,
                ),
                anchor_id=anchor_id, chunk_id=o.chunk_id, document_revision_id=o.document_revision_id,
                logical_document_id=o.logical_document_id, field=o.field,  # type: ignore[arg-type]
                start_char=o.start_char, end_char=o.end_char, surface_text=o.surface, source_ref=o.source_ref,
            )
            for o in group
        ]
        group_postings.sort(key=_posting_sort_key)
        # Deduplicate identical spans (the same identity found by two lanes in
        # the same place is ONE occurrence, never two).
        seen: set[str] = set()
        deduped: list[AnchorPosting] = []
        for posting in group_postings:
            if posting.posting_hash in seen:
                continue
            seen.add(posting.posting_hash)
            deduped.append(posting)

        display_variants = sorted({p.surface_text for p in deduped})
        # The frozen display rule: the FIRST posting's exact surface form in
        # deterministic order (identity.DISPLAY_TITLE_RULE).
        display_text = deduped[0].surface_text

        extraction_method = {
            identity.ANCHOR_KIND_IDENTIFIER: EXTRACTION_METHOD_LANE1,
            identity.ANCHOR_KIND_PHRASE: EXTRACTION_METHOD_LANE2,
            identity.ANCHOR_KIND_HEADING_TITLE: EXTRACTION_METHOD_LANE3,
        }[anchor_kind]

        anchors.append(
            WikiAnchor(
                anchor_id=anchor_id, anchor_kind=anchor_kind,  # type: ignore[arg-type]
                normalized_value=normalized_value, display_text=display_text,
                extraction_method=extraction_method,
                is_ambiguous=len(display_variants) > 1, display_variants=display_variants,
                has_disjoint_identifier_context=False,
            )
        )
        postings.extend(deduped)

    return anchors, postings


def _flag_disjoint_identifier_context(
    anchors: list[WikiAnchor], postings: list[AnchorPosting], sections: list[WikiSection]
) -> None:
    """Revision 6 SS2.1: a PHRASE anchor posting into sections with disjoint
    identifier sets is flagged, and its links are downgraded to advisory.

    Implemented as PAIRWISE disjointness across the sections the phrase posts
    into. The flag is recorded and reported; it deliberately does NOT split the
    page, because splitting is contracted only for the "duplicate names" case
    (SS3.3) -- a deterministic detector cannot tell a genuine duplicate name
    from a legitimate cross-document bridging anchor, and splitting the latter
    would destroy the very hub SS0.1/SS1.5 depend on.
    """
    identifiers_by_chunk = {s.chunk_id: identity.identifiers_in(s.source_text) for s in sections}
    postings_by_anchor: dict[str, list[AnchorPosting]] = defaultdict(list)
    for posting in postings:
        postings_by_anchor[posting.anchor_id].append(posting)

    for anchor in anchors:
        if anchor.anchor_kind != identity.ANCHOR_KIND_PHRASE:
            continue
        chunk_ids = sorted({p.chunk_id for p in postings_by_anchor[anchor.anchor_id]})
        if len(chunk_ids) < 2:
            continue
        sets = [identifiers_by_chunk.get(cid, set()) for cid in chunk_ids]
        pairwise_disjoint = all(
            not (sets[i] & sets[j]) for i in range(len(sets)) for j in range(i + 1, len(sets))
        )
        anchor.has_disjoint_identifier_context = pairwise_disjoint


def _build_page_identities(anchors: list[WikiAnchor]) -> list[PageIdentity]:
    """Only Lane 1 and Lane 2 anchors carry page identities. A
    `heading_title` anchor NEVER creates a hub (Revision 6 SS3.2, SS7.1)."""
    identities: list[PageIdentity] = []
    for anchor in anchors:
        if anchor.anchor_kind not in identity.PAGE_TYPE_BY_ANCHOR_KIND:
            continue
        identities.append(
            PageIdentity(
                page_key=identity.page_key(anchor.anchor_kind, anchor.normalized_value),
                page_type=identity.page_type_for(anchor.anchor_kind),  # type: ignore[arg-type]
                display_title=anchor.display_text,
                anchor_id=anchor.anchor_id,
                normalized_identity=anchor.normalized_value,
                identity_confidence="ambiguous" if (anchor.is_ambiguous or anchor.has_disjoint_identifier_context) else "exact",
            )
        )
    return sorted(identities, key=lambda p: p.page_key)


def _build_facets(page_identities: list[PageIdentity], postings: list[AnchorPosting]) -> list[Facet]:
    """THE membership rule (Revision 6 SS2.2):

        a facet exists if and only if its page identity has >= 1 posting in
        that revision.

    Nothing else can create, remove or alter a facet -- not a claim, an alias,
    a summary, a validation outcome, an adjudication verdict, or a compiler
    failure. That independence is what Stage 7C tests, and it is guaranteed
    here by construction: this function's only inputs are page identities and
    postings.
    """
    postings_by_anchor: dict[str, list[AnchorPosting]] = defaultdict(list)
    for posting in postings:
        postings_by_anchor[posting.anchor_id].append(posting)

    facets: list[Facet] = []
    for page in page_identities:
        grouped: dict[str, list[AnchorPosting]] = defaultdict(list)
        for posting in postings_by_anchor[page.anchor_id]:
            grouped[posting.document_revision_id].append(posting)
        for document_revision_id in sorted(grouped):
            own = sorted(grouped[document_revision_id], key=_posting_sort_key)
            chunk_ids = sorted({p.chunk_id for p in own})
            posting_hashes = [p.posting_hash for p in own]
            facets.append(
                Facet(
                    page_key=page.page_key,
                    document_revision_id=document_revision_id,
                    logical_document_id=own[0].logical_document_id,
                    chunk_ids=chunk_ids,
                    posting_hashes=posting_hashes,
                    membership_hash=_sha256(
                        _canonical_json(
                            {
                                "page_key": page.page_key, "document_revision_id": document_revision_id,
                                "chunk_ids": chunk_ids, "posting_hashes": sorted(posting_hashes),
                            }
                        )
                    ),
                )
            )
    return sorted(facets, key=lambda f: (f.page_key, f.document_revision_id))


# --- links -------------------------------------------------------------------


def _link_id(*parts: str) -> str:
    return _sha256("|".join(parts))


def _build_structural_links(
    sections: list[WikiSection], revision_pages: list[WikiRevisionPage]
) -> list[WikiLink]:
    """Document / page / section hierarchy only. Deterministic, asserts NO
    relationship between entities."""
    links: list[WikiLink] = []
    page_by_revision = {p.document_revision_id: p for p in revision_pages}

    for section in sections:
        page = page_by_revision[section.document_revision_id]
        for relation, from_section, to_section in (
            ("section_of_revision_page", section.section_id, None),
            ("revision_page_has_section", None, section.section_id),
        ):
            links.append(
                WikiLink(
                    link_id=_link_id("structural", relation, section.section_id, page.document_revision_id),
                    link_type="structural", from_section_id=from_section, to_section_id=to_section,
                    from_document_revision_id=section.document_revision_id,
                    to_document_revision_id=page.document_revision_id,
                    from_logical_document_id=section.logical_document_id,
                    to_logical_document_id=page.logical_document_id,
                    structural_relation=relation,
                )
            )

    # Revision-history view: every ordered pair of revisions of the SAME
    # logical document. Carries no currency claim -- only "same document".
    by_document: dict[str, list[WikiRevisionPage]] = defaultdict(list)
    for page in revision_pages:
        by_document[page.logical_document_id].append(page)
    for logical_document_id in sorted(by_document):
        pages = sorted(by_document[logical_document_id], key=lambda p: (p.revision_number or 0, p.document_revision_id))
        for source in pages:
            for target in pages:
                if source.document_revision_id == target.document_revision_id:
                    continue
                links.append(
                    WikiLink(
                        link_id=_link_id("structural", "revision_history", source.document_revision_id, target.document_revision_id),
                        link_type="structural",
                        from_document_revision_id=source.document_revision_id,
                        to_document_revision_id=target.document_revision_id,
                        from_logical_document_id=logical_document_id,
                        to_logical_document_id=logical_document_id,
                        structural_relation="revision_history_sibling",
                    )
                )
    return sorted(links, key=lambda link: link.link_id)


def _build_exact_anchor_links(
    anchors: list[WikiAnchor], postings: list[AnchorPosting], sections: list[WikiSection]
) -> list[WikiLink]:
    """section -(anchor)-> every OTHER section posting the same anchor.

    Means ONLY "this same source-backed identity occurs there". No direction,
    no relationship type, no lineage -- ever.
    """
    section_by_chunk = {s.chunk_id: s for s in sections}
    anchor_by_id = {a.anchor_id: a for a in anchors}
    postings_by_anchor: dict[str, list[AnchorPosting]] = defaultdict(list)
    for posting in postings:
        postings_by_anchor[posting.anchor_id].append(posting)

    links: list[WikiLink] = []
    for anchor_id in sorted(postings_by_anchor):
        anchor = anchor_by_id[anchor_id]
        chunk_ids = sorted({p.chunk_id for p in postings_by_anchor[anchor_id]})
        if len(chunk_ids) < 2:
            continue
        for source_chunk in chunk_ids:
            for target_chunk in chunk_ids:
                if source_chunk == target_chunk:
                    continue
                source = section_by_chunk[source_chunk]
                target = section_by_chunk[target_chunk]
                links.append(
                    WikiLink(
                        link_id=_link_id("exact_anchor", anchor_id, source.section_id, target.section_id),
                        link_type="exact_anchor", from_section_id=source.section_id, to_section_id=target.section_id,
                        from_document_revision_id=source.document_revision_id,
                        to_document_revision_id=target.document_revision_id,
                        from_logical_document_id=source.logical_document_id,
                        to_logical_document_id=target.logical_document_id,
                        anchor_id=anchor_id,
                        is_advisory=anchor.has_disjoint_identifier_context,
                    )
                )
    return sorted(links, key=lambda link: link.link_id)


# --- M_max -------------------------------------------------------------------


def compute_m_max(facets: list[Facet]) -> tuple[int, list[str]]:
    """Revision 6 SS6.5, the R6 addition:

        M_max = max over page_key of
                |{document_revision_id : page has >= 1 anchor posting there}|

    A MEASURED property of the completed projection, never a configuration
    knob and never chosen by hand. It is the term R5's ceiling
    `C = (P_seed + B) x F_max` was missing, and it is frozen with 7C.0 so that
    Stage 7C.2 can evaluate `C = (P_seed + B) x M_max x F_max`.
    """
    revisions_by_page: dict[str, set[str]] = defaultdict(set)
    for facet in facets:
        revisions_by_page[facet.page_key].add(facet.document_revision_id)
    if not revisions_by_page:
        return 0, []
    m_max = max(len(revisions) for revisions in revisions_by_page.values())
    argmax = sorted(key for key, revisions in revisions_by_page.items() if len(revisions) == m_max)
    return m_max, argmax


# --- the build ---------------------------------------------------------------


def build_projection(fixtures: dict[str, RevisionFixture]) -> WikiProjection:
    """Build the complete deterministic projection. ZERO LLM calls, zero
    authority reads, zero benchmark-truth reads."""
    chunk_by_id: dict[str, CanonicalChunk] = {c.chunk_id: c for fx in fixtures.values() for c in fx.chunks}

    sections = _build_sections(fixtures)
    revision_pages = _build_revision_pages(fixtures, sections)

    lane13 = _lane1_and_lane3_occurrences(sections, chunk_by_id)
    lane2, lane2_ledger = _lane2_occurrences(sections, chunk_by_id)

    anchors, postings = _build_anchors_and_postings(lane13 + lane2)
    _flag_disjoint_identifier_context(anchors, postings, sections)

    # Back-fill each section's anchor inventory (a view field, derived from
    # postings -- never an independent source of membership).
    anchors_by_chunk: dict[str, set[str]] = defaultdict(set)
    for posting in postings:
        anchors_by_chunk[posting.chunk_id].add(posting.anchor_id)
    for section in sections:
        section.anchor_ids = sorted(anchors_by_chunk.get(section.chunk_id, set()))

    page_identities = _build_page_identities(anchors)
    facets = _build_facets(page_identities, postings)

    links = _build_structural_links(sections, revision_pages) + _build_exact_anchor_links(anchors, postings, sections)
    links.sort(key=lambda link: link.link_id)

    m_max, m_max_pages = compute_m_max(facets)

    anchor_count_by_kind: dict[str, int] = defaultdict(int)
    for anchor in anchors:
        anchor_count_by_kind[anchor.anchor_kind] += 1
    anchor_kind_by_id = {a.anchor_id: a.anchor_kind for a in anchors}
    posting_count_by_kind: dict[str, int] = defaultdict(int)
    for posting in postings:
        posting_count_by_kind[anchor_kind_by_id[posting.anchor_id]] += 1
    page_count_by_type: dict[str, int] = defaultdict(int)
    for page in page_identities:
        page_count_by_type[page.page_type] += 1

    counts = ProjectionCounts(
        logical_document_count=len({fx.logical_document_id for fx in fixtures.values()}),
        revision_count=len(revision_pages),
        section_count=len(sections),
        anchor_count=len(anchors),
        anchor_count_by_kind=dict(sorted(anchor_count_by_kind.items())),
        posting_count=len(postings),
        posting_count_by_kind=dict(sorted(posting_count_by_kind.items())),
        page_identity_count=len(page_identities),
        page_identity_count_by_type=dict(sorted(page_count_by_type.items())),
        facet_count=len(facets),
        structural_link_count=sum(1 for link in links if link.link_type == "structural"),
        exact_anchor_link_count=sum(1 for link in links if link.link_type == "exact_anchor"),
        advisory_link_count=sum(1 for link in links if link.is_advisory),
        m_max=m_max,
        facets_per_page_max_page_keys=m_max_pages,
    )

    projection = WikiProjection(
        contract_version=PROJECTION_CONTRACT_VERSION,
        corpus_logical_document_ids=sorted({fx.logical_document_id for fx in fixtures.values()}),
        sections=sections, revision_pages=revision_pages, anchors=anchors, postings=postings,
        page_identities=page_identities, facets=facets, links=links,
        phrase_lane_ledger=lane2_ledger, counts=counts,
        projection_hash="",
    )
    projection.projection_hash = compute_projection_hash(projection)
    return projection


def compute_projection_hash(projection: WikiProjection) -> str:
    """Deterministic hash over every projection record. Independent of
    authority state, of wall-clock time, and of run identity -- so an
    authority change provably cannot move it."""
    payload = {
        "contract_version": projection.contract_version,
        "corpus_logical_document_ids": projection.corpus_logical_document_ids,
        "sections": [s.model_dump(mode="json") for s in projection.sections],
        "revision_pages": [p.model_dump(mode="json") for p in projection.revision_pages],
        "anchors": [a.model_dump(mode="json") for a in projection.anchors],
        "postings": [p.model_dump(mode="json") for p in projection.postings],
        "page_identities": [p.model_dump(mode="json") for p in projection.page_identities],
        "facets": [f.model_dump(mode="json") for f in projection.facets],
        "links": [link.model_dump(mode="json") for link in projection.links],
    }
    return _sha256(_canonical_json(payload))


# --- authority-scoped views (QUERY time only) --------------------------------


class AuthorityScopedView(BaseModel):
    """A VIEW. Authority filtering happens HERE, never in the build, and never
    changes a stored record or a hash."""

    model_config = ConfigDict(extra="forbid")

    eligible_revision_ids: list[str]
    section_ids: list[str]
    revision_page_ids: list[str]
    facet_keys: list[tuple[str, str]]
    visible_page_keys: list[str]
    link_ids: list[str]
    hidden_section_count: int
    hidden_facet_count: int
    hidden_link_count: int


def authority_scoped_view(projection: WikiProjection, eligible_revision_ids: list[str]) -> AuthorityScopedView:
    """Restrict the projection to `eligible_revision_ids` BEFORE anything is
    ranked or rendered. An empty eligible set yields an empty view -- never
    "show everything".

    A link survives only when BOTH endpoints are eligible, so no traversal can
    leak into an ineligible revision.
    """
    eligible = set(eligible_revision_ids)

    sections = [s for s in projection.sections if s.document_revision_id in eligible]
    pages = [p for p in projection.revision_pages if p.document_revision_id in eligible]
    facets = [f for f in projection.facets if f.document_revision_id in eligible]
    links = [
        link
        for link in projection.links
        if link.from_document_revision_id in eligible and link.to_document_revision_id in eligible
    ]

    return AuthorityScopedView(
        eligible_revision_ids=sorted(eligible),
        section_ids=[s.section_id for s in sections],
        revision_page_ids=[p.document_revision_id for p in pages],
        facet_keys=[(f.page_key, f.document_revision_id) for f in facets],
        visible_page_keys=sorted({f.page_key for f in facets}),
        link_ids=[link.link_id for link in links],
        hidden_section_count=len(projection.sections) - len(sections),
        hidden_facet_count=len(projection.facets) - len(facets),
        hidden_link_count=len(projection.links) - len(links),
    )


# --- FROZEN D0 CONTRACT PRIMITIVES -- defined and tested, NOT executed -------
#
# Revision 6 SS7.4.2 requires the D0 seed procedure and D0 branch prioritizer to
# be FROZEN at 7C.0 so that Stage 7C.2 cannot tune them toward a result. The
# deterministic primitives live here because they operate on anchor postings,
# which are this module's domain.
#
# Stage 7C.0 does NOT run a D0 benchmark: no query is embedded for D0, no hub
# expansion is performed, no traversal is executed and no evidence is assembled.
# Only the ordering rules are implemented and tested.

D0_SEED_PROCEDURE_VERSION = "d0_seed_procedure_v1"
D0_PRIORITIZER_VERSION = "d0_branch_prioritizer_v1"

D0_SEED_PROCEDURE_STEPS = [
    "embed the query once with the EXISTING V/W0 embedding provider (no new embedding representation)",
    "authority-first search over the EXISTING chunk embeddings: WHERE document_revision_id IN (:eligible) ORDER BY embedding <=> :q",
    "retrieve up to P_seed = K source chunks",
    "map each retrieved chunk to its deterministic AnchorPostings",
    "map those postings to page identities (Lane 1 / Lane 2 pages only)",
    "order seed pages by (retrieved chunk rank, posting start_char, posting end_char, stable page_key)",
    "deduplicate preserving first occurrence",
    "truncate to P_seed",
    "record the rank-1 seed page as the later path origin",
]

D0_PRIORITIZER_CLAUSES = [
    "(a) max cosine between the already-computed query embedding and the EXISTING chunk embeddings of the target page's eligible facets",
    "(b) deterministic link-type priority: exact_anchor before structural",
    "(c) stable page_key order",
]

_D0_LINK_TYPE_PRIORITY = {"exact_anchor": 0, "structural": 1}


class D0SeedPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_key: str
    seed_rank: int
    origin_chunk_id: str
    origin_chunk_rank: int
    origin_posting_hash: str


def d0_seed_pages_from_ranked_chunks(
    *, ranked_chunk_ids: list[str], projection: WikiProjection, eligible_revision_ids: list[str], p_seed: int
) -> list[D0SeedPage]:
    """The frozen D0 seed ordering rule (steps 4-9), as a PURE function.

    Takes an already-ranked chunk list -- it never embeds, never searches and
    never traverses -- so freezing it here commits the ordering without running
    any part of the D0 benchmark. Carries NO facet embedding, NO claim, NO
    alias, NO summary and NO compiler output of any kind.
    """
    eligible = set(eligible_revision_ids)
    page_by_anchor = {p.anchor_id: p for p in projection.page_identities}
    postings_by_chunk: dict[str, list[AnchorPosting]] = defaultdict(list)
    for posting in projection.postings:
        if posting.document_revision_id in eligible and posting.anchor_id in page_by_anchor:
            postings_by_chunk[posting.chunk_id].append(posting)

    seeds: list[D0SeedPage] = []
    seen: set[str] = set()
    for chunk_rank, chunk_id in enumerate(ranked_chunk_ids, start=1):
        candidates = sorted(
            postings_by_chunk.get(chunk_id, []),
            key=lambda p: (p.start_char, p.end_char, page_by_anchor[p.anchor_id].page_key),
        )
        for posting in candidates:
            key = page_by_anchor[posting.anchor_id].page_key
            if key in seen:
                continue
            seen.add(key)
            seeds.append(
                D0SeedPage(
                    page_key=key, seed_rank=len(seeds) + 1, origin_chunk_id=chunk_id,
                    origin_chunk_rank=chunk_rank, origin_posting_hash=posting.posting_hash,
                )
            )
            if len(seeds) >= p_seed:
                return seeds
    return seeds


def d0_branch_order(candidates: list[tuple[str, str, float]]) -> list[str]:
    """The frozen D0 branch-prioritization rule, as a PURE comparator.

    `candidates` are `(page_key, link_type, max_chunk_cosine)` triples; the
    caller supplies the cosine because Stage 7C.0 does not execute a traversal.
    Ordering: descending chunk cosine, then link-type priority, then stable
    page_key. Reads NO facet embedding, NO claim predicate, NO summary and NO
    alias -- by construction, since none of those is even a parameter.
    """
    return [
        page_key
        for page_key, _link_type, _cosine in sorted(
            candidates,
            key=lambda triple: (-triple[2], _D0_LINK_TYPE_PRIORITY.get(triple[1], 99), triple[0]),
        )
    ]


def d0_contract_identity() -> dict:
    """The frozen D0 seed + prioritizer contract and its hash."""
    seed = {"version": D0_SEED_PROCEDURE_VERSION, "steps": D0_SEED_PROCEDURE_STEPS}
    prioritizer = {"version": D0_PRIORITIZER_VERSION, "clauses": D0_PRIORITIZER_CLAUSES,
                   "link_type_priority": _D0_LINK_TYPE_PRIORITY}
    return {
        "seed_procedure": {**seed, "sha256": _sha256(_canonical_json(seed))},
        "branch_prioritizer": {**prioritizer, "sha256": _sha256(_canonical_json(prioritizer))},
        "forbidden_inputs": [
            "W1 facet embeddings", "compiler output", "claims", "summary sentences", "aliases",
            "adjudication verdicts", "query-time LLM reasoning",
        ],
        "executed_in_stage_7c0": False,
    }
