"""Stage 7B.2 runner: the hybrid Vector-Graph value probe.

Verifies all frozen Stage 7B.0 / 7B.1 inputs, loads the committed Stage
7B.1 real graph snapshot (NO OpenAI re-extraction) and builds the perfect
FakeRelationshipExtractor graph, runs the five modes (V/G/H0/H1/H2) over
both graph conditions with real sentence-transformers embeddings, scores
them with the frozen Stage 7B.0 scorer, applies the fixed decision gates,
and writes the reports/artifacts/decision doc from one run object.

No query-time LLM. Retrieval-ranking probe only. Never modifies any
frozen stage.

Usage (from the repo root, venv active):
    python scripts/run_stage7b2_hybrid_probe.py          # real sentence-transformers
    python scripts/run_stage7b2_hybrid_probe.py --fake   # deterministic, no download
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "fixtures"))

from ingestion_bench.hybrid_retrieval_benchmark import config as hcfg  # noqa: E402
from ingestion_bench.hybrid_retrieval_benchmark.benchmark_runner import run_probe  # noqa: E402
from ingestion_bench.hybrid_retrieval_benchmark.report import render_decision_doc, render_results_json, render_scorecard_markdown  # noqa: E402
from ingestion_bench.retrieval_baseline.embeddings import FakeEmbeddingProvider, SentenceTransformerEmbeddingProvider  # noqa: E402
from ingestion_bench.revision_authority.repository import InMemoryRevisionAuthorityRepository  # noqa: E402


def main() -> None:
    fake = "--fake" in sys.argv[1:]
    # The MEASURED run uses the isolated Postgres stores (section 4).
    # `--in-memory` forces the deterministic in-memory path (e.g. when no
    # Postgres is available); `--fake` implies deterministic in-memory.
    persisted = not fake and "--in-memory" not in sys.argv[1:]
    provider = FakeEmbeddingProvider() if fake else SentenceTransformerEmbeddingProvider()
    repository = InMemoryRevisionAuthorityRepository()
    print(f"Mode: {'FAKE (deterministic, no download)' if fake else 'REAL sentence-transformers'} ({provider.model_identity})")
    print(f"Stores: {'PERSISTED Postgres (isolated tables)' if persisted else 'in-memory (deterministic)'}")

    result = run_probe(hcfg.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH, hcfg.load_probe_config(), repository, provider, persisted=persisted)

    art = hcfg.ARTIFACTS_ROOT
    (art / "query_results" / "real_graph").mkdir(parents=True, exist_ok=True)
    (art / "query_results" / "perfect_graph").mkdir(parents=True, exist_ok=True)

    (art / "input_verification.json").write_text(result.input_verification.model_dump_json(indent=2), encoding="utf-8")
    (art / "real_graph_manifest.json").write_text(json.dumps({"payload_sha256": result.input_verification.committed_real_graph_payload_hash, "node_count": result.input_verification.real_graph_node_count, "edge_count": result.input_verification.real_graph_edge_count, "extraction_run_id": result.input_verification.real_graph_extraction_run_id}, indent=2), encoding="utf-8")
    (art / "perfect_graph_manifest.json").write_text(json.dumps({"payload_sha256": result.input_verification.perfect_graph_payload_hash, "recall": result.input_verification.perfect_graph_recall, "precision": result.input_verification.perfect_graph_precision, "collisions": result.input_verification.perfect_graph_collisions}, indent=2), encoding="utf-8")
    (art / "edge_embedding_index_manifest.json").write_text(json.dumps(result.edge_index_manifests, indent=2), encoding="utf-8")
    (art / "ablation_comparison.json").write_text(json.dumps([json.loads(m.model_dump_json()) for m in result.mode_results], indent=2), encoding="utf-8")
    (art / "final_decision.json").write_text(json.dumps({"decision_gate": result.decision_gate, "decision": result.decision, "rationale": result.decision_rationale, "real_gate_inputs": result.real_gate_inputs, "perfect_gate_inputs": result.perfect_gate_inputs}, indent=2), encoding="utf-8")
    # per-question, per-condition mode results
    by_q_cond: dict[tuple[str, str], list] = {}
    for m in result.mode_results:
        cond = m.graph_condition
        if cond == "common":
            for c in ("real_graph", "perfect_graph"):
                by_q_cond.setdefault((m.question_id, c), []).append(json.loads(m.model_dump_json()))
        else:
            by_q_cond.setdefault((m.question_id, cond), []).append(json.loads(m.model_dump_json()))
    for (qid, cond), rows in by_q_cond.items():
        (art / "query_results" / cond / f"{qid}.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")

    hcfg.REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    (hcfg.REPORTS_ROOT / "stage7b2_hybrid_retrieval_results.json").write_text(render_results_json(result), encoding="utf-8")
    (hcfg.REPORTS_ROOT / "stage7b2_hybrid_retrieval_scorecard.md").write_text(render_scorecard_markdown(result), encoding="utf-8")
    (REPO_ROOT / "docs" / "STAGE7B2_HYBRID_GRAPH_CLOSURE_DECISION.md").write_text(render_decision_doc(result), encoding="utf-8")

    iv = result.input_verification
    print(f"\nFrozen inputs verified: corpus={iv.corpus_index_hash_matches}, real_graph_payload={iv.real_graph_payload_hash_matches}, perfect recall/precision={iv.perfect_graph_recall}/{iv.perfect_graph_precision}")
    print(f"Total authority leakage (all modes): {sum(m.authority_leakage_count for m in result.mode_results)}")
    print(f"Final budget respected: {all(len(m.final_chunk_ids) <= m.top_k for m in result.mode_results)}")
    print(f"\nDECISION GATE {result.decision_gate}: {result.decision}")
    print(f"  {result.decision_rationale}")
    print(f"  real H2 gate inputs:    {result.real_gate_inputs}")
    print(f"  perfect H2 gate inputs: {result.perfect_gate_inputs}")
    print(f"\nReports: {hcfg.REPORTS_ROOT}/stage7b2_*  Decision doc: docs/STAGE7B2_HYBRID_GRAPH_CLOSURE_DECISION.md  Artifacts: {art}")


if __name__ == "__main__":
    main()
