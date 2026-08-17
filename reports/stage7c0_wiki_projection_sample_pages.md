# Stage 7C.0 — representative rendered W0 pages

Deterministic output of `scripts/run_stage7c0_wiki_projection.py`. Rendered under the **current-intent** authority scope, so historical and draft revisions are correctly hidden.

Zero LLM calls: every page's model-derived block is empty by construction.

---

# APP-224510

- **page_key**: `IDENT:APP-224510`
- **page_type**: `governed_identifier` (deterministic, from anchor kind `identifier`)
- **display_title**: verbatim source surface form (never re-worded, never generated)
- **identity_confidence**: `exact`
- **anchor_id**: `82d2fda404690aa0...`

**Authority visibility**: 1 of 1 revision-scoped facets are eligible under the current query scope; 0 hidden. Authority is resolved at query time and is not stored.

## Revision-scoped source facets

### Facet — APP-PORTFOLIO / app_rev2

- **document_revision_id**: `a6441298d656c12d...`
- **revision_number**: 2
- **membership_hash**: `8381dfcab8911ce9...`
- **membership basis**: this page's identity occurs in this revision's source material (1 anchor posting(s)) — membership is independent of any model output

#### Source section `3265f3d6e24d7aed...`

- **heading_path**: Application Portfolio > Registered Applications
- **chunk_id**: `2e409298eff569e2...`
- **content_sha256**: `cd362e1283ef769a...`
- **source_refs**: `[{'element_id': 'b4f381a4e1458e7f56e4c4c25e9a179180c6c8fb653599ccded3a05b40db2ea7', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]`

**A — source-authoritative content** (verbatim `CanonicalChunk.source_text`):

> Application APP-224510 supports the Payment Settlement business service.

**B — model-derived content**:

_None. Stage 7C.0 makes zero LLM calls; no claim, alias or summary exists yet._

**Anchor occurrences in this section** (occurrence evidence, never a relationship):

- `APP-224510` at source_text[12:22] — posting `ff6bbb015f0c...`

## Navigation

_An `exact_anchor` link means only: **this same source-backed identity occurs there**. It carries no direction, no relationship type and no lineage. A `structural` link expresses only the source hierarchy._

### exact_anchor links (1)

- via anchor `Payment Settlement` → SERVICE-CATALOGUE / svc_rev1 **[advisory]** — *this same source-backed identity occurs there*

### structural links (1)

- `section_of_revision_page` → APP-PORTFOLIO / app_rev2

---

_Stage 7C.0 deterministic W0 projection. Zero LLM calls. No claim, alias, summary, adjudication verdict or facet embedding exists. `is_authoritative_lineage` is False on every link._


---

# Payment Settlement

- **page_key**: `PHRASE:payment settlement`
- **page_type**: `business_topic` (deterministic, from anchor kind `phrase`)
- **display_title**: verbatim source surface form (never re-worded, never generated)
- **identity_confidence**: `ambiguous`
- **anchor_id**: `8f4a1d672e501db0...`
- **DISJOINT IDENTIFIER CONTEXT**: this phrase posts into sections with pairwise-disjoint identifier sets; its exact-anchor links are downgraded to **advisory**

**Authority visibility**: 2 of 3 revision-scoped facets are eligible under the current query scope; 1 hidden. Authority is resolved at query time and is not stored.

## Revision-scoped source facets

### Facet — SERVICE-CATALOGUE / svc_rev1

- **document_revision_id**: `56a7b958d0522a04...`
- **revision_number**: 1
- **membership_hash**: `5aeb43a3eef1c402...`
- **membership basis**: this page's identity occurs in this revision's source material (1 anchor posting(s)) — membership is independent of any model output

#### Source section `ac590a3393d76ff2...`

- **heading_path**: Business Service Catalogue > Governed Services
- **chunk_id**: `d00ddb9a8090249b...`
- **content_sha256**: `9e594b6177af4102...`
- **source_refs**: `[{'element_id': '64c635750aad130b5b10ee9f74a3f4237314375b7fe64db6ff763af6080df978', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]`

**A — source-authoritative content** (verbatim `CanonicalChunk.source_text`):

> The Payment Settlement business service is governed by Obligation O-31.

**B — model-derived content**:

_None. Stage 7C.0 makes zero LLM calls; no claim, alias or summary exists yet._

**Anchor occurrences in this section** (occurrence evidence, never a relationship):

- `Payment Settlement` at source_text[4:22] — posting `47c3f90fdffb...`

### Facet — APP-PORTFOLIO / app_rev2

- **document_revision_id**: `a6441298d656c12d...`
- **revision_number**: 2
- **membership_hash**: `1c052f6abe1921f6...`
- **membership basis**: this page's identity occurs in this revision's source material (1 anchor posting(s)) — membership is independent of any model output

#### Source section `3265f3d6e24d7aed...`

- **heading_path**: Application Portfolio > Registered Applications
- **chunk_id**: `2e409298eff569e2...`
- **content_sha256**: `cd362e1283ef769a...`
- **source_refs**: `[{'element_id': 'b4f381a4e1458e7f56e4c4c25e9a179180c6c8fb653599ccded3a05b40db2ea7', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]`

**A — source-authoritative content** (verbatim `CanonicalChunk.source_text`):

> Application APP-224510 supports the Payment Settlement business service.

**B — model-derived content**:

_None. Stage 7C.0 makes zero LLM calls; no claim, alias or summary exists yet._

**Anchor occurrences in this section** (occurrence evidence, never a relationship):

- `Payment Settlement` at source_text[36:54] — posting `1c197d8b2366...`

## Navigation

_An `exact_anchor` link means only: **this same source-backed identity occurs there**. It carries no direction, no relationship type and no lineage. A `structural` link expresses only the source hierarchy._

### exact_anchor links (3)

- via anchor `O-31` → OBLIGATION-REGISTER / obl_rev2 — *this same source-backed identity occurs there*
- via anchor `Payment Settlement` → APP-PORTFOLIO / app_rev2 **[advisory]** — *this same source-backed identity occurs there*
- via anchor `Payment Settlement` → SERVICE-CATALOGUE / svc_rev1 **[advisory]** — *this same source-backed identity occurs there*

### structural links (2)

- `section_of_revision_page` → SERVICE-CATALOGUE / svc_rev1
- `section_of_revision_page` → APP-PORTFOLIO / app_rev2

---

_Stage 7C.0 deterministic W0 projection. Zero LLM calls. No claim, alias, summary, adjudication verdict or facet embedding exists. `is_authoritative_lineage` is False on every link._


---

# O-31

- **page_key**: `IDENT:O-31`
- **page_type**: `governed_identifier` (deterministic, from anchor kind `identifier`)
- **display_title**: verbatim source surface form (never re-worded, never generated)
- **identity_confidence**: `exact`
- **anchor_id**: `6f65053cce8e43af...`

**Authority visibility**: 2 of 3 revision-scoped facets are eligible under the current query scope; 1 hidden. Authority is resolved at query time and is not stored.

## Revision-scoped source facets

### Facet — SERVICE-CATALOGUE / svc_rev1

- **document_revision_id**: `56a7b958d0522a04...`
- **revision_number**: 1
- **membership_hash**: `9a5728157327bffd...`
- **membership basis**: this page's identity occurs in this revision's source material (1 anchor posting(s)) — membership is independent of any model output

#### Source section `ac590a3393d76ff2...`

- **heading_path**: Business Service Catalogue > Governed Services
- **chunk_id**: `d00ddb9a8090249b...`
- **content_sha256**: `9e594b6177af4102...`
- **source_refs**: `[{'element_id': '64c635750aad130b5b10ee9f74a3f4237314375b7fe64db6ff763af6080df978', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]`

**A — source-authoritative content** (verbatim `CanonicalChunk.source_text`):

> The Payment Settlement business service is governed by Obligation O-31.

**B — model-derived content**:

_None. Stage 7C.0 makes zero LLM calls; no claim, alias or summary exists yet._

**Anchor occurrences in this section** (occurrence evidence, never a relationship):

- `O-31` at source_text[66:70] — posting `d7e758c1b9dd...`

### Facet — OBLIGATION-REGISTER / obl_rev2

- **document_revision_id**: `7e11f49c9d7b8b53...`
- **revision_number**: 2
- **membership_hash**: `d10fbe05f19c45f3...`
- **membership basis**: this page's identity occurs in this revision's source material (1 anchor posting(s)) — membership is independent of any model output

#### Source section `acf78881b2e0cbe3...`

- **heading_path**: Obligation Register > Obligation Coverage
- **chunk_id**: `5f10b139bf62039f...`
- **content_sha256**: `85c6c84a6ac4761a...`
- **source_refs**: `[{'element_id': '2cadac731ee907f7adff182121d3dd161852e8f52d814d6faf2edb2e32fb234f', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]`

**A — source-authoritative content** (verbatim `CanonicalChunk.source_text`):

> Obligation O-31 is satisfied by Control C-88.

**B — model-derived content**:

_None. Stage 7C.0 makes zero LLM calls; no claim, alias or summary exists yet._

**Anchor occurrences in this section** (occurrence evidence, never a relationship):

- `O-31` at source_text[11:15] — posting `b838da867364...`

## Navigation

_An `exact_anchor` link means only: **this same source-backed identity occurs there**. It carries no direction, no relationship type and no lineage. A `structural` link expresses only the source hierarchy._

### exact_anchor links (4)

- via anchor `O-31` → SERVICE-CATALOGUE / svc_rev1 — *this same source-backed identity occurs there*
- via anchor `O-31` → OBLIGATION-REGISTER / obl_rev2 — *this same source-backed identity occurs there*
- via anchor `Payment Settlement` → APP-PORTFOLIO / app_rev2 **[advisory]** — *this same source-backed identity occurs there*
- via anchor `C-88` → CONTROL-LIBRARY / ctl_rev2 — *this same source-backed identity occurs there*

### structural links (2)

- `section_of_revision_page` → OBLIGATION-REGISTER / obl_rev2
- `section_of_revision_page` → SERVICE-CATALOGUE / svc_rev1

---

_Stage 7C.0 deterministic W0 projection. Zero LLM calls. No claim, alias, summary, adjudication verdict or facet embedding exists. `is_authoritative_lineage` is False on every link._


---

# C-88

- **page_key**: `IDENT:C-88`
- **page_type**: `governed_identifier` (deterministic, from anchor kind `identifier`)
- **display_title**: verbatim source surface form (never re-worded, never generated)
- **identity_confidence**: `exact`
- **anchor_id**: `9724b0b2c16f8814...`

**Authority visibility**: 2 of 2 revision-scoped facets are eligible under the current query scope; 0 hidden. Authority is resolved at query time and is not stored.

## Revision-scoped source facets

### Facet — CONTROL-LIBRARY / ctl_rev2

- **document_revision_id**: `1ccf46cdf6b68534...`
- **revision_number**: 2
- **membership_hash**: `211ae6145a64b192...`
- **membership basis**: this page's identity occurs in this revision's source material (1 anchor posting(s)) — membership is independent of any model output

#### Source section `fd92215316d6f9f2...`

- **heading_path**: Control Library > Control Implementations
- **chunk_id**: `57aae7e4f9ee474d...`
- **content_sha256**: `78ee76a964e9515f...`
- **source_refs**: `[{'element_id': 'cefd0b37349f50f3e1dc027e500a7aebeaa4e4fad92b06945f8f25815f374434', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]`

**A — source-authoritative content** (verbatim `CanonicalChunk.source_text`):

> Control C-88 is implemented through Procedure P-205.

**B — model-derived content**:

_None. Stage 7C.0 makes zero LLM calls; no claim, alias or summary exists yet._

**Anchor occurrences in this section** (occurrence evidence, never a relationship):

- `C-88` at source_text[8:12] — posting `d71f002d6762...`

### Facet — OBLIGATION-REGISTER / obl_rev2

- **document_revision_id**: `7e11f49c9d7b8b53...`
- **revision_number**: 2
- **membership_hash**: `d213dbf72b2e6077...`
- **membership basis**: this page's identity occurs in this revision's source material (1 anchor posting(s)) — membership is independent of any model output

#### Source section `acf78881b2e0cbe3...`

- **heading_path**: Obligation Register > Obligation Coverage
- **chunk_id**: `5f10b139bf62039f...`
- **content_sha256**: `85c6c84a6ac4761a...`
- **source_refs**: `[{'element_id': '2cadac731ee907f7adff182121d3dd161852e8f52d814d6faf2edb2e32fb234f', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]`

**A — source-authoritative content** (verbatim `CanonicalChunk.source_text`):

> Obligation O-31 is satisfied by Control C-88.

**B — model-derived content**:

_None. Stage 7C.0 makes zero LLM calls; no claim, alias or summary exists yet._

**Anchor occurrences in this section** (occurrence evidence, never a relationship):

- `C-88` at source_text[40:44] — posting `86ab20782ff2...`

## Navigation

_An `exact_anchor` link means only: **this same source-backed identity occurs there**. It carries no direction, no relationship type and no lineage. A `structural` link expresses only the source hierarchy._

### exact_anchor links (4)

- via anchor `O-31` → SERVICE-CATALOGUE / svc_rev1 — *this same source-backed identity occurs there*
- via anchor `P-205` → PROCEDURE-CATALOGUE / prc_rev2 — *this same source-backed identity occurs there*
- via anchor `C-88` → OBLIGATION-REGISTER / obl_rev2 — *this same source-backed identity occurs there*
- via anchor `C-88` → CONTROL-LIBRARY / ctl_rev2 — *this same source-backed identity occurs there*

### structural links (2)

- `section_of_revision_page` → CONTROL-LIBRARY / ctl_rev2
- `section_of_revision_page` → OBLIGATION-REGISTER / obl_rev2

---

_Stage 7C.0 deterministic W0 projection. Zero LLM calls. No claim, alias, summary, adjudication verdict or facet embedding exists. `is_authoritative_lineage` is False on every link._


---

# C-88a

- **page_key**: `IDENT:C-88A`
- **page_type**: `governed_identifier` (deterministic, from anchor kind `identifier`)
- **display_title**: verbatim source surface form (never re-worded, never generated)
- **identity_confidence**: `exact`
- **anchor_id**: `a67a88fe8d845e47...`

**Authority visibility**: 0 of 2 revision-scoped facets are eligible under the current query scope; 2 hidden. Authority is resolved at query time and is not stored.

## Revision-scoped source facets

_No facet of this page is eligible under the current authority scope._

## Navigation

_An `exact_anchor` link means only: **this same source-backed identity occurs there**. It carries no direction, no relationship type and no lineage. A `structural` link expresses only the source hierarchy._

_No eligible outgoing link under the current authority scope._

---

_Stage 7C.0 deterministic W0 projection. Zero LLM calls. No claim, alias, summary, adjudication verdict or facet embedding exists. `is_authoritative_lineage` is False on every link._


---

# P-205

- **page_key**: `IDENT:P-205`
- **page_type**: `governed_identifier` (deterministic, from anchor kind `identifier`)
- **display_title**: verbatim source surface form (never re-worded, never generated)
- **identity_confidence**: `exact`
- **anchor_id**: `317db1d10a2189bf...`

**Authority visibility**: 2 of 3 revision-scoped facets are eligible under the current query scope; 1 hidden. Authority is resolved at query time and is not stored.

## Revision-scoped source facets

### Facet — CONTROL-LIBRARY / ctl_rev2

- **document_revision_id**: `1ccf46cdf6b68534...`
- **revision_number**: 2
- **membership_hash**: `4619f3a82913ddc7...`
- **membership basis**: this page's identity occurs in this revision's source material (1 anchor posting(s)) — membership is independent of any model output

#### Source section `fd92215316d6f9f2...`

- **heading_path**: Control Library > Control Implementations
- **chunk_id**: `57aae7e4f9ee474d...`
- **content_sha256**: `78ee76a964e9515f...`
- **source_refs**: `[{'element_id': 'cefd0b37349f50f3e1dc027e500a7aebeaa4e4fad92b06945f8f25815f374434', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]`

**A — source-authoritative content** (verbatim `CanonicalChunk.source_text`):

> Control C-88 is implemented through Procedure P-205.

**B — model-derived content**:

_None. Stage 7C.0 makes zero LLM calls; no claim, alias or summary exists yet._

**Anchor occurrences in this section** (occurrence evidence, never a relationship):

- `P-205` at source_text[46:51] — posting `78348d9a8418...`

### Facet — PROCEDURE-CATALOGUE / prc_rev2

- **document_revision_id**: `cc8084b399bab8de...`
- **revision_number**: 2
- **membership_hash**: `295bf02b718d343c...`
- **membership basis**: this page's identity occurs in this revision's source material (1 anchor posting(s)) — membership is independent of any model output

#### Source section `cb967ccb5cd5b545...`

- **heading_path**: Procedure Catalogue > Operating Procedures
- **chunk_id**: `1528d94345257125...`
- **content_sha256**: `e856f21141ca346e...`
- **source_refs**: `[{'element_id': 'fe6fa1fb6d0932d39ea4b0184d053844d4195280d9a670aa66f0911eaac2abc1', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]`

**A — source-authoritative content** (verbatim `CanonicalChunk.source_text`):

> Procedure P-205 is the current operating procedure.

**B — model-derived content**:

_None. Stage 7C.0 makes zero LLM calls; no claim, alias or summary exists yet._

**Anchor occurrences in this section** (occurrence evidence, never a relationship):

- `P-205` at source_text[10:15] — posting `89b5c6daca48...`

## Navigation

_An `exact_anchor` link means only: **this same source-backed identity occurs there**. It carries no direction, no relationship type and no lineage. A `structural` link expresses only the source hierarchy._

### exact_anchor links (3)

- via anchor `P-205` → CONTROL-LIBRARY / ctl_rev2 — *this same source-backed identity occurs there*
- via anchor `P-205` → PROCEDURE-CATALOGUE / prc_rev2 — *this same source-backed identity occurs there*
- via anchor `C-88` → OBLIGATION-REGISTER / obl_rev2 — *this same source-backed identity occurs there*

### structural links (2)

- `section_of_revision_page` → CONTROL-LIBRARY / ctl_rev2
- `section_of_revision_page` → PROCEDURE-CATALOGUE / prc_rev2

---

_Stage 7C.0 deterministic W0 projection. Zero LLM calls. No claim, alias, summary, adjudication verdict or facet embedding exists. `is_authoritative_lineage` is False on every link._


---
