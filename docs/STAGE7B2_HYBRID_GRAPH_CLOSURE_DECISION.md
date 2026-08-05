# Stage 7B.2a -- Hybrid Vector-Graph Closure Decision

Durable decision record for Stage 7B.2, the bounded hybrid probe that
closes the Graph investigation. Companion to
`reports/stage7b2_hybrid_retrieval_scorecard.md` and
`reports/stage7b2_hybrid_retrieval_results.json` (same run object), and to
`docs/STAGE7B1_GRAPH_VS_VECTOR_DECISION.md`.

## What was tested

Whether Vector-assisted graph seeding, semantic edge matching, semantic
path ranking, and deterministic Vector/Graph RRF fusion can expose
Graph's latent multi-hop value **without** increasing the final evidence
budget, introducing authority leakage, or adding a query-time LLM. Five
frozen modes (V, G, H0, H1, H2) over two graph conditions (the frozen
real Stage 7B.1 snapshot and the deterministic perfect graph), all scored
by the frozen Stage 7B.0 scorer over the frozen top-K budgets.

## Decision

**Gate D: Do not retain Graph in the online retrieval path. Navigation or offline relationship analysis remains a separate, unevaluated use case.**

Neither gate A nor gate B applies. Real-graph H2 has no regressions relative to Vector (zero authority leakage, same final K, no query-time LLM) but improves only 0 of the three target questions (< 2).

## Key evidence

- Target questions Q04/Q06/Q07 complete-chain (Vector -> real-H2 -> perfect-H2):
  Q04 0.50->0.50->0.50,
  Q06 0.80->0.80->0.80,
  Q07 0.80->0.80->0.80 (coverage@K).
- Real-graph H2 target complete-chain improvements: 0; regressions vs Vector: []; Q12 regressed: False.
- Perfect-graph H2 target complete-chain improvements: 0; regressions vs Vector: [].
- Authority leakage: 0 across all modes/questions/conditions. Final budget never exceeds frozen top-K. No query-time LLM.

## Attribution

The ablation (G -> H0 -> H1 -> H2, plus the perfect-graph upper bound in
the scorecard) isolates whether any gain comes from fusion, better
seeding, semantic path ranking, or graph extraction quality. See the
"Ablation / attribution" table in the scorecard.

## Claim boundary

This decision states a result, not an impossibility theorem. The
conclusions hold ONLY for: the tested equal-weight RRF implementation;
the declared supplemental-seed budget (every explicit-alias seed retained
plus at most `max_supplemental_seed_nodes` RRF-ranked supplemental seeds);
the corrected semantic-path generation (ALL authority-eligible simple
paths enumerated and semantically ranked BEFORE any truncation to
`max_candidate_paths`); this corpus; and this embedding model. It is NOT
the claim "Hybrid cannot exceed Vector under a fixed budget" -- this very
run's perfect-graph H0 improves Q06 complete-chain coverage from 0.80 to
1.00, so graph structure demonstrably can help within budget. Graph was
simply not worth retaining in the ONLINE retrieval path under these
tested conditions.

## Limitations

- Small controlled corpus (~11 chunks, <=6 eligible per current query):
  Vector's recall ceiling is easy to reach, compressing any hybrid gain.
- The real graph is a single non-deterministic LLM extraction snapshot
  (Stage 7B.1); its missing/inconsistent edges cap what any hybrid over
  it can recover.
- The final evidence budget is the frozen Stage 7B.0 top-K (not enlarged
  for Hybrid), by design -- so a hybrid gain must come from better
  ranking within the SAME budget, not more evidence.
- No query-time LLM, no query decomposition, no router -- deliberately,
  to keep this a bounded ranking/fusion probe.
