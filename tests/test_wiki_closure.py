"""Stage 7C.1 post-adjudication closure (Revision 6 SS4.6 pass 3 onward).

Runs the real closure over the frozen Runs 1/2/3 and the owner's real verdict
set, with deterministic FAKE embeddings so the suite needs no model download.
No compiler call is made or reachable.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from ingestion_bench.cross_document_benchmark.benchmark_runner import build_evidence_alignment, load_contract
from ingestion_bench.cross_document_benchmark.fixtures import load_all_revision_fixtures
from ingestion_bench.retrieval_baseline.embeddings import FakeEmbeddingProvider
from ingestion_bench.wiki_projection import config
from ingestion_bench.wiki_projection.assembly import compose_payload_preview
from ingestion_bench.wiki_projection.benchmark import PRIMARY_RUN_ID, facet_key, load_frozen_runs
from ingestion_bench.wiki_projection.closure import (
    ClosurePreflightError,
    build_final_embeddings,
    compute_expected_fact_recall,
    evaluate_final_gate_q,
    run_preflight,
)
from ingestion_bench.wiki_projection.projection import build_projection
from ingestion_bench.wiki_projection.validation import (
    AdjudicationVerdictSet,
    apply_pass3,
    required_adjudication_item_ids,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
WIKI_ROOT = REPO_ROOT / "src" / "ingestion_bench" / "wiki_projection"

FROZEN_PROJECTION_HASH = "4162fa515cf29d09391c0d963b76c7e63b1d454c4439ee0568805d1a31e3b613"
FROZEN_PACKET_SHA256 = "5d08b88dc9473a07ff94ddaead911a1a2aa54aba384afeec0f85b9a97ccb2065"
EXPECTED_VERDICT_SET_SHA256 = "d49cc8643388f830ffbcf5097faa8335a40c366b06b8f54a176aa978b06158bd"

RUNS_PATH = REPO_ROOT / "reports" / "stage7c1_compilation_runs.json"
VERDICTS_PATH = REPO_ROOT / "reports" / "stage7c1_adjudication_verdict_set.json"
PACKET_PATH = REPO_ROOT / "reports" / "stage7c1_owner_adjudication_packet.json"
Q5_PATH = REPO_ROOT / "reports" / "stage7c_q5_owner_decision.json"

# The three owner-INCORRECT accepted claims and two owner-INCORRECT summaries.
FAILED_CLAIM_PAGES = {"IDENT:C-88", "IDENT:O-32", "IDENT:P-301"}
FAILED_SUMMARY_PAGES = {"IDENT:C-88", "IDENT:O-32"}
# Semantically CORRECT but mechanically reference-invalid -- must stay excluded.
REFERENCE_INVALID_CORRECT_SUMMARY = (
    "SUMMARY::PHRASE:payment settlement|"
    "895467b2b856639286818a30384b0bea8e3b16b3068770ef1c70b0c97bd364da::sentence_1"
)


def _require(path: Path):
    if not path.exists():
        pytest.skip(f"{path} not present")


@pytest.fixture(scope="module")
def frozen():
    for path in (RUNS_PATH, VERDICTS_PATH, PACKET_PATH, Q5_PATH):
        _require(path)
    contract = load_contract(config.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH)
    fixtures = load_all_revision_fixtures(contract["fixtures"])
    projection = build_projection(fixtures)
    pages_by_key = {p.page_key: p for p in projection.page_identities}
    return {
        "contract": contract, "fixtures": fixtures, "projection": projection,
        "pages_by_key": pages_by_key,
        "sections_by_chunk": {s.chunk_id: s for s in projection.sections},
        "facets_by_key": {facet_key(f.page_key, f.document_revision_id): f for f in projection.facets},
        "runs": load_frozen_runs(RUNS_PATH, pages_by_key=pages_by_key),
        "verdicts": AdjudicationVerdictSet.model_validate_json(VERDICTS_PATH.read_text(encoding="utf-8")),
        "q5": json.loads(Q5_PATH.read_text(encoding="utf-8")),
        "packet_sha": json.loads(PACKET_PATH.read_text(encoding="utf-8"))["packet_sha256"],
    }


@pytest.fixture(scope="module")
def closed(frozen):
    """The real closure: pass 3 -> payloads -> embeddings -> recall -> Gate Q."""
    projection, verdicts = frozen["projection"], frozen["verdicts"]
    run_1 = frozen["runs"].validations_by_run[str(PRIMARY_RUN_ID)]
    postings_by_chunk: dict[str, list] = {}
    for posting in projection.postings:
        postings_by_chunk.setdefault(posting.chunk_id, []).append(posting)

    pass3 = {
        key: apply_pass3(
            validation, page=frozen["pages_by_key"][validation.page_key],
            sections_by_chunk=frozen["sections_by_chunk"], all_page_keys=set(frozen["pages_by_key"]),
            verdicts=verdicts,
        )
        for key, validation in sorted(run_1.items())
    }
    payloads = {
        key: compose_payload_preview(
            run_1[key], facet=frozen["facets_by_key"][key],
            page=frozen["pages_by_key"][run_1[key].page_key],
            sections_by_chunk=frozen["sections_by_chunk"], postings_by_chunk=postings_by_chunk,
            pass3=pass3[key], verdict_set_sha256=EXPECTED_VERDICT_SET_SHA256,
        )
        for key in sorted(pass3)
    }
    primary = next(p for p in frozen["runs"].run_provenance if p.run_id == PRIMARY_RUN_ID)
    embeddings = build_final_embeddings(
        payloads=payloads, projection=projection, embedding_provider=FakeEmbeddingProvider(),
        verdict_set_sha256=EXPECTED_VERDICT_SET_SHA256,
        compiler_model_identity=primary.model_identity,
        prompt_version=primary.prompt_version, prompt_sha256_value=primary.prompt_sha256,
    )
    surviving = {
        key: [c for c in run_1[key].claims if c.claim_id in set(pass3[key].surviving_accepted_claim_ids)]
        for key in sorted(pass3)
    }
    recall = compute_expected_fact_recall(
        surviving_claims_by_facet=surviving,
        contract_facts=frozen["contract"]["facts"],
        evidence_by_fact=build_evidence_alignment(frozen["contract"], frozen["fixtures"]),
    )
    gate_q = evaluate_final_gate_q(
        run_1=run_1, pass3_by_facet=pass3, verdicts=verdicts,
        repeatability=frozen["runs"].repeatability, recall=recall, q5_decision=frozen["q5"],
        verdict_set_sha256=EXPECTED_VERDICT_SET_SHA256, projection_hash=projection.projection_hash,
    )
    return {"pass3": pass3, "payloads": payloads, "embeddings": embeddings,
            "recall": recall, "gate_q": gate_q, "run_1": run_1, "surviving": surviving}


def _totals(pass3, field):
    return (
        sum(r.counts_before[field] for r in pass3.values()),
        sum(r.counts_after[field] for r in pass3.values()),
    )


# --- 1/2: verdict-set completeness and SHA ----------------------------------


def test_verdict_set_is_exactly_complete_with_no_extras(frozen):
    run_1 = frozen["runs"].validations_by_run[str(PRIMARY_RUN_ID)]
    required = {item for v in run_1.values() for item in required_adjudication_item_ids(v)}
    supplied = set(frozen["verdicts"].verdicts)
    assert supplied == required
    assert len(required) == 68


def test_verdict_set_sha_matches_the_expected_value(frozen):
    assert frozen["verdicts"].verdict_set_sha256() == EXPECTED_VERDICT_SET_SHA256


def test_verdict_distribution_is_the_owner_supplied_one(frozen):
    values = list(frozen["verdicts"].verdicts.values())
    assert len(values) == 68
    assert values.count("CORRECT") == 63
    assert values.count("INCORRECT") == 5
    assert values.count("UNVERIFIABLE") == 0


# --- preflight fails closed --------------------------------------------------


def test_preflight_passes_on_the_real_frozen_inputs(frozen):
    report = run_preflight(
        projection=frozen["projection"], runs=frozen["runs"], verdicts=frozen["verdicts"],
        expected_projection_hash=FROZEN_PROJECTION_HASH,
        expected_verdict_set_sha256=EXPECTED_VERDICT_SET_SHA256,
        expected_packet_sha256=FROZEN_PACKET_SHA256, packet_sha256=frozen["packet_sha"],
    )
    assert report.all_checks_passed is True
    assert report.primary_run_id == 1
    assert report.missing_item_ids == [] and report.extra_item_ids == []


@pytest.mark.parametrize(
    "mutation",
    ["wrong_projection_hash", "wrong_verdict_sha", "missing_verdict", "extra_verdict", "wrong_packet_sha"],
)
def test_preflight_fails_closed_on_any_integrity_breach(frozen, mutation):
    verdicts = frozen["verdicts"]
    kwargs = dict(
        projection=frozen["projection"], runs=frozen["runs"], verdicts=verdicts,
        expected_projection_hash=FROZEN_PROJECTION_HASH,
        expected_verdict_set_sha256=EXPECTED_VERDICT_SET_SHA256,
        expected_packet_sha256=FROZEN_PACKET_SHA256, packet_sha256=frozen["packet_sha"],
    )
    if mutation == "wrong_projection_hash":
        kwargs["expected_projection_hash"] = "0" * 64
    elif mutation == "wrong_verdict_sha":
        kwargs["expected_verdict_set_sha256"] = "0" * 64
    elif mutation == "wrong_packet_sha":
        kwargs["packet_sha256"] = "0" * 64
    elif mutation == "missing_verdict":
        trimmed = dict(verdicts.verdicts)
        trimmed.pop(next(iter(trimmed)))
        kwargs["verdicts"] = AdjudicationVerdictSet(verdicts=trimmed)
    elif mutation == "extra_verdict":
        extended = dict(verdicts.verdicts)
        extended["CLAIM::not-a-real-facet::x"] = "CORRECT"
        kwargs["verdicts"] = AdjudicationVerdictSet(verdicts=extended)

    with pytest.raises(ClosurePreflightError):
        run_preflight(**kwargs)


# --- 3-7: pass-3 aggregates --------------------------------------------------


def test_all_22_facets_receive_pass_3(closed):
    assert len(closed["pass3"]) == 22


def test_no_supported_alias_is_withdrawn(closed):
    before, after = _totals(closed["pass3"], "supported_aliases")
    assert (before, after) == (21, 21)
    assert all(not r.withdrawn_alias_ids for r in closed["pass3"].values())


def test_accepted_claims_go_from_25_to_22(closed):
    assert _totals(closed["pass3"], "accepted_claims") == (25, 22)


def test_reference_valid_summaries_go_from_21_to_19(closed):
    assert _totals(closed["pass3"], "reference_valid_summary_sentences") == (21, 19)


def test_derived_links_go_from_34_to_30(closed):
    before, after = _totals(closed["pass3"], "derived_links")
    assert (before, after) == (34, 30)
    assert sum(len(r.derived_links) for r in closed["pass3"].values()) == 30


# --- 8-12: the specific failed items cannot survive --------------------------


@pytest.mark.parametrize("page_key", sorted(FAILED_CLAIM_PAGES))
def test_each_owner_failed_claim_is_absent_from_payload_and_links(closed, page_key):
    """C-88/O-31 reversed direction, O-32 governance reversal, malformed
    O-32 -> P-301 triple. Each must leave no trace in the vector or the links."""
    withdrawn_texts: list[str] = []
    for key, result in closed["pass3"].items():
        if not key.startswith(f"{page_key}|") or not result.withdrawn_claim_ids:
            continue
        validation = closed["run_1"][key]
        for claim in validation.claims:
            if claim.claim_id in result.withdrawn_claim_ids:
                withdrawn_texts.append(claim.claim_text)
                # no surviving link may descend from it
                assert all(link.claim_id != claim.claim_id for link in result.derived_links)
        component_6 = next(c for c in closed["payloads"][key].components if c.number == 6)
        for text in withdrawn_texts:
            assert text not in component_6.text
    assert withdrawn_texts, f"expected a withdrawn claim on {page_key}"


def test_no_surviving_link_descends_from_a_failed_claim(closed):
    surviving_link_claim_ids = {
        link.claim_id for result in closed["pass3"].values() for link in result.derived_links
    }
    withdrawn_claim_ids = {
        cid for result in closed["pass3"].values() for cid in result.withdrawn_claim_ids
    }
    facet_scoped = {
        (key, cid) for key, result in closed["pass3"].items() for cid in result.withdrawn_claim_ids
    }
    assert facet_scoped, "the owner verdicts withdraw at least one claim"
    for key, result in closed["pass3"].items():
        for link in result.derived_links:
            assert link.claim_id not in set(result.withdrawn_claim_ids)
    assert isinstance(surviving_link_claim_ids, set) and isinstance(withdrawn_claim_ids, set)


@pytest.mark.parametrize("page_key", sorted(FAILED_SUMMARY_PAGES))
def test_each_owner_failed_summary_is_absent_from_the_payload(closed, page_key):
    found = False
    for key, result in closed["pass3"].items():
        if not key.startswith(f"{page_key}|") or not result.withdrawn_summary_ids:
            continue
        found = True
        validation = closed["run_1"][key]
        component_7 = next(c for c in closed["payloads"][key].components if c.number == 7)
        for sentence in validation.summary_sentences:
            if sentence.sentence_id in result.withdrawn_summary_ids:
                assert sentence.text not in component_7.text
    assert found, f"expected a withdrawn summary on {page_key}"


def test_reference_invalid_but_owner_correct_summary_stays_excluded(frozen, closed):
    """Its owner verdict is CORRECT, but its mechanical `reference_valid` is
    False because it references no accepted in-scope claim. The verdict means
    only that the sentence is faithful to its source -- it does not repair
    structural ineligibility, and nothing here may 'fix' it."""
    assert frozen["verdicts"].verdicts[REFERENCE_INVALID_CORRECT_SUMMARY] == "CORRECT"

    facet_key_part, sentence_id = REFERENCE_INVALID_CORRECT_SUMMARY[len("SUMMARY::"):].rsplit("::", 1)
    validation = closed["run_1"][facet_key_part]
    sentence = next(s for s in validation.summary_sentences if s.sentence_id == sentence_id)
    assert sentence.reference_valid is False, "the mechanical record must be untouched"

    result = closed["pass3"][facet_key_part]
    assert sentence_id not in result.surviving_summary_sentence_ids
    component_7 = next(c for c in closed["payloads"][facet_key_part].components if c.number == 7)
    assert sentence.text not in component_7.text


def test_mechanical_validation_status_is_never_rewritten_by_a_verdict(closed):
    """Owner withdrawal is a separate state; SS4.2 keeps the mechanical record."""
    for key, result in closed["pass3"].items():
        validation = closed["run_1"][key]
        for claim_id in result.withdrawn_claim_ids:
            claim = next(c for c in validation.claims if c.claim_id == claim_id)
            assert claim.validation_status == "accepted"


# --- 13-16: final payloads ---------------------------------------------------


def test_there_are_exactly_22_final_payloads_all_marked_final(closed):
    assert len(closed["payloads"]) == 22
    assert all(p.is_final is True for p in closed["payloads"].values())


def test_no_final_payload_has_pending_adjudication_components(closed):
    for payload in closed["payloads"].values():
        assert payload.pending_components == []
        assert all(not c.pending_owner_adjudication for c in payload.components)


def test_every_final_payload_carries_the_verdict_set_hash(closed):
    assert all(p.verdict_set_sha256 == EXPECTED_VERDICT_SET_SHA256 for p in closed["payloads"].values())


def test_component_order_dedupe_and_drop_order_are_unchanged(closed):
    from ingestion_bench.wiki_projection.assembly import NEVER_DROPPED_COMPONENTS, PAY_MAX_DROP_ORDER

    assert PAY_MAX_DROP_ORDER == (7, 6, 5, 2)
    assert NEVER_DROPPED_COMPONENTS == frozenset({1, 3, 4})
    for payload in closed["payloads"].values():
        assert [c.number for c in payload.components] == [1, 2, 3, 4, 5, 6, 7]


def test_membership_and_page_identity_are_unchanged_by_closure(frozen, closed):
    from ingestion_bench.wiki_projection.projection import compute_projection_hash

    projection = frozen["projection"]
    assert projection.projection_hash == FROZEN_PROJECTION_HASH
    assert compute_projection_hash(projection) == FROZEN_PROJECTION_HASH
    assert len(projection.facets) == 22
    assert len(projection.page_identities) == 13


# --- 17-18: final embeddings -------------------------------------------------


def test_exactly_22_final_facet_embeddings_and_no_page_vector(closed):
    embeddings = closed["embeddings"]
    assert len(embeddings) == 22
    keys = {(e.page_key, e.document_revision_id) for e in embeddings}
    assert len(keys) == 22, "one embedding per FACET, never per page"
    assert len({e.page_key for e in embeddings}) == 13


def test_embedding_provenance_binds_vector_to_payload_and_verdict_set(closed):
    payloads = closed["payloads"]
    for record in closed["embeddings"]:
        key = f"{record.page_key}|{record.document_revision_id}"
        assert record.payload_sha256 == payloads[key].preview_sha256
        assert record.payload_text == payloads[key].preview_text
        assert record.verdict_set_sha256 == EXPECTED_VERDICT_SET_SHA256
        assert record.projection_hash == FROZEN_PROJECTION_HASH
        assert record.repeatability_run_id == 1
        assert record.representation_derivation == "post_adjudication_w1_facet_payload"
        assert record.is_authoritative_lineage is False
        assert record.embedding_dimension == len(record.embedding) > 0
        assert record.compiler_model_identity and record.prompt_sha256
        assert hashlib.sha256(record.payload_text.encode("utf-8")).hexdigest() == record.payload_sha256


# --- 19-24: final Gate Q -----------------------------------------------------


def _criterion(gate_q, name):
    return next(c for c in gate_q.criteria if c.criterion == name)


def test_q5_computes_0_88_and_fails(closed):
    q5 = _criterion(closed["gate_q"], "Q-5")
    assert q5.observed == pytest.approx(22 / 25)
    assert q5.observed == pytest.approx(0.88)
    assert q5.status == "FAIL"


def test_q6_uses_surviving_claims_and_reports_both_rules(closed):
    recall = closed["recall"]
    assert recall.surviving_claim_count == 22
    assert recall.denominator == 15
    assert recall.numerator == 13
    assert recall.recall == pytest.approx(13 / 15)
    # the stricter rule is reported alongside, so the choice is visible
    assert recall.strict_numerator == 9
    assert recall.strict_recall == pytest.approx(9 / 15)
    assert "Graph" in recall.mapping_rule


def test_q7_records_two_incorrect_and_fails(closed):
    q7 = _criterion(closed["gate_q"], "Q-7")
    assert q7.observed == 2
    assert q7.status == "FAIL"
    assert "20 correct" in q7.detail


def test_q8_fails_only_on_claim_jaccard_and_citation_agreement_passes(closed):
    q8 = _criterion(closed["gate_q"], "Q-8")
    assert q8.status == "FAIL"
    assert q8.observed["accepted_claim_set_jaccard_min"] == pytest.approx(0.620690, abs=1e-6)
    assert q8.observed["citation_exact_agreement_min"] == 1.0
    assert q8.observed["false_merges_any_run"] == 0
    assert q8.observed["ceiling_breaches_any_run"] == 0
    assert "accepted_claim_set_jaccard" in q8.detail
    # the obsolete pre-correction citation-Jaccard failure must not reappear
    assert "citation_exact_agreement min" not in q8.detail


def test_q10_records_zero_incorrect_supported_aliases_and_passes(closed):
    q10 = _criterion(closed["gate_q"], "Q-10")
    assert q10.observed == 0
    assert q10.status == "PASS"
    assert "21/21" in q10.detail


def test_gate_q_is_conjunctive_and_every_criterion_is_evaluated(closed):
    gate_q = closed["gate_q"]
    assert [c.criterion for c in gate_q.criteria] == [f"Q-{n}" for n in range(1, 11)]
    assert gate_q.overall_status == "FAIL"
    assert set(gate_q.failing_criteria) == {"Q-5", "Q-7", "Q-8"}
    assert gate_q.overall_status == ("PASS" if not gate_q.failing_criteria else "FAIL")
    assert "conjunctive" in gate_q.evaluation_rule


def test_gate_q_binds_to_the_q5_decision_and_frozen_identities(frozen, closed):
    gate_q = closed["gate_q"]
    assert gate_q.q5_decision_id == frozen["q5"]["decision_id"]
    assert frozen["q5"]["decision"] == "APPROVED"
    assert gate_q.verdict_set_sha256 == EXPECTED_VERDICT_SET_SHA256
    assert gate_q.projection_hash == FROZEN_PROJECTION_HASH


# --- 25-26: no compiler reachable; determinism -------------------------------


def test_no_compiler_or_model_call_is_reachable_from_the_closure(frozen):
    """The closure module and runner must not import or construct a facet
    compiler, and must make no LLM call."""
    for path in (WIKI_ROOT / "closure.py", REPO_ROOT / "scripts" / "close_stage7c1_after_adjudication.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.add(node.module)
                imported.update(a.name for a in node.names)
        assert not any("openai" in m.lower() for m in imported), path.name
        assert "OpenAIFacetCompiler" not in imported, path.name
        assert "FakeFacetCompiler" not in imported, path.name
        assert "ScriptedFacetCompiler" not in imported, path.name
        assert not any("graph_retrieval_benchmark" in m for m in imported), path.name
        source = path.read_text(encoding="utf-8")
        assert "compile_facet" not in source, path.name


def test_closure_is_deterministic_over_identical_frozen_inputs(frozen):
    """Re-running the deterministic closure must give identical semantic
    results -- same pass-3 outcome, same payload hashes, same Gate Q."""
    projection, verdicts = frozen["projection"], frozen["verdicts"]
    run_1 = frozen["runs"].validations_by_run[str(PRIMARY_RUN_ID)]
    postings_by_chunk: dict[str, list] = {}
    for posting in projection.postings:
        postings_by_chunk.setdefault(posting.chunk_id, []).append(posting)

    def once():
        pass3 = {
            key: apply_pass3(
                v, page=frozen["pages_by_key"][v.page_key], sections_by_chunk=frozen["sections_by_chunk"],
                all_page_keys=set(frozen["pages_by_key"]), verdicts=verdicts,
            )
            for key, v in sorted(run_1.items())
        }
        payloads = {
            key: compose_payload_preview(
                run_1[key], facet=frozen["facets_by_key"][key],
                page=frozen["pages_by_key"][run_1[key].page_key],
                sections_by_chunk=frozen["sections_by_chunk"], postings_by_chunk=postings_by_chunk,
                pass3=pass3[key], verdict_set_sha256=EXPECTED_VERDICT_SET_SHA256,
            )
            for key in sorted(pass3)
        }
        return (
            {k: v.model_dump_json() for k, v in pass3.items()},
            {k: v.preview_sha256 for k, v in payloads.items()},
        )

    assert once() == once()


def test_fake_and_real_embedding_providers_change_no_payload_text(frozen, closed):
    """The embedding provider must not influence what is embedded."""
    payload_hashes = {k: v.preview_sha256 for k, v in closed["payloads"].items()}
    primary = next(p for p in frozen["runs"].run_provenance if p.run_id == PRIMARY_RUN_ID)
    records = build_final_embeddings(
        payloads=closed["payloads"], projection=frozen["projection"],
        embedding_provider=FakeEmbeddingProvider(dimension=64),
        verdict_set_sha256=EXPECTED_VERDICT_SET_SHA256,
        compiler_model_identity=primary.model_identity,
        prompt_version=primary.prompt_version, prompt_sha256_value=primary.prompt_sha256,
    )
    assert {f"{r.page_key}|{r.document_revision_id}": r.payload_sha256 for r in records} == payload_hashes
    assert all(r.embedding_dimension == 64 for r in records)


def test_frozen_inputs_are_not_written_by_the_closure_runner():
    """The runner must never write the frozen runs, packet, projection contract
    or the plan."""
    source = (REPO_ROOT / "scripts" / "close_stage7c1_after_adjudication.py").read_text(encoding="utf-8")
    for frozen_name in (
        "stage7c1_compilation_runs.json", "stage7c1_owner_adjudication_packet",
        "wiki_projection_v1.json", "STAGE7C_WIKI_PLAN.md",
    ):
        for line in source.splitlines():
            if frozen_name in line:
                assert "write_text" not in line, f"runner appears to write {frozen_name}: {line.strip()}"
