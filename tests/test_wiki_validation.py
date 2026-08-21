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
