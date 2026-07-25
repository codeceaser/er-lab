"""Stage 7A.1: report rendering.

The Markdown scorecard and the JSON results file are always rendered
from the SAME in-memory RetrievalEvaluationRun object -- same discipline
established at Stage 5A.1/D-039 and reused at every stage since: never
two separate executions producing two reports that could silently drift
apart.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ingestion_bench.retrieval_baseline.evaluation import RetrievalEvaluationRun
from ingestion_bench.retrieval_baseline.indexer import IndexBuildResult


def render_index_manifest(index_builds: list[IndexBuildResult]) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "indexes": {b.corpus_profile: b.model_dump(mode="json") for b in index_builds},
    }


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def render_scorecard_markdown(run: RetrievalEvaluationRun) -> str:
    ks = run.ks
    header = "| K | " + " | ".join(str(k) for k in ks) + " |\n|---|" + "---:|" * len(ks)

    def _row(label: str, values: dict[str, float | None], fmt) -> str:
        cells = " | ".join(fmt(values[str(k)]) for k in ks)
        return f"| {label} | {cells} |"

    aggregate_table = "\n".join(
        [
            header,
            _row("Mean required-fact coverage@K", run.aggregate.mean_coverage_at_k, _fmt_pct),
            _row("Mean Recall@K (chunk-level)", run.aggregate.mean_recall_at_k, _fmt_pct),
            _row("All-required-facts-retrieved rate@K", run.aggregate.all_required_retrieved_rate_at_k, _fmt_pct),
            _row("Mean forbidden-fact hit rate@K", run.aggregate.mean_forbidden_hit_rate_at_k, _fmt_pct),
        ]
    )

    question_rows = []
    for qr in run.question_results:
        max_k = str(max(ks))
        question_rows.append(
            f"| {qr.question_id} | {qr.difficulty} | "
            f"{_fmt_pct(qr.metrics.coverage_at_k[max_k])} | {_fmt_pct(qr.metrics.recall_at_k[max_k])} | "
            f"{qr.metrics.reciprocal_rank:.3f} | {_fmt_pct(qr.metrics.forbidden_hit_rate_at_k[max_k])} | "
            f"{qr.metrics.available_required_fact_count} | {qr.metrics.excluded_required_fact_count} | "
            f"{qr.metrics.available_forbidden_fact_count} |"
        )
    question_table = (
        f"| Question | Difficulty | Coverage@{max(ks)} | Recall@{max(ks)} | Reciprocal rank | "
        f"Forbidden hit@{max(ks)} | Available req. facts | Excluded req. facts | Available forbidden facts |\n"
        "|---|---|---:|---:|---:|---:|---:|---:|---:|\n" + "\n".join(question_rows)
    )

    return f"""# Stage 7A.1 -- Regular Vector Retrieval Baseline: Scorecard

Generated from a single in-memory `RetrievalEvaluationRun` -- this
Markdown and `reports/stage7a_vector_retrieval_results.json` come from
the SAME execution, never two separate runs (same discipline as Stage
5A.1/D-039 and every stage since).

`corpus_profile`: `{run.corpus_profile}`
`embedding_model`: `{run.embedding_model}`
`generated_at`: `{run.generated_at}`
`index_hash`: `{run.index_build.index_hash}`
`total_indexed_records`: {run.index_build.total_record_count}
`K values evaluated`: {", ".join(str(k) for k in ks)}

This report compares real retrieval results, computed by exact chunk_id
membership against the Stage 6A/6B gold evidence catalog, against the 12
frozen Stage 6B benchmark questions. No LLM or semantic judge scores
anything here. A retrieved chunk counts as relevant to a required fact
ONLY when its chunk_id is a member of that fact's resolved gold
chunk_ids (fixture + fact_id + chunk_id scoped, see
`src/ingestion_bench/retrieval_baseline/gold.py`).

## Index build

- Candidate chunks: {run.index_build.candidate_chunk_count}
- Empty-retrieval_text chunks skipped (never indexed): {run.index_build.empty_retrieval_text_skipped_count}
- Indexed this run: {run.index_build.indexed_count}
- Skipped as unchanged: {run.index_build.skipped_unchanged_count}
- Build latency: {run.index_build.build_latency_seconds:.3f}s (embedding: {run.index_build.embedding_elapsed_seconds:.3f}s)
- Embedding cost (USD, where available): {run.index_build.embedding_cost_usd if run.index_build.embedding_cost_usd is not None else "n/a (local model, no per-token API cost)"}

## Aggregate scorecard (mean across {run.aggregate.question_count} questions)

{aggregate_table}

`n/a` means the metric had no applicable denominator for that K (e.g. a
question whose required facts were all missing-from-ingestion/not-
applicable/not-indexed in this corpus profile) -- never silently
reported as 0%. Mean reciprocal rank of the first relevant chunk (over
the full ranked list, not per-K): {run.aggregate.mean_reciprocal_rank:.3f}.
Mean retrieval latency: {run.aggregate.mean_retrieval_latency_seconds * 1000:.1f}ms.

## Per-question summary

{question_table}

Full per-question provenance (top-K results, matched/leaked fact ids,
resolved gold evidence) is in `artifacts/stage7a/question_results/`
and `reports/stage7a_vector_retrieval_results.json`.

## What this report does NOT establish

- Answer quality or correctness of any kind -- no answer-generation
  layer exists (this stage performs retrieval only).
- Graph-enriched retrieval, wiki retrieval, or vision-enriched ingestion
  quality -- not implemented (later stages).
- Cross-corpus-profile comparison beyond index-build metadata -- the
  scorecard above is computed against `{run.corpus_profile}` only; see
  `artifacts/stage7a/index_manifest.json` for the other built indexes'
  own chunk counts.
"""
