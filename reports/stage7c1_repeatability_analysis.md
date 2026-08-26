# Stage 7C.1 — repeatability analysis over the frozen Runs 1/2/3

> **Read-only.** No frozen Stage 7C.1 artifact was modified, no compilation was
> rerun, no model call was made, and **Gate Q is not updated by this document.**
> Machine-readable companion: `reports/stage7c1_repeatability_analysis.json`,
> regenerable with `python scripts/analyze_stage7c1_repeatability.py`.
>
> Frozen projection `4162fa515cf29d09…` · primary run **1** · compiler
> `gpt-4o-mini` @ `temperature = 0` · 22 facets × 3 runs.

---

## 1. Why the code and the checkpoint report disagree

Revision 6 §8F states the repeatability quantity **twice**, and the two
statements differ:

| Where | Wording |
|---|---|
| §8F *metric list* | "claim-set stability (**Jaccard over normalized `(subject, predicate, object, sorted supporting_chunk_ids)`**)" — population unqualified |
| §8F *threshold* | "**accepted-claim set** pairwise Jaccard **≥ 0.90**, **citation sets on matched claims ≥ 0.95 exact**" |

What the code does:

- **`benchmark._normalized_claim_keys()`** implements the **metric-list**
  wording — its docstring quotes that tuple verbatim — and so iterates
  `validation.claims`, i.e. **every** claim the compiler emitted, including
  `rejected`, `uncertain` and `out_of_page_scope`.
- **`benchmark._citation_keys()`** implements **neither**. It computes a Jaccard
  over tuples that *embed the quotes*, so a differing quote makes the whole
  tuple miss — conflating "this claim did not appear in the other run" with
  "this claim's citations differed". The contract asks for a different shape
  entirely: among claims that **match** between two runs, the fraction whose
  citation sets are **exactly** equal.

What the report did: `report.build_gate_q_pre_status()` compared the
all-output number against the **accepted-claim** threshold and printed it under
the label *"accepted-claim-set pairwise Jaccard"*. **The label described the
contract; the number did not.**

## 2. Every variant, side by side

| pair | claim (all output) | claim (accepted only) | citation (all, as-implemented) | citation (accepted, as-implemented) |
|---|---|---|---|---|
| run1 vs run2 | 0.6250 | 0.6667 | 0.5758 | 0.6667 |
| run1 vs run3 | 0.5294 | 0.6207 | 0.5294 | 0.6207 |
| run2 vs run3 | 0.7931 | 0.8261 | 0.6774 | 0.8261 |
| **min** | **0.5294** | **0.6207** | **0.5294** | **0.6207** |

Distinct keys per run — all-output **26 / 26 / 26**; accepted-only **25 / 20 / 22**.

**The metric §8F's threshold actually names for citations** — exact agreement on
matched claims, not a Jaccard:

| pair | accepted-only | all-output |
|---|---|---|
| run1 vs run2 | 18/18 = **1.0000** | 19/20 = 0.9500 |
| run1 vs run3 | 18/18 = **1.0000** | 18/18 = 1.0000 |
| run2 vs run3 | 19/19 = **1.0000** | 21/23 = 0.9130 |

### What this changes

| Threshold | Previously reported | Correct population / metric | Status |
|---|---|---|---|
| accepted-claim Jaccard ≥ 0.90 | 0.5294 | **0.6207** | **still breached** |
| citation ≥ 0.95 exact on matched | "0.5294 < 0.95" | **1.0000** | **not breached — this failure does not exist** |

So the Q-8 breach is **real but single-cause**: claim-set instability. The
citation half of the reported breach was an artifact of the wrong metric. The
committed `reports/stage7c1_checkpoint_results.json` still carries the original
figures; it is left byte-identical on purpose, and this document is the
correction of record.

### The misses are genuine model variance, not validator flicker

| pair | union | shared | misses | same output, different status | genuine content difference |
|---|---|---|---|---|---|
| run1 vs run2 | 27 | 18 | 9 | 1 | **8** |
| run1 vs run3 | 29 | 18 | 11 | 0 | **11** |
| run2 vs run3 | 23 | 19 | 4 | 1 | **3** |

Only 2 of 24 misses across all pairs are the same claim accepted in one run and
not the other. The rest are the model saying something different.

## 3. Facet-by-facet classification

**15 of 22 facets are byte-identical across all three runs.** All variance is
concentrated in 7 facets.

Pairwise difference instances (one divergence can surface in up to two pairs):

| Classification | Instances |
|---|---|
| noun-phrase / canonical wording variation | 8 |
| **semantic direction change** | **4** |
| omitted / extra claim | 4 |
| quote-span variation | 3 |
| **entity / endpoint change** | **2** |
| **semantic predicate change** | **1** |

| Facet | Revision | Nature of variance |
|---|---|---|
| `IDENT:APP-224499` | app_rev1 | wording (`the …` prefix) |
| `IDENT:APP-330012` | adj_rev1 | wording |
| `IDENT:C-88` | obl_rev2 | **direction** |
| `IDENT:O-32` | adj_rev1 | quote-span — drives a `rejected` → `accepted` flip |
| `IDENT:P-301` | adj_rev1 | **direction + entity + predicate**, plus omitted/extra |
| `PHRASE:payment settlement` | app_rev1 | wording — drives `out_of_page_scope` → `accepted` |
| `PHRASE:payment settlement` | app_rev2 | wording — drives `accepted` → `out_of_page_scope` |

Two structural observations:

1. **`adj_rev1` is the corpus's only multi-sentence chunk** (5 sentences) and
   hosts 3 of the 7 unstable facets, including *every* entity and predicate
   change. Single-sentence facets are stable apart from one direction swap and
   the noun-phrase variants. Instability tracks chunk complexity.
2. **Wording variants are not cosmetic here.** §4.1.15 page coherence is an
   exact normalized match, so `Payment Settlement` vs `Payment Settlement
   business service` flips acceptance outright — which is why three of the
   status changes above are driven by wording alone.

## 4. Semantic changes — source and all three runs

### `IDENT:C-88` / obl_rev2

**Source:** `"Obligation O-31 is satisfied by Control C-88."`

| Run | Claim | Quote | Status |
|---|---|---|---|
| 1 | `Control C-88` —[is satisfied by]→ `Obligation O-31` | *"Obligation O-31 is satisfied by Control C-88."* | accepted |
| 2 | `Control C-88` —[is satisfied by]→ `Obligation O-31` | same | accepted |
| 3 | `Obligation O-31` —[is satisfied by]→ `Control C-88` | same | accepted |

Same predicate, same quote, **endpoints swapped**. Runs 1/2 and run 3 assert
opposite directions and all three were mechanically accepted. Run 1 — the frozen
primary — carries the ordering that is reversed relative to the source sentence.

### `IDENT:P-301` / adj_rev1

**Source:** `"Application APP-330012 supports the Payment Reconciliation business service. / The Payment Reconciliation business service is governed by Obligation O-32. / Obligation O-32 is satisfied by Control C-77. / Control C-77 is implemented through Procedure P-301. / Procedure P-301 is the current operating procedure for reconciliation."`

| Run | Claim | Quote | Status |
|---|---|---|---|
| 1 | `Obligation O-32` —[is governed by]→ `Procedure P-301` | *"Obligation O-32 is satisfied by Control C-77."* | accepted |
| 1 | `Control C-77` —[is implemented through]→ `Procedure P-301` | *"Control C-77 is implemented through Procedure P-301."* | accepted |
| 1 | `Procedure P-301` —[is the current operating procedure for]→ `reconciliation` | *"Procedure P-301 is the current operating procedure for reconciliation."* | accepted |
| 2 | `Procedure P-301` —[is implemented through]→ `Control C-77` | *"Procedure P-301 is implemented through Control C-77."* | rejected — quote not in source |
| 2 | `Control C-77` —[is satisfied by]→ `Obligation O-32` | *"Obligation O-32 is satisfied by Control C-77."* | out_of_page_scope |
| 2 | `Obligation O-32` —[governed by]→ `Payment Reconciliation business service` | *"The Payment Reconciliation business service is governed by Obligation O-32."* | out_of_page_scope |
| 3 | `Procedure P-301` —[is implemented through]→ `Control C-77` | *"Procedure P-301 is implemented through Control C-77."* | rejected |
| 3 | `Control C-77` —[is satisfied by]→ `Obligation O-32` | *"Control C-77 is satisfied by Obligation O-32."* | out_of_page_scope |
| 3 | `Obligation O-32` —[is governed by]→ `Payment Reconciliation business service` | same as run 2 | out_of_page_scope |

Three distinct changes:

- **direction** — `C-77 → P-301` (run 1) vs `P-301 → C-77` (runs 2/3);
- **entity/endpoint** — same subject and predicate, object `Procedure P-301`
  (run 1) vs `Payment Reconciliation business service` (runs 2/3);
- **predicate** — `governed by` (run 2) vs `is governed by` (run 3), which also
  changes coherence normalization.

> **One item flagged for adjudication attention, with no verdict rendered here.**
> Run 1's first row asserts `O-32 —is governed by→ P-301` while its cited quote
> states *"Obligation O-32 is satisfied by Control C-77"* — a different subject,
> predicate and object than the claim. It passed mechanically because the quote
> is an exact substring of an in-scope chunk, `P-301` appears as the object
> satisfying §4.1.15 coherence, and both identifiers occur somewhere in the
> cited chunk. It is packet item `CLAIM::IDENT:P-301|…::claim_1`. Whether the
> claim faithfully represents the passage is a §4.3 judgement and remains yours.

## 5. What this document does not do

- It does **not** update Gate Q. The accepted-claim breach (0.6207 < 0.90)
  stands; the citation breach does not exist. Whether that changes the Gate Q
  outcome is your call under open question **Q5**.
- It does **not** modify any frozen Stage 7C.1 artifact, rerun the compiler,
  change a threshold, or repair an output.
- It does **not** implement either known gap. Both remain pending a
  Stage 7C.1B decision:
  1. **Metric correction** — `_normalized_claim_keys` / `_citation_keys` should
     compute the threshold's population and definition, or §8F's two statements
     should be reconciled explicitly.
  2. **Pass-3 claim withdrawal** — §4.6's closing invariant ("Nothing that
     failed adjudication reaches a vector, a summary, or a derived link") is not
     implemented for claims; only the alias cascade and summary withdrawal are.
     All 25 accepted-claim verdicts are therefore load-bearing for the final
     W1-D / W1-FULL representation and routing.
