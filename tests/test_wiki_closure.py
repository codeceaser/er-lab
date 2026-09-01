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
    # Prefer the EXACT frozen vectors; fall back to the deterministic fake only
    # when the artifact is absent, so the suite never silently tests a different
    # vector set than the one that is frozen.
    frozen_vectors = REPO_ROOT / "artifacts" / "stage7c1_closure" / "facet_embeddings.json"
    if frozen_vectors.exists():
        from ingestion_bench.wiki_projection.closure import FacetEmbeddingRecord, embedding_sha256

        embeddings = [
            FacetEmbeddingRecord(**{**e, "embedding_sha256": embedding_sha256(e["embedding"])})
            for e in json.loads(frozen_vectors.read_text(encoding="utf-8"))
        ]
        embeddings.sort(key=lambda r: (r.page_key, r.document_revision_id))
    else:
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
        declared_dollar_cap_usd=5.0, total_estimated_cost_usd=frozen["runs"].total_estimated_cost_usd,
    )
    preflight = run_preflight(
        projection=projection, runs=frozen["runs"], verdicts=verdicts,
        expected_projection_hash=FROZEN_PROJECTION_HASH,
        expected_verdict_set_sha256=EXPECTED_VERDICT_SET_SHA256,
        expected_packet_sha256=FROZEN_PACKET_SHA256, packet_sha256=frozen["packet_sha"],
    )
    return {"pass3": pass3, "payloads": payloads, "embeddings": embeddings,
            "recall": recall, "gate_q": gate_q, "run_1": run_1, "surviving": surviving,
            "preflight": preflight}


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


# =============================================================================
# Stage 7C.1 closure HARDENING (corrections A-G)
# =============================================================================

COMPILER_CONTRACT_PATH = REPO_ROOT / "contracts" / "wiki_compiler_v1.json"
FROZEN_VECTORS_PATH = REPO_ROOT / "artifacts" / "stage7c1_closure" / "facet_embeddings.json"
EXPECTED_COMPILER_CONTRACT_SHA = "35ccad855b10e6e8c08f6699136dff590dbd37abcef3c64147500a94edcad793"


# --- A: the frozen Stage 7C.1 compiler contract ------------------------------


def test_compiler_contract_file_exists_and_is_frozen():
    """Revision 6 SS10.2/SS11 require contracts/wiki_compiler_v1.json at 7C.1."""
    assert COMPILER_CONTRACT_PATH.exists()
    contract = json.loads(COMPILER_CONTRACT_PATH.read_text(encoding="utf-8"))
    assert contract["contract_version"] == "wiki_compiler_v1"
    assert contract["stage"] == "7C.1"
    assert contract["status"] == "frozen"


def test_compiler_contract_pins_the_critical_frozen_values():
    contract = json.loads(COMPILER_CONTRACT_PATH.read_text(encoding="utf-8"))
    assert contract["compiler_model"] == "gpt-4o-mini"
    assert contract["temperature"] == 0
    assert contract["prompt_version"] == "stage7c1-facet-compiler-v1"
    assert contract["prompt_sha256"] == (
        "1144ceff32112796aa698a1a2508373cd5d3617989aa0f5e5af8e02950d85b53"
    )
    assert contract["model_output_schema"]["fields"] == ["aliases", "claims", "summary_sentences"]
    assert contract["model_output_schema"]["additional_properties_permitted"] is False

    ceilings = contract["ceilings"]
    assert ceilings["input_chunks_per_facet_F_max"] == 12
    assert ceilings["input_tokens_per_facet"] == 8000
    assert ceilings["accepted_plus_uncertain_claims_per_facet"] == 20
    assert ceilings["aliases_per_facet"] == 8
    assert ceilings["summary_sentences_per_facet"] == 5
    assert ceilings["output_tokens_per_facet"] == 4000
    assert ceilings["payload_characters_PAY_max"] == 4000
    assert ceilings["whole_run_dollar_ceiling_usd"] == 5.0

    payload = contract["payload_composition"]
    assert [c["number"] for c in payload["component_order"]] == [1, 2, 3, 4, 5, 6, 7]
    assert payload["owner_dependent_components"] == [2, 6, 7]
    assert payload["pay_max_drop_order"] == [7, 6, 5, 2]
    assert payload["never_dropped_components"] == [1, 3, 4]

    assert contract["embedding"]["embedding_model"] == "sentence-transformers/all-MiniLM-L6-v2"
    assert contract["embedding"]["page_level_vector_permitted"] is False
    assert contract["embedding"]["reranker"] is None
    assert contract["embedding"]["query_time_llm"] is None

    retrieval = contract["retrieval_rules_frozen_for_stage_7c2"]
    assert retrieval["executed_in_stage_7c1"] is False
    assert retrieval["hop_budget_B"] == 6
    assert retrieval["m_max"] == 3
    assert retrieval["candidate_ceiling_rule"] == "C = (P_seed + B) x M_max x F_max"
    assert retrieval["traversable_anchor_kinds"] == ["identifier", "phrase"]
    assert retrieval["vector_backfill_permitted"] is False

    q8 = contract["gate_q_thresholds"]["Q-8_repeatability"]
    assert q8["accepted_claim_set_pairwise_jaccard_min"] == 0.9
    assert q8["citation_exact_agreement_on_matched_accepted_claims_min"] == 0.95
    assert contract["gate_q_thresholds"]["Q-5_accepted_claim_precision_min"] == 0.95
    assert contract["gate_q_thresholds"]["Q-6_expected_fact_recall_min"] == 0.80
    assert contract["gate_q_thresholds"]["Q-7_incorrect_summary_sentences_max"] == 0
    assert contract["gate_q_thresholds"]["Q-10_incorrect_supported_aliases_max"] == 0
    assert contract["owner_adjudication"]["verdict_set_sha256"] == EXPECTED_VERDICT_SET_SHA256
    assert contract["projection_hash"] == FROZEN_PROJECTION_HASH


def test_compiler_contract_sha_is_pinned_and_reproducible(frozen):
    from ingestion_bench.wiki_projection.report import build_compiler_contract

    committed = json.loads(COMPILER_CONTRACT_PATH.read_text(encoding="utf-8"))
    rebuilt = build_compiler_contract(
        projection_hash=FROZEN_PROJECTION_HASH, m_max=3,
        verdict_set_sha256=EXPECTED_VERDICT_SET_SHA256, declared_dollar_cap_usd=5.0,
        embedding_model="sentence-transformers/all-MiniLM-L6-v2", q5_decision=frozen["q5"],
    )
    assert committed["contract_sha256"] == EXPECTED_COMPILER_CONTRACT_SHA
    assert rebuilt["contract_sha256"] == committed["contract_sha256"]


# --- B: the three Stage 7C.1 persistence surfaces ---------------------------


@pytest.fixture(scope="module")
def persisted(closed):
    """Round-trip the closure through the in-memory Stage 7C.1 store."""
    from ingestion_bench.wiki_projection.facet_store import (
        CompilationAuditRow,
        FacetEmbeddingRow,
        FacetRecord,
        InMemoryStage7C1Store,
    )

    store = InMemoryStage7C1Store()
    store.upsert_facets([
        FacetRecord(
            page_key=r.page_key, document_revision_id=r.document_revision_id,
            validation_state="final_post_pass3", facet_membership_hash=r.facet_membership_hash,
            facet_hash=r.payload_sha256, run_id=1, compiled={"payload_sha256": r.payload_sha256},
        )
        for r in closed["embeddings"]
    ])
    store.upsert_facet_embeddings([
        FacetEmbeddingRow(
            page_key=r.page_key, document_revision_id=r.document_revision_id, embedding=r.embedding,
            embedding_dimension=r.embedding_dimension, embedding_sha256=r.embedding_sha256,
            payload_sha256=r.payload_sha256, payload_text=r.payload_text,
            component_manifest=r.component_manifest, verdict_set_sha256=r.verdict_set_sha256,
            projection_hash=r.projection_hash, embedding_model=r.embedding_model,
            compiler_model_identity=r.compiler_model_identity, prompt_version=r.prompt_version,
            prompt_sha256=r.prompt_sha256, run_id=r.repeatability_run_id,
            source_chunk_ids=r.source_chunk_ids,
        )
        for r in closed["embeddings"]
    ])
    store.upsert_compilation_audit([
        CompilationAuditRow(page_key=r.page_key, document_revision_id=r.document_revision_id, run_id=1)
        for r in closed["embeddings"]
    ])
    return store


def test_all_three_persistence_surfaces_round_trip(persisted, closed):
    assert persisted.facet_count() == 22
    assert persisted.facet_embedding_count() == 22
    assert persisted.compilation_audit_count() == 22

    rows = persisted.all_facet_embeddings()
    assert len(rows) == 22
    by_key = {f"{r.page_key}|{r.document_revision_id}": r for r in rows}
    for record in closed["embeddings"]:
        row = by_key[f"{record.page_key}|{record.document_revision_id}"]
        assert row.embedding == record.embedding
        assert row.embedding_sha256 == record.embedding_sha256
        assert row.payload_sha256 == record.payload_sha256


def test_persistence_is_idempotent(persisted, closed):
    before = (persisted.facet_count(), persisted.facet_embedding_count(), persisted.compilation_audit_count())
    persisted.upsert_facet_embeddings(persisted.all_facet_embeddings())
    after = (persisted.facet_count(), persisted.facet_embedding_count(), persisted.compilation_audit_count())
    assert before == after


def test_authority_filtering_precedes_the_vector_limit(persisted, closed):
    """An eligible set smaller than top_k must bound the result -- proving the
    restriction is applied BEFORE ranking/LIMIT, not after."""
    rows = persisted.all_facet_embeddings()
    one_revision = rows[0].document_revision_id
    eligible_rows = [r for r in rows if r.document_revision_id == one_revision]

    hits = persisted.search_eligible_facets(
        query_vector=rows[0].embedding, eligible_revision_ids=[one_revision], top_k=50,
    )
    assert len(hits) == len(eligible_rows) <= 50
    assert all(row.document_revision_id == one_revision for row, _score in hits)


def test_an_empty_eligible_set_returns_nothing_never_everything(persisted, closed):
    assert persisted.search_eligible_facets(
        query_vector=closed["embeddings"][0].embedding, eligible_revision_ids=[], top_k=5
    ) == []


def test_stage7c2_can_load_the_frozen_vectors_without_an_embedding_provider(persisted, closed):
    """The whole point of persisting: 7C.2 reads the frozen vectors rather than
    rebuilding them."""
    rows = persisted.all_facet_embeddings()
    assert len(rows) == 22
    assert all(len(r.embedding) == 384 for r in rows)
    eligible = sorted({r.document_revision_id for r in rows})
    hits = persisted.search_eligible_facets(
        query_vector=rows[0].embedding, eligible_revision_ids=eligible, top_k=3
    )
    assert len(hits) == 3
    # the identical vector ranks itself first
    assert hits[0][0].embedding_sha256 == rows[0].embedding_sha256
    assert hits[0][1] == pytest.approx(1.0, abs=1e-6)


def test_no_authority_state_is_stored_in_any_surface():
    from ingestion_bench.wiki_projection.facet_store import (
        CompilationAuditRow,
        FacetEmbeddingRow,
        FacetRecord,
    )

    forbidden = {"authority", "is_current", "current", "effective", "eligible_revision_ids", "derived_state"}
    for model in (FacetRecord, FacetEmbeddingRow, CompilationAuditRow):
        assert not (set(model.model_fields) & forbidden), model.__name__


def test_facet_store_is_separate_from_the_stage_7c0_projection_store():
    """SS10.3's 7C.1 tables must not contaminate pg_store.py, which owns the
    frozen 7C.0 projection surface."""
    pg_store = (WIKI_ROOT / "pg_store.py").read_text(encoding="utf-8")
    for table in ("edib_stage7c_facet", "edib_stage7c_facet_embedding", "edib_stage7c_compilation_audit"):
        assert table not in pg_store
    assert (WIKI_ROOT / "facet_store.py").exists()


def test_the_postgres_store_filters_authority_in_the_same_statement_as_limit():
    source = (WIKI_ROOT / "facet_store.py").read_text(encoding="utf-8")
    statement = source.split("def search_eligible_facets", 2)[-1]
    assert "WHERE document_revision_id = ANY(:eligible)" in statement
    assert "ORDER BY embedding" in statement
    assert "LIMIT :k" in statement
    where = statement.index("WHERE document_revision_id")
    assert where < statement.index("ORDER BY embedding") < statement.index("LIMIT :k")


def test_the_stage_7c2_pipeline_is_not_implemented_here():
    source = (WIKI_ROOT / "facet_store.py").read_text(encoding="utf-8")
    for forbidden in ("hub_expansion", "traverse", "final_k", "hop_budget", "seed_page_priority"):
        assert forbidden not in source
    for name in ("retrieval.py", "navigation.py"):
        assert not (WIKI_ROOT / name).exists()


# --- C: cryptographic identity for the vectors -------------------------------


def test_every_embedding_record_carries_an_embedding_sha256(closed):
    for record in closed["embeddings"]:
        assert len(record.embedding_sha256) == 64
    assert len({r.embedding_sha256 for r in closed["embeddings"]}) == 22


def test_embedding_hash_is_canonical_and_value_sensitive():
    from ingestion_bench.wiki_projection.closure import embedding_sha256

    base = [0.1, -0.25, 0.5]
    assert embedding_sha256(base) == embedding_sha256(list(base))
    assert embedding_sha256(base) != embedding_sha256([0.1, -0.25, 0.5000001])
    assert embedding_sha256(base) != embedding_sha256([-0.25, 0.1, 0.5]), "order must matter"


def test_embedding_set_hash_is_order_independent_but_content_sensitive(closed):
    from ingestion_bench.wiki_projection.closure import embedding_set_sha256

    records = closed["embeddings"]
    assert embedding_set_sha256(records) == embedding_set_sha256(list(reversed(records)))

    mutated = [r.model_copy(deep=True) for r in records]
    mutated[0].embedding_sha256 = "0" * 64
    assert embedding_set_sha256(mutated) != embedding_set_sha256(records)


def test_tracked_manifest_carries_vector_identities_and_the_set_hash():
    manifest_path = REPO_ROOT / "reports" / "stage7c1_final_embedding_manifest.json"
    if not manifest_path.exists():
        pytest.skip("manifest not present")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest["embedding_set_sha256"]) == 64
    assert "float32" in manifest["embedding_hash_serialization"]
    assert manifest["embedding_count"] == 22
    assert len(manifest["records"]) == 22
    for record in manifest["records"]:
        assert len(record["embedding_sha256"]) == 64
        # the raw vector deliberately stays out of the manifest
        assert "embedding" not in record


# --- D: the closure semantic hash covers the vectors -------------------------


def test_mutating_one_vector_coordinate_changes_both_hashes(closed):
    """A vector change must be visible in that record's hash AND in the closure
    semantic hash -- otherwise two different vector sets over the same payloads
    would be indistinguishable."""
    from ingestion_bench.wiki_projection.closure import (
        Stage7C1ClosureResult,
        embedding_sha256,
        run_preflight,
    )

    records = [r.model_copy(deep=True) for r in closed["embeddings"]]

    def build(embeddings):
        return Stage7C1ClosureResult(
            generated_at="fixed-not-hashed", preflight=closed["preflight"],
            pass3_by_facet=closed["pass3"], aggregate_counts_before={}, aggregate_counts_after={},
            withdrawn_claim_item_ids=[], withdrawn_summary_item_ids=[], withdrawn_alias_item_ids=[],
            final_payloads=closed["payloads"],
            final_derived_links=[link for r in closed["pass3"].values() for link in r.derived_links],
            embeddings=embeddings, recall=closed["recall"], gate_q=closed["gate_q"],
        )

    before_record_sha = records[0].embedding_sha256
    before_closure = build(records).semantic_hash()

    mutated = [r.model_copy(deep=True) for r in records]
    mutated[0].embedding[0] = mutated[0].embedding[0] + 0.5
    mutated[0].embedding_sha256 = embedding_sha256(mutated[0].embedding)

    assert mutated[0].embedding_sha256 != before_record_sha
    assert build(mutated).semantic_hash() != before_closure


def test_semantic_hash_excludes_wall_clock_fields(closed):
    from ingestion_bench.wiki_projection.closure import Stage7C1ClosureResult

    def build(timestamp):
        return Stage7C1ClosureResult(
            generated_at=timestamp, preflight=closed["preflight"], pass3_by_facet=closed["pass3"],
            aggregate_counts_before={}, aggregate_counts_after={}, withdrawn_claim_item_ids=[],
            withdrawn_summary_item_ids=[], withdrawn_alias_item_ids=[], final_payloads=closed["payloads"],
            final_derived_links=[], embeddings=closed["embeddings"], recall=closed["recall"],
            gate_q=closed["gate_q"],
        )

    assert build("2026-01-01T00:00:00Z").semantic_hash() == build("2030-12-31T23:59:59Z").semantic_hash()


# --- E: Q-9 checks the dollar cap --------------------------------------------


def test_q9_checks_cost_against_the_declared_cap(closed):
    q9 = next(c for c in closed["gate_q"].criteria if c.criterion == "Q-9")
    assert q9.observed["declared_dollar_cap_usd"] == 5.0
    assert q9.observed["total_estimated_cost_usd"] == pytest.approx(0.018790499999999995)
    assert q9.observed["within_declared_dollar_cap"] is True
    assert q9.observed["ceiling_breaches"] == 0
    assert q9.observed["generation_failures"] == 0
    assert q9.status == "PASS"
    assert "0.0187905" in q9.detail and "5.00" in q9.detail


def test_q9_fails_when_cost_exceeds_the_cap(frozen, closed):
    from ingestion_bench.wiki_projection.closure import evaluate_final_gate_q

    gate_q = evaluate_final_gate_q(
        run_1=closed["run_1"], pass3_by_facet=closed["pass3"], verdicts=frozen["verdicts"],
        repeatability=frozen["runs"].repeatability, recall=closed["recall"], q5_decision=frozen["q5"],
        verdict_set_sha256=EXPECTED_VERDICT_SET_SHA256, projection_hash=FROZEN_PROJECTION_HASH,
        declared_dollar_cap_usd=0.001, total_estimated_cost_usd=0.0187905,
    )
    q9 = next(c for c in gate_q.criteria if c.criterion == "Q-9")
    assert q9.status == "FAIL"
    assert q9.observed["within_declared_dollar_cap"] is False


def test_q9_does_not_pass_on_an_unavailable_cost(frozen, closed):
    """An unknown cost cannot demonstrate being within the cap."""
    from ingestion_bench.wiki_projection.closure import evaluate_final_gate_q

    gate_q = evaluate_final_gate_q(
        run_1=closed["run_1"], pass3_by_facet=closed["pass3"], verdicts=frozen["verdicts"],
        repeatability=frozen["runs"].repeatability, recall=closed["recall"], q5_decision=frozen["q5"],
        verdict_set_sha256=EXPECTED_VERDICT_SET_SHA256, projection_hash=FROZEN_PROJECTION_HASH,
        declared_dollar_cap_usd=5.0, total_estimated_cost_usd=None,
    )
    assert next(c for c in gate_q.criteria if c.criterion == "Q-9").status == "FAIL"


# --- F: preflight fails closed on identity drift -----------------------------


def _preflight_kwargs(frozen, contract):
    return dict(
        projection=frozen["projection"], runs=frozen["runs"], verdicts=frozen["verdicts"],
        expected_projection_hash=FROZEN_PROJECTION_HASH,
        expected_verdict_set_sha256=EXPECTED_VERDICT_SET_SHA256,
        expected_packet_sha256=FROZEN_PACKET_SHA256, packet_sha256=frozen["packet_sha"],
        q5_decision=frozen["q5"], compiler_contract=contract,
        expected_compiler_contract_sha256=contract["contract_sha256"],
    )


@pytest.fixture(scope="module")
def contract_dict(frozen):
    from ingestion_bench.wiki_projection.report import build_compiler_contract

    return build_compiler_contract(
        projection_hash=FROZEN_PROJECTION_HASH, m_max=3,
        verdict_set_sha256=EXPECTED_VERDICT_SET_SHA256, declared_dollar_cap_usd=5.0,
        embedding_model="sentence-transformers/all-MiniLM-L6-v2", q5_decision=frozen["q5"],
    )


def test_preflight_passes_with_q5_and_the_compiler_contract(frozen, contract_dict):
    from ingestion_bench.wiki_projection.closure import run_preflight

    report = run_preflight(**_preflight_kwargs(frozen, contract_dict))
    assert report.all_checks_passed is True
    assert report.q5_decision_id == "STAGE7C-Q5-REPEATABILITY-THRESHOLDS"
    assert len(report.q5_content_sha256) == 64
    assert report.q5_git_blob_sha1_expected == "60f26ea7aa304490bfb88ed304f862fa0fa2588b"
    assert report.compiler_contract_sha256 == contract_dict["contract_sha256"]


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("decision", "REJECTED"),
        ("decision_id", "SOMETHING-ELSE"),
    ],
)
def test_a_changed_q5_decision_fails_preflight(frozen, contract_dict, field, bad_value):
    from ingestion_bench.wiki_projection.closure import ClosurePreflightError, run_preflight

    kwargs = _preflight_kwargs(frozen, contract_dict)
    kwargs["q5_decision"] = {**frozen["q5"], field: bad_value}
    with pytest.raises(ClosurePreflightError):
        run_preflight(**kwargs)


@pytest.mark.parametrize(
    "threshold",
    ["accepted_claim_set_pairwise_jaccard_min", "citation_exact_agreement_on_matched_accepted_claims_min",
     "false_merges_max_each_run", "runs_n"],
)
def test_a_changed_q5_threshold_fails_preflight(frozen, contract_dict, threshold):
    """A silently altered decision file must not be able to move Gate Q."""
    from ingestion_bench.wiki_projection.closure import ClosurePreflightError, run_preflight

    kwargs = _preflight_kwargs(frozen, contract_dict)
    tampered = {**frozen["q5"], "thresholds": {**frozen["q5"]["thresholds"], threshold: 0.01}}
    kwargs["q5_decision"] = tampered
    with pytest.raises(ClosurePreflightError):
        run_preflight(**kwargs)


@pytest.mark.parametrize("field", ["model_identity", "prompt_version", "prompt_sha256"])
def test_changed_run1_compiler_provenance_fails_preflight(frozen, contract_dict, field):
    from ingestion_bench.wiki_projection.closure import ClosurePreflightError, run_preflight

    runs = frozen["runs"].model_copy(deep=True)
    primary = next(p for p in runs.run_provenance if p.run_id == 1)
    setattr(primary, field, "tampered-value")
    kwargs = _preflight_kwargs(frozen, contract_dict)
    kwargs["runs"] = runs
    with pytest.raises(ClosurePreflightError):
        run_preflight(**kwargs)


@pytest.mark.parametrize("field", ["compiler_model", "prompt_version", "prompt_sha256"])
def test_a_tampered_compiler_contract_fails_preflight(frozen, contract_dict, field):
    from ingestion_bench.wiki_projection.closure import ClosurePreflightError, run_preflight

    kwargs = _preflight_kwargs(frozen, contract_dict)
    kwargs["compiler_contract"] = {**contract_dict, field: "tampered"}
    with pytest.raises(ClosurePreflightError):
        run_preflight(**kwargs)


def test_a_changed_compiler_contract_sha_fails_preflight(frozen, contract_dict):
    from ingestion_bench.wiki_projection.closure import ClosurePreflightError, run_preflight

    kwargs = _preflight_kwargs(frozen, contract_dict)
    kwargs["expected_compiler_contract_sha256"] = "0" * 64
    with pytest.raises(ClosurePreflightError):
        run_preflight(**kwargs)


def test_the_committed_q5_file_matches_its_pinned_git_blob_sha(frozen):
    """Documented hash semantics: Git blob SHA-1 identifies the exact committed
    file; the canonical content SHA-256 is what preflight verifies at runtime."""
    import subprocess

    result = subprocess.run(
        ["git", "hash-object", str(Q5_PATH)], cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        pytest.skip("git unavailable")
    assert result.stdout.strip() == "60f26ea7aa304490bfb88ed304f862fa0fa2588b"


# --- G: Q-6 endpoint matching is directional ---------------------------------


def test_q6_matching_is_directional_not_an_unordered_set(frozen, closed):
    """A direction-reversed claim must NOT be credited: the frozen Stage 7B.1
    evaluator compared subject to subject and object to object."""
    from ingestion_bench.wiki_projection.closure import compute_expected_fact_recall

    contract = frozen["contract"]
    evidence = build_evidence_alignment(contract, frozen["fixtures"])
    fact = next(f for f in contract["facts"] if f["fact_id"] == "F_obl_current")
    chunk = evidence["F_obl_current"].supporting_chunk_id

    class _Claim:
        def __init__(self, subject, obj):
            self.claim_id = "x"
            self.subject = subject
            self.object = obj
            self.supporting_chunk_ids = [chunk]

    forward = compute_expected_fact_recall(
        surviving_claims_by_facet={"k": [_Claim(fact["subject"], fact["object"])]},
        contract_facts=[fact], evidence_by_fact=evidence,
    )
    reversed_ = compute_expected_fact_recall(
        surviving_claims_by_facet={"k": [_Claim(fact["object"], fact["subject"])]},
        contract_facts=[fact], evidence_by_fact=evidence,
    )
    assert forward.numerator == 1
    assert reversed_.numerator == 0, "an unordered set comparison would wrongly credit this"


def test_q6_rule_documents_directionality_and_graph_parity(closed):
    rule = closed["recall"].mapping_rule
    assert "DIRECTIONAL" in rule
    assert "Stage 7B.1" in rule
    assert "Predicate equality is not required" in rule


def test_corrected_q6_result_is_recorded(closed):
    """Derived, not forced -- whatever it computes to is what is recorded."""
    recall = closed["recall"]
    assert recall.denominator == 15
    assert recall.numerator == 13
    assert recall.recall == pytest.approx(13 / 15)
    assert recall.strict_numerator == 9
    assert recall.surviving_claim_count == 22
    q6 = next(c for c in closed["gate_q"].criteria if c.criterion == "Q-6")
    assert q6.observed == pytest.approx(13 / 15)
    assert q6.status == "PASS"


# --- cross-cutting: nothing regressed ----------------------------------------


def test_no_graph_runtime_dependency_in_any_new_module():
    for name in ("closure.py", "facet_store.py"):
        tree = ast.parse((WIKI_ROOT / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for module in modules:
                assert "graph_retrieval_benchmark" not in module, name
                assert "hybrid_retrieval_benchmark" not in module, name
                assert "neo4j" not in module.lower(), name


def test_no_compiler_call_reachable_from_the_new_store():
    source = (WIKI_ROOT / "facet_store.py").read_text(encoding="utf-8")
    assert "compile_facet" not in source
    assert "openai" not in source.lower()


def test_the_frozen_vector_artifact_still_verifies_against_the_committed_payloads():
    """The exact d67ebfe vectors, re-verified end to end."""
    if not FROZEN_VECTORS_PATH.exists():
        pytest.skip("frozen vector artifact not present locally")
    payloads_path = REPO_ROOT / "reports" / "stage7c1_final_payloads.json"
    if not payloads_path.exists():
        pytest.skip("final payloads not present")

    vectors = json.loads(FROZEN_VECTORS_PATH.read_text(encoding="utf-8"))
    payloads = json.loads(payloads_path.read_text(encoding="utf-8"))["payloads"]
    assert len(vectors) == 22
    for entry in vectors:
        key = f"{entry['page_key']}|{entry['document_revision_id']}"
        assert entry["payload_text"] == payloads[key]["preview_text"]
        assert entry["payload_sha256"] == payloads[key]["preview_sha256"]
        assert hashlib.sha256(entry["payload_text"].encode("utf-8")).hexdigest() == entry["payload_sha256"]
        assert entry["verdict_set_sha256"] == EXPECTED_VERDICT_SET_SHA256
        assert entry["projection_hash"] == FROZEN_PROJECTION_HASH
        assert entry["embedding_model"] == "sentence-transformers/all-MiniLM-L6-v2"
        assert len(entry["embedding"]) == 384
