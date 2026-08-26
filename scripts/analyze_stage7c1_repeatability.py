"""READ-ONLY repeatability analysis over the frozen Stage 7C.1 Runs 1/2/3.

Reads `reports/stage7c1_compilation_runs.json` and rebuilds the frozen Stage
7C.0 projection (deterministic, zero LLM calls) purely to recover `source_text`
for display. It writes ONE new file --
`reports/stage7c1_repeatability_analysis.json` -- and modifies no frozen
artifact, reruns no compilation, and makes no model call.

Why this exists: Revision 6 SS8F states the repeatability quantity twice, and the
two statements differ.

  * the METRIC LIST says "claim-set stability (Jaccard over normalized
    (subject, predicate, object, sorted supporting_chunk_ids))" -- population
    unqualified, i.e. every claim the compiler emitted;
  * the THRESHOLD says "accepted-claim set pairwise Jaccard >= 0.90, citation
    sets on matched claims >= 0.95 exact".

`benchmark._normalized_claim_keys` implements the metric-list wording (all
claims); `benchmark._citation_keys` implements neither, computing a Jaccard over
quote-bearing tuples rather than exact agreement on matched claims. This script
computes every variant side by side so the difference is visible rather than
argued about. It does NOT change Gate Q, the thresholds, or any stored result.
"""

from __future__ import annotations

import json
import re
import sys
from itertools import combinations
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "fixtures"))

from ingestion_bench.cross_document_benchmark.benchmark_runner import load_contract  # noqa: E402
from ingestion_bench.cross_document_benchmark.fixtures import load_all_revision_fixtures  # noqa: E402
from ingestion_bench.wiki_projection import config  # noqa: E402
from ingestion_bench.wiki_projection.projection import build_projection  # noqa: E402
from ingestion_bench.wiki_projection.validation import (  # noqa: E402
    normalize_triple_part,
    normalize_whitespace,
)

RUN_IDS = ["1", "2", "3"]
FROZEN_RUNS_PATH = REPO_ROOT / "reports" / "stage7c1_compilation_runs.json"
OUTPUT_PATH = REPO_ROOT / "reports" / "stage7c1_repeatability_analysis.json"

# Determiners and generic enterprise type nouns, stripped ONLY to classify a
# difference as wording-vs-semantic. Never used to change any stored value.
_ARTICLES = ("the ", "a ", "an ")
_TYPE_PREFIX = ("application ", "control ", "obligation ", "procedure ")
_TYPE_SUFFIX = (" business service", " operating procedure", " service")
_PUNCT = re.compile(r"[^\w\s]")


def loose_entity(text: str) -> str:
    result = normalize_triple_part(text)
    changed = True
    while changed:
        changed = False
        for article in _ARTICLES:
            if result.startswith(article):
                result, changed = result[len(article):], True
        for prefix in _TYPE_PREFIX:
            if result.startswith(prefix) and len(result) > len(prefix):
                result, changed = result[len(prefix):], True
        for suffix in _TYPE_SUFFIX:
            if result.endswith(suffix) and len(result) > len(suffix):
                result, changed = result[: -len(suffix)], True
    return result.strip()


def _view(claim: dict) -> dict:
    return {
        "claim_id": claim["claim_id"], "status": claim["validation_status"],
        "subject": claim["subject"], "predicate": claim["predicate"], "object": claim["object"],
        "quotes": sorted(normalize_whitespace(q) for q in claim["supporting_quotes"]),
        "chunks": tuple(sorted(claim["supporting_chunk_ids"])),
        "sn": normalize_triple_part(claim["subject"]),
        "pn": claim["predicate"].strip().casefold(),
        "on": normalize_triple_part(claim["object"]),
        "sl": loose_entity(claim["subject"]), "ol": loose_entity(claim["object"]),
    }


def _claim_key(facet_key: str, claim: dict) -> tuple:
    """Exactly as `benchmark._normalized_claim_keys` computes it."""
    return (facet_key, normalize_triple_part(claim["subject"]), claim["predicate"].strip().casefold(),
            normalize_triple_part(claim["object"]), tuple(sorted(claim["supporting_chunk_ids"])))


def _citation_key(facet_key: str, claim: dict) -> tuple:
    """Exactly as `benchmark._citation_keys` computes it."""
    return (facet_key, normalize_triple_part(claim["subject"]), claim["predicate"].strip().casefold(),
            normalize_triple_part(claim["object"]),
            tuple(sorted(normalize_whitespace(q) for q in claim["supporting_quotes"])))


def _jaccard(left: set, right: set) -> float:
    if not left and not right:
        return 1.0
    return len(left & right) / len(left | right)


def _collect(runs: dict, run: str, keyfn, accepted_only: bool) -> set:
    out = set()
    for facet_key, validation in runs["validations_by_run"][run].items():
        for claim in validation["claims"]:
            if accepted_only and claim["validation_status"] != "accepted":
                continue
            out.add(keyfn(facet_key, claim))
    return out


def _pairwise(runs: dict, keyfn, accepted_only: bool) -> dict[str, float]:
    sets = {r: _collect(runs, r, keyfn, accepted_only) for r in RUN_IDS}
    return {f"run{a}_vs_run{b}": _jaccard(sets[a], sets[b]) for a, b in combinations(RUN_IDS, 2)}


def citation_exact_on_matched(runs: dict, accepted_only: bool) -> dict:
    """The quantity SS8F's THRESHOLD names: among claims that MATCH on
    (facet, subject, predicate, object) between two runs, the fraction whose
    normalized citation sets are exactly equal. This is not a Jaccard."""
    out: dict[str, dict] = {}
    for a, b in combinations(RUN_IDS, 2):
        index: dict[str, dict[tuple, set]] = {}
        for run in (a, b):
            index[run] = {}
            for facet_key, validation in runs["validations_by_run"][run].items():
                for claim in validation["claims"]:
                    if accepted_only and claim["validation_status"] != "accepted":
                        continue
                    triple = (facet_key, normalize_triple_part(claim["subject"]),
                              claim["predicate"].strip().casefold(),
                              normalize_triple_part(claim["object"]))
                    index[run].setdefault(triple, set()).update(
                        normalize_whitespace(q) for q in claim["supporting_quotes"]
                    )
        matched = set(index[a]) & set(index[b])
        exact = sum(1 for triple in matched if index[a][triple] == index[b][triple])
        out[f"run{a}_vs_run{b}"] = {
            "matched_claims": len(matched), "citation_sets_exactly_equal": exact,
            "rate": (exact / len(matched)) if matched else 1.0,
        }
    return out


def decompose_accepted_misses(runs: dict) -> dict:
    """Split accepted-set Jaccard misses into 'same model output, different
    validation outcome' versus genuine content difference."""
    out: dict[str, dict] = {}
    for a, b in combinations(RUN_IDS, 2):
        accepted = {r: _collect(runs, r, _claim_key, True) for r in (a, b)}
        everything = {r: _collect(runs, r, _claim_key, False) for r in (a, b)}
        union = accepted[a] | accepted[b]
        shared = accepted[a] & accepted[b]
        miss = union - shared
        status_only = sum(1 for key in miss if key in everything[a] and key in everything[b])
        out[f"run{a}_vs_run{b}"] = {
            "union": len(union), "shared": len(shared), "misses": len(miss),
            "status_change_only": status_only, "content_difference": len(miss) - status_only,
        }
    return out


def _punct_only(left: set[str], right: set[str]) -> bool:
    normalize = lambda values: {_PUNCT.sub("", v).strip().casefold() for v in values}  # noqa: E731
    return normalize(left) == normalize(right)


def classify(a: dict, b: dict) -> tuple[str | None, str]:
    if (a["sn"], a["pn"], a["on"]) == (b["sn"], b["pn"], b["on"]):
        if a["quotes"] == b["quotes"]:
            return None, "identical"
        if _punct_only(set(a["quotes"]), set(b["quotes"])):
            return "quote_punctuation", "quote/punctuation-only variation"
        return "quote_span", "quote-span variation"
    if a["sl"] == b["ol"] and a["ol"] == b["sl"] and a["sl"] != a["ol"]:
        return "direction", "SEMANTIC direction change (subject/object swapped)"
    if (a["sl"], a["ol"]) == (b["sl"], b["ol"]) and a["pn"] != b["pn"]:
        return "predicate", "SEMANTIC predicate change"
    if (a["sl"], a["ol"]) == (b["sl"], b["ol"]):
        return "wording", "noun-phrase/canonical wording variation"
    if a["sl"] == b["sl"] or a["ol"] == b["ol"]:
        return "entity", "ENTITY/endpoint change"
    return "other", "other"


def _align(left_claims: list[dict], right_claims: list[dict]) -> tuple[list, list, list]:
    """Greedy alignment, most specific tier first."""
    tiers = (
        lambda x, y: (x["sn"], x["pn"], x["on"], tuple(x["quotes"])) == (y["sn"], y["pn"], y["on"], tuple(y["quotes"])),
        lambda x, y: (x["sn"], x["pn"], x["on"]) == (y["sn"], y["pn"], y["on"]),
        lambda x, y: {x["sl"], x["ol"]} == {y["sl"], y["ol"]},
        lambda x, y: x["sl"] == y["sl"] or x["ol"] == y["ol"],
    )
    pairs: list[tuple[int, int]] = []
    used_right: set[int] = set()
    for tier in tiers:
        for i, x in enumerate(left_claims):
            if any(i == pi for pi, _ in pairs):
                continue
            for j, y in enumerate(right_claims):
                if j in used_right:
                    continue
                if tier(x, y):
                    pairs.append((i, j))
                    used_right.add(j)
                    break
    matched_left = {i for i, _ in pairs}
    return (
        [(left_claims[i], right_claims[j]) for i, j in pairs],
        [x for i, x in enumerate(left_claims) if i not in matched_left],
        [y for j, y in enumerate(right_claims) if j not in used_right],
    )


def main() -> None:
    runs = json.loads(FROZEN_RUNS_PATH.read_text(encoding="utf-8"))

    contract = load_contract(config.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH)
    fixtures = load_all_revision_fixtures(contract["fixtures"])
    projection = build_projection(fixtures)
    if projection.projection_hash != runs["projection_hash"]:
        raise SystemExit("STOP -- frozen runs were compiled against a different projection")
    source_by_chunk = {s.chunk_id: s.source_text for s in projection.sections}
    symbol_by_revision = {fx.document_revision_id: sym for sym, fx in fixtures.items()}

    facet_reports: list[dict] = []
    tally: dict[str, int] = {}
    identical_facets = 0

    for facet_key in sorted(runs["validations_by_run"]["1"]):
        per_run = {r: [_view(c) for c in runs["validations_by_run"][r][facet_key]["claims"]] for r in RUN_IDS}
        differences: list[dict] = []
        for a, b in combinations(RUN_IDS, 2):
            matched, only_a, only_b = _align(per_run[a], per_run[b])
            for x, y in matched:
                code, label = classify(x, y)
                if code is None:
                    continue
                tally[code] = tally.get(code, 0) + 1
                differences.append({
                    "pair": f"run{a}_vs_run{b}", "code": code, "label": label,
                    f"run{a}": {k: x[k] for k in ("claim_id", "subject", "predicate", "object", "status", "quotes")},
                    f"run{b}": {k: y[k] for k in ("claim_id", "subject", "predicate", "object", "status", "quotes")},
                })
            for x in only_a:
                tally["omitted_extra"] = tally.get("omitted_extra", 0) + 1
                differences.append({"pair": f"run{a}_vs_run{b}", "code": "omitted_extra",
                                    "label": f"present in run{a}, absent in run{b}",
                                    "claim": {k: x[k] for k in ("claim_id", "subject", "predicate", "object", "status")}})
            for y in only_b:
                tally["omitted_extra"] = tally.get("omitted_extra", 0) + 1
                differences.append({"pair": f"run{a}_vs_run{b}", "code": "omitted_extra",
                                    "label": f"present in run{b}, absent in run{a}",
                                    "claim": {k: y[k] for k in ("claim_id", "subject", "predicate", "object", "status")}})

        page_key, revision_id = facet_key.split("|", 1)
        if not differences:
            identical_facets += 1
        facet_reports.append({
            "facet_key": facet_key, "page_key": page_key,
            "revision_symbol": symbol_by_revision.get(revision_id),
            "claim_counts_by_run": {r: len(per_run[r]) for r in RUN_IDS},
            "identical_across_runs": not differences,
            "source_text": {
                cid: source_by_chunk.get(cid)
                for cid in sorted({c for claims in per_run.values() for v in claims for c in v["chunks"]})
            },
            "claims_by_run": {
                r: [{k: v[k] for k in ("claim_id", "subject", "predicate", "object", "status", "quotes")}
                    for v in per_run[r]]
                for r in RUN_IDS
            },
            "differences": differences,
        })

    report = {
        "analysis": "Stage 7C.1 repeatability, READ-ONLY over the frozen Runs 1/2/3",
        "modifies_frozen_artifacts": False,
        "reran_compilation": False,
        "model_calls": 0,
        "updates_gate_q": False,
        "projection_hash": runs["projection_hash"],
        "primary_run_id": runs["primary_run_id"],
        "population_sizes": {
            "all_output_claim_keys_by_run": {
                r: len(_collect(runs, r, _claim_key, False)) for r in RUN_IDS},
            "accepted_only_claim_keys_by_run": {
                r: len(_collect(runs, r, _claim_key, True)) for r in RUN_IDS},
        },
        "claim_jaccard_all_output": _pairwise(runs, _claim_key, False),
        "claim_jaccard_accepted_only": _pairwise(runs, _claim_key, True),
        "citation_jaccard_all_output_as_implemented": _pairwise(runs, _citation_key, False),
        "citation_jaccard_accepted_only_as_implemented": _pairwise(runs, _citation_key, True),
        "citation_exact_on_matched_all_output": citation_exact_on_matched(runs, False),
        "citation_exact_on_matched_accepted_only": citation_exact_on_matched(runs, True),
        "accepted_miss_decomposition": decompose_accepted_misses(runs),
        "classification_tally": dict(sorted(tally.items(), key=lambda kv: -kv[1])),
        "facets_total": len(facet_reports),
        "facets_identical_across_runs": identical_facets,
        "facets": facet_reports,
        "metric_definition_note": (
            "SS8F states the repeatability quantity twice and the two statements differ. The metric list "
            "leaves the population unqualified; the threshold names the ACCEPTED-claim set and, for "
            "citations, 'citation sets on matched claims >= 0.95 exact' -- which is an exact-agreement "
            "rate, not a Jaccard. benchmark._normalized_claim_keys implements the metric-list wording; "
            "benchmark._citation_keys implements neither. Every variant is reported here side by side."
        ),
    }
    OUTPUT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"facets: {report['facets_total']} ({identical_facets} identical across all three runs)")
    print(f"claim Jaccard  all-output    : {report['claim_jaccard_all_output']}")
    print(f"claim Jaccard  accepted-only : {report['claim_jaccard_accepted_only']}")
    print(f"citation exact on matched (accepted): "
          f"{ {k: round(v['rate'], 4) for k, v in report['citation_exact_on_matched_accepted_only'].items()} }")
    print(f"tally: {report['classification_tally']}")
    print(f"written: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
