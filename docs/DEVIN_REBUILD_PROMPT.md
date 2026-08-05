# Prompt for Devin — Authority-Aware Retrieval + Graph-vs-Vector Investigation (self-contained)

You are building a document-ingestion / retrieval benchmark and a bounded
Graph-vs-Vector investigation **from scratch**. You do **not** have access
to any prior repository. This document is the complete specification: it
already incorporates every correction and refinement learned on a previous
build, so **do not re-derive them and do not repeat the mistakes called
out below**. Treat each stage below as a *refined product* — build it
right the first time.

Work stage by stage, in order. After each stage, run its tests and a full
test run, and only then continue. Do not begin a later stage's concerns
early. Commit only when the human explicitly asks.

---

## 0. Mission & scope

Build, in this order:

- **Stage A — Revision Authority Registry & Resolver.** Decide which
  *revision* of a *logical document* is authoritative for a query, at a
  given `as_of_date`, under four intents (current / as_of / comparison /
  draft). Pure metadata governance; never touches document content.
- **Stage B — Authority-Aware Vector Retrieval.** Prove the registry
  actually changes semantic-search results: an isolated vector index +
  a retriever that filters eligible revisions *inside* the SQL ranking
  query.
- **Stage C — Cross-Document Relationship Holdout + Vector baseline.** A
  corpus whose relationship chains are distributed one hop per document;
  measure how much of each chain Vector recovers. Freeze a fairness
  contract for a future graph comparison.
- **Stage D — Evidence-Backed Graph + Vector-vs-Graph comparison.** Build
  a revision-scoped graph from the exact same chunks (LLM relationship
  extraction), compare Graph retrieval to the frozen Vector baseline.
- **Stage E — Hybrid Vector-Graph probe.** Test whether fusion + smarter
  seeding + semantic path ranking exposes graph's latent value without
  enlarging the evidence budget or adding a query-time LLM. Decide.

**Do NOT build** (in any stage): answer generation, an agentic router,
query-decomposition or query-planning LLM, wiki retrieval, vision
enrichment, Neo4j, a generic graph/retrieval framework, or production
orchestration. These stages are *measurement*, not a product.

Each stage may conclude **negatively** (e.g. "graph does not help").
Never encode a desired outcome as a test expectation.

---

## 1. Tech stack & ground rules

- Python 3.13, `pydantic` v2 with `ConfigDict(extra="forbid")` on every
  model. Type-hint everything.
- Postgres + `pgvector` for all persisted vector/graph state. Each
  benchmark uses its **own isolated table(s)** — never another stage's
  table. Connection string from a `DATABASE_URL` env var; never hardcode
  or log secrets.
- Embeddings: local `sentence-transformers/all-MiniLM-L6-v2` (no API key),
  env-overridable. LLM (Stage D extraction only): OpenAI `gpt-4o-mini`,
  env-overridable, lazily constructed (constructing the client must not
  require a key or network).
- **Every hosted/networked dependency gets a deterministic, no-network
  Fake** (fake embedding provider, fake relationship extractor). The
  default test suite must pass with **no network and no API key**. Real
  infra is exercised by **one skippable integration test per stage**
  (skip with the exact reason when `DATABASE_URL`/`OPENAI_API_KEY`/Postgres
  is unavailable).
- Determinism: fixed content + fixed timestamps; DOCX/PPTX are ZIP
  packages — rewrite every ZIP entry timestamp to a fixed value so bytes
  (and `source_sha256`) reproduce. A hosted LLM is non-deterministic even
  at temperature 0 — treat its output as a labelled snapshot and validate
  it mechanically.
- Reports: JSON + Markdown must derive from the **same run object**.
  Commit reports that embed enough per-item + provenance detail to audit
  the conclusion. `artifacts/` may be gitignored (regenerable); the
  committed reports must stand alone.
- Commit only on explicit request. Stage exactly the intended files.

---

## 2. Reused upstream contracts (assume these exist / build minimal versions)

You need a canonical ingestion layer. Build a **minimal** version of these
(they are not the focus — do not gold-plate):

- `CanonicalChunk`: an immutable, content-hashed chunk with at least:
  `chunk_id`, `doc_id`, `logical_document_id`, `document_revision_id`,
  `source_document_sha256`, `version_label`, `revision_number`,
  `chunk_type`, `unit_indices`, `heading_path`, `source_element_ids`,
  `source_refs` (list of structured provenance refs), `retrieval_text`
  (the exact text embedded), `content_sha256` (hash over content +
  provenance), `embedding_input_sha256`.
- `compute_document_revision_id(logical_document_id, source_document_sha256,
  version_label, revision_number) -> sha256 hex`: deterministic identity of
  one revision (never a random UUID).
- `chunk_document(canonical_document, config, *, revision_context) ->
  list[CanonicalChunk]`: a deterministic chunker. Same input → same
  `chunk_id`s and `content_sha256`s.
- A document adapter that converts a source file (DOCX is enough) to a
  canonical document with a real `source_sha256`. (A library like Docling
  works; a minimal DOCX text extractor is fine — the benchmarks only need
  one sentence per chunk.) **However, numerical comparability requires a
  fixed adapter+chunker:** if you intend to reproduce the prior run's
  chunk ids / content hashes / retrieval numbers (see Appendix A
  `G_fixture_source_text`), you must use the SAME adapter and chunker
  configuration throughout — do NOT swap in a different minimal DOCX parser
  while simultaneously requiring reproduction of prior hashes/results.
  Choose one adapter/chunker, freeze it, and reuse it read-only.
- `EmbeddingProvider` protocol: `embed(list[str]) -> vectors + call_count
  + elapsed + cost`. Provide `FakeEmbeddingProvider` (deterministic
  hash-based unit vectors) and `SentenceTransformerEmbeddingProvider`
  (lazy load).

**Freeze the canonical/chunker/adapter/embedding contracts once working.**
Later stages must reuse them read-only and must never rechunk differently.

---

## 3. Cross-cutting principles (REQUIREMENTS — these are the baked-in learnings)

Apply all of these in every relevant stage:

1. **Authority is query-time metadata, never content.** Never write
   draft/effective/superseded/proposed status into a source document or a
   chunk. It comes only from the resolver. *(A previous build leaked a
   "PROPOSED" line into a fixture and had to redo fixtures, hashes,
   chunks, vectors, and reports — do not repeat this.)*
2. **Authority filtering happens BEFORE ranking, inside the store query.**
   The eligibility predicate (`document_revision_id IN (:ids)`) must be in
   the SAME SQL as `ORDER BY <distance> LIMIT`. Never fetch an unfiltered
   top-K and post-filter. An empty eligible set returns zero results
   (never "search everything"). This applies to vector search,
   semantic-edge search, and graph traversal alike.
3. **Complete provenance on every hit; no bare edge is evidence.** Only a
   source chunk is retrievable evidence. A graph edge merely *cites* a
   chunk.
4. **Verify frozen inputs by a content-covering hash before building on
   them.** Recompute an index hash over every `(chunk_id, content_sha256)`
   and compare to the committed value; fail before doing any work if it
   differs. Also verify source SHA-256, document_revision_ids, chunk_ids.
5. **One shared scorer across compared modes.** Implement the metric
   computation once; every mode/graph/hybrid result is scored by the same
   function over the same fact→chunk alignment. Prove it (import identity
   test). Never reimplement metrics per mode.
6. **Evaluation truth is read only by the evaluator.** Required/forbidden
   facts and expected chains must never be read by any ingestion,
   retrieval, extraction, seeding, path, or fusion code. Enforce with an
   AST test that looks for subscript-key / attribute reads (not a
   substring scan — a docstring may name the fields to say it avoids
   them).
7. **Never encode a desired outcome as a test expectation.** Tests assert
   safety/structure (authority leakage = 0, budget respected, provenance
   complete, determinism, no query-time LLM). The value question is
   reported; the stage may conclude negatively.
8. **Metric names must say exactly what they count.** e.g.
   `ineligible_hit_count_at_k` (not "leakage"), `eligible_hit_precision_at_k`,
   `distinct_ineligible_revision_count_at_k`.
9. **Entity normalization (graph): connect same-entity surface forms but
   never merge distinct identifiers.** Strip leading articles and leading
   entity-type nouns ("Control ", "Procedure ", "Obligation ",
   "Application ") uniformly; keep `C-88` and `C-88a` distinct. Measure
   collisions; fail on a dangerous merge. Derive the rule generally —
   never from the expected chain.
10. **Config/decision contracts are global and pre-declared.** One
    immutable parameter set + decision gates, no per-question tuning, no
    evaluation-truth hints, gates evaluated in a fixed order and never
    changed after seeing results.

---

## 4. Stage A — Revision Authority Registry & Resolver (refined)

**Model (three-way split — keep them separate):**
- `RevisionIdentity` (immutable): `logical_document_id`,
  `document_revision_id`, `source_document_sha256`, `version_label`,
  `revision_number`. (Reuse the chunker's revision-context identity;
  never recompute differently.)
- `AuthorityMetadata` (mutable governance status ONLY): `publication_status`
  ∈ {draft, under_review, approved, withdrawn}, `approved_at`,
  authority source/reference/recorded_at/recorded_by. **No effective
  dates here.**
- `AuthorityPeriod` (the SOLE source of effective dates): `effective_from`,
  `effective_to` (nullable = open), `predecessor_revision_id`,
  opening/closing event ids, `closure_reason`, provenance. A revision may
  have MULTIPLE non-overlapping periods over time. Interval convention:
  `effective_from <= as_of_date < effective_to`. A **zero-width** period
  (`effective_to == effective_from`) is a valid representation of a
  pre-effective correction (matches no date).
- Append-only `AuthorityDecisionEvent` audit log with structured
  `decision_effective_date` and `closure_reason` (never parse these out of
  free text).

**Derived authority state** (6 values, computed at query time, never
stored): draft / under_review / approved_future / effective / superseded /
withdrawn.

**Operations (narrow; each appends an audit event; each atomic):**
- `register_revision` → creates identity + draft metadata + event, all in
  ONE `repository.transaction()`.
- `record_authority_decision` → a PURE status change. **May set ONLY
  draft/under_review** (approved requires a real period via activate;
  withdrawn requires closing a period via withdraw). **Additionally reject
  it if the revision already has ANY non-zero-width period** (current,
  historical, or scheduled future) — once a revision has held real
  authority, only activate/reinstate/withdraw may change it. Zero-width
  corrected candidates remain editable. Wrap writes in one transaction.
- `activate_revision` → opens a new period; closes the predecessor's open
  period as `superseded`. No public generic `closure_reason` parameter.
- `reinstate_revision` → like activate but closes the old period as
  `rollback` (for post-effective rollback). Shares one private validated
  atomic path with activate.
- `withdraw_revision` → closes the open period at an explicit
  `withdrawal_effective_date` (NEVER `recorded_at`). Accepts only
  `withdrawn`/`correction`. **`correction` requires
  `withdrawal_effective_date == open_period.effective_from` exactly**
  (a correction retracts a period that never took effect).
- All activation/reinstatement fully **validate before any write**
  (existence, same logical document, no self-supersession, exactly one
  open period to close, no period overlap) — a validation failure raises
  before the transaction opens. Prove atomicity with fault-injection tests
  (in-memory snapshot/restore) AND a **real mid-transaction Postgres
  fault** that writes then raises and proves ROLLBACK (a pre-write
  validation rejection is NOT sufficient evidence of DB rollback).

**Resolver — four intents, ONE central integrity pass first:**
- `resolve_query_scope(repository, logical_document_id, query_intent,
  as_of_date, requested_revision_ids)`. `as_of_date` is always explicit —
  never default to today.
- Run ONE `validate_document_integrity` before eligibility selection,
  shared by all four intents. Classify each problem as **revision-scoped**
  (excludable individually) or **document-scoped** (hard-fails the WHOLE
  query for ALL intents, including comparison/draft — the shared timeline
  is untrustworthy). Specific error codes (e.g.
  `cross_revision_period_overlap`, `missing_successor`, `orphaned_period`,
  `unapproved_with_real_period`, `no_effective_revision`), never a generic
  bucket.
- current/as_of pick exactly one effective revision (any problem fails
  closed — never silently pick one of two overlapping revisions).
  comparison/draft take explicit `requested_revision_ids` and exclude a
  malformed *revision* individually.

**Persistence:** three isolated tables (registry, period, event). For a
**from-scratch build these tables are created fresh, so legacy-schema
migration/reset is NOT in mandatory scope** — just create the three
tables.

> *Optional integration note (only if you are attaching to a database that
> already holds an older revision-authority schema):* handle it explicitly
> — `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for new columns; detect
> populated legacy effective/supersession columns with no matching period
> and **fail fast** with a clear error plus a one-time reset script
> (drop/recreate only these three tables); never silently ignore populated
> legacy data. This is not required for a clean-slate rebuild.

**Scenario contract:** a JSON of registry setups + queries; the runner
requires **EXACT equality** on eligible revisions, excluded
(revision, reason_code) pairs, the full authority-label state set, and the
integrity error code. An unexpected *extra* exclusion or label must FAIL
the scenario.

**Pitfalls we hit — avoid:** storing effective dates on metadata (they
belong only on periods); letting `record_authority_decision` set
approved/withdrawn or edit a revision with real authority; conflating
`withdrawal_effective_date` with `recorded_at`; a generic public
`closure_reason` that lets a caller mislabel a transition; comparison/draft
NOT hard-failing on document-scoped corruption; scenario comparison being a
subset check instead of exact equality; "proving" Postgres rollback with a
pre-write validation error.

---

## 5. Stage B — Authority-Aware Vector Retrieval (refined)

- Build ONE isolated pgvector table for this benchmark. Ingest/chunk/embed
  each revision **once**. Record: row count, an **index content hash**
  over `(chunk_id, content_sha256)`, an **`embedding_payload_sha256`**
  over ordered `(chunk_id, content_sha256, sha256(retrieval_text),
  stored_vector_literal)` (proves the stored *embedding*, not just chunk
  identity, is unchanged), embedding model, embedding-call count, chunk
  ids/hashes. Scope every store operation by `logical_document_id`
  explicitly.
- **Retriever:** call the Stage A resolver → fail closed on
  `integrity_error` (never call the store then) → get eligible revision
  ids → SQL `WHERE document_revision_id IN (:ids)` **before** `ORDER BY
  embedding <=> :q LIMIT :k`. Also run an **unfiltered** search for an
  honest comparison. Each hit carries query intent, as_of, registry
  snapshot hash, eligible ids, excluded+reasons, authority label, document
  identity, chunk + source provenance, similarity score/rank.
- **Fixtures:** N near-identical real DOCX revisions of ONE logical
  document, differing ONLY in the fact value (e.g. a retention period).
  **No revision's text may carry any authority signal** — labels come only
  from the resolver. Track the DOCX bytes; record expected SHA-256 in a
  manifest and re-verify on load (fail on divergence).
- **Scenarios:** current (returns the effective revision), historical
  (as_of returns the then-effective revision), draft (explicit draft
  revision, labeled draft), comparison (exactly the requested revisions),
  and **authority switch without reindexing**: activate a new,
  already-indexed revision superseding the current one; prove the index
  hash, row count, chunk ids/hashes, stored embeddings, and
  embedding-call count are **byte-identical** before/after — only the
  registry snapshot hash and the eligible/search results change. Validate
  the resolver's before/after authority labels against the contract.
- **Metrics** (name precisely): `ineligible_hit_count_at_k`,
  `distinct_ineligible_revision_count_at_k`, `eligible_hit_precision_at_k`,
  required-revision hit@k, expected-value retrieved, latencies. Report
  honestly (unfiltered search *will* surface ineligible revisions; that is
  the point).

**Pitfalls we hit — avoid:** a fixture carrying its own status text;
post-filtering instead of SQL-level eligibility; discarding the full
search result after computing metrics (persist it); index/embedding
immutability proven only by chunk id (add the embedding payload hash);
per-op scoping by embedding_model only (add logical_document_id).

---

## 6. Stage C — Cross-Document Relationship Holdout + Vector baseline (refined)

- **Corpus:** one logical policy whose CURRENT relationship chain is
  distributed **one hop per logical document** (e.g. App → Service →
  Obligation → Control → Procedure across 5 documents). Each real-chain
  document contains a **single relationship sentence** so the chunker
  yields one single-fact chunk — **no chunk holds a pre-assembled multi-hop
  answer** (enforce with a test). Add projection-neutral distractors:
  a retired app, a superseded control, a historical procedure (all
  authority-historical), a draft control (registered, never activated),
  and one **lexically similar but unrelated** "adjacent" chain that is
  authority-CURRENT (so authority can't remove it — it tests vector
  ranking). Distractors live in separate revisions or a separate document.
  Use ONE format.
- **Projection-neutral fact contract (JSON):** each fact = fact_id,
  subject, predicate, object, supporting logical_document_id + revision
  symbol, `expected_supporting_passage` (a substring that resolves to the
  chunk at runtime — do NOT hardcode chunk ids, they depend on
  logical_document_id), authority applicability, current/historical/draft
  classification, distractor status. Ingestion/retrieval NEVER read these.
- **Question contract (JSON, ~10–12):** across direct / one-hop /
  distributed two-hop / distributed multi-hop / consolidation /
  distractor-resistance / current-authority / historical / draft. Each
  declares intent, as_of, requested revision symbols (for draft/
  comparison), required + forbidden fact ids, expected relationship chain
  (evaluation truth only), and a **top-K evidence budget** sized so
  `chain_length <= top_k < eligible-corpus-size` (so ranking actually
  matters — do NOT set top_k >= eligible corpus or the answer is trivially
  retrieved).
- **Retriever:** cross-document — resolve EACH document via the Stage A
  resolver, union eligible revisions, one SQL `document_revision_id IN
  (union)` filter over the whole corpus BEFORE ranking/LIMIT, fail closed
  if any document has an integrity error.
- **Metrics:** required_fact_coverage@k, all_required@k, complete_chain,
  MRR, nDCG, authority-leakage (must be 0), evidence-document diversity,
  solved/partial/failed, latencies. Expect: Vector **solves** direct/
  shallow and **partially** retrieves deep chains (misses the intermediate
  hops the query never names, out-ranked by the adjacent chunk). Report
  honestly.
- **Freeze a fairness contract** for the future graph comparison: same
  docs/chunks/resolver/as_of/questions/required+forbidden/top-K/provenance;
  no question-specific precomputed path; no eval-truth access during
  projection; every future node/edge must cite existing chunk ids;
  authority filtering before traversal for the graph side too.

**Pitfalls we hit — avoid:** hardcoding chunk ids in the contract (resolve
by passage at runtime); top_k >= eligible-corpus-size (makes multi-hop
trivially "solved" and hides the real gap); putting the adjacent chain in
the same chunk as a real fact (keep it a separate document so provenance is
clean); a substring-based "no eval truth" test (use AST).

---

## 7. Stage D — Evidence-Backed Graph + Vector-vs-Graph (refined)

- **Verify frozen inputs first** (source sha, revision ids, chunk ids,
  content hashes via index hash, corpus doc ids). Fail before building if
  anything differs. Do not rechunk.
- **Narrow relationship extractor** (one interface, two impls — no plugin
  framework): a deterministic `FakeRelationshipExtractor` (a rule-based
  parser of the chunk text, for tests) and an `OpenAIRelationshipExtractor`
  (strict JSON-schema output; records model, prompt version + sha,
  temperature, request hash, response hash, tokens, latency, cost,
  failures). Input is ONLY chunk text + lineage + provenance — never the
  fact contract or questions. Output: entities (name, type, aliases) +
  relationships (subject, predicate, object, `supporting_text`). Rules:
  only explicitly-stated relationships; preserve identifiers exactly;
  `supporting_text` must be an exact substring (reject otherwise); reject
  an edge whose subject/object is not present in the supporting_text.
- **Graph model:** `GraphNode` (node_id from normalized name, type,
  canonical name, aliases). `GraphEdgeAssertion` is **revision-scoped**:
  subject/predicate/object node ids + logical_document_id +
  document_revision_id + supporting_chunk_id + supporting_content_sha256 +
  supporting_text + full provenance + extraction_run_id. **Store NO
  is_current/latest/effective/superseded flag, NO question id, NO expected
  path, NO answer.** The same relationship from a current vs a historical
  chunk is TWO distinct assertions — never merged into one timeless edge.
  Every edge cites an existing chunk. Apply the entity-normalization rule
  (strip type-word prefixes uniformly; never merge distinct identifiers).
- **Persistence:** isolated Postgres tables (node/edge/extraction_run). No
  Neo4j. In-memory store for tests. Record node/edge/evidence counts, a
  graph payload hash, storage estimate, build latency, extraction
  tokens/cost.
- **Graph build never reads eval truth.** A SEPARATE evaluator (after
  construction) measures build accuracy vs the facts: expected-fact edge
  recall, extracted-edge precision, missing facts, unsupported edges,
  duplicate assertions, provenance completeness, edges with invalid chunk,
  **entity-normalization collisions**. Never repair an edge using
  benchmark truth.
- **Authority-aware graph retriever:** resolve each doc, fail closed, union
  eligible revisions, load ONLY eligible edge assertions (filter before
  traversal), seed by exact/normalized alias match against the query
  (never the expected chain), BFS to a fixed hop cap (≤5) both directions
  preserving edge direction, rank supporting chunks by (hop distance,
  supporting-chunk similarity, id), return the frozen top-K unique chunks.
  Paths are metadata; only chunks are evidence. `no_seed_entity` outcome if
  no seed. Score with the SAME frozen Stage C scorer (import identity).
- **Compare** to the frozen Stage C Vector results (loaded, never rerun).

**Reference observation from the prior implementation (NOT acceptance
criteria):** Observed configuration — one real `gpt-*` extraction snapshot
(temperature 0), the deterministic perfect FakeRelationshipExtractor as
best-case, hop cap ≤5, the frozen Stage C scorer, this corpus and the
`sentence-transformers/all-MiniLM-L6-v2` embedding model. Under that
configuration the real graph build was imperfect (edge recall ≈0.8) and
non-deterministic; a single missed or inconsistently-named edge broke a
multi-hop chain, so real-graph retrieval improved nothing and regressed
several multi-hop questions, while only the perfect extractor improved the
deep endpoint questions. This is a **reproducibility reference, not a
target**: build the system honestly, report both the real snapshot and the
deterministic best-case, and if your numbers diverge, INVESTIGATE and
report the divergence — never change code or parameters merely to
reproduce this reference.

**Pitfalls we hit — avoid:** merging current/historical assertions;
normalization that either fails to connect ("Control C-88" vs "C-88") or
dangerously merges ("C-88" vs "C-88a"); ranking that ignores the mandated
order; committing a non-deterministic real run without labeling it a
snapshot; a scratch stray NUL byte in a source separator (use an explicit
separator char, not a bare space, if your editor injects control bytes).

---

## 8. Stage E — Hybrid Vector-Graph probe (refined)

- Compare exactly five frozen modes: **V** (frozen Vector), **G** (frozen
  simple Graph), **H0** (RRF fuse V + simple G), **H1** (H0 but the graph
  side traverses from EXPANDED seeds), **H2** (H1 but the graph side ranks
  bounded simple PATHS by query↔path-representation semantic similarity,
  not hop distance). Run G/H0/H1/H2 over TWO graph conditions: the frozen
  **real** graph snapshot (loaded, verified by payload hash — NOT
  re-extracted) and the deterministic **perfect** graph (verify recall/
  precision 1.0). V is common.
- **No query-time LLM.** Add a dependency-isolation test that no OpenAI
  import/class is reachable from query execution.
- One immutable global config in a contract (vector candidate multiplier,
  max vector seed chunks, semantic edge candidate count, max hops ≤5, max
  candidate paths/beam, RRF constant; final top-K only from the Stage C
  question contract) + the decision gates. No per-question tuning; no
  eval-truth hints. (Naming the target questions inside the *decision
  gates* is allowed — that's the gate criteria, not tuning.)
- **Edge semantic index** (isolated, in-memory + Postgres): embed
  `canonical subject + predicate + canonical object + supporting_text`;
  semantic search returns ONLY authority-eligible edges with the
  eligibility predicate applied **before** similarity + LIMIT.
- **Three seed providers:** explicit alias (from the query), Vector-chunk
  (authority-aware vector over a fixed candidate pool → the subject/object
  nodes of eligible edges supported by each candidate chunk; never infer an
  entity absent an edge), semantic-edge (top-N eligible semantic edges →
  their subject/object nodes). Dedup by node id, preserve ALL origins,
  support multiple seeds, retain full seed provenance.
- **Bounded simple paths:** no repeated node, ≤ max hops, fixed beam;
  derive the path representation from its OWN existing edges only; embed;
  rank by query↔path cosine (NOT hop distance). Track the node path during
  traversal (do NOT reconstruct node order from edges — that produces
  spurious repeats when the first edge is traversed backward).
- **RRF fusion**, one global constant, into exactly the frozen top-K unique
  chunks — **never a larger budget than V or G**. Each final chunk retains
  vector rank/score, graph rank/score, RRF contributions, final rank, seed
  sources, supporting paths + edges, authority label, full provenance.
- Score every mode with the SAME frozen Stage C scorer. Report the full
  ablation (V→G→H0→H1→H2 for real and perfect), hybrid metrics (seed counts
  by source, no-seed rate, seed-source contribution, semantic-edge hits,
  candidate path count, V/G overlap@k, only-V/only-G/both counts, embedding
  calls, zero query-time LLM), and the Q04/Q06/Q07 (deep chain), Q05/Q10
  (mid-chain), Q12 (unnamed-entity) highlights — without hardcoding their
  seeds/paths.
- **Decision gates (fixed order A→B→D→C, pre-declared):** A retain (real
  H2 improves ≥2 target complete-chains, 0 regressions, no Q12 regression,
  0 leakage, same K, no LLM, ≤2× latency); B defer (perfect H2 meets A but
  real does not); D do-not-retain-Graph-online (neither A nor B; real H2
  has no regressions but improves <2 targets, with the same hard-safety
  requirements); C close (none of A/B/D). Add a test proving gate B is
  reachable and is not shadowed by gate D.
- **Seed budget & saturation (7B.2a):** always retain every explicit-alias
  seed; RANK supplemental (Vector-chunk + semantic-edge) seed candidates by
  RRF over their two source ranks and keep only the global top
  `max_supplemental_seed_nodes`; report eligible-graph-node-count,
  supplemental-candidate/selected counts, total seeds, and the saturation
  ratio; FAIL qualification if supplemental seeds exceed 40% of eligible
  graph nodes (except when ≤4 eligible nodes).
- **Path generation (7B.2a):** enumerate ALL authority-eligible simple
  paths (no repeated node, ≤max_hops), failing explicitly past a 5000
  safety ceiling; embed and semantically rank EVERY enumerated path; apply
  `max_candidate_paths` ONLY after ranking. Report paths-enumerated,
  paths-retained, count-by-hop-length, count-by-originating-seed, and
  eligible-edge path coverage.
- **Measured run (7B.2a):** use isolated Postgres stores — a graph store,
  an edge-semantic index, and a pgvector candidate store whose SQL includes
  the eligible revision ids BEFORE `ORDER BY`/`LIMIT`. In-memory stores are
  for deterministic tests only; the real integration test must invoke the
  SAME persisted measured path.
- **Frozen G (7B.2a):** the real-graph G is the frozen prior per-question
  Graph result, loaded directly; when the embedding model matches, a rerun
  must reproduce the ranked (chunk_id, rank, score) tuples EXACTLY.
- **Timing/calls (7B.2a):** record query-embedding, authority-resolution,
  vector-candidate-store, semantic-edge-store, graph-load, traversal/path-
  enumeration, path-embedding, and fusion latencies separately; never
  double-count resolver latency; `query_time_embedding_calls` counts the
  initial query embedding plus all path-embedding batches.

**Reference observation from the prior implementation (NOT acceptance
criteria):** Observed configuration — equal-weight RRF with one global
constant; every explicit-alias seed retained plus at most 4 RRF-ranked
supplemental seeds; ALL eligible simple paths enumerated and semantically
ranked before truncation; the frozen per-question top-K budget; no
query-time LLM; this corpus and the `all-MiniLM-L6-v2` model. Under that
configuration the prior run reached **gate D** (do not retain Graph in the
online retrieval path): hybrid rescued a bad graph up to Vector and, on
the perfect graph, mixing the fixed Vector ranking into a complete graph
chain under the shared budget diluted the gain; semantic seeding/path
ranking added nothing over plain fusion. Do NOT treat "gate D" as the
required answer — the same run's perfect-graph H0 raised Q06 0.80→1.00, so
graph structure CAN help within budget. Report whichever gate your honest
run reaches and explain it. For the latency gate, compare against the
**frozen Vector total latency**, not a resolver-only recompute (or the
ratio is meaninglessly inflated on a tiny corpus).

**Pitfalls we hit — avoid:** giving hybrid a larger final budget;
reconstructing path node order from edges (repeats a node); a latency
baseline that excludes vector-search time; forbidding question ids
*everywhere* in the probe contract (they legitimately appear in the
decision-gate criteria — forbid them only outside the gates, and forbid
eval-truth tokens everywhere); a stale Postgres schema flag after dropping
tables in a re-run cleanup (reset the "schema ready" flag, and delete the
corpus's own registry rows before re-running authority setup on a shared
registry).

---

## 9. Testing & determinism checklist (every stage)

- Deterministic fake-provider unit + integration tests (no network).
- One skippable real integration test (Postgres and/or sentence-transformers
  and/or OpenAI) that skips with the exact reason when infra is missing.
- Authority: zero leakage; empty eligible set → zero results; ineligible
  strongest match never appears (adversarial store test).
- Provenance completeness on every hit; only source chunks are evidence.
- No eval-truth read in ingestion/retrieval/extraction/seed/path/fusion
  (AST test). Frozen scorer reused (import-identity test). No frozen stage
  modified (git-diff test).
- Determinism: regenerate fixtures → identical hashes; re-run → identical
  decision/metrics.
- **No test asserts the "good" outcome** (vector<graph, or hybrid>vector).

---

## 10. Deliverables per stage

Per stage: the isolated package, an isolated Postgres schema, a JSON
contract where applicable, a runner script (real + `--fake`), tests,
committed `reports/*.{json,md}` (audit-complete), gitignored regenerable
`artifacts/`, and a short **decision/findings doc** for stages D and E.
Maintain a single status table (stage, scope, deliverables, tests,
findings) and a consolidated findings/limitations doc.

**Reference observations from the prior implementation (read AFTER you
have your own results — never as a target):** For each prior finding
below, the exact configuration under which it was observed is stated; each
is a reproducibility reference, not acceptance criteria; divergent results
must be investigated and reported honestly; and code/parameters must never
be changed merely to reproduce the reference.

- *Vector vs Graph (Stage D config: one real temperature-0 extraction
  snapshot; perfect FakeRelationshipExtractor best-case; hop cap ≤5; frozen
  Stage C scorer; this corpus; all-MiniLM-L6-v2):* real graph regressed
  several multi-hop questions; only the perfect graph improved deep
  endpoints.
- *Hybrid (Stage E / 7B.2a config: equal-weight RRF, ≤4 RRF-ranked
  supplemental seeds, all-paths-before-ranking, frozen per-question top-K,
  no query-time LLM, this corpus, all-MiniLM-L6-v2):* reached gate D — but
  perfect-graph H0 improved Q06 complete-chain 0.80→1.00, so graph
  structure can help within budget.

Do NOT re-litigate a predetermined conclusion. Build the system to the
contract, run it honestly, and let the pre-declared gates decide. The
exact, machine-readable fixtures/identities/timelines/scenarios/facts/
questions and the corrected 7B.2a algorithm contract + gates required to
reproduce these references are in **Appendix A** (`docs/DEVIN_REBUILD_APPENDICES.json`).
