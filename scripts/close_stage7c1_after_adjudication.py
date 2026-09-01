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
    EMBEDDING_HASH_SERIALIZATION,
    ClosurePreflightError,
    FacetEmbeddingRecord,
    Stage7C1ClosureResult,
    build_final_embeddings,
    compute_expected_fact_recall,
    embedding_set_sha256,
    embedding_sha256,
    evaluate_final_gate_q,
    run_preflight,
)
from ingestion_bench.wiki_projection.facet_store import (  # noqa: E402
    CompilationAuditRow,
    FacetEmbeddingRow,
    FacetRecord,
    InMemoryStage7C1Store,
)
from ingestion_bench.wiki_projection.report import build_compiler_contract  # noqa: E402
from ingestion_bench.wiki_projection.projection import build_projection  # noqa: E402
from ingestion_bench.wiki_projection.validation import AdjudicationVerdictSet, apply_pass3  # noqa: E402

# Frozen identities this closure is contractually bound to.
FROZEN_PROJECTION_HASH = "4162fa515cf29d09391c0d963b76c7e63b1d454c4439ee0568805d1a31e3b613"
FROZEN_PACKET_SHA256 = "5d08b88dc9473a07ff94ddaead911a1a2aa54aba384afeec0f85b9a97ccb2065"
EXPECTED_VERDICT_SET_SHA256 = "d49cc8643388f830ffbcf5097faa8335a40c366b06b8f54a176aa978b06158bd"
DECLARED_DOLLAR_CAP_USD = 5.0
M_MAX = 3
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# The exact vectors produced by the d67ebfe closure. Reused rather than
# regenerated: a regenerated set would be a DIFFERENT frozen representation even
# if numerically close, and calling it the same one would be false.
FROZEN_VECTORS_PATH = REPO_ROOT / "artifacts" / "stage7c1_closure" / "facet_embeddings.json"

REPORTS = config.REPORTS_ROOT
Q5_DECISION_PATH = REPORTS / "stage7c_q5_owner_decision.json"
VERDICT_SET_PATH = REPORTS / "stage7c1_adjudication_verdict_set.json"
FROZEN_RUNS_PATH = REPORTS / "stage7c1_compilation_runs.json"
FROZEN_PACKET_PATH = REPORTS / "stage7c1_owner_adjudication_packet.json"



def _load_frozen_vectors(final_payloads) -> tuple[list, str]:
    """Reuse the EXACT vectors produced by the d67ebfe closure.

    Every vector is verified against the payload it must belong to before it is
    accepted. If the artifact is absent the closure STOPS rather than silently
    regenerating: a replacement set would be a DIFFERENT frozen representation,
    and presenting it as the same one would be false.
    """
    if not FROZEN_VECTORS_PATH.exists():
        print(f"STOP -- the exact frozen vector set is unavailable at {FROZEN_VECTORS_PATH}.")
        print()
        print("Not regenerating. A replacement embedding set would be a DIFFERENT frozen Stage 7C.1")
        print("representation, and calling it the same one would be false. Restore the artifact, or")
        print("explicitly authorise generating and re-freezing a new embedding set.")
        sys.exit(2)

    raw = json.loads(FROZEN_VECTORS_PATH.read_text(encoding="utf-8"))
    records: list[FacetEmbeddingRecord] = []
    problems: list[str] = []
    for entry in raw:
        key = f"{entry['page_key']}|{entry['document_revision_id']}"
        payload = final_payloads.get(key)
        if payload is None:
            problems.append(f"{key}: no matching final payload")
            continue
        checks = {
            "payload_text": entry["payload_text"] == payload.preview_text,
            "payload_sha256": entry["payload_sha256"] == payload.preview_sha256,
            "recomputed_sha": hashlib.sha256(entry["payload_text"].encode("utf-8")).hexdigest()
            == payload.preview_sha256,
            "verdict_set_sha256": entry["verdict_set_sha256"] == EXPECTED_VERDICT_SET_SHA256,
            "projection_hash": entry["projection_hash"] == FROZEN_PROJECTION_HASH,
            "embedding_model": entry["embedding_model"] == EMBEDDING_MODEL,
        }
        if not all(checks.values()):
            problems.append(f"{key}: {[k for k, v in checks.items() if not v]}")
            continue
        records.append(
            FacetEmbeddingRecord(**{**entry, "embedding_sha256": embedding_sha256(entry["embedding"])})
        )

    if problems or len(records) != len(final_payloads):
        print("STOP -- the stored vector set does not verify against the final payloads:")
        for problem in problems[:10]:
            print(f"  - {problem}")
        if len(records) != len(final_payloads):
            print(f"  - verified {len(records)} of {len(final_payloads)} payloads")
        sys.exit(2)
    return records, f"reused the exact d67ebfe vectors, all {len(records)} verified"


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
    compiler_contract = build_compiler_contract(
        projection_hash=projection.projection_hash, m_max=M_MAX,
        verdict_set_sha256=EXPECTED_VERDICT_SET_SHA256,
        declared_dollar_cap_usd=DECLARED_DOLLAR_CAP_USD, embedding_model=EMBEDDING_MODEL,
        q5_decision=q5_decision,
    )
    committed_contract_path = config.CONTRACTS_ROOT / "wiki_compiler_v1.json"
    expected_contract_sha = (
        json.loads(committed_contract_path.read_text(encoding="utf-8")).get("contract_sha256")
        if committed_contract_path.exists()
        else None
    )

    try:
        preflight = run_preflight(
            projection=projection, runs=runs, verdicts=verdicts,
            expected_projection_hash=FROZEN_PROJECTION_HASH,
            expected_verdict_set_sha256=EXPECTED_VERDICT_SET_SHA256,
            expected_packet_sha256=FROZEN_PACKET_SHA256, packet_sha256=packet_sha,
            q5_decision=q5_decision, compiler_contract=compiler_contract,
            expected_compiler_contract_sha256=expected_contract_sha,
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
    primary = next(p for p in runs.run_provenance if p.run_id == PRIMARY_RUN_ID)
    if use_fake:
        embeddings = build_final_embeddings(
            payloads=final_payloads, projection=projection, embedding_provider=FakeEmbeddingProvider(),
            verdict_set_sha256=EXPECTED_VERDICT_SET_SHA256,
            compiler_model_identity=primary.model_identity,
            prompt_version=primary.prompt_version, prompt_sha256_value=primary.prompt_sha256,
        )
        source_note = "fake provider (diagnostic only)"
    else:
        embeddings, source_note = _load_frozen_vectors(final_payloads)
    print(f"Final facet embeddings: {len(embeddings)} ({embeddings[0].embedding_model}, "
          f"dim={embeddings[0].embedding_dimension}) -- {source_note}")
    set_sha = embedding_set_sha256(embeddings)
    print(f"Embedding set SHA-256: {set_sha}")

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
        declared_dollar_cap_usd=DECLARED_DOLLAR_CAP_USD,
        total_estimated_cost_usd=runs.total_estimated_cost_usd,
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

    # --- Stage 7C.1 persistence (SS10.3): facet / facet_embedding / audit ---
    # In-memory reference store by default; the Postgres implementation shares
    # the same protocol. No authority state is stored in any of the three.
    store = InMemoryStage7C1Store()
    facet_rows = []
    embedding_rows = []
    audit_rows = []
    embedding_by_key = {f"{e.page_key}|{e.document_revision_id}": e for e in embeddings}
    for key in sorted(pass3_by_facet):
        validation, result_3, payload = run_1[key], pass3_by_facet[key], final_payloads[key]
        facet = facets_by_key[key]
        surviving_ids = set(result_3.surviving_accepted_claim_ids)
        compiled = {
            "surviving_accepted_claims": [
                json.loads(c.model_dump_json()) for c in validation.claims if c.claim_id in surviving_ids
            ],
            "payload_eligible_aliases": result_3.payload_eligible_alias_texts,
            "surviving_summary_sentence_ids": result_3.surviving_summary_sentence_ids,
            "final_derived_links": [json.loads(link.model_dump_json()) for link in result_3.derived_links],
            "final_payload_sha256": payload.preview_sha256,
            "verdict_set_sha256": EXPECTED_VERDICT_SET_SHA256,
        }
        facet_rows.append(
            FacetRecord(
                page_key=validation.page_key, document_revision_id=validation.document_revision_id,
                validation_state="final_post_pass3", facet_membership_hash=facet.membership_hash,
                facet_hash=payload.preview_sha256, run_id=PRIMARY_RUN_ID, compiled=compiled,
            )
        )
        record = embedding_by_key[key]
        embedding_rows.append(
            FacetEmbeddingRow(
                page_key=record.page_key, document_revision_id=record.document_revision_id,
                embedding=record.embedding, embedding_dimension=record.embedding_dimension,
                embedding_sha256=record.embedding_sha256, payload_sha256=record.payload_sha256,
                payload_text=record.payload_text, component_manifest=record.component_manifest,
                verdict_set_sha256=record.verdict_set_sha256, projection_hash=record.projection_hash,
                embedding_model=record.embedding_model,
                compiler_model_identity=record.compiler_model_identity,
                prompt_version=record.prompt_version, prompt_sha256=record.prompt_sha256,
                run_id=record.repeatability_run_id, source_chunk_ids=record.source_chunk_ids,
            )
        )
        audit_rows.append(
            CompilationAuditRow(
                page_key=validation.page_key, document_revision_id=validation.document_revision_id,
                run_id=PRIMARY_RUN_ID,
                rejected_claims=[
                    json.loads(c.model_dump_json()) for c in validation.claims
                    if c.validation_status == "rejected"
                ],
                out_of_page_scope_claims=[
                    json.loads(c.model_dump_json()) for c in validation.claims
                    if c.validation_status == "out_of_page_scope"
                ],
                uncertain_claims=[
                    json.loads(c.model_dump_json()) for c in validation.claims
                    if c.validation_status == "uncertain"
                ],
                unlinkable_claim_endpoints=validation.unlinkable_claim_endpoints,
                unresolved_identity_mentions=validation.unresolved_identity_mentions,
                adjudication_verdicts={
                    item: verdict for item, verdict in verdicts.verdicts.items() if f"::{key}::" in item
                },
                adjudication_reasons={
                    item: reason for item, reason in verdicts.reasons.items() if f"::{key}::" in item
                },
                withdrawn_claim_ids=result_3.withdrawn_claim_ids,
                withdrawn_summary_ids=result_3.withdrawn_summary_ids,
                withdrawn_alias_ids=result_3.withdrawn_alias_ids,
                demoted_to_out_of_page_scope=result_3.demoted_to_out_of_page_scope,
                payload_truncated_components=payload.payload_truncated_components,
                summary_payload_dedup_count=payload.summary_payload_dedup_count,
                input_tokens=validation.input_tokens, output_tokens=validation.output_tokens,
                estimated_cost_usd=validation.estimated_cost_usd,
                latency_seconds=validation.latency_seconds, model_identity=validation.model_identity,
                prompt_version=validation.prompt_version, prompt_sha256=validation.prompt_sha256,
                ceiling_breaches=validation.ceiling_breaches,
                generation_failed=validation.generation_failed, generation_error=validation.generation_error,
            )
        )
    store.upsert_facets(facet_rows)
    store.upsert_facet_embeddings(embedding_rows)
    store.upsert_compilation_audit(audit_rows)
    print(f"Persisted: facet={store.facet_count()} facet_embedding={store.facet_embedding_count()} "
          f"compilation_audit={store.compilation_audit_count()}")

    # --- tracked artifacts -------------------------------------------------
    REPORTS.mkdir(parents=True, exist_ok=True)
    if not use_fake:
        config.CONTRACTS_ROOT.mkdir(parents=True, exist_ok=True)
        (config.CONTRACTS_ROOT / "wiki_compiler_v1.json").write_text(
            json.dumps(compiler_contract, indent=2), encoding="utf-8"
        )
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
        "embedding_model": embeddings[0].embedding_model,
        "embedding_count": len(embeddings),
        "projection_hash": projection.projection_hash,
        "verdict_set_sha256": EXPECTED_VERDICT_SET_SHA256,
        # Identifies the exact VECTOR SET without carrying the raw vectors, so
        # the frozen record is complete even though the values live in the
        # Stage 7C.1 store.
        "embedding_set_sha256": set_sha,
        "embedding_hash_serialization": EMBEDDING_HASH_SERIALIZATION,
        "vector_source": source_note,
        "compiler_contract_sha256": compiler_contract["contract_sha256"],
        "persisted_row_counts": {
            "facet": store.facet_count(),
            "facet_embedding": store.facet_embedding_count(),
            "compilation_audit": store.compilation_audit_count(),
        },
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

    _write(REPORTS / f"stage7c1_persistence_manifest{suffix}.json", {
        "tables": ["edib_stage7c_facet", "edib_stage7c_facet_embedding", "edib_stage7c_compilation_audit"],
        "row_counts": {
            "facet": store.facet_count(),
            "facet_embedding": store.facet_embedding_count(),
            "compilation_audit": store.compilation_audit_count(),
        },
        "authority_state_stored": False,
        "authority_read_pattern":
            "document_revision_id = ANY(:eligible) in the SAME statement as ORDER BY / LIMIT",
        "stage_7c2_retrieval_implemented": False,
        "facets": [json.loads(r.model_dump_json()) for r in facet_rows],
        "compilation_audit": [json.loads(r.model_dump_json()) for r in audit_rows],
    })

    print(f"\nClosure semantic hash: {result.closure_sha256}")
    print(f"Artifacts written under {REPORTS} and {artifacts_dir}")
    print("\nStage 7C.2 NOT started: no D0, no W1-D, no W1-FULL, no retrieval question run.")


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
