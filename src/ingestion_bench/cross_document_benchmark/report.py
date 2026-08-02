"""Stage 7B.0: renders the SAME BenchmarkRunResult to both JSON and
Markdown -- never two independently-computed reports."""

from __future__ import annotations

from ingestion_bench.cross_document_benchmark.benchmark_runner import BenchmarkRunResult


def render_results_json(result: BenchmarkRunResult) -> str:
    return result.model_dump_json(indent=2)


def render_scorecard_markdown(result: BenchmarkRunResult) -> str:
    fixture_rows = "\n".join(
        f"| {f.symbol} | {f.logical_document_id} | {f.revision_number} | {f.source_document_sha256[:16]}... | {f.chunk_count} |"
        for f in result.fixture_inventory
    )
    fact_rows = "\n".join(
        f"| {e.fact_id} | {e.subject} {e.predicate} {e.object} | {e.supporting_logical_document_id} | "
        f"{e.temporal_classification} | {e.distractor_status} | {e.supporting_chunk_id[:12]}... |"
        for e in result.fact_evidence
    )
    type_rows = "\n".join(f"| {qtype} | {count} |" for qtype, count in sorted(result.question_type_counts.items()))
    question_rows = "\n".join(
        f"| {q.question_id} | {q.question_type} | {q.query_intent} | {q.top_k} | "
        f"{q.required_fact_coverage_at_k:.2f} | {q.all_required_facts_retrieved_at_k} | {q.mrr:.3f} | {q.ndcg_at_k:.3f} | "
        f"{q.authority_leakage_count} | {q.unfiltered_ineligible_hit_count} | {q.evidence_document_diversity} | "
        f"{q.vector_outcome} | {q.authority_correct} |"
        for q in result.question_results
    )
    detail_sections = "\n\n".join(
        f"### {q.question_id} -- {q.question_type}\n\n"
        f"> {q.query}\n\n"
        f"- intent: `{q.query_intent}`, as_of_date: `{q.as_of_date}`, top_k: {q.top_k}\n"
        f"- eligible revisions (cross-document union): `{q.eligible_revision_symbols}`\n"
        f"- required facts: `{q.required_fact_ids}`\n"
        f"- forbidden facts: `{q.forbidden_fact_ids}`\n"
        f"- authority-aware hits (ranked documents): `{q.authority_aware_hit_documents}`\n"
        f"- unfiltered hits (ranked documents): `{q.unfiltered_hit_documents}`\n"
        f"- required-fact coverage@{q.top_k}: **{q.required_fact_coverage_at_k:.2f}** "
        f"({'ALL required retrieved' if q.all_required_facts_retrieved_at_k else 'PARTIAL / none'})\n"
        f"- complete relationship chain represented: **{q.complete_chain_represented}**\n"
        f"- MRR: {q.mrr:.3f}, nDCG@{q.top_k}: {q.ndcg_at_k:.3f}\n"
        f"- authority leakage (authority-aware, must be 0): **{q.authority_leakage_count}**\n"
        f"- forbidden facts appearing in authority-aware hits: `{q.forbidden_fact_hit_ids}` "
        "(adjacent-domain lexical distractors are eligible and not an authority failure)\n"
        f"- unfiltered ineligible hits (removed by authority filtering): **{q.unfiltered_ineligible_hit_count}**\n"
        f"- evidence-document diversity (distinct docs in authority-aware top-K): **{q.evidence_document_diversity}**\n"
        f"- vector outcome: **{q.vector_outcome}**, authority correct: **{q.authority_correct}**\n"
        f"- latency: resolver {q.resolver_latency_seconds:.6f}s, authority-aware {q.authority_aware_vector_search_latency_seconds:.6f}s, "
        f"unfiltered {q.unfiltered_vector_search_latency_seconds:.6f}s, total {q.total_latency_seconds:.6f}s\n"
        + (f"- **AUTHORITY FAILURE**: {q.failure_reasons}\n" if not q.authority_correct else "")
        for q in result.question_results
    )

    solved = [q.question_id for q in result.question_results if q.vector_outcome == "solved"]
    partial = [q.question_id for q in result.question_results if q.vector_outcome == "partial"]
    failed = [q.question_id for q in result.question_results if q.vector_outcome == "failed"]

    return f"""# Stage 7B.0 -- Cross-Document Relationship Vector Baseline Scorecard

Generated from a single `BenchmarkRunResult` -- this Markdown,
`reports/stage7b0_cross_document_vector_results.json`, and every
per-question artifact under `artifacts/stage7b0/query_results/` come from
the SAME execution. Retrieval is Vector-only; NO graph nodes, edges,
traversal, or answer generation exist in this stage.

`contract_version`: `{result.contract_version}`
`corpus_id`: `{result.corpus_id}`
`generated_at`: `{result.generated_at}`
`embedding_model`: `{result.embedding_model}`
`authority correct`: {result.authority_correct_count}/{result.questions_total} (must be all)
`vector outcomes`: solved={result.vector_solved_count}, partial={result.vector_partial_count}, failed={result.vector_failed_count}
`all_authority_correct`: **{result.all_authority_correct}**

## Source fixture inventory

| Symbol | Logical document | Rev # | source_document_sha256 | Chunks |
|---|---|---|---|---|
{fixture_rows}

## Relationship fact inventory (evidence alignment)

| Fact | Relationship | Supporting document | Temporal | Distractor | Supporting chunk |
|---|---|---|---|---|---|
{fact_rows}

## Question inventory by type

| Question type | Count |
|---|---|
{type_rows}

## Index build

- corpus documents: {len(result.index_build.logical_document_ids)}
- candidate chunks: {result.index_build.candidate_chunk_count}
- indexed (embedded): {result.index_build.indexed_count}
- total records: {result.index_build.total_record_count}
- index_hash: `{result.index_build.index_hash}`

## Vector baseline results

| Question | Type | Intent | K | Coverage@K | All@K | MRR | nDCG@K | Auth leak | Unfilt. ineligible | Doc diversity | Outcome | Auth OK |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
{question_rows}

- **Vector solved** (entire required chain retrieved within budget): `{solved}`
- **Vector partial** (some but not all required facts retrieved): `{partial}`
- **Vector failed** (no required facts retrieved): `{failed}`

## Question detail

{detail_sections}

## What this benchmark proves / does not prove

- **Proves**: the corpus genuinely distributes each multi-hop relationship
  across separate documents (no chunk holds a pre-assembled answer);
  authority filtering (current/historical/draft) happens BEFORE vector
  ranking; and it measures exactly how much of each distributed chain a
  Vector baseline recovers within a fixed evidence budget.
- **Does not prove** that a graph projection is better -- no graph is
  built here. It only qualifies a fair, frozen comparison harness (see
  the contract's `fairness_contract`) and records the Vector baseline a
  future graph must be measured against under identical conditions.
- This is a small, controlled corpus: with only a handful of
  authority-eligible chunks per query, the vector recall ceiling is
  easy to reach, so absolute scores overstate what Vector would achieve
  on a large corpus. The value is the methodology and the honest
  per-question breakdown, not the headline numbers.
"""
