"""Stage 7C.0: the projection storage protocol and its in-memory reference
implementation.

Only the TWO projection tables exist at 7C.0 -- `anchor` and
`anchor_posting`. `facet`, `facet_embedding` and `compilation_audit` belong
to Stage 7C.1 and are deliberately NOT created here (Revision 6 SS10.3 and the
scope rule "do not pre-build 7C.1/7C.2 machinery").

Facets are computed deterministically from postings (SS2.2), so at 7C.0 they
need no storage of their own: recomputing them from stored postings is the
membership invariant, not a cache.
"""

from __future__ import annotations

from typing import Protocol

from ingestion_bench.wiki_projection.model import AnchorPosting, WikiAnchor


class WikiProjectionStore(Protocol):
    def upsert_anchors(self, anchors: list[WikiAnchor]) -> int: ...

    def upsert_postings(self, postings: list[AnchorPosting]) -> int: ...

    def all_anchors(self) -> list[WikiAnchor]: ...

    def postings_for_revisions(self, eligible_revision_ids: list[str]) -> list[AnchorPosting]:
        """Authority filtering happens HERE, before anything is ranked or
        rendered. An empty eligible set yields [] -- never "return
        everything"."""
        ...

    def anchor_count(self) -> int: ...

    def posting_count(self) -> int: ...


class InMemoryWikiProjectionStore:
    """Pure-Python reference implementation -- no external database. Records
    are keyed by their own deterministic hashes, so re-upserting an unchanged
    projection is a no-op rather than a duplicate."""

    def __init__(self) -> None:
        self._anchors: dict[str, WikiAnchor] = {}
        self._postings: dict[str, AnchorPosting] = {}

    def upsert_anchors(self, anchors: list[WikiAnchor]) -> int:
        for anchor in anchors:
            self._anchors[anchor.anchor_id] = anchor
        return len(anchors)

    def upsert_postings(self, postings: list[AnchorPosting]) -> int:
        for posting in postings:
            self._postings[posting.posting_hash] = posting
        return len(postings)

    def all_anchors(self) -> list[WikiAnchor]:
        return [self._anchors[key] for key in sorted(self._anchors)]

    def postings_for_revisions(self, eligible_revision_ids: list[str]) -> list[AnchorPosting]:
        if not eligible_revision_ids:
            return []
        eligible = set(eligible_revision_ids)
        selected = [p for p in self._postings.values() if p.document_revision_id in eligible]
        return sorted(selected, key=lambda p: (p.document_revision_id, p.chunk_id, p.start_char, p.end_char, p.anchor_id))

    def anchor_count(self) -> int:
        return len(self._anchors)

    def posting_count(self) -> int:
        return len(self._postings)
