"""Stage 7C.0 runner: builds the deterministic Wiki projection (W0) over the
frozen Stage 7B.0 corpus, runs the W0 semantic CONTROL against V with the
frozen Stage 7B.0 evaluator, freezes the projection contract (including the
measured M_max, the sentence splitter, and the D0 seed / prioritizer
contracts), and writes the manifest, ledger, scorecard and rendered pages.

ZERO LLM calls. No W1 compilation, no facet embedding, and NO measured
D0 / W1-D / W1-FULL comparison -- those belong to Stage 7C.1 / 7C.2.

Usage (from the repository root, venv active):
    python scripts/run_stage7c0_wiki_projection.py            # real embeddings
    python scripts/run_stage7c0_wiki_projection.py --fake     # fake embeddings
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "fixtures"))

from ingestion_bench.cross_document_benchmark.store import InMemoryCrossDocumentVectorStore  # noqa: E402
from ingestion_bench.retrieval_baseline.embeddings import (  # noqa: E402
    FakeEmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
)
from ingestion_bench.revision_authority.repository import InMemoryRevisionAuthorityRepository  # noqa: E402
from ingestion_bench.wiki_projection import config  # noqa: E402
from ingestion_bench.wiki_projection.benchmark import run_stage7c0  # noqa: E402
from ingestion_bench.wiki_projection.rendering import render_page, render_revision_page  # noqa: E402
from ingestion_bench.wiki_projection.report import (  # noqa: E402
    build_cost_ledger,
    build_projection_contract,
    build_projection_manifest,
    render_scorecard_markdown,
)
from ingestion_bench.wiki_projection.store import InMemoryWikiProjectionStore  # noqa: E402

WIKI_PACKAGE = REPO_ROOT / "src" / "ingestion_bench" / "wiki_projection"

# Representative identities for owner review (Revision 6 / owner SS11).
REPRESENTATIVE_PAGES = [
    "IDENT:APP-224510", "PHRASE:payment settlement", "IDENT:O-31", "IDENT:C-88", "IDENT:C-88A", "IDENT:P-205",
]


def _loc_by_file() -> dict[str, int]:
    out: dict[str, int] = {}
    for path in sorted(WIKI_PACKAGE.glob("*.py")):
        out[str(path.relative_to(REPO_ROOT)).replace("\\", "/")] = len(path.read_text(encoding="utf-8").splitlines())
    script = Path(__file__)
    out[str(script.relative_to(REPO_ROOT)).replace("\\", "/")] = len(script.read_text(encoding="utf-8").splitlines())
    return out


def main() -> None:
    use_fake = "--fake" in sys.argv
    provider = FakeEmbeddingProvider() if use_fake else SentenceTransformerEmbeddingProvider()

    print(f"Embedding provider: {provider.model_identity}{' (FAKE)' if use_fake else ''}")
    print("LLM calls: 0 (Stage 7C.0 is deterministic by contract)")

    result = run_stage7c0(
        config.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH,
        InMemoryRevisionAuthorityRepository(),
        provider,
        InMemoryCrossDocumentVectorStore(),
    )
    projection = result.projection

    # Exercise the projection store round-trip (in-memory reference impl).
    store = InMemoryWikiProjectionStore()
    store.upsert_anchors(projection.anchors)
    store.upsert_postings(projection.postings)

    manifest = build_projection_manifest(result)
    contract = build_projection_contract(projection)
    ledger = build_cost_ledger(
        result,
        module_files=sorted(str(p.relative_to(REPO_ROOT)).replace("\\", "/") for p in WIKI_PACKAGE.glob("*.py")),
        loc_by_file=_loc_by_file(),
    )

    config.ARTIFACTS_ROOT.mkdir(parents=True, exist_ok=True)
    pages_dir = config.ARTIFACTS_ROOT / "rendered_pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    (config.ARTIFACTS_ROOT / "projection_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (config.ARTIFACTS_ROOT / "projection.json").write_text(projection.model_dump_json(indent=2), encoding="utf-8")
    (config.ARTIFACTS_ROOT / "build_cost_ledger.json").write_text(json.dumps(ledger, indent=2), encoding="utf-8")

    # FREEZE the projection contract.
    config.WIKI_PROJECTION_CONTRACT_PATH.write_text(json.dumps(contract, indent=2), encoding="utf-8")

    # Rendered owner-facing pages, under the CURRENT-intent eligible scope.
    current_eligible = sorted(
        {
            f.document_revision_id
            for f in projection.facets
            if result.revision_symbol_by_id.get(f.document_revision_id)
            in {"app_rev2", "svc_rev1", "obl_rev2", "ctl_rev2", "prc_rev2", "adj_rev1"}
        }
    )
    all_revisions = sorted({p.document_revision_id for p in projection.revision_pages})

    rendered: list[str] = []
    for page_key in REPRESENTATIVE_PAGES:
        if not any(p.page_key == page_key for p in projection.page_identities):
            print(f"  (page {page_key} not created by the deterministic projection -- skipped)")
            continue
        safe = page_key.replace(":", "__").replace(" ", "_")
        for label, scope in (("current_scope", current_eligible), ("all_revisions", all_revisions)):
            path = pages_dir / f"{safe}.{label}.md"
            path.write_text(
                render_page(projection, page_key, eligible_revision_ids=scope,
                            revision_symbol_by_id=result.revision_symbol_by_id),
                encoding="utf-8",
            )
            rendered.append(str(path.relative_to(REPO_ROOT)).replace("\\", "/"))

    for revision_page in projection.revision_pages:
        symbol = result.revision_symbol_by_id.get(revision_page.document_revision_id, revision_page.document_revision_id[:12])
        path = pages_dir / f"revision__{symbol}.md"
        path.write_text(
            render_revision_page(projection, revision_page.document_revision_id, eligible_revision_ids=current_eligible),
            encoding="utf-8",
        )
        rendered.append(str(path.relative_to(REPO_ROOT)).replace("\\", "/"))

    config.REPORTS_ROOT.mkdir(parents=True, exist_ok=True)

    # `artifacts/` is gitignored and regenerable (plan SS10.2), so the
    # representative pages are ALSO collected into one tracked report file, so
    # owner review needs no rerun.
    sample: list[str] = [
        "# Stage 7C.0 — representative rendered W0 pages",
        "",
        "Deterministic output of `scripts/run_stage7c0_wiki_projection.py`. Rendered under the "
        "**current-intent** authority scope, so historical and draft revisions are correctly hidden.",
        "",
        "Zero LLM calls: every page's model-derived block is empty by construction.",
        "",
        "---",
        "",
    ]
    for page_key in REPRESENTATIVE_PAGES:
        if not any(p.page_key == page_key for p in projection.page_identities):
            continue
        sample.append(
            render_page(projection, page_key, eligible_revision_ids=current_eligible,
                        revision_symbol_by_id=result.revision_symbol_by_id)
        )
        sample.append("\n---\n")
    (config.REPORTS_ROOT / "stage7c0_wiki_projection_sample_pages.md").write_text(
        "\n".join(sample), encoding="utf-8"
    )

    (config.REPORTS_ROOT / "stage7c0_wiki_projection_results.json").write_text(
        json.dumps(
            {
                "contract_version": result.contract_version, "generated_at": result.generated_at,
                "corpus_id": result.corpus_id, "manifest": manifest, "cost_ledger": ledger,
                "w0_control": json.loads(result.w0_control.model_dump_json()),
                "rendered_pages": rendered,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (config.REPORTS_ROOT / "stage7c0_wiki_projection_scorecard.md").write_text(
        render_scorecard_markdown(result, manifest), encoding="utf-8"
    )

    counts = projection.counts
    print(f"\nProjection: {counts.section_count} sections, {counts.anchor_count} anchors "
          f"({counts.anchor_count_by_kind}), {counts.posting_count} postings")
    print(f"Page identities: {counts.page_identity_count} ({counts.page_identity_count_by_type})")
    print(f"Facets: {counts.facet_count}")
    print(f"Links: structural={counts.structural_link_count}, exact_anchor={counts.exact_anchor_link_count} "
          f"(advisory={counts.advisory_link_count})")
    print(f"M_max (measured): {counts.m_max}  argmax={counts.facets_per_page_max_page_keys}")
    print(f"Projection hash: {projection.projection_hash}")
    print(f"\nW0 control: identical to V on {result.w0_control.identical_to_v_count}/"
          f"{result.w0_control.questions_total} questions; W0 == V: {result.w0_control.w0_equals_v}")
    print(f"Authority leakage (V + W0): {result.w0_control.total_authority_leakage} (must be 0)")
    print(f"\nFrozen contract: {config.WIKI_PROJECTION_CONTRACT_PATH}")
    print(f"Scorecard: {config.REPORTS_ROOT / 'stage7c0_wiki_projection_scorecard.md'}")
    print(f"Artifacts: {config.ARTIFACTS_ROOT}")

    if result.w0_control.total_authority_leakage != 0:
        print("\nHARD-SAFETY FAILURE: authority leakage != 0")
        sys.exit(1)


if __name__ == "__main__":
    main()
