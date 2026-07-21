"""Central configuration loaded from environment variables (.env)."""

import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Copy .env.example to .env and adjust it."
    )

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

# Retrieval defaults
VECTOR_TOP_K = 5
GRAPH_ARTIFACT_TOP_K = 5
GRAPH_EXPANSION_MAX_DEPTH = 4
