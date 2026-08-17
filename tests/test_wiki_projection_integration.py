"""Stage 7C.0: end-to-end projection qualification tests.

Runs the REAL contract through the REAL Stage 5A adapter + Stage 4/4.1
chunker with a deterministic FAKE embedding provider and in-memory
store/registry, then asserts:

  - authority-scoped views filter BEFORE rendering, and an authority change
    alters ONLY the view -- never a record, a membership hash, or the
    projection hash;
  - the W0 semantic control equals V and is scored by the frozen Stage 7B.0
    evaluator imported by identity;
  - rendering is deterministic, separates source from model-derived content,
    and never states an inferred relationship;
  - the frozen projection contract and manifest are stable and carry M_max,
    the sentence splitter and both D0 contracts.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ingestion_bench.cross_document_benchmark.benchmark_runner import _evaluate_question, load_contract
from ingestion_bench.cross_document_benchmark.store import InMemoryCrossDocumentVectorStore
from ingestion_bench.retrieval_baseline.embeddings import FakeEmbeddingProvider
from ingestion_bench.revision_authority.repository import InMemoryRevisionAuthorityRepository
from ingestion_bench.wiki_projection import config
from ingestion_bench.wiki_projection.benchmark import (
    W0SectionMappingError,
    run_stage7c0,
    w0_result_from_vector_result,
)
from ingestion_bench.wiki_projection.projection import authority_scoped_view, compute_projection_hash
from ingestion_bench.wiki_projection.rendering import EXACT_ANCHOR_MEANING, render_page, render_revision_page
from ingestion_bench.wiki_projection.report import (
    build_cost_ledger,
    build_projection_contract,
    build_projection_manifest,
    render_scorecard_markdown,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

CURRENT_ELIGIBLE_SYMBOLS = {"app_rev2", "svc_rev1", "obl_rev2", "ctl_rev2", "prc_rev2", "adj_rev1"}
HISTORICAL_OR_DRAFT_SYMBOLS = {"app_rev1", "obl_rev1", "ctl_rev1", "prc_rev1", "ctl_rev3"}


@pytest.fixture(scope="module")
def contract():
    return load_contract(config.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH)


@pytest.fixture(scope="module")
def stage_result():
    """ONE real run (real Docling x11, real chunker, fake embeddings,
    in-memory store/registry) shared by every test in this module."""
    return run_stage7c0(
        config.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH,
        InMemoryRevisionAuthorityRepository(),
        FakeEmbeddingProvider(),
        InMemoryCrossDocumentVectorStore(),
    )


def _revision_ids(stage_result, symbols: set[str]) -> list[str]:
    return sorted(rid for rid, symbol in stage_result.revision_symbol_by_id.items() if symbol in symbols)


# --- authority-scoped views --------------------------------------------------


def test_authority_view_hides_ineligible_revisions_only(stage_result):
    projection = stage_result.projection
    current = _revision_ids(stage_result, CURRENT_ELIGIBLE_SYMBOLS)
    view = authority_scoped_view(projection, current)

    assert set(view.eligible_revision_ids) == set(current)
    assert view.hidden_section_count == 5
    assert view.hidden_facet_count > 0

    eligible = set(current)
    for section_id in view.section_ids:
        section = next(s for s in projection.sections if s.section_id == section_id)
        assert section.document_revision_id in eligible
    for _page_key, revision_id in view.facet_keys:
        assert revision_id in eligible


def test_authority_view_never_leaks_a_link_into_an_ineligible_revision(stage_result):
    projection = stage_result.projection
    current = set(_revision_ids(stage_result, CURRENT_ELIGIBLE_SYMBOLS))
    view = authority_scoped_view(projection, sorted(current))
    for link_id in view.link_ids:
        link = next(link for link in projection.links if link.link_id == link_id)
        assert link.from_document_revision_id in current
        assert link.to_document_revision_id in current


def test_empty_authority_scope_yields_an_empty_view_never_everything(stage_result):
    view = authority_scoped_view(stage_result.projection, [])
    assert view.section_ids == []
    assert view.facet_keys == []
    assert view.link_ids == []
    assert view.visible_page_keys == []


def test_authority_change_alters_only_the_view(stage_result):
    """The hard test: an authority activation causes no reparse, no rechunk,
    no anchor rebuild, no embedding rebuild and no hash change."""
    projection = stage_result.projection
    before_hash = projection.projection_hash
    before_records = projection.model_dump_json()

    current = _revision_ids(stage_result, CURRENT_ELIGIBLE_SYMBOLS)
    historical = _revision_ids(stage_result, HISTORICAL_OR_DRAFT_SYMBOLS)

    current_view = authority_scoped_view(projection, current)
    historical_view = authority_scoped_view(projection, historical)

    assert current_view.section_ids != historical_view.section_ids
    assert current_view.facet_keys != historical_view.facet_keys

    assert projection.projection_hash == before_hash
    assert compute_projection_hash(projection) == before_hash
    assert projection.model_dump_json() == before_records


def test_membership_hashes_are_identical_under_every_authority_scope(stage_result):
    projection = stage_result.projection
    baseline = {(f.page_key, f.document_revision_id): f.membership_hash for f in projection.facets}
    for symbols in (CURRENT_ELIGIBLE_SYMBOLS, HISTORICAL_OR_DRAFT_SYMBOLS, set()):
        authority_scoped_view(projection, _revision_ids(stage_result, symbols))
        assert {(f.page_key, f.document_revision_id): f.membership_hash for f in projection.facets} == baseline


def test_a_page_keeps_all_facets_but_shows_only_eligible_ones(stage_result):
    """Authority alters VISIBILITY, never membership: Payment Settlement keeps
    3 facets while only 2 are eligible under a current-intent scope."""
    projection = stage_result.projection
    all_facets = [f for f in projection.facets if f.page_key == "PHRASE:payment settlement"]
    assert len(all_facets) == 3

    current = set(_revision_ids(stage_result, CURRENT_ELIGIBLE_SYMBOLS))
    visible = [f for f in all_facets if f.document_revision_id in current]
    assert len(visible) == 2
    assert len([f for f in projection.facets if f.page_key == "PHRASE:payment settlement"]) == 3


# --- W0 semantic control -----------------------------------------------------


def test_w0_semantic_control_equals_v(stage_result):
    """W0 ~ V is a SUCCESSFUL control outcome: a W0 section is 1:1 with a
    chunk and reuses that chunk's existing embedding."""
    control = stage_result.w0_control
    assert control.questions_total == 12
    assert control.identical_to_v_count == 12
    assert control.w0_equals_v is True
    assert control.v_outcome_counts == control.w0_outcome_counts


def test_w0_control_uses_the_frozen_stage7b0_evaluator_by_identity(stage_result):
    expected = f"{_evaluate_question.__module__}.{_evaluate_question.__qualname__}"
    assert stage_result.w0_control.evaluator_identity == expected
    assert "cross_document_benchmark" in expected


def test_w0_control_has_zero_authority_leakage(stage_result):
    assert stage_result.w0_control.total_authority_leakage == 0
    for question in stage_result.w0_control.questions:
        assert question.v_authority_leakage == 0
        assert question.w0_authority_leakage == 0


def test_w0_never_exceeds_the_questions_own_final_k(stage_result):
    for question in stage_result.w0_control.questions:
        assert len(question.w0_hit_chunk_ids) <= question.top_k
        assert len(question.w0_hit_chunk_ids) == len(question.v_hit_chunk_ids)


def test_w0_mapping_goes_through_the_section_view(stage_result):
    for question in stage_result.w0_control.questions:
        assert len(question.w0_section_ids) == len(question.w0_hit_chunk_ids)


def test_w0_mapping_fails_loudly_when_the_section_view_is_incomplete(stage_result):
    """A broken 1:1 view must raise, never silently reproduce V."""
    projection = stage_result.projection
    broken = projection.model_copy(deep=True)
    broken.sections = broken.sections[:1]

    class _FakeHit:
        chunk_id = "a" * 64

        def model_copy(self, **_kwargs):
            return self

    class _FakeResult:
        hits = [_FakeHit()]

        def model_copy(self, **_kwargs):
            return self

    with pytest.raises(W0SectionMappingError):
        w0_result_from_vector_result(broken, _FakeResult(), 3)


# --- rendering ---------------------------------------------------------------


def test_rendering_is_byte_deterministic(stage_result):
    projection = stage_result.projection
    current = _revision_ids(stage_result, CURRENT_ELIGIBLE_SYMBOLS)
    for page_key in ("IDENT:C-88", "PHRASE:payment settlement", "IDENT:P-205"):
        first = render_page(projection, page_key, eligible_revision_ids=current,
                            revision_symbol_by_id=stage_result.revision_symbol_by_id)
        second = render_page(projection, page_key, eligible_revision_ids=current,
                             revision_symbol_by_id=stage_result.revision_symbol_by_id)
        assert first == second


def test_rendering_separates_source_from_model_derived_content(stage_result):
    page = render_page(
        stage_result.projection, "IDENT:O-31",
        eligible_revision_ids=_revision_ids(stage_result, CURRENT_ELIGIBLE_SYMBOLS),
        revision_symbol_by_id=stage_result.revision_symbol_by_id,
    )
    assert "**A — source-authoritative content**" in page
    assert "**B — model-derived content**" in page
    assert "Stage 7C.0 makes zero LLM calls" in page


def test_rendering_never_states_an_inferred_relationship(stage_result):
    """An exact-anchor link must be rendered as co-occurrence only."""
    projection = stage_result.projection
    current = _revision_ids(stage_result, CURRENT_ELIGIBLE_SYMBOLS)
    for page in projection.page_identities:
        rendered = render_page(projection, page.page_key, eligible_revision_ids=current,
                               revision_symbol_by_id=stage_result.revision_symbol_by_id)
        if "exact_anchor links" in rendered:
            assert EXACT_ANCHOR_MEANING in rendered
        for inferred in ("is governed by", "is satisfied by", "is implemented through", "supports the"):
            navigation = rendered.split("## Navigation", 1)[-1]
            assert inferred not in navigation


def test_rendering_applies_authority_before_rendering(stage_result):
    projection = stage_result.projection
    current = _revision_ids(stage_result, CURRENT_ELIGIBLE_SYMBOLS)
    page = render_page(projection, "PHRASE:payment settlement", eligible_revision_ids=current,
                       revision_symbol_by_id=stage_result.revision_symbol_by_id)
    assert "app_rev1" not in page
    assert "APP-224499" not in page
    assert "app_rev2" in page


def test_representative_owner_pages_render(stage_result):
    projection = stage_result.projection
    current = _revision_ids(stage_result, CURRENT_ELIGIBLE_SYMBOLS)
    for page_key in ("IDENT:APP-224510", "PHRASE:payment settlement", "IDENT:O-31", "IDENT:C-88", "IDENT:P-205"):
        assert any(p.page_key == page_key for p in projection.page_identities)
        rendered = render_page(projection, page_key, eligible_revision_ids=current,
                               revision_symbol_by_id=stage_result.revision_symbol_by_id)
        assert rendered.startswith("# ")
        assert "membership basis" in rendered


def test_revision_page_renders_without_a_currency_flag(stage_result):
    projection = stage_result.projection
    current = _revision_ids(stage_result, CURRENT_ELIGIBLE_SYMBOLS)
    rendered = render_revision_page(projection, projection.revision_pages[0].document_revision_id,
                                    eligible_revision_ids=current)
    assert "authority is resolved at query time, never stored" in rendered


# --- frozen contract, manifest, ledger, scorecard ----------------------------


def test_projection_contract_is_stable_and_carries_the_frozen_rules(stage_result):
    first = build_projection_contract(stage_result.projection)
    assert first == build_projection_contract(stage_result.projection)
    assert first["status"] == "frozen"
    assert first["llm_calls"] == 0
    assert first["measured_projection_properties"]["m_max"] == 3
    assert first["measured_projection_properties"]["candidate_ceiling_evaluated_in_stage"] == "7C.2"
    assert first["membership_rule"]["may_not_depend_on"]
    assert first["sentence_splitter"]["version"] == "wiki_sentence_splitter_v1"
    assert first["d0_contract"]["executed_in_stage_7c0"] is False
    assert first["anchor_lanes"]["lane_3_heading_title"]["creates_page_identity"] is False
    assert len(first["contract_sha256"]) == 64


def test_committed_contract_file_matches_the_rebuilt_contract(stage_result):
    """The frozen `contracts/wiki_projection_v1.json` must still describe the
    projection the code produces."""
    import json

    committed = json.loads(config.WIKI_PROJECTION_CONTRACT_PATH.read_text(encoding="utf-8"))
    assert committed["contract_sha256"] == build_projection_contract(stage_result.projection)["contract_sha256"]


def test_manifest_is_stable_and_carries_the_required_inventories(stage_result):
    first = build_projection_manifest(stage_result)
    assert first["manifest_sha256"] == build_projection_manifest(stage_result)["manifest_sha256"]
    for key in (
        "anchor_inventory", "phrase_anchor_inventory", "page_identity_inventory", "facet_membership_inventory",
        "page_to_revision_facet_counts", "c88_c88a_separation_proof", "ambiguity_flags", "link_counts",
        "provenance_completeness", "m_max", "sentence_splitter", "d0_contract", "deterministic_build_hashes",
    ):
        assert key in first
    assert first["c88_c88a_separation_proof"]["distinct_anchor_ids"] is True
    assert first["c88_c88a_separation_proof"]["shared_chunk_ids"] == []
    assert first["link_counts"]["is_authoritative_lineage_true_count"] == 0
    assert first["provenance_completeness"]["postings_with_source_ref"] == first["provenance_completeness"]["postings_total"]


def test_cost_ledger_records_zero_llm_calls_and_no_invented_values(stage_result):
    ledger = build_cost_ledger(stage_result, module_files=["a.py"], loc_by_file={"a.py": 10})
    assert ledger["llm_calls"] == 0
    assert ledger["embedding_calls_attributable_to_7c0"] == 0
    assert ledger["authority_change_rebuild_cost"]["projection_hash_change"] == 0
    assert "edib_stage7c_facet (Stage 7C.1)" in ledger["database_tables_deliberately_not_created"]
    serialized = str(ledger)
    assert "person-day" not in serialized and "person_day" not in serialized


def test_scorecard_states_the_control_and_scope_honestly(stage_result):
    scorecard = render_scorecard_markdown(stage_result, build_projection_manifest(stage_result))
    assert "successful control outcome" in scorecard
    assert "W0 semantic control is NOT D0" in scorecard
    assert "Zero LLM calls" in scorecard
    assert "measured property of the completed projection" in scorecard
    assert "frozen, not executed" in scorecard


# --- cross-process determinism ----------------------------------------------


def test_projection_hash_is_identical_across_processes_and_hash_seeds():
    """Same-process rebuilds cannot detect PYTHONHASHSEED-dependent ordering,
    because the seed is fixed for a process's lifetime. This spawns real child
    processes with different seeds and diffs the projection hash, which is the
    only way to prove the build order is genuinely deterministic."""
    import os
    import subprocess
    import sys

    code = (
        "from ingestion_bench.cross_document_benchmark.benchmark_runner import load_contract;"
        "from ingestion_bench.cross_document_benchmark.fixtures import load_all_revision_fixtures;"
        "from ingestion_bench.wiki_projection import config;"
        "from ingestion_bench.wiki_projection.projection import build_projection;"
        "c = load_contract(config.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH);"
        "p = build_projection(load_all_revision_fixtures(c['fixtures']));"
        "print(p.projection_hash)"
    )
    hashes = []
    for seed in ("0", "1", "12345"):
        env = dict(os.environ)
        env["PYTHONHASHSEED"] = seed
        env["PYTHONPATH"] = str(REPO_ROOT / "src") + os.pathsep + str(REPO_ROOT / "fixtures")
        completed = subprocess.run(
            [sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=600
        )
        assert completed.returncode == 0, f"seed={seed} failed:\n{completed.stderr}"
        hashes.append(completed.stdout.strip().splitlines()[-1])

    assert len(set(hashes)) == 1, f"projection hash varies across hash seeds: {hashes}"
    assert len(hashes[0]) == 64
