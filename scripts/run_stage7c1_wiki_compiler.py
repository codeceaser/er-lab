"""Stage 7C.1 runner -- to the OWNER-ADJUDICATION CHECKPOINT only.

Loads the frozen Stage 7C.0 projection read-only, runs the one frozen W1
compiler treatment over every facet three times, validates every run
mechanically, measures repeatability, and emits the Run-1 owner adjudication
packet plus pending-W1 page previews.

STOPS THERE. It does not self-adjudicate, does not apply verdicts, does not
build or freeze facet embeddings, does not declare Gate Q, and does not begin
Stage 7C.2.

Preflight (all BEFORE the first model call):
  1. the compiler model must equal the frozen Stage 7B.1 extraction model;
  2. the whole-run dollar ceiling must be RESOLVED -- Revision 6 leaves it open
     (Q6), and this script will not choose one.

Usage (from the repository root, venv active):
    # real compiler -- requires the owner's approved cap
    INGESTION_BENCH_STAGE7C1_DOLLAR_CAP=<usd> python scripts/run_stage7c1_wiki_compiler.py
    # or
    python scripts/run_stage7c1_wiki_compiler.py --dollar-cap <usd>

    # pipeline rehearsal with the deterministic non-LLM test double (0 calls)
    python scripts/run_stage7c1_wiki_compiler.py --fake
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "fixtures"))

from ingestion_bench.cross_document_benchmark.benchmark_runner import load_contract  # noqa: E402
from ingestion_bench.cross_document_benchmark.fixtures import load_all_revision_fixtures  # noqa: E402
from ingestion_bench.wiki_projection import config  # noqa: E402
from ingestion_bench.wiki_projection.adjudication import (  # noqa: E402
    build_adjudication_packet,
    render_packet_markdown,
)
from ingestion_bench.wiki_projection.assembly import compose_payload_preview, render_w1_page_preview  # noqa: E402
from ingestion_bench.wiki_projection.benchmark import (  # noqa: E402
    PRIMARY_RUN_ID,
    facet_key,
    run_stage7c1_compilation,
)
from ingestion_bench.wiki_projection.compiler import (  # noqa: E402
    COMPILER_MODEL,
    FakeFacetCompiler,
    OpenAIFacetCompiler,
    PROMPT_VERSION,
    UnresolvedBudgetError,
    prompt_sha256,
    resolve_run_dollar_ceiling,
    verify_model_parity,
)
from ingestion_bench.wiki_projection.projection import build_projection  # noqa: E402
from ingestion_bench.wiki_projection.report import (  # noqa: E402
    build_gate_q_pre_status,
    build_stage7c1_cost_ledger,
)

REPRESENTATIVE_PAGES = [
    "IDENT:APP-224510", "PHRASE:payment settlement", "IDENT:O-31", "IDENT:C-88", "IDENT:C-88A", "IDENT:P-205",
]


def _resolve_cap(argv: list[str]) -> float:
    if "--dollar-cap" in argv:
        return float(argv[argv.index("--dollar-cap") + 1])
    return resolve_run_dollar_ceiling()


def main() -> None:
    use_fake = "--fake" in sys.argv
    # Regenerate reports from already-executed runs: no model call, and no
    # chance of re-rolling the frozen Run 1 (SS8F forbids selecting a run).
    reuse_artifacts = "--from-artifacts" in sys.argv

    # --- PREFLIGHT 1: model parity (Revision 6 SS3.8) ---------------------
    if not use_fake and "--from-artifacts" not in sys.argv:
        verify_model_parity(COMPILER_MODEL)

    # --- PREFLIGHT 2: the whole-run dollar ceiling ------------------------
    try:
        dollar_cap = _resolve_cap(sys.argv)
    except UnresolvedBudgetError as exc:
        print("STOP -- required frozen configuration value is UNRESOLVED.\n")
        print(str(exc))
        print("\nNo model call has been made. Nothing has been written.")
        sys.exit(2)

    contract = load_contract(config.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH)
    fixtures = load_all_revision_fixtures(contract["fixtures"])
    projection = build_projection(fixtures)

    committed = json.loads(config.WIKI_PROJECTION_CONTRACT_PATH.read_text(encoding="utf-8"))
    if committed["projection_hash"] != projection.projection_hash:
        print(f"STOP -- the frozen Stage 7C.0 projection has changed.\n"
              f"  committed: {committed['projection_hash']}\n"
              f"  rebuilt:   {projection.projection_hash}")
        sys.exit(2)

    facet_compiler = FakeFacetCompiler() if use_fake else OpenAIFacetCompiler()
    if reuse_artifacts:
        facet_compiler = FakeFacetCompiler()  # never called; a placeholder for provenance printing

    # A rehearsal with the deterministic test double produces NO W1 content --
    # only proof that the pipeline runs. Writing it to the real packet path
    # would invite the owner to adjudicate fabricated items, so rehearsal output
    # is segregated and loudly named.
    suffix = "_REHEARSAL_DO_NOT_ADJUDICATE" if use_fake else ""
    artifacts = REPO_ROOT / "artifacts" / ("stage7c1_rehearsal" if use_fake else "stage7c1")

    print(f"Frozen projection: {projection.projection_hash[:16]}... "
          f"({len(projection.facets)} facets, {len(projection.page_identities)} pages)")
    print(f"Compiler: {facet_compiler.model_identity}{' (FAKE TEST DOUBLE -- 0 LLM calls)' if use_fake else ''}")
    print(f"Prompt: {PROMPT_VERSION} / {prompt_sha256()[:16]}...")
    print(f"Whole-run dollar cap: ${dollar_cap}")
    print(f"RUN {PRIMARY_RUN_ID} IS THE PRIMARY REPRESENTATION CANDIDATE (designated before execution)")
    print()

    if reuse_artifacts:
        # Regenerate reports from the ALREADY-EXECUTED runs. No model call, no
        # cost, and -- critically -- no possibility of re-rolling Run 1 and
        # picking a different one, which SS8F forbids.
        from ingestion_bench.wiki_projection.benchmark import Stage7C1Result

        stored = REPO_ROOT / "artifacts" / "stage7c1" / "stage7c1_runs.json"
        if not stored.exists():
            # Fall back to the tracked copy: `artifacts/` is gitignored, so a
            # fresh clone has only this one.
            stored = config.REPORTS_ROOT / "stage7c1_compilation_runs.json"
        if not stored.exists():
            print(f"STOP -- no stored runs found; nothing to regenerate.")
            sys.exit(2)
        result = Stage7C1Result.model_validate_json(stored.read_text(encoding="utf-8"))
        if result.projection_hash != projection.projection_hash:
            print("STOP -- stored runs were compiled against a different projection.")
            sys.exit(2)
        print(f"Reusing stored runs (0 model calls): {result.compiler_calls_total} recorded compilations")
    else:
        result = run_stage7c1_compilation(projection, facet_compiler, dollar_ceiling_usd=dollar_cap)

    # --- Run 1 ONLY feeds adjudication, previews and the payload preview ---
    run_1 = result.validations_by_run[str(PRIMARY_RUN_ID)]
    facets_by_key = {facet_key(f.page_key, f.document_revision_id): f for f in projection.facets}
    pages_by_key = {p.page_key: p for p in projection.page_identities}
    sections_by_chunk = {s.chunk_id: s for s in projection.sections}
    postings_by_chunk: dict[str, list] = {}
    for posting in projection.postings:
        postings_by_chunk.setdefault(posting.chunk_id, []).append(posting)

    symbol_by_revision = {
        fx.document_revision_id: symbol for symbol, fx in fixtures.items()
    }

    # Provenance is taken from the RUN THAT ACTUALLY EXECUTED, never from the
    # compiler object in hand: under --from-artifacts that object is a
    # placeholder, and reporting its identity would falsify the packet.
    primary_provenance = next(p for p in result.run_provenance if p.run_id == PRIMARY_RUN_ID)

    packet = build_adjudication_packet(
        run_id=PRIMARY_RUN_ID, validations=run_1, projection_hash=projection.projection_hash,
        facets_by_key=facets_by_key, pages_by_key=pages_by_key, sections_by_chunk=sections_by_chunk,
        revision_symbol_by_id=symbol_by_revision, model_identity=primary_provenance.model_identity,
        prompt_version=primary_provenance.prompt_version,
        prompt_sha256_value=primary_provenance.prompt_sha256,
    )

    payload_previews = {
        key: compose_payload_preview(
            validation, facet=facets_by_key[key], page=pages_by_key[validation.page_key],
            sections_by_chunk=sections_by_chunk, postings_by_chunk=postings_by_chunk,
        )
        for key, validation in run_1.items()
    }

    gate_q = build_gate_q_pre_status(result, packet)
    ledger = build_stage7c1_cost_ledger(result, packet)

    # --- persist ------------------------------------------------------------
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "compilation_audit").mkdir(parents=True, exist_ok=True)
    previews_dir = artifacts / "w1_page_previews"
    previews_dir.mkdir(parents=True, exist_ok=True)

    (artifacts / "stage7c1_runs.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
    # ALSO written to tracked reports/. `artifacts/` is gitignored as
    # "regenerable", but these runs are NOT: SS8F designates Run 1 the primary
    # representation before execution and forbids selecting a run, and the
    # measured run-to-run variance means re-running would produce a DIFFERENT
    # Run 1. Losing this file would destroy irreplaceable frozen evidence.
    if not use_fake:
        (config.REPORTS_ROOT / "stage7c1_compilation_runs.json").write_text(
            result.model_dump_json(indent=2), encoding="utf-8"
        )
    for run_id, validations in result.validations_by_run.items():
        (artifacts / "compilation_audit" / f"run_{run_id}.json").write_text(
            json.dumps({key: json.loads(v.model_dump_json()) for key, v in sorted(validations.items())}, indent=2),
            encoding="utf-8",
        )
    (artifacts / "payload_previews.json").write_text(
        json.dumps({k: json.loads(v.model_dump_json()) for k, v in sorted(payload_previews.items())}, indent=2),
        encoding="utf-8",
    )

    config.REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    packet_json = config.REPORTS_ROOT / f"stage7c1_owner_adjudication_packet{suffix}.json"
    packet_md = config.REPORTS_ROOT / f"stage7c1_owner_adjudication_packet{suffix}.md"
    packet_json.write_text(packet.model_dump_json(indent=2), encoding="utf-8")
    packet_md.write_text(render_packet_markdown(packet), encoding="utf-8")

    all_revisions = sorted({p.document_revision_id for p in projection.revision_pages})
    current = sorted(
        rid for rid, symbol in symbol_by_revision.items()
        if symbol in {"app_rev2", "svc_rev1", "obl_rev2", "ctl_rev2", "prc_rev2", "adj_rev1"}
    )
    preview_paths: list[str] = []
    combined = [
        "# Stage 7C.1 — representative W1 page PREVIEWS (pending owner adjudication)",
        "",
        "> Previews for owner comprehension and adjudication only. Not final W1 pages, not scored, and "
        "not a benchmark result. No facet embedding exists.",
        "",
        "---",
        "",
    ]
    for page_key in REPRESENTATIVE_PAGES:
        page = pages_by_key.get(page_key)
        if page is None:
            continue
        rendered = render_w1_page_preview(
            page, facets=projection.facets, validations=run_1, sections_by_chunk=sections_by_chunk,
            postings_by_chunk=postings_by_chunk, deterministic_links=projection.links,
            eligible_revision_ids=all_revisions, revision_symbol_by_id=symbol_by_revision,
            payload_previews=payload_previews,
        )
        path = previews_dir / f"{page_key.replace(':', '__').replace(' ', '_')}.md"
        path.write_text(rendered, encoding="utf-8")
        preview_paths.append(str(path.relative_to(REPO_ROOT)).replace("\\", "/"))
        combined.append(rendered)
        combined.append("\n---\n")
    (config.REPORTS_ROOT / f"stage7c1_w1_page_previews{suffix}.md").write_text("\n".join(combined), encoding="utf-8")

    (config.REPORTS_ROOT / f"stage7c1_checkpoint_results{suffix}.json").write_text(
        json.dumps(
            {
                "generated_at": result.generated_at,
                "projection_hash": result.projection_hash,
                "primary_run_id": result.primary_run_id,
                "gate_q_pre_status": gate_q,
                "cost_ledger": ledger,
                "repeatability": json.loads(result.repeatability.model_dump_json()),
                "run_provenance": [json.loads(p.model_dump_json()) for p in result.run_provenance],
                "adjudication_packet": {
                    "json": str(packet_json.relative_to(REPO_ROOT)).replace("\\", "/"),
                    "markdown": str(packet_md.relative_to(REPO_ROOT)).replace("\\", "/"),
                    "sha256": packet.packet_sha256,
                },
                "w1_page_previews": preview_paths,
                "facet_embeddings_created": 0,
                "stage_7c2_started": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # --- console summary ----------------------------------------------------
    counts = gate_q["run_1_counts"]
    print(f"Compiler calls: {result.compiler_calls_total} across runs "
          f"{[p.run_id for p in result.run_provenance]}")
    print(f"Membership unchanged by the compiler: {result.membership_unchanged}")
    print()
    print(f"Run 1: {counts['claims_total']} claims "
          f"(accepted={counts['claims_accepted']}, rejected={counts['claims_rejected']}, "
          f"uncertain={counts['claims_uncertain']}, out_of_page_scope={counts['claims_out_of_page_scope']})")
    print(f"       {counts['aliases_total']} aliases (supported={counts['aliases_supported']}), "
          f"{counts['summary_sentences_total']} summary sentences, "
          f"{counts['derived_links']} derived links")
    print(f"       facets with ZERO accepted claims: {counts['facets_with_zero_accepted_claims']} "
          f"(still fully navigable — membership is independent)")
    print()
    print(f"Repeatability claim Jaccard: {result.repeatability.claim_set_jaccard_pairwise}")
    print(f"Total estimated cost: {result.total_estimated_cost_usd} USD (cap ${dollar_cap})")
    print()
    print(f"GATE Q: {gate_q['gate_q_status']}")
    print(f"OWNER ADJUDICATION ITEMS: {packet.total_item_count} "
          f"(claims={packet.claim_item_count}, aliases={packet.alias_item_count}, "
          f"summaries={packet.summary_item_count})")
    print()
    print(f"Packet (JSON): {packet_json}")
    print(f"Packet (MD):   {packet_md}")
    print(f"Previews:      {config.REPORTS_ROOT / f'stage7c1_w1_page_previews{suffix}.md'}")
    print()
    print("STOPPED at the owner-adjudication checkpoint. No verdict applied, no embedding created, "
          "no Gate Q declared, Stage 7C.2 not started.")


if __name__ == "__main__":
    main()
