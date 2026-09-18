# Stage 11 Plan (Revision 1 — design only, owner review) — Rich-Corpus Knowledge-Interface Benchmark: Vector / Source-Grounded Graph / Deterministic Wiki / Enriched Wiki / Neo4j-Native GraphRAG, Static and Agent

> **Status: DESIGN ONLY.** No corpus exists, no parser has been run, no
> embedding has been generated, no graph or wiki has been projected, no Neo4j
> instance has been created, no retrieval has executed and no Agent has run for
> this experiment. Work stops at the end of this document for owner review
> (§19). Nothing here may be cited as a result.
>
> **This is a new experiment.** Per the briefing, no measured outcome, tuning
> choice, threshold or question-specific observation from Stages 7A/7B/7C is
> carried in. What *is* carried in is architectural: the layer separation
> (D-040), the authority-before-ranking rule, the provenance discipline, the
> metric-naming rules, the one-scorer rule and the freeze discipline — all from
> `docs/CONSOLIDATED_FINDINGS_AND_LEARNINGS.md` §3, which exists precisely so
> these are not rediscovered. Every threshold in this document is justified from
> what *this* experiment needs to be interpretable, never from what a previous
> stage happened to measure; §11.4 says so explicitly for the one gate where the
> temptation is strongest.
>
> **Stages 7B and 7C are frozen and untouched.** No 7B/7C artifact, contract,
> table, report or code path is modified, re-run, reinterpreted or repaired
> here. `wiki_projection/compiler.py` is not imported by any Stage 11 module
> (hard test, §16).

---

## 0. Stage numbering and the Stage 8 relationship — decision required before any work

`docs/POC_STATUS_AND_EVIDENCE.md` records, per D-056: Stage 8 = the Agent/Wiki
experiment (design complete, **never run**), Stage 9 = cross-lane
quality/cost/latency/ROI, Stage 10A/10B = the OpenAI vision / vendor-native
*ingestion* lanes. This briefing is none of those:

- it is **a superset of Stage 8** — Stage 8's `V` vs `W` contrast survives here
  intact as `V` vs `W-D0`, and Stage 8's `V+` / `V-lex` payload and exact-match
  controls are retained because this briefing's §18 asks for the same controls;
  and
- it adds four things Stage 8 explicitly excluded: source-grounded **Graph**
  arms, an **enriched Wiki** treatment (`W1-R`), **Neo4j** as a physical
  substrate, and a **vendor-native** GraphRAG reference.

The vendor-native arm here is *Neo4j GraphRAG*, which is a **retrieval**
comparison. Stage 10A/10B are *ingestion*-lane comparisons against OpenAI. They
are different axes and must not be merged.

**Proposed (owner decision O-1):** this experiment takes **Stage 11**
(`11.0` design, `11A` static, `11B` Agent), and **Stage 8A/8B is withdrawn and
subsumed** — not cancelled as a question, but absorbed, because running both
would author two rich corpora to ask overlapping questions. Stage 8's plan
remains in the repository as the origin of the `V`/`W` contrast and of the corpus
blueprint this plan extends, marked *superseded by Stage 11* rather than deleted.
Stage 9 and Stage 10A/10B keep their numbers and meanings.

**The alternative** — run Stage 8 first, then Stage 11 — is defensible and
cheaper per step, and it buys a clean `V`-vs-`W` reading before the larger matrix
lands. It costs a second corpus build and makes the two sets of numbers
non-comparable. I recommend subsumption, but this is the owner's call, and no
Stage 11 work begins until O-1 is settled.

*Settling O-1 does not approve the rest of this plan. §19 lists the remaining
open decisions.*

---

## 1. The Stage 11 experimental contract

### 1.1 The question

> Does **explicit navigable structure** provide measurable retrieval or
> Agent-research value over flat semantic Vector retrieval, when every treatment
> operates over **the same rich authoritative corpus**, the same evidence
> universe, the same authority rules and the same final evidence budget?

And, secondarily:

> Does a **custom source-grounded** Graph/Wiki design behave materially
> differently from a **vendor-provided** Neo4j GraphRAG implementation — and if
> so, is the difference *extraction* or *retrieval*?

### 1.2 The design commitment that makes the question answerable

Every arm is built from one frozen Canonical evidence set, and the deterministic
arms are built from **one projection-neutral relationship universe** — the Source
Relationship Set (§3.4). `G-SG` and `W-D0` therefore differ in *how the same
relationships are indexed and traversed*, not in *which relationships exist*.

This is the most important structural choice in the plan. Without it, a
Graph-vs-Wiki difference is uninterpretable, because it could be extraction
recall rather than representation — which is exactly the confusion Stage 7B.1 ran
into, and the reason §21 of the briefing insists on attributing results to the
narrow mechanism actually tested.

Only three holders may carry relationships the SRS does not:

| Holder | Extra relationships | Consequence |
|---|---|---|
| `W1-R` | model-derived enrichment (aliases, summaries, statements, derived links) | must pass **Gate Q2** (§11) or every `W1-R` number is `NON-QUALIFYING / DIAGNOSTIC` |
| `G-N4J` | vendor LLM-extracted graph | labelled **vendor-native / LLM-derived**; preceded by **Gate X** extraction measurement (§10.4) |
| *(nothing else)* | — | — |

### 1.3 Hypotheses, stated so each can fail

None is phrased as an expected winner. Operational falsification criteria are in
§18.

- **H1 (Vector).** Flat `V` is at least as strong as every structured arm on
  direct semantic lookup (`T1`, `T2`) and low-hop (`T4`) questions, at every
  tier.
- **H2 (Graph).** `G-SG`'s advantage over `V` is **non-decreasing** in required
  relationship depth and in query→evidence semantic distance, both measured as
  declared covariates rather than asserted.
- **H3 (deterministic Wiki).** `W-D0` improves **reachability robustness** —
  `candidate_recall_before_final_k` and `complete_chain_represented` — over `V`
  on questions whose truth hops are carried by source identity and anchors that
  embeddings under-rank, and does so with no generated layer.
- **H4 (enriched Wiki).** `W1-R` improves ranking and coverage over `W-D0`
  **while** the per-facet and per-page caps hold — i.e. the improvement survives
  the §9 unit-preservation controls and is not produced by facet size or seed
  expansion monopolising final `K`.
- **H5 (Agent effect).** The measured value of navigable structure is **larger
  under an Agent** than under static top-K, for the same representation, corpus,
  authority scope and final `K`.
- **H6 (vendor comparison).** Any `G-N4J` − `G-SG` difference decomposes into an
  **extraction** component (measured against the SRS before retrieval, Gate X)
  and a **retrieval** component (measured with extraction held constant via
  `G-N4J-canon`, §10.5). A difference that cannot be decomposed is reported as
  undecomposed, never attributed.

**H0, the null this experiment must be able to confirm:** at equal budgets over
this corpus, no structured representation beats `V`, and the Agent does not
change that. H0 is a publishable outcome and no test asserts against it.

### 1.4 Arms — summary (full matrix in §9)

| Arm | Substrate | One line | Role |
|---|---|---|---|
| `V` | Postgres/pgvector | authority-eligible chunk vectors, one query, exact top-K | primary baseline |
| `V+` | Postgres/pgvector | `V` plus an index of the **identical** facet payloads `W` embeds, **no** page structure or links | isolates payload repacking from navigation |
| `V-lex` | Postgres/pgvector | `V` plus a deterministic exact-identifier channel | isolates "structure = exact match" |
| `G-SG` | Neo4j | source-grounded graph over the SRS; semantic seeds, bounded traversal | Graph treatment |
| `G-N4J` | Neo4j | Neo4j GraphRAG / KG Builder near stock | vendor reference, **LLM-derived** |
| `W-D0` | Neo4j | deterministic source-grounded Wiki; structure selects the neighbourhood, bounded local selection picks the evidence | Wiki treatment |
| `W1-R` | Neo4j | `W-D0` topology + preregistered semantic enrichment + revised two-stage retrieval | enriched Wiki treatment, gated |

### 1.5 Scope exclusions, recorded before it runs

Not in Stage 11: multimodal/vision evidence (deferred so modality never becomes
a second independent variable — §6.1); the ingestion-lane comparison (Stages
10A/10B); cross-lane ROI (Stage 9); unrestricted Text2Cypher in any primary arm;
production deployment concerns; more than one domain, one generator, one
embedding capability, one primary agent model; any claim about corpora larger
than `S2`.

---

## 2. Architecture

The four layers stay separate, and the separation is enforced by tests, not by
intent. **`(a)` is the rule that makes the comparison legal: no
projection-specific state may enter Canonical (D-040).**

```
  SOURCE DOCUMENTS                        fixtures/stage11/<tier>/*.docx|pptx|pdf
  bytes + per-file SHA-256                        generation_manifest.json
        |
        |  PARSING  (held constant for the primary comparison; varied only in P)
        v
  CANONICAL EVIDENCE MODEL                        [FROZEN, PROJECTION-NEUTRAL]
  CanonicalDocument . CanonicalChunk . CanonicalPicture . units . provenance
  RevisionRegistry (Stage 7R)  - authority resolved at query time, never stored
        |
        |  DETERMINISTIC RELATION DERIVATION                (a) nothing flows back up
        v
  SOURCE RELATIONSHIP SET (SRS)
  typed, directed, evidence-backed; derivation_class in
  {source_explicit, deterministic}          [model_derived is NEVER in the SRS]
        |
        +--------------+---------------+--------------+----------------+
        v              v               v              v                v
  KNOWLEDGE PROJECTIONS (siblings; none authoritative over another)
   +--------+   +-----------+   +--------+   +--------------+   +--------------+
   |   V    |   |   G-SG    |   |  W-D0  |   |     W1-R     |   |    G-N4J     |
   | chunk  |   | nodes +   |   | pages +|   | W-D0 topology|   | vendor LLM-  |
   | vectors|   | typed     |   | facets |   | + model-     |   | extracted    |
   |        |   | edges     |   | + links|   | derived layer|   | graph        |
   +--------+   +-----------+   +--------+   +--------------+   +--------------+
                                                    |                  |
                                              Gate Q2 (S11)       Gate X (S11)
        |              |               |            |                  |
        v              v               v            v                  v
  PHYSICAL SUBSTRATE
  Postgres/pgvector (V, V+, V-lex)        Neo4j (G-SG, W-D0, W1-R, G-N4J)
  gemini-embedding-2 vectors written in as properties; Neo4j NEVER generates one
  Gate P0: substrate parity - exact V in Postgres == exact V in Neo4j, same vectors
        |
        v
  RETRIEVAL / AGENT INTERFACE
  static: one query, one frozen policy per arm, identical final K
  agent : symmetric tool surfaces, identical budgets, identical prompt semantics
        |
        v
  ONE EVALUATOR  (single frozen scorer, import-identity test; no arm may read truth)
```

**Enforced separations.**

| Separation | Enforcement |
|---|---|
| no projection state in Canonical | AST test over `canonical/` + Canonical schema hash equality across all arms |
| no evaluation truth in any build / retrieval / agent path | AST test for subscript and attribute reads of truth fields (7B.0 pattern), extended over every tool-server module |
| Neo4j rebuildable from Canonical + SRS | teardown-and-rebuild test: node, edge and property hash equality |
| Neo4j not the source of truth | every Neo4j node carries `canonical_ref` + `content_sha256`; a node without one fails import |
| one scorer for every arm | import-identity test on the evaluator symbol |
| no embedding regenerated in a measured stage | vector manifest hash verified at the start of every run (§6.5) |

---

## 3. Canonical schema

### 3.1 Reused unchanged (frozen; Stage 11 adds no field to these types)

From `src/ingestion_bench/canonical/model.py` and
`src/ingestion_bench/chunking/model.py`:

`CanonicalDocument` (`doc_id`, `source_format`, `source_filename`,
`source_relative_path`, source SHA, `units`, `headings`, `paragraphs`,
`list_items`, `captions`, `tables` — `CanonicalTableCell` carrying
`row`/`col`/`row_span`/`col_span`/`is_header` — `pictures`, `annotations`,
`provenance`); `CanonicalUnit` (page/slide geometry); `BoundingBox` /
`NormalizedBoundingBox`; `ProvenanceEntry`; `DocumentRevisionContext`
(`logical_document_id`, `document_revision_id`, `version_label`,
`revision_number`); `CanonicalChunk` (`chunk_id`, `doc_id`,
`logical_document_id`, `document_revision_id`, `chunk_index`, `chunk_type`,
`unit_indices`, `heading_path`, `source_element_ids`, `source_refs` —
`ChunkSourceRef` with element / unit / order / bbox / fragment /
`start_char` / `end_char` — `asset_refs`, `source_text`, `model_derived_text`,
`retrieval_text`, `contains_model_derived`, `content_sha256`, `chunker_version`,
`chunking_config_hash`).

This already satisfies every Canonical requirement in the briefing — document
identity, source SHA, chunk SHA, page/slide location, source span, hierarchy,
table geometry, media artifacts — with two exceptions, handled in §3.2 and §3.4:
**revision validity / authority status**, and **relationships explicitly present
in source**.

### 3.2 Authority is resolved, never stored (reused, unchanged)

The Stage 7R registry and resolver decide `effective / current / historical /
draft` against a question's `as_of_date` and `query_intent`. No chunk, node, page
or facet carries an authority label as stored state, and no source document text
states one. Every arm calls the **same** resolver, and the eligibility predicate
is applied **inside** the ranking or traversal query — before any
`ORDER BY … LIMIT`, before any traversal frontier expansion, and before any facet
admission. Retrieve-then-post-filter is prohibited in every arm: it leaks
ineligible revisions whenever the budget is smaller than the number of ineligible
candidates ranked above the first eligible one.

### 3.3 New Canonical-layer artifacts (sidecars, not fields)

| Artifact | Contents | Why a sidecar |
|---|---|---|
| `canonical_evidence_index_v1.json` | every `(chunk_id, content_sha256, logical_document_id, document_revision_id)` | the covering index hash that proves identity *and* content before anything is built on it |
| `canonical_table_records_v1.json` | per `CanonicalTable`: header row, normalized column names, per-row cell values with `(table_id, row, col)` back-refs | table geometry is Canonical; *interpreting* a row as a relationship is derivation |
| `canonical_relation_candidates_v1.json` | the SRS (§3.4) | projection-neutral, derived, independently hashed |

All three are JSON, serialized outside any store, hashed with
`canonical/hashing.py`, and committed.

### 3.4 The Source Relationship Set (SRS)

The briefing requires Canonical to represent "relationships explicitly present in
source"; D-040 forbids projection-specific state inside Canonical. Both hold if
relationships are derived into a **sibling artifact** that every deterministic
projection consumes and none owns.

```
SourceRelation
  relation_id            content-addressed, stable
  subject_ref            EntityRef (identifier family + normalized surface, or anchor key)
  predicate              from the frozen backbone predicate vocabulary (§7.2)
  object_ref             EntityRef
  directed               always true (symmetry is expressed as two relations)
  derivation_class       "source_explicit" | "deterministic"
  derivation_rule_id     which frozen rule produced it (R-TBL-01, R-CUE-03, ...)
  evidence_unit_ids      [chunk_id, ...]   always >= 1
  evidence_spans         [(chunk_id, start_char, end_char), ...]
  document_revision_id   the revision asserting it (authority applies here)
  effective_scope        the scope qualifier the source states, verbatim, or null
  confidence             null for both deterministic classes
```

**Derivation classes, precisely.**

- `source_explicit` — the source states the relation in a machine-recoverable
  structure: a register table row whose header columns are declared in F1
  (`Control ID | Title | Owner | Satisfies | Status` yields
  `CTL-114 --satisfied_by--> OBL-207` read in the declared direction), a
  definition list, or a cross-reference field. No model, no heuristic.
- `deterministic` — a frozen lexical cue rule fires on source text
  (`"<SUBJ> is implemented by <OBJ>"`), with the cue list frozen in F1 **before
  the corpus is authored**. Still no model, but it is an inference and is
  labelled as one.
- `model_derived` — **never enters the SRS.** It lives only in `W1-R`'s
  enrichment artifact or in `G-N4J`'s own graph, each separately hashed and
  separately gated.

**The prose-only residue is the point.** The corpus is authored so that **≥ 30%**
of truth hops are expressible *only* in prose that no table rule and no cue rule
can capture (§7.4). Those hops are invisible to the SRS by construction. That is
deliberate: it is the headroom in which `W1-R` and `G-N4J` can earn a win, and it
is why a deterministic-only result can never be read as "structure does not
help".

**Frozen before the corpus is authored (F1):** identifier families, table-header
vocabulary, cue-phrase list, predicate vocabulary, entity normalization rules. A
derivation rule written *after* seeing the corpus is a rule tuned to the answer
key; the F1 hash is verified before authoring begins.

**Entity normalization** (carried learning, not a new choice): general rules only
— strip leading articles and leading type nouns — and **never merge distinct
enterprise identifiers**. `CTL-114`, `CTL-114A` and `CTL-014` stay three
entities; a hard test asserts it and `normalization_collision_count` is a
released corpus property.

---

## 4. Parsing track

### 4.1 Held constant for the primary comparison

The primary V/G/W/W1-R comparison uses **one** parsing configuration: the frozen
Canonical parsing contract, Docling `DOCLING_STANDARD_LOCAL` (path A), with the
frozen chunker at `ChunkingConfig(max_chars=1200, cross_unit_boundaries=False,
table_as_standalone_chunk=True, picture_as_standalone_chunk=True)` and its
`chunking_config_hash` recorded in F2 and identical for every tier and every arm.

Parsing is the layer most capable of silently deciding a retrieval comparison —
a lost table, a merged heading, a different chunk boundary changes the evidence
universe itself. Holding it constant is what lets a difference between arms be
attributed to the projection.

### 4.2 Sub-experiment P — parser / reference comparison (separate, mechanical, non-contaminating)

Run **only** on a small declared subset (the `S0` document set, all formats), and
**never** feeding the primary comparison.

| Lane | Ingestion |
|---|---|
| **P-A** | Canonical / Docling parsing (the frozen contract) |
| **P-B** | Neo4j native loader / `SimpleKGPipeline` ingestion, near stock |

Compared mechanically, per document, with no retrieval and no arm involved:

| Measure | Definition |
|---|---|
| `text_coverage` | fraction of P-A normalized source characters present in P-B output, by longest-common-subsequence alignment |
| `identifier_retention` | fraction of F1-family identifier occurrences retained, by family |
| `heading_retention` | fraction of P-A headings present, with level preserved |
| `table_preservation` | cells retained; row/column structure retained; header row identified |
| `chunk_boundary_agreement` | Jaccard over character spans of the two chunk sets |
| `provenance_granularity` | deepest available locator per lane (span / element / page / document / none) |
| `omission_rate` | P-A characters absent from P-B |
| `duplicate_text_rate` | P-B characters appearing more than once where P-A has them once |
| `reading_order_agreement` | Kendall's tau over the common element sequence |

Output: `reports/stage11p_parser_comparison.md` plus per-document JSON. **No
threshold, no gate, no winner.** Its only binding effect on the main experiment
is interpretive: if P shows P-B loses material content, then any `G-N4J` deficit
must be reported as *possibly parsing*, and §10.5's `G-N4J-canon` variant becomes
mandatory rather than diagnostic.

**Contamination controls.** P runs after F2 on the same frozen bytes; it writes
no vector, no node and no row that any arm reads; its tables are not inputs to
any gate.
---

## 5. Neo4j's role, projection schema, and the parity requirement

### 5.1 Neo4j is a substrate, not a source of truth

Neo4j holds physical storage, search and traversal for `G-SG`, `W-D0`, `W1-R` and
`G-N4J`. It is **rebuildable from Canonical + SRS**, holds no fact that those
artifacts do not, and is torn down and rebuilt as part of the test suite with
node/edge/property hash equality asserted.

This is a deliberate reversal of the project's earlier position ("Postgres is
sufficient at this scale — no Neo4j"). That position was correct *for Stage 7B's
scale and question*. It is not correct here: `S2` fan-out of up to 120 and 3–6
hop traversal budgets are what Neo4j exists for, and the briefing asks for a
vendor-native comparison that only exists on Neo4j. The reversal is recorded as a
decision, not slipped in.

**Deployment.** `neo4j:5-community` added to `docker-compose.yml` on host ports
**7688** (bolt) and **7475** (http) to avoid clashing with any local default
install, mirroring the existing choice of Postgres 5434. A separate database per
tier (`s11s0`, `s11s1`, `s11s2`) and per projection family, so no arm can read
another's nodes.

### 5.2 Projection schema

```
(:Document      {logical_document_id, title, source_format, source_document_sha256})
(:Revision      {document_revision_id, logical_document_id, version_label, revision_number})
(:Chunk         {chunk_id, content_sha256, chunk_index, chunk_type, heading_path,
                 source_text, retrieval_text, canonical_ref, embedding})
(:Page          {page_key, display_title, page_type, identity_lane})
(:Facet         {facet_id, page_key, document_revision_id, embedding, payload_sha256})
(:Entity        {entity_key, entity_type, normalized_surface, identifier_family})

(:Document)-[:HAS_REVISION]->(:Revision)
(:Revision)-[:HAS_CHUNK]->(:Chunk)
(:Revision)-[:SUPERSEDES]->(:Revision)
(:Page)-[:HAS_FACET]->(:Facet)
(:Facet)-[:CONTAINS]->(:Chunk)
(:Page)-[:RELATED_TO]->(:Page)            typed via `predicate`, always directed
(:Entity)-[:ANCHORED_IN]->(:Chunk)
(:Entity)-[:REL {predicate}]->(:Entity)   the G-SG edge
(:Page)-[:IS_ENTITY]->(:Entity)           identity bridge; Page and Entity are 1:1 on L1 pages
```

**Every derived relationship carries, as edge properties:**

```
derivation_class   "source_explicit" | "deterministic" | "model_derived"
derivation_rule_id
evidence_unit_ids  [chunk_id, ...]        never empty
evidence_spans     [(chunk_id, start, end), ...]
predicate
direction_asserted_by  the evidence span that fixes subject/object order
relation_id        back-reference into the SRS (null only for model_derived)
```

A relationship without `evidence_unit_ids` cannot be imported. **No bare edge is
ever evidence** — only the source chunk it cites is (carried learning, 7B).

**Page ≡ Entity, deliberately.** On identifier-lane pages, the Wiki `Page` and the
Graph `Entity` are the same real-world thing, projected twice. They are kept as
separate labels joined by `IS_ENTITY` so that the `G-SG` and `W-D0` arms can be
measured as different *interfaces over the same identity*, which is precisely the
representation question. A test asserts the bijection on L1 pages and reports the
non-bijective residue (phrase-lane pages with no entity) as a corpus property.

### 5.3 Exact vs approximate search — Gate P0 and Gate P1

The briefing's requirement, made operational:

**Gate P0 — substrate parity (hard precondition, before any arm result is read).**
`V` is computed twice over the *same frozen vectors*: once in Postgres/pgvector
with exact cosine, once in Neo4j with exact cosine. For every question at every
tier, the ranked `chunk_id` list to depth `K` must be **identical**, under the
frozen tie-break rule (`score desc, chunk_id asc`). Any divergence means the
substrate itself is a variable, and every Neo4j-hosted arm is demoted to
`DIAGNOSTIC` until it is resolved. This costs one extra scan and buys the right
to compare a Postgres-hosted baseline with Neo4j-hosted treatments at all.

**Primary benchmark uses exact similarity everywhere.** No arm's primary numbers
come from an ANN index.

**Gate P1 — ANN fidelity (preregistered, run once, before any arm result is
read).** Neo4j's native vector index is built with frozen settings and compared to
exact retrieval: `ann_recall@K ≥ 0.98` averaged over all questions **and**
`≥ 0.95` at every individual question, at every tier. Settings are frozen before
the measurement and **may not be re-tuned after seeing the result** — a failure is
reported as a failure and the operational-ANN claim is withdrawn, not repaired.
P1 has no effect on any primary number; it exists so the plan can say honestly
whether an operational deployment could use ANN.

### 5.4 What Neo4j provides versus what remains custom

| Concern | Neo4j provides | Stage 11 must build |
|---|---|---|
| node/edge storage, labels, properties | ✔ | schema design, constraints, import idempotency |
| Cypher traversal, variable-length paths, shortest path | ✔ | the *bounded* traversal policy, hop budgets, fan-out caps |
| vector index (HNSW) and `db.index.vector.queryNodes` | ✔ | exact-cosine path for the primary benchmark; Gate P0/P1 harness |
| full-text index | ✔ | the deterministic identifier channel and its normalization |
| APOC / GDS path and centrality algorithms | ✔ (unused in primary arms) | — |
| `neo4j-graphrag` KG Builder: schema-guided LLM extraction, splitter, writer | ✔ | freezing its config; the Gate X extraction measurement; span→Canonical attribution |
| `neo4j-graphrag` retrievers (`VectorRetriever`, `VectorCypherRetriever`, `HybridRetriever`, `Text2Cypher`) | ✔ | arm configuration, budget parity, `Text2Cypher` **excluded** from primary |
| embedding generation | ✔ (**deliberately not used**) | shared external adapter (§6); vectors written in as properties |
| authority/revision resolution | ✘ | Stage 7R resolver, applied inside every query predicate |
| provenance to character span | ✘ | `evidence_spans` on every node and edge |
| projection-neutral relationship universe | ✘ | the SRS (§3.4) |
| Wiki page/facet identity, membership, caps | ✘ | the `W-D0` / `W1-R` projection |
| evaluation, metrics, fairness harness | ✘ | one frozen evaluator for every arm |

Read plainly: **Neo4j supplies storage, traversal and a vendor pipeline. Every
property this experiment actually measures — evidence grounding, authority
correctness, bounded policy, fairness, attribution — remains custom.** That is
itself a finding worth recording before the experiment, because it bounds what a
"just use Neo4j" recommendation could mean.

---

## 6. Embeddings — owner-frozen binding

### 6.1 The frozen decision

**Owner decision, recorded as frozen; not re-opened by this plan.**

| Parameter | Value |
|---|---|
| `model_id` | **`gemini-embedding-2`** |
| `output_dimensionality` | **1536** |
| modality | **text only** for the primary experiment |
| normalization policy | frozen, identical across arms (§6.3) |
| similarity function | frozen, identical across comparable arms (cosine) |
| input formatting | Gemini Embedding 2's documented **asymmetric retrieval** roles: query inputs and document/corpus inputs are formatted differently, with both templates frozen **before corpus embedding** |
| generation location | **outside Neo4j**, through one shared adapter |

Gemini Embedding 2 supports flexible dimensionality up to 3,072 (Google
recommends 768 / 1,536 / 3,072). **1536 is used consistently** so dimensionality
does not become a treatment variable. Multimodal input is supported by the model
and is **deliberately not used**: modality would be a second independent variable
inside the Vector/Graph/Wiki comparison. Multimodal retrieval is a later
extension with its own plan.

No substitution of another embedding model without explicit owner approval. If
the hosted model version changes mid-campaign, §6.6 applies.

### 6.2 The shared adapter, and the rule it exists to enforce

```
        gemini-embedding-2
                |
      shared embedding adapter          (one module, one config, one template set)
                |
      frozen embedding artifacts        (manifests + vectors, hashed, committed)
                |
   +-------+---------+---------+------------------+
   |       |         |         |                  |
   V     G-SG      W-D0      W1-R           Neo4j indexes
```

**The same `CanonicalChunk` has the same chunk vector wherever it is consumed.**
`V`, `V+`, `V-lex`, `G-SG`, `W-D0` and `W1-R` all rank chunks with byte-identical
vectors; a test asserts vector-hash equality per `chunk_id` across every arm's
store. No arm regenerates chunk embeddings. **Neo4j never generates a vector for
any arm** — including `G-N4J`, whose own splitter output is embedded *through the
same adapter* with the same model, dimensionality, templates and normalization.
Only the *text* differs there, and that difference is exactly the vendor
treatment being measured.

### 6.3 Representations and their frozen input-construction rules

Different representation objects may legitimately carry different embeddings;
each has a **preregistered, deterministic input-construction rule**, frozen in F4
before any vector is generated.

| `representation_type` | Object | Input construction (frozen template) | Used by |
|---|---|---|---|
| `chunk` | `CanonicalChunk` | `retrieval_text` only — heading context as the chunker already composes it. **No** summaries, aliases, relations, wiki statements, question text or truth. | every arm |
| `facet_d0` | `(page_key, document_revision_id)` | deterministic payload: display title, page type, revision label, ordered anchor spans, member chunk heading paths | `W-D0`, `V+` |
| `facet_r` | same key | `facet_d0` payload **plus** the model-derived enrichment block (aliases, source-grounded summary, statements) | `W1-R` only |
| `edge` | SRS relation | `subject_surface + predicate_label + object_surface + the single evidence span` | `G-SG` seeds |
| `entity` | `Entity` | normalized surface + entity type + the display title of its first source posting | `G-SG` seeds |
| `page` | `Page` | display title + page type + entity type | diagnostic only, never in a primary ranking |
| `vendor_chunk` | `G-N4J` splitter output | the vendor's chunk text, verbatim | `G-N4J` |

**Leakage rule, enforced by test.** A chunk embedding may never contain a summary,
alias, graph relationship, Wiki statement, evaluator label or question-specific
material. The only places such material legitimately enters an embedding input are
`facet_r` (where the enrichment *is* the `W1-R` treatment) and `facet_d0` as
consumed by `V+` (where the payload repacking *is* the control being tested). The
test asserts, per representation type, that the input string is reproducible from
its declared sources alone and matches the stored `input_sha256`.

**Two distinct objects sharing a model do not share a retrieval signal.** A facet
vector and a chunk vector are not interchangeable and are never compared to each
other; index cardinality per representation per tier is a released property,
because a ranking over 5,200 facets and a ranking over 3,200 chunks are different
retrieval surfaces even at equal `K`.

### 6.4 Persisted per embedding (all fields required; the manifest is hashed)

```
object_id                 chunk_id | facet_id | relation_id | entity_key | vendor_chunk_id
representation_type       chunk | facet_d0 | facet_r | edge | entity | page | vendor_chunk
exact_embedding_input     the exact normalized string sent to the API
input_sha256
model_id                  gemini-embedding-2
output_dimensionality     1536
task_role                 RETRIEVAL_QUERY | RETRIEVAL_DOCUMENT
vector                    float32[1536]
vector_sha256
generated_at, adapter_version, api_version, observed_model_version
```

Two manifests are committed and hash-verified before every measured run:
`stage11_embedding_input_manifest.json` and `stage11_vector_manifest.json`.

**Normalization policy (frozen).** Inputs: Unicode NFC, CRLF→LF, internal
whitespace collapsed to single spaces, leading/trailing whitespace stripped, no
case folding, no truncation below the model limit (an over-length input fails
loudly rather than silently truncating). Outputs: L2-normalized once at
generation, stored normalized, and cosine computed as a dot product everywhere —
so no arm can differ by re-normalizing.

### 6.5 Pre-measurement stability and integrity check; then the vectors are authoritative

Before F4 closes, on a frozen stratified sample (100 chunks + 50 facets + 50
edges per tier):

1. **Determinism probe** — each sampled input embedded 3× in separate calls;
   report `identical_vector_rate` and max pairwise cosine deviation. A
   non-deterministic provider is disclosed, not hidden.
2. **Integrity check** — `input_sha256` recomputed from the declared sources;
   `vector_sha256` recomputed; dimensionality and L2 norm asserted.
3. **Degenerate-vector screen** — no zero vector, no duplicate vector across
   distinct `input_sha256`.
4. **Retrieval sanity screen** — a handful of trivially self-matching probes
   confirm the asymmetric query/document templates are wired the right way round
   (a swapped role pair is silent and catastrophic).

**Once F4 closes the stored vectors are authoritative.** No regeneration during
any measured run, for any reason; the manifest hash is verified at run start and
a mismatch aborts the run rather than re-embedding.

### 6.6 Model-drift handling

`observed_model_version` is recorded per call. If it changes mid-build, the build
stops and restarts from scratch on the new version, with the change recorded — a
corpus embedded under two versions is not one embedding capability. If it changes
*between* the build and a measured run, the run proceeds (vectors are frozen and
authoritative) and the drift is disclosed in the scorecard.

---

## 7. Rich corpus specification — `ERL-S11-REGOPS`, tiers `S0` / `S1` / `S2`

### 7.1 Domain, namespace, and why it is authored rather than collected

Regulated-payments change-and-control operations: enterprise-plausible, naturally
register-and-revision shaped, and with **no identifier, phrase or entity reused
from Stage 7C**. The identifier families below are adopted verbatim from Stage 8's
F1 (never used, since Stage 8 never authored a corpus) because they were designed
for exactly this hazard class.

| Family | Regex | Entity type |
|---|---|---|
| `SYS-\d{4}` | System | `System` |
| `SVC-\d{3}` | Business service | `Service` |
| `OBL-\d{3}` | Regulatory obligation | `Obligation` |
| `CTL-\d{3}[A-Z]?` | Control | `Control` |
| `PRD-\d{3}` | Procedure | `Procedure` |
| `STD-\d{2}` | Internal standard | `Standard` |
| `IFC-\d{3}` | Interface / data flow | `Interface` |
| `DE-\d{4}` | Data element | `DataElement` |
| `TPV-\d{3}` | Third-party vendor | `Vendor` |
| `TST-\d{3}` | Control test | `Test` |
| `RSK-\d{3}` | Risk item | `Risk` |

`CTL-\d{3}[A-Z]?` reproduces the near-collision hazard deliberately
(`CTL-114` / `CTL-114A` / `CTL-014`).

Authoring is deterministic and LLM-free, following the frozen Stage-7B.0 fixture
pattern: declarative spec → templated DOCX/PPTX/PDF emission, fixed document
timestamps **and** normalized ZIP entry timestamps so bytes and therefore
`source_document_sha256` are reproducible; generated files tracked in git; a
`generation_manifest.json` of expected SHA-256s re-verified on load with loud
failure.

### 7.2 The semantic backbone — invariant across tiers

One declarative spec, `contracts/stage11_backbone_v1.json`, holding typed
entities and the frozen predicate vocabulary:

```
System      --serves-->          Service
Service     --governed_by-->     Obligation
Obligation  --satisfied_by-->    Control
Control     --implemented_by-->  Procedure
Procedure   --owned_by-->        Role
Control     --tested_by-->       Test
Service     --depends_on-->      Interface
Interface   --carries-->         DataElement
DataElement --classified_by-->   Standard
Interface   --provided_by-->     Vendor
Obligation  --mitigates-->       Risk
Standard    --supersedes-->      Standard
```

**Invariance rule (hard test).** `S0`, `S1` and `S2` share, byte-identically: the
backbone entity set, the typed relation set, every `fact_id` and its
`(subject, predicate, object)`, each fact's authority applicability, every
`question_id`, query string, `required_fact_ids`, `required_evidence_unit_ids`
partition, `forbidden_fact_ids`, `expected_relationship_chain`, accepted answer
surface variants, and per-question `K`. Only the **binding** from a fact to its
`(logical_document_id, document_revision_id, chunk_id)` differs per tier. The
test hashes the tier-invariant slice of each tier's contract and asserts the three
hashes are equal.

**Required-evidence-unit invariance.** The *partition* of each question's required
facts into chunks is also tier-invariant: facts sharing a chunk at `S0` share one
at `S1` and `S2`; facts kept separate stay separate. This holds `U` — and
therefore `K` — constant, so the `K/N` ladder is the only thing moving.

### 7.3 Relationship expression channels — the mechanism the structured arms live or die on

Every backbone fact is authored through exactly one declared **expression
channel**, frozen with the corpus and reported per question per tier:

| `relation_channel` | How the relation appears | Visible to SRS? | Whom it pressures |
|---|---|---|---|
| `table_row` | a register table row under F1 headers | ✔ `source_explicit` | `V` more (table chunks embed poorly) |
| `cue_phrase` | a frozen cue construction in prose | ✔ `deterministic` | neither, particularly |
| `prose_only` | stated in prose with no table row and no cue word | ✘ | `G-SG`, `W-D0` — this is their blind spot |
| `split_across_chunks` | subject and object stated in different chunks of the same facet, joined only by shared identity | ✘ (as a single relation) | `V` most |
| `cross_document` | asserted in one document about entities registered in another | partially | `V` more |

**Declared band, frozen in F1 before authoring:** `prose_only` covers **≥ 30%** of
truth hops; `deterministic_relation_channel_share` — hops visible to the SRS via
`table_row` or `cue_phrase` — lands in **0.45 – 0.70**. Measured and reported
*before* any arm runs; out of band means **re-author, not re-interpret**.

The band's bounds are set by interpretability, not taste. Below 0.45, more than
half the truth hops have no SRS relation at all, so `G-SG` and `W-D0` cannot
assemble most chains *in principle* and any loss is a corpus floor effect. Above
0.70, nearly every hop is pre-linked, navigation degenerates into following a
pre-built answer path, and the structure has effectively encoded the answer key.

### 7.4 Elaboration rules — how richness is added without manufacturing a winner

Every chunk in `S1`/`S2` that is not an `S0` chunk is produced by a declared
elaboration rule and carries a machine-readable `elaboration_reason`:

| `elaboration_reason` | What it adds | Pressures |
|---|---|---|
| `backbone_restatement` | the same fact restated elsewhere with a scope qualifier | all |
| `competing_entity` | another same-type entity with its own true, irrelevant relations | all |
| `qualifier_variant` | near-paraphrase, wrong by jurisdiction / product line / effective period | `V` more |
| `superseded_variant` | the correct relation in an authority-ineligible revision | all |
| `adjacent_domain` | a parallel chain in a neighbouring domain | `V` more |
| `direction_inversion` | lexically similar text asserting the reverse relation | `V`, `G-N4J` more |
| `anchor_fanout_inflation` | a backbone identifier mentioned in chunks irrelevant to it | `W`, `G-SG` more |
| `title_collision` | near-identical register titles and phrase-anchor collisions | `W` more |
| `identifier_variant_noise` | `CTL-114` / `CTL-114A` / `CTL-014` in proximity | `W`, `G-SG` more |
| `prose_only_backbone` | a backbone fact no table row and no cue can capture | `W`, `G-SG` more |
| `alias_drift` | an entity referred to by an unregistered surface variant | `G-SG`, `W-D0` more; `W1-R`'s alias layer exists for this |
| `temporal_conflict` | two eligible-looking statements whose correctness depends on `as_of_date` | all |

**Declared before authoring:** `S1` and `S2` must grow the
structure-adversarial reasons (last five rows) **at least proportionally** to the
`V`-adversarial ones. The per-reason, per-tier audit table is a release artifact.
A richness ladder built only from semantic near-duplicates is adversarial to `V`
alone and would manufacture the result.

### 7.5 Concrete tier targets

Targets, not post-hoc descriptions. Authoring iterates until each tier's measured
profile is inside its band; the profile is then frozen with the corpus (F2) and
published as `reports/stage11_corpus_profile.json`.

| Measurement | `S0` controlled | `S1` rich | `S2` stress |
|---|---|---|---|
| logical documents | 16 | 50 | 150 |
| document revisions | 26 | 95 | 290 |
| chunks (total) | 200 ± 15 | 1,000 ± 60 | 3,600 ± 200 |
| chunk length, median tokens | ~200 | ~320 | ~340 |
| chunk length band | 140–260 (≤ 5 % > 400) | 200–500 (≤ 5 % > 550) | 200–500 (≤ 5 % > 550) |
| facts per chunk, median | 3 (band 2–4) | 4 (band 3–6) | 4 (band 3–6) |
| authority-eligible chunks per question (`N`) | 110–140 | 480–580 | 1,600–1,950 |
| final evidence `K` | `U + 2` (3–8) | `U + 2` (3–8) | `U + 2` (3–8) |
| **`K/N`** | 0.021 – 0.073 | 0.005 – 0.017 | 0.002 – 0.005 |
| SRS relations | ~260 | ~1,400 | ~5,000 |
| Wiki page identities | ~80 | ~290 | ~900 |
| Wiki facets (page × revision) | ~340 | ~1,700 | ~5,800 |
| average chunks per facet | 2.4 | 3.1 | 3.6 |
| maximum chunks per facet | 7 | 18 | 40 |
| average facets per page | 4.3 | 5.9 | 6.4 |
| graph fan-out, average / max out-degree | 4 / 12 | 9 / 40 | 18 / 120 |
| Wiki fan-out (qualifying links per facet), avg / max | 4 / 12 | 9 / 40 | 18 / 120 |
| truth-path depth (hops) | 1–4 | 1–5 | **2–6** |
| competing plausible paths per multi-hop question | 1–2 | 3–6 | 6–12 |
| authored distractors per question | 10–18 | 45–80 | 160–280 |
| alias variants per entity | 0–1 | 1–2 | 2–4 |
| revisions per logical document, median | 1 | 2 | 2 |
| `temporal_conflict` instances | ≥ 6 | ≥ 25 | ≥ 80 |
| hops with **no** lexical/semantic bridge from query text | ≥ 1 on ≥ 20 % of multi-hop Qs | ≥ 30 % | ≥ 40 % |

**`K = U + 2` is held constant across tiers on purpose.** `U` is the count of
distinct required **evidence units** — the distinct canonical chunks carrying the
question's required facts — not the required-*fact* count `R`. Chunks here carry
2–6 facts, so `U ≤ R`; budgeting on `R` would hand every arm `R − U` slots of
invisible slack and blunt exactly the precision pressure the `K/N` ladder applies.
`U` is frozen per question in F3.

**Definitions used by the profile report.** `N` is produced by the Stage 7R
resolver for that question's `(query_intent, as_of_date)`, never hand-counted.
`authored_distractor_count` is design-time, from `elaboration_reason` tags.
`embedding_distractor_density@τ` is measured *after* the embedding build and
*before* any arm runs (eligible non-required chunks with cosine ≥ τ = 0.75 to the
query vector) — a descriptor, never a tuning target. `competing plausible path` is
enumerated deterministically over the SRS link graph.

### 7.6 Pre-freeze validity screens (all before F2/F3; none involves an arm)

1. **Single-chunk sufficiency audit** — for every multi-hop question, prove no
   single chunk, revision or logical document holds all required facts.
2. **Answer-co-occurrence audit** — the answer entity's surface forms must not
   co-occur with the question's distinctive terms in any single eligible chunk.
3. **Lexical-triviality screen** — a declared exact-term-overlap top-`K` baseline
   (no embeddings, not an arm) is run; any question it fully solves is re-authored
   or demoted out of the multi-hop class. Published as a corpus property.
4. **Identifier-leak audit** — no question text may contain a projection-internal
   string (`page_key`, `facet_id`, `relation_id`, `entity_key`, `chunk_id`,
   `document_revision_id`). Corpus-native identifiers are permitted only in the
   classes that declare them; every question records `identifier_mention_count` as
   an analysis covariate.
5. **Channel-share band** — §7.3's `deterministic_relation_channel_share` ∈
   [0.45, 0.70] with `prose_only` ≥ 30 %.
6. **Distractor-mix audit** — counts per `elaboration_reason` per tier with the
   structure-adversarial proportionality check.
7. **Authority-scope audit** — every question's eligible set produced by the frozen
   resolver; every `forbidden_fact_id` classified as *authority-ineligible* or
   *eligible-but-wrong*, because the two score differently.
8. **`K/N`, fan-out and facet-size audit** — against §7.5's bands, including the
   maximum-chunks-per-facet figure that §9's cap is defined against.
9. **Anchor-prevalence audit** — per phrase-anchor posting counts, chunk share and
   document share, with the refusal list produced by the F1 ceiling. The ceiling
   may **not** be adjusted after seeing this.

---

## 8. Question and task taxonomy

### 8.1 Classes (balanced, frozen in F3, tier-invariant)

| ID | Class | Count | What it isolates |
|---|---|---|---|
| `T1` | direct identifier lookup | 4 | `V`'s floor; exact-match parity |
| `T2` | semantic lookup, no identifier in query | 5 | seeding without an identity handle |
| `T3` | near-collision / distractor resistance | 4 | normalization and precision (`CTL-114` vs `CTL-114A`) |
| `T4` | one-hop relationship | 4 | the cheapest structure benefit |
| `T5` | two-hop relationship | 5 | where `V` begins to degrade |
| `T6` | 3–6 hop distributed relationship | 6 | the depth hypothesis (H2) |
| `T7` | temporal / current-vs-historical authority | 4 | authority correctness under conflict |
| `T8` | revision supersession | 4 | stale-but-plausible resistance |
| `T9` | consolidation across multiple chunks | 4 | multi-unit coverage, not ranking |
| `T10` | relationship directionality | 4 | direction errors (7C.1's sharpest failure class) |
| `T11` | source-backed lineage | 4 | chain representation and citability |
| `T12` | evidence split across multiple facets | 4 | §9's unit-preservation question, directly |
| `T13` | required evidence semantically distant from the query | 4 | the navigation-reservation hypothesis |
| | **total** | **52** | |

A question belongs to exactly one primary class and may carry secondary tags;
metrics are reported per primary class, and the secondary tags exist for
covariate analysis only.

### 8.2 Question record schema (frozen in F3)

```
question_id
tier_invariant            true for every field below the divider
query_text                the exact string embedded with the RETRIEVAL_QUERY template
primary_class             T1..T13
secondary_tags            [...]
query_intent              current | historical | as_of        (drives the resolver)
as_of_date
required_fact_ids         [...]                                R = |required_fact_ids|
forbidden_fact_ids        [...]  each tagged authority_ineligible | eligible_but_wrong
expected_relationship_chain  ordered [(subject, predicate, object), ...] or null
answer_surface_variants   accepted final-answer strings
relation_channel_per_hop  [table_row | cue_phrase | prose_only | ...]
required_hop_count        evaluation truth; never shown to any arm
identifier_mention_count  covariate
-------------------------------------------------- per tier --------------------
required_evidence_unit_ids   [chunk_id, ...]      U = |required_evidence_unit_ids|
acceptable_source_chunk_ids  superset: any chunk that discharges a required fact
K                            U + 2
N                            resolver-produced eligible chunk count
```

**`required fact ≠ required evidence unit`, preserved everywhere.** `R` counts
facts; `U` counts the distinct chunks carrying them; `acceptable_source_chunk_ids`
is the wider set of chunks that would *also* discharge a required fact. Coverage
is reported at both levels, never averaged together, and `K` is budgeted on `U`
because `K` budgets chunks.

### 8.3 Subsets and run counts

| Subset | Size | Used for |
|---|---|---|
| **static full** | 52 | every static arm, every tier |
| **agent subset** | 16 | `11B` primary agent runs; stratified across `T1`–`T13` with all six `T6` questions included |
| **repeat core** | 8 | 3 repeats per `(arm, question)` at `S1` and `S2` |
| **practice set** | 6 | harness debugging only; authored separately, **never scored, never in any scorecard** |

The practice set exists so nobody debugs a tool server against a scored question.
A test asserts practice `question_id`s are absent from every result file.
---

## 9. The arm matrix, and the shared bounded-selection policy

### 9.1 Static arms

| Arm | Class | Substrate | Relationship universe | What it isolates |
|---|---|---|---|---|
| `V` | **core** | PG | none | flat semantic baseline |
| `V+` | **core** | PG | none (facet *payloads* only, no links) | payload repacking vs navigation |
| `V-lex` | diagnostic | PG | none | "structure = exact identifier match" |
| `G-SG` | **core** | Neo4j | SRS (`source_explicit` + `deterministic`) | graph representation |
| `G-SG-explicit` | diagnostic | Neo4j | SRS `source_explicit` only | how much the cue-rule inference layer contributes |
| `G-N4J` | **core** | Neo4j | vendor LLM-extracted | vendor-native reference |
| `G-N4J-canon` | **core if P shows parser loss**, else diagnostic | Neo4j | vendor LLM-extracted, but over *Canonical* chunks | separates parsing from extraction+retrieval |
| `W-D0` | **core** | Neo4j | SRS | deterministic Wiki representation |
| `W-D0-rev` | **core** | Neo4j | SRS | `W1-R`'s *retrieval policy* on deterministic artifacts |
| `W1-R-det` | **core** | Neo4j | SRS + enrichment | `W1-R`'s *artifacts* under `W-D0`'s retrieval policy |
| `W1-R` | **core** (gated) | Neo4j | SRS + enrichment | enriched Wiki: artifacts **and** policy |
| `W1-R[E·L·R]` cells | **core** (6 cells, one of which *is* `W1-R`) | Neo4j | SRS + enrichment | §9.6 eligibility × selector × reservation factorial |
| `W-D0[−R]` | diagnostic | Neo4j | SRS | reservation contribution without enrichment |

**`W-D0-rev` and `W1-R-det` are not decorations.** The briefing defines `W1-R` as
"enriched Wiki **+ revised retrieval**" — two independent variables moved at once.
Without these two arms, a `W1-R` − `W-D0` delta cannot be attributed to either.
This is the single largest accidental-confound risk in the briefing as written,
and §17.1 lists it first.

### 9.2 Agent arms

| Arm | Class | Condition |
|---|---|---|
| `Agent-V` | **core** | — |
| `Agent-W-D0` | **core** | — |
| `Agent-G-SG` | **core** | — |
| `Agent-W1-R` | **core** | only if Gate Q2 passes; otherwise runs and is labelled `NON-QUALIFYING / DIAGNOSTIC` |
| `Agent-V+` | **core control** | run at `S1`, and at `S2` whenever an agent advantage is found at `S2` |
| `Agent-G-N4J` | diagnostic | only if interface parity (§13.4) can be maintained; otherwise omitted with the reason recorded |

### 9.3 Held identical across every static arm

Corpus bytes; Canonical artifacts; chunker and config hash; the Stage 7R resolver
and its `(query_intent, as_of_date)` inputs; chunk vectors; similarity function
(cosine over L2-normalized vectors); tie-break (`score desc, chunk_id asc`); final
`K = U + 2`; the evaluator; the provenance record attached to every returned
chunk. **The only thing that varies is how the candidate set is discovered and
ordered.**

### 9.4 The four-stage decision every structured arm must express separately

```
   PAGE / FACET / NODE ADMISSION      "which neighbourhood deserves attention"
              |
              v
   EVIDENCE ELIGIBILITY               "which chunks there are even candidates"
              |
              v
   BOUNDED LOCAL SELECTION            "which of those, at most c_max, are taken"
              |
              v
   FINAL K                            "which of all candidates fill the budget"
```

These are four decisions, not one. Every arm records, per question, the size of
the set at each stage, and every admitted chunk records which stage admitted it
(`selection_reason` ∈ `semantic | structural_reserved | identity_exact |
local_selector`). Collapsing any two of them is the failure mode §21 of the
briefing warns about: "Wiki does not work" is unreadable when the measured
mechanism could have failed at any of four places.

### 9.5 Preregistered bounds — the unit-preservation policy

Frozen in F5-S before any arm runs. **Facet admission is never evidence
admission.**

| Bound | Value | Why this value |
|---|---|---|
| `P_seed` — neighbourhoods admitted at Stage A | **5** | must exceed the deepest truth chain's distinct facets (≤ 4 at `S0`) without letting Stage A become a top-K of its own |
| `M_max` — navigation hops | **3** | `T6` needs 3–6 hops; 3 hops from up to 5 seeds reaches a 6-hop chain from both ends. Higher is not "more navigation", it is an unbounded scan |
| `c_max` — chunks contributed to final `K` by any one **facet** | **2** | `S2` facets hold up to **40** chunks and `K` is 3–8; without this cap one facet could fill `K` entirely and "navigation" would mean "pick a big facet" |
| `p_max` — chunks contributed by any one **page** | **3** | a page has ~6 facets at `S2`; page-level saturation is the same failure one level up |
| `e_max` — chunks contributed by any one **graph edge** | **2** | the `G-SG` counterpart of `c_max` |
| `r_nav` — final-`K` slots reserved for the structural lane | **`min(2, ⌊K/3⌋)`** | with `K` ∈ 3–8 this is 1–2 slots: enough for a semantically distant but structurally justified hop to survive, small enough that structure cannot outvote semantics |
| `C_max` — total candidates before final `K` | **200** | bounds cost and makes `candidate_recall_before_final_k` comparable across arms |
| `F_max` — neighbours expanded per node/facet per hop | **20** | `S2` max fan-out is 120; without this, one hub node is the whole frontier |

**`c_max` is the briefing's §9 correction made numeric.** Ten chunks in a facet do
not become ten protected chunks; nor is only the single link-establishing chunk
protected (that is `E1`, tested as an ablation in §9.6). The reached
neighbourhood's authority-eligible chunks become *candidates*, then at most
`c_max` of them are taken, independently of how large the facet is.

`facet_size_independence` is reported as a check: the correlation between a
facet's chunk count and the number of final-`K` slots it wins. A design whose
correlation approaches 1 has failed this policy regardless of its retrieval score.

### 9.6 The navigation-reservation experiment, as a factorial

Two variables, tested separately rather than assumed to co-vary:

*(Level codes are `E…` and `L…` so they can never be confused with the tier names
`S0`/`S1`/`S2`.)*

| Factor | Level `E1` | Level `E2` |
|---|---|---|
| **eligibility expansion** | only the chunk whose link established the hop | all authority-eligible chunks in the reached facet, then `c_max` |

| Factor | Level `Lc` | Level `Lw` |
|---|---|---|
| **within-navigation selection** | local `cosine(query, chunk)` | the frozen Wiki-native selector (§10.6.3) |

Four cells, each run at every tier, plus reservation on/off on two of them:

| Cell | Eligibility | Selector | Reservation | Role |
|---|---|---|---|---|
| `W1-R[E2·Lc·+R]` | expanded | cosine | on | **this is `W1-R` proper** |
| `W1-R[E1·Lc·+R]` | link chunk only | cosine | on | the too-narrow bound |
| `W1-R[E2·Lw·+R]` | expanded | Wiki-native | on | does a structural selector beat cosine locally? |
| `W1-R[E1·Lw·+R]` | link chunk only | Wiki-native | on | interaction check |
| `W1-R[E2·Lc·−R]` | expanded | cosine | **off** | the reservation lane's own effect |
| `W1-R[E1·Lc·−R]` | link chunk only | cosine | **off** | reservation effect at the narrow bound |

All six reuse the frozen vectors and the frozen Wiki; they cost scans, not
builds. **Final `K` is held constant in every cell.** No cell may enlarge the
evidence budget — the one move that would make Wiki look better for no reason.

---

## 10. Retrieval algorithms

Notation: `Q` is the query vector (`RETRIEVAL_QUERY` template); `E(q)` is the
resolver's authority-eligible chunk set for question `q`; `cos(a,b)` is a dot
product over L2-normalized vectors.

### 10.1 `V`, `V+`, `V-lex`

```
V(q):
  eligible = resolver.eligible_revisions(q.query_intent, q.as_of_date)
  return top_K( cos(Q, chunk.embedding)
                WHERE chunk.document_revision_id IN eligible )   # predicate INSIDE
       ordered by (score desc, chunk_id asc)
```

Frozen: cosine; `K = U + 2`; the eligibility predicate inside the ranking query;
tie-break. No structure of any kind.

`V+` runs the identical query over a union index of chunk vectors **and**
`facet_d0` vectors; a facet hit contributes its member chunks under `c_max`,
scored by the facet's own score, with **no links, no pages and no traversal**. It
answers: is the benefit "entity-keyed payload repacking" rather than navigation?

`V-lex` adds a deterministic exact-identifier channel: identifiers in the query
text (F1 regex) match chunks containing the same identifier, and those chunks are
merged ahead of ties at equal cosine, under the same `K`. It answers: is the
benefit just exact matching?

### 10.2 `G-SG` — source-grounded Graph

```
G-SG(q):
  # --- Stage A: seeds ---
  seeds  = top_s( cos(Q, entity.embedding) )  ∪  top_s( cos(Q, edge.embedding) )
  seeds += exact identifier matches from q.query_text          # identity lane
  seeds  = dedup(seeds)[:P_seed]                               # s = 8, P_seed = 5
  record seed_count, seed_kind per seed

  # --- Stage B: bounded traversal (authority predicate inside the expansion) ---
  frontier = seeds; visited = {}
  for hop in 1..M_max:
      for node in frontier:
          nbrs = OUT/IN edges of node
                 WHERE edge.document_revision_id IN eligible     # INSIDE
                 ORDER BY (cos(Q, edge.embedding) desc, relation_id asc)
                 LIMIT F_max
          for each traversed edge:
              path_score(edge) = decay^hop * seed_score(origin)   # decay = 0.6
              candidates += evidence chunks of edge, at most e_max per edge,
                            each tagged (relation_id, hop, path_score)
      stop when |candidates| >= C_max

  # --- Stage C: final K, scores kept separate ---
  for c in candidates:
      semantic_score(c) = cos(Q, c.embedding)
      path_score(c)     = max path_score over the edges that contributed c
      final_score(c)    = semantic_score(c)              # ranking is semantic
  take r_nav slots by path_score desc  -> selection_reason = "structural_reserved"
  fill remaining K - r_nav by final_score desc           -> "semantic"
  return with (semantic_score, path_score, final_score, selection_reason,
               path provenance = ordered [(relation_id, evidence chunk, span)])
```

`decay = 0.6` and `s = 8` are frozen in F5-S with the rest. Evidence is always the
cited chunk, never the edge. Path provenance is returned whether or not the path
contributed to `K`, because `complete_chain_represented` is measured over
candidates as well as over final `K`.

### 10.3 `W-D0` — deterministic source-grounded Wiki

**Projection.** Pages from two identity lanes, frozen in F1 *before authoring*:
`L1` governed identifiers (the F1 families), `L2` repeated business phrases
(≥ 2 tokens, ≥ 2 distinct chunks, ≥ 2 distinct logical documents, identifier
tokens win, prevalence ceiling enforced with a refusal log). Headings anchor but
**do not create page identity**. A facet `(page_key, document_revision_id)` exists
if and only if that identity has ≥ 1 anchor posting in that revision — membership
never depends on a model, a summary, a validation outcome or an authority state.
Links: structural (document / revision-sibling), `exact_anchor` (this same
source-backed identity occurs there — asserts *no* relationship), and **typed
source-backed links projected from the SRS** (`predicate`, directed,
`evidence_unit_ids`). No generated claim layer. No summaries.

```
W-D0(q):
  # --- Stage A: neighbourhood selection ---
  A = top_P_seed( cos(Q, facet_d0.embedding)
                  WHERE facet.document_revision_id IN eligible )
  A += facets of pages whose page_key matches an identifier in q.query_text
  A  = dedup(A)[:P_seed];  record hop-0 seed pages/facets

  # --- Stage A': bounded navigation, M_max hops ---
  for hop in 1..M_max:
      for f in frontier:
          links = typed + exact_anchor links out of f
                  WHERE destination facet revision IN eligible
                  ORDER BY (link_type_rank, cos(Q, dest_facet.embedding) desc,
                            page_key asc)                      # deterministic
                  LIMIT F_max
          reached += destination facets, tagged (link_id, link_type, hop,
                                                 establishing chunk)
      stop when |candidates| >= C_max

  # --- Stage B: bounded local evidence selection (the unit-preservation step) ---
  for f in (A ∪ reached):
      eligible_chunks(f) = members of f WHERE revision IN eligible     # E2
      take top c_max by cos(Q, chunk.embedding)                        # Lc
      enforce p_max across the facets of one page
      tag each with (facet_id, page_key, hop, link_id, admission_source)

  # --- Stage C: final K ---
  r_nav slots  <- candidates from hop >= 1, ordered by (hop asc, link_type_rank,
                  cos desc)                    -> "structural_reserved"
  remaining    <- all candidates by cos desc   -> "semantic" | "identity_exact"
  return with full provenance and per-stage counts
```

Core `W-D0` therefore is *"structure discovers the candidate set; query cosine
ranks the evidence inside it"*, plus a small reserved lane so a semantically
distant hop can survive. This makes a static `W-D0` win **more** likely than a
traversal-ordered design would, and that is stated here, before measurement, so
the outcome cannot later look like a moved goalpost.

### 10.4 `G-N4J` — Neo4j-native GraphRAG reference

**Labelled, everywhere it appears: `vendor-native / LLM-derived graph`.** Its
extracted graph is never treated as ground truth, and it is never used to
validate, seed, correct or filter any other arm.

Built with `neo4j-graphrag`'s `SimpleKGPipeline` / KG Builder as close to its
supported intended configuration as practical. Frozen in F5-S before any arm
runs, and hashed:

| Frozen | Value |
|---|---|
| extraction LLM | one named model + version, `temperature = 0` |
| extraction prompt | the library's default template, recorded verbatim |
| schema | the **frozen backbone entity types and predicate vocabulary** (§7.2) |
| splitter | the library's default, its config recorded |
| embeddings | **the shared adapter** (§6.2) — `gemini-embedding-2`, 1536-d, same templates; Neo4j generates nothing |
| retriever | `VectorCypherRetriever` with the library's default traversal expansion |
| budgets | the same `K`, `C_max`, `F_max` and authority predicate as every other arm |

**Giving the vendor arm the backbone schema is a deliberate concession, and it is
parity, not leakage.** `G-SG` is built from the same frozen predicate vocabulary;
withholding it from `G-N4J` would measure schema discovery, not retrieval. Neither
arm receives evaluator truth, required/forbidden facts, expected chains or
`elaboration_reason` tags.

**Gate X — extraction quality and repeatability, measured before any `G-N4J`
retrieval claim.** Against the SRS, restricted to SRS-visible channels
(`table_row` + `cue_phrase`) so the comparison is fair — prose-only relations are
outside the SRS and are reported separately as *vendor-only extractions*, which is
where the vendor arm can legitimately exceed the deterministic arms:

| Measure | Definition |
|---|---|
| `relation_precision` / `recall` / `f1` | against the SRS under a frozen matching rule (normalized subject, predicate, object; direction significant) |
| `direction_accuracy` | of matched relations, the fraction with the same direction |
| `entity_resolution_precision` | distinct SRS entities not merged; `CTL-114` vs `CTL-114A` never merged |
| `vendor_only_relation_count` | extracted relations with no SRS counterpart, sampled and human-adjudicated (100 per tier) into *correct prose-only* / *incorrect* |
| `extraction_repeatability` | 3 runs on a frozen stratified 10 % chunk sample: accepted-relation-set Jaccard, plus the *same-output/different-outcome* vs *different-output* split |

**Gate X has no pass/fail threshold and blocks nothing.** It supplies the
denominators that make H6's decomposition possible. Its binding effect is
interpretive: a `G-N4J` deficit may not be attributed to retrieval unless Gate X
shows extraction recall is comparable, and a `G-N4J` win may not be attributed to
the vendor retriever unless `vendor_only_relation_count` and `G-N4J-canon`
together say so.

### 10.5 `G-N4J-canon` — the parsing/extraction separator

`G-N4J`'s pipeline changes **five** things at once relative to `G-SG`: parser,
chunker, extractor, graph shape and retriever. `G-N4J-canon` runs the vendor's
extractor and retriever over **Canonical chunks** (the frozen parse, the frozen
chunker, the frozen chunk vectors), holding parsing constant.

```
G-SG            canonical parse | canonical chunks | deterministic SRS | custom retriever
G-N4J-canon     canonical parse | canonical chunks | vendor extraction | vendor retriever
G-N4J           vendor parse    | vendor chunks    | vendor extraction | vendor retriever
```

`G-N4J-canon − G-SG` isolates extraction + retriever. `G-N4J − G-N4J-canon`
isolates parsing and chunking. Neither difference is interpretable without the
other, which is why `G-N4J-canon` is **core whenever sub-experiment P shows
material parser divergence** and diagnostic otherwise.

**Cross-parser evidence attribution (a measurement problem, not a detail).** The
evaluator scores Canonical `chunk_id`s. `G-N4J`'s evidence is vendor chunks, which
do not exist in Canonical. Attribution rule, frozen before measurement: a vendor
chunk maps to every Canonical chunk with which it shares **≥ 50 % of that
Canonical chunk's characters**, by span alignment on the normalized source text.
A vendor chunk mapping to nothing increments `unattributable_evidence_count`. A
`G-N4J` result whose unattributable rate exceeds **0.10** on a question is
reported with an explicit attribution caveat, and the rate is published per tier.
This rule can only *lose* credit for the vendor arm where alignment fails, never
invent it, and the direction of that bias is recorded in §17.

### 10.6 `W1-R` — enriched Wiki and revised retrieval

#### 10.6.1 The enrichment layer (built once, frozen, separately hashed)

Compiled per **facet** (never per page, never across revisions) by a bounded
compiler at `temperature = 0`, producing four kinds of artifact, each one
**physically separated from source evidence** in storage, in the payload, and in
every returned record:

| Artifact | Bound | Separation |
|---|---|---|
| `alias` | ≤ 4 per facet; each must be a verbatim span in a member chunk | `derivation_class = model_derived`, with `(chunk_id, start, end)` |
| `summary` | ≤ 3 sentences; every sentence must cite ≥ 1 member chunk span | rendered in a distinct block; never concatenated into `source_text` |
| `statement` | ≤ 6 per facet; `(subject, predicate, object)` with predicate from the frozen vocabulary; must cite a member chunk span | stored as `model_derived` relations, never written into the SRS |
| `derived_link` | only between facets already sharing an entity or statement subject/object | `derivation_class = model_derived` on the edge |

`W1-R`'s page/facet **topology is `W-D0`'s, unchanged** — same identity lanes,
same membership rule, same structural and `exact_anchor` links, same authority
behaviour. Enrichment adds semantics to facets and adds derived links; it may
never create, delete or move a facet. A hard test asserts facet-set equality
between `W-D0` and `W1-R`.

#### 10.6.2 Retrieval — the two nested decisions, stated as two

```
W1-R(q):
  # --- Stage A: neighbourhood selection (which page/facet deserves attention) ---
  signals, all preregistered, combined by frozen rank fusion (RRF, k0 = 60):
     a. cos(Q, facet_r.embedding)          # enriched facet semantics
     b. Wiki path: facets reachable in <= M_max hops from an A-seed
     c. source anchor / exact identifier match on page_key
     d. source-backed statement match: statement subject or object matches a
        query identifier or normalized phrase
  A = top_P_seed(fused)                    # P_seed = 5, unchanged from W-D0

  # --- Stage B: evidence selection inside the reached neighbourhood ---
  for each structurally qualified facet f:
      eligible_chunks(f) = members WHERE revision IN eligible     # E2
      score by the selector under test (Lc = cosine, Lw = §10.6.3)
      take at most c_max;  enforce p_max per page
  # --- Stage C: final K, with r_nav reserved (identical to W-D0) ---
```

**Stage B's score is a local selector inside a structurally qualified lane, not a
global ranking signal.** It is never compared across facets, never used to admit a
facet, and never used to break ties in the semantic lane. Reported separately so
the two can never be conflated.

#### 10.6.3 The Wiki-native selector (`Lw` level; truth-free, frozen before measurement)

For chunk `c` in facet `f` reached by link `L`:

```
wiki_local_score(c) = 1.0 * anchor_density(c, f.page_key)
                    + 1.0 * relation_compatibility(c, predicate(L))
                    + 0.5 * heading_specificity(c)
```

- `anchor_density` — postings of `f`'s identity in `c`, normalized by `c`'s token
  count.
- `relation_compatibility` — 1 if `c` carries an SRS relation with `predicate(L)`
  or its inverse, 0.5 if it carries any relation between `f`'s entity and any
  entity, else 0.
- `heading_specificity` — depth of `c.heading_path` normalized by the document's
  max depth.

Weights `(1.0, 1.0, 0.5)` are frozen in F5-S **before any measurement** and may
not be tuned afterwards. No benchmark truth, no per-question material, no
evaluator label enters this function — enforced by the AST test.

---

## 11. Gate Q2 — the `W1-R` qualification gate

Fresh for Stage 11. **No qualification is inherited from any earlier stage**, and
no earlier stage's outcome sets a threshold here.

### 11.1 Population and timing

Evaluated on the **frozen, as-built** `W1-R` enrichment artifact, per tier, after
the compile and **before any `W1-R` retrieval runs**. Adjudication sample: 120
accepted statements + 80 aliases + 60 derived links per tier, drawn by a frozen
stratified sampling frame (by page type, facet size, and revision status) declared
before the compile.

### 11.2 Dimensions, metrics and thresholds (all frozen before measurement)

| # | Dimension | Metric (named for exactly what it counts) | Threshold |
|---|---|---|---|
| Q2-1 | source support | `accepted_statement_citation_validity` — cited span exists, is inside a member chunk of that facet, and the chunk's `content_sha256` matches | **1.000** |
| Q2-2 | semantic correctness | `adjudicated_statement_semantic_accuracy` on the sample | **≥ 0.90** |
| Q2-3 | directionality | `adjudicated_statement_direction_accuracy` on statements whose predicate is asymmetric | **≥ 0.95** |
| Q2-4 | alias correctness | `adjudicated_alias_referent_accuracy` (alias denotes the page's entity, not a neighbour) | **≥ 0.95** |
| Q2-5 | revision correctness | `statement_revision_scope_accuracy` — statement asserted only from spans in its own revision | **1.000** |
| Q2-6 | malformed structure | `malformed_triple_rate` — missing/empty subject, object or out-of-vocabulary predicate | **≤ 0.02** |
| Q2-7 | unsupported links | `unsupported_derived_link_rate` — derived link with no shared entity and no statement basis | **≤ 0.02** |
| Q2-8 | repeatability | `accepted_statement_set_jaccard` over 3 compiles of a frozen 10 % facet sample | **≥ 0.90** |
| Q2-9 | repeatability decomposition | of Jaccard misses: `same_output_different_validation_outcome` vs `different_output` | report only |
| Q2-10 | stability distribution | per-facet identical-output rate, reported beside the aggregate | report only |

Q2-3 is the highest bar because direction errors are the failure that silently
inverts a lineage answer while every citation stays valid. Q2-1 and Q2-5 are at
1.000 because they are mechanical: a citation that does not resolve, or a
statement asserted from another revision's text, is a build defect, not a quality
score.

### 11.3 Two implementation rules, carried from the metric-naming learnings

1. **The gated quantity is computed in the same function that compares it to its
   threshold.** A contract that states a metric twice will diverge, and the
   implementation will follow the prose while the report prints the threshold's
   label.
2. **The population is asserted in the metric's own name.**
   `accepted_statement_set_jaccard`, never `statement_jaccard`.

### 11.4 Where these thresholds come from — stated plainly

They come from what this experiment needs to remain interpretable, not from any
prior measurement:

- **Q2-1/Q2-5 at 1.000** — mechanical properties; anything less is a build bug.
- **Q2-3 at 0.95** — a lineage answer is wrong if one hop is reversed, so the
  direction error rate must be well below the per-question hop count's reciprocal
  (chains here run 3–6 hops, so 0.95 gives a chain-level direction-correctness
  expectation of roughly 0.74–0.86; below 0.95 the enriched layer cannot support
  `T11` at all).
- **Q2-2/Q2-4 at 0.90/0.95** — an enrichment layer wrong more than one time in ten
  would be measuring the compiler, not the representation.
- **Q2-8 at 0.90** — "no more than one accepted statement in ten moves on a
  rebuild". This is the reproducibility requirement (§15) expressed as a number.

**An honest disclosure, made before the run:** a bounded compiler at
`temperature = 0` has previously been observed in this repository to be stable on
simple input and unstable on compound input, and Q2-8 is the dimension most likely
to fail. That is a reason to *expect* a possible failure, not a reason to lower the
bar. **If Gate Q2 fails on any threshold, every `W1-R` and `Agent-W1-R` number is
reported as `NON-QUALIFYING / DIAGNOSTIC` — even if `W1-R` beats every other
arm** — and the failing dimension is named in every table where those numbers
appear. The stage does not abort; `W-D0`, `G-SG`, `V` and `G-N4J` are unaffected,
and the §9.6 factorial still runs, because the mechanism question is separable
from the artifact-quality question.

---

## 12. Static metric specification

One evaluator, imported by every arm (import-identity test). No arm reads truth.
**No composite winner score is computed, at any level, ever.**

### 12.1 Retrieval-quality metrics — per question, per tier, per arm

| Metric | Definition |
|---|---|
| `mrr` | reciprocal rank of the first chunk in `acceptable_source_chunk_ids` |
| `binary_ndcg_at_k` | binary-gain nDCG@K over `acceptable_source_chunk_ids` |
| `required_fact_coverage_at_k` | fraction of `required_fact_ids` discharged by the final `K` |
| `required_evidence_unit_coverage_at_k` | fraction of `required_evidence_unit_ids` present in the final `K` |
| `all_required_retrieved_at_k` | 1 iff `required_evidence_unit_coverage_at_k == 1.0` |
| `complete_chain_represented` | 1 iff every hop of `expected_relationship_chain` has ≥ 1 supporting chunk in the final `K`; reported **also** over the pre-`K` candidate set as `complete_chain_representable` |
| `forbidden_fact_hit_count_at_k` | final-`K` chunks discharging a `forbidden_fact_id`, split by `authority_ineligible` vs `eligible_but_wrong` |
| `ineligible_hit_count_at_k` | final-`K` chunks from authority-ineligible revisions — **must be 0 for every arm** |
| `eligible_hit_precision_at_k` | precision over eligible hits |
| `distinct_evidence_unit_count_at_k` | distinct chunks in the final `K` (multiplicity matters) |

Fact-level and unit-level coverage are **reported separately and never averaged
together**, because `U ≤ R` by construction here.

### 12.2 Structural process metrics — per question, per tier, per structured arm

| Metric | What it answers |
|---|---|
| `seed_page_count`, `seed_facet_count`, `seed_node_count`, `seed_kind_mix` | how Stage A started |
| `hop0_candidate_count` | how much of the candidate set never required navigation |
| `hop0_final_k_admission_count` | how much of final `K` came from hop 0 — **if this equals `K`, no navigation happened, whatever the score says** |
| `pages_reached_per_hop`, `facets_reached_per_hop`, `nodes_visited_per_hop` | reach by depth |
| `links_exposed`, `links_traversed`, `distinct_unseen_destinations` | navigation opportunity vs use |
| `effective_novel_branching_factor` | `distinct_unseen_destinations / links_traversed` — whether fan-out is real or repetitive |
| `eligible_chunks_per_reached_facet` | the size of the set `c_max` is bounding |
| `structural_lane_candidate_count`, `structural_lane_selected_count` | the reservation lane's supply and use |
| `page_saturation` | max chunks contributed by one page ÷ `K` |
| `facet_saturation` | max chunks contributed by one facet ÷ `K` |
| `facet_size_independence` | correlation between facet size and final-`K` slots won (§9.5) |
| `final_k_admission_source_mix` | counts by `selection_reason` |
| `required_fact_contribution_by_admission_source` | which lane actually delivered the answer |
| `candidate_recall_before_final_k` | `required_evidence_unit` recall over the pre-`K` candidate set — **the reachability metric H3 is stated on** |
| `unattributable_evidence_count` | `G-N4J` only (§10.5) |

The two most important rows are `candidate_recall_before_final_k` and
`final_k_admission_source_mix`: together they say whether a structured arm failed
because it could not *reach* the evidence or because it could not *rank* it —
different failures with different fixes, and §21 of the briefing exists because
they are routinely conflated.

### 12.3 Reporting rules

Per question, per class, per tier, per arm — never pooled across tiers, never
pooled across classes, never combined into an index. Deltas are reported as
**question counts first, rates second** (52 questions is small; a rate to three
decimals implies a precision it does not have). Every mandatory metric must be
present for every applicable `(question, tier, arm)` triple; a missing or
unlabelled metric **aborts the stage** rather than producing a partial scorecard.
---

## 13. The Agent experiment (`11B`)

Runs **only** after every static substrate and every tool contract is frozen
(§15, F6). The agent contract is frozen **before any Stage 11 measured result is
observed, static included** — otherwise the tool surfaces could be shaped by
static outcomes, and the comparison would be unfalsifiable.

### 13.1 Held identical across every agent arm

Agent model and version; system instructions (byte-identical,
`shared_prompt_sha256` asserted equal); question text; `as_of_date` and
`query_intent`; the authority rules and the resolver; token budget; wall-clock
budget; maximum tool calls; **information-return budget in characters**; final
evidence `K`; the output schema; the evaluator; and the pairing/interleaving of
runs.

| Budget | Value | On breach |
|---|---|---|
| tool calls | 40 | forced submit with whatever the agent holds |
| returned-evidence characters | 240,000 | forced submit |
| cumulative input tokens, one run | 400,000 | forced submit, `budget_exhausted_reason = "tokens"` |
| wall clock | 480 s | forced submit |
| final cited evidence | `K = U + 2` | over-citation is truncated in citation order and flagged |

The information-return budget matters as much as the call budget: an arm that
returns more source text per call has more evidence for the same 40 calls, and
that is a payload advantage, not a navigation advantage.

### 13.2 Symmetric tool surfaces

**Shared by every arm — identical implementations, identical response shapes:**

| Tool | Signature | Returns | Cap |
|---|---|---|---|
| `open_chunk` | `(chunk_id)` | verbatim `source_text` + full provenance + resolver authority label | ≤ 2,000 chars |
| `list_revision_chunks` | `(document_revision_id, page)` | ordered `(chunk_id, heading_path, first 120 chars)` | 20 rows/page |
| `list_documents` | `()` | eligible `(logical_document_id, title)` | once |
| `submit` | `(answer JSON)` | terminates the run | — |

**Per-arm surfaces:**

| Arm | Tools |
|---|---|
| `Agent-V` | `search_chunks(query, k ≤ 10, identifier_filter=None, document_filter=None)` |
| `Agent-V+` | `search_chunks(...)` over the union chunk + `facet_d0` payload index |
| `Agent-G-SG` | `search_graph_seeds(query, k ≤ 10)` · `list_neighbors(node, predicate=None, page, rank_by ∈ {relevance, structural}, query=None)` · `follow_edge(relation_id)` → its evidence chunks |
| `Agent-W-D0` / `Agent-W1-R` | `search_facets(query, k ≤ 10)` · `open_page(page_key)` · `list_related_pages(page_key, link_type=None, page, rank_by, query=None)` · `open_facet(facet_id)` · `search_within_facet(query, facet_id)` |
| `Agent-G-N4J` (diagnostic) | the vendor retriever exposed through the **same** signatures as `Agent-G-SG`; no extra capability |

**`Text2Cypher` and any arbitrary-query capability are excluded from every primary
arm.** Unrestricted database power for one treatment and not the others is the
clearest possible way to make the comparison meaningless. If the owner wants a
Text2Cypher reading, it is a separately labelled diagnostic in which *every* arm
gets an equivalent arbitrary-query surface over its own store, or none does.

### 13.3 Why `search_within_facet` is not an unfair extra

`Agent-V` has `document_filter`; `Agent-G-SG` has `rank_by="relevance"`;
`Agent-W` has `search_within_facet`. All three are the same capability —
*semantic ranking over a restricted candidate set*. Only the way the restriction
is **chosen** differs, and that choice is the treatment. Without this parity, a
Wiki win could be "the Wiki arm could search inside a scope and the Vector arm
could not", which is a tooling artifact.

### 13.4 Expressive-fairness matrix (audited before `11B` runs)

| Capability | `Agent-V` | `Agent-G-SG` | `Agent-W-*` | Verdict |
|---|---|---|---|---|
| semantic search, unlimited reformulation | `search_chunks` | `search_graph_seeds` | `search_facets` | matched |
| exact identifier match | `identifier_filter` | identity seed lane | `L1` page identity | matched on purpose |
| scoped semantic ranking | `document_filter` | `rank_by="relevance"` | `search_within_facet` | matched (§13.3) |
| structural browsing of a revision | `list_revision_chunks` | same | same | matched |
| verbatim source access | `open_chunk` | same | same | matched |
| corpus orientation | `list_documents` | same | same | matched |
| typed directed traversal | — | `list_neighbors` + `follow_edge` | `list_related_pages` | **the treatment** |
| entity/page-level membership view | — | — | `open_page` / `open_facet` | **the treatment** |
| tool count | 5 | 7 | 8 | residual recorded in §17 |
| per-call and total return caps | equal | equal | equal | matched |

No arm receives benchmark truth, required/forbidden facts, expected chains,
`elaboration_reason` tags, `required_hop_count`, or distractor labels — enforced
by the AST test extended over every tool-server module.

### 13.5 The prompt must give `Agent-V` a real chance

The shared prompt explicitly instructs iterative research: reformulate using
identifiers and entity names discovered in retrieved text, search again, verify
each hop against opened source, and cite a verbatim span per hop. **The null
hypothesis of this entire experiment is that iterative semantic search
reconstructs navigation**, and a prompt that under-prompts `Agent-V` would
manufacture the result. `reformulation_count` and `discovered_identifier_reuse_rate`
are reported per arm as evidence that `Agent-V` actually did this.

### 13.6 Output contract and mechanical validation (no LLM judge in any primary metric)

```
{ "answer": str,
  "citations": [ {"chunk_id": str, "quoted_span": str, "supports": str} ],
  "lineage":   [ {"subject": str, "predicate": str, "object": str,
                  "evidence_chunk_id": str, "quoted_span": str} ],
  "abstained": bool, "abstention_reason": str|null }
```

Validated mechanically: every `quoted_span` must occur verbatim in the cited
chunk's `source_text`; every cited chunk must be authority-eligible; `lineage`
hops are matched against `expected_relationship_chain` by normalized
`(subject, predicate, object)` with **direction significant**; the answer is
matched against `answer_surface_variants`. Abstention is a separately reported
outcome class, never silently scored as a miss.

### 13.7 Agent process metrics

| Metric | Notes |
|---|---|
| `tool_call_count`, per-tool breakdown | |
| `search_count`, `query_reformulation_count` | a reformulation is a search whose text differs from every previous search in that run |
| `local_subquery_count` | `search_within_facet` / scoped searches |
| `chunks_opened`, `pages_opened`, `facets_opened`, `graph_nodes_visited` | |
| `navigation_depth_max`, `navigation_depth_mean` | |
| `dead_end_count` | a navigation call returning no new destination |
| `backtrack_count`, `repeat_visit_count` | |
| `distinct_evidence_units_inspected` | **evidence SEEN** |
| `final_citation_count`, `distinct_cited_evidence_units` | **evidence CITED** |
| `seen_not_cited_count`, `cited_not_opened_count` | the two are tracked separately and never merged; `cited_not_opened_count > 0` is a citation-integrity failure |
| `source_backed_lineage_correctness` | fraction of expected hops with a valid, direction-correct, verbatim-supported lineage entry |
| `task_completed` | answer matches a surface variant **and** citation validity holds |
| `input_tokens`, `output_tokens`, `wall_clock_s`, `budget_exhausted_reason` | |
| `estimated_cost_usd` | from a live per-model price table; `None` where a price is unknown |

Efficiency ratios are reported as ratios, never folded into quality:
`required_facts_per_tool_call`, `distinct_evidence_units_per_1k_returned_chars`.

### 13.8 Run counts

| Block | Runs |
|---|---|
| primary: 4 core agent arms × 12-question agent subset × `S1`, `S2` | 96 |
| `S0` anchor: `Agent-V`, `Agent-W-D0` × 12 | 24 |
| repeat core: 6 questions × 4 arms × `S2` × 2 additional repeats | 48 |
| `Agent-V+` payload control × 12 × `S1`, `S2` | 24 |
| **primary campaign total** | **192** |
| conditional follow-ups (second model, doubled budget, `Agent-G-N4J`, blind replication) | ≤ 68 |
| **campaign hard stop** | **260 runs** |

Tier order `S1 → S0 → S2`, with a cost checkpoint between each: `S1` alone yields
a readable primary result, `S0` makes the richness interaction readable, `S2`
tests the strongest claim last. Because every contract is frozen before the first
run, run order cannot bias any arm. Runs are **paired and interleaved** by
question so provider-side drift cannot align with an arm.

---

## 14. Decision gates and their fixed evaluation order

**Hard preconditions** (all, for every arm, before any gate is read): zero
`ineligible_hit_count_at_k` everywhere; every frozen hash verified (corpus, chunk
index, embedding inputs, vectors, SRS, projections, contracts); no re-embedding in
a measured stage; citation validity computed for every asserted citation; no
evaluation truth reachable from any build, retrieval, tool or agent path (AST
test); practice set absent from every scorecard; `shared_prompt_sha256` equal
across agent arms; identical budgets recorded per arm; metric completeness (§12.3).

| Order | Gate | Question | Effect of failure |
|---|---|---|---|
| 1 | **P0** substrate parity | is Neo4j-exact ≡ Postgres-exact on the same vectors? | every Neo4j-hosted arm demoted to `DIAGNOSTIC` |
| 2 | **P1** ANN fidelity | is Neo4j ANN faithful to exact? | the operational-ANN claim is withdrawn; primary numbers unaffected |
| 3 | **X** vendor extraction | how good and how repeatable is the vendor graph? | no pass/fail; supplies H6's decomposition denominators |
| 4 | **Q2** `W1-R` qualification | is the enrichment layer sound and stable? | all `W1-R` numbers `NON-QUALIFYING / DIAGNOSTIC` |
| 5 | **S** static record | per-arm, per-class, per-tier, metric by metric | **no winner required**; record-only |
| 6 | **N** unit preservation | did the caps hold? | a structured arm breaching `facet_saturation` or `facet_size_independence` has its result reported as *cap-breached* |
| 7 | **A** agent effect | is there an agent advantage at equal budgets? | H5 unsupported |
| 8 | **A-attrib** attribution | is it navigation, or payload / exact-match / ordering? | the advantage is reattributed, not discarded |
| 9 | **R** robustness | does it survive repeats and the covariate checks? | the claim is reported as unreplicated |

Gate S requires no arm to win. Gate A's bar, frozen before any run, stated in
question counts first: on the 12-question agent subset, at `S1` **or** `S2`, a
structured agent arm must improve on **≥ 3 of 12** questions, regress on **≤ 1**,
hold a net advantage of **≥ +2** questions on `source_backed_lineage_correctness`,
degrade neither citation validity nor authority correctness, and hold direction in
the majority of repeats on the repeat core. *Improvement* is strictly better on
the highest-priority differing element of the ordered tuple (`task_completed`,
`lineage_complete`, `source_backed_lineage_correctness`,
`required_evidence_unit_coverage_at_k`). Every regression counts; the word
"material" is not used.

---

## 15. Freeze and hash manifest

Nothing below may change after its freeze point. Every item is content-hashed,
the hash is committed, and the hash is verified at the start of every measured
run; a mismatch **aborts the run**.

| Freeze | Contents | Frozen at | Consequence of breach |
|---|---|---|---|
| **F1** — derivation contract | identifier families, table-header vocabulary, cue list, predicate vocabulary, entity normalization rules, Wiki identity lanes and prevalence ceilings, channel-share band | **before the corpus is authored** | a rule tuned to the answer key; result void |
| **F2** — corpus | source bytes + per-file SHA-256, `generation_manifest.json`, chunker version + `chunking_config_hash`, `canonical_evidence_index_v1` covering hash | before embedding | any post-hoc corpus edit voids the stage |
| **F3** — benchmark truth | facts, questions, query text, intents, `as_of_date`, required/forbidden facts, expected chains, answer variants, `U`, `K`, the tier-invariant slice hash | before embedding | **no question or truth change after any arm result is seen, ever** |
| **F4** — embeddings | `model_id`, dimensionality, task roles, query/document templates, normalization policy, per-representation input rules, input manifest, vector manifest | before any arm runs | re-embedding in a measured stage is a hard failure |
| **F5-P** — projections | SRS, `G-SG` graph, `W-D0` wiki, `W1-R` enrichment artifact, Neo4j import artifacts + rebuild hash, `G-N4J` extraction config and its output graph | before any arm runs | a projection rebuilt mid-campaign is a different experiment |
| **F5-S** — static configuration | every arm's retrieval config; `P_seed`, `M_max`, `c_max`, `p_max`, `e_max`, `r_nav`, `C_max`, `F_max`, `s`, `decay`, RRF `k0`, Wiki-native selector weights; tie-break; `K`; Gate P0/P1/X/Q2/S/N definitions and thresholds | before any arm runs | per-question tuning; result void |
| **F6** — agent contract | tool names, signatures, caps, ordering semantics; prompt bytes; every budget; output schema; validation rules; Gates A / A-attrib / R with their margins and order | **before *any* Stage-11 measured result is observed, static included** | the agent contract could be shaped by static outcomes; result void |
| **F7** — evaluation code | the scorer, its import identity, the metric definitions | before any arm runs | metrics changed after seeing results |

**Reproducibility requirement.** Every result must be reproducible from the frozen
artifacts alone: given F1–F7 and the committed vectors, a clean checkout must
reproduce every static number byte-for-byte (agent numbers reproduce distributionally,
with transcripts committed). A `reproduce.py` that rebuilds every store from the
manifests and re-runs every static arm is a release artifact.

---

## 16. Implementation sequencing

No stage begins before owner approval of this document. Each has its own freeze
boundary and committed artifacts.

| Stage | Scope | Key artifacts | Freeze on exit |
|---|---|---|---|
| **11.0** | this design | `docs/STAGE11_KNOWLEDGE_INTERFACE_BENCHMARK_PLAN.md` | — (owner review) |
| **11A.0** | F1 contracts: derivation rules, identity lanes, backbone, predicate vocabulary, task taxonomy, question schema | `contracts/stage11_derivation_v1.json`, `stage11_backbone_v1.json`, `stage11_questions_schema_v1.json` | **F1** |
| **11A.1** | corpus authoring + generation `S0`/`S1`/`S2`; Canonical parse; chunking with the frozen config; §7.6 screens | `fixtures/stage11/<tier>/`, `generation_manifest.json`, `reports/stage11_corpus_profile.json`, screen reports | **F2, F3** |
| **11A.2** | SRS derivation; table records; evidence index | `canonical_relation_candidates_v1.json` + hashes, SRS coverage report | part of **F5-P** |
| **11A.3** | embedding adapter, templates, guards, batch/retry, §6.5 stability + integrity checks, fake provider, all representations | input + vector manifests, probe report | **F4** |
| **11A.4** | Neo4j deployment; `G-SG` and `W-D0` projections; import + rebuild-hash test; **Gate P0**, then **Gate P1** | projection reports, parity report, ANN-recall report | **F5-P** (partial) |
| **11A.5** | `W1-R` enrichment compile + **Gate Q2** (incl. adjudication) | enrichment artifact + hash, `reports/stage11_gateq2_scorecard.md` | **F5-P** (complete) |
| **11A.6** | `G-N4J` build + **Gate X**; sub-experiment **P** (parser comparison) | vendor graph + config hash, `reports/stage11_gatex_extraction.md`, `reports/stage11p_parser_comparison.md` | — |
| **11A.7** | **the complete agent contract is written and frozen here**, before any measured result | `contracts/stage11_agent_contract_v1.json` + `contract_sha256` | **F5-S, F6, F7** |
| **11A.8** | static measured run: every core arm + §9.6 factorial × 3 tiers. **The first measured number in Stage 11** | `reports/stage11a_static_results.json`, scorecard, §12.2 diagnostics | — |
| **11B.0** | agent harness implementing the already-frozen F6 contract: tool servers, budget meters, validators, pairing/interleaving, audit tests, dry run **on the practice set only** | harness tests, contract-conformance test against `contract_sha256`, fairness-matrix audit | — |
| **11B.1** | primary agent campaign — 192 runs, `S1 → S0 → S2`, paired and interleaved | `reports/stage11b_agent_results.json`, per-run transcripts with tool-call ledgers | — |
| **11B.2** | conditional follow-ups, each run iff its trigger fired | per-follow-up report naming the trigger | — |
| **11B.3** | analysis: gates in declared order, attribution, confound audit, decision record | `docs/STAGE11_KNOWLEDGE_INTERFACE_DECISION.md`, findings page | decision frozen |

**Proposed repository changes (not made yet).** New packages
`src/ingestion_bench/source_relations/` (SRS derivation),
`src/ingestion_bench/gemini_embeddings/` (adapter, templates, manifests, fake),
`src/ingestion_bench/neo4j_substrate/` (schema, import, rebuild, parity),
`src/ingestion_bench/stage11_graph/` (`G-SG`), `src/ingestion_bench/stage11_wiki/`
(`W-D0`, `W1-R`), `src/ingestion_bench/stage11_vendor/` (`G-N4J`, `G-N4J-canon`,
sub-experiment P), `src/ingestion_bench/stage11_benchmark/` (runner, evaluator,
agent harness, tool servers); `fixtures/stage11/`; `contracts/stage11_*.json`; new
Postgres tables prefixed **`edib_stage11_`** only; Neo4j databases `s11*` only.
Reused **read-only and unmodified**: the chunker and `ChunkingConfig`, the Stage 7R
registry/resolver, the Stage 7B.0 evaluator, the identifier regex, the
fixture-determinism pattern. Explicitly **not modified**: every Stage-7B and
Stage-7C module, contract, table and report. A hard test asserts nothing under
`src/ingestion_bench/stage11_*` imports `wiki_projection/compiler.py`.

---

## 17. Cost, runtime, and the places this proposal moves more than one variable

### 17.1 Where a single measured delta would mix two independent variables — read this first

The briefing asks for this list explicitly. These are the places where, as
written, one comparison would change two things at once. Each has a proposed
separator; each separator costs a scan or a small extra build, never a new corpus.

| # | The confound | Why it happens | Separator (already in the plan) |
|---|---|---|---|
| **1** | **`W1-R` = enriched artifacts **and** revised retrieval** | §8/§10 of the briefing define `W1-R` as both at once, so `W1-R − W-D0` is uninterpretable | `W-D0-rev` (new policy, old artifacts) and `W1-R-det` (new artifacts, old policy) are **core**, §9.1 |
| **2** | **`G-N4J` = new parser + new chunker + new extractor + new graph shape + new retriever** | the vendor pipeline replaces the whole stack | `G-N4J-canon` holds parsing and chunking constant, §10.5; sub-experiment P measures the parser difference independently, §4.2 |
| **3** | **Neo4j as substrate ∧ ANN as search** | moving arms to Neo4j while switching exact→approximate would mix storage with retrieval math | primary benchmark is **exact everywhere**; Gate P0 proves substrate parity; ANN is a separate preregistered Gate P1, §5.3 |
| **4** | **eligibility expansion ∧ within-navigation selector** | the briefing's §11 describes them together | the 2×2 factorial with reservation on/off, §9.6 |
| **5** | **facet embeddings ∧ page structure ∧ links** (the "does `W` just have richer payloads?" question) | `W`'s index entries carry more text per entry than `V`'s | `V+` embeds the **identical** facet payloads with no structure, §10.1; `Agent-V+` is the agent counterpart |
| **6** | **richness tier = `N` ∧ distractor density ∧ fan-out ∧ chain depth**, all rising together | a "richness ladder" is inherently multivariate | not fully separable; mitigated by holding the backbone, `U`, `K`, the question set and the required-unit partition byte-identical (§7.2), and by reporting the four richness covariates separately so a `S0→S2` trend can be regressed against each. **Declared as a residual confound, not solved** |
| **7** | **structured arms get a reserved lane ∧ a bounded local selector** | both are new machinery relative to `V` | reservation on/off is a factor in §9.6; `selection_reason` attribution in §12.2 says which lane actually delivered each required fact |
| **8** | **`G-SG` uses `deterministic` cue-rule relations on top of `source_explicit` ones** | the cue layer is an inference, not a source reading | `G-SG-explicit` runs on `source_explicit` only, §9.1 |
| **9** | **Agent tool count differs (5 / 7 / 8)** | structured arms need more verbs to express navigation | the §13.4 parity matrix maps every capability; the residual (`open_page`/`open_facet`) *is* the treatment and is named as such |
| **10** | **Vendor evidence is scored through a span-alignment map** | vendor chunks are not Canonical chunks | frozen ≥ 50 % overlap rule, `unattributable_evidence_count` published; the bias direction (can only lose the vendor credit, never invent it) is recorded, §10.5 |
| **11** | **Enrichment quality ∧ enrichment *presence*** | if Gate Q2 fails, a `W1-R` loss could be "enrichment does not help" or "this compiler is bad" | Gate Q2's per-dimension scorecard is published beside the retrieval result, and a Q2 failure forces the `NON-QUALIFYING / DIAGNOSTIC` label rather than a conclusion, §11.4 |

Items 1–5, 7, 8 and 10 are **solved by design**. Item 6 is **not solved** and is
declared. Items 9 and 11 are **bounded and labelled** rather than eliminated.

### 17.2 Other confounds and their handling

- **The corpus is authored by the party designing the structured arms** — the most
  material risk in the whole plan. Mitigations: F1 freezes every derivation rule
  and identity lane *before* a word of corpus exists; the structure-adversarial
  elaboration quota (§7.4); the channel-share band that caps how much of the truth
  is pre-linked (§7.3); the §7.6 screens; and, as a conditional follow-up, a
  **blind replication** in which a second party authors a `S1-B` corpus from the
  frozen backbone without seeing any arm. None of this eliminates the risk, and
  the finding must be reported with it stated.
- **Is `S2` rich, or simply adversarial to `V`?** Answered by the per-reason
  distractor audit and the proportionality rule (§7.4), published before any arm
  runs.
- **Does question wording leak page identity?** `identifier_mention_count` is a
  covariate; `T2` and `T6` carry no identifiers; a structured-arm advantage that
  lives only on identifier-bearing questions is reported as exact-match, not
  navigation.
- **Can `Agent-V` recreate navigation by iterative search?** That is the null
  (§13.5), and `reformulation_count` / `discovered_identifier_reuse_rate` are the
  evidence that it was given the chance.
- **Agent non-determinism** — repeats on the repeat core, paired and interleaved
  runs, transcripts committed, observed model version recorded per run.
- **Statistical power** — 12 agent questions and 52 static questions are small.
  Counts are reported first, rates second; no p-value is computed on 12 paired
  observations; a claimed advantage must hold in the majority of repeats.
- **Single domain, one generator, one embedding capability, one agent model** —
  stated as a scope limit in §20, not defended.
- **Table chunks embed poorly** — `table_as_standalone_chunk=True` is held for all
  arms, and per-`chunk_type` metric breakdowns are reported so the effect is
  visible rather than absorbed.

### 17.3 Cost and runtime

Following repository convention, **no fabricated dollar figure appears here**. The
runner computes cost from a live per-model price table and returns `None` where a
price is unknown. What can be stated are the quantities.

**Embedding volume (`gemini-embedding-2`, 1536-d, one pass):**

| Representation | `S0` | `S1` | `S2` | total tokens |
|---|---|---|---|---|
| `chunk` | ~40 k | ~320 k | ~1.22 M | ~1.58 M |
| `facet_d0` | ~85 k | ~425 k | ~1.45 M | ~1.96 M |
| `facet_r` | ~135 k | ~680 k | ~2.32 M | ~3.14 M |
| `edge` + `entity` | ~15 k | ~70 k | ~215 k | ~0.30 M |
| `vendor_chunk` | ~60 k | ~300 k | ~1.08 M | ~1.44 M |
| **total** | | | | **~8.4 M tokens, one pass** |

Embedding is a one-off and is not a constraint on this experiment.

**LLM volume (the real cost, and it is dominated by two builds):**

| Build | Calls | Note |
|---|---|---|
| `W1-R` enrichment compile | ~7,840 facet compiles (340 + 1,700 + 5,800) | one pass, `temperature = 0` |
| Gate Q2 repeatability | ~1,570 extra (10 % sample × 2 extra compiles) | |
| `G-N4J` extraction | ~4,800 chunk extractions | one pass |
| Gate X repeatability | ~960 extra | |
| **build total** | **~15,200 LLM calls** | |
| agent campaign | **192 primary runs**, ≤ 40 calls each, ≤ 400 k input tokens each | hard stop 260 runs |

**Worst-case primary agent input tokens:** 192 × 400 k = **76.8 M** before prompt
caching; realistically order **18–30 M** with caching and typical sub-40-call runs.

**Human cost, which is not optional:** Gate Q2 adjudication is ~260 items per tier
(780 total) and Gate X adjudication is 100 vendor-only relations per tier (300
total). At the observed rate of this project's earlier adjudications this is the
schedule's critical path, not the compute.

**The single largest controllable cost is the `S2` `W1-R` compile (5,800 facets).**
Owner decision O-7 (§19): compile `W1-R` at `S2` in full — recommended, because
`S2` is where H4 is most interesting and a missing tier makes the richness claim
unreadable — or restrict `W1-R` and Gate Q2 to `S0`/`S1` and report H4 without an
`S2` reading. `STAGE11_USD_CEILING` is owner-set, checked after every run and
after every build batch; the campaign aborts when the running total would exceed
it.

---

## 18. Falsification criteria, per hypothesis

Each is operational, stated before measurement, and readable from the committed
result files without re-analysis.

**H1 (Vector strongest at low hops) is falsified** if, at any tier, a structured
arm exceeds `V` on `required_evidence_unit_coverage_at_k` on the `T1`+`T2`+`T4`
strata by **≥ 2 questions net** with no regression — i.e. structure helps even
where it was not supposed to be needed. *Consequence:* the "structure pays off
only with depth" framing is wrong and must be rewritten, not softened.

**H2 (Graph gains with depth) is falsified** if any of:
(a) `G-SG − V` on `complete_chain_represented` is **non-increasing** across the
`T4 → T5 → T6` depth strata at both `S1` and `S2`; (b) the `G-SG` advantage does
not survive regression against the query→evidence semantic-distance covariate;
(c) `G-SG` loses to `V` on `T6` at every tier. *Consequence:* graph depth value is
not demonstrated on this corpus, which is a real result and must be reported as
one.

**H3 (deterministic Wiki reachability) is falsified** if `W-D0` does not exceed
`V` on `candidate_recall_before_final_k` at `S1` **and** `S2` by ≥ 2 questions
net, **or** if its advantage there does not convert into any advantage on
`complete_chain_represented` or `required_evidence_unit_coverage_at_k` at any tier
— reach that never converts is reported as reach that never converts, which is
itself the interesting finding about the four-stage decomposition (§9.4).

**H4 (enriched Wiki) is falsified** if any of:
(a) `W1-R ≤ W-D0` on both coverage metrics at every tier; (b) the `W1-R − W-D0`
delta is fully explained by `W-D0-rev` (it was the retrieval policy, not the
enrichment) or fully by `W1-R-det` (it was the artifacts, not the policy) — in
both cases H4-as-stated is false and the true, narrower claim is reported;
(c) `facet_saturation` or `facet_size_independence` breaches its cap (Gate N) —
the gain came from facet size, not enrichment; (d) Gate Q2 fails, in which case
H4 is **unevaluable**, not false, and is labelled so.

**H5 (Agent effect) is falsified** if the best structured-arm advantage under the
Agent is **not larger** than the same arm's static advantage on the same 12
questions at the same tier and the same `K`. The comparison is paired and
question-matched; a structured arm that wins statically and wins no more under the
Agent falsifies H5 even while winning.

**H6 (vendor comparison) is falsified as an attributable claim** if a
`G-N4J − G-SG` difference exists that **cannot** be decomposed — i.e. Gate X shows
comparable extraction recall *and* `G-N4J-canon` sits between them without
separating parsing from retrieval, *and* the vendor-only relation adjudication does
not account for the residue. The plan then reports "a difference exists whose
source we could not isolate", which is a weaker but honest outcome and must not be
upgraded in the write-up.

**H0 (the null) is confirmed** if no structured arm clears Gate A at any tier and
no structured arm exceeds `V` on either coverage metric at any tier. This is a
publishable result, it is what the earlier stages of this project already
suggested at smaller scale, and nothing in the harness asserts against it.

---

## 19. Owner decisions required before any work begins

| # | Decision | Recommendation |
|---|---|---|
| **O-1** | Stage numbering: Stage 11 with Stage 8A/8B subsumed, or Stage 8 first then Stage 11? | **Stage 11, Stage 8 subsumed** (§0) |
| **O-2** | Is adding Neo4j as a substrate approved, reversing "Postgres is sufficient — no Neo4j"? | approve; it is required by the briefing's vendor comparison and by `S2` fan-out (§5.1) |
| **O-3** | Is the vendor arm given the frozen backbone schema (parity with `G-SG`) or run schema-free? | **schema-guided**, for parity; a schema-free run is a conditional diagnostic (§10.4) |
| **O-4** | Are the §9.5 bounds accepted as frozen — `P_seed=5`, `M_max=3`, `c_max=2`, `p_max=3`, `r_nav=min(2,⌊K/3⌋)`, `C_max=200`, `F_max=20`? | accept; each is justified against `S2`'s measured fan-out and facet-size targets |
| **O-5** | Is `K = U + 2`, constant across tiers, on **evidence units** not facts, accepted? | accept (§7.5) |
| **O-6** | Gate Q2 thresholds (§11.2) — accepted as frozen? | accept, with the §11.4 disclosure that Q2-8 is the likely failure |
| **O-7** | `W1-R` at `S2`: full compile (~5,800 facets) or restrict `W1-R`/Gate Q2 to `S0`/`S1`? | **full compile**; otherwise H4 has no `S2` reading (§17.3) |
| **O-8** | `STAGE11_USD_CEILING` — the one number this plan cannot supply | owner-set |
| **O-9** | Agent model and version for `11B`; second-model confirmation as a conditional? | owner choice; conditional follow-up recommended |
| **O-10** | Sub-experiment P scope: `S0` only, or `S0` + a `S1` sample? | `S0` only unless P shows material divergence |
| **O-11** | Blind `S1-B` replication by a second author — commissioned now or only on a positive result? | on a positive result, as a conditional (§17.2) |
| **O-12** | Is the human adjudication load (~1,080 items) accepted as the schedule's critical path? | it must be accepted or Gates Q2 and X shrink, and the plan must say which |

**Closed by owner instruction, not re-opened here:** the embedding binding —
`gemini-embedding-2`, 1536-d, text-only, asymmetric query/document templates,
generated outside Neo4j through one shared adapter, frozen before corpus embedding
and authoritative thereafter (§6).

---

## 20. What this experiment will not establish, recorded before it runs

- Not that "Wiki works" or "Graph does not". Every result attaches to *this*
  projection, *this* navigation policy, *this* final-`K` rule, *this* corpus,
  *this* embedding capability and *this* agent model. §21 of the briefing is the
  standing instruction and it is repeated in the decision document's first
  paragraph.
- Not a production recommendation. Build cost, maintenance cost, freshness and
  operational risk are asymmetric across these arms and are only partially
  measured here.
- Not a general claim about Neo4j or about `neo4j-graphrag`. One configuration,
  one library version, one extraction model, one corpus.
- Not a claim about corpora larger than `S2`, other domains, other embedding
  models, other chunk sizes, or multimodal evidence.
- Not a ranking of ingestion lanes — that is Stages 10A/10B — and not an ROI
  comparison, which is Stage 9.
- Not a claim that the deterministic arms *could not* have been better with more
  derivation rules. The rules are frozen before the corpus exists precisely so
  they cannot be improved against it, and the price of that discipline is that
  the deterministic arms are not tuned.

---

## 21. Deliverables checklist for this design phase

| # | Briefing deliverable | Where |
|---|---|---|
| 1 | architecture diagram | §2 |
| 2 | Canonical schema | §3 |
| 3 | Neo4j projection schema | §5.2 |
| 4 | rich corpus specification `S0`/`S1`/`S2` | §7 |
| 5 | question taxonomy | §8 |
| 6 | complete arm matrix | §9.1–§9.2 |
| 7 | `W-D0` retrieval algorithm | §10.3 |
| 8 | `W1-R` retrieval algorithm | §10.6 |
| 9 | source-grounded Graph retrieval algorithm | §10.2 |
| 10 | Neo4j-native GraphRAG reference design | §10.4–§10.5 |
| 11 | `W1-R` qualification gate | §11 |
| 12 | static metric specification | §12 |
| 13 | Agent tool contracts | §13.2 |
| 14 | fairness constraints | §9.3, §13.1, §13.3–§13.4 |
| 15 | freeze/hash manifest | §15 |
| 16 | implementation sequencing | §16 |
| 17 | expected cost/runtime | §17.3 |
| 18 | risks/confounds | §17.1–§17.2 |
| 19 | falsification criteria per hypothesis | §18 |
| 20 | Neo4j provides vs remains custom | §5.4 |
| 21 | parser/reference sub-experiment | §4.2 |
| 22 | multi-variable change highlights | **§17.1** |

---

**STOP.** This is the end of the design phase. No corpus is generated, no code is
implemented, no arm is run, and no outcome is inspected until the §19 decisions
are settled and this plan is approved.
