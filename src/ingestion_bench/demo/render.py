"""Stage 7A.3: static HTML rendering.

A single, self-contained page: inline CSS, and a tiny inline JS handler
that only TOGGLES element visibility (`style.display`) between
pre-rendered, server-escaped sections -- it never writes page content
via `innerHTML` or string concatenation from data, so there is no
client-side injection surface at all. Every text value derived from real
data is passed through `html.escape` before being placed in the page.
This module accepts only already-built `QuestionDemoView` objects
(view_model.py) -- never a raw string a caller could use to inject an
arbitrary chunk id or source reference.

One lightweight local UI approach consistent with this repository's own
conventions (plain Python string templates producing a static file,
exactly like `retrieval_baseline/report.py`'s Markdown rendering) -- no
enterprise UI framework, no build step, no server process required to
view it.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone

from ingestion_bench.demo.view_model import CitedChunkView, ClaimView, QuestionDemoView

_STATUS_BADGE_CLASS = {
    "current": "badge-current",
    "retired": "badge-retired",
    "historical": "badge-historical",
    "superseded": "badge-superseded",
    "draft": "badge-draft",
    "decommissioned": "badge-decommissioned",
}


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _render_status_badges(labels: list[str]) -> str:
    if not labels:
        return ""
    spans = "".join(
        f'<span class="badge {_STATUS_BADGE_CLASS.get(label, "badge-other")}">{_esc(label)}</span>' for label in labels
    )
    return f'<div class="status-badges">{spans}</div>'


def _render_cited_chunk(chunk: CitedChunkView) -> str:
    warning = (
        '<div class="warning cross-doc-warning">&#9888; This citation comes from a different '
        f"document/fixture (<code>{_esc(chunk.fixture)}</code>) than the principal evidence used "
        "by this answer. Shown for audit purposes -- evidence is never removed.</div>"
        if chunk.cross_document_warning
        else ""
    )
    return f"""<div class="cited-chunk">
  <div class="cited-chunk-header">
    <code class="chunk-id">{_esc(chunk.chunk_id)}</code>
    <span class="fixture">{_esc(chunk.fixture)}</span>
    <span class="doc-id">doc_id: {_esc(chunk.doc_id)}</span>
    <span class="source-format">{_esc(chunk.source_format)}</span>
  </div>
  {_render_status_badges(chunk.status_labels)}
  {warning}
  <div class="provenance-grid">
    <div><strong>unit_indices</strong>: {_esc(chunk.unit_indices)}</div>
    <div><strong>source_element_ids</strong>: {_esc(chunk.source_element_ids)}</div>
    <div><strong>heading_source_element_ids</strong>: {_esc(chunk.heading_source_element_ids)}</div>
    <div><strong>annotation_ids</strong>: {_esc(chunk.annotation_ids)}</div>
    <div><strong>source_refs</strong>: {_esc(chunk.source_refs)}</div>
  </div>
  <pre class="chunk-text">{_esc(chunk.chunk_text)}</pre>
</div>"""


def _render_claim(claim: ClaimView) -> str:
    chunk_html = "".join(_render_cited_chunk(c) for c in claim.cited_chunks)
    unresolved_html = (
        f'<div class="warning unresolved-warning">{claim.unresolved_citation_count} citation(s) did not '
        "resolve to a retrieved chunk (invalid citation -- flagged, never fabricated).</div>"
        if claim.unresolved_citation_count
        else ""
    )
    if not claim.cited_chunks and not claim.unresolved_citation_count:
        chunk_html = '<div class="no-citation">(no citation for this claim)</div>'
    return f"""<div class="claim">
  <div class="claim-text">{_esc(claim.claim_text)}</div>
  {unresolved_html}
  {chunk_html}
</div>"""


def _render_question_section(view: QuestionDemoView, active: bool) -> str:
    sufficiency_class = "sufficient" if view.evidence_sufficient else "insufficient"
    sufficiency_label = "✓ Evidence sufficient" if view.evidence_sufficient else "⚠ Evidence INSUFFICIENT"
    claims_html = "".join(_render_claim(c) for c in view.claims)
    cost = f"${view.estimated_cost_usd:.6f}" if view.estimated_cost_usd is not None else "n/a"
    input_tokens = view.input_tokens if view.input_tokens is not None else "n/a"
    output_tokens = view.output_tokens if view.output_tokens is not None else "n/a"
    display = "block" if active else "none"

    return f"""<section id="q-{_esc(view.question_id)}" class="question-section" style="display:{display}">
  <h2>{_esc(view.question_id)} <span class="difficulty">{_esc(view.difficulty)}</span></h2>
  <div class="question-text"><strong>Question:</strong> {_esc(view.question)}</div>
  <div class="answer-text"><strong>Answer:</strong> {_esc(view.answer_text)}</div>
  <div class="sufficiency-badge {sufficiency_class}">{sufficiency_label}</div>
  <div class="metrics-row">
    <span>model: {_esc(view.model_identity)}</span>
    <span>latency: {view.answer_latency_seconds:.3f}s</span>
    <span>input tokens: {_esc(input_tokens)}</span>
    <span>output tokens: {_esc(output_tokens)}</span>
    <span>estimated cost: {_esc(cost)}</span>
  </div>
  <div class="human-review-row">
    <span>answer-text review: <strong>{_esc(view.answer_text_correctness_human_review)}</strong></span>
    <span>citation-support review: <strong>{_esc(view.citation_support_human_review)}</strong></span>
  </div>
  <h3>Claim-level citations</h3>
  {claims_html}
</section>"""


_CSS = """
:root {
  color-scheme: light dark;
  --paper: #f7f5ee;
  --ink: #23261f;
  --ink-muted: #6b6a5c;
  --hairline: #ddd8c7;
  --surface: #efece0;
  --code-surface: #e9e5d3;
  --accent: #1d5c5a;
  --good: #2f7a4d;
  --warn: #a3521a;
  --critical: #a3311f;
  --serif: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
  --sans: -apple-system, "Segoe UI", Roboto, sans-serif;
  --mono: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) {
  :root {
    --paper: #151813; --ink: #e8e4d6; --ink-muted: #a19d89; --hairline: #34382c;
    --surface: #1e2119; --code-surface: #262a1f;
    --accent: #59b3ac; --good: #5fbb84; --warn: #e0954f; --critical: #e2695a;
  }
}
:root[data-theme="dark"] {
  --paper: #151813; --ink: #e8e4d6; --ink-muted: #a19d89; --hairline: #34382c;
  --surface: #1e2119; --code-surface: #262a1f;
  --accent: #59b3ac; --good: #5fbb84; --warn: #e0954f; --critical: #e2695a;
}
:root[data-theme="light"] {
  --paper: #f7f5ee; --ink: #23261f; --ink-muted: #6b6a5c; --hairline: #ddd8c7;
  --surface: #efece0; --code-surface: #e9e5d3;
  --accent: #1d5c5a; --good: #2f7a4d; --warn: #a3521a; --critical: #a3311f;
}
* { box-sizing: border-box; }
body {
  font-family: var(--sans); background: var(--paper); color: var(--ink);
  max-width: 760px; margin: 2.5rem auto; padding: 0 1.25rem 4rem; line-height: 1.55;
}
h1 { font-family: var(--serif); font-size: 1.6rem; font-weight: 600; margin: 0 0 0.4rem; text-wrap: balance; }
h2 { font-family: var(--serif); font-size: 1.25rem; font-weight: 600; margin: 0 0 0.6rem; text-wrap: balance; }
h3 { font-family: var(--serif); font-size: 1rem; font-weight: 600; color: var(--ink-muted); margin: 1.4rem 0 0.5rem; letter-spacing: 0.01em; }
.subtitle { color: var(--ink-muted); font-size: 0.92rem; max-width: 60ch; }
.subtitle code { font-family: var(--mono); font-size: 0.85em; }
label { font-family: var(--sans); font-size: 0.9rem; }
select {
  font-family: var(--sans); font-size: 0.95rem; padding: 0.5rem 0.7rem; margin: 0.5rem 0 1.75rem;
  max-width: 100%; width: 100%; background: var(--surface); color: var(--ink);
  border: 1px solid var(--hairline); border-radius: 6px;
}
select:focus-visible, a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.question-section { border-top: 1px solid var(--hairline); padding-top: 1.5rem; margin-top: 1.5rem; }
.difficulty {
  font-family: var(--sans); font-size: 0.68rem; color: var(--ink-muted); font-weight: 600;
  border: 1px solid var(--hairline); border-radius: 999px; padding: 0.15rem 0.55rem;
  text-transform: uppercase; letter-spacing: 0.04em; vertical-align: middle;
}
.question-text, .answer-text { margin: 0.6rem 0; }
.answer-text { padding: 0.75rem 0.9rem; background: var(--surface); border-radius: 8px; white-space: pre-wrap; }
.sufficiency-badge {
  display: inline-block; padding: 0.3rem 0.7rem; border-radius: 999px; font-weight: 600;
  font-size: 0.85rem; margin: 0.6rem 0; color: #fff;
}
.sufficiency-badge.sufficient { background: var(--good); }
.sufficiency-badge.insufficient { background: var(--critical); }
.metrics-row, .human-review-row {
  font-family: var(--mono); font-variant-numeric: tabular-nums; font-size: 0.78rem;
  color: var(--ink-muted); display: flex; gap: 0 1.1rem; flex-wrap: wrap; margin: 0.4rem 0;
}
.human-review-row { font-family: var(--sans); }
.human-review-row strong { color: var(--ink); }
.claim {
  border: 1px solid var(--hairline); border-radius: 8px; padding: 0.75rem 0.9rem;
  margin: 0.75rem 0; background: color-mix(in srgb, var(--surface) 35%, transparent);
}
.claim-text { font-family: var(--serif); font-size: 1.02rem; margin-bottom: 0.5rem; }
.cited-chunk { border-left: 3px solid var(--accent); padding-left: 0.75rem; margin: 0.65rem 0; }
.cited-chunk-header { display: flex; gap: 0.6rem; flex-wrap: wrap; font-size: 0.8rem; align-items: baseline; color: var(--ink-muted); }
.chunk-id { font-family: var(--mono); background: var(--code-surface); padding: 0.1rem 0.4rem; border-radius: 4px; color: var(--ink); }
.provenance-grid { font-family: var(--mono); font-size: 0.74rem; color: var(--ink-muted); margin: 0.4rem 0; display: grid; gap: 0.2rem; }
.provenance-grid strong { color: var(--ink); font-family: var(--sans); font-weight: 600; }
.chunk-text {
  font-family: var(--mono); background: var(--code-surface); padding: 0.6rem 0.7rem; border-radius: 6px;
  white-space: pre-wrap; font-size: 0.82rem; margin-top: 0.4rem; border: 1px solid var(--hairline);
}
.status-badges { margin: 0.4rem 0; }
.badge {
  display: inline-block; font-family: var(--sans); font-size: 0.66rem; font-weight: 700;
  padding: 0.12rem 0.45rem; border-radius: 4px; margin-right: 0.3rem; text-transform: uppercase;
  letter-spacing: 0.03em; color: #fff;
}
.badge-current { background: var(--good); }
.badge-retired, .badge-historical, .badge-superseded, .badge-draft, .badge-decommissioned { background: var(--critical); }
.badge-other { background: var(--ink-muted); }
.warning { font-size: 0.82rem; padding: 0.5rem 0.7rem; border-radius: 6px; margin: 0.45rem 0; border: 1px solid; }
.cross-doc-warning, .unresolved-warning {
  background: color-mix(in srgb, var(--warn) 14%, var(--paper)); color: var(--warn); border-color: color-mix(in srgb, var(--warn) 45%, transparent);
}
.no-citation { font-size: 0.85rem; color: var(--ink-muted); font-style: italic; }
"""

_TOGGLE_JS = (
    "document.querySelectorAll('.question-section').forEach(function(s){s.style.display='none';});"
    "document.getElementById(this.value).style.display='block';"
)


def render_demo_html(views: list[QuestionDemoView]) -> str:
    options_html = "".join(
        f'<option value="q-{_esc(v.question_id)}">{_esc(v.question_id)} -- {_esc(v.question)}</option>' for v in views
    )
    sections_html = "".join(_render_question_section(v, active=(i == 0)) for i, v in enumerate(views))
    generated_at = datetime.now(timezone.utc).isoformat()

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Stage 7A.3 -- Auditable Semantic-Search Demo</title>
<style>{_CSS}</style>
</head>
<body>
<h1>Stage 7A.3 -- Auditable Vector-RAG Semantic-Search Demo</h1>
<p class="subtitle">A read-only viewer over the frozen Stage 7A.2/7A.2a answer baseline
(<code>reports/stage7a2_vector_answer_results.json</code>) -- no live retrieval, no live
inference. Generated {_esc(generated_at)}.</p>
<label for="question-select"><strong>Question:</strong></label><br>
<select id="question-select" onchange="{_TOGGLE_JS}">
{options_html}
</select>
{sections_html}
</body>
</html>"""
