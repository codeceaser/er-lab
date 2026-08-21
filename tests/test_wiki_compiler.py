"""Stage 7C.1: compiler contract, run discipline, previews and the
owner-adjudication packet.

Deterministic: no network, no API key, no model call. The real
`OpenAIFacetCompiler` is exercised only for its lazy-client and parity
behaviour, never by calling it.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from ingestion_bench.cross_document_benchmark.benchmark_runner import load_contract
from ingestion_bench.cross_document_benchmark.fixtures import load_all_revision_fixtures
from ingestion_bench.wiki_projection import config
from ingestion_bench.wiki_projection.adjudication import (
    OWNER_VERDICT_VALUES,
    build_adjudication_packet,
    render_packet_markdown,
)
from ingestion_bench.wiki_projection.assembly import compose_payload_preview, render_w1_page_preview
from ingestion_bench.wiki_projection.benchmark import (
    PRIMARY_RUN_ID,
    REPEATABILITY_RUN_IDS,
    facet_key,
    run_stage7c1_compilation,
)
from ingestion_bench.wiki_projection.compiler import (
    FACET_JSON_SCHEMA,
    MAX_ALIASES_PER_FACET,
    PROMPT_VERSION,
    STAGE7B1_EXTRACTION_MODEL,
    CeilingBreach,
    CompilerModelParityError,
    FakeFacetCompiler,
    OpenAIFacetCompiler,
    ScriptedFacetCompiler,
    UnresolvedBudgetError,
    build_facet_input,
    build_user_prompt,
    estimate_cost_usd,
    prompt_sha256,
    resolve_run_dollar_ceiling,
    verify_model_parity,
)
from ingestion_bench.wiki_projection.projection import build_projection
from ingestion_bench.wiki_projection.report import build_gate_q_pre_status, build_stage7c1_cost_ledger

REPO_ROOT = Path(__file__).resolve().parent.parent
WIKI_ROOT = REPO_ROOT / "src" / "ingestion_bench" / "wiki_projection"
STAGE7C1_MODULES = ["compiler.py", "validation.py", "assembly.py", "adjudication.py"]


@pytest.fixture(scope="module")
def projection():
    contract = load_contract(config.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH)
    return build_projection(load_all_revision_fixtures(contract["fixtures"]))


@pytest.fixture(scope="module")
def compiled(projection):
    """One deterministic 3-run compilation with the non-LLM test double."""
    return run_stage7c1_compilation(projection, FakeFacetCompiler(), dollar_ceiling_usd=1.0)


@pytest.fixture(scope="module")
def packet(projection, compiled):
    run_1 = compiled.validations_by_run[str(PRIMARY_RUN_ID)]
    return build_adjudication_packet(
        run_id=PRIMARY_RUN_ID, validations=run_1, projection_hash=projection.projection_hash,
        facets_by_key={facet_key(f.page_key, f.document_revision_id): f for f in projection.facets},
        pages_by_key={p.page_key: p for p in projection.page_identities},
        sections_by_chunk={s.chunk_id: s for s in projection.sections},
        revision_symbol_by_id={}, model_identity="fake-deterministic-facet-compiler-v1",
        prompt_version=PROMPT_VERSION, prompt_sha256_value=prompt_sha256(),
    )


# --- compiler schema ---------------------------------------------------------


def test_model_output_schema_is_exactly_three_fields():
    """Revision 6 SS3.2/SS3.7: the LLM's structured output is exactly aliases,
    claims and summary_sentences -- nothing else is trusted from the model."""
    assert set(FACET_JSON_SCHEMA["required"]) == {"aliases", "claims", "summary_sentences"}
    assert set(FACET_JSON_SCHEMA["properties"]) == {"aliases", "claims", "summary_sentences"}
    assert FACET_JSON_SCHEMA["additionalProperties"] is False


def test_schema_forbids_model_created_identity_membership_or_authority():
    """A model-emitted title, page type, membership or currency field must be
    impossible by schema, not merely rejected later.

    Checked against the schema's actual PROPERTY NAMES, not a substring scan:
    `supporting_chunk_ids` legitimately contains "chunk_ids", and the model must
    cite chunks, so a substring test would forbid the contract's own citation
    field.
    """
    names: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                names.update(node.get("properties", {}))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(FACET_JSON_SCHEMA)
    assert names == {
        "aliases", "claims", "summary_sentences",
        "alias", "status", "supporting_chunk_ids", "supporting_quotes",
        "claim_id", "subject", "predicate", "object", "claim_text",
        "sentence_id", "text", "supported_claim_ids",
    }
    for forbidden in (
        "page_key", "display_title", "page_type", "input_chunk_ids", "membership",
        "document_revision_id", "is_current", "effective", "authority", "validation_status",
        "derivation", "related_page_candidates", "link_target", "traversal_direction",
    ):
        assert forbidden not in names, f"schema exposes {forbidden!r} to the model"


def test_every_schema_object_forbids_additional_properties():
    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(FACET_JSON_SCHEMA)


def test_claim_status_is_never_a_model_field():
    """SS3.4: `validation_status` is assigned by the deterministic validator,
    never by the model."""
    claim_properties = FACET_JSON_SCHEMA["properties"]["claims"]["items"]["properties"]
    assert "validation_status" not in claim_properties
    assert "derivation" not in claim_properties


# --- facet isolation ---------------------------------------------------------


def test_compiler_input_carries_only_this_facets_chunks(projection):
    """SS3.1: each compilation sees ONLY the chunks of that revision that carry
    that page identity -- never another revision, page or facet."""
    sections_by_chunk = {s.chunk_id: s for s in projection.sections}
    pages_by_key = {p.page_key: p for p in projection.page_identities}
    for facet in projection.facets:
        facet_input = build_facet_input(facet, pages_by_key[facet.page_key], sections_by_chunk)
        assert set(facet_input.input_chunk_ids) == set(facet.chunk_ids)
        assert set(facet_input.chunk_texts) == set(facet.chunk_ids)
        for chunk_id in facet_input.input_chunk_ids:
            assert sections_by_chunk[chunk_id].document_revision_id == facet.document_revision_id


def test_prompt_contains_no_other_revision_and_no_benchmark_truth(projection):
    sections_by_chunk = {s.chunk_id: s for s in projection.sections}
    pages_by_key = {p.page_key: p for p in projection.page_identities}
    facet = next(f for f in projection.facets if f.page_key == "IDENT:C-88")
    prompt = build_user_prompt(build_facet_input(facet, pages_by_key[facet.page_key], sections_by_chunk))

    other_revisions = {s.document_revision_id for s in projection.sections} - {facet.document_revision_id}
    for revision_id in other_revisions:
        assert revision_id not in prompt
    for truth in ("required_fact", "forbidden_fact", "expected_relationship_chain", "F_svc", "F_prc_current"):
        assert truth not in prompt


def test_prompt_forbids_the_model_from_inventing_structure():
    """The instruction set must explicitly deny identity/membership/link/
    authority creation -- the schema and the prompt agree."""
    from ingestion_bench.wiki_projection.compiler import SYSTEM_PROMPT

    lowered = SYSTEM_PROMPT.lower()
    for required in ("page identities", "link targets", "membership", "authority state", "verbatim", "c-88a"):
        assert required in lowered


# --- model parity and budget -------------------------------------------------


def test_compiler_model_parity_is_enforced_before_any_call():
    verify_model_parity(STAGE7B1_EXTRACTION_MODEL)
    with pytest.raises(CompilerModelParityError):
        verify_model_parity("gpt-4o")
    with pytest.raises(CompilerModelParityError):
        OpenAIFacetCompiler(model_identity="gpt-4o")


def test_openai_compiler_constructs_without_network_or_key():
    """Lazy client: constructing must never require an API key or a network."""
    compiler = OpenAIFacetCompiler()
    assert compiler.model_identity == STAGE7B1_EXTRACTION_MODEL
    assert compiler._client is None


def test_unresolved_dollar_ceiling_stops_before_any_call(monkeypatch):
    """Revision 6 leaves SS3.9's whole-run dollar ceiling open (Q6). It must be
    a hard STOP, never a value this code chooses."""
    monkeypatch.delenv("INGESTION_BENCH_STAGE7C1_DOLLAR_CAP", raising=False)
    with pytest.raises(UnresolvedBudgetError) as excinfo:
        resolve_run_dollar_ceiling()
    assert "Q6" in str(excinfo.value)

    monkeypatch.setenv("INGESTION_BENCH_STAGE7C1_DOLLAR_CAP", "0.75")
    assert resolve_run_dollar_ceiling() == 0.75


def test_no_default_dollar_cap_is_hardcoded_anywhere():
    """The cap must have no numeric default anywhere. `*_ENV_VAR` names are
    excluded: those hold the NAME of the variable to read, not a cap value."""
    tree = ast.parse((WIKI_ROOT / "compiler.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if "DOLLAR" not in target.id or target.id.endswith("_ENV_VAR"):
                continue
            assert not isinstance(node.value, ast.Constant) or isinstance(node.value.value, str), (
                f"{target.id} must not carry a numeric default -- the cap is the owner's to set"
            )

    # And `os.environ.get` for the cap must have no fallback value.
    source = (WIKI_ROOT / "compiler.py").read_text(encoding="utf-8")
    assert "os.environ.get(RUN_DOLLAR_CEILING_ENV_VAR)" in source
    assert "os.environ.get(RUN_DOLLAR_CEILING_ENV_VAR," not in source


def test_cost_estimate_returns_none_rather_than_a_fabricated_number():
    assert estimate_cost_usd("gpt-4o-mini", 1000, 1000) == pytest.approx(0.00075)
    assert estimate_cost_usd("some-unpriced-model", 1000, 1000) is None
    assert estimate_cost_usd("gpt-4o-mini", None, 100) is None


# --- ceilings ----------------------------------------------------------------


def test_input_chunk_ceiling_fails_the_facet_before_the_call(projection):
    from ingestion_bench.wiki_projection.compiler import FacetCompilationInput

    oversized = FacetCompilationInput(
        page_key="IDENT:X-1", page_type="governed_identifier", display_title="X-1",
        document_revision_id="r", logical_document_id="d",
        input_chunk_ids=[f"c{i}" for i in range(13)],
        chunk_texts={f"c{i}": "text" for i in range(13)},
        chunk_heading_paths={f"c{i}": [] for i in range(13)},
    )
    with pytest.raises(CeilingBreach):
        FakeFacetCompiler().compile_facet(oversized, 1)


def test_output_ceilings_fail_the_facet(projection):
    """SS3.9: a breach FAILS THE FACET. There is no batching, truncate-and-
    continue, or mid-run ceiling raise."""
    facet = next(f for f in projection.facets if f.page_key == "IDENT:C-88")
    chunk_id = facet.chunk_ids[0]
    section = next(s for s in projection.sections if s.chunk_id == chunk_id)
    scripted = {
        (facet.page_key, facet.document_revision_id): {
            "aliases": [
                {"alias": "C-88", "supporting_chunk_ids": [chunk_id], "supporting_quotes": ["C-88"],
                 "status": "supported"}
                for _ in range(MAX_ALIASES_PER_FACET + 1)
            ],
            "claims": [], "summary_sentences": [],
        }
    }
    result = run_stage7c1_compilation(
        projection, ScriptedFacetCompiler(scripted), dollar_ceiling_usd=1.0, run_ids=(1,)
    )
    validation = result.validations_by_run["1"][facet_key(facet.page_key, facet.document_revision_id)]
    assert validation.ceiling_breaches
    assert validation.facet_failed is True
    assert section.source_text  # the source is untouched by the breach


def test_a_ceiling_breach_leaves_deterministic_membership_intact(projection):
    before = {(f.page_key, f.document_revision_id): f.membership_hash for f in projection.facets}
    facet = next(f for f in projection.facets if f.page_key == "IDENT:C-88")
    scripted = {
        (facet.page_key, facet.document_revision_id): {
            "aliases": [{"alias": "C-88", "supporting_chunk_ids": [facet.chunk_ids[0]],
                         "supporting_quotes": ["C-88"], "status": "supported"}] * 20,
            "claims": [], "summary_sentences": [],
        }
    }
    run_stage7c1_compilation(projection, ScriptedFacetCompiler(scripted), dollar_ceiling_usd=1.0, run_ids=(1,))
    after = {(f.page_key, f.document_revision_id): f.membership_hash for f in projection.facets}
    assert before == after


# --- run discipline ----------------------------------------------------------


def test_run_1_is_primary_and_designated_before_execution(compiled):
    assert PRIMARY_RUN_ID == 1
    assert compiled.primary_run_id == 1
    primary = [p for p in compiled.run_provenance if p.is_primary]
    assert len(primary) == 1 and primary[0].run_id == 1


def test_three_runs_execute_with_identical_configuration(compiled, projection):
    assert [p.run_id for p in compiled.run_provenance] == list(REPEATABILITY_RUN_IDS)
    assert compiled.compiler_calls_total == len(projection.facets) * len(REPEATABILITY_RUN_IDS)
    assert len({p.prompt_sha256 for p in compiled.run_provenance}) == 1
    assert len({p.model_identity for p in compiled.run_provenance}) == 1
    assert len({p.temperature for p in compiled.run_provenance}) == 1
    assert len({p.facets_attempted for p in compiled.run_provenance}) == 1


def test_runs_2_and_3_never_substitute_for_run_1(projection):
    """A run-2/3 result must be unable to reach the adjudication packet. Runs
    are compiled with a compiler that emits DIFFERENT content per run, and the
    packet must contain run 1's content only."""
    scripted_by_run: dict[int, str] = {1: "one", 2: "two", 3: "three"}

    class PerRunCompiler:
        model_identity = "per-run-test-double"

        def compile_facet(self, facet_input, run_id):
            from ingestion_bench.wiki_projection.compiler import FacetCompilationOutput, RawClaim

            chunk_id = facet_input.input_chunk_ids[0]
            return FacetCompilationOutput(
                page_key=facet_input.page_key, document_revision_id=facet_input.document_revision_id,
                run_id=run_id,
                claims=[RawClaim(
                    claim_id=f"clm_{scripted_by_run[run_id]}", subject=facet_input.display_title,
                    predicate="marker", object=scripted_by_run[run_id],
                    claim_text=f"marker {scripted_by_run[run_id]}",
                    supporting_chunk_ids=[chunk_id], supporting_quotes=["nonexistent-quote"],
                )],
                model_identity=self.model_identity, temperature=0.0,
                prompt_version=PROMPT_VERSION, prompt_sha256=prompt_sha256(),
                input_chunk_ids=list(facet_input.input_chunk_ids),
            )

    result = run_stage7c1_compilation(projection, PerRunCompiler(), dollar_ceiling_usd=1.0)
    run_1_ids = {c.claim_id for v in result.validations_by_run["1"].values() for c in v.claims}
    assert run_1_ids == {"clm_one"}
    for other in ("2", "3"):
        other_ids = {c.claim_id for v in result.validations_by_run[other].values() for c in v.claims}
        assert not (run_1_ids & other_ids)


def test_prompt_and_model_provenance_is_persisted_per_run(compiled):
    for provenance in compiled.run_provenance:
        assert provenance.prompt_version == PROMPT_VERSION
        assert provenance.prompt_sha256 == prompt_sha256()
        assert len(provenance.prompt_sha256) == 64
        assert provenance.model_identity


def test_prompt_hash_changes_when_the_prompt_contract_changes(monkeypatch):
    baseline = prompt_sha256()
    import ingestion_bench.wiki_projection.compiler as compiler_module

    monkeypatch.setattr(compiler_module, "SYSTEM_PROMPT", compiler_module.SYSTEM_PROMPT + " EXTRA")
    assert prompt_sha256() != baseline


def test_audit_persists_every_facet_including_empty_ones(compiled, projection):
    """SS4.2: nothing is discarded silently -- every facet has an audit record,
    including those whose claims were all rejected or absent."""
    for run_id in ("1", "2", "3"):
        assert len(compiled.validations_by_run[run_id]) == len(projection.facets)


def test_generation_failure_is_recorded_never_dropped(projection):
    class FailingCompiler:
        model_identity = "failing-test-double"

        def compile_facet(self, facet_input, run_id):
            from ingestion_bench.wiki_projection.compiler import FacetCompilationOutput

            return FacetCompilationOutput(
                page_key=facet_input.page_key, document_revision_id=facet_input.document_revision_id,
                run_id=run_id, model_identity=self.model_identity, temperature=0.0,
                prompt_version=PROMPT_VERSION, prompt_sha256=prompt_sha256(),
                input_chunk_ids=list(facet_input.input_chunk_ids),
                generation_failed=True, generation_error="RuntimeError: simulated",
            )

    result = run_stage7c1_compilation(projection, FailingCompiler(), dollar_ceiling_usd=1.0, run_ids=(1,))
    validations = result.validations_by_run["1"]
    assert len(validations) == len(projection.facets)
    assert all(v.generation_failed and v.generation_error for v in validations.values())


# --- the checkpoint's central discipline: NO self-adjudication ---------------


def test_no_owner_verdict_is_ever_pre_populated(packet):
    assert packet.total_item_count > 0
    for item in [*packet.claims, *packet.aliases, *packet.summary_sentences]:
        assert item.owner.owner_verdict is None
        assert item.owner.owner_reason == ""
        assert item.owner.allowed_values == list(OWNER_VERDICT_VALUES)


def test_validated_records_carry_no_semantic_verdict(compiled):
    for validation in compiled.validations_by_run["1"].values():
        for record in [*validation.claims, *validation.aliases, *validation.summary_sentences]:
            assert record.owner_semantic_verdict is None


def test_packet_offers_no_recommendation_beside_the_blank_verdict(packet):
    """No recommendation may sit beside a verdict slot. Checked over the ITEM
    sections only -- the header's own disclaimer legitimately contains the word
    "recommendation" while promising the opposite."""
    markdown = render_packet_markdown(packet)
    items_only = markdown.split("## A. CLAIMS", 1)[1]
    for biasing in (
        "recommend", "suggest", "likely correct", "probably", "confidence", "we believe",
        "appears correct", "should be marked", "our assessment", "score",
    ):
        assert biasing not in items_only.lower(), f"packet biases the owner with {biasing!r}"


def test_packet_items_are_ordered_by_stable_id_not_by_likelihood(packet):
    for group in (packet.claims, packet.aliases, packet.summary_sentences):
        ids = [item.adjudication_item_id for item in group]
        assert ids == sorted(ids)


def test_packet_distinguishes_mechanical_validity_from_semantic_correctness(packet):
    markdown = render_packet_markdown(packet)
    assert "Citation validity is not claim correctness" in markdown
    assert "not alias semantic correctness" in markdown
    assert "not summary correctness" in markdown


def test_packet_covers_every_accepted_claim_supported_alias_and_summary(compiled, packet):
    run_1 = compiled.validations_by_run["1"]
    expected_claims = sum(1 for v in run_1.values() for c in v.claims if c.validation_status == "accepted")
    expected_aliases = sum(1 for v in run_1.values() for a in v.aliases if a.status == "supported")
    expected_summaries = sum(len(v.summary_sentences) for v in run_1.values())
    assert packet.claim_item_count == expected_claims
    assert packet.alias_item_count == expected_aliases
    assert packet.summary_item_count == expected_summaries


def test_packet_shows_alias_dependency_both_ways(compiled, packet):
    """A claim must declare whether it depends on an alias, and the alias must
    list the claims that would fall with it."""
    for item in packet.claims:
        assert isinstance(item.acceptance_depends_on_alias, bool)
        if item.acceptance_depends_on_alias:
            assert item.alias_dependency_ids
    for item in packet.aliases:
        assert isinstance(item.claims_whose_coherence_depends_on_this_alias, list)


def test_packet_shows_the_link_that_would_result_from_acceptance(packet):
    for item in packet.claims:
        for link in item.derived_link_if_accepted:
            assert link["is_authoritative_lineage"] is False
            assert link["predicate"]


def test_packet_supplies_enough_source_context_to_judge(packet):
    for item in packet.claims:
        assert item.full_source_text
        assert any(text.strip() for text in item.surrounding_source_text.values())
    for item in packet.summary_sentences:
        assert item.full_source_text
        assert item.referenced_claims_readable or not item.referenced_claim_ids


# --- payload preview is NOT the final representation -------------------------


def test_payload_preview_is_never_final_and_marks_pending_components(projection, compiled):
    run_1 = compiled.validations_by_run["1"]
    facets_by_key = {facet_key(f.page_key, f.document_revision_id): f for f in projection.facets}
    pages_by_key = {p.page_key: p for p in projection.page_identities}
    sections_by_chunk = {s.chunk_id: s for s in projection.sections}
    postings_by_chunk: dict[str, list] = {}
    for posting in projection.postings:
        postings_by_chunk.setdefault(posting.chunk_id, []).append(posting)

    any_pending = False
    for key, validation in run_1.items():
        preview = compose_payload_preview(
            validation, facet=facets_by_key[key], page=pages_by_key[validation.page_key],
            sections_by_chunk=sections_by_chunk, postings_by_chunk=postings_by_chunk,
        )
        assert preview.is_final is False
        assert "PREVIEW ONLY" in preview.not_final_reason
        # Components 2 and 7 are the owner-dependent ones.
        assert set(preview.pending_components) <= {2, 6, 7}
        any_pending = any_pending or bool(preview.pending_components)
    assert any_pending, "at least one facet should have owner-dependent payload components"


def test_payload_preview_never_drops_the_identity_components(projection, compiled):
    from ingestion_bench.wiki_projection.assembly import NEVER_DROPPED_COMPONENTS, PAY_MAX_DROP_ORDER

    assert NEVER_DROPPED_COMPONENTS == frozenset({1, 3, 4})
    assert PAY_MAX_DROP_ORDER == (7, 6, 5, 2)
    assert not (set(PAY_MAX_DROP_ORDER) & NEVER_DROPPED_COMPONENTS)


def test_no_facet_embedding_is_created_anywhere_in_stage_7c1():
    """SS4.6: facet embeddings are written only after adjudication pass 3."""
    for name in STAGE7C1_MODULES:
        source = (WIKI_ROOT / name).read_text(encoding="utf-8")
        for forbidden in ("embed(", "SentenceTransformer", "facet_embedding", "EmbeddingProvider"):
            assert forbidden not in source, f"{name} touches embeddings at the checkpoint: {forbidden}"


# --- page previews -----------------------------------------------------------


def test_page_preview_separates_deterministic_from_model_derived(projection, compiled):
    run_1 = compiled.validations_by_run["1"]
    page = next(p for p in projection.page_identities if p.page_key == "IDENT:C-88")
    sections_by_chunk = {s.chunk_id: s for s in projection.sections}
    postings_by_chunk: dict[str, list] = {}
    for posting in projection.postings:
        postings_by_chunk.setdefault(posting.chunk_id, []).append(posting)

    rendered = render_w1_page_preview(
        page, facets=projection.facets, validations=run_1, sections_by_chunk=sections_by_chunk,
        postings_by_chunk=postings_by_chunk, deterministic_links=projection.links,
        eligible_revision_ids=sorted({s.document_revision_id for s in projection.sections}),
        revision_symbol_by_id={}, payload_previews={},
    )
    assert "BLOCK A — SOURCE-BACKED / DETERMINISTIC" in rendered
    assert "BLOCK B — MODEL-DERIVED / PENDING OWNER ADJUDICATION" in rendered
    assert "PREVIEW for owner comprehension" in rendered
    assert "OWNER VERDICT: pending" in rendered
    assert rendered.index("BLOCK A") < rendered.index("BLOCK B")


def test_page_preview_states_no_quality_score_is_computed(projection, compiled):
    page = next(p for p in projection.page_identities if p.page_key == "IDENT:P-205")
    sections_by_chunk = {s.chunk_id: s for s in projection.sections}
    rendered = render_w1_page_preview(
        page, facets=projection.facets, validations=compiled.validations_by_run["1"],
        sections_by_chunk=sections_by_chunk, postings_by_chunk={},
        deterministic_links=projection.links,
        eligible_revision_ids=sorted({s.document_revision_id for s in projection.sections}),
        revision_symbol_by_id={}, payload_previews={},
    )
    assert "No page-quality score is computed" in rendered


# --- Gate Q pre-status -------------------------------------------------------


def test_gate_q_is_pending_never_pass_or_fail(compiled, packet):
    status = build_gate_q_pre_status(compiled, packet)
    assert status["gate_q_status"] == "PENDING OWNER ADJUDICATION"
    assert status["gate_q_status"] not in ("PASS", "FAIL")


def test_gate_q_marks_semantic_criteria_as_owner_dependent(compiled, packet):
    status = build_gate_q_pre_status(compiled, packet)
    for criterion in ("Q-5_accepted_claim_precision", "Q-6_expected_fact_recall",
                      "Q-7_summary_correctness", "Q-10_supported_alias_precision"):
        assert status["criteria"][criterion]["decidable_mechanically"] is False
        assert "awaiting" in status["criteria"][criterion]
    for criterion in ("Q-1_citation_validity", "Q-2_invalid_source_references",
                      "Q-3_revision_scope_contamination", "Q-4_false_merges"):
        assert status["criteria"][criterion]["decidable_mechanically"] is True


def test_gate_q_uses_the_revision_scope_contamination_name(compiled, packet):
    status = build_gate_q_pre_status(compiled, packet)
    assert "Q-3_revision_scope_contamination" in status["criteria"]
    assert not any("authority_contamination" in key for key in status["criteria"])


def test_cost_ledger_records_zero_embeddings_and_no_human_time_estimate(compiled, packet):
    ledger = build_stage7c1_cost_ledger(compiled, packet)
    assert ledger["facet_embeddings_created"] == 0
    assert "NOT ESTIMATED" in ledger["human_adjudication_time"]
    assert ledger["run_1_adjudication_item_count"] == packet.total_item_count
    assert ledger["compiler_calls_total"] == compiled.compiler_calls_total


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


def test_stage_7c1_modules_have_no_graph_runtime_dependency():
    for name in STAGE7C1_MODULES:
        for module in _imported_modules(WIKI_ROOT / name):
            assert "graph_retrieval_benchmark" not in module
            assert "hybrid_retrieval_benchmark" not in module
            assert "neo4j" not in module.lower()


def test_stage_7c1_modules_never_read_benchmark_truth():
    for name in STAGE7C1_MODULES:
        source = (WIKI_ROOT / name).read_text(encoding="utf-8")
        for token in ("required_fact_ids", "forbidden_fact_ids", "expected_relationship_chain",
                      "expected_supporting_passage"):
            assert token not in source, f"{name} reads benchmark truth: {token}"


def test_stage_7c1_modules_never_read_authority_state():
    for name in STAGE7C1_MODULES:
        source = (WIKI_ROOT / name).read_text(encoding="utf-8")
        assert "resolve_query_scope" not in source
        assert "RevisionAuthorityService" not in source


def test_model_parity_value_is_named_not_imported_from_the_frozen_graph_package():
    """SS3.8 pins the compiler to the frozen 7B.1 extraction model by NAMING the
    value; importing the frozen graph package would be a Graph runtime
    dependency. Checked over real imports, not comments -- the module comment
    legitimately explains why the import is absent."""
    assert STAGE7B1_EXTRACTION_MODEL == "gpt-4o-mini"
    for module in _imported_modules(WIKI_ROOT / "compiler.py"):
        assert "graph_retrieval_benchmark" not in module


def test_stage_7c2_modules_still_do_not_exist():
    for name in ("retrieval.py", "navigation.py"):
        assert not (WIKI_ROOT / name).exists(), f"{name} belongs to Stage 7C.2"


def test_gate_q_surfaces_a_mechanically_failing_proposed_threshold(projection):
    """A mechanically decidable criterion that already breaches its PROPOSED
    threshold must be surfaced loudly -- the owner should see it before
    spending adjudication effort -- while the status stays PENDING, because the
    threshold itself is still open question Q5."""

    class UnstableCompiler:
        """Emits a different claim per run, so the claim-set Jaccard collapses."""

        model_identity = "unstable-test-double"

        def compile_facet(self, facet_input, run_id):
            from ingestion_bench.wiki_projection.compiler import FacetCompilationOutput, RawClaim

            chunk_id = facet_input.input_chunk_ids[0]
            text = facet_input.chunk_texts[chunk_id]
            quote = text.split(".")[0]
            return FacetCompilationOutput(
                page_key=facet_input.page_key, document_revision_id=facet_input.document_revision_id,
                run_id=run_id,
                claims=[RawClaim(
                    claim_id=f"clm_{run_id}", subject=facet_input.display_title,
                    predicate=f"varies_{run_id}", object=f"target_{run_id}",
                    claim_text=quote, supporting_chunk_ids=[chunk_id], supporting_quotes=[quote],
                )],
                model_identity=self.model_identity, temperature=0.0,
                prompt_version=PROMPT_VERSION, prompt_sha256=prompt_sha256(),
                input_chunk_ids=list(facet_input.input_chunk_ids),
            )

    result = run_stage7c1_compilation(projection, UnstableCompiler(), dollar_ceiling_usd=1.0)
    run_1 = result.validations_by_run["1"]
    unstable_packet = build_adjudication_packet(
        run_id=PRIMARY_RUN_ID, validations=run_1, projection_hash=projection.projection_hash,
        facets_by_key={facet_key(f.page_key, f.document_revision_id): f for f in projection.facets},
        pages_by_key={p.page_key: p for p in projection.page_identities},
        sections_by_chunk={s.chunk_id: s for s in projection.sections},
        revision_symbol_by_id={}, model_identity="unstable-test-double",
        prompt_version=PROMPT_VERSION, prompt_sha256_value=prompt_sha256(),
    )
    status = build_gate_q_pre_status(result, unstable_packet)

    assert status["mechanical_criteria_failing_proposed_thresholds"]
    assert status["mechanical_blocker_warning"] is not None
    assert "Q-8" in status["mechanical_blocker_warning"]
    assert status["criteria"]["Q-8_repeatability"]["meets_proposed_threshold"] is False
    # Still PENDING: the threshold is a proposal (Q5), so this is not a verdict.
    assert status["gate_q_status"] == "PENDING OWNER ADJUDICATION"


def test_adjudication_packet_provenance_comes_from_the_executed_run(projection, compiled):
    """Regression guard: the packet's model identity must come from the run
    that actually executed, never from whatever compiler object is in hand.
    Reporting a placeholder's identity would falsify the packet."""
    primary = next(p for p in compiled.run_provenance if p.run_id == PRIMARY_RUN_ID)
    built = build_adjudication_packet(
        run_id=PRIMARY_RUN_ID, validations=compiled.validations_by_run["1"],
        projection_hash=projection.projection_hash,
        facets_by_key={facet_key(f.page_key, f.document_revision_id): f for f in projection.facets},
        pages_by_key={p.page_key: p for p in projection.page_identities},
        sections_by_chunk={s.chunk_id: s for s in projection.sections},
        revision_symbol_by_id={}, model_identity=primary.model_identity,
        prompt_version=primary.prompt_version, prompt_sha256_value=primary.prompt_sha256,
    )
    assert built.model_identity == primary.model_identity
    assert built.prompt_sha256 == primary.prompt_sha256


def test_runner_takes_provenance_from_run_provenance_not_the_compiler_object():
    """Pins the fix at the call site, so a future edit cannot reintroduce it."""
    source = (REPO_ROOT / "scripts" / "run_stage7c1_wiki_compiler.py").read_text(encoding="utf-8")
    assert "model_identity=primary_provenance.model_identity" in source
    assert "model_identity=facet_compiler.model_identity" not in source
