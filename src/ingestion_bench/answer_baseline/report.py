"""Stage 7A.2: report rendering.

The Markdown scorecard and the JSON results file are always rendered
from the SAME in-memory `AnswerEvaluationRun` object -- same discipline
as Stage 5A.1/D-039 and every stage since (including Stage 7A.1's own
report.py): never two separate executions producing two reports that
could silently drift apart.
"""

from __future__ import annotations

from ingestion_bench.answer_baseline.config import HIGHLIGHTED_QUESTION_IDS
from ingestion_bench.answer_baseline.evaluation import AnswerEvaluationRun


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def _fmt_bool(value: bool | None) -> str:
    if value is None:
        return "n/a"
    return "yes" if value else "no"


def _fmt_cost(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"${value:.6f}"


def render_scorecard_markdown(run: AnswerEvaluationRun) -> str:
    question_rows = []
    for qr in run.question_results:
        highlight = " ★" if qr.question_id in HIGHLIGHTED_QUESTION_IDS else ""
        question_rows.append(
            f"| {qr.question_id}{highlight} | {qr.difficulty} | "
            f"{_fmt_bool(qr.answer.evidence_sufficient)} | "
            f"{_fmt_pct(qr.validation.required_fact_citation_coverage_rate)} | "
            f"{_fmt_pct(qr.validation.cited_chunk_forbidden_evidence_exposure_rate)} | "
            f"{qr.validation.invalid_citation_count} | "
            f"{qr.validation.uncited_claim_count}/{qr.validation.total_claim_count} | "
            f"{_fmt_bool(qr.validation.evidence_sufficiency_accuracy)} | "
            f"{qr.answer.answer_latency_seconds:.3f}s | "
            f"{qr.answer_text_correctness_human_review} | "
            f"{qr.citation_support_human_review} |"
        )
    question_table = (
        "| Question | Difficulty | Evidence sufficient | Req. fact coverage | Cited-chunk forbidden exposure | "
        "Invalid citations | Uncited/total claims | Sufficiency accuracy | Latency | "
        "Answer-text review | Citation-support review |\n"
        "|---|---|---|---:|---:|---:|---:|---|---:|---|---|\n" + "\n".join(question_rows)
    )

    highlighted_section_rows = []
    for qr in run.question_results:
        if qr.question_id not in HIGHLIGHTED_QUESTION_IDS:
            continue
        cited_facts = ", ".join(
            fact_id for fact_id, covered in qr.validation.required_fact_citation_coverage.items() if covered
        ) or "(none)"
        missed_facts = ", ".join(
            fact_id for fact_id, covered in qr.validation.required_fact_citation_coverage.items() if not covered
        ) or "(none)"
        forbidden = ", ".join(qr.validation.forbidden_cited_fact_ids) or "(none)"
        notes = f"\n\n**Citation-support review notes:** {qr.citation_support_notes}" if qr.citation_support_notes else ""
        highlighted_section_rows.append(
            f"### {qr.question_id} ({qr.difficulty})\n\n"
            f"**Question:** {qr.question}\n\n"
            f"**Answer rubric:** {qr.answer_rubric}\n\n"
            f"**Generated answer:** {qr.answer.answer_text}\n\n"
            f"**Evidence sufficient (model-reported):** {_fmt_bool(qr.answer.evidence_sufficient)}\n\n"
            f"**Required facts cited:** {cited_facts}\n\n"
            f"**Required facts NOT cited:** {missed_facts}\n\n"
            f"**Forbidden facts cited (should be empty):** {forbidden}\n\n"
            f"**Invalid citations:** {qr.validation.invalid_citation_count}\n\n"
            f"**Evidence-sufficiency accuracy:** {_fmt_bool(qr.validation.evidence_sufficiency_accuracy)} "
            f"(scored only when retrieval did not return all required facts)\n\n"
            f"**Answer-text correctness (human review):** {qr.answer_text_correctness_human_review}\n\n"
            f"**Citation-support (human review):** {qr.citation_support_human_review}{notes}\n"
        )
    highlighted_section = "\n".join(highlighted_section_rows)

    return f"""# Stage 7A.2 -- Auditable Vector-RAG Answer Baseline: Scorecard

Generated from a single in-memory `AnswerEvaluationRun` -- this Markdown
and `reports/stage7a2_vector_answer_results.json` come from the SAME
execution, never two separate runs.

`answer_model`: `{run.answer_model}`
`answer_temperature`: `{run.answer_temperature}`
`answer_prompt_version`: `{run.answer_prompt_version}`
`answer_prompt_sha256`: `{run.answer_prompt_sha256}`
`generated_at`: `{run.generated_at}`
`retrieval_source`: `{run.retrieval_source}` (repository-relative;
Stage 7A.1's own frozen, committed output -- retrieval was never re-run
for this stage)
`retrieval_results_sha256`: `{run.retrieval_results_sha256}`
`retrieval_corpus_profile`: `{run.retrieval_corpus_profile}`
`retrieval_embedding_model`: `{run.retrieval_embedding_model}`

This report validates citations MECHANICALLY -- exact chunk_id set
membership against the Stage 7A.1 retrieval context and the Stage 6A/6B
gold evidence catalog. No LLM or semantic judge scores anything here.
Answer-TEXT correctness and citation SUPPORT (whether a cited chunk's
own text actually backs its claim, as opposed to the mechanical
retrieval/coverage checks above) are separate, explicitly human-review
fields on every question result (`answer_text_correctness_human_review`,
`citation_support_human_review`) -- never silently assumed or
auto-graded. `cited_chunk_forbidden_evidence_exposure_rate` measures
only whether a CITED CHUNK CONTAINS forbidden evidence -- it does not by
itself prove the answer text presented that evidence as current or
correct; that judgment is exactly what `citation_support_human_review`
records.

## Aggregate scorecard (across {run.aggregate.question_count} questions)

| Metric | Value |
|---|---:|
| Total invalid citations | {run.aggregate.total_invalid_citations} |
| Total unresolved-provenance citations | {run.aggregate.total_unresolved_provenance_citations} |
| Mean required-fact citation coverage rate | {_fmt_pct(run.aggregate.mean_required_fact_citation_coverage_rate)} |
| Mean cited-chunk forbidden-evidence exposure rate | {_fmt_pct(run.aggregate.mean_cited_chunk_forbidden_evidence_exposure_rate)} |
| Uncited / total claims | {run.aggregate.total_uncited_claims} / {run.aggregate.total_claims} |
| Mean citation completeness | {_fmt_pct(run.aggregate.mean_citation_completeness)} |
| Evidence-sufficiency accuracy (scored questions) | {_fmt_pct(run.aggregate.evidence_sufficiency_accuracy_rate)} ({run.aggregate.evidence_sufficiency_scored_question_count} of {run.aggregate.question_count} questions had incomplete retrieval, the only case this accuracy is scored) |
| Total input tokens | {run.aggregate.total_input_tokens if run.aggregate.total_input_tokens is not None else "n/a"} |
| Total output tokens | {run.aggregate.total_output_tokens if run.aggregate.total_output_tokens is not None else "n/a"} |
| Total estimated cost (USD) | {_fmt_cost(run.aggregate.total_estimated_cost_usd)} |
| Mean answer latency | {run.aggregate.mean_answer_latency_seconds:.3f}s |

`n/a` means no applicable denominator (e.g. a question with zero
available required facts to score coverage against), never a misleading
0%/0 value.

## Per-question summary

★ marks the 7 questions Stage 7A.2's own spec calls out as exposing
the two real Stage 7A.1 findings (required/forbidden evidence
co-located in the same chunk; the RTO/RPO table chunk absent from top-5
for the consolidation question).

{question_table}

## Highlighted questions (detail)

{highlighted_section}

## What this report does NOT establish

- Any automatic/semantic grading of answer-text correctness or citation
  support -- both `answer_text_correctness_human_review` and
  `citation_support_human_review` are filled in by a HUMAN reading the
  committed answers, never by a second LLM or inferred classifier.
- That a chunk's forbidden-evidence content was actually presented as
  current by the answer text -- `cited_chunk_forbidden_evidence_exposure_rate`
  is a mechanical, chunk-membership-only signal (see above); read it
  together with `citation_support_human_review`, never alone.
- Any retrieval-quality claim beyond what `reports/stage7a_vector_retrieval_scorecard.md`
  already establishes -- retrieval itself was not re-run or re-scored here.
- Graph RAG, wiki retrieval, vision-enriched ingestion, reranking, hybrid
  retrieval, query decomposition, ADK orchestration -- none implemented
  or used anywhere in this stage.

Full per-question provenance (retrieved chunks, claim citations, raw
validation output) is in `artifacts/stage7a2/question_answers/` and
`reports/stage7a2_vector_answer_results.json`.
"""
