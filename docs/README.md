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

**Stage 4.2a complete** (commit `47fad5f` on `main`): canonical document
model, deterministic benchmark fixtures, and deterministic canonical
chunking are implemented and tested (256 tests passing). **Stage 5 (the
first parser adapter) has not started.** See `POC_STATUS_AND_EVIDENCE.md`
for the authoritative, up-to-date status.

## Repository root

`C:\Users\Admin\dev\er-lab` on the machine these documents were authored
on. Treat this as a local-development-environment detail only — do not
assume this path on another machine.

## Python / runtime assumptions

Python 3.13 in a local virtualenv (`.venv`). Dependencies: see
`requirements.txt` (loose pins) and `constraints.txt` (exact `pip freeze`
snapshot). `pytest.ini` sets `pythonpath = src fixtures`, so `pytest` runs
from the repository root need no extra path setup; running a one-off
script outside `pytest` requires `PYTHONPATH` to include both `src` and
`fixtures` (Windows path separator is `;`, not `:`).

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

This runs all four test files (`test_canonical_schema.py`,
`test_canonical_hashing.py`, `test_fixture_generation.py`,
`test_chunking.py`) — 256 tests as of Stage 4.2a. It does **not** exercise
any parser adapter, embedding, retrieval, or evaluator code, because none
of that exists yet.

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
