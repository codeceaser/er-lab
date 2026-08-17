"""Stage 7C.0: the deterministic Wiki projection records.

Every record here is derived from frozen `CanonicalChunk`s by fixed rules.
NOTHING in this module stores authority state, a `current`/`effective`/
`latest` flag, benchmark truth, Graph output, or any model-derived assertion.
Authority is resolved at QUERY time by the frozen Stage 7R resolver and
applied as a VIEW (see `projection.authority_scoped_view`).

`WikiSection` and `WikiRevisionPage` are derived VIEWS over canonical chunks
(Revision 6 SS10.3: they are deliberately not stored tables). `WikiAnchor` and
`AnchorPosting` are the two stored projection tables.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AnchorKind = Literal["identifier", "phrase", "heading_title"]
PageType = Literal["governed_identifier", "business_topic"]
LinkType = Literal["structural", "exact_anchor"]


class WikiAnchor(BaseModel):
    """STORED. A deterministic identity observed in source material."""

    model_config = ConfigDict(extra="forbid")

    anchor_id: str
    anchor_kind: AnchorKind
    normalized_value: str
    # The anchor's canonical surface form under the frozen W0 display rule
    # (identity.DISPLAY_TITLE_RULE) -- copied verbatim from source, never
    # re-worded and never generated.
    display_text: str
    extraction_method: str

    # True when ONE normalized key carries MORE THAN ONE distinct display
    # surface form. Such an anchor is never silently merged (Revision 6 SS2.1).
    is_ambiguous: bool = False
    display_variants: list[str] = Field(default_factory=list)

    # Revision 6 SS2.1: "A phrase posting into sections with disjoint identifier
    # sets is flagged ambiguous and its links downgraded to advisory." Kept as
    # its OWN field rather than folded into `is_ambiguous`, because the two
    # conditions have different causes and different consequences, and
    # conflating them would hide which rule fired.
    has_disjoint_identifier_context: bool = False


class AnchorPosting(BaseModel):
    """STORED. Occurrence evidence -- NEVER a relationship assertion.

    This record is what makes facet/page membership a property of the TEXT
    (Revision 6 SS2.2): a facet exists if and only if its page identity has at
    least one posting in that revision.
    """

    model_config = ConfigDict(extra="forbid")

    posting_hash: str
    anchor_id: str
    chunk_id: str
    document_revision_id: str
    logical_document_id: str
    # Which frozen chunk field this occurrence was found in.
    field: Literal["source_text", "heading_path"]
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=0)
    surface_text: str
    source_ref: dict


class WikiSection(BaseModel):
    """DERIVED VIEW, 1:1 with a `CanonicalChunk` -- not a stored table.

    `model_derived_text` is carried in its own labelled field and is NEVER
    merged into `source_text` (Revision 6 SS2.1, SS4.7).
    """

    model_config = ConfigDict(extra="forbid")

    section_id: str
    chunk_id: str
    document_revision_id: str
    logical_document_id: str
    chunk_index: int
    chunk_type: str
    heading_path: list[str]
    source_text: str
    model_derived_text: str | None
    content_sha256: str
    source_refs: list[dict]
    anchor_ids: list[str]


class WikiRevisionPage(BaseModel):
    """DERIVED VIEW, one per `document_revision_id`. NO `current` flag."""

    model_config = ConfigDict(extra="forbid")

    document_revision_id: str
    logical_document_id: str
    version_label: str | None
    revision_number: int | None
    source_document_sha256: str
    heading_structure: list[list[str]]
    section_ids: list[str]


class PageIdentity(BaseModel):
    """A deterministic page identity (an information HUB, never a vector)."""

    model_config = ConfigDict(extra="forbid")

    page_key: str
    page_type: PageType
    display_title: str
    anchor_id: str
    normalized_identity: str
    identity_confidence: Literal["exact", "ambiguous"] = "exact"


class Facet(BaseModel):
    """Deterministic membership: `(page_key, document_revision_id)`.

    This record carries NO claim, alias, summary, validation status or
    adjudication verdict -- those belong to Stage 7C.1 and, by Revision 6
    SS4.0, may never alter anything here.
    """

    model_config = ConfigDict(extra="forbid")

    page_key: str
    document_revision_id: str
    logical_document_id: str
    chunk_ids: list[str]
    posting_hashes: list[str]
    membership_hash: str


class WikiLink(BaseModel):
    """A deterministic navigation edge. `is_authoritative_lineage` is False
    ALWAYS -- for every link type, without exception (Revision 6 SS2.1, SS7.1)."""

    model_config = ConfigDict(extra="forbid")

    link_id: str
    link_type: LinkType
    from_section_id: str | None = None
    to_section_id: str | None = None
    from_document_revision_id: str
    to_document_revision_id: str
    from_logical_document_id: str
    to_logical_document_id: str
    # Populated for exact_anchor links only.
    anchor_id: str | None = None
    # Structural relation name, e.g. "section_of_revision_page" -- derived from
    # the source hierarchy, never from an inferred relationship.
    structural_relation: str | None = None
    # Downgraded per Revision 6 SS2.1 when the anchor has disjoint identifier
    # context. Advisory links stay traversable but are marked everywhere.
    is_advisory: bool = False
    is_authoritative_lineage: Literal[False] = False


class ProjectionCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    logical_document_count: int
    revision_count: int
    section_count: int
    anchor_count: int
    anchor_count_by_kind: dict[str, int]
    posting_count: int
    posting_count_by_kind: dict[str, int]
    page_identity_count: int
    page_identity_count_by_type: dict[str, int]
    facet_count: int
    structural_link_count: int
    exact_anchor_link_count: int
    advisory_link_count: int
    m_max: int
    facets_per_page_max_page_keys: list[str]


class WikiProjection(BaseModel):
    """The complete deterministic Stage 7C.0 projection."""

    model_config = ConfigDict(extra="forbid")

    contract_version: str
    corpus_logical_document_ids: list[str]

    sections: list[WikiSection]
    revision_pages: list[WikiRevisionPage]
    anchors: list[WikiAnchor]
    postings: list[AnchorPosting]
    page_identities: list[PageIdentity]
    facets: list[Facet]
    links: list[WikiLink]

    # Every Lane 2 candidate key with its accept/reject decision and reason.
    # Auditable, but deliberately OUTSIDE the hashed projection surface: it is
    # a record of decisions, not a projection record.
    phrase_lane_ledger: list[dict] = Field(default_factory=list)

    counts: ProjectionCounts
    projection_hash: str
