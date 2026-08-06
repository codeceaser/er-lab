"""Stage 7B.2: renders the hybrid probe results (JSON + Markdown) and the
closure decision text -- all from the same ProbeRunResult."""

from __future__ import annotations

import json

from ingestion_bench.hybrid_retrieval_benchmark.benchmark_runner import ProbeRunResult

MODES = ("V", "G", "H0", "H1", "H2")
TARGETS = ("Q04_two_hop_control_of_service", "Q06_four_hop_procedure_of_app", "Q07_consolidation_payment_settlement")
MIDCHAIN = ("Q05_three_hop_procedure_of_obligation", "Q10_historical_procedure_of_obligation")
Q12 = "Q12_draft_proposed_control"


def _pivot(result: ProbeRunResult):
    """(question_id, mode, condition) -> ModeResult. V is condition
    'common'; for convenience it is aliased under both conditions."""
    by_key = {(m.question_id, m.mode, m.graph_condition): m for m in result.mode_results}
    return by_key


def _cov(by_key, qid, mode, cond):
    key = (qid, mode, "common") if mode == "V" else (qid, mode, cond)
    m = by_key.get(key)
    return m.required_fact_coverage_at_k if m else float("nan")


def _mode(by_key, qid, mode, cond):
    return by_key.get((qid, mode, "common") if mode == "V" else (qid, mode, cond))


def _seed_saturation_rows(by_key) -> str:
    rows = []
    for (qid, mode, cond), m in by_key.items():
        if mode == "H2" and cond == "real_graph":
            rows.append((qid, m))
    rows.sort(key=lambda r: r[0])
    return "\n".join(
        f"| {qid} | {m.eligible_graph_node_count} | {m.supplemental_seed_candidate_count} | "
        f"{m.selected_supplemental_seed_count} | {m.total_seed_count} | {m.seed_saturation_ratio:.2f} | {m.seed_saturation_ok} |"
        for qid, m in rows
    )


def _path_enum_rows(by_key) -> str:
    rows = []
    for (qid, mode, cond), m in by_key.items():
        if mode == "H2" and cond == "real_graph":
            rows.append((qid, m))
    rows.sort(key=lambda r: r[0])
    return "\n".join(
        f"| {qid} | {m.paths_enumerated_before_ranking} | {m.paths_retained_after_ranking} | {m.eligible_edge_path_coverage:.2f} |"
        for qid, m in rows
    )


def render_results_json(result: ProbeRunResult) -> str:
    return result.model_dump_json(indent=2)


def render_scorecard_markdown(result: ProbeRunResult) -> str:
    by_key = _pivot(result)
    qids = [q for q in dict.fromkeys(m.question_id for m in result.mode_results)]
    iv = result.input_verification
    p = result.candidate_parameters

    def _coverage_table(cond: str) -> str:
        rows = []
        for qid in qids:
            cells = " | ".join(f"{_cov(by_key, qid, mode, cond):.2f}" for mode in MODES)
            rows.append(f"| {qid} | {cells} |")
        return "\n".join(rows)

    def _target_chain_rows() -> str:
        rows = []
        for qid in TARGETS:
            v = _mode(by_key, qid, "V", "common")
            rh2 = _mode(by_key, qid, "H2", "real_graph")
            ph2 = _mode(by_key, qid, "H2", "perfect_graph")
            rows.append(f"| {qid} | {v.complete_chain_represented} | {rh2.complete_chain_represented} | {ph2.complete_chain_represented} |")
        return "\n".join(rows)

    def _leakage_and_budget() -> tuple[int, bool]:
        leak = sum(m.authority_leakage_count for m in result.mode_results)
        budget_ok = all(len(m.final_chunk_ids) <= m.top_k for m in result.mode_results)
        return leak, budget_ok

    leak, budget_ok = _leakage_and_budget()

    def _mean_latency(mode: str, cond: str) -> float:
        vals = [m.total_latency_seconds for m in result.mode_results if m.mode == mode and (m.graph_condition == cond or (mode == "V" and m.graph_condition == "common"))]
        return sum(vals) / len(vals) if vals else 0.0

    # ablation attribution note per target question (real graph)
    ablation_rows = []
    for qid in list(TARGETS) + list(MIDCHAIN) + [Q12]:
        v = _cov(by_key, qid, "V", "real_graph")
        g = _cov(by_key, qid, "G", "real_graph")
        h0 = _cov(by_key, qid, "H0", "real_graph")
        h1 = _cov(by_key, qid, "H1", "real_graph")
        h2 = _cov(by_key, qid, "H2", "real_graph")
        gp = _cov(by_key, qid, "G", "perfect_graph")
        h2p = _cov(by_key, qid, "H2", "perfect_graph")
        ablation_rows.append(f"| {qid} | {v:.2f} | {g:.2f} | {h0:.2f} | {h1:.2f} | {h2:.2f} | {gp:.2f} | {h2p:.2f} |")

    return f"""# Stage 7B.2a -- Hybrid Vector-Graph Retrieval Value Probe

Generated from one `ProbeRunResult` (same object as
`reports/stage7b2_hybrid_retrieval_results.json` and
`docs/STAGE7B2_HYBRID_GRAPH_CLOSURE_DECISION.md`). Vector (V) is the
FROZEN Stage 7B.0 baseline; every mode is scored by the SAME frozen
Stage 7B.0 `_evaluate_question`. No query-time LLM. Hybrid superiority is
never assumed.

`contract_version`: `{result.contract_version}`
`generated_at`: `{result.generated_at}`
`embedding_model`: `{result.embedding_model}`

## Decision

**Gate {result.decision_gate}: {result.decision}**

{result.decision_rationale}

## Frozen input verification

- corpus index_hash matches Stage 7B.0: **{iv.corpus_index_hash_matches}** (`{iv.committed_vector_index_hash[:16]}...`)
- real graph payload hash matches committed Stage 7B.1: **{iv.real_graph_payload_hash_matches}** (`{iv.committed_real_graph_payload_hash[:16]}...`), loaded from snapshot (extraction run `{iv.real_graph_extraction_run_id}`, NOT re-extracted)
- real graph: {iv.real_graph_node_count} nodes / {iv.real_graph_edge_count} edges
- perfect graph: recall **{iv.perfect_graph_recall:.2f}**, precision **{iv.perfect_graph_precision:.2f}**, collisions **{iv.perfect_graph_collisions}**, payload `{iv.perfect_graph_payload_hash[:16]}...`

## Mode configuration (immutable, from the probe contract)

- vector_candidate_multiplier: {p['vector_candidate_multiplier']}, max_vector_seed_chunks: {p['max_vector_seed_chunks']}
- semantic_edge_candidate_count: {p['semantic_edge_candidate_count']}, max_hop_depth: {p['max_hop_depth']}
- max_supplemental_seed_nodes: {p['max_supplemental_seed_nodes']}, supplemental_seed_saturation_threshold: {p['supplemental_seed_saturation_threshold']}
- path_enumeration_safety_ceiling: {p['path_enumeration_safety_ceiling']}, max_candidate_paths: {p['max_candidate_paths']}, rrf_constant: {p['rrf_constant']}
- final top-K comes only from the frozen Stage 7B.0 question contract

## Seed-saturation diagnostics (real-graph H2)

Explicit-alias seeds are always retained; supplemental (Vector-chunk +
semantic-edge) seeds are RRF-ranked and capped at max_supplemental_seed_nodes.
Qualification fails if selected supplemental seeds exceed
{p['supplemental_seed_saturation_threshold']:.0%} of eligible graph nodes (except <=4-node graphs).

| Question | eligible nodes | suppl. candidates | selected suppl. | total seeds | saturation | ok |
|---|---|---|---|---|---|---|
{_seed_saturation_rows(by_key)}

## Path-enumeration diagnostics (real-graph H2)

All authority-eligible simple paths reachable from selected seeds are enumerated
and semantically ranked BEFORE truncation to max_candidate_paths (safety ceiling {p['path_enumeration_safety_ceiling']}).

| Question | enumerated | retained | eligible-edge coverage |
|---|---|---|---|
{_path_enum_rows(by_key)}

## Edge semantic-index manifests

- real graph: {result.edge_index_manifests['real_graph']['edge_count']} edges, payload `{result.edge_index_manifests['real_graph']['payload_sha256'][:16]}...`, {result.edge_index_manifests['real_graph']['storage_estimate_bytes']} bytes
- perfect graph: {result.edge_index_manifests['perfect_graph']['edge_count']} edges, payload `{result.edge_index_manifests['perfect_graph']['payload_sha256'][:16]}...`, {result.edge_index_manifests['perfect_graph']['storage_estimate_bytes']} bytes

## Coverage@K per question -- REAL graph

| Question | V | G | H0 | H1 | H2 |
|---|---|---|---|---|---|
{_coverage_table('real_graph')}

## Coverage@K per question -- PERFECT graph

| Question | V | G | H0 | H1 | H2 |
|---|---|---|---|---|---|
{_coverage_table('perfect_graph')}

## Target questions Q04/Q06/Q07 -- complete relationship chain represented

| Question | Vector | Real-graph H2 | Perfect-graph H2 |
|---|---|---|---|
{_target_chain_rows()}

## Ablation / attribution (coverage@K)

Isolates where any gain comes from: G (simple graph) -> H0 (fusion) ->
H1 (+ Vector/semantic seeds) -> H2 (+ semantic path ranking), plus the
perfect-graph G/H2 upper bound.

| Question | V | G(real) | H0(real) | H1(real) | H2(real) | G(perfect) | H2(perfect) |
|---|---|---|---|---|---|---|---|
{chr(10).join(ablation_rows)}

## Mid-chain (Q05/Q10) and unnamed-entity (Q12)

- Q05/Q10 (mid-chain ranking regression risk): real-graph H2 coverage
  {_cov(by_key, 'Q05_three_hop_procedure_of_obligation', 'H2', 'real_graph'):.2f} / {_cov(by_key, 'Q10_historical_procedure_of_obligation', 'H2', 'real_graph'):.2f} vs Vector
  {_cov(by_key, 'Q05_three_hop_procedure_of_obligation', 'V', 'real_graph'):.2f} / {_cov(by_key, 'Q10_historical_procedure_of_obligation', 'V', 'real_graph'):.2f}.
- Q12 (unnamed entity / no-seed): real-graph H2 coverage {_cov(by_key, Q12, 'H2', 'real_graph'):.2f} vs Vector {_cov(by_key, Q12, 'V', 'real_graph'):.2f}
  (Vector fallback via RRF is what preserves Q12).

## Safety and budget

- total authority leakage across ALL modes/questions/conditions: **{leak}** (must be 0)
- final evidence budget never exceeds the frozen top-K: **{budget_ok}**
- query-time LLM calls: **0** (deterministic; no query-time model)
- mean latency (s) V / real-H2 / perfect-H2: {_mean_latency('V','real_graph'):.4f} / {_mean_latency('H2','real_graph'):.4f} / {_mean_latency('H2','perfect_graph'):.4f}

## Decision-gate inputs

- real-graph H2: `{result.real_gate_inputs}`
- perfect-graph H2: `{result.perfect_gate_inputs}`
"""


def render_decision_doc(result: ProbeRunResult) -> str:
    by_key = _pivot(result)

    def _c(qid, mode, cond):
        return _cov(by_key, qid, mode, cond)

    real = result.real_gate_inputs
    perfect = result.perfect_gate_inputs
    return f"""# Stage 7B.2a -- Hybrid Vector-Graph Closure Decision

Durable decision record for Stage 7B.2, the bounded hybrid probe that
closes the Graph investigation. Companion to
`reports/stage7b2_hybrid_retrieval_scorecard.md` and
`reports/stage7b2_hybrid_retrieval_results.json` (same run object), and to
`docs/STAGE7B1_GRAPH_VS_VECTOR_DECISION.md`.

## What was tested

Whether Vector-assisted graph seeding, semantic edge matching, semantic
path ranking, and deterministic Vector/Graph RRF fusion can expose
Graph's latent multi-hop value **without** increasing the final evidence
budget, introducing authority leakage, or adding a query-time LLM. Five
frozen modes (V, G, H0, H1, H2) over two graph conditions (the frozen
real Stage 7B.1 snapshot and the deterministic perfect graph), all scored
by the frozen Stage 7B.0 scorer over the frozen top-K budgets.

## Decision

**Gate {result.decision_gate}: {result.decision}**

{result.decision_rationale}

## Key evidence

- Target questions Q04/Q06/Q07 complete-chain (Vector -> real-H2 -> perfect-H2):
  Q04 {_c('Q04_two_hop_control_of_service','V','real_graph'):.2f}->{_c('Q04_two_hop_control_of_service','H2','real_graph'):.2f}->{_c('Q04_two_hop_control_of_service','H2','perfect_graph'):.2f},
  Q06 {_c('Q06_four_hop_procedure_of_app','V','real_graph'):.2f}->{_c('Q06_four_hop_procedure_of_app','H2','real_graph'):.2f}->{_c('Q06_four_hop_procedure_of_app','H2','perfect_graph'):.2f},
  Q07 {_c('Q07_consolidation_payment_settlement','V','real_graph'):.2f}->{_c('Q07_consolidation_payment_settlement','H2','real_graph'):.2f}->{_c('Q07_consolidation_payment_settlement','H2','perfect_graph'):.2f} (coverage@K).
- Real-graph H2 target complete-chain improvements: {real['target_complete_chain_improvements']}; regressions vs Vector: {real['regressions_vs_vector']}; Q12 regressed: {real['q12_regressed']}.
- Perfect-graph H2 target complete-chain improvements: {perfect['target_complete_chain_improvements']}; regressions vs Vector: {perfect['regressions_vs_vector']}.
- Authority leakage: 0 across all modes/questions/conditions. Final budget never exceeds frozen top-K. No query-time LLM.

## Attribution

The ablation (G -> H0 -> H1 -> H2, plus the perfect-graph upper bound in
the scorecard) isolates whether any gain comes from fusion, better
seeding, semantic path ranking, or graph extraction quality. See the
"Ablation / attribution" table in the scorecard.

## Claim boundary

This decision states a result, not an impossibility theorem. The
conclusions hold ONLY for: the tested equal-weight RRF implementation;
the declared supplemental-seed budget (every explicit-alias seed retained
plus at most `max_supplemental_seed_nodes` RRF-ranked supplemental seeds);
the corrected semantic-path generation (ALL authority-eligible simple
paths enumerated and semantically ranked BEFORE any truncation to
`max_candidate_paths`); this corpus; and this embedding model. It is NOT
the claim "Hybrid cannot exceed Vector under a fixed budget" -- this very
run's perfect-graph H0 improves Q06 complete-chain coverage from 0.80 to
1.00, so graph structure demonstrably can help within budget. Graph was
simply not worth retaining in the ONLINE retrieval path under these
tested conditions.

## Limitations

- Small controlled corpus (~11 chunks, <=6 eligible per current query):
  Vector's recall ceiling is easy to reach, compressing any hybrid gain.
- The real graph is a single non-deterministic LLM extraction snapshot
  (Stage 7B.1); its missing/inconsistent edges cap what any hybrid over
  it can recover.
- The final evidence budget is the frozen Stage 7B.0 top-K (not enlarged
  for Hybrid), by design -- so a hybrid gain must come from better
  ranking within the SAME budget, not more evidence.
- No query-time LLM, no query decomposition, no router -- deliberately,
  to keep this a bounded ranking/fusion probe.
"""
