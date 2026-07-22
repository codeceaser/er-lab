"""Explicit DOCLING_STANDARD_LOCAL pipeline configuration (path A).

This is the only module that decides Docling pipeline options. Every
option here is set explicitly -- nothing is left to an implicit library
default that could silently change behavior on a Docling upgrade.

Deliberately OFF, matching the Stage 5A scope gate:
  - do_picture_classification (no picture-class model)
  - do_picture_description     (no VLM captioning)
  - do_chart_extraction        (no chart-to-numeric-fact interpretation)
  - do_code_enrichment / do_formula_enrichment
  - enable_remote_services      (no network calls of any kind)
  - allow_external_plugins

Deliberately ON:
  - do_ocr (RapidOcrOptions explicitly, not "auto" -- see module docstring
    note below on why "auto" was rejected)
  - do_table_structure (TableFormerMode.ACCURATE)
  - generate_picture_images (needed to extract picture bytes for
    CanonicalPicture.content_sha256/artifact_ref)

RapidOcrOptions was chosen explicitly over OcrOptions/OcrAutoOptions
(Docling 2.114.0's own default): OcrAutoOptions resolves to whichever OCR
engine happens to be importable at runtime, which is itself a form of
environment-dependent nondeterminism this project avoids everywhere else
(see docs/POC_DECISION_LOG.md D-010). RapidOcrOptions is explicit and
matches what is actually installed (onnxruntime backend; easyocr/
tesseract are not installed dependencies of this project).
"""

from __future__ import annotations

import importlib.metadata

from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions, TableFormerMode
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline

ALLOWED_FORMATS: tuple[InputFormat, ...] = (InputFormat.PDF, InputFormat.DOCX, InputFormat.PPTX)


def docling_version() -> str:
    return importlib.metadata.version("docling")


def docling_core_version() -> str:
    return importlib.metadata.version("docling-core")


def build_pdf_pipeline_options() -> PdfPipelineOptions:
    options = PdfPipelineOptions()
    options.do_ocr = True
    options.ocr_options = RapidOcrOptions()
    options.do_table_structure = True
    options.table_structure_options.mode = TableFormerMode.ACCURATE
    options.generate_page_images = False
    options.generate_picture_images = True
    options.do_picture_classification = False
    options.do_picture_description = False
    options.do_chart_extraction = False
    options.do_code_enrichment = False
    options.do_formula_enrichment = False
    options.enable_remote_services = False
    options.allow_external_plugins = False
    options.accelerator_options = AcceleratorOptions(device=AcceleratorDevice.CPU)
    return options


def build_converter() -> DocumentConverter:
    """One DocumentConverter, meant to be built ONCE and reused across every
    fixture in a batch run -- Docling's own models load lazily on first use
    and are cached on the converter/pipeline instance, so reusing one
    instance avoids reloading model weights per file."""
    pdf_options = build_pdf_pipeline_options()
    return DocumentConverter(
        allowed_formats=list(ALLOWED_FORMATS),
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_options, pipeline_cls=StandardPdfPipeline),
        },
    )


def effective_configuration_summary() -> dict:
    """A plain-dict summary of the effective pipeline configuration, for
    the conversion/baseline report -- not used for conversion itself."""
    pdf_options = build_pdf_pipeline_options()
    return {
        "allowed_formats": [f.value for f in ALLOWED_FORMATS],
        "docling_version": docling_version(),
        "docling_core_version": docling_core_version(),
        "do_ocr": pdf_options.do_ocr,
        "ocr_backend": type(pdf_options.ocr_options).__name__,
        "table_mode": pdf_options.table_structure_options.mode.value,
        "do_table_structure": pdf_options.do_table_structure,
        "generate_picture_images": pdf_options.generate_picture_images,
        "generate_page_images": pdf_options.generate_page_images,
        "do_picture_classification": pdf_options.do_picture_classification,
        "do_picture_description": pdf_options.do_picture_description,
        "do_chart_extraction": pdf_options.do_chart_extraction,
        "enable_remote_services": pdf_options.enable_remote_services,
        "accelerator_device": pdf_options.accelerator_options.device,
    }
