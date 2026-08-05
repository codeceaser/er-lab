"""Assemble Appendix A for the Devin rebuild prompt (Stage 7B.2a, section 8).

Builds `docs/DEVIN_REBUILD_APPENDICES.json` -- an EXACT, machine-readable
bundle copied verbatim from the authoritative contracts, plus the exact
per-fixture source text as the benchmark itself parses it (via the repo's
own fixture loader). Nothing here is hand-transcribed: re-run this script
to regenerate the appendices from source. It is a reproducibility
reference for a from-scratch rebuild, never acceptance criteria.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "fixtures"))

from ingestion_bench.graph_retrieval_benchmark.benchmark_runner import load_contract  # noqa: E402
from ingestion_bench.graph_retrieval_benchmark.builder import load_fixtures_and_verify  # noqa: E402

CONTRACTS = REPO_ROOT / "contracts"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _fixture_source_text(cross_contract: dict) -> dict[str, list[dict]]:
    """The EXACT ordered chunk text per revision symbol, as the benchmark
    parses the generated .docx -- so a rebuild can reproduce identical
    chunks/hashes with the same adapter/chunker configuration."""
    fixtures, _verify = load_fixtures_and_verify(cross_contract)
    out: dict[str, list[dict]] = {}
    for symbol, fx in fixtures.items():
        out[symbol] = [
            {
                "chunk_id": c.chunk_id,
                "chunk_type": getattr(c, "chunk_type", "text"),
                "heading_path": list(getattr(c, "heading_path", []) or []),
                "content_sha256": getattr(c, "content_sha256", None),
                "text": getattr(c, "retrieval_text", None) or getattr(c, "text", None) or getattr(c, "content", None),
            }
            for c in fx.chunks
        ]
    return out


def main() -> None:
    cross = _load(CONTRACTS / "cross_document_relationship_benchmark_v1.json")
    rev_auth = _load(CONTRACTS / "revision_authority_scenarios_v2.json")
    rev_search = _load(CONTRACTS / "revision_search_benchmark_v1.json")
    hybrid = _load(CONTRACTS / "hybrid_retrieval_probe_v1.json")

    appendices = {
        "appendix_id": "DEVIN_REBUILD_APPENDIX_A",
        "purpose": "Exact, machine-readable reproduction reference for a from-scratch rebuild (Stage 7B.2a). NOT acceptance criteria: build honestly, and if results diverge, investigate and report -- never change code/parameters merely to reproduce these.",
        "source_contract_versions": {
            "cross_document": cross["contract_version"],
            "revision_authority_scenarios": rev_auth["contract_version"],
            "revision_search_benchmark": rev_search["contract_version"],
            "hybrid_retrieval_probe": hybrid["contract_version"],
        },
        "source_contract_sha256": {
            "cross_document": _sha(cross),
            "revision_authority_scenarios": _sha(rev_auth),
            "revision_search_benchmark": _sha(rev_search),
            "hybrid_retrieval_probe": _sha(hybrid),
        },
        # A. corrected Stage 7B.2a algorithm contract + decision gates (verbatim)
        "A_hybrid_probe_contract_7b2a": hybrid,
        # B. logical document / revision identities
        "B_logical_documents": cross["logical_documents"],
        "B_fixtures_revision_identities": cross["fixtures"],
        # C. authority timelines and dates + revision-authority scenarios
        "C_authority_setup_timelines": cross["authority_setup"],
        "C_revision_authority_scenarios": rev_auth,
        # D. revision-search scenarios
        "D_revision_search_scenarios": rev_search,
        # E. the 15 cross-document facts (verbatim)
        "E_cross_document_facts": cross["facts"],
        # F. all 12 questions (intents, dates, required/forbidden facts, top-K)
        "F_questions": cross["questions"],
        # G. exact fixture source text (as parsed by the benchmark)
        "G_fixture_source_text": _fixture_source_text(cross),
    }

    out_path = REPO_ROOT / "docs" / "DEVIN_REBUILD_APPENDICES.json"
    out_path.write_text(json.dumps(appendices, indent=2, ensure_ascii=False), encoding="utf-8")
    n_facts = len(appendices["E_cross_document_facts"])
    n_q = len(appendices["F_questions"])
    n_fx = len(appendices["G_fixture_source_text"])
    print(f"Wrote {out_path.relative_to(REPO_ROOT)}: {n_facts} facts, {n_q} questions, {n_fx} fixtures, "
          f"{len(appendices['C_revision_authority_scenarios']['query_scenarios'])} authority scenarios, "
          f"{len(appendices['D_revision_search_scenarios']['queries'])} revision-search queries.")


if __name__ == "__main__":
    main()
