"""Public surface of the canonical document model.

Importing this package (rather than model.py or annotations.py directly) is
the safe way to get a fully-built CanonicalDocument: model.py declares its
`annotations` field as a forward reference to Annotation (defined in
annotations.py) specifically to avoid a circular import, since annotations.py
itself imports BoundingBox from model.py. This module imports both, then
resolves the forward reference with an explicit model_rebuild() call, once,
in a safe, deterministic order.
"""

from .annotations import (
    Annotation,
    AnnotationBase,
    DiagramEdgeAnnotation,
    DiagramNodeAnnotation,
    IdentifierAnnotation,
    ImageDescriptionAnnotation,
    OcrAnnotation,
    PictureClassAnnotation,
    SemanticClaimAnnotation,
    UncertaintyAnnotation,
    VisibleTextAnnotation,
    VisualFactAnnotation,
)
from .extraction_run import ExtractionRun, ModelArtifact, RemoteInferenceCall
from .hashing import compute_manifest_sha256, stable_canonical_hash, stable_element_id
from .model import (
    BoundingBox,
    CanonicalCaption,
    CanonicalDocument,
    CanonicalHeading,
    CanonicalListItem,
    CanonicalParagraph,
    CanonicalPicture,
    CanonicalTable,
    CanonicalTableCell,
    CanonicalUnit,
    NormalizedBoundingBox,
    ProvenanceEntry,
)

CanonicalDocument.model_rebuild(_types_namespace={"Annotation": Annotation})

__all__ = [
    "Annotation",
    "AnnotationBase",
    "DiagramEdgeAnnotation",
    "DiagramNodeAnnotation",
    "IdentifierAnnotation",
    "ImageDescriptionAnnotation",
    "OcrAnnotation",
    "PictureClassAnnotation",
    "SemanticClaimAnnotation",
    "UncertaintyAnnotation",
    "VisibleTextAnnotation",
    "VisualFactAnnotation",
    "ExtractionRun",
    "ModelArtifact",
    "RemoteInferenceCall",
    "compute_manifest_sha256",
    "stable_canonical_hash",
    "stable_element_id",
    "BoundingBox",
    "CanonicalCaption",
    "CanonicalDocument",
    "CanonicalHeading",
    "CanonicalListItem",
    "CanonicalParagraph",
    "CanonicalPicture",
    "CanonicalTable",
    "CanonicalTableCell",
    "CanonicalUnit",
    "NormalizedBoundingBox",
    "ProvenanceEntry",
]
