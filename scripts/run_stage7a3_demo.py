"""Stage 7A.3 runner: renders the minimal local auditable-semantic-search
demo -- a single, self-contained static HTML file over the frozen Stage
7A.2/7A.2a answer baseline (reports/stage7a2_vector_answer_results.json).

Never performs retrieval or answer generation itself -- reads the
already-committed answer run verbatim. Never modifies Stage 5A/6A/6B/
7A.1/7A.2/7A.2a code or artifacts.

Usage (from the repository root, with the venv active, AFTER
reports/stage7a2_vector_answer_results.json exists):
    python scripts/run_stage7a3_demo.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "fixtures"))

from ingestion_bench.answer_baseline import config  # noqa: E402
from ingestion_bench.answer_baseline.evaluation import AnswerEvaluationRun  # noqa: E402
from ingestion_bench.demo.render import render_demo_html  # noqa: E402
from ingestion_bench.demo.view_model import build_all_question_views  # noqa: E402


def main() -> None:
    results_path = config.REPORTS_ROOT / "stage7a2_vector_answer_results.json"
    run = AnswerEvaluationRun.model_validate(json.loads(results_path.read_text(encoding="utf-8")))

    views = build_all_question_views(run.question_results)
    html_page = render_demo_html(views)

    output_path = config.REPORTS_ROOT / "stage7a3_demo.html"
    output_path.write_text(html_page, encoding="utf-8")

    print(f"Loaded {len(run.question_results)} questions from {results_path}")
    print(f"Demo written to: {output_path}")
    print("Open it directly in a browser -- no server process required.")


if __name__ == "__main__":
    main()
