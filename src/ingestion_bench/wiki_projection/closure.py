"""Stage 7C.1 post-adjudication CLOSURE (Revision 6 SS4.6 pass 3 onward).

Deterministic path from the owner's verdict set to a frozen final Stage 7C.1
representation:

    owner verdict set
      -> completeness / integrity preflight (fail closed)
      -> SS4.6 pass 3          (existing `apply_pass3`, not re-implemented here)
      -> final facet payloads  (existing `compose_payload_preview`, final mode)
      -> final facet embeddings
      -> expected-fact recall  (deferred until now, SS8A / Gate Q-6)
      -> final Gate Q
      -> closure artifacts

**ZERO compiler calls.** Nothing in this module constructs, imports or reaches a
facet compiler; a test asserts that structurally. The only model invoked is the
existing embedding provider, and only after pass 3 completes.

Two boundaries this module holds deliberately:

* it never writes to the frozen Runs 1/2/3, the frozen owner packet, the frozen
  7C.0 projection, or the plan;
* it never rewrites a mechanical `validation_status` to match an owner verdict.
  Withdrawal is a separate, owner-originated state (SS4.2 keeps the mechanical
  record in the audit); conflating them would destroy the distinction SS4.3-4.5
  exist to preserve.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from ingestion_bench.wiki_projection.assembly import FacetPayloadPreview, compose_payload_preview
from ingestion_bench.wiki_projection.benchmark import PRIMARY_RUN_ID, Stage7C1Result, facet_key
from ingestion_bench.wiki_projection.model import WikiProjection
from ingestion_bench.wiki_projection.validation import (
    AdjudicationVerdictSet,
    DerivedLink,
    FacetValidationResult,
    Pass3FacetResult,
    apply_pass3,
    required_adjudication_item_ids,
)

CLOSURE_CONTRACT_VERSION = "stage7c1_closure_v1"


class ClosurePreflightError(RuntimeError):
    """A frozen-input or verdict-set integrity check failed. Raised BEFORE pass
    3 and before any embedding is created -- the closure fails closed."""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(payload) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# --- preflight ---------------------------------------------------------------


class PreflightReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    projection_hash: str
    projection_hash_matches_expected: bool
    runs_match_projection: bool
    primary_run_id: int
    model_identity: str
    prompt_version: str
    prompt_sha256: str
    packet_sha256: str | None
    verdict_set_sha256: str
    required_item_count: int
    supplied_item_count: int
    missing_item_ids: list[str]
    extra_item_ids: list[str]
    verdict_distribution: dict[str, int]
    all_checks_passed: bool


def run_preflight(
    *,
    projection: WikiProjection,
    runs: Stage7C1Result,
    verdicts: AdjudicationVerdictSet,
    expected_projection_hash: str,
    expected_verdict_set_sha256: str,
    expected_packet_sha256: str | None = None,
    packet_sha256: str | None = None,
    expected_item_count: int = 68,
) -> PreflightReport:
    """Every check the closure must pass before pass 3 or embedding creation.

    Raises `ClosurePreflightError` on the first failure rather than degrading:
    a partial closure over unverified inputs would produce a representation
    nobody could later trust.
    """
    failures: list[str] = []

    # 1 -- the frozen Stage 7C.0 projection still rebuilds to its frozen hash.
    projection_ok = projection.projection_hash == expected_projection_hash
    if not projection_ok:
        failures.append(
            f"projection hash {projection.projection_hash} != frozen {expected_projection_hash}"
        )

    # 2 -- the stored runs were compiled against THAT projection.
    runs_ok = runs.projection_hash == expected_projection_hash
    if not runs_ok:
        failures.append(f"stored runs' projection hash {runs.projection_hash} != frozen {expected_projection_hash}")

    # 3 -- the primary run is exactly Run 1 (SS8F, designated before execution).
    if runs.primary_run_id != PRIMARY_RUN_ID:
        failures.append(f"primary run is {runs.primary_run_id}, expected {PRIMARY_RUN_ID}")
    if str(PRIMARY_RUN_ID) not in runs.validations_by_run:
        failures.append("stored runs contain no Run 1")

    # 4 -- model / prompt provenance matches the frozen Run-1 provenance.
    primary = next((p for p in runs.run_provenance if p.run_id == PRIMARY_RUN_ID), None)
    if primary is None:
        raise ClosurePreflightError("stored runs carry no Run-1 provenance record")
    if not primary.is_primary:
        failures.append("Run-1 provenance is not flagged primary")

    # 5 -- the owner packet is the frozen packet.
    if expected_packet_sha256 is not None and packet_sha256 is not None:
        if packet_sha256 != expected_packet_sha256:
            failures.append(f"adjudication packet SHA {packet_sha256} != frozen {expected_packet_sha256}")

    # 6/7/8/9 -- verdict set completeness: exact set equality, exact count.
    run_1 = runs.validations_by_run[str(PRIMARY_RUN_ID)]
    required = sorted({item for validation in run_1.values() for item in required_adjudication_item_ids(validation)})
    supplied = set(verdicts.verdicts)
    missing = sorted(set(required) - supplied)
    extra = sorted(supplied - set(required))
    if missing:
        failures.append(f"{len(missing)} required verdict(s) missing, e.g. {missing[:3]}")
    if extra:
        failures.append(f"{len(extra)} unexpected verdict id(s), e.g. {extra[:3]}")
    if len(required) != expected_item_count:
        failures.append(f"required adjudication items = {len(required)}, expected {expected_item_count}")
    if len(supplied) != expected_item_count:
        failures.append(f"supplied verdicts = {len(supplied)}, expected {expected_item_count}")

    # 10 -- the verdict set is the one the owner signed off.
    observed_sha = verdicts.verdict_set_sha256()
    if observed_sha != expected_verdict_set_sha256:
        failures.append(f"verdict-set SHA {observed_sha} != expected {expected_verdict_set_sha256}")

    distribution: dict[str, int] = {}
    for verdict in verdicts.verdicts.values():
        distribution[verdict] = distribution.get(verdict, 0) + 1

    report = PreflightReport(
        projection_hash=projection.projection_hash,
        projection_hash_matches_expected=projection_ok,
        runs_match_projection=runs_ok,
        primary_run_id=runs.primary_run_id,
        model_identity=primary.model_identity,
        prompt_version=primary.prompt_version,
        prompt_sha256=primary.prompt_sha256,
        packet_sha256=packet_sha256,
        verdict_set_sha256=observed_sha,
        required_item_count=len(required),
        supplied_item_count=len(supplied),
        missing_item_ids=missing,
        extra_item_ids=extra,
        verdict_distribution=dict(sorted(distribution.items())),
        all_checks_passed=not failures,
    )
    if failures:
        raise ClosurePreflightError(
            "Stage 7C.1 closure preflight FAILED -- stopping before pass 3 and before any embedding:\n  - "
            + "\n  - ".join(failures)
        )
    return report


# --- final facet embeddings --------------------------------------------------


class FacetEmbeddingRecord(BaseModel):
    """One final W1 facet embedding with the full SS6.2 provenance set.

    `is_authoritative_lineage` is False always: an embedding of a derived
    payload is never promoted to authoritative evidence (SS4.7, SS7.1).
    """

    model_config = ConfigDict(extra="forbid")

    page_key: str
    document_revision_id: str
    facet_membership_hash: str

    payload_text: str
    payload_sha256: str
    component_manifest: list[dict]
    payload_truncated_components: list[int]
    summary_payload_dedup_count: int

    projection_hash: str
    verdict_set_sha256: str
    compiler_model_identity: str
    prompt_version: str
    prompt_sha256: str
    repeatability_run_id: int

    embedding_model: str
    embedding_dimension: int
    embedding: list[float]

    source_chunk_ids: list[str]
    source_revision_id: str
    generated_at: str
    representation_derivation: str = "post_adjudication_w1_facet_payload"
    is_authoritative_lineage: bool = False


def build_final_embeddings(
    *,
    payloads: dict[str, FacetPayloadPreview],
    projection: WikiProjection,
    embedding_provider,
    verdict_set_sha256: str,
    compiler_model_identity: str,
    prompt_version: str,
    prompt_sha256_value: str,
) -> list[FacetEmbeddingRecord]:
    """Embed exactly the final post-pass-3 payload text, one vector per facet.

    No page-level vector, no second representation, no reranker, no LLM. The
    existing provider is used unchanged.
    """
    facets_by_key = {facet_key(f.page_key, f.document_revision_id): f for f in projection.facets}
    ordered_keys = sorted(payloads)
    texts = [payloads[key].preview_text for key in ordered_keys]
    embedded = embedding_provider.embed(texts)
    generated_at = datetime.now(timezone.utc).isoformat()

    records: list[FacetEmbeddingRecord] = []
    for key, vector in zip(ordered_keys, embedded.vectors):
        payload = payloads[key]
        facet = facets_by_key[key]
        records.append(
            FacetEmbeddingRecord(
                page_key=payload.page_key, document_revision_id=payload.document_revision_id,
                facet_membership_hash=facet.membership_hash,
                payload_text=payload.preview_text, payload_sha256=payload.preview_sha256,
                component_manifest=[
                    {
                        "number": c.number, "name": c.name, "label": c.label,
                        "present": bool(c.text), "provenance": c.provenance,
                    }
                    for c in payload.components
                ],
                payload_truncated_components=payload.payload_truncated_components,
                summary_payload_dedup_count=payload.summary_payload_dedup_count,
                projection_hash=projection.projection_hash,
                verdict_set_sha256=verdict_set_sha256,
                compiler_model_identity=compiler_model_identity,
                prompt_version=prompt_version, prompt_sha256=prompt_sha256_value,
                repeatability_run_id=PRIMARY_RUN_ID,
                embedding_model=embedding_provider.model_identity,
                embedding_dimension=len(vector), embedding=list(vector),
                source_chunk_ids=list(facet.chunk_ids), source_revision_id=facet.document_revision_id,
                generated_at=generated_at,
            )
        )
    return records


# --- expected-fact recall (Gate Q-6), deferred until now ---------------------


# Determiners and generic enterprise type nouns. This mirrors the normalization
# the FROZEN Stage 7B.1 Graph extractor applied when its own expected-fact edge
# recall (0.80) was measured -- lifted as a neutral local rule rather than
# imported, because a Graph runtime dependency is forbidden (SS1.3/SS9.1, and the
# same lifting precedent as `identifiers_in` under Q9).
#
# It exists so SS9.4's Wiki-vs-Graph attribution compares like with like. Scoring
# Wiki under a stricter rule than the Graph figure was computed with would
# understate Wiki by construction.
_RECALL_ARTICLES = ("the ", "a ", "an ")
_RECALL_TYPE_PREFIXES = ("application ", "control ", "obligation ", "procedure ")
_RECALL_TYPE_SUFFIXES = (" business service", " operating procedure", " service")


def entity_normalize(text: str) -> str:
    """Identifier-preserving entity normalization for recall matching only.

    Never used to build, repair or alter a W1 artifact -- solely to decide
    whether a surviving claim expresses a frozen expected fact.
    """
    from ingestion_bench.wiki_projection.validation import normalize_triple_part

    result = normalize_triple_part(text)
    changed = True
    while changed:
        changed = False
        for article in _RECALL_ARTICLES:
            if result.startswith(article):
                result, changed = result[len(article):], True
        for prefix in _RECALL_TYPE_PREFIXES:
            if result.startswith(prefix) and len(result) > len(prefix):
                result, changed = result[len(prefix):], True
        for suffix in _RECALL_TYPE_SUFFIXES:
            if result.endswith(suffix) and len(result) > len(suffix):
                result, changed = result[: -len(suffix)], True
    return result.strip()


class RecallLedgerEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_id: str
    subject: str
    predicate: str
    object: str
    supporting_chunk_id: str
    matched: bool
    matched_by_claim_ids: list[str] = Field(default_factory=list)
    match_basis: str | None = None
    # True when the fact matches under entity normalization but NOT under exact
    # normalized endpoints -- i.e. the difference is determiner/type-noun
    # wording only. Reported so the sensitivity of the rule is visible.
    matched_only_after_entity_normalization: bool = False
    miss_reason: str | None = None


class RecallLedger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    numerator: int
    denominator: int
    recall: float
    mapping_rule: str
    entries: list[RecallLedgerEntry]
    surviving_claim_count: int
    # The same computation under the stricter exact-endpoint rule, reported so
    # the primary figure's sensitivity to the normalization choice is explicit
    # rather than buried.
    strict_numerator: int = 0
    strict_recall: float = 0.0
    strict_rule: str = ""


def compute_expected_fact_recall(
    *,
    surviving_claims_by_facet: dict[str, list],
    contract_facts: list[dict],
    evidence_by_fact: dict,
) -> RecallLedger:
    """Expected-fact recall over the SURVIVING post-pass-3 claims.

    Deferred to closure on purpose (Gate Q-6): scoring earlier would have put
    benchmark truth beside unadjudicated output. Truth is read ONLY here, only
    to score -- never to add, repair or rewrite a claim.

    PRIMARY mapping rule, declared before the number is read: a frozen fact is
    recalled when some surviving accepted claim (a) cites that fact's supporting
    chunk, and (b) has endpoints whose ENTITY normalization equals the fact's
    {subject, object} as a set.

    Two deliberate choices, each with its reason:

    * **Entity normalization, not exact.** The frozen Stage 7B.1 Graph figure
      this will be compared against in SS9.4 (edge recall 0.80) was itself
      measured after `normalize_entity_name`, which strips determiners and
      generic type nouns. Scoring Wiki under a stricter rule would understate it
      relative to Graph by construction and make the attribution unsound. The
      stricter exact-endpoint figure is computed and reported alongside, so the
      sensitivity is visible rather than buried.
    * **Direction is not re-tested.** Direction correctness is an owner semantic
      judgement (SS4.3) already applied in pass 3; a surviving claim has been
      judged faithful, and re-testing direction mechanically here would
      double-count that judgement.
    """
    from ingestion_bench.wiki_projection.validation import normalize_triple_part

    surviving = [claim for claims in surviving_claims_by_facet.values() for claim in claims]

    entries: list[RecallLedgerEntry] = []
    strict_hits = 0
    for fact in contract_facts:
        evidence = evidence_by_fact[fact["fact_id"]]
        target_chunk = evidence.supporting_chunk_id
        fact_entity = {entity_normalize(fact["subject"]), entity_normalize(fact["object"])}
        fact_exact = {normalize_triple_part(fact["subject"]), normalize_triple_part(fact["object"])}

        matched_ids: list[str] = []
        strict_ids: list[str] = []
        cites_chunk = False
        for claim in surviving:
            if target_chunk not in claim.supporting_chunk_ids:
                continue
            cites_chunk = True
            if {entity_normalize(claim.subject), entity_normalize(claim.object)} == fact_entity:
                matched_ids.append(claim.claim_id)
            if {normalize_triple_part(claim.subject), normalize_triple_part(claim.object)} == fact_exact:
                strict_ids.append(claim.claim_id)

        if strict_ids:
            strict_hits += 1
        miss_reason = None
        if not matched_ids:
            miss_reason = (
                "no surviving claim cites this fact's supporting chunk"
                if not cites_chunk
                else "surviving claims cite the chunk but state different endpoints"
            )
        entries.append(
            RecallLedgerEntry(
                fact_id=fact["fact_id"], subject=fact["subject"], predicate=fact["predicate"],
                object=fact["object"], supporting_chunk_id=target_chunk,
                matched=bool(matched_ids), matched_by_claim_ids=sorted(matched_ids),
                match_basis="chunk_and_entity_normalized_endpoints" if matched_ids else None,
                matched_only_after_entity_normalization=bool(matched_ids) and not strict_ids,
                miss_reason=miss_reason,
            )
        )

    numerator = sum(1 for e in entries if e.matched)
    denominator = len(entries)
    return RecallLedger(
        numerator=numerator, denominator=denominator,
        recall=(numerator / denominator) if denominator else 0.0,
        mapping_rule=(
            "PRIMARY: a frozen expected fact is recalled when a SURVIVING post-pass-3 accepted claim cites "
            "that fact's supporting chunk AND its ENTITY-normalized endpoints equal the fact's "
            "{subject, object} as a set. Entity normalization strips determiners and generic type nouns, "
            "mirroring the normalization under which the frozen Stage 7B.1 Graph recall (0.80) was measured, "
            "so SS9.4 compares like with like. Direction is not re-tested mechanically: SS4.3 makes it an "
            "owner judgement already applied in pass 3."
        ),
        entries=entries, surviving_claim_count=len(surviving),
        strict_numerator=strict_hits,
        strict_recall=(strict_hits / denominator) if denominator else 0.0,
        strict_rule=(
            "SENSITIVITY: the same computation requiring EXACT normalized endpoints (no determiner or "
            "type-noun stripping). Reported for transparency; not the gated figure, because the frozen "
            "Graph comparator was not measured this way."
        ),
    )


# --- final Gate Q ------------------------------------------------------------


class GateQCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion: str
    description: str
    required: str
    observed: object
    status: str  # PASS | FAIL
    detail: str = ""


class FinalGateQ(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criteria: list[GateQCriterion]
    overall_status: str
    failing_criteria: list[str]
    evaluation_rule: str
    q5_decision_id: str
    verdict_set_sha256: str
    projection_hash: str


def evaluate_final_gate_q(
    *,
    run_1: dict[str, FacetValidationResult],
    pass3_by_facet: dict[str, Pass3FacetResult],
    verdicts: AdjudicationVerdictSet,
    repeatability,
    recall: RecallLedger,
    q5_decision: dict,
    verdict_set_sha256: str,
    projection_hash: str,
) -> FinalGateQ:
    """All ten criteria, computed independently and combined conjunctively.

    Every criterion is evaluated even once one has failed: Gate Q is a record of
    where the compilation stood, not a short-circuit.
    """
    from ingestion_bench.wiki_projection.validation import claim_item_id, facet_key_of, summary_item_id

    thresholds = q5_decision["thresholds"]

    total_claims = sum(len(v.claims) for v in run_1.values())
    citation_valid = sum(1 for v in run_1.values() for c in v.claims if c.citation_valid)
    accepted = [
        (facet_key_of(v.page_key, v.document_revision_id), c)
        for v in run_1.values() for c in v.claims if c.validation_status == "accepted"
    ]
    accepted_correct = sum(1 for key, c in accepted if verdicts.passes(claim_item_id(key, c.claim_id)))

    invalid_refs = sum(
        1 for v in run_1.values() for c in v.claims
        for reason in c.rejection_reasons if "source_ref" in reason or "does not exist" in reason
    )
    revision_scope = sum(
        1 for v in run_1.values() for c in v.claims
        for reason in c.rejection_reasons if "revision-scope contamination" in reason or "another revision" in reason
    )
    false_merges = max(repeatability.false_merges_by_run.values())
    ceiling_breaches = max(repeatability.ceiling_breaches_by_run.values())
    generation_failures = sum(1 for v in run_1.values() if v.generation_failed)

    summaries = [
        (facet_key_of(v.page_key, v.document_revision_id), s)
        for v in run_1.values() for s in v.summary_sentences
    ]
    summary_incorrect = sum(1 for key, s in summaries if verdicts.failed(summary_item_id(key, s.sentence_id)))
    summary_correct = sum(1 for key, s in summaries if verdicts.passes(summary_item_id(key, s.sentence_id)))

    supported_aliases = [
        (facet_key_of(v.page_key, v.document_revision_id), a)
        for v in run_1.values() for a in v.aliases if a.status == "supported"
    ]
    from ingestion_bench.wiki_projection.validation import alias_item_id

    alias_incorrect = sum(1 for key, a in supported_aliases if verdicts.failed(alias_item_id(key, a.alias_id)))

    claim_jaccard = list(repeatability.accepted_claim_set_jaccard.values())
    citation_rates = [
        e["rate"] for e in repeatability.citation_exact_agreement_on_matched_accepted_claims.values()
    ]
    claim_jaccard_min = min(claim_jaccard) if claim_jaccard else None
    citation_min = min(citation_rates) if citation_rates else None

    precision = (accepted_correct / len(accepted)) if accepted else 1.0
    citation_validity = (citation_valid / total_claims) if total_claims else 1.0

    q8_ok = (
        claim_jaccard_min is not None
        and claim_jaccard_min >= thresholds["accepted_claim_set_pairwise_jaccard_min"]
        and citation_min is not None
        and citation_min >= thresholds["citation_exact_agreement_on_matched_accepted_claims_min"]
        and false_merges <= thresholds["false_merges_max_each_run"]
        and ceiling_breaches <= thresholds["ceiling_breaches_max_each_run"]
    )
    q8_detail = []
    if claim_jaccard_min is not None and claim_jaccard_min < thresholds["accepted_claim_set_pairwise_jaccard_min"]:
        q8_detail.append(
            f"accepted_claim_set_jaccard min {claim_jaccard_min:.6f} < "
            f"{thresholds['accepted_claim_set_pairwise_jaccard_min']}"
        )
    if citation_min is not None and citation_min < thresholds["citation_exact_agreement_on_matched_accepted_claims_min"]:
        q8_detail.append(
            f"citation_exact_agreement min {citation_min:.6f} < "
            f"{thresholds['citation_exact_agreement_on_matched_accepted_claims_min']}"
        )

    criteria = [
        GateQCriterion(
            criterion="Q-1", description="Citation validity", required="1.00",
            observed=citation_validity, status="PASS" if citation_validity >= 1.0 else "FAIL",
            detail=f"{citation_valid}/{total_claims} claims with exact-substring citations",
        ),
        GateQCriterion(
            criterion="Q-2", description="Invalid source references", required="0",
            observed=invalid_refs, status="PASS" if invalid_refs == 0 else "FAIL",
        ),
        GateQCriterion(
            criterion="Q-3", description="Revision-scope contamination", required="0",
            observed=revision_scope, status="PASS" if revision_scope == 0 else "FAIL",
            detail="renamed from 'authority contamination' in Revision 6; the compiler is authority-blind",
        ),
        GateQCriterion(
            criterion="Q-4", description="False merges (incl. C-88 / C-88A)", required="0",
            observed=false_merges, status="PASS" if false_merges == 0 else "FAIL",
        ),
        GateQCriterion(
            criterion="Q-5", description="Accepted-claim precision (owner-adjudicated)", required=">= 0.95",
            observed=precision, status="PASS" if precision >= 0.95 else "FAIL",
            detail=f"{accepted_correct} owner-CORRECT / {len(accepted)} mechanically accepted",
        ),
        GateQCriterion(
            criterion="Q-6", description="Expected-fact recall in surviving accepted claims", required=">= 0.80",
            observed=recall.recall, status="PASS" if recall.recall >= 0.80 else "FAIL",
            detail=f"{recall.numerator}/{recall.denominator} frozen facts recalled",
        ),
        GateQCriterion(
            criterion="Q-7", description="Summary correctness (owner-adjudicated)", required="0 incorrect",
            observed=summary_incorrect, status="PASS" if summary_incorrect == 0 else "FAIL",
            detail=f"{summary_correct} correct / {summary_incorrect} incorrect of {len(summaries)} sentences",
        ),
        GateQCriterion(
            criterion="Q-8", description="Repeatability (Q5-approved thresholds)",
            required=(
                f"accepted-claim Jaccard >= {thresholds['accepted_claim_set_pairwise_jaccard_min']}, "
                f"citation exact agreement >= {thresholds['citation_exact_agreement_on_matched_accepted_claims_min']}, "
                "false merges 0, ceiling breaches 0"
            ),
            observed={
                "accepted_claim_set_jaccard_min": claim_jaccard_min,
                "citation_exact_agreement_min": citation_min,
                "false_merges_any_run": false_merges,
                "ceiling_breaches_any_run": ceiling_breaches,
            },
            status="PASS" if q8_ok else "FAIL",
            detail="; ".join(q8_detail),
        ),
        GateQCriterion(
            criterion="Q-9", description="Budget and ceilings", required="no breach; within declared cap",
            observed={"ceiling_breaches": ceiling_breaches, "generation_failures": generation_failures},
            status="PASS" if ceiling_breaches == 0 and generation_failures == 0 else "FAIL",
        ),
        GateQCriterion(
            criterion="Q-10", description="Supported-alias precision (owner-adjudicated)",
            required="0 incorrect supported aliases", observed=alias_incorrect,
            status="PASS" if alias_incorrect == 0 else "FAIL",
            detail=f"{len(supported_aliases) - alias_incorrect}/{len(supported_aliases)} supported aliases owner-CORRECT",
        ),
    ]

    failing = [c.criterion for c in criteria if c.status == "FAIL"]
    return FinalGateQ(
        criteria=criteria,
        overall_status="PASS" if not failing else "FAIL",
        failing_criteria=failing,
        evaluation_rule="conjunctive: every criterion must PASS; no averaging, no partial credit",
        q5_decision_id=q5_decision["decision_id"],
        verdict_set_sha256=verdict_set_sha256,
        projection_hash=projection_hash,
    )


# --- the whole closure -------------------------------------------------------


class Stage7C1ClosureResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str = CLOSURE_CONTRACT_VERSION
    generated_at: str
    preflight: PreflightReport

    pass3_by_facet: dict[str, Pass3FacetResult]
    aggregate_counts_before: dict[str, int]
    aggregate_counts_after: dict[str, int]
    withdrawn_claim_item_ids: list[str]
    withdrawn_summary_item_ids: list[str]
    withdrawn_alias_item_ids: list[str]

    final_payloads: dict[str, FacetPayloadPreview]
    final_derived_links: list[DerivedLink]
    embeddings: list[FacetEmbeddingRecord]

    recall: RecallLedger
    gate_q: FinalGateQ

    closure_sha256: str = ""

    def semantic_hash(self) -> str:
        """A hash over everything the closure DERIVES, excluding wall-clock
        fields, so a re-run over identical frozen inputs is provably identical."""
        payload = {
            "pass3": {k: v.model_dump(mode="json") for k, v in sorted(self.pass3_by_facet.items())},
            "payload_sha256": {k: v.preview_sha256 for k, v in sorted(self.final_payloads.items())},
            "links": sorted(link.link_id for link in self.final_derived_links),
            "embedding_payload_sha256": sorted(e.payload_sha256 for e in self.embeddings),
            "recall": self.recall.model_dump(mode="json"),
            "gate_q": [c.model_dump(mode="json") for c in self.gate_q.criteria],
            "overall": self.gate_q.overall_status,
        }
        return _sha256(_canonical(payload))
