# Stage 7C.1 — post-adjudication closure and decision record

> **Stage 7C.1 is CLOSED. Final Gate Q = FAIL** (Q-5, Q-7, Q-8).
> Stage 7C.2 is **not started**: no D0, no W1-D, no W1-FULL, no retrieval
> question was run.
>
> Zero compiler calls were made in this closure. Frozen Runs 1/2/3, the frozen
> owner-adjudication packet, the frozen Stage 7C.0 projection and
> `docs/STAGE7C_WIKI_PLAN.md` are byte-identical.

| Frozen identity | Value |
|---|---|
| Basis commit | `a443535ab6aaed294f98af10ef5fe5e30739b9b8` |
| Projection hash | `4162fa515cf29d09391c0d963b76c7e63b1d454c4439ee0568805d1a31e3b613` |
| Adjudication packet SHA-256 | `5d08b88dc9473a07ff94ddaead911a1a2aa54aba384afeec0f85b9a97ccb2065` |
| Verdict-set SHA-256 | `d49cc8643388f830ffbcf5097faa8335a40c366b06b8f54a176aa978b06158bd` |
| Compiler / prompt | `gpt-4o-mini` · `stage7c1-facet-compiler-v1` · `1144ceff32112796…` |
| Primary representation | Run 1 (designated before execution) |
| Facets / pages | 22 / 13 |
| Closure semantic hash | `03a1f08203551c7b3907aec4f63be295d3c09c287d2ee11f3613e68a7b008bb7` |

---

## 1. Owner inputs of record

**Q5 — APPROVED** (`reports/stage7c_q5_owner_decision.json`). The predeclared
Revision 6 repeatability thresholds are adopted exactly as proposed: N = 3,
Run 1 primary, accepted-claim pairwise Jaccard ≥ 0.90, citation exact agreement
on matched accepted claims ≥ 0.95, false merges 0, ceiling breaches 0. No
threshold was changed in response to any measured result. This is a post-plan
owner decision of record; it does **not** amend Revision 6.

**Verdict set** (`reports/stage7c1_adjudication_verdict_set.json`) — 68 items:
25 claims, 21 supported aliases, 22 summary sentences; **63 CORRECT, 5
INCORRECT, 0 UNVERIFIABLE**. Used exactly as supplied; no verdict or reason was
reinterpreted, normalized, repaired or replaced.

## 2. Preflight — fail closed

All ten integrity checks passed before pass 3 and before any embedding: the
7C.0 projection still rebuilds to its frozen hash; the stored runs correspond to
that projection; the primary run is Run 1; model and prompt provenance match the
frozen Run-1 record; the packet SHA matches the frozen packet; the verdict JSON
parses as `AdjudicationVerdictSet`; the required item ids collected across all 22
Run-1 facets equal the supplied ids **exactly** (no missing, no extra); the count
is 68; and the verdict-set SHA matches.

## 3. Pass 3 (§4.6) — aggregate before → after

Applied by the existing `apply_pass3()`; no second implementation of
adjudication semantics exists.

| Quantity | Before | After |
|---|---|---|
| Supported aliases | 21 | **21** |
| Mechanically accepted claims | 25 | **22** |
| Reference-valid summary sentences | 21 | **19** |
| Claim-derived links | 34 | **30** |

**No alias was withdrawn.** Three accepted claims and two summary sentences did
not survive:

| Withdrawn | Facet | What the owner judged |
|---|---|---|
| claim | `IDENT:C-88` / obl_rev2 | C-88 / O-31 reversed direction |
| claim | `IDENT:O-32` / adj_rev1 | O-32 / Payment Reconciliation reversed direction |
| claim | `IDENT:P-301` / adj_rev1 | malformed O-32 → P-301 structured triple |
| summary | `IDENT:C-88` / obl_rev2 | C-88 / O-31 reversed summary |
| summary | `IDENT:O-32` / adj_rev1 | governance-reversal composite |

**Mechanical status was never rewritten.** Each withdrawn claim still reads
`validation_status = "accepted"` in the audit record; withdrawal is a separate,
owner-originated state. §4.2 requires the mechanical record to stand, and
conflating the two would erase the distinction §4.3–4.5 exist to preserve.

**One edge case, deliberately not "repaired".**
`SUMMARY::PHRASE:payment settlement|8954…::sentence_1` carries owner verdict
**CORRECT**, but its mechanical `reference_valid` is **False** — it references no
accepted in-scope claim on that facet. It remains structurally ineligible and is
absent from the final payload. The verdict means only that the sentence is
faithful to its source; it does not confer structural eligibility.

**Membership untouched.** Projection hash, facet membership hashes, postings and
deterministic links are identical before and after, under every verdict.

## 4. Final representation

- **22 final facet payloads**, composed by the one frozen
  `compose_payload_preview` path in final mode. Every payload:
  `is_final == True`, `pending_components == []`, carries the verdict-set hash,
  contains no withdrawn alias / failed claim / ineligible summary, and preserves
  the fixed component order, the exact-match summary dedupe and the `PAY_max`
  drop order.
- **30 claim-derived links**, re-derived through the existing `derive_links()`
  from surviving claims only — never by filtering the old 34-link set. No
  inverse predicate was invented; deterministic structural and exact-anchor
  links are untouched.
- **22 final facet embeddings** — one per facet, none per page — using the
  existing `sentence-transformers/all-MiniLM-L6-v2` provider at dim 384. Each
  record binds its vector to `payload_sha256`, `projection_hash`,
  `verdict_set_sha256`, compiler model, prompt version + SHA, run id 1, source
  chunk ids and revision, with `representation_derivation =
  post_adjudication_w1_facet_payload` and `is_authoritative_lineage = False`.

No page-level vector, no second representation, no reranker, no LLM at embedding
time, and no global page summary. Facet remains the semantic landing/embedding
unit; page remains the deterministic identity hub.

## 5. Expected-fact recall (Gate Q-6), computed only now

Deferred until after adjudication on purpose, so benchmark truth was never
placed beside unadjudicated output. Truth is read **read-only**, solely to
score — nothing was added, repaired or rewritten.

**Primary: 13 / 15 = 0.8667.**

*Mapping rule, declared before the number was read:* a frozen fact is recalled
when a **surviving** post-pass-3 accepted claim (a) cites that fact's supporting
chunk and (b) has **entity-normalized** endpoints equal to the fact's
`{subject, object}` as a set. Entity normalization strips determiners and generic
type nouns.

Two choices, each with its reason:

- **Entity normalization, not exact matching.** The frozen Stage 7B.1 Graph
  figure this will be compared against in §9.4 (edge recall 0.80) was itself
  measured after `normalize_entity_name`, which strips exactly these. Scoring
  Wiki more strictly than its comparator would understate it by construction and
  make the attribution unsound. *(The rule is lifted as a neutral local
  implementation, not imported — a Graph runtime dependency stays forbidden.)*
- **Direction is not re-tested mechanically.** Direction correctness is an owner
  judgement (§4.3) already applied in pass 3; re-testing it here would
  double-count that judgement.

**Sensitivity, reported so the choice is visible: 9 / 15 = 0.6000** under exact
normalized endpoints. Four facts match only after entity normalization
(`F_prc_current`, `F_app_historical`, `F_prc_historical`, `F_adj_app`) — in each
case the difference is a determiner or a `business service` / `operating
procedure` type noun.

The two genuine misses:

| Fact | Why |
|---|---|
| `F_adj_svc` | its claim was the owner-INCORRECT governance reversal, withdrawn in pass 3 |
| `F_adj_prc` | the surviving claim states object `reconciliation`, not `current operating procedure for reconciliation` |

Under the strict rule Q-6 would read 0.60 and FAIL. **Gate Q is FAIL either way**
(Q-5, Q-7, Q-8), so this choice does not change the outcome — but it changes the
record, and the §9.4 comparison later depends on it, so both figures are
reported.

## 6. Final Gate Q — conjunctive, every criterion evaluated

| # | Criterion | Required | Observed | Status |
|---|---|---|---|---|
| Q-1 | Citation validity | 1.00 | 1.00 (26/26) | **PASS** |
| Q-2 | Invalid source references | 0 | 0 | **PASS** |
| Q-3 | Revision-scope contamination | 0 | 0 | **PASS** |
| Q-4 | False merges (incl. C-88 / C-88A) | 0 | 0 | **PASS** |
| Q-5 | Accepted-claim precision | ≥ 0.95 | **0.88** (22 CORRECT / 25 accepted) | **FAIL** |
| Q-6 | Expected-fact recall | ≥ 0.80 | 0.8667 (13/15) | **PASS** |
| Q-7 | Summary correctness | 0 incorrect | **2 incorrect** (20 correct of 22) | **FAIL** |
| Q-8 | Repeatability | Jaccard ≥ 0.90, citation ≥ 0.95, merges 0, breaches 0 | **Jaccard min 0.620690**; citation min 1.0000; merges 0; breaches 0 | **FAIL** |
| Q-9 | Budget and ceilings | no breach | 0 breaches, 0 generation failures | **PASS** |
| Q-10 | Supported-alias precision | 0 incorrect | 0 (21/21 CORRECT) | **PASS** |

### GATE Q = FAIL

**Exact reasons, and only these three:**

1. **Q-5** — accepted-claim precision 22/25 = 0.88 < 0.95. Three mechanically
   accepted claims were owner-judged INCORRECT.
2. **Q-7** — 2 summary sentences owner-judged INCORRECT; the bar is zero.
   Mechanical reference validity is kept separate: the one reference-invalid but
   semantically CORRECT sentence does not offset these two semantic errors.
3. **Q-8** — accepted-claim pairwise Jaccard minimum 0.620690 < 0.90.
   **Solely claim-set instability.** Citation exact agreement is 1.0000 on every
   pair and passes; the pre-correction citation-Jaccard "failure" was a metric
   artifact and is not resurrected here.

No threshold was relaxed after seeing these results.

## 7. Consequence — recorded, not executed

- Stage 7C.2 **remains permitted** under Revision 6 and is **not started**.
- When it runs, W1-D and W1-FULL results must carry
  **`NON-QUALIFYING / DIAGNOSTIC ONLY`** with the Q-5/Q-7/Q-8 failures printed
  adjacent.
- **Gate A is unreachable for W1.**
- **D0 consumes no W1-derived model output** and remains fully qualifying; the
  deterministic Wiki evidence can still support a later Gate-B analysis.
- This closure implements and runs **no** D0, W1-D, W1-FULL or retrieval
  question, and draws **no** conclusion about W1's retrieval value.

## 8. Artifacts

| File | Contents |
|---|---|
| `reports/stage7c_q5_owner_decision.json` | owner Q5 decision (as supplied) |
| `reports/stage7c1_adjudication_verdict_set.json` | the 68 verdicts (as supplied) |
| `reports/stage7c1_pass3_results.json` | per-facet pass 3, aggregate before/after, withdrawals |
| `reports/stage7c1_final_payloads.json` | 22 final payloads + 30 final links |
| `reports/stage7c1_final_embedding_manifest.json` | embedding provenance (vectors excluded) |
| `reports/stage7c1_expected_fact_recall.json` | recall ledger, both rules, per-fact |
| `reports/stage7c1_gate_q_final.json` | criterion-by-criterion Gate Q |
| `artifacts/stage7c1_closure/facet_embeddings.json` | the 22 vectors (gitignored) |

Regenerate deterministically with
`python scripts/close_stage7c1_after_adjudication.py`. The closure semantic hash
covers every derived output and excludes wall-clock fields, so a re-run over
identical frozen inputs is provably identical.

## 9. Cost and storage for this closure

| Item | Value |
|---|---|
| Compiler / LLM calls | **0** |
| Model dollars | **$0.00** |
| Embedding calls | 22 (one batch, existing local provider, no API cost) |
| Final facet embeddings | 22 × dim 384 |
| Adjudication items closed | 68 |
| Cumulative Stage 7C.1 compiler cost | $0.018790 (unchanged — the 3 frozen runs) |

Owner adjudication effort is recorded as **measured by the owner**, not
estimated here.
