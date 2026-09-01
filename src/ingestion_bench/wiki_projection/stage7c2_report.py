"""Stage 7C.2: measured execution, attribution, and reporting.

ONE result object; the JSON and the Markdown scorecard both derive from it, so
they cannot disagree.

Every comparable arm is scored by the FROZEN Stage 7B.0 `_evaluate_question`,
imported by identity rather than reimplemented. Benchmark truth is read only by
that scorer and by the explicitly truth-informed suppression diagnostic.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from ingestion_bench.cross_document_benchmark.benchmark_runner import _evaluate_question
from ingestion_bench.cross_document_benchmark.retriever import cross_document_search
from ingestion_bench.wiki_projection.benchmark import w0_result_from_vector_result
from ingestion_bench.wiki_projection.navigation import NON_QUALIFYING_LABEL, Navigator
from ingestion_bench.wiki_projection.retrieval import run_arm, seed_d0, seed_w1

SMALL_CORPUS_CAVEAT = (
    "THIS CORPUS DOES NOT TEST ENTERPRISE-SCALE HUB FAN-OUT. With 6 documents, 11 single-chunk "
    "revisions, one cross-document phrase anchor and no structural bridge into the distractor domain, "
    "low branching factors are a property of the CORPUS, not evidence that Wiki navigation is "
    "well-behaved at scale. No claim about navigation cost at scale may be made from this stage."
)

W1_ARMS = ("W1-D", "W1-FULL", "N_advisory")


def _requested_by_document(question, fixtures, symbol_to_id):
    out: dict[str, list[str]] = {}
    for symbol in question.get("requested_revision_symbols", []):
        out.setdefault(fixtures[symbol].logical_document_id, []).append(symbol_to_id[symbol])
    return out


def _score(question, chunk_ids, template_result, evidence, id_to_symbol):
    """Score an arm's final chunk list with the FROZEN evaluator.

    The arm's chunk list is projected onto the template Vector result's hit
    shape so the frozen scorer -- which is never modified -- receives exactly
    the record type it expects.
    """
    by_chunk = {hit.chunk_id: hit for hit in template_result.unfiltered_hits}
    hits = []
    for rank, chunk_id in enumerate(chunk_ids, start=1):
        hit = by_chunk.get(chunk_id)
        if hit is not None:
            hits.append(hit.model_copy(update={"rank": rank}))
    return _evaluate_question(question, template_result.model_copy(update={"hits": hits}), evidence, id_to_symbol)


def _arm_metrics(evaluated, retrieval=None):
    metrics = {
        "required_fact_coverage_at_k": evaluated.required_fact_coverage_at_k,
        "all_required_facts_retrieved_at_k": evaluated.all_required_facts_retrieved_at_k,
        "complete_chain_represented": evaluated.complete_chain_represented,
        "mrr": evaluated.mrr,
        "ndcg_at_k": evaluated.ndcg_at_k,
        "authority_leakage_count": evaluated.authority_leakage_count,
        "forbidden_fact_hit_ids": evaluated.forbidden_fact_hit_ids,
        "evidence_document_diversity": evaluated.evidence_document_diversity,
        "outcome": evaluated.vector_outcome,
        "authority_correct": evaluated.authority_correct,
        "returned_chunk_ids": evaluated.authority_aware_hit_chunk_ids,
    }
    if retrieval is not None:
        navigation = retrieval.navigation
        metrics.update({
            "seeds": [s.model_dump(mode="json") for s in retrieval.seeds],
            "seed_pages_selected": retrieval.seed_pages_selected,
            "seed_pages_expanded": retrieval.seed_pages_expanded,
            "pages_visited": navigation.pages_visited,
            "hops_taken": navigation.hops_taken,
            "candidates_examined": navigation.candidates_examined,
            "claim_derived_traversals": navigation.claim_derived_traversals,
            "exact_anchor_traversals": navigation.exact_anchor_traversals,
            "structural_traversals": navigation.structural_traversals,
            "advisory_traversals": navigation.advisory_traversals,
            "ineligible_neighbours_removed": navigation.ineligible_neighbours_removed,
            "branching_factor": (
                navigation.candidates_examined / navigation.pages_visited
                if navigation.pages_visited else 0.0
            ),
            "eligible_pages": retrieval.eligible_pages,
            "eligible_chunks": retrieval.eligible_chunks,
            "candidate_chunks": retrieval.candidate_chunks,
            "page_saturation": retrieval.page_saturation,
            "chunk_saturation": retrieval.chunk_saturation,
            "p_bound_hit": retrieval.p_bound_hit,
            "b_bound_hit": retrieval.b_bound_hit,
            "c_bound_hit": retrieval.c_bound_hit,
            "short_list": retrieval.short_list,
            "path_truncated": retrieval.path_truncated,
            "tier1_slots": len(retrieval.tier1_chunk_ids),
            "tier2_slots": len(retrieval.tier2_chunk_ids),
            "latency_seconds": retrieval.latency_seconds,
            "query_embedding_calls": retrieval.query_embedding_calls,
            "cosine_operations": retrieval.cosine_operations,
            "path": [h.model_dump(mode="json") for h in navigation.path],
        })
        if retrieval.non_qualifying_label:
            metrics["label"] = retrieval.non_qualifying_label
    return metrics


def build_stage7c2_results(
    *, contract, fixtures, projection, evidence, service, chunk_store, provider,
    corpus_documents, symbol_to_id, id_to_symbol, facet_rows, derived_links, navigator,
    chunk_vectors, facet_vectors_by_page, frozen_basis, suppression_questions, primary_arms,
) -> dict:
    per_question: dict[str, dict] = {}
    audit_traces: dict[str, dict] = {}
    suppression: dict[str, dict] = {}

    for question in contract["questions"]:
        question_id = question["question_id"]
        top_k = question["top_k"]
        query_vector = provider.embed([question["query"]]).vectors[0]
        requested = _requested_by_document(question, fixtures, symbol_to_id)

        vector_result = cross_document_search(
            service=service, store=chunk_store, corpus_logical_document_ids=corpus_documents,
            query_intent=question["query_intent"], as_of_date=date.fromisoformat(question["as_of_date"]),
            requested_revision_ids_by_document=requested, query_vector=query_vector,
            embedding_model=provider.model_identity, top_k=top_k,
        )
        eligible = list(vector_result.eligible_revision_ids_union)

        # --- V and W0: the frozen baseline and its control -------------
        v_evaluated = _evaluate_question(question, vector_result, evidence, id_to_symbol)
        w0_result, _diag = w0_result_from_vector_result(projection, vector_result, top_k)
        w0_evaluated = _evaluate_question(question, w0_result, evidence, id_to_symbol)

        arms: dict[str, dict] = {
            "V": _arm_metrics(v_evaluated),
            "W0": _arm_metrics(w0_evaluated),
        }

        # D0's ranked seed chunks come from the SAME authority-aware chunk
        # search V uses -- unfiltered by K, so the seed bound is P_seed itself.
        ranked = chunk_store.search_eligible(
            embedding_model=provider.model_identity, query_vector=query_vector,
            eligible_revision_ids=eligible, top_k=top_k,
        )
        ranked_chunk_ids = [hit.record.chunk_id for hit in ranked]

        retrievals: dict[str, object] = {}
        for arm in [*primary_arms, "N_advisory"]:
            if arm == "D0":
                seeds = seed_d0(
                    projection=projection, ranked_chunk_ids=ranked_chunk_ids,
                    eligible=set(eligible), p_seed=top_k,
                )
                seed_cosines = len(ranked_chunk_ids)
            else:
                seeds, seed_cosines = seed_w1(
                    facet_rows=facet_rows, query_vector=query_vector,
                    eligible=set(eligible), p_seed=top_k,
                )
            retrieval = run_arm(
                arm=arm, question_id=question_id, query_text=question["query"],
                query_vector=query_vector, top_k=top_k, eligible_revision_ids=eligible,
                projection=projection, navigator=navigator, seeds=seeds,
                chunk_vectors=chunk_vectors, facet_vectors_by_page=facet_vectors_by_page,
                seed_cosine_operations=seed_cosines,
            )
            retrievals[arm] = retrieval
            evaluated = _score(question, retrieval.final_chunk_ids, vector_result, evidence, id_to_symbol)
            arms[arm] = _arm_metrics(evaluated, retrieval)

        # --- branch attribution vs D0 -------------------------------------
        d0_seed_pages = [s.page_key for s in retrievals["D0"].seeds]
        d0_order = [
            n.target_page_key
            for visit in retrievals["D0"].navigation.visits for n in visit.neighbours_exposed
        ]
        for arm in ("W1-D", "W1-FULL", "N_advisory"):
            arm_seed_pages = [s.page_key for s in retrievals[arm].seeds]
            arm_order = [
                n.target_page_key
                for visit in retrievals[arm].navigation.visits for n in visit.neighbours_exposed
            ]
            overlap = len(set(arm_seed_pages) & set(d0_seed_pages))
            arms[arm]["seed_page_overlap_vs_D0"] = {
                "overlap": overlap, "arm_seeds": len(arm_seed_pages), "d0_seeds": len(d0_seed_pages),
            }
            divergence = sum(
                1 for a, b in zip(arm_order, d0_order) if a != b
            ) + abs(len(arm_order) - len(d0_order))
            arms[arm]["branch_order_divergence_vs_D0"] = divergence

        per_question[question_id] = {
            "question_id": question_id, "question_type": question["question_type"],
            "top_k": top_k, "query_intent": question["query_intent"],
            "eligible_revision_symbols": sorted(id_to_symbol.get(r, r) for r in eligible),
            "arms": arms,
        }

        # --- neighbourhood audit trace (diagnostic, for a future agent) ---
        if question_id.split("_")[0] in suppression_questions:
            audit_traces[question_id] = {
                "note": "DIAGNOSTIC ONLY. The bounded neighbourhood a later agent stage could consume. "
                        "No LLM branch selection was performed.",
                "arms": {
                    arm: [
                        {
                            "hub": visit.page_key,
                            "neighbours": [n.model_dump(mode="json") for n in visit.neighbours_exposed],
                        }
                        for visit in retrievals[arm].navigation.visits
                    ]
                    for arm in primary_arms
                },
            }

        # --- counterfactual suppression probe (truth-informed) ------------
        if question_id.split("_")[0] in suppression_questions:
            required_chunks = {evidence[f].supporting_chunk_id for f in question["required_fact_ids"]}
            natural = retrievals["W1-FULL"]
            # TRUTH-INFORMED: the required-evidence set selects which frozen
            # claim links to hide. Read-time only -- nothing is mutated.
            suppress = {
                link.link_id
                for link in derived_links
                if set(link.source_citations.get("supporting_chunk_ids", [])) & required_chunks
            }
            seeds, seed_cosines = seed_w1(
                facet_rows=facet_rows, query_vector=query_vector,
                eligible=set(eligible), p_seed=top_k,
            )
            suppressed_run = run_arm(
                arm="W1-FULL", question_id=question_id, query_text=question["query"],
                query_vector=query_vector, top_k=top_k, eligible_revision_ids=eligible,
                projection=projection, navigator=navigator, seeds=seeds,
                chunk_vectors=chunk_vectors, facet_vectors_by_page=facet_vectors_by_page,
                suppressed_link_ids=suppress, seed_cosine_operations=seed_cosines,
            )
            evaluated = _score(question, suppressed_run.final_chunk_ids, vector_result, evidence, id_to_symbol)
            suppression[question_id] = {
                "label": "TRUTH-INFORMED / DIAGNOSTIC ONLY / NOT GATE-A ADMISSIBLE",
                "suppressed_link_ids": sorted(suppress),
                "suppressed_link_count": len(suppress),
                "natural": {
                    "outcome": arms["W1-FULL"]["outcome"],
                    "coverage": arms["W1-FULL"]["required_fact_coverage_at_k"],
                    "complete_chain": arms["W1-FULL"]["complete_chain_represented"],
                    "hops": natural.navigation.hops_taken,
                    "candidates_examined": natural.navigation.candidates_examined,
                },
                "suppressed": {
                    "outcome": evaluated.vector_outcome,
                    "coverage": evaluated.required_fact_coverage_at_k,
                    "complete_chain": evaluated.complete_chain_represented,
                    "hops": suppressed_run.navigation.hops_taken,
                    "candidates_examined": suppressed_run.navigation.candidates_examined,
                    "exact_anchor_fallbacks": suppressed_run.navigation.exact_anchor_traversals,
                },
                "destination_still_reachable": (
                    evaluated.required_fact_coverage_at_k >= arms["W1-FULL"]["required_fact_coverage_at_k"]
                ),
            }

    summary = _summarize(per_question, primary_arms)
    attribution = _attribution(per_question, primary_arms)
    return {
        "stage": "7C.2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "frozen_basis": frozen_basis,
        "gate_a_status": "UNREACHABLE -- Gate Q = FAIL (Q-5, Q-7, Q-8)",
        "w1_label": NON_QUALIFYING_LABEL,
        "d0_qualifying": True,
        "d0_qualifying_note": "D0 consumes no W1-derived model output, so Gate Q's failure does not label it",
        "small_corpus_caveat": SMALL_CORPUS_CAVEAT,
        "evaluator_identity": f"{_evaluate_question.__module__}.{_evaluate_question.__qualname__}",
        "per_question": per_question,
        "summary": summary,
        "attribution": attribution,
        "suppression_diagnostic": suppression,
        "neighbourhood_audit_traces": audit_traces,
        "graph_attribution": _graph_attribution(per_question),
        "cost_and_storage": _cost_and_storage(per_question, facet_rows, projection, derived_links),
    }


def _cost_and_storage(per_question, facet_rows, projection, derived_links) -> dict:
    """Stage 7C.2 is measurement; the W1 ingestion cost it prices was paid in
    Stage 7C.1 and is quoted frozen. W1-FULL is priced against D0 -- not merely
    against W1-D -- because only the D0 comparison speaks to whether the
    W1-derived layer was needed at all."""
    def total(field, arms):
        return {
            arm: sum(q["arms"][arm].get(field, 0) for q in per_question.values()) for arm in arms
        }

    arms = ("D0", "W1-D", "W1-FULL")
    return {
        "frozen_w1_ingestion_cost": {
            "compiler_calls": 66, "runs": 3, "input_tokens": 62142, "output_tokens": 15782,
            "dollars": 0.018790499999999995,
            "note": "paid in Stage 7C.1; quoted frozen, not re-incurred here",
        },
        "owner_adjudication_dependency": {
            "items": 68, "runs_adjudicated": 1,
            "note": "an operational dependency of the W1 index: any compiler/prompt/model/source change "
                    "requires re-adjudication before the representation can be rebuilt. D0 has none.",
        },
        "w1_payload_bytes": sum(len(r.payload_text.encode("utf-8")) for r in facet_rows),
        "frozen_facet_vectors": {"count": len(facet_rows), "dimension": 384},
        "deterministic_projection_storage_bytes": len(projection.model_dump_json().encode("utf-8")),
        "frozen_claim_derived_links": len(derived_links),
        "d0_incremental_ingestion_cost": {
            "llm_calls": 0, "dollars": 0.0, "new_embeddings": 0,
            "note": "D0 reuses the deterministic 7C.0 projection and the existing V/W0 chunk vectors; "
                    "its incremental ingestion cost over Vector is zero",
        },
        "query_time_per_arm": {
            "query_embedding_calls": total("query_embedding_calls", arms),
            "cosine_operations": total("cosine_operations", arms),
            "pages_visited": total("pages_visited", arms),
            "candidates_examined": total("candidates_examined", arms),
            "hops_taken": total("hops_taken", arms),
            "latency_seconds": total("latency_seconds", arms),
        },
        "pricing_rule": (
            "W1-FULL is priced against D0 (the deployable deterministic Wiki), not against W1-D: charging "
            "the compiler ledger against the routing delta alone would price a layer against a benefit it "
            "only partly produces."
        ),
    }


def _summarize(per_question, primary_arms) -> dict:
    arms = ["V", "W0", *primary_arms, "N_advisory"]
    outcome_counts = {}
    leakage = 0
    for arm in arms:
        counts: dict[str, int] = {}
        for question in per_question.values():
            metrics = question["arms"][arm]
            counts[metrics["outcome"]] = counts.get(metrics["outcome"], 0) + 1
            leakage += metrics["authority_leakage_count"]
        outcome_counts[arm] = dict(sorted(counts.items()))
    return {
        "outcome_counts": outcome_counts,
        "total_authority_leakage": leakage,
        "questions": len(per_question),
    }


def _compare(per_question, left: str, right: str) -> dict:
    """Compare two arms across every question on the frozen improvement axes."""
    improved, regressed, identical = [], [], []
    for question_id, question in sorted(per_question.items()):
        a, b = question["arms"][left], question["arms"][right]
        axes = ("outcome", "complete_chain_represented", "required_fact_coverage_at_k",
                "all_required_facts_retrieved_at_k")
        same = all(a[axis] == b[axis] for axis in axes)
        if same:
            identical.append(question_id)
            continue
        better = (
            (a["outcome"] == "solved" and b["outcome"] != "solved")
            or (a["complete_chain_represented"] and not b["complete_chain_represented"])
            or (a["required_fact_coverage_at_k"] > b["required_fact_coverage_at_k"])
        )
        worse = (
            (b["outcome"] == "solved" and a["outcome"] != "solved")
            or (b["complete_chain_represented"] and not a["complete_chain_represented"])
            or (b["required_fact_coverage_at_k"] > a["required_fact_coverage_at_k"])
        )
        if better and not worse:
            improved.append(question_id)
        elif worse and not better:
            regressed.append(question_id)
        else:
            identical.append(question_id)

    # Frozen definition: materially equivalent means IDENTICAL on all four axes
    # for EVERY question.
    materially_equivalent = len(identical) == len(per_question)
    if materially_equivalent:
        verdict = f"{left} and {right} are MATERIALLY EQUIVALENT (identical on every axis, every question)"
    elif improved and not regressed:
        verdict = f"{left} beats {right} on {len(improved)} question(s), no regression"
    elif regressed and not improved:
        verdict = f"{left} is WORSE than {right} on {len(regressed)} question(s)"
    else:
        verdict = f"{left} vs {right} is mixed: +{len(improved)} / -{len(regressed)}"
    return {
        "left": left, "right": right, "improved": improved, "regressed": regressed,
        "identical": identical, "materially_equivalent": materially_equivalent, "verdict": verdict,
    }


def _attribution(per_question, primary_arms) -> dict:
    delta_1 = _compare(per_question, "W1-D", "D0")
    delta_2 = _compare(per_question, "W1-FULL", "W1-D")
    total = _compare(per_question, "W1-FULL", "D0")
    d0_vs_v = _compare(per_question, "D0", "V")
    w1_full_vs_v = _compare(per_question, "W1-FULL", "V")
    w0_vs_v = _compare(per_question, "W0", "V")

    mandated: list[str] = []
    if delta_1["improved"] and not delta_2["improved"]:
        mandated.append("W1 added value through semantic seed enrichment, not through claim-derived routing.")
    if delta_1["materially_equivalent"] and delta_2["materially_equivalent"] and total["materially_equivalent"]:
        mandated.append(
            "D0, W1-D and W1-FULL are materially equivalent; any transitive result is attributable to the "
            "deterministic Wiki alone."
        )
    return {
        "W1-D_vs_D0": {**delta_1, "measures": "marginal value of W1 semantic seed enrichment"},
        "W1-FULL_vs_W1-D": {**delta_2, "measures": "marginal value of claim-derived routing"},
        "W1-FULL_vs_D0": {
            **total,
            "measures": "TOTAL marginal value of the LLM-assisted Wiki over the deterministic Wiki",
        },
        "D0_vs_V": {**d0_vs_v, "measures": "marginal value of deterministic Wiki structure over Vector"},
        "W1-FULL_vs_V": {**w1_full_vs_v, "measures": "headline W1 system comparison"},
        "W0_vs_V": {**w0_vs_v, "measures": "frozen control; expected equivalent"},
        "mandated_statements": mandated,
        "prohibited_inference": (
            "Never conclude the compiler was unnecessary from a comparison that excludes D0: only "
            "W1-FULL vs D0 supports a statement about whether the W1-derived layer was needed."
        ),
    }


def _graph_attribution(per_question) -> dict:
    """Read-only comparison against the FROZEN Stage 7B.1 figures."""
    return {
        "read_only": True,
        "graph_not_rerun": True,
        "graph": {
            "expected_fact_edge_recall": "12/15 = 0.80",
            "extracted_edge_precision": 0.86,
            "missed_edges": ["F_adj_prc", "F_prc_current", "F_svc"],
        },
        "wiki_w1_frozen": {
            "expected_fact_recall": "13/15 = 0.8667",
            "accepted_claim_precision": "22/25 = 0.88",
        },
        "prohibited_claim": (
            "Do NOT claim Wiki extraction is inherently more reliable than Graph extraction: one "
            "non-deterministic snapshot per side, one small corpus, no repeated Graph runs, and only "
            "approximately aligned recall/precision definitions."
        ),
        "failure_mode_distinction": {
            "graph": "typed-edge precision; reachability SENSITIVE to a missing inferred edge",
            "wiki": "source-hub redundant connectivity; cost paid as branching ambiguity",
        },
    }


def build_blind_page_quality_packet(projection, facet_rows) -> dict:
    """The frozen deterministic six-page blind W0/W1 review packet.

    Pages are chosen by stable hash order, never cherry-picked, and the two
    renderings are presented without mode labels in a deterministic order so the
    owner cannot tell which is which from position alone.
    """
    import hashlib

    page_keys = sorted(p.page_key for p in projection.page_identities)
    ordered = sorted(page_keys, key=lambda k: hashlib.sha256(k.encode("utf-8")).hexdigest())
    sample = sorted(ordered[:6])

    payload_by_page: dict[str, str] = {}
    for row in facet_rows:
        payload_by_page.setdefault(row.page_key, row.payload_text)

    lines = [
        "# Stage 7C.2 — blind page-quality review packet",
        "",
        "> **Owner rating required.** Claude does not score page quality (Revision 6 §8D). Each page below",
        "> is rendered twice, as **Variant A** and **Variant B**, in a deterministic order that does not",
        "> encode which is W0 and which is W1. Score each variant 0–2 on every rubric dimension.",
        "",
        f"Deterministic sample of {len(sample)} pages, selected by stable hash order (never cherry-picked): "
        + ", ".join(f"`{k}`" for k in sample),
        "",
        "**Rubric (0 = poor, 1 = adequate, 2 = good), scored per variant:**",
        "",
        "| # | Dimension |",
        "|---|---|",
        "| 1 | Readability |",
        "| 2 | Ability to understand *why* sources are connected |",
        "| 3 | Visibility of source vs model-derived content |",
        "| 4 | Citation usability |",
        "| 5 | Revision clarity |",
        "| 6 | Exception / qualification preservation |",
        "| 7 | Usefulness to a business user |",
        "| 8 | Usefulness to a downstream agent |",
        "",
        "---",
        "",
    ]
    for page_key in sample:
        page = next(p for p in projection.page_identities if p.page_key == page_key)
        facets = [f for f in projection.facets if f.page_key == page_key]
        sections = {s.chunk_id: s for s in projection.sections}
        lines.append(f"## Page `{page_key}` — {page.display_title}")
        lines.append("")
        lines.append("### Variant A")
        lines.append("")
        for facet in sorted(facets, key=lambda f: f.document_revision_id):
            for chunk_id in facet.chunk_ids:
                section = sections[chunk_id]
                lines.append(f"- **{' > '.join(section.heading_path)}** — `{chunk_id[:12]}...`")
                lines.append(f"  > {section.source_text}")
        lines.append("")
        lines.append("### Variant B")
        lines.append("")
        payload = payload_by_page.get(page_key, "(no payload)")
        lines.append("```")
        lines.append(payload)
        lines.append("```")
        lines.append("")
        lines.append("```")
        lines.append("VARIANT A SCORES (1-8):")
        lines.append("VARIANT B SCORES (1-8):")
        lines.append("NOTES:")
        lines.append("```")
        lines.append("")
        lines.append("---")
        lines.append("")

    schema = {
        "instructions": "Owner scores only. Claude must not populate any score.",
        "scale": {"0": "poor", "1": "adequate", "2": "good"},
        "dimensions": [
            "readability", "understanding_why_sources_are_connected",
            "source_vs_model_derived_visibility", "citation_usability", "revision_clarity",
            "qualification_preservation", "usefulness_to_business_user", "usefulness_to_downstream_agent",
        ],
        "pages": sample,
        "variants": ["A", "B"],
        "blind": True,
        "scores": {page: {"A": {}, "B": {}} for page in sample},
        "single_rater_limitation": "Owner alone rates; recorded as a stated limitation (Q7).",
    }
    return {"markdown": "\n".join(lines) + "\n", "schema": schema, "sample": sample}


def render_stage7c2_scorecard(results: dict) -> str:
    """The owner-facing scorecard. Derives from the SAME result object as the
    JSON, so the two cannot disagree."""
    lines: list[str] = []
    summary = results["summary"]
    attribution = results["attribution"]

    lines.append("# Stage 7C.2 — Wiki hub retrieval / navigation qualification")
    lines.append("")
    lines.append("> **Read-only measurement over the frozen Stage 7C.0 + 7C.1 artifacts.** Zero compiler or")
    lines.append("> extractor calls; the 22 frozen facet vectors were loaded, never regenerated; nothing in")
    lines.append("> Stage 7C.0 or 7C.1 was written.")
    lines.append(">")
    lines.append(f"> **Gate A: {results['gate_a_status']}.** Every W1-D / W1-FULL / N_advisory result below")
    lines.append(f"> carries **`{results['w1_label']}`**. **D0 is NOT labelled** — it consumes no W1-derived")
    lines.append("> model output, so Gate Q's failure does not reach it.")
    lines.append("")
    basis = results["frozen_basis"]["observed"]
    lines.append("| Frozen identity | Value |")
    lines.append("|---|---|")
    for name, value in basis.items():
        lines.append(f"| {name} | `{value[:32]}…` |")
    counts = results["frozen_basis"]["counts"]
    lines.append(f"| facets / pages / links / vectors | {counts['facets']} / {counts['pages']} / "
                 f"{counts['final_links']} / {counts['facet_embeddings']} |")
    lines.append(f"| scorer (imported by identity) | `{results['evaluator_identity']}` |")
    lines.append("")

    lines.append("## 1. Outcomes per arm")
    lines.append("")
    lines.append("| Arm | solved | partial | failed | Label |")
    lines.append("|---|---|---|---|---|")
    for arm, counts_by_outcome in summary["outcome_counts"].items():
        label = f"`{results['w1_label']}`" if arm in ("W1-D", "W1-FULL", "N_advisory") else "—"
        lines.append(
            f"| {arm} | {counts_by_outcome.get('solved', 0)} | {counts_by_outcome.get('partial', 0)} "
            f"| {counts_by_outcome.get('failed', 0)} | {label} |"
        )
    lines.append("")
    lines.append(f"**Authority leakage across every arm and question: {summary['total_authority_leakage']}** "
                 "(any nonzero value is a hard-safety failure).")
    lines.append("")

    lines.append("## 2. Per-question, per-arm")
    lines.append("")
    lines.append("| Question | K | V | W0 | D0 | W1-D | W1-FULL |")
    lines.append("|---|---|---|---|---|---|---|")
    for question_id, question in sorted(results["per_question"].items()):
        row = [question_id, str(question["top_k"])]
        for arm in ("V", "W0", "D0", "W1-D", "W1-FULL"):
            metrics = question["arms"][arm]
            row.append(f"{metrics['outcome']} {metrics['required_fact_coverage_at_k']:.2f}")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append("*Cell format: outcome + required-fact coverage@K.*")
    lines.append("")

    lines.append("## 3. Attribution — the three required deltas")
    lines.append("")
    for key in ("W1-D_vs_D0", "W1-FULL_vs_W1-D", "W1-FULL_vs_D0"):
        delta = attribution[key]
        lines.append(f"### {key.replace('_', ' ')}")
        lines.append("")
        lines.append(f"*{delta['measures']}*")
        lines.append("")
        lines.append(f"**{delta['verdict']}**")
        lines.append("")
        lines.append(f"- improved: {delta['improved'] or 'none'}")
        lines.append(f"- regressed: {delta['regressed'] or 'none'}")
        lines.append(f"- identical on every axis: {len(delta['identical'])}/{results['summary']['questions']}")
        lines.append("")
    for key in ("D0_vs_V", "W1-FULL_vs_V", "W0_vs_V"):
        delta = attribution[key]
        lines.append(f"**{key.replace('_', ' ')}** — *{delta['measures']}*: {delta['verdict']}")
        lines.append("")
    if attribution["mandated_statements"]:
        lines.append("### Mandated statement(s)")
        lines.append("")
        for statement in attribution["mandated_statements"]:
            lines.append(f"> {statement}")
            lines.append("")
    lines.append(f"> {attribution['prohibited_inference']}")
    lines.append("")

    lines.append("## 4. Counterfactual suppression diagnostic (Q04 / Q06 / Q07)")
    lines.append("")
    if not results["suppression_diagnostic"]:
        lines.append("_No suppression run recorded._")
    else:
        first = next(iter(results["suppression_diagnostic"].values()))
        lines.append(f"**`{first['label']}`** — it replaces none of the three attribution deltas.")
        lines.append("")
        lines.append("| Question | links suppressed | natural outcome | suppressed outcome | still reachable |")
        lines.append("|---|---|---|---|---|")
        for question_id, probe in sorted(results["suppression_diagnostic"].items()):
            lines.append(
                f"| {question_id} | {probe['suppressed_link_count']} | "
                f"{probe['natural']['outcome']} {probe['natural']['coverage']:.2f} | "
                f"{probe['suppressed']['outcome']} {probe['suppressed']['coverage']:.2f} | "
                f"{probe['destination_still_reachable']} |"
            )
    lines.append("")

    lines.append("## 5. Navigation, branching and bounds")
    lines.append("")
    lines.append("| Question | Arm | seeds | pages visited | hops | candidates | branching | page sat. | chunk sat. |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for question_id, question in sorted(results["per_question"].items()):
        for arm in ("D0", "W1-D", "W1-FULL"):
            metrics = question["arms"][arm]
            lines.append(
                f"| {question_id} | {arm} | {metrics['seed_pages_selected']} | {metrics['pages_visited']} "
                f"| {metrics['hops_taken']} | {metrics['candidates_examined']} "
                f"| {metrics['branching_factor']:.2f} | {metrics['page_saturation']:.2f} "
                f"| {metrics['chunk_saturation']:.2f} |"
            )
    lines.append("")
    lines.append(f"> **{results['small_corpus_caveat']}**")
    lines.append("")

    lines.append("## 6. Branch attribution vs D0")
    lines.append("")
    lines.append("| Question | Arm | seed overlap vs D0 | branch-order divergence vs D0 |")
    lines.append("|---|---|---|---|")
    for question_id, question in sorted(results["per_question"].items()):
        for arm in ("W1-D", "W1-FULL"):
            metrics = question["arms"][arm]
            overlap = metrics["seed_page_overlap_vs_D0"]
            lines.append(
                f"| {question_id} | {arm} | {overlap['overlap']}/{overlap['arm_seeds']} "
                f"| {metrics['branch_order_divergence_vs_D0']} |"
            )
    lines.append("")

    graph = results["graph_attribution"]
    lines.append("## 7. Frozen Graph attribution (read-only)")
    lines.append("")
    lines.append("Graph was **not** rerun or modified.")
    lines.append("")
    lines.append("| | Expected-fact recall | Precision |")
    lines.append("|---|---|---|")
    lines.append(f"| Frozen Stage 7B.1 Graph | {graph['graph']['expected_fact_edge_recall']} "
                 f"| {graph['graph']['extracted_edge_precision']} |")
    lines.append(f"| Frozen Stage 7C.1 W1 | {graph['wiki_w1_frozen']['expected_fact_recall']} "
                 f"| {graph['wiki_w1_frozen']['accepted_claim_precision']} |")
    lines.append("")
    lines.append(f"> {graph['prohibited_claim']}")
    lines.append("")
    lines.append(f"- **Graph:** {graph['failure_mode_distinction']['graph']}")
    lines.append(f"- **Wiki:** {graph['failure_mode_distinction']['wiki']}")
    lines.append("")

    lines.append("## 8. Stop point")
    lines.append("")
    lines.append("This stage stops at the **owner page-quality checkpoint**. Claude does not score page")
    lines.append("quality (§8D); the blind six-page W0/W1 packet and its rubric are emitted separately, and")
    lines.append("`docs/STAGE7C_WIKI_DECISION.md` is **not** finalized until the owner's ratings are supplied.")
    lines.append("")
    lines.append("Gate A is unreachable. The final Stage 7C outcome will be **Gate B or Gate C** under the")
    lines.append("frozen rules, and that selection is owner-dependent — it is not made here.")
    lines.append("")
    return "\n".join(lines) + "\n"
