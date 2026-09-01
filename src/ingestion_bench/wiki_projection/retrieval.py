"""Stage 7C.2: the unified Wiki retrieval flow and the frozen final-K policy.

    query + authority context
      -> eligible revisions                    (frozen Stage 7R resolver)
      -> SEED                                  (arm-specific; the first variable)
      -> hub expansion                         (deterministic membership, SS2.2)
      -> neighbour exposure + traversal        (arm link set; the second variable)
      -> structurally reached CanonicalChunks
      -> frozen two-tier final-K policy
      -> the frozen Stage 7B.0 evaluator

Read-only over frozen Stage 7C.0/7C.1 artifacts. No compiler call, no embedding
creation, no page vector, no reranker, no query-time LLM, no Vector backfill.

Two seeds, one engine. That is the whole experiment: D0 seeds from the existing
V/W0 chunk vectors and consumes NO W1-derived output; W1-D and W1-FULL seed from
the frozen post-adjudication facet vectors. Holding everything else identical is
what makes the three attribution deltas interpretable.

**Benchmark truth is unreachable from here.** Nothing in this module reads
required facts, forbidden facts or expected chains; only the frozen evaluator
and the explicitly truth-informed suppression probe may.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ingestion_bench.wiki_projection.facet_store import cosine_similarity
from ingestion_bench.wiki_projection.model import WikiProjection
from ingestion_bench.wiki_projection.navigation import (
    HOP_BUDGET_B,
    Hop,
    HubVisit,
    NavigationResult,
    Navigator,
    candidate_ceiling,
    order_neighbours,
)


class SeedPage(BaseModel):
    """One selected seed hub, with the evidence that produced it."""

    model_config = ConfigDict(extra="forbid")

    page_key: str
    rank: int
    # W1 arms: the facet that matched and its similarity. D0: the retrieved
    # chunk and the posting that mapped it to this page.
    seed_facet: str | None = None
    seed_page_priority: float | None = None
    origin_chunk_id: str | None = None
    origin_chunk_rank: int | None = None
    origin_posting_hash: str | None = None
    seed_order_rule: str = ""


class WikiRetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arm: str
    question_id: str
    top_k: int

    eligible_revision_ids: list[str]
    eligible_pages: int
    eligible_chunks: int

    seeds: list[SeedPage] = Field(default_factory=list)
    seed_pages_selected: int = 0
    seed_pages_expanded: int = 0

    navigation: NavigationResult | None = None

    tier1_chunk_ids: list[str] = Field(default_factory=list)
    tier2_chunk_ids: list[str] = Field(default_factory=list)
    final_chunk_ids: list[str] = Field(default_factory=list)
    candidate_chunks: int = 0

    p_bound_hit: bool = False
    b_bound_hit: bool = False
    c_bound_hit: bool = False
    short_list: bool = False
    path_truncated: bool = False

    page_saturation: float = 0.0
    chunk_saturation: float = 0.0
    latency_seconds: float = 0.0
    query_embedding_calls: int = 0
    cosine_operations: int = 0

    non_qualifying_label: str | None = None


# --- seeding ------------------------------------------------------------------


def seed_d0(
    *,
    projection: WikiProjection,
    ranked_chunk_ids: list[str],
    eligible: set[str],
    p_seed: int,
) -> list[SeedPage]:
    """The frozen D0 seed procedure (SS7.4.2), steps 4-9.

    Consumes NO W1-derived output: it maps already-ranked chunks from the
    existing V/W0 vector space through frozen anchor postings to page
    identities, ordered by (chunk rank, posting span, stable page key).
    """
    from ingestion_bench.wiki_projection.projection import d0_seed_pages_from_ranked_chunks

    raw = d0_seed_pages_from_ranked_chunks(
        ranked_chunk_ids=ranked_chunk_ids, projection=projection,
        eligible_revision_ids=sorted(eligible), p_seed=p_seed,
    )
    return [
        SeedPage(
            page_key=s.page_key, rank=s.seed_rank, origin_chunk_id=s.origin_chunk_id,
            origin_chunk_rank=s.origin_chunk_rank, origin_posting_hash=s.origin_posting_hash,
            seed_order_rule="D0_posting_order",
        )
        for s in raw
    ]


def seed_w1(
    *,
    facet_rows: list,
    query_vector: list[float],
    eligible: set[str],
    p_seed: int,
) -> tuple[list[SeedPage], int]:
    """The W1 seed: authority-first search over the FROZEN facet vectors.

    Eligibility is applied to the candidate pool BEFORE ranking, so an
    ineligible facet can never occupy a rank position. Pages are ordered by
    `seed_page_priority` = max eligible-facet similarity (SS6.3), which is a
    grouping convenience for ordering hubs -- never "semantic page retrieval",
    because no page vector exists.
    """
    pool = [row for row in facet_rows if row.document_revision_id in eligible]
    scored = [(row, cosine_similarity(query_vector, row.embedding)) for row in pool]
    cosine_ops = len(scored)

    best: dict[str, tuple[float, object]] = {}
    for row, score in scored:
        current = best.get(row.page_key)
        if current is None or score > current[0]:
            best[row.page_key] = (score, row)

    ordered = sorted(best.items(), key=lambda item: (-item[1][0], item[0]))
    seeds = [
        SeedPage(
            page_key=page_key, rank=index,
            seed_facet=f"{row.page_key}|{row.document_revision_id}",
            seed_page_priority=score, seed_order_rule="seed_page_priority",
        )
        for index, (page_key, (score, row)) in enumerate(ordered[:p_seed], start=1)
    ]
    return seeds, cosine_ops


# --- the unified flow ----------------------------------------------------------


def run_arm(
    *,
    arm: str,
    question_id: str,
    query_text: str,
    query_vector: list[float],
    top_k: int,
    eligible_revision_ids: list[str],
    projection: WikiProjection,
    navigator: Navigator,
    seeds: list[SeedPage],
    chunk_vectors: dict[str, list[float]],
    facet_vectors_by_page: dict[str, list[float]],
    suppressed_link_ids: set[str] | None = None,
    query_embedding_calls: int = 1,
    seed_cosine_operations: int = 0,
) -> WikiRetrievalResult:
    """Execute SS6.4 steps [4]-[10] for one arm and one question.

    The seed is supplied by the caller so the two seed procedures stay visibly
    separate; everything after it is shared, which is precisely what makes the
    attribution deltas mean what they claim.
    """
    import time

    from ingestion_bench.wiki_projection.navigation import NON_QUALIFYING_LABEL, W1_DERIVED_ARMS

    start = time.perf_counter()
    eligible = set(eligible_revision_ids)
    ceiling = candidate_ceiling(top_k)
    cosine_ops = seed_cosine_operations

    eligible_pages = sorted({f.page_key for f in projection.facets if f.document_revision_id in eligible})
    eligible_chunks = sorted(
        {cid for f in projection.facets if f.document_revision_id in eligible for cid in f.chunk_ids}
    )

    navigation = NavigationResult(arm=arm, seed_page_keys=[s.page_key for s in seeds])
    reached: list[str] = []
    visited: list[str] = []
    path: list[Hop] = []
    path_chunks: list[str] = []

    def target_cosines(neighbours) -> dict[str, float]:
        """Branch-priority cosine per target page.

        W1 arms use the frozen FACET vectors; D0 uses the existing CHUNK vectors
        of the target page's eligible facets -- the SS7.4.2 substitution, since a
        W1-LLM-free arm may not consult a W1-derived vector.
        """
        nonlocal cosine_ops
        out: dict[str, float] = {}
        for neighbour in neighbours:
            page_key = neighbour.target_page_key
            if page_key in out:
                continue
            if arm == "D0":
                candidates = [
                    chunk_vectors[cid]
                    for f in projection.facets
                    if f.page_key == page_key and f.document_revision_id in eligible
                    for cid in f.chunk_ids
                    if cid in chunk_vectors
                ]
                out[page_key] = max(
                    (cosine_similarity(query_vector, v) for v in candidates), default=0.0
                )
                cosine_ops += len(candidates)
            else:
                vector = facet_vectors_by_page.get(page_key)
                out[page_key] = cosine_similarity(query_vector, vector) if vector else 0.0
                cosine_ops += 1 if vector else 0
        return out

    # --- SS6.5 / SS6.6: ONE selected path from the rank-1 seed ------------
    #
    # The selected path is a single chain -- the rank-1 seed page, then at each
    # step the FIRST neighbour in the frozen branch order -- not every edge of a
    # breadth-first sweep. Only that chain's path-establishing chunks are
    # protected in Tier 1; everything else reached lands in Tier 2. Treating
    # every traversed edge as path evidence would let breadth-first noise
    # occupy the protected slots and crowd out required evidence.
    seed_origin_chunk = {s.page_key: s.origin_chunk_id for s in seeds}
    expanded = 0

    def visit(page_key: str, arrived_by: str) -> tuple[list[str], list]:
        """Expand a hub and expose its neighbours. Expansion is NOT a hop."""
        nonlocal expanded
        visited.append(page_key)
        facet_keys, chunk_ids = navigator.expand_page(page_key, eligible)
        if arrived_by == "seed":
            expanded += 1
        for chunk_id in chunk_ids:
            if chunk_id in reached:
                continue
            if len(reached) >= ceiling:
                navigation.c_bound_hit = True
                break
            reached.append(chunk_id)

        neighbours, removed = navigator.expose_neighbours(
            page_key, arm=arm, eligible=eligible, suppressed_link_ids=suppressed_link_ids
        )
        navigation.ineligible_neighbours_removed += removed
        ordered = order_neighbours(
            neighbours, arm=arm, query_text=query_text, target_cosine=target_cosines(neighbours)
        )
        navigation.candidates_examined += len(ordered)
        navigation.visits.append(
            HubVisit(
                page_key=page_key, arrived_by=arrived_by, eligible_facets=facet_keys,
                chunks_collected=chunk_ids, neighbours_exposed=ordered,
                ineligible_neighbours_removed=removed,
            )
        )
        return chunk_ids, ordered

    if seeds:
        # The rank-1 seed is the path origin (SS6.5).
        origin = seeds[0]
        chunk_ids, ordered = visit(origin.page_key, "seed")
        # The seed's path-establishing chunk: the chunk carrying the posting the
        # seed was selected on, when known (D0), else this hub's first chunk.
        establishing = seed_origin_chunk.get(origin.page_key)
        if establishing not in chunk_ids:
            establishing = chunk_ids[0] if chunk_ids else None
        if establishing:
            path_chunks.append(establishing)

        current = origin.page_key
        while navigation.hops_taken < HOP_BUDGET_B:
            step = next((n for n in ordered if n.target_page_key not in visited), None)
            if step is None:
                break
            step.selected = True
            navigation.hops_taken += 1
            mechanism = step.link_type
            if mechanism == "claim_derived":
                navigation.claim_derived_traversals += 1
            elif mechanism == "exact_anchor":
                navigation.exact_anchor_traversals += 1
            elif mechanism == "structural":
                navigation.structural_traversals += 1
            else:
                navigation.advisory_traversals += 1

            destination_chunks, ordered = visit(step.target_page_key, mechanism)
            # SS6.6: the path-establishing chunk is the chunk in the DESTINATION
            # page's eligible facets that carried the anchor posting or claim
            # citation used to justify the hop.
            justifying = next(
                (cid for cid in step.source_chunk_ids if cid in destination_chunks),
                destination_chunks[0] if destination_chunks else None,
            )
            path.append(
                Hop(
                    hop_index=navigation.hops_taken, from_page_key=current,
                    to_page_key=step.target_page_key, mechanism=mechanism, link_id=step.link_id,
                    predicate=step.predicate, claim_id=step.claim_id,
                    justifying_chunk_ids=list(step.source_chunk_ids),
                    path_establishing_chunk_id=justifying,
                )
            )
            if justifying and justifying not in path_chunks:
                path_chunks.append(justifying)
            current = step.target_page_key
        else:
            navigation.b_bound_hit = True

        # Lower-ranked seeds are EXPANDED (expansion is not a hop) and
        # contribute at Tier 2 (SS6.5).
        for seed in seeds[1:]:
            if seed.page_key not in visited:
                visit(seed.page_key, "seed")

    navigation.path = path
    navigation.pages_visited = len(visited)
    navigation.reached_chunk_ids = list(reached)
    navigation.path_establishing_chunk_ids = list(path_chunks)

    # --- the frozen two-tier final-K policy (SS6.6) ---------------------
    tier1 = [cid for cid in path_chunks if cid in reached]
    tier2_pool = [cid for cid in reached if cid not in tier1]

    def tier2_key(chunk_id: str):
        nonlocal cosine_ops
        vector = chunk_vectors.get(chunk_id)
        score = cosine_similarity(query_vector, vector) if vector else 0.0
        cosine_ops += 1 if vector else 0
        section = next((s for s in projection.sections if s.chunk_id == chunk_id), None)
        return (-score, section.document_revision_id if section else "",
                section.chunk_index if section else 0, chunk_id)

    tier2 = sorted(tier2_pool, key=tier2_key)
    final = (tier1 + tier2)[:top_k]

    result = WikiRetrievalResult(
        arm=arm, question_id=question_id, top_k=top_k,
        eligible_revision_ids=sorted(eligible), eligible_pages=len(eligible_pages),
        eligible_chunks=len(eligible_chunks), seeds=seeds,
        seed_pages_selected=len(seeds), seed_pages_expanded=expanded,
        navigation=navigation, tier1_chunk_ids=tier1, tier2_chunk_ids=tier2,
        final_chunk_ids=final, candidate_chunks=len(reached),
        p_bound_hit=len(seeds) >= top_k, b_bound_hit=navigation.b_bound_hit,
        c_bound_hit=navigation.c_bound_hit, short_list=len(final) < top_k,
        path_truncated=len(tier1) > top_k,
        page_saturation=(len(visited) / len(eligible_pages)) if eligible_pages else 0.0,
        chunk_saturation=(len(reached) / len(eligible_chunks)) if eligible_chunks else 0.0,
        latency_seconds=time.perf_counter() - start,
        query_embedding_calls=query_embedding_calls, cosine_operations=cosine_ops,
        non_qualifying_label=NON_QUALIFYING_LABEL if arm in W1_DERIVED_ARMS else None,
    )
    return result
