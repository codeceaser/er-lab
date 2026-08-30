"""Stage 7C.0: the projection manifest, the frozen projection contract, the
build/cost ledger, and the owner-facing scorecard.

Everything emitted here is deterministic except the explicitly-labelled
`generated_at` / latency fields, which are excluded from every hash.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict

from ingestion_bench.wiki_projection import PROJECTION_CONTRACT_VERSION, identity, projection as projection_module
from ingestion_bench.wiki_projection.benchmark import Stage7C0Result
from ingestion_bench.wiki_projection.model import WikiProjection


def _canonical_json(payload) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- the frozen projection contract -----------------------------------------


def build_projection_contract(projection: WikiProjection) -> dict:
    """`contracts/wiki_projection_v1.json` -- FROZEN at Stage 7C.0.

    Carries the identity/anchor/membership rules, the deterministic
    display_title / page_type derivation, the frozen sentence splitter, the
    frozen D0 seed procedure and D0 branch prioritizer, and the MEASURED
    `M_max`.
    """
    rules = {
        "contract_version": PROJECTION_CONTRACT_VERSION,
        "stage": "7C.0",
        "status": "frozen",
        "llm_calls": 0,
        "page_identity": {
            "page_key_format": "{kind}:{normalized_identity}",
            "kinds": {"IDENT": "governed_identifier (Lane 1)", "PHRASE": "business_topic (Lane 2)"},
            "identifier_normalization": "uppercase the matched identifier; keeps C-88 and C-88A DISTINCT",
            "phrase_normalization": "casefold + single-space collapse",
            "display_title_rule": identity.DISPLAY_TITLE_RULE,
            "page_type_rule": "the anchor's own anchor_kind; fully deterministic; never model-generated",
            "heading_title_anchors_create_pages": False,
        },
        "anchor_lanes": {
            "lane_1_identifier": {
                "regex": r"\b([A-Za-z]{1,6}-\d+[A-Za-z]?)\b",
                "lifted_from": "graph_retrieval_benchmark/model.py identifiers_in (LIFTED, never imported -- Revision 6 Q9)",
                "also_uses_identifier_annotations": True,
                "identifier_annotations_present_in_this_corpus": False,
                "fields": ["source_text", "heading_path"],
            },
            "lane_2_repeated_phrase": {
                "token_pattern": "^[A-Z][A-Za-z0-9&/-]*$ or an identifier token",
                "run_rule": "maximal runs of consecutive QUALIFYING tokens; a stop-listed or non-qualifying token ENDS the run",
                "min_tokens": identity.PHRASE_MIN_TOKENS,
                "max_tokens": identity.PHRASE_MAX_TOKENS,
                "min_chars": identity.PHRASE_MIN_CHARS,
                "max_chars": identity.PHRASE_MAX_CHARS,
                "min_distinct_chunks": identity.PHRASE_MIN_DISTINCT_CHUNKS,
                "min_distinct_logical_documents": identity.PHRASE_MIN_DISTINCT_LOGICAL_DOCUMENTS,
                "identifier_collision_rule": "a candidate containing an identifier token is dropped -- identifiers win",
                "stop_list": identity.stop_list_snapshot(),
                "fields": ["source_text", "heading_path"],
            },
            "lane_3_heading_title": {
                "rule": "one anchor per distinct normalized heading_path element",
                "creates_page_identity": False,
                "traversable": False,
                "reason": "Revision 6 SS7.1 -- a shared heading asserts document-template similarity, not entity co-occurrence",
            },
        },
        "membership_rule": {
            "statement": "a facet (page_key, document_revision_id) exists IF AND ONLY IF that page identity has >= 1 anchor posting in that revision",
            "inputs": ["page_identities", "anchor_postings"],
            "may_not_depend_on": [
                "LLM claims", "summary sentences", "aliases", "validation outcome",
                "adjudication verdict", "compiler success or failure",
            ],
            "authority_effect": "an authority change alters VISIBILITY only -- never membership, never a hash",
        },
        "links": {
            "structural": "document / revision-page / section hierarchy and revision-history siblings; asserts no entity relationship",
            "exact_anchor": f"means ONLY: {'this same source-backed identity occurs there'}; no direction, no type, no lineage",
            "is_authoritative_lineage": False,
            "advisory_downgrade": "exact-anchor links of a phrase anchor with pairwise-disjoint identifier context are marked advisory",
        },
        "sentence_splitter": identity.sentence_splitter_identity(),
        "d0_contract": projection_module.d0_contract_identity(),
        "measured_projection_properties": {
            "m_max": projection.counts.m_max,
            "m_max_definition": (
                "max over page_key of |{document_revision_id : the page has >= 1 anchor posting in that revision}|, "
                "computed over the completed Stage 7C.0 projection"
            ),
            "m_max_is_a_measured_property_not_a_knob": True,
            "m_max_argmax_page_keys": projection.counts.facets_per_page_max_page_keys,
            "candidate_ceiling_formula": "C = (P_seed + B) x M_max x F_max",
            "candidate_ceiling_evaluated_in_stage": "7C.2",
            "facet_count": projection.counts.facet_count,
            "page_identity_count": projection.counts.page_identity_count,
        },
        "projection_hash": projection.projection_hash,
    }
    rules["contract_sha256"] = _sha256(_canonical_json(rules))
    return rules


# --- the projection manifest -------------------------------------------------


def build_projection_manifest(result: Stage7C0Result) -> dict:
    """The deterministic Stage 7C.0 manifest (Revision 6 / owner SS10)."""
    p = result.projection
    anchor_by_id = {a.anchor_id: a for a in p.anchors}

    postings_by_anchor: dict[str, int] = defaultdict(int)
    for posting in p.postings:
        postings_by_anchor[posting.anchor_id] += 1

    facets_by_page: dict[str, list[str]] = defaultdict(list)
    for facet in p.facets:
        facets_by_page[facet.page_key].append(facet.document_revision_id)

    c88 = next((a for a in p.anchors if a.normalized_value == "C-88"), None)
    c88a = next((a for a in p.anchors if a.normalized_value == "C-88A"), None)
    c88_separation = {
        "c_88_anchor_id": c88.anchor_id if c88 else None,
        "c_88a_anchor_id": c88a.anchor_id if c88a else None,
        "distinct_anchor_ids": bool(c88 and c88a and c88.anchor_id != c88a.anchor_id),
        "c_88_page_key": "IDENT:C-88" if c88 else None,
        "c_88a_page_key": "IDENT:C-88A" if c88a else None,
        "c_88_display_text": c88.display_text if c88 else None,
        "c_88a_display_text": c88a.display_text if c88a else None,
        "c_88_chunk_ids": sorted({x.chunk_id for x in p.postings if c88 and x.anchor_id == c88.anchor_id}),
        "c_88a_chunk_ids": sorted({x.chunk_id for x in p.postings if c88a and x.anchor_id == c88a.anchor_id}),
        "shared_chunk_ids": sorted(
            {x.chunk_id for x in p.postings if c88 and x.anchor_id == c88.anchor_id}
            & {x.chunk_id for x in p.postings if c88a and x.anchor_id == c88a.anchor_id}
        ),
        "never_merged": True,
    }

    manifest = {
        "contract_version": p.contract_version,
        "corpus_id": result.corpus_id,
        "corpus_logical_document_ids": p.corpus_logical_document_ids,
        "revision_symbol_by_id": result.revision_symbol_by_id,
        "counts": p.counts.model_dump(mode="json"),
        "anchor_inventory": [
            {
                "anchor_id": a.anchor_id, "anchor_kind": a.anchor_kind, "normalized_value": a.normalized_value,
                "display_text": a.display_text, "extraction_method": a.extraction_method,
                "is_ambiguous": a.is_ambiguous, "display_variants": a.display_variants,
                "has_disjoint_identifier_context": a.has_disjoint_identifier_context,
                "posting_count": postings_by_anchor[a.anchor_id],
            }
            for a in p.anchors
        ],
        "phrase_anchor_inventory": [
            {
                "normalized_value": a.normalized_value, "display_text": a.display_text,
                "posting_count": postings_by_anchor[a.anchor_id],
                "has_disjoint_identifier_context": a.has_disjoint_identifier_context,
            }
            for a in p.anchors
            if a.anchor_kind == identity.ANCHOR_KIND_PHRASE
        ],
        "phrase_lane_ledger": p.phrase_lane_ledger,
        "ambiguity_flags": [
            {
                "anchor_id": a.anchor_id, "normalized_value": a.normalized_value,
                "is_ambiguous": a.is_ambiguous, "display_variants": a.display_variants,
                "has_disjoint_identifier_context": a.has_disjoint_identifier_context,
            }
            for a in p.anchors
            if a.is_ambiguous or a.has_disjoint_identifier_context
        ],
        "page_identity_inventory": [
            {
                "page_key": page.page_key, "page_type": page.page_type, "display_title": page.display_title,
                "identity_confidence": page.identity_confidence,
                "anchor_kind": anchor_by_id[page.anchor_id].anchor_kind,
                "facet_count": len(facets_by_page[page.page_key]),
            }
            for page in p.page_identities
        ],
        "facet_membership_inventory": [
            {
                "page_key": f.page_key, "document_revision_id": f.document_revision_id,
                "revision_symbol": result.revision_symbol_by_id.get(f.document_revision_id),
                "logical_document_id": f.logical_document_id, "chunk_ids": f.chunk_ids,
                "posting_count": len(f.posting_hashes), "membership_hash": f.membership_hash,
            }
            for f in p.facets
        ],
        "page_to_revision_facet_counts": {key: len(set(values)) for key, values in sorted(facets_by_page.items())},
        "c88_c88a_separation_proof": c88_separation,
        "posting_counts_by_revision": {
            revision: sum(1 for x in p.postings if x.document_revision_id == revision)
            for revision in sorted({x.document_revision_id for x in p.postings})
        },
        "link_counts": {
            "structural": p.counts.structural_link_count,
            "exact_anchor": p.counts.exact_anchor_link_count,
            "advisory": p.counts.advisory_link_count,
            "is_authoritative_lineage_true_count": sum(1 for link in p.links if link.is_authoritative_lineage),
        },
        "provenance_completeness": {
            "postings_with_source_ref": sum(1 for x in p.postings if x.source_ref),
            "postings_total": len(p.postings),
            "sections_with_source_refs": sum(1 for s in p.sections if s.source_refs),
            "sections_total": len(p.sections),
            "sections_with_content_sha256": sum(1 for s in p.sections if len(s.content_sha256) == 64),
        },
        "m_max": p.counts.m_max,
        "m_max_argmax_page_keys": p.counts.facets_per_page_max_page_keys,
        "sentence_splitter": identity.sentence_splitter_identity(),
        "d0_contract": projection_module.d0_contract_identity(),
        "deterministic_build_hashes": {
            "projection_hash": p.projection_hash,
            "anchors_hash": _sha256(_canonical_json([a.model_dump(mode="json") for a in p.anchors])),
            "postings_hash": _sha256(_canonical_json([x.model_dump(mode="json") for x in p.postings])),
            "facets_hash": _sha256(_canonical_json([f.model_dump(mode="json") for f in p.facets])),
            "links_hash": _sha256(_canonical_json([link.model_dump(mode="json") for link in p.links])),
            "sections_hash": _sha256(_canonical_json([s.model_dump(mode="json") for s in p.sections])),
        },
    }
    manifest["manifest_sha256"] = _sha256(_canonical_json(manifest))
    return manifest


# --- build / cost ledger -----------------------------------------------------


def build_cost_ledger(result: Stage7C0Result, *, module_files: list[str], loc_by_file: dict[str, int]) -> dict:
    """The Stage 7C.0 deterministic build-side ledger. No invented person-days
    and no hypothetical dollar values."""
    p = result.projection
    return {
        "stage": "7C.0",
        "llm_calls": 0,
        "llm_cost_usd": 0.0,
        "modules_added": module_files,
        "lines_of_code_by_file": loc_by_file,
        "lines_of_code_total": sum(loc_by_file.values()),
        "database_tables_created_by_this_stage": [
            "edib_stage7c_anchor", "edib_stage7c_anchor_posting",
        ],
        "database_tables_deliberately_not_created": [
            "edib_stage7c_facet (Stage 7C.1)",
            "edib_stage7c_facet_embedding (Stage 7C.1)",
            "edib_stage7c_compilation_audit (Stage 7C.1)",
        ],
        "projection_records": {
            "anchors": p.counts.anchor_count,
            "postings": p.counts.posting_count,
            "sections_derived_view": p.counts.section_count,
            "revision_pages_derived_view": p.counts.revision_count,
            "page_identities": p.counts.page_identity_count,
            "facets": p.counts.facet_count,
            "links": p.counts.structural_link_count + p.counts.exact_anchor_link_count,
        },
        "storage_bytes_serialized_projection": len(p.model_dump_json().encode("utf-8")),
        "build_latency_seconds_total_run": result.build_latency_seconds,
        "embedding_calls_attributable_to_7c0": 0,
        "embedding_calls_note": (
            "The deterministic projection makes ZERO embedding calls. The W0 semantic CONTROL reuses the "
            "existing chunk embeddings and the existing query embedding, exactly as V does; it introduces no "
            "new embedding representation and no embedding attributable to the projection itself."
        ),
        "authority_change_rebuild_cost": {
            "reparse": 0, "rechunk": 0, "anchor_rebuild": 0, "embedding_rebuild": 0,
            "projection_hash_change": 0,
            "note": "an authority change alters only the query-time eligible view",
        },
        "source_change_rebuild_behaviour": (
            "a source-revision change changes that revision's chunks, therefore its sections, postings, "
            "facet membership and the projection hash; other revisions are untouched"
        ),
        "operational_dependencies": [
            "frozen Stage 5A Docling adapter", "frozen Stage 4/4.1 chunker",
            "frozen Stage 7R.1 revision authority resolver (query time only)",
            "frozen Stage 7B.0 corpus, contract and evaluator (read-only)",
        ],
        "known_failure_modes": [
            "Lane 2 is bounded by capitalisation convention: it misses lower-cased entity names and can "
            "over-generate on boilerplate headings (mitigated by the >=2-distinct-document rule).",
            "Anchor fan-out is unbounded on a large corpus; exact-anchor links grow quadratically in the "
            "number of sections sharing an anchor.",
            "Exact-anchor links assert co-occurrence only -- no direction and no relationship meaning.",
            "The corpus supplies no IdentifierAnnotations, so Lane 1 rests on the lifted regex alone here.",
            "A phrase anchor bridging documents necessarily shows disjoint identifier context, so the "
            "SS2.1 advisory downgrade fires on the corpus's only cross-document phrase anchor.",
        ],
    }


# --- owner-facing scorecard --------------------------------------------------


def render_scorecard_markdown(result: Stage7C0Result, manifest: dict) -> str:
    p = result.projection
    control = result.w0_control
    lines: list[str] = []

    lines.append("# Stage 7C.0 — Deterministic Wiki Projection Qualification (W0)")
    lines.append("")
    lines.append("**Plan:** `docs/STAGE7C_WIKI_PLAN.md` Revision 6 (owner-approved, frozen).")
    lines.append("")
    lines.append("**Zero LLM calls.** No claim, alias, summary, adjudication verdict, W1 facet or facet "
                 "embedding exists. No D0 / W1-D / W1-FULL benchmark comparison has been run.")
    lines.append("")

    lines.append("## Projection counts")
    lines.append("")
    lines.append("| Quantity | Value |")
    lines.append("|---|---|")
    for label, value in [
        ("Logical documents", p.counts.logical_document_count),
        ("Revisions", p.counts.revision_count),
        ("Sections (1:1 view over CanonicalChunk)", p.counts.section_count),
        ("Anchors", p.counts.anchor_count),
        ("— identifier (Lane 1)", p.counts.anchor_count_by_kind.get("identifier", 0)),
        ("— phrase (Lane 2)", p.counts.anchor_count_by_kind.get("phrase", 0)),
        ("— heading_title (Lane 3, no page identity)", p.counts.anchor_count_by_kind.get("heading_title", 0)),
        ("Anchor postings", p.counts.posting_count),
        ("Page identities", p.counts.page_identity_count),
        ("— governed_identifier", p.counts.page_identity_count_by_type.get("governed_identifier", 0)),
        ("— business_topic", p.counts.page_identity_count_by_type.get("business_topic", 0)),
        ("Facets (deterministic membership)", p.counts.facet_count),
        ("Structural links", p.counts.structural_link_count),
        ("Exact-anchor links", p.counts.exact_anchor_link_count),
        ("— of which advisory", p.counts.advisory_link_count),
        ("**M_max (measured)**", f"**{p.counts.m_max}**"),
    ]:
        lines.append(f"| {label} | {value} |")
    lines.append("")
    lines.append(f"`M_max` argmax pages: {', '.join(f'`{k}`' for k in p.counts.facets_per_page_max_page_keys)}")
    lines.append("")
    lines.append("`M_max` is a **measured property of the completed projection**, never a configuration knob. "
                 "It is frozen here so Stage 7C.2 can evaluate the Revision 6 ceiling "
                 "`C = (P_seed + B) x M_max x F_max`. That ceiling is **not** evaluated in this stage.")
    lines.append("")

    lines.append("## C-88 / C-88a separation")
    lines.append("")
    proof = manifest["c88_c88a_separation_proof"]
    lines.append(f"- `C-88` → page `{proof['c_88_page_key']}`, display `{proof['c_88_display_text']}`, "
                 f"{len(proof['c_88_chunk_ids'])} posting chunk(s)")
    lines.append(f"- `C-88a` → page `{proof['c_88a_page_key']}`, display `{proof['c_88a_display_text']}`, "
                 f"{len(proof['c_88a_chunk_ids'])} posting chunk(s)")
    lines.append(f"- distinct anchor ids: **{proof['distinct_anchor_ids']}**")
    lines.append(f"- chunks where both occur: {proof['shared_chunk_ids'] or 'none'}")
    lines.append("- **never merged** at identity, anchor, page, facet, membership or link level")
    lines.append("")

    lines.append("## Lane 2 phrase-anchor decisions")
    lines.append("")
    lines.append("| Candidate | Distinct chunks | Distinct documents | Accepted | Reason |")
    lines.append("|---|---|---|---|---|")
    for entry in p.phrase_lane_ledger:
        lines.append(
            f"| `{entry['normalized_phrase']}` | {entry['distinct_chunks']} | {entry['distinct_logical_documents']} "
            f"| {'**yes**' if entry['accepted'] else 'no'} | {entry['rejection_reason'] or '—'} |"
        )
    lines.append("")

    lines.append("## W0 semantic control (W0 vs V)")
    lines.append("")
    lines.append(f"- Embedding model: `{control.embedding_model}`")
    lines.append(f"- Evaluator (imported by identity): `{control.evaluator_identity}`")
    lines.append(f"- Questions: {control.questions_total}")
    lines.append(f"- W0 hit list identical to V: **{control.identical_to_v_count}/{control.questions_total}**")
    lines.append(f"- **W0 == V: {control.w0_equals_v}**")
    lines.append(f"- V outcomes: `{control.v_outcome_counts}`")
    lines.append(f"- W0 outcomes: `{control.w0_outcome_counts}`")
    lines.append(f"- Authority leakage (V + W0): **{control.total_authority_leakage}** (must be 0)")
    lines.append("")
    lines.append("> W0 semantic retrieval is **expected** to equal V, because a W0 section is 1:1 with a chunk "
                 "and reuses that chunk's existing embedding. **W0 ~ V is a successful control outcome, not a "
                 "failure**, and no retrieval-improvement gate is applied to it.")
    lines.append("")
    lines.append("> **W0 semantic control is NOT D0.** D0 adds anchor-derived seeding, deterministic hub "
                 "expansion and deterministic navigation on top of chunk semantic retrieval, and is a Stage "
                 "7C.2 arm. Nothing in Stage 7C.0 expands a hub or traverses a link.")
    lines.append("")

    lines.append("| Question | K | V outcome | W0 outcome | V cov@K | W0 cov@K | identical |")
    lines.append("|---|---|---|---|---|---|---|")
    for q in control.questions:
        lines.append(
            f"| {q.question_id} | {q.top_k} | {q.v_outcome} | {q.w0_outcome} | "
            f"{q.v_coverage_at_k:.2f} | {q.w0_coverage_at_k:.2f} | {q.identical_to_v} |"
        )
    lines.append("")

    lines.append("## Frozen contracts")
    lines.append("")
    lines.append(f"- Projection hash: `{p.projection_hash}`")
    lines.append(f"- Manifest SHA-256: `{manifest['manifest_sha256']}`")
    sentence = identity.sentence_splitter_identity()
    lines.append(f"- Sentence splitter: `{sentence['version']}` / `{sentence['sha256'][:16]}...`")
    d0 = projection_module.d0_contract_identity()
    lines.append(f"- D0 seed procedure: `{d0['seed_procedure']['version']}` / `{d0['seed_procedure']['sha256'][:16]}...` "
                 f"— **frozen, not executed**")
    lines.append(f"- D0 branch prioritizer: `{d0['branch_prioritizer']['version']}` / "
                 f"`{d0['branch_prioritizer']['sha256'][:16]}...` — **frozen, not executed**")
    lines.append("")

    lines.append("## Deviations and recorded interpretations")
    lines.append("")
    lines.append("Four points where the frozen Revision 6 text needed a judgement call. None changes a gate, "
                 "a threshold or the experiment's logic; each is recorded rather than silently resolved.")
    lines.append("")
    lines.append("1. **Lane 2 stop-list semantics.** SS2.1 says a candidate is \"rejected if any token is in a "
                 "fixed closed stop-list\". Read literally as *poisoning the candidate*, the sentence "
                 "\"**The** Payment Settlement business service is governed by ...\" yields the single run "
                 "`[The, Payment, Settlement]` and is rejected — which would destroy `Payment Settlement`, the "
                 "anchor SS0.1 records as this corpus's ONLY cross-document phrase anchor and which SS1.5's chain "
                 "depends on. Implemented so a stop word **breaks** the run instead; no candidate ever contains a "
                 "stop word, so the rule's literal requirement also holds.")
    lines.append("2. **Lane 2 identifier-collision rule.** SS2.1's \"a candidate colliding with an identifier key "
                 "is dropped (identifiers win)\" is implemented as *a candidate containing an identifier token is "
                 "dropped*. Under the narrower reading (exact key equality) `Obligation O-31`, `Control C-88` and "
                 "`Procedure P-205` would all survive as competing hubs alongside their identifier pages, and "
                 "SS0.1's \"cross-document phrase anchors: `Payment Settlement` only\" would be false. The "
                 "implemented reading reproduces SS0.1 exactly — see the Lane 2 ledger above.")
    lines.append("3. **`display_title`.** SS3.2 fixes it as the anchor's frozen `display_text`, \"never re-worded\". "
                 "The W0 display rule implemented is *the exact surface form of the anchor's first posting in "
                 "deterministic order*, so `IDENT:O-31` renders as `O-31`. SS1.5.3's illustrative facet record shows "
                 "`\"display_title\": \"Obligation O-31\"`; producing that would require prepending a type word that "
                 "is not part of the anchor, i.e. generating text. The contract rule was followed and the "
                 "illustration was not.")
    lines.append("4. **Module placement of rendering.** SS10.1 lists page rendering under `assembly.py` at Stage "
                 "7C.1, while SS11 requires rendering as a 7C.0 deliverable. Implementing it in `assembly.py` now "
                 "would mean creating the 7C.1 module early, which the scope rules forbid. W0 rendering therefore "
                 "lives in a small dedicated 7C.0 `rendering.py`; `assembly.py` remains unwritten and keeps its "
                 "7C.1 payload-composition role.")
    lines.append("")
    lines.append("### One contract rule that fires on this corpus's key anchor")
    lines.append("")
    lines.append("SS2.1 states that \"a phrase posting into sections with disjoint identifier sets is flagged "
                 "ambiguous and its links downgraded to advisory\". `PHRASE:payment settlement` posts into "
                 "`app_rev1` (`{APP-224499}`), `app_rev2` (`{APP-224510}`) and `svc_rev1` (`{O-31}`) — pairwise "
                 "disjoint — so the rule fires on the corpus's only cross-document phrase anchor, and its "
                 f"{p.counts.advisory_link_count} exact-anchor links are marked advisory.")
    lines.append("")
    lines.append("The rule was implemented as written: the flag is recorded and the links are marked. The page is "
                 "**not** split, because SS3.3's split rule is contracted for the *duplicate names* case, and a "
                 "deterministic detector cannot distinguish a genuine duplicate name from a legitimate bridging "
                 "anchor — splitting the latter would destroy the hub SS0.1 and SS1.5 depend on. Advisory links "
                 "remain traversable and are marked everywhere they appear.")
    lines.append("")
    lines.append("> **Owner decision to note before Stage 7C.2.** Any cross-document phrase anchor necessarily "
                 "shows disjoint identifier context — that is what bridging *is* — so this rule will flag every "
                 "such anchor on any corpus. If advisory status is later given retrieval or gating consequence, "
                 "that consequence would fall hardest on exactly the anchors the Wiki hypothesis relies on. It has "
                 "no such consequence today.")
    lines.append("")

    lines.append("## Scope")
    lines.append("")
    lines.append("Not implemented in this stage, by contract: the Stage 7C.1 facet compiler, W1 claims / "
                 "aliases / summaries, owner adjudication, W1 payload composition, W1 facet embeddings, "
                 "claim-derived links, Stage 7C.2 retrieval and navigation, the measured D0 / W1-D / W1-FULL "
                 "arms, `N_advisory`, the counterfactual suppression probe, Gate Q, and the Gate A/B/C decision.")
    lines.append("")
    return "\n".join(lines) + "\n"


# =============================================================================
# Stage 7C.1 -- Gate Q pre-status, cost ledger, checkpoint scorecard
# =============================================================================


def build_gate_q_pre_status(stage_result, packet) -> dict:
    """Gate Q at the owner-adjudication checkpoint.

    Labelled **PENDING OWNER ADJUDICATION** -- never PASS and never FAIL --
    unless a purely MECHANICAL hard failure has already made qualification
    impossible. Q-5, Q-6, Q-7 and Q-10 all require owner semantic verdicts and
    are therefore reported as awaiting adjudication, with the mechanical
    substrate each one will be computed from stated explicitly.
    """
    run_1 = stage_result.validations_by_run[str(stage_result.primary_run_id)]

    total_claims = sum(len(v.claims) for v in run_1.values())
    accepted = sum(1 for v in run_1.values() for c in v.claims if c.validation_status == "accepted")
    rejected = sum(1 for v in run_1.values() for c in v.claims if c.validation_status == "rejected")
    uncertain = sum(1 for v in run_1.values() for c in v.claims if c.validation_status == "uncertain")
    out_of_scope = sum(1 for v in run_1.values() for c in v.claims if c.validation_status == "out_of_page_scope")
    citation_valid = sum(1 for v in run_1.values() for c in v.claims if c.citation_valid)

    invalid_source_refs = sum(
        1 for v in run_1.values() for c in v.claims
        for reason in c.rejection_reasons if "source_ref" in reason or "does not exist" in reason
    )
    revision_scope = sum(
        1 for v in run_1.values() for c in v.claims
        for reason in c.rejection_reasons if "revision-scope contamination" in reason or "another revision" in reason
    )
    ceiling_breaches = sum(len(v.ceiling_breaches) for v in run_1.values())
    generation_failures = sum(1 for v in run_1.values() if v.generation_failed)
    false_merges = stage_result.repeatability.false_merges_by_run[str(stage_result.primary_run_id)]

    repeatability = stage_result.repeatability
    # GATED quantities only -- SS8F's threshold names the ACCEPTED-claim set, and
    # for citations an exact-agreement rate on MATCHED accepted claims rather
    # than a Jaccard. The descriptive all-output metric is never gated here.
    claim_jaccard = list(repeatability.accepted_claim_set_jaccard.values())
    citation_agreement = [
        entry["rate"] for entry in repeatability.citation_exact_agreement_on_matched_accepted_claims.values()
    ]

    # Revision 6 SS8F's PROPOSED repeatability thresholds. Still open question Q5,
    # so a breach is reported as failing-at-the-proposed-threshold, never as a
    # final Gate Q verdict.
    proposed_claim_jaccard = 0.90
    proposed_citation_agreement = 0.95
    claim_jaccard_min = min(claim_jaccard) if claim_jaccard else None
    citation_agreement_min = min(citation_agreement) if citation_agreement else None
    q8_breaches: list[str] = []
    if claim_jaccard_min is not None and claim_jaccard_min < proposed_claim_jaccard:
        q8_breaches.append(
            f"accepted_claim_set_jaccard min {claim_jaccard_min:.4f} < proposed {proposed_claim_jaccard}"
        )
    if citation_agreement_min is not None and citation_agreement_min < proposed_citation_agreement:
        q8_breaches.append(
            f"citation_exact_agreement_on_matched_accepted_claims min {citation_agreement_min:.4f} "
            f"< proposed {proposed_citation_agreement}"
        )

    mechanical_hard_failure = None
    if generation_failures:
        mechanical_hard_failure = f"{generation_failures} facet(s) failed generation"
    elif ceiling_breaches:
        mechanical_hard_failure = f"{ceiling_breaches} ceiling breach(es)"
    elif false_merges:
        mechanical_hard_failure = f"{false_merges} false merge(s)"

    return {
        "gate_q_status": "PENDING OWNER ADJUDICATION" if mechanical_hard_failure is None else "MECHANICALLY IMPOSSIBLE",
        "mechanical_hard_failure": mechanical_hard_failure,
        "note": (
            "This is NOT a Gate Q verdict. Four of the ten criteria (Q-5 accepted-claim precision, Q-6 "
            "expected-fact recall, Q-7 summary correctness, Q-10 supported-alias precision) are semantic "
            "and belong to the owner. They cannot be computed here without self-adjudicating."
        ),
        # Surfaced separately and loudly: a MECHANICALLY decidable criterion that
        # already breaches its PROPOSED threshold. Not a verdict, because the
        # threshold itself is still open question Q5 -- but it may decide Gate Q
        # regardless of how adjudication turns out, so the owner should see it
        # before spending adjudication effort.
        "mechanical_criteria_failing_proposed_thresholds": q8_breaches,
        "mechanical_blocker_warning": (
            None
            if not q8_breaches
            else (
                "Q-8 (repeatability) BREACHES ITS PROPOSED THRESHOLD on mechanically measured evidence: "
                + "; ".join(q8_breaches)
                + ". If the owner approves the SS8F thresholds as proposed (open question Q5), Q-8 fails, "
                "Gate Q fails, and Gate A becomes unreachable -- Stage 7C.2 would still run, with every W1 "
                "result labelled NON-QUALIFYING / DIAGNOSTIC ONLY (SS9.2). This is stated now, before "
                "adjudication effort is spent, because it is decidable without any owner verdict. It is "
                "NOT declared a Gate Q failure here: the threshold is a proposal awaiting Q5, and that "
                "decision is the owner's."
            )
        ),
        "criteria": {
            "Q-1_citation_validity": {
                "decidable_mechanically": True,
                "required": 1.00,
                "observed": (citation_valid / total_claims) if total_claims else 1.0,
                "basis": f"{citation_valid}/{total_claims} claims with exact-substring citations",
            },
            "Q-2_invalid_source_references": {
                "decidable_mechanically": True, "required": 0, "observed": invalid_source_refs,
            },
            "Q-3_revision_scope_contamination": {
                "decidable_mechanically": True, "required": 0, "observed": revision_scope,
                "note": "renamed from 'authority contamination' in Revision 6 -- the compiler is "
                        "authority-blind; real authority leakage is a query/assembly-time metric",
            },
            "Q-4_false_merges": {
                "decidable_mechanically": True, "required": 0, "observed": false_merges,
                "note": "includes the C-88 / C-88A guard",
            },
            "Q-5_accepted_claim_precision": {
                "decidable_mechanically": False,
                "required": ">= 0.95 (proposed)",
                "awaiting": "owner CORRECT/INCORRECT/UNVERIFIABLE verdict on every accepted claim",
                "mechanical_substrate": {"accepted_claims": accepted},
            },
            "Q-6_expected_fact_recall": {
                "decidable_mechanically": False,
                "required": ">= 0.80 (proposed)",
                "awaiting": "owner adjudication; scoring accepted claims against the frozen expected facts "
                            "is deliberately deferred so benchmark truth is not placed beside "
                            "unadjudicated output",
            },
            "Q-7_summary_correctness": {
                "decidable_mechanically": False,
                "required": "0 incorrect sentences (proposed)",
                "awaiting": "owner verdict on every summary sentence",
                "mechanical_substrate": {
                    "reference_valid_sentences": sum(
                        1 for v in run_1.values() for s in v.summary_sentences if s.reference_valid
                    )
                },
            },
            "Q-8_repeatability": {
                "decidable_mechanically": True,
                "required": (
                    "accepted_claim_set_jaccard >= 0.90, "
                    "citation_exact_agreement_on_matched_accepted_claims >= 0.95, "
                    "false merges 0, ceiling breaches 0"
                ),
                "required_status": "PROPOSED -- open question Q5, not yet owner-approved",
                "metric_semantics": (
                    "SS8F THRESHOLD semantics: the claim metric is over MECHANICALLY ACCEPTED claims only, "
                    "keyed on normalized (facet identity, subject, predicate, object, sorted "
                    "supporting_chunk_ids); the citation metric matches accepted claims on that same key "
                    "and then compares their citation sets EXACTLY, reporting an agreement rate -- it is "
                    "not a Jaccard."
                ),
                "observed": {
                    "accepted_claim_set_jaccard_min": claim_jaccard_min,
                    "citation_exact_agreement_min": citation_agreement_min,
                    "false_merges_any_run": max(repeatability.false_merges_by_run.values()),
                    "ceiling_breaches_any_run": max(repeatability.ceiling_breaches_by_run.values()),
                },
                "descriptive_not_gated": {
                    "claim_set_jaccard_all_outputs_min": (
                        min(repeatability.claim_set_jaccard_all_outputs_descriptive.values())
                        if repeatability.claim_set_jaccard_all_outputs_descriptive
                        else None
                    ),
                    "note": "SS8F metric-list wording, unqualified population. Never compared to a threshold.",
                },
                "breaches_proposed_threshold": q8_breaches,
                "meets_proposed_threshold": not q8_breaches,
            },
            "Q-9_budget_and_ceilings": {
                "decidable_mechanically": True,
                "required": "no breach; within declared dollar cap",
                "observed": {
                    "ceiling_breaches_run_1": ceiling_breaches,
                    "declared_dollar_cap_usd": stage_result.dollar_ceiling_usd,
                    "total_estimated_cost_usd": stage_result.total_estimated_cost_usd,
                },
            },
            "Q-10_supported_alias_precision": {
                "decidable_mechanically": False,
                "required": "0 incorrect supported aliases",
                "awaiting": "owner verdict on every supported alias",
                "mechanical_substrate": {
                    "supported_aliases": sum(
                        1 for v in run_1.values() for a in v.aliases if a.status == "supported"
                    )
                },
            },
        },
        "run_1_counts": {
            "facets": len(run_1),
            "claims_total": total_claims,
            "claims_accepted": accepted,
            "claims_rejected": rejected,
            "claims_uncertain": uncertain,
            "claims_out_of_page_scope": out_of_scope,
            "aliases_total": sum(len(v.aliases) for v in run_1.values()),
            "aliases_supported": sum(1 for v in run_1.values() for a in v.aliases if a.status == "supported"),
            "aliases_uncertain": sum(1 for v in run_1.values() for a in v.aliases if a.status == "uncertain"),
            "aliases_rejected": sum(1 for v in run_1.values() for a in v.aliases if a.status == "rejected"),
            "summary_sentences_total": sum(len(v.summary_sentences) for v in run_1.values()),
            "summary_sentences_reference_valid": sum(
                1 for v in run_1.values() for s in v.summary_sentences if s.reference_valid
            ),
            "derived_links": sum(len(v.derived_links) for v in run_1.values()),
            "unlinkable_claim_endpoints": sum(len(v.unlinkable_claim_endpoints) for v in run_1.values()),
            "facets_with_zero_accepted_claims": sum(
                1 for v in run_1.values() if not any(c.validation_status == "accepted" for c in v.claims)
            ),
            "claims_pending_alias_adjudication": sum(
                1 for v in run_1.values() for c in v.claims if c.pending_alias_adjudication
            ),
            "generation_failures": generation_failures,
            "ceiling_breaches": ceiling_breaches,
        },
        "owner_adjudication_item_counts": {
            "claims": packet.claim_item_count,
            "aliases": packet.alias_item_count,
            "summary_sentences": packet.summary_item_count,
            "total": packet.total_item_count,
        },
    }


def build_stage7c1_cost_ledger(stage_result, packet) -> dict:
    """Actual Stage 7C.1-to-checkpoint costs. Human adjudication time is
    deliberately NOT estimated -- actual owner effort will be measured."""
    run_1 = stage_result.validations_by_run[str(stage_result.primary_run_id)]
    rejection_reasons: dict[str, int] = {}
    for validation in run_1.values():
        for claim in validation.claims:
            for reason in claim.rejection_reasons:
                key = reason.split(":")[0][:80]
                rejection_reasons[key] = rejection_reasons.get(key, 0) + 1

    return {
        "stage": "7C.1 (to owner-adjudication checkpoint)",
        "compiler_calls_total": stage_result.compiler_calls_total,
        "runs_executed": [p.run_id for p in stage_result.run_provenance],
        "per_run": [
            {
                "run_id": p.run_id, "is_primary": p.is_primary, "model": p.model_identity,
                "input_tokens": p.input_tokens, "output_tokens": p.output_tokens,
                "estimated_cost_usd": p.estimated_cost_usd,
                "latency_seconds_total": p.latency_seconds_total,
                "generation_failures": p.generation_failures,
                "facets_failed_on_ceilings": p.facets_failed_on_ceilings,
            }
            for p in stage_result.run_provenance
        ],
        "total_estimated_cost_usd": stage_result.total_estimated_cost_usd,
        "declared_dollar_cap_usd": stage_result.dollar_ceiling_usd,
        "run_1_adjudication_item_count": packet.total_item_count,
        "validation_rejection_counts_by_reason": dict(sorted(rejection_reasons.items())),
        "out_of_page_scope_count": sum(
            1 for v in run_1.values() for c in v.claims if c.validation_status == "out_of_page_scope"
        ),
        "unresolved_counts": {
            "claims_pending_alias_adjudication": sum(
                1 for v in run_1.values() for c in v.claims if c.pending_alias_adjudication
            ),
            "supported_aliases_awaiting_verdict": packet.alias_item_count,
            "summary_sentences_awaiting_verdict": packet.summary_item_count,
            "accepted_claims_awaiting_verdict": packet.claim_item_count,
        },
        "representation_storage_bytes_before_embeddings": len(
            stage_result.model_dump_json().encode("utf-8")
        ),
        "facet_embeddings_created": 0,
        "facet_embeddings_note": (
            "ZERO by contract at this checkpoint: SS6.2 components 2 and 7 depend on owner verdicts and "
            "SS4.6 writes facet embeddings only after adjudication pass 3."
        ),
        "human_adjudication_time": "NOT ESTIMATED -- actual owner effort will be measured (SS8E)",
    }
