"""Stage 7A.3: explicit-text-label status detection.

Literal, case-insensitive SUBSTRING matching only -- never inferred or
semantic classification (the demo spec's own requirement: "based only
on explicit text labels, not inferred classification"). A chunk's
retrieval_text either literally contains one of these words or it
doesn't; no model, no heuristic scoring, no synonym expansion.
"""

from __future__ import annotations

EXPLICIT_STATUS_LABELS: tuple[str, ...] = (
    "current",
    "retired",
    "historical",
    "superseded",
    "draft",
    "decommissioned",
)


def detect_explicit_status_labels(text: str) -> list[str]:
    """Returns the subset of EXPLICIT_STATUS_LABELS literally present in
    `text` (case-insensitive), in EXPLICIT_STATUS_LABELS' own fixed
    order -- deterministic, never dependent on where in the text a label
    appears."""
    lowered = text.lower()
    return [label for label in EXPLICIT_STATUS_LABELS if label in lowered]
