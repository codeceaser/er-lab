"""Stage 7C.0: deterministic Wiki projection tests.

Covers identity/anchor extraction, deterministic membership and its hard
independence invariant, C-88 / C-88a separation, determinism and hashing,
M_max derivation, the frozen sentence splitter, the frozen D0 seed and
prioritizer contracts, and the purity guards (no benchmark truth, no Graph
runtime dependency, no LLM call).

Deterministic: real Docling conversion of the tracked DOCX fixtures, no
embeddings, no network, no database, no model call.
"""

from __future__ import annotations

import ast
import copy
from pathlib import Path

import pytest

from ingestion_bench.cross_document_benchmark.benchmark_runner import load_contract
from ingestion_bench.cross_document_benchmark.fixtures import load_all_revision_fixtures
from ingestion_bench.wiki_projection import config, identity
from ingestion_bench.wiki_projection.projection import (
    build_projection,
    compute_m_max,
    compute_projection_hash,
    d0_branch_order,
    d0_contract_identity,
    d0_seed_pages_from_ranked_chunks,
    _build_facets,
)
from ingestion_bench.wiki_projection.store import InMemoryWikiProjectionStore

REPO_ROOT = Path(__file__).resolve().parent.parent
WIKI_ROOT = REPO_ROOT / "src" / "ingestion_bench" / "wiki_projection"

# The deterministic BUILD path. `benchmark.py` is excluded from the
# truth-access guard on purpose: it hosts the W0 semantic control, which is
# scored by the frozen Stage 7B.0 evaluator and therefore legitimately reaches
# evaluation truth -- but only AFTER the projection is built, and never inside
# it.
BUILD_PATH_MODULES = ["identity.py", "model.py", "projection.py", "store.py", "pg_store.py", "rendering.py"]


@pytest.fixture(scope="module")
def contract():
    return load_contract(config.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH)


@pytest.fixture(scope="module")
def fixtures(contract):
    return load_all_revision_fixtures(contract["fixtures"])


@pytest.fixture(scope="module")
def projection(fixtures):
    return build_projection(fixtures)


# --- identity primitives -----------------------------------------------------


def test_identifiers_in_uppercases_and_separates_c88_from_c88a():
    assert identity.identifiers_in("Control C-88 is implemented") == {"C-88"}
    assert identity.identifiers_in("Control C-88a is implemented") == {"C-88A"}
    assert identity.identifiers_in("C-88 and C-88a") == {"C-88", "C-88A"}


def test_identifier_occurrences_carry_exact_spans():
    text = "Application APP-224510 supports the Payment Settlement business service."
    occurrences = identity.identifier_occurrences(text)
    assert [o.normalized for o in occurrences] == ["APP-224510"]
    occurrence = occurrences[0]
    assert text[occurrence.start_char : occurrence.end_char] == "APP-224510"


def test_phrase_candidates_break_on_stop_words_and_keep_payment_settlement():
    """The stop-listed 'The' must BREAK the run, not poison the candidate --
    otherwise this corpus's only cross-document phrase anchor is destroyed."""
    text = "The Payment Settlement business service is governed by Obligation O-31."
    keys = {c.normalized for c in identity.phrase_candidates(text)}
    assert "payment settlement" in keys
    assert not any(key.startswith("the ") for key in keys)


def test_phrase_candidates_never_span_a_sentence_boundary():
    text = "Control C-77 is implemented through Procedure P-301. Procedure P-301 is current."
    for candidate in identity.phrase_candidates(text):
        assert "." not in candidate.surface


def test_phrase_candidate_spans_are_exact():
    text = "Application APP-224510 supports the Payment Settlement business service."
    for candidate in identity.phrase_candidates(text):
        assert text[candidate.start_char : candidate.end_char] == candidate.surface


def test_identifier_bearing_phrase_candidates_are_dropped_identifiers_win():
    assert identity.phrase_candidate_is_identifier_colliding("obligation o-31") is True
    assert identity.phrase_candidate_is_identifier_colliding("payment settlement") is False


def test_page_key_and_page_type_are_deterministic():
    assert identity.page_key("identifier", "O-31") == "IDENT:O-31"
    assert identity.page_key("phrase", "payment settlement") == "PHRASE:payment settlement"
    assert identity.page_type_for("identifier") == "governed_identifier"
    assert identity.page_type_for("phrase") == "business_topic"


def test_heading_title_anchor_kind_has_no_page_identity():
    """Revision 6 SS7.1: a shared heading asserts document-template similarity,
    never entity co-occurrence, so it must never create a hub."""
    with pytest.raises(ValueError):
        identity.page_key("heading_title", "operating procedures")
    with pytest.raises(ValueError):
        identity.page_type_for("heading_title")


# --- the projection's shape --------------------------------------------------


def test_sections_are_one_to_one_with_canonical_chunks(projection, fixtures):
    all_chunk_ids = {c.chunk_id for fx in fixtures.values() for c in fx.chunks}
    assert len(projection.sections) == len(all_chunk_ids) == 11
    assert {s.chunk_id for s in projection.sections} == all_chunk_ids
    assert len({s.section_id for s in projection.sections}) == 11


def test_sections_never_merge_model_derived_text_into_source_text(projection, fixtures):
    source_by_chunk = {c.chunk_id: c.source_text for fx in fixtures.values() for c in fx.chunks}
    for section in projection.sections:
        assert section.source_text == source_by_chunk[section.chunk_id]


def test_revision_pages_have_no_currency_flag(projection):
    for page in projection.revision_pages:
        dumped = page.model_dump()
        for forbidden in ("current", "is_current", "is_latest", "effective", "is_effective", "superseded"):
            assert forbidden not in dumped


def test_only_payment_settlement_survives_lane_2(projection):
    """Matches the frozen plan's SS0.1 measured corpus property exactly."""
    phrase_anchors = [a for a in projection.anchors if a.anchor_kind == "phrase"]
    assert [a.normalized_value for a in phrase_anchors] == ["payment settlement"]


def test_payment_reconciliation_fails_the_two_document_rule(projection):
    entry = next(e for e in projection.phrase_lane_ledger if e["normalized_phrase"] == "payment reconciliation")
    assert entry["accepted"] is False
    assert entry["distinct_logical_documents"] == 1


def test_every_posting_span_matches_its_source_text(projection):
    section_by_chunk = {s.chunk_id: s for s in projection.sections}
    for posting in projection.postings:
        section = section_by_chunk[posting.chunk_id]
        if posting.field == "source_text":
            assert section.source_text[posting.start_char : posting.end_char] == posting.surface_text


def test_every_posting_carries_complete_provenance(projection):
    for posting in projection.postings:
        assert posting.chunk_id and posting.document_revision_id and posting.logical_document_id
        assert posting.source_ref
        assert posting.end_char >= posting.start_char
        assert len(posting.posting_hash) == 64


def test_no_link_is_ever_authoritative_lineage(projection):
    assert projection.links
    for link in projection.links:
        assert link.is_authoritative_lineage is False


def test_display_title_is_a_verbatim_source_surface_form(projection):
    surfaces_by_anchor: dict[str, set[str]] = {}
    for posting in projection.postings:
        surfaces_by_anchor.setdefault(posting.anchor_id, set()).add(posting.surface_text)
    for page in projection.page_identities:
        assert page.display_title in surfaces_by_anchor[page.anchor_id]


# --- C-88 / C-88a separation (hard test) -------------------------------------


def test_c88_and_c88a_are_never_merged_at_any_level(projection):
    c88 = next(a for a in projection.anchors if a.normalized_value == "C-88")
    c88a = next(a for a in projection.anchors if a.normalized_value == "C-88A")

    assert c88.anchor_id != c88a.anchor_id
    assert c88.display_text == "C-88"
    assert c88a.display_text == "C-88a"

    keys = {p.page_key for p in projection.page_identities}
    assert "IDENT:C-88" in keys and "IDENT:C-88A" in keys

    c88_chunks = {p.chunk_id for p in projection.postings if p.anchor_id == c88.anchor_id}
    c88a_chunks = {p.chunk_id for p in projection.postings if p.anchor_id == c88a.anchor_id}
    assert c88_chunks and c88a_chunks
    assert not (c88_chunks & c88a_chunks)

    c88_facets = {f.document_revision_id for f in projection.facets if f.page_key == "IDENT:C-88"}
    c88a_facets = {f.document_revision_id for f in projection.facets if f.page_key == "IDENT:C-88A"}
    assert not (c88_facets & c88a_facets)

    for link in projection.links:
        if link.anchor_id == c88.anchor_id:
            assert link.anchor_id != c88a.anchor_id


def test_c88_page_never_posts_into_a_c88a_only_chunk(projection):
    section_by_chunk = {s.chunk_id: s for s in projection.sections}
    c88 = next(a for a in projection.anchors if a.normalized_value == "C-88")
    for posting in projection.postings:
        if posting.anchor_id != c88.anchor_id:
            continue
        assert "C-88" in identity.identifiers_in(section_by_chunk[posting.chunk_id].source_text)


# --- membership: THE hard invariant -----------------------------------------


def test_membership_is_a_pure_function_of_identities_and_postings(projection):
    """Recomputing membership from page identities + postings alone must
    reproduce the projection's facets exactly. Nothing else is an input."""
    recomputed = _build_facets(projection.page_identities, projection.postings)
    assert [f.model_dump() for f in recomputed] == [f.model_dump() for f in projection.facets]


def test_facet_exists_iff_page_identity_has_a_posting_in_that_revision(projection):
    anchor_by_page = {p.page_key: p.anchor_id for p in projection.page_identities}
    expected: set[tuple[str, str]] = set()
    for posting in projection.postings:
        for page_key, anchor_id in anchor_by_page.items():
            if posting.anchor_id == anchor_id:
                expected.add((page_key, posting.document_revision_id))
    assert {(f.page_key, f.document_revision_id) for f in projection.facets} == expected


def test_facet_records_carry_no_model_derived_field(projection):
    """A Stage 7C.1 claim/alias/summary/verdict must have nowhere to live on a
    membership record -- the invariant is structural, not merely validated."""
    forbidden = {
        "claims", "claim", "aliases", "alias", "summary_sentences", "summary", "validation_status",
        "adjudication", "adjudication_verdict", "compiled", "embedding", "payload", "derived_links",
    }
    for facet in projection.facets:
        assert not (set(facet.model_dump()) & forbidden)
    for section in projection.sections:
        assert not (set(section.model_dump()) & forbidden)


def test_every_facet_is_functional_with_zero_claims(projection):
    """At Stage 7C.0 EVERY facet has zero accepted claims -- no compiler
    exists. Each must still exist, retain source chunks and anchors, and be
    expandable and traversable."""
    section_by_chunk = {s.chunk_id: s for s in projection.sections}
    assert len(projection.facets) == 22
    for facet in projection.facets:
        assert facet.chunk_ids, "a facet must retain its source chunks with zero claims"
        assert facet.posting_hashes, "a facet must retain its anchor postings with zero claims"
        for chunk_id in facet.chunk_ids:
            assert section_by_chunk[chunk_id].anchor_ids, "the facet's section must retain its anchors"


def test_membership_survives_every_simulated_compiler_outcome(projection):
    """Membership must be unchanged whether a (future) compiler succeeds
    totally, partially, or not at all. Since membership's only inputs are
    identities and postings, every simulated outcome is the same computation
    -- which is exactly the invariant."""
    baseline = [f.model_dump() for f in _build_facets(projection.page_identities, projection.postings)]
    for _simulated_outcome in ("all_claims_accepted", "all_claims_rejected", "compiler_crashed"):
        assert [f.model_dump() for f in _build_facets(projection.page_identities, projection.postings)] == baseline


# --- determinism and hashing -------------------------------------------------


def test_rebuild_over_identical_inputs_is_byte_identical(fixtures):
    first = build_projection(fixtures)
    second = build_projection(fixtures)
    assert first.projection_hash == second.projection_hash
    assert first.model_dump_json() == second.model_dump_json()


def test_projection_hash_covers_every_record(projection):
    assert compute_projection_hash(projection) == projection.projection_hash

    tampered = projection.model_copy(deep=True)
    tampered.postings[0].start_char += 1
    assert compute_projection_hash(tampered) != projection.projection_hash


def test_a_source_change_changes_only_that_revision(fixtures, projection):
    """A source-revision change must alter that revision's projection and the
    global hash, and leave every other revision's membership untouched."""
    mutated = copy.deepcopy(fixtures)
    target_symbol = "prc_rev2"
    chunk = mutated[target_symbol].chunks[0]
    mutated[target_symbol].chunks[0] = chunk.model_copy(
        update={"source_text": chunk.source_text.replace("P-205", "P-999")}
    )
    rebuilt = build_projection(mutated)

    assert rebuilt.projection_hash != projection.projection_hash

    changed_revision = mutated[target_symbol].document_revision_id
    before = {
        (f.page_key, f.document_revision_id): f.membership_hash
        for f in projection.facets
        if f.document_revision_id != changed_revision
    }
    after = {
        (f.page_key, f.document_revision_id): f.membership_hash
        for f in rebuilt.facets
        if f.document_revision_id != changed_revision
    }
    assert before == after

    assert any(p.page_key == "IDENT:P-999" for p in rebuilt.page_identities)
    assert changed_revision not in {f.document_revision_id for f in rebuilt.facets if f.page_key == "IDENT:P-205"}


def test_store_roundtrip_is_idempotent(projection):
    store = InMemoryWikiProjectionStore()
    store.upsert_anchors(projection.anchors)
    store.upsert_postings(projection.postings)
    first = (store.anchor_count(), store.posting_count())
    store.upsert_anchors(projection.anchors)
    store.upsert_postings(projection.postings)
    assert (store.anchor_count(), store.posting_count()) == first


def test_store_authority_filter_returns_nothing_for_an_empty_scope(projection):
    store = InMemoryWikiProjectionStore()
    store.upsert_postings(projection.postings)
    assert store.postings_for_revisions([]) == []


# --- M_max -------------------------------------------------------------------


def test_m_max_is_the_max_facet_count_per_page(projection):
    m_max, argmax = compute_m_max(projection.facets)
    assert m_max == projection.counts.m_max == 3

    revisions_by_page: dict[str, set[str]] = {}
    for facet in projection.facets:
        revisions_by_page.setdefault(facet.page_key, set()).add(facet.document_revision_id)
    assert m_max == max(len(v) for v in revisions_by_page.values())
    assert set(argmax) == {key for key, v in revisions_by_page.items() if len(v) == m_max}
    assert set(argmax) == {"IDENT:O-31", "IDENT:P-205", "PHRASE:payment settlement"}


def test_m_max_bounds_every_page_so_the_ceiling_formula_is_valid(projection):
    """`C = (P_seed + B) x M_max x F_max` is only a valid upper bound if
    M_max really bounds facets-per-page. Stage 7C.0 verifies the bound; Stage
    7C.2 evaluates the ceiling."""
    counts: dict[str, int] = {}
    for facet in projection.facets:
        counts[facet.page_key] = counts.get(facet.page_key, 0) + 1
    assert all(count <= projection.counts.m_max for count in counts.values())


def test_m_max_is_empty_safe():
    assert compute_m_max([]) == (0, [])


# --- frozen sentence splitter ------------------------------------------------


def test_sentence_splitter_is_deterministic_and_spans_are_exact():
    text = "Procedure P-205 is the current operating procedure. It applies now."
    first = identity.split_sentences(text)
    assert [s.surface for s in first] == [
        "Procedure P-205 is the current operating procedure.",
        "It applies now.",
    ]
    for sentence in first:
        assert text[sentence.start_char : sentence.end_char] == sentence.surface
    assert [s.surface for s in identity.split_sentences(text)] == [s.surface for s in first]


def test_sentence_splitter_identity_is_stable():
    assert identity.sentence_splitter_identity() == identity.sentence_splitter_identity()
    assert len(identity.sentence_splitter_identity()["sha256"]) == 64


# --- frozen D0 contracts (defined and tested, NOT executed) ------------------


def test_d0_contract_identity_is_stable_and_declares_its_exclusions():
    first = d0_contract_identity()
    assert first == d0_contract_identity()
    assert first["executed_in_stage_7c0"] is False
    assert len(first["seed_procedure"]["sha256"]) == 64
    assert len(first["branch_prioritizer"]["sha256"]) == 64
    forbidden = " ".join(first["forbidden_inputs"]).lower()
    for excluded in ("facet embedding", "compiler output", "claims", "summary", "aliases"):
        assert excluded in forbidden


def test_d0_seed_ordering_is_deterministic_and_bounded(projection):
    eligible = sorted({f.document_revision_id for f in projection.facets})
    ranked = [s.chunk_id for s in projection.sections]

    first = d0_seed_pages_from_ranked_chunks(
        ranked_chunk_ids=ranked, projection=projection, eligible_revision_ids=eligible, p_seed=3
    )
    second = d0_seed_pages_from_ranked_chunks(
        ranked_chunk_ids=ranked, projection=projection, eligible_revision_ids=eligible, p_seed=3
    )
    assert [s.model_dump() for s in first] == [s.model_dump() for s in second]
    assert len(first) <= 3
    assert [s.seed_rank for s in first] == list(range(1, len(first) + 1))
    assert len({s.page_key for s in first}) == len(first), "seed pages must be deduplicated"
    assert first[0].origin_chunk_rank == 1, "the rank-1 seed page is the path origin"


def test_d0_seed_respects_authority_eligibility(projection):
    ranked = [s.chunk_id for s in projection.sections]
    assert d0_seed_pages_from_ranked_chunks(
        ranked_chunk_ids=ranked, projection=projection, eligible_revision_ids=[], p_seed=5
    ) == []

    one_revision = projection.facets[0].document_revision_id
    seeds = d0_seed_pages_from_ranked_chunks(
        ranked_chunk_ids=ranked, projection=projection, eligible_revision_ids=[one_revision], p_seed=99
    )
    chunk_ids_of_revision = {s.chunk_id for s in projection.sections if s.document_revision_id == one_revision}
    assert all(seed.origin_chunk_id in chunk_ids_of_revision for seed in seeds)


def test_d0_seed_never_reads_a_facet_embedding_or_compiler_output():
    """Structural guard: the frozen seed function's parameters make W1 output
    impossible to supply, so the exclusion cannot be violated by accident."""
    import inspect

    parameters = set(inspect.signature(d0_seed_pages_from_ranked_chunks).parameters)
    assert parameters == {"ranked_chunk_ids", "projection", "eligible_revision_ids", "p_seed"}
    for forbidden in ("facet_embedding", "claims", "aliases", "summaries", "payload", "compiled"):
        assert forbidden not in parameters


def test_d0_branch_order_is_deterministic_and_uses_the_declared_precedence():
    candidates = [
        ("IDENT:P-205", "structural", 0.5),
        ("IDENT:C-88", "exact_anchor", 0.9),
        ("IDENT:O-31", "exact_anchor", 0.5),
    ]
    assert d0_branch_order(candidates) == ["IDENT:C-88", "IDENT:O-31", "IDENT:P-205"]
    assert d0_branch_order(candidates) == d0_branch_order(list(reversed(candidates)))


def test_d0_branch_order_breaks_ties_on_stable_page_key():
    candidates = [("IDENT:B", "exact_anchor", 0.5), ("IDENT:A", "exact_anchor", 0.5)]
    assert d0_branch_order(candidates) == ["IDENT:A", "IDENT:B"]


# --- purity guards -----------------------------------------------------------


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_no_module_has_a_graph_or_hybrid_runtime_dependency():
    for path in sorted(WIKI_ROOT.glob("*.py")):
        for module in _imported_modules(path):
            assert "graph_retrieval_benchmark" not in module, f"{path.name} imports Graph: {module}"
            assert "hybrid_retrieval_benchmark" not in module, f"{path.name} imports Hybrid: {module}"
            assert "neo4j" not in module.lower(), f"{path.name} imports Neo4j: {module}"


def test_the_build_path_never_reads_benchmark_truth():
    forbidden = ("required_fact_ids", "forbidden_fact_ids", "expected_relationship_chain", "expected_supporting_passage")
    for name in BUILD_PATH_MODULES:
        source = (WIKI_ROOT / name).read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"{name} references benchmark truth: {token}"


def test_the_build_path_makes_no_llm_or_network_call():
    forbidden = ("openai", "OpenAI", "anthropic", "requests.", "httpx", "urllib.request", "SentenceTransformer")
    for name in BUILD_PATH_MODULES:
        source = (WIKI_ROOT / name).read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"{name} references a model/network call: {token}"


def test_the_build_path_never_reads_authority_state():
    """Build time must never call the resolver. Authority appears only as a
    query-time VIEW parameter (`eligible_revision_ids`)."""
    for name in ("identity.py", "model.py", "store.py"):
        source = (WIKI_ROOT / name).read_text(encoding="utf-8")
        assert "revision_authority" not in source
        assert "resolve_query_scope" not in source
    projection_source = (WIKI_ROOT / "projection.py").read_text(encoding="utf-8")
    assert "resolve_query_scope" not in projection_source
    assert "RevisionAuthorityService" not in projection_source


def test_stage_7c0_modules_remain_projection_only():
    """Scope guard, narrowed twice as the frontier moved.

    It originally asserted the 7C.1 modules did not exist, then the 7C.2 ones;
    both are now authorised and present. What it still protects is the boundary
    that matters: the Stage 7C.0 projection modules must not acquire retrieval,
    navigation or compilation responsibilities.
    """
    for name in ("identity.py", "model.py", "projection.py", "store.py", "pg_store.py"):
        source = (WIKI_ROOT / name).read_text(encoding="utf-8")
        for forbidden in ("hop_budget", "final_k", "seed_page_priority", "compile_facet", "claim_derived"):
            assert forbidden not in source, f"{name} acquired a later-stage responsibility: {forbidden}"
