"""Canonical, parser-agnostic document model.

Stable content only: no run/extraction metadata (see extraction_run.py) and no
derived/model-generated content beyond bare structural facts (see
annotations.py, imported here only as a forward reference -- see
canonical/__init__.py for how the reference is resolved without a circular
import).
"""

from __future__ import annotations

import math
import re
from pathlib import PurePosixPath, PureWindowsPath
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


def validate_sha256_hex(value: str, field_name: str) -> str:
    """Shared validator: lowercase 64-character hexadecimal SHA-256 string.
    Reused by benchmark_binding.BenchmarkBinding as well as the fields here."""
    if not SHA256_HEX_RE.match(value):
        raise ValueError(
            f"{field_name} must be a lowercase 64-character hexadecimal SHA-256 string: {value!r}"
        )
    return value


class NormalizedBoundingBox(BaseModel):
    nx0: float = Field(ge=0.0, le=1.0)
    ny0: float = Field(ge=0.0, le=1.0)
    nx1: float = Field(ge=0.0, le=1.0)
    ny1: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_ordering(self) -> NormalizedBoundingBox:
        if self.nx1 < self.nx0:
            raise ValueError(f"nx1 ({self.nx1}) must be >= nx0 ({self.nx0})")
        if self.ny1 < self.ny0:
            raise ValueError(f"ny1 ({self.ny1}) must be >= ny0 ({self.ny0})")
        return self


class BoundingBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float
    coordinate_unit: Literal["pt", "px", "emu"]
    coordinate_origin: Literal["top-left", "bottom-left"]
    rotation: float = 0.0
    normalized: NormalizedBoundingBox | None = None

    @model_validator(mode="after")
    def _validate_geometry(self) -> BoundingBox:
        for name, value in (("x0", self.x0), ("y0", self.y0), ("x1", self.x1), ("y1", self.y1), ("rotation", self.rotation)):
            if not math.isfinite(value):
                raise ValueError(f"BoundingBox.{name} must be a finite number, got {value!r}")
        if self.x1 < self.x0:
            raise ValueError(f"x1 ({self.x1}) must be >= x0 ({self.x0})")
        if self.y1 < self.y0:
            raise ValueError(f"y1 ({self.y1}) must be >= y0 ({self.y0})")
        return self


class CanonicalUnit(BaseModel):
    unit_index: int = Field(ge=0)
    unit_type: Literal["page", "slide"]
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    rotation: float = 0.0
    coordinate_unit: Literal["pt", "px", "emu"]
    coordinate_origin: Literal["top-left", "bottom-left"]


class CanonicalHeading(BaseModel):
    block_id: str
    unit_index: int
    order_index: int = Field(ge=0)
    text: str
    bbox: BoundingBox | None = None
    level: int = Field(ge=1)


class CanonicalParagraph(BaseModel):
    block_id: str
    unit_index: int
    order_index: int = Field(ge=0)
    text: str
    bbox: BoundingBox | None = None


class CanonicalListItem(BaseModel):
    block_id: str
    unit_index: int
    order_index: int = Field(ge=0)
    text: str
    bbox: BoundingBox | None = None
    list_id: str
    indent_level: int = Field(ge=0)
    parent_block_id: str | None = None


class CanonicalCaption(BaseModel):
    block_id: str
    unit_index: int
    order_index: int = Field(ge=0)
    text: str
    bbox: BoundingBox | None = None
    target_picture_id: str


class CanonicalTableCell(BaseModel):
    row: int = Field(ge=0)
    col: int = Field(ge=0)
    row_span: int = Field(default=1, ge=1)
    col_span: int = Field(default=1, ge=1)
    text: str
    is_header: bool = False


class CanonicalTable(BaseModel):
    table_id: str
    unit_index: int
    order_index: int = Field(ge=0)
    bbox: BoundingBox | None = None
    n_rows: int = Field(gt=0)
    n_cols: int = Field(gt=0)
    cells: list[CanonicalTableCell] = Field(default_factory=list)


def _validate_portable_relative_path(value: str, field_name: str) -> str:
    """Shared rule for source_relative_path and artifact_ref: relative,
    POSIX-style, no backslashes, no '..' traversal, nonempty."""
    if not value:
        raise ValueError(f"{field_name} must not be empty")
    if "\\" in value:
        raise ValueError(
            f"{field_name} must use normalized POSIX-style separators ('/'), not backslashes: {value!r}"
        )
    if PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute():
        raise ValueError(f"{field_name} must be a relative, portable reference, not an absolute path: {value!r}")
    if ".." in PurePosixPath(value).parts:
        raise ValueError(f"{field_name} must not contain '..' path traversal components: {value!r}")
    return value


class CanonicalPicture(BaseModel):
    picture_id: str
    unit_index: int
    bbox: BoundingBox | None = None
    content_sha256: str
    # Portable reference only -- never an absolute path, and never a run_id
    # (guaranteed structurally: no field on this model or on CanonicalDocument
    # ever carries a run_id, so one cannot leak into artifact_ref even by
    # accident). Absolute, run-specific paths belong on
    # ExtractionRun.raw_artifact_refs instead.
    artifact_ref: str

    @field_validator("content_sha256")
    @classmethod
    def _content_sha256_is_valid(cls, v: str) -> str:
        return validate_sha256_hex(v, "content_sha256")

    @field_validator("artifact_ref")
    @classmethod
    def _artifact_ref_is_portable(cls, v: str) -> str:
        return _validate_portable_relative_path(v, "artifact_ref")


class ProvenanceEntry(BaseModel):
    element_id: str
    unit_index: int
    order_index: int | None = Field(default=None, ge=0)
    bbox: BoundingBox | None = None
    z_order: int | None = None
    source_element_ref: str | None = None
    source_locator: dict | None = None


class CanonicalDocument(BaseModel):
    doc_id: str
    source_format: Literal["docx", "pdf", "pptx"]
    source_filename: str
    # Portable, POSIX-style, relative path -- never an absolute filesystem
    # path. Absolute paths belong on ExtractionRun.raw_artifact_refs instead,
    # since CanonicalDocument must be reproducible/comparable regardless of
    # which machine or directory it was processed on.
    source_relative_path: str
    source_sha256: str
    # Deliberately NOT here: manifest_version / manifest_sha256. CanonicalDocument
    # says what was extracted -- it must never know which manifest (if any) it is
    # being evaluated against, and stable_canonical_hash() must never depend on
    # benchmark metadata. See benchmark_binding.BenchmarkBinding for the explicit,
    # separate link between a canonical document's hash and a manifest version.
    units: list[CanonicalUnit] = Field(default_factory=list)
    headings: list[CanonicalHeading] = Field(default_factory=list)
    paragraphs: list[CanonicalParagraph] = Field(default_factory=list)
    list_items: list[CanonicalListItem] = Field(default_factory=list)
    captions: list[CanonicalCaption] = Field(default_factory=list)
    tables: list[CanonicalTable] = Field(default_factory=list)
    pictures: list[CanonicalPicture] = Field(default_factory=list)
    # "Annotation" is a forward reference resolved by canonical/__init__.py's
    # explicit model_rebuild() call, not imported here, to avoid a circular
    # import (annotations.py imports BoundingBox from this module).
    annotations: list[Annotation] = Field(default_factory=list)
    provenance: list[ProvenanceEntry] = Field(default_factory=list)

    @field_validator("source_sha256")
    @classmethod
    def _source_sha256_is_valid(cls, v: str) -> str:
        return validate_sha256_hex(v, "source_sha256")

    @field_validator("source_filename")
    @classmethod
    def _source_filename_is_basename(cls, v: str) -> str:
        if not v:
            raise ValueError("source_filename must not be empty")
        if "/" in v or "\\" in v:
            raise ValueError(f"source_filename must be a basename only, not a path: {v!r}")
        return v

    @field_validator("source_relative_path")
    @classmethod
    def _source_relative_path_is_portable(cls, v: str) -> str:
        return _validate_portable_relative_path(v, "source_relative_path")

    @model_validator(mode="after")
    def _validate_unique_unit_indices(self) -> CanonicalDocument:
        seen: set[int] = set()
        for unit in self.units:
            if unit.unit_index in seen:
                raise ValueError(f"duplicate unit_index: {unit.unit_index}")
            seen.add(unit.unit_index)
        return self

    @model_validator(mode="after")
    def _validate_unit_references(self) -> CanonicalDocument:
        """Every element's unit_index must reference a real CanonicalUnit,
        whether or not that element has a bbox. (The bbox validator below only
        checks elements that HAVE a bbox -- this one closes that gap for
        elements without one, e.g. a paragraph with no bbox available.)"""
        valid_indices = {unit.unit_index for unit in self.units}

        def check(unit_index: int, where: str) -> None:
            if unit_index not in valid_indices:
                raise ValueError(f"{where}: unit_index {unit_index} has no matching CanonicalUnit")

        for heading in self.headings:
            check(heading.unit_index, f"heading {heading.block_id}")
        for paragraph in self.paragraphs:
            check(paragraph.unit_index, f"paragraph {paragraph.block_id}")
        for list_item in self.list_items:
            check(list_item.unit_index, f"list_item {list_item.block_id}")
        for caption in self.captions:
            check(caption.unit_index, f"caption {caption.block_id}")
        for table in self.tables:
            check(table.unit_index, f"table {table.table_id}")
        for picture in self.pictures:
            check(picture.unit_index, f"picture {picture.picture_id}")
        for annotation in self.annotations:
            check(annotation.unit_index, f"annotation {annotation.annotation_id}")
        for entry in self.provenance:
            check(entry.unit_index, f"provenance entry {entry.element_id}")

        return self

    @model_validator(mode="after")
    def _validate_caption_targets(self) -> CanonicalDocument:
        """CanonicalCaption.target_picture_id must resolve to a real
        CanonicalPicture.picture_id in this document."""
        picture_ids = {picture.picture_id for picture in self.pictures}
        for caption in self.captions:
            if caption.target_picture_id not in picture_ids:
                raise ValueError(
                    f"caption {caption.block_id}: target_picture_id={caption.target_picture_id!r} "
                    "does not resolve to any CanonicalPicture.picture_id in this document"
                )
        return self

    @model_validator(mode="after")
    def _validate_list_item_parents(self) -> CanonicalDocument:
        """CanonicalListItem.parent_block_id, when set, must resolve to
        another CanonicalListItem.block_id in this document."""
        list_item_ids = {list_item.block_id for list_item in self.list_items}
        for list_item in self.list_items:
            if list_item.parent_block_id is not None and list_item.parent_block_id not in list_item_ids:
                raise ValueError(
                    f"list_item {list_item.block_id}: parent_block_id={list_item.parent_block_id!r} "
                    "does not resolve to any CanonicalListItem.block_id in this document"
                )
        return self

    @model_validator(mode="after")
    def _validate_annotation_target_refs(self) -> CanonicalDocument:
        """Every Annotation.target_ref must resolve to a real block/table/
        picture id in this document -- an annotation must always be anchored
        to something that was actually extracted."""
        known_ids: set[str] = set()
        known_ids.update(heading.block_id for heading in self.headings)
        known_ids.update(paragraph.block_id for paragraph in self.paragraphs)
        known_ids.update(list_item.block_id for list_item in self.list_items)
        known_ids.update(caption.block_id for caption in self.captions)
        known_ids.update(table.table_id for table in self.tables)
        known_ids.update(picture.picture_id for picture in self.pictures)

        for annotation in self.annotations:
            if annotation.target_ref not in known_ids:
                raise ValueError(
                    f"annotation {annotation.annotation_id}: target_ref={annotation.target_ref!r} "
                    "does not resolve to any block/table/picture id in this document"
                )
        return self

    @model_validator(mode="after")
    def _validate_provenance_element_ids(self) -> CanonicalDocument:
        """ProvenanceEntry.element_id must resolve to an existing canonical
        element (block/table/picture) OR annotation id."""
        known_ids: set[str] = set()
        known_ids.update(heading.block_id for heading in self.headings)
        known_ids.update(paragraph.block_id for paragraph in self.paragraphs)
        known_ids.update(list_item.block_id for list_item in self.list_items)
        known_ids.update(caption.block_id for caption in self.captions)
        known_ids.update(table.table_id for table in self.tables)
        known_ids.update(picture.picture_id for picture in self.pictures)
        known_ids.update(annotation.annotation_id for annotation in self.annotations)

        for entry in self.provenance:
            if entry.element_id not in known_ids:
                raise ValueError(
                    f"provenance entry element_id={entry.element_id!r} does not resolve to any "
                    "canonical element or annotation id in this document"
                )
        return self

    @model_validator(mode="after")
    def _validate_table_cell_bounds(self) -> CanonicalDocument:
        """Every CanonicalTableCell must fit within its table's declared
        n_rows/n_cols, including any row_span/col_span."""
        for table in self.tables:
            for cell in table.cells:
                if not (0 <= cell.row < table.n_rows):
                    raise ValueError(
                        f"table {table.table_id}: cell row {cell.row} out of bounds for n_rows={table.n_rows}"
                    )
                if not (0 <= cell.col < table.n_cols):
                    raise ValueError(
                        f"table {table.table_id}: cell col {cell.col} out of bounds for n_cols={table.n_cols}"
                    )
                if cell.row + cell.row_span > table.n_rows:
                    raise ValueError(
                        f"table {table.table_id}: cell at row {cell.row} with row_span={cell.row_span} "
                        f"exceeds n_rows={table.n_rows}"
                    )
                if cell.col + cell.col_span > table.n_cols:
                    raise ValueError(
                        f"table {table.table_id}: cell at col {cell.col} with col_span={cell.col_span} "
                        f"exceeds n_cols={table.n_cols}"
                    )
        return self

    @model_validator(mode="after")
    def _validate_unique_ids(self) -> CanonicalDocument:
        """block_id, table_id, and picture_id share ONE global namespace,
        since Annotation.target_ref can reference any of them -- a block_id
        colliding with a picture_id would be just as broken as colliding with
        another block_id. annotation_id and diagram node_id are each their
        own separate namespace. All of these are supposed to be
        deterministically generated (never random), so any collision
        indicates an upstream adapter bug, not a legitimate document."""

        def check_unique(values: list[str], kind: str) -> None:
            seen: set[str] = set()
            for value in values:
                if value in seen:
                    raise ValueError(f"duplicate {kind} id: {value!r}")
                seen.add(value)

        core_element_ids = (
            [heading.block_id for heading in self.headings]
            + [paragraph.block_id for paragraph in self.paragraphs]
            + [list_item.block_id for list_item in self.list_items]
            + [caption.block_id for caption in self.captions]
            + [table.table_id for table in self.tables]
            + [picture.picture_id for picture in self.pictures]
        )
        check_unique(core_element_ids, "core element (block/table/picture)")
        check_unique([annotation.annotation_id for annotation in self.annotations], "annotation")
        check_unique(
            [
                annotation.node_id
                for annotation in self.annotations
                if getattr(annotation, "annotation_type", None) == "diagram_node"
            ],
            "diagram node",
        )
        return self

    @model_validator(mode="after")
    def _validate_bbox_coordinate_systems(self) -> CanonicalDocument:
        """Every element's bbox must use its owning CanonicalUnit's coordinate
        system. The model only validates this -- converting a bbox into the
        right coordinate system before construction is the adapter's job."""
        units_by_index = {unit.unit_index: unit for unit in self.units}

        def check(unit_index: int, bbox: BoundingBox | None, where: str) -> None:
            if bbox is None:
                return
            unit = units_by_index.get(unit_index)
            if unit is None:
                raise ValueError(f"{where}: unit_index {unit_index} has no matching CanonicalUnit")
            if bbox.coordinate_unit != unit.coordinate_unit:
                raise ValueError(
                    f"{where}: bbox.coordinate_unit={bbox.coordinate_unit!r} does not match "
                    f"owning CanonicalUnit(unit_index={unit_index}).coordinate_unit="
                    f"{unit.coordinate_unit!r}. The adapter must convert bounding boxes into "
                    "the owning unit's coordinate system before constructing CanonicalDocument."
                )
            if bbox.coordinate_origin != unit.coordinate_origin:
                raise ValueError(
                    f"{where}: bbox.coordinate_origin={bbox.coordinate_origin!r} does not match "
                    f"owning CanonicalUnit(unit_index={unit_index}).coordinate_origin="
                    f"{unit.coordinate_origin!r}."
                )

        for heading in self.headings:
            check(heading.unit_index, heading.bbox, f"heading {heading.block_id}")
        for paragraph in self.paragraphs:
            check(paragraph.unit_index, paragraph.bbox, f"paragraph {paragraph.block_id}")
        for list_item in self.list_items:
            check(list_item.unit_index, list_item.bbox, f"list_item {list_item.block_id}")
        for caption in self.captions:
            check(caption.unit_index, caption.bbox, f"caption {caption.block_id}")
        for table in self.tables:
            check(table.unit_index, table.bbox, f"table {table.table_id}")
        for picture in self.pictures:
            check(picture.unit_index, picture.bbox, f"picture {picture.picture_id}")
        for annotation in self.annotations:
            check(annotation.unit_index, annotation.bbox, f"annotation {annotation.annotation_id}")
            node_bbox = getattr(annotation, "node_bbox", None)
            if node_bbox is not None:
                check(annotation.unit_index, node_bbox, f"annotation {annotation.annotation_id} node_bbox")

        return self

    @model_validator(mode="after")
    def _validate_diagram_edge_node_references(self) -> CanonicalDocument:
        """DiagramEdgeAnnotation.source_node_id/target_node_id must resolve to
        a real DiagramNodeAnnotation.node_id in this same document."""
        node_ids = {
            annotation.node_id
            for annotation in self.annotations
            if getattr(annotation, "annotation_type", None) == "diagram_node"
        }
        for annotation in self.annotations:
            if getattr(annotation, "annotation_type", None) != "diagram_edge":
                continue
            for ref_name in ("source_node_id", "target_node_id"):
                node_id = getattr(annotation, ref_name)
                if node_id not in node_ids:
                    raise ValueError(
                        f"annotation {annotation.annotation_id}: {ref_name}={node_id!r} does not "
                        "resolve to any DiagramNodeAnnotation.node_id in this document"
                    )
        return self
