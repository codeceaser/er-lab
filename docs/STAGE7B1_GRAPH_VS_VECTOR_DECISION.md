# Stage 7B.1 — Evidence-Backed Graph vs Vector: Findings and Decision

This is the durable decision record for Stage 7B.1. It documents what was
built, what was measured, and the resulting recommendation. It is the
companion to the machine-generated reports
`reports/stage7b1_graph_build_results.json`,
`reports/stage7b1_graph_retrieval_results.json`, and
`reports/stage7b1_vector_vs_graph_scorecard.md`, and to the Stage 7B.0
qualification doc `docs/STAGE7B0_CROSS_DOCUMENT_QUALIFICATION.md`.

Stage 7B.1 built an evidence-backed graph projection from the **exact**
Stage 7B.0 canonical chunks and compared Graph retrieval against the
frozen Stage 7B.0 Vector baseline under Stage 7B.0's frozen fairness
contract. **No answer generation, no ADK, no wiki, no vision, no query
decomposition, no retrieval router, no Neo4j, no generic graph
framework, no workflow/state management** was built. Graph superiority
was never encoded as a test expectation; the stage was free to conclude
Graph does not add sufficient value — and it did.

## What was measured (real run: `openai:gpt-4o-mini`, real Postgres, real embeddings)

Frozen input identity re-verified before any graph work (source SHA-256,
document_revision_ids, chunk_ids, and content hashes via the committed
Stage 7B.0 `index_hash`) — **all matched**.

### Graph build accuracy vs the Stage 7B.0 facts
| Metric | Value |
|---|---|
| Nodes / edge assertions / distinct evidence chunks | 17 / 14 / 10 |
| Expected-fact edge recall | **0.80** (12/15); missing `F_svc`, `F_prc_current`, `F_adj_prc` |
| Extracted-edge precision | 0.86 (2 unsupported edges) |
| Relationships rejected during build (unsupported `supporting_text`) | 1 |
| Entity-normalization collisions (e.g. C-88 vs C-88a merged) | **0** |
| Provenance completeness / edges with invalid-or-missing chunk | 1.00 / 0 |
| Extraction tokens (in/out) / estimated cost / failures | 3708 / 958 / **$0.0011** / 0 |
| Graph payload hash | `1ffd01c8f7977d82…` |

### Retrieval comparison (same 12 questions, same intents/as-of/required+forbidden/top-K)
- **Graph authority correct: 12/12; total authority leakage: 0** (historical/draft
  edges never entered a current traversal — authority filtered *before* traversal).
- **Improved: 0. Unchanged: 7. Regressed: 5.**
- Mean query latency (Vector / Graph): ~123 ms / ~114 ms — comparable
  (both dominated by the resolver + embedding on this tiny corpus).

| Question | Vector cov | Graph cov | Vector chain | Graph chain | Change |
|---|---|---|---|---|---|
| Q01 direct | 1.00 | 1.00 | ✓ | ✓ | unchanged |
| Q02 one-hop | 1.00 | 1.00 | ✓ | ✓ | unchanged |
| Q03 two-hop | 1.00 | 0.50 | ✓ | ✗ | **regressed** |
| Q04 two-hop | 0.50 | 0.00 | ✗ | ✗ | **regressed** |
| Q05 three-hop | 1.00 | 1.00 | ✓ | ✓ | unchanged |
| Q06 four-hop | 0.80 | 0.20 | ✗ | ✗ | **regressed** |
| Q07 consolidation | 0.80 | 0.20 | ✗ | ✗ | **regressed** |
| Q08 distractor | 1.00 | 1.00 | ✓ | ✓ | unchanged |
| Q09 current-authority | 1.00 | 1.00 | ✓ | ✓ | unchanged |
| Q10 historical multi-hop | 1.00 | 1.00 | ✓ | ✓ | unchanged |
| Q11 historical direct | 1.00 | 1.00 | ✓ | ✓ | unchanged |
| Q12 draft | 1.00 | 0.00 | ✓ | ✗ | **regressed** |

**Q04/Q06/Q07 — the very distributed multi-hop questions Vector missed —
did NOT become complete-chain under Graph.** The naive expectation
(Graph follows explicit edges and beats Vector on multi-hop) did not hold
with a real extractor.

## Why Graph lost (the substantive finding)

Graph's multi-hop advantage is **entirely contingent on the LLM
extracting every hop, consistently**:

1. **Missing edges break the chain.** In the measured run the LLM did not
   extract the `SERVICE-CATALOGUE` "Payment Settlement → Obligation O-31"
   edge (`F_svc`), so traversal from `APP-224510` dead-ends at
   "Payment Settlement" and never reaches O-31 → C-88 → P-205 (Q06 → 0.20).
2. **Inconsistent entity surface forms fragment nodes.** In an earlier
   run the LLM emitted "Control C-88" in one chunk and bare "C-88" in
   another, creating two nodes for the same control and breaking the
   chain there instead. A principled, benchmark-truth-free normalization
   (strip leading enterprise type-nouns like "Control "/"Procedure ",
   applied uniformly, never merging distinct identifiers) reconnected
   *those* nodes but could not recover an edge the model simply never
   produced.
3. **Extraction is non-deterministic.** Even at temperature 0, a hosted
   model varies between runs, so which hop is missing (and therefore the
   exact per-question numbers) shifts. The committed numbers are a
   labelled snapshot.

Vector RAG has none of this fragility — it retrieves chunks by embedding
similarity regardless of extraction completeness — which is precisely why
it degraded gracefully to *partial* on the multi-hop questions (Stage
7B.0) rather than collapsing.

### Even the best case is only mixed
The deterministic `FakeRelationshipExtractor` (a perfect, rule-based
extractor: recall 1.00, precision 1.00, 0 collisions) is the upper bound.
Under it, Graph **improves the deep endpoint multi-hop Q04/Q06/Q07** (a
seed at a chain endpoint traverses the whole chain), but **regresses
Q05/Q10** (a mid-chain seed reaches the chain in *both* directions and
the tight frozen top-K budget drops the far but required hop under the
mandated hop-distance-first ranking) and **Q12** (the draft query never
names C-91, so seeding yields `no_seed_entity`). So even with perfect
extraction the benefit is mixed, not a clear win, under 7B.0's frozen
budgets and the mandated ranking.

## Decision

**Recommendation: defer Graph — its benefit does not justify its
cost/fragility for this architecture.**

- `reject` was reserved for a *broken or unsafe* graph (authority
  leakage, dangerous entity collisions, or very low recall); this graph
  is authority-safe (0 leakage), collision-free, and recall 0.80, so
  outright rejection is too strong.
- The benefit is **latent** (a perfect extractor helps deep multi-hop)
  but **not reliably achievable** with a real, non-deterministic LLM
  extractor, and it adds real extraction cost, prompt/normalization
  maintenance, and chain-breakage risk.
- **Revisit only if** a higher-recall/deterministic extractor becomes
  available, or a larger/noisier corpus (where Vector's own recall
  degrades and the small-corpus ceiling no longer masks the difference)
  changes the economics.

## Implementation and maintenance limitations

- Graph retrieval depends on the query naming a seedable graph entity; a
  question that never names one (the draft-control question, which never
  mentions C-91) returns `no_seed_entity` and retrieves nothing, where
  lexical Vector still matches.
- Hop-distance-first ranking (mandated) under a tight, frozen top-K
  budget can drop a far-but-required hop when a mid-chain seed reaches the
  rest of the chain in both directions.
- Graph adds an extraction step: real model cost, prompt maintenance,
  entity-normalization risk, and run-to-run non-determinism that Vector
  does not have.
- This is a small controlled corpus; absolute deltas would differ on a
  larger, noisier corpus — the value here is the **fair, frozen
  comparison methodology and the honest per-question evidence**, not the
  headline deltas.

## Audit trail

The committed `reports/stage7b1_graph_build_results.json` embeds the full
node set and every edge assertion with complete provenance (supporting
chunk id, content hash, source path, source refs, extraction run id), so
the measured result is auditable even though `artifacts/stage7b1/` is
gitignored. Graph and Vector are scored by the **same** frozen Stage 7B.0
`_evaluate_question` over the **same** `build_evidence_alignment`
fact→chunk mapping (import identity, proven by
`tests/test_graph_retrieval.py::test_graph_uses_the_frozen_stage7b0_scorer_and_fact_alignment`).
