# Consolidated Findings, Limitations, and Engineering Learnings

Cross-cutting record for the authority-aware retrieval and Graph
investigation (Stages 7R.1 → 7B.2). Per-stage detail lives in the
stage decision docs; this document captures the *transferable* findings,
limitations, and engineering learnings so they are not rediscovered.

Companion documents:
- `docs/STAGE7B0_CROSS_DOCUMENT_QUALIFICATION.md`
- `docs/STAGE7B1_GRAPH_VS_VECTOR_DECISION.md`
- `docs/STAGE7B2_HYBRID_GRAPH_CLOSURE_DECISION.md`
- `docs/POC_STATUS_AND_EVIDENCE.md` (per-stage table)

---

## 1. The headline findings

1. **Revision authority must be resolved at query time, never baked into content.**
   Effective/current/historical/draft status is decided by the Stage 7R
   registry/resolver against an `as_of_date`; it is never stored on a
   chunk and never written into source-document text. (Corrected in
   7R.2a after a fixture leaked a "PROPOSED" status into a document.)

2. **Authority filtering must happen BEFORE ranking/traversal — in the store predicate.**
   The eligibility restriction (`document_revision_id IN (...)`) belongs
   *inside* the ranking query, before `ORDER BY <distance> LIMIT`. A
   "retrieve top-K then post-filter" design leaks ineligible revisions
   whenever the budget is smaller than the number of ineligible
   candidates ranked above the first eligible one. This holds identically
   for Vector search, semantic-edge search, and graph traversal.

3. **Vector RAG degrades *gracefully* on distributed multi-hop; it retrieves partial chains.**
   With evidence distributed one hop per document, Vector fully answers
   direct/one-hop questions and retrieves *part* of deep chains — it
   misses the intermediate hops the query never names, out-ranked by
   lexically-similar but unrelated chunks. This is a real, measurable gap
   (Stage 7B.0), not a failure.

4. **A real LLM graph extractor does NOT reliably close that gap.**
   (Stage 7B.1.) A single missed or inconsistently-named edge breaks a
   multi-hop chain, so graph traversal retrieves *less* than Vector.
   Extraction is imperfect (recall ~0.8) and non-deterministic even at
   temperature 0. The multi-hop advantage is real only with a *perfect*
   extractor.

5. **In this experiment, hybrid fusion converged to Vector.**
   (Stage 7B.2a.) For *the tested equal-weight RRF implementation*, *the
   declared supplemental-seed budget (max 4 RRF-ranked seeds)*, *the
   corrected semantic-path generation (all eligible simple paths
   enumerated and ranked before truncation)*, *this corpus, and this
   embedding model*, Reciprocal-Rank Fusion of Vector with Graph — under
   the same top-K budget and with no query-time LLM — *rescued* a bad
   graph up to Vector's level (removing graph regressions) but did not
   improve any of the three target questions; on the perfect graph, mixing
   the fixed Vector ranking into a complete graph chain under the shared
   budget diluted the graph's gains. Vector-assisted seeding and semantic
   path ranking added nothing over plain fusion here. This is an observed
   result under the stated configuration, **not** a proof that hybrid can
   never exceed Vector: the same run's perfect-graph H0 raised Q06 from
   0.80 to 1.00, so graph structure *can* help within budget. **Decision
   (gate D): do not retain Graph in the online retrieval path. Navigation
   or offline relationship analysis remains a separate, unevaluated use
   case.**

**Net architectural conclusion (scoped):** for this corpus, this
embedding model, this fixed evidence budget, and these constraints,
authority-aware **Vector** retrieval was the right choice — Graph added
cost, maintenance, entity-normalization risk, and non-determinism without
a net retrieval win in the online path. Revisit graph only if (a) a
higher-recall/deterministic structured-relationship source exists, (b)
the corpus grows large/noisy enough that Vector's own recall degrades, or
(c) the evidence budget is allowed to grow (so fusion is not a zero-sum
dilution).

---

## 2. Known limitations (apply to all of 7B.*)

- **Small controlled corpus.** ~11 chunks; under a current-intent query
  only ~6 chunks are authority-eligible. Vector's recall ceiling is easy
  to reach, so absolute scores overstate large-corpus Vector performance
  and *compress* any hybrid gain. The value is the **methodology and the
  frozen fairness harness**, not the headline deltas.
- **LLM extraction non-determinism.** The real graph is a single labelled
  snapshot; re-running changes which edge is missed. Committed numbers are
  a snapshot, not a guarantee.
- **Fixed evidence budget is a zero-sum constraint on fusion.** Because
  Hybrid may not enlarge the final top-K, a hybrid gain must come from
  better *ranking* within the same budget — which fusion with a fixed
  Vector ranking structurally prevents.
- **Seeding depends on the query naming a graph entity.** A question that
  never names a seedable entity (e.g. a draft-control question that never
  says "C-91") yields `no_seed_entity`; only Vector fallback answers it.
- **Single embedding model, single format (DOCX).** These benchmarks
  isolate authority/distribution/relationship behavior, not format parity
  or embedding-model choice.

---

## 3. Engineering learnings (transferable, baked into the frozen products)

### Determinism & reproducibility
- Generate fixtures deterministically: fixed document timestamps AND
  normalized ZIP entry timestamps (DOCX/PPTX are ZIP packages), so bytes
  — and therefore `source_sha256` — are reproducible. Track the generated
  bytes AND record their expected SHA-256 in a manifest; re-verify on load
  and fail loudly on divergence.
- Provide a deterministic, no-network **fake** for every hosted/networked
  dependency (embeddings, answer model, relationship extractor) so the
  default test suite needs no network or API key.
- Treat any hosted-LLM output as non-deterministic; commit it as a
  labelled snapshot and mechanically validate it (never trust it).

### Provenance & auditability
- Every retrieval result — Vector, Graph, or Hybrid — carries complete
  chunk provenance: `logical_document_id`, `document_revision_id`,
  `chunk_id`, `content_sha256`, `source_document_sha256`, source path,
  `source_refs`, plus the resolver's authority label. No bare graph edge
  is ever "evidence"; only the source chunk it cites is.
- Verify frozen inputs by a content-covering hash (an index hash over
  every `(chunk_id, content_sha256)`), not just by chunk ids — this proves
  both identity *and* content match before building anything on them.
- Commit reports that embed enough per-item + provenance detail to audit
  the conclusion even though the regenerable `artifacts/` tree is
  gitignored.

### Scoring integrity / fair comparison
- Reuse ONE scorer across every mode being compared (import the frozen
  `_evaluate_question` + `build_evidence_alignment`; prove it by an
  import-identity test). Never reimplement metrics per mode.
- Keep evaluation truth (required/forbidden facts, expected chains) out of
  every retrieval/construction path; only the evaluator reads it. Enforce
  with an AST test (subscript/attribute reads), not a substring scan (a
  docstring may legitimately *name* the fields to say it does not read
  them).
- Never encode a desired outcome (e.g. "graph beats vector") as a test
  expectation. Tests assert *safety and structure* (authority, budget,
  provenance, determinism); the value question is *reported*, and the
  stage must be free to conclude negatively.

### Entity normalization (graph)
- Normalize entity surface forms to connect the same entity across chunks
  (strip leading articles and leading entity-type nouns like
  "Control "/"Procedure " uniformly), but NEVER merge distinct enterprise
  identifiers (`C-88` vs `C-88a` must stay separate). Measure
  normalization collisions and fail on a dangerous merge.
- Do this normalization from *general* rules only — never using the
  benchmark's expected chain to decide which nodes to merge.

### Metric naming precision
- Name metrics for exactly what they count: `ineligible_hit_count_at_k`
  (how many hits are authority-ineligible) is not "leakage";
  `eligible_hit_precision_at_k` is precision over eligible hits. Add
  `distinct_..._count` where multiplicity matters. Ambiguous names caused
  a correction (7R.2a).

### Contract/scenario discipline
- Scenario comparison must be **exact equality** (eligible set, excluded
  (revision, reason) pairs, full label set, integrity error code). An
  unexpected *extra* exclusion or label must fail the scenario, not pass
  silently (7R.1b).
- Configuration/decision contracts hold ONE immutable global config +
  decision gates, declared *before* the measured run, with NO
  per-question tuning and NO evaluation-truth hints. Decision gates are
  evaluated in a fixed, pre-declared order and never altered after seeing
  results.

### Isolation
- Each benchmark gets its OWN isolated Postgres table(s); never touch a
  prior stage's table or the unrelated GraphRAG POC tables. Scripts that
  re-run against a shared registry must clean only their own logical
  documents first.
- Postgres is sufficient for graph persistence at this scale — no Neo4j,
  no generic graph framework.

### Process
- Prefer running the real test suite (or a saved script) over many
  slightly-varying inline one-liners — a permission "don't ask again"
  does not match across varying inline command text.
- Commit only on explicit request; stage exactly the intended files and
  leave unrelated scratch files untracked.
