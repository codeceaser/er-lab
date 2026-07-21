"""Deterministic hashing: CanonicalDocument reproducibility comparisons, and
pinning an exact reference_manifest.json revision.

Both use the same canonical JSON serialization -- sorted keys, compact
separators, UTF-8 -- so the hash never varies with key ordering or
whitespace, whether across repeated runs or across machines.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .model import CanonicalDocument


def _canonical_json_bytes(data: dict[str, Any]) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def stable_canonical_hash(document: CanonicalDocument) -> str:
    """SHA-256 hex digest of a CanonicalDocument's stable content.

    Two runs of a deterministic parser over the same input must produce the
    same hash. CanonicalDocument never contains ExtractionRun fields (they
    live in a separate model entirely), so no additional exclusion is needed
    here beyond serializing the document as-is.
    """
    payload = document.model_dump(mode="json")
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def compute_manifest_sha256(manifest: dict[str, Any]) -> str:
    """SHA-256 hex digest of a reference_manifest.json's content.

    Defensively excludes any 'manifest_sha256' key from the input before
    hashing, so this can never be computed over itself even if a caller
    accidentally passes a dict that already contains one -- the frozen
    reference_manifest.json file does not embed its own hash.
    """
    payload = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def stable_element_id(
    doc_id: str,
    element_type: str,
    unit_index: int,
    order_index: int | None = None,
    discriminator: str | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """Deterministic id for a canonical element (block/table/picture/
    annotation/diagram node/...), derived only from stable identity
    components. Never uses Python's built-in hashing function (unstable
    across processes/runs) or a random UUID generator -- adapters must call
    this instead of generating their own ids.

    Stable input components:
      doc_id         -- which document this element belongs to
      element_type   -- e.g. "heading", "paragraph", "table", "picture",
                         "annotation:identifier", "diagram_node"
      unit_index     -- which page/slide it's on
      order_index    -- reading-order position, when applicable (None for
                         elements without one, e.g. a picture)
      discriminator  -- any additional string needed to disambiguate elements
                         that would otherwise share the same
                         (doc_id, element_type, unit_index, order_index)
                         tuple, e.g. an annotation's (target_ref,
                         extraction_method, occurrence_index)
      extra          -- additional identity components as a dict, for cases
                         the fixed parameters above don't cover; canonical
                         JSON serialization (sorted keys) means the dict's
                         insertion order never affects the result

    Two calls with identical inputs always produce identical ids; changing
    any identity component changes the id.
    """
    payload: dict[str, Any] = {
        "doc_id": doc_id,
        "element_type": element_type,
        "unit_index": unit_index,
        "order_index": order_index,
        "discriminator": discriminator,
        "extra": extra or {},
    }
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()
