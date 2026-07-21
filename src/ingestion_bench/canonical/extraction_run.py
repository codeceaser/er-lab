"""Volatile per-run extraction metadata.

Never part of CanonicalDocument and never included in stable_canonical_hash
(see hashing.py) -- run_id may be random precisely because ExtractionRun is
excluded from the stable hash entirely.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ModelArtifact(BaseModel):
    """Governance record for a LOCALLY invoked model artifact (e.g. Docling's
    own layout/TableFormer/picture-classifier/OCR models, or a future local
    Granite Vision path). Never used for remote API calls -- see
    RemoteInferenceCall for those."""

    model_repo_id: str
    revision: str
    file_hashes: dict[str, str] = Field(default_factory=dict)
    license: str
    local_artifact_path: str
    downloaded_size_bytes: int
    inference_runtime: str
    torch_dtype: str | None = None
    device: Literal["cpu", "cuda", "mps"]
    # Only meaningful for prompted/generative models (e.g. a local VLM);
    # None for non-generative models (layout, TableFormer, picture-classifier, OCR).
    prompt_version: str | None = None


class RemoteInferenceCall(BaseModel):
    """Audit record for a remote API call (OpenAI paths B and C). Never used
    for locally invoked models -- see ModelArtifact for those. Never contains
    the API key or any other secret."""

    provider: str
    model_id: str
    prompt_version: str | None = None
    request_id: str
    input_mode: str
    token_usage: dict | None = None
    elapsed_seconds: float


class ExtractionRun(BaseModel):
    run_id: str
    doc_id: str
    path_id: Literal["A", "B", "C", "D"]
    parser_name: str
    parser_version: str
    vision_enricher_name: str | None = None
    parser_config: dict = Field(default_factory=dict)
    generated_at: datetime
    elapsed_seconds: float
    warnings: list[str] = Field(default_factory=list)
    token_usage: dict | None = None
    # Absolute, machine-specific paths live here, never on CanonicalDocument.
    raw_artifact_refs: list[str] = Field(default_factory=list)
    canonical_document_hash: str
    model_artifacts: list[ModelArtifact] = Field(default_factory=list)
    remote_inference_calls: list[RemoteInferenceCall] = Field(default_factory=list)
