# Stage 7C Plan (Revision 6 — Wiki Hub Resilience experimental contract, attribution-corrected) — Deterministic Wiki Control (W0) and Bounded, Auditable LLM-Assisted Evidence Wiki (W1)

> ## STATUS: REVISION 6 — OWNER-APPROVED AND FROZEN
>
> **Revision 6 is the final pre-implementation contract for Stage 7C.** It was
> approved by the owner after the R6 attribution corrections and one subsequent
> terminology-only correction (the "zero-model" → "zero-W1-LLM" / "no W1-derived
> model output" / "deterministic D0" wording change recorded in §14.5). **No
> behaviour, gate, attribution rule, contract, measurement or architectural
> element was changed by that terminology correction.**
>
> **This document is now frozen.** Amending it requires fresh owner approval and
> a new revision number. Stage 7C.0, 7C.1 and 7C.2 implement *this* text.
>
> **Implementation status:** **Stage 7C.0 (deterministic Wiki projection
> qualification, W0) is IMPLEMENTED.** Stage 7C.1 (compilation) and Stage 7C.2
> (retrieval/navigation comparison) are **not started** and require fresh owner
> instruction. No LLM call has been made, no W1 facet has been compiled, no W1
> facet embedding exists, and no D0 / W1-D / W1-FULL benchmark comparison has been
> run. No frozen predecessor stage has been modified.
>
> **Revision history.** R1 ("Source-Backed Navigational Wiki Projection")
> defined `WikiSection` ≈ 1:1 with `CanonicalChunk` and reused the same chunk
> embeddings — making Wiki retrieval the same computation as Vector retrieval in
> a different wrapper. R2 reclassified that work as a control (**W0**) and
> introduced one bounded LLM-compiled evidence Wiki (**W1**). R3 corrected R2's
> remaining overclaims and cut its surface: the compilation unit became the
> facet, page identity became fully deterministic and shared between W0 and W1,
> links became derived rather than invented, summaries left the embedding
> payload, retrieval bounds became derived rather than picked, summary
> correctness stopped being asserted "by construction", and a hard qualification
> gate was placed between compilation and retention. R4 added six contract
> amendments: Gate Q governing retention eligibility rather than measurement
> permission; page-coherence validation; alias semantic adjudication;
> deterministic `display_title` / `page_type`; a mandatory extraction-vs-
> representation attribution section; and compiler-model parity with the frozen
> 7B.1 Real Graph extractor.
>
> **R5 (this revision) corrects what Stage 7C actually tests.** R4's W1
> hypothesis was that a missing claim only *perturbs a facet embedding* — i.e.
> resilience was located in **ranking**. Owner review identified this as
> materially wrong: under R4's own §6.4 flow, the candidate chunk set was
> reachable *only* through accepted claims, so a missing claim removed the
> evidence outright. R4's retrieval path made claims a **connectivity gate**,
> which is the same brittleness Graph has, wearing different clothes. R5
> relocates resilience to where the design can actually provide it —
> **deterministic page/facet membership and source anchors** — and rewrites the
> query-time flow, the facet representation, the metrics, the diagnostics and the
> gates accordingly. R5 changes **no** Stage 7C.0 architecture and reopens **no**
> frozen stage.
>
> **R6 (this revision) is not a redesign.** The R5 Wiki Hub Resilience
> architecture is accepted and is preserved intact — Stage 7C.0 unchanged,
> deterministic membership unchanged, facet/page/anchor/chunk semantics unchanged,
> the payload unchanged, the flow unchanged, Gate Q thresholds unchanged, A-2 and
> the regression rules unchanged. R6 applies six narrow **attribution**
> corrections identified in owner review, because R5's *measurement* could not
> support the conclusions R5's *gates* were about to draw from it (full
> diff-of-intent in §14.4): (1) R5 compared `N_W0` against `N_W1` while holding
> the **W1 enriched facet seed constant in both arms**, so it could establish
> whether claim-derived *routing* helped but could **never** establish that the
> W1 compiler was unnecessary — the W1 facet representation may already have
> contributed through **seed discovery**. R6 adds one deterministic,
> zero-W1-LLM ablation, **D0**, and names the three attribution arms **D0 / W1-D / W1-FULL**
> (§7.4); (2) it requires **two separate attribution deltas** plus the total
> (§9.5); (3) it corrects Gate A / Gate B attribution semantics so that Gate A
> measures W1-FULL against the *deployable, deterministic* D0 rather than against a
> same-W1-seed arm, and Gate B may not be selected from a same-seed comparison
> (§9.3); (4) it keeps the §8.G probe diagnostic-only, unchanged; (5) it corrects
> the candidate compute-ceiling derivation, which multiplied a **per-facet** chunk
> ceiling by a page count without bounding facets per page (§6.5); and (6) it
> renames Gate Q's `authority contamination` to **`revision-scope contamination`**,
> terminology only, because the compiler is authority-blind (§9.2). **D0 is not a
> new Wiki variant** and introduces no model, prompt, payload, embedding,
> reranker or planner.
>
> **What R5 changes** (full diff-of-intent in §14): the W1 hypothesis (§1.3); the
> role of claims, from connectivity gate to routing enrichment (§3.7, §6.4); the
> W1 query-time flow, now semantic-seed → hub expansion → structural navigation →
> bounded evidence (§6.4); a declared final-K evidence policy (§6.6); a
> semantically enriched facet payload that admits adjudicated-correct summary
> sentences and a deterministically selected identity-bearing source passage
> (§6.2); unification of retrieval and navigation for the W1 treatment (§7);
> a counterfactual claim-omission resilience diagnostic (§8.G); Wiki-specific
> resilience/ambiguity metrics (§8.H); a structural-attribution requirement
> alongside the existing extraction attribution (§9.5); explicit falsification
> outcomes (§9.6); and one Gate A amendment that **raises** the bar (§9.3).
>
> **Predecessor context.** Stage 7B.2a is **completed and frozen at Gate D**
> ("do not retain Graph in the online retrieval path"). Stage 7C does not reopen
> it. W1 **must not** consume Graph nodes, edges, aliases, paths, extraction
> output, H0/H1/H2, traversal, path ranking, RRF fusion, query planning, Neo4j,
> or any Graph benchmark contract or report at build or query time. W1 derives
> independently from the same frozen `CanonicalChunk`s. *(§1.3 cites the frozen
> 7B decision **document** to state W1's prior honestly; §9.4/§9.5 read the frozen
> 7B.1 **report files** at decision-writing time for the mandatory attribution
> comparisons; §3.8 pins the compiler model by **naming the value** recorded in
> the frozen graph config. All are documentation references — read-only, outside
> build and query time, never imports. No Graph module, table, artifact or output
> enters the W1 build path or the retrieval path.)*

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

### 0.1 Corpus shape — verified, and decisive for R5 (new in R5)

R5's design and its honest limits both follow from the *measured* shape of the
frozen corpus, read directly from
`contracts/cross_document_relationship_benchmark_v1.json` and
`docs/DEVIN_REBUILD_APPENDICES.json` (read-only). These facts are stated here
because several R5 sections are only interpretable against them, and because
§14.3 records what this corpus **cannot** test.

| Observed property | Value | Why it matters to R5 |
|---|---|---|
| Chunks per revision | **exactly 1**, for all 11 revisions | A facet's input set is one chunk. `F_max = 12` (§3.9) can never bind. Hub expansion is trivially cheap. |
| Final K | **per-question `top_k`**: 3 (Q01–Q04, Q08, Q09, Q11, Q12), 4 (Q05, Q10), 5 (Q06, Q07) | K is small; "same final K as V" is per-question, not global. |
| Q06 / Q07 | **5 required facts at K = 5** | **Zero slack.** Every returned chunk must be a required-fact chunk. One wasted slot = one lost required fact. |
| Q04 | 2 required facts at K = 3 | One slot of slack. |
| Required-fact chunk mapping | each required fact is carried by exactly the one chunk of its revision | **Path-establishing chunks and fact-carrying chunks coincide** on the target chain — so "protect the path" and "maximize coverage" do not conflict here (they could on other corpora). |
| Cross-document phrase anchors | **`Payment Settlement` only** | `Payment Reconciliation` occurs in a single logical document (`ADJACENT-DOMAIN`) and therefore **fails Lane 2's ≥2-distinct-document rule** (§2.1). |
| Heading paths | document-unique (`Application Portfolio > Registered Applications`, `Business Service Catalogue > Governed Services`, …) | No heading anchor bridges two logical documents. |
| Adjacent distractor domain | one revision (`adj_rev1`), one chunk, all five `F_adj_*` facts, no shared identifier and no qualifying shared phrase anchor with the target chain | The adjacent chain is **structurally unreachable by navigation** from the target chain. Forbidden-fact hits can essentially only enter through **semantic seeding**, not through traversal. |

**Two consequences, stated before any measurement.**

1. **Reachability on this corpus is not the hard part; bounded selection is.**
   The full APP-224510 → P-205 chain is reachable from a `Payment Settlement`
   seed using deterministic anchors alone, in 3–4 hops, yielding *exactly* the
   five required chunks. The binding constraint for Q06/Q07 is that K equals the
   number of required facts, so the experiment is really a test of **precision
   under a zero-slack evidence budget**, not of whether a path exists.
2. **This corpus cannot exercise the branching-ambiguity failure mode** that
   §1.3 identifies as Wiki's characteristic weakness. With 6 documents, 11
   single-chunk revisions, one cross-document phrase anchor and no bridge into
   the distractor domain, branching factors will be near-minimal **because the
   corpus is small, not because the representation is robust.** §8.H's branching
   metrics must therefore be reported as *descriptive of this corpus* and may
   **never** be quoted as evidence that Wiki navigation scales. This is recorded
   as a stated limitation in §14.3 and repeated in the decision record.

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
storage, owner adjudication effort, and ongoing diagnostics.

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
work a **control**, not a treatment — *for semantic retrieval*. R5 notes
separately (§7.4) that the same deterministic structure, when used for
**navigation inside the retrieval flow**, is not a control at all but a serious
competitor to W1, and must be measured as one.

### 1.3 The hypothesis under test — replaced in R5

#### 1.3.1 What R4 claimed, and why it was wrong

R4 stated the hypothesis as *"Page-centric semantic retrieval over compiled
evidence is more resilient to imperfect extraction than multi-hop traversal over
extracted edges"*, with the mechanism: *"a missing or wrong edge breaks a
traversal path outright, whereas a missing or wrong claim only perturbs a page
facet's embedding — the facet remains retrievable on its other accepted claims."*

**That mechanism was not implemented by R4's own retrieval flow.** R4 §6.4
reached evidence by: *select pages → collect **accepted claims** → union their
`supporting_chunk_ids` → candidate chunk set*. A chunk that no accepted claim
cited **could not enter the candidate set at all**. A missing claim therefore did
not degrade ranking; it deleted the evidence. R4's claims were a **connectivity
gate**, exactly as Graph's edges are — so R4's stated resilience advantage over
Graph did not exist, and the stage would have measured a differently-shaped
version of the same brittleness.

R5 corrects the design rather than the wording.

#### 1.3.2 The R5 hypothesis

> **An authority-aware Wiki uses semantically enriched, revision-scoped facet
> representations to discover entity-centric hubs; deterministic source
> membership preserves neighbourhood reachability; source anchors provide
> fallback connectivity between hubs; and source-cited LLM claims improve routing
> precision without being required for connectivity. Original `CanonicalChunk`s
> remain the only authoritative evidence.**

**This is a hypothesis, not an architectural conclusion.** Nothing in this plan
assumes Wiki is superior. The experiment is constructed so that it can — and on
several predeclared paths, plausibly will — **reject** it (§9.6).

#### 1.3.3 The expected failure modes, distinguished

| | Strength | Characteristic failure |
|---|---|---|
| **Graph** (frozen, 7B.1/7B.2a) | strong **typed** relationship traversal when extraction is correct: direction, relation type and endpoint are all explicit | a **missing inferred edge breaks reachability** outright; the path simply does not exist |
| **Wiki** (7C, this plan) | deterministic page/facet/anchor **membership** may preserve reachability despite a missing inferred claim; evidence can be reached structurally without a claim asserting it | **hub expansion introduces branch ambiguity and navigation cost**: more neighbours to consider, weaker signal about *which* neighbour, and evidence slots consumed by material reached but not required |

#### 1.3.4 The architectural question

> **Does Wiki's redundant, source-backed connectivity preserve transitive evidence
> often enough, and within a reasonable navigation/cost budget, to justify the
> representation layer?**

Redundancy is the proposed value and ambiguity is its price. The stage measures
both and lets §9.3's gates judge.

#### 1.3.5 W1's relationship to Graph — unchanged from R4, restated

> **W1 uses the same class of artifact as Stage 7B's Graph: LLM-inferred,
> source-cited relationships extracted from the same frozen chunks. Stage 7C
> does not claim, and must not be read as claiming, that Wiki-style extraction
> is inherently more reliable than Graph extraction.**

W1's claims and 7B's edge assertions are produced by the same kind of process and
are subject to the same failure modes: missed relationships, inconsistent
phrasing, and inferred predicates a citation cannot validate (§4.3). The frozen
7B closure record states this directly — *"The real graph is a single
non-deterministic LLM extraction snapshot; its missing/inconsistent edges cap what
any hybrid over it can recover"* — and that cap applies to W1 in equal measure.

**The R5 difference is that W1 is no longer supposed to beat that cap by
extracting better. It is supposed to survive the cap by not depending on
extraction for connectivity.** Whether it does is the experiment.

**The prior this sets, honestly.** 7B's frozen record notes that its
*perfect-graph* H0 improved Q06 complete-chain coverage 0.80 → 1.00, while the
*real* extracted graph improved 0 of 3 target questions, missing the edges behind
`F_adj_prc`, `F_prc_current` and `F_svc`. Structure demonstrably can help within
budget; **LLM extraction quality was the binding constraint.** R5's mechanism is
directly aimed at two of those three misses (§1.5.4) — and if it recovers them,
§9.5 must then determine whether the recovery came from W1's compiled claims or
from W0's deterministic projection, because the answer decides between Gate A and
Gate B.

### 1.4 The three modes

| | What it is | Retrieval unit | New model calls | Evaluated for |
|---|---|---|---|---|
| **V** | Frozen authority-aware Vector baseline over original chunks | chunk | 0 | Reference. Not rerun. |
| **W0** | Deterministic source Wiki **control** | chunk (via section) | 0 | Organization, provenance orientation, revision navigation, exact-anchor browsing, cost. **Not** semantic-retrieval improvement. Additionally, W0's projection and link set supply the two zero-claim arms of the unified flow (§7.4): **D0**, which carries no W1-derived model output and is the *deployable* deterministic Wiki, and **W1-D**, which borrows the W1 facet seed. Both *are* retrieval competitors and are measured as such. |
| **W1** | Bounded LLM-assisted source-grounded **evidence Wiki** | facet seed → page hub → structural navigation → cited chunks | ingestion-time only | Compilation quality, retrieval, navigation, resilience, page quality, repeatability, cost. |

**One** LLM Wiki variant. No W2, no compiler A/B, no prompt tournament (§12).
Neither **W1-D** (R4 §7.2's existing `N_W0` nesting level, evaluated inside the
unified flow with the W1 seed held constant) nor **D0** (new in R6, the same
deterministic link set driven by a seed carrying no W1-derived model output) is a new Wiki variant: they
are configurations of the same pipeline over the same frozen projection, adding
no model, prompt, payload, embedding, reranker or planner (§7.4, §12).

### 1.5 One complete worked example

The frozen corpus contains a chain across five documents:

```
APP-224510          --supports-->              Payment Settlement   (APP-PORTFOLIO rev2)
Payment Settlement  --is governed by-->        Obligation O-31      (SERVICE-CATALOGUE rev1)
Obligation O-31     --is satisfied by-->       Control C-88         (OBLIGATION-REGISTER rev2)
Control C-88        --is implemented through-->Procedure P-205      (CONTROL-LIBRARY rev2)
Procedure P-205     --is the-->                current operating procedure (PROCEDURE-CATALOGUE rev2)
```

#### 1.5.1 Under V

Stage 7B.0 measured Q04/Q06/Q07 as *partial*: top-K is dominated by chunks
lexically near the query, and the far end of the chain (P-205) falls outside K
because no single chunk contains both ends.

#### 1.5.2 Under W0

`Payment Settlement` (phrase) and `APP-224510`/`O-31`/`C-88`/`P-205`
(identifier) anchors are extracted deterministically. Semantic retrieval returns
what V returned — same embeddings. *Navigation* works: APP-PORTFOLIO → click
`Payment Settlement` → SERVICE-CATALOGUE → click `O-31` → OBLIGATION-REGISTER →
click `C-88` → CONTROL-LIBRARY → click `P-205` → PROCEDURE-CATALOGUE. Four
clicks, every hop source-backed — but each click means only *"this literal string
also appears here."*

#### 1.5.3 Under W1 — the facet record (unchanged from R4)

The compilation unit is the **facet** `(page_key, document_revision_id)`. For
`(IDENT:O-31, OBLIGATION-REGISTER:rev2)` the compiler sees only OBLIGATION-
REGISTER rev2 chunks containing `O-31`, and the **assembled facet record** is
(abridged, post-validation):

```jsonc
{
  // ---- deterministic assembly metadata (NOT model output) ----
  "page_key": "IDENT:O-31",
  "document_revision_id": "OBLIGATION-REGISTER:rev2",
  "display_title": "Obligation O-31",
  "page_type": "governed_identifier",
  "input_chunk_ids": ["chunk_obl_0003"],

  // ---- model structured output: aliases + claims + summary_sentences only ----
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

Note also what is **not model output**: `page_key`, `document_revision_id`,
`display_title`, `page_type` and `input_chunk_ids` are deterministic compiler
*inputs* and assembly metadata derived from the frozen W0 anchor / page-identity
contract (§3.2). **The LLM structured output is exactly three fields: `aliases`,
`claims`, `summary_sentences`** (§3.7, §10.2 `wiki_compiler_v1.json`).

The single claim also satisfies **page coherence** (§4.1.15): its normalized
subject `O-31` equals this facet's normalized page identity. A claim such as
*"C-88 is implemented through P-205"* appearing on the `IDENT:O-31` facet would
involve neither endpoint of this page's identity and would be classified
`out_of_page_scope` — retained in audit, not accepted, not embedded, unable to
support a summary or derive a link.

The link `IDENT:O-31 --is satisfied by--> IDENT:C-88` is produced
**deterministically** from `clm_obl_rev2_1`, because `C-88` normalizes to an
existing page key.

#### 1.5.4 Under W1 — what R5 changes, and the two facts it targets

R4 stopped the example at "retrieval walks: facets → pages → accepted claims →
cited chunks". **R5 replaces that walk** (§6.4). The difference is best shown on
the two chain facts the frozen 7B.1 Real Graph **missed**:

**`F_svc` — "The Payment Settlement business service is governed by Obligation
O-31."** (`SERVICE-CATALOGUE:svc_rev1`; Graph missed this edge.)
The page `PHRASE:payment settlement` has a facet at `SERVICE-CATALOGUE:svc_rev1`
**because the phrase deterministically occurs in that revision's source text** —
not because any claim was extracted from it. Under R5, expanding the
`PHRASE:payment settlement` hub returns that facet's source chunk **whether or
not the compiler produced a single claim about it.** Under R4, if the compiler
missed the claim, the chunk was unreachable.

**`F_prc_current` — "Procedure P-205 is the current operating procedure."**
(`PROCEDURE-CATALOGUE:prc_rev2`; Graph missed this edge.)
This one is sharper, because W1's *own validator* is hostile to it: §4.1.11's
closed status lexicon rejects `current` in a predicate or `claim_text` unless it
sits inside an exact quoted span, so a `has_status → "current operating
procedure"` claim is at material risk of demotion or rejection. Under R4 that
would have made `prc_rev2` unreachable — W1 would have failed on this fact **by
its own safety rule**. Under R5 the `IDENT:P-205` page has a deterministic facet
at `PROCEDURE-CATALOGUE:prc_rev2` because `P-205` occurs there, and hub expansion
returns the chunk regardless. **The claim layer and the connectivity layer are
now independent, which is the entire point of R5.**

**And the honest counterweight, stated in the same breath:** both recoveries are
achieved by **deterministic** membership and **deterministic** anchors — that is,
by **W0's** projection. Neither requires a single LLM claim. §9.5 therefore makes
"which layer did the work" a **mandatory** analysis.

> **R6 correction to that counterweight.** "Requires no LLM *claim*" is not the
> same as "requires no LLM". Reaching the chain still requires **landing on the
> right hub first**, and under R5 both zero-claim arms were seeded from the
> **W1 enriched facet representation** — itself a compiler output. R5 therefore
> would have concluded "the compiler was unnecessary" from an experiment in which
> the compiler was still supplying the seed. R6 adds **D0** (§7.4), which seeds
> from the existing V/W0 chunk embeddings and uses **no W1-derived model output
> anywhere**,
> and §9.3 makes Gate A conditional on the complete W1 treatment beating **D0** —
> not on claim-derived routing specifically. If W1's value turns out to come from
> semantic seed enrichment rather than from claim-derived routing, that is still
> W1 value and Gate A remains available; it is only when **D0 itself** delivers
> the transitive win that the correct outcome is **Gate B**. This plan says so in
> advance rather than discovering it during interpretation.

---

## 2. W0 — deterministic source Wiki control

### 2.1 Building blocks

**Unchanged from R4. Stage 7C.0 is not redesigned by R5.**

All records are Pydantic models; all IDs and hashes are SHA-256 over stable
inputs (never random, never run-scoped). The W0 projection build makes **zero LLM
calls** — it is pure text processing over frozen chunks. *(The separate W0
**semantic control** of §2.3 does invoke the existing embedding model, as V does;
"zero LLM calls" throughout this plan means no compiler/generative call, never
"no ML inference of any kind".)*

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

### 2.2 Deterministic membership is the structural capital (new in R5)

> **Facet and page membership MUST NOT depend on LLM claims, in any stage, at
> build time or query time.**

A source chunk belongs to a page's facet **because that page's deterministic
identity is present in that source material** — a Lane 1 identifier occurrence or
a Lane 2 phrase occurrence, recorded as an `AnchorPosting` at 7C.0 with zero
model calls. Membership is a property of the **text**, not of the compiler's
success.

Concretely, and as hard tests at 7C.0 and 7C.1:

- a facet exists if and only if its page identity has ≥1 posting in that
  revision;
- a facet with **zero accepted claims** is still a facet, still carries its
  source chunks, still carries its anchors, and is still expandable and
  traversable;
- deleting, demoting or rejecting every claim on a facet changes **no**
  membership, **no** posting, and **no** anchor;
- an authority change alters only which facets are *visible*, never which chunks
  belong to them.

**This is the structural capital whose resilience Stage 7C tests.** R4 owned this
property at build time and then discarded it at query time by routing all
evidence through accepted claims (§1.3.1). R5 keeps it end to end.

### 2.3 W0 retrieval

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

> **R5 boundary, stated to prevent a category error.** The sentence above is
> about **W0 as a semantic retriever** and remains true and ungated. It is *not*
> a statement about the deterministic-link arms of the unified flow (§7.4) —
> **W1-D** (W1 facet seed + W0 link set) and **D0** (chunk-embedding seed + W0
> link set) — both of which are genuine retrieval treatments and are expected on
> this corpus to be **strong**. Confusing them with W0 semantic retrieval would
> let a hub-expansion win be reported as a chunk-vector result; confusing **W1-D**
> with **D0** would let a *W1-seeded* win be reported as a *deterministic D0* one.
> §9.3 and §9.5 exist to prevent both errors.

### 2.4 W0 navigation, expected value, and limitations

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

This makes three properties **structural rather than merely validated**:

| Property | R2 | R3+ |
|---|---|---|
| Claims are single-revision | a validation rule | the compiler cannot see another revision |
| No current/historical blending | a validation rule | structurally impossible |
| Facet embedding ↔ compilation unit | two concepts to keep aligned | one and the same unit |

Truth-isolation is enforced by AST tests over the compiler and prompt modules
*and* a runtime guard that fails the run if truth objects enter the compiler's
call path.

**R5 addition:** the facet is the compilation unit and the embedding unit, but it
is **not** the membership unit's owner — membership is fixed by §2.2 before the
compiler runs and is unaffected by what the compiler returns.

### 3.2 Page identity — deterministic, and identical for W0 and W1

**Unchanged from R4.**

> **Page identities are produced by the deterministic extractor of §2.1 and are
> byte-identical for W0 and W1.** The LLM does not create page identities.

| Kind | Source |
|---|---|
| `governed_identifier` | Lane 1 identifier anchors |
| `business_topic` | Lane 2 phrase anchors |

`page_key = "{kind}:{normalized_identity}"` — e.g. `IDENT:O-31`,
`PHRASE:payment settlement`.

**`display_title` and `page_type` are deterministic, not generated.** Both are
derived from the frozen W0 anchor / page-identity contract (§2.1, §10.2
`wiki_projection_v1.json`) and are computed by `identity.py` before any model
call:

| Field | Derivation | Determinism |
|---|---|---|
| `page_type` | `governed_identifier` for a Lane 1 identifier anchor, `business_topic` for a Lane 2 phrase anchor — i.e. the anchor's `anchor_kind` | fully deterministic |
| `display_title` | the anchor's frozen `display_text` (the anchor's canonical surface form under the W0 display rule), never re-worded | fully deterministic |

They are **compiler inputs and assembly metadata, not LLM-generated fields**. A
model-emitted title or page type is a schema violation and fails the facet.

> **The LLM structured output is limited to three fields: `aliases`, `claims`,
> `summary_sentences`.** Everything else on a facet record is deterministic —
> identity and metadata from §2.1/§3.2, membership from §2.2, links derived from
> claims (§3.7), validation status from §4.1.

**Model-proposed identities are excluded from page creation, embeddings,
retrieval, navigation, and every decision gate.** If the compiler names an entity
that is not an existing page key, that observation is written to the **audit
record only** (§10.3, `unresolved_identity_mentions`) as a recall diagnostic for a
possible future stage. It creates nothing and scores nothing.

Rationale: it makes the W0 and W1 page inventories identical, so the comparison
isolates exactly one variable — **page content representation** — and cannot be
confounded by a different page set. It also removes a whole class of
repeatability noise: run-to-run inventory churn (§8F) becomes impossible by
construction.

### 3.3 Collision and ambiguity handling

**Unchanged from R4.**

| Case | Rule |
|---|---|
| **C-88 vs C-88a** | Distinct keys via the `identifiers_in` uppercase rule (`C-88` / `C-88A`). Hard test at identity, facet, claim, alias, link, membership and embedding level. Never merged. |
| **Duplicate names** | If one normalized key resolves to occurrence sets with disjoint identifier context, pages are **kept separate** with a deterministic disambiguator from the sorted `logical_document_id` set; both flagged `identity_confidence = "ambiguous"`. |
| **Aliases** | `status ∈ {supported, uncertain}`. `supported` requires an exact quoted span **and** owner semantic adjudication on Run 1 (§4.5). An `uncertain` alias — or a `supported` alias adjudicated `incorrect`/`unverifiable` — may **never** merge pages, **never** satisfy an identifier-grounding check, **never** enter the embedding payload, and **never** participate in page-identity matching (§4.1.15). |
| **Abbreviations** | Alias proposals; same rule. No expansion dictionary. |
| **Uncertain identity match** | Separate page, marked ambiguous. **Silent merging is a hard-safety failure.** |
| **Same phrase, different concept** | Detected as disjoint-identifier-context and split; if undetectable, flagged ambiguous and outgoing links downgraded to advisory. |

### 3.4 Claims

**Unchanged from R4 in structure; changed in §3.7/§6.4 in role.**

One atomic assertion per claim: `claim_id`, `subject`, `predicate`, `object`,
`claim_text`, `supporting_chunk_ids`, `supporting_quotes`,
`derivation = "model_derived"`, `validation_status ∈ {accepted, rejected,
uncertain, out_of_page_scope}` (§4.1.15, §4.2). The `validation_status` value is
assigned by the deterministic validator, never by the model. The facet's
`document_revision_id` is the claim's revision — no per-claim revision field is
needed, because the compiler could not have seen another one.

Multi-document *chains* remain fully expressible as several single-revision
claims across sibling facets, which is exactly how §1.5 represents the
APP-224510 → P-205 chain.

### 3.5 Summaries — presentation, and (new in R5) bounded discovery

R4 excluded summary sentences from the embedding payload entirely. **R5 admits
them under a strict condition**, because R4 was too conservative for the
discovery step the new flow depends on: the seed must land on the right hub, and
an adjudicated-correct sentence is often the most query-shaped text a facet has.

Sentence-level records are unchanged: `summary_sentences: [{sentence_id, text,
supported_claim_ids, derivation}]`. Every sentence must reference ≥1 accepted
claim **on the same facet**.

> **A summary sentence may enter the W1 facet semantic payload (§6.2) only after
> the existing Run-1 owner adjudication (§4.6) marks it `correct`. Sentences
> adjudicated `incorrect` or `unverifiable` never enter any embedding.**

**Summaries remain non-authoritative.** They are never evidence, never returned
as an answer, never counted toward coverage, and never substitute for a
`CanonicalChunk`. Their only new power is to help the seed step find the right
hub. Authority stays with source chunks throughout.

**Three costs of this change, recorded rather than glossed:**

1. **A summary defect can now move a retrieval number.** R4's §3.5 guaranteed it
   could not. That guarantee is deliberately traded for discovery quality, and
   the mitigation is the adjudication gate above plus §9.2's Q-7 (`0 incorrect
   sentences`), not an argument that defects are impossible.
2. **The W1 representation is no longer reproducible from (source, model, prompt)
   alone** — it now also depends on a recorded human adjudication artifact. This
   is a real operational dependency and is carried as a cost in §8E, not as a
   footnote. The adjudication verdicts are persisted, versioned and replayable
   (§10.3 `compilation_audit`), so the representation remains *deterministically
   reconstructible* given the verdict set; it is not reconstructible without it.
3. **Partial double-counting with claims.** R3 removed summaries from the payload
   partly because a summary derived from claims that are themselves in the
   payload double-counts the same content. R5 accepts that objection and bounds
   it: a summary sentence whose normalized text is **exactly equal** to an
   accepted `claim_text` already in the payload is dropped by a deterministic
   dedupe (§6.2). Residual near-duplication is accepted, with the reason stated:
   the payload's job is now **discovery recall of the correct hub**, not
   evidence, and reinforcing a page's own identity terms cannot promote anything
   to evidence status. This is a representation trade-off, not a correctness one.

### 3.6 Aliases

As §3.3. Aliases enter the embedding payload **only when `status == "supported"`
and the alias has passed owner semantic adjudication** (§4.5), and only for that
facet's revision. Span validity and semantic correctness are separate properties
and are reported separately; span validity alone never qualifies an alias for the
payload or for page-identity matching.

### 3.7 Links — derived, not invented; and no longer a connectivity gate

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
predicate string**. An endpoint that resolves to no page key emits no link and is
counted as `unlinkable_claim_endpoint` — a reported recall diagnostic.

#### 3.7.1 What a claim-derived link may and may not do (new in R5)

**A claim-derived link MAY provide:**

- relationship **type** (the verbatim predicate);
- traversal **direction** (`forward` / `inverse`);
- **routing priority** (§7.3 ordering);
- **explanation** for a rendered hop ("because rev2 says *O-31 is satisfied by
  C-88*");
- **source citations** for that hop.

**Failure to extract a claim MUST NOT remove:**

- the source facet;
- its original source chunks;
- its deterministic anchors;
- exact-anchor navigation available from those source chunks.

Therefore, as a design invariant with hard tests:

```
claim exists    → richer, more precise, explainable navigation
claim missing   → navigation degrades to deterministic anchor fallback
                → connectivity may still survive
```

Two further consequences, unchanged from R4 and still true: link quality is
**bounded by claim quality by construction**, so link precision is a *derived*
measure rather than an independent LLM output; and the compiler's output schema
is exactly **aliases + claims + summary sentences**, which is the whole of what it
is trusted to produce.

**The graceful-degradation property above is not asserted — it is measured**, by
the truth-free zero-claim arms **W1-D** and **D0** (§7.4) and by the
counterfactual probe (§8.G, truth-informed).

### 3.8 What makes W1 "bounded"

One compiler, one prompt version, one model, one structured schema, strict
JSON-schema output mode, `temperature = 0`, no free prose as a primary persisted
field, no LLM-created page identities, no LLM-generated `display_title` or
`page_type` (§3.2), no LLM-invented links, **no LLM-determined membership
(§2.2)**, no query-time LLM, no compiler-visible benchmark truth, no cross-facet
context, and the hard ceilings of §3.9.

**Compiler-model parity — frozen.**

> **The initial measured W1 compiler must use the same model as the frozen Stage
> 7B.1 Real Graph extractor: `gpt-4o-mini` at `temperature = 0`**
> (`graph_retrieval_benchmark/config.py:25`, `DEFAULT_EXTRACTION_MODEL`).

**The rationale is methodological parity, not cost and not
configured-default convenience.** §9.4 requires W1's accepted-claim
recall/precision to be compared against 7B.1's frozen edge recall/precision
(0.80 / 0.86) before any retrieval improvement is attributed to page-centric
consumption. That comparison is only interpretable if extraction capability is
held constant across the two systems; a stronger W1 model would confound
representation with extraction capability and make the attribution analysis
unresolvable. Cost happens to fall out favourably, but it is not the reason and
must not be reported as the reason.

**No stronger W1 model is introduced in Stage 7C.** A capability-ceiling probe on
a stronger model is a separate stage requiring fresh owner approval (§11, §12); it
may not be added to 7C as a variant. If the environment resolves the compiler
model to anything other than the 7B.1 extraction model, the run fails before the
first call.

### 3.9 Hard ceilings (input and output, per facet)

Declared before the run; **not** tunable per facet or per question.

| Ceiling | Proposed value | Breach behaviour |
|---|---|---|
| Input chunks per facet (`F_max`) | **12** | fails the facet |
| Input tokens per facet | **8,000** | fails the facet |
| Accepted + uncertain claims per facet | **20** | fails the facet |
| Aliases per facet | **8** | fails the facet |
| Summary sentences per facet | **5** | fails the facet |
| Output tokens per facet | **4,000** | fails the facet |
| **Facet payload characters (`PAY_max`, new in R5)** | **4,000** | **deterministic drop, reported — see below** |
| Whole-run dollar ceiling | declared before the run (**Q6**) | fails the run |

> **Breach behaviour for model input/output ceilings: exceeding any of them fails
> the facet, and a failed facet fails Stage 7C.1 qualification (§9.2).**
> There is **no batching, no map-reduce, no hierarchical summarization, no
> truncate-and-continue, and no ceiling raise mid-run.**

Rationale: if the corpus does not fit a bounded compiler, *that is the finding*.
Engineering around it inside the POC would silently convert "one bounded model
call per facet" into a multi-stage summarization pipeline with its own error
modes and its own cost curve — the exact complexity the stage exists to price.

**`PAY_max` is deliberately the one exception, and here is why.** The facet
payload (§6.2) is composed **deterministically from already-validated material**;
its length is a property of the corpus and the composition rule, not of model
behaviour. Failing a facet — and therefore the stage — because its own validated
content is verbose would punish compilation quality for a formatting fact. So
payload overflow instead triggers a **declared, fixed drop order** (§6.2), is
counted as `payload_truncated`, and is reported per facet in §8A. It is **not**
tunable, **not** per-question, and **not** silent. On this corpus (§0.1: one
chunk per revision, 1–2 sentences each) it is not expected to bind at all; the
ceiling exists so that behaviour is defined rather than discovered.

---

## 4. Source-grounding and validation contract

**Preserved from R4 in full.** R5 changes no validation rule, no adjudication
requirement, no provenance rule, no alias control, no page-coherence rule, and no
source/model separation rule. The only R5 amendments are (a) the explicit
statement that validation outcomes never affect membership (§4.0), and (b) the
adjudication ordering note in §4.6 extended to cover summary-sentence payload
eligibility.

### 4.0 Validation governs claims, never membership (new in R5)

> **No validation outcome — `rejected`, `uncertain`, `out_of_page_scope`, a
> ceiling breach, a failed adjudication, or a total compilation failure on a
> facet — may remove or alter that facet's deterministic membership, its source
> chunks, its anchors, or its anchor postings.**

Validation decides what W1 may *assert* and *embed*. §2.2 decides what a page
*contains*. A facet whose every claim is rejected still holds its source chunks,
is still expanded by §6.4, and is still traversable by anchor. Hard test.

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
7. **C-88 and C-88A are not merged** at identity, facet, claim, alias, link,
   membership or embedding level.
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

    > **R5 note.** This rule is expected to demote or reject the natural claim
    > for `F_prc_current` ("Procedure P-205 is the **current** operating
    > procedure"). Under R4 that would have made the fact unreachable. Under R5
    > it does not, because membership is independent of claims (§2.2, §4.0). The
    > rule is therefore **kept unchanged** — it is a genuine safety invariant, and
    > R5 removes the reason it was dangerous. This interaction is called out
    > because it is one of the clearest demonstrations that R5's redesign is
    > load-bearing rather than cosmetic (§1.5.4).

12. **Duplicate and contradictory claims.** Normalize `(subject, predicate,
    object)`. Same triple within a facet → duplicate, deduped with both
    citations retained. Same `(subject, predicate)` with different `object`
    **within a facet** → `contradictory`; **both demoted to `uncertain`**,
    neither silently dropped, the pair reported. The same divergence *across*
    facets of different revisions is `revision_divergent` — expected evolution,
    both accepted, each revision-scoped.
13. All ceilings of §3.9 respected (with `PAY_max` handled per §3.9's stated
    exception).
14. Rejected outputs and **the reason for each rejection** persisted for audit;
    nothing discarded silently.
15. **Page coherence.** Every accepted claim on a facet must *directly involve
    that facet's page identity*:

    ```
    normalized_page_identity == normalized(claim.subject)
      OR
    normalized_page_identity == normalized(claim.object)
    ```

    Normalization is the same identity normalization that produced page keys
    (§3.2) — so `C-88` and `C-88A` never satisfy each other's comparison. A
    **validated supported alias** of the page identity may satisfy the same
    comparison in place of the identity itself; "validated" means `status ==
    "supported"` **and** passed semantic adjudication (§4.5). Aliases that are
    `uncertain`, or `supported` but adjudicated `incorrect`/`unverifiable`, may
    **not** be used for this match.

    A claim satisfying neither comparison is classified `out_of_page_scope`. Such
    a claim:

    - **is retained in audit** (`compilation_audit`, with its reason);
    - **is not accepted**;
    - **is not embedded** (excluded from the §6.2 payload);
    - **cannot support a summary sentence** (§4.1.8);
    - **cannot derive a navigation link** (§3.7);
    - **does not affect membership** (§4.0) — the facet keeps its chunks.

    The `out_of_page_scope` count is reported in the compilation metrics (§8A).

    *Rationale:* a facet is the compilation unit *and* the embedding unit
    (§3.1, §6.2). A claim about two other entities that merely co-occur in the
    facet's chunks would pull unrelated content into that page's vector, making
    the page retrievable on material it does not represent — quietly
    reintroducing the co-occurrence semantics that §2.4 identifies as W0's
    limitation. Coherence keeps the facet embedding a representation of *this
    page* under *this revision*. Cross-entity relationships remain fully
    expressible: they belong on the facets of the entities they are about, which
    is how §1.5's five-document chain is represented.

### 4.2 Acceptance and rejection behaviour

`accepted` → persisted; eligible for the embedding payload, for supporting a
summary sentence, and for deriving links. `uncertain` → persisted and **rendered
as uncertain**; excluded from the embedding payload; may not support a summary
sentence or derive a link. `out_of_page_scope` (§4.1.15) → persisted **in the
audit record only**, with its normalized subject/object and the page identity it
failed to match; never accepted, never embedded, never able to support a summary
or derive a link. It is counted and reported separately from `rejected`, because
it is a *scoping* outcome rather than a grounding failure. `rejected` → persisted
**in the audit record only**; never in the page view, never embedded. A facet
whose claims are all rejected is persisted as an empty facet with its rejection
ledger — never deleted, since deletion would hide the failure mode from §8E
**and would violate §4.0**.

### 4.3 Citation validity is not claim correctness

> **An exact-substring citation proves only that the cited passage exists and
> contains the quoted text. It does not prove that the model's inferred
> `predicate` accurately represents that passage.**

| Property | Definition | How measured |
|---|---|---|
| **Citation validity** | Cited chunk exists, is in facet scope, quote is an exact substring | **Deterministic**, 100% mechanical (§4.1.1–4.1.5) |
| **Claim correctness** | The `(subject, predicate, object)` faithfully represents the cited passage | **Not mechanically decidable.** Frozen-fact match **plus owner adjudication of every accepted claim** (§4.6) |

A run with 100% citation validity and poor claim correctness is a Gate C signal,
not a success.

### 4.4 Summary reference validity is not summary correctness

Claim-ID mapping proves only that a sentence *points at* accepted claims. It does
not prove the sentence faithfully represents them: a sentence can cite two valid
claims and still overstate them, merge them into an unsupported composite, invert
a direction, or add a qualifier that appears in neither.

| Property | Definition | How measured |
|---|---|---|
| **Summary reference validity** | Every sentence references ≥1 accepted claim on the same facet | **Deterministic** (§4.1.8) |
| **Summary correctness** | The sentence faithfully represents exactly those claims — no addition, overstatement, merge error, or direction inversion | **Not mechanically decidable.** **Owner adjudication of every summary sentence** (§4.6) |

Both are reported separately. Neither substitutes for the other.

> **R5 raises the stakes on this section.** Under R4, summary correctness was a
> page-quality property with no retrieval consequence. Under R5 an
> adjudicated-`correct` sentence enters the facet payload (§3.5, §6.2), so
> **summary adjudication is now on the critical path for retrieval**, not only
> for §8D. Q-7's bar (`0 incorrect sentences`) is unchanged but is now
> load-bearing in a second way, and the effort is carried in §8E.

### 4.5 Alias span validity is not alias semantic correctness

`status == "supported"` proves only that the alias string appears verbatim in a
cited chunk of this facet. It does not prove the alias actually *names this
page's entity*.

| Property | Definition | How measured |
|---|---|---|
| **Alias span validity** | The alias string is an exact quoted substring of a cited chunk in this facet's declared input set | **Deterministic** (§4.1.3, §4.1.6) |
| **Alias semantic correctness** | The alias genuinely denotes *this facet's page identity* — not a related, broader, narrower, or adjacent entity | **Not mechanically decidable.** **Owner adjudication of every supported alias** (§4.6) |

This distinction has teeth because supported aliases do two load-bearing things:
they enter the **embedding payload** (§6.2), and they can satisfy **page-identity
matching** in the page-coherence check (§4.1.15).

> **A supported alias that fails semantic adjudication must not enter the
> embedding payload and must not participate in page-identity matching.** It is
> retained in the audit record with its adjudication reason, and it is rendered,
> if at all, only as an unaccepted observation.

**Supported-alias precision** = (supported aliases adjudicated `correct`) /
(supported aliases). Reported in §8A, gated in §9.2. **On this corpus the
requirement is `incorrect supported aliases = 0`.**

**Aliases never affect membership** (§4.0): an alias cannot add a chunk to a page
or remove one from it. Membership comes from anchor postings alone.

### 4.6 Adjudication scope

The corpus is small — 6 documents, 11 revisions, and a facet count in the tens.
Sampling is therefore unnecessary and would only add variance:

> **Every accepted claim, every summary sentence, and every supported alias is
> owner-adjudicated.**

Adjudication is performed on **Run 1 only** (§8F), recorded as
`correct | incorrect | unverifiable` with a reason, and persisted in the decision
record.

| Adjudicated object | Question the owner answers | Feeds |
|---|---|---|
| Accepted claim | Does `(subject, predicate, object)` faithfully represent the cited passage? (§4.3) | Claim correctness → §8A, Gate Q-5 |
| Summary sentence | Does the sentence faithfully represent exactly the claims it references? (§4.4) | Summary correctness → §8A, Gate Q-7; **and payload eligibility (§3.5, §6.2)** |
| Supported alias | Does this alias genuinely denote *this facet's page identity*? (§4.5) | Supported-alias precision → §8A, Gate Q-10; payload and page-identity-matching eligibility |

Adjudication happens **after** compilation and **before** any retrieval run — its
outputs are inputs to the §9.2 qualification gate, and the alias **and now
summary** verdicts determine payload composition (§6.2) and page-identity
matching (§4.1.15), so they must be settled before facet embeddings are written.

**Ordering, stated explicitly.** 7C.1 runs in three passes:

1. **Deterministic validation** (§4.1), using span-valid `supported` aliases for
   identifier grounding (§4.1.6) and page-identity matching (§4.1.15);
2. **Owner adjudication** (this section) of every accepted claim, summary
   sentence and supported alias;
3. **Deterministic re-validation**, which withdraws every alias that failed
   adjudication and re-applies §4.1.6 and §4.1.15 without it. A claim whose
   coherence rested *solely* on a withdrawn alias becomes `out_of_page_scope`;
   a claim whose identifier grounding rested solely on one is demoted per §4.2.
   **Summary sentences that failed adjudication are withdrawn from the payload
   composition set (§6.2) at this point** (new in R5). Counts are reported before
   and after pass 3.

**Facet embeddings are written only after pass 3.** Nothing that failed
adjudication reaches a vector, a summary, or a derived link. **Membership is
untouched by all three passes** (§4.0).

### 4.7 Source vs model-derived separation

Persisted and rendered in separate labelled blocks. **A — source-authoritative:**
original `source_text`, `source_refs`, revision identity, document provenance.
**B — model-derived:** aliases, claims, summaries, derived links and their
predicates. B is auditable, versioned, regenerable, replaceable, **never silently
promoted to source truth, and never sufficient evidence without its cited source
chunks**. Any final answer or benchmark fact resolves to A.

**Every component of the §6.2 payload is individually labelled `source_derived`
or `model_derived` and retains exact provenance** — including the new
identity-bearing source passage (source) and the new adjudicated summary
sentences (model).

---

## 5. Authority and revision model

**Unchanged from R4.**

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
  model, contract version, **adjudication verdict set**) only; stable across
  authority changes (hard test). *(R5 adds the verdict set to the hash inputs,
  because §3.5 makes the payload depend on it — see §8F.)*
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
triggered by authority events — and it contradicts a repo-wide invariant.

**Cost of A, stated plainly:** the eligible-scope summary is composed by
*filtering* sentences, not regenerating them. Under a narrower authority scope
the remaining summary can read as terse or disjointed, and it is never
re-smoothed. A page may render a *shorter* summary under a narrower scope but
**never** an unqualified mixture of current and superseded claims. If every
sentence is dropped, the page renders "no summary available for this authority
scope" rather than falling back to unfiltered text.

> **R5 amendment to this cost.** Because summary sentences now enter the facet
> payload (§3.5), summary filtering under a narrow authority scope affects
> **presentation only, not the embedding** — the embedding is built per facet,
> and a facet belongs to exactly one revision, so authority filtering removes the
> whole facet or none of it. The payload is never partially recomposed at query
> time. R4's claim that summary degradation "affects presentation only, never
> retrieval" therefore survives R5 intact, for a slightly different reason.
> Summary-degradation rate per intent is still reported (§8D).

---

## 6. Embedding and retrieval design

**No new embedding model. No reranker.** Existing provider only.

### 6.1 Payloads

| Mode | Payload | New embeddings |
|---|---|---|
| **V** | existing `CanonicalChunk.retrieval_text` embedding | 0 |
| **W0** | the **same** chunk embedding (section == chunk); *not a materially new retrieval representation* (§2.3) | 0 |
| **W1** | facet payload (§6.2) | 1 per facet |

### 6.2 The W1 facet semantic representation (revised in R5)

> **There is exactly ONE W1 facet semantic representation.** No variants, no A/B,
> no alternative embedding recipe (§12). It is revision-scoped and
> authority-filterable, exactly as in R4.

One embedding per `(page_key, document_revision_id)` — i.e. **one per compilation
unit** — composed in this **fixed declared order**:

| # | Component | Label | Source |
|---|---|---|---|
| 1 | `display_title` | `source_derived` | deterministic (§3.2) |
| 2 | validated supported aliases (`status == "supported"` **and** adjudicated `correct`, §4.5; sorted) | `model_derived` | compiler + adjudication |
| 3 | revision headings for this facet's chunks | `source_derived` | `heading_path` |
| 4 | stable source identifiers occurring in this facet (sorted, from lifted `identifiers_in`) | `source_derived` | source text |
| 5 | **deterministically selected identity-bearing source passage(s)** — new in R5 | `source_derived` | source text |
| 6 | accepted `claim_text`s for this facet (sorted by `claim_id`) — excludes `uncertain`, `rejected`, `out_of_page_scope` | `model_derived` | compiler + validator |
| 7 | **owner-adjudicated-`correct` summary sentences** (sorted by `sentence_id`) — new in R5 | `model_derived` | compiler + adjudication |

**Component 5 — the deterministic selection rule.** Declared before the run, not
tunable:

1. Consider this facet's input chunks in ascending `(chunk_index, chunk_id)`.
2. Within each, split `source_text` on the declared sentence boundary rule
   (single documented splitter, frozen in `wiki_projection_v1.json`).
3. Keep sentences that contain an occurrence of this page's identity — matched
   by **anchor posting `char_span`**, not by re-searching text, so the match is
   the same one that created membership (§2.2).
4. Take the first **2** such sentences in document order, each capped at 400
   characters, truncated at a word boundary with an explicit ellipsis marker.

This is the passage that made the page exist. It is `source_derived`, exactly
provenanced to `(chunk_id, char_span)`, and byte-stable.

**Component 7 — dedupe.** A summary sentence whose whitespace/case-normalized
text is **exactly equal** to a `claim_text` already present in component 6 is
dropped (§3.5, cost 3). Reported as `summary_payload_dedup_count`.

**Overflow — `PAY_max` drop order** (§3.9). If the composed payload exceeds
`PAY_max`, components are dropped **whole**, in this fixed order, until it fits:
**7, then 6, then 5, then 2**; components **1, 3 and 4 are never dropped** (they
are the page's identity and are what makes the facet findable at all). Each drop
is recorded per facet as `payload_truncated_components`. There is no partial
component, no per-question variation, and no re-ordering.

**Recorded with every W1 embedding:** payload text; payload SHA-256; per-component
manifest with `source_derived`/`model_derived` labels and provenance; facet
generation hash; **adjudication verdict-set hash** (new in R5, §5.1); compiler
model identity; prompt version + SHA-256; embedding model; embedding dimension;
generation timestamp; source chunk IDs; source revision ID; repeatability run ID
(always Run 1 for the frozen representation, §8F); `payload_truncated_components`;
`summary_payload_dedup_count`.

**Why facets rather than one page embedding.** A whole-page embedding mixes claims
from superseded and effective revisions into one vector, making page *ranking*
authority-blind so a page could be discovered largely on ineligible content.
Facets keyed by `document_revision_id` let the **existing authority-first
pattern** — `document_revision_id IN (:eligible)` in the same SQL statement as
`ORDER BY embedding <=> :q LIMIT :k` — apply unchanged.

> **A whole, authority-blind page embedding remains prohibited** (hard-safety,
> §9.1). There is no page vector of any kind.

**Honest note on what §6.2 buys on this corpus.** Because each revision is a
single 1–2 sentence chunk (§0.1), component 5 will in practice reproduce nearly
the whole chunk. The W1 facet vector is therefore **close to the V chunk vector
plus a title, aliases, claims and a summary**. This is deliberate — the seed step
should be at least as good as V at finding the right chunk — but it means
**semantic enrichment cannot be credited with much on this corpus**, and the seed
step is not where W1's differentiation will show. §9.5 must attribute accordingly.

### 6.3 The role of the page — stated precisely (new in R5)

R4's language occasionally read as if a page were a retrieval unit with its own
semantics. It is not, and R5 fixes the vocabulary because the whole flow depends
on it.

> **A page is an entity-centric INFORMATION HUB.**

| Concept | Role | Not |
|---|---|---|
| **Facet** `(page_key, revision)` | the **semantic landing unit** — the only thing with an embedding | not evidence, not a page |
| **Page identity** | the **grouping / expansion hub** — a key that gathers facets and exposes neighbours | **not a vector**; there is no page embedding |
| **Links and anchors** | the **movement / navigation mechanisms** between hubs | not evidence, not lineage |
| **`CanonicalChunk`** | the **authoritative evidence** — the only thing returned and scored | not derived, not regenerable |

If several eligible facets of one page match the query, the page may be assigned a
**seed-page priority** — proposed: `max` over that page's eligible-facet
similarities. This is a **grouping convenience for ordering hubs**, and it must be
called `seed_page_priority` in code, reports and the decision record. It is **not**
"semantic page retrieval" and must never be described as one.

### 6.4 W1 query-time flow (replaced in R5)

R4's flow is superseded for the reason given in §1.3.1. The R5 flow is:

```
query text  +  structured authority context (intent, as_of_date)
        │
        ▼
[1] resolve eligible revisions
        resolve_query_scope(intent, as_of_date) → eligible_revision_ids
        │
        ▼
[2] semantic search over ELIGIBLE FACET REPRESENTATIONS ONLY
        SQL: facet_embedding
             WHERE document_revision_id IN (:eligible)
             ORDER BY embedding <=> :q
        (authority filter and ranking in the SAME statement — §0 pattern)
        │
        ▼
[3] top seed facets  →  seed page identities
        page ordered by seed_page_priority = max eligible-facet similarity (§6.3)
        bounded by P_seed (§6.5)
        │
        ▼
[4] HUB EXPANSION: expand ALL eligible source facets of each selected page
        deterministic membership (§2.2) — no claim required
        │
        ▼
[5] collect authoritative source chunks on those facets
        │
        ▼
[6] discover neighbouring page identities from the visited hub, using:
        (a) claim-derived links, when available   → typed, directed, explained
        (b) deterministic exact/source-anchor links → fallback, untyped
        │
        ▼
[7] traverse to adjacent page hubs, under the global hop budget B (§7.3)
        branch order by the §7.3 prioritizer; all exposures recorded (§8.H)
        │
        ▼
[8] expand their eligible source facets  → back to [4] until B is exhausted
        │
        ▼
[9] collect original CanonicalChunks encountered along the structural path
        │
        ▼
[10] apply the FINAL-K EVIDENCE POLICY (§6.6)
        │
        ▼
     bounded final authoritative evidence set  (|set| ≤ K, same K as V)
        │
        ▼
     scored by the frozen Stage 7B.0 evaluator, unchanged
```

**Reading of the flow, stated so it cannot be misread:**

- **The semantic search discovers the seed. The Wiki structure performs the
  expansion and navigation after the seed.** Steps [4]–[9] contain no vector
  search over chunks.
- **There is no second global raw-chunk cosine search.** Evidence reached by a
  valid structural path is not re-authorized against the query. R4's
  `SCORE every candidate chunk against the query` step is **removed** as a
  gatekeeper.
- **Query similarity survives only as a predeclared branch-prioritization signal**
  (§7.3) and as the Tier-2 tie-break inside §6.6. It may **never** erase source
  evidence already reached through a valid structural path merely because that
  downstream chunk is semantically distant from the original query — which is
  exactly the failure that would have sunk Q06 (`F_prc_current`, whose chunk says
  nothing about applications).
- **No backfill.** If the flow yields fewer than K chunks, W1 returns fewer than
  K. Topping up from V would silently blend the two systems and inflate W1's
  measured coverage. Short lists are reported as `short_list`.

**Excluded:** query-time LLM, reranker, router, query decomposition, Graph
traversal, per-question tuning, whole-page vectors. Generated summaries and claim
texts **never** count as source evidence; only `CanonicalChunk`s do.

### 6.5 Bounds policy — derived, not picked (revised in R5)

R4 derived `P = K` and `C = P × F_max` for a flow that had no traversal. R5's flow
adds expansion, so the bounds are re-derived rather than carried over.

**Seed bound.** `P_seed = K`, unchanged in value and in derivation: the seed layer
exists to be **selective**, and permitting more seed pages than final evidence
slots removes that selectivity and degenerates W1 toward "rank everything
eligible", i.e. toward V.

**Seed processing order.** Seed pages are processed in descending
`seed_page_priority`. The **rank-1 seed page is the path origin** used by §6.6
Tier 1. Lower-ranked seeds are expanded only while hop budget remains and
contribute at Tier 2. `seed_rank_used` and `seed_pages_expanded` are reported.

*Why the rank-1 seed is privileged:* §6.6's Tier 1 protects **one** traversed
path, and a path has one origin. Deriving the origin from the ranking rather than
picking it keeps the rule non-tunable.

> **R6 note.** `seed_page_priority` is defined over **facet** similarities and is
> therefore available only to the W1 arms. The **D0** arm reads no facet
> embedding, so it substitutes the deterministic seed order of §7.4.2 step 5 and
> reports `seed_order_rule = "D0_posting_order"`. `P_seed = K`, the rank-1 seed as
> path origin, the hop budget, the §6.6 policy and the no-backfill rule are
> **identical across all three arms** — the seed *ordering rule* is the only thing
> that differs, and it differs because a W1-LLM-free arm cannot consult a
> W1-derived vector.

**Hop budget.** `B`, global, declared before the run (proposed **6**, §7.3),
never tuned per question. **One hop = one traversal from a visited page identity
to an adjacent page identity.** Expanding a page's own eligible facets (§6.4 step
[4]) is **not** a hop — it is deterministic membership, not movement — but its
cost is fully reported as branching and candidate counts (§8.H). The longest
target chain on this corpus is 4 hops (§1.5.2), so `B = 6` leaves slack; whether
that slack is enough under mis-prioritized branching is part of what is measured.

**Candidate compute ceiling (derivation corrected in R6).**

R5 stated `C = (P_seed + B) × F_max`. That is **not a valid upper bound**:
`F_max` (§3.9) is a **per-facet** input-chunk ceiling, while a visited page may
expose **several eligible facets** — one per revision in which its identity
occurs — and §6.4 step [4] expands *all* of them. The R5 formula silently assumed
one facet per visited page, which is false in general (and false on this corpus
for any page appearing in more than one revision).

The corrected bound introduces one additional deterministic, predeclared term:

```
M_max = the maximum number of facets attached to any single page identity,
        computed deterministically over the frozen Stage 7C.0 projection
        (max over page_key of |{document_revision_id : the page has ≥1
         anchor posting in that revision}|)

C = (P_seed + B) × M_max × F_max
```

*Derivation:* the flow visits at most `P_seed` seed pages plus `B` traversed
pages; each visited page exposes at most `M_max` facets (eligible facets are a
subset of all facets, so the all-revisions maximum bounds the authority-filtered
count); and each facet carries at most `F_max` input chunks. The product is
therefore a genuine upper bound on chunks carried into the final-K policy.

**`M_max` is a measured property of the frozen projection, not a knob.** It is
computed once at 7C.0 with zero LLM calls, recorded in
`contracts/wiki_projection_v1.json` alongside the projection manifest, and frozen
with it. It is never chosen, never tuned, never per-question, and never
recomputed at 7C.2. Any equivalent mathematically valid deterministic bound may
be substituted, but it must be derived and frozen the same way.

C remains a **non-binding compute guard, not a selection filter**, and on this
corpus it is provably non-binding (§0.1: one chunk per revision, so the `F_max`
factor is 1 in practice and `M_max` is bounded by 11). If it ever binds, that is
a contract-breach event requiring owner review — reported, never silently
truncated.

> **R6 note, stated so the correction cannot be misread as a loosening.**
> Correcting this bound **changes no measured evidence policy**. `P_seed`, `B`,
> the §6.6 final-K policy, the §7.3 prioritizer and every selection rule are
> untouched. The only change is that `C` is now an arithmetically valid ceiling
> rather than an under-stated one; a ceiling that was too *low* to be sound was
> never protecting anything, and raising it to the correct value selects nothing.

**Reported per question** (all modes where applicable):

| Quantity | Meaning |
|---|---|
| `eligible_pages` | pages with ≥1 eligible facet after authority filtering |
| `seed_pages_selected` / `seed_pages_expanded` | seeds chosen (≤ `P_seed`) and actually expanded |
| `pages_visited` | distinct page identities expanded, including traversed ones |
| `eligible_chunks` | distinct chunks on eligible facets of visited pages |
| `candidate_chunks` | chunks carried into the final-K policy (≤ C) |
| `page_saturation` | `pages_visited / eligible_pages` |
| `chunk_saturation` | `candidate_chunks / eligible_chunks` |
| `P_bound_hit`, `B_bound_hit`, `C_bound_hit` | whether each ceiling actually bound |
| `short_list` | whether fewer than K chunks were returned |

Saturation near 1.0 means the bounds are not selecting — a signal that W1 is
degenerating toward V and that the retrieval comparison must be read with that in
mind. **On this corpus, high saturation is likely and expected** (§0.1: there are
only 11 revisions in total), and must be reported as a corpus property rather than
as a design success.

### 6.6 The final-K evidence policy (new in R5 — requires owner approval, Q15)

The requirement is a deterministic policy that (a) preserves the same final K as
the frozen Vector benchmark, (b) protects the source chunks that establish the
traversed path, (c) does not reintroduce ordinary Vector retrieval as a backfill,
(d) is declared before the measured run, and (e) cannot be tuned per question.

**The proposed policy, in full.**

> **Definitions.**
> *The selected path* = the traversal sequence from the rank-1 seed page (§6.5)
> to the deepest hub reached, taking, at each step, the first neighbour in the
> §7.3 deterministic branch order. Ties are broken by stable page key. The path
> is recorded before any truncation.
> *A path-establishing chunk* = for the seed page, the chunk that carried the
> anchor posting the seed facet was selected on; for each hop, the chunk in the
> **destination** page's eligible facets that carried the anchor posting or claim
> citation used to justify that hop.
>
> **Tier 1 — protected path evidence.** The seed's path-establishing chunk,
> followed by each hop's path-establishing chunk, **in hop order (nearest
> first)**, deduplicated preserving first position.
>
> **Tier 2 — remaining reached evidence.** Every other chunk collected in §6.4
> step [9], ordered by cosine against the query using the **existing chunk
> embeddings**, then by `(document_revision_id, chunk_index, chunk_id)` for ties.
>
> **Assembly.** Concatenate Tier 1 then Tier 2, and truncate to K.

**Why this satisfies each requirement.**

| Requirement | How |
|---|---|
| same final K as V | truncation is to the question's own frozen `top_k`; no other K exists in the policy |
| protects path evidence | Tier 1 is filled before any similarity consideration, so a structurally required chunk cannot be displaced by a semantically closer irrelevant one |
| no Vector backfill | Tier 2 ranks **only chunks already reached by the structural flow**. Nothing enters from a global search. If Tier 1 + Tier 2 < K, the list is short and reported |
| declared before the run | frozen in `contracts/wiki_compiler_v1.json` at 7C.1, before 7C.2 executes |
| not tunable per question | the only per-question input is `top_k`, which is the frozen benchmark's own parameter |

**Two honest limits of this policy, stated in advance.**

1. **Tier-1 ordering is nearest-first, so if the path is longer than K, the far
   end is dropped** — and on a "what ultimately supports X?" question the far end
   *is* the answer. Nearest-first is chosen because the alternative (prefer the
   terminal hop) is only correct for terminal-answer questions and would amount
   to encoding question shape into the policy, which (e) forbids. On this corpus
   the longest chain is 4 hops against K = 5, so the case does not arise; a
   `path_truncated` flag is reported so that it is visible if it ever does.
2. **A mis-prioritized branch spends a Tier-1 slot on a wrong chunk.** With Q06/
   Q07 at zero slack (§0.1), one wrong hop costs one required fact outright. This
   is not a flaw in the policy — it is precisely the "branch ambiguity and
   navigation cost" failure mode §1.3.3 predicts, and §8.H measures it directly.

**Predeclared expectation on this corpus, recorded so the result cannot be
presented as a surprise:** on Q04/Q06/Q07, a `Payment Settlement` or `APP-224510`
seed followed by identifier-anchor hops yields exactly the required chunk set with
no waste (§0.1). The policy is expected to score well here **because the corpus is
clean**, not because the policy is proven.

### 6.7 Regeneration policy

| Trigger | Recompile facet? | Re-embed? |
|---|---|---|
| Source revision changes | **Yes**, that revision's facets | Yes |
| An accepted claim changes | **Yes** (it is an output of compilation) | Yes |
| Compiler model changes | **Yes**, all facets | Yes |
| Compiler prompt changes | **Yes**, all facets | Yes |
| **An adjudication verdict changes** (new in R5) | **No** — no model call | **Yes** — the payload depends on verdicts (§3.5, §6.2) |
| **Authority state changes only** | **No** | **No** — view-only (hard test) |

The new row is a real operational cost of §3.5 and is carried in §8E: W1 now has a
re-embedding trigger that is neither a source change nor a model change.

---

## 7. Navigation design — unified with retrieval for the W1 treatment

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

**Traversable anchor kinds (new in R5, Q16).** For hub-to-hub traversal in §6.4
step [6b], only `identifier` and `phrase` anchors are traversable.
`heading_title` anchors remain in the W0 inventory and remain usable for
`structural` browsing, but are **not** entity-fallback links: a shared heading
asserts document-template similarity, not entity co-occurrence, and traversing it
would connect every "Operating Procedures" section in a corpus to every other. On
this corpus the distinction is inert (§0.1: heading paths are document-unique), so
the rule costs nothing here and prevents a known scaling pathology. Declared
before the run; not tunable.

### 7.2 Navigation is part of W1 retrieval (revised in R5)

R4 treated W1 retrieval (§6.4) and `N_W1` navigation (§8C) as two separate
measurements. **R5 unifies them for the primary W1 treatment:**

```
semantic seed  →  hub expansion  →  structural navigation  →  evidence
```

is **one pipeline** (§6.4), and its output is what §8B scores. There is no
separate "W1 retrieval result" that navigation might later improve; navigation is
how W1 retrieves.

> **The primary comparison must therefore make clear that Wiki's value hypothesis
> is structural reachability after semantic seeding — not merely a different
> vector candidate filter.** Any report or summary describing W1 as "a
> facet-level vector search" is wrong and must be corrected.

### 7.3 Nested navigation configurations, preserved as diagnostics

R4's nesting is preserved, and is now evaluated **inside** the unified pipeline by
holding the seed constant and varying only the traversable link set:

```
N_W0       = structural + exact_anchor                     (deterministic only)
N_W1       = N_W0 + claim_derived                          (the primary W1 treatment)
N_advisory = N_W1 + advisory_semantic                      (diagnostic only)
```

`N_W0 ⊂ N_W1 ⊂ N_advisory` — a strict nesting, so each level's **marginal
contribution is directly measurable**: `N_W1 − N_W0` isolates the value of
claim-derived routing over deterministic anchors, and `N_advisory − N_W1`
isolates the advisory contribution.

> **R6 clarification — a link set is not an arm.** `N_W0` / `N_W1` /
> `N_advisory` name **traversable link sets** only. An experimental arm is a
> **(seed representation × link set)** pair, and R5 conflated the two: it read
> `N_W1 − N_W0` as "the marginal value of the LLM Wiki" when both sides were
> seeded from the **W1 facet representation**, so that delta isolates
> claim-derived *routing* and nothing else. The three attribution arms are
> defined in §7.4; these three names continue to designate link sets exactly as
> R5 defined them, and `N_W1 − N_W0` keeps its R5 meaning — one of the two
> deltas, not the whole question.

**`N_advisory` is retained only because R4 already required it as a diagnostic.**
It adds **no model call** (it reuses facet embeddings already computed for §6.2).
It **may not** be used to satisfy Gate A, may not be folded into any source-backed
result, and its links are never labelled lineage. If the owner prefers to drop it,
nothing else in R5 depends on it.

**Global hop budget** `B`, declared before the run (proposed **6**), never tuned
per question. One hop = one page-to-page traversal (§6.5). Authority leakage along
any traversed link is a hard failure.

**Branch prioritization — a weak deterministic prioritizer, no new model call.**
Outgoing links ordered by (a) cosine between the already-computed query embedding
and the target page's eligible facet embedding, then (b) lexical overlap between
the link's `predicate` and the query, then (c) link-type priority
(`claim_derived` before `exact_anchor` before `structural`), then (d) stable key
order. **This prioritizer is used by `W1-D` and `W1-FULL`; the deterministic
`D0` arm uses the substitution declared in §7.4.2, since clause (a) reads a
W1-derived facet embedding and clause (b) reads a claim predicate.**

> **Stated as a limitation, not a capability:** *this is similarity ordering, not
> intent understanding.* It cannot reliably distinguish "which control satisfies
> O-31?" from "which procedure implements C-88?" when both targets are
> semantically close, and predicate matching is purely lexical — it models neither
> direction nor relation type. Where prioritization fails, the navigator degrades
> to deterministic breadth-first order, and **that degradation is reported in the
> navigation results, not concealed inside BFS.** Fixing it properly needs a
> query-planning LLM or a typed relation registry, both out of scope (§12).

### 7.4 The three attribution arms — D0, W1-D, W1-FULL (corrected in R6)

This is the most consequential measurement point in the plan and it is stated
separately so it cannot be lost inside §7.3.

#### 7.4.1 The seed-attribution confound R5 contained

Under R4, W0 was only ever a *semantic-retrieval* control (≈ V, ungated, §2.3).
Under R5's unified flow, running the same pipeline with the `N_W0` link set gives
a genuine retrieval system: **W1 facet seed + deterministic hub expansion +
deterministic anchor traversal + the §6.6 final-K policy, with zero claims used
for connectivity or routing.** R5 then compared that arm against `N_W1` and
proposed to conclude from the result whether the LLM compiler was needed at all.

**That inference does not follow, and R6 corrects it.** Both sides of R5's
comparison were seeded from the **same W1 enriched facet representation** (§6.2),
which is a compiler output that depends on accepted claims, adjudicated summary
sentences and validated aliases. Holding it constant correctly isolates the
marginal value of **claim-derived routing** — but it can say nothing about
whether the compiler was unnecessary, because the compiler was still running on
both sides, supplying the step that decides *where the traversal starts*.

The R5 hypothesis (§1.3.2) in fact contains **two distinct possible
model-derived contributions**, and the experiment must measure them
independently:

1. **semantic facet enrichment may improve SEED DISCOVERY** — the enriched facet
   payload lands on a better hub than a raw chunk vector would;
2. **accepted claims may improve ROUTING after the seed** — typed, directed,
   prioritized hops beat untyped anchor fallback.

R5 measured only (2). R6 measures both.

#### 7.4.2 D0 — the deterministic, zero-W1-LLM ablation (new in R6)

> **D0 is NOT a new Wiki variant.** It introduces **no** new model, prompt,
> payload, embedding representation, reranker or planner, and adds no module and
> no table. It is one additional configuration of `retrieval.py` +
> `navigation.py` over the already-frozen 7C.0 projection, run at 7C.2 alongside
> the arms R5 already required.

> **What "D0" does and does not exclude — read this before quoting the arm
> anywhere (terminology correction, R6).** D0 excludes **W1-derived model
> output**: no compiler call, no claim, no alias, no summary sentence, no
> adjudication verdict, no facet payload, no facet embedding. D0 **does** use the
> **existing embedding model** — the same query embedding and the same V/W0
> chunk embeddings that the frozen Vector baseline uses — because reusing them is
> what makes D0 comparable to V and to the W1 arms, and introducing a second
> representation is forbidden (§12). So D0 is **not** "an arm with no machine
> learning in it"; it is the arm with **no Stage 7C.1 LLM layer** in it. Where
> this plan calls D0 *deterministic*, that means its Wiki-specific steps — anchor
> mapping, seed ordering, hub expansion, traversal, final-K assembly — are fixed
> rules over frozen artifacts, not that its retrieval contains no learned model.
> Prefer **"zero-W1-LLM"**, **"no W1-derived model output"** or **"deterministic
> D0"** in reports; never write "no model" unqualified.

D0 exists to answer one question R5 could not: **what does the deterministic Wiki
achieve with no W1-derived model output anywhere in the path?** It is therefore the
*deployable* deterministic Wiki — the thing a Gate B decision would actually
retain — and it is the correct baseline for pricing the LLM layer.

**The D0 seed procedure — fully predeclared, truth-free and untunable.**
Declared here, frozen in `contracts/wiki_projection_v1.json` at 7C.0, before any
measured run:

1. Embed the query **once**, with the existing provider, into the **existing
   V/W0 chunk embedding space**. *(No second embedding representation is
   introduced — this is the same query vector V uses.)*
2. Authority-first SQL over the **existing chunk embeddings**, exactly the §0
   pattern: `WHERE document_revision_id IN (:eligible) ORDER BY embedding <=> :q
   LIMIT P_seed`. The bound is `P_seed = K` (§6.5), unchanged and shared with the
   W1 arms.
3. Map each retrieved chunk to **deterministic source anchors**: the
   `AnchorPosting`s already recorded against that `chunk_id` at 7C.0 (§2.2).
4. Map those anchors to **seed page identities** — the page keys they belong to.
5. Order seed pages deterministically by (a) the rank of the retrieved chunk they
   came from, then (b) ascending posting `char_span` start within that chunk,
   then (c) stable `page_key`. Deduplicate preserving first position; truncate to
   `P_seed`. The **rank-1 seed page is the path origin** for §6.6 Tier 1, and its
   path-establishing chunk is the retrieved chunk that produced it.
6. From here the flow is **identical to §6.4 step [4] onward**: deterministic hub
   expansion of all eligible facets of each seed page, deterministic
   exact/source-anchor navigation only (the `N_W0` link set), the same global hop
   budget `B`, and the **same §6.6 final-K policy** truncating to the same
   per-question `top_k`.

**No `seed_page_priority` cosine over facet embeddings is computed for D0**, since
D0 may not read a facet embedding; its seed order is the deterministic rule in
step 5, and it is reported as `seed_order_rule = "D0_posting_order"`.

**The D0 branch prioritizer.** §7.3's prioritizer ranks outgoing links partly by
cosine against the **target page's facet embedding**, which is model-derived and
therefore unavailable to D0. D0 substitutes the deterministic analogue, declared
before the run and not tunable: (a) max cosine between the already-computed query
embedding and the **existing chunk embeddings** of the target page's eligible
facets; then (b) link-type priority (`exact_anchor` before `structural`); then
(c) stable key order. Clause (b) of §7.3 (lexical predicate overlap) is
inapplicable — D0 traverses no `claim_derived` link and so has no predicate.

> **The one honest rider on this substitution, stated in advance.** Because D0
> may not use a facet embedding *anywhere*, the D0 → W1-D difference covers
> **both** seed discovery **and** branch ordering, not seed discovery alone. This
> is a confound *of necessity*, not an oversight: a W1-LLM-free arm cannot borrow
> a W1-derived facet vector for branch ordering without ceasing to be free of W1
> model output.
> The delta is therefore named **"marginal value of W1 semantic facet
> enrichment"** rather than "of seeding", and §8.H reports
> `branch_order_divergence_vs_D0` — the count of visited hubs at which W1-D's
> branch order differs from D0's — so the size of the rider is measured rather
> than assumed. On this corpus it is expected to be near zero (§0.1: branching is
> minimal), which would make the delta effectively a seed-discovery measurement.

#### 7.4.3 The three arms, defined

All three share the corpus, the authority scope, the frozen 7C.0 projection, the
hop budget `B`, the §6.6 final-K policy, the per-question `top_k`, and the frozen
7B.0 evaluator. They differ **only** in the two columns below.

| Arm | Seed representation | Traversable link set | Model output used anywhere in the path | Existing name |
|---|---|---|---|---|
| **D0** | existing **W0/V source-chunk** embeddings → deterministic source anchors → page identities (§7.4.2) | `N_W0` (structural + exact_anchor) | **none** | *new in R6* |
| **W1-D** | **W1 enriched facet** representation (§6.2) → seed page identities | `N_W0` (structural + exact_anchor) | facet payload only (compiler + adjudication); **no claim used for connectivity or routing** | R5's "`N_W0` unified arm" |
| **W1-FULL** | **same W1 enriched facet seed** | `N_W1` (+ `claim_derived`) | facet payload **and** claim-derived routing | R5's `N_W1`, the primary W1 treatment |

`N_advisory` (§7.3) remains a diagnostic on top of W1-FULL and is unchanged: it
may not satisfy Gate A and nothing depends on it.

> **Reports, tables, code identifiers and the decision record MUST use the arm
> names `D0`, `W1-D` and `W1-FULL`** wherever an experimental role is meant, and
> reserve `N_W0` / `N_W1` / `N_advisory` for link sets. Writing "`N_W0`" where an
> arm is meant is the exact ambiguity that produced R5's confound. Where the R5
> name aids continuity, write `W1-D (= the N_W0 link set on the W1 seed)`.

#### 7.4.4 What each comparison can and cannot establish

| Comparison | Isolates | Can establish | Cannot establish |
|---|---|---|---|
| **W1-D vs D0** | seed representation (+ branch ordering, §7.4.2 rider) | whether **semantic facet enrichment** contributed | anything about claims |
| **W1-FULL vs W1-D** | traversable link set | whether **claim-derived routing** contributed | whether the compiler was needed at all |
| **W1-FULL vs D0** | the whole LLM layer | the **total marginal value** of the LLM-assisted Wiki over the deployable deterministic Wiki | which of the two sub-layers produced it |

Per §0.1 and §1.5.4, **D0** is expected to reconstruct the Q04/Q06/Q07 chain on
this corpus by itself. If it does, then the R5 hypothesis is supported — but *for
the deterministic projection* — and Gate B becomes the likely outcome (§9.6). What
R6 changes is that this conclusion may now only be drawn from **D0**, never from
the same-W1-seed comparison alone.

**Two attributions must not be confused**, and §9.5 enforces the separation:

| Question | Answered by | Feeds |
|---|---|---|
| Was the win extraction or representation? | §9.4 (W1 claims vs frozen 7B.1 edges) | Gate A precondition |
| Was the win **deterministic structure or model-derived structure** — and if model-derived, **seed enrichment or routing**? | §9.5 (the two deltas plus the total, over D0 / W1-D / W1-FULL) | Gate A precondition **and** the A-vs-B decision |

All three arms are **truth-free** — none uses benchmark knowledge or selects
anything by hand — so, unlike §8.G's probe, all three **are** admissible Gate-A
evidence.

> **R6 closes a gap R5's Gate B wording had left open.** R5 noted that a W0-only
> deployment "would need a seed of its own" and had no arm supplying one. **D0 is
> that arm.** Gate B can now be selected on evidence about a system that could
> actually be deployed, rather than by inference from an arm that borrowed the
> compiler's seed.

---

## 8. Benchmark contract

Dimensions are kept separate and never averaged into a single score.

### 8.A Compilation quality (W1)

Measured against the frozen facts **only after compilation is complete**;
compiler never reads benchmark truth (AST tests + runtime guard).

Metrics: expected-fact recall in accepted claims; accepted-claim precision;
unsupported claim count; **citation validity** (deterministic); **claim
correctness** (frozen-fact match + owner adjudication of *every* accepted claim,
§4.6); omitted relationship count; entity identity accuracy; **alias span
validity**; **supported-alias precision** (owner-adjudicated, with incorrect and
unverifiable counts separate); **`out_of_page_scope` claim count** (absolute, as a
share of technically valid claims, and broken down by whether the claim was
otherwise well-cited); **false merge count (target 0)**; duplicate /
`contradictory` / `revision_divergent` counts; **summary reference validity**;
**summary correctness** (owner-adjudicated, every sentence); derived-link precision
and recall *(reported as derived from claim quality, §3.7 — not an independent
output)*; `unlinkable_claim_endpoint` count; `unresolved_identity_mentions` count
(audit only); provenance completeness; generation failures; ceiling breaches;
validation rejections by reason.

**New in R5 — representation composition metrics:** per facet,
`payload_truncated_components`, `summary_payload_dedup_count`, component
presence/absence counts, and the count of facets with **zero accepted claims**
(reported prominently, because under R5 such a facet is still fully functional for
membership and traversal — §2.2 — and the count is a direct measure of how much of
the corpus the claim layer failed to cover).

**Reported in the form §9.4 consumes.** Accepted-claim recall and precision are
additionally reported in the shape directly comparable to the frozen Stage 7B.1
Real Graph extraction figures (expected-fact edge recall **0.80**, extracted-edge
precision **0.86**; missed `F_adj_prc`, `F_prc_current`, `F_svc`), including which
expected facts were missed, so the attribution analysis can be performed without
re-deriving either side.

### 8.B Retrieval quality (V vs W0 vs W1)

Same questions; same intent and `as_of_date`; same eligible revisions; **same
final source-chunk K** (the question's frozen `top_k`); **same frozen Stage 7B.0
evaluator**; zero query-time LLM; no per-question tuning.

Reported per mode and question: required-fact coverage@K; all-required-
retrieved@K; complete-chain represented; MRR; nDCG@K; forbidden-fact hits;
authority-leakage count (**must be 0**); evidence-document diversity;
solved/partial/failed; the §6.5 bounds and saturation table; and an explicit
**per-question gains and regressions** table.

**R5 added rows to that table; R6 corrects and completes them.** The comparison
set is now, using the §7.4 arm names:

```
W1-FULL      vs  V           the headline retrieval result
W1-FULL      vs  D0          ← TOTAL marginal value of the LLM-assisted Wiki
                                over the deployable deterministic Wiki.
                                Decisive for Gate A (A-7, §9.3, §9.5)
W1-D         vs  D0          ← ATTRIBUTION DELTA 1: marginal value of W1
                                semantic facet enrichment (§7.4.2 rider applies)
W1-FULL      vs  W1-D        ← ATTRIBUTION DELTA 2: marginal value of
                                claim-derived routing
D0           vs  V           the deterministic-structure result (no W1 LLM)
W0 semantic  vs  V           unchanged control (expected ≈)
```

> **All three attribution rows are mandatory and none substitutes for another.**
> Reporting `W1-FULL vs W1-D` alone — R5's error — measures routing and is
> **prohibited** as a basis for any statement about whether the compiler was
> needed (§9.5). `N_advisory` is reported separately as a diagnostic and enters
> no gate.

> **Labelling when Gate Q fails.** W1 retrieval is measured whether or not Gate Q
> passed (§9.2). If Gate Q failed, **every W1 row, figure, table cell and summary
> statement in the results, scorecard and decision record carries the label
> `NON-QUALIFYING / DIAGNOSTIC ONLY`**, and the specific failing Gate Q criteria
> are printed adjacent to the numbers. Such results may inform the §9.4/§9.5
> attribution analyses and the Gate B/C narrative; they may **never** be cited as
> satisfying Gate A, quoted without the label, or compared against V as if
> qualified.

**V is not rerun, rescored, or altered** — frozen Stage 7B.0 results and evaluator
loaded read-only, with a rerun-equality verification step only if exact benchmark
parity requires it.

### 8.C Navigation quality (D0 vs W1-D vs W1-FULL vs `N_advisory`)

Because navigation is now part of retrieval (§7.2), §8C reports the *navigational
properties* of the same runs §8B scores, rather than a separate experiment:
required-evidence reachability; complete-chain navigability; minimum clicks to
required evidence; branch count; irrelevant-destination count; ambiguity rate;
authority leakage (**must be 0**); forbidden-fact exposure; **marginal contribution
of each nesting level** (§7.3); **the two §9.5 attribution deltas and the total,
reported as navigation outcomes as well as retrieval outcomes** (new in R6);
navigation-path explainability (every hop cites an `anchor_id`, or a `claim_id` +
`source_ref`); prioritizer-degradation rate (§7.3, reported for D0's substituted
prioritizer as well, §7.4.2). Primary targets Q04/Q06/Q07. Semantic similarity
alone is **never** treated as verified lineage.

### 8.D User-facing page quality

A fixed sample (proposed **6 pages**, selected deterministically by hash, never
cherry-picked), rendered for W0 and W1, presented **blind to mode label in
deterministic order**, scored 0–2 on: readability; ability to understand *why*
sources are connected; visibility of source vs model-derived content; citation
usability; revision clarity; exception/qualification preservation; usefulness to a
business user; usefulness to a downstream agent. Scored by the owner (**Q7**). A
deterministic mechanical proxy is reported alongside — citation density,
summary-degradation rate per intent — but **never substituted for the rubric**.

### 8.E Cost and maintainability

Implementation surface (modules, LOC, tables); compilation calls; input/output
tokens; **dollar cost** via the existing `estimate_cost_usd()` (returning `None`
rather than a fabricated figure for an unpriced model); build latency; retrieval
latency (V vs W0 vs **D0** vs **W1-D** vs **W1-FULL**, warm); storage; validation rejection rate;
reprocessing cost after a source change, after an authority change, after a
model/prompt change, and — **new in R5** — **after an adjudication-verdict change**
(§6.7); output stability (§8F); debugging difficulty; stale-page risk; operational
dependencies.

**New in R5, and not to be understated:** the **owner adjudication effort is now on
the retrieval critical path**, not only the quality path (§4.4). W1's ledger must
record adjudication as an *operational dependency of the index*, not as a one-off
evaluation task: any change to the compiler, prompt, model or source requires
re-adjudication before the representation can be rebuilt. Report the measured
adjudication item count and elapsed effort for Run 1.

> **Lower maintenance will not be claimed merely because pages are
> human-readable.** W1's ledger carries its compiler, prompt versioning,
> validator, adjudication effort, rejection triage, regeneration policy and model
> dependency as costs, compared honestly against V (near-zero marginal), against
> the **D0 deterministic arm** (§7.4 — zero LLM calls, zero adjudication, zero
> compiler, and therefore the true cost floor for a deployable Wiki), against
> **W1-D** (which pays for the compiler and adjudication but not for claim-derived
> routing), and against the frozen 7B Graph/Hybrid ledger.
>
> **R6 pricing rule.** The compiler's cost is charged against the **W1-FULL vs
> D0** total, not against the W1-FULL vs W1-D delta. Charging the full compiler
> ledger against the routing delta alone — R5's implicit framing — would price a
> layer against a benefit it only partly produces.

Order-of-magnitude expectation, to be replaced by measurement and never quoted as
a result: tens of facets × a few thousand input tokens at `gpt-4o-mini` pricing →
well under one dollar per compilation run, ×3 runs for §8F.

### 8.F Repeatability

**N = 3** full compilation runs with identical model, prompt, source chunks,
configuration and authority scope, at `temperature = 0` — noting the repo's own
recorded caveat that this is the lowest-variance setting available and **not** a
determinism guarantee for a hosted model.

> **Run 1 is designated the primary frozen representation, before any run
> executes.** Runs 2 and 3 measure stability only. They are never used to replace,
> merge with, supplement, or improve Run 1. **Selecting the best-scoring run is
> prohibited.** The freeze record stores Run 1's facet hashes, and all retrieval,
> navigation, page-quality and adjudication work in 7C.2 reads Run 1 exclusively.

Measured across runs: claim-set stability (Jaccard over normalized
`(subject, predicate, object, sorted supporting_chunk_ids)`); citation stability;
alias stability; summary stability; derived-link stability; fact-recall variance;
unsupported-claim variance; token and latency variance. *Page identity stability is
not measured — it is 100% by construction (§3.2).*

**New in R5 — membership stability is also not measured, and saying so is the
point.** Facet membership, source chunks, anchors and postings are produced at
7C.0 with zero LLM calls and are **byte-identical across all three runs by
construction** (§2.2). The claim-set Jaccard therefore measures variance in the
*routing/enrichment* layer only, sitting on top of an invariant connectivity
layer. This is exactly the structural property R5 asserts, and its verification is
a hard test rather than a metric.

**Adjudication and repeatability.** Only Run 1 is adjudicated (§4.6), so only Run
1 has a payload-eligible summary set. Runs 2 and 3 are compared on **structured
claims, citations, aliases, links and raw summary text**, never on payload
composition. This is stated to prevent a false stability reading.

**Textual summaries need not be byte-identical.** Structured accepted claims and
citations must meet declared thresholds — proposed: accepted-claim set pairwise
Jaccard **≥ 0.90**, citation sets on matched claims **≥ 0.95 exact**, false merges
**0 in every run**, ceiling breaches **0 in every run** (**Q5**).

### 8.G Counterfactual claim-omission resilience diagnostic (new in R5)

**Label, mandatory and verbatim, on every artifact this produces:**

> ### COUNTERFACTUAL RESILIENCE DIAGNOSTIC

**Purpose.** Test whether Wiki connectivity truly survives the loss of an
LLM-derived relationship.

**The primary measured W1 run remains natural and untouched.** This probe is a
separate, additional pass.

**Procedure.** For the target transitive questions **Q04, Q06, Q07** only:

1. Run the natural W1 flow (§6.4) and record the selected path and the
   `claim_derived` links used on it.
2. Deterministically **suppress**, at read time in the navigator, every
   `claim_derived` link lying on any minimal-hop path between the seed page and a
   page carrying that question's required evidence.
3. Re-run the identical flow with the identical seed, budget, prioritizer and
   final-K policy.

**What is suppressed, and what is not:**

| Suppressed | Explicitly NOT touched |
|---|---|
| the identified `claim_derived` navigation links | deterministic page/facet membership (§2.2) |
| | source chunks |
| | exact/source anchors and postings |
| | authority resolution or eligibility |
| | the facet semantic representation or any embedding |
| | the compiler, prompt, model, claims, or any stored artifact |

**Implementation constraint — this is how it stays inside the freeze boundary.**
Suppression is a **read-time filter applied by the navigator over the frozen 7C.1
link set**. It writes nothing, mutates nothing, and regenerates nothing. §11's
rule that "7C.2 may not change the projection, compiler, prompt, accepted claim
set, derived links, or any embedding" is therefore respected literally: the stored
link set is unchanged; one query-time configuration ignores part of it.

**Measured:** whether the target evidence remains reachable through deterministic
hub expansion and anchor fallback within the same hop budget, plus the full §8.H
metric set for the suppressed run.

**Standing and limits — binding.**

- It is **NOT** a second W1 variant.
- It **cannot satisfy Gate A**, and — because its suppression target is chosen
  using the question's required-evidence set, i.e. **frozen benchmark truth** —
  it is **truth-informed and therefore not admissible as Gate A evidence at
  all.** It informs the Gate B/C narrative and the §9.5 attribution discussion.
- **It does not replace either truth-free attribution comparison** (new in R6,
  and binding). This probe varies **only** the claim-derived link set on the W1
  seed, so at most it speaks to the same territory as the **W1-FULL vs W1-D**
  delta — and it speaks to it *less* well, being truth-informed. It says nothing
  whatever about **W1-D vs D0** or **W1-FULL vs D0**. The truth-free comparisons
  that **are** Gate-A-admissible are the §7.4 arms: **W1-D**, which suppresses
  *all* claim-derived links without consulting truth, and **D0**, which
  additionally removes the model-derived seed.
- **It does not perfectly simulate a full extraction miss.** The frozen facet
  semantic representation was created **before** the link was suppressed, so the
  seed step still benefits from the claim's text in payload component 6 and from
  any summary sentence derived from it (component 7, §6.2). The probe tests
  **dependency on claim-derived routing connectivity only** — nothing more — and
  must be described that way everywhere it appears.
- **The natural Run-1 extraction results remain the primary evidence for actual
  extraction omissions.** Where the compiler genuinely missed a relationship, that
  is a real, uncontrived instance of the condition this probe simulates, and it
  outranks the probe as evidence.
- **Predeclared expectation:** given §0.1, this probe is expected to report
  "still reachable" for all three questions, **trivially** — the chain is fully
  covered by identifier anchors. A positive result here is therefore weak
  evidence and must be reported as weak. A *negative* result would be strong
  evidence against the R5 hypothesis.

### 8.H Wiki resilience and ambiguity metrics (new in R5)

Reported **per question**, for every arm (**D0**, **W1-D**, **W1-FULL**,
`N_advisory`, and the §8.G suppressed run), at minimum:

| Metric | Notes |
|---|---|
| seed facet(s) | `(page_key, document_revision_id)` and rank. **D0 reports the retrieved seed chunk(s) and the postings that produced its seed pages instead** (§7.4.2) |
| seed page identity | plus `seed_page_priority` (§6.3) for the W1 arms; `seed_order_rule = "D0_posting_order"` for D0 |
| **`seed_page_overlap_vs_D0`** | **new in R6** — how many of the arm's seed pages D0 also selected, and at what rank. Directly quantifies attribution delta 1's mechanism |
| **`branch_order_divergence_vs_D0`** | **new in R6** — visited hubs at which this arm's branch order differs from D0's; bounds the §7.4.2 prioritizer rider |
| target evidence reachable | yes / no |
| minimum discovered hops to required evidence | over the discovered graph, not the taken path |
| actual traversed hops | ≤ `B` |
| eligible neighbours exposed at each visited hub | list, per hub |
| branching factor per hop | exposed neighbours ÷ hops taken |
| total candidate neighbours examined | cumulative |
| claim-derived traversals | count and which |
| exact-anchor fallback traversals | count and which |
| destination reachable after relevant claim-link suppression | yes / no (§8.G) |
| authority-ineligible neighbours removed | count |
| **authority leakage** | **target 0** — any nonzero value is a hard-safety failure (§9.1) |
| source chunks encountered | distinct count |
| final evidence chunks returned | ≤ K |
| complete-chain represented | frozen evaluator |
| required-fact coverage@K | frozen evaluator |
| latency | query + navigation, warm |
| ingestion cost attributable to W1 | tokens, calls, dollars (§8E) |
| query / navigation cost | traversals, facet expansions, cosine computations |
| persisted representation size | bytes, by table |

**No acceptable branching-factor threshold is invented.** The frozen contract
contains none, so none is asserted here. The cost is reported and §9.3's retain
gates judge whether the value justifies it.

**Mandatory caveat on every branching figure** (§0.1, consequence 2): on a
6-document, 11-revision corpus with one cross-document phrase anchor and no bridge
into the distractor domain, low branching factors are a property of the **corpus**,
not evidence that Wiki navigation is well-behaved at scale. This caveat is
reproduced verbatim in the scorecard and the decision record.

---

## 9. Gates

### 9.1 Hard safety requirements (pass/fail preconditions on everything)

Original chunks remain the sole authoritative evidence; zero authority leakage;
zero invalid source references; complete claim-level provenance; every accepted
claim has exact supporting source spans; model-derived and source-derived content
visibly separate; no silent entity merge (C-88/C-88A included); no timeless
current/effective flag; no Graph dependency; no benchmark-truth access during
compilation or retrieval *(the §8.G probe is truth-informed by construction and is
therefore excluded from Gate A evidence and clearly labelled — it is not an
exception to this rule for any qualifying measurement)*; no query-time LLM; same
final source-evidence K; full model/prompt/input/output/cost provenance;
deterministic validation; explicit regeneration policy.

**New in R5:**

- **no whole-page, authority-blind embedding of any kind** (§6.2, §6.3);
- **membership independence** — no LLM output, validation outcome, or adjudication
  verdict may alter facet membership, source chunks, anchors or postings
  (§2.2, §4.0);
- **no Vector backfill** into the W1 evidence set (§6.4, §6.6).

**No mode failing any hard-safety condition may satisfy a retain gate**, however
good its retrieval numbers are.

### 9.2 Gate Q — Stage 7C.1 qualification (evaluated **before** any W1 retrieval)

**Unchanged from R4 in every threshold and in its semantics.**

> **Gate Q controls retention eligibility, not measurement permission.**

| # | Criterion | Required |
|---|---|---|
| Q-1 | Citation validity | **1.00** |
| Q-2 | Invalid source references | **0** |
| Q-3 | **Revision-scope contamination** (any claim citing a chunk outside its facet's revision) | **0** |
| Q-4 | False merges (incl. C-88 / C-88A) | **0** |
| Q-5 | Accepted-claim precision | **≥ predeclared threshold** (proposed **0.95**) |
| Q-6 | Expected-fact recall in accepted claims | **≥ predeclared threshold** (proposed **0.80**) |
| Q-7 | Summary correctness (owner-adjudicated, every sentence) | **pass at predeclared threshold** (proposed **0 incorrect sentences**) |
| Q-8 | Repeatability (§8F thresholds) | **pass** |
| Q-9 | Budget and ceilings (§3.9) | **no breach; within declared dollar cap** |
| Q-10 | Supported-alias precision (owner-adjudicated, every supported alias, §4.5) | **incorrect supported aliases = 0** |

> **R6 terminology correction to Q-3 — a rename only.** R5 called this condition
> "authority contamination". That name was wrong in a way that could mislead a
> reader of the decision record: **the compiler is authority-blind** (§3.1 — it
> never sees the resolver, authority state, or any revision but its facet's), so
> it cannot contaminate an authority scope. What Q-3 actually detects is a claim
> escaping its facet's **revision scope**, which is why §3.1 makes it structurally
> near-impossible and §4.1.2/§4.1.4 check it mechanically. **Actual authority
> leakage is a separate, query/assembly-time hard-safety metric** — §9.1, §8.B and
> §8.H, each with target 0 — and remains exactly as specified. **Behaviour,
> detection rule and threshold (= 0) are unchanged; only the name changes.** Code,
> contracts, reports and the decision record use `revision_scope_contamination`.

Recall stays a Gate Q criterion because **low recall is a completeness failure**: a
compilation that misses expected facts is an incomplete evidence layer and cannot
be retained on that basis.

> **R5 note on Q-6 and the new hypothesis.** One might argue that since R5 no
> longer routes connectivity through claims, low claim recall should no longer
> block retention. **Q-6 is deliberately kept as-is.** If claim recall is low and
> retrieval still works, that is not a reason to retain the compiler — it is
> evidence that the compiler was not needed **for connectivity**, which points
> toward Gate B via §7.4. The threshold's job is to stop a weak compiler being
> retained on someone else's results, and that job is *more* necessary under R5,
> not less.
>
> **R6 qualification.** "Someone else's results" must be identified correctly.
> Low claim recall plus working retrieval shows the *claims* were not needed; it
> does **not** show the *compiler* was not needed, because the compiler also
> produces the seed representation (§6.2) that `W1-D` and `W1-FULL` both consume.
> Whether the compiler was needed at all is settled against **`D0`** (§9.5.1), not
> against Q-6. Q-6's threshold and semantics are unchanged.

> **If Gate Q fails after a *technically completed* compilation:**
>
> - **W1 can never satisfy Gate A**;
> - **nevertheless Stage 7C.2 still runs** the full unified flow over the frozen
>   Run 1 facets, including the **D0** and **W1-D** arms and the §8.G probe
>   *(D0 is unaffected by a Gate Q failure — it consumes no compiler output, so
>   its results are never labelled `NON-QUALIFYING`)*;
> - **all W1 results are explicitly labelled `NON-QUALIFYING / DIAGNOSTIC ONLY`**
>   (§8B), alongside the specific failing criteria;
> - the stage proceeds to **Gate B or Gate C**, with the diagnostic evidence and
>   the §9.4/§9.5 attribution analyses informing which.
>
> "Technically completed" means the compilation run finished and produced
> validated facet records: no generation failure, no ceiling breach (Q-9), and no
> hard-safety violation (§9.1). A run that is **not** technically completed does
> **not** proceed to 7C.2.

**Why measure a failed compilation.** §1.3 states that Stage 7C tests whether
source-hub connectivity is resilient to imperfect extraction. An imperfect
compilation is precisely the condition under which that hypothesis is
informative — more so under R5 than under R4, because R5's mechanism is supposed
to work *without* claims. Refusing to measure it would guarantee that the one
predicted-likely outcome yields no evidence at all.

**Note:** a strong diagnostic result is **not** grounds to relax a Gate Q
threshold, rerun the compiler, or promote the result.

### 9.3 Retain gates (immutable; declared before the measured run; no required winner)

**Improvement — exact definition. Unchanged from R4.** A target question counts as
improved only if **both** hold, comparing W1 to V:

1. status transitions **partial → solved**, **and**
2. complete-chain represented transitions **false → true**.

**Regression — exact definition. Unchanged from R4.** A question regresses if
**any** of the following holds, comparing W1 to V:

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

**Gate A — Retain W1 semantic Wiki.** All of:

| | Requirement | Status in R5 |
|---|---|---|
| A-1 | Gate Q passed; all hard-safety passed | unchanged |
| A-2 | **≥2 of Q04/Q06/Q07 improved** by the definition above | **unchanged — the strict bar is preserved** |
| A-3 | **zero regressions** on every other question | unchanged |
| A-4 | same final source-evidence K; zero authority leakage | unchanged |
| A-5 | user-facing page quality (§8D) improves over W0 | unchanged |
| A-6 | the **§9.4 extraction attribution** completed and recorded | unchanged |
| A-7 | **the §9.5 structural attribution completed — both deltas and the total computed and recorded — and the complete W1 treatment (`W1-FULL`) demonstrates measurable value over the deployable deterministic `D0` Wiki (which uses no W1-derived model output) on the target questions** | **REPLACED in R6** |
| A-8 | cost/maintenance justified relative to V **and relative to the `D0` arm** (the zero-W1-LLM cost floor, §8E) | strengthened |

> **Gate A is unreachable if Gate Q failed**, irrespective of how good the
> diagnostic retrieval numbers are (§9.2).

**Why A-7 exists, and what R6 corrected in it.** The strict Q04/Q06/Q07
improvement rule was to be preserved unless the corrected experiment logically
required an adjustment. **A-2 is preserved verbatim, and so are all the
regression rules.** A-7 exists because R5's redesign made it possible for W1 to
satisfy A-2 while contributing nothing: evidence can be reached with zero claims
(§7.4, §1.5.4), so without A-7 Gate A could retain an LLM compiler on the
strength of a deterministic result.

**R5 wrote A-7 against the wrong comparator.** It required `N_W1` to beat the
same-W1-seed `N_W0` arm — i.e. it demanded that **claim-derived routing
specifically** carry the win. That is too narrow in one direction and unfounded
in the other:

- *too narrow* — if the W1 facet representation produces the qualifying
  improvement through **seed discovery**, that is genuine, measured value from
  the LLM layer, and R5's A-7 would have discarded it and forced Gate B;
- *unfounded* — a same-seed comparison cannot show the compiler was unnecessary,
  because the compiler was seeding both arms (§7.4.1).

> **A-7, corrected, defined concretely.** On Q04/Q06/Q07, **W1-FULL** must show a
> strictly better outcome than **D0** on at least one of {status, complete-chain
> represented, required-fact coverage@K}, with no regression on the others, and
> with no regression from **D0** on the remaining nine questions. In addition,
> both §9.5 attribution deltas (**W1-D vs D0** and **W1-FULL vs W1-D**) and the
> total (**W1-FULL vs D0**) must be computed and recorded, so the decision record
> states *which* sub-layer produced the value.
>
> **Claim-derived routing does NOT have to contribute.** If semantic facet
> enrichment alone produces the qualifying W1-FULL improvement over D0, A-7 is
> met and Gate A remains available. The attribution deltas determine what is
> *written down* about the mechanism, not whether the gate opens.

A-7 still raises the bar relative to R4 — nothing in R5 or R6 lowers it — and it
now measures against a system that could actually be deployed. If A-2 is met but
A-7 is not, the outcome is **Gate B**.

**Gate B — Retain W0 only, as a source-navigation and deterministic-retrieval
layer.** W1 fails Gate Q, or fails Gate A (including failing **A-7**); W0 provides
useful revision / provenance / exact-anchor navigation; W0 maintenance remains
low.

> **Gate B's evidentiary requirement, corrected in R6 and binding.** Gate B is a
> decision that the **deployable deterministic Wiki suffices**, so it must rest on
> evidence about the deployable deterministic Wiki:
>
> **Gate B requires either**
> (i) **D0** is *sufficient* — it achieves the transitive result on the target
> questions, and **W1-FULL vs D0** shows no qualifying improvement; **or**
> (ii) **W1-FULL vs D0** shows a measured improvement, but that **incremental
> value is not worth its cost** against §8E's ledger (compiler, validator,
> adjudication as an index dependency, regeneration policy, model dependency),
> with the cost judgement stated explicitly and the measured delta quoted
> alongside it.
>
> **Gate B MUST NOT be selected from a same-W1-seed comparison.** In particular,
> "`W1-FULL` did not beat `W1-D`" is **not** grounds for Gate B on its own: both
> arms consume the compiler, so that result establishes only that *claim-derived
> routing* added nothing, while the compiler may still have been carrying the
> result through the seed. Selecting Gate B on that basis would retire a layer the
> experiment showed was working — the mirror image of the misattribution A-7
> exists to prevent.

> **R5 amends R4's Gate B wording.** R4 required that "W0 is not represented as a
> superior semantic retriever (its retrieval is reported as ≈ V, by
> construction)". That sentence is **kept for W0's pure semantic retrieval**
> (§2.3) and **does not apply to the deterministic-link arms of the unified flow**
> (§7.4), which may legitimately outperform V — they are a different computation,
> using hub expansion and anchor traversal rather than a single chunk-vector
> search. Gate B may therefore record a genuine deterministic retrieval win,
> provided the arms are never conflated in wording. This amendment is required by
> R5's unification of retrieval and navigation; R4's wording predates it and would
> otherwise force a true result to be reported as impossible.
>
> **R6 completes this amendment.** R5 had to add the caveat that the arm's "seed
> comes from the W1 facet representation and a W0-only deployment would need a
> seed of its own" — an admission that R5 had no arm capable of grounding Gate B.
> **D0 is that arm** (§7.4.2), and it is what a Gate B decision retains. A Gate B
> record must therefore report **D0's** numbers as the deterministic result. It
> may report **W1-D** alongside, but only labelled as what it is — *a
> compiler-seeded arm, not a deployable W1-LLM-free system* — and never as the
> basis for concluding the compiler was unnecessary.

Where W1 ran diagnostically, its labelled results and both attribution analyses
are reported as part of the Gate B record.

**Gate C — Do not retain a Wiki projection.** W1 does not improve retrieval or
navigation; or page quality depends on unsupported generated prose; or omissions
or unstable links remain high; or authority-safe composition proves impractical;
or maintenance burden approaches or exceeds the Graph/Hybrid path; or **no arm —
neither `D0`, nor `W1-D`, nor `W1-FULL` — preserves transitive reachability**
(which would falsify the R5 hypothesis outright, §9.6); or W0 adds insufficient
value beyond the existing chunk/audit viewer.

Evaluated in the fixed declared order **A → B → C**. Retrieval value, navigation
value, page quality and cost are kept distinct and never averaged. No outcome is
encoded as required; no test asserts W1 > W0 > V.

### 9.4 Mandatory attribution analysis I — extraction vs representation

**Unchanged from R4, with one R5 extension at the end.**

> **Before attributing any W1 retrieval improvement to page-centric consumption,
> the decision record must compare W1's extraction quality against the frozen
> Stage 7B.1 Real Graph extraction quality.** Mandatory for every outcome; Gate A
> may not be granted without it.

| Side | Quantity | Source |
|---|---|---|
| Graph (frozen) | expected-fact **edge** recall = **0.80** (12/15; missing `F_adj_prc`, `F_prc_current`, `F_svc`), extracted-**edge** precision = **0.86**, unsupported edges = 2 | `reports/stage7b1_graph_build_results.json`, `reports/stage7b1_vector_vs_graph_scorecard.md` — read-only |
| Wiki (7C.1) | expected-fact recall in **accepted claims**, **accepted-claim** precision, unsupported claim count | §8A, Run 1 |

Both sides are LLM extraction over the same frozen chunks, scored against the same
15 frozen facts, and — per §3.8 — produced by the **same model**. Declare before
the run what counts as *similar*: proposed **±0.05 on recall and on precision**.

**Interpretation — the four cases, stated in advance.**

| W1 extraction vs Graph | W1 retrieval vs V | Reading that must be recorded |
|---|---|---|
| **similar or worse** | **better** | **Consistent with the resilience hypothesis** — representation carried the improvement despite no extraction advantage. **In R5 this is necessary but no longer sufficient**: §9.5 must then show it was the *model-derived* structure and not the deterministic one. |
| **better** | **better** | **The W1 system improved overall, but the improvement cannot be attributed solely to page representation.** Record as a joint result; do not claim the resilience mechanism was demonstrated. |
| **better** | **same or worse** | **Better extraction alone did not justify the Wiki.** Evidence against the representation, not against extraction. |
| **similar or worse** | **same or worse** | **Page representation did not overcome extraction weakness.** Points to Gate B or Gate C. |

**Prohibited conclusions.**

> **Do not claim that Wiki extraction is inherently more reliable than Graph
> extraction.** §1.3.5 forbids it and this stage cannot support it: a single
> non-deterministic extraction snapshot on each side, one small corpus, no
> repeated Graph runs to compare against §8F's W1 variance, and different output
> shapes whose recall/precision definitions are aligned only approximately. A W1
> figure above 7B.1's is **one observation on one corpus.**

Also prohibited: attributing improvement to page-centric consumption without
performing this comparison; quoting W1 extraction figures without the Graph
figures alongside; and treating the shared-model constraint (§3.8) as
interchangeable with a controlled experiment.

**R5 extension — the reachability comparison (required).** The decision record
must additionally compare, fact by fact:

| | Graph (frozen 7B.1/7B.2a) | Wiki (7C.2 — reported for **D0**, **W1-D** and **W1-FULL** separately) |
|---|---|---|
| `F_svc` | edge missing → chain broken; 7B.2a hybrid could not recover it | reachable? by which mechanism (membership / anchor / claim)? |
| `F_prc_current` | edge missing → chain broken | reachable? by which mechanism? |
| `F_ctl_current`, `F_obl_current`, `F_app_current` | edges present | reachable? at what navigation cost? |

and state, for each, **what navigation cost Wiki paid** (hops, neighbours
examined, evidence slots consumed) to preserve reachability that Real Graph lost.

**The final comparison must explicitly distinguish:**

> **Graph:** typed-edge precision, and reachability that is *sensitive to missing
> edges*.
> **Wiki:** source-hub connectivity, and *branching ambiguity*.

**Do not rebuild, rerun, improve, or extend Graph. Do not build a Graph-summary
variant.** The frozen Stage 7B.1 / 7B.2a evidence is used read-only, as
documentation.

### 9.5 Mandatory attribution analysis II — deterministic vs model-derived structure (new in R5)

> **Before attributing any W1 result to the compiled Wiki, the decision record
> must establish which structural layer produced it.** Mandatory for every
> outcome; Gate A may not be granted without it (A-7).

**The comparison — corrected in R6.** R5 compared two arms. That was insufficient:
both shared the **W1 enriched facet seed**, so the single delta it produced
isolated claim-derived routing and could not speak to whether the compiler was
needed (§7.4.1). R6 uses **three** arms, all sharing the hop budget, the §6.6
final-K policy, the per-question `top_k` and the frozen evaluator:

| Arm | Seed representation | Connectivity available | Model output used anywhere in the path |
|---|---|---|---|
| **D0** | existing V/W0 chunk embeddings → deterministic anchors → pages (§7.4.2) | structural + exact_anchor | **none** |
| **W1-D** | W1 enriched facet payload (§6.2) | structural + exact_anchor | facet payload only |
| **W1-FULL** | W1 enriched facet payload | + claim_derived | payload **and** routing |
| §8.G suppressed | W1 enriched facet payload | `N_W1` minus the path-relevant claim links | truth-informed; **diagnostic only, replaces neither delta** |

#### 9.5.1 The three required numbers

All three are mandatory in the decision record, each on the target questions and
across the full 12:

```
W1-D      vs  D0     =  marginal value of W1 semantic seed enrichment
                        (§7.4.2 rider: includes branch ordering; report
                         branch_order_divergence_vs_D0 alongside)

W1-FULL   vs  W1-D   =  marginal value of claim-derived routing

W1-FULL   vs  D0     =  TOTAL marginal value of the LLM-assisted Wiki over
                        the deployable deterministic Wiki  (the A-7 comparison)
```

> **The prohibited inference, stated as a rule.** *Do not conclude that the
> compiler, validator, adjudication process or model dependency was unnecessary
> merely because claim-derived routing did not beat deterministic routing.*
> `W1-FULL ≈ W1-D` establishes one thing only: **the claims did not improve
> routing.** The compiler was still producing the seed representation in both
> arms. Only **D0** can support a statement about whether the LLM layer was
> needed at all.

#### 9.5.2 Mandated readings

**If W1-D beats D0 while W1-FULL does not beat W1-D**, the decision record must
contain this sentence verbatim:

```
W1 added value through semantic seed enrichment, not through
claim-derived routing.
```

and Gate A remains available on A-7 (which compares W1-FULL against D0), with the
compiler priced against the **W1-FULL vs D0** total (§8E).

**If D0, W1-D and W1-FULL are materially equivalent and D0 provides the transitive
win**, then — and **only** then — may the result be attributed to the
deterministic Wiki alone, selecting Gate B. *"Materially equivalent" is
predeclared, not judged after the fact:* all three arms return identical values
for {status, complete-chain represented, required-fact coverage@K,
all-required-retrieved@K} on **every** question. Any divergence on any question
means the arms are not equivalent and the attribution must be stated in the terms
of §9.5.1's deltas instead.

**Full interpretation table, declared in advance:**

| D0 reaches target? | W1-D vs D0 (delta 1) | W1-FULL vs W1-D (delta 2) | Reading that must be recorded |
|---|---|---|---|
| **yes** | no better | no better | All three materially equivalent and **the deterministic projection did the work.** The R5 hypothesis is supported, but *for the deterministic Wiki*. Compiler, validator, adjudication and model dependency were not required → **Gate B**. A legitimate and valuable outcome, not a failure of the stage. |
| **yes** | **better** | no better | **W1 added value through semantic seed enrichment, not through claim-derived routing** (verbatim sentence above). Gate A available if A-7 (W1-FULL vs D0) is met; otherwise Gate B under branch (ii). |
| **yes** | no better | **better** | **Claim-derived routing carried the value**; the enriched seed did not. Gate A available if A-7 is met. Price the compiler against the total, not the routing delta. |
| **yes** | **better** | **better** | **Both model-derived sub-layers contribute.** Record each delta separately; the compiler's total benefit is W1-FULL vs D0 and must be priced against §8E → Gate A possible. |
| **no** | **better** (W1-D reaches) | either | **The model-derived seed representation was necessary for reachability** — D0 could not find the right hub. A strong case for W1 independent of claims. |
| **no** | no better (W1-D also fails) | **better** (W1-FULL reaches) | **Model-derived connectivity was necessary.** The strongest possible case for W1 — and the case in which §8.G's probe should show a reachability loss. Record the mechanism precisely. |
| **no** | no better | no better | **No structural layer preserved transitive reachability** → the R5 hypothesis is falsified (§9.6) → **Gate C**. |

**Prohibited:**

- reporting a W1 win, or any Gate A/B selection, without all three numbers of
  §9.5.1;
- reporting only `W1-FULL vs W1-D` — R5's error — or presenting it as "the"
  marginal value of the Wiki;
- concluding the compiler was unnecessary from any comparison that does not
  include **D0**;
- describing **D0** or **W1-D** as "a control" in the results narrative (§7.4 —
  both are competitors), or describing **W1-D** as free of W1-derived model output
  (it is not);
- quoting the §8.G probe in place of any of the three deltas, since the probe is
  truth-informed, the arms are not, and the probe covers at most delta 2's
  territory.

### 9.6 Falsification — when the hypothesis is NOT supported (new in R5)

The Wiki resilience hypothesis (§1.3.2) is **not supported** if any of the
following is observed, and each is recorded explicitly in the decision record with
its evidence:

| # | Observation | Where measured |
|---|---|---|
| F-1 | required evidence still becomes unreachable when a relevant claim link is missing | §8.G, §9.5 row 4 |
| F-2 | deterministic anchor fallback rarely preserves transitive reachability | **D0** and **W1-D** arms, §8.H `target evidence reachable` |
| F-3 | hub branching prevents reaching the target inside the fixed hop budget `B` | §8.H `branching factor`, `B_bound_hit` |
| F-4 | semantic seed discovery fails to land on useful hubs | §8.H seed metrics; `seed_rank_used`; `seed_page_overlap_vs_D0` |
| F-5 | authority-safe expansion cannot be maintained (any leakage > 0) | §8.H, §9.1 — also a hard-safety failure |
| F-6 | the Wiki improves nothing over authority-aware Vector (V) | §8B |
| F-7 | engineering / ingestion / navigation cost is not justified by the measured value | §8E, §8.H cost rows |

**Evidence *supporting* the hypothesis requires BOTH of the following. Either
alone is insufficient:**

> **1.** Useful transitive evidence is reached that Vector and/or Real Graph
> failed or struggled to recover (§9.4's reachability table, §8B);
> **and**
> **2.** the measured hub/anchor structure **materially contributed** to that
> reachability — established by §9.5's arm comparison — rather than the result
> being explained solely by better LLM extraction (§9.4).

**And a third condition applies specifically to retaining W1 rather than W0:** by
A-7, the *model-derived* portion of the W1 treatment must itself have
contributed, measured as **W1-FULL vs D0** (§9.5.1). *(R6 correction: that
portion may be the **seed representation**, the **claim-derived routing**, or
both — §9.5.2's readings say which, but any of them satisfies the condition.)*
Satisfying 1 and 2 with a mechanism that **D0 reproduces entirely** supports the
hypothesis and selects **Gate B**.

**Predeclared honest expectation, recorded now so the outcome cannot be
retrofitted:** given §0.1 and §1.5.4, the most likely result on this corpus is
that conditions 1 and 2 are both met by the **deterministic D0 layer**, that
W1-FULL vs D0 shows no qualifying improvement, that A-7 therefore fails, and that
the stage resolves to **Gate B**. §6.2's honest note reinforces this: with one
1–2 sentence chunk per revision, the enriched facet vector is close to the V
chunk vector, so delta 1 (**W1-D vs D0**) is expected to be small as well. This
plan is approved on the understanding that Gate B is a likely and acceptable
outcome — indeed, that establishing it cheaply and rigorously is much of the
stage's value. **R6's contribution is that this conclusion will now rest on a
W1-LLM-free measurement rather than on an arm the compiler was seeding.**

---

## 10. Proposed repository changes

> **Principle: this is a POC that must price a capability, not a production Wiki
> platform. No table, module or abstraction is created before the value it serves
> has been demonstrated.** R3 cut R2's proposed surface from 16 modules and 11
> tables to 11 modules and 5 tables. R4 added no module and no table. **R5 adds no
> module and no table either**: the unified flow, the W1-D arm, the §6.6 final-K
> policy and the §8.G suppression probe are all configurations of
> `retrieval.py` + `navigation.py`; the enriched payload is a change to
> `assembly.py`'s composition function; the adjudication verdict set is already a
> `compilation_audit` column. **R6 adds no module and no table either**: the
> **D0** arm is one more configuration of the same two modules — a seed function
> reading the existing chunk-embedding store and the existing `anchor_posting`
> table, then joining the shared flow at §6.4 step [4] — and `M_max` (§6.5) is a
> scalar computed during the existing 7C.0 projection build.

### 10.1 New package — `src/ingestion_bench/wiki_projection/`

| Module | Purpose | Stage |
|---|---|---|
| `model.py` | records for anchors, postings, facets, claims, aliases, summary sentences, derived links | 7C.0 |
| `identity.py` | neutral `identifiers_in` lift; Lane 1 + Lane 2 extraction; deterministic page identity + normalization (shared by W0 and W1) | 7C.0 |
| `projection.py` | W0 build (postings, structural + exact-anchor links), **deterministic facet membership (§2.2)**, and authority-scoped views over canonical chunks | 7C.0 |
| `store.py` | storage protocol + in-memory implementation | 7C.0 |
| `pg_store.py` | isolated Postgres; `IN (...)` before ranking (mirrors 7B.2a `vector_candidate_store.py`) | 7C.0 |
| `compiler.py` | `PROMPT_VERSION` / `prompt_sha256()`, facet prompt builder, §3.9 ceilings, `OpenAIFacetCompiler` + `FakeFacetCompiler` | 7C.1 |
| `validation.py` | §4 deterministic validator (incl. §4.1.15 page coherence, §4.0 membership independence) **and** §3.7 deterministic link derivation | 7C.1 |
| `assembly.py` | authority-scoped facet view, summary filtering, **§6.2 payload composition incl. the identity-bearing passage selector, dedupe and `PAY_max` drop order**, page rendering | 7C.1 |
| `retrieval.py` | the §6.4 unified flow, §6.5 bounds, **§6.6 final-K policy**, saturation accounting; W0 semantic control; **the D0 deterministic seed procedure (§7.4.2)** | 7C.2 |
| `navigation.py` | hub expansion, traversal, §7.3 prioritizer **and D0's deterministic prioritizer substitution (§7.4.2)**, `N_W0` / `N_W1` / `N_advisory` link-set configurations, **the D0 / W1-D / W1-FULL arm configurations (§7.4.3)**, **§8.G read-time suppression filter** | 7C.2 |
| `benchmark.py` | runner, metrics, report; imports the frozen 7B.0 `_evaluate_question` **by identity**; §8.H metric emission; `NON-QUALIFYING / DIAGNOSTIC ONLY` labelling (§8B, §9.2) | 7C.2 |

Plus `config.py` (env-driven, per repo convention).

### 10.2 Other new files

`contracts/wiki_projection_v1.json` (W0 projection + anchor + identity contract —
including the deterministic `display_title` / `page_type` derivation of §3.2, the
**membership rule of §2.2**, the **sentence-splitter definition** used by §6.2
component 5, and — new in R6 — **the D0 seed procedure and D0 prioritizer of
§7.4.2** and **the computed `M_max` value of §6.5** — frozen at 7C.0);
`contracts/wiki_compiler_v1.json` (facet schema
whose model output is exactly `aliases` + `claims` + `summary_sentences`, prompt
version, model identity pinned to the frozen 7B.1 extraction model (§3.8),
ceilings **including `PAY_max` and its drop order**, budget cap, validation rules,
**the §6.2 payload composition order**, **the §6.6 final-K policy**, **the hop
budget `B`, the corrected candidate ceiling `C = (P_seed + B) × M_max × F_max`
(§6.5) and traversable anchor kinds (§7.1)**, Gate Q thresholds **(Q-3 renamed
`revision_scope_contamination`, §9.2)**, retain gates **including the R6-corrected
A-7 and the Gate B evidentiary requirement**, and the §9.4/§9.5 attribution
requirements **including the three mandatory deltas of §9.5.1** — frozen at 7C.1);
`scripts/run_stage7c_wiki_probe.py` (`--fake` / `--in-memory`, as 7B.2a);
`tests/test_wiki_projection.py`, `tests/test_wiki_compiler.py`,
`tests/test_wiki_validation.py`, **`tests/test_wiki_navigation.py`** (membership
independence, suppression filter purity, hop accounting);
`docs/STAGE7C_WIKI_DECISION.md`; `reports/stage7c_wiki_{results.json,
scorecard.md}`; `artifacts/stage7c/` (gitignored, regenerable).

### 10.3 Database tables — five, prefixed `edib_stage7c_`

| Table | Columns (essentials) | Why it must exist |
|---|---|---|
| `anchor` | `anchor_id`, `anchor_kind`, `normalized_value`, `display_text`, `is_ambiguous` | page identity universe, shared by W0 and W1 |
| `anchor_posting` | `anchor_id`, `chunk_id`, `document_revision_id`, `logical_document_id`, `char_span`, `source_ref` | **deterministic membership (§2.2)**, authority filtering, exact-anchor navigation; indexed on `anchor_id`, `document_revision_id` |
| `facet` | `page_key`, `document_revision_id`, `validation_status`, `facet_hash`, `run_id`, **`compiled JSONB`** (validated claims, aliases, summary sentences, derived links) | the compilation record; indexed on `page_key`, `document_revision_id` |
| `facet_embedding` | `page_key`, `document_revision_id`, `embedding VECTOR(dim)`, payload SHA-256, **per-component manifest**, **adjudication verdict-set hash**, provenance (§6.2) | authority-first vector retrieval; indexed on `document_revision_id` |
| `compilation_audit` | raw output, rejections + reasons, `out_of_page_scope` claims, **alias adjudication verdicts**, **summary adjudication verdicts (§3.5)**, `unresolved_identity_mentions`, `payload_truncated_components`, tokens, cost, latency, model, prompt hash, run id, ceiling breaches | §8A/§8E evidence and Gate Q inputs |

**Not created:** `wiki_page`, `wiki_section` (derived views), `wiki_link` (W0 links
derive from postings; W1 links derive from claims in `facet.compiled`), and R2's
four separate claim/alias/summary/candidate tables (now one JSONB column).

Authority filtering is **always** `document_revision_id IN (:eligible)` in the same
statement as ranking/LIMIT.

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

**Unchanged sequence. R5 does not alter the implementation order.**

**Stage 7C.0 — Projection qualification (W0, deterministic, zero LLM calls).**
Anchors, postings, **deterministic facet membership (§2.2)**, structural +
exact-anchor links, deterministic page identity, authority-scoped views,
rendering. Prove hard safety: full provenance, zero benchmark-truth access,
C-88/C-88a separation, deterministic and immutable rebuilds, correct authority
views, no Graph dependency, **membership independence from any future model
output**. Produce projection manifests, rendered sample pages, build-side ledger,
and the W0 ≈ V control measurement. **New in R6:** compute and record `M_max`
(§6.5) from the completed projection, and freeze the **D0 seed procedure and D0
prioritizer** (§7.4.2) — both are deterministic, free of W1-derived model
output, and derived from
artifacts this stage already produces.
**Freeze: the projection contract, the identity/anchor/membership rules, the
sentence-splitter definition, `M_max`, the D0 seed procedure, and the builder.**

**Stage 7C.1 — Compilation qualification (W1 build side only).** Facet compiler,
prompt, schema, ceilings, deterministic validator, deterministic link derivation,
authority-scoped assembly, **§6.2 payload composition**, facet embeddings, the §8F
repeatability runs, §8A compilation metrics, and §4.6 owner adjudication of every
accepted claim, every summary sentence, and every supported alias. The compiler
model is pinned to the frozen 7B.1 extraction model (§3.8). **No retrieval or
navigation is run in 7C.1.** The stage ends by evaluating **Gate Q (§9.2)** and
recording its verdict.
**Freeze: the compiler contract, prompt version + hash, model identity, Run 1's
accepted claim set, derived links, adjudication verdict set, and facet
embeddings.**

**Stage 7C.2 — Retrieval and navigation comparison (read-only).** *Entered
whenever 7C.1 produced a **technically completed** compilation — regardless of
Gate Q pass or fail (§9.2).* Load the frozen 7C.0 projection and frozen 7C.1 **Run
1** facets/embeddings read-only; run the unified flow for the three attribution
arms **`W1-FULL` (primary), `W1-D` and `D0` (§7.4)** plus `N_advisory`
(diagnostic) and the W0 semantic control (§8B); run the **§8.G counterfactual
probe**; emit **§8.H metrics**; run the page-quality rubric (§8D) and the cost
ledger (§8E); perform the **mandatory §9.4 and §9.5 attribution analyses,
including all three §9.5.1 deltas**; apply the §9.3 retain gates; write
`docs/STAGE7C_WIKI_DECISION.md`.

> **D0 runs at 7C.2 for sequencing convenience only.** It depends on nothing from
> 7C.1 — no compiler, prompt, claim, adjudication verdict, facet embedding or
> model call — and reads only the frozen 7C.0 projection plus the existing chunk
> embeddings. It could equally have been measured at 7C.0; it is placed here so
> that all arms share one runner, one evaluator invocation and one report.

> If Gate Q failed, 7C.2 runs identically but every W1 result is emitted under the
> `NON-QUALIFYING / DIAGNOSTIC ONLY` label (§8B), Gate A is unreachable (§9.3), and
> the stage resolves to Gate B or Gate C. Running 7C.2 in that case is a
> **measurement**, not an appeal.

**Freeze boundary.** 7C.1 may not change the 7C.0 projection, identity rules,
anchor rules, membership rules, or hashes. 7C.2 may not change the projection,
compiler, prompt, accepted claim set, derived links, or any embedding — it only
queries and measures. **The §8.G suppression probe is a read-time navigator
filter and writes nothing** (§8.G), so it is inside this boundary.

**No additional variants after W1.** If W1 fails Gate Q or Gate A, the outcome is
Gate B or Gate C — **not** a second compiler, a new prompt, a stronger compiler
model (§3.8), a raised ceiling, a second payload recipe, or a tuned retrieval
flow. Any such proposal is a new stage requiring fresh owner approval.

> **D0 is not an exception to that rule** (R6). It adds **no** model, prompt,
> payload, embedding representation, reranker, planner, module or table. It is an
> **ablation** of the existing pipeline — strictly fewer inputs than every other
> arm — and its seed procedure is frozen at 7C.0 before any measured run, so it
> cannot be tuned toward a result. Adding an ablation removes degrees of freedom;
> it does not expand scope.

---

## 12. Scope exclusions

Another Graph experiment; **a Graph-summary variant**; multiple W1 compiler
variants; **multiple facet payload or embedding variants (§6.2 is singular)**;
**any second embedding representation — D0 reuses the existing V/W0 chunk
embeddings and introduces none (§7.4.2)**; a
stronger-model compiler run or capability-ceiling probe (§3.8); query-time answer
generation; **query-time LLM or ADK reasoning of any kind**; agent workflows;
query decomposition; query-planning LLM; rerankers; retrieval router; ontology
engines; planners; ontology expansion; Neo4j; UI framework implementation; human
approval workflow implementation; vision; vendor-native ingestion; final
direct-document LLM benchmark. The final direct-LLM and provider-managed retrieval
baselines remain on the larger roadmap but are not part of Stage 7C.

---

## 13. Open questions requiring owner approval

| # | Question | Recommendation |
|---|---|---|
| **Q1** | **Per-facet ceilings** (§3.9) — chunks 12, input tokens 8k, claims 20, aliases 8, summary sentences 5, output tokens 4k, breach ⇒ qualification failure and no batching? | Approve; the no-workaround rule is the point |
| **Q2** | **Bounds policy** (§6.5) — `P_seed = K`, hop budget `B`, **`C = (P_seed + B) × M_max × F_max` (corrected in R6; `M_max` computed and frozen at 7C.0)**, rank-1 seed as path origin, no backfill, saturation reported? | Approve. The R5 formula was not a valid upper bound — it multiplied a *per-facet* chunk ceiling by a page count without bounding facets per page. `C` remains a non-selection compute guard |
| **Q3** | **Gate Q thresholds** (§9.2) — accepted-claim precision 0.95, expected-fact recall 0.80, summary correctness 0 incorrect, supported-alias precision 0 incorrect? | Approve or set your own; unchanged from R4 |
| **Q4** | **Gate A improvement** — require **both** partial→solved **and** complete-chain false→true on ≥2 of Q04/Q06/Q07? | Approve; **preserved verbatim in R5** |
| **Q5** | **Repeatability thresholds** (§8F) — N = 3, claim Jaccard ≥ 0.90, citations ≥ 0.95, false merges 0, ceiling breaches 0, Run 1 primary? | Approve |
| **Q6** | **Compiler model and dollar cap** — model pinned to `gpt-4o-mini` @ `temperature = 0` for §9.4 parity; only the per-run dollar cap remains open | Confirm the parity freeze and set the cap |
| **Q7** | **Page-quality rubric** (§8D) — owner alone, blind, 6-page deterministic sample? | Owner alone for 7C; single-rater recorded as a limitation |
| **Q8** | **Hop budget** (§7.3) — global **6**? Note this is *proposed*, not frozen, and under R5 it now binds **retrieval**, not only navigation | Approve 6; the longest target chain is 4 hops (§1.5.2) |
| **Q9** | **`identifiers_in` reuse** — lift the ~4-line regex into a neutral module? | Approve |
| **Q10** | **Summary degradation** (§5.3) — accept shorter/disjointed summaries under narrow authority scope? | Approve |
| **Q11** | **Lane 2 phrase anchors** — in scope for 7C.0? | In scope: `Payment Settlement` is the corpus's only cross-document phrase anchor (§0.1) and the chain is unreachable without it |
| **Q12** | **Adjudication effort** (§4.6) — every accepted claim, summary sentence and supported alias, on Run 1 | Approve — and note R5 makes it **load-bearing for retrieval** (§4.4, §8E), not only for quality |
| **Q13** | **Gate Q semantics** (§9.2) — retention eligibility only; 7C.2 still measures, labelled `NON-QUALIFYING / DIAGNOSTIC ONLY` | Approve |
| **Q14** | **Attribution "similar" band** (§9.4) — ±0.05 on recall and precision against 0.80 / 0.86 | Approve or set your own |
| **Q15** | **NEW — final-K evidence policy** (§6.6) — Tier 1 protected path-establishing chunks in hop order, Tier 2 reached-only chunks by query cosine, truncate to the question's frozen `top_k`, no backfill? | **Approve.** It meets all five stated requirements; its two limits (nearest-first truncation, one wrong hop = one lost slot at zero slack) are declared in §6.6 rather than engineered away |
| **Q16** | **NEW — traversable anchor kinds** (§7.1) — `identifier` and `phrase` traversable; `heading_title` structural-only? | Approve; inert on this corpus, prevents a known scaling pathology |
| **Q17** | **NEW — enriched facet payload** (§6.2) — admit an identity-bearing source passage (2 sentences, 400 chars each, selected by anchor span) and owner-adjudicated-`correct` summary sentences, with exact-match dedupe and a `PAY_max` drop order? | Approve, **with the three costs of §3.5 accepted explicitly** — a summary defect can now move a retrieval number; the representation depends on a human adjudication artifact; and residual claim/summary redundancy is tolerated |
| **Q18** | **Gate A-7** (§9.3) — **REPLACED in R6.** Require `W1-FULL` to outperform the **deterministic `D0`** arm on the target questions before retaining W1 — rather than R5's requirement that `W1-FULL` beat the same-W1-seed `W1-D` arm? | **Approve.** R5's version demanded that claim-derived routing specifically carry the win, which would have discarded genuine value arriving through seed discovery, and rested on a comparison in which the compiler seeded both sides. A-7 still raises the bar over R4; A-2 and every regression rule are unchanged |
| **Q19** | **§8.G probe standing** — truth-informed, therefore **not** admissible as Gate A evidence at all (stricter than "cannot satisfy Gate A by itself"), with the truth-free arms carrying that role — **and, per R6, the probe replaces neither attribution delta** (it covers at most `W1-FULL vs W1-D`)? | Approve; otherwise a benchmark-truth-selected diagnostic would enter a retention decision, or would be mistaken for the `D0` comparison |
| **Q22** | **NEW (R6) — the `D0` deterministic, zero-W1-LLM ablation** (§7.4.2) — add one arm seeded from the existing V/W0 chunk embeddings via deterministic anchor postings, using the deterministic link set, the same `B`, the same §6.6 final-K policy and a deterministic prioritizer substitution; no new LLM, prompt, payload, embedding representation, module or table? | **Approve.** Without it the plan cannot distinguish "the compiler was unnecessary" from "the compiler was doing the seeding", and Gate B would be selected on evidence about a system that could not be deployed |
| **Q23** | **NEW (R6) — the two attribution deltas plus the total** (§9.5.1) — mandate reporting `W1-D vs D0`, `W1-FULL vs W1-D` and `W1-FULL vs D0`, with the prohibition on concluding the compiler was unnecessary from any comparison excluding `D0`, and the verbatim sentence required when seed enrichment carries the value (§9.5.2)? | Approve |
| **Q24** | **NEW (R6) — the §7.4.2 prioritizer rider** — accept that `D0` must substitute chunk embeddings for facet embeddings in branch ordering, so `W1-D vs D0` measures semantic facet enrichment across *both* seeding and branch ordering, bounded by the reported `branch_order_divergence_vs_D0`? | Approve. A W1-LLM-free arm cannot borrow a W1-derived facet vector without ceasing to be free of W1 model output; the rider is measured rather than assumed, and is expected to be near zero on this corpus |
| **Q25** | **NEW (R6) — Gate B evidentiary requirement** (§9.3) — Gate B requires either that `D0` is sufficient or that the measured `W1-FULL vs D0` value is not worth its cost, and may **never** be selected from `W1-FULL ≈ W1-D` alone; plus the predeclared definition of "materially equivalent" (§9.5.2)? | Approve. Selecting Gate B from a same-seed comparison would retire a layer the experiment showed was working — the mirror image of the error A-7 prevents |
| **Q20** | **NEW — corpus limitation acknowledgement** (§0.1, §8.H) — accept that this corpus **cannot** exercise hub branching ambiguity, and that every branching figure carries the mandatory caveat and may never be quoted as evidence about scale? | Approve; the alternative is a larger corpus, which is a separate stage |
| **Q21** | **NEW — likely outcome** (§9.6) — accept that **Gate B is the most likely honest result** on this corpus, and that establishing it rigorously is a successful stage outcome rather than a failure? | Approve before 7C.0 begins; agreeing to this in advance is what prevents the result being renegotiated afterwards |

---

## 14. Diff-of-intent

### 14.1 Revision 4 → Revision 5: what changed

> **Read as a historical record.** Rows 10, 13 and 14 below describe R5's
> *measurement* decisions, which **R6 corrects** — see §14.4. R5's architecture
> rows (1–9, 11–12, 15–20) stand unchanged.

| # | Area | R4 | R5 | Why |
|---|---|---|---|---|
| 1 | **Hypothesis** (§1.3) | resilience located in **ranking**: a missing claim "only perturbs a facet embedding" | resilience located in **deterministic membership + source anchors**; claims provide routing precision, not connectivity | R4's mechanism was contradicted by R4's own §6.4 flow, where a chunk no accepted claim cited was unreachable. R4 made claims a connectivity gate — the same brittleness as Graph |
| 2 | **Role of claims** (§3.7.1) | accepted claims were the sole route to evidence | claims may supply type, direction, priority, explanation and citations; they may **never** be required for membership, chunks, anchors or anchor navigation | makes the graceful-degradation property real rather than asserted |
| 3 | **Membership** (§2.2, §4.0) | implied at build time, discarded at query time | explicit, hard-tested invariant: no LLM output or validation/adjudication outcome may alter membership | this is the structural capital the stage tests |
| 4 | **W1 query flow** (§6.4) | facet search → page group → accepted claims → cited chunks → **second global cosine re-ranking** → K | seed → hub expansion → structural navigation → path evidence → **§6.6 policy** → K; no re-authorization of structurally reached evidence | removes the claim gate and the similarity gate that would have discarded far-end chain evidence |
| 5 | **Final-K policy** (§6.6) | "score every candidate by cosine, truncate" | two-tier: protected path-establishing chunks, then reached-only chunks by cosine | required by (4); preserves K, protects the path, forbids backfill, predeclared, untunable |
| 6 | **Page semantics** (§6.3) | loose language implying page-level retrieval | facet = landing unit; page = hub (**no vector**); links/anchors = movement; chunk = evidence. `seed_page_priority` named explicitly | prevents "semantic page retrieval" being read into a design that has no page embedding |
| 7 | **Facet payload** (§6.2) | title + aliases + accepted claims + headings + identifiers; **summaries excluded** | adds (5) a deterministically selected identity-bearing source passage and (7) owner-adjudicated-`correct` summary sentences; dedupe + `PAY_max` drop order | R4 was too conservative for a flow whose seed quality now determines everything downstream |
| 8 | **Summary status** (§3.5) | presentation only; "a summary defect can never move a retrieval number" | discovery-eligible after adjudication; **that guarantee is explicitly surrendered**, with three costs recorded | honest trade, not a silent one |
| 9 | **Retrieval vs navigation** (§7.2) | two separate measurements | **one pipeline**; navigation is how W1 retrieves | R4 treated them too independently; the value hypothesis is structural reachability after seeding |
| 10 | **`N_W0` status** (§7.4) | a navigation nesting level, and separately a semantic control expected ≈ V | inside the unified flow it is a **retrieval competitor**, expected to be strong on this corpus | without this, a deterministic win could be reported as a W1 win |
| 11 | **New diagnostic** (§8.G) | none | counterfactual claim-link suppression on Q04/Q06/Q07, read-time only, truth-informed, **not Gate-A admissible** | directly tests dependency on claim-derived routing |
| 12 | **New metrics** (§8.H) | retrieval + navigation metrics | full per-question resilience/ambiguity set: seeds, hops, branching, fallback traversals, suppression outcome, costs, sizes | the architectural question is about cost as well as reachability |
| 13 | **Attribution** (§9.5) | one axis: extraction vs representation | second axis added: **deterministic vs model-derived structure** | R5's own redesign creates a new misattribution risk |
| 14 | **Gate A** (§9.3) | A-1…A-6 | **A-7 added**: `N_W1` must beat `N_W0`. A-2's strict rule preserved verbatim | strengthens; prevents retaining a compiler for a deterministic result |
| 15 | **Gate B wording** (§9.3) | "W0 is not represented as a superior semantic retriever" | that sentence retained for W0 *semantic* retrieval; explicitly does **not** apply to the `N_W0` unified arm | R4's wording predates unification and would force a true result to be unreportable |
| 16 | **Falsification** (§9.6) | implicit in Gate C | explicit F-1…F-7, plus the two required conditions for support, plus a predeclared likely outcome | makes the experiment rejectable on the record |
| 17 | **Graph comparison** (§9.4) | extraction figures only | adds a **fact-by-fact reachability comparison** and the required Graph-vs-Wiki failure-mode distinction | requested; and the frozen misses (`F_svc`, `F_prc_current`) are exactly what R5 targets |
| 18 | **Ceilings** (§3.9) | six model ceilings | adds `PAY_max` with a **declared drop order** rather than facet failure, with the asymmetry justified | payload length is a corpus property, not model behaviour |
| 19 | **Regeneration** (§6.7) | five triggers | adds "adjudication verdict changes → re-embed, no model call" | direct consequence of (7)/(8); a real operational cost |
| 20 | **Corpus grounding** (§0.1) | not present | measured corpus shape, and the two consequences that follow | several R5 sections are uninterpretable without it, and it is what bounds the stage's claims |

### 14.2 Revision 4 → Revision 5: what deliberately did **not** change

Stage 7C.0's architecture in full (§2.1, §3.2 — anchors, postings, identity,
`display_title` / `page_type`, both extraction lanes, build-vs-query separation);
every validation rule in §4.1 including the page-coherence rule and the timeless-
status lexicon; the alias controls of §3.3/§3.6/§4.5; owner adjudication scope and
ordering (§4.6); source/model separation (§4.7); Design A and the rejection of
Design B (§5); authority-first SQL; the compiler-model parity freeze (§3.8); the
one-variant rule (§12); Gate Q and all its thresholds (§9.2); the improvement and
regression definitions (§9.3); the mandatory extraction attribution (§9.4); the
`NON-QUALIFYING / DIAGNOSTIC ONLY` regime; the module and table surface (§10); the
7C.0 → 7C.1 → 7C.2 sequence and freeze boundaries (§11); and every frozen
Graph/Vector stage.

### 14.3 Stated limitations of this experiment, recorded before it runs

1. **The corpus cannot exercise branching ambiguity** (§0.1). Six documents, 11
   single-chunk revisions, one cross-document phrase anchor, and a distractor
   domain with no structural bridge. Low branching figures will be a corpus
   property. No claim about navigation cost at scale may be made from this stage.
2. **The most likely honest outcome is Gate B** (§9.6): deterministic membership
   and anchors reconstruct the target chain unaided **from a deterministic,
   W1-LLM-free seed** (`D0`), A-7 fails, and the compiled claim layer is shown to be unnecessary for
   connectivity on this corpus. *(R6: "unaided" now means unaided by any model
   output, including the seed — which is what R5's comparison could not
   establish.)*
3. **Semantic enrichment buys little here** (§6.2): with one 1–2 sentence chunk
   per revision, the identity-bearing passage is nearly the whole chunk, so the
   W1 facet vector is close to the V chunk vector. The seed step is not where
   differentiation will appear.
4. **The §8.G probe is weak-positive by construction** (§8.G): it is expected to
   report "still reachable" trivially. Only a *negative* result from it is strong.
5. **Single-rater adjudication** (§8D, Q7) and **single extraction snapshot per
   side** (§9.4) both remain, unchanged from R4.
6. **W1's representation now depends on a human artifact** (§3.5 cost 2), so it is
   deterministically *reconstructible* but not *derivable* from source + model +
   prompt alone.
7. **`W1-D vs D0` measures facet enrichment across seeding *and* branch ordering**
   (§7.4.2 rider), not seeding in isolation. Bounded and reported via
   `branch_order_divergence_vs_D0`, expected near zero here (new in R6).

### 14.4 Revision 5 → Revision 6: the attribution corrections

**R6 changes no architecture.** Every item below concerns what is *measured*,
what is *compared*, and what may be *concluded*. Stage 7C.0 is untouched; the
compiler, validator, payload, flow, ceilings' *behaviour*, Gate Q thresholds, A-2
and the regression rules are untouched.

| # | Area | R5 | R6 | Why |
|---|---|---|---|---|
| 1 | **Attribution arms** (§7.4) | two: `N_W0` and `N_W1`, **both seeded from the W1 enriched facet representation** | three, named by role: **`D0`** (deterministic, no W1-derived model output, new), **`W1-D`** (= R5's `N_W0` arm), **`W1-FULL`** (= `N_W1`) | R5 held the W1 seed constant in both arms, so it could isolate claim-derived *routing* but could never show the compiler was unnecessary — the compiler was seeding both sides |
| 2 | **`D0` seed procedure** (§7.4.2) | did not exist | predeclared, truth-free, untunable: existing V/W0 chunk embeddings → deterministic anchor postings → seed page identities → shared hub expansion and final-K policy. No second embedding representation | the deployable deterministic Wiki needed a seed of its own; R5 admitted the gap in its Gate B wording and had no arm to fill it |
| 3 | **`D0` prioritizer** (§7.4.2) | n/a | deterministic substitution: chunk-embedding cosine, then link type, then stable key; the resulting rider is *named* and *measured*, not hidden | a W1-LLM-free arm cannot borrow a W1-derived facet vector for branch ordering |
| 4 | **Attribution deltas** (§9.5.1) | one: `N_W1 − N_W0` | three, all mandatory: **`W1-D vs D0`** (seed enrichment), **`W1-FULL vs W1-D`** (claim-derived routing), **`W1-FULL vs D0`** (total) | the R5 hypothesis contains two distinct model-derived contributions; both must be measured independently |
| 5 | **Prohibited inference** (§9.5.1) | absent | explicit: *do not conclude the compiler/validator/adjudication/model dependency was unnecessary merely because claim-derived routing did not beat deterministic routing* | this is exactly the inference R5's single delta invited |
| 6 | **Mandated readings** (§9.5.2) | four-row table keyed on one delta | seven-row table keyed on `D0` reachability × both deltas; the verbatim "seed enrichment, not claim-derived routing" sentence; a predeclared definition of *materially equivalent*; attribution to the deterministic Wiki alone permitted **only** when all three arms are equivalent and `D0` provides the transitive win | removes the interpretive freedom that produced the confound |
| 7 | **Gate A-7** (§9.3) | `N_W1` must beat the same-seed `N_W0` arm | **`W1-FULL` must demonstrate measurable value over `D0`**, with both deltas and the total recorded. **Claim-derived routing need not contribute** if facet enrichment produces the qualifying improvement | R5's version was too narrow (discarded genuine seed-derived value) and unfounded (same-seed comparison). A-2 and the regression rules are preserved verbatim |
| 8 | **Gate B** (§9.3) | selectable when `N_W1` failed to beat `N_W0` | requires evidence that **`D0` is sufficient**, or that the measured `W1-FULL vs D0` value is not worth its cost. **May never be selected from `W1-FULL ≈ W1-D` alone** | selecting Gate B from a same-seed comparison would retire a layer the experiment showed was working |
| 9 | **§8.G probe** (§8.G) | truth-informed, not Gate-A admissible | **unchanged**, plus one added limit: it **replaces neither truth-free delta** and covers at most delta 2's territory | preserved exactly as R5 wrote it, including every caveat |
| 10 | **Candidate ceiling** (§6.5) | `C = (P_seed + B) × F_max` | `C = (P_seed + B) × M_max × F_max`, with `M_max` computed deterministically from the frozen 7C.0 projection and frozen with it | `F_max` is a **per-facet** chunk ceiling; a visited page may expose several eligible facets, so R5's formula was not a valid upper bound. Non-selection compute guard either way; **no measured evidence policy changes** |
| 11 | **Gate Q Q-3 name** (§9.2) | "authority contamination" | **"revision-scope contamination"**; identifier `revision_scope_contamination` | the compiler is authority-blind (§3.1) and cannot contaminate an authority scope. Actual authority leakage remains a query/assembly-time hard-safety metric. **Behaviour and threshold = 0 unchanged** |
| 12 | **Cost attribution** (§8E) | compiler ledger implicitly priced against the routing delta | priced against the **`W1-FULL vs D0`** total; `D0` is the zero-W1-LLM cost floor | pricing a layer against a benefit it only partly produces understates its value |
| 13 | **Reporting vocabulary** (§7.4.3, §8B, §8C, §8H) | `N_W0` / `N_W1` used for both link sets and arms | `N_*` names reserved for **link sets**; `D0` / `W1-D` / `W1-FULL` required wherever an experimental role is meant | the naming collision is what made R5's confound easy to miss |

### 14.5 Post-approval terminology correction (wording only)

One correction was applied after the R6 attribution corrections and before
implementation. **It changed no behaviour, no gate, no attribution logic, no
contract, no measurement and no architecture** — only prose.

**The problem.** R6 described the D0 arm as "zero-model". Read literally that
implies no machine-learning inference is involved at all, which is false: **D0
uses the existing embedding model** — the same query embedding and the same V/W0
chunk embeddings as the frozen Vector baseline. What D0 actually excludes is the
**Stage 7C.1 LLM layer**: the compiler, its claims, aliases, summary sentences,
adjudication verdicts, facet payload and facet embeddings.

**The correction.** The experimental arm identifier **`D0` is unchanged**.
"zero-model" was replaced throughout with, as contextually appropriate:

| Replacement | Used where the point is |
|---|---|
| **`zero-W1-LLM`** | the absence of the Stage 7C.1 compiler layer, especially in cost framing |
| **`no W1-derived model output`** | the precise exclusion (claims, aliases, summaries, verdicts, payload, facet embeddings) |
| **`deterministic D0`** | the Wiki-specific steps being fixed rules over frozen artifacts |

`zero model calls` was likewise narrowed to **`zero LLM calls`** where it meant
"no compiler/generative call", with an explicit note at §2.1 that the W0 semantic
control does invoke the existing embedding model. §7.4.2 carries a binding
reading note stating exactly what D0 does and does not exclude, and forbidding
the unqualified phrase "no model" in reports.

**Unchanged by this correction:** the D0 seed procedure and prioritizer, every
gate, both attribution deltas and the total, `M_max` and the ceiling formula, the
Gate Q rename, all thresholds, every contract, and every measurement.

**What R6 deliberately did not change:** the R5 Wiki Hub Resilience hypothesis
(§1.3.2); Stage 7C.0's architecture; deterministic membership independent of LLM
output (§2.2, §4.0); facet = semantic landing unit, page = information hub with
no page vector, anchors/links = movement, `CanonicalChunk`s = sole authoritative
evidence (§6.3); the semantically enriched revision-scoped facet payload and its
owner-adjudicated summaries (§6.2); no whole-page embedding; authority-first facet
search; semantic seed → hub expansion → structural navigation → evidence (§6.4);
no second global chunk-cosine gatekeeper; no Vector backfill; claims as routing
enrichment rather than connectivity gates (§3.7.1); unified retrieval and
navigation (§7.2); the fixed hop budget; the branching/resilience metrics and the
small-corpus branching limitation (§8.H, §0.1); the claim-omission diagnostic
(§8.G); the frozen Graph comparison and extraction attribution (§9.4); explicit
falsification logic (§9.6); same-model compiler parity (§3.8); no query-time
LLM/ADK; no additional W variants; no Graph rerun; and no scope expansion of any
kind.

---

## 15. Conflicts with existing frozen contracts

The requested experiment was checked against every frozen stage and contract. The
findings are below. **None of them requires reopening a frozen stage**; three
require an owner decision recorded in §13.

### 15.1 No conflict with any frozen stage

- **Stage 7B.0** (`cross_document_benchmark`, the evaluator, the 12 questions and
  15 facts) — used read-only and unchanged; K remains each question's frozen
  `top_k`; the scorer is imported by identity.
- **Stage 7B.1 / 7B.2a** (Graph, Hybrid, Gate D) — read as **documentation only**
  (`reports/stage7b1_*`) for §9.4's comparison. No Graph module, table, artifact or
  output enters the build or query path. **No Graph rerun, improvement, or
  Graph-summary variant** is proposed (§9.4, §12).
- **Stage 7R.1 / 7R.2** (authority) — the resolver is used exactly as specified;
  authority remains query-time and dynamic; no `current` flag is stored anywhere,
  and §4.1.11 keeps enforcing that at the claim level.
- **Stage 7A.2** (`answer_baseline`) — pattern precedent only, never imported; no
  query-time LLM is introduced (§12).

### 15.2 Three points where the request meets a boundary, and how each is resolved

| # | Point | Resolution |
|---|---|---|
| **C-1** | The request refers to "**the frozen global click/hop budget**". **No such frozen value exists.** Nothing in Stage 7C is frozen — the plan is pre-approval — and the click budget is **R4's open question Q8**, proposed at 6. | Treated as **proposed 6**, re-scoped in §7.3 to bind **retrieval** (not only navigation) because of unification, and re-raised as **Q8** with that change flagged. The longest target chain is 4 hops, so 6 leaves slack. |
| **C-2** | The §8.G suppression probe modifies the link set used at query time, while §11's freeze boundary says 7C.2 "may not change … derived links". | Resolved by **construction**: suppression is a **read-time navigator filter over the frozen link set**. It writes nothing and mutates nothing; one query-time configuration ignores part of a stored set. §8.G and §11 both state this explicitly, and `tests/test_wiki_navigation.py` asserts purity. |
| **C-3** | Admitting owner-adjudicated summary sentences into the embedding payload makes the **retrieval representation depend on a human adjudication artifact**, which sits awkwardly with §8F's repeatability framing and §5.1's "hash is a function of (inputs, prompt, model, contract) only". | Resolved by **extending the hash** to include the adjudication verdict-set hash (§5.1, §6.2), adding a **regeneration trigger** (§6.7), restricting payload eligibility to **Run 1** (§8F), and carrying the dependency as an explicit **operational cost** (§8E). Raised for approval as **Q17**. |

### 15.3 Two internal tensions R5 resolves against R4 (not frozen, but recorded)

| # | Tension | Resolution |
|---|---|---|
| **T-1** | R4 §3.5 guaranteed "a summary defect can never silently move a retrieval number"; R5 §6.2 admits adjudicated summaries into the payload. | The guarantee is **surrendered deliberately**, not quietly. §3.5 records the three costs; Q-7's `0 incorrect sentences` bar and the §4.6 pass-3 withdrawal are the mitigations; Q17 asks the owner to accept the trade. |
| **T-2** | R4 §2.2/Gate B required that W0 never be represented as a superior retriever; R5 §7.4 expects the deterministic **unified arms** to be strong. | Separated by name and by definition (§2.3 boundary note, §9.3 Gate B amendment): "W0 semantic retrieval ≈ V" is preserved and remains ungated; `W1-D` and `D0` are different computations and are reported as such. Conflating them is explicitly prohibited. |

### 15.5 One tension R6 resolves against R5 (not frozen, but recorded)

| # | Tension | Resolution |
|---|---|---|
| **T-3** | R5 §7.4 proposed to conclude "the compiler contributed nothing → Gate B" from `N_W1 ≈ N_W0`, while R5 §6.2 simultaneously built the seed representation those arms *both* consumed — and R5 §9.3's own Gate B amendment conceded that "a W0-only deployment would need a seed of its own". R5 therefore contained the counter-evidence to its own inference. | Resolved by **adding the missing arm rather than reinterpreting the existing ones**: `D0` (§7.4.2) supplies the deterministic, W1-LLM-free seed R5 conceded was absent; A-7 is re-pointed at `W1-FULL vs D0` (§9.3); Gate B gains an evidentiary requirement naming `D0` (§9.3); and §9.5.1 mandates all three deltas so neither misattribution can recur. No R5 architecture is altered. Raised for approval as **Q22**, **Q23** and **Q25**. |

### 15.4 One thing the request asked for that this plan declines to promise

The request's §7 says to keep `N_advisory` "only if Revision 4 already requires it
as a diagnostic; it must not become necessary for Gate A and must not add a new
model call." R4 does require it (§7.2 nesting), it adds **no** model call (it
reuses §6.2 embeddings), and §7.3 forbids it from satisfying Gate A. **So it is
retained** — but with the note that nothing else in R5 depends on it, and dropping
it would cost nothing. That decision is left with the owner rather than made here.

---

*Revision 6 — Wiki Hub Resilience experimental contract, attribution-corrected.
**OWNER-APPROVED AND FROZEN.** The R5 Wiki Hub Resilience architecture and Stage
7C.0's architecture are unchanged; R6 altered measurement, comparison and
conclusion rules only, plus the §14.5 terminology-only correction. Stage 7C.0 is
implemented; Stage 7C.1 and Stage 7C.2 are not started and require fresh owner
instruction. No LLM call has been made and no frozen predecessor stage has been
modified; Stage 7B.2a remains frozen at Gate D.*
