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

**Stage 5A.2 complete and frozen** (committed — see `git log` for the
exact commit): canonical document model, deterministic benchmark
fixtures, deterministic canonical chunking, and the Docling
`DOCLING_STANDARD_LOCAL` parser adapter (path A) are implemented,
hardened, and tested (350 tests passing, 3 pre-existing warnings from
Docling's own dependencies). All 9 generated fixtures convert to a valid
`CanonicalDocument` through real Docling (7 `success`, 2 `partial` — the
two DOCX fixtures, since Docling exposes no DOCX pagination geometry) and
chunk through the unmodified frozen chunker. The frozen baseline now
includes: truthful `conversion_status` validation (a `"success"` result
cannot carry a fidelity-affecting diagnostic), fidelity-impact diagnostics
independent of severity, DOCX valid-but-`partial` status, OCR annotation
provenance, complete portable diagnostics, component-level determinism
evidence (five independent comparisons, not one collapsed hash), and
generated (not hand-typed) environment/model-footprint evidence — all
baseline Markdown/JSON generated from one execution.

**Next: Stage 6A — the deterministic ingestion-fidelity evaluator**, not
vision enrichment. See `POC_STATUS_AND_EVIDENCE.md` "Benchmark dimensions
(corrected roadmap)" for the full corrected stage sequence (Stage 6A
evaluator → Stage 6B retrieval benchmark contract → Stages 7A/7B/7C
vector/graph/wiki projections → Stages 8A/8B vision enrichment/OpenAI
vendor-native → Stage 9 cross-lane comparison) and why vision enrichment
moved later (decision D-040).

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

This runs all nine test files (`test_canonical_schema.py`,
`test_canonical_hashing.py`, `test_fixture_generation.py`,
`test_chunking.py`, `test_docling_standard_mapper.py`,
`test_docling_standard_adapter.py`, `test_docling_standard_integration.py`,
`test_adapters_base.py`, `test_run_docling_standard_report.py`) — 350
tests as of Stage 5A.2 (3 pre-existing warnings from Docling's own
dependencies, not this project's code). The three `test_docling_standard_*`
files run the real Docling adapter (not mocked) against the generated
fixtures. It does **not** exercise embedding, retrieval, or evaluator
code, because none of that exists yet (the evaluator is Stage 6A, next).

To reproduce the Stage 5A baseline conversion of every fixture (not just
run the test suite): `python scripts/run_docling_standard.py` — writes
`artifacts/stage5a/` (gitignored, regenerable) and
`reports/stage5a_docling_standard_results.json`.

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
