"""Stage 7C.0: the deterministic Wiki projection (W0).

CanonicalChunk -> deterministic identities -> anchors -> anchor postings ->
deterministic facet/page membership -> structural + exact-anchor links ->
authority-scoped views -> deterministic rendering.

ZERO LLM calls. Nothing in this package reads benchmark truth, Graph output,
authority state at build time, or any (future) Stage 7C.1 compiler output.
Membership is a property of the SOURCE TEXT and of nothing else -- see
`projection.build_projection` and the Revision 6 plan's SS2.2/SS4.0.
"""

from __future__ import annotations

__all__ = ["PROJECTION_CONTRACT_VERSION"]

PROJECTION_CONTRACT_VERSION = "wiki_projection_v1"
