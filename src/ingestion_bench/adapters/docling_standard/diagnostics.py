"""Deterministic diagnostic collection for the Docling-standard-local
adapter.

Every skipped Docling item, unsupported label, missing-provenance
element, malformed table cell, or use of a documented compatibility
fallback is recorded here -- never silently dropped. Depends only on
ingestion_bench.adapters.base (the parser-neutral AdapterDiagnostic
model), never on Docling types directly.
"""

from __future__ import annotations

from collections import Counter
from typing import Literal

from ingestion_bench.adapters.base import AdapterDiagnostic


class DiagnosticCollector:
    def __init__(self) -> None:
        self._diagnostics: list[AdapterDiagnostic] = []

    def record(
        self,
        category: str,
        message: str,
        *,
        severity: Literal["info", "warning", "error"] = "warning",
        docling_self_ref: str | None = None,
        unit_index: int | None = None,
        affects_fidelity: bool = False,
    ) -> None:
        self._diagnostics.append(AdapterDiagnostic(
            category=category, severity=severity, message=message,
            docling_self_ref=docling_self_ref, unit_index=unit_index,
            affects_fidelity=affects_fidelity,
        ))

    @property
    def diagnostics(self) -> list[AdapterDiagnostic]:
        return list(self._diagnostics)

    def count_by_category(self) -> dict[str, int]:
        return dict(Counter(d.category for d in self._diagnostics))

    def count_by_severity(self) -> dict[str, int]:
        return dict(Counter(d.severity for d in self._diagnostics))

    def has_errors(self) -> bool:
        return any(d.severity == "error" for d in self._diagnostics)

    def has_fidelity_impact(self) -> bool:
        """conversion_status derivation (Stage 5A.1) reads this, never
        severity -- a fidelity-affecting diagnostic can be "info" severity
        (e.g. DOCX pagination collapsing to one unit), and a high-severity
        diagnostic need not affect fidelity."""
        return any(d.affects_fidelity for d in self._diagnostics)

    def count_by_affects_fidelity(self) -> dict[str, int]:
        counts = Counter("fidelity_affecting" if d.affects_fidelity else "non_fidelity_affecting" for d in self._diagnostics)
        return dict(counts)
