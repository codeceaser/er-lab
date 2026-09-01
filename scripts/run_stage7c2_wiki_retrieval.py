"""Stage 7C.2 runner: Wiki hub retrieval / navigation qualification.

READ-ONLY measurement over the frozen Stage 7C.0 + 7C.1 artifacts. Executes the
frozen questions for V, W0, D0, W1-D, W1-FULL and N_advisory, runs the
truth-informed suppression diagnostic on Q04/Q06/Q07, computes the three
attribution deltas, and emits one result object from which both the JSON and the
Markdown scorecard derive.

ZERO compiler / extractor calls. The frozen 22 facet vectors are LOADED, never
regenerated. Nothing in Stage 7C.0 or 7C.1 is written.

Usage (from the repository root, venv active):
    python scripts/run_stage7c2_wiki_retrieval.py            # real embeddings
    python scripts/run_stage7c2_wiki_retrieval.py --fake     # deterministic fake
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "fixtures"))

from ingestion_bench.cross_document_benchmark.benchmark_runner import (  # noqa: E402
    _evaluate_question,  # FROZEN Stage 7B.0 scorer, imported BY IDENTITY
    build_evidence_alignment,
    load_contract,
)
from ingestion_bench.cross_document_benchmark.fixtures import load_all_revision_fixtures  # noqa: E402
from ingestion_bench.cross_document_benchmark.indexer import build_index  # noqa: E402
from ingestion_bench.cross_document_benchmark.retriever import cross_document_search  # noqa: E402
from ingestion_bench.cross_document_benchmark.store import InMemoryCrossDocumentVectorStore  # noqa: E402
from ingestion_bench.retrieval_baseline.embeddings import (  # noqa: E402
    FakeEmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
)
from ingestion_bench.revision_authority.contract_runner import _run_registry_setup  # noqa: E402
from ingestion_bench.revision_authority.repository import InMemoryRevisionAuthorityRepository  # noqa: E402
from ingestion_bench.revision_authority.service import RevisionAuthorityService  # noqa: E402
from ingestion_bench.wiki_projection import config  # noqa: E402
from ingestion_bench.wiki_projection.benchmark import w0_result_from_vector_result  # noqa: E402
from ingestion_bench.wiki_projection.facet_store import FacetEmbeddingRow, InMemoryStage7C1Store  # noqa: E402
from ingestion_bench.wiki_projection.navigation import NON_QUALIFYING_LABEL, Navigator  # noqa: E402
from ingestion_bench.wiki_projection.projection import build_projection  # noqa: E402
from ingestion_bench.wiki_projection.retrieval import run_arm, seed_d0, seed_w1  # noqa: E402
from ingestion_bench.wiki_projection.stage7c2_report import (  # noqa: E402
    build_blind_page_quality_packet,
    build_stage7c2_results,
    render_stage7c2_scorecard,
)
from ingestion_bench.wiki_projection.validation import DerivedLink  # noqa: E402

# Frozen identities -- fail closed if any drifts.
FROZEN = {
    "projection_hash": "4162fa515cf29d09391c0d963b76c7e63b1d454c4439ee0568805d1a31e3b613",
    "verdict_set_sha256": "d49cc8643388f830ffbcf5097faa8335a40c366b06b8f54a176aa978b06158bd",
    "compiler_contract_sha256": "35ccad855b10e6e8c08f6699136dff590dbd37abcef3c64147500a94edcad793",
    "embedding_set_sha256": "bbc233f68a6b7ccdbdebabf9dfe6e35f3a13ee27309077100aec2662e921a5a0",
    "closure_semantic_hash": "bf2a55e5168d33281d90e61fe2ee62f1cf6d789bd0bc967c813df3ed662d92d9",
}
SUPPRESSION_QUESTIONS = {"Q04", "Q06", "Q07"}
PRIMARY_ARMS = ["D0", "W1-D", "W1-FULL"]


class FrozenBasisError(RuntimeError):
    """A frozen Stage 7C.0/7C.1 identity is missing or mismatched."""


def verify_frozen_basis(projection) -> dict:
    """Fail closed BEFORE any measured behaviour."""
    failures: list[str] = []
    contracts = config.CONTRACTS_ROOT
    reports = config.REPORTS_ROOT

    compiler_contract = json.loads((contracts / "wiki_compiler_v1.json").read_text(encoding="utf-8"))
    manifest = json.loads((reports / "stage7c1_final_embedding_manifest.json").read_text(encoding="utf-8"))
    payloads = json.loads((reports / "stage7c1_final_payloads.json").read_text(encoding="utf-8"))
    gate_q = json.loads((reports / "stage7c1_gate_q_final.json").read_text(encoding="utf-8"))

    observed = {
        "projection_hash": projection.projection_hash,
        "verdict_set_sha256": compiler_contract["owner_adjudication"]["verdict_set_sha256"],
        "compiler_contract_sha256": compiler_contract["contract_sha256"],
        "embedding_set_sha256": manifest["embedding_set_sha256"],
    }
    for name, expected in FROZEN.items():
        if name == "closure_semantic_hash":
            continue
        if observed.get(name) != expected:
            failures.append(f"{name}: {observed.get(name)} != {expected}")

    counts = {
        "facets": len(payloads["payloads"]),
        "pages": len(projection.page_identities),
        "final_links": len(payloads["final_derived_links"]),
        "facet_embeddings": manifest["embedding_count"],
    }
    for name, expected_count in (("facets", 22), ("pages", 13), ("final_links", 30), ("facet_embeddings", 22)):
        if counts[name] != expected_count:
            failures.append(f"{name} = {counts[name]}, expected {expected_count}")
    if gate_q["overall_status"] != "FAIL" or set(gate_q["failing_criteria"]) != {"Q-5", "Q-7", "Q-8"}:
        failures.append(f"Gate Q is {gate_q['overall_status']} {gate_q['failing_criteria']}, expected FAIL on Q-5/Q-7/Q-8")

    if failures:
        raise FrozenBasisError(
            "Stage 7C.2 STOPPED -- frozen basis mismatch. No measured behaviour was run:\n  - "
            + "\n  - ".join(failures)
        )
    return {"observed": observed, "counts": counts, "gate_q": gate_q}


def load_frozen_facet_vectors() -> list[FacetEmbeddingRow]:
    """Load the frozen 22 vectors. NEVER regenerate: a replacement set would be
    a different frozen representation."""
    path = REPO_ROOT / "artifacts" / "stage7c1_closure" / "facet_embeddings.json"
    if not path.exists():
        raise FrozenBasisError(
            f"the frozen facet vectors are unavailable at {path}. Stage 7C.2 will not regenerate them."
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [
        FacetEmbeddingRow(
            page_key=r["page_key"], document_revision_id=r["document_revision_id"],
            embedding=r["embedding"], embedding_dimension=r["embedding_dimension"],
            embedding_sha256=r.get("embedding_sha256", ""), payload_sha256=r["payload_sha256"],
            payload_text=r["payload_text"], component_manifest=r["component_manifest"],
            verdict_set_sha256=r["verdict_set_sha256"], projection_hash=r["projection_hash"],
            embedding_model=r["embedding_model"], compiler_model_identity=r["compiler_model_identity"],
            prompt_version=r["prompt_version"], prompt_sha256=r["prompt_sha256"],
            run_id=r["repeatability_run_id"], source_chunk_ids=r["source_chunk_ids"],
        )
        for r in raw
    ]


def load_frozen_derived_links() -> list[DerivedLink]:
    """The 30 frozen post-pass-3 claim-derived links."""
    payloads = json.loads(
        (config.REPORTS_ROOT / "stage7c1_final_payloads.json").read_text(encoding="utf-8")
    )
    return [DerivedLink.model_validate(link) for link in payloads["final_derived_links"]]


def main() -> None:
    use_fake = "--fake" in sys.argv
    suffix = "_FAKE" if use_fake else ""

    contract = load_contract(config.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH)
    fixtures = load_all_revision_fixtures(contract["fixtures"])
    projection = build_projection(fixtures)

    try:
        basis = verify_frozen_basis(projection)
    except FrozenBasisError as exc:
        print(str(exc))
        sys.exit(2)

    facet_rows = load_frozen_facet_vectors()
    derived_links = load_frozen_derived_links()
    store = InMemoryStage7C1Store()
    store.upsert_facet_embeddings(facet_rows)

    print("Stage 7C.2 -- WIKI HUB RETRIEVAL / NAVIGATION QUALIFICATION")
    print(f"  frozen projection    : {projection.projection_hash[:16]}...")
    print(f"  frozen facet vectors : {len(facet_rows)} loaded (not regenerated)")
    print(f"  frozen claim links   : {len(derived_links)}")
    print(f"  Gate Q               : {basis['gate_q']['overall_status']} "
          f"{basis['gate_q']['failing_criteria']} -> Gate A unreachable; W1 arms labelled")
    print("  compiler calls       : 0 (none reachable)")
    print()

    provider = FakeEmbeddingProvider() if use_fake else SentenceTransformerEmbeddingProvider()
    chunk_store = InMemoryCrossDocumentVectorStore()
    build_index(fixtures, provider, chunk_store)

    repository = InMemoryRevisionAuthorityRepository()
    service = RevisionAuthorityService(repository)
    revision_by_symbol = {
        symbol: {
            "source_document_sha256": fx.source_document_sha256,
            "version_label": fx.version_label, "revision_number": fx.revision_number,
        }
        for symbol, fx in fixtures.items()
    }
    symbol_to_id: dict[str, str] = {}
    id_to_symbol: dict[str, str] = {}
    for document in contract["authority_setup"]["documents"]:
        _run_registry_setup(repository, service, document, revision_by_symbol, symbol_to_id, id_to_symbol, [], [])

    evidence = build_evidence_alignment(contract, fixtures)
    corpus_documents = sorted({fx.logical_document_id for fx in fixtures.values()})
    chunk_vectors = {
        record.chunk_id: record.embedding
        for record in chunk_store._records.values()  # noqa: SLF001 -- in-memory reference store
    }
    facet_vectors_by_page: dict[str, list[float]] = {}
    for row in facet_rows:
        facet_vectors_by_page.setdefault(row.page_key, row.embedding)

    navigator = Navigator(projection, derived_links=derived_links)
    results = build_stage7c2_results(
        contract=contract, fixtures=fixtures, projection=projection, evidence=evidence,
        service=service, chunk_store=chunk_store, provider=provider,
        corpus_documents=corpus_documents, symbol_to_id=symbol_to_id, id_to_symbol=id_to_symbol,
        facet_rows=facet_rows, derived_links=derived_links, navigator=navigator,
        chunk_vectors=chunk_vectors, facet_vectors_by_page=facet_vectors_by_page,
        frozen_basis=basis, suppression_questions=SUPPRESSION_QUESTIONS, primary_arms=PRIMARY_ARMS,
    )

    config.REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    (config.REPORTS_ROOT / f"stage7c_wiki_results{suffix}.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    (config.REPORTS_ROOT / f"stage7c_wiki_scorecard{suffix}.md").write_text(
        render_stage7c2_scorecard(results), encoding="utf-8"
    )
    packet = build_blind_page_quality_packet(projection, facet_rows)
    (config.REPORTS_ROOT / f"stage7c_page_quality_blind_packet{suffix}.md").write_text(
        packet["markdown"], encoding="utf-8"
    )
    (config.REPORTS_ROOT / f"stage7c_page_quality_rubric{suffix}.json").write_text(
        json.dumps(packet["schema"], indent=2), encoding="utf-8"
    )

    summary = results["summary"]
    print("Per-arm outcomes (frozen Stage 7B.0 scorer):")
    for arm, counts in summary["outcome_counts"].items():
        label = "  [NON-QUALIFYING]" if arm in ("W1-D", "W1-FULL", "N_advisory") else ""
        print(f"  {arm:12} {counts}{label}")
    print()
    for name, delta in results["attribution"].items():
        if isinstance(delta, dict) and "verdict" in delta:
            print(f"  {name:22} {delta['verdict']}")
    for statement in results["attribution"]["mandated_statements"]:
        print(f"  MANDATED: {statement}")
    print()
    print(f"Authority leakage (all arms): {summary['total_authority_leakage']} (must be 0)")
    print(f"GATE A: unreachable (Gate Q = FAIL)")
    print(f"\nResults:   {config.REPORTS_ROOT / f'stage7c_wiki_results{suffix}.json'}")
    print(f"Scorecard: {config.REPORTS_ROOT / f'stage7c_wiki_scorecard{suffix}.md'}")
    print(f"Blind page-quality packet: "
          f"{config.REPORTS_ROOT / f'stage7c_page_quality_blind_packet{suffix}.md'}")
    print("\nSTOPPED at the owner page-quality checkpoint. "
          "docs/STAGE7C_WIKI_DECISION.md is NOT finalized.")

    if summary["total_authority_leakage"] != 0:
        print("\nHARD FAILURE: authority leakage != 0")
        sys.exit(1)


if __name__ == "__main__":
    main()
