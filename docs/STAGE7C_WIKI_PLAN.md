# Stage 7C Plan — Source-Backed Navigational Wiki Projection

> **Status: PLAN ONLY — pending owner review and approval.** No code, tables,
> fixtures, or frozen stages have been created or modified for Stage 7C. This
> document is the implementation/benchmark plan requested for review.
>
> **Predecessor context:** Stage 7B.2a is **completed and frozen** at Gate D
> ("Do not retain Graph in the online retrieval path; navigation or offline
> relationship analysis remains a separate, unevaluated use case"). Stage 7C
> does **not** reopen Graph retrieval — no Graph nodes/edges, extractor, router,
> query planner, path ranker, Neo4j, or traversal experiment.

---

## 0. Grounding facts (verified in the repo, read-only)

- **`CanonicalChunk`** (`chunking/model.py:255`) already carries everything a
  Wiki page needs: `chunk_id`, `logical_document_id`, `document_revision_id`,
  `source_document_sha256`, `version_label`, `revision_number`, `chunk_index`,
  `chunk_type`, `unit_indices`, `heading_path`, `heading_source_element_ids/refs`,
  `source_element_ids`, `annotation_ids`, `source_refs`, and — critically —
  **three separated text fields**: `source_text`, `model_derived_text`,
  `retrieval_text`. The source/model separation the plan demands (§8) is already
  a first-class property.
- **`IdentifierAnnotation`** (`canonical/annotations.py:33`): `raw_text`,
  `normalized_value`, `target_ref`, `start_char/end_char`, `derivation`. The
  deterministic identifier-anchor source, linked to chunks via
  `CanonicalChunk.annotation_ids`.
- **`identifiers_in()`** (`graph_retrieval_benchmark/model.py:58`) with regex
  `\b([A-Za-z]{1,6}-\d+[A-Za-z]?)\b` uppercased → `C-88` normalizes to `"C-88"`,
  `C-88a` to `"C-88A"`. Exact primitive that already protects the **C-88 vs
  C-88a boundary**. *(It lives in the graph package; §5 forbids depending on
  Graph artifacts, so 7C lifts this ~4-line regex into a neutral module rather
  than importing the graph package.)*
- **Resolver** (`revision_authority/resolver.py`): `resolve_query_scope(...) →
  QueryResolutionResult{ eligible_revision_ids, authority_labels }` with
  `RevisionAuthorityLabel{publication_status, derived_state}`;
  `derived_state ∈ {effective, approved_future, superseded, draft,
  under_review, withdrawn}`. Authority is already **query-time and dynamic** —
  no stored "current" flag. Exactly §11's model.
- **Authority-first pgvector pattern** exists in
  `revision_search_benchmark/pgvector_store.py`,
  `cross_document_benchmark/pgvector_store.py`, and 7B.2a's
  `vector_candidate_store.py`/`edge_index.py`: SQL `document_revision_id IN (:ids)`
  in the **same** statement as `ORDER BY embedding <=> :q LIMIT :k`. Reusable.
- **Frozen scorer**: `cross_document_benchmark/benchmark_runner._evaluate_question`
  (the Stage 7B.0 evaluator, reused by 7B.2a via import identity). W must reuse
  it unchanged.
- **Embeddings**: `RevisionVectorRecord{embedding}` + `cosine_similarity`
  (`revision_search_benchmark/store.py`); `SentenceTransformerEmbeddingProvider` /
  `FakeEmbeddingProvider` (`retrieval_baseline/embeddings.py`).
- **Corpus**: 6 logical docs / 11 revisions / 15 facts / 12 questions; exact
  source text already extracted in `docs/DEVIN_REBUILD_APPENDICES.json`
  (`G_fixture_source_text`).

---

## 1. Owner's briefing

**Business question.** Can a *deterministic, source-backed Wiki projection*
complement authority-aware Vector search with useful, **inspectable navigation
and lineage exploration** — without Graph construction, without a query-time
LLM, and without Wiki pages becoming a second source of enterprise truth?

**Corpus & worked example.** The current chain is distributed across five
documents:

```
APP-224510  --supports-->  Payment Settlement   (APP-PORTFOLIO rev2)
Payment Settlement  --is governed by-->  Obligation O-31   (SERVICE-CATALOGUE rev1)
Obligation O-31  --is satisfied by-->  Control C-88   (OBLIGATION-REGISTER rev2)
Control C-88  --is implemented through-->  Procedure P-205   (CONTROL-LIBRARY / PROCEDURE-CATALOGUE)
```

**Expected user experience.** A user querying "APP-224510" lands on the
App-Portfolio source section, sees the exact anchor **Payment Settlement**,
follows it to the Service-Catalogue section that names **O-31**, follows
**O-31** to the Obligation section that names **C-88**, then **C-88 -> P-205** —
every hop being *"the same source-backed term appears in this other eligible
passage,"* never *"a verified relationship exists."* The relationship meaning
stays in the source sentence.

**Difference from Vector and Graph.**

| | Question answered | Unit | Authority | 7B result |
|---|---|---|---|---|
| **Vector** | Which source passages are semantically similar? | chunk | query-time filter | solved 9/12, partial Q04/Q06/Q07 |
| **Wiki** | How do I orient within, and move between, related source passages? | page/section/anchor | query-time filter | *(this stage)* |
| **Graph** | Which formal relationship path connects entities? | node/edge | — | **Gate D — not retained; do not reopen** |

The Wiki's value is **navigation + provenance orientation**, evaluated
*separately* from any retrieval effect.

---

## 2. Proposed Wiki data model (minimal)

All records are Pydantic models in a new isolated package
`src/ingestion_bench/wiki_projection/`. IDs and hashes are deterministic
SHA-256 over stable inputs (never random, never run-scoped).

- **`WikiRevisionPage`** (page type A, immutable, one per `document_revision_id`):
  `page_id = sha256(document_revision_id | projection_contract_version)`;
  `logical_document_id`, `document_revision_id`, `source_relative_path`,
  `source_document_sha256`, `revision_number`, `version_label`, ordered
  `heading_structure`, `section_ids[]`, `page_hash`. **No `current` flag.**
- **`WikiSection`** (source-backed): `section_id = sha256(document_revision_id |
  chunk_id)` (1:1 with a `CanonicalChunk` in the base design — see §12),
  `chunk_id`, `heading_path`, `source_text` (verbatim), `source_refs`
  (verbatim), `source_element_ids`, `content_sha256`, `anchor_ids[]`,
  `section_hash`. `model_derived_text` kept in a **separate, clearly-labelled**
  field, never merged into `source_text`.
- **`WikiAnchor`** (page type C backing): `anchor_id = sha256(anchor_kind |
  normalized_value)`; `anchor_kind ∈ {identifier, phrase, heading_title}`;
  `normalized_value`; `display_text`; `extraction_method`; `is_ambiguous`.
  Anchors are corpus-level identities; eligibility derives from postings at
  query time.
- **`AnchorPosting`** (anchor↔section occurrence): `anchor_id`, `section_id`,
  `document_revision_id`, `logical_document_id`, `char_span`, `source_ref`,
  `posting_hash`. Occurrence evidence, **never a relationship assertion.**
- **`WikiLink`** (typed): `link_id`, `from_ref`, `to_ref`, `link_type ∈
  {structural, exact_anchor, semantic_related}`, `provenance` (anchor_id /
  shared source_ref / cosine score), `is_authoritative_lineage = False`
  **always**. `semantic_related` links carry `classification = "advisory"`.
- **`WikiSectionEmbedding`** (only if a section ≠ a single chunk; §12): reuses
  the existing chunk embedding by default; a *new* payload is created only for
  aggregated sections, with its own `payload_sha256`, `embedding_model`, and
  rebuild policy.

The **logical-document / revision-history page (type B)** and the **authority
label on any page** are **query-time views**, not stored rows (see §4/§11).

---

## 3. Anchor-extraction contract (the crux)

Two deterministic, benchmark-truth-free lanes. Both read only
`CanonicalChunk.source_text`, `heading_path`, and `IdentifierAnnotation`s.
Neither reads facts, questions, expected chains, Graph nodes/edges, or hardcoded
entity names.

**Lane 1 — Identifier anchors (high precision).** For every chunk, take its
`IdentifierAnnotation`s with `derivation == "extracted"` (plus a lift of the
`identifiers_in` regex for defense-in-depth). `normalized_value` is the anchor
key; `char_span` from `start_char/end_char` is the provenance. Deterministically
yields **APP-224510, O-31, C-88, P-205** with exact spans. **Collision
protection:** the `identifiers_in` uppercase rule makes `C-88` / `C-88A`
distinct keys — a hard test asserts they never merge.

**Lane 2 — Conservative repeated-phrase anchors (needed for "Payment
Settlement").** Identifiers give 4 of the 5 chain anchors; the
APP-PORTFOLIO→SERVICE-CATALOGUE hop needs the business-service name **Payment
Settlement**, which is not an identifier. Exact deterministic rule:

- **Candidate span:** a maximal run of 2–4 tokens where every token is
  Capitalized (`^[A-Z][A-Za-z0-9&/-]*$`) or is an identifier token; from
  `source_text` and `heading_path`.
- **Stop-words:** reject if any token ∈ a fixed closed stop-list, or the whole
  span is a single common word.
- **Length:** 2 ≤ tokens ≤ 4; 3 ≤ chars ≤ 60.
- **Occurrence threshold:** normalized span must occur in **≥ 2 distinct chunks**
  *and* **≥ 2 distinct `logical_document_id`s** (cross-document requirement —
  this distinguishes a navigational anchor from incidental capitalization).
- **Provenance:** keep the exact `(chunk_id, char_span, source_ref)` of *each*
  occurrence as postings.
- **Normalization & collision:** key = casefold + single-space; a candidate
  colliding with an *identifier* key is dropped (identifiers win). Two display
  forms mapping to one key are flagged `is_ambiguous` and **not** silently
  merged into a lineage claim.
- **Ambiguity handling:** if a normalized phrase maps to postings whose sections
  contain disjoint identifier sets, flag `is_ambiguous=True` and mark its links
  `advisory` regardless of type.

**Worked discovery (frozen text, no truth read):** "Application APP-224510
supports the Payment Settlement business service." (APP-PORTFOLIO) and the
Service-Catalogue section naming "Payment Settlement … Obligation O-31" both
contain the capitalized 2-gram **Payment Settlement** in ≥2 documents → accepted
as a `phrase` anchor with postings in both. Combined with identifier anchors
O-31/C-88/P-205, the full APP-224510→P-205 chain becomes navigable **purely from
source repetition**, with zero benchmark-truth access.

**Known limitations:** the phrase rule is recall- and precision-limited by
capitalization conventions; it will miss lower-cased entities and over-generate
on boilerplate headings (mitigated by the cross-document ≥2 rule). It asserts
co-occurrence, not relationship. A **future optional lane** (documented,
**not implemented in 7C**): an external authoritative catalog/CMDB supplies the
anchor vocabulary, converting Lane 2 from "discovered" to "governed."

---

## 4. Authority model (build-time vs query-time)

- **Build-time (immutable):** parse → chunk → sections → anchors → postings →
  structural/exact-anchor links → optional semantic metadata. Produces
  **revision-scoped immutable** pages. Build **never** calls the resolver and
  stores **no** authority state.
- **Query-time (dynamic):** `intent + as_of_date → resolve_query_scope →
  eligible_revision_ids` → SQL `document_revision_id IN (:eligible)` filters
  eligible **sections, anchor postings, and links** *before* ranking/rendering →
  the type-B revision-history view and each page's authority label are computed
  from `authority_labels`.
- **Examples:** a *current* query on OBLIGATION-REGISTER shows rev2 (effective)
  and hides rev1 (superseded); a *historical* query surfaces rev1 with a
  `superseded/historical` label; *draft/comparison* intent changes the eligible
  set again — all over the **same immutable pages**. An authority activation
  changes only the eligible view; **no re-parse, re-chunk, re-embed, or
  page-hash change** (asserted by a hard test).

---

## 5. Retrieval design (Eval A: V vs W)

- **V** = frozen Stage 7B.0 authority-aware Vector chunk retrieval (loaded, not
  rerun).
- **W** = authority-aware semantic retrieval over **Wiki sections**: embed the
  query once (existing provider), SQL-filter sections by `document_revision_id
  IN (eligible)` **before** `ORDER BY cosine LIMIT k`, take top-K sections,
  **map each back to its unique originating `CanonicalChunk.chunk_id`**, dedupe
  preserving order, truncate to the **same final top-K** as V.
- **Embedding reuse (§12):** in the base design a section is 1:1 with a chunk,
  so **W reuses the existing chunk embedding directly — zero new model calls.**
  The only variable under test is whether *section context* (title/heading/anchor
  index prepended to the section representation) helps or hurts; if that variant
  is measured, it needs a **new section-representation embedding** with its own
  hash/manifest, run through the **same** provider. Recommendation: 7C.0 ships
  reuse-only W; the context-augmented W is an explicit, separately-hashed option.
- **Scoring:** convert W's chunk IDs into the Stage 7B.0 result shape and score
  with the **same frozen `_evaluate_question`**. No query-time LLM, **no
  link-following inside W** (navigation is Eval B).

---

## 6. Navigation design (Eval B: N_exact vs N_semantic)

- **Link graph** (built, immutable, then authority-filtered at query time):
  - `structural`: section ↔ its revision page; page ↔ revision-history view.
  - `exact_anchor`: section →(anchor)→ every other **eligible** section posting
    the same anchor.
  - `semantic_related` (advisory): section/page ↔ nearest by cosine over reused
    embeddings/centroids above a fixed threshold, **labelled advisory, never
    lineage**.
- **Navigator (deterministic, no LLM):** start at the **top retrieved W
  page/section**; BFS/greedy over eligible links; **click = one link traversal**;
  visit order deterministic (link_type priority `structural < exact_anchor <
  semantic_related`, then anchor/id, then section_id). Authority leakage along
  any traversed link is a hard failure.
- **Configurations:** `N_exact` = structural + exact_anchor only; `N_semantic` =
  `N_exact` + advisory semantic links. Measured **separately**.
- **Click budget:** one **global** budget declared before the run (proposed
  **6 clicks**; open question §14), never tuned per question.
- **Worked path (APP-224510 → P-205), N_exact:** land on APP-PORTFOLIO section →
  click `Payment Settlement` → SERVICE-CATALOGUE section → click `O-31` →
  OBLIGATION-REGISTER section → click `C-88` → CONTROL-LIBRARY section → click
  `P-205` → PROCEDURE-CATALOGUE section. 4 clicks ≤ budget, all source-backed
  exact anchors.

---

## 7. Benchmark contract

**Retrieval metrics (Eval A):** required-fact coverage@K,
all-required-retrieved@K, complete-chain represented, MRR, nDCG@K,
forbidden-fact hits, authority-leakage count, evidence-document diversity —
**all via the frozen 7B.0 evaluator**, W vs V, same K.

**Navigation metrics (Eval B, precise deterministic defs):**
required-source-section reachability; complete-chain navigability; min clicks to
each required fact; min clicks to complete evidence set; navigation success @
budget; authority leakage along reachable paths (must be 0); forbidden-fact
exposure; distractor branches encountered; exact-anchor vs semantic-link
contribution (marginal gain of N_semantic over N_exact); orphan-page rate;
broken-link rate; ambiguous-anchor rate; anchor-collision rate; eligible
page/section coverage; link-provenance completeness; navigation-path
explainability (every click cites an anchor_id/source_ref). Primary targets
**Q04/Q06/Q07**; builder/navigator never read their required facts or expected
paths — the evaluator maps required facts → sections **after** projection.

**Maintainability metrics:** the §13 ledger.
**Hard safety:** §15, as pass/fail preconditions on any retain gate.
**Immutable decision gates:** §14 (declared before the measured run).

---

## 8. Proposed repository changes (new package; no frozen edits)

New package `src/ingestion_bench/wiki_projection/` (all new):
`model.py`, `anchor_extractor.py` (lifts `identifiers_in` regex locally — no
graph import), `projection_builder.py`, `store.py` / `pg_store.py` (in-memory +
isolated Postgres, `IN (...)` before ranking — mirrors 7B.2a
`vector_candidate_store.py`), `retriever.py` (W), `navigator.py`
(N_exact/N_semantic), `evaluator.py` (navigation metrics; imports frozen 7B.0
`_evaluate_question` by identity for retrieval), `benchmark_runner.py`,
`report.py`, `config.py`, `renderers.py`.

New: `contracts/wiki_projection_v1.json` (immutable projection + anchor + gate
contract), `scripts/run_stage7c_wiki_probe.py` (`--fake`/`--in-memory` like
7B.2a), `tests/test_wiki_projection.py`.

**Reused read-only:** `canonical/*`, `chunking/*`, `adapters/docling_standard`
(5A), `revision_authority/*` (7R.1), the 7R.2 authority-first pattern, 7B.0
corpus/facts/questions + evaluator, `retrieval_baseline/embeddings.py`, existing
pgvector patterns. **Not modified:** any frozen stage, including all of
`graph_retrieval_benchmark/` and `hybrid_retrieval_benchmark/` (7B.2a frozen).

---

## 9. Database design

Isolated tables prefixed `edib_stage7c_`: `wiki_page`, `wiki_section` (incl.
`document_revision_id`, `chunk_id`, `content_sha256`, `section_hash`, indexed on
`document_revision_id`), `wiki_anchor`, `anchor_posting` (indexed on `anchor_id`,
`document_revision_id`), `wiki_link` (indexed on `from_ref`, `link_type`,
`document_revision_id`), and `wiki_section_embedding` **only if** aggregated
sections are used (`VECTOR(dim)`, indexed on `document_revision_id`).
**Authority filtering** is always `document_revision_id IN (:eligible)` in the
same statement as ranking/LIMIT. **Incremental regeneration:** IDs/hashes derive
from `(document_revision_id, content)`, so rebuilding one revision touches only
its pages/sections/postings/embeddings + the anchor/semantic links incident to
them; unrelated hashes are byte-stable (asserted).

---

## 10. Test plan

- **Unit:** anchor extractor (identifier + phrase rules, stop-words, length,
  cross-doc threshold), hash/ID determinism, page/section/link builders.
- **Determinism:** rebuild from same frozen inputs → identical hashes; two runs →
  identical W results and navigation metrics.
- **Truth-isolation (AST + runtime):** builder/retriever/navigator never
  reference `required_fact_ids`, `forbidden_fact_ids`,
  `expected_relationship_chain`, question text, or any
  `graph_retrieval_benchmark`/`hybrid_retrieval_benchmark` symbol.
- **Authority:** empty eligible → zero sections/links; ineligible strongest
  match never surfaces (adversarial store test); current/historical/draft
  produce different eligible views over identical page hashes.
- **Collision:** C-88 vs C-88a never merge (anchor + posting level).
- **Incremental & immutability:** change one revision → only its artifacts
  rebuild; authority switch → eligible view changes, page/section hashes
  unchanged.
- **Real integration (skippable):** real sentence-transformers + isolated
  Postgres, full W + navigation over the persisted path.
- **Navigation eval:** reachability/click metrics on Q04/Q06/Q07 with truth read
  only post-projection.
- No test asserts W>V or that navigation must succeed.

---

## 11. Reports & audit artifacts

`reports/stage7c_wiki_{results.json, scorecard.md}`;
`docs/STAGE7C_WIKI_DECISION.md`; rendered **sample pages** (Markdown, provenance
panels) for the APP-224510→P-205 walk; **page/link manifests** (counts + payload
hashes); the **cost-and-value ledger** (§13); `artifacts/stage7c/` (gitignored,
regenerable). Every displayed sentence resolves to ≥1 `chunk_id`; source-derived
and model-derived content rendered in separate labelled blocks.

---

## 12. Risks & stopping conditions

- **Wiki-becomes-Graph:** if exact-anchor links get treated as lineage, or the
  navigator scores "relationship strength," stop — links stay "same term appears
  here," `is_authoritative_lineage=False`.
- **Anchor extraction fails:** if Lane 2 can't surface Payment-Settlement-class
  anchors without truth (or over-generates noise), navigation collapses — a
  legitimate **Gate C** outcome, not a reason to hardcode entities.
- **Semantic links mislead:** if navigability depends mainly on advisory
  semantic links (N_semantic ≫ N_exact but N_exact ≈ 0), the capability isn't
  source-backed → do not claim navigation value.
- **Explicit stop conditions:** any hard-safety failure; provenance
  incompleteness; benchmark-truth leakage into build/retrieval; C-88/C-88a
  merge; nondeterministic rebuild; or ledger burden disproportionate to measured
  value.

---

## 13. Cost-and-value ledger (maintainability)

A measured table: new modules; new tables; page/section/anchor/posting/link
counts; build time; index time; warm query latency (V vs W vs navigation);
storage footprint; **model calls & $ (target: 0 new for base W)**; deterministic
rebuild time; **change fan-out** for one revision change vs one authority-state
change; count of persisted derived artifacts; operational dependencies; recurring
maintenance; diagnostic difficulty; stale-page/stale-link risk. Effort is an
**honest relative classification** (e.g., "materially below the Graph/Hybrid
path: no extractor, no edge store, no traversal, reuses embeddings"), not
invented person-days. Includes the incremental-change and authority-switch tests
as ledger evidence.

---

## 14. Proposed decision gates (immutable, no required outcome)

- **Gate A — Retain Wiki semantic search + navigation:** all hard-safety pass;
  W improves retrieval on **≥2 of Q04/Q06/Q07** with **zero regressions** vs V
  on the rest; **same final K**; acceptable warm latency; **and** navigation
  adds measurable reachability.
- **Gate B — Retain Wiki as a navigation complement:** all hard-safety pass; W
  does **not** materially beat V but does **not** regress it; **N_exact** gives
  repeatable complete-chain navigation improvement on **≥2 of Q04/Q06/Q07**
  within the fixed click budget; achieved with **no Graph, no query-time LLM**;
  and maintenance burden materially below the Graph/Hybrid path.
- **Gate C — Do not retain Wiki:** neither retrieval nor navigation shows
  meaningful value; or navigability depends mainly on advisory semantic links;
  or source/authority/provenance safety can't be maintained; or burden is
  disproportionate.

Evaluated in a fixed order (propose **A → B → C**), declared before the run;
retrieval value and navigation value kept distinct.

---

## 15. Hard safety requirements

Any retained Wiki mode must demonstrate: zero authority leakage; zero invalid
source references; complete section-level provenance; no unsupported factual
text; deterministic page/link generation; no benchmark-truth access during build
or retrieval; no Graph package/artifact dependency; no query-time LLM; same final
source-evidence K for retrieval comparison; explicit "advisory" labelling of
semantic links; revision-scoped immutable source pages; no C-88/C-88a false
merge. No mode failing a hard-safety condition may satisfy a retain gate.

---

## 16. Proposed stage decomposition & freeze boundary

- **Stage 7C.0 — Projection qualification.** Build pages/sections/anchors/
  postings/links deterministically; prove **hard safety** (full provenance, zero
  benchmark-truth access, C-88/C-88a separation, deterministic + immutable
  rebuilds, correct authority views, no Graph dependency). Produce projection
  manifests + rendered sample pages + build-side ledger numbers.
  **Freeze the projection contract + builder here.**
- **Stage 7C.1 — Retrieval & navigation comparison.** Read the frozen 7C.0
  projection **read-only**; run V vs W and N_exact vs N_semantic; compute all
  metrics + query-side ledger; apply the gates; write the decision record.
- **Freeze boundary:** 7C.1 may not change the projection, anchor rules,
  page/link hashes, or embeddings; it only queries and measures — the same
  7B.0→7B.2a discipline.

---

## 17. Scope exclusions (not planned or implemented in 7C)

Graph nodes/edges/traversal; relationship extraction; query decomposition;
query-planning LLM; retrieval router; answer generation; ADK; agent workflows;
LLM-written persistent Wiki articles; manually curated benchmark-specific pages;
ontology expansion; rerankers; Neo4j; UI framework; Wiki editing/approval
workflow; vision processing; vendor-native ingestion; final direct-LLM
benchmark. (The final direct-LLM and provider-managed retrieval baselines remain
on the overall POC roadmap but are out of Stage 7C scope.)

---

## 18. Open questions requiring owner approval before implementation

1. **Click budget** — propose a global **6**; acceptable, or a different
   value/derivation?
2. **Section granularity** — base design uses **section == source chunk**
   (maximizes embedding reuse, zero new model calls). Approve, or heading-grouped
   sections (which need new, separately-hashed embeddings)?
3. **Context-augmented W** — ship reuse-only W in 7C.0 and treat
   "title/heading/anchor-prefixed section embedding" as a separately-measured
   option in 7C.1? Or exclude it for now?
4. **Phrase-anchor lane scope** — is Lane 2 in-scope for 7C.0, or should 7C.0
   ship identifier anchors only and gate Lane 2 as an option (it carries the most
   risk)?
5. **"Reaching a required source section"** — define as the required **chunk_id**
   appearing in a navigated section (assumption). Confirm.
6. **Advisory semantic-link threshold** — fixed cosine cutoff vs top-N per page;
   and should N_semantic count toward a retain gate at all, or be reported as
   advisory-only evidence?
7. **`identifiers_in` reuse** — approve lifting the ~4-line regex into a neutral
   module to avoid importing the frozen graph package?

---

*Plan only. No code, tables, fixtures, or frozen stages created or modified.
Awaiting review and the §14/§18 decisions before any Stage 7C.0 work.*
