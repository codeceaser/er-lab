# Stage 7C.0 — Deterministic Wiki Projection Qualification (W0)

**Plan:** `docs/STAGE7C_WIKI_PLAN.md` Revision 6 (owner-approved, frozen).

**Zero LLM calls.** No claim, alias, summary, adjudication verdict, W1 facet or facet embedding exists. No D0 / W1-D / W1-FULL benchmark comparison has been run.

## Projection counts

| Quantity | Value |
|---|---|
| Logical documents | 6 |
| Revisions | 11 |
| Sections (1:1 view over CanonicalChunk) | 11 |
| Anchors | 25 |
| — identifier (Lane 1) | 12 |
| — phrase (Lane 2) | 1 |
| — heading_title (Lane 3, no page identity) | 12 |
| Anchor postings | 47 |
| Page identities | 13 |
| — governed_identifier | 12 |
| — business_topic | 1 |
| Facets (deterministic membership) | 22 |
| Structural links | 34 |
| Exact-anchor links | 48 |
| — of which advisory | 6 |
| **M_max (measured)** | **3** |

`M_max` argmax pages: `IDENT:O-31`, `IDENT:P-205`, `PHRASE:payment settlement`

`M_max` is a **measured property of the completed projection**, never a configuration knob. It is frozen here so Stage 7C.2 can evaluate the Revision 6 ceiling `C = (P_seed + B) x M_max x F_max`. That ceiling is **not** evaluated in this stage.

## C-88 / C-88a separation

- `C-88` → page `IDENT:C-88`, display `C-88`, 2 posting chunk(s)
- `C-88a` → page `IDENT:C-88A`, display `C-88a`, 2 posting chunk(s)
- distinct anchor ids: **True**
- chunks where both occur: none
- **never merged** at identity, anchor, page, facet, membership or link level

## Lane 2 phrase-anchor decisions

| Candidate | Distinct chunks | Distinct documents | Accepted | Reason |
|---|---|---|---|---|
| `adjacent domain reference` | 1 | 1 | no | below_min_distinct_chunks |
| `application app-224499` | 1 | 1 | no | identifier_collision |
| `application app-224510` | 1 | 1 | no | identifier_collision |
| `application app-330012` | 1 | 1 | no | identifier_collision |
| `application portfolio` | 2 | 1 | no | below_min_distinct_logical_documents |
| `business service catalogue` | 1 | 1 | no | below_min_distinct_chunks |
| `control c-77` | 1 | 1 | no | identifier_collision |
| `control c-88` | 2 | 2 | no | identifier_collision |
| `control c-88a` | 2 | 2 | no | identifier_collision |
| `control c-91` | 1 | 1 | no | identifier_collision |
| `control implementations` | 3 | 1 | no | below_min_distinct_logical_documents |
| `control library` | 3 | 1 | no | below_min_distinct_logical_documents |
| `governed services` | 1 | 1 | no | below_min_distinct_chunks |
| `obligation coverage` | 2 | 1 | no | below_min_distinct_logical_documents |
| `obligation o-31` | 3 | 2 | no | identifier_collision |
| `obligation o-32` | 1 | 1 | no | identifier_collision |
| `obligation register` | 2 | 1 | no | below_min_distinct_logical_documents |
| `operating procedures` | 2 | 1 | no | below_min_distinct_logical_documents |
| `payment reconciliation` | 1 | 1 | no | below_min_distinct_chunks |
| `payment reconciliation chain` | 1 | 1 | no | below_min_distinct_chunks |
| `payment settlement` | 3 | 2 | **yes** | — |
| `procedure catalogue` | 2 | 1 | no | below_min_distinct_logical_documents |
| `procedure p-204` | 2 | 2 | no | identifier_collision |
| `procedure p-205` | 3 | 2 | no | identifier_collision |
| `procedure p-301` | 1 | 1 | no | identifier_collision |
| `registered applications` | 2 | 1 | no | below_min_distinct_logical_documents |

## W0 semantic control (W0 vs V)

- Embedding model: `sentence-transformers/all-MiniLM-L6-v2`
- Evaluator (imported by identity): `ingestion_bench.cross_document_benchmark.benchmark_runner._evaluate_question`
- Questions: 12
- W0 hit list identical to V: **12/12**
- **W0 == V: True**
- V outcomes: `{'partial': 3, 'solved': 9}`
- W0 outcomes: `{'partial': 3, 'solved': 9}`
- Authority leakage (V + W0): **0** (must be 0)

> W0 semantic retrieval is **expected** to equal V, because a W0 section is 1:1 with a chunk and reuses that chunk's existing embedding. **W0 ~ V is a successful control outcome, not a failure**, and no retrieval-improvement gate is applied to it.

> **W0 semantic control is NOT D0.** D0 adds anchor-derived seeding, deterministic hub expansion and deterministic navigation on top of chunk semantic retrieval, and is a Stage 7C.2 arm. Nothing in Stage 7C.0 expands a hub or traverses a link.

| Question | K | V outcome | W0 outcome | V cov@K | W0 cov@K | identical |
|---|---|---|---|---|---|---|
| Q01_direct_service_of_app | 3 | solved | solved | 1.00 | 1.00 | True |
| Q02_one_hop_control_of_obligation | 3 | solved | solved | 1.00 | 1.00 | True |
| Q03_two_hop_obligation_of_app | 3 | solved | solved | 1.00 | 1.00 | True |
| Q04_two_hop_control_of_service | 3 | partial | partial | 0.50 | 0.50 | True |
| Q05_three_hop_procedure_of_obligation | 4 | solved | solved | 1.00 | 1.00 | True |
| Q06_four_hop_procedure_of_app | 5 | partial | partial | 0.80 | 0.80 | True |
| Q07_consolidation_payment_settlement | 5 | partial | partial | 0.80 | 0.80 | True |
| Q08_distractor_resistance_current_control | 3 | solved | solved | 1.00 | 1.00 | True |
| Q09_current_authority_app | 3 | solved | solved | 1.00 | 1.00 | True |
| Q10_historical_procedure_of_obligation | 4 | solved | solved | 1.00 | 1.00 | True |
| Q11_historical_app_of_service | 3 | solved | solved | 1.00 | 1.00 | True |
| Q12_draft_proposed_control | 3 | solved | solved | 1.00 | 1.00 | True |

## Frozen contracts

- Projection hash: `4162fa515cf29d09391c0d963b76c7e63b1d454c4439ee0568805d1a31e3b613`
- Manifest SHA-256: `8aeee003092f2e9bd2f2f630b8c77c29283d0141ad498cdc5eb28be995a7316b`
- Sentence splitter: `wiki_sentence_splitter_v1` / `30ddb7d3484deabd...`
- D0 seed procedure: `d0_seed_procedure_v1` / `7033640938d3ed12...` — **frozen, not executed**
- D0 branch prioritizer: `d0_branch_prioritizer_v1` / `8c4f18449fe09c72...` — **frozen, not executed**

## Deviations and recorded interpretations

Four points where the frozen Revision 6 text needed a judgement call. None changes a gate, a threshold or the experiment's logic; each is recorded rather than silently resolved.

1. **Lane 2 stop-list semantics.** SS2.1 says a candidate is "rejected if any token is in a fixed closed stop-list". Read literally as *poisoning the candidate*, the sentence "**The** Payment Settlement business service is governed by ..." yields the single run `[The, Payment, Settlement]` and is rejected — which would destroy `Payment Settlement`, the anchor SS0.1 records as this corpus's ONLY cross-document phrase anchor and which SS1.5's chain depends on. Implemented so a stop word **breaks** the run instead; no candidate ever contains a stop word, so the rule's literal requirement also holds.
2. **Lane 2 identifier-collision rule.** SS2.1's "a candidate colliding with an identifier key is dropped (identifiers win)" is implemented as *a candidate containing an identifier token is dropped*. Under the narrower reading (exact key equality) `Obligation O-31`, `Control C-88` and `Procedure P-205` would all survive as competing hubs alongside their identifier pages, and SS0.1's "cross-document phrase anchors: `Payment Settlement` only" would be false. The implemented reading reproduces SS0.1 exactly — see the Lane 2 ledger above.
3. **`display_title`.** SS3.2 fixes it as the anchor's frozen `display_text`, "never re-worded". The W0 display rule implemented is *the exact surface form of the anchor's first posting in deterministic order*, so `IDENT:O-31` renders as `O-31`. SS1.5.3's illustrative facet record shows `"display_title": "Obligation O-31"`; producing that would require prepending a type word that is not part of the anchor, i.e. generating text. The contract rule was followed and the illustration was not.
4. **Module placement of rendering.** SS10.1 lists page rendering under `assembly.py` at Stage 7C.1, while SS11 requires rendering as a 7C.0 deliverable. Implementing it in `assembly.py` now would mean creating the 7C.1 module early, which the scope rules forbid. W0 rendering therefore lives in a small dedicated 7C.0 `rendering.py`; `assembly.py` remains unwritten and keeps its 7C.1 payload-composition role.

### One contract rule that fires on this corpus's key anchor

SS2.1 states that "a phrase posting into sections with disjoint identifier sets is flagged ambiguous and its links downgraded to advisory". `PHRASE:payment settlement` posts into `app_rev1` (`{APP-224499}`), `app_rev2` (`{APP-224510}`) and `svc_rev1` (`{O-31}`) — pairwise disjoint — so the rule fires on the corpus's only cross-document phrase anchor, and its 6 exact-anchor links are marked advisory.

The rule was implemented as written: the flag is recorded and the links are marked. The page is **not** split, because SS3.3's split rule is contracted for the *duplicate names* case, and a deterministic detector cannot distinguish a genuine duplicate name from a legitimate bridging anchor — splitting the latter would destroy the hub SS0.1 and SS1.5 depend on. Advisory links remain traversable and are marked everywhere they appear.

> **Owner decision to note before Stage 7C.2.** Any cross-document phrase anchor necessarily shows disjoint identifier context — that is what bridging *is* — so this rule will flag every such anchor on any corpus. If advisory status is later given retrieval or gating consequence, that consequence would fall hardest on exactly the anchors the Wiki hypothesis relies on. It has no such consequence today.

## Scope

Not implemented in this stage, by contract: the Stage 7C.1 facet compiler, W1 claims / aliases / summaries, owner adjudication, W1 payload composition, W1 facet embeddings, claim-derived links, Stage 7C.2 retrieval and navigation, the measured D0 / W1-D / W1-FULL arms, `N_advisory`, the counterfactual suppression probe, Gate Q, and the Gate A/B/C decision.

