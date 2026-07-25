"""Stage 7A.1: environment-driven configuration.

Every credential-shaped or environment-specific value is read from an
environment variable, never hardcoded, and never written to any report
or artifact this package produces. This module never logs or serializes
the resolved values themselves (only field NAMES appear in error
messages).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[3]

# The one configured real embedding model (local sentence-transformers --
# no API key required, but still overridable via env, never hardcoded
# into calling code).
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_MODEL = os.environ.get("INGESTION_BENCH_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)

# The one configured real vector-store backend: Postgres + pgvector.
# Reuses the SAME DATABASE_URL variable name/convention as the existing
# ER GraphRAG POC's own .env (see src/config.py) -- but this package
# never imports that POC's code and writes only to its OWN table
# (INGESTION_BENCH_VECTOR_TABLE), never document_chunks/documents/kg_*.
# Never raises at import time: a missing DATABASE_URL only matters to
# the real pgvector store, never to the in-memory store the unit-test
# suite uses by default.
DATABASE_URL = os.environ.get("DATABASE_URL")
VECTOR_TABLE_NAME = os.environ.get("INGESTION_BENCH_VECTOR_TABLE", "ingestion_bench_stage7a_vectors")

CONTRACTS_ROOT = REPO_ROOT / "contracts"
CORPUS_PROFILES_PATH = CONTRACTS_ROOT / "corpus_profiles_v1.json"
RETRIEVAL_BENCHMARK_CONTRACT_PATH = CONTRACTS_ROOT / "retrieval_benchmark_v1.json"

ARTIFACTS_STAGE5A_ROOT = REPO_ROOT / "artifacts" / "stage5a"
ARTIFACTS_STAGE6A_ROOT = REPO_ROOT / "artifacts" / "stage6a"
EVIDENCE_ALIGNMENT_PATH = ARTIFACTS_STAGE6A_ROOT / "evidence_alignment.json"

ARTIFACTS_STAGE7A_ROOT = REPO_ROOT / "artifacts" / "stage7a"
REPORTS_ROOT = REPO_ROOT / "reports"

DEFAULT_TOP_KS: tuple[int, ...] = (1, 3, 5)
