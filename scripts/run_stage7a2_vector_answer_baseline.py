"""Stage 7A.2 runner: generates one auditable answer per Stage 6B
question, using ONLY the frozen Stage 7A.1 top-5 retrieval context
(reports/stage7a_vector_retrieval_results.json, never re-run), then
deterministically validates every citation. Writes the scorecard/
results/artifacts.

Never modifies Stage 5A/6A/6B/7A.1 code or artifacts. Uses the one
configured real answer model (`INGESTION_BENCH_ANSWER_MODEL`, default
gpt-4o-mini) -- requires `OPENAI_API_KEY` in the environment/.env.

Usage (from the repository root, with the venv active, AFTER
scripts/run_stage7a_retrieval_baseline.py has produced
reports/stage7a_vector_retrieval_results.json at least once):
    python scripts/run_stage7a2_vector_answer_baseline.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "fixtures"))

from ingestion_bench.answer_baseline import config  # noqa: E402
from ingestion_bench.answer_baseline.answer_generator import OpenAIAnswerGenerator  # noqa: E402
from ingestion_bench.answer_baseline.evaluation import load_retrieval_run, run_answer_evaluation  # noqa: E402
from ingestion_bench.answer_baseline.report import render_scorecard_markdown  # noqa: E402


def main() -> None:
    retrieval_run = load_retrieval_run()
    print(f"Loaded retrieval context: {config.STAGE7A_RETRIEVAL_RESULTS_PATH}")
    print(f"  corpus_profile={retrieval_run.corpus_profile!r} embedding_model={retrieval_run.embedding_model!r}")
    print(f"  questions={len(retrieval_run.question_results)}")

    generator = OpenAIAnswerGenerator()
    print(f"Answer model: {generator.model_identity}")

    run = run_answer_evaluation(retrieval_run, generator)

    config.ARTIFACTS_STAGE7A2_ROOT.mkdir(parents=True, exist_ok=True)
    answers_dir = config.ARTIFACTS_STAGE7A2_ROOT / "question_answers"
    answers_dir.mkdir(parents=True, exist_ok=True)
    for qr in run.question_results:
        (answers_dir / f"{qr.question_id}.json").write_text(qr.model_dump_json(indent=2), encoding="utf-8")

    config.REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    (config.REPORTS_ROOT / "stage7a2_vector_answer_results.json").write_text(
        run.model_dump_json(indent=2), encoding="utf-8"
    )
    (config.REPORTS_ROOT / "stage7a2_vector_answer_scorecard.md").write_text(
        render_scorecard_markdown(run), encoding="utf-8"
    )

    print(f"\nGenerated {len(run.question_results)} answers.")
    print(f"  total_invalid_citations={run.aggregate.total_invalid_citations}")
    print(f"  total_unresolved_provenance_citations={run.aggregate.total_unresolved_provenance_citations}")
    print(f"  mean_required_fact_citation_coverage_rate={run.aggregate.mean_required_fact_citation_coverage_rate}")
    print(f"  mean_forbidden_fact_citation_rate={run.aggregate.mean_forbidden_fact_citation_rate}")
    print(f"  uncited/total claims={run.aggregate.total_uncited_claims}/{run.aggregate.total_claims}")
    print(
        f"  evidence_sufficiency_accuracy_rate={run.aggregate.evidence_sufficiency_accuracy_rate} "
        f"(scored {run.aggregate.evidence_sufficiency_scored_question_count} questions)"
    )
    print(f"  total_input_tokens={run.aggregate.total_input_tokens} total_output_tokens={run.aggregate.total_output_tokens}")
    print(f"  total_estimated_cost_usd={run.aggregate.total_estimated_cost_usd}")
    print(f"  mean_answer_latency_seconds={run.aggregate.mean_answer_latency_seconds:.3f}")
    print(f"\nScorecard: {config.REPORTS_ROOT / 'stage7a2_vector_answer_scorecard.md'}")
    print(f"Results: {config.REPORTS_ROOT / 'stage7a2_vector_answer_results.json'}")
    print(f"Per-question artifacts: {answers_dir}")


if __name__ == "__main__":
    main()
