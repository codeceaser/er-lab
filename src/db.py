"""Database access helpers: SQLAlchemy engine, connections, and embedding utilities.

All scripts in this project are run directly (e.g. `python src/create_schema.py`),
so imports here are bare module names rather than a `src.` package prefix.
"""

from contextlib import contextmanager
from functools import lru_cache

from sentence_transformers import SentenceTransformer
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from config import DATABASE_URL, EMBEDDING_MODEL_NAME

_engine: Engine | None = None


def get_engine() -> Engine:
    """Return a lazily-created, process-wide SQLAlchemy engine."""
    global _engine
    if _engine is None:
        _engine = create_engine(DATABASE_URL, future=True)
    return _engine


@contextmanager
def get_connection():
    """Yield a SQLAlchemy connection. Caller is responsible for commit/rollback."""
    engine = get_engine()
    with engine.connect() as conn:
        yield conn


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    """Load (once) and cache the sentence-transformers embedding model."""
    return SentenceTransformer(EMBEDDING_MODEL_NAME)


def embed_text(text: str) -> list[float]:
    """Embed a single string into a normalized 384-dim vector."""
    model = get_embedding_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


def to_vector_literal(embedding: list[float]) -> str:
    """Format a Python list of floats as a pgvector literal, e.g. '[0.1,0.2,...]'."""
    return "[" + ",".join(f"{value:.8f}" for value in embedding) + "]"
