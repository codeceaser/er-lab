# Stage 7C Plan (Revision 3) — Deterministic Wiki Control (W0) and Bounded, Auditable LLM-Assisted Evidence Wiki (W1)

> **Status: PLAN ONLY — pending owner review and approval.** No code, tables,
> fixtures, embeddings, or LLM calls have been created, run, or modified for
> Stage 7C. No frozen stage has been touched.
>
> **Revision history.** R1 ("Source-Backed Navigational Wiki Projection")
> defined `WikiSection` ≈ 1:1 with `CanonicalChunk` and reused the same chunk
> embeddings — making Wiki retrieval the same computation as Vector retrieval in
> a different wrapper. R2 reclassified that work as a control (**W0**) and
> introduced one bounded LLM-compiled evidence Wiki (**W1**). **R3 (this
> revision)** corrects R2's remaining overclaims and cuts its surface: the
> compilation unit becomes the facet, page identity becomes fully deterministic
> and shared between W0 and W1, links become derived rather than invented,
> summaries leave the embedding payload, retrieval bounds become derived rather
> than picked, summary correctness stops being asserted "by construction", and a
> hard qualification gate now stands between compilation and retrieval.
>
> **Predecessor context.** Stage 7B.2a is **completed and frozen at Gate D**
> ("do not retain Graph in the online retrieval path"). Stage 7C does not reopen
> it. W1 **must not** consume Graph nodes, edges, aliases, paths, extraction
> output, H0/H1/H2, traversal, path ranking, RRF fusion, query planning, Neo4j,
> or any Graph benchmark contract or report at build or query time. W1 derives
> independently from the same frozen `CanonicalChunk`s. *(§1.3 cites the frozen
> 7B decision **document** to state W1's prior honestly; that is a documentation
> reference, not a runtime dependency.)*

---

## 0. Grounding facts (verified in the repo, read-only)

**Canonical layer**

- **`CanonicalChunk`** (`chunking/model.py:255`) carries `chunk_id`,
  `logical_document_id`, `document_revision_id`, `source_document_sha256`,
  `version_label`, `revision_number`, `chunk_index`, `chunk_type`,
  `unit_indices`, `heading_path`, `heading_source_element_ids/refs`,
  `source_element_ids`, `annotation_ids`, `source_refs`, and — critically —
  **three separated text fields**: `source_text`, `model_derived_text`,
  `retrieval_text`. The source-vs-model separation this plan requires is already
  a first-class property of the canonical model.
- **`IdentifierAnnotation`** (`canonical/annotations.py:33`): `raw_text`,
  `normalized_value`, `target_ref`, `start_char/end_char`, `derivation`.
- **`identifiers_in()`** (`graph_retrieval_benchmark/model.py:58`), regex
  `\b([A-Za-z]{1,6}-\d+[A-Za-z]?)\b` uppercased: `C-88` → `"C-88"`, `C-88a` →
  `"C-88A"`. Protects the **C-88 / C-88a boundary**. It lives in the frozen
  graph package, so 7C **lifts this ~4-line regex into a neutral module** rather
  than importing that package (**Q9**).

**Authority layer**

- **Resolver** (`revision_authority/resolver.py:150`): `resolve_query_scope(...)
  → QueryResolutionResult{eligible_revision_ids, authority_labels}`
  (`:55`, `:77`); `derived_state ∈ {effective, approved_future, superseded,
  draft, under_review, withdrawn}`. **Authority is query-time and dynamic —
  there is no stored `current` flag anywhere in the repo.**
- **Authority-first pgvector pattern** (`revision_search_benchmark/`,
  `cross_document_benchmark/`, 7B.2a `vector_candidate_store.py`): SQL
  `document_revision_id IN (:ids)` in the **same statement** as
  `ORDER BY embedding <=> :q LIMIT :k`.

**Evaluation layer**

- **Frozen scorer**: `cross_document_benchmark/benchmark_runner._evaluate_question`
  (Stage 7B.0 evaluator, reused by 7B.2a via import identity). V, W0 and W1 are
  all scored by this, unchanged.
- **Corpus**: 6 logical documents / 11 revisions / 15 frozen facts / 12
  questions; exact source text in `docs/DEVIN_REBUILD_APPENDICES.json`.

**Embedding layer**

- `EmbeddingProvider`, `SentenceTransformerEmbeddingProvider`,
  `FakeEmbeddingProvider` (`retrieval_baseline/embeddings.py:31,37,73`).
  **Stage 7C introduces no new embedding model and no reranker.**

**LLM layer — the existing precedent W1 follows**

Stage 7A.2's `answer_baseline/` is a working bounded, audited, mechanically
validated model call. W1 reuses its *shape*, not its code path:
`answer_generator.py:152` (lazy client, strict `json_schema` output, usage
capture); `config.py:23,32` (one configured model, `temperature = 0`, plus the
in-repo comment that this is the lowest-variance setting available and **not a
determinism guarantee** — the direct justification for §8F);
`config.py:38,44` (`estimate_cost_usd()`, returning `None` rather than a
fabricated number); `prompt.py:23,106` (`PROMPT_VERSION`, `prompt_sha256()`);
`validation.py:19,99` and `model.py:42,67` (mechanical non-LLM validation of
model claims against cited chunks).

**Consequence:** W1 needs no new provider, SDK, cost model, or determinism
story — only a facet-level schema, a stricter validator, and authority-aware
assembly.

---

## 1. Owner's briefing

### 1.1 The business question

> **Can a bounded, auditable LLM compile source-backed evidence pages that
> improve semantic retrieval and navigability enough to justify the additional
> derived layer — while preserving original `CanonicalChunk`s as the sole
> authoritative evidence?**

This is a cost-justification question, not a feasibility question. The
measurable benefit of W1 must be weighed against ingestion-time model calls, a
validation subsystem, regeneration machinery, prompt/model versioning, derived
storage, and ongoing diagnostics.

### 1.2 Why R1's deterministic plan was insufficient

R1's two retrieval paths were the same computation:

```
V :  query embedding  →  chunk embeddings  →  top-K chunks
W :  query embedding  →  the same chunk embeddings, wrapped in
                          WikiSection rows  →  top-K sections  →  their chunks
```

W was *expected* to equal V, yet R1 placed it under a retrieval-improvement
gate. R1's navigation model asserted only co-occurrence (`section → shared
literal anchor → every section containing it`), which on an enterprise corpus
degrades to "here are 200 places this string appears" with no notion of which
relationship or direction the user asked about. That makes the deterministic
work a **control**, not a treatment.

### 1.3 W1's relationship to Graph — stated plainly

> **W1 uses the same class of artifact as Stage 7B's Graph: LLM-inferred,
> source-cited relationships extracted from the same frozen chunks. Stage 7C
> does not claim, and must not be read as claiming, that Wiki-style extraction
> is inherently more reliable than Graph extraction.**

W1's claims and 7B's edge assertions are produced by the same kind of process
and are subject to the same failure modes: missed relationships, inconsistent
phrasing, and inferred predicates that a citation cannot validate (§4.3). The
frozen 7B closure record states this limitation directly — *"The real graph is a
single non-deterministic LLM extraction snapshot; its missing/inconsistent edges
cap what any hybrid over it can recover"* — and that cap applies to W1 in equal
measure.

**The hypothesis under test is therefore narrow, and it is about consumption,
not extraction:**

> *Page-centric semantic retrieval over compiled evidence is more resilient to
> imperfect extraction than multi-hop traversal over extracted edges.*

The mechanism proposed for that resilience: a **missing or wrong edge breaks a
traversal path outright**, whereas a missing or wrong claim only perturbs a
page facet's embedding — the facet remains retrievable on its other accepted
claims, and the final evidence is the cited chunk set rather than a path.
Retrieval degrades to ranking rather than to failure.

**The prior this sets, honestly.** 7B's frozen record notes that its
*perfect-graph* H0 improved Q06 complete-chain coverage 0.80 → 1.00, while the
*real* extracted graph improved 0 of 3 target questions. Structure demonstrably
can help within budget; **LLM extraction quality was the binding constraint.**
W1 inherits that same constraint. If W1's compiled claims prove no better than
7B's extracted edges — which is the expected case, not the pessimistic one —
then W1's entire case rests on the resilience mechanism above. If that mechanism
does not deliver, the correct outcome is Gate C, and §9.2's qualification gate is
designed to surface a compilation-quality ceiling **before** any retrieval run is
allowed to obscure it.

### 1.4 The three modes

| | What it is | Retrieval unit | New model calls | Evaluated for |
|---|---|---|---|---|
| **V** | Frozen authority-aware Vector baseline over original chunks | chunk | 0 | Reference. Not rerun. |
| **W0** | Deterministic source Wiki **control** | chunk (via section) | 0 | Organization, provenance orientation, revision navigation, exact-anchor browsing, cost. **Not** semantic-retrieval improvement. |
| **W1** | Bounded LLM-assisted source-grounded **evidence Wiki** | page facet → cited chunks | ingestion-time only | Compilation quality, retrieval, navigation, page quality, repeatability, cost. |

**One** LLM Wiki variant. No W2, no compiler A/B, no prompt tournament (§12).

### 1.5 One complete worked example

The frozen corpus contains a chain across five documents:

```
APP-224510          --supports-->              Payment Settlement   (APP-PORTFOLIO rev2)
Payment Settlement  --is governed by-->        Obligation O-31      (SERVICE-CATALOGUE rev1)
Obligation O-31     --is satisfied by-->       Control C-88         (OBLIGATION-REGISTER rev2)
Control C-88        --is implemented through-->Procedure P-205      (CONTROL-LIBRARY / PROCEDURE-CATALOGUE)
```

**Under V.** Stage 7B.0 measured Q04/Q06/Q07 as *partial*: top-K is dominated by
chunks lexically near the query, and the far end of the chain (P-205) falls
outside K because no single chunk contains both ends.

**Under W0.** `Payment Settlement` (phrase) and `O-31`/`C-88`/`P-205`
(identifier) anchors are extracted deterministically. Semantic retrieval returns
what V returned — same embeddings. *Navigation* works: APP-PORTFOLIO → click
`Payment Settlement` → SERVICE-CATALOGUE → click `O-31` → OBLIGATION-REGISTER →
click `C-88` → CONTROL-LIBRARY → click `P-205` → PROCEDURE-CATALOGUE. Four
clicks, every hop source-backed — but each click means only *"this literal
string also appears here."*

**Under W1.** The compilation unit is the **facet** `(page_key,
document_revision_id)`. For `(IDENT:O-31, OBLIGATION-REGISTER:rev2)` the
compiler sees only OBLIGATION-REGISTER rev2 chunks containing `O-31`, and emits
(abridged, post-validation):

```json
{
  "page_key": "IDENT:O-31",
  "document_revision_id": "OBLIGATION-REGISTER:rev2",
  "display_title": "Obligation O-31",
  "page_type": "governed_identifier",
  "input_chunk_ids": ["chunk_obl_0003"],
  "aliases": [
    { "alias": "Obligation O-31", "supporting_chunk_ids": ["chunk_obl_0003"],
      "supporting_quotes": ["Obligation O-31"], "status": "supported" }
  ],
  "claims": [
    { "claim_id": "clm_obl_rev2_1", "subject": "O-31",
      "predicate": "is satisfied by", "object": "C-88",
      "claim_text": "Obligation O-31 is satisfied by Control C-88.",
      "supporting_chunk_ids": ["chunk_obl_0003"],
      "supporting_quotes": ["Obligation O-31 is satisfied by Control C-88"],
      "derivation": "model_derived", "validation_status": "accepted" }
  ],
  "summary_sentences": [
    { "sentence_id": "s1",
      "text": "O-31 is satisfied by Control C-88.",
      "supported_claim_ids": ["clm_obl_rev2_1"], "derivation": "model_derived" }
  ]
}
```

Note what is **absent**: no `related_page_candidates` (links are *derived*, §3.7),
no cross-revision evidence (structurally impossible — the compiler never saw
another revision), no page-level status field.

The link `IDENT:O-31 --is satisfied by--> IDENT:C-88` is then produced
**deterministically** from `clm_obl_rev2_1`, because `C-88` normalizes to an
existing page key. The **facet embedding** covers title + supported aliases +
accepted claim texts + revision headings + stable identifiers — **not** the
summary (§6.2). A sibling facet `(PHRASE:payment settlement,
SERVICE-CATALOGUE:rev1)` independently carries *"Payment Settlement is governed
by Obligation O-31"*. Retrieval walks: eligible facets → selected pages →
accepted eligible claims → **cited original chunks** → ranked by existing chunk
embeddings → **same final K as V**. The generated sentence is never evidence;
`chunk_obl_0003` is.

---

## 2. W0 — deterministic source Wiki control

### 2.1 Building blocks

All records are Pydantic models; all IDs and hashes are SHA-256 over stable
inputs (never random, never run-scoped). W0 makes **zero model calls**.

- **`WikiSection`** — a **view** over a `CanonicalChunk`, 1:1, not a stored
  table (§10.3): `section_id = sha256(document_revision_id | chunk_id)`,
  `heading_path`, verbatim `source_text` and `source_refs`, `content_sha256`,
  `anchor_ids[]`. `model_derived_text` stays in a separate labelled field and is
  **never merged into `source_text`**.
- **`WikiRevisionPage`** — likewise a derived view, one per
  `document_revision_id`: ordered heading structure over its sections.
  **No `current` flag.**
- **`WikiAnchor`** (stored): `anchor_id = sha256(anchor_kind |
  normalized_value)`; `anchor_kind ∈ {identifier, phrase, heading_title}`;
  `normalized_value`, `display_text`, `extraction_method`, `is_ambiguous`.
- **`AnchorPosting`** (stored): `anchor_id`, `chunk_id`, `document_revision_id`,
  `logical_document_id`, `char_span`, `source_ref`, `posting_hash`. Occurrence
  evidence, **never a relationship assertion**.
- **`WikiLink`**: `structural` and `exact_anchor` types for W0, derived from
  postings; `is_authoritative_lineage = False` **always**.

**Anchor extraction — two deterministic, benchmark-truth-free lanes**, reading
only `source_text`, `heading_path`, and `IdentifierAnnotation`s. Neither reads
facts, questions, expected chains, Graph output, or hardcoded entity names.

- **Lane 1 — identifier anchors.** `IdentifierAnnotation`s with
  `derivation == "extracted"`, plus the lifted `identifiers_in` regex for
  defense-in-depth. Yields **APP-224510, O-31, C-88, C-88A, P-205** with exact
  spans. The uppercase rule keeps **C-88 and C-88A distinct**; a hard test
  asserts they never merge.
- **Lane 2 — conservative repeated-phrase anchors.** Needed for *Payment
  Settlement*. Candidate = a maximal run of 2–4 tokens each matching
  `^[A-Z][A-Za-z0-9&/-]*$` or an identifier token, from `source_text` and
  `heading_path`; rejected if any token is in a fixed closed stop-list;
  2 ≤ tokens ≤ 4, 3 ≤ chars ≤ 60; the normalized span must occur in **≥2
  distinct chunks and ≥2 distinct `logical_document_id`s**. Key = casefold +
  single-space. A candidate colliding with an identifier key is dropped
  (identifiers win). Two display forms mapping to one key are flagged
  `is_ambiguous` and **never silently merged**. A phrase posting into sections
  with disjoint identifier sets is flagged ambiguous and its links downgraded to
  advisory.

**Build vs query time.** Build (chunks → anchors → postings → structural and
exact-anchor links) is immutable and revision-scoped; it **never** calls the
resolver and stores **no** authority state. Query time resolves `intent +
as_of_date → eligible_revision_ids` and filters via `document_revision_id IN
(:eligible)` **before** ranking or rendering. An authority activation changes
only the eligible view — **no re-parse, re-chunk, re-embed, or hash change**
(hard test).

### 2.2 W0 retrieval

Embed the query once; SQL-filter by `document_revision_id IN (:eligible)` before
`ORDER BY cosine LIMIT k`; map each section back to its originating `chunk_id`;
dedupe preserving order; truncate to the **same final K as V**; score with the
**frozen 7B.0 evaluator**.

> **Stated explicitly:** *W0 semantic retrieval is expected to be identical or
> nearly identical to V, because a W0 section is 1:1 with a chunk and reuses that
> chunk's existing embedding and retrieval payload. Any observed difference is
> expected to arise only from dedupe ordering or tie-breaking, not from a
> materially different semantic representation.*

W0 runs **as a control quantifying wrapper overhead**, and **no
retrieval-improvement gate is applied to it** (§9). W0 ≈ V is a successful
control outcome, not a failure.

### 2.3 W0 navigation, expected value, and limitations

`structural` (section ↔ revision page ↔ revision-history view) and
`exact_anchor` (section →(anchor)→ every other **eligible** section posting the
same anchor). Deterministic navigator, no LLM; one click = one traversal;
deterministic visit order; authority leakage along any traversed link is a hard
failure.

**Value:** human-readable organization; provenance orientation (every rendered
sentence resolves to a `chunk_id` and `source_ref`); revision-history
navigation; exact-anchor browsing; near-zero marginal cost.

**Limitations:** no semantic-retrieval improvement over V, by construction;
exact-anchor links assert co-occurrence only — no direction, no meaning; Lane 2
is bounded by capitalization convention (misses lower-cased entities,
over-generates on boilerplate headings, partly mitigated by the cross-document
≥2 rule); anchor fan-out is unbounded on a large corpus. A future *optional*
lane — an external catalog/CMDB supplying a governed anchor vocabulary — is
**documented, not implemented in 7C**.

---

## 3. W1 — bounded LLM-assisted source-grounded evidence Wiki

### 3.1 The compilation unit is the facet

> **One compilation = one `(page_key, document_revision_id)` facet.**

Each compilation receives **only** the chunks *from that revision* that contain
that page identity. It never sees another revision, another page, another
facet's output, benchmark truth, authority state, the resolver, or Graph output.

This makes three R2 properties **structural rather than merely validated**:

| Property | R2 | R3 |
|---|---|---|
| Claims are single-revision | a validation rule | the compiler cannot see another revision |
| No current/historical blending | a validation rule | structurally impossible |
| Facet embedding ↔ compilation unit | two concepts to keep aligned | one and the same unit |

Truth-isolation is enforced by AST tests over the compiler and prompt modules
*and* a runtime guard that fails the run if truth objects enter the compiler's
call path.

### 3.2 Page identity — deterministic, and identical for W0 and W1

> **Page identities are produced by the deterministic extractor of §2.1 and are
> byte-identical for W0 and W1.** The LLM does not create page identities.

| Kind | Source |
|---|---|
| `governed_identifier` | Lane 1 identifier anchors |
| `business_topic` | Lane 2 phrase anchors |

`page_key = "{kind}:{normalized_identity}"` — e.g. `IDENT:O-31`,
`PHRASE:payment settlement`.

**Model-proposed identities are excluded from page creation, embeddings,
retrieval, navigation, and every decision gate.** If the compiler names an
entity that is not an existing page key, that observation is written to the
**audit record only** (§10.3, `unresolved_identity_mentions`) as a recall
diagnostic for a possible future stage. It creates nothing and scores nothing.

Rationale: it makes the W0 and W1 page inventories identical, so the comparison
isolates exactly one variable — **page content representation** — and cannot be
confounded by a different page set. It also removes a whole class of
repeatability noise: run-to-run inventory churn (§8F) becomes impossible by
construction, so §8F measures content stability, which is what it is for.

### 3.3 Collision and ambiguity handling

| Case | Rule |
|---|---|
| **C-88 vs C-88a** | Distinct keys via the `identifiers_in` uppercase rule (`C-88` / `C-88A`). Hard test at identity, facet, claim, alias, link and embedding level. Never merged. |
| **Duplicate names** | If one normalized key resolves to occurrence sets with disjoint identifier context, pages are **kept separate** with a deterministic disambiguator from the sorted `logical_document_id` set; both flagged `identity_confidence = "ambiguous"`. |
| **Aliases** | `status ∈ {supported, uncertain}`. `supported` requires an exact quoted span. An `uncertain` alias may **never** merge pages and **never** satisfy an identifier-grounding check. |
| **Abbreviations** | Alias proposals; same rule. No expansion dictionary. |
| **Uncertain identity match** | Separate page, marked ambiguous. **Silent merging is a hard-safety failure.** |
| **Same phrase, different concept** | Detected as disjoint-identifier-context and split; if undetectable, flagged ambiguous and outgoing links downgraded to advisory. |

### 3.4 Claims

One atomic assertion per claim: `claim_id`, `subject`, `predicate`, `object`,
`claim_text`, `supporting_chunk_ids`, `supporting_quotes`,
`derivation = "model_derived"`, `validation_status ∈ {accepted, rejected,
uncertain}`. The facet's `document_revision_id` is the claim's revision — no
per-claim revision field is needed, because the compiler could not have seen
another one.

Multi-document *chains* remain fully expressible as several single-revision
claims across sibling facets, which is exactly how §1.5 represents the
APP-224510 → P-205 chain.

### 3.5 Summaries — presentation only

Sentence-level records: `summary_sentences: [{sentence_id, text,
supported_claim_ids, derivation}]`. Every sentence must reference ≥1 accepted
claim **on the same facet**.

> **Summaries are for presentation and rendering only. They are excluded from
> the W1 facet embedding payload (§6.2) and therefore have no effect on
> retrieval.**

Consequence: a summary defect degrades page quality (§8D) and fails the summary-
correctness criterion (§4.4, §9.2), but it can never silently move a retrieval
number. This also removes R2's circularity, in which a summary derived from
claims was embedded alongside those same claims.

### 3.6 Aliases

As §3.3. Aliases enter the embedding payload **only when `status ==
"supported"`** and only for that facet's revision.

### 3.7 Links — derived, not invented

> **The LLM is never asked to propose link targets or relationship labels.**
> Source-cited model-derived links are generated **deterministically from
> accepted claims**.

For each accepted claim, normalize `subject` and `object` with the same identity
normalization that produced page keys (§3.2). If an endpoint matches an existing
page key, emit a link record:

| Field | Value |
|---|---|
| `claim_id` | the originating accepted claim |
| `subject_page_key` | resolved subject page |
| `predicate` | the claim's predicate, verbatim |
| `object_page_key` | resolved object page |
| `source_citations` | the claim's `supporting_chunk_ids` + `supporting_quotes` |
| `document_revision_id` | the facet's revision |
| `traversal_direction` | `forward` (subject→object) or `inverse` (object→subject) |
| `is_authoritative_lineage` | `False`, always |

The `inverse` record is materialized so navigation can walk backwards; rendering
marks it explicitly as an inverse traversal and **never fabricates an inverse
predicate string**. An endpoint that resolves to no page key emits no link and
is counted as `unlinkable_claim_endpoint` — a reported recall diagnostic.

Two consequences, stated rather than glossed: link quality is now **bounded by
claim quality by construction**, so link precision is a *derived* measure rather
than an independent LLM output; and the compiler's output schema shrinks to
**aliases + claims + summary sentences**, which is the whole of what it is
trusted to produce.

### 3.8 What makes W1 "bounded"

One compiler, one prompt version, one model, one structured schema, strict
JSON-schema output mode, `temperature = 0`, no free prose as a primary persisted
field, no LLM-created page identities, no LLM-invented links, no query-time LLM,
no compiler-visible benchmark truth, no cross-facet context, and the hard
ceilings of §3.9.

### 3.9 Hard ceilings (input and output, per facet)

Declared before the run; **not** tunable per facet or per question.

| Ceiling | Proposed value |
|---|---|
| Input chunks per facet (`F_max`) | **12** |
| Input tokens per facet | **8,000** |
| Accepted + uncertain claims per facet | **20** |
| Aliases per facet | **8** |
| Summary sentences per facet | **5** |
| Output tokens per facet | **4,000** |
| Whole-run dollar ceiling | declared before the run (**Q6**) |

> **Breach behaviour: exceeding any input or output ceiling fails the facet, and
> a failed facet fails Stage 7C.1 qualification (§9.2).**
> There is **no batching, no map-reduce, no hierarchical summarization, no
> truncate-and-continue, and no ceiling raise mid-run.**

Rationale: if the corpus does not fit a bounded compiler, *that is the finding*.
Engineering around it inside the POC would silently convert "one bounded model
call per facet" into a multi-stage summarization pipeline with its own error
modes and its own cost curve — the exact complexity the stage exists to price.
A breach must surface as a qualification failure, not disappear into machinery.

---

## 4. Source-grounding and validation contract

Validation is **deterministic and non-LLM**, runs after the model returns
structured output, and is the only path by which anything becomes `accepted`.

### 4.1 Deterministic checks (all must pass for `accepted`)

1. Every `chunk_id` referenced exists.
2. Every referenced chunk is in **this facet's** declared input set — which,
   per §3.1, also proves the claim is confined to the facet's revision.
3. Every `supporting_quote` is an **exact substring** of the cited chunk's
   `source_text` (byte-exact after one declared whitespace normalization).
4. The facet's `document_revision_id` is valid and matches every cited chunk.
5. Every `source_ref` resolves.
6. Every identifier appearing in `claim_text`, `subject`, `object`, an alias, or
   a summary sentence — extracted with the lifted `identifiers_in` — occurs in
   the cited evidence, or is linked to a `supported` alias record. *(Primary
   hallucinated-identifier guard.)*
7. **C-88 and C-88A are not merged** at identity, facet, claim, alias, link or
   embedding level.
8. Every summary sentence references ≥1 `accepted` claim on the same facet
   (**reference validity only** — see §4.4).
9. Every derived link (§3.7) resolves to an existing page key and an accepted
   claim.
10. No unsupported factual field is persisted as `accepted`.
11. **No timeless status.** A closed status lexicon (`current`, `effective`,
    `in force`, `active`, `latest`, `now applies`, predicative `supersedes`, …)
    is rejected in `predicate` / `claim_text` / summary text unless it appears
    inside an exact quoted source span. The compiler may never emit a page-level
    status, currency or effectiveness field. *(Protects the repo-wide "no stored
    current flag" invariant.)*
12. **Duplicate and contradictory claims.** Normalize `(subject, predicate,
    object)`. Same triple within a facet → duplicate, deduped with both
    citations retained. Same `(subject, predicate)` with different `object`
    **within a facet** → `contradictory`; **both demoted to `uncertain`**,
    neither silently dropped, the pair reported. The same divergence *across*
    facets of different revisions is `revision_divergent` — expected evolution,
    both accepted, each revision-scoped.
13. All ceilings of §3.9 respected.
14. Rejected outputs and **the reason for each rejection** persisted for audit;
    nothing discarded silently.

### 4.2 Acceptance and rejection behaviour

`accepted` → persisted; eligible for the embedding payload, for supporting a
summary sentence, and for deriving links. `uncertain` → persisted and **rendered
as uncertain**; excluded from the embedding payload; may not support a summary
sentence or derive a link. `rejected` → persisted **in the audit record only**;
never in the page view, never embedded. A facet whose claims are all rejected is
persisted as an empty facet with its rejection ledger — never deleted, since
deletion would hide the failure mode from §8E.

### 4.3 Citation validity is not claim correctness

> **An exact-substring citation proves only that the cited passage exists and
> contains the quoted text. It does not prove that the model's inferred
> `predicate` accurately represents that passage.**

| Property | Definition | How measured |
|---|---|---|
| **Citation validity** | Cited chunk exists, is in facet scope, quote is an exact substring | **Deterministic**, 100% mechanical (§4.1.1–4.1.5) |
| **Claim correctness** | The `(subject, predicate, object)` faithfully represents the cited passage | **Not mechanically decidable.** Frozen-fact match **plus owner adjudication of every accepted claim** (§4.5) |

A run with 100% citation validity and poor claim correctness is a Gate C signal,
not a success.

### 4.4 Summary reference validity is not summary correctness

R2 asserted that a summary sentence mapping to accepted claim IDs made
unsupported summary statements impossible "by construction". **That was wrong,
and is corrected here.** Claim-ID mapping proves only that the sentence *points
at* accepted claims. It does not prove the sentence faithfully represents them:
a sentence can cite two valid claims and still overstate them, merge them into an
unsupported composite, invert a direction, or add a qualifier that appears in
neither.

| Property | Definition | How measured |
|---|---|---|
| **Summary reference validity** | Every sentence references ≥1 accepted claim on the same facet | **Deterministic** (§4.1.8) |
| **Summary correctness** | The sentence faithfully represents exactly those claims — no addition, overstatement, merge error, or direction inversion | **Not mechanically decidable.** **Owner adjudication of every summary sentence** (§4.5) |

Both are reported separately. Neither substitutes for the other.

### 4.5 Adjudication scope

The corpus is small — 6 documents, 11 revisions, and a facet count in the tens.
Sampling is therefore unnecessary and would only add variance:

> **Every accepted claim and every summary sentence is owner-adjudicated.**

Adjudication is performed on **Run 1 only** (§8F), blind to no label (the
adjudicator is judging correctness against cited source, not comparing modes),
recorded as `correct | incorrect | unverifiable` with a reason, and persisted in
the decision record. Adjudication happens **after** compilation and **before**
any retrieval run — it is an input to the §9.2 qualification gate.

### 4.6 Source vs model-derived separation

Persisted and rendered in separate labelled blocks. **A —
source-authoritative:** original `source_text`, `source_refs`, revision
identity, document provenance. **B — model-derived:** aliases, claims,
summaries, derived links and their predicates. B is auditable, versioned,
regenerable, replaceable, **never silently promoted to source truth, and never
sufficient evidence without its cited source chunks**. Any final answer or
benchmark fact resolves to A.

---

## 5. Authority and revision model

### 5.1 Design A — revision-scoped claim compilation (recommended)

Claims are compiled per facet and carry that facet's revision. The page **view**
is assembled at query time from facets whose revision is in
`eligible_revision_ids`. No query-time LLM.

- **Authority activation:** changes only which facets are visible. No
  recompilation, no re-embedding, no hash change.
- **Rebuild fan-out:** zero on authority change. On a source-revision change,
  only that revision's facets recompile.
- **Stale-page risk:** structurally low — nothing stored depends on authority
  state.
- **Hash behaviour:** facet hash is a function of (inputs, prompt version,
  model, contract version) only; stable across authority changes (hard test).
- **Historical/draft queries:** work by construction.
- **Summary validity:** solved by §3.5 sentence-level records plus deterministic
  authority-scoped composition — drop any sentence whose `supported_claim_ids`
  are not all eligible.

### 5.2 Design B — authority-snapshot page compilation (rejected)

Pages compiled against an explicit eligible-revision snapshot, snapshot hash
persisted, regeneration triggered by authority change.

- **Authority activation** invalidates every page whose snapshot included an
  affected revision → recompilation and re-embedding, i.e. **LLM calls fired by
  authority events**.
- **Rebuild fan-out** potentially large and hard to bound.
- **Stale-page risk** high and *silent*.
- **Hash behaviour** authority-dependent, breaking the "authority is query-time,
  never stored" invariant.
- **Historical/draft queries** need a snapshot per intent (combinatorial) or are
  unsupported.
- **Summary validity** better — natively fluent for one authority scope.

### 5.3 Recommendation and its honest cost

**Design A. Only Design A will be implemented.** B's sole advantage is a more
fluent holistic summary, bought with stored authority dependency, unbounded
rebuild fan-out, silent staleness, authority-dependent hashes, and model calls
triggered by authority events — and it contradicts a repo-wide invariant. Not a
trade worth making for prose fluency.

**Cost of A, stated plainly:** the eligible-scope summary is composed by
*filtering* sentences, not regenerating them. Under a narrower authority scope
the remaining summary can read as terse or disjointed, and it is never
re-smoothed (that needs a query-time LLM, excluded by §9.1). A page may render a
*shorter* summary under a narrower scope but **never** an unqualified mixture of
current and superseded claims. If every sentence is dropped, the page renders
"no summary available for this authority scope" rather than falling back to
unfiltered text. Because summaries are outside the embedding payload (§3.5),
this degradation affects presentation only, never retrieval.
Summary-degradation rate per intent is reported (§8D).

---

## 6. Embedding and retrieval design

**No new embedding model. No reranker.** Existing provider only.

### 6.1 Payloads

| Mode | Payload | New embeddings |
|---|---|---|
| **V** | existing `CanonicalChunk.retrieval_text` embedding | 0 |
| **W0** | the **same** chunk embedding (section == chunk); *not a materially new retrieval representation* (§2.2) | 0 |
| **W1** | facet payload (§6.2) | 1 per facet |

### 6.2 The W1 facet payload

One embedding per `(page_key, document_revision_id)` — i.e. **one per
compilation unit** — composed in a fixed declared order:

```
display_title
+ revision-supported aliases (status == "supported", sorted)
+ accepted claim_texts for this facet (sorted by claim_id)
+ revision headings for this facet's chunks
+ stable source identifiers occurring in this facet
```

> **Summary sentences are excluded from the payload** (§3.5). They are
> presentation output and must not influence retrieval — and embedding a summary
> derived from claims that are themselves in the payload would double-count the
> same content.

Every component is labelled `source_derived` or `model_derived` in the stored
payload manifest.

**Why facets rather than one page embedding.** A whole-page embedding mixes
claims from superseded and effective revisions into one vector, making page
*ranking* authority-blind so a page could be discovered largely on ineligible
content. Facets keyed by `document_revision_id` let the **existing
authority-first pattern** — `document_revision_id IN (:eligible)` in the same SQL
statement as `ORDER BY embedding <=> :q LIMIT :k` — apply unchanged. Page score =
max over eligible facets.

**Recorded with every W1 embedding:** payload text; payload SHA-256; facet
generation hash; compiler model identity; prompt version + SHA-256; embedding
model; embedding dimension; generation timestamp; source chunk IDs; source
revision ID; repeatability run ID (always Run 1 for the frozen representation,
§8F).

### 6.3 Regeneration policy

| Trigger | Recompile facet? | Re-embed? |
|---|---|---|
| Source revision changes | **Yes**, that revision's facets | Yes |
| An accepted claim changes | **Yes** (it is an output of compilation) | Yes |
| Compiler model changes | **Yes**, all facets | Yes |
| Compiler prompt changes | **Yes**, all facets | Yes |
| **Authority state changes only** | **No** | **No** — view-only (hard test) |

### 6.4 W1 retrieval flow

```
query
 → resolve_query_scope(intent, as_of_date) → eligible_revision_ids
 → SQL: facet_embedding WHERE document_revision_id IN (:eligible)
        ORDER BY embedding <=> :q                  -- eligible facets, ranked
 → group facets to pages, page score = max eligible facet score
 → select top P pages                              -- §6.5
 → collect accepted claims from those pages' eligible facets
 → union their supporting_chunk_ids → candidate chunk set
 → SCORE every candidate chunk against the query
   using the existing chunk embeddings              -- before any truncation
 → apply compute ceiling C to the SCORED, RANKED list
 → return top K original CanonicalChunks            -- same K as V
 → score with the frozen Stage 7B.0 evaluator
```

**No backfill.** If the page layer yields fewer than K candidate chunks, W1
returns fewer than K. Topping up from V would silently blend the two systems and
inflate W1's measured coverage. Short lists are a genuine property of the design
and are reported as such.

**Excluded:** query-time LLM, reranker, router, query decomposition, Graph
traversal, per-question tuning. Generated summaries and claim texts **never**
count as source evidence; only cited `CanonicalChunk`s do.

### 6.5 Bounds policy — derived, not picked

R2's `P_pages = 5` / `C = 50` were unjustified constants. R3 derives both from
declared benchmark parameters, so neither is a tuning knob.

**Page selection bound.** `P = K` — the final evidence budget.

*Justification:* W1's page layer exists to be **selective**. Permitting more
selected pages than final evidence slots removes that selectivity and degenerates
W1 toward "rank all eligible chunks", i.e. toward V — at which point the
comparison measures nothing. Tying P to K makes the bound scale with the
benchmark rather than with a hand-picked number, and it is declared before the
run.

**Candidate compute ceiling.** `C = P × F_max` (§3.9), i.e. `K × 12`.

*Justification:* a facet's accepted claims can cite at most the chunks that facet
was given, so P selected pages can cite at most `P × F_max` distinct chunks. C is
therefore a **provably non-binding compute ceiling on this corpus, not a
selection filter.** If it ever binds, that is a contract-breach event requiring
owner review — reported, never silently truncated.

**Scoring order.** Every candidate chunk is scored against the query **before**
any truncation; C truncates the *scored, ranked* list. Truncation can therefore
only ever remove the lowest-ranked candidates, never an unscored one.

**Reported per question** (all modes where applicable):

| Quantity | Meaning |
|---|---|
| `eligible_pages` | pages with ≥1 eligible facet after authority filtering |
| `selected_pages` | pages actually selected (≤ P) |
| `eligible_chunks` | distinct chunks cited by accepted claims on eligible facets |
| `candidate_chunks` | chunks carried into the final ranking (≤ C) |
| `page_saturation` | `selected_pages / eligible_pages` |
| `chunk_saturation` | `candidate_chunks / eligible_chunks` |
| `P_bound_hit`, `C_bound_hit` | whether either ceiling actually bound |
| `short_list` | whether fewer than K chunks were returned |

Saturation near 1.0 means the bound is not selecting — a signal that W1 is
degenerating toward V and that the retrieval comparison should be read with that
in mind.

---

## 7. Navigation design

### 7.1 Link types

| Type | Meaning | Determinism | Asserts a relationship? |
|---|---|---|---|
| `structural` | document / page / section hierarchy | deterministic | no |
| `exact_anchor` | the same literal source-backed anchor appears elsewhere | deterministic | **no** |
| `claim_derived` | derived deterministically from an accepted claim (§3.7), carrying predicate, citations and traversal direction | deterministic **given the claims**; the claims are model-derived | yes — but **model-derived, auditable, replaceable** |
| `advisory_semantic` | cosine-nearest eligible facets above a fixed threshold | deterministic given embeddings | **no** |

`is_authoritative_lineage = False` on **all** types, always. A `claim_derived`
link is **not** an authoritative registry edge, and cosine-nearest links are
**never** labelled lineage.

### 7.2 Configurations compared

```
N_W0       = structural + exact_anchor
N_W1       = structural + exact_anchor + claim_derived
N_advisory = N_W1 + advisory_semantic
```

`N_W0 ⊂ N_W1 ⊂ N_advisory` — a strict nesting, so each configuration's **marginal
contribution is directly measurable**: `N_W1 − N_W0` isolates the value of
claim-derived links over deterministic anchors, and `N_advisory − N_W1` isolates
the advisory contribution. Advisory links can therefore never be folded into the
source-backed result.

### 7.3 Branch prioritization — and its honest limit

Global click budget declared before the run (proposed **6**), never tuned per
question. One click = one traversal. Authority leakage along any traversed link
is a hard failure.

A **weak deterministic prioritizer** is available with no new model call:
outgoing links ordered by (a) cosine between the already-computed query embedding
and the target page's eligible facet embedding, then (b) lexical overlap between
the link's `predicate` and the query, then (c) link-type priority, then (d)
stable key order.

> **Stated as a limitation, not a capability:** *this is similarity ordering, not
> intent understanding.* It cannot reliably distinguish "which control satisfies
> O-31?" from "which procedure implements C-88?" when both targets are
> semantically close, and predicate matching is purely lexical — it models
> neither direction nor relation type. Where prioritization fails, the navigator
> degrades to deterministic breadth-first order, and **that degradation is
> reported in the navigation results, not concealed inside BFS.** Fixing it
> properly needs a query-planning LLM or a typed relation registry, both out of
> scope (§12).

---

## 8. Benchmark contract

Dimensions are kept separate and never averaged into a single score.

### 8.A Compilation quality (W1)

Measured against the frozen facts **only after compilation is complete**;
compiler never reads benchmark truth (AST tests + runtime guard).

Metrics: expected-fact recall in accepted claims; accepted-claim precision;
unsupported claim count; **citation validity** (deterministic); **claim
correctness** (frozen-fact match + owner adjudication of *every* accepted claim,
§4.5); omitted relationship count; entity identity accuracy; alias accuracy;
**false merge count (target 0)**; duplicate / `contradictory` / `revision_divergent`
counts; **summary reference validity** (deterministic); **summary correctness**
(owner-adjudicated, every sentence); derived-link precision and recall *(reported
as derived from claim quality, §3.7 — not an independent output)*;
`unlinkable_claim_endpoint` count; `unresolved_identity_mentions` count (audit
only, §3.2); provenance completeness; generation failures; ceiling breaches;
validation rejections by reason.

### 8.B Retrieval quality (V vs W0 vs W1)

Same questions; same intent and `as_of_date`; same eligible revisions; **same
final source-chunk K**; **same frozen Stage 7B.0 evaluator**; zero query-time
LLM; no per-question tuning.

Reported per mode and question: required-fact coverage@K; all-required-
retrieved@K; complete-chain represented; MRR; nDCG@K; forbidden-fact hits;
authority-leakage count (**must be 0**); evidence-document diversity;
solved/partial/failed; the §6.5 bounds and saturation table; and an explicit
**per-question gains and regressions** table (W1 vs V, W1 vs W0, W0 vs V).

**V is not rerun, rescored, or altered** — frozen Stage 7B.0 results and
evaluator loaded read-only, with a rerun-equality verification step only if exact
benchmark parity requires it (the discipline 7B.2a used for the frozen G
projection).

### 8.C Navigation quality (`N_W0` vs `N_W1` vs `N_advisory`)

Required-evidence reachability; complete-chain navigability; minimum clicks to
required evidence; branch count; irrelevant-destination count; ambiguity rate;
authority leakage (**must be 0**); forbidden-fact exposure; **marginal
contribution of each nesting level** (§7.2); navigation-path explainability
(every click cites an `anchor_id`, or a `claim_id` + `source_ref`);
prioritizer-degradation rate (§7.3). Primary targets Q04/Q06/Q07. Semantic
similarity alone is **never** treated as verified lineage.

### 8.D User-facing page quality

A fixed sample (proposed **6 pages**, selected deterministically by hash, never
cherry-picked), rendered for W0 and W1, presented **blind to mode label in
deterministic order**, scored 0–2 on: readability; ability to understand *why*
sources are connected; visibility of source vs model-derived content; citation
usability; revision clarity; exception/qualification preservation; usefulness to
a business user; usefulness to a downstream agent. Scored by the owner (**Q7**).
A deterministic mechanical proxy is reported alongside — citation density,
summary-degradation rate per intent — but **never substituted for the rubric**.

### 8.E Cost and maintainability

Implementation surface (modules, LOC, tables); compilation calls; input/output
tokens; **dollar cost** via the existing `estimate_cost_usd()` (returning `None`
rather than a fabricated figure for an unpriced model); build latency; retrieval
latency (V vs W0 vs W1, warm); storage; validation rejection rate; reprocessing
cost after a source change, after an authority change, and after a model/prompt
change (three separate numbers); output stability (§8F); debugging difficulty;
stale-page risk; operational dependencies.

> **Lower maintenance will not be claimed merely because pages are
> human-readable.** W1's ledger carries its compiler, prompt versioning,
> validator, adjudication effort, rejection triage, regeneration policy and model
> dependency as costs, compared honestly against V (near-zero marginal) and the
> frozen 7B Graph/Hybrid ledger.

Order-of-magnitude expectation, to be replaced by measurement and never quoted as
a result: tens of facets × a few thousand input tokens at `gpt-4o-mini` pricing →
well under one dollar per compilation run, ×3 runs for §8F.

### 8.F Repeatability

**N = 3** full compilation runs with identical model, prompt, source chunks,
configuration and authority scope, at `temperature = 0` — noting the repo's own
recorded caveat that this is the lowest-variance setting available and **not** a
determinism guarantee for a hosted model.

> **Run 1 is designated the primary frozen representation, before any run
> executes.** Runs 2 and 3 measure stability only. They are never used to
> replace, merge with, supplement, or improve Run 1. **Selecting the best-scoring
> run is prohibited** and would invalidate the experiment. The freeze record
> stores Run 1's facet hashes, and all retrieval, navigation, page-quality and
> adjudication work in 7C.2 reads Run 1 exclusively.

Measured across runs: claim-set stability (Jaccard over normalized
`(subject, predicate, object, sorted supporting_chunk_ids)`); citation stability;
alias stability; summary stability; derived-link stability; fact-recall variance;
unsupported-claim variance; token and latency variance. *Page identity stability
is not measured — it is 100% by construction (§3.2), and saying so is the point.*

**Textual summaries need not be byte-identical.** Structured accepted claims and
citations must meet declared thresholds — proposed: accepted-claim set pairwise
Jaccard **≥ 0.90**, citation sets on matched claims **≥ 0.95 exact**, false
merges **0 in every run**, ceiling breaches **0 in every run** (**Q5**).

---

## 9. Gates

### 9.1 Hard safety requirements (pass/fail preconditions on everything)

Original chunks remain the sole authoritative evidence; zero authority leakage;
zero invalid source references; complete claim-level provenance; every accepted
claim has exact supporting source spans; model-derived and source-derived content
visibly separate; no silent entity merge (C-88/C-88A included); no timeless
current/effective flag; no Graph dependency; no benchmark-truth access during
compilation or retrieval; no query-time LLM; same final source-evidence K; full
model/prompt/input/output/cost provenance; deterministic validation; explicit
regeneration policy.

**No mode failing any hard-safety condition may satisfy a retain gate**, however
good its retrieval numbers are.

### 9.2 Gate Q — Stage 7C.1 qualification (evaluated **before** any W1 retrieval)

All criteria must hold. No partial credit, no averaging.

| # | Criterion | Required |
|---|---|---|
| Q-1 | Citation validity | **1.00** |
| Q-2 | Invalid source references | **0** |
| Q-3 | Authority contamination (any claim citing a chunk outside its facet's revision) | **0** |
| Q-4 | False merges (incl. C-88 / C-88A) | **0** |
| Q-5 | Accepted-claim precision | **≥ predeclared threshold** (proposed **0.95**) |
| Q-6 | Expected-fact recall in accepted claims | **≥ predeclared threshold** (proposed **0.80**) |
| Q-7 | Summary correctness (owner-adjudicated, every sentence) | **pass at predeclared threshold** (proposed **0 incorrect sentences**) |
| Q-8 | Repeatability (§8F thresholds) | **pass** |
| Q-9 | Budget and ceilings (§3.9) | **no breach; within declared dollar cap** |

> **If Gate Q fails, W1 retrieval and navigation are not run at all.** The stage
> proceeds directly to Gate B or Gate C on W0 evidence alone, and the failure is
> reported as the result.

Rationale: retrieval numbers computed over a compilation layer that has already
failed on precision, provenance or stability are not interpretable — a lucky
retrieval score would obscure exactly the ceiling §1.3 identifies as W1's
principal risk. Compilation must qualify on its own before it is allowed to
compete.

### 9.3 Retain gates (immutable; declared before the measured run; no required winner)

**Improvement — exact definition.** A target question counts as improved only if
**both** hold, comparing W1 to V:

1. status transitions **partial → solved**, **and**
2. complete-chain represented transitions **false → true**.

**Regression — exact definition.** A question regresses if **any** of the
following holds, comparing W1 to V:

- status moves adversely: solved → partial, solved → failed, or partial → failed;
- complete-chain represented: true → false;
- required-fact coverage@K decreases by **any** amount;
- all-required-retrieved@K: true → false;
- a forbidden-fact hit appears where V had none;
- any authority leakage occurs (also an independent hard-safety failure);
- fewer than K chunks are returned where V returned K **and** coverage@K
  decreased. *(A short list alone is not a regression if coverage holds.)*

The word "material" is deliberately not used: **every** regression by this
definition counts.

**Gate A — Retain W1 semantic Wiki.** Gate Q passed; all hard-safety passed;
**≥2 of Q04/Q06/Q07 improved** by the definition above; **zero regressions** by
the definition above on every other question; same final source-evidence K; zero
authority leakage; user-facing page quality (§8D) improves over W0; and
cost/maintenance justified relative to V.

**Gate B — Retain W0 only, as a source-navigation UI.** W1 fails Gate Q or fails
Gate A; W0 provides useful revision / provenance / exact-anchor navigation; W0
maintenance remains low; and **W0 is not represented as a superior semantic
retriever** (its retrieval is reported as ≈ V, by construction).

**Gate C — Do not retain a Wiki projection.** W1 does not improve retrieval or
navigation; or page quality depends on unsupported generated prose; or omissions
or unstable links remain high; or authority-safe composition proves impractical;
or maintenance burden approaches or exceeds the Graph/Hybrid path; or W0 adds
insufficient value beyond the existing chunk/audit viewer.

Evaluated in the fixed declared order **A → B → C**. Retrieval value, navigation
value, page quality and cost are kept distinct and never averaged. No outcome is
encoded as required; no test asserts W1 > W0 > V.

---

## 10. Proposed repository changes

> **Principle: this is a POC that must price a capability, not a production Wiki
> platform. No table, module or abstraction is created before the value it
> serves has been demonstrated.** R3 cuts R2's proposed surface from 16 modules
> and 11 tables to **11 modules and 5 tables**, principally by (a) making W0
> pages and sections *derived views* over existing canonical chunk storage
> rather than new tables, and (b) collapsing claims, aliases, summaries and
> derived links into one validated JSONB compilation record per facet.

### 10.1 New package — `src/ingestion_bench/wiki_projection/`

| Module | Purpose | Stage |
|---|---|---|
| `model.py` | records for anchors, postings, facets, claims, aliases, summary sentences, derived links | 7C.0 |
| `identity.py` | neutral `identifiers_in` lift; Lane 1 + Lane 2 extraction; deterministic page identity + normalization (shared by W0 and W1) | 7C.0 |
| `projection.py` | W0 build (postings, structural + exact-anchor links) and authority-scoped views over canonical chunks | 7C.0 |
| `store.py` | storage protocol + in-memory implementation | 7C.0 |
| `pg_store.py` | isolated Postgres; `IN (...)` before ranking (mirrors 7B.2a `vector_candidate_store.py`) | 7C.0 |
| `compiler.py` | `PROMPT_VERSION` / `prompt_sha256()`, facet prompt builder, §3.9 ceilings, `OpenAIFacetCompiler` + `FakeFacetCompiler` | 7C.1 |
| `validation.py` | §4 deterministic validator **and** §3.7 deterministic link derivation | 7C.1 |
| `assembly.py` | authority-scoped facet view, summary filtering, §6.2 payload composition, page rendering | 7C.1 |
| `retrieval.py` | W0 and W1 retrieval, §6.5 bounds policy and saturation accounting | 7C.2 |
| `navigation.py` | `N_W0` / `N_W1` / `N_advisory` (§7) | 7C.2 |
| `benchmark.py` | runner, metrics, report; imports the frozen 7B.0 `_evaluate_question` **by identity** | 7C.2 |

Plus `config.py` (env-driven, per repo convention).

*Cut from R2, and why:* `anchor_extractor.py` → folded into `identity.py` (same
normalization must be shared, so splitting invited drift); `projection_builder.py`
+ `renderers.py` → `projection.py` / `assembly.py`; `compiler_prompt.py` →
`compiler.py` (prompt and ceilings version together); `page_compiler.py` +
`page_validation.py` + `page_assembler.py` + `embedding_payload.py` → three
modules; `evaluator.py` + `report.py` + `benchmark_runner.py` → `benchmark.py`.

### 10.2 Other new files

`contracts/wiki_projection_v1.json` (W0 projection + anchor + identity contract,
frozen at 7C.0); `contracts/wiki_compiler_v1.json` (facet schema, prompt version,
model, ceilings, budget cap, validation rules, Gate Q thresholds, retain gates —
frozen at 7C.1); `scripts/run_stage7c_wiki_probe.py` (`--fake` / `--in-memory`,
as 7B.2a); `tests/test_wiki_projection.py`, `tests/test_wiki_compiler.py`,
`tests/test_wiki_validation.py`; `docs/STAGE7C_WIKI_DECISION.md`;
`reports/stage7c_wiki_{results.json, scorecard.md}`; `artifacts/stage7c/`
(gitignored, regenerable).

### 10.3 Database tables — five, prefixed `edib_stage7c_`

| Table | Columns (essentials) | Why it must exist |
|---|---|---|
| `anchor` | `anchor_id`, `anchor_kind`, `normalized_value`, `display_text`, `is_ambiguous` | page identity universe, shared by W0 and W1 |
| `anchor_posting` | `anchor_id`, `chunk_id`, `document_revision_id`, `logical_document_id`, `char_span`, `source_ref` | authority filtering + W0 exact-anchor navigation; indexed on `anchor_id`, `document_revision_id` |
| `facet` | `page_key`, `document_revision_id`, `validation_status`, `facet_hash`, `run_id`, **`compiled JSONB`** (validated claims, aliases, summary sentences, derived links) | the compilation record; indexed on `page_key`, `document_revision_id` |
| `facet_embedding` | `page_key`, `document_revision_id`, `embedding VECTOR(dim)`, payload SHA-256 + provenance (§6.2) | authority-first vector retrieval; indexed on `document_revision_id` |
| `compilation_audit` | raw output, rejections + reasons, `unresolved_identity_mentions`, tokens, cost, latency, model, prompt hash, run id, ceiling breaches | §8A/§8E evidence and Gate Q inputs |

**Not created:** `wiki_page`, `wiki_section` (derived views over existing
canonical chunk storage), `wiki_link` (W0 links derive from postings; W1 links
derive from claims in `facet.compiled`), and R2's four separate
claim/alias/summary/candidate tables (now one JSONB column).

**Why JSONB.** The compiled record is written once, validated as a whole, read as
a whole for assembly and rendering, and never partially updated. Relational
decomposition would buy query flexibility the POC does not need while adding four
tables, four migrations and four sets of referential-integrity tests. The columns
that must be *filtered* — `page_key`, `document_revision_id`, `validation_status`
— are promoted to real indexed columns; everything else stays in the document.

Authority filtering is **always** `document_revision_id IN (:eligible)` in the
same statement as ranking/LIMIT.

### 10.4 Reused read-only

`canonical/*`, `chunking/*`, `adapters/docling_standard` (5A),
`revision_authority/*` (7R.1), the 7R.2 authority-first SQL pattern, the 7B.0
corpus/facts/questions and its `_evaluate_question`,
`retrieval_baseline/embeddings.py`, and — as **pattern precedent, not import** —
`answer_baseline/`'s lazy-client, strict-schema, prompt-hash, usage/cost and
mechanical-validation approach.

### 10.5 Frozen code explicitly **not** modified

All of `graph_retrieval_benchmark/` and `hybrid_retrieval_benchmark/` (7B.2a,
Gate D), `cross_document_benchmark/` (7B.0), `revision_authority/` (7R.1),
`revision_search_benchmark/` (7R.2), `answer_baseline/` (7A.2), `canonical/`,
`chunking/`, `adapters/`, and every existing contract and report.

---

## 11. Stage decomposition and freeze boundaries

**Stage 7C.0 — Projection qualification (W0, deterministic, zero model calls).**
Anchors, postings, structural + exact-anchor links, deterministic page identity,
authority-scoped views, rendering. Prove hard safety: full provenance, zero
benchmark-truth access, C-88/C-88a separation, deterministic and immutable
rebuilds, correct authority views, no Graph dependency. Produce projection
manifests, rendered sample pages, build-side ledger, and the W0 ≈ V control
measurement.
**Freeze: the projection contract, the identity/anchor rules, and the builder.**

**Stage 7C.1 — Compilation qualification (W1 build side only).** Facet compiler,
prompt, schema, ceilings, deterministic validator, deterministic link derivation,
authority-scoped assembly, facet embeddings, the §8F repeatability runs, §8A
compilation metrics, and §4.5 owner adjudication of every accepted claim and
summary sentence. **No retrieval or navigation is run in 7C.1.** The stage ends
by evaluating **Gate Q (§9.2)**.
**Freeze: the compiler contract, prompt version + hash, model identity, Run 1's
accepted claim set, derived links, and facet embeddings.**

**Stage 7C.2 — Retrieval and navigation comparison (read-only).** *Entered only
if Gate Q passed.* Load the frozen 7C.0 projection and frozen 7C.1 **Run 1**
facets/embeddings read-only; run V vs W0 vs W1 (§8B), `N_W0` vs `N_W1` vs
`N_advisory` (§8C), the page-quality rubric (§8D), the cost ledger (§8E); apply
the §9.3 retain gates; write `docs/STAGE7C_WIKI_DECISION.md`.

**Freeze boundary.** 7C.1 may not change the 7C.0 projection, identity rules,
anchor rules, or hashes. 7C.2 may not change the projection, compiler, prompt,
accepted claim set, derived links, or any embedding — it only queries and
measures. Same 7B.0 → 7B.2a discipline.

**No additional variants after W1.** If W1 fails Gate Q or Gate A, the outcome is
Gate B or Gate C — **not** a second compiler, a new prompt, a raised ceiling, or a
tuned retrieval flow. Any such proposal is a new stage requiring fresh owner
approval.

---

## 12. Scope exclusions

Another Graph experiment; multiple W1 compiler variants; query-time answer
generation; ADK; agent workflows; query decomposition; query-planning LLM;
rerankers; retrieval router; ontology expansion; Neo4j; UI framework
implementation; human approval workflow implementation; vision; vendor-native
ingestion; final direct-document LLM benchmark. The final direct-LLM and
provider-managed retrieval baselines remain on the larger roadmap but are not
part of Stage 7C.

---

## 13. Open questions requiring owner approval

| # | Question | Recommendation |
|---|---|---|
| **Q1** | **Per-facet ceilings** (§3.9) — chunks 12, input tokens 8k, claims 20, aliases 8, summary sentences 5, output tokens 4k, with **breach ⇒ qualification failure and no batching**? | Approve; the no-workaround rule is the point |
| **Q2** | **Bounds policy** (§6.5) — `P = K`, `C = P × F_max`, score-before-truncate, no backfill, saturation reported? | Approve |
| **Q3** | **Gate Q thresholds** (§9.2) — accepted-claim precision **0.95**, expected-fact recall **0.80**, summary correctness **0 incorrect sentences**? | Approve or set your own; they must be declared before compilation |
| **Q4** | **Gate A improvement** — require **both** partial→solved **and** complete-chain false→true on ≥2 of Q04/Q06/Q07? This is a strict bar; a question that gains complete-chain without changing status will not count. | Approve; the pair is what "the chain now works" actually means |
| **Q5** | **Repeatability thresholds** (§8F) — N = 3, claim Jaccard ≥ 0.90, citations ≥ 0.95, false merges 0, ceiling breaches 0, **Run 1 primary**? | Approve |
| **Q6** | **Compiler model and dollar cap** — `gpt-4o-mini` at `temperature = 0` with a declared per-run cap? Or `gpt-4o` for a stronger upper bound on achievable quality? | `gpt-4o-mini` first: it is the configured default and keeps the cost question honest |
| **Q7** | **Page-quality rubric** (§8D) — owner alone, blind, 6-page deterministic sample? Or a second rater? | Owner alone for 7C; single-rater recorded as a stated limitation |
| **Q8** | **Click budget** (§7.3) — global **6**? | Approve |
| **Q9** | **`identifiers_in` reuse** — lift the ~4-line regex into a neutral module to avoid importing the frozen graph package? | Approve |
| **Q10** | **Summary degradation** (§5.3) — accept that a narrower authority scope yields a shorter, possibly disjointed summary, floor being "no summary available for this authority scope"? | Approve; the alternative needs a query-time LLM |
| **Q11** | **Lane 2 phrase anchors** — in scope for 7C.0, or identifiers-only? | In scope: without it the `Payment Settlement` hop is unreachable and both W0 and W1 lose the worked example |
| **Q12** | **Adjudication effort** (§4.5) — every accepted claim and every summary sentence, on Run 1. On this corpus that is a bounded but real manual task. Acceptable? | Approve; sampling on a corpus this size adds variance without saving meaningful effort |

---

*Plan only (Revision 3). No code, tables, fixtures, embeddings, or LLM calls
created or run; no frozen stage modified. Stage 7B.2a remains frozen at Gate D.
Awaiting review and the §9/§13 decisions before any Stage 7C.0 work.*
