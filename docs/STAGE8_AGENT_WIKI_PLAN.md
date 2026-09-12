# Stage 8 Plan (Revision 1 — PROPOSED, awaiting owner review) — Deterministic Source-Grounded Wiki as an *Agent* Knowledge Interface vs Authority-Aware Vector

> **Status: DESIGN ONLY. Nothing in this document has been implemented, and no
> measured retrieval, embedding build, corpus generation or Agent run has been
> performed.** This document is the deliverable of Stage 8.0. Work stops here
> for owner review (§12).
>
> **Stage 7C is frozen and untouched.** No Stage-7C artifact, contract, table,
> report or code path is modified, re-run, reinterpreted or repaired by this
> plan. Stage 7C's corpus is explicitly **not** the primary benchmark corpus for
> Stage 8 (§2). Where this plan reuses Stage-7C-era *code*, it reuses only
> read-only, already-frozen components (the chunker, the Stage 7R resolver, the
> Stage 7B.0 evaluator) and never the W1 compiler (§4).
>
> **Graph is outside the core experiment.** No LLM-extracted graph, no
> semantic-edge store, no traversal-as-evidence. §4.3 states precisely why the
> deterministic table-derived typed links this plan *does* propose are not the
> Stage 7B graph, and §10.18 records the reviewer challenge on that point
> honestly rather than hiding it.

---

## 0. Naming conflict that must be resolved before implementation

`docs/POC_STATUS_AND_EVIDENCE.md` already pencils in **Stage 8A/8B** for
"selective vision/vendor-native comparison (paths B/C)" and **Stage 9** for the
cross-lane quality/cost/latency/ROI comparison. The owner's briefing uses
**Stage 8A** for this experiment's first text-only measured run and **Stage 8C**
for a later multimodal extension. These cannot both be Stage 8.

**RESOLVED — owner-approved, landed as decision D-056.** This experiment takes
Stage 8 (`8.0` design, `8A` static, `8B` Agent, `8C` optional multimodal). The
previously pencilled vision/vendor-native ingestion comparison is renumbered
**Stage 10A/10B**. Stage 9 keeps its number and now depends on Stages 6A–10B.
Nothing else in the roadmap moves. The status table, the "Corrected roadmap"
block, the walkthrough stage sequence and the handoff-seed stage list are updated
to match; per the decision log's own append-only rule, any "Stage 8A"/"Stage 8B"
reference in an entry or report predating D-056 means what is now Stage 10A/10B.

*The resolution of this item does not imply approval of the rest of this plan:
§12's remaining eleven decisions are still open, and no Stage 8A/8B work may
begin until they are settled.*

---

## 1. The Stage 8 experimental contract

### 1.1 The business question

> **A deterministic, source-grounded Wiki may lose the static top-K retrieval
> contest and still be the better thing to hand an Agent.** Static top-K asks
> "what are the best K chunks for this query string?" — a question one vector
> search answers well. An Agent conducting source-backed multi-hop research asks
> a different question: "given what I just learned, where do I go next, and can I
> prove each hop?" Stage 8 asks whether a deterministic Wiki is a better
> *interface for that second question*, and whether the answer depends on corpus
> richness.

### 1.2 The hypothesis, stated so it can fail

**H8 (composite).** There exists a deterministic, source-grounded Wiki
representation `W`, built with no generated claims, summaries or claim-derived
links, such that:

- **H8-a (static, permissive).** At every richness tier, `W`'s static
  authority-aware top-K retrieval is **inferior or indistinguishable** from
  authority-aware Vector `V` on required-fact coverage@K. *(This is a premise,
  not a win condition. A static `W` win does not confirm H8; it weakens the
  framing and must be reported as such — §9, Gate S.)*
- **H8-b (agent — the actual claim).** At equal agent model, prompt, authority
  scope, tool-call budget, **information-return budget**, timeout and final
  evidence `K`, `Agent-W` achieves **higher source-backed relationship-lineage
  completion** and **higher required-fact completion** than `Agent-V`.
- **H8-c (richness interaction).** The `Agent-W − Agent-V` advantage is
  **non-decreasing** from `S0` → `S1` → `S2`.

**H8 is not supported** if any of the following holds (§9.6 makes each
operational):

1. `Agent-W` shows no advantage over `Agent-V` at equal budgets at any tier; or
2. the advantage vanishes against the **`V+` payload-repacking control** — i.e.
   the benefit was "more source text per index entry", not navigation; or
3. the advantage exists only when `Agent-W`'s information return exceeds
   `Agent-V`'s; or
4. the advantage exists only at `S0` and shrinks with richness (the opposite of
   the stated mechanism, and a signal that the corpus, not the representation,
   is producing it); or
5. the advantage rests on questions whose wording names a Wiki page identity, and
   disappears on the no-identifier (`T2`) and multi-hop (`T4`) strata.

### 1.3 The arms

| Arm | Kind | What it is | Role |
|---|---|---|---|
| **`V`** | static | authority-aware chunk-vector retrieval, one query, top-K | primary static baseline |
| **`V-lex`** | static | `V` plus a deterministic exact-identifier match channel | fairness control: isolates "Wiki = exact match" |
| **`V+`** | static | `V` plus an index of the **identical** facet payloads `W` embeds, with **no** page structure, links or traversal | fairness control: isolates "payload repacking" from "navigation" |
| **`W`** | static | deterministic source-grounded Wiki retrieval + navigation | the treatment |
| **`W-semrank`** | static, diagnostic | `W` with query-similarity neighbour ordering | declared diagnostic, never the headline |
| **`Agent-V`** | agent | iterative agent with vector search (+ identifier filter) + source open | agent baseline |
| **`Agent-W`** | agent | same agent with Wiki search / page open / neighbour navigation + source open | the agent treatment |
| **`Agent-V+`** | agent, ablation | `Agent-V` whose search also covers facet payloads | payload control, `S1` only |

`V-lex`, `V+` and `Agent-V+` are not decorations. The two most likely
explanations of an `Agent-W` win that have nothing to do with navigation are
(a) the Wiki simply gets exact identifier matching that `V` lacks, and (b) the
Wiki's index entries carry more source text per entry. Both are cheap to control
for — no new embeddings, no new corpus — and without them a positive result is
not interpretable (§10.4).

### 1.4 What is frozen, and when

| Freeze | Contents | Frozen at | Consequence of breach |
|---|---|---|---|
| **F1 — ingestion/anchor-lane contract** | identifier families, phrase-anchor rules, heading rules, table-record rules, cross-reference cue list | **before the corpus is authored** | a lane tuned to the answer key; result void |
| **F2 — corpus** | source bytes + per-file SHA-256 manifest, chunking config hash, covering index hash over every `(chunk_id, content_sha256)` | before embedding | any post-hoc corpus edit voids the stage |
| **F3 — benchmark truth** | facts, questions, query text, intents, `as_of_date`, required/forbidden facts, expected chains, answer surface variants, per-question `K` | before embedding | **no question or truth change after any arm result is seen, ever** |
| **F4 — vectors** | chunk vectors, facet vectors, embedding-input-hash and vector-hash manifests | before any arm runs | re-embedding in a measured stage is a hard failure |
| **F5 — arm configuration** | retrieval configs, agent prompt bytes, budgets, gate definitions and their evaluation order | before any arm runs | per-question tuning; result void |

One immutable global configuration. **No per-question tuning. No
evaluation-truth hints on any retrieval, navigation, Wiki-build or Agent path.**
Enforced the way Stage 7B/7C enforce it: an AST test proving that no module
outside the evaluator subscripts or attribute-reads `required_fact_ids`,
`forbidden_fact_ids`, `expected_relationship_chain`,
`expected_supporting_passage` or `answer_surface_variants`.

### 1.5 Scope exclusions (Stage 8A/8B)

Multimodal/image evidence (deferred to a separately proposed `8C`);
LLM-extracted graphs; generated claims, summaries or abstracts anywhere in the
Wiki; rerankers; fine-tuning; ANN indexes (§3.5); multi-format parity (DOCX only,
as in 7B.0); production deployment; UI; any Stage-7C artifact change.

---

## 2. S0 / S1 / S2 corpus blueprint

### 2.1 Why the Stage-7C corpus cannot be the primary corpus

Measured and recorded in the frozen Stage 7C plan §0.1: 6 logical documents, 11
revisions, **exactly one chunk per revision**, ~6 authority-eligible chunks under
a current-intent query, per-question `top_k` of 3–5. That gives `K/N ≈ 0.5`, and
for two questions `K` equals the number of required facts exactly. At those
proportions a top-K budget is a large fraction of the eligible corpus, branching
is near-minimal *because the corpus is small*, and both `V` and `W` sit near a
recall ceiling. It is the wrong instrument for a richness-interaction hypothesis.
It stays frozen, cited as prior art, and may optionally be re-scored as a
historical reference point **only** after Stage 8's own gates are evaluated.

### 2.2 Domain and namespace

New corpus family: **`ERL-S8-REGOPS`** — regulated-payments change-and-control
operations. Enterprise-plausible, naturally register-and-revision shaped, and
with **no identifier, phrase or entity reused from Stage 7C** (no `APP-224510`,
`O-31`, `C-88`, `C-88a`, `P-204`, `P-205`, `Payment Settlement`, `Payment
Reconciliation`). Identifier families, declared in F1 before authoring:

| Family | Regex | Entity type |
|---|---|---|
| `SYS-\d{4}` | system / application | `System` |
| `SVC-\d{3}` | business service | `Service` |
| `OBL-\d{3}` | regulatory obligation | `Obligation` |
| `CTL-\d{3}[A-Z]?` | control | `Control` |
| `PRD-\d{3}` | procedure | `Procedure` |
| `STD-\d{2}` | internal standard | `Standard` |
| `IFC-\d{3}` | interface / data flow | `Interface` |
| `DE-\d{4}` | data element | `DataElement` |
| `TPV-\d{3}` | third-party vendor | `Vendor` |
| `TST-\d{3}` | control test | `Test` |
| `RSK-\d{3}` | risk item | `Risk` |

The `CTL-\d{3}[A-Z]?` family deliberately reproduces the `C-88`/`C-88a` hazard
class in a new namespace (`CTL-114` vs `CTL-114A` vs `CTL-014`): a hard test
asserts no normalization merges them.

### 2.3 The semantic backbone — invariant across all three tiers

One declarative backbone spec (`contracts/stage8_backbone_v1.json`) holds typed
entities and typed relations. Primary spine plus deliberate side-spines:

```
System        --serves-->        Service
Service       --governed_by-->   Obligation
Obligation    --satisfied_by-->  Control
Control       --implemented_by-->Procedure
Procedure     --owned_by-->      Role
Control       --tested_by-->     Test
Service       --depends_on-->    Interface
Interface     --carries-->       DataElement
DataElement   --classified_by--> Standard
Interface     --provided_by-->   Vendor
Obligation    --mitigates-->     Risk
```

**Invariance rule (hard test).** `S0`, `S1` and `S2` share, byte-identically:
the backbone entity set, the typed relation set, every `fact_id` and its
`(subject, predicate, object)`, the authority applicability of each fact, every
`question_id`, every query string, every `required_fact_ids` /
`forbidden_fact_ids` / `expected_relationship_chain`, every accepted answer
surface variant, and every per-question `K`. Only the **binding** from a fact to
its `(logical_document_id, document_revision_id, chunk_id)` differs per tier.
The test hashes the tier-invariant slice of each tier's contract and asserts the
three hashes are equal.

**Required-evidence-unit invariance (authoring constraint, hard test).** The
*partition* of each question's required facts into supporting chunks must also be
tier-invariant: if two required facts share one chunk at `S0`, they share one
chunk at `S1` and `S2`, and if they are separate at `S0` they stay separate. This
keeps `U` — and therefore `K` (§2.4) — identical across tiers, which is what makes
the `K/N` ladder the only thing moving. Non-required facts are free to be packed
however the elaboration rules dictate.

**Elaboration rule.** Every chunk in `S1`/`S2` that is not an `S0` chunk must be
generated by a *declared elaboration rule* applied to the same backbone, and must
carry a machine-readable `elaboration_reason` from a closed vocabulary:

| `elaboration_reason` | What it adds | Whom it pressures |
|---|---|---|
| `backbone_restatement` | the same fact restated in another document, with a scope qualifier | both |
| `competing_entity` | another entity of the same type with its own (true, irrelevant) relations | both |
| `qualifier_variant` | a near-paraphrase of a backbone fact, wrong because of jurisdiction / product line / effective period / entity variant | `V` more |
| `superseded_variant` | the correct relation in an authority-ineligible revision | both |
| `adjacent_domain` | a parallel chain in a neighbouring domain | `V` more |
| `direction_inversion` | lexically similar text asserting the reverse relation | both |
| `anchor_fanout_inflation` | a backbone identifier mentioned in chunks irrelevant to it | **`W` more** |
| `title_collision` | near-identical register titles / phrase-anchor collisions | **`W` more** |
| `identifier_variant_noise` | `CTL-114` vs `CTL-114A` vs `CTL-014` in proximity | **`W` more** |
| `prose_only_backbone` | a backbone fact expressed so that no table row and no cue word can capture it | **`W` more** |

The last four exist because a richness ladder built only from semantic
near-duplicates is adversarial to `V` alone, which would manufacture the result
(§10.2). **Declared before authoring:** `S1` and `S2` must grow the
`W`-adversarial reasons at least proportionally to the `V`-adversarial ones, and
the audit table reporting counts per reason per tier is a release artifact.

**Adversarial-authoring quota (declared in F1, before authoring).**
`prose_only_backbone` must cover **≥ 30%** of backbone facts, and the fraction of
truth hops that have a qualifying deterministic Wiki link must land in the band
**0.55 – 0.75**. Above that band the corpus was written for the Wiki; below it
the Wiki has no structure to offer. Measured and reported **before** any arm
runs; out-of-band means re-author, not re-interpret.

### 2.4 Concrete tier targets

Targets, not post-hoc descriptions. Authoring iterates until each tier's
measured profile is inside its declared band; the profile is then frozen with the
corpus (F2) and published as `reports/stage8_corpus_profile.json`.

| Measurement | `S0` controlled | `S1` rich | `S2` stress |
|---|---|---|---|
| logical documents | 14 | 45 | 140 |
| document revisions | 22 | 85 | 260 |
| chunks (total) | 180 ± 15 | 900 ± 60 | 3,200 ± 200 |
| chunk length, median tokens | ~200 | ~320 | ~340 |
| chunk length, declared band | 140–260 (≤ 5% > 400) | 200–500 (≤ 5% > 550) | 200–500 (≤ 5% > 550) |
| facts per chunk, median | 3 (band 2–4) | 4 (band 3–6) | 4 (band 3–6) |
| authority-eligible chunks per question (`N`) | 100–125 | 430–520 | 1,450–1,750 |
| final evidence `K` | `U + 2` (3–7) | `U + 2` (3–7) | `U + 2` (3–7) |
| `K/N` | 0.024 – 0.070 | 0.006 – 0.016 | 0.002 – 0.005 |
| authored distractors per question (all reasons) | 8–15 | 40–70 | 150–260 |
| authored `qualifier_variant` + `direction_inversion` per multi-hop question | ≥ 2 | ≥ 5 | ≥ 9 |
| Wiki page identities | ~70 | ~260 | ~800 |
| Wiki facets (page × revision) | ~300 | ~1,500 | ~5,200 |
| average fan-out (qualifying links per facet) | 4 | 9 | 18 |
| maximum fan-out | 12 | 40 | 120 |
| truth-path depth (hops) | 1–4 | 1–5 | 2–6 |
| competing plausible paths per multi-hop question | 1–2 | 3–6 | 6–12 |
| intermediate hops with **no** lexical/semantic bridge from the query text | ≥ 1 on ≥ 20% of multi-hop questions | ≥ 1 on ≥ 30% | ≥ 1 on ≥ 40% |

**`K` is held constant across tiers on purpose.** `K = U + 2`, where **`U` is the
question's count of distinct required *evidence units*** — the distinct canonical
chunks carrying its required facts — and **not** its required-*fact* count `R`.
The two diverge here by design: Stage 8 chunks carry 2–6 facts each (§2.4), so
one chunk can discharge several required facts and `U ≤ R`. `K` budgets *chunks*,
so `K` must be defined on chunks; defining it on `R` would hand every arm
`R − U` slots of invisible slack and blunt exactly the precision pressure the
`K/N` ladder is built to apply. `U` is frozen per question in F3, and §8.2 keeps
the unit-level and fact-level metrics separately reported for the same reason.
Same question, same `K`, at all three tiers, so
the tier ladder moves `N`, distractor pressure and fan-out — and *only* those.
This is what makes the tiers comparable at all (§10.3), and it is why `K/N` falls
by an order of magnitude per tier without any budget change.

**Definitions used by the profile report.**

- `N` — chunks belonging to revisions that the Stage 7R resolver declares
  eligible for that question's `(query_intent, as_of_date)`, summed over every
  logical document in scope. Measured by the resolver, never hand-counted.
- `authored_distractor_count` — design-time, from `elaboration_reason` tags: the
  controlled quantity.
- `embedding_distractor_density@τ` — measured *after* the embedding build and
  *before* any arm runs: the count of eligible non-required chunks with cosine
  ≥ `τ = 0.75` to the query vector. A descriptor, never a tuning target;
  reported per question per tier.
- `competing plausible path` — a path in the deterministic link graph from the
  question's seedable anchor to any terminal entity of the answer's type that is
  not the truth path. Deterministically enumerable, so it is counted, not
  estimated.
- `fan-out` — qualifying links per facet in the authority-scoped view under the
  question's own scope.

### 2.5 Generation method

Deterministic authoring, no LLM in the loop, following the frozen Stage-7B.0
fixture pattern: a declarative spec plus templated DOCX emission, fixed document
timestamps **and** normalized ZIP entry timestamps so bytes and therefore
`source_document_sha256` are byte-reproducible; generated files tracked in git;
a `generation_manifest.json` recording each file's expected SHA-256, re-verified
on load with a loud failure on divergence.

Document archetypes (each authored as realistic multi-paragraph sections so the
**frozen chunker, unmodified**, at `ChunkingConfig(max_chars=1200,
cross_unit_boundaries=False, table_as_standalone_chunk=True)` produces the target
chunk-length distribution): register documents with real tables
(`Control ID | Title | Owner | Satisfies | Status`), standards and policy prose,
procedure documents, meeting-minute style approval records, interface
specifications, vendor attestations, and change-request records.

**Chunk sizes are controlled by authored section length, never by changing the
chunker.** The chunking config hash is part of F2 and identical for all tiers and
all arms.

### 2.6 Pre-freeze corpus validity screens (all before F2/F3 freeze)

Each screen either passes or the corpus is re-authored. None involves an arm
comparison; all are corpus properties.

1. **Single-chunk sufficiency audit.** For every multi-hop question, prove
   mechanically that no single chunk, no single revision and no single logical
   document contains all required facts.
2. **Answer-co-occurrence audit.** The answer entity's surface forms must not
   co-occur with the question's distinctive surface terms in any single eligible
   chunk, for every multi-hop question.
3. **Lexical-triviality screen.** A declared exact-term-overlap top-`K` baseline
   (no embeddings, no arm) is run; any question it fully solves is demoted out of
   the multi-hop class or re-authored. This screen is *not* an arm and its numbers
   are published as a corpus property.
4. **Identifier-leak audit.** No question text may contain a Wiki-internal
   artifact string (`page_key`, `facet_id`, `section_id`, `anchor_id`,
   `link_id`, `chunk_id`, `document_revision_id`). Corpus-native enterprise
   identifiers are permitted only in the classes that declare them, and every
   question records `identifier_mention_count` as an analysis covariate.
5. **Deterministic-link coverage band.** §2.3's 0.55–0.75 band.
6. **Distractor-mix audit.** Counts per `elaboration_reason` per tier, with the
   `W`-adversarial proportionality check.
7. **Authority-scope audit.** Every question's eligible set is produced by the
   frozen resolver and recorded; every `forbidden_fact_id` is classified as
   authority-ineligible or eligible-but-wrong, because the two are scored
   differently (7B.0 semantics).
8. **`K/N` and fan-out audit.** Measured against §2.4's bands.

---

## 3. Benchmark and task taxonomy

### 3.1 Task classes

48 questions per tier: **8 classes × 6 questions**, identical text at all three
tiers.

`R` = required facts; `U` = distinct required evidence units (chunks), `U ≤ R`;
`K = U + 2` (§2.4). Both `R` and `U` are frozen per question in F3.

| Class | Name | Requirement | `R` | `U` | Depth |
|---|---|---|---|---|---|
| `T1` | identifier-explicit lookup | names ≥ 1 corpus identifier; single fact | 1 | 1 | 1 |
| `T2` | semantically phrased, no identifier | **names no identifier at all**; descriptive phrasing only | 1–2 | 1–2 | 1–2 |
| `T3` | one-hop relationship | one typed relation, named endpoint | 1 | 1 | 1 |
| `T4` | multi-hop distributed | 3–6 hops, evidence in ≥ 3 documents, ≥ 1 hop with no lexical bridge | 3–6 | 3–5 | 3–6 |
| `T5` | temporal / authority | correct answer depends on `as_of_date` / intent; a superseded or draft variant exists | 1–3 | 1–3 | 1–3 |
| `T6` | distractor resistance | ≥ 2 near-paraphrase competitors wrong by qualifier; one is lexically closer to the query than the truth | 1–2 | 1–2 | 1–2 |
| `T7` | consolidation | enumerate **all** currently-authoritative facts of one type for one subject (≥ 3, spread over ≥ 3 documents) | 3–5 | 3–5 | 1–2 |
| `T8` | relationship lineage | produce the chain *and* cite a validating source span per hop | 3–6 | 3–5 | 3–6 |

`T4`/`T8` deliberately include at least one question per tier where two required
facts share a chunk (`U < R`), so the unit-versus-fact metric split in §8.2 is
actually exercised rather than merely declared.

`T4` and `T8` overlap in shape and differ in what is scored: `T4` scores whether
the evidence was found, `T8` scores whether the **lineage was asserted and
mechanically validated hop by hop** (§7.3). Keeping them separate is how this
design distinguishes disconnected evidence coverage from a coherent chain of
evidence (§10.9).

### 3.2 Question record schema

`contracts/stage8_benchmark_v1.json` (per tier, sharing the invariant slice):

```
question_id, task_class, query, query_intent, as_of_date,
requested_revision_symbols[], required_fact_ids[], forbidden_fact_ids[],
expected_relationship_chain[ {from, relation, to, fact_id} ],
required_hop_count,
required_fact_count R, required_evidence_unit_count U, K (= U + 2),
required_evidence_units[ { chunk_id, fact_ids[] } ],
answer_key { entities[], answer_surface_variants[] },
agent_subset: bool, agent_repeat_core: bool,
identifier_mention_count, leak_audit: { names_wiki_internal: false },
stratum_tags[]
```

### 3.3 Subsets and run counts

| Population | Size | Used for |
|---|---|---|
| full static set | 48 / tier | every static arm, every tier |
| agent subset | 24 / tier (3 per class) | `Agent-V`, `Agent-W`, every tier |
| agent repeat core | 12 / tier | 3 repeats per arm, for variance |

Static evaluations: 48 × 3 tiers × 4 arms = **576** (+144 for the `W-semrank`
diagnostic). Agent runs: 24 × 3 × 2 = 144 primary, + 12 × 3 × 2 × 2 extra
repeats = 144, + `Agent-V+` at `S1` (24), + a second-model confirmation at `S1`
on the repeat core (24) = **336 agent runs**. Cost model in §8.6.

### 3.4 Practice set (harness debugging only)

A separate 8-question practice set over the same corpus, **declared and frozen
with F3 but excluded from every reported metric**, exists so that tool-contract
and harness debugging never touches a benchmark question. A hard test asserts
that no practice `question_id` appears in any scorecard.

### 3.5 One retrieval mechanic for every arm

Cosine distance (`<=>`) over unit-norm vectors; **exact scan, no ANN index**, at
every tier for every arm. At `S2`'s ~3,200 chunks and ~5,200 facets an exact scan
is trivially affordable, and an ANN index would introduce arm-dependent recall
that no amount of scoring discipline could disentangle. If an index is ever
introduced it must be identical in type and parameters across arms, and every
affected number must be re-reported.

Authority filtering is a **store predicate inside the ranking statement**
(`document_revision_id IN (:eligible)` in the same statement as
`ORDER BY embedding <=> :q LIMIT :k`) for chunk search, facet search **and**
neighbour ranking. Retrieve-then-post-filter is a hard failure — the finding is
already frozen in the consolidated learnings and applies unchanged to facet
search and traversal.

---

## 4. `gemini-embedding-2` binding proposal

### 4.1 Model facts this binding relies on

| Property | Value | Source |
|---|---|---|
| model id | `gemini-embedding-2` (public preview, Gemini API / Vertex) | Google docs |
| default dimensionality | 3,072, MRL-truncatable 128–3,072 via `output_dimensionality` | Google docs |
| recommended dimensionalities | 3,072 / 1,536 / 768 | Google docs |
| normalization | 3,072 always normalized; **truncated dimensionalities auto-renormalized** | Google docs |
| max input tokens | 8,192 (shared across modalities) | Google docs |
| `task_type` parameter | **not supported** — task instructions go in the input string | Google docs |
| asymmetric retrieval formats | query `task: {task} \| query: {content}`; document `title: {title} \| text: {content}` | Google docs |
| price (text) | $0.20 / 1M tokens; Batch API $0.10 / 1M | Google pricing |

The absence of a `task_type` parameter is the single most consequential fact for
this binding: the task instruction is **part of the hashed embedding input**, so
it must be frozen as a template and recorded in the manifests (§4.6).

### 4.2 Output dimensionality — proposed **1,536**, frozen

Justification, in priority order:

1. **Index-option parity.** pgvector's `vector` type supports HNSW up to 2,000
   dimensions; 3,072 would force `halfvec` (float16) to remain indexable. Even
   though Stage 8 uses exact scan (§3.5), committing to a dimensionality that
   cannot be indexed without changing numeric precision imports a
   precision-versus-fairness decision into a later stage. 1,536 avoids it.
2. **Recommended tier.** 1,536 is one of the three recommended sizes, so no
   off-menu truncation behaviour is being relied on.
3. **Auto-renormalization.** Truncated dimensionalities are auto-renormalized,
   so cosine remains direction-only with no manual renormalization step that
   could diverge between arms.
4. **Cost and footprint.** Half the storage and scan cost of 3,072 at
   near-parity retrieval quality; at `S2` this is the difference between a
   comfortable and an awkward exact scan.

`3,072` is declared as an **optional sensitivity run at `S1` only**, executed
*after* the primary measured run, reported separately, and never as the headline.

### 4.3 Exact input formats — frozen templates

Four templates only. Every embedded string in Stage 8 is produced by one of
them, and `payload_template_version = "stage8_v1"` is recorded on every row.

**(a) Query (all arms, static and agent, including every agent reformulation):**

```
task: search result | query: {query_text}
```

One declared task label — `search result` — for the whole experiment. Per-class
or per-question task labels would be per-question tuning and are banned by F5.
`Agent-V`, `Agent-W`, `V`, `V-lex`, `V+` and `W` all embed queries through this
one template, so no arm can gain from prompt-side asymmetry.

**(b) Chunk evidence payload (shared by `V`, `V-lex`, `V+` and `W`'s evidence
layer — literally the same stored rows):**

```
title: {logical_document_id} > {" > ".join(heading_path)} | text: {chunk.source_text}
```

`source_text` only. `model_derived_text` is **never** embedded by any arm
(Stage 8A is text-only DOCX, so no OCR or vision annotation exists; the
exclusion is asserted by test regardless).

**(c) Facet discovery payload (`W`, and — identically — `V+`):**

```
title: {page_display_title} [{page_entity_type}] {doc_title} > {heading_path} | text: {occurrence_spans}
```

`occurrence_spans` is built by a frozen deterministic rule: for each member chunk
of the facet, in `(chunk_index, chunk_id)` order, take the **verbatim
sentence-level span(s) containing each anchor occurrence** (sentence boundaries
from the frozen chunker's boundary regex), join with `" "`, and pack to a frozen
**1,500-token** budget using the frozen boundary-packing algorithm. Overflow is
dropped, never truncated mid-span, and the row records
`payload_truncated = true` with `dropped_span_count`.

**(d) Page display title source.** `page_display_title` is verbatim source text
(a register row's Title cell, or the anchor's display form) — never composed
prose.

**The no-new-text proof (hard test).** Strip the closed-vocabulary template
scaffolding from any facet payload, and every remaining span must be a verbatim
substring of some member chunk's `source_text`, or of the anchor's normalized /
display surface form, or of a closed structural vocabulary (document titles,
heading paths, entity-type labels, revision labels). Any residue fails the build.
This is the mechanical guarantee that **the Wiki receives no information `V`
lacks — only a different organization of the same bytes** (§10.4).

### 4.4 Normalization assumptions

Vectors arrive unit-norm at 1,536 dimensions by the model's auto-renormalization.
The build **verifies** `‖v‖ ∈ [1 − 1e−3, 1 + 1e−3]` per vector and fails loudly
on violation; it never silently renormalizes. Cosine is the single distance for
every arm. Because vectors are unit-norm, cosine and dot product coincide — the
contract names cosine and the SQL uses `<=>`, everywhere, with no arm-specific
variation.

### 4.5 Batch, retry and input-guard rules

- **Batch size:** ≤ 32 inputs per request (conservative). The implementation
  stage must read the live per-request and rate limits and record the *actual*
  effective limits in the run manifest rather than assuming this number.
- **Input guard:** every payload is token-counted before the call; > 8,192 tokens
  is a **build-time error**, never a silent truncation. Silent truncation would
  drop evidence and make the evidence universe arm-dependent. §4.3(c)'s 1,500-token
  facet budget and the chunker's 1,200-char packing keep every payload far inside
  the limit by construction; the guard exists to catch a contract violation, not
  a routine case.
- **Retry:** on 429 / 5xx only, deterministic exponential backoff (base 2s, ×2,
  max 5 attempts, **zero jitter** for reproducibility). A permanent failure
  aborts the whole build — no partial index is ever written, because a partial
  index makes the evidence universe silently arm- and order-dependent.
- **Batch API:** permitted for the corpus build (50% price) provided the same
  templates, model id and dimensionality are used; the endpoint actually used is
  recorded per row. Query-time embedding (agent reformulations) uses the
  synchronous endpoint.
- **Query-embedding cache:** a content-addressed cache keyed by
  `embedding_input_sha256`, **shared by both arms**, so an identical query string
  always yields an identical vector within and across runs. This removes an
  entire class of hosted-model-drift noise from the agent repeats.

### 4.6 Authoritative-by-storage policy

- **Text authority** lives in the frozen source bytes (F2). **Vector authority**
  lives in the store (F4). A vector is never regenerated to "match" text; a
  mismatch is a failure, not a repair trigger.
- Every stored row carries: `row_key`, `embedding_input_sha256` (SHA-256 of the
  exact string sent), `vector_sha256` (SHA-256 over the little-endian float32
  byte concatenation), `model_identity = "gemini-embedding-2"`,
  `output_dimensionality = 1536`, `payload_template_version`, `task_label`,
  `api_endpoint`, `response_model_version` (as returned), `built_at`.
- **Every measured stage verifies before it runs:** recompute each payload from
  frozen source, compare `embedding_input_sha256`; recompute `vector_sha256` from
  the stored vector; compare covering index hashes. Any divergence aborts the
  stage. **No measured stage may embed anything except an agent's own live query
  strings** — asserted by a test that the measured runners import no corpus
  embedding entry point.
- Manifests: `reports/stage8_embedding_input_manifest.json` (per-row input hashes
  + a covering hash over all `(row_key, embedding_input_sha256)`) and
  `reports/stage8_vector_manifest.json` (per-row vector hashes + covering hash +
  model/dimension/endpoint metadata + per-tier counts).

### 4.7 Determinism disclosure and the shared-row rule

A hosted embedding model is not guaranteed bit-identical across calls, and
`gemini-embedding-2` is in public preview. Therefore:

- the vectors are a **frozen labelled snapshot**, exactly as Stage 7B.1 treated
  its extracted graph;
- a pre-freeze **stability probe** embeds a fixed 50-payload sample three times
  and reports maximum cosine drift and maximum `vector_sha256` disagreement. This
  is a **disclosure**, not a gate: the number is published and the snapshot is
  frozen either way;
- **shared-row rule (hard test):** `V`, `V-lex`, `V+`, `W`, `Agent-V` and
  `Agent-W` read chunk vectors from the *same table rows*, proven by row-identity
  assertion, so no embedding difference can ever explain an arm delta. `W` and
  `V+` likewise share the facet-vector rows.
- a deterministic 1,536-dimension **fake provider** (the existing
  `FakeEmbeddingProvider` pattern) keeps the default test suite offline and
  key-free.

### 4.8 Estimated embedding cost

| Tier | chunk tokens | facet tokens | total | @ $0.20/1M | @ batch $0.10/1M |
|---|---|---|---|---|---|
| `S0` | ~36k | ~90k | ~0.13M | ~$0.03 | ~$0.01 |
| `S1` | ~288k | ~600k | ~0.89M | ~$0.18 | ~$0.09 |
| `S2` | ~1.09M | ~2.34M | ~3.43M | ~$0.69 | ~$0.34 |
| all | | | ~4.45M | **~$0.90** | **~$0.44** |

Embedding cost is not a constraint on this experiment. The agent runs are
(§8.6).

---

## 5. Deterministic source-grounded Wiki architecture (`W`)

### 5.1 Constraints restated as build rules

No Stage-7C W1 compiler. No generated claims, no generated summaries, no
claim-derived links, no LLM call anywhere in the build (the embedding call is ML
inference over source text, identical for `V`). Page identity, membership,
anchors and qualifying links come from deterministic or source-grounded
information only. Pages, links and embeddings are **discovery/navigation
artifacts**; all final factual evidence resolves to canonical source chunks.

### 5.2 Identity lanes (frozen in F1, before the corpus is authored)

`L1`–`L3` carry over from Stage 7C's deterministic projection, which measured
well and needs no redesign. `L4` and `L5` are the justified strengthening over a
straight D0 reproduction.

| Lane | Source of truth | Yields |
|---|---|---|
| **`L1` identifier anchors** | `IdentifierAnnotation(derivation="extracted")` + the neutral identifier regex per declared family; uppercase normalization | page identity per enterprise identifier; `CTL-114`/`CTL-114A`/`CTL-014` never merged (hard test) |
| **`L2` repeated-phrase anchors** | maximal 2–4 token capitalized runs from `source_text` and `heading_path`; closed stop-list; normalized key must occur in ≥ 2 distinct chunks **and** ≥ 2 distinct logical documents; identifier collisions lose; two display forms on one key are flagged `is_ambiguous` and never silently merged | page identity for named services, standards, domain phrases |
| **`L3` heading-title anchors** | `heading_path` leaves | structural page identity and section scoping |
| **`L4` source-native register records** *(new)* | `CanonicalTableCell` structure already in the canonical model (`row`, `col`, `is_header`, `row_span`, `col_span`), on the standalone table chunks the frozen chunker emits | **directed, typed links whose direction and relation name come from the document's own table**: row-subject identifier → column-header predicate → cell-object identifier; plus verbatim page display titles and typed attributes |
| **`L5` source-native cross-reference cues** *(new)* | a closed cue list frozen in F1 *before authoring* (`supersedes`, `superseded by`, `as defined in`, `in accordance with`, `refer to`, `see`, `implemented through`, `governed by`, `owned by`), matched to an identifier within a bounded token window | directed typed links from prose |

**`L4` is the strongest legitimate deterministic structure available**, and it is
why this design does not simply reproduce D0. An enterprise register table
*already encodes* subject, predicate and object: the row's identifier is the
subject, the column header is the predicate, an identifier in the cell is the
object. Reading that requires no inference, no model and no benchmark truth — only
the table geometry the canonical model has carried since Stage 4.2. Every `L4`
link's relation name is a **verbatim column header**, so the relation vocabulary
is the corpus's, not ours.

**`L5`'s honest risk, and its containment.** A cue list is a hand-authored
artifact and could be tuned toward the answer key. Containment: the list is frozen
in F1 **before** any corpus text exists; a hard test asserts it contains no
corpus-specific token (no identifier, no entity name, no corpus phrase); and §9
requires a **lane ablation** (`W` minus `L4`, `W` minus `L5`) so that the decision
record states which deterministic lane actually carried any result. If `L5`
carries the win, that is a weaker, more corpus-specific finding, and the record
must say so.

### 5.3 Objects

- **`SourceSection`** — a 1:1 view over a `CanonicalChunk`;
  `section_id = sha256(document_revision_id | chunk_id)`; verbatim `source_text`,
  `heading_path`, `source_refs`, `content_sha256`; `model_derived_text` kept in a
  separate labelled field and **never merged**.
- **`PageIdentity`** — `(anchor_kind, normalized_value)` →
  `page_key = sha256(...)`, plus `entity_type` from the declared identifier family
  (or `phrase`/`heading`), plus a verbatim `display_title`.
- **`Facet`** — `(page_identity × document_revision_id)`. The compilation and
  embedding unit. **Membership is a property of the text**: a facet exists iff its
  page identity has ≥ 1 anchor posting in that revision. No `current` flag
  anywhere; authority is resolved at query time only.
- **`AnchorPosting`** — occurrence evidence (`anchor_id`, `chunk_id`,
  `document_revision_id`, `char_span`, `source_ref`, `posting_hash`). **Never a
  relationship assertion.**
- **`WikiLink`** — `link_type ∈ {structural, exact_anchor, typed_record,
  typed_cue}`; `is_directed` true only for `typed_record` / `typed_cue`;
  `relation_label` verbatim (column header or cue phrase) or `null`;
  `is_authoritative_lineage = False` **always**; and a mandatory
  `link_evidence = (chunk_id, char_span, source_ref)`. **A link without source
  evidence cannot exist** (hard test: zero evidence-free links).

### 5.4 What is embedded, and what deliberately is not

Embedded: **chunk payloads** (§4.3b, rows shared with `V`) and **facet payloads**
(§4.3c, rows shared with `V+`).

**Not embedded: any cross-revision page-level vector.** A page spans revisions
with different authority states, so a page vector would either bake authority into
the index (banned — the frozen finding is that authority is query-time only) or
require re-embedding when an authority activation happens (banned by F4, and
Stage 7C proved an authority change must alter only the eligible *view*: no
re-parse, re-chunk, re-embed or hash change). Discovery therefore happens at facet
granularity and pages are assembled at query time from eligible facets.

### 5.5 Query-time flow (static `W`)

1. Resolve authority per logical document via the frozen
   `resolve_query_scope(...)`; union the eligible revision ids.
2. Embed the query once, through template §4.3(a).
3. **Facet seeding:** rank facets by cosine with `document_revision_id IN
   (:eligible)` inside the ranking statement; take the top `P_seed = 3` facets.
4. **Bounded expansion:** from each seed facet, traverse qualifying links in the
   authority-scoped view, breadth-first, to depth `M_max = 3`, with
   `neighbour_page_size = 20` per expansion and a declared candidate ceiling as a
   function of `P_seed` and `M_max`. Ineligible revisions are filtered **before**
   neighbour ranking.
5. **Deterministic neighbour order** (default `W`): `typed_record` links first
   (by verbatim relation label, lexical), then `typed_cue`, then `exact_anchor`
   (identifier before phrase), then `structural`; within a class by
   (distinct-document count desc, `chunk_index` asc, `chunk_id` asc). **No
   semantic reranking in the default arm** — semantic neighbour ranking would
   import `V`'s capability into `W` and make attribution impossible. It exists as
   the declared `W-semrank` diagnostic instead.
6. **Evidence resolution:** map every reached facet to its member chunks, dedupe
   preserving traversal order, truncate to the question's `K`, and emit **chunk
   provenance only**: `logical_document_id`, `document_revision_id`, `chunk_id`,
   `content_sha256`, `source_document_sha256`, source path, `source_refs`, plus
   the resolver's authority label.
7. Score with the frozen Stage 7B.0 evaluator, by import identity.

**Hard test:** the object handed to the scorer contains no `page_key`,
`facet_id`, `section_id`, `anchor_id` or `link_id` — only chunk provenance. The
Wiki is a route to evidence, never evidence.

### 5.6 Fan-out at `S2`, stated before it is measured

At `S2`, maximum fan-out is targeted at 120. A deterministic navigator with
`neighbour_page_size = 20` therefore cannot see a hub's whole neighbourhood in one
step, and an agent must page or filter. **This is the designed stress, not an
accident**: it is exactly the branching-ambiguity failure mode Stage 7C's frozen
plan recorded that its corpus could not exercise. If `W` or `Agent-W` degrades at
`S2` because of fan-out, that is a finding about the representation, and the
report must say so rather than raising the page size after the fact (F5).

### 5.7 Stated limitations of `W`, recorded before it runs

`L2` is bounded by capitalization convention. `L4` requires register-shaped
tables — the `prose_only_backbone` quota (§2.3) guarantees ≥ 30% of backbone facts
are outside its reach, by design. `L5` depends on conventional cue wording. Table
chunks embed with the frozen chunker's structural rendering (`row=`, `col=`,
`header=` tokens), which is noise for a text embedder — **equally for `V` and `W`**,
since they share those rows. Anchor fan-out is unbounded in principle; only the
paging rule bounds it. An external governed anchor vocabulary (CMDB/catalog) would
be a legitimate further lane and is documented, not implemented.

---

## 6. Static experiment (`8A`)

### 6.1 Held identical across `V`, `V-lex`, `V+`, `W`

Corpus bytes and chunk set (covering index hash verified); chunking config hash;
embedding model, dimensionality, templates and **rows**; the Stage 7R resolver,
per-question `query_intent` and `as_of_date`; query strings; per-question final
evidence `K`; the frozen Stage 7B.0 evaluator by import identity; and the source
evidence universe (all arms may only ever return canonical chunks from the same
frozen set).

### 6.2 Arm definitions, stated precisely

- **`V`** — one query embedding, authority-predicated ranking of chunk vectors,
  top-`K`.
- **`V-lex`** — `V`, plus: identifiers present in the query text (by the declared
  regex families) contribute an exact-match candidate set, fused with the vector
  ranking by a declared, fixed rule (identifier-exact candidates first in
  document-then-chunk order, then vector ranking, deduped, truncated to `K`). No
  tuning, no weights to pick.
- **`V+`** — `V`, plus the facet payload rows as *additional index entries*;
  a facet hit resolves to its member chunks. **No links, no traversal, no page
  structure, no neighbour listing.** This is "the Wiki's text repacking without
  the Wiki".
- **`W`** — §5.5.
- **`W-semrank`** — `W` with neighbour ordering by query cosine. Diagnostic.

### 6.3 Reported per tier

The full mandatory metric set of **§8.2**, per question and per task class, for
every static arm, plus distinct-document diversity, returned-hit count, and the
arm deltas `W − V`, `W − V+`, `W − V-lex`, `V+ − V`, `V-lex − V` computed
metric-by-metric (never on a composite).

Absolute numbers are **never compared across tiers** without the `K/N` covariate.
The comparable quantity within a tier is the arm difference; the comparable
quantity across tiers is the **trend in that difference** (§10.3).

---

## 7. Agent experiment (`8B`)

### 7.1 Frozen identically across `Agent-V` and `Agent-W`

| Item | Value |
|---|---|
| agent model | `claude-sonnet-5`, `temperature = 0` (primary) |
| confirmation model | `claude-opus-5`, `S1` repeat core only (§7.6) |
| system + task prompt | byte-identical except the tool block; `shared_prompt_sha256` recorded and asserted equal |
| authority scope | the question's `(query_intent, as_of_date)`, resolved by the frozen resolver; the agent cannot widen it |
| question text | identical to the static arms' query |
| max tool calls | **40** per question |
| information-return budget | **240,000 characters** of tool-returned content per question (metered deterministically at 4 chars/token nominal; model-reported token usage recorded separately) |
| wall-clock timeout | 480 s per question |
| tool-error retry policy | ≤ 3 retries per call, deterministic backoff, errors counted |
| final evidence `K` | the question's `K` — identical to the static arms |
| evaluator | the same frozen scorer plus the §7.3 lineage validator |
| output contract | strict JSON schema (§7.2) |

Budgets are **constant across tiers**, so the tier ladder measures corpus
difficulty rather than budget. One declared budget-sensitivity arm doubles the
call and return budgets at `S2` only and is reported separately.

### 7.2 Output contract

```
{
  "answer": string,
  "abstain": bool,
  "citations":   [ { "chunk_id": str, "quoted_span": str } ],
  "chain":       [ { "from": str, "relation": str, "to": str,
                     "chunk_id": str, "quoted_span": str } ],
  "unresolved":  [ string ]
}
```

At most `K` citations (a longer list is truncated to `K` in declared order and the
overflow recorded). Abstention is permitted and scored as its own outcome —
never silently as a failure — because an agent that declines rather than
fabricates is a different and better failure mode.

### 7.3 Mechanical validation (no LLM judge in any primary metric)

- **Citation validity** — `quoted_span` must be a verbatim substring of that
  `chunk_id`'s frozen `source_text`. Invalid citations are counted and excluded
  from coverage credit.
- **Authority correctness** — every cited `document_revision_id` must be in the
  question's eligible union. A violation is a hard-safety failure for that run.
- **Lineage validation** — a truth hop `(from, relation, to)` counts as
  **source-backed** iff the agent asserted a chain element with matching
  normalized endpoints **and matching direction**, whose `chunk_id` is the hop's
  supporting chunk, and whose `quoted_span` validates verbatim. `relation` is
  matched against a frozen accepted-label set per hop (declared in F3 — the
  corpus's own verbatim relation vocabulary), never by semantic similarity.
  `lineage_fraction` = validated hops / truth hops; `lineage_complete` = all hops.
  **Direction matters**: Stage 7C measured a compiler asserting a relation and its
  exact reverse from the same quote, both mechanically accepted. Stage 8 does not
  repeat that mistake.
- **Task completion** — the answer must contain an accepted surface variant of
  every answer-key entity (normalized exact match against the F3-frozen variant
  list), with authority correctness holding and no forbidden fact asserted.

No post-hoc variant additions. If a human later judges an unmatched answer
correct, the frozen score stands and the corrected re-score is published as a
labelled secondary analysis.

### 7.4 Tool contracts

**Shared by both arms (identical implementations, identical response shapes):**

| Tool | Signature | Returns | Caps |
|---|---|---|---|
| `open_source` | `(chunk_id)` | verbatim `source_text` + full provenance + authority label | ≤ 2,000 chars per call |
| `list_revision_chunks` | `(document_revision_id, page)` | ordered `(chunk_id, heading_path, first 120 chars)` | 20 rows/page |
| `list_documents` | `()` | eligible `(logical_document_id, title)` | full list, once |
| `submit` | `(answer JSON)` | terminates the run | — |

**`Agent-V` only:**

| Tool | Signature | Returns | Caps |
|---|---|---|---|
| `vector_search` | `(query, k ≤ 10, identifier_filter=None)` | ranked `(chunk_id, heading_path, 400-char preview, score)` | 10 results |

**`Agent-W` only:**

| Tool | Signature | Returns | Caps |
|---|---|---|---|
| `wiki_search` | `(query, k ≤ 10)` | ranked `(page_key, display_title, entity_type, 400-char preview, score)` | 10 results |
| `open_page` | `(page_key)` | eligible facets: `(document_revision_id, heading_path, member chunk_ids, anchor spans)`, plus link-type counts | ≤ 2,000 chars |
| `list_neighbours` | `(page_key, link_type=None, page)` | `(relation_label, direction, neighbour page_key, display_title, evidence chunk_id)` | 20 rows/page |

**Expressive-fairness mapping (audited before `8B` runs).** Every capability
granted to one arm has a declared counterpart in the other, or is recorded as the
treatment:

| Capability | `Agent-V` | `Agent-W` | Verdict |
|---|---|---|---|
| semantic search with unlimited reformulation | `vector_search` | `wiki_search` | matched |
| exact identifier match | `identifier_filter` | `L1` page identity | **matched on purpose** — without this, `W`'s win could be mere exact match |
| structural browsing of a revision | `list_revision_chunks` | `list_revision_chunks` | matched |
| verbatim source access | `open_source` | `open_source` | matched |
| corpus-level orientation | `list_documents` | `list_documents` | matched |
| typed, directed neighbour traversal | — | `list_neighbours` | **the treatment** |
| page-level membership view | — | `open_page` | **the treatment** |
| tool count | 5 | 6 | 6 vs 5; the residual is `open_page`, recorded in §10.5 |
| per-call return cap | equal | equal | matched |
| total return budget | 240k chars | 240k chars | matched |

Neither arm receives benchmark truth, answer-specific metadata, required/forbidden
fact information, expected chains, `elaboration_reason` tags, or distractor
labels — enforced by the §1.4 AST test extended over every tool-server module.
Neither arm is told how many hops the answer needs (`required_hop_count` is
evaluation truth).

### 7.5 The prompt must give `Agent-V` a real chance

The shared prompt explicitly instructs iterative research: reformulate queries
using identifiers and entity names discovered in retrieved text, search again,
verify each hop against opened source, and cite a verbatim span per hop. This
text is identical for both arms. The null hypothesis of this whole experiment is
that **iterative semantic search reconstructs navigation**, and a prompt that
under-prompts `Agent-V` would manufacture the result. `reformulation_count` and
`discovered-identifier reuse rate` are reported per arm as evidence that
`Agent-V` actually did this (§10.6).

### 7.6 Repeats and model sensitivity

Three repeats per `(arm, question)` on the 12-question repeat core, one elsewhere.
A claimed advantage must hold in the **majority of repeats** with consistent
per-question direction. A `claude-opus-5` confirmation runs both arms on the `S1`
repeat core: agent capability is itself a confound — too weak an agent shows no
difference, too strong an agent may close `V`'s gap by sheer reformulation skill —
so the direction of the effect must be shown to survive a model change or be
reported as model-specific.

---

## 8. Metrics and evaluator

### 8.1 The four distinct levels (never averaged together)

| Level | Question it answers | Metric |
|---|---|---|
| **1. Evidence coverage** | did the required facts end up in the final `K`, and in what ranked position? | `required_fact_coverage@K`, `required_evidence_unit_coverage@K`, `all_required_retrieved@K` (set-level, order-free, **no connectivity implied**) and the ranking pair `mrr`, `ndcg@K` (binary gain, unit-level) |
| **2. Chain discovery** | were all truth-chain chunks *seen* during research, and *represented* in final `K`? | `chain_discovered` (over the explored set), `chain_represented` (over final `K`) |
| **3. Source-backed lineage** | did the agent *assert* each hop with correct direction and a validating verbatim span? | `lineage_fraction`, `lineage_complete` (§7.3) |
| **4. Task completion** | is the final answer right, authority-correct and distractor-free? | `task_completed`, `abstained`, `forbidden_fact_asserted` |

The gap between levels is the point. A run with `required_fact_coverage@K = 1.0` and
`lineage_complete = false` has **disconnected evidence**: it held every needed
chunk and could not join them. A dedicated counter,
`disconnected_coverage_count` (coverage = 1 ∧ lineage < 1), is reported per arm
per tier, and the joint `(coverage, lineage)` distribution is published as a 2-D
table rather than two marginals. This is the direct answer to "can the metrics
distinguish disconnected coverage from a coherent chain of evidence?" (§10.9).

**No composite score exists anywhere in Stage 8.** No level is averaged into
another, no arm is ranked by a blended index, and no gate reads a composite.
Every gate in §9 names the individual metrics it reads. Retrieval ranking, fact
coverage, chain completeness, contamination and authority correctness are
reported — and decided on — separately.

### 8.2 Mandatory retrieval-quality metrics (required measured outputs)

**Binding.** The following are **required** outputs of every measured Stage 8 run,
reported **per question**, **per corpus tier** (`S0`, `S1`, `S2`), and **per
qualifying arm** wherever semantically applicable. They are reported
**independently — never collapsed into a composite score, index, or weighted
average** — so that ranking quality, fact coverage, chain completeness,
contamination and authority correctness each remain separately readable and
separately falsifiable. Aggregates (per task class, per tier) are permitted only
as per-metric aggregates of these same quantities.

| Metric | Definition as measured | Applies to |
|---|---|---|
| `mrr` | reciprocal rank of the **first relevant authoritative evidence item** in the arm's ranked final evidence list; aggregated across questions as Mean Reciprocal Rank | every ranked arm; agent arms over the submitted citation order (§8.2.3) |
| `required_fact_coverage@K` | **fraction of the question's frozen required *facts*** represented in the final authoritative evidence set — fact-level, not chunk-level (§8.2.1) | all arms |
| `all_required_retrieved@K` | boolean: every required fact is represented | all arms |
| `complete_chain_represented` | boolean: the **full required multi-hop relationship chain** is represented by the final evidence, not merely a set of disconnected relevant facts | all arms |
| `ndcg@K` | **binary relevance gain**: a relevant authoritative evidence unit scores gain 1, an irrelevant one gain 0; the normal rank discount applies; ideal DCG over `min(U, K)` unit gains of 1 | every ranked arm; agent arms as above |
| `forbidden_fact_hits@K` | **count** and **boolean presence** of frozen forbidden facts in the final evidence, reported split by authority-ineligible versus eligible-but-wrong (the two mean different things — 7B.0 semantics) | all arms |
| `authority_leakage_count` | authority-aware hits belonging to an ineligible revision. **Must remain zero**; non-zero is a hard-safety failure (§9), not a score | all arms |

Graded relevance is **not** introduced anywhere. If graded relevance is ever
wanted it must be predeclared as a separate, separately-named metric in a
revision of this contract, and it may not replace the binary form.

#### 8.2.1 Units versus facts — the divergence, stated before it bites

`ndcg@K` and `mrr` rank **evidence units** (canonical chunks).
`required_fact_coverage@K` measures **semantic fact coverage**. Stage 8 chunks
carry 2–6 facts by design, so the two populations genuinely differ: *a chunk
containing three required facts is one relevant evidence unit for binary nDCG, yet
contributes all three facts to required-fact coverage once the frozen evaluator
verifies them.*

This matters concretely, because **the frozen Stage 7B.0 evaluator computes its
coverage over the set of distinct required supporting *chunks*, not facts**
(`required_chunk_ids = {evidence[f].supporting_chunk_id for f in
required_fact_ids}`). On the Stage 7C corpus that was a distinction without a
difference — one chunk per revision, one required fact per chunk — so the frozen
function's number was simultaneously a unit count and a fact count. On the Stage 8
corpus it is not. Reusing that number under the name
`required_fact_coverage@K` would silently report unit coverage under a fact label:
exactly the metric-name/threshold divergence the consolidated learnings record as
having already caused one false gate breach.

Therefore, and as hard requirements:

- `required_evidence_unit_coverage@K` — the frozen evaluator's own quantity,
  reported under a name that states its population, and used for the `ndcg@K`
  ideal-DCG denominator;
- `required_fact_coverage@K` — computed fact-by-fact in the Stage 8 sibling
  evaluator over `required_evidence_units[{chunk_id, fact_ids[]}]`: a required
  fact counts as represented iff its supporting chunk is in the final evidence set
  **and** that fact's frozen `expected_supporting_passage` verifies verbatim
  against that chunk's frozen `source_text` (verified once at F2/F3 and re-checked
  at run time);
- both are reported side by side for every question, and any question where they
  differ is flagged `unit_fact_divergent: true` in the scorecard;
- `all_required_retrieved@K` is evaluated on the **fact-level** population;
- every gate threshold is computed **in the same function that compares it to its
  threshold**, and every metric name states its population — the two cheap guards
  the consolidated learnings prescribe.

#### 8.2.2 Chain completeness is not coverage

`complete_chain_represented` requires the final evidence to represent **every hop**
of `expected_relationship_chain`, in the sense the frozen evaluator already
implements (all chain-supporting chunks present). It is reported independently of
`required_fact_coverage@K` and is never inferred from it: a question can reach
`required_fact_coverage@K = 1.0` with `complete_chain_represented = false` when the
required-fact set and the chain differ, and that combination is precisely the
"disconnected evidence" signal §8.1 exists to expose. For agent arms, chain
completeness is reported at all three of: *discovered* (seen while researching),
*represented* (in the final `K`), and *source-backed lineage* (asserted, correctly
directed, span-validated — §7.3). Those three are never merged.

#### 8.2.3 Applicability per arm ("wherever semantically applicable")

- **Static arms** (`V`, `V-lex`, `V+`, `W`, `W-semrank`): all seven metrics, over
  the arm's ranked top-`K` evidence list.
- **Agent arms** (`Agent-V`, `Agent-W`, `Agent-V+`): all seven metrics, over the
  **submitted citation list in the order submitted**, capped at `K`. `mrr` and
  `ndcg@K` are labelled `citation_order_mrr` / `citation_order_ndcg@K` in agent
  scorecards, because an agent's citation order is a deliberate authoring choice
  rather than a retrieval ranking; they are compared agent-arm-to-agent-arm and
  **not** quoted against static ranking numbers as if identical instruments.
- **Coverage, chain, forbidden-fact and authority metrics** carry the same meaning
  for static and agent arms and are directly comparable across them.
- Invalid citations (span does not verify) are excluded from relevance credit and
  counted separately; they never silently become gain-0 filler that inflates a
  rank discount.

#### 8.2.4 Implementation rule

The frozen Stage 7B.0 evaluator is imported by identity and unchanged; every
Stage 8 addition (fact-level coverage, class-stratified aggregates, `K/N`
covariate views, `T7` consolidation recall, the agent lineage validator) lives in
a **sibling** module that *calls* the frozen function. An import-identity test
proves the frozen scorer was reused rather than reimplemented, and a test asserts
that no reported field name is used for two different populations anywhere in the
scorecards.

### 8.3 Agent process metrics

`tool_calls_total` and per tool; `searches`; `reformulation_count`;
`distinct_pages_opened`; `distinct_chunks_opened`; `navigation_steps`;
`max_navigation_depth_reached`; `dead_ends` (a call returning zero
not-previously-seen evidence); `backtracking_events` (revisiting a node after ≥ 1
intervening distinct node); `recovery_rate` (dead-end runs that still reached
`lineage_complete`); `evidence_chars_returned` and its share of budget;
`prompt_tokens`, `completion_tokens`, `cached_tokens`; `wall_clock_seconds`;
`usd_cost`; `budget_exhausted_reason ∈ {submitted, calls, chars, timeout}`.

### 8.4 Efficiency ratios

`tool_calls_per_required_fact`, `evidence_chars_per_validated_hop`,
`required_facts_per_10k_returned_chars`, `usd_per_lineage_complete`. These are how
"`Agent-W` used its budget better" is stated quantitatively rather than
rhetorically, and they are also the check on the subtler unfairness: an arm that
spends the same budget but receives denser evidence per call (§10.7).

### 8.5 Statistical discipline

48 static questions and 24 agent questions per tier is small. **No significance
claim** will be made on a stratum with < 20 questions. Reporting is: per-question
tables, pre-declared absolute margins (§9), effect sizes, and repeat variance. A
difference inside the declared noise band is reported as **no difference**, not as
a trend.

### 8.6 Cost model

Embedding cost is ~$0.90 total (§4.8). Agent cost dominates: 336 runs × up to 40
calls, with returned evidence capped at 240k characters (~60k tokens) per run, so
worst-case order ~20M input tokens (before prompt caching, which the harness must
enable and count). Following repo convention, the plan does **not** print a
fabricated dollar figure: the runner computes cost from a live per-model price
table and returns `None` where a price is unknown, exactly as
`answer_baseline/config.estimate_cost_usd` does. **Owner decision Q6** is whether
a cost ceiling should bound the repeat and confirmation runs.

---

## 9. Decision gates

Hard-safety preconditions (all must pass, for every arm, before any gate is
read): zero authority leakage; all frozen hashes verified (corpus, chunk index,
embedding inputs, vectors); no re-embedding in a measured stage; citation validity
computed for every asserted citation; no evaluation truth reachable from any
retrieval / Wiki-build / agent / tool path (AST test); the practice set absent
from every scorecard; `shared_prompt_sha256` equal across agent arms; identical
budgets recorded per arm; and **metric completeness** — every §8.2 mandatory
metric present for every applicable `(question, tier, arm)` triple, with
`authority_leakage_count = 0` everywhere. A missing or unlabelled mandatory metric
aborts the stage rather than producing a partial scorecard.

Gates are evaluated in this fixed, pre-declared order. **No outcome is required,
and no test asserts that any arm wins.**

**Gate S — static result (record-only, no winner required).** Report `V`, `V-lex`,
`V+`, `W` per tier across the **full §8.2 metric set, metric by metric**. H8-a's
premise is read off `required_fact_coverage@K` specifically — the metric the
hypothesis names — while `mrr`, `ndcg@K`, `complete_chain_represented`,
`forbidden_fact_hits@K` and `authority_leakage_count` are reported alongside and
never folded in. `W` may plausibly lose on ranking metrics and hold on coverage,
or the reverse; both readings are publishable and must be stated separately.
Expected: `W ≤ V` or indistinguishable on coverage. If `W` beats `V` statically at
any tier, H8-a's premise is weakened and the record must say so plainly rather
than quietly enjoying the win.

**Gate A1 — an agent advantage exists.** At `S1` **or** `S2`, on the agent
subset, with equal budgets: `Agent-W` exceeds `Agent-V` on `lineage_complete`
rate by **≥ 0.20 absolute** (≥ 5 of 24 questions), **and** per-question
improvements ≥ 5 with regressions ≤ 1, **and** no degradation in citation validity
or authority correctness, **and** the direction holds in the majority of repeats
on the repeat core.

*Per-question improvement* = strictly better on the highest-priority differing
element of the ordered tuple (`task_completed`, `lineage_complete`,
`lineage_fraction`, `required_fact_coverage@K`) with neither citation validity nor authority
correctness degraded. *Regression* = the mirror image. Every regression counts;
the word "material" is not used.

**Gate A2 — the advantage is navigation, not payload or exact match.** `Agent-W`
must retain a qualifying advantage over **`Agent-V+`** at `S1`, **and** the static
`W − V+` and `W − V-lex` deltas must be reported, **and** the lane ablation
(`W` minus `L4`, `W` minus `L5`) must be completed so the record names which
deterministic lane carried the result. If the advantage disappears against `V+`,
the finding is "repacking source text into entity-keyed payloads helps", which is
a real but different — and much cheaper — result, and must be reported as that.

**Gate A3 — richness interaction.** The `Agent-W − Agent-V` advantage must be
non-decreasing across `S0 → S1 → S2`. An advantage present only at `S0` and
shrinking with richness contradicts the stated mechanism and triggers a
corpus-artifact investigation before any claim is published.

**Gate R — retain the deterministic Wiki as an agent knowledge interface.**
A1 ∧ A2 ∧ (A3 satisfied or its failure explained and accepted) ∧ the §8.4/§8.6
cost ledger justifies the build and maintenance cost against `V` **and** against
`V+`. A Gate R record must state explicitly that `W` is retained as an *agent
interface* and **not** as a better static retriever, quoting Gate S alongside.

**Gate N — do not retain.** No qualifying advantage at equal budgets; or the
advantage dies against `V+`; or it requires unequal information return; or it
holds only on identifier-naming questions and vanishes on `T2`/`T4`; or the
deterministic-link coverage band (§2.3) was out of band; or cost is not justified.

**Falsification, stated before the run.** The four quadrants are all publishable
results: (i) `W` static-inferior **and** `Agent-W` superior → H8 supported, the
interesting outcome; (ii) `W` static-inferior **and** `Agent-W` not superior →
**H8 refuted**; the deterministic Wiki is not worth its cost in either mode, and
Stage 8 says so; (iii) `W` static-superior **and** `Agent-W` superior → a
different and simpler story than H8 (the Wiki is just a better index here); H8-a's
premise fails and the framing must be rewritten, not the data; (iv) `W`
static-superior **and** `Agent-W` not superior → the agent harness or budget is
suspect; investigate before publishing anything.

---

## 10. Confounds, unfair advantages, and falsification analysis

Every item below is a challenge to *this* design, with the mechanism, the proposed
mitigation, and the residual risk that survives mitigation. Items 1, 2, 4, 5, 6
and 9 are the ones I consider capable of invalidating the experiment outright.

### 10.1 The corpus is authored by the same party that designs the Wiki — **most material**

*Mechanism.* Documents can be written, consciously or not, in exactly the shapes
`L4`/`L5` capture, so `W` is measured on a corpus tailored to it. This is the
single biggest threat to the whole experiment.

*Mitigation.* F1 freezes the lane contract **before** any corpus text exists; the
corpus generator is written against the backbone spec and is blind to the lane
implementation; the `prose_only_backbone` quota puts ≥ 30% of backbone facts out
of `L4`/`L5` reach by construction; the deterministic-link coverage band
(0.55–0.75) is declared in advance and a measured value outside it means
**re-author, not re-interpret**; per-lane backbone coverage is a published
pre-freeze artifact.

*Residual risk.* Real. The strongest available fix is a **blind replication**:
`S1-B`, authored from the same backbone spec by a party (or an LLM session) with
no access to the lane rules, run through the identical harness. Recommended as
required for a Gate R publication — **owner decision Q4**.

### 10.2 Is richness controlled, or is `S2` simply adversarial to `V`?

*Mechanism.* Semantic near-duplicates hurt a vector retriever more than an
identifier-keyed index. A ladder built only from `qualifier_variant` and
`adjacent_domain` content would produce H8-b mechanically.

*Mitigation.* The closed `elaboration_reason` vocabulary (§2.3) includes four
explicitly **`W`-adversarial** growth modes — anchor fan-out inflation, title
collisions, identifier-variant noise, prose-only backbone facts — and the tier
ladder must grow them at least proportionally to the `V`-adversarial modes. Counts
per reason per tier are a published artifact, and every added chunk carries its
reason tag.

*Residual risk.* "Proportional" is a judgement about what counts as equally
adversarial. The mitigation makes the mix **visible and pre-declared**; it cannot
make it provably neutral. The record must publish the mix beside the result so a
reader can discount it.

### 10.3 Are `S0`/`S1`/`S2` genuinely comparable?

*Mechanism.* `N` changes by an order of magnitude, so coverage, `ndcg@K` and
random-hit probability are not comparable across tiers; a naive "coverage fell at
`S2`" reading would be meaningless.

*Mitigation.* Questions, answers, `K`, prompts, budgets, embedding config and
evaluator are invariant; only `N`, distractor pressure and fan-out move.
Cross-tier claims are made **only on the arm difference**, never on levels. `K/N`
is reported with every number, and a chance-corrected view accompanies the raw
metrics.

*Residual risk.* The tiers are three points, not a curve; "non-decreasing across
three points" is weak evidence for a monotone mechanism, and §9's Gate A3 should
be read as a direction check, not a scaling law.

### 10.4 Does the Wiki receive information `V` lacks?

*Mechanism.* `W` has facet payloads, typed links and an anchor index. Each is
derived from the same bytes, but as *index structure* they are information `V`
does not have.

*Mitigation.* Three layers. (a) The **no-new-text proof** (§4.3) mechanically
guarantees every embedded Wiki token traces to verbatim source or a closed
structural vocabulary. (b) **`V+`** gets the identical facet payload rows without
structure, so `V+ − V` prices the repacking and `W − V+` prices the navigation.
(c) **`V-lex`** gets exact identifier matching, so `W`'s `L1` lane cannot masquerade
as a win.

*Residual risk.* Typed links have no `V` counterpart at all — that is the declared
treatment, not a leak. But it means a Gate R result says "deterministic typed
structure over source tables helps an agent", which is narrower than "a Wiki
helps".

### 10.5 Is `Agent-W`'s interface more expressive?

*Mechanism.* Six tools versus five; `list_neighbours` returns structured
relational metadata at very low token cost, which is a genuine information-density
advantage even at an equal call count.

*Mitigation.* The §7.4 capability matrix requires a declared counterpart for every
capability; the binding control is the **equal information-return budget in
characters**, not merely equal call counts; per-call return caps are equal; and
§8.4's efficiency ratios expose density differences directly.

*Residual risk.* The residual asymmetry (`open_page`) is the treatment itself and
cannot be neutralized without deleting the experiment. Honest framing: Stage 8
measures whether *this specific added expressiveness*, at equal budgets, buys
research performance.

### 10.6 Can `Agent-V` recreate navigation by iterative semantic search?

*Mechanism.* This is the null hypothesis, and it is a strong one: an agent that
reads `CTL-114` in a retrieved chunk can search for `CTL-114` next — which is
navigation by another route.

*Mitigation.* `identifier_filter` on `vector_search` makes that route *exact*
rather than approximate; the shared prompt explicitly instructs reformulation from
discovered entities; `reformulation_count` and discovered-identifier reuse rate are
reported so the record can show `Agent-V` actually tried; and the `claude-opus-5`
confirmation run tests whether a stronger agent closes the gap.

*Residual risk.* If the effect is agent-capability-dependent, the honest finding is
"the Wiki helps *this* agent at *this* budget" — which is a legitimate and useful
engineering result, but must not be stated as a representation-level truth.

### 10.7 Do `K` or exploration budgets advantage an arm?

*Mechanism.* Final `K` is identical, but `W`'s exploration *unit* is a facet that
can hand over several member chunks at once, so a single `open_page` may deliver
multiple required facts.

*Mitigation.* Final `K` is identical and enforced; exploration is bounded by the
**character** budget rather than the call count, which prices dense returns;
`evidence_chars_per_validated_hop` and `required_facts_per_10k_returned_chars` are
reported; and a doubled-budget sensitivity arm at `S2` shows whether the result is
budget-bound at all.

*Residual risk.* Character metering at a nominal 4 chars/token is approximate
across arms whose returns have different structure (tables versus prose). The
harness therefore records model-reported token usage as well, and any arm gap over
5% in actual returned tokens must be reported beside the result.

### 10.8 Does question wording leak page identity?

*Mechanism.* `W`'s page keys *are* the corpus's identifiers, so any question
naming `CTL-114` names a page. Class `T1` does this by definition.

*Mitigation.* No question may name a Wiki-**internal** artifact (hard test);
corpus-native identifiers are permitted only in declaring classes; `T2` forbids
identifiers entirely; `identifier_mention_count` is an analysis covariate; and
**§9 Gate N fires if the advantage holds only on identifier-naming questions and
vanishes on `T2`/`T4`**. Results are always class-stratified.

*Residual risk.* Identifier-explicit questions are realistic enterprise queries, so
excluding them would be its own distortion. The design keeps them and refuses to
let them carry the headline.

### 10.9 Do the task classes truly require multi-hop discovery, and can the metrics tell coverage from chains?

*Mechanism.* A "multi-hop" question that a single chunk answers, or whose answer
co-occurs with the query terms somewhere, is a one-hop question in disguise. And
coverage metrics alone cannot distinguish "held all five chunks" from "joined all
five hops".

*Mitigation.* The §2.6 screens (single-chunk sufficiency, answer co-occurrence,
lexical triviality) run **before** F2/F3 and demote or re-author any question that
fails. The §8.1 four-level metric split plus `disconnected_coverage_count` and the
joint `(coverage, lineage)` table make the distinction the primary reported
quantity, and lineage requires **direction-correct, span-validated** hops.

*Residual risk.* Lineage validation depends on the frozen accepted-relation-label
set; an agent that expresses a correct hop with an unlisted label scores zero. The
label sets come from the corpus's own verbatim vocabulary, and any such miss is
reported as an evaluator limitation with the frozen score standing.

### 10.10 Agent non-determinism
Repeats on the core, majority rule, published variance, declared noise band;
differences inside the band are reported as no difference.

### 10.11 Hosted-model drift (preview embedding model)
Vectors frozen with manifests; stability probe published; query-embedding cache
shared by both arms; `response_model_version` recorded per row. A mid-experiment
provider change cannot silently alter frozen vectors, and re-embedding is banned.

### 10.12 Evaluator surface-form dependence
Accepted variants frozen in F3 before any run; no post-hoc additions; corrections
publishable only as labelled secondary analysis.

### 10.13 Build-cost asymmetry
`W` costs more to build (facet payloads ≈ 2× the chunk tokens, plus lane
extraction). The full ledger — build, storage, query, agent, maintenance — is
reported, and Gate R requires cost justification against both `V` and `V+`.

### 10.14 Statistical power
48/24 questions per tier. No significance claims below 20 per stratum;
pre-declared margins and per-question tables instead.

### 10.15 Single domain, generator, embedding model, agent model
All findings are scoped to one synthetic domain, one deterministic generator, one
embedding model, one primary agent model, DOCX only. Recorded as a stated
limitation in the decision record, not discovered afterwards.

### 10.16 Table-chunk embedding noise
The frozen chunker's structural table rendering (`row=`, `col=`, `header=`) is
poor embedding input. It affects `V` and `W` identically because they share the
rows — but it may depress *both* arms' performance on register content, which is
where much backbone truth lives. Reported as a measured observation per tier
(register-chunk retrieval rate), never fixed mid-experiment.

### 10.17 Fan-out paging interacts with the agent budget
At `S2`, a 120-neighbour hub needs six `list_neighbours` calls to enumerate. That
consumes the very budget `Agent-W` needs for verification, and could make `W` look
worse at `S2` for a paging-parameter reason rather than a representational one.
Mitigation: `neighbour_page_size` is frozen in F5, the doubled-budget sensitivity
arm at `S2` distinguishes the two explanations, and `budget_exhausted_reason` is
reported per run.

### 10.18 "You reintroduced the Graph"
`L4`/`L5` produce directed, typed, relation-labelled links — structurally
graph-like. The distinction, stated before the run so it cannot look like a
retrofit: Stage 7B's graph was **LLM-extracted** (recall ≈ 0.8, non-deterministic
at temperature 0, a missed edge breaking a chain); Stage 8's links are
**deterministic reads of source table geometry and verbatim cue phrases**, with a
mandatory source span per link and byte-reproducible output. And no link is ever
evidence: every asserted hop must resolve to a source chunk span (§5.5 step 7,
§7.3). If the owner considers `L4` too graph-adjacent for the core experiment,
running it as a declared `W`-lane ablation instead is a one-line contract change —
**owner decision Q3**.

### 10.19 Proposed modifications this analysis recommends

1. **Add `V-lex` and `V+` as required static arms** and `Agent-V+` as a required
   `S1` ablation (they make a positive result interpretable).
2. **Meter the information-return budget in characters, not tool calls** — the
   real fairness knob.
3. **Include the four `W`-adversarial elaboration reasons** in the richness ladder.
4. **Pre-declare the deterministic-link coverage band (0.55–0.75)** and re-author
   if it is missed.
5. **Add the pre-freeze lexical-triviality and single-chunk-sufficiency screens**.
6. **Add a practice question set** so harness debugging never touches benchmark
   questions.
7. **Add the `claude-opus-5` confirmation run** so an agent-capability confound is
   measured rather than assumed.
8. **Strongly consider the blind-authored `S1-B` replication** (Q4) — it is the
   only real answer to §10.1.

---

## 11. Implementation-stage plan

No stage begins before owner approval of this document; each stage has its own
freeze boundary and its own committed artifacts.

| Stage | Scope | Key artifacts | Freeze on exit |
|---|---|---|---|
| **8.0** | this design | `docs/STAGE8_AGENT_WIKI_PLAN.md` | — (owner review) |
| **8A.0** | F1: lane contract, identifier families, cue list, backbone spec, task taxonomy, question schema | `contracts/stage8_ingestion_lanes_v1.json`, `contracts/stage8_backbone_v1.json` | **F1** |
| **8A.1** | corpus authoring + generation for `S0`/`S1`/`S2`; chunking with the frozen config; §2.6 validity screens | `fixtures/stage8/<tier>/`, `generation_manifest.json`, `reports/stage8_corpus_profile.json`, screen reports | **F2, F3** |
| **8A.2** | `gemini-embedding-2` binding: provider, templates, guards, batch/retry, stability probe, manifests, fake provider, chunk + facet vectors | `stage8_embedding_input_manifest.json`, `stage8_vector_manifest.json`, probe report | **F4** |
| **8A.3** | deterministic Wiki build (`L1`–`L5`), link evidence, authority-scoped view, lane-ablation builds | projection report, per-lane coverage, fan-out and page/facet counts | Wiki build immutable |
| **8A.4** | static measured run: `V`, `V-lex`, `V+`, `W` (+ `W-semrank`) × 3 tiers; Gate S record | `reports/stage8a_static_results.json`, scorecard | **F5** for static |
| **8B.0** | agent harness: tool servers, budget meters, output schema, mechanical validators, audit tests, dry run on the practice set only | harness tests, capability-matrix audit, `shared_prompt_sha256` | agent config |
| **8B.1** | agent measured run: `Agent-V` vs `Agent-W` × 3 tiers; repeats; `Agent-V+` at `S1`; `claude-opus-5` confirmation; `S2` doubled-budget sensitivity | `reports/stage8b_agent_results.json`, per-run transcripts with tool-call ledgers | — |
| **8B.2** | analysis: gates in declared order, lane and payload attribution, confound audit, decision record | `docs/STAGE8_AGENT_WIKI_DECISION.md`, findings page | decision frozen |
| **8C** | *optional, separately proposed*: source-native image/multimodal evidence on the same model | new plan document | — |

**Proposed repository changes (not made yet).** New package
`src/ingestion_bench/source_wiki/` (identity lanes, projection, navigation,
retrieval, payloads); `src/ingestion_bench/gemini_embeddings/` (provider,
templates, manifests, fake); `src/ingestion_bench/stage8_benchmark/` (runner,
sibling evaluator, agent harness, tool servers); `fixtures/stage8/`;
`contracts/stage8_*.json`; new Postgres tables prefixed **`edib_stage8_`** only.
Reused **read-only and unmodified**: the chunker and `ChunkingConfig`, the
Stage 7R registry/resolver, the Stage 7B.0 evaluator (`_evaluate_question`,
`build_evidence_alignment`), the identifier regex, the fixture-determinism
pattern. Explicitly **not modified**: every Stage-7C module, contract, table and
report; `wiki_projection/compiler.py` is not imported by anything in Stage 8
(hard test).

---

## 12. Open questions requiring owner decision before implementation

Q1 is resolved (D-056). Eleven remain open, and Stage 8A cannot begin until
they are settled.

| # | Question | Recommendation |
|---|---|---|
| ~~**Q1**~~ | ~~Stage-numbering collision with the pencilled Stage 8A/8B vision lane (§0)~~ | **RESOLVED — approved and landed as D-056: Stage 8 is this experiment; vision lane → Stage 10A/10B** |
| **Q2** | Output dimensionality: 1,536 frozen, with 3,072 as an `S1` sensitivity run? | yes — 1,536 (§4.2) |
| **Q3** | Is the `L4` table-derived typed-link lane inside the core `W`, or a declared ablation only? | inside core `W`; lane ablation mandatory either way (§10.18) |
| **Q4** | Commission the blind-authored `S1-B` replication corpus? | yes if a Gate R publication is intended (§10.1) |
| **Q5** | Agent model: `claude-sonnet-5` primary + `claude-opus-5` `S1` confirmation? | yes (§7.6) |
| **Q6** | Cost ceiling for the 336 agent runs, and whether repeats/confirmation are in or out of scope | owner call; the plan degrades gracefully to 144 runs with repeats dropped |
| **Q7** | Tier sizes as tabled (§2.4), or a smaller `S2` (e.g. 2,000 chunks) to control cost? | as tabled; `S2` is where the hypothesis lives |
| **Q8** | Are `V-lex`, `V+` and `Agent-V+` accepted as required arms? | yes — without them a positive result is uninterpretable (§1.3) |
| **Q9** | Is agent abstention an acceptable outcome class? | yes — scored separately, never silently as failure |
| **Q10** | Deterministic-link coverage band 0.55–0.75 — accepted as a re-author trigger? | yes (§2.3) |
| **Q11** | Final `K` defined on required **evidence units** (`K = U + 2`) rather than required facts (`R + 2`), because `K` budgets chunks and Stage 8 chunks carry 2–6 facts? | yes — §2.4; `R + 2` would hand every arm invisible slack |
| **Q12** | Report `required_fact_coverage@K` (fact-level, new sibling computation) **beside** `required_evidence_unit_coverage@K` (the frozen 7B.0 quantity), rather than reusing the frozen number under a fact-level name? | yes — §8.2.1; reusing it would repeat the 7C metric-label divergence |

---

## 13. What this experiment will not establish, recorded before it runs

It will not establish that a Wiki helps agents in general: one synthetic
enterprise-governance domain, one deterministic generator, one embedding model,
one primary agent model, DOCX only, three corpus sizes topping out at ~3,200
chunks. It will not establish production scalability, latency or cost under real
load. It will not measure human usability of the Wiki pages. It will not settle
the Graph question — that remains closed at Stage 7B.2a gate D. It will not
produce a claim about multimodal evidence (`8C`, unproposed). And it cannot fully
escape §10.1: the corpus and the Wiki come from the same hand, and only a
blind-authored replication would answer that properly.

---

## 14. Sources for the `gemini-embedding-2` binding

- [Embeddings | Gemini API | Google AI for Developers](https://ai.google.dev/gemini-api/docs/embeddings)
- [Building with Gemini Embedding 2: Agentic multimodal RAG and beyond — Google Developers Blog](https://developers.googleblog.com/building-with-gemini-embedding-2/)
- [Gemini Embedding 2: Our first natively multimodal embedding model — Google blog](https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-embedding-2/)
- [Gemini Embedding 2 | Gemini Enterprise Agent Platform | Google Cloud Documentation](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/embedding-2)
- [Gemini Developer API pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [pgvector — index dimension limits (`vector` 2,000 / `halfvec` 4,000 for HNSW)](https://github.com/pgvector/pgvector)
