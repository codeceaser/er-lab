"""Stage 7A.2a closure: migrates the ALREADY-COMMITTED Stage 7A.2 answer
run to the corrected field name/added provenance metadata and applies
the recorded human review, regenerating reports/stage7a2_vector_answer_
{results.json,scorecard.md} from that SAME answer data. Never re-runs
retrieval, never re-invokes the answer model -- the human review below
was performed against the exact answers already committed (commit
7a18f18) and would be invalidated by generating new ones.

This is a single, one-off closure action (hardcoding exactly this run's
review), never a generic run-metadata/review framework.

Usage (from the repository root, with the venv active):
    python scripts/apply_stage7a2a_closure.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "fixtures"))

from ingestion_bench.answer_baseline import config  # noqa: E402
from ingestion_bench.answer_baseline.evaluation import (  # noqa: E402
    AnswerEvaluationRun,
    QuestionAnswerResult,
    build_aggregate_answer_metrics,
    repo_relative_path,
    sha256_file,
)
from ingestion_bench.answer_baseline.prompt import PROMPT_VERSION, prompt_sha256  # noqa: E402
from ingestion_bench.answer_baseline.report import render_scorecard_markdown  # noqa: E402

# Manual review of the exact 12 answers committed in
# reports/stage7a2_vector_answer_results.json (commit 7a18f18). Verified
# by direct inspection of artifacts/stage7a2/question_answers/*.json
# (retrieved chunk text vs. claim text vs. cited chunk provenance)
# before this closure was written -- "fully_supported" is asserted only
# for questions where every cited chunk's own fixture/text was actually
# checked against its claim, never assumed by default.
REVIEW: dict[str, dict[str, str]] = {
    "Q_DIRECT_001": {"answer_text": "correct", "citation_support": "fully_supported"},
    "Q_DIRECT_002": {"answer_text": "correct", "citation_support": "fully_supported"},
    "Q_DIRECT_003": {
        "answer_text": "correct",
        "citation_support": "partially_supported",
        "citation_support_notes": (
            "Cites the correct Payment Settlement RTO table chunk (29ec1f09e064...) AND an "
            "unrelated STRESS_PPTX_001 4-hour annotation chunk (39f484de8715...) for the same "
            "claim. The answer text itself is correct, but one of its two supporting citations "
            "is not actually about Payment Settlement."
        ),
    },
    "Q_DIRECT_004": {"answer_text": "correct", "citation_support": "fully_supported"},
    "Q_DISTRACTOR_001": {"answer_text": "correct", "citation_support": "fully_supported"},
    "Q_DISTRACTOR_002": {"answer_text": "correct", "citation_support": "fully_supported"},
    "Q_DISTRACTOR_003": {"answer_text": "correct", "citation_support": "fully_supported"},
    "Q_MULTIHOP_001": {"answer_text": "correct", "citation_support": "fully_supported"},
    "Q_MULTIHOP_002": {"answer_text": "correct", "citation_support": "fully_supported"},
    "Q_RELATIONAL_001": {"answer_text": "correct", "citation_support": "fully_supported"},
    "Q_RELATIONAL_002": {"answer_text": "correct", "citation_support": "fully_supported"},
    "Q_CONSOLIDATION_001": {
        "answer_text": "partially_correct",
        "answer_text_notes": (
            "Application/ownership/control/obligation/recovery-procedure facts are correct and "
            "RPO is correctly flagged insufficient; the RTO=4h claim is textually correct but "
            "its citation is not (see citation-support notes)."
        ),
        "citation_support": "partially_supported",
        "citation_support_notes": (
            "The RTO=4h claim is supported ONLY by the unrelated STRESS_PPTX_001 annotation "
            "chunk (39f484de8715...); the actual Payment Settlement RTO/RPO table chunk "
            "(29ec1f09e064...) was not in this question's top-5 retrieval at all -- the same "
            "real Stage 7A.1 narrative-vs-table-chunk finding surfacing at the answer layer."
        ),
    },
}


def main() -> None:
    results_path = config.REPORTS_ROOT / "stage7a2_vector_answer_results.json"
    old = json.loads(results_path.read_text(encoding="utf-8"))

    old_question_ids = {qr["question_id"] for qr in old["question_results"]}
    if set(REVIEW.keys()) != old_question_ids:
        raise SystemExit(
            f"REVIEW map does not exactly match committed question_ids: "
            f"missing={old_question_ids - set(REVIEW.keys())} extra={set(REVIEW.keys()) - old_question_ids}"
        )

    question_results: list[QuestionAnswerResult] = []
    for qr_dict in old["question_results"]:
        qid = qr_dict["question_id"]
        review = REVIEW[qid]

        validation_dict = dict(qr_dict["validation"])
        validation_dict["cited_chunk_forbidden_evidence_exposure_rate"] = validation_dict.pop("forbidden_fact_citation_rate")

        migrated = dict(qr_dict)
        migrated["validation"] = validation_dict
        migrated["answer_text_correctness_human_review"] = review["answer_text"]
        migrated["answer_text_correctness_notes"] = review.get("answer_text_notes")
        migrated["citation_support_human_review"] = review["citation_support"]
        migrated["citation_support_notes"] = review.get("citation_support_notes")

        question_results.append(QuestionAnswerResult.model_validate(migrated))

    aggregate = build_aggregate_answer_metrics(question_results)

    retrieval_results_path = config.STAGE7A_RETRIEVAL_RESULTS_PATH
    run = AnswerEvaluationRun(
        answer_model=old["answer_model"],
        answer_temperature=config.ANSWER_TEMPERATURE,
        answer_prompt_version=PROMPT_VERSION,
        answer_prompt_sha256=prompt_sha256(),
        generated_at=old["generated_at"],
        retrieval_source=repo_relative_path(retrieval_results_path),
        retrieval_results_sha256=sha256_file(retrieval_results_path),
        retrieval_corpus_profile=old["retrieval_corpus_profile"],
        retrieval_embedding_model=old["retrieval_embedding_model"],
        question_results=question_results,
        aggregate=aggregate,
    )

    answers_dir = config.ARTIFACTS_STAGE7A2_ROOT / "question_answers"
    answers_dir.mkdir(parents=True, exist_ok=True)
    for qr in run.question_results:
        (answers_dir / f"{qr.question_id}.json").write_text(qr.model_dump_json(indent=2), encoding="utf-8")

    results_path.write_text(run.model_dump_json(indent=2), encoding="utf-8")
    (config.REPORTS_ROOT / "stage7a2_vector_answer_scorecard.md").write_text(
        render_scorecard_markdown(run), encoding="utf-8"
    )

    print(f"Migrated {len(run.question_results)} questions (no retrieval or answer-model re-run).")
    print(f"retrieval_source={run.retrieval_source!r}")
    print(f"retrieval_results_sha256={run.retrieval_results_sha256}")
    print(f"answer_prompt_version={run.answer_prompt_version!r} answer_prompt_sha256={run.answer_prompt_sha256}")
    print(f"answer_temperature={run.answer_temperature}")
    print(
        "mean_cited_chunk_forbidden_evidence_exposure_rate="
        f"{run.aggregate.mean_cited_chunk_forbidden_evidence_exposure_rate}"
    )
    print(f"Results: {results_path}")
    print(f"Scorecard: {config.REPORTS_ROOT / 'stage7a2_vector_answer_scorecard.md'}")


if __name__ == "__main__":
    main()
