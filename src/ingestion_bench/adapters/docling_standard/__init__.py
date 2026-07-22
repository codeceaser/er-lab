"""DOCLING_STANDARD_LOCAL adapter (path A) -- Docling's standard local
pipeline only: no VLM, no picture description, no chart interpretation, no
remote services. See fixtures/BENCHMARK_CONTRACT.md section 1.
"""

from .adapter import DoclingStandardAdapter
from .config import build_converter, effective_configuration_summary
from .mapper import DocxPageFallback, DoclingToCanonicalMapper

__all__ = [
    "DoclingStandardAdapter",
    "build_converter",
    "effective_configuration_summary",
    "DocxPageFallback",
    "DoclingToCanonicalMapper",
]
