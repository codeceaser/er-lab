"""Stage 7A.1: embedding providers.

Exactly ONE real embedding model is configured -- local
sentence-transformers, no API key required -- never a provider/plugin
framework supporting swappable backends. A separate, deterministic FAKE
provider exists ONLY for the unit-test suite, so tests never need to
download or run the real model, and never depend on network access.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Protocol

from ingestion_bench.retrieval_baseline.config import EMBEDDING_MODEL


@dataclass(frozen=True)
class EmbeddingBatchResult:
    vectors: list[list[float]]
    elapsed_seconds: float
    # None means "no cost information available for this model" (e.g. a
    # local model with no per-token API charge) -- never fabricated as 0.0
    # when it is genuinely unknown, and never omitted when it IS known.
    cost_usd: float | None
    call_count: int


class EmbeddingProvider(Protocol):
    model_identity: str

    def embed(self, texts: list[str]) -> EmbeddingBatchResult: ...


class FakeEmbeddingProvider:
    """Deterministic, hash-based embedding -- the SAME text always
    produces the SAME vector, in this process or any other (no
    randomness, no model weights, no network, no filesystem access).
    Used ONLY by the unit-test suite."""

    model_identity = "fake-deterministic-sha256-v1"

    def __init__(self, dimension: int = 32) -> None:
        self.dimension = dimension

    def embed(self, texts: list[str]) -> EmbeddingBatchResult:
        start = time.perf_counter()
        vectors = [self._embed_one(t) for t in texts]
        return EmbeddingBatchResult(
            vectors=vectors, elapsed_seconds=time.perf_counter() - start, cost_usd=0.0, call_count=len(texts)
        )

    def _embed_one(self, text: str) -> list[float]:
        raw = text.encode("utf-8")
        values: list[float] = []
        counter = 0
        while len(values) < self.dimension:
            digest = hashlib.sha256(raw + counter.to_bytes(4, "big")).digest()
            for offset in range(0, len(digest), 4):
                if len(values) >= self.dimension:
                    break
                as_int = int.from_bytes(digest[offset : offset + 4], "big")
                values.append((as_int / 0xFFFFFFFF) * 2.0 - 1.0)
            counter += 1
        norm = sum(v * v for v in values) ** 0.5
        if norm == 0:
            return values
        return [v / norm for v in values]


class SentenceTransformerEmbeddingProvider:
    """The one REAL, configured embedding model. Loaded LAZILY (only on
    first `embed()` call, never at import/construction time), so merely
    importing or constructing this class never requires network access
    or a model download -- only actually using it does. Local model: no
    per-token API cost (`cost_usd` is always None, "where available")."""

    def __init__(self, model_name: str | None = None) -> None:
        self.model_identity = model_name or EMBEDDING_MODEL
        self._model = None

    def _ensure_loaded(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_identity)
        return self._model

    @property
    def dimension(self) -> int:
        model = self._ensure_loaded()
        if hasattr(model, "get_embedding_dimension"):
            return model.get_embedding_dimension()
        return model.get_sentence_embedding_dimension()  # older sentence-transformers versions

    def embed(self, texts: list[str]) -> EmbeddingBatchResult:
        model = self._ensure_loaded()
        start = time.perf_counter()
        vectors = model.encode(texts, normalize_embeddings=True)
        elapsed = time.perf_counter() - start
        return EmbeddingBatchResult(
            vectors=[v.tolist() for v in vectors], elapsed_seconds=elapsed, cost_usd=None, call_count=len(texts)
        )
