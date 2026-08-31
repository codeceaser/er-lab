"""Stage 7C.1 post-adjudication CLOSURE runner.

Separate from `scripts/run_stage7c1_wiki_compiler.py` on purpose: that script is
contractually the runner *to the owner-adjudication checkpoint only* and keeps
that boundary. This one starts where it stops.

    frozen Runs 1/2/3 + owner verdict set
      -> preflight (fail closed)
      -> SS4.6 pass 3
      -> final facet payloads
      -> final facet embeddings
      -> expected-fact recall
      -> final Gate Q
      -> tracked closure artifacts

**ZERO compiler/LLM calls.** No facet compiler is imported or constructed here;
the only model used is the existing embedding provider, and only after pass 3.

Never writes to: the frozen Runs 1/2/3, `reports/stage7c1_compilation_runs.json`,
the frozen owner-adjudication packet, the frozen Stage 7C.0 projection, or
`docs/STAGE7C_WIKI_PLAN.md`.

Usage (from the repository root, venv active):
    python scripts/close_stage7c1_after_adjudication.py           # real embeddings
    python scripts/close_stage7c1_after_adjudication.py --fake    # deterministic fake
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "fixtures"))

from ingestion_bench.cross_document_benchmark.benchmark_runner import (  # noqa: E402
    build_evidence_alignment,
    load_contract,
)
from ingestion_bench.cross_document_benchmark.fixtures import load_all_revision_fixtures  # noqa: E402
from ingestion_bench.retrieval_baseline.embeddings import (  # noqa: E402
    FakeEmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
)
from ingestion_bench.wiki_projection import config  # noqa: E402
from ingestion_bench.wiki_projection.assembly import compose_payload_preview  # noqa: E402
from ingestion_bench.wiki_projection.benchmark import (  # noqa: E402
    PRIMARY_RUN_ID,
    facet_key,
    load_frozen_runs,
)
from ingestion_bench.wiki_projection.closure import (  # noqa: E402
    ClosurePreflightError,
    Stage7C1ClosureResult,
    build_final_embeddings,
    compute_expected_fact_recall,
    evaluate_final_gate_q,
    run_preflight,
)
from ingestion_bench.wiki_projection.projection import build_projection  # noqa: E402
from ingestion_bench.wiki_projection.validation import AdjudicationVerdictSet, apply_pass3  # noqa: E402

# Frozen identities this closure is contractually bound to.
FROZEN_PROJECTION_HASH = "4162fa515cf29d09391c0d963b76c7e63b1d454c4439ee0568805d1a31e3b613"
FROZEN_PACKET_SHA256 = "5d08b88dc9473a07ff94ddaead911a1a2aa54aba384afeec0f85b9a97ccb2065"
EXPECTED_VERDICT_SET_SHA256 = "d49cc8643388f830ffbcf5097faa8335a40c366b06b8f54a176aa978b06158bd"

REPORTS = config.REPORTS_ROOT
Q5_DECISION_PATH = REPORTS / "stage7c_q5_owner_decision.json"
VERDICT_SET_PATH = REPORTS / "stage7c1_adjudication_verdict_set.json"
FROZEN_RUNS_PATH = REPORTS / "stage7c1_compilation_runs.json"
FROZEN_PACKET_PATH = REPORTS / "stage7c1_owner_adjudication_packet.json"


def main() -> None:
    use_fake = "--fake" in sys.argv
    suffix = "_FAKE_EMBEDDINGS" if use_fake else ""

    # --- frozen inputs, all read-only ------------------------------------
    contract = load_contract(config.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH)
    fixtures = load_all_revision_fixtures(contract["fixtures"])
    projection = build_projection(fixtures)

    pages_by_key = {p.page_key: p for p in projection.page_identities}
    sections_by_chunk = {s.chunk_id: s for s in projection.sections}
    facets_by_key = {facet_key(f.page_key, f.document_revision_id): f for f in projection.facets}
    postings_by_chunk: dict[str, list] = {}
    for posting in projection.postings:
        postings_by_chunk.setdefault(posting.chunk_id, []).append(posting)

    runs = load_frozen_runs(FROZEN_RUNS_PATH, pages_by_key=pages_by_key)
    verdicts = AdjudicationVerdictSet.model_validate_json(VERDICT_SET_PATH.read_text(encoding="utf-8"))
    q5_decision = json.loads(Q5_DECISION_PATH.read_text(encoding="utf-8"))
    packet_sha = json.loads(FROZEN_PACKET_PATH.read_text(encoding="utf-8"))["packet_sha256"]

    print("Stage 7C.1 POST-ADJUDICATION CLOSURE")
    print(f"  frozen projection : {projection.projection_hash[:16]}...")
    print(f"  frozen packet SHA : {packet_sha[:16]}...")
    print(f"  verdict set       : {len(verdicts.verdicts)} verdicts")
    print(f"  Q5 decision       : {q5_decision['decision_id']} = {q5_decision['decision']}")
    print("  compiler calls    : 0 (none reachable from this runner)")
    print()

    # --- preflight: fail closed -------------------------------------------
    try:
        preflight = run_preflight(
            projection=projection, runs=runs, verdicts=verdicts,
            expected_projection_hash=FROZEN_PROJECTION_HASH,
            expected_verdict_set_sha256=EXPECTED_VERDICT_SET_SHA256,
            expected_packet_sha256=FROZEN_PACKET_SHA256, packet_sha256=packet_sha,
        )
    except ClosurePreflightError as exc:
        print("STOP -- preflight failed. No pass 3 was run and no embedding was created.\n")
        print(str(exc))
        sys.exit(2)

    print(f"Preflight PASSED: {preflight.supplied_item_count} verdicts "
          f"{preflight.verdict_distribution}, SHA {preflight.verdict_set_sha256[:16]}...")

    # --- SS4.6 pass 3, over Run 1 only ------------------------------------
    run_1 = runs.validations_by_run[str(PRIMARY_RUN_ID)]
    membership_before = {(f.page_key, f.document_revision_id): f.membership_hash for f in projection.facets}

    pass3_by_facet = {
        key: apply_pass3(
            validation, page=pages_by_key[validation.page_key], sections_by_chunk=sections_by_chunk,
            all_page_keys=set(pages_by_key), verdicts=verdicts,
        )
        for key, validation in sorted(run_1.items())
    }

    before: dict[str, int] = {}
    after: dict[str, int] = {}
    for result in pass3_by_facet.values():
        for field, value in result.counts_before.items():
            before[field] = before.get(field, 0) + value
        for field, value in result.counts_after.items():
            after[field] = after.get(field, 0) + value

    print(f"Pass 3 over {len(pass3_by_facet)} facets:")
    for field in sorted(before):
        print(f"    {field:38} {before[field]:3} -> {after[field]:3}")

    # --- final payloads, via the ONE frozen composition path ---------------
    final_payloads = {
        key: compose_payload_preview(
            run_1[key], facet=facets_by_key[key], page=pages_by_key[run_1[key].page_key],
            sections_by_chunk=sections_by_chunk, postings_by_chunk=postings_by_chunk,
            pass3=pass3_by_facet[key], verdict_set_sha256=EXPECTED_VERDICT_SET_SHA256,
        )
        for key in sorted(pass3_by_facet)
    }
    assert all(p.is_final for p in final_payloads.values())
    assert all(not p.pending_components for p in final_payloads.values())

    final_links = sorted(
        (link for result in pass3_by_facet.values() for link in result.derived_links),
        key=lambda link: link.link_id,
    )
    print(f"Final payloads: {len(final_payloads)} | final claim-derived links: {len(final_links)}")

    # --- final facet embeddings (permitted only now) -----------------------
    provider = FakeEmbeddingProvider() if use_fake else SentenceTransformerEmbeddingProvider()
    primary = next(p for p in runs.run_provenance if p.run_id == PRIMARY_RUN_ID)
    embeddings = build_final_embeddings(
        payloads=final_payloads, projection=projection, embedding_provider=provider,
        verdict_set_sha256=EXPECTED_VERDICT_SET_SHA256,
        compiler_model_identity=primary.model_identity,
        prompt_version=primary.prompt_version, prompt_sha256_value=primary.prompt_sha256,
    )
    print(f"Final facet embeddings: {len(embeddings)} ({provider.model_identity}, "
          f"dim={embeddings[0].embedding_dimension})")

    # --- membership must be untouched by all of the above ------------------
    membership_after = {(f.page_key, f.document_revision_id): f.membership_hash for f in projection.facets}
    assert membership_before == membership_after, "closure altered deterministic membership"

    # --- expected-fact recall, computed only now ---------------------------
    evidence = build_evidence_alignment(contract, fixtures)
    surviving_claims = {
        key: [c for c in run_1[key].claims if c.claim_id in set(pass3_by_facet[key].surviving_accepted_claim_ids)]
        for key in sorted(pass3_by_facet)
    }
    recall = compute_expected_fact_recall(
        surviving_claims_by_facet=surviving_claims, contract_facts=contract["facts"], evidence_by_fact=evidence,
    )
    print(f"Expected-fact recall: {recall.numerator}/{recall.denominator} = {recall.recall:.4f}")

    # --- final Gate Q ------------------------------------------------------
    gate_q = evaluate_final_gate_q(
        run_1=run_1, pass3_by_facet=pass3_by_facet, verdicts=verdicts,
        repeatability=runs.repeatability, recall=recall, q5_decision=q5_decision,
        verdict_set_sha256=EXPECTED_VERDICT_SET_SHA256, projection_hash=projection.projection_hash,
    )
    print()
    for criterion in gate_q.criteria:
        print(f"  {criterion.criterion:5} {criterion.status:4} {criterion.description}")
    print(f"\nGATE Q = {gate_q.overall_status}  (failing: {', '.join(gate_q.failing_criteria) or 'none'})")

    result = Stage7C1ClosureResult(
        generated_at=datetime.now(timezone.utc).isoformat(), preflight=preflight,
        pass3_by_facet=pass3_by_facet, aggregate_counts_before=before, aggregate_counts_after=after,
        withdrawn_claim_item_ids=sorted(
            f"{key}::{cid}" for key, r in pass3_by_facet.items() for cid in r.withdrawn_claim_ids
        ),
        withdrawn_summary_item_ids=sorted(
            f"{key}::{sid}" for key, r in pass3_by_facet.items() for sid in r.withdrawn_summary_ids
        ),
        withdrawn_alias_item_ids=sorted(
            f"{key}::{aid}" for key, r in pass3_by_facet.items() for aid in r.withdrawn_alias_ids
        ),
        final_payloads=final_payloads, final_derived_links=final_links, embeddings=embeddings,
        recall=recall, gate_q=gate_q,
    )
    result.closure_sha256 = result.semantic_hash()

    # --- tracked artifacts -------------------------------------------------
    REPORTS.mkdir(parents=True, exist_ok=True)
    _write(REPORTS / f"stage7c1_pass3_results{suffix}.json", {
        "projection_hash": projection.projection_hash,
        "verdict_set_sha256": EXPECTED_VERDICT_SET_SHA256,
        "aggregate_counts_before": before, "aggregate_counts_after": after,
        "withdrawn_claims": result.withdrawn_claim_item_ids,
        "withdrawn_summaries": result.withdrawn_summary_item_ids,
        "withdrawn_aliases": result.withdrawn_alias_item_ids,
        "per_facet": {k: json.loads(v.model_dump_json()) for k, v in sorted(pass3_by_facet.items())},
    })
    _write(REPORTS / f"stage7c1_final_payloads{suffix}.json", {
        "projection_hash": projection.projection_hash,
        "verdict_set_sha256": EXPECTED_VERDICT_SET_SHA256,
        "facet_count": len(final_payloads),
        "payloads": {k: json.loads(v.model_dump_json()) for k, v in sorted(final_payloads.items())},
        "final_derived_links": [json.loads(link.model_dump_json()) for link in final_links],
    })
    # The manifest omits raw vectors (they live with the records); it carries the
    # provenance that binds each vector to its payload and verdict set.
    _write(REPORTS / f"stage7c1_final_embedding_manifest{suffix}.json", {
        "embedding_model": provider.model_identity,
        "embedding_count": len(embeddings),
        "projection_hash": projection.projection_hash,
        "verdict_set_sha256": EXPECTED_VERDICT_SET_SHA256,
        "records": [
            {k: v for k, v in json.loads(record.model_dump_json()).items() if k != "embedding"}
            for record in embeddings
        ],
    })
    _write(REPORTS / f"stage7c1_gate_q_final{suffix}.json", json.loads(gate_q.model_dump_json()))
    _write(REPORTS / f"stage7c1_expected_fact_recall{suffix}.json", json.loads(recall.model_dump_json()))

    artifacts_dir = REPO_ROOT / "artifacts" / "stage7c1_closure"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / f"facet_embeddings{suffix}.json").write_text(
        json.dumps([json.loads(r.model_dump_json()) for r in embeddings], indent=2), encoding="utf-8"
    )

    print(f"\nClosure semantic hash: {result.closure_sha256}")
    print(f"Artifacts written under {REPORTS} and {artifacts_dir}")
    print("\nStage 7C.2 NOT started: no D0, no W1-D, no W1-FULL, no retrieval question run.")


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
