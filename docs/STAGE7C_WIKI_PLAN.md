# Stage 7C Plan (Revision 2) — Deterministic Wiki Control (W0) and Bounded, Auditable LLM-Assisted Evidence Wiki (W1)

> **Status: PLAN ONLY — pending owner review and approval.** No code, tables,
> fixtures, embeddings, or LLM calls have been created, run, or modified for
> Stage 7C. No frozen stage has been touched. This document supersedes
> Revision 1 ("Source-Backed Navigational Wiki Projection").
>
> **What changed in Revision 2.** Revision 1 defined `WikiSection` ≈ 1:1 with
> `CanonicalChunk` and reused the same chunk embeddings for Wiki retrieval. That
> makes Wiki semantic retrieval *the same computation as Vector retrieval in a
> different wrapper* — it cannot be expected to retrieve differently, and
> presenting it as a semantic-retrieval candidate was an error. Revision 2
> **reclassifies that deterministic work as a control (W0)** and introduces one
> bounded, auditable LLM-compiled evidence Wiki (**W1**) as the actual
> representation under test.
>
> **Predecessor context.** Stage 7B.2a is **completed and frozen at Gate D**
> ("do not retain Graph in the online retrieval path"). Stage 7C does not reopen
> it. W1 **must not** consume Graph nodes, edges, aliases, paths, extraction
> output, H0/H1/H2, traversal, path ranking, RRF fusion, query planning, Neo4j,
> or any Graph benchmark contract or report. W1 derives independently from the
> same frozen `CanonicalChunk`s.

---

## 0. Grounding facts (verified in the repo, read-only)

These are the primitives Revision 2 builds on. Each was read directly.

**Canonical layer**

- **`CanonicalChunk`** (`chunking/model.py:255`) carries `chunk_id`,
  `logical_document_id`, `document_revision_id`, `source_document_sha256`,
  `version_label`, `revision_number`, `chunk_index`, `chunk_type`,
  `unit_indices`, `heading_path`, `heading_source_element_ids/refs`,
  `source_element_ids`, `annotation_ids`, `source_refs`, and — critically —
  **three separated text fields**: `source_text`, `model_derived_text`,
  `retrieval_text`. The source-vs-model separation this plan requires (§4) is
  already a first-class property of the canonical model, not something Stage 7C
  invents.
- **`IdentifierAnnotation`** (`canonical/annotations.py:33`): `raw_text`,
  `normalized_value`, `target_ref`, `start_char/end_char`, `derivation`.
  Deterministic identifier-anchor source, linked via
  `CanonicalChunk.annotation_ids`.
- **`identifiers_in()`** (`graph_retrieval_benchmark/model.py:58`), regex
  `\b([A-Za-z]{1,6}-\d+[A-Za-z]?)\b` uppercased: `C-88` → `"C-88"`, `C-88a` →
  `"C-88A"`. Exact primitive that protects the **C-88 / C-88a boundary**.
  *It lives in the frozen graph package; §3 of the owner's directive forbids
  depending on Graph artifacts, so 7C **lifts this ~4-line regex into a neutral
  module** rather than importing the graph package* (open question Q13).

**Authority layer**

- **Resolver** (`revision_authority/resolver.py:150`): `resolve_query_scope(...)
  → QueryResolutionResult{eligible_revision_ids, authority_labels}` with
  `RevisionAuthorityLabel{publication_status, derived_state}` (`resolver.py:55`,
  `:77`); `derived_state ∈ {effective, approved_future, superseded, draft,
  under_review, withdrawn}`. **Authority is query-time and dynamic — there is no
  stored `current` flag anywhere in the repo.** This is the single most important
  constraint on §5.
- **Authority-first pgvector pattern** exists in
  `revision_search_benchmark/pgvector_store.py`,
  `cross_document_benchmark/pgvector_store.py`, and 7B.2a's
  `vector_candidate_store.py`: SQL `document_revision_id IN (:ids)` in the
  **same statement** as `ORDER BY embedding <=> :q LIMIT :k`. Directly reusable
  for page-facet retrieval (§6).

**Evaluation layer**

- **Frozen scorer**: `cross_document_benchmark/benchmark_runner._evaluate_question`
  (Stage 7B.0 evaluator, reused by 7B.2a via import identity). V, W0 and W1 must
  all be scored by this, unchanged.
- **Corpus**: 6 logical documents / 11 revisions / 15 frozen facts / 12
  questions; exact source text already extracted in
  `docs/DEVIN_REBUILD_APPENDICES.json` (`G_fixture_source_text`).

**Embedding layer**

- `EmbeddingProvider` protocol, `SentenceTransformerEmbeddingProvider` (lazy
  load), `FakeEmbeddingProvider` (deterministic, dim 32) —
  `retrieval_baseline/embeddings.py:31,37,73`. **Stage 7C introduces no new
  embedding model and no reranker.**

**LLM layer — already exists and is the pattern W1 must follow**

Stage 7A.2's `answer_baseline/` package is a working precedent for a bounded,
audited, mechanically-validated model call. W1 reuses its *shape*, not its code
path:

- `answer_generator.py:152` `OpenAIAnswerGenerator` — **lazy** client
  construction (importing/constructing never needs a key or network), OpenAI
  **strict `json_schema` structured output** so results always parse, token usage
  captured from `response.usage`, latency measured.
- A `FakeAnswerGenerator` sibling exists for deterministic offline tests.
- `config.py:23,32` — one configured model (`gpt-4o-mini` default, env-override
  `INGESTION_BENCH_ANSWER_MODEL`), `ANSWER_TEMPERATURE = 0`, and an explicit
  in-repo comment that **temperature=0 is the lowest-variance setting available
  but is not a determinism guarantee for a hosted model** — which is precisely
  why §8F (repeatability) is mandatory rather than optional.
- `config.py:38,44` — `_PRICING_USD_PER_MILLION_TOKENS` + `estimate_cost_usd()`,
  returning `None` rather than a fabricated number for unpriced models.
- `prompt.py:23,106` — `PROMPT_VERSION = "stage7a2-v1"` and `prompt_sha256()`,
  the exact prompt-versioning primitive §6 requires.
- `validation.py:19,99` — `CitationValidationResult` / `validate_answer()`:
  mechanical, non-LLM validation of model claims against cited chunks. W1's
  validator (§4) is a strict superset of this idea.
- `model.py:42,67` — `ClaimCitation` / `AnswerResult` with model validators
  asserting provenance IDs are a subset of cited IDs. Same discipline applies to
  W1 claims.

**Consequence:** W1 requires no new provider, no new SDK, no new cost model, and
no new determinism story. It requires a new *page-level* schema, a much stricter
validator, and an authority-aware assembly step.

---

## 1. Owner's briefing

### 1.1 The business question

> **Can a bounded, auditable LLM compile source-backed evidence pages that
> improve semantic retrieval and navigability enough to justify the additional
> derived layer — while preserving original `CanonicalChunk`s as the sole
> authoritative evidence?**

The question is explicitly **not** "can an LLM write a nice wiki." It is a
cost-justification question. The measurable benefit of W1 must be weighed
against: ingestion-time model calls, a validation subsystem, page regeneration
machinery, prompt/model versioning, derived-page storage, and the ongoing
diagnostics and maintenance all of that implies.

### 1.2 Why Revision 1's deterministic plan was insufficient

Revision 1 proposed `WikiSection` ≈ 1:1 with `CanonicalChunk`, reusing the chunk
embedding. Written out, the two retrieval paths were:

```
V :  query embedding  →  chunk embeddings  →  top-K chunks
W :  query embedding  →  the same chunk embeddings, wrapped in
                          WikiSection rows  →  top-K sections  →  their chunks
```

These are the same computation. Barring tie-breaking and dedupe artifacts, W was
**expected to equal V**, and any observed difference would have been noise or an
artifact of the wrapper — not evidence of a better knowledge representation.
Revision 1 nonetheless placed W under a retrieval-improvement gate (Gate A),
which was not a fair or meaningful test.

Revision 1's navigation model had a second, distinct limitation:

```
section  →  shared literal anchor  →  every eligible section containing that anchor
```

On a 6-document corpus this produces clean chains. On an enterprise corpus, a
common anchor posts into hundreds of sections, and the model has **no
understanding of which relationship or direction the user is asking about** — it
asserts only co-occurrence. It degrades toward "here are 200 places this string
appears."

Neither observation makes the deterministic work worthless. It makes it a
**control**, not a treatment. Revision 2 keeps it, renames it **W0**, and stops
asking it to win a semantic-retrieval gate.

### 1.3 The three modes

| | What it is | Retrieval unit | New model calls | What it is evaluated for |
|---|---|---|---|---|
| **V** | Frozen authority-aware Vector baseline over original chunks | chunk | 0 | Reference. Not rerun. |
| **W0** | Deterministic source Wiki **control** | chunk (via section) | 0 | Organization, provenance orientation, revision navigation, exact-anchor browsing, cost. **Not** semantic-retrieval improvement. |
| **W1** | Bounded LLM-assisted source-grounded **evidence Wiki** | page facet → cited chunks | ingestion-time only | Retrieval, navigation, page quality, compilation quality, repeatability, cost. |

**One** LLM Wiki variant is proposed. No W2, no compiler A/B, no prompt
tournament (§17).

### 1.4 One complete worked example

The frozen corpus contains a five-hop chain distributed across five documents:

```
APP-224510          --supports-->              Payment Settlement   (APP-PORTFOLIO rev2)
Payment Settlement  --is governed by-->        Obligation O-31      (SERVICE-CATALOGUE rev1)
Obligation O-31     --is satisfied by-->       Control C-88         (OBLIGATION-REGISTER rev2)
Control C-88        --is implemented through-->Procedure P-205      (CONTROL-LIBRARY / PROCEDURE-CATALOGUE)
```

**Under V.** The query "what procedure implements the control for APP-224510's
settlement obligation?" embeds once and retrieves the top-K most similar chunks.
Stage 7B.0 measured this as *partial* on Q04/Q06/Q07: the top-K is dominated by
chunks lexically near the query, and the far end of the chain (P-205) falls
outside K because no single chunk contains both ends.

**Under W0.** A `Payment Settlement` phrase anchor and `O-31`/`C-88`/`P-205`
identifier anchors are extracted deterministically. Semantic retrieval returns
the same chunks V returned (same embeddings). *Navigation*, however, works: land
on the APP-PORTFOLIO section, click `Payment Settlement` → SERVICE-CATALOGUE,
click `O-31` → OBLIGATION-REGISTER, click `C-88` → CONTROL-LIBRARY, click
`P-205` → PROCEDURE-CATALOGUE. **4 clicks, every hop source-backed.** But each
click means only *"this same literal string also appears here"* — the direction
and meaning of the relationship live in the source sentence, not in the link.

**Under W1.** A page `PAGE:IDENT:O-31` is compiled from the chunks in which
`O-31` occurs. Abridged, validated output:

```json
{
  "page_key": "IDENT:O-31",
  "display_title": "Obligation O-31",
  "page_type": "governed_identifier",
  "identity_confidence": "supported",
  "source_chunk_ids": ["chunk_svc_0007", "chunk_obl_0003"],
  "aliases": [
    { "alias": "Obligation O-31", "supporting_chunk_ids": ["chunk_obl_0003"],
      "supporting_quotes": ["Obligation O-31"], "status": "supported" }
  ],
  "claims": [
    { "claim_id": "clm_1", "subject": "Payment Settlement",
      "predicate": "is governed by", "object": "O-31",
      "claim_text": "The Payment Settlement business service is governed by Obligation O-31.",
      "supporting_chunk_ids": ["chunk_svc_0007"],
      "supporting_revision_id": "SERVICE-CATALOGUE:rev1",
      "supporting_quotes": ["Payment Settlement ... is governed by Obligation O-31"],
      "derivation": "model_derived", "validation_status": "accepted" },
    { "claim_id": "clm_2", "subject": "O-31",
      "predicate": "is satisfied by", "object": "C-88",
      "claim_text": "Obligation O-31 is satisfied by Control C-88.",
      "supporting_chunk_ids": ["chunk_obl_0003"],
      "supporting_revision_id": "OBLIGATION-REGISTER:rev2",
      "supporting_quotes": ["Obligation O-31 is satisfied by Control C-88"],
      "derivation": "model_derived", "validation_status": "accepted" }
  ],
  "summary_sentences": [
    { "sentence_id": "s1",
      "text": "O-31 governs the Payment Settlement service and is satisfied by Control C-88.",
      "supported_claim_ids": ["clm_1", "clm_2"], "derivation": "model_derived" }
  ],
  "related_page_candidates": [
    { "target_page_key": "IDENT:C-88", "relationship_label": "is satisfied by",
      "supporting_claim_ids": ["clm_2"], "classification": "source_cited_model_derived" },
    { "target_page_key": "PHRASE:payment settlement", "relationship_label": "governs",
      "supporting_claim_ids": ["clm_1"], "classification": "source_cited_model_derived" }
  ]
}
```

The **page facet embedding** for `(IDENT:O-31, OBLIGATION-REGISTER:rev2)` covers
title + supported aliases + accepted claim texts from that revision + the
eligible summary sentence. The query above is semantically close to that
*compiled* text in a way it is not close to any single raw chunk — that is the
one and only hypothesis W1 tests. Retrieval then walks: eligible facets → top
pages → their accepted claims → **the cited original chunks** → ranked by the
existing chunk embeddings → **the same final K as V**. The generated sentence
never counts as evidence; `chunk_svc_0007` and `chunk_obl_0003` do.

Navigation under W1 is `clm_2`-backed: the hop O-31 → C-88 carries the label
*"is satisfied by"* and cites the exact sentence that says so — a strictly more
informative click than W0's *"the string C-88 also appears here."* It is still
**model-derived and replaceable**, not an authoritative registry edge.

---

## 2. W0 — deterministic source Wiki control

### 2.1 Building blocks

All records are Pydantic models; all IDs and hashes are SHA-256 over stable
inputs (never random, never run-scoped). W0 makes **zero model calls**.

- **`WikiRevisionPage`** (immutable, one per `document_revision_id`):
  `page_id = sha256(document_revision_id | projection_contract_version)`;
  `logical_document_id`, `document_revision_id`, `source_relative_path`,
  `source_document_sha256`, `revision_number`, `version_label`, ordered
  `heading_structure`, `section_ids[]`, `page_hash`. **No `current` flag.**
- **`WikiSection`**: `section_id = sha256(document_revision_id | chunk_id)`,
  1:1 with a `CanonicalChunk`; `chunk_id`, `heading_path`, `source_text`
  (verbatim), `source_refs` (verbatim), `source_element_ids`, `content_sha256`,
  `anchor_ids[]`, `section_hash`. `model_derived_text` is retained in a
  separate, clearly-labelled field and **never merged into `source_text`**.
- **`WikiAnchor`**: `anchor_id = sha256(anchor_kind | normalized_value)`;
  `anchor_kind ∈ {identifier, phrase, heading_title}`; `normalized_value`,
  `display_text`, `extraction_method`, `is_ambiguous`.
- **`AnchorPosting`**: `anchor_id`, `section_id`, `document_revision_id`,
  `logical_document_id`, `char_span`, `source_ref`, `posting_hash`. Occurrence
  evidence, **never a relationship assertion**.
- **`WikiLink`**: `link_id`, `from_ref`, `to_ref`, `link_type ∈ {structural,
  exact_anchor}`, `provenance` (anchor_id / shared source_ref),
  `is_authoritative_lineage = False` **always**.

The **logical-document / revision-history view** and **every authority label**
are query-time views, never stored rows.

**Anchor extraction — two deterministic, benchmark-truth-free lanes.** Both read
only `CanonicalChunk.source_text`, `heading_path`, and `IdentifierAnnotation`s.
Neither reads facts, questions, expected chains, Graph output, or hardcoded
entity names.

- **Lane 1 — identifier anchors (high precision).** `IdentifierAnnotation`s with
  `derivation == "extracted"`, plus the lifted `identifiers_in` regex for
  defense-in-depth. `normalized_value` is the key; `start_char/end_char` the
  provenance. Yields **APP-224510, O-31, C-88, C-88A, P-205** with exact spans.
  The uppercase rule keeps **C-88 and C-88A distinct** — a hard test asserts they
  never merge.
- **Lane 2 — conservative repeated-phrase anchors.** Needed for *Payment
  Settlement*, which is not an identifier. Candidate = a maximal run of 2–4
  tokens each matching `^[A-Z][A-Za-z0-9&/-]*$` or an identifier token, drawn
  from `source_text` and `heading_path`; rejected if any token is in a fixed
  closed stop-list; 2 ≤ tokens ≤ 4, 3 ≤ chars ≤ 60; the normalized span must
  occur in **≥2 distinct chunks and ≥2 distinct `logical_document_id`s**. Key =
  casefold + single-space. A candidate colliding with an identifier key is
  dropped (identifiers win). Two display forms mapping to one key are flagged
  `is_ambiguous` and **never silently merged**. If a normalized phrase posts into
  sections with disjoint identifier sets, it is flagged ambiguous and its links
  are marked advisory regardless of type.

**Build-time vs query-time.** Build (parse → chunk → sections → anchors →
postings → structural/exact-anchor links) is immutable and revision-scoped; it
**never** calls the resolver and stores **no** authority state. Query time
resolves `intent + as_of_date → eligible_revision_ids` and filters sections,
postings and links via `document_revision_id IN (:eligible)` **before** ranking
or rendering. An authority activation changes only the eligible view — **no
re-parse, re-chunk, re-embed, or page-hash change** (asserted by a hard test).

### 2.2 W0 retrieval

Embed the query once with the existing provider; SQL-filter sections by
`document_revision_id IN (:eligible)` before `ORDER BY cosine LIMIT k`; map each
returned section back to its unique originating `chunk_id`; dedupe preserving
order; truncate to the **same final K as V**; score with the **frozen 7B.0
evaluator**.

> **Stated explicitly, as required:** *W0 semantic retrieval is expected to be
> identical or nearly identical to V, because a W0 section is 1:1 with a chunk
> and reuses that chunk's existing embedding and retrieval payload. Any observed
> difference is expected to arise only from dedupe ordering or tie-breaking, not
> from a materially different semantic representation.*

W0 is therefore run **as a control that quantifies wrapper overhead**, and
**no retrieval-improvement gate is applied to it** (§9). Reporting W0 ≈ V is a
successful control outcome, not a failure.

### 2.3 W0 navigation

`structural` links (section ↔ revision page; page ↔ revision-history view) and
`exact_anchor` links (section →(anchor)→ every other **eligible** section posting
the same anchor). Deterministic navigator, no LLM: start at the top retrieved
section; traverse eligible links; one click = one traversal; visit order is
deterministic (`structural < exact_anchor`, then anchor key, then section_id).
Authority leakage along any traversed link is a hard failure.

### 2.4 Expected value

Human-readable source organization; provenance orientation (every rendered
sentence resolves to a `chunk_id` and `source_ref`); revision-history navigation
via the resolver; exact-anchor browsing; near-zero marginal cost (no model
calls, embeddings reused, one builder).

### 2.5 Expected limitations

No semantic-retrieval improvement over V (by construction). Exact-anchor links
assert co-occurrence only — no direction, no relationship meaning. Lane 2 is
bounded by capitalization convention: it will miss lower-cased entities and
over-generate on boilerplate headings (partially mitigated by the cross-document
≥2 rule). Anchor fan-out is unbounded on a large corpus and degrades to a
string-occurrence index. A future *optional* lane — an external authoritative
catalog/CMDB supplying a governed anchor vocabulary — is **documented, not
implemented in 7C**.

---

## 3. W1 — bounded LLM-assisted source-grounded evidence Wiki

### 3.1 Inputs

For each candidate page identity, the compiler receives **only**:

- the ordered set of `CanonicalChunk`s in which that identity occurs, each with
  `chunk_id`, `document_revision_id`, `logical_document_id`, `heading_path`, and
  verbatim `source_text`;
- the candidate identity key and its deterministic display forms;
- the projection contract version and prompt version.

The compiler **never** receives: benchmark facts, questions, required/forbidden
fact IDs, expected relationship chains, Graph nodes/edges/aliases/paths, another
page's compiled output, authority state, or the resolver. Truth-isolation is
enforced by AST tests over the compiler and prompt-builder modules *and* by a
runtime guard (§8A).

### 3.2 Page identity — the recommended model

**Recommendation: the `governed-subject page`** — one page per *anchor identity*,
where the identity universe is **the W0 anchor set** (Lane 1 identifiers + Lane 2
conservative phrases), plus a capped, separately-marked lane of model-proposed
identities.

Rationale: it makes the identity universes of W0 and W1 **the same**, so the
V/W0/W1 comparison isolates exactly one variable — *page content representation*
— rather than confounding it with a different page inventory. It also means the
deterministic, already-planned extraction work is not wasted.

`page_key = "{kind}:{normalized_identity}"`, e.g. `IDENT:O-31`,
`PHRASE:payment settlement`, `IDENT:APP-224510`. Page kinds:

| Kind | Source | Cap |
|---|---|---|
| `governed_identifier` | Lane 1 identifier anchors | uncapped (deterministic, precise) |
| `business_topic` | Lane 2 phrase anchors | uncapped (already conservatively bounded) |
| `model_proposed` | compiler-proposed entity grounded in exact source spans | **capped globally (proposed 10)**, always marked, measured separately |

**Every** model-proposed identity must cite the exact chunks and exact character
spans in which the identity string occurs, and the span must be an exact
substring of the cited chunk's `source_text`; otherwise it is rejected. Rejected
identity proposals are retained in the audit record.

*Rejected alternative:* letting the compiler define the page inventory freely.
It produces a different page set per run, destroys the W0/W1 comparison, and
makes repeatability (§8F) measure inventory churn rather than content stability.

### 3.3 Collision and ambiguity handling

| Case | Rule |
|---|---|
| **C-88 vs C-88a** | Distinct keys via the `identifiers_in` uppercase rule (`C-88` / `C-88A`). Hard test at identity, claim, alias, link and embedding level. Never merged, in any lane. |
| **Duplicate names** | If one normalized key resolves to occurrence sets with disjoint identifier context, the pages are **kept separate** with a deterministic disambiguator suffix derived from the sorted `logical_document_id` set, and both are flagged `identity_confidence = "ambiguous"`. |
| **Aliases** | `status ∈ {supported, uncertain}`. A `supported` alias requires an exact quoted span. An `uncertain` alias is rendered and stored but **may never merge two pages** and **may never satisfy an identifier-grounding check**. |
| **Abbreviations** | Treated as alias proposals; same rule. No expansion dictionary is introduced. |
| **Uncertain identity match** | Remains a separate page, marked ambiguous. **Silent merging is a hard-safety failure.** |
| **Same phrase, different business concept** | Detected as disjoint-identifier-context (row 2) and split; if undetectable, the page is flagged ambiguous and its outgoing links are downgraded to advisory. |

### 3.4 Claims

One atomic assertion per claim: `subject`, `predicate`, `object`, `claim_text`,
`supporting_chunk_ids`, `supporting_revision_id`, `supporting_quotes`,
`derivation = "model_derived"`, `validation_status ∈ {accepted, rejected,
uncertain}`.

**Recommended restriction: a claim's supporting chunks must all belong to a
single `document_revision_id`.** This makes claim eligibility trivially decidable
(`supporting_revision_id ∈ eligible_revision_ids`) and structurally prevents
cross-revision synthesis inside a single assertion. Multi-document *chains* are
still fully expressible — as several single-revision claims on one page, which is
exactly how the §1.4 worked example represents the APP-224510 → P-205 chain.

*Rejected alternative:* multi-revision claims with conjunctive eligibility (all
supporting revisions must be eligible). It is sound but adds a second eligibility
path, a harder contradiction analysis, and a much weaker "no blending" argument
for no demonstrated benefit on this corpus. Raised as open question **Q2**.

### 3.5 Summaries

The compiler emits **sentence-level** summary records, not a prose blob:
`summary_sentences: [{sentence_id, text, supported_claim_ids, derivation}]`.
Every sentence must map to ≥1 accepted claim on the same page. This is the
refinement that makes authority-safe summaries possible without a query-time LLM
(§5.3).

### 3.6 Aliases

As §3.3. Aliases contribute to the W1 embedding payload **only when
`status == "supported"`**.

### 3.7 Links

`related_page_candidates: [{target_page_key, relationship_label,
supporting_claim_ids, classification: "source_cited_model_derived"}]`. The target
must be an existing page key; the supporting claims must be `accepted` and on the
emitting page. These are **model-derived and replaceable**, never authoritative
registry edges (§7).

### 3.8 Bounded-ness — what makes W1 "bounded"

One compiler, one prompt version, one model, one structured schema, strict
JSON-schema output mode, `temperature = 0`, no free prose as a primary persisted
field, a global cap on model-proposed identities, no query-time LLM, no
compiler-visible benchmark truth, no page-to-page context, and a declared
per-run call/token/dollar ceiling that aborts the run rather than overrunning.

---

## 4. Source-grounding and validation contract

Validation is **deterministic and non-LLM**, runs after the model returns
structured output, and is the only path by which anything becomes `accepted`.

### 4.1 Deterministic checks (all must pass for `accepted`)

1. Every `chunk_id` referenced exists.
2. Every referenced chunk belongs to the page's declared input set.
3. Every `supporting_quote` is an **exact substring** of the cited chunk's
   `source_text` (byte-exact after a single declared whitespace normalization).
4. Every `document_revision_id` is valid and matches the cited chunks.
5. Every `source_ref` resolves.
6. Every identifier appearing in `claim_text`, `subject`, `object`, an alias, or
   a summary sentence — extracted with the lifted `identifiers_in` — occurs in
   the cited evidence, or is linked to a `supported` alias record. *(This is the
   primary hallucinated-identifier guard.)*
7. **C-88 and C-88A are not merged** at identity, claim, alias, link or
   embedding level.
8. Every summary sentence maps to ≥1 `accepted` claim ID on the same page.
9. Every `related_page_candidate` maps to `accepted` claims or to `supported`
   identity evidence, and its target page key exists.
10. No unsupported factual field is persisted as `accepted`.
11. **No timeless status.** A closed status lexicon (`current`, `effective`,
    `in force`, `active`, `latest`, `now applies`, `supersedes` used
    predicatively, …) is rejected in `predicate`/`claim_text`/summary text unless
    it appears inside an exact quoted source span **and** the claim carries its
    `supporting_revision_id`. The compiler may never emit a page-level status,
    currency, or effectiveness field. *(Directly protects the repo-wide "no
    stored current flag" invariant.)*
12. **Duplicate and contradictory claims.** Normalize `(subject, predicate,
    object)`. Same triple, same revision → duplicate, deduped with both citations
    retained. Same `(subject, predicate)`, different `object`:
    - different revisions → `revision_divergent` (expected evolution; both
      accepted, both revision-scoped);
    - same revision → `contradictory`; **both are demoted to `uncertain`**,
      neither is silently dropped, and the pair is reported.
13. Rejected outputs and **the reason for each rejection** are persisted for
    audit; nothing is discarded silently.
14. Schema conformance, cap conformance (model-proposed identity cap), and
    budget conformance.

### 4.2 Acceptance and rejection behaviour

`accepted` → persisted, eligible for the embedding payload, eligible to support
a summary sentence or a link. `uncertain` → persisted and **rendered as
uncertain**, excluded from the embedding payload, may not support a summary
sentence or link. `rejected` → persisted **in the audit record only**, never in
the page view, never embedded. A page whose claims are all rejected is persisted
as an empty page with its rejection ledger — not deleted (deletion would hide the
failure mode from §8E).

### 4.3 Citation validity is not claim correctness

> **Stated explicitly, as required:** *An exact-substring citation proves only
> that the cited source passage exists and contains the quoted text. It does not
> prove that the model's inferred `predicate` accurately represents that
> passage.*

| Property | Definition | How measured |
|---|---|---|
| **Citation validity** | The cited chunk exists, is in scope, and the quote is an exact substring. | **Deterministic**, 100% mechanically checkable (§4.1.1–4.1.5). |
| **Claim correctness** | The generated `(subject, predicate, object)` faithfully represents the cited passage. | **Not mechanically decidable.** Measured post-hoc (§8A) against the 15 frozen facts, plus owner adjudication of a deterministic sample of claims that match no frozen fact. |

Both are reported separately and **neither is allowed to stand in for the
other**. A run with 100% citation validity and poor claim correctness is a Gate C
signal, not a success.

### 4.4 Source vs model-derived separation

Persisted and rendered in separate, labelled blocks:

- **A — source-authoritative:** original `CanonicalChunk.source_text`,
  `source_refs`, revision identity, document provenance.
- **B — model-derived:** page identity proposals, aliases, claims, summaries,
  related-page links, relationship labels.

B is auditable, versioned, regenerable, replaceable, **never silently promoted to
source truth, and never sufficient evidence without its cited source chunks**.
Any final answer or benchmark fact resolves back to A.

---

## 5. Authority and revision model

A holistic page can combine evidence from multiple documents and revisions. The
central risk is a **timeless page** that blends current, historical and draft
evidence. Two designs are feasible.

### 5.1 Design A — revision-scoped claim compilation

Claims are compiled from revision-scoped chunks and persisted with their
`supporting_revision_id`. The page **view** is assembled dynamically at query
time from claims whose revision is in `eligible_revision_ids`. No query-time LLM.

- **Authority activation:** changes only which claims are visible. No
  recompilation, no re-embedding, no page-hash change.
- **Rebuild fan-out:** zero on authority change. On a source-revision change,
  only pages whose input chunks include that revision recompile.
- **Stale-page risk:** structurally low — nothing is stored that depends on
  authority state.
- **Page-hash behaviour:** page hash is a function of (inputs, prompt version,
  model, contract version) only. Stable across authority changes — assertable by
  test.
- **Historical/draft queries:** work by construction; the same page renders a
  different eligible claim set per intent.
- **Summary validity:** the hard part. Solved by §3.5 sentence-level summaries
  plus **deterministic authority-scoped composition**: at query time, drop every
  summary sentence not all of whose `supported_claim_ids` are eligible.

### 5.2 Design B — authority-snapshot page compilation

Pages are compiled against an explicit eligible-revision snapshot, and the
snapshot hash is persisted with the page. Regeneration is triggered when
authority state changes.

- **Authority activation:** invalidates every page whose snapshot included an
  affected revision → **recompilation and re-embedding**, i.e. model calls
  triggered by an authority event.
- **Rebuild fan-out:** potentially large and hard to bound; one activation can
  touch most pages.
- **Stale-page risk:** high and *silent* — a page can look authoritative while
  its snapshot is obsolete.
- **Page-hash behaviour:** hash depends on authority state; the "authority is
  query-time, never stored" invariant is broken.
- **Historical/draft queries:** need either a separate snapshot per intent
  (combinatorial) or are unsupported.
- **Summary validity:** better — the summary is natively fluent for exactly one
  authority scope.

### 5.3 Recommendation: **Design A**

Design B's only real advantage is a more fluent holistic summary. It buys that
with a stored authority dependency, unbounded rebuild fan-out, silent staleness,
authority-dependent page hashes, and LLM calls fired by authority events — and it
contradicts the repo-wide invariant that authority is resolved at query time and
never stored. That is not a trade worth making for prose fluency.

**Design A is recommended. Only Design A will be implemented.**

**Honest cost of Design A, stated plainly:** the eligible-scope summary is
composed by *filtering* sentences, not by regenerating them. When some claims
become ineligible, the remaining summary can read as terse or disjointed, and it
is never re-smoothed for the eligible scope (that would require a query-time LLM,
which is excluded by §16). A page is therefore permitted to render a *shorter*
summary under a narrower authority scope, but is **never** permitted to render an
unqualified mixture of current and superseded claims. If every summary sentence
is dropped, the page renders "no summary available for this authority scope"
rather than falling back to the unfiltered text. Summary-degradation rate under
each intent is a reported metric (§8D).

---

## 6. Embedding and retrieval design

**No new embedding model. No reranker.** Existing provider only.

### 6.1 Payloads

| Mode | Payload | New embeddings |
|---|---|---|
| **V** | existing `CanonicalChunk.retrieval_text` embedding | 0 |
| **W0** | the **same** chunk embedding (section == chunk). *This does not create a materially new retrieval representation* (§2.2). | 0 |
| **W1** | **page-facet payload** (§6.2) | 1 per (page, revision) facet |

### 6.2 The W1 page-facet payload

Rather than one embedding per page, W1 embeds one **facet per
`(page_key, document_revision_id)`**, composed in a fixed, declared order:

```
display_title
+ supported aliases (sorted)
+ accepted claim_texts for this revision (sorted by claim_id)
+ summary sentences fully supported by those claims
+ selected source headings for this revision
+ stable source identifiers occurring in this facet
```

Every component is labelled `source_derived` or `model_derived` in the stored
payload manifest.

**Why facets rather than one page embedding.** A whole-page embedding mixes
claims from superseded and effective revisions into one vector, so page *ranking*
becomes authority-blind and a page can be discovered largely on the strength of
ineligible content. Facets keyed by `document_revision_id` allow the **existing
authority-first pattern** — `document_revision_id IN (:eligible)` in the same SQL
statement as `ORDER BY embedding <=> :q LIMIT :k` — to apply unchanged. Page
score = max over its eligible facets. Facet count is bounded by
(pages × revisions containing that identity), which on this corpus is small.

*Rejected alternative:* one authority-blind page embedding with authority applied
only when collecting chunks. Cheaper, but it makes discovery authority-blind and
weakens the leakage argument. *Rejected alternative:* one embedding per
(page, authority-scope) — combinatorial, and stores authority state.

**Recorded with every W1 embedding:** payload text; payload SHA-256; page
generation hash; page compiler model identity; compiler prompt version + prompt
SHA-256; embedding model; embedding dimension; generation timestamp; source chunk
IDs; source revision IDs.

### 6.3 Regeneration policy

| Trigger | Recompile page? | Re-embed facet? |
|---|---|---|
| Source revision changes | **Yes**, for pages whose input chunks include it | Yes, affected facets |
| An accepted claim changes | **Yes** (it is an output of compilation) | Yes, that facet |
| Compiler model changes | **Yes**, all pages (recorded as a new compiler generation) | Yes, all |
| Compiler prompt changes | **Yes**, all pages | Yes, all |
| **Authority state changes only** | **No** | **No** — view-only change (asserted by a hard test) |

### 6.4 W1 retrieval flow

```
query
 → resolve_query_scope(intent, as_of_date) → eligible_revision_ids
 → SQL: page_facet WHERE document_revision_id IN (:eligible)
        ORDER BY embedding <=> :q LIMIT P          -- top page facets
 → group facets to pages, page score = max eligible facet score, take top P_pages
 → collect accepted, eligible claims from those pages
 → union their supporting_chunk_ids  → candidate chunk set (cap C)
 → rank candidates by cosine(query, existing chunk embedding)
 → return top K original CanonicalChunks           -- same K as V
 → score with the frozen Stage 7B.0 evaluator
```

**Global bounds, declared before the run and never tuned per question:**
`P_pages` (top pages, proposed **5**), `C` (max candidate chunks carried into the
final ranking, proposed **50**), `K` = **exactly the same final K as V**.

**No backfill.** If the page layer yields fewer than K candidate chunks, W1
returns fewer than K. Topping up from V would silently blend the two systems and
inflate W1's measured coverage. Short result lists are a genuine property of the
design and are reported as such.

**Excluded from the flow:** query-time LLM, reranker, router, query
decomposition, Graph traversal, per-question tuning. Generated summaries and
claim texts **never** count as source evidence; only cited `CanonicalChunk`s do.

---

## 7. Navigation design

### 7.1 Link types

| Type | Meaning | Determinism | Asserts a relationship? |
|---|---|---|---|
| `structural` | document / page / section hierarchy | deterministic | no |
| `exact_anchor` | the same literal source-backed anchor appears elsewhere | deterministic | **no** |
| `source_cited_model_derived` | compiler proposes a related page + relationship label, citing accepted claims and source chunks | model-derived, validated | yes, but **model-derived, auditable, replaceable** |
| `advisory_semantic` | cosine-nearest page facets above a fixed threshold | deterministic given embeddings | **no** |

`is_authoritative_lineage = False` on **all** link types, always. A
`source_cited_model_derived` link is **not** equivalent to an authoritative
registry edge, and generic cosine-nearest-neighbour links are **never** labelled
lineage. Advisory semantic links are evaluated in a **separate configuration**
from source-cited links, so their contribution can never be folded into the
source-backed navigation result.

### 7.2 Configurations compared

- `N_W0` = `structural` + `exact_anchor` (W0 navigation).
- `N_W1` = `structural` + `source_cited_model_derived` (W1 navigation).
- `N_advisory` = either of the above **+** `advisory_semantic`, reported
  separately as marginal contribution only.

### 7.3 Branch prioritization — and its honest limit

Click budget: one **global** budget declared before the run (proposed **6**),
never tuned per question. One click = one link traversal. Authority leakage along
any traversed link is a hard failure.

A **weak deterministic prioritizer** is available without any new model call:
outgoing links are ordered by (a) cosine between the already-computed query
embedding and the target page's eligible facet embedding, then (b) lexical
overlap between the link's `relationship_label` and the query, then (c) link type
priority, then (d) stable key order.

> **Stated as a limitation, not a capability:** *this is similarity ordering, not
> intent understanding.* It cannot reliably distinguish "which control satisfies
> O-31?" from "which procedure implements C-88?" when both targets are
> semantically close to the query, and `relationship_label` matching is purely
> lexical — it does not model direction or relation type. Where prioritization
> fails, the navigator degrades to deterministic breadth-first order, and that
> degradation is **reported as a limitation in the navigation results, not
> concealed inside BFS**. Fixing it properly would require a query-planning LLM
> or a typed relation registry, both explicitly out of scope (§17).

---

## 8. Benchmark contract

Dimensions are kept separate and never averaged into a single score.

### 8.A Page compilation quality (W1 only)

Measured against the frozen facts **only after page generation is complete**. The
compiler never reads benchmark truth — enforced by AST tests over the compiler
and prompt modules and by a runtime guard that fails the run if truth objects
enter the compiler's call path.

Metrics: expected-fact recall in accepted claims; accepted-claim precision;
unsupported claim count; **citation validity** (deterministic); **citation
entailment/claim correctness** (frozen-fact match + owner adjudication of a
deterministic sample, §4.3); omitted relationship count; entity identity
accuracy; alias accuracy; **false merge count (target 0)**; contradictory-claim
handling counts (`duplicate` / `revision_divergent` / `contradictory`); summary
claim coverage; summary unsupported-statement count (target 0 by construction —
any non-zero is a validator defect); related-page link precision and recall;
source provenance completeness; revision/authority contamination; generation
failures; validation rejection counts by reason.

### 8.B Retrieval quality (V vs W0 vs W1)

Same questions; same intent and `as_of_date`; same eligible revisions; **same
final source-chunk K**; **same frozen Stage 7B.0 evaluator**; zero query-time
LLM; no per-question tuning.

Reported per mode and per question: required-fact coverage@K;
all-required-retrieved@K; complete-chain represented; MRR; nDCG@K; forbidden-fact
hits; authority-leakage count (**must be 0**); evidence-document diversity;
solved/partial/failed; and an explicit **per-question gains and regressions**
table (W1 vs V, W1 vs W0, W0 vs V).

**V is not rerun, rescored, or altered** — the frozen Stage 7B.0 results and
evaluator are loaded read-only, with a rerun-equality verification step only if
exact benchmark parity requires it (the same discipline 7B.2a used for the frozen
G projection).

### 8.C Navigation quality (`N_W0` vs `N_W1`)

Required-evidence reachability; complete-chain navigability; minimum clicks to
required evidence; branch count; irrelevant-destination count; ambiguity rate;
authority leakage (**must be 0**); forbidden-fact exposure; source-backed vs
advisory-link contribution (marginal gain of `N_advisory`); navigation-path
explainability (every click cites an `anchor_id` or a `claim_id` + `source_ref`);
prioritizer-degradation rate (§7.3). Primary targets Q04/Q06/Q07. Semantic
similarity alone is **never** treated as verified lineage.

### 8.D User-facing page quality (rubric, not impressions)

A fixed sample (proposed **6 pages**, selected deterministically by hash, not
cherry-picked) rendered for W0 and W1, presented **blind to mode label in
deterministic order**, scored 0–2 on each of: readability; ability to understand
*why* sources are connected; visibility of source vs model-derived content;
citation usability; revision clarity; exception/qualification preservation;
usefulness to a business user; usefulness to a downstream agent. Scored by the
owner (open question **Q10** covers who scores and whether a second rater is
required). A deterministic mechanical proxy is reported alongside — citation
density, unsupported-sentence count, summary-degradation rate per intent — but
**never substituted for the rubric**.

### 8.E Cost and maintainability

Implementation surface (modules, LOC, tables); new tables; **page-generation
calls; input/output tokens; dollar cost** (via the existing
`estimate_cost_usd()`, reporting `None` rather than a fabricated figure for an
unpriced model); build latency; retrieval latency (V vs W0 vs W1, warm); page and
embedding storage; validation rejection rate; reprocessing cost after a source
change, after an authority change, and after a model/prompt change (three
separate numbers); output stability across repeated runs (§8F); debugging
difficulty; stale-page risk; operational dependencies.

> **Stated explicitly:** *lower maintenance will not be claimed merely because
> pages are human-readable.* W1's ledger must carry its compiler, prompt
> versioning, validator, rejection triage, regeneration policy and model
> dependency as costs, and be compared honestly against both V (near-zero
> marginal) and the frozen Graph/Hybrid ledger from 7B.

**Budget ceiling.** A per-run call/token/dollar ceiling is declared before the
run; exceeding it aborts the run rather than silently overrunning. Order-of-
magnitude expectation on this corpus (to be replaced by measurement, not quoted
as a result): tens of pages × a few thousand input tokens at `gpt-4o-mini`
pricing → well under one dollar per full compilation run, ×N runs for §8F.

### 8.F Repeatability experiment

A single generation run is insufficient. **N repeated full compilation runs**
(proposed **N = 3**) with identical model, prompt, source chunks, configuration
and authority scope, at `temperature = 0` — noting the repo's own recorded
caveat that this is the lowest-variance setting available and **not** a
determinism guarantee for a hosted model.

Measured across runs: page identity stability; claim-set stability (Jaccard over
normalized `(subject, predicate, object, sorted supporting_chunk_ids)`); citation
stability; alias stability; summary stability; link stability; fact-recall
variance; unsupported-claim variance; token and latency variance.

**Textual summaries are not required to be byte-identical.** Structured accepted
claims and citations must meet a declared threshold — proposed: page identity set
**100% identical**, accepted-claim set pairwise Jaccard **≥ 0.90**, citation sets
on matched claims **≥ 0.95 exact**, false-merge count **0 in every run**.
Thresholds are declared before the run and are owner-approval item **Q8**.

---

## 9. Decision gates and hard safety

### 9.1 Hard safety requirements (pass/fail preconditions)

Any retained W1 mode must demonstrate: original chunks remain the sole
authoritative evidence; zero authority leakage; zero invalid source references;
complete claim-level provenance; every accepted claim has exact supporting source
spans; no unsupported summary sentence; model-derived and source-derived content
remain visibly separate; no silent entity merge (C-88/C-88A included); no
timeless current/effective flag; no Graph dependency; no benchmark-truth access
during generation or retrieval; no query-time LLM in the Stage 7C representation
benchmark; the same final source-evidence K; full model/prompt/input/output/cost
provenance; deterministic validation; an explicit regeneration policy.

**No mode failing any hard-safety condition may satisfy a retain gate**, however
good its retrieval numbers are.

### 9.2 Gates (immutable; declared before the measured run; no required winner)

**Gate A — Retain W1 semantic Wiki.** All hard-safety pass; W1 **materially
improves at least two of Q04/Q06/Q07**; **zero material regressions** on the
remaining questions; same final source-evidence K; zero authority leakage;
accepted-claim precision and citation correctness meet the declared thresholds;
repeatability (§8F) within the declared thresholds; user-facing page quality
(§8D) improves over W0; and cost/maintenance is justified relative to V.

**Gate B — Retain W0 only, as a source-navigation UI.** W1 fails to justify
itself; W0 provides useful revision / provenance / exact-anchor navigation; W0
maintenance remains low; and **W0 is not represented as a superior semantic
retriever** (its retrieval is reported as ≈ V, by construction).

**Gate C — Do not retain a Wiki projection.** W1 does not materially improve
retrieval or navigation; or page quality depends on unsupported generated prose;
or omissions or unstable links remain high; or authority-safe page composition
proves impractical; or the maintenance burden approaches or exceeds the
Graph/Hybrid path; or W0 adds insufficient value beyond the existing chunk/audit
viewer.

Evaluated in the fixed declared order **A → B → C**. Retrieval value, navigation
value, page quality and cost are kept distinct and are never averaged. No
outcome is encoded as required, and no test asserts that W1 > W0 > V.

---

## 10. Proposed repository changes

### 10.1 New package — `src/ingestion_bench/wiki_projection/`

| Module | Purpose | Stage |
|---|---|---|
| `model.py` | W0 + W1 Pydantic records (pages, sections, anchors, postings, links, claims, aliases, summary sentences, facets) | 7C.0 |
| `identifiers.py` | neutral lift of the `identifiers_in` regex — **no graph import** | 7C.0 |
| `anchor_extractor.py` | Lane 1 + Lane 2 deterministic extraction | 7C.0 |
| `projection_builder.py` | W0 pages/sections/postings/structural + exact-anchor links | 7C.0 |
| `store.py` / `pg_store.py` | in-memory + isolated Postgres; `IN (...)` before ranking (mirrors 7B.2a `vector_candidate_store.py`) | 7C.0 |
| `renderers.py` | page rendering with separated source / model-derived blocks | 7C.0 |
| `compiler_prompt.py` | `PROMPT_VERSION`, `prompt_sha256()`, page-scoped prompt builder | 7C.1 |
| `page_compiler.py` | `OpenAIPageCompiler` (lazy client, strict `json_schema`, `temperature=0`, usage capture) + `FakePageCompiler` | 7C.1 |
| `page_validation.py` | the §4 deterministic validator | 7C.1 |
| `page_assembler.py` | authority-scoped view assembly + summary-sentence filtering (§5.3) | 7C.1 |
| `embedding_payload.py` | facet payload composition + manifest | 7C.1 |
| `retriever.py` | W0 and W1 retrieval (§6.4) | 7C.2 |
| `navigator.py` | `N_W0` / `N_W1` / `N_advisory` (§7) | 7C.2 |
| `evaluator.py` | navigation + compilation metrics; imports the frozen 7B.0 `_evaluate_question` **by identity** for retrieval | 7C.2 |
| `benchmark_runner.py`, `report.py`, `config.py` | orchestration, scorecards, env-driven config | 7C.2 |

### 10.2 Other new files

`contracts/wiki_projection_v1.json` (W0 projection + anchor contract, frozen at
7C.0); `contracts/wiki_compiler_v1.json` (W1 schema, prompt version, model,
caps, budget ceiling, validation rules, gates — frozen at 7C.1);
`scripts/run_stage7c_wiki_probe.py` (with `--fake` / `--in-memory`, as 7B.2a);
`tests/test_wiki_projection.py`, `tests/test_wiki_page_compiler.py`,
`tests/test_wiki_page_validation.py`; `docs/STAGE7C_WIKI_DECISION.md`;
`reports/stage7c_wiki_{results.json, scorecard.md}`; `artifacts/stage7c/`
(gitignored, regenerable).

### 10.3 Database tables (isolated, prefixed `edib_stage7c_`)

`wiki_page`, `wiki_section` (indexed on `document_revision_id`), `wiki_anchor`,
`anchor_posting` (indexed on `anchor_id`, `document_revision_id`), `wiki_link`
(indexed on `from_ref`, `link_type`, `document_revision_id`), `wiki_page_claim`
(indexed on `page_key`, `supporting_revision_id`, `validation_status`),
`wiki_page_alias`, `wiki_page_summary_sentence`, `wiki_related_page_candidate`,
`wiki_page_facet_embedding` (`VECTOR(dim)`, indexed on `document_revision_id`),
`wiki_compilation_audit` (raw output, rejections + reasons, tokens, cost,
latency, model, prompt hash, run id). Authority filtering is **always**
`document_revision_id IN (:eligible)` in the same statement as ranking/LIMIT.

### 10.4 Reused read-only

`canonical/*`, `chunking/*`, `adapters/docling_standard` (5A),
`revision_authority/*` (7R.1), the 7R.2 authority-first SQL pattern, the 7B.0
corpus/facts/questions and its `_evaluate_question` evaluator,
`retrieval_baseline/embeddings.py`, and — as **pattern precedent, not import** —
`answer_baseline/`'s lazy-client, strict-schema, prompt-hash, usage/cost and
mechanical-validation approach.

### 10.5 Frozen code explicitly **not** modified

All of `graph_retrieval_benchmark/` and `hybrid_retrieval_benchmark/` (7B.2a,
Gate D), `cross_document_benchmark/` (7B.0 evaluator + corpus),
`revision_authority/` (7R.1), `revision_search_benchmark/` (7R.2),
`answer_baseline/` (7A.2), `canonical/`, `chunking/`, `adapters/`, and every
existing contract and report.

---

## 11. Stage decomposition and freeze boundaries

**Stage 7C.0 — Projection qualification (W0, deterministic, zero model calls).**
Build pages / sections / anchors / postings / structural + exact-anchor links.
Prove hard safety: full provenance, zero benchmark-truth access, C-88/C-88a
separation, deterministic and immutable rebuilds, correct authority views, no
Graph dependency. Produce projection manifests, rendered sample pages, build-side
ledger numbers, and the W0 ≈ V control measurement.
**Freeze: the projection contract and the builder.**

**Stage 7C.1 — LLM page-compilation qualification (W1 build side only).**
Compiler, prompt, schema, deterministic validator, authority-scoped assembly,
facet embeddings, the §8F repeatability experiment, and the §8A compilation-
quality metrics. **No retrieval or navigation comparison is run in 7C.1** — the
build side must qualify on its own before it is allowed to compete.
**Freeze: the compiler contract, prompt version + hash, model identity, accepted
page set, and facet embeddings.**

**Stage 7C.2 — Retrieval and navigation comparison (read-only).** Load the frozen
7C.0 projection and frozen 7C.1 pages/embeddings **read-only**; run V vs W0 vs
W1 (§8B), `N_W0` vs `N_W1` vs `N_advisory` (§8C), the page-quality rubric (§8D)
and the cost ledger (§8E); apply the §9 gates; write
`docs/STAGE7C_WIKI_DECISION.md`.

**Freeze boundary.** 7C.1 may not change the 7C.0 projection, anchor rules, or
page/link hashes. 7C.2 may not change the projection, the compiler, the prompt,
the accepted claim set, or any embedding — it only queries and measures. This is
the same 7B.0 → 7B.2a discipline.

**No additional variants after W1.** If W1 fails, the outcome is Gate B or Gate
C — **not** a second compiler, a new prompt, or a tuned retrieval flow. Any such
proposal is a new stage requiring fresh owner approval.

---

## 12. Open questions requiring owner approval

| # | Question | Recommendation |
|---|---|---|
| **Q1** | **Page identity model** — governed-subject pages keyed to the W0 anchor set, plus a capped `model_proposed` lane (§3.2)? | Approve; it makes W0/W1 directly comparable |
| **Q2** | **Single-revision claim restriction** (§3.4) — claims must cite chunks from one revision? | Approve for 7C; note the conjunctive multi-revision alternative as future work |
| **Q3** | **Model-proposed identity cap** — global cap of 10, always marked, measured separately? Or exclude the lane entirely from 7C? | Approve the capped lane; it is the only place W1 can show identity value beyond W0 |
| **Q4** | **Facet embeddings** (§6.2) — embed per `(page, revision)` rather than per page? | Approve; it preserves the authority-first SQL pattern |
| **Q5** | **Retrieval bounds** — `P_pages = 5`, `C = 50`, `K` = same as V, **no backfill**? | Approve, especially the no-backfill rule |
| **Q6** | **Click budget** — global **6**? | Approve |
| **Q7** | **Advisory semantic links** — reported as marginal contribution only, never gate-bearing? | Approve |
| **Q8** | **Repeatability** — N = 3; identity 100%, claim Jaccard ≥ 0.90, citations ≥ 0.95, false merges 0? | Approve or set your own thresholds — they must be declared before the run |
| **Q9** | **Compiler model and budget** — `gpt-4o-mini` (existing default) at `temperature = 0`, with a declared per-run dollar ceiling? Or `gpt-4o` for a stronger upper bound on achievable quality? | `gpt-4o-mini` first; it is the configured default and keeps the cost question honest |
| **Q10** | **Page-quality rubric (§8D)** — who scores? Owner alone, blind, on a 6-page deterministic sample? Or is a second rater required? | Owner alone for 7C, blind and deterministic; note single-rater as a stated limitation |
| **Q11** | **Claim-correctness adjudication (§4.3)** — claims matching no frozen fact cannot be auto-scored. Approve owner adjudication of a deterministic sample, and what sample size? | Deterministic sample of 20 claims |
| **Q12** | **Lane 2 phrase anchors** — in scope for 7C.0, or identifiers-only with Lane 2 gated as an option? | In scope: without it the `Payment Settlement` hop is unreachable and both W0 and W1 lose the worked example |
| **Q13** | **`identifiers_in` reuse** — approve lifting the ~4-line regex into a neutral module to avoid importing the frozen graph package? | Approve |
| **Q14** | **Summary degradation (§5.3)** — accept that a narrower authority scope yields a shorter, possibly disjointed summary, with "no summary available for this authority scope" as the floor? | Approve; the alternative requires a query-time LLM |

---

*Plan only (Revision 2). No code, tables, fixtures, embeddings, or LLM calls
created or run; no frozen stage modified. Stage 7B.2a remains frozen at Gate D.
Awaiting review and the §9/§12 decisions before any Stage 7C.0 work.*
