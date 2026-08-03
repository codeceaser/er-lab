"""Stage 7B.1: renders the graph build results, graph retrieval results,
and the Vector-vs-Graph scorecard -- all from the SAME run objects.

The committed reports embed the full node/edge/provenance detail (the
corpus is tiny), so the measured result stays auditable even though the
`artifacts/stage7b1/` tree is gitignored.
"""

from __future__ import annotations

import json

from ingestion_bench.graph_retrieval_benchmark.benchmark_runner import GraphBenchmarkRunResult
from ingestion_bench.graph_retrieval_benchmark.builder import GraphProjection


def recommend(result: GraphBenchmarkRunResult) -> tuple[str, str]:
    """Data-driven recommendation (advisory). One of: retain-selective /
    retain-experimental / defer / reject. `reject` is reserved for a
    graph that is broken or unsafe (authority leakage, dangerous entity
    collisions, or very low extraction recall); a graph that is
    authority-safe but simply not worth its cost is `defer`."""
    improved = len(result.improved_question_ids)
    regressed = len(result.regressed_question_ids)
    be = result.build_evaluation
    total_leakage = sum(c.graph_authority_leakage_count for c in result.comparisons)
    unsafe = total_leakage > 0 or be.entity_normalization_collision_count > 0 or be.expected_fact_edge_recall < 0.5
    clean_build = be.expected_fact_edge_recall >= 0.99 and be.unsupported_extracted_edge_count == 0 and be.entity_normalization_collision_count == 0

    if unsafe:
        return ("reject Graph for this architecture",
                f"Graph is unsafe/broken here: authority leakage {total_leakage}, normalization collisions "
                f"{be.entity_normalization_collision_count}, extraction recall {be.expected_fact_edge_recall:.2f}.")
    if regressed == 0 and improved > 0 and clean_build:
        return ("retain Graph as a selective relationship projection",
                "Graph strictly improves the deep multi-hop questions with no regressions and clean extraction.")
    if improved > regressed:
        return ("retain Graph only experimentally",
                f"Graph improves {improved} question(s) (notably deep multi-hop) but regresses {regressed}; the net is positive but the "
                "regressions and the extraction cost/maintenance mean it is not yet a clear win for this corpus.")
    if improved == 0:
        return ("defer Graph because its benefit does not justify its cost",
                f"With the real LLM extractor the graph improved NO question and regressed {regressed}: a single missed or "
                "inconsistently-normalized edge breaks a multi-hop chain, so traversal retrieves less than Vector, and extraction is "
                "non-deterministic and adds real cost/maintenance. (The deterministic best-case -- a perfect extractor -- does improve the "
                "deep endpoint multi-hop questions, so the benefit is latent but not reliably achievable with a real extractor here.)")
    return ("defer Graph because its benefit does not justify its cost",
            f"Graph improves {improved} question(s) but regresses {regressed}; the mixed result plus extraction cost/maintenance does not "
            "justify adopting it for this architecture yet.")


def render_build_results_json(result: GraphBenchmarkRunResult, projection: GraphProjection) -> str:
    payload = {
        "contract_version": result.contract_version,
        "generated_at": result.generated_at,
        "corpus_id": result.corpus_id,
        "embedding_model": result.embedding_model,
        "frozen_input_verification": json.loads(result.frozen_input_verification.model_dump_json()),
        "extraction_run": json.loads(result.extraction_run.model_dump_json()),
        "build_manifest": json.loads(result.build_manifest.model_dump_json()),
        "build_evaluation": json.loads(result.build_evaluation.model_dump_json()),
        # Full nodes + edge assertions embedded for audit.
        "nodes": [json.loads(n.model_dump_json()) for n in sorted(projection.nodes.values(), key=lambda n: n.canonical_name)],
        "edge_assertions": [json.loads(e.model_dump_json()) for e in sorted(projection.edge_assertions, key=lambda e: (e.logical_document_id, e.predicate))],
    }
    return json.dumps(payload, indent=2)


def render_retrieval_results_json(result: GraphBenchmarkRunResult) -> str:
    payload = {
        "contract_version": result.contract_version,
        "generated_at": result.generated_at,
        "embedding_model": result.embedding_model,
        "graph_all_authority_correct": result.graph_all_authority_correct,
        "improved_question_ids": result.improved_question_ids,
        "unchanged_question_ids": result.unchanged_question_ids,
        "regressed_question_ids": result.regressed_question_ids,
        "graph_question_metrics": [json.loads(g.model_dump_json()) for g in result.graph_question_metrics],
        "comparisons": [json.loads(c.model_dump_json()) for c in result.comparisons],
    }
    return json.dumps(payload, indent=2)


def render_scorecard_markdown(result: GraphBenchmarkRunResult) -> str:
    be = result.build_evaluation
    er = result.extraction_run
    bm = result.build_manifest
    rec, rec_reason = recommend(result)

    comp_rows = "\n".join(
        f"| {c.question_id} | {c.question_type} | {c.query_intent} | {c.top_k} | "
        f"{c.vector_coverage_at_k:.2f} | {c.graph_coverage_at_k:.2f} | {c.coverage_delta:+.2f} | "
        f"{c.vector_complete_chain} | {c.graph_complete_chain} | {c.vector_mrr:.2f}/{c.graph_mrr:.2f} | "
        f"{c.vector_ndcg_at_k:.2f}/{c.graph_ndcg_at_k:.2f} | {c.graph_authority_leakage_count} | "
        f"{c.vector_total_latency_seconds*1000:.1f}/{c.graph_total_latency_seconds*1000:.1f} | {c.outcome_change} |"
        for c in result.comparisons
    )

    highlight_rows = "\n".join(
        f"### {c.question_id}\n\n"
        f"- Vector coverage@{c.top_k}: **{c.vector_coverage_at_k:.2f}** (complete chain: {c.vector_complete_chain}) -> "
        f"Graph coverage@{c.top_k}: **{c.graph_coverage_at_k:.2f}** (complete chain: {c.graph_complete_chain}) [{c.outcome_change}]\n"
        for c in result.comparisons if c.question_id in ("Q04_two_hop_control_of_service", "Q06_four_hop_procedure_of_app", "Q07_consolidation_payment_settlement")
    )

    q_detail = "\n\n".join(
        f"### {g.question_id} -- {g.question_type}\n\n"
        f"- intent: `{g.query_intent}`, top_k: {g.top_k}, graph outcome: **{g.graph_outcome}**, authority correct: **{g.authority_correct}**\n"
        f"- seed entities: `{g.seed_entities}`\n"
        f"- graph hit documents (ranked): `{g.graph_hit_documents}`\n"
        f"- coverage@{g.top_k}: **{g.required_fact_coverage_at_k:.2f}**, all-required: {g.all_required_facts_retrieved_at_k}, "
        f"complete chain: {g.complete_chain_represented}, MRR: {g.mrr:.2f}, nDCG: {g.ndcg_at_k:.2f}\n"
        f"- authority leakage (must be 0): **{g.authority_leakage_count}**, forbidden facts in hits: `{g.forbidden_fact_hit_ids}`\n"
        f"- traversed edges: {len(g.graph_result.traversed_edges)}, evidence hits: {len(g.graph_result.hits)}, "
        f"total latency: {g.total_latency_seconds*1000:.1f}ms\n"
        + (f"- outcome: `{g.graph_result.outcome}`\n" if g.graph_result.outcome != "ok" else "")
        for g in result.graph_question_metrics
    )

    return f"""# Stage 7B.1 -- Vector vs Graph Retrieval Scorecard

Generated from the same run objects as
`reports/stage7b1_graph_build_results.json` and
`reports/stage7b1_graph_retrieval_results.json`. The Vector baseline is
the FROZEN Stage 7B.0 result (loaded, never rerun or rescored); Graph is
scored by the SAME frozen Stage 7B.0 `_evaluate_question` over the SAME
fact alignment. NO answer generation, NO graph framework, NO Neo4j.

`contract_version`: `{result.contract_version}`
`corpus_id`: `{result.corpus_id}`
`generated_at`: `{result.generated_at}`
`embedding_model`: `{result.embedding_model}`
`extractor`: `{er.extractor_identity}`
`frozen input verified`: **{result.frozen_input_verification.index_hash_matches}** (index_hash `{result.frozen_input_verification.committed_index_hash[:16]}...`)
`graph authority correct`: {result.graph_authority_correct_count}/{result.questions_total}
`improved / unchanged / regressed`: {len(result.improved_question_ids)} / {len(result.unchanged_question_ids)} / {len(result.regressed_question_ids)}

## Graph build

- extractor: `{er.extractor_identity}`{f" (model `{er.model}`, prompt `{er.prompt_version}` sha `{er.prompt_sha256[:12] if er.prompt_sha256 else None}...`)" if er.model else ""}
- nodes: {bm.node_count}, edge assertions: {bm.edge_assertion_count}, distinct evidence chunks: {bm.evidence_count}
- graph payload hash: `{bm.graph_payload_sha256}`
- storage estimate: {bm.storage_estimate_bytes} bytes, build latency: {bm.build_latency_seconds:.3f}s
- extraction tokens (in/out): {er.input_tokens}/{er.output_tokens}, estimated cost: {er.estimated_cost_usd}, failures: {er.extraction_failure_count}
- rejected (unsupported) relationships during build: {be.rejected_relationship_count}

## Graph build accuracy (vs Stage 7B.0 facts)

- expected-fact edge recall: **{be.expected_fact_edge_recall:.2f}** ({be.covered_expected_fact_count}/{be.expected_fact_count}); missing: `{be.missing_expected_fact_ids}`
- extracted-edge precision: **{be.extracted_edge_precision:.2f}**; unsupported extracted edges: {be.unsupported_extracted_edge_count}
- duplicate assertions: {be.duplicate_assertion_count}
- provenance completeness: **{be.provenance_completeness:.2f}**; edges with invalid/missing supporting chunk: {be.edges_with_invalid_or_missing_supporting_chunk}
- entity normalization collisions: {be.entity_normalization_collision_count} `{be.entity_normalization_collisions}`

## Vector vs Graph, per question

| Question | Type | Intent | K | V cov | G cov | delta | V chain | G chain | MRR V/G | nDCG V/G | G auth-leak | latency ms V/G | change |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
{comp_rows}

## Highlighted distributed multi-hop questions (Q04, Q06, Q07)

The Graph retriever was NOT given these questions' expected paths.

{highlight_rows}

## Per-question graph detail

{q_detail}

## Decision report

- Questions Graph **improves**: `{result.improved_question_ids}`
- Questions **unchanged**: `{result.unchanged_question_ids}`
- Questions Graph **regresses**: `{result.regressed_question_ids}`
- Q04/Q06/Q07 become complete-chain under Graph: {[c.graph_complete_chain for c in result.comparisons if c.question_id in ('Q04_two_hop_control_of_service','Q06_four_hop_procedure_of_app','Q07_consolidation_payment_settlement')]}
- Graph extraction accuracy: recall {be.expected_fact_edge_recall:.2f}, precision {be.extracted_edge_precision:.2f}, unsupported edges {be.unsupported_extracted_edge_count}
- Authority leakage across all questions: {sum(c.graph_authority_leakage_count for c in result.comparisons)} (must be 0)
- Graph build tokens/cost: {er.input_tokens}/{er.output_tokens} tokens, {er.estimated_cost_usd} USD; storage {bm.storage_estimate_bytes} bytes
- Vector vs Graph query latency (mean ms): {sum(c.vector_total_latency_seconds for c in result.comparisons)/len(result.comparisons)*1000:.1f} vs {sum(c.graph_total_latency_seconds for c in result.comparisons)/len(result.comparisons)*1000:.1f}

**Recommendation: {rec}.**

{rec_reason}

### Implementation and maintenance limitations

- Graph retrieval depends on the query naming a seedable graph entity; a
  question that never names one (e.g. the draft-control question, which
  does not mention C-91) yields `no_seed_entity` and retrieves nothing,
  where lexical Vector still matches.
- Hop-distance-first ranking under a tight top-K budget can drop a far
  but required hop when a mid-chain seed reaches the rest of the chain in
  both directions.
- Graph adds an extraction step (real model cost, prompt maintenance,
  entity-normalization risk) that Vector does not have.
- This is a small controlled corpus; absolute deltas would differ on a
  larger, noisier corpus.
"""
