"""Stage 7R.1: environment-driven configuration.

Every credential-shaped or environment-specific value is read from an
environment variable, never hardcoded, and never written to any report
or artifact this package produces. Reuses the SAME `DATABASE_URL`
variable name/convention as `retrieval_baseline/config.py` (and, before
that, the original ER GraphRAG POC's own `.env`) -- but this package
never imports that POC's code, and writes only to its OWN two tables
(`edib_document_revision_registry`, `edib_authority_decision_event`),
never `document_chunks`/`documents`/`kg_*` or `ingestion_bench_stage7a_*`.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[3]

DATABASE_URL = os.environ.get("DATABASE_URL")

REVISION_REGISTRY_TABLE = os.environ.get(
    "INGESTION_BENCH_REVISION_REGISTRY_TABLE", "edib_document_revision_registry"
)
AUTHORITY_PERIOD_TABLE = os.environ.get(
    "INGESTION_BENCH_AUTHORITY_PERIOD_TABLE", "edib_revision_authority_period"
)
AUTHORITY_EVENT_TABLE = os.environ.get(
    "INGESTION_BENCH_AUTHORITY_EVENT_TABLE", "edib_authority_decision_event"
)

CONTRACTS_ROOT = REPO_ROOT / "contracts"
REVISION_AUTHORITY_SCENARIOS_CONTRACT_PATH = CONTRACTS_ROOT / "revision_authority_scenarios_v2.json"

REPORTS_ROOT = REPO_ROOT / "reports"
