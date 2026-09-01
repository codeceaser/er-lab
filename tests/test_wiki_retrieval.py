"""Stage 7C.2: retrieval / navigation qualification invariants.

Tests assert INVARIANTS, never a desired winner. Nothing here checks that any
arm beats another; they check that each arm is the thing it claims to be, that
authority is applied before ranking, that the frozen artifacts are untouched,
and that benchmark truth is unreachable from ordinary retrieval.

Deterministic: fake embeddings, in-memory stores, no network, no model call.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from ingestion_bench.cross_document_benchmark.benchmark_runner import _evaluate_question, load_contract
from ingestion_bench.cross_document_benchmark.fixtures import load_all_revision_fixtures
from ingestion_bench.wiki_projection import config
from ingestion_bench.wiki_projection.facet_store import FacetEmbeddingRow, InMemoryStage7C1Store
from ingestion_bench.wiki_projection.navigation import (
    ARM_LINK_SETS,
    HOP_BUDGET_B,
    NON_QUALIFYING_LABEL,
    TRAVERSABLE_ANCHOR_KINDS,
    W1_DERIVED_ARMS,
    Navigator,
    candidate_ceiling,
)
from ingestion_bench.wiki_projection.projection import build_projection
from ingestion_bench.wiki_projection.retrieval import run_arm, seed_d0, seed_w1
from ingestion_bench.wiki_projection.validation import DerivedLink

REPO_ROOT = Path(__file__).resolve().parent.parent
WIKI_ROOT = REPO_ROOT / "src" / "ingestion_bench" / "wiki_projection"
SCRIPT = REPO_ROOT / "scripts" / "run_stage7c2_wiki_retrieval.py"

FROZEN_PROJECTION_HASH = "4162fa515cf29d09391c0d963b76c7e63b1d454c4439ee0568805d1a31e3b613"
FROZEN_VERDICT_SHA = "d49cc8643388f830ffbcf5097faa8335a40c366b06b8f54a176aa978b06158bd"
FROZEN_CONTRACT_SHA = "35ccad855b10e6e8c08f6699136dff590dbd37abcef3c64147500a94edcad793"
FROZEN_EMBEDDING_SET_SHA = "bbc233f68a6b7ccdbdebabf9dfe6e35f3a13ee27309077100aec2662e921a5a0"

VECTORS_PATH = REPO_ROOT / "artifacts" / "stage7c1_closure" / "facet_embeddings.json"
PAYLOADS_PATH = REPO_ROOT / "reports" / "stage7c1_final_payloads.json"
RESULTS_PATH = REPO_ROOT / "reports" / "stage7c_wiki_results.json"


@pytest.fixture(scope="module")
def projection():
    contract = load_contract(config.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH)
    return build_projection(load_all_revision_fixtures(contract["fixtures"]))


@pytest.fixture(scope="module")
def frozen_vectors():
    if not VECTORS_PATH.exists():
        pytest.skip("frozen vectors not present")
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
        for r in json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
    ]


@pytest.fixture(scope="module")
def derived_links():
    if not PAYLOADS_PATH.exists():
        pytest.skip("final payloads not present")
    return [
        DerivedLink.model_validate(link)
        for link in json.loads(PAYLOADS_PATH.read_text(encoding="utf-8"))["final_derived_links"]
    ]


@pytest.fixture(scope="module")
def navigator(projection, derived_links):
    return Navigator(projection, derived_links=derived_links)


# --- 1/2: frozen basis --------------------------------------------------------


def test_all_frozen_hashes_match(projection):
    contract = json.loads((REPO_ROOT / "contracts" / "wiki_compiler_v1.json").read_text(encoding="utf-8"))
    manifest = json.loads(
        (REPO_ROOT / "reports" / "stage7c1_final_embedding_manifest.json").read_text(encoding="utf-8")
    )
    assert projection.projection_hash == FROZEN_PROJECTION_HASH
    assert contract["contract_sha256"] == FROZEN_CONTRACT_SHA
    assert contract["owner_adjudication"]["verdict_set_sha256"] == FROZEN_VERDICT_SHA
    assert manifest["embedding_set_sha256"] == FROZEN_EMBEDDING_SET_SHA


def test_frozen_vectors_load_without_an_embedding_provider(frozen_vectors):
    """Stage 7C.2 reads the frozen 22-vector set; it never rebuilds it."""
    assert len(frozen_vectors) == 22
    assert all(len(v.embedding) == 384 for v in frozen_vectors)
    assert all(v.projection_hash == FROZEN_PROJECTION_HASH for v in frozen_vectors)
    assert all(v.verdict_set_sha256 == FROZEN_VERDICT_SHA for v in frozen_vectors)


def test_frozen_derived_links_are_the_thirty_post_pass3_links(derived_links):
    assert len(derived_links) == 30
    assert all(link.is_authoritative_lineage is False for link in derived_links)


# --- 3/4: no compiler, no page vector ----------------------------------------


def test_no_compiler_or_extractor_call_is_reachable(navigator):
    for path in (WIKI_ROOT / "retrieval.py", WIKI_ROOT / "navigation.py",
                 WIKI_ROOT / "stage7c2_report.py", SCRIPT):
        source = path.read_text(encoding="utf-8")
        assert "compile_facet" not in source, path.name
        assert "OpenAIFacetCompiler" not in source, path.name
        assert "RelationshipExtractor" not in source, path.name
        tree = ast.parse(source)
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for module in modules:
                assert "openai" not in module.lower(), path.name
                assert "graph_retrieval_benchmark" not in module, path.name
                assert "hybrid_retrieval_benchmark" not in module, path.name


def test_no_page_level_vector_exists(frozen_vectors):
    keys = {(v.page_key, v.document_revision_id) for v in frozen_vectors}
    assert len(keys) == 22, "one vector per FACET"
    assert len({v.page_key for v in frozen_vectors}) == 13, "13 pages, but no page-level vector"


# --- 5/6: authority first -----------------------------------------------------


def test_authority_filtering_precedes_ranking_in_the_facet_store(frozen_vectors):
    store = InMemoryStage7C1Store()
    store.upsert_facet_embeddings(frozen_vectors)
    one = frozen_vectors[0].document_revision_id
    expected = sum(1 for v in frozen_vectors if v.document_revision_id == one)
    hits = store.search_eligible_facets(
        query_vector=frozen_vectors[0].embedding, eligible_revision_ids=[one], top_k=99
    )
    assert len(hits) == expected
    assert all(row.document_revision_id == one for row, _ in hits)


def test_empty_eligible_set_returns_nothing(frozen_vectors, projection):
    store = InMemoryStage7C1Store()
    store.upsert_facet_embeddings(frozen_vectors)
    assert store.search_eligible_facets(
        query_vector=frozen_vectors[0].embedding, eligible_revision_ids=[], top_k=5
    ) == []
    seeds, _ = seed_w1(
        facet_rows=frozen_vectors, query_vector=frozen_vectors[0].embedding, eligible=set(), p_seed=3
    )
    assert seeds == []
    assert seed_d0(
        projection=projection, ranked_chunk_ids=[s.chunk_id for s in projection.sections],
        eligible=set(), p_seed=3,
    ) == []


def test_no_ineligible_facet_influences_seed_or_expansion(projection, frozen_vectors, navigator):
    eligible = {projection.facets[0].document_revision_id}
    seeds, _ = seed_w1(
        facet_rows=frozen_vectors, query_vector=frozen_vectors[0].embedding,
        eligible=eligible, p_seed=5,
    )
    for seed in seeds:
        facet_keys, chunk_ids = navigator.expand_page(seed.page_key, eligible)
        for key in facet_keys:
            assert key.rsplit("|", 1)[-1] in eligible
        for chunk_id in chunk_ids:
            section = next(s for s in projection.sections if s.chunk_id == chunk_id)
            assert section.document_revision_id in eligible


# --- 7: the scorer is reused by identity -------------------------------------


def test_scorer_is_the_frozen_one_imported_by_identity():
    from ingestion_bench.wiki_projection import stage7c2_report

    assert stage7c2_report._evaluate_question is _evaluate_question
    assert _evaluate_question.__module__ == "ingestion_bench.cross_document_benchmark.benchmark_runner"


# --- 8/9/10/11: the arms are what they claim ---------------------------------


def test_d0_reads_no_w1_derived_field(projection):
    """D0's seed is a pure function of ranked chunks + frozen postings; it
    cannot receive a facet embedding, claim, alias or summary."""
    import inspect

    signature = set(inspect.signature(seed_d0).parameters)
    assert signature == {"projection", "ranked_chunk_ids", "eligible", "p_seed"}
    for forbidden in ("facet_row", "facet_vector", "claim", "alias", "summary", "payload"):
        assert not any(forbidden in p for p in signature)


def test_w1_d_never_traverses_a_claim_derived_link(projection, navigator, frozen_vectors):
    eligible = {f.document_revision_id for f in projection.facets}
    assert "claim_derived" not in ARM_LINK_SETS["W1-D"]
    for page in projection.page_identities:
        neighbours, _ = navigator.expose_neighbours(page.page_key, arm="W1-D", eligible=eligible)
        assert all(n.link_type != "claim_derived" for n in neighbours)


def test_w1_full_uses_only_the_frozen_post_pass3_claim_links(projection, navigator, derived_links):
    eligible = {f.document_revision_id for f in projection.facets}
    frozen_ids = {link.link_id for link in derived_links}
    seen = set()
    for page in projection.page_identities:
        neighbours, _ = navigator.expose_neighbours(page.page_key, arm="W1-FULL", eligible=eligible)
        for neighbour in neighbours:
            if neighbour.link_type == "claim_derived":
                seen.add(neighbour.link_id)
                assert neighbour.link_id in frozen_ids
                assert neighbour.predicate, "a claim hop carries its verbatim predicate"
                assert neighbour.claim_id
                assert neighbour.is_authoritative_lineage is False
    assert seen, "W1-FULL must expose at least one frozen claim-derived link"


def test_n_advisory_is_diagnostic_and_a_superset(projection):
    assert ARM_LINK_SETS["N_advisory"] > ARM_LINK_SETS["W1-FULL"]
    assert "advisory_semantic" in ARM_LINK_SETS["N_advisory"]
    assert "N_advisory" in W1_DERIVED_ARMS


# --- 12/13: traversable anchor kinds -----------------------------------------


def test_heading_anchors_are_not_traversable(projection, navigator):
    assert "heading_title" not in TRAVERSABLE_ANCHOR_KINDS
    eligible = {f.document_revision_id for f in projection.facets}
    heading_ids = {a.anchor_id for a in projection.anchors if a.anchor_kind == "heading_title"}
    assert heading_ids, "the corpus has heading anchors"
    for page in projection.page_identities:
        neighbours, _ = navigator.expose_neighbours(page.page_key, arm="W1-FULL", eligible=eligible)
        assert all(n.anchor_id not in heading_ids for n in neighbours)


def test_identifier_and_phrase_anchors_are_traversable():
    assert TRAVERSABLE_ANCHOR_KINDS == frozenset({"identifier", "phrase"})


# --- 14/15/16/17: bounds ------------------------------------------------------


def test_hop_budget_is_six_and_enforced(projection, navigator, frozen_vectors):
    assert HOP_BUDGET_B == 6
    eligible = {f.document_revision_id for f in projection.facets}
    seeds, _ = seed_w1(
        facet_rows=frozen_vectors, query_vector=frozen_vectors[0].embedding, eligible=eligible, p_seed=5
    )
    result = run_arm(
        arm="W1-FULL", question_id="T", query_text="test", query_vector=frozen_vectors[0].embedding,
        top_k=5, eligible_revision_ids=sorted(eligible), projection=projection, navigator=navigator,
        seeds=seeds, chunk_vectors={}, facet_vectors_by_page={},
    )
    assert result.navigation.hops_taken <= HOP_BUDGET_B


def test_p_seed_equals_k(projection, frozen_vectors):
    eligible = {f.document_revision_id for f in projection.facets}
    for k in (3, 4, 5):
        seeds, _ = seed_w1(
            facet_rows=frozen_vectors, query_vector=frozen_vectors[0].embedding,
            eligible=eligible, p_seed=k,
        )
        assert len(seeds) <= k


def test_candidate_ceiling_uses_the_frozen_values():
    # C = (P_seed + B) x M_max x F_max, with M_max = 3 and F_max = 12 frozen.
    assert candidate_ceiling(3) == (3 + 6) * 3 * 12
    assert candidate_ceiling(5) == (5 + 6) * 3 * 12


def test_no_vector_backfill_final_is_a_subset_of_reached(projection, navigator, frozen_vectors):
    eligible = {f.document_revision_id for f in projection.facets}
    seeds, _ = seed_w1(
        facet_rows=frozen_vectors, query_vector=frozen_vectors[0].embedding, eligible=eligible, p_seed=3
    )
    result = run_arm(
        arm="W1-FULL", question_id="T", query_text="test", query_vector=frozen_vectors[0].embedding,
        top_k=3, eligible_revision_ids=sorted(eligible), projection=projection, navigator=navigator,
        seeds=seeds, chunk_vectors={}, facet_vectors_by_page={},
    )
    assert set(result.final_chunk_ids) <= set(result.navigation.reached_chunk_ids)
    assert set(result.tier2_chunk_ids) <= set(result.navigation.reached_chunk_ids)


# --- 18/19/20/21/22: the final-K policy --------------------------------------


def test_tier1_precedes_tier2_and_tier2_holds_only_reached_chunks(projection, navigator, frozen_vectors):
    eligible = {f.document_revision_id for f in projection.facets}
    seeds, _ = seed_w1(
        facet_rows=frozen_vectors, query_vector=frozen_vectors[0].embedding, eligible=eligible, p_seed=3
    )
    result = run_arm(
        arm="D0", question_id="T", query_text="test", query_vector=frozen_vectors[0].embedding,
        top_k=5, eligible_revision_ids=sorted(eligible), projection=projection, navigator=navigator,
        seeds=seeds, chunk_vectors={}, facet_vectors_by_page={},
    )
    combined = result.tier1_chunk_ids + result.tier2_chunk_ids
    assert result.final_chunk_ids == combined[: result.top_k]
    assert not (set(result.tier1_chunk_ids) & set(result.tier2_chunk_ids))
    assert set(result.tier2_chunk_ids) <= set(result.navigation.reached_chunk_ids)


def test_final_k_never_exceeds_the_questions_frozen_k():
    if not RESULTS_PATH.exists():
        pytest.skip("measured results not present")
    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    for question in results["per_question"].values():
        for arm, metrics in question["arms"].items():
            assert len(metrics["returned_chunk_ids"]) <= question["top_k"], arm


def test_links_are_never_returned_as_evidence(projection, navigator, frozen_vectors):
    """Only CanonicalChunks are evidence; a link id must never appear in one."""
    eligible = {f.document_revision_id for f in projection.facets}
    chunk_ids = {s.chunk_id for s in projection.sections}
    seeds, _ = seed_w1(
        facet_rows=frozen_vectors, query_vector=frozen_vectors[0].embedding, eligible=eligible, p_seed=3
    )
    result = run_arm(
        arm="W1-FULL", question_id="T", query_text="test", query_vector=frozen_vectors[0].embedding,
        top_k=5, eligible_revision_ids=sorted(eligible), projection=projection, navigator=navigator,
        seeds=seeds, chunk_vectors={}, facet_vectors_by_page={},
    )
    assert set(result.final_chunk_ids) <= chunk_ids
    link_ids = {link.link_id for link in projection.links}
    assert not (set(result.final_chunk_ids) & link_ids)


def test_all_evidence_is_a_canonical_chunk_with_provenance(projection):
    if not RESULTS_PATH.exists():
        pytest.skip("measured results not present")
    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    sections = {s.chunk_id: s for s in projection.sections}
    for question in results["per_question"].values():
        for metrics in question["arms"].values():
            for chunk_id in metrics["returned_chunk_ids"]:
                assert chunk_id in sections
                assert sections[chunk_id].source_refs
                assert len(sections[chunk_id].content_sha256) == 64


# --- 23: authority leakage hard-fails ----------------------------------------


def test_authority_leakage_is_zero_across_every_arm():
    if not RESULTS_PATH.exists():
        pytest.skip("measured results not present")
    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    assert results["summary"]["total_authority_leakage"] == 0
    for question in results["per_question"].values():
        for arm, metrics in question["arms"].items():
            assert metrics["authority_leakage_count"] == 0, f"{arm} leaked authority"


# --- 24: truth isolation ------------------------------------------------------


def test_ordinary_retrieval_cannot_read_benchmark_truth():
    """Only the frozen scorer and the explicitly truth-informed suppression
    probe may touch truth."""
    for name in ("retrieval.py", "navigation.py"):
        source = (WIKI_ROOT / name).read_text(encoding="utf-8")
        for token in ("required_fact_ids", "forbidden_fact_ids", "expected_relationship_chain",
                      "expected_supporting_passage"):
            assert token not in source, f"{name} reads benchmark truth: {token}"


def test_truth_is_confined_to_the_scorer_and_the_labelled_probe():
    source = (WIKI_ROOT / "stage7c2_report.py").read_text(encoding="utf-8")
    # required_fact_ids appears ONLY inside the suppression block, which is
    # labelled truth-informed.
    assert "TRUTH-INFORMED" in source
    truth_uses = [line for line in source.splitlines() if "required_fact_ids" in line]
    assert len(truth_uses) == 1, "truth must be read in exactly one, labelled place"


# --- 25/26: the suppression probe --------------------------------------------


def test_suppression_probe_mutates_nothing(projection, navigator, derived_links, frozen_vectors):
    before_links = [link.model_dump_json() for link in derived_links]
    before_hash = projection.projection_hash
    eligible = {f.document_revision_id for f in projection.facets}
    seeds, _ = seed_w1(
        facet_rows=frozen_vectors, query_vector=frozen_vectors[0].embedding, eligible=eligible, p_seed=3
    )
    run_arm(
        arm="W1-FULL", question_id="T", query_text="test", query_vector=frozen_vectors[0].embedding,
        top_k=3, eligible_revision_ids=sorted(eligible), projection=projection, navigator=navigator,
        seeds=seeds, chunk_vectors={}, facet_vectors_by_page={},
        suppressed_link_ids={derived_links[0].link_id},
    )
    assert [link.model_dump_json() for link in derived_links] == before_links
    assert projection.projection_hash == before_hash
    assert len(navigator.derived_links) == 30


def test_suppression_is_read_time_only_and_hides_the_named_link(projection, navigator, derived_links):
    eligible = {f.document_revision_id for f in projection.facets}
    target = derived_links[0]
    origin = target.subject_page_key if target.traversal_direction == "forward" else target.object_page_key
    before, _ = navigator.expose_neighbours(origin, arm="W1-FULL", eligible=eligible)
    after, _ = navigator.expose_neighbours(
        origin, arm="W1-FULL", eligible=eligible, suppressed_link_ids={target.link_id}
    )
    assert target.link_id in {n.link_id for n in before}
    assert target.link_id not in {n.link_id for n in after}


def test_suppression_runs_only_on_the_three_target_questions():
    if not RESULTS_PATH.exists():
        pytest.skip("measured results not present")
    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    probed = set(results["suppression_diagnostic"])
    assert probed, "the probe must run"
    assert all(q.split("_")[0] in {"Q04", "Q06", "Q07"} for q in probed)
    for probe in results["suppression_diagnostic"].values():
        assert probe["label"] == "TRUTH-INFORMED / DIAGNOSTIC ONLY / NOT GATE-A ADMISSIBLE"


# --- 27/28/29: attribution instrumentation ------------------------------------


def test_seed_overlap_and_branch_divergence_vs_d0_are_emitted():
    if not RESULTS_PATH.exists():
        pytest.skip("measured results not present")
    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    for question in results["per_question"].values():
        for arm in ("W1-D", "W1-FULL"):
            metrics = question["arms"][arm]
            assert "seed_page_overlap_vs_D0" in metrics
            assert "branch_order_divergence_vs_D0" in metrics


def test_all_three_attribution_deltas_are_emitted():
    if not RESULTS_PATH.exists():
        pytest.skip("measured results not present")
    attribution = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))["attribution"]
    for key in ("W1-D_vs_D0", "W1-FULL_vs_W1-D", "W1-FULL_vs_D0"):
        assert key in attribution
        assert attribution[key]["verdict"]
        assert attribution[key]["measures"]
    assert "only" in attribution["prohibited_inference"].lower()


# --- 30/31: labelling ---------------------------------------------------------


def test_every_w1_result_carries_the_non_qualifying_label():
    if not RESULTS_PATH.exists():
        pytest.skip("measured results not present")
    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    for question in results["per_question"].values():
        for arm in ("W1-D", "W1-FULL", "N_advisory"):
            assert question["arms"][arm]["label"] == NON_QUALIFYING_LABEL, arm
    assert "UNREACHABLE" in results["gate_a_status"]


def test_d0_does_not_carry_the_non_qualifying_label():
    if not RESULTS_PATH.exists():
        pytest.skip("measured results not present")
    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    for question in results["per_question"].values():
        assert "label" not in question["arms"]["D0"]
        assert "label" not in question["arms"]["V"]
    assert results["d0_qualifying"] is True


# --- 32/33: determinism and frozen-artifact integrity ------------------------


def test_arm_execution_is_deterministic(projection, navigator, frozen_vectors):
    eligible = {f.document_revision_id for f in projection.facets}

    def once():
        seeds, _ = seed_w1(
            facet_rows=frozen_vectors, query_vector=frozen_vectors[0].embedding,
            eligible=eligible, p_seed=3,
        )
        result = run_arm(
            arm="W1-FULL", question_id="T", query_text="test",
            query_vector=frozen_vectors[0].embedding, top_k=3,
            eligible_revision_ids=sorted(eligible), projection=projection, navigator=navigator,
            seeds=seeds, chunk_vectors={}, facet_vectors_by_page={},
        )
        return (result.final_chunk_ids, result.tier1_chunk_ids, result.tier2_chunk_ids,
                [h.model_dump_json() for h in result.navigation.path])

    assert once() == once()


def test_stage_7c0_and_7c1_artifacts_are_not_mutated(projection):
    """Stage 7C.2 is read-only over every frozen input."""
    import hashlib

    expected = {
        "reports/stage7c1_compilation_runs.json": "5cb7c3bb856ee502",
        "reports/stage7c1_owner_adjudication_packet.json": "ff2a4741762c99b3",
        "contracts/wiki_projection_v1.json": "4a911bb24226ed6a",
    }
    for relative, prefix in expected.items():
        path = REPO_ROOT / relative
        if not path.exists():
            pytest.skip(f"{relative} not present")
        assert hashlib.sha256(path.read_bytes()).hexdigest().startswith(prefix), relative
    assert projection.projection_hash == FROZEN_PROJECTION_HASH


def test_the_runner_never_writes_a_frozen_artifact():
    source = SCRIPT.read_text(encoding="utf-8")
    for frozen_name in (
        "stage7c1_compilation_runs.json", "stage7c1_owner_adjudication_packet",
        "wiki_projection_v1.json", "wiki_compiler_v1.json", "STAGE7C_WIKI_PLAN.md",
        "facet_embeddings.json", "stage7c1_final_payloads.json",
    ):
        for line in source.splitlines():
            if frozen_name in line:
                assert "write_text" not in line, f"runner writes {frozen_name}: {line.strip()}"


def test_small_corpus_caveat_is_carried_in_the_results():
    if not RESULTS_PATH.exists():
        pytest.skip("measured results not present")
    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    assert "DOES NOT TEST ENTERPRISE-SCALE" in results["small_corpus_caveat"]


def test_graph_attribution_is_read_only_and_carries_the_prohibition():
    if not RESULTS_PATH.exists():
        pytest.skip("measured results not present")
    graph = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))["graph_attribution"]
    assert graph["read_only"] is True and graph["graph_not_rerun"] is True
    assert graph["graph"]["expected_fact_edge_recall"] == "12/15 = 0.80"
    assert graph["graph"]["extracted_edge_precision"] == 0.86
    assert "inherently more reliable" in graph["prohibited_claim"]
