"""Stage 7C.2: hub expansion, traversal and the per-arm link sets.

ONE traversal engine, four arm configurations. The arms differ in exactly two
places -- the SEED representation (supplied by `retrieval.py`) and the
TRAVERSABLE LINK SET declared here -- so any measured difference between them is
attributable to those two variables and nothing else.

    D0          structural + exact_anchor      seed: chunk vectors (no W1 output)
    W1-D        structural + exact_anchor      seed: frozen W1 facet vectors
    W1-FULL     + frozen claim_derived         seed: frozen W1 facet vectors
    N_advisory  + advisory_semantic            diagnostic only

Read-only over frozen Stage 7C.0/7C.1 artifacts. This module makes no compiler
call, creates no embedding, and mutates nothing it is given -- the counterfactual
suppression probe is a READ-TIME filter over the frozen link set, never a write.

Three invariants the engine enforces rather than assumes:

* **Authority first.** Eligibility is applied when facets are expanded and when
  neighbours are exposed, never after ranking. An ineligible facet cannot
  contribute a chunk, a neighbour or a rank position.
* **Links are movement, never evidence.** Only `CanonicalChunk`s are collected
  as evidence; a link's own text never enters the evidence set.
* **A missing claim removes nothing.** Claim-derived links add routing; the
  deterministic membership, chunks, anchors and exact-anchor connectivity of
  every facet stand whether or not any claim exists (SS3.7.1).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ingestion_bench.wiki_projection.model import WikiProjection
from ingestion_bench.wiki_projection.validation import DerivedLink

ArmName = Literal["D0", "W1-D", "W1-FULL", "N_advisory"]

# Revision 6 SS7.1: only identifier and phrase anchors are traversable.
# `heading_title` stays structural-only -- a shared heading asserts document
# template similarity, not entity co-occurrence, and traversing it would connect
# every "Operating Procedures" section to every other.
TRAVERSABLE_ANCHOR_KINDS = frozenset({"identifier", "phrase"})

# Frozen traversal bounds (SS6.5, SS7.3).
HOP_BUDGET_B = 6
M_MAX = 3
F_MAX = 12

# The link sets each arm may traverse.
ARM_LINK_SETS: dict[str, frozenset[str]] = {
    "D0": frozenset({"structural", "exact_anchor"}),
    "W1-D": frozenset({"structural", "exact_anchor"}),
    "W1-FULL": frozenset({"structural", "exact_anchor", "claim_derived"}),
    "N_advisory": frozenset({"structural", "exact_anchor", "claim_derived", "advisory_semantic"}),
}

# Arms that consume W1-derived model output anywhere in their path. Gate Q
# failed, so every result from these must carry the non-qualifying label.
W1_DERIVED_ARMS = frozenset({"W1-D", "W1-FULL", "N_advisory"})

NON_QUALIFYING_LABEL = "NON-QUALIFYING / DIAGNOSTIC ONLY"

# Deterministic link-type priority (SS7.3 clause c / SS7.4.2 clause b).
_LINK_TYPE_PRIORITY = {"claim_derived": 0, "exact_anchor": 1, "structural": 2, "advisory_semantic": 3}


def candidate_ceiling(p_seed: int) -> int:
    """C = (P_seed + B) x M_max x F_max -- the corrected R6 bound. A
    non-selection compute guard; if it ever binds that is a contract-breach
    event, reported and never silently truncated."""
    return (p_seed + HOP_BUDGET_B) * M_MAX * F_MAX


class Neighbour(BaseModel):
    """One navigation opportunity exposed at a visited hub."""

    model_config = ConfigDict(extra="forbid")

    target_page_key: str
    link_type: str
    link_id: str
    # Populated for claim_derived hops only; verbatim, never fabricated.
    predicate: str | None = None
    claim_id: str | None = None
    traversal_direction: str | None = None
    anchor_id: str | None = None
    source_chunk_ids: list[str] = Field(default_factory=list)
    source_snippet: str | None = None
    document_revision_id: str | None = None
    authority_eligible: bool = True
    branch_priority_cosine: float | None = None
    branch_priority_lexical: float | None = None
    final_order: int | None = None
    selected: bool = False
    selection_reason: str = ""
    is_authoritative_lineage: Literal[False] = False


class Hop(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hop_index: int
    from_page_key: str
    to_page_key: str
    mechanism: str
    link_id: str
    predicate: str | None = None
    claim_id: str | None = None
    justifying_chunk_ids: list[str] = Field(default_factory=list)
    path_establishing_chunk_id: str | None = None


class HubVisit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_key: str
    arrived_by: str
    eligible_facets: list[str] = Field(default_factory=list)
    chunks_collected: list[str] = Field(default_factory=list)
    neighbours_exposed: list[Neighbour] = Field(default_factory=list)
    ineligible_neighbours_removed: int = 0


class NavigationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arm: str
    seed_page_keys: list[str]
    path: list[Hop] = Field(default_factory=list)
    visits: list[HubVisit] = Field(default_factory=list)
    reached_chunk_ids: list[str] = Field(default_factory=list)
    path_establishing_chunk_ids: list[str] = Field(default_factory=list)

    pages_visited: int = 0
    hops_taken: int = 0
    b_bound_hit: bool = False
    c_bound_hit: bool = False
    candidates_examined: int = 0
    claim_derived_traversals: int = 0
    exact_anchor_traversals: int = 0
    structural_traversals: int = 0
    advisory_traversals: int = 0
    ineligible_neighbours_removed: int = 0
    prioritizer_degraded: bool = False


def _page_key_of_section(projection: WikiProjection, section_id: str) -> list[str]:
    """Every page identity whose facet contains the section's chunk."""
    section = next((s for s in projection.sections if s.section_id == section_id), None)
    if section is None:
        return []
    return sorted({f.page_key for f in projection.facets if section.chunk_id in f.chunk_ids})


class Navigator:
    """The shared traversal engine, configured per arm.

    Constructed once per measured run over the frozen projection; holds no
    mutable state between queries beyond the indexes it builds read-only.
    """

    def __init__(
        self,
        projection: WikiProjection,
        *,
        derived_links: list[DerivedLink] | None = None,
        advisory_links: list[tuple[str, str, float]] | None = None,
    ) -> None:
        self.projection = projection
        self.derived_links = list(derived_links or [])
        self.advisory_links = list(advisory_links or [])

        self._sections_by_chunk = {s.chunk_id: s for s in projection.sections}
        self._section_by_id = {s.section_id: s for s in projection.sections}
        self._anchor_by_id = {a.anchor_id: a for a in projection.anchors}
        self._facets_by_page: dict[str, list] = {}
        for facet in projection.facets:
            self._facets_by_page.setdefault(facet.page_key, []).append(facet)

        # Deterministic links indexed by the page they leave from.
        self._structural_by_page: dict[str, list] = {}
        self._exact_by_page: dict[str, list] = {}
        for link in projection.links:
            if link.from_section_id is None:
                continue
            for page_key in _page_key_of_section(projection, link.from_section_id):
                if link.link_type == "structural":
                    self._structural_by_page.setdefault(page_key, []).append(link)
                elif link.link_type == "exact_anchor":
                    self._exact_by_page.setdefault(page_key, []).append(link)

        self._claim_by_page: dict[str, list[DerivedLink]] = {}
        for link in self.derived_links:
            origin = link.subject_page_key if link.traversal_direction == "forward" else link.object_page_key
            self._claim_by_page.setdefault(origin, []).append(link)

    # --- expansion -------------------------------------------------------

    def eligible_facets(self, page_key: str, eligible: set[str]) -> list:
        return sorted(
            (f for f in self._facets_by_page.get(page_key, []) if f.document_revision_id in eligible),
            key=lambda f: f.document_revision_id,
        )

    def expand_page(self, page_key: str, eligible: set[str]) -> tuple[list[str], list[str]]:
        """SS6.4 step [4]: expand ALL eligible facets of a page and collect their
        deterministic source chunks. No claim is required -- membership is a
        property of the source text (SS2.2)."""
        facets = self.eligible_facets(page_key, eligible)
        chunk_ids: list[str] = []
        for facet in facets:
            for chunk_id in facet.chunk_ids:
                if chunk_id not in chunk_ids:
                    chunk_ids.append(chunk_id)
        return [f"{f.page_key}|{f.document_revision_id}" for f in facets], chunk_ids

    # --- neighbour exposure ----------------------------------------------

    def expose_neighbours(
        self, page_key: str, *, arm: str, eligible: set[str], suppressed_link_ids: set[str] | None = None
    ) -> tuple[list[Neighbour], int]:
        """Every navigation opportunity this ARM may see from this hub.

        `suppressed_link_ids` is the SS8.G read-time filter: it hides frozen
        links from this traversal without touching the stored set.
        """
        permitted = ARM_LINK_SETS[arm]
        suppressed = suppressed_link_ids or set()
        neighbours: list[Neighbour] = []
        removed = 0

        if "exact_anchor" in permitted:
            for link in self._exact_by_page.get(page_key, []):
                if link.link_id in suppressed:
                    continue
                anchor = self._anchor_by_id.get(link.anchor_id) if link.anchor_id else None
                # SS7.1: only identifier and phrase anchors are traversable.
                if anchor is None or anchor.anchor_kind not in TRAVERSABLE_ANCHOR_KINDS:
                    continue
                if link.to_document_revision_id not in eligible:
                    removed += 1
                    continue
                target_section = self._section_by_id.get(link.to_section_id or "")
                if target_section is None:
                    continue
                for target_page in _page_key_of_section(self.projection, target_section.section_id):
                    if target_page == page_key:
                        continue
                    neighbours.append(
                        Neighbour(
                            target_page_key=target_page, link_type="exact_anchor", link_id=link.link_id,
                            anchor_id=link.anchor_id, source_chunk_ids=[target_section.chunk_id],
                            source_snippet=target_section.source_text[:200],
                            document_revision_id=link.to_document_revision_id, authority_eligible=True,
                        )
                    )

        if "claim_derived" in permitted:
            for link in self._claim_by_page.get(page_key, []):
                if link.link_id in suppressed:
                    continue
                target = link.object_page_key if link.traversal_direction == "forward" else link.subject_page_key
                if target == page_key:
                    continue
                if link.document_revision_id not in eligible:
                    removed += 1
                    continue
                chunk_ids = list(link.source_citations.get("supporting_chunk_ids", []))
                snippet = None
                if chunk_ids and chunk_ids[0] in self._sections_by_chunk:
                    snippet = self._sections_by_chunk[chunk_ids[0]].source_text[:200]
                neighbours.append(
                    Neighbour(
                        target_page_key=target, link_type="claim_derived", link_id=link.link_id,
                        predicate=link.predicate, claim_id=link.claim_id,
                        traversal_direction=link.traversal_direction,
                        source_chunk_ids=chunk_ids, source_snippet=snippet,
                        document_revision_id=link.document_revision_id, authority_eligible=True,
                    )
                )

        if "structural" in permitted:
            for link in self._structural_by_page.get(page_key, []):
                if link.link_id in suppressed or link.to_section_id is None:
                    continue
                if link.to_document_revision_id not in eligible:
                    removed += 1
                    continue
                target_section = self._section_by_id.get(link.to_section_id)
                if target_section is None:
                    continue
                for target_page in _page_key_of_section(self.projection, target_section.section_id):
                    if target_page == page_key:
                        continue
                    neighbours.append(
                        Neighbour(
                            target_page_key=target_page, link_type="structural", link_id=link.link_id,
                            source_chunk_ids=[target_section.chunk_id],
                            source_snippet=target_section.source_text[:200],
                            document_revision_id=link.to_document_revision_id, authority_eligible=True,
                        )
                    )

        if "advisory_semantic" in permitted:
            for source_page, target_page, score in self.advisory_links:
                if source_page != page_key or target_page == page_key:
                    continue
                neighbours.append(
                    Neighbour(
                        target_page_key=target_page, link_type="advisory_semantic",
                        link_id=f"advisory::{source_page}::{target_page}",
                        branch_priority_cosine=score, authority_eligible=True,
                    )
                )

        # Deduplicate by (target, link_type) preserving first exposure.
        seen: set[tuple[str, str]] = set()
        deduped: list[Neighbour] = []
        for neighbour in neighbours:
            key = (neighbour.target_page_key, neighbour.link_type)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(neighbour)
        return deduped, removed


def order_neighbours(
    neighbours: list[Neighbour], *, arm: str, query_text: str, target_cosine: dict[str, float]
) -> list[Neighbour]:
    """Frozen branch prioritization.

    W1 arms (SS7.3): query cosine against the target page's eligible FACET
    embedding, then lexical predicate overlap, then link-type priority, then
    stable page key.

    D0 (SS7.4.2): the same shape with the facet-embedding term replaced by
    cosine against the target page's existing CHUNK embeddings, and with clause
    (b) inapplicable -- D0 traverses no claim-derived link, so it has no
    predicate to overlap.
    """
    query_terms = {t for t in query_text.casefold().split() if len(t) > 2}

    def lexical(neighbour: Neighbour) -> float:
        if arm == "D0" or not neighbour.predicate:
            return 0.0
        predicate_terms = {t for t in neighbour.predicate.casefold().split() if len(t) > 2}
        if not predicate_terms:
            return 0.0
        return len(predicate_terms & query_terms) / len(predicate_terms)

    for neighbour in neighbours:
        neighbour.branch_priority_cosine = target_cosine.get(neighbour.target_page_key, 0.0)
        neighbour.branch_priority_lexical = lexical(neighbour)

    ordered = sorted(
        neighbours,
        key=lambda n: (
            -(n.branch_priority_cosine or 0.0),
            -(n.branch_priority_lexical or 0.0),
            _LINK_TYPE_PRIORITY.get(n.link_type, 99),
            n.target_page_key,
        ),
    )
    for index, neighbour in enumerate(ordered):
        neighbour.final_order = index
        neighbour.selection_reason = (
            f"cosine={neighbour.branch_priority_cosine:.4f}, "
            f"lexical={neighbour.branch_priority_lexical:.4f}, "
            f"type_priority={_LINK_TYPE_PRIORITY.get(neighbour.link_type, 99)}, "
            f"stable_key={neighbour.target_page_key}"
        )
    return ordered
