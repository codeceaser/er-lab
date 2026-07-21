"""Deterministic image generation via Pillow.

Every image here is built from fixed coordinates and the frozen manifest's
own data -- no randomness, no LLM, no network. Re-running any function on the
same manifest content must produce byte-identical PNG bytes (see
test_fixture_generation.py's determinism tests).
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont

from manifest_schema import ReferenceManifest

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)


def _font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    # Pillow's bundled default font (no external .ttf dependency, so this is
    # reproducible across machines, not just across runs on this one).
    return ImageFont.load_default(size=size)


def _save_png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    # Fixed save options: no "optimize" pass (which can behave differently
    # across Pillow/zlib builds) and no metadata (no timestamp chunks are
    # added by default, but pnginfo is left explicitly unset to be sure).
    image.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


def _center_text(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, font, fill=BLACK) -> None:
    x0, y0, x1, y1 = box
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    cx = x0 + (x1 - x0 - text_w) / 2 - bbox[0]
    cy = y0 + (y1 - y0 - text_h) / 2 - bbox[1]
    draw.text((cx, cy), text, font=font, fill=fill)


def _draw_arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], width: int = 2) -> None:
    draw.line([start, end], fill=BLACK, width=width)
    x1, y1 = end
    # Fixed-size arrowhead, pointing in the (assumed horizontal) direction of travel.
    direction = 1 if x1 >= start[0] else -1
    head = [(x1, y1), (x1 - direction * 10, y1 - 6), (x1 - direction * 10, y1 + 6)]
    draw.polygon(head, fill=BLACK)


def generate_diagram_png(manifest: ReferenceManifest) -> bytes:
    """The parity suite's one shared image: a flow diagram with the exact
    nodes/edges declared in manifest.parity_suite.diagram_nodes/diagram_edges,
    at their declared bbox_px coordinates. Canvas 700x160, per the manifest's
    description_for_generator."""
    image = Image.new("RGB", (700, 160), WHITE)
    draw = ImageDraw.Draw(image)
    font = _font(14)

    nodes_by_id = {node.fact_id: node for node in manifest.parity_suite.diagram_nodes}

    for node in manifest.parity_suite.diagram_nodes:
        assert node.bbox_px is not None, f"diagram node {node.fact_id} has no bbox_px"
        x0, y0, x1, y1 = node.bbox_px
        draw.rectangle([x0, y0, x1, y1], outline=BLACK, width=2)
        _center_text(draw, (x0, y0, x1, y1), node.label, font)

    for edge in manifest.parity_suite.diagram_edges:
        source = nodes_by_id[edge.source]
        target = nodes_by_id[edge.target]
        sx0, sy0, sx1, sy1 = source.bbox_px
        tx0, ty0, tx1, ty1 = target.bbox_px
        start = (sx1, (sy0 + sy1) // 2)
        end = (tx0, (ty0 + ty1) // 2)
        _draw_arrow(draw, start, end)

    return _save_png_bytes(image)


def generate_chart_png(manifest: ReferenceManifest) -> bytes:
    """The chart_visual_stress fixture's bar chart: quarterly pass rates,
    drawn directly from manifest.stress_suite.chart_visual_stress.visual_facts
    (the fact_type == "numeric" entries)."""
    numeric_facts = [
        fact for fact in manifest.stress_suite.chart_visual_stress.visual_facts
        if fact.fact_type == "numeric"
    ]
    # Deterministic order: sort by subject, since that's the manifest's own
    # declared field (not insertion order of some other process).
    numeric_facts = sorted(numeric_facts, key=lambda fact: fact.subject)

    width, height = 500, 320
    margin_bottom = 50
    margin_top = 40
    plot_height = height - margin_top - margin_bottom
    bar_width = 60
    gap = 40
    left_margin = 50

    image = Image.new("RGB", (width, height), WHITE)
    draw = ImageDraw.Draw(image)
    title_font = _font(16)
    label_font = _font(14)

    draw.text((left_margin, 10), "Quarterly Recovery-Test Pass Rate", font=title_font, fill=BLACK)

    max_value = 100.0
    for index, fact in enumerate(numeric_facts):
        assert fact.value is not None
        x0 = left_margin + index * (bar_width + gap)
        x1 = x0 + bar_width
        bar_height = int(plot_height * (fact.value / max_value))
        y1 = height - margin_bottom
        y0 = y1 - bar_height
        draw.rectangle([x0, y0, x1, y1], fill=BLACK)

        value_label = f"{fact.value:g}{fact.unit or ''}"
        _center_text(draw, (x0, y0 - 20, x1, y0), value_label, label_font)

        quarter_label = fact.subject.split(" ")[0]  # "Q1 pass rate" -> "Q1"
        _center_text(draw, (x0, y1 + 5, x1, y1 + 25), quarter_label, label_font)

    return _save_png_bytes(image)


def generate_scanned_text_png(manifest: ReferenceManifest) -> bytes:
    """The scanned_pdf_ocr_stress fixture's source image: the manifest's
    expected_ocr_text rendered as pixels, with no underlying digital text --
    this PNG is later embedded into a PDF page with no drawString() calls at
    all, so the PDF itself has no text layer."""
    text = manifest.stress_suite.scanned_pdf_ocr_stress.expected_ocr_text

    width, height = 900, 120
    image = Image.new("RGB", (width, height), WHITE)
    draw = ImageDraw.Draw(image)
    font = _font(20)

    # Fixed, deterministic manual word-wrap at a fixed character budget --
    # no dynamic measurement-based wrapping, so line breaks never depend on
    # anything but the text itself.
    words = text.split(" ")
    lines: list[str] = []
    current: list[str] = []
    chars_per_line = 55
    for word in words:
        candidate = " ".join(current + [word])
        if len(candidate) > chars_per_line and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))

    y = 20
    for line in lines:
        draw.text((20, y), line, font=font, fill=BLACK)
        y += 30

    return _save_png_bytes(image)
