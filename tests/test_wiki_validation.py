"""Stage 7C.1: the deterministic validator (Revision 6 SS4) and claim-derived
link derivation (SS3.7).

Every rule is exercised by INJECTING model output through
`ScriptedFacetCompiler` -- including output a well-behaved compiler would never
produce (fabricated quotes, cross-revision citations, out-of-page claims,
forbidden status terms, C-88/C-88a merges). Deterministic: no network, no model
call.

The suite also pins the three things that must NEVER happen: membership
changing because of compiler output, a semantic verdict being written by code,
and connectivity depending on a claim.
"""

from __future__ import annotations

import pytest

from ingestion_bench.cross_document_benchmark.benchmark_runner import load_contract
from ingestion_bench.cross_document_benchmark.fixtures import load_all_revision_fixtures
from ingestion_bench.wiki_projection import config
from ingestion_bench.wiki_projection.compiler import ScriptedFacetCompiler
from ingestion_bench.wiki_projection.projection import build_projection
from ingestion_bench.wiki_projection.validation import (
    STATUS_LEXICON,
    assert_membership_unchanged,
    normalize_triple_part,
    normalize_whitespace,
    resolve_page_key,
    validate_facet,
)


@pytest.fixture(scope="module")
def projection():
    contract = load_contract(config.CROSS_DOCUMENT_BENCHMARK_CONTRACT_PATH)
    return build_projection(load_all_revision_fixtures(contract["fixtures"]))


@pytest.fixture(scope="module")
def context(projection):
    return {
        "sections_by_chunk": {s.chunk_id: s for s in projection.sections},
        "pages_by_key": {p.page_key: p for p in projection.page_identities},
        "all_page_keys": {p.page_key for p in projection.page_identities},
    }


def _facet(projection, page_key: str, symbol_hint: str | None = None):
    facets = [f for f in projection.facets if f.page_key == page_key]
    assert facets, f"no facet for {page_key}"
    return facets[0] if symbol_hint is None else next(f for f in facets if symbol_hint in f.logical_document_id)


def _run(projection, context, facet, payload):
    """Validate one injected model output against one real facet."""
    from ingestion_bench.wiki_projection.compiler import build_facet_input

    page = context["pages_by_key"][facet.page_key]
    compiler = ScriptedFacetCompiler({(facet.page_key, facet.document_revision_id): payload})
    facet_input = build_facet_input(facet, page, context["sections_by_chunk"])
    output = compiler.compile_facet(facet_input, 1)
    return validate_facet(
        output, facet=facet, page=page, sections_by_chunk=context["sections_by_chunk"],
        all_page_keys=context["all_page_keys"],
    )


def _claim(chunk_id, **overrides):
    base = {
        "claim_id": "clm_1", "subject": "C-88", "predicate": "is implemented through",
        "object": "P-205", "claim_text": "Control C-88 is implemented through Procedure P-205.",
        "supporting_chunk_ids": [chunk_id],
        "supporting_quotes": ["Control C-88 is implemented through Procedure P-205"],
    }
    base.update(overrides)
    return base


# --- normalization primitives ------------------------------------------------


def test_normalize_triple_part_keeps_c88_and_c88a_distinct():
    assert normalize_triple_part("C-88") == "C-88"
    assert normalize_triple_part("Control C-88a") == "C-88A"
    assert normalize_triple_part("C-88") != normalize_triple_part("C-88a")


def test_normalize_whitespace_is_the_one_declared_normalization():
    assert normalize_whitespace("  a   b \n c ") == "a b c"


def test_resolve_page_key_is_strict_and_never_guesses(context):
    keys = context["all_page_keys"]
    assert resolve_page_key("Control C-88", keys) == "IDENT:C-88"
    assert resolve_page_key("C-88a", keys) == "IDENT:C-88A"
    assert resolve_page_key("the Payment Settlement business service", keys) is None
    assert resolve_page_key("Payment Settlement", keys) == "PHRASE:payment settlement"
    # An endpoint naming two identifiers is ambiguous -- never guessed.
    assert resolve_page_key("C-88 and P-205", keys) is None
    assert resolve_page_key("something never seen", keys) is None


# --- SS4.1.1-4.1.5: citation existence, scope and exactness ------------------


def test_a_well_formed_claim_is_accepted(projection, context):
    facet = _facet(projection, "IDENT:C-88", "CONTROL-LIBRARY")
    result = _run(projection, context, facet, {"claims": [_claim(facet.chunk_ids[0])]})
    claim = result.claims[0]
    assert claim.validation_status == "accepted"
    assert claim.citation_valid is True
    assert claim.rejection_reasons == []


def test_a_nonexistent_cited_chunk_is_rejected(projection, context):
    facet = _facet(projection, "IDENT:C-88", "CONTROL-LIBRARY")
    result = _run(projection, context, facet, {"claims": [_claim("0" * 64)]})
    claim = result.claims[0]
    assert claim.validation_status == "rejected"
    assert any("does not exist" in r for r in claim.rejection_reasons)


def test_a_cross_revision_citation_is_revision_scope_contamination(projection, context):
    """SS4.1.2/SS4.1.4 -- and SS3.1 makes it structurally near-impossible, since
    the compiler never sees another revision."""
    facet = _facet(projection, "IDENT:C-88", "CONTROL-LIBRARY")
    other = next(
        s.chunk_id for s in projection.sections if s.document_revision_id != facet.document_revision_id
    )
    result = _run(projection, context, facet, {"claims": [_claim(other)]})
    claim = result.claims[0]
    assert claim.validation_status == "rejected"
    assert any("revision-scope contamination" in r for r in claim.rejection_reasons)


def test_a_fabricated_quote_is_rejected(projection, context):
    facet = _facet(projection, "IDENT:C-88", "CONTROL-LIBRARY")
    result = _run(
        projection, context, facet,
        {"claims": [_claim(facet.chunk_ids[0], supporting_quotes=["C-88 was approved by the board"])]},
    )
    claim = result.claims[0]
    assert claim.citation_valid is False
    assert claim.validation_status == "rejected"
    assert any("not an exact substring" in r for r in claim.rejection_reasons)


def test_a_claim_with_no_quote_is_rejected(projection, context):
    facet = _facet(projection, "IDENT:C-88", "CONTROL-LIBRARY")
    result = _run(projection, context, facet, {"claims": [_claim(facet.chunk_ids[0], supporting_quotes=[])]})
    assert result.claims[0].validation_status == "rejected"
    assert any("no supporting quote" in r for r in result.claims[0].rejection_reasons)


def test_citation_validity_is_not_claim_correctness(projection, context):
    """SS4.3: a perfectly cited claim whose predicate misrepresents the passage
    is still mechanically 'accepted' -- and carries NO semantic verdict."""
    facet = _facet(projection, "IDENT:C-88", "CONTROL-LIBRARY")
    result = _run(
        projection, context, facet,
        {"claims": [_claim(facet.chunk_ids[0], predicate="is prohibited by")]},
    )
    claim = result.claims[0]
    assert claim.citation_valid is True
    assert claim.validation_status == "accepted"
    assert claim.owner_semantic_verdict is None


# --- SS4.1.6: hallucinated identifiers ---------------------------------------


def test_an_identifier_absent_from_the_evidence_is_rejected(projection, context):
    facet = _facet(projection, "IDENT:C-88", "CONTROL-LIBRARY")
    result = _run(
        projection, context, facet,
        {"claims": [_claim(facet.chunk_ids[0], object="P-999",
                           claim_text="Control C-88 is implemented through Procedure P-999.")]},
    )
    claim = result.claims[0]
    assert claim.validation_status == "rejected"
    assert any("P-999" in r for r in claim.rejection_reasons)


# --- SS4.1.7 / SS3.3: C-88 vs C-88A ------------------------------------------


def test_c88_and_c88a_are_never_merged_by_a_claim(projection, context):
    """A claim on the C-88 page whose subject is C-88a must not be accepted as
    if it were about this page."""
    facet = _facet(projection, "IDENT:C-88", "CONTROL-LIBRARY")
    result = _run(
        projection, context, facet,
        {"claims": [_claim(facet.chunk_ids[0], subject="C-88a", object="P-204",
                           claim_text="Control C-88a is implemented through Procedure P-204.",
                           supporting_quotes=["Control C-88 is implemented through Procedure P-205"])]},
    )
    assert result.claims[0].validation_status in ("rejected", "out_of_page_scope")


def test_an_alias_bridging_two_identifiers_is_never_supported(projection, context):
    facet = _facet(projection, "IDENT:C-88", "CONTROL-LIBRARY")
    result = _run(
        projection, context, facet,
        {"aliases": [{"alias": "C-88a", "supporting_chunk_ids": [facet.chunk_ids[0]],
                      "supporting_quotes": ["C-88"], "status": "supported"}]},
    )
    alias = result.aliases[0]
    assert alias.status != "supported"
    assert any("distinct identifiers are never merged" in r for r in alias.rejection_reasons)


def test_link_derivation_never_crosses_the_c88_boundary(projection, context):
    facet = _facet(projection, "IDENT:C-88", "CONTROL-LIBRARY")
    result = _run(projection, context, facet, {"claims": [_claim(facet.chunk_ids[0])]})
    for link in result.derived_links:
        assert "IDENT:C-88A" not in (link.subject_page_key, link.object_page_key)


# --- SS4.1.11: no timeless status --------------------------------------------


def test_a_status_term_outside_a_quote_is_rejected(projection, context):
    facet = _facet(projection, "IDENT:P-205", "PROCEDURE-CATALOGUE")
    result = _run(
        projection, context, facet,
        {"claims": [{
            "claim_id": "clm_1", "subject": "P-205", "predicate": "has status", "object": "current",
            "claim_text": "P-205 is the latest procedure and supersedes P-204.",
            "supporting_chunk_ids": [facet.chunk_ids[0]],
            "supporting_quotes": ["Procedure P-205"],
        }]},
    )
    claim = result.claims[0]
    assert claim.validation_status == "rejected"
    assert any("status term" in r for r in claim.rejection_reasons)


def test_a_status_term_inside_an_exact_quote_is_permitted(projection, context):
    """The rule permits a status word that sits inside the verbatim source span
    -- the compiler is quoting the source, not asserting currency itself."""
    facet = _facet(projection, "IDENT:P-205", "PROCEDURE-CATALOGUE")
    result = _run(
        projection, context, facet,
        {"claims": [{
            "claim_id": "clm_1", "subject": "P-205", "predicate": "is described as",
            "object": "the current operating procedure",
            "claim_text": "Procedure P-205 is the current operating procedure.",
            "supporting_chunk_ids": [facet.chunk_ids[0]],
            "supporting_quotes": ["Procedure P-205 is the current operating procedure"],
        }]},
    )
    claim = result.claims[0]
    assert not any("status term" in r for r in claim.rejection_reasons)
    assert claim.validation_status == "accepted"


def test_status_lexicon_is_closed_and_covers_the_contract_terms():
    for term in ("current", "effective", "in force", "active", "latest", "now applies", "supersedes"):
        assert term in STATUS_LEXICON


def test_a_summary_may_not_smuggle_a_status_term(projection, context):
    facet = _facet(projection, "IDENT:C-88", "CONTROL-LIBRARY")
    result = _run(
        projection, context, facet,
        {
            "claims": [_claim(facet.chunk_ids[0])],
            "summary_sentences": [{"sentence_id": "s1", "text": "C-88 is the currently effective control.",
                                   "supported_claim_ids": ["clm_1"]}],
        },
    )
    sentence = result.summary_sentences[0]
    assert sentence.reference_valid is False
    assert any("status term" in r for r in sentence.rejection_reasons)


# --- SS4.1.15: page coherence ------------------------------------------------


def test_a_claim_about_two_other_entities_is_out_of_page_scope(projection, context):
    """The SS4.1.15 example: a claim involving neither endpoint of this page's
    identity is retained in audit, not accepted, and cannot derive a link."""
    facet = _facet(projection, "IDENT:O-31", "OBLIGATION-REGISTER")
    result = _run(
        projection, context, facet,
        {"claims": [{
            "claim_id": "clm_1", "subject": "C-88", "predicate": "is implemented through", "object": "P-205",
            "claim_text": "C-88 is implemented through P-205.",
            "supporting_chunk_ids": [facet.chunk_ids[0]],
            "supporting_quotes": ["Control C-88"],
        }]},
    )
    claim = result.claims[0]
    assert claim.validation_status == "out_of_page_scope"
    assert claim.coherence_basis is None
    assert result.derived_links == []


def test_coherence_is_satisfied_by_subject_or_object(projection, context):
    facet = _facet(projection, "IDENT:C-88", "CONTROL-LIBRARY")
    as_subject = _run(projection, context, facet, {"claims": [_claim(facet.chunk_ids[0])]})
    assert as_subject.claims[0].coherence_basis == "identity_subject"

    facet_obl = _facet(projection, "IDENT:C-88", "OBLIGATION-REGISTER")
    as_object = _run(
        projection, context, facet_obl,
        {"claims": [{
            "claim_id": "clm_1", "subject": "O-31", "predicate": "is satisfied by", "object": "C-88",
            "claim_text": "Obligation O-31 is satisfied by Control C-88.",
            "supporting_chunk_ids": [facet_obl.chunk_ids[0]],
            "supporting_quotes": ["Obligation O-31 is satisfied by Control C-88"],
        }]},
    )
    assert as_object.claims[0].coherence_basis == "identity_object"
    assert as_object.claims[0].validation_status == "accepted"


def test_out_of_page_scope_is_reported_separately_from_rejected(projection, context):
    facet = _facet(projection, "IDENT:O-31", "OBLIGATION-REGISTER")
    result = _run(
        projection, context, facet,
        {"claims": [
            {"claim_id": "a", "subject": "C-88", "predicate": "x", "object": "P-205", "claim_text": "C-88 x P-205.",
             "supporting_chunk_ids": [facet.chunk_ids[0]], "supporting_quotes": ["Control C-88"]},
            {"claim_id": "b", "subject": "O-31", "predicate": "is satisfied by", "object": "C-88",
             "claim_text": "O-31 is satisfied by C-88.", "supporting_chunk_ids": [facet.chunk_ids[0]],
             "supporting_quotes": ["fabricated"]},
        ]},
    )
    statuses = {c.claim_id: c.validation_status for c in result.claims}
    assert statuses["a"] == "out_of_page_scope"
    assert statuses["b"] == "rejected"


# --- alias dependency handling (SS4.6 pass 1 vs pass 3) ----------------------


def test_a_claim_resting_on_an_alias_is_marked_pending_not_settled(projection, context):
    """The owner has not adjudicated yet, so a claim whose coherence rests
    SOLELY on a supported alias must be flagged pending -- SS4.6 pass 3 cannot
    run before adjudication returns."""
    facet = _facet(projection, "PHRASE:payment settlement", "SERVICE-CATALOGUE")
    chunk_id = facet.chunk_ids[0]
    result = _run(
        projection, context, facet,
        {
            "aliases": [{"alias": "Payment Settlement business service", "supporting_chunk_ids": [chunk_id],
                         "supporting_quotes": ["Payment Settlement business service"], "status": "supported"}],
            "claims": [{
                "claim_id": "clm_1", "subject": "Payment Settlement business service",
                "predicate": "is governed by", "object": "O-31",
                "claim_text": "The Payment Settlement business service is governed by Obligation O-31.",
                "supporting_chunk_ids": [chunk_id],
                "supporting_quotes": ["The Payment Settlement business service is governed by Obligation O-31"],
            }],
        },
    )
    claim = result.claims[0]
    assert claim.coherence_basis == "alias_subject"
    assert claim.depends_on_alias is True
    assert claim.pending_alias_adjudication is True
    assert claim.alias_dependency_ids


def test_an_alias_with_no_source_occurrence_is_not_supported(projection, context):
    facet = _facet(projection, "IDENT:C-88", "CONTROL-LIBRARY")
    result = _run(
        projection, context, facet,
        {"aliases": [{"alias": "Board Control 88", "supporting_chunk_ids": [facet.chunk_ids[0]],
                      "supporting_quotes": ["Board Control 88"], "status": "supported"}]},
    )
    alias = result.aliases[0]
    assert alias.span_valid is False
    assert alias.status != "supported"


def test_alias_span_validity_is_not_alias_semantic_correctness(projection, context):
    """SS4.5: a verbatim occurrence yields span_valid=True and NO semantic
    verdict -- even when the string plainly names a different entity."""
    facet = _facet(projection, "PHRASE:payment settlement", "APP-PORTFOLIO")
    result = _run(
        projection, context, facet,
        {"aliases": [{"alias": "Application Portfolio", "supporting_chunk_ids": [facet.chunk_ids[0]],
                      "supporting_quotes": ["Application Portfolio"], "status": "supported"}]},
    )
    alias = result.aliases[0]
    assert alias.owner_semantic_verdict is None


# --- SS4.1.8 / SS4.4: summary reference validity -----------------------------


def test_a_summary_referencing_no_accepted_claim_is_invalid(projection, context):
    facet = _facet(projection, "IDENT:C-88", "CONTROL-LIBRARY")
    result = _run(
        projection, context, facet,
        {"summary_sentences": [{"sentence_id": "s1", "text": "C-88 does things.",
                                "supported_claim_ids": ["clm_missing"]}]},
    )
    sentence = result.summary_sentences[0]
    assert sentence.reference_valid is False
    assert any("unknown claim" in r for r in sentence.rejection_reasons)


def test_summary_reference_validity_is_not_summary_correctness(projection, context):
    """SS4.4: a sentence that inverts its claim's direction still passes the
    mechanical check, and carries no semantic verdict."""
    facet = _facet(projection, "IDENT:C-88", "CONTROL-LIBRARY")
    result = _run(
        projection, context, facet,
        {
            "claims": [_claim(facet.chunk_ids[0])],
            "summary_sentences": [{"sentence_id": "s1",
                                   "text": "Procedure P-205 is implemented through Control C-88.",
                                   "supported_claim_ids": ["clm_1"]}],
        },
    )
    sentence = result.summary_sentences[0]
    assert sentence.reference_valid is True
    assert sentence.owner_semantic_verdict is None


# --- SS4.1.12: duplicates and contradictions ---------------------------------


def test_duplicate_claims_are_deduped_with_both_citations_retained(projection, context):
    facet = _facet(projection, "IDENT:C-88", "CONTROL-LIBRARY")
    chunk_id = facet.chunk_ids[0]
    result = _run(
        projection, context, facet,
        {"claims": [
            _claim(chunk_id, claim_id="a"),
            _claim(chunk_id, claim_id="b", supporting_quotes=["Control C-88 is implemented through"]),
        ]},
    )
    by_id = {c.claim_id: c for c in result.claims}
    assert by_id["b"].duplicate_of == "a"
    assert len(by_id["a"].supporting_quotes) >= 2  # both citations retained, nothing dropped


def test_contradictory_claims_are_both_demoted_to_uncertain(projection, context):
    facet = _facet(projection, "IDENT:C-88", "CONTROL-LIBRARY")
    chunk_id = facet.chunk_ids[0]
    result = _run(
        projection, context, facet,
        {"claims": [
            _claim(chunk_id, claim_id="a", object="P-205"),
            _claim(chunk_id, claim_id="b", object="C-88",
                   claim_text="Control C-88 is implemented through Control C-88.",
                   supporting_quotes=["Control C-88"]),
        ]},
    )
    by_id = {c.claim_id: c for c in result.claims}
    assert by_id["a"].validation_status == "uncertain"
    assert by_id["b"].validation_status == "uncertain"
    assert by_id["a"].contradicts_claim_ids == ["b"]
    # Neither is silently dropped.
    assert len(result.claims) == 2


def test_an_uncertain_claim_derives_no_link(projection, context):
    facet = _facet(projection, "IDENT:C-88", "CONTROL-LIBRARY")
    chunk_id = facet.chunk_ids[0]
    result = _run(
        projection, context, facet,
        {"claims": [
            _claim(chunk_id, claim_id="a", object="P-205"),
            _claim(chunk_id, claim_id="b", object="C-88",
                   claim_text="Control C-88 is implemented through Control C-88.",
                   supporting_quotes=["Control C-88"]),
        ]},
    )
    assert result.derived_links == []


# --- SS3.7: claim-derived links ----------------------------------------------


def test_an_accepted_claim_derives_forward_and_inverse_links(projection, context):
    facet = _facet(projection, "IDENT:C-88", "CONTROL-LIBRARY")
    result = _run(projection, context, facet, {"claims": [_claim(facet.chunk_ids[0])]})
    directions = {link.traversal_direction for link in result.derived_links}
    assert directions == {"forward", "inverse"}
    for link in result.derived_links:
        assert link.subject_page_key == "IDENT:C-88"
        assert link.object_page_key == "IDENT:P-205"
        assert link.is_authoritative_lineage is False
        assert link.source_citations["supporting_chunk_ids"]


def test_the_inverse_predicate_is_never_fabricated(projection, context):
    facet = _facet(projection, "IDENT:C-88", "CONTROL-LIBRARY")
    result = _run(projection, context, facet, {"claims": [_claim(facet.chunk_ids[0])]})
    predicates = {link.predicate for link in result.derived_links}
    assert predicates == {"is implemented through"}  # verbatim, in both directions


def test_an_unresolvable_endpoint_emits_no_link_and_is_counted(projection, context):
    facet = _facet(projection, "IDENT:C-88", "CONTROL-LIBRARY")
    result = _run(
        projection, context, facet,
        {"claims": [_claim(facet.chunk_ids[0], object="the control library process",
                           claim_text="Control C-88 is implemented through the control library process.",
                           supporting_quotes=["Control C-88 is implemented through"])]},
    )
    assert result.derived_links == []
    assert result.unlinkable_claim_endpoints
    assert result.unlinkable_claim_endpoints[0]["endpoint_role"] == "object"


def test_a_rejected_or_out_of_scope_claim_never_derives_a_link(projection, context):
    facet = _facet(projection, "IDENT:O-31", "OBLIGATION-REGISTER")
    result = _run(
        projection, context, facet,
        {"claims": [{
            "claim_id": "clm_1", "subject": "C-88", "predicate": "is implemented through", "object": "P-205",
            "claim_text": "C-88 is implemented through P-205.",
            "supporting_chunk_ids": [facet.chunk_ids[0]], "supporting_quotes": ["Control C-88"],
        }]},
    )
    assert result.claims[0].validation_status == "out_of_page_scope"
    assert result.derived_links == []


# --- THE hard invariants ------------------------------------------------------


def test_validation_never_alters_membership(projection, context):
    """SS4.0: no validation outcome may remove or alter a facet's membership,
    source chunks, anchors or postings."""
    before = [f.model_copy(deep=True) for f in projection.facets]
    facet = _facet(projection, "IDENT:C-88", "CONTROL-LIBRARY")
    for payload in (
        {"claims": [_claim(facet.chunk_ids[0])]},
        {"claims": [_claim(facet.chunk_ids[0], supporting_quotes=["fabricated"])]},
        {"claims": []},
        {"claims": [{"claim_id": "x", "subject": "Q-1", "predicate": "p", "object": "R-2",
                     "claim_text": "Q-1 p R-2.", "supporting_chunk_ids": [facet.chunk_ids[0]],
                     "supporting_quotes": ["Control"]}]},
    ):
        _run(projection, context, facet, payload)
    assert_membership_unchanged(before, projection.facets)


def test_membership_guard_actually_detects_a_violation(projection):
    """The guard must not be vacuous."""
    before = [f.model_copy(deep=True) for f in projection.facets]
    tampered = [f.model_copy(deep=True) for f in projection.facets]
    tampered[0].membership_hash = "0" * 64
    with pytest.raises(AssertionError, match="MEMBERSHIP INDEPENDENCE VIOLATED"):
        assert_membership_unchanged(before, tampered)


def test_a_facet_with_every_claim_rejected_keeps_its_chunks_and_anchors(projection, context):
    facet = _facet(projection, "IDENT:C-88", "CONTROL-LIBRARY")
    chunks_before = list(facet.chunk_ids)
    postings_before = list(facet.posting_hashes)
    result = _run(
        projection, context, facet,
        {"claims": [_claim(facet.chunk_ids[0], supporting_quotes=["totally fabricated"])]},
    )
    assert result.claims[0].validation_status == "rejected"
    assert facet.chunk_ids == chunks_before
    assert facet.posting_hashes == postings_before


def test_a_zero_claim_facet_remains_fully_navigable(projection, context):
    """SS3.7.1: claim missing -> navigation degrades to the deterministic anchor
    fallback, and connectivity survives."""
    facet = _facet(projection, "IDENT:P-205", "PROCEDURE-CATALOGUE")
    result = _run(projection, context, facet, {"claims": [], "aliases": [], "summary_sentences": []})
    assert result.claims == []
    assert result.derived_links == []

    section_ids = {
        s.section_id for s in projection.sections if s.chunk_id in facet.chunk_ids
    }
    deterministic = [
        link for link in projection.links
        if link.from_section_id in section_ids and link.link_type == "exact_anchor"
    ]
    assert deterministic, "the facet must still be reachable by deterministic anchors with zero claims"
    assert facet.chunk_ids and facet.posting_hashes


def test_a_generation_failure_leaves_the_deterministic_facet_intact(projection, context):
    from ingestion_bench.wiki_projection.compiler import FacetCompilationOutput

    facet = _facet(projection, "IDENT:C-88", "CONTROL-LIBRARY")
    page = context["pages_by_key"][facet.page_key]
    failed = FacetCompilationOutput(
        page_key=facet.page_key, document_revision_id=facet.document_revision_id, run_id=1,
        model_identity="x", temperature=0.0, prompt_version="p", prompt_sha256="h",
        input_chunk_ids=list(facet.chunk_ids), generation_failed=True, generation_error="boom",
    )
    result = validate_facet(
        failed, facet=facet, page=page, sections_by_chunk=context["sections_by_chunk"],
        all_page_keys=context["all_page_keys"],
    )
    assert result.generation_failed is True
    assert result.facet_failed is True
    assert facet.chunk_ids and facet.posting_hashes
    section_ids = {s.section_id for s in projection.sections if s.chunk_id in facet.chunk_ids}
    assert any(link.from_section_id in section_ids for link in projection.links)


def test_the_validator_never_writes_a_semantic_verdict(projection, context):
    """SS4.3/SS4.4/SS4.5: the three semantic judgements are the owner's alone."""
    facet = _facet(projection, "IDENT:C-88", "CONTROL-LIBRARY")
    result = _run(
        projection, context, facet,
        {
            "aliases": [{"alias": "C-88", "supporting_chunk_ids": [facet.chunk_ids[0]],
                         "supporting_quotes": ["C-88"], "status": "supported"}],
            "claims": [_claim(facet.chunk_ids[0])],
            "summary_sentences": [{"sentence_id": "s1", "text": "C-88 is implemented through P-205.",
                                   "supported_claim_ids": ["clm_1"]}],
        },
    )
    for record in [*result.claims, *result.aliases, *result.summary_sentences]:
        assert record.owner_semantic_verdict is None


def test_the_validator_module_writes_no_verdict_field():
    """Structural guard: `owner_semantic_verdict` is typed `None` on every
    validated record, so a verdict cannot be assigned by this code at all."""
    from ingestion_bench.wiki_projection.validation import (
        ValidatedAlias,
        ValidatedClaim,
        ValidatedSummarySentence,
    )

    for model in (ValidatedClaim, ValidatedAlias, ValidatedSummarySentence):
        annotation = model.model_fields["owner_semantic_verdict"].annotation
        assert annotation is type(None), f"{model.__name__} allows a code-written verdict"


def test_nothing_is_discarded_silently(projection, context):
    """SS4.1.14: every rejected item is persisted WITH its reason."""
    facet = _facet(projection, "IDENT:C-88", "CONTROL-LIBRARY")
    result = _run(
        projection, context, facet,
        {"claims": [
            _claim(facet.chunk_ids[0], claim_id="good"),
            _claim(facet.chunk_ids[0], claim_id="bad", supporting_quotes=["fabricated"]),
        ]},
    )
    assert {c.claim_id for c in result.claims} == {"good", "bad"}
    bad = next(c for c in result.claims if c.claim_id == "bad")
    assert bad.validation_status == "rejected"
    assert bad.rejection_reasons


# =============================================================================
# PASS 3 -- deterministic re-validation after owner adjudication (SS4.6)
# =============================================================================


def _pass3(projection, context, validation, verdict_map):
    """Apply pass 3 to one validated facet with an explicit verdict map."""
    from ingestion_bench.wiki_projection.validation import AdjudicationVerdictSet, apply_pass3

    return apply_pass3(
        validation, page=context["pages_by_key"][validation.page_key],
        sections_by_chunk=context["sections_by_chunk"], all_page_keys=context["all_page_keys"],
        verdicts=AdjudicationVerdictSet(verdicts=verdict_map),
    )


def _all_correct(validation):
    from ingestion_bench.wiki_projection.validation import required_adjudication_item_ids

    return {item_id: "CORRECT" for item_id in required_adjudication_item_ids(validation)}


def _postings_by_chunk(projection):
    out: dict[str, list] = {}
    for posting in projection.postings:
        out.setdefault(posting.chunk_id, []).append(posting)
    return out


def _c88_payload(chunk_id):
    """One supported alias, one accepted claim, one summary referencing it."""
    return {
        "aliases": [{"alias": "C-88", "supporting_chunk_ids": [chunk_id],
                     "supporting_quotes": ["C-88"], "status": "supported"}],
        "claims": [_claim(chunk_id)],
        "summary_sentences": [{"sentence_id": "s1", "text": "C-88 is implemented through P-205.",
                               "supported_claim_ids": ["clm_1"]}],
    }


@pytest.fixture
def c88_validation(projection, context):
    facet = _facet(projection, "IDENT:C-88", "CONTROL-LIBRARY")
    return facet, _run(projection, context, facet, _c88_payload(facet.chunk_ids[0]))


def test_all_correct_verdicts_keep_everything(projection, context, c88_validation):
    _facet_obj, validation = c88_validation
    result = _pass3(projection, context, validation, _all_correct(validation))

    assert result.surviving_accepted_claim_ids == ["clm_1"]
    assert result.surviving_summary_sentence_ids == ["s1"]
    assert result.payload_eligible_alias_texts == ["C-88"]
    assert result.withdrawn_claim_ids == []
    assert result.derived_links, "a surviving accepted claim must still derive its links"


@pytest.mark.parametrize("failing_verdict", ["INCORRECT", "UNVERIFIABLE"])
def test_owner_failed_claim_is_withdrawn_from_payload_links_and_summary(
    projection, context, c88_validation, failing_verdict
):
    """SS4.6's binding invariant: nothing that failed adjudication reaches a
    vector, a summary, or a derived link. SS3.3/SS3.5 treat INCORRECT and
    UNVERIFIABLE alike."""
    from ingestion_bench.wiki_projection.assembly import compose_payload_preview
    from ingestion_bench.wiki_projection.validation import claim_item_id, facet_key_of

    facet, validation = c88_validation
    verdicts = _all_correct(validation)
    key = facet_key_of(validation.page_key, validation.document_revision_id)
    verdicts[claim_item_id(key, "clm_1")] = failing_verdict

    result = _pass3(projection, context, validation, verdicts)

    # the mechanical record is preserved; withdrawal is tracked separately
    assert validation.claims[0].validation_status == "accepted"
    assert result.withdrawn_claim_ids == ["clm_1"]
    assert result.surviving_accepted_claim_ids == []
    # ... it reaches no derived link ...
    assert result.derived_links == []
    # ... nor the summary that depended on it ...
    assert result.surviving_summary_sentence_ids == []
    assert "s1" in result.withdrawn_summary_ids
    # ... nor the vector payload.
    payload = compose_payload_preview(
        validation, facet=facet, page=context["pages_by_key"][validation.page_key],
        sections_by_chunk=context["sections_by_chunk"],
        postings_by_chunk=_postings_by_chunk(projection), pass3=result,
    )
    component_5 = next(c for c in payload.components if c.number == 5)
    component_6 = next(c for c in payload.components if c.number == 6)
    component_7 = next(c for c in payload.components if c.number == 7)
    assert component_6.text == "", "the withdrawn claim must not reach the vector payload"
    assert component_7.text == ""
    # ... while the SOURCE passage is untouched. Component 5 is `source_derived`
    # and no owner verdict may remove it, even though this corpus's source
    # sentence happens to read the same as the withdrawn claim_text.
    assert "Control C-88 is implemented through Procedure P-205." in component_5.text
    assert component_5.label == "source_derived"


def test_correct_claim_remains_in_the_final_payload(projection, context, c88_validation):
    from ingestion_bench.wiki_projection.assembly import compose_payload_preview

    facet, validation = c88_validation
    result = _pass3(projection, context, validation, _all_correct(validation))
    payload = compose_payload_preview(
        validation, facet=facet, page=context["pages_by_key"][validation.page_key],
        sections_by_chunk=context["sections_by_chunk"],
        postings_by_chunk=_postings_by_chunk(projection), pass3=result,
    )
    component_6 = next(c for c in payload.components if c.number == 6)
    assert "Control C-88 is implemented through Procedure P-205." in component_6.text
    assert payload.is_final is True
    assert payload.pending_components == []


def test_a_correct_summary_dies_with_its_only_withdrawn_claim(projection, context, c88_validation):
    """Its OWN verdict is CORRECT, but SS4.1.8 reference validity no longer
    holds once the claim it references is withdrawn."""
    from ingestion_bench.wiki_projection.validation import claim_item_id, facet_key_of, summary_item_id

    _facet_obj, validation = c88_validation
    key = facet_key_of(validation.page_key, validation.document_revision_id)
    verdicts = _all_correct(validation)
    verdicts[claim_item_id(key, "clm_1")] = "INCORRECT"
    assert verdicts[summary_item_id(key, "s1")] == "CORRECT"

    result = _pass3(projection, context, validation, verdicts)
    assert result.surviving_summary_sentence_ids == []
    assert "every claim it references was withdrawn" in result.withdrawal_reasons["s1"]


def test_a_summary_survives_if_another_referenced_claim_survives(projection, context):
    """The rule is SS4.1.8's '>= 1 accepted claim', not 'all of them'."""
    from ingestion_bench.wiki_projection.validation import claim_item_id, facet_key_of

    # adj_rev1 is the corpus's only multi-sentence chunk, so it is the only
    # facet that can carry two independently-quotable claims about one identity.
    facet = _facet(projection, "IDENT:C-77", "ADJACENT-DOMAIN")
    chunk_id = facet.chunk_ids[0]
    validation = _run(
        projection, context, facet,
        {"claims": [
            {"claim_id": "a", "subject": "Obligation O-32", "predicate": "is satisfied by",
             "object": "Control C-77", "claim_text": "Obligation O-32 is satisfied by Control C-77.",
             "supporting_chunk_ids": [chunk_id],
             "supporting_quotes": ["Obligation O-32 is satisfied by Control C-77"]},
            {"claim_id": "b", "subject": "Control C-77", "predicate": "is implemented through",
             "object": "Procedure P-301", "claim_text": "Control C-77 is implemented through Procedure P-301.",
             "supporting_chunk_ids": [chunk_id],
             "supporting_quotes": ["Control C-77 is implemented through Procedure P-301"]},
        ],
         "summary_sentences": [{"sentence_id": "s1", "text": "C-77 satisfies O-32 and uses P-301.",
                                "supported_claim_ids": ["a", "b"]}]},
    )
    assert [c.validation_status for c in validation.claims] == ["accepted", "accepted"]
    key = facet_key_of(validation.page_key, validation.document_revision_id)
    verdicts = _all_correct(validation)
    verdicts[claim_item_id(key, "a")] = "INCORRECT"

    result = _pass3(projection, context, validation, verdicts)
    assert result.withdrawn_claim_ids == ["a"]
    assert result.surviving_accepted_claim_ids == ["b"]
    assert result.surviving_summary_sentence_ids == ["s1"]


def test_a_failed_summary_verdict_withdraws_only_the_summary(projection, context, c88_validation):
    from ingestion_bench.wiki_projection.validation import facet_key_of, summary_item_id

    _facet_obj, validation = c88_validation
    key = facet_key_of(validation.page_key, validation.document_revision_id)
    verdicts = _all_correct(validation)
    verdicts[summary_item_id(key, "s1")] = "INCORRECT"

    result = _pass3(projection, context, validation, verdicts)
    assert result.withdrawn_summary_ids == ["s1"]
    assert result.surviving_accepted_claim_ids == ["clm_1"], "the claim itself is unaffected"
    assert result.derived_links, "its links survive too"


def test_incorrect_alias_cascade_is_preserved(projection, context):
    """The pre-existing SS4.6 cascade must still fire: a claim whose coherence
    rested SOLELY on a withdrawn alias becomes out_of_page_scope."""
    from ingestion_bench.wiki_projection.validation import alias_item_id, facet_key_of

    facet = _facet(projection, "PHRASE:payment settlement", "SERVICE-CATALOGUE")
    chunk_id = facet.chunk_ids[0]
    validation = _run(
        projection, context, facet,
        {
            "aliases": [{"alias": "Payment Settlement business service", "supporting_chunk_ids": [chunk_id],
                         "supporting_quotes": ["Payment Settlement business service"], "status": "supported"}],
            "claims": [{
                "claim_id": "clm_1", "subject": "Payment Settlement business service",
                "predicate": "is governed by", "object": "O-31",
                "claim_text": "The Payment Settlement business service is governed by Obligation O-31.",
                "supporting_chunk_ids": [chunk_id],
                "supporting_quotes": ["The Payment Settlement business service is governed by Obligation O-31"],
            }],
        },
    )
    assert validation.claims[0].depends_on_alias is True

    key = facet_key_of(validation.page_key, validation.document_revision_id)
    verdicts = _all_correct(validation)
    alias_id = validation.aliases[0].alias_id
    verdicts[alias_item_id(key, alias_id)] = "INCORRECT"

    result = _pass3(projection, context, validation, verdicts)
    assert result.withdrawn_alias_ids == [alias_id]
    assert result.payload_eligible_alias_texts == []
    assert result.demoted_to_out_of_page_scope == ["clm_1"]
    assert result.surviving_accepted_claim_ids == []
    assert result.derived_links == []


def test_an_absent_verdict_is_not_a_pass(projection, context, c88_validation):
    """SS4.6 requires EVERY accepted claim to be adjudicated; a missing verdict
    must not be silently treated as approval."""
    from ingestion_bench.wiki_projection.validation import (
        AdjudicationVerdictSet,
        required_adjudication_item_ids,
    )

    _facet_obj, validation = c88_validation
    result = _pass3(projection, context, validation, {})
    assert result.surviving_accepted_claim_ids == []
    assert result.surviving_summary_sentence_ids == []
    assert result.payload_eligible_alias_texts == []

    missing = AdjudicationVerdictSet().missing_items(required_adjudication_item_ids(validation))
    assert len(missing) == 3  # one claim, one alias, one summary


def test_pass3_reports_before_and_after_counts(projection, context, c88_validation):
    """SS4.6: 'Counts are reported before and after pass 3.'"""
    from ingestion_bench.wiki_projection.validation import claim_item_id, facet_key_of

    _facet_obj, validation = c88_validation
    key = facet_key_of(validation.page_key, validation.document_revision_id)
    verdicts = _all_correct(validation)
    verdicts[claim_item_id(key, "clm_1")] = "INCORRECT"
    result = _pass3(projection, context, validation, verdicts)

    assert result.counts_before["accepted_claims"] == 1
    assert result.counts_after["accepted_claims"] == 0
    assert result.counts_before["derived_links"] == 2  # forward + inverse
    assert result.counts_after["derived_links"] == 0
    assert result.withdrawal_reasons["clm_1"]


@pytest.mark.parametrize(
    "verdict_scenario",
    ["all_correct", "all_incorrect", "all_unverifiable", "none_recorded", "mixed"],
)
def test_no_owner_verdict_can_alter_deterministic_membership_or_hashes(
    projection, context, c88_validation, verdict_scenario
):
    """SS4.0/SS2.2: membership is untouched by all three passes. No verdict may
    move a facet, a chunk, an anchor, a posting or the projection hash."""
    from ingestion_bench.wiki_projection.projection import compute_projection_hash
    from ingestion_bench.wiki_projection.validation import required_adjudication_item_ids

    before_hash = projection.projection_hash
    before_membership = {(f.page_key, f.document_revision_id): f.membership_hash for f in projection.facets}
    before_postings = len(projection.postings)
    before_links = len(projection.links)

    _facet_obj, validation = c88_validation
    item_ids = required_adjudication_item_ids(validation)
    verdicts = {
        "all_correct": {i: "CORRECT" for i in item_ids},
        "all_incorrect": {i: "INCORRECT" for i in item_ids},
        "all_unverifiable": {i: "UNVERIFIABLE" for i in item_ids},
        "none_recorded": {},
        "mixed": {i: ("CORRECT" if n % 2 else "INCORRECT") for n, i in enumerate(item_ids)},
    }[verdict_scenario]

    _pass3(projection, context, validation, verdicts)

    assert projection.projection_hash == before_hash
    assert compute_projection_hash(projection) == before_hash
    assert {(f.page_key, f.document_revision_id): f.membership_hash for f in projection.facets} == before_membership
    assert len(projection.postings) == before_postings
    assert len(projection.links) == before_links


def test_verdict_set_hash_is_stable_and_order_independent():
    from ingestion_bench.wiki_projection.validation import AdjudicationVerdictSet

    a = AdjudicationVerdictSet(verdicts={"X": "CORRECT", "Y": "INCORRECT"})
    b = AdjudicationVerdictSet(verdicts={"Y": "INCORRECT", "X": "CORRECT"})
    assert a.verdict_set_sha256() == b.verdict_set_sha256()
    assert len(a.verdict_set_sha256()) == 64
    c = AdjudicationVerdictSet(verdicts={"X": "CORRECT", "Y": "CORRECT"})
    assert c.verdict_set_sha256() != a.verdict_set_sha256()
