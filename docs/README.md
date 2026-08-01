# Documentation Index — Enterprise Document-Ingestion Benchmark POC

## POC purpose

This POC exists to prove whether Docling and/or OpenAI vendor-native
document understanding can faithfully populate a **canonical,
parser-agnostic document model** from synthetic DOCX/PDF/PPTX fixtures,
scored objectively against a frozen, human-authored ground-truth manifest
— upstream of, and independent from, retrieval. It is a separate effort
from the ER GraphRAG POC also in this repository (see root `README.md`);
the two are not wired together.

## Current stage

**Stage 6A / 6A.1 / 6A.2 / 6A.2a / 6A.2b is complete and FROZEN**
(`EVALUATOR_VERSION` `1.2.1`; see `git log` for the exact commit). Stage
5A/5A.1/5A.2 (Docling `DOCLING_STANDARD_LOCAL` adapter, path A) remain
**complete and frozen**: all 9 generated fixtures convert to a valid
`CanonicalDocument` (7 `success`, 2 `partial` — the two DOCX fixtures)
and chunk through the unmodified frozen chunker, with truthful
`conversion_status` validation, component-level determinism evidence, and
generated (not hand-typed) environment/model-footprint evidence.
**Stage 6A/6A.1/6A.2/6A.2a/6A.2b — the deterministic ingestion-fidelity
evaluator — scores that output against the frozen
`reference_manifest.json`**: 9/9 fixtures scored, 56 classified misses,
147 gold evidence-alignment entries, matched/partial/missing/not_applicable
(`artifacts/stage6a/evidence_alignment.json`). The 6A.1 hardening patch
made identifier occurrence recall one-to-one (never globally counted-and-
capped), made the evidence catalog complete (not matched-only), corrected
parser-vs-mapper attribution to require explicit raw relationship
evidence, made the miss ledger exhaustive, and added input-bundle
traceability. The 6A.2 patch scoped identifier-occurrence miss
ATTRIBUTION to each occurrence's own expected context (fixing a real
DOCX/PPTX `mapper_loss` misclassification), made unsupported-visual-claim
absence scored per claim, enforced supporting-miss referential integrity,
and added a separate `evaluation_content_hash` result identity plus
strengthened hash-field validation throughout. The 6A.2a patch fixed a
real bug where the chart-fact catalog builder silently truncated the
structured fields the 6A.2 per-claim matcher depended on, and added a
real-manifest integration test proving it. The 6A.2b patch made every
persisted output collection deterministic across processes (sorted
identifier iteration, canonically-ordered `unexpected_observations`),
verified by real `PYTHONHASHSEED` subprocess tests — none of these
sub-stages changed a single match/miss outcome from Stage 6A.1's baseline
except the one `mapper_loss` -> `parser_content_loss` reclassification at
6A.2. See `reports/stage6a_docling_baseline_scorecard.md` for the real,
measured results and `POC_STATUS_AND_EVIDENCE.md` "Stage 6A.2b findings"
for their interpretation, including the old-vs-new comparisons.

**Stage 6B — the minimal retrieval benchmark contract — is complete**:
exactly 12 frozen questions (`contracts/retrieval_benchmark_v1.json`;
4 direct, 3 distractor_sensitive, 2 relational, 2 multi_hop, 1
consolidation), every required/forbidden fact id verified real against
the Stage 6A catalog, plus a single-fixture fact-to-chunk resolver
(`src/ingestion_bench/retrieval_benchmark/`).

**Stage 7A.1 — the regular vector retrieval baseline — is complete and
FROZEN** (indexing/retrieval/metrics code must not change for Stage
7A.2's answer-generation layer to build on top of it):
local `sentence-transformers/all-MiniLM-L6-v2` embeddings, a REAL
Postgres/pgvector index (its own isolated table, never the separate ER
GraphRAG POC's tables), 4 corpus profiles
(`contracts/corpus_profiles_v1.json`), a new corpus-level gold resolver
scoped by fixture+fact_id+chunk_id, and deterministic K=1/3/5 retrieval
metrics that exclude ingestion-side gaps from ever being scored as a
retrieval failure (`src/ingestion_bench/retrieval_baseline/`). Real
measured baseline against the `baseline_demo` corpus: mean required-fact
coverage 83.3%/95.8%/95.8% at K=1/3/5, mean reciprocal rank 0.944. See
`reports/stage7a_vector_retrieval_scorecard.md` for the full scorecard
and `POC_STATUS_AND_EVIDENCE.md` "Stage 7A.1 findings" for two genuine
measured findings (a chunk-granularity-driven forbidden-fact hit rate,
and a narrative-vs-table chunk split on the consolidation question).

**547 tests passing** (3 pre-existing warnings from Docling's own
dependencies).

**Next: Stage 7B — graph-enriched RAG projection**, scored against the
SAME frozen Stage 6B benchmark contract Stage 7A.1 used, so results are
directly comparable. See `POC_STATUS_AND_EVIDENCE.md` "Benchmark
dimensions (corrected roadmap)" for the full corrected stage sequence
(Stage 6A/6A.1/6A.2/6A.2a/6A.2b done → Stage 6B done → Stage 7A.1 done →
Stage 7B next → Stage 7C wiki projection → Stages 8A/8B vision
enrichment/OpenAI vendor-native → Stage 9 cross-lane comparison) and why
vision enrichment moved later (decision D-040).

## Repository root

`C:\Users\Admin\dev\er-lab` on the machine these documents were authored
on. Treat this as a local-development-environment detail only — do not
assume this path on another machine.

## Python / runtime assumptions

Python 3.13 in a local virtualenv (`.venv`). Dependencies: see
`requirements.txt` (loose pins) and `constraints.txt` (exact `pip freeze`
snapshot) — includes `docling==2.114.0` and `onnxruntime` as of Stage 5A.
`pytest.ini` sets `pythonpath = src fixtures`, so `pytest` runs from the
repository root need no extra path setup; running a one-off script outside
`pytest` requires `PYTHONPATH` to include both `src` and `fixtures`
(Windows path separator is `;`, not `:`).

Stage 5A's tests run real (small, CPU-only) Docling conversions. If disk
space on the system drive is tight, set `HF_HOME`/`HF_HUB_CACHE` to a
different drive before the first run to redirect Docling's one-time
~505MB model download (this repository used `D:\ai-models\huggingface`)
— see `reports/stage5a_docling_standard_baseline.md` section 1.

## How to run the complete test suite

From the repository root, with the virtualenv active:

```
pytest
```

or, explicit interpreter path (as used throughout this project's own
stage reports):

```
.venv/Scripts/python.exe -m pytest -v
```

This runs all twenty-six test files (`test_canonical_schema.py`,
`test_canonical_hashing.py`, `test_fixture_generation.py`,
`test_chunking.py`, `test_docling_standard_mapper.py`,
`test_docling_standard_adapter.py`, `test_docling_standard_integration.py`,
`test_adapters_base.py`, `test_run_docling_standard_report.py`,
`test_evaluation_models.py`, `test_evaluation_normalization.py`,
`test_evaluation_matcher.py`, `test_evaluation_aggregation.py`,
`test_evaluation_identifier_occurrence.py`, `test_evaluation_table_matching.py`,
`test_evaluation_visual_claims.py`, `test_evaluation_determinism_subprocess.py`,
`test_stage6a_integration.py`, `test_stage6a_report_generation.py`,
`test_retrieval_benchmark_contract.py`, `test_retrieval_baseline_corpus.py`,
`test_retrieval_baseline_indexing.py`, `test_retrieval_baseline_retrieval.py`,
`test_retrieval_baseline_gold.py`, `test_retrieval_baseline_metrics.py`,
`test_retrieval_baseline_integration.py`) — 547 tests as of Stage 7A.1 (3
pre-existing warnings from Docling's own dependencies, not this project's
code). The three `test_docling_standard_*` files run the real Docling
adapter (not mocked) against the generated fixtures; the
`test_evaluation_*`/`test_stage6a_*` files run the real, frozen Stage
6A.2b evaluator against real Stage 5A output; the `test_retrieval_*`
files run the real, frozen Stage 6B benchmark contract and the real
Stage 7A.1 retrieval baseline (real sentence-transformers embeddings,
real Postgres/pgvector for one test, otherwise deterministic fake
embeddings/an in-memory vector store) against real Stage 5A/6A
artifacts. It does **not** exercise answer generation, Graph RAG, wiki
generation, or vision enrichment, because none of that exists yet
(Stage 7B onward).

To reproduce the Stage 5A baseline conversion of every fixture (not just
run the test suite): `python scripts/run_docling_standard.py` — writes
`artifacts/stage5a/` (gitignored, regenerable) and
`reports/stage5a_docling_standard_results.json`. To then score that
output against the manifest: `python scripts/run_stage6a_evaluation.py`
— writes `artifacts/stage6a/` (gitignored, regenerable),
`reports/stage6a_docling_baseline_scorecard.md`,
`reports/stage6a_docling_baseline_results.json`, and
`reports/stage6a_docling_miss_ledger.json`. To then build the Stage
7A.1 vector indexes and run the frozen Stage 6B benchmark against them:
`python scripts/run_stage7a_retrieval_baseline.py` — requires a
reachable `DATABASE_URL` (Postgres + pgvector; the real, configured
vector store) and writes `artifacts/stage7a/` (gitignored, regenerable),
`reports/stage7a_vector_retrieval_scorecard.md`, and
`reports/stage7a_vector_retrieval_results.json`.

Regenerating the benchmark fixtures (`fixtures/generated/` is gitignored,
not committed) requires running the generator directly, e.g.:

```
.venv/Scripts/python.exe fixtures/generate_fixtures.py
```

## Warning: reference_manifest.json is benchmark ground truth, not production document metadata

`fixtures/reference_manifest.json` is a synthetic, hand-authored answer
key for this benchmark's own fixtures. It is **not** an input to any
parser, it is **not** required for or present alongside any real
production document, and it is **not** part of `CanonicalDocument`'s
identity or hash. See `POC_ARCHITECTURE.md` section C for the full
architectural rule.

## Documents in this folder

| Document | Purpose |
|---|---|
| `POC_ARCHITECTURE.md` | The intended end-to-end architecture, its component boundaries, and what is implemented vs. planned. Read this first. |
| `IMPLEMENTATION_WALKTHROUGH.md` | Stage-by-stage walkthrough of what has actually been implemented, with source paths, symbols, invariants, tests, and one real worked example. |
| `POC_DECISION_LOG.md` | Durable, sequential (`D-001`, `D-002`, ...) record of why each significant architectural decision was made, including alternatives considered and reconsideration triggers. Never silently rewritten — superseded entries are marked, not deleted. |
| `POC_STATUS_AND_EVIDENCE.md` | Current, accurate implementation status per stage, test evidence, what the tests do and do not prove, and explicitly deferred scope. Updated at the end of every stage. |
| `DEVIN_HANDOFF_SEED.md` | Concise, validated-only seed for reproducing this implementation elsewhere — module boundaries, contracts, stage order, acceptance tests, constraints, and which decisions must not be reopened. Not a final handoff prompt by itself. |

## Recommended reading order

1. `POC_ARCHITECTURE.md`
2. `IMPLEMENTATION_WALKTHROUGH.md`
3. `POC_DECISION_LOG.md`
4. `POC_STATUS_AND_EVIDENCE.md`
5. `DEVIN_HANDOFF_SEED.md`

## Maintenance rules

After every subsequent implementation stage:

1. Update `POC_STATUS_AND_EVIDENCE.md`.
2. Add or revise relevant `POC_DECISION_LOG.md` entries (new sequential
   IDs; never renumber).
3. Extend `IMPLEMENTATION_WALKTHROUGH.md` with the actual new code.
4. Update `POC_ARCHITECTURE.md` only if a boundary genuinely changes.
5. Update `DEVIN_HANDOFF_SEED.md` only with validated conclusions.
6. Never rewrite a historical **Accepted** decision without marking the
   old entry **Superseded** and linking the replacement decision.
