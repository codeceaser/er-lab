"""Derived annotations layered on top of the source-preserving core in
model.py. Every annotation carries derivation/extraction_method/confidence and
its own unit_index + bbox, so provenance is self-contained on the annotation
record itself.

Annotation is a Pydantic discriminated union keyed on annotation_type -- a raw
dict with the right annotation_type value is parsed into the correct concrete
subtype automatically, and an unrecognized annotation_type is rejected at
validation time.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .model import BoundingBox


class AnnotationBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    annotation_id: str
    target_ref: str
    unit_index: int = Field(ge=0)
    bbox: BoundingBox | None = None
    derivation: Literal["extracted", "model_derived"]
    extraction_method: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class IdentifierAnnotation(AnnotationBase):
    annotation_type: Literal["identifier"] = "identifier"
    raw_text: str
    normalized_value: str
    start_char: int | None = None
    end_char: int | None = None

    @model_validator(mode="after")
    def _validate_char_offsets(self) -> IdentifierAnnotation:
        # Half-open interval semantics, matching Python's own text[start:end]
        # slicing convention.
        if (self.start_char is None) != (self.end_char is None):
            raise ValueError("start_char and end_char must either both be None or both be populated")
        if self.start_char is not None and self.end_char is not None:
            if self.start_char < 0:
                raise ValueError(f"start_char must be >= 0, got {self.start_char}")
            if self.start_char > self.end_char:
                raise ValueError(f"start_char ({self.start_char}) must be <= end_char ({self.end_char})")
        return self


class OcrAnnotation(AnnotationBase):
    """Actual OCR-engine output only (e.g. RapidOCR / Docling's OCR
    pipeline) -- mechanical, character-level text recognition, hence always
    derivation="extracted" (no semantic/interpretive judgment involved).
    Never used for a multimodal model's own text reading -- see
    VisibleTextAnnotation for that."""

    annotation_type: Literal["ocr"] = "ocr"
    derivation: Literal["extracted"] = "extracted"
    text: str


class VisibleTextAnnotation(AnnotationBase):
    """A multimodal model's own transcription of text visible in an image --
    always derivation="model_derived". Never used for actual OCR-engine
    output -- see OcrAnnotation for that."""

    annotation_type: Literal["visible_text"] = "visible_text"
    derivation: Literal["model_derived"] = "model_derived"
    text: str


class PictureClassAnnotation(AnnotationBase):
    annotation_type: Literal["picture_class"] = "picture_class"
    picture_class: str


class VisualFactAnnotation(AnnotationBase):
    """Structured numeric/comparative/categorical fact recoverable from an
    image. subject/relation/[object|value+unit] can represent both an
    equality/measurement fact ("Q1 pass rate equals 82%") and a comparative
    fact ("Q4 pass rate is greater than Q1 pass rate") with one shape.
    Always derivation="model_derived" (requires a vision-capable model)."""

    annotation_type: Literal["visual_fact"] = "visual_fact"
    derivation: Literal["model_derived"] = "model_derived"
    fact_type: Literal["numeric", "comparative", "categorical", "other"]
    subject: str
    relation: str
    object: str | None = None
    value: float | str | None = None
    unit: str | None = None
    raw_text: str


class DiagramNodeAnnotation(AnnotationBase):
    """May be derivation="extracted" (native shape/connector structure, e.g.
    PPTX) or "model_derived" (a VisionEnricher reading a flat image) -- both
    are legitimate sources of diagram structure."""

    annotation_type: Literal["diagram_node"] = "diagram_node"
    node_id: str
    label: str
    node_bbox: BoundingBox | None = None


class DiagramEdgeAnnotation(AnnotationBase):
    """See DiagramNodeAnnotation -- either derivation value is legitimate."""

    annotation_type: Literal["diagram_edge"] = "diagram_edge"
    # Must resolve to a real DiagramNodeAnnotation.node_id in the same
    # CanonicalDocument -- validated by CanonicalDocument, not here, since
    # that requires seeing sibling annotations.
    source_node_id: str
    target_node_id: str
    label: str | None = None
    directed: bool = True


class ImageDescriptionAnnotation(AnnotationBase):
    """Free prose. Human-review only -- never deterministically scored.
    Always derivation="model_derived" (requires a vision-capable model)."""

    annotation_type: Literal["image_description"] = "image_description"
    derivation: Literal["model_derived"] = "model_derived"
    description: str


class UncertaintyAnnotation(AnnotationBase):
    annotation_type: Literal["uncertainty"] = "uncertainty"
    note: str


class SemanticClaimAnnotation(AnnotationBase):
    """Free-form higher-level assertion not covered by a more specific
    structured type above -- mainly for path C's document-level claims."""

    annotation_type: Literal["semantic_claim"] = "semantic_claim"
    claim: str


Annotation = Annotated[
    Union[
        IdentifierAnnotation,
        OcrAnnotation,
        VisibleTextAnnotation,
        PictureClassAnnotation,
        VisualFactAnnotation,
        DiagramNodeAnnotation,
        DiagramEdgeAnnotation,
        ImageDescriptionAnnotation,
        UncertaintyAnnotation,
        SemanticClaimAnnotation,
    ],
    Field(discriminator="annotation_type"),
]
