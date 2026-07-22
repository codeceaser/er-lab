"""Parser-adapter boundary: converts a source document into a validated
CanonicalDocument.

This package (and its subpackages, e.g. docling_standard/) is the ONLY
place any parser-specific library may be imported. ingestion_bench.canonical
and ingestion_bench.chunking must remain completely independent of every
adapter -- see base.py for the shared, parser-neutral interface every
adapter implements.
"""

from .base import AdapterConversionResult, AdapterDiagnostic, ConversionStatus, DocumentParserAdapter

__all__ = [
    "AdapterConversionResult",
    "AdapterDiagnostic",
    "ConversionStatus",
    "DocumentParserAdapter",
]
