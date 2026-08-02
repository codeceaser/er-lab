"""Stage 7R.2: renders the SAME BenchmarkRunResult to both JSON and
Markdown -- never two independently-computed reports."""

from __future__ import annotations

from ingestion_bench.revision_search_benchmark.benchmark_runner import BenchmarkRunResult


def render_results_json(result: BenchmarkRunResult) -> str:
    return result.model_dump_json(indent=2)


def render_scorecard_markdown(result: BenchmarkRunResult) -> str:
    query_rows = "\n".join(
        f"| {q.question_id} | {q.query_intent} | {q.as_of_date} | {', '.join(q.actual_eligible_symbols) or '(none)'} | "
        f"{q.ineligible_revision_leakage_at_k} | {q.eligible_revision_precision_at_k:.2f} | {q.required_revision_hit_at_k} | "
        f"{q.expected_value_retrieved} | {'PASS' if q.passed else 'FAIL'} |"
        for q in result.query_scenarios
    )
    detail_sections = "\n\n".join(
        f"### {q.question_id}\n\n"
        f"{q.description}\n\n"
        f"- query_intent: `{q.query_intent}`, as_of_date: `{q.as_of_date}`, requested: `{q.requested_symbols}`\n"
        f"- expected eligible: `{q.expected_eligible_symbols}` / actual: `{q.actual_eligible_symbols}`\n"
        f"- forbidden: `{q.forbidden_symbols}`\n"
        f"- expected authority labels: `{q.expected_authority_labels}` / actual: `{q.actual_authority_labels}`\n"
        f"- authority-aware top-K revisions: `{q.authority_aware_top_k_symbols}`\n"
        f"- unfiltered top-K revisions: `{q.unfiltered_top_k_symbols}`\n"
        f"- ineligible-revision leakage@K (unfiltered): **{q.ineligible_revision_leakage_at_k}**\n"
        f"- eligible-revision precision@K (authority-aware): **{q.eligible_revision_precision_at_k:.2f}**\n"
        f"- required-revision hit@K (authority-aware): **{q.required_revision_hit_at_k}**\n"
        f"- expected-value retrieved (authority-aware): **{q.expected_value_retrieved}**\n"
        f"- resolver latency: {q.resolver_latency_seconds:.6f}s, authority-aware vector search: "
        f"{q.authority_aware_vector_search_latency_seconds:.6f}s, unfiltered vector search: "
        f"{q.unfiltered_vector_search_latency_seconds:.6f}s, total: {q.total_latency_seconds:.6f}s\n"
        + (f"- integrity_error: `{q.integrity_error}`\n" if q.integrity_error else "")
        + (f"- **FAILED**: {q.failure_reasons}\n" if not q.passed else "- **PASSED**\n")
        for q in result.query_scenarios
    )

    switch = result.authority_switch
    switch_section = f"""## Scenario E -- authority switch without reindexing

- question_id: `{switch.question_id}`, as_of_date: `{switch.as_of_date}`
- BEFORE activation: eligible = `{switch.before_eligible_symbols}`, top-1 = `{switch.before_top1_symbol}`, value found = **{switch.before_value_found}**
- AFTER activation (v5 supersedes v3): eligible = `{switch.after_eligible_symbols}`, top-1 = `{switch.after_top1_symbol}`, value found = **{switch.after_value_found}**
- registry_snapshot_hash: `{switch.registry_snapshot_hash_before}` -> `{switch.registry_snapshot_hash_after}` (changed = **{switch.registry_snapshot_hash_changed}**, expected True)
- index_hash: `{switch.index_hash_before}` -> `{switch.index_hash_after}` (unchanged = **{switch.index_hash_unchanged}**, expected True)
- row_count: {switch.row_count_before} -> {switch.row_count_after} (unchanged = **{switch.row_count_unchanged}**, expected True)
- chunk_ids unchanged: **{switch.chunk_ids_unchanged}** (expected True)
- chunk content hashes unchanged: **{switch.chunk_hashes_unchanged}** (expected True)
- embedding calls during the switch itself: **{switch.embedded_count_during_switch}** (expected 0)
- **{'PASSED' if switch.passed else 'FAILED: ' + str(switch.failure_reasons)}**
"""

    fixture_rows = "\n".join(
        f"| {f.symbol} | {f.revision_number} | {f.source_document_sha256[:16]}... | {f.document_revision_id[:16]}... | "
        f"{f.chunk_count} | {f.retention_value} |"
        for f in result.fixture_inventory
    )

    return f"""# Stage 7R.2 -- Authority-Aware Vector Retrieval Scorecard

Generated from a single `BenchmarkRunResult` -- this Markdown and
`reports/stage7r2_authority_aware_vector_results.json` come from the
SAME execution, over the isolated POLICY-RETENTION-001 index (never
Stage 7A.1's own table).

`contract_version`: `{result.contract_version}`
`generated_at`: `{result.generated_at}`
`embedding_model`: `{result.embedding_model}`
`query_scenarios`: {result.query_scenarios_passed}/{result.query_scenarios_total} passed
`authority_switch`: {'PASSED' if result.authority_switch.passed else 'FAILED'}
`all_passed`: **{result.all_passed}**

## Fixture inventory

| Symbol | Revision # | source_document_sha256 | document_revision_id | Chunks | Retention value |
|---|---|---|---|---|---|
{fixture_rows}

## Index build

- candidate chunks: {result.index_build.candidate_chunk_count}
- indexed (embedded): {result.index_build.indexed_count}
- skipped unchanged: {result.index_build.skipped_unchanged_count}
- total records: {result.index_build.total_record_count}
- index_hash: `{result.index_build.index_hash}`
- embedding calls: {result.index_build.embedded_count}

## Query scenarios

| Question | Intent | As of | Eligible | Leakage@K (unfiltered) | Precision@K (aware) | Hit@K (aware) | Value retrieved | Result |
|---|---|---|---|---|---|---|---|---|
{query_rows}

## Scenario detail

{detail_sections}

{switch_section}

## What this report does NOT establish

- Any answer generation over these results -- Stage 7R.2 stops at
  retrieval evaluation.
- Graph RAG, wiki retrieval, ADK, or vision enrichment -- none of this
  package depends on any of them.
"""
