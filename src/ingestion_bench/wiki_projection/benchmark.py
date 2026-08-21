"""Stage 7C.0: the W0 semantic CONTROL and the projection qualification run.

The W0 semantic control (Revision 6 SS2.3):

    query -> existing query embedding
          -> authority-aware search over the EXISTING chunk embeddings
          -> WikiSection / chunk mapping
          -> dedupe preserving order
          -> same final K as V
          -> the FROZEN Stage 7B.0 evaluator

`_evaluate_question` is imported BY IDENTITY from the frozen Stage 7B.0
`cross_document_benchmark.benchmark_runner`; it is never copied, wrapped or
re-implemented. V and W0 are scored by the same function object.

> W0 semantic retrieval is EXPECTED to equal V, because a W0 section is 1:1
> with a chunk and reuses that chunk's existing embedding. W0 ~ V is a
> SUCCESSFUL control outcome, not a failure, and no retrieval-improvement gate
> is applied to it.

This module does NOT implement D0. D0 is a Stage 7C.2 arm: it adds anchor-
derived seeding, deterministic hub expansion and traversal on top of chunk
semantic retrieval. Nothing here expands a hub or traverses a link.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from ingestion_bench.cross_document_benchmark.benchmark_runner import (
    FactEvidence,
    QuestionResult,
    _evaluate_question,  # FROZEN Stage 7B.0 evaluator, imported by identity
    build_evidence_alignment,
    load_contract,
)
from ingestion_bench.cross_document_benchmark.fixtures import RevisionFixture, load_all_revision_fixtures
from ingestion_bench.cross_document_benchmark.indexer import IndexBuildResult, build_index
from ingestion_bench.cross_document_benchmark.retriever import CrossDocumentSearchResult, cross_document_search
from ingestion_bench.cross_document_benchmark.store import CrossDocumentVectorStore
from ingestion_bench.retrieval_baseline.embeddings import EmbeddingProvider
from ingestion_bench.revision_authority.contract_runner import _run_registry_setup
from ingestion_bench.revision_authority.repository import RevisionAuthorityRepository
from ingestion_bench.revision_authority.service import RevisionAuthorityService
from ingestion_bench.wiki_projection import identity as wiki_identity
from ingestion_bench.wiki_projection.compiler import (
    COMPILER_TEMPERATURE,
    PROMPT_VERSION,
    build_facet_input,
    prompt_sha256,
)
from ingestion_bench.wiki_projection.model import WikiProjection
from ingestion_bench.wiki_projection.projection import build_projection
from ingestion_bench.wiki_projection.validation import (
    FacetValidationResult,
    assert_membership_unchanged,
    normalize_triple_part,
    normalize_whitespace,
    validate_facet,
)


class W0SectionMappingError(RuntimeError):
    """Raised when a retrieved chunk has no `WikiSection`, or a section does
    not map back to its own chunk -- the 1:1 view would be broken and the
    control would no longer be a control."""


def w0_result_from_vector_result(
    projection: WikiProjection, vector_result: CrossDocumentSearchResult, top_k: int
) -> tuple[CrossDocumentSearchResult, dict[str, Any]]:
    """Map a V search result through the W0 section view, exactly as SS2.3
    specifies: section -> originating chunk_id, dedupe preserving order,
    truncate to the same final K.

    The mapping goes THROUGH the projection (chunk -> section -> chunk) rather
    than passing chunk ids straight through, so a broken 1:1 view fails loudly
    instead of silently reproducing V.
    """
    section_by_chunk = {s.chunk_id: s for s in projection.sections}

    mapped: list = []
    seen: set[str] = set()
    section_ids: list[str] = []
    for hit in vector_result.hits:
        section = section_by_chunk.get(hit.chunk_id)
        if section is None:
            raise W0SectionMappingError(
                f"retrieved chunk {hit.chunk_id!r} has no WikiSection -- the 1:1 section view is incomplete"
            )
        if section.chunk_id != hit.chunk_id:
            raise W0SectionMappingError(
                f"section {section.section_id!r} maps back to chunk {section.chunk_id!r}, not {hit.chunk_id!r}"
            )
        if hit.chunk_id in seen:
            continue
        seen.add(hit.chunk_id)
        section_ids.append(section.section_id)
        mapped.append(hit)

    truncated = mapped[:top_k]
    reranked = [hit.model_copy(update={"rank": rank}) for rank, hit in enumerate(truncated, start=1)]

    w0_result = vector_result.model_copy(update={"hits": reranked})
    diagnostics = {
        "section_ids": section_ids[:top_k],
        "deduped_count": len(mapped) - len(seen) if len(mapped) != len(seen) else 0,
        "dropped_by_dedupe": len(vector_result.hits) - len(mapped),
        "truncated_count": max(0, len(mapped) - top_k),
    }
    return w0_result, diagnostics


class W0ControlQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    top_k: int
    v_hit_chunk_ids: list[str]
    w0_hit_chunk_ids: list[str]
    identical_to_v: bool
    v_outcome: str
    w0_outcome: str
    v_coverage_at_k: float
    w0_coverage_at_k: float
    v_complete_chain: bool
    w0_complete_chain: bool
    v_authority_leakage: int
    w0_authority_leakage: int
    w0_section_ids: list[str]
    dropped_by_dedupe: int
    truncated_count: int


class W0ControlResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    embedding_model: str
    evaluator_identity: str
    questions: list[W0ControlQuestion]
    questions_total: int
    identical_to_v_count: int
    w0_equals_v: bool
    v_outcome_counts: dict[str, int]
    w0_outcome_counts: dict[str, int]
    total_authority_leakage: int


class Stage7C0Result(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str
    generated_at: str
    corpus_id: str

    projection: WikiProjection
    index_build: IndexBuildResult
    w0_control: W0ControlResult

    revision_symbol_by_id: dict[str, str]
    build_latency_seconds: float


def _requested_by_document(
    question: dict[str, Any], fixtures: dict[str, RevisionFixture], symbol_to_id: dict[str, str]
) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for symbol in question.get("requested_revision_symbols", []):
        out.setdefault(fixtures[symbol].logical_document_id, []).append(symbol_to_id[symbol])
    return out


def run_stage7c0(
    contract_path: Path,
    repository: RevisionAuthorityRepository,
    embedding_provider: EmbeddingProvider,
    store: CrossDocumentVectorStore,
) -> Stage7C0Result:
    """Build the deterministic projection and run the W0 semantic control.

    Runs NO D0 seeding, NO hub expansion, NO traversal, NO W1 compilation and
    NO facet embedding -- those belong to Stage 7C.1 / 7C.2.
    """
    start = time.perf_counter()
    contract = load_contract(contract_path)
    fixtures = load_all_revision_fixtures(contract["fixtures"])
    corpus_logical_document_ids = sorted({fx.logical_document_id for fx in fixtures.values()})

    # --- the deterministic projection: no authority read, no LLM call ---
    projection = build_projection(fixtures)

    # --- authority setup, replayed through Stage 7R.1's own unmodified code ---
    service = RevisionAuthorityService(repository)
    revision_by_symbol = {
        symbol: {
            "source_document_sha256": fx.source_document_sha256,
            "version_label": fx.version_label,
            "revision_number": fx.revision_number,
        }
        for symbol, fx in fixtures.items()
    }
    symbol_to_id: dict[str, str] = {}
    id_to_symbol: dict[str, str] = {}
    registration_checks: list = []
    transition_checks: list = []
    for document in contract["authority_setup"]["documents"]:
        _run_registry_setup(
            repository, service, document, revision_by_symbol, symbol_to_id, id_to_symbol,
            registration_checks, transition_checks,
        )

    evidence: dict[str, FactEvidence] = build_evidence_alignment(contract, fixtures)
    index_result = build_index(fixtures, embedding_provider, store)

    control_questions: list[W0ControlQuestion] = []
    v_outcomes: dict[str, int] = {}
    w0_outcomes: dict[str, int] = {}
    total_leakage = 0

    for question in contract["questions"]:
        query_vector = embedding_provider.embed([question["query"]]).vectors[0]
        requested = _requested_by_document(question, fixtures, symbol_to_id)
        v_result = cross_document_search(
            service=service, store=store, corpus_logical_document_ids=corpus_logical_document_ids,
            query_intent=question["query_intent"], as_of_date=date.fromisoformat(question["as_of_date"]),
            requested_revision_ids_by_document=requested, query_vector=query_vector,
            embedding_model=embedding_provider.model_identity, top_k=question["top_k"],
        )
        w0_result, diagnostics = w0_result_from_vector_result(projection, v_result, question["top_k"])

        v_evaluated: QuestionResult = _evaluate_question(question, v_result, evidence, id_to_symbol)
        w0_evaluated: QuestionResult = _evaluate_question(question, w0_result, evidence, id_to_symbol)

        v_outcomes[v_evaluated.vector_outcome] = v_outcomes.get(v_evaluated.vector_outcome, 0) + 1
        w0_outcomes[w0_evaluated.vector_outcome] = w0_outcomes.get(w0_evaluated.vector_outcome, 0) + 1
        total_leakage += v_evaluated.authority_leakage_count + w0_evaluated.authority_leakage_count

        control_questions.append(
            W0ControlQuestion(
                question_id=question["question_id"], top_k=question["top_k"],
                v_hit_chunk_ids=v_evaluated.authority_aware_hit_chunk_ids,
                w0_hit_chunk_ids=w0_evaluated.authority_aware_hit_chunk_ids,
                identical_to_v=(
                    v_evaluated.authority_aware_hit_chunk_ids == w0_evaluated.authority_aware_hit_chunk_ids
                ),
                v_outcome=v_evaluated.vector_outcome, w0_outcome=w0_evaluated.vector_outcome,
                v_coverage_at_k=v_evaluated.required_fact_coverage_at_k,
                w0_coverage_at_k=w0_evaluated.required_fact_coverage_at_k,
                v_complete_chain=v_evaluated.complete_chain_represented,
                w0_complete_chain=w0_evaluated.complete_chain_represented,
                v_authority_leakage=v_evaluated.authority_leakage_count,
                w0_authority_leakage=w0_evaluated.authority_leakage_count,
                w0_section_ids=diagnostics["section_ids"],
                dropped_by_dedupe=diagnostics["dropped_by_dedupe"],
                truncated_count=diagnostics["truncated_count"],
            )
        )

    control = W0ControlResult(
        embedding_model=embedding_provider.model_identity,
        evaluator_identity=f"{_evaluate_question.__module__}.{_evaluate_question.__qualname__}",
        questions=control_questions,
        questions_total=len(control_questions),
        identical_to_v_count=sum(1 for q in control_questions if q.identical_to_v),
        w0_equals_v=all(q.identical_to_v for q in control_questions),
        v_outcome_counts=dict(sorted(v_outcomes.items())),
        w0_outcome_counts=dict(sorted(w0_outcomes.items())),
        total_authority_leakage=total_leakage,
    )

    return Stage7C0Result(
        contract_version=projection.contract_version,
        generated_at=datetime.now(timezone.utc).isoformat(),
        corpus_id=contract["corpus_id"],
        projection=projection,
        index_build=index_result,
        w0_control=control,
        revision_symbol_by_id=id_to_symbol,
        build_latency_seconds=time.perf_counter() - start,
    )


# =============================================================================
# Stage 7C.1 -- compilation runs, mechanical validation, repeatability
# =============================================================================
#
# RUN 1 IS THE PRIMARY REPRESENTATION CANDIDATE, designated BEFORE any call
# executes (Revision 6 SS8F). Runs 2 and 3 measure stability only. Selecting the
# best-scoring run is PROHIBITED, and so is merging runs, repairing Run 1 from
# Run 2/3, or supplementing Run 1 with another run's output. That is enforced
# structurally below: `primary_run_id` is a literal 1, and only run 1 is ever
# handed to the adjudication packet, the payload preview or the page previews.

PRIMARY_RUN_ID = 1
REPEATABILITY_RUN_IDS = (1, 2, 3)


class RunProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: int
    model_identity: str
    temperature: float
    prompt_version: str
    prompt_sha256: str
    facets_attempted: int
    generation_failures: int
    facets_failed_on_ceilings: int
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost_usd: float | None
    latency_seconds_total: float
    is_primary: bool


class RepeatabilityMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_ids: list[int]
    claim_set_jaccard_pairwise: dict[str, float]
    citation_stability_pairwise: dict[str, float]
    alias_stability_pairwise: dict[str, float]
    raw_summary_stability_pairwise: dict[str, float]
    derived_link_stability_pairwise: dict[str, float]
    unsupported_claim_counts_by_run: dict[str, int]
    accepted_claim_counts_by_run: dict[str, int]
    input_tokens_by_run: dict[str, int | None]
    output_tokens_by_run: dict[str, int | None]
    latency_seconds_by_run: dict[str, float]
    false_merges_by_run: dict[str, int]
    ceiling_breaches_by_run: dict[str, int]
    membership_stable_across_runs: bool
    notes: list[str]


class Stage7C1Result(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: str
    projection_hash: str
    primary_run_id: int = PRIMARY_RUN_ID

    run_provenance: list[RunProvenance]
    # Keyed "page_key|document_revision_id". ONLY run 1 feeds adjudication.
    validations_by_run: dict[str, dict[str, FacetValidationResult]]
    repeatability: RepeatabilityMetrics

    dollar_ceiling_usd: float
    total_estimated_cost_usd: float | None
    membership_unchanged: bool
    compiler_calls_total: int


def facet_key(page_key: str, document_revision_id: str) -> str:
    return f"{page_key}|{document_revision_id}"


def _jaccard(left: set, right: set) -> float:
    if not left and not right:
        return 1.0
    return len(left & right) / len(left | right)


def _normalized_claim_keys(validations: dict[str, FacetValidationResult]) -> set[tuple]:
    """SS8F: Jaccard over normalized (subject, predicate, object, sorted
    supporting_chunk_ids)."""
    return {
        (
            key,
            normalize_triple_part(claim.subject),
            claim.predicate.strip().casefold(),
            normalize_triple_part(claim.object),
            tuple(sorted(claim.supporting_chunk_ids)),
        )
        for key, validation in validations.items()
        for claim in validation.claims
    }


def _citation_keys(validations: dict[str, FacetValidationResult]) -> set[tuple]:
    return {
        (
            key,
            normalize_triple_part(claim.subject),
            claim.predicate.strip().casefold(),
            normalize_triple_part(claim.object),
            tuple(sorted(normalize_whitespace(q) for q in claim.supporting_quotes)),
        )
        for key, validation in validations.items()
        for claim in validation.claims
    }


def _alias_keys(validations: dict[str, FacetValidationResult]) -> set[tuple]:
    return {
        (key, alias.alias.strip().casefold(), alias.status)
        for key, validation in validations.items()
        for alias in validation.aliases
    }


def _summary_keys(validations: dict[str, FacetValidationResult]) -> set[tuple]:
    return {
        (key, normalize_whitespace(sentence.text).casefold())
        for key, validation in validations.items()
        for sentence in validation.summary_sentences
    }


def _link_keys(validations: dict[str, FacetValidationResult]) -> set[tuple]:
    return {
        (key, link.subject_page_key, link.predicate.strip().casefold(), link.object_page_key,
         link.traversal_direction)
        for key, validation in validations.items()
        for link in validation.derived_links
    }


def _count_false_merges(validations: dict[str, FacetValidationResult], page_by_key: dict) -> int:
    """A false merge is a supported alias whose identifier set differs from its
    own page's -- the C-88 / C-88A guard, at the alias level."""
    merges = 0
    for key, validation in validations.items():
        page = page_by_key.get(key.split("|", 1)[0])
        if page is None:
            continue
        page_identifiers = wiki_identity.identifiers_in(page.normalized_identity)
        if not page_identifiers:
            continue
        for alias in validation.aliases:
            if alias.status != "supported":
                continue
            alias_identifiers = wiki_identity.identifiers_in(alias.alias)
            if alias_identifiers and alias_identifiers != page_identifiers:
                merges += 1
    return merges


def run_stage7c1_compilation(
    projection: WikiProjection,
    facet_compiler,
    *,
    dollar_ceiling_usd: float,
    run_ids: tuple[int, ...] = REPEATABILITY_RUN_IDS,
) -> Stage7C1Result:
    """Execute the frozen W1 compiler over every facet, N times, and validate
    each run mechanically.

    Every run uses IDENTICAL source chunks, facet membership, model, prompt,
    configuration, temperature and ceilings -- the only thing that differs
    between runs is the model's own nondeterminism, which is exactly what SS8F
    exists to measure.
    """
    membership_before = [f.model_copy(deep=True) for f in projection.facets]

    sections_by_chunk = {s.chunk_id: s for s in projection.sections}
    page_by_key = {p.page_key: p for p in projection.page_identities}
    all_page_keys = set(page_by_key)

    validations_by_run: dict[str, dict[str, FacetValidationResult]] = {}
    provenance: list[RunProvenance] = []
    total_cost: float | None = 0.0
    calls = 0

    for run_id in run_ids:
        per_facet: dict[str, FacetValidationResult] = {}
        run_input_tokens: int | None = 0
        run_output_tokens: int | None = 0
        run_cost: float | None = 0.0
        run_latency = 0.0
        failures = 0
        ceiling_failures = 0

        for facet in projection.facets:
            page = page_by_key[facet.page_key]
            facet_input = build_facet_input(facet, page, sections_by_chunk)
            output = facet_compiler.compile_facet(facet_input, run_id)
            calls += 1

            validation = validate_facet(
                output, facet=facet, page=page, sections_by_chunk=sections_by_chunk,
                all_page_keys=all_page_keys,
            )
            per_facet[facet_key(facet.page_key, facet.document_revision_id)] = validation

            if validation.generation_failed:
                failures += 1
            if validation.ceiling_breaches:
                ceiling_failures += 1
            run_latency += validation.latency_seconds
            if run_input_tokens is None or validation.input_tokens is None:
                run_input_tokens = None
            else:
                run_input_tokens += validation.input_tokens
            if run_output_tokens is None or validation.output_tokens is None:
                run_output_tokens = None
            else:
                run_output_tokens += validation.output_tokens
            if run_cost is None or validation.estimated_cost_usd is None:
                run_cost = None
            else:
                run_cost += validation.estimated_cost_usd

            # SS3.9: the whole-run dollar ceiling FAILS THE RUN. Enforced as the
            # run proceeds, so the cap can never be exceeded and then merely
            # reported afterwards.
            if run_cost is not None and run_cost > dollar_ceiling_usd:
                raise RuntimeError(
                    f"whole-run dollar ceiling exceeded on run {run_id}: "
                    f"${run_cost:.4f} > ${dollar_ceiling_usd:.4f} (Revision 6 SS3.9 -- fails the run)"
                )

        validations_by_run[str(run_id)] = per_facet
        total_cost = None if (total_cost is None or run_cost is None) else total_cost + run_cost
        provenance.append(
            RunProvenance(
                run_id=run_id, model_identity=getattr(facet_compiler, "model_identity", "unknown"),
                temperature=float(COMPILER_TEMPERATURE), prompt_version=PROMPT_VERSION,
                prompt_sha256=prompt_sha256(), facets_attempted=len(projection.facets),
                generation_failures=failures, facets_failed_on_ceilings=ceiling_failures,
                input_tokens=run_input_tokens, output_tokens=run_output_tokens,
                estimated_cost_usd=run_cost, latency_seconds_total=run_latency,
                is_primary=(run_id == PRIMARY_RUN_ID),
            )
        )

    # SS2.2 / SS4.0 -- prove the compiler changed no membership at all.
    assert_membership_unchanged(membership_before, projection.facets)

    return Stage7C1Result(
        generated_at=datetime.now(timezone.utc).isoformat(),
        projection_hash=projection.projection_hash,
        run_provenance=provenance,
        validations_by_run=validations_by_run,
        repeatability=_compute_repeatability(validations_by_run, page_by_key),
        dollar_ceiling_usd=dollar_ceiling_usd,
        total_estimated_cost_usd=total_cost,
        membership_unchanged=True,
        compiler_calls_total=calls,
    )


def _compute_repeatability(
    validations_by_run: dict[str, dict[str, FacetValidationResult]], page_by_key: dict
) -> RepeatabilityMetrics:
    run_ids = sorted(validations_by_run, key=int)
    pairs = [(a, b) for i, a in enumerate(run_ids) for b in run_ids[i + 1:]]

    def pairwise(extractor) -> dict[str, float]:
        return {
            f"run{a}_vs_run{b}": _jaccard(extractor(validations_by_run[a]), extractor(validations_by_run[b]))
            for a, b in pairs
        }

    def total_tokens(run: str, field: str) -> int | None:
        values = [getattr(v, field) for v in validations_by_run[run].values()]
        return None if any(value is None for value in values) else sum(values)

    return RepeatabilityMetrics(
        run_ids=[int(r) for r in run_ids],
        claim_set_jaccard_pairwise=pairwise(_normalized_claim_keys),
        citation_stability_pairwise=pairwise(_citation_keys),
        alias_stability_pairwise=pairwise(_alias_keys),
        raw_summary_stability_pairwise=pairwise(_summary_keys),
        derived_link_stability_pairwise=pairwise(_link_keys),
        unsupported_claim_counts_by_run={
            run: sum(
                1 for v in validations_by_run[run].values()
                for c in v.claims if c.validation_status in ("rejected", "out_of_page_scope")
            )
            for run in run_ids
        },
        accepted_claim_counts_by_run={
            run: sum(
                1 for v in validations_by_run[run].values()
                for c in v.claims if c.validation_status == "accepted"
            )
            for run in run_ids
        },
        input_tokens_by_run={run: total_tokens(run, "input_tokens") for run in run_ids},
        output_tokens_by_run={run: total_tokens(run, "output_tokens") for run in run_ids},
        latency_seconds_by_run={
            run: sum(v.latency_seconds for v in validations_by_run[run].values()) for run in run_ids
        },
        false_merges_by_run={run: _count_false_merges(validations_by_run[run], page_by_key) for run in run_ids},
        ceiling_breaches_by_run={
            run: sum(len(v.ceiling_breaches) for v in validations_by_run[run].values()) for run in run_ids
        },
        membership_stable_across_runs=True,
        notes=[
            "Membership stability is NOT measured because it is 100% by construction: facet membership, "
            "source chunks, anchors and postings are produced at Stage 7C.0 with zero LLM calls and are "
            "byte-identical across all runs (Revision 6 SS8F). The claim-set Jaccard therefore measures "
            "variance in the routing/enrichment layer ONLY, sitting on an invariant connectivity layer.",
            "Only Run 1 is owner-adjudicated, so runs are compared on structured claims, citations, "
            "aliases, raw summary text and derived links -- NEVER on payload composition, which does not "
            "exist for runs 2 and 3. This is stated to prevent a false stability reading.",
            "Fact-recall variance against the frozen expected facts is deliberately NOT computed at this "
            "checkpoint: it would place benchmark truth beside unadjudicated output, and SS8A permits it "
            "only once compilation is complete.",
        ],
    )
