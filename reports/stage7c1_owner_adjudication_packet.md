# Stage 7C.1 — OWNER ADJUDICATION PACKET (Run 1)

> **You are the only semantic adjudicator.** Mechanical validation has already run; what remains are three judgements no deterministic rule can make. No verdict below is pre-filled and no recommendation is offered.

- Run: **1** (the primary representation candidate, designated before execution)
- Compiler model: `gpt-4o-mini`
- Prompt: `stage7c1-facet-compiler-v1` / `1144ceff32112796...`
- Frozen projection: `4162fa515cf29d09...`
- Packet SHA-256: `5d08b88dc9473a07...`

**Items awaiting your verdict: 68** (25 claims, 21 aliases, 22 summary sentences)

## How to record a verdict

1. Fill ONLY `owner_verdict` (CORRECT / INCORRECT / UNVERIFIABLE) and `owner_reason` on each item.
2. CLAIM: does (subject, predicate, object) faithfully represent the cited passage? A valid exact citation proves the passage exists and contains the quote -- it does NOT prove the inferred predicate represents it (Revision 6 SS4.3).
3. ALIAS: does this alias genuinely denote THIS facet's page identity -- not a related, broader, narrower or adjacent entity? A verbatim occurrence proves the string is there, not that it names this entity (SS4.5).
4. SUMMARY: does the sentence faithfully represent EXACTLY the claims it references -- no addition, overstatement, merge error, direction inversion, dropped qualification or temporal/status distortion? Valid claim-id references prove only that it points at accepted claims (SS4.4).
5. An INCORRECT alias verdict also demotes every claim listed under `claims_whose_coherence_depends_on_this_alias` to out_of_page_scope (SS4.6 pass 3).
6. Nothing here is pre-filled and no recommendation is offered: these three judgements are yours alone, and the representation cannot be built without them.

---

## A. CLAIMS

_Citation validity is not claim correctness (SS4.3)._

### `CLAIM::IDENT:APP-224499|895467b2b856639286818a30384b0bea8e3b16b3068770ef1c70b0c97bd364da::claim-1`

- **page**: APP-224499 (`IDENT:APP-224499`)
- **facet**: `IDENT:APP-224499|895467b2b856639286818a30384b0bea8e3b16b3068770ef1c70b0c97bd364da` — APP-PORTFOLIO / app_rev1
- **subject**: APP-224499
- **predicate**: supports
- **object**: Payment Settlement business service
- **claim_text**: APP-224499 supports the Payment Settlement business service.
- **cites**: `1a5af9b5351cdb8dd8b97af698c83c6208746b972fc6edc69d3b8bdc595dfac8`
- **exact supporting quote(s)**: ['Application APP-224499 supports the Payment Settlement business service.']
- **source_refs**: `{'1a5af9b5351cdb8dd8b97af698c83c6208746b972fc6edc69d3b8bdc595dfac8': [{'element_id': 'e4c046d70a286e271e77c82de8fe97b4a2e469f85fa1675e74943cde777cec9f', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]}`

**Source passage (enough context to judge meaning):**

- `1a5af9b5351cdb8d...`:

  > Application APP-224499 supports the Payment Settlement business service.

- **mechanical validation**: status=`accepted`, citation_valid=True, coherence=identity_subject
- **acceptance depends on an alias**: False
- **derived link that would result if accepted**: none (an endpoint resolves to no existing page key)

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `CLAIM::IDENT:APP-224510|a6441298d656c12d1a36a4ce1367d4ef5cb5ca148ef02733c68f277b96e0657a::claim-1`

- **page**: APP-224510 (`IDENT:APP-224510`)
- **facet**: `IDENT:APP-224510|a6441298d656c12d1a36a4ce1367d4ef5cb5ca148ef02733c68f277b96e0657a` — APP-PORTFOLIO / app_rev2
- **subject**: APP-224510
- **predicate**: supports
- **object**: the Payment Settlement business service
- **claim_text**: APP-224510 supports the Payment Settlement business service.
- **cites**: `2e409298eff569e23010445d05ffcd32b1276aacb0bc48525bf4a07cbcb1a8b2`
- **exact supporting quote(s)**: ['Application APP-224510 supports the Payment Settlement business service.']
- **source_refs**: `{'2e409298eff569e23010445d05ffcd32b1276aacb0bc48525bf4a07cbcb1a8b2': [{'element_id': 'b4f381a4e1458e7f56e4c4c25e9a179180c6c8fb653599ccded3a05b40db2ea7', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]}`

**Source passage (enough context to judge meaning):**

- `2e409298eff569e2...`:

  > Application APP-224510 supports the Payment Settlement business service.

- **mechanical validation**: status=`accepted`, citation_valid=True, coherence=identity_subject
- **acceptance depends on an alias**: False
- **derived link that would result if accepted**: none (an endpoint resolves to no existing page key)

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `CLAIM::IDENT:APP-330012|8b2000480b7b2cf4b4b38e9f479e090137b3a978c6a7b0bfe421dbdb44322cec::claim1`

- **page**: APP-330012 (`IDENT:APP-330012`)
- **facet**: `IDENT:APP-330012|8b2000480b7b2cf4b4b38e9f479e090137b3a978c6a7b0bfe421dbdb44322cec` — ADJACENT-DOMAIN / adj_rev1
- **subject**: APP-330012
- **predicate**: supports
- **object**: Payment Reconciliation business service
- **claim_text**: APP-330012 supports the Payment Reconciliation business service.
- **cites**: `ced1fc0535981101f44ecc6dd7cd00302d7f9d03d017735d9d360eb92a760011`
- **exact supporting quote(s)**: ['Application APP-330012 supports the Payment Reconciliation business service.']
- **source_refs**: `{'ced1fc0535981101f44ecc6dd7cd00302d7f9d03d017735d9d360eb92a760011': [{'element_id': 'dcc0aad4c2d3c5ba46fed5a00d9e508701c843c1dfcd009fdbb6973ec1d8dcf5', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': '1a998dbc8e49642a4422c20ef7fcb4301f264e988351bc903f07edac8f69bab3', 'unit_index': 0, 'order_index': 3, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': 'e0e17914cf92ea3ec67d4b0479ab17940c5a9c88e58c42d52f3fde746a15e4b2', 'unit_index': 0, 'order_index': 4, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': '93401a943c035fac84276aae5a74de1c05763ef248736b09f4932894de7a83c9', 'unit_index': 0, 'order_index': 5, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': 'e732b7b01b0568ce1fb0bb86bbe79942922f392373699cf054b271be83c5687b', 'unit_index': 0, 'order_index': 6, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]}`

**Source passage (enough context to judge meaning):**

- `ced1fc0535981101...`:

  > Application APP-330012 supports the Payment Reconciliation business service.
  > 
  > The Payment Reconciliation business service is governed by Obligation O-32.
  > 
  > Obligation O-32 is satisfied by Control C-77.
  > 
  > Control C-77 is implemented through Procedure P-301.
  > 
  > Procedure P-301 is the current operating procedure for reconciliation.

- **mechanical validation**: status=`accepted`, citation_valid=True, coherence=identity_subject
- **acceptance depends on an alias**: False
- **derived link that would result if accepted**: none (an endpoint resolves to no existing page key)

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `CLAIM::IDENT:C-77|8b2000480b7b2cf4b4b38e9f479e090137b3a978c6a7b0bfe421dbdb44322cec::claim1`

- **page**: C-77 (`IDENT:C-77`)
- **facet**: `IDENT:C-77|8b2000480b7b2cf4b4b38e9f479e090137b3a978c6a7b0bfe421dbdb44322cec` — ADJACENT-DOMAIN / adj_rev1
- **subject**: Obligation O-32
- **predicate**: is satisfied by
- **object**: Control C-77
- **claim_text**: Obligation O-32 is satisfied by Control C-77.
- **cites**: `ced1fc0535981101f44ecc6dd7cd00302d7f9d03d017735d9d360eb92a760011`
- **exact supporting quote(s)**: ['Obligation O-32 is satisfied by Control C-77.']
- **source_refs**: `{'ced1fc0535981101f44ecc6dd7cd00302d7f9d03d017735d9d360eb92a760011': [{'element_id': 'dcc0aad4c2d3c5ba46fed5a00d9e508701c843c1dfcd009fdbb6973ec1d8dcf5', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': '1a998dbc8e49642a4422c20ef7fcb4301f264e988351bc903f07edac8f69bab3', 'unit_index': 0, 'order_index': 3, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': 'e0e17914cf92ea3ec67d4b0479ab17940c5a9c88e58c42d52f3fde746a15e4b2', 'unit_index': 0, 'order_index': 4, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': '93401a943c035fac84276aae5a74de1c05763ef248736b09f4932894de7a83c9', 'unit_index': 0, 'order_index': 5, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': 'e732b7b01b0568ce1fb0bb86bbe79942922f392373699cf054b271be83c5687b', 'unit_index': 0, 'order_index': 6, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]}`

**Source passage (enough context to judge meaning):**

- `ced1fc0535981101...`:

  > Application APP-330012 supports the Payment Reconciliation business service.
  > 
  > The Payment Reconciliation business service is governed by Obligation O-32.
  > 
  > Obligation O-32 is satisfied by Control C-77.
  > 
  > Control C-77 is implemented through Procedure P-301.
  > 
  > Procedure P-301 is the current operating procedure for reconciliation.

- **mechanical validation**: status=`accepted`, citation_valid=True, coherence=identity_object
- **acceptance depends on an alias**: False
- **derived link that would result if accepted**:
  - `IDENT:O-32` —*is satisfied by*→ `IDENT:C-77` (inverse)
  - `IDENT:O-32` —*is satisfied by*→ `IDENT:C-77` (forward)

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `CLAIM::IDENT:C-77|8b2000480b7b2cf4b4b38e9f479e090137b3a978c6a7b0bfe421dbdb44322cec::claim2`

- **page**: C-77 (`IDENT:C-77`)
- **facet**: `IDENT:C-77|8b2000480b7b2cf4b4b38e9f479e090137b3a978c6a7b0bfe421dbdb44322cec` — ADJACENT-DOMAIN / adj_rev1
- **subject**: Control C-77
- **predicate**: is implemented through
- **object**: Procedure P-301
- **claim_text**: Control C-77 is implemented through Procedure P-301.
- **cites**: `ced1fc0535981101f44ecc6dd7cd00302d7f9d03d017735d9d360eb92a760011`
- **exact supporting quote(s)**: ['Control C-77 is implemented through Procedure P-301.']
- **source_refs**: `{'ced1fc0535981101f44ecc6dd7cd00302d7f9d03d017735d9d360eb92a760011': [{'element_id': 'dcc0aad4c2d3c5ba46fed5a00d9e508701c843c1dfcd009fdbb6973ec1d8dcf5', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': '1a998dbc8e49642a4422c20ef7fcb4301f264e988351bc903f07edac8f69bab3', 'unit_index': 0, 'order_index': 3, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': 'e0e17914cf92ea3ec67d4b0479ab17940c5a9c88e58c42d52f3fde746a15e4b2', 'unit_index': 0, 'order_index': 4, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': '93401a943c035fac84276aae5a74de1c05763ef248736b09f4932894de7a83c9', 'unit_index': 0, 'order_index': 5, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': 'e732b7b01b0568ce1fb0bb86bbe79942922f392373699cf054b271be83c5687b', 'unit_index': 0, 'order_index': 6, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]}`

**Source passage (enough context to judge meaning):**

- `ced1fc0535981101...`:

  > Application APP-330012 supports the Payment Reconciliation business service.
  > 
  > The Payment Reconciliation business service is governed by Obligation O-32.
  > 
  > Obligation O-32 is satisfied by Control C-77.
  > 
  > Control C-77 is implemented through Procedure P-301.
  > 
  > Procedure P-301 is the current operating procedure for reconciliation.

- **mechanical validation**: status=`accepted`, citation_valid=True, coherence=identity_subject
- **acceptance depends on an alias**: False
- **derived link that would result if accepted**:
  - `IDENT:C-77` —*is implemented through*→ `IDENT:P-301` (forward)
  - `IDENT:C-77` —*is implemented through*→ `IDENT:P-301` (inverse)

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `CLAIM::IDENT:C-88A|049930b3b215c7ad5fb5e8f1ea0b303a2111312f42293ebafa4336da9563d25b::claim1`

- **page**: C-88a (`IDENT:C-88A`)
- **facet**: `IDENT:C-88A|049930b3b215c7ad5fb5e8f1ea0b303a2111312f42293ebafa4336da9563d25b` — CONTROL-LIBRARY / ctl_rev1
- **subject**: C-88a
- **predicate**: is implemented through
- **object**: Procedure P-204
- **claim_text**: C-88a is implemented through Procedure P-204.
- **cites**: `dfca23730d4262d1947b10fc27e2357139a0ef7c6716a016fff70e89a32d461a`
- **exact supporting quote(s)**: ['Control C-88a is implemented through Procedure P-204.']
- **source_refs**: `{'dfca23730d4262d1947b10fc27e2357139a0ef7c6716a016fff70e89a32d461a': [{'element_id': '8e26839de1ff885561c0ebdc3197ee062120db0a684855d51ef508e556524bde', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]}`

**Source passage (enough context to judge meaning):**

- `dfca23730d4262d1...`:

  > Control C-88a is implemented through Procedure P-204.

- **mechanical validation**: status=`accepted`, citation_valid=True, coherence=identity_subject
- **acceptance depends on an alias**: False
- **derived link that would result if accepted**:
  - `IDENT:C-88A` —*is implemented through*→ `IDENT:P-204` (forward)
  - `IDENT:C-88A` —*is implemented through*→ `IDENT:P-204` (inverse)

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `CLAIM::IDENT:C-88A|ad26ab9483b67f2540f5bd6da379c37887fd8762e5e966b46221274a6fe97689::claim1`

- **page**: C-88a (`IDENT:C-88A`)
- **facet**: `IDENT:C-88A|ad26ab9483b67f2540f5bd6da379c37887fd8762e5e966b46221274a6fe97689` — OBLIGATION-REGISTER / obl_rev1
- **subject**: Obligation O-31
- **predicate**: is satisfied by
- **object**: Control C-88a
- **claim_text**: Obligation O-31 is satisfied by Control C-88a.
- **cites**: `54188cb210abf626030baa93b61a999b2db6018ab85fbc2592039ab7ddf4235a`
- **exact supporting quote(s)**: ['Obligation O-31 is satisfied by Control C-88a.']
- **source_refs**: `{'54188cb210abf626030baa93b61a999b2db6018ab85fbc2592039ab7ddf4235a': [{'element_id': 'bff56946bc24afd4d5f343cc43daab1dad32cfe0677ac1a9e72f6e80fa2df49f', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]}`

**Source passage (enough context to judge meaning):**

- `54188cb210abf626...`:

  > Obligation O-31 is satisfied by Control C-88a.

- **mechanical validation**: status=`accepted`, citation_valid=True, coherence=identity_object
- **acceptance depends on an alias**: False
- **derived link that would result if accepted**:
  - `IDENT:O-31` —*is satisfied by*→ `IDENT:C-88A` (inverse)
  - `IDENT:O-31` —*is satisfied by*→ `IDENT:C-88A` (forward)

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `CLAIM::IDENT:C-88|1ccf46cdf6b68534932b46efff0fa5f15673b3934f7aa79ec05697ce0df68f23::claim1`

- **page**: C-88 (`IDENT:C-88`)
- **facet**: `IDENT:C-88|1ccf46cdf6b68534932b46efff0fa5f15673b3934f7aa79ec05697ce0df68f23` — CONTROL-LIBRARY / ctl_rev2
- **subject**: C-88
- **predicate**: is implemented through
- **object**: Procedure P-205
- **claim_text**: C-88 is implemented through Procedure P-205.
- **cites**: `57aae7e4f9ee474d03f50711d0d3a8c3bcdaa265b004afa582a6b6c48156b00d`
- **exact supporting quote(s)**: ['Control C-88 is implemented through Procedure P-205.']
- **source_refs**: `{'57aae7e4f9ee474d03f50711d0d3a8c3bcdaa265b004afa582a6b6c48156b00d': [{'element_id': 'cefd0b37349f50f3e1dc027e500a7aebeaa4e4fad92b06945f8f25815f374434', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]}`

**Source passage (enough context to judge meaning):**

- `57aae7e4f9ee474d...`:

  > Control C-88 is implemented through Procedure P-205.

- **mechanical validation**: status=`accepted`, citation_valid=True, coherence=identity_subject
- **acceptance depends on an alias**: False
- **derived link that would result if accepted**:
  - `IDENT:C-88` —*is implemented through*→ `IDENT:P-205` (forward)
  - `IDENT:C-88` —*is implemented through*→ `IDENT:P-205` (inverse)

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `CLAIM::IDENT:C-88|7e11f49c9d7b8b53d319fa11b629c60ae00ed138d33fa4f50d1bf7415241d9cc::claim1`

- **page**: C-88 (`IDENT:C-88`)
- **facet**: `IDENT:C-88|7e11f49c9d7b8b53d319fa11b629c60ae00ed138d33fa4f50d1bf7415241d9cc` — OBLIGATION-REGISTER / obl_rev2
- **subject**: Control C-88
- **predicate**: is satisfied by
- **object**: Obligation O-31
- **claim_text**: Control C-88 is satisfied by Obligation O-31.
- **cites**: `5f10b139bf62039fc587b84fa08f251fb9a2be835c1e5865b8d29c6f2c9196a8`
- **exact supporting quote(s)**: ['Obligation O-31 is satisfied by Control C-88.']
- **source_refs**: `{'5f10b139bf62039fc587b84fa08f251fb9a2be835c1e5865b8d29c6f2c9196a8': [{'element_id': '2cadac731ee907f7adff182121d3dd161852e8f52d814d6faf2edb2e32fb234f', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]}`

**Source passage (enough context to judge meaning):**

- `5f10b139bf62039f...`:

  > Obligation O-31 is satisfied by Control C-88.

- **mechanical validation**: status=`accepted`, citation_valid=True, coherence=identity_subject
- **acceptance depends on an alias**: False
- **derived link that would result if accepted**:
  - `IDENT:C-88` —*is satisfied by*→ `IDENT:O-31` (forward)
  - `IDENT:C-88` —*is satisfied by*→ `IDENT:O-31` (inverse)

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `CLAIM::IDENT:C-91|02827f19b5553859742110cbcffa8bdf01251d923399741bea8d5bf0bd9eff82::claim1`

- **page**: C-91 (`IDENT:C-91`)
- **facet**: `IDENT:C-91|02827f19b5553859742110cbcffa8bdf01251d923399741bea8d5bf0bd9eff82` — CONTROL-LIBRARY / ctl_rev3
- **subject**: Control C-91
- **predicate**: is implemented through
- **object**: Procedure P-205
- **claim_text**: Control C-91 is implemented through Procedure P-205.
- **cites**: `fac4d4cba8c743cb31248aaa614b1c8928b8c7a3fc4d1510c3c041b749a4c21c`
- **exact supporting quote(s)**: ['Control C-91 is implemented through Procedure P-205.']
- **source_refs**: `{'fac4d4cba8c743cb31248aaa614b1c8928b8c7a3fc4d1510c3c041b749a4c21c': [{'element_id': '60cb174e8ec1f58f08af943484d3eb6b1716aa30b555d8b8506db28af5a6a0d8', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]}`

**Source passage (enough context to judge meaning):**

- `fac4d4cba8c743cb...`:

  > Control C-91 is implemented through Procedure P-205.

- **mechanical validation**: status=`accepted`, citation_valid=True, coherence=identity_subject
- **acceptance depends on an alias**: False
- **derived link that would result if accepted**:
  - `IDENT:C-91` —*is implemented through*→ `IDENT:P-205` (forward)
  - `IDENT:C-91` —*is implemented through*→ `IDENT:P-205` (inverse)

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `CLAIM::IDENT:O-31|56a7b958d0522a0402a16bee101ad10b41e66297129f9cb988bb65b52735e868::claim1`

- **page**: O-31 (`IDENT:O-31`)
- **facet**: `IDENT:O-31|56a7b958d0522a0402a16bee101ad10b41e66297129f9cb988bb65b52735e868` — SERVICE-CATALOGUE / svc_rev1
- **subject**: Payment Settlement business service
- **predicate**: is governed by
- **object**: Obligation O-31
- **claim_text**: The Payment Settlement business service is governed by Obligation O-31.
- **cites**: `d00ddb9a8090249bd214a1ee50ac8b1fe5a1d7e307e4948048f3ab9ed2b44614`
- **exact supporting quote(s)**: ['The Payment Settlement business service is governed by Obligation O-31.']
- **source_refs**: `{'d00ddb9a8090249bd214a1ee50ac8b1fe5a1d7e307e4948048f3ab9ed2b44614': [{'element_id': '64c635750aad130b5b10ee9f74a3f4237314375b7fe64db6ff763af6080df978', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]}`

**Source passage (enough context to judge meaning):**

- `d00ddb9a8090249b...`:

  > The Payment Settlement business service is governed by Obligation O-31.

- **mechanical validation**: status=`accepted`, citation_valid=True, coherence=identity_object
- **acceptance depends on an alias**: False
- **derived link that would result if accepted**: none (an endpoint resolves to no existing page key)

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `CLAIM::IDENT:O-31|7e11f49c9d7b8b53d319fa11b629c60ae00ed138d33fa4f50d1bf7415241d9cc::claim1`

- **page**: O-31 (`IDENT:O-31`)
- **facet**: `IDENT:O-31|7e11f49c9d7b8b53d319fa11b629c60ae00ed138d33fa4f50d1bf7415241d9cc` — OBLIGATION-REGISTER / obl_rev2
- **subject**: Obligation O-31
- **predicate**: is satisfied by
- **object**: Control C-88
- **claim_text**: Obligation O-31 is satisfied by Control C-88.
- **cites**: `5f10b139bf62039fc587b84fa08f251fb9a2be835c1e5865b8d29c6f2c9196a8`
- **exact supporting quote(s)**: ['Obligation O-31 is satisfied by Control C-88.']
- **source_refs**: `{'5f10b139bf62039fc587b84fa08f251fb9a2be835c1e5865b8d29c6f2c9196a8': [{'element_id': '2cadac731ee907f7adff182121d3dd161852e8f52d814d6faf2edb2e32fb234f', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]}`

**Source passage (enough context to judge meaning):**

- `5f10b139bf62039f...`:

  > Obligation O-31 is satisfied by Control C-88.

- **mechanical validation**: status=`accepted`, citation_valid=True, coherence=identity_subject
- **acceptance depends on an alias**: False
- **derived link that would result if accepted**:
  - `IDENT:O-31` —*is satisfied by*→ `IDENT:C-88` (forward)
  - `IDENT:O-31` —*is satisfied by*→ `IDENT:C-88` (inverse)

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `CLAIM::IDENT:O-31|ad26ab9483b67f2540f5bd6da379c37887fd8762e5e966b46221274a6fe97689::claim1`

- **page**: O-31 (`IDENT:O-31`)
- **facet**: `IDENT:O-31|ad26ab9483b67f2540f5bd6da379c37887fd8762e5e966b46221274a6fe97689` — OBLIGATION-REGISTER / obl_rev1
- **subject**: Obligation O-31
- **predicate**: is satisfied by
- **object**: Control C-88a
- **claim_text**: Obligation O-31 is satisfied by Control C-88a.
- **cites**: `54188cb210abf626030baa93b61a999b2db6018ab85fbc2592039ab7ddf4235a`
- **exact supporting quote(s)**: ['Obligation O-31 is satisfied by Control C-88a.']
- **source_refs**: `{'54188cb210abf626030baa93b61a999b2db6018ab85fbc2592039ab7ddf4235a': [{'element_id': 'bff56946bc24afd4d5f343cc43daab1dad32cfe0677ac1a9e72f6e80fa2df49f', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]}`

**Source passage (enough context to judge meaning):**

- `54188cb210abf626...`:

  > Obligation O-31 is satisfied by Control C-88a.

- **mechanical validation**: status=`accepted`, citation_valid=True, coherence=identity_subject
- **acceptance depends on an alias**: False
- **derived link that would result if accepted**:
  - `IDENT:O-31` —*is satisfied by*→ `IDENT:C-88A` (inverse)
  - `IDENT:O-31` —*is satisfied by*→ `IDENT:C-88A` (forward)

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `CLAIM::IDENT:O-32|8b2000480b7b2cf4b4b38e9f479e090137b3a978c6a7b0bfe421dbdb44322cec::claim1`

- **page**: O-32 (`IDENT:O-32`)
- **facet**: `IDENT:O-32|8b2000480b7b2cf4b4b38e9f479e090137b3a978c6a7b0bfe421dbdb44322cec` — ADJACENT-DOMAIN / adj_rev1
- **subject**: Obligation O-32
- **predicate**: is governed by
- **object**: Payment Reconciliation business service
- **claim_text**: Obligation O-32 is governed by Payment Reconciliation business service.
- **cites**: `ced1fc0535981101f44ecc6dd7cd00302d7f9d03d017735d9d360eb92a760011`
- **exact supporting quote(s)**: ['The Payment Reconciliation business service is governed by Obligation O-32.']
- **source_refs**: `{'ced1fc0535981101f44ecc6dd7cd00302d7f9d03d017735d9d360eb92a760011': [{'element_id': 'dcc0aad4c2d3c5ba46fed5a00d9e508701c843c1dfcd009fdbb6973ec1d8dcf5', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': '1a998dbc8e49642a4422c20ef7fcb4301f264e988351bc903f07edac8f69bab3', 'unit_index': 0, 'order_index': 3, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': 'e0e17914cf92ea3ec67d4b0479ab17940c5a9c88e58c42d52f3fde746a15e4b2', 'unit_index': 0, 'order_index': 4, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': '93401a943c035fac84276aae5a74de1c05763ef248736b09f4932894de7a83c9', 'unit_index': 0, 'order_index': 5, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': 'e732b7b01b0568ce1fb0bb86bbe79942922f392373699cf054b271be83c5687b', 'unit_index': 0, 'order_index': 6, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]}`

**Source passage (enough context to judge meaning):**

- `ced1fc0535981101...`:

  > Application APP-330012 supports the Payment Reconciliation business service.
  > 
  > The Payment Reconciliation business service is governed by Obligation O-32.
  > 
  > Obligation O-32 is satisfied by Control C-77.
  > 
  > Control C-77 is implemented through Procedure P-301.
  > 
  > Procedure P-301 is the current operating procedure for reconciliation.

- **mechanical validation**: status=`accepted`, citation_valid=True, coherence=identity_subject
- **acceptance depends on an alias**: False
- **derived link that would result if accepted**: none (an endpoint resolves to no existing page key)

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `CLAIM::IDENT:O-32|8b2000480b7b2cf4b4b38e9f479e090137b3a978c6a7b0bfe421dbdb44322cec::claim2`

- **page**: O-32 (`IDENT:O-32`)
- **facet**: `IDENT:O-32|8b2000480b7b2cf4b4b38e9f479e090137b3a978c6a7b0bfe421dbdb44322cec` — ADJACENT-DOMAIN / adj_rev1
- **subject**: Obligation O-32
- **predicate**: is satisfied by
- **object**: Control C-77
- **claim_text**: Obligation O-32 is satisfied by Control C-77.
- **cites**: `ced1fc0535981101f44ecc6dd7cd00302d7f9d03d017735d9d360eb92a760011`
- **exact supporting quote(s)**: ['Obligation O-32 is satisfied by Control C-77.']
- **source_refs**: `{'ced1fc0535981101f44ecc6dd7cd00302d7f9d03d017735d9d360eb92a760011': [{'element_id': 'dcc0aad4c2d3c5ba46fed5a00d9e508701c843c1dfcd009fdbb6973ec1d8dcf5', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': '1a998dbc8e49642a4422c20ef7fcb4301f264e988351bc903f07edac8f69bab3', 'unit_index': 0, 'order_index': 3, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': 'e0e17914cf92ea3ec67d4b0479ab17940c5a9c88e58c42d52f3fde746a15e4b2', 'unit_index': 0, 'order_index': 4, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': '93401a943c035fac84276aae5a74de1c05763ef248736b09f4932894de7a83c9', 'unit_index': 0, 'order_index': 5, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': 'e732b7b01b0568ce1fb0bb86bbe79942922f392373699cf054b271be83c5687b', 'unit_index': 0, 'order_index': 6, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]}`

**Source passage (enough context to judge meaning):**

- `ced1fc0535981101...`:

  > Application APP-330012 supports the Payment Reconciliation business service.
  > 
  > The Payment Reconciliation business service is governed by Obligation O-32.
  > 
  > Obligation O-32 is satisfied by Control C-77.
  > 
  > Control C-77 is implemented through Procedure P-301.
  > 
  > Procedure P-301 is the current operating procedure for reconciliation.

- **mechanical validation**: status=`accepted`, citation_valid=True, coherence=identity_subject
- **acceptance depends on an alias**: False
- **derived link that would result if accepted**:
  - `IDENT:O-32` —*is satisfied by*→ `IDENT:C-77` (inverse)
  - `IDENT:O-32` —*is satisfied by*→ `IDENT:C-77` (forward)

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `CLAIM::IDENT:P-204|049930b3b215c7ad5fb5e8f1ea0b303a2111312f42293ebafa4336da9563d25b::claim1`

- **page**: P-204 (`IDENT:P-204`)
- **facet**: `IDENT:P-204|049930b3b215c7ad5fb5e8f1ea0b303a2111312f42293ebafa4336da9563d25b` — CONTROL-LIBRARY / ctl_rev1
- **subject**: Control C-88a
- **predicate**: is implemented through
- **object**: Procedure P-204
- **claim_text**: Control C-88a is implemented through Procedure P-204.
- **cites**: `dfca23730d4262d1947b10fc27e2357139a0ef7c6716a016fff70e89a32d461a`
- **exact supporting quote(s)**: ['Control C-88a is implemented through Procedure P-204.']
- **source_refs**: `{'dfca23730d4262d1947b10fc27e2357139a0ef7c6716a016fff70e89a32d461a': [{'element_id': '8e26839de1ff885561c0ebdc3197ee062120db0a684855d51ef508e556524bde', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]}`

**Source passage (enough context to judge meaning):**

- `dfca23730d4262d1...`:

  > Control C-88a is implemented through Procedure P-204.

- **mechanical validation**: status=`accepted`, citation_valid=True, coherence=identity_object
- **acceptance depends on an alias**: False
- **derived link that would result if accepted**:
  - `IDENT:C-88A` —*is implemented through*→ `IDENT:P-204` (forward)
  - `IDENT:C-88A` —*is implemented through*→ `IDENT:P-204` (inverse)

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `CLAIM::IDENT:P-204|27f1d2453664009f3eee76a12010b1bddf7be434343cbfbbb47cebe2900bacea::claim1`

- **page**: P-204 (`IDENT:P-204`)
- **facet**: `IDENT:P-204|27f1d2453664009f3eee76a12010b1bddf7be434343cbfbbb47cebe2900bacea` — PROCEDURE-CATALOGUE / prc_rev1
- **subject**: Procedure P-204
- **predicate**: is
- **object**: a retired operating procedure
- **claim_text**: Procedure P-204 is a retired operating procedure.
- **cites**: `cb11a682186470d08cb42d0ccb60029cca3974165bb2220d78d4636f21216ec1`
- **exact supporting quote(s)**: ['Procedure P-204 is a retired operating procedure.']
- **source_refs**: `{'cb11a682186470d08cb42d0ccb60029cca3974165bb2220d78d4636f21216ec1': [{'element_id': '1f854b5c7752ee97efec8ce36e64a603e1d0c1b671a925fd075e10951449b6d8', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]}`

**Source passage (enough context to judge meaning):**

- `cb11a682186470d0...`:

  > Procedure P-204 is a retired operating procedure.

- **mechanical validation**: status=`accepted`, citation_valid=True, coherence=identity_subject
- **acceptance depends on an alias**: False
- **derived link that would result if accepted**: none (an endpoint resolves to no existing page key)

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `CLAIM::IDENT:P-205|02827f19b5553859742110cbcffa8bdf01251d923399741bea8d5bf0bd9eff82::claim1`

- **page**: P-205 (`IDENT:P-205`)
- **facet**: `IDENT:P-205|02827f19b5553859742110cbcffa8bdf01251d923399741bea8d5bf0bd9eff82` — CONTROL-LIBRARY / ctl_rev3
- **subject**: Control C-91
- **predicate**: is implemented through
- **object**: Procedure P-205
- **claim_text**: Control C-91 is implemented through Procedure P-205.
- **cites**: `fac4d4cba8c743cb31248aaa614b1c8928b8c7a3fc4d1510c3c041b749a4c21c`
- **exact supporting quote(s)**: ['Control C-91 is implemented through Procedure P-205.']
- **source_refs**: `{'fac4d4cba8c743cb31248aaa614b1c8928b8c7a3fc4d1510c3c041b749a4c21c': [{'element_id': '60cb174e8ec1f58f08af943484d3eb6b1716aa30b555d8b8506db28af5a6a0d8', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]}`

**Source passage (enough context to judge meaning):**

- `fac4d4cba8c743cb...`:

  > Control C-91 is implemented through Procedure P-205.

- **mechanical validation**: status=`accepted`, citation_valid=True, coherence=identity_object
- **acceptance depends on an alias**: False
- **derived link that would result if accepted**:
  - `IDENT:C-91` —*is implemented through*→ `IDENT:P-205` (forward)
  - `IDENT:C-91` —*is implemented through*→ `IDENT:P-205` (inverse)

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `CLAIM::IDENT:P-205|1ccf46cdf6b68534932b46efff0fa5f15673b3934f7aa79ec05697ce0df68f23::claim1`

- **page**: P-205 (`IDENT:P-205`)
- **facet**: `IDENT:P-205|1ccf46cdf6b68534932b46efff0fa5f15673b3934f7aa79ec05697ce0df68f23` — CONTROL-LIBRARY / ctl_rev2
- **subject**: Control C-88
- **predicate**: is implemented through
- **object**: Procedure P-205
- **claim_text**: Control C-88 is implemented through Procedure P-205.
- **cites**: `57aae7e4f9ee474d03f50711d0d3a8c3bcdaa265b004afa582a6b6c48156b00d`
- **exact supporting quote(s)**: ['Control C-88 is implemented through Procedure P-205.']
- **source_refs**: `{'57aae7e4f9ee474d03f50711d0d3a8c3bcdaa265b004afa582a6b6c48156b00d': [{'element_id': 'cefd0b37349f50f3e1dc027e500a7aebeaa4e4fad92b06945f8f25815f374434', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]}`

**Source passage (enough context to judge meaning):**

- `57aae7e4f9ee474d...`:

  > Control C-88 is implemented through Procedure P-205.

- **mechanical validation**: status=`accepted`, citation_valid=True, coherence=identity_object
- **acceptance depends on an alias**: False
- **derived link that would result if accepted**:
  - `IDENT:C-88` —*is implemented through*→ `IDENT:P-205` (forward)
  - `IDENT:C-88` —*is implemented through*→ `IDENT:P-205` (inverse)

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `CLAIM::IDENT:P-205|cc8084b399bab8de5222c7b465033da3e77d1f85e38ccf94805d69a18126c0a4::claim1`

- **page**: P-205 (`IDENT:P-205`)
- **facet**: `IDENT:P-205|cc8084b399bab8de5222c7b465033da3e77d1f85e38ccf94805d69a18126c0a4` — PROCEDURE-CATALOGUE / prc_rev2
- **subject**: Procedure P-205
- **predicate**: is
- **object**: the current operating procedure
- **claim_text**: Procedure P-205 is the current operating procedure.
- **cites**: `1528d94345257125ba196f7c615f798a04f5844284c086338052f515d664eaeb`
- **exact supporting quote(s)**: ['Procedure P-205 is the current operating procedure.']
- **source_refs**: `{'1528d94345257125ba196f7c615f798a04f5844284c086338052f515d664eaeb': [{'element_id': 'fe6fa1fb6d0932d39ea4b0184d053844d4195280d9a670aa66f0911eaac2abc1', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]}`

**Source passage (enough context to judge meaning):**

- `1528d94345257125...`:

  > Procedure P-205 is the current operating procedure.

- **mechanical validation**: status=`accepted`, citation_valid=True, coherence=identity_subject
- **acceptance depends on an alias**: False
- **derived link that would result if accepted**: none (an endpoint resolves to no existing page key)

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `CLAIM::IDENT:P-301|8b2000480b7b2cf4b4b38e9f479e090137b3a978c6a7b0bfe421dbdb44322cec::claim1`

- **page**: P-301 (`IDENT:P-301`)
- **facet**: `IDENT:P-301|8b2000480b7b2cf4b4b38e9f479e090137b3a978c6a7b0bfe421dbdb44322cec` — ADJACENT-DOMAIN / adj_rev1
- **subject**: Obligation O-32
- **predicate**: is governed by
- **object**: Procedure P-301
- **claim_text**: Obligation O-32 is satisfied by Control C-77.
- **cites**: `ced1fc0535981101f44ecc6dd7cd00302d7f9d03d017735d9d360eb92a760011`
- **exact supporting quote(s)**: ['Obligation O-32 is satisfied by Control C-77.']
- **source_refs**: `{'ced1fc0535981101f44ecc6dd7cd00302d7f9d03d017735d9d360eb92a760011': [{'element_id': 'dcc0aad4c2d3c5ba46fed5a00d9e508701c843c1dfcd009fdbb6973ec1d8dcf5', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': '1a998dbc8e49642a4422c20ef7fcb4301f264e988351bc903f07edac8f69bab3', 'unit_index': 0, 'order_index': 3, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': 'e0e17914cf92ea3ec67d4b0479ab17940c5a9c88e58c42d52f3fde746a15e4b2', 'unit_index': 0, 'order_index': 4, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': '93401a943c035fac84276aae5a74de1c05763ef248736b09f4932894de7a83c9', 'unit_index': 0, 'order_index': 5, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': 'e732b7b01b0568ce1fb0bb86bbe79942922f392373699cf054b271be83c5687b', 'unit_index': 0, 'order_index': 6, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]}`

**Source passage (enough context to judge meaning):**

- `ced1fc0535981101...`:

  > Application APP-330012 supports the Payment Reconciliation business service.
  > 
  > The Payment Reconciliation business service is governed by Obligation O-32.
  > 
  > Obligation O-32 is satisfied by Control C-77.
  > 
  > Control C-77 is implemented through Procedure P-301.
  > 
  > Procedure P-301 is the current operating procedure for reconciliation.

- **mechanical validation**: status=`accepted`, citation_valid=True, coherence=identity_object
- **acceptance depends on an alias**: False
- **derived link that would result if accepted**:
  - `IDENT:O-32` —*is governed by*→ `IDENT:P-301` (inverse)
  - `IDENT:O-32` —*is governed by*→ `IDENT:P-301` (forward)

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `CLAIM::IDENT:P-301|8b2000480b7b2cf4b4b38e9f479e090137b3a978c6a7b0bfe421dbdb44322cec::claim2`

- **page**: P-301 (`IDENT:P-301`)
- **facet**: `IDENT:P-301|8b2000480b7b2cf4b4b38e9f479e090137b3a978c6a7b0bfe421dbdb44322cec` — ADJACENT-DOMAIN / adj_rev1
- **subject**: Control C-77
- **predicate**: is implemented through
- **object**: Procedure P-301
- **claim_text**: Control C-77 is implemented through Procedure P-301.
- **cites**: `ced1fc0535981101f44ecc6dd7cd00302d7f9d03d017735d9d360eb92a760011`
- **exact supporting quote(s)**: ['Control C-77 is implemented through Procedure P-301.']
- **source_refs**: `{'ced1fc0535981101f44ecc6dd7cd00302d7f9d03d017735d9d360eb92a760011': [{'element_id': 'dcc0aad4c2d3c5ba46fed5a00d9e508701c843c1dfcd009fdbb6973ec1d8dcf5', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': '1a998dbc8e49642a4422c20ef7fcb4301f264e988351bc903f07edac8f69bab3', 'unit_index': 0, 'order_index': 3, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': 'e0e17914cf92ea3ec67d4b0479ab17940c5a9c88e58c42d52f3fde746a15e4b2', 'unit_index': 0, 'order_index': 4, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': '93401a943c035fac84276aae5a74de1c05763ef248736b09f4932894de7a83c9', 'unit_index': 0, 'order_index': 5, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': 'e732b7b01b0568ce1fb0bb86bbe79942922f392373699cf054b271be83c5687b', 'unit_index': 0, 'order_index': 6, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]}`

**Source passage (enough context to judge meaning):**

- `ced1fc0535981101...`:

  > Application APP-330012 supports the Payment Reconciliation business service.
  > 
  > The Payment Reconciliation business service is governed by Obligation O-32.
  > 
  > Obligation O-32 is satisfied by Control C-77.
  > 
  > Control C-77 is implemented through Procedure P-301.
  > 
  > Procedure P-301 is the current operating procedure for reconciliation.

- **mechanical validation**: status=`accepted`, citation_valid=True, coherence=identity_object
- **acceptance depends on an alias**: False
- **derived link that would result if accepted**:
  - `IDENT:C-77` —*is implemented through*→ `IDENT:P-301` (forward)
  - `IDENT:C-77` —*is implemented through*→ `IDENT:P-301` (inverse)

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `CLAIM::IDENT:P-301|8b2000480b7b2cf4b4b38e9f479e090137b3a978c6a7b0bfe421dbdb44322cec::claim3`

- **page**: P-301 (`IDENT:P-301`)
- **facet**: `IDENT:P-301|8b2000480b7b2cf4b4b38e9f479e090137b3a978c6a7b0bfe421dbdb44322cec` — ADJACENT-DOMAIN / adj_rev1
- **subject**: Procedure P-301
- **predicate**: is the current operating procedure for
- **object**: reconciliation
- **claim_text**: Procedure P-301 is the current operating procedure for reconciliation.
- **cites**: `ced1fc0535981101f44ecc6dd7cd00302d7f9d03d017735d9d360eb92a760011`
- **exact supporting quote(s)**: ['Procedure P-301 is the current operating procedure for reconciliation.']
- **source_refs**: `{'ced1fc0535981101f44ecc6dd7cd00302d7f9d03d017735d9d360eb92a760011': [{'element_id': 'dcc0aad4c2d3c5ba46fed5a00d9e508701c843c1dfcd009fdbb6973ec1d8dcf5', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': '1a998dbc8e49642a4422c20ef7fcb4301f264e988351bc903f07edac8f69bab3', 'unit_index': 0, 'order_index': 3, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': 'e0e17914cf92ea3ec67d4b0479ab17940c5a9c88e58c42d52f3fde746a15e4b2', 'unit_index': 0, 'order_index': 4, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': '93401a943c035fac84276aae5a74de1c05763ef248736b09f4932894de7a83c9', 'unit_index': 0, 'order_index': 5, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}, {'element_id': 'e732b7b01b0568ce1fb0bb86bbe79942922f392373699cf054b271be83c5687b', 'unit_index': 0, 'order_index': 6, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]}`

**Source passage (enough context to judge meaning):**

- `ced1fc0535981101...`:

  > Application APP-330012 supports the Payment Reconciliation business service.
  > 
  > The Payment Reconciliation business service is governed by Obligation O-32.
  > 
  > Obligation O-32 is satisfied by Control C-77.
  > 
  > Control C-77 is implemented through Procedure P-301.
  > 
  > Procedure P-301 is the current operating procedure for reconciliation.

- **mechanical validation**: status=`accepted`, citation_valid=True, coherence=identity_subject
- **acceptance depends on an alias**: False
- **derived link that would result if accepted**: none (an endpoint resolves to no existing page key)

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `CLAIM::PHRASE:payment settlement|56a7b958d0522a0402a16bee101ad10b41e66297129f9cb988bb65b52735e868::claim1`

- **page**: Payment Settlement (`PHRASE:payment settlement`)
- **facet**: `PHRASE:payment settlement|56a7b958d0522a0402a16bee101ad10b41e66297129f9cb988bb65b52735e868` — SERVICE-CATALOGUE / svc_rev1
- **subject**: Payment Settlement
- **predicate**: is governed by
- **object**: Obligation O-31
- **claim_text**: Payment Settlement is governed by Obligation O-31.
- **cites**: `d00ddb9a8090249bd214a1ee50ac8b1fe5a1d7e307e4948048f3ab9ed2b44614`
- **exact supporting quote(s)**: ['The Payment Settlement business service is governed by Obligation O-31.']
- **source_refs**: `{'d00ddb9a8090249bd214a1ee50ac8b1fe5a1d7e307e4948048f3ab9ed2b44614': [{'element_id': '64c635750aad130b5b10ee9f74a3f4237314375b7fe64db6ff763af6080df978', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]}`

**Source passage (enough context to judge meaning):**

- `d00ddb9a8090249b...`:

  > The Payment Settlement business service is governed by Obligation O-31.

- **mechanical validation**: status=`accepted`, citation_valid=True, coherence=identity_subject
- **acceptance depends on an alias**: False
- **derived link that would result if accepted**:
  - `PHRASE:payment settlement` —*is governed by*→ `IDENT:O-31` (forward)
  - `PHRASE:payment settlement` —*is governed by*→ `IDENT:O-31` (inverse)

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `CLAIM::PHRASE:payment settlement|a6441298d656c12d1a36a4ce1367d4ef5cb5ca148ef02733c68f277b96e0657a::claim1`

- **page**: Payment Settlement (`PHRASE:payment settlement`)
- **facet**: `PHRASE:payment settlement|a6441298d656c12d1a36a4ce1367d4ef5cb5ca148ef02733c68f277b96e0657a` — APP-PORTFOLIO / app_rev2
- **subject**: Application APP-224510
- **predicate**: supports
- **object**: Payment Settlement
- **claim_text**: Application APP-224510 supports the Payment Settlement business service.
- **cites**: `2e409298eff569e23010445d05ffcd32b1276aacb0bc48525bf4a07cbcb1a8b2`
- **exact supporting quote(s)**: ['Application APP-224510 supports the Payment Settlement business service.']
- **source_refs**: `{'2e409298eff569e23010445d05ffcd32b1276aacb0bc48525bf4a07cbcb1a8b2': [{'element_id': 'b4f381a4e1458e7f56e4c4c25e9a179180c6c8fb653599ccded3a05b40db2ea7', 'unit_index': 0, 'order_index': 2, 'bbox': None, 'element_type': 'paragraph', 'fragment_index': None, 'start_char': None, 'end_char': None}]}`

**Source passage (enough context to judge meaning):**

- `2e409298eff569e2...`:

  > Application APP-224510 supports the Payment Settlement business service.

- **mechanical validation**: status=`accepted`, citation_valid=True, coherence=identity_object
- **acceptance depends on an alias**: False
- **derived link that would result if accepted**:
  - `IDENT:APP-224510` —*supports*→ `PHRASE:payment settlement` (forward)
  - `IDENT:APP-224510` —*supports*→ `PHRASE:payment settlement` (inverse)

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

---

## B. SUPPORTED ALIASES

_Alias span validity is not alias semantic correctness (SS4.5)._

### `ALIAS::IDENT:APP-224499|895467b2b856639286818a30384b0bea8e3b16b3068770ef1c70b0c97bd364da::0`

- **page identity**: APP-224499 (`APP-224499`)
- **revision**: app_rev1
- **alias text**: `APP-224499`
- **exact source occurrence(s)**: [{'chunk_id': '1a5af9b5351cdb8dd8b97af698c83c6208746b972fc6edc69d3b8bdc595dfac8', 'start_char': 12, 'end_char': 22, 'exact_text': 'APP-224499'}]

- context in `1a5af9b5351cdb8d...`:

  > Application APP-224499 supports the Payment Settlement business service.

- **mechanical span validity**: True (status=`supported`)
- **claims depending on this alias**: none

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `ALIAS::IDENT:APP-224510|a6441298d656c12d1a36a4ce1367d4ef5cb5ca148ef02733c68f277b96e0657a::0`

- **page identity**: APP-224510 (`APP-224510`)
- **revision**: app_rev2
- **alias text**: `APP-224510`
- **exact source occurrence(s)**: [{'chunk_id': '2e409298eff569e23010445d05ffcd32b1276aacb0bc48525bf4a07cbcb1a8b2', 'start_char': 12, 'end_char': 22, 'exact_text': 'APP-224510'}]

- context in `2e409298eff569e2...`:

  > Application APP-224510 supports the Payment Settlement business service.

- **mechanical span validity**: True (status=`supported`)
- **claims depending on this alias**: none

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `ALIAS::IDENT:APP-330012|8b2000480b7b2cf4b4b38e9f479e090137b3a978c6a7b0bfe421dbdb44322cec::0`

- **page identity**: APP-330012 (`APP-330012`)
- **revision**: adj_rev1
- **alias text**: `APP-330012`
- **exact source occurrence(s)**: [{'chunk_id': 'ced1fc0535981101f44ecc6dd7cd00302d7f9d03d017735d9d360eb92a760011', 'start_char': 12, 'end_char': 22, 'exact_text': 'APP-330012'}]

- context in `ced1fc0535981101...`:

  > Application APP-330012 supports the Payment Reconciliation business service.
  > 
  > The Payment Reconciliation business service is governed by Obligation O-32.
  > 
  > Obligation O-32 is satisfied by Control C-77.
  > 
  > Control C-77 is implemented through Procedure P-301.
  > 
  > Procedure P-301 is the current operating procedure for reconciliat...

- **mechanical span validity**: True (status=`supported`)
- **claims depending on this alias**: none

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `ALIAS::IDENT:C-77|8b2000480b7b2cf4b4b38e9f479e090137b3a978c6a7b0bfe421dbdb44322cec::0`

- **page identity**: C-77 (`C-77`)
- **revision**: adj_rev1
- **alias text**: `Control C-77`
- **exact source occurrence(s)**: [{'chunk_id': 'ced1fc0535981101f44ecc6dd7cd00302d7f9d03d017735d9d360eb92a760011', 'start_char': 187, 'end_char': 199, 'exact_text': 'Control C-77'}]

- context in `ced1fc0535981101...`:

  > Application APP-330012 supports the Payment Reconciliation business service.
  > 
  > The Payment Reconciliation business service is governed by Obligation O-32.
  > 
  > Obligation O-32 is satisfied by Control C-77.
  > 
  > Control C-77 is implemented through Procedure P-301.
  > 
  > Procedure P-301 is the current operating procedure for reconciliation.

- **mechanical span validity**: True (status=`supported`)
- **claims depending on this alias**: none

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `ALIAS::IDENT:C-88A|049930b3b215c7ad5fb5e8f1ea0b303a2111312f42293ebafa4336da9563d25b::0`

- **page identity**: C-88a (`C-88A`)
- **revision**: ctl_rev1
- **alias text**: `C-88a`
- **exact source occurrence(s)**: [{'chunk_id': 'dfca23730d4262d1947b10fc27e2357139a0ef7c6716a016fff70e89a32d461a', 'start_char': 8, 'end_char': 13, 'exact_text': 'C-88a'}]

- context in `dfca23730d4262d1...`:

  > Control C-88a is implemented through Procedure P-204.

- **mechanical span validity**: True (status=`supported`)
- **claims depending on this alias**: none

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `ALIAS::IDENT:C-88A|ad26ab9483b67f2540f5bd6da379c37887fd8762e5e966b46221274a6fe97689::0`

- **page identity**: C-88a (`C-88A`)
- **revision**: obl_rev1
- **alias text**: `Control C-88a`
- **exact source occurrence(s)**: [{'chunk_id': '54188cb210abf626030baa93b61a999b2db6018ab85fbc2592039ab7ddf4235a', 'start_char': 32, 'end_char': 45, 'exact_text': 'Control C-88a'}]

- context in `54188cb210abf626...`:

  > Obligation O-31 is satisfied by Control C-88a.

- **mechanical span validity**: True (status=`supported`)
- **claims depending on this alias**: none

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `ALIAS::IDENT:C-88|1ccf46cdf6b68534932b46efff0fa5f15673b3934f7aa79ec05697ce0df68f23::0`

- **page identity**: C-88 (`C-88`)
- **revision**: ctl_rev2
- **alias text**: `C-88`
- **exact source occurrence(s)**: [{'chunk_id': '57aae7e4f9ee474d03f50711d0d3a8c3bcdaa265b004afa582a6b6c48156b00d', 'start_char': 8, 'end_char': 12, 'exact_text': 'C-88'}]

- context in `57aae7e4f9ee474d...`:

  > Control C-88 is implemented through Procedure P-205.

- **mechanical span validity**: True (status=`supported`)
- **claims depending on this alias**: none

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `ALIAS::IDENT:C-88|7e11f49c9d7b8b53d319fa11b629c60ae00ed138d33fa4f50d1bf7415241d9cc::0`

- **page identity**: C-88 (`C-88`)
- **revision**: obl_rev2
- **alias text**: `Control C-88`
- **exact source occurrence(s)**: [{'chunk_id': '5f10b139bf62039fc587b84fa08f251fb9a2be835c1e5865b8d29c6f2c9196a8', 'start_char': 32, 'end_char': 44, 'exact_text': 'Control C-88'}]

- context in `5f10b139bf62039f...`:

  > Obligation O-31 is satisfied by Control C-88.

- **mechanical span validity**: True (status=`supported`)
- **claims depending on this alias**: none

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `ALIAS::IDENT:C-91|02827f19b5553859742110cbcffa8bdf01251d923399741bea8d5bf0bd9eff82::0`

- **page identity**: C-91 (`C-91`)
- **revision**: ctl_rev3
- **alias text**: `Control C-91`
- **exact source occurrence(s)**: [{'chunk_id': 'fac4d4cba8c743cb31248aaa614b1c8928b8c7a3fc4d1510c3c041b749a4c21c', 'start_char': 0, 'end_char': 12, 'exact_text': 'Control C-91'}]

- context in `fac4d4cba8c743cb...`:

  > Control C-91 is implemented through Procedure P-205.

- **mechanical span validity**: True (status=`supported`)
- **claims depending on this alias**: none

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `ALIAS::IDENT:O-31|56a7b958d0522a0402a16bee101ad10b41e66297129f9cb988bb65b52735e868::0`

- **page identity**: O-31 (`O-31`)
- **revision**: svc_rev1
- **alias text**: `Obligation O-31`
- **exact source occurrence(s)**: [{'chunk_id': 'd00ddb9a8090249bd214a1ee50ac8b1fe5a1d7e307e4948048f3ab9ed2b44614', 'start_char': 55, 'end_char': 70, 'exact_text': 'Obligation O-31'}]

- context in `d00ddb9a8090249b...`:

  > The Payment Settlement business service is governed by Obligation O-31.

- **mechanical span validity**: True (status=`supported`)
- **claims depending on this alias**: none

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `ALIAS::IDENT:O-31|7e11f49c9d7b8b53d319fa11b629c60ae00ed138d33fa4f50d1bf7415241d9cc::0`

- **page identity**: O-31 (`O-31`)
- **revision**: obl_rev2
- **alias text**: `Obligation O-31`
- **exact source occurrence(s)**: [{'chunk_id': '5f10b139bf62039fc587b84fa08f251fb9a2be835c1e5865b8d29c6f2c9196a8', 'start_char': 0, 'end_char': 15, 'exact_text': 'Obligation O-31'}]

- context in `5f10b139bf62039f...`:

  > Obligation O-31 is satisfied by Control C-88.

- **mechanical span validity**: True (status=`supported`)
- **claims depending on this alias**: none

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `ALIAS::IDENT:O-31|ad26ab9483b67f2540f5bd6da379c37887fd8762e5e966b46221274a6fe97689::0`

- **page identity**: O-31 (`O-31`)
- **revision**: obl_rev1
- **alias text**: `Obligation O-31`
- **exact source occurrence(s)**: [{'chunk_id': '54188cb210abf626030baa93b61a999b2db6018ab85fbc2592039ab7ddf4235a', 'start_char': 0, 'end_char': 15, 'exact_text': 'Obligation O-31'}]

- context in `54188cb210abf626...`:

  > Obligation O-31 is satisfied by Control C-88a.

- **mechanical span validity**: True (status=`supported`)
- **claims depending on this alias**: none

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `ALIAS::IDENT:O-32|8b2000480b7b2cf4b4b38e9f479e090137b3a978c6a7b0bfe421dbdb44322cec::0`

- **page identity**: O-32 (`O-32`)
- **revision**: adj_rev1
- **alias text**: `Obligation O-32`
- **exact source occurrence(s)**: [{'chunk_id': 'ced1fc0535981101f44ecc6dd7cd00302d7f9d03d017735d9d360eb92a760011', 'start_char': 137, 'end_char': 152, 'exact_text': 'Obligation O-32'}]

- context in `ced1fc0535981101...`:

  > Application APP-330012 supports the Payment Reconciliation business service.
  > 
  > The Payment Reconciliation business service is governed by Obligation O-32.
  > 
  > Obligation O-32 is satisfied by Control C-77.
  > 
  > Control C-77 is implemented through Procedure P-301.
  > 
  > Procedure P-301 is the current operating procedure for reconciliation.

- **mechanical span validity**: True (status=`supported`)
- **claims depending on this alias**: none

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `ALIAS::IDENT:P-204|049930b3b215c7ad5fb5e8f1ea0b303a2111312f42293ebafa4336da9563d25b::0`

- **page identity**: P-204 (`P-204`)
- **revision**: ctl_rev1
- **alias text**: `Procedure P-204`
- **exact source occurrence(s)**: [{'chunk_id': 'dfca23730d4262d1947b10fc27e2357139a0ef7c6716a016fff70e89a32d461a', 'start_char': 37, 'end_char': 52, 'exact_text': 'Procedure P-204'}]

- context in `dfca23730d4262d1...`:

  > Control C-88a is implemented through Procedure P-204.

- **mechanical span validity**: True (status=`supported`)
- **claims depending on this alias**: none

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `ALIAS::IDENT:P-204|27f1d2453664009f3eee76a12010b1bddf7be434343cbfbbb47cebe2900bacea::0`

- **page identity**: P-204 (`P-204`)
- **revision**: prc_rev1
- **alias text**: `Procedure P-204`
- **exact source occurrence(s)**: [{'chunk_id': 'cb11a682186470d08cb42d0ccb60029cca3974165bb2220d78d4636f21216ec1', 'start_char': 0, 'end_char': 15, 'exact_text': 'Procedure P-204'}]

- context in `cb11a682186470d0...`:

  > Procedure P-204 is a retired operating procedure.

- **mechanical span validity**: True (status=`supported`)
- **claims depending on this alias**: none

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `ALIAS::IDENT:P-205|02827f19b5553859742110cbcffa8bdf01251d923399741bea8d5bf0bd9eff82::0`

- **page identity**: P-205 (`P-205`)
- **revision**: ctl_rev3
- **alias text**: `Procedure P-205`
- **exact source occurrence(s)**: [{'chunk_id': 'fac4d4cba8c743cb31248aaa614b1c8928b8c7a3fc4d1510c3c041b749a4c21c', 'start_char': 36, 'end_char': 51, 'exact_text': 'Procedure P-205'}]

- context in `fac4d4cba8c743cb...`:

  > Control C-91 is implemented through Procedure P-205.

- **mechanical span validity**: True (status=`supported`)
- **claims depending on this alias**: none

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `ALIAS::IDENT:P-205|1ccf46cdf6b68534932b46efff0fa5f15673b3934f7aa79ec05697ce0df68f23::0`

- **page identity**: P-205 (`P-205`)
- **revision**: ctl_rev2
- **alias text**: `Procedure P-205`
- **exact source occurrence(s)**: [{'chunk_id': '57aae7e4f9ee474d03f50711d0d3a8c3bcdaa265b004afa582a6b6c48156b00d', 'start_char': 36, 'end_char': 51, 'exact_text': 'Procedure P-205'}]

- context in `57aae7e4f9ee474d...`:

  > Control C-88 is implemented through Procedure P-205.

- **mechanical span validity**: True (status=`supported`)
- **claims depending on this alias**: none

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `ALIAS::IDENT:P-205|cc8084b399bab8de5222c7b465033da3e77d1f85e38ccf94805d69a18126c0a4::0`

- **page identity**: P-205 (`P-205`)
- **revision**: prc_rev2
- **alias text**: `Procedure P-205`
- **exact source occurrence(s)**: [{'chunk_id': '1528d94345257125ba196f7c615f798a04f5844284c086338052f515d664eaeb', 'start_char': 0, 'end_char': 15, 'exact_text': 'Procedure P-205'}]

- context in `1528d94345257125...`:

  > Procedure P-205 is the current operating procedure.

- **mechanical span validity**: True (status=`supported`)
- **claims depending on this alias**: none

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `ALIAS::IDENT:P-301|8b2000480b7b2cf4b4b38e9f479e090137b3a978c6a7b0bfe421dbdb44322cec::0`

- **page identity**: P-301 (`P-301`)
- **revision**: adj_rev1
- **alias text**: `Procedure P-301`
- **exact source occurrence(s)**: [{'chunk_id': 'ced1fc0535981101f44ecc6dd7cd00302d7f9d03d017735d9d360eb92a760011', 'start_char': 238, 'end_char': 253, 'exact_text': 'Procedure P-301'}]

- context in `ced1fc0535981101...`:

  > Application APP-330012 supports the Payment Reconciliation business service.
  > 
  > The Payment Reconciliation business service is governed by Obligation O-32.
  > 
  > Obligation O-32 is satisfied by Control C-77.
  > 
  > Control C-77 is implemented through Procedure P-301.
  > 
  > Procedure P-301 is the current operating procedure for reconciliation.

- **mechanical span validity**: True (status=`supported`)
- **claims depending on this alias**: none

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `ALIAS::PHRASE:payment settlement|56a7b958d0522a0402a16bee101ad10b41e66297129f9cb988bb65b52735e868::0`

- **page identity**: Payment Settlement (`payment settlement`)
- **revision**: svc_rev1
- **alias text**: `Payment Settlement`
- **exact source occurrence(s)**: [{'chunk_id': 'd00ddb9a8090249bd214a1ee50ac8b1fe5a1d7e307e4948048f3ab9ed2b44614', 'start_char': 4, 'end_char': 22, 'exact_text': 'Payment Settlement'}]

- context in `d00ddb9a8090249b...`:

  > The Payment Settlement business service is governed by Obligation O-31.

- **mechanical span validity**: True (status=`supported`)
- **claims depending on this alias**: none

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `ALIAS::PHRASE:payment settlement|a6441298d656c12d1a36a4ce1367d4ef5cb5ca148ef02733c68f277b96e0657a::0`

- **page identity**: Payment Settlement (`payment settlement`)
- **revision**: app_rev2
- **alias text**: `Payment Settlement`
- **exact source occurrence(s)**: [{'chunk_id': '2e409298eff569e23010445d05ffcd32b1276aacb0bc48525bf4a07cbcb1a8b2', 'start_char': 36, 'end_char': 54, 'exact_text': 'Payment Settlement'}]

- context in `2e409298eff569e2...`:

  > Application APP-224510 supports the Payment Settlement business service.

- **mechanical span validity**: True (status=`supported`)
- **claims depending on this alias**: none

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

---

## C. SUMMARY SENTENCES

_Summary reference validity is not summary correctness (SS4.4). Look specifically for overstatement, direction inversion, unsupported composition, dropped qualification, and temporal/status distortion._

### `SUMMARY::IDENT:APP-224499|895467b2b856639286818a30384b0bea8e3b16b3068770ef1c70b0c97bd364da::sentence-1`

- **page**: APP-224499 (`IDENT:APP-224499`) — app_rev1
- **summary text**: APP-224499 supports the Payment Settlement business service (claim-1).
- **referenced claim ids**: ['claim-1']
- **referenced claims, in readable form**:
  - `claim-1` [accepted]: APP-224499 — *supports* → Payment Settlement business service
- **their exact source quotes**: ['Application APP-224499 supports the Payment Settlement business service.']

**Full facet source text:**

- `1a5af9b5351cdb8d...`:

  > Application APP-224499 supports the Payment Settlement business service.

- **mechanical reference validity**: True

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `SUMMARY::IDENT:APP-224510|a6441298d656c12d1a36a4ce1367d4ef5cb5ca148ef02733c68f277b96e0657a::summary-1`

- **page**: APP-224510 (`IDENT:APP-224510`) — app_rev2
- **summary text**: APP-224510 supports the Payment Settlement business service (claim-1).
- **referenced claim ids**: ['claim-1']
- **referenced claims, in readable form**:
  - `claim-1` [accepted]: APP-224510 — *supports* → the Payment Settlement business service
- **their exact source quotes**: ['Application APP-224510 supports the Payment Settlement business service.']

**Full facet source text:**

- `2e409298eff569e2...`:

  > Application APP-224510 supports the Payment Settlement business service.

- **mechanical reference validity**: True

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `SUMMARY::IDENT:APP-330012|8b2000480b7b2cf4b4b38e9f479e090137b3a978c6a7b0bfe421dbdb44322cec::summary1`

- **page**: APP-330012 (`IDENT:APP-330012`) — adj_rev1
- **summary text**: APP-330012 supports the Payment Reconciliation business service (claim1).
- **referenced claim ids**: ['claim1']
- **referenced claims, in readable form**:
  - `claim1` [accepted]: APP-330012 — *supports* → Payment Reconciliation business service
- **their exact source quotes**: ['Application APP-330012 supports the Payment Reconciliation business service.']

**Full facet source text:**

- `ced1fc0535981101...`:

  > Application APP-330012 supports the Payment Reconciliation business service.
  > 
  > The Payment Reconciliation business service is governed by Obligation O-32.
  > 
  > Obligation O-32 is satisfied by Control C-77.
  > 
  > Control C-77 is implemented through Procedure P-301.
  > 
  > Procedure P-301 is the current operating procedure for reconciliation.

- **mechanical reference validity**: True

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `SUMMARY::IDENT:C-77|8b2000480b7b2cf4b4b38e9f479e090137b3a978c6a7b0bfe421dbdb44322cec::summary1`

- **page**: C-77 (`IDENT:C-77`) — adj_rev1
- **summary text**: Obligation O-32 is satisfied by Control C-77, which is implemented through Procedure P-301.
- **referenced claim ids**: ['claim1', 'claim2']
- **referenced claims, in readable form**:
  - `claim1` [accepted]: Obligation O-32 — *is satisfied by* → Control C-77
  - `claim2` [accepted]: Control C-77 — *is implemented through* → Procedure P-301
- **their exact source quotes**: ['Obligation O-32 is satisfied by Control C-77.', 'Control C-77 is implemented through Procedure P-301.']

**Full facet source text:**

- `ced1fc0535981101...`:

  > Application APP-330012 supports the Payment Reconciliation business service.
  > 
  > The Payment Reconciliation business service is governed by Obligation O-32.
  > 
  > Obligation O-32 is satisfied by Control C-77.
  > 
  > Control C-77 is implemented through Procedure P-301.
  > 
  > Procedure P-301 is the current operating procedure for reconciliation.

- **mechanical reference validity**: True

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `SUMMARY::IDENT:C-88A|049930b3b215c7ad5fb5e8f1ea0b303a2111312f42293ebafa4336da9563d25b::summary1`

- **page**: C-88a (`IDENT:C-88A`) — ctl_rev1
- **summary text**: C-88a is implemented through Procedure P-204 (claim1).
- **referenced claim ids**: ['claim1']
- **referenced claims, in readable form**:
  - `claim1` [accepted]: C-88a — *is implemented through* → Procedure P-204
- **their exact source quotes**: ['Control C-88a is implemented through Procedure P-204.']

**Full facet source text:**

- `dfca23730d4262d1...`:

  > Control C-88a is implemented through Procedure P-204.

- **mechanical reference validity**: True

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `SUMMARY::IDENT:C-88A|ad26ab9483b67f2540f5bd6da379c37887fd8762e5e966b46221274a6fe97689::summary1`

- **page**: C-88a (`IDENT:C-88A`) — obl_rev1
- **summary text**: Obligation O-31 is satisfied by Control C-88a (claim1).
- **referenced claim ids**: ['claim1']
- **referenced claims, in readable form**:
  - `claim1` [accepted]: Obligation O-31 — *is satisfied by* → Control C-88a
- **their exact source quotes**: ['Obligation O-31 is satisfied by Control C-88a.']

**Full facet source text:**

- `54188cb210abf626...`:

  > Obligation O-31 is satisfied by Control C-88a.

- **mechanical reference validity**: True

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `SUMMARY::IDENT:C-88|1ccf46cdf6b68534932b46efff0fa5f15673b3934f7aa79ec05697ce0df68f23::summary1`

- **page**: C-88 (`IDENT:C-88`) — ctl_rev2
- **summary text**: C-88 is implemented through Procedure P-205 (claim1).
- **referenced claim ids**: ['claim1']
- **referenced claims, in readable form**:
  - `claim1` [accepted]: C-88 — *is implemented through* → Procedure P-205
- **their exact source quotes**: ['Control C-88 is implemented through Procedure P-205.']

**Full facet source text:**

- `57aae7e4f9ee474d...`:

  > Control C-88 is implemented through Procedure P-205.

- **mechanical reference validity**: True

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `SUMMARY::IDENT:C-88|7e11f49c9d7b8b53d319fa11b629c60ae00ed138d33fa4f50d1bf7415241d9cc::sentence1`

- **page**: C-88 (`IDENT:C-88`) — obl_rev2
- **summary text**: Control C-88 is satisfied by Obligation O-31 (claim1).
- **referenced claim ids**: ['claim1']
- **referenced claims, in readable form**:
  - `claim1` [accepted]: Control C-88 — *is satisfied by* → Obligation O-31
- **their exact source quotes**: ['Obligation O-31 is satisfied by Control C-88.']

**Full facet source text:**

- `5f10b139bf62039f...`:

  > Obligation O-31 is satisfied by Control C-88.

- **mechanical reference validity**: True

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `SUMMARY::IDENT:C-91|02827f19b5553859742110cbcffa8bdf01251d923399741bea8d5bf0bd9eff82::sentence1`

- **page**: C-91 (`IDENT:C-91`) — ctl_rev3
- **summary text**: Control C-91 is implemented through Procedure P-205 as stated in claim claim1.
- **referenced claim ids**: ['claim1']
- **referenced claims, in readable form**:
  - `claim1` [accepted]: Control C-91 — *is implemented through* → Procedure P-205
- **their exact source quotes**: ['Control C-91 is implemented through Procedure P-205.']

**Full facet source text:**

- `fac4d4cba8c743cb...`:

  > Control C-91 is implemented through Procedure P-205.

- **mechanical reference validity**: True

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `SUMMARY::IDENT:O-31|56a7b958d0522a0402a16bee101ad10b41e66297129f9cb988bb65b52735e868::summary1`

- **page**: O-31 (`IDENT:O-31`) — svc_rev1
- **summary text**: The Payment Settlement business service is governed by Obligation O-31 (claim1).
- **referenced claim ids**: ['claim1']
- **referenced claims, in readable form**:
  - `claim1` [accepted]: Payment Settlement business service — *is governed by* → Obligation O-31
- **their exact source quotes**: ['The Payment Settlement business service is governed by Obligation O-31.']

**Full facet source text:**

- `d00ddb9a8090249b...`:

  > The Payment Settlement business service is governed by Obligation O-31.

- **mechanical reference validity**: True

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `SUMMARY::IDENT:O-31|7e11f49c9d7b8b53d319fa11b629c60ae00ed138d33fa4f50d1bf7415241d9cc::summary1`

- **page**: O-31 (`IDENT:O-31`) — obl_rev2
- **summary text**: Obligation O-31 is satisfied by Control C-88 (claim1).
- **referenced claim ids**: ['claim1']
- **referenced claims, in readable form**:
  - `claim1` [accepted]: Obligation O-31 — *is satisfied by* → Control C-88
- **their exact source quotes**: ['Obligation O-31 is satisfied by Control C-88.']

**Full facet source text:**

- `5f10b139bf62039f...`:

  > Obligation O-31 is satisfied by Control C-88.

- **mechanical reference validity**: True

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `SUMMARY::IDENT:O-31|ad26ab9483b67f2540f5bd6da379c37887fd8762e5e966b46221274a6fe97689::summary1`

- **page**: O-31 (`IDENT:O-31`) — obl_rev1
- **summary text**: Obligation O-31 is satisfied by Control C-88a (claim1).
- **referenced claim ids**: ['claim1']
- **referenced claims, in readable form**:
  - `claim1` [accepted]: Obligation O-31 — *is satisfied by* → Control C-88a
- **their exact source quotes**: ['Obligation O-31 is satisfied by Control C-88a.']

**Full facet source text:**

- `54188cb210abf626...`:

  > Obligation O-31 is satisfied by Control C-88a.

- **mechanical reference validity**: True

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `SUMMARY::IDENT:O-32|8b2000480b7b2cf4b4b38e9f479e090137b3a978c6a7b0bfe421dbdb44322cec::summary1`

- **page**: O-32 (`IDENT:O-32`) — adj_rev1
- **summary text**: Obligation O-32 is governed by the Payment Reconciliation business service and is satisfied by Control C-77.
- **referenced claim ids**: ['claim1', 'claim2']
- **referenced claims, in readable form**:
  - `claim1` [accepted]: Obligation O-32 — *is governed by* → Payment Reconciliation business service
  - `claim2` [accepted]: Obligation O-32 — *is satisfied by* → Control C-77
- **their exact source quotes**: ['The Payment Reconciliation business service is governed by Obligation O-32.', 'Obligation O-32 is satisfied by Control C-77.']

**Full facet source text:**

- `ced1fc0535981101...`:

  > Application APP-330012 supports the Payment Reconciliation business service.
  > 
  > The Payment Reconciliation business service is governed by Obligation O-32.
  > 
  > Obligation O-32 is satisfied by Control C-77.
  > 
  > Control C-77 is implemented through Procedure P-301.
  > 
  > Procedure P-301 is the current operating procedure for reconciliation.

- **mechanical reference validity**: True

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `SUMMARY::IDENT:P-204|049930b3b215c7ad5fb5e8f1ea0b303a2111312f42293ebafa4336da9563d25b::summary1`

- **page**: P-204 (`IDENT:P-204`) — ctl_rev1
- **summary text**: Control C-88a is implemented through Procedure P-204 (claim1).
- **referenced claim ids**: ['claim1']
- **referenced claims, in readable form**:
  - `claim1` [accepted]: Control C-88a — *is implemented through* → Procedure P-204
- **their exact source quotes**: ['Control C-88a is implemented through Procedure P-204.']

**Full facet source text:**

- `dfca23730d4262d1...`:

  > Control C-88a is implemented through Procedure P-204.

- **mechanical reference validity**: True

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `SUMMARY::IDENT:P-204|27f1d2453664009f3eee76a12010b1bddf7be434343cbfbbb47cebe2900bacea::summary1`

- **page**: P-204 (`IDENT:P-204`) — prc_rev1
- **summary text**: Procedure P-204 is a retired operating procedure.
- **referenced claim ids**: ['claim1']
- **referenced claims, in readable form**:
  - `claim1` [accepted]: Procedure P-204 — *is* → a retired operating procedure
- **their exact source quotes**: ['Procedure P-204 is a retired operating procedure.']

**Full facet source text:**

- `cb11a682186470d0...`:

  > Procedure P-204 is a retired operating procedure.

- **mechanical reference validity**: True

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `SUMMARY::IDENT:P-205|02827f19b5553859742110cbcffa8bdf01251d923399741bea8d5bf0bd9eff82::sentence1`

- **page**: P-205 (`IDENT:P-205`) — ctl_rev3
- **summary text**: Control C-91 is implemented through Procedure P-205 as stated in the document.
- **referenced claim ids**: ['claim1']
- **referenced claims, in readable form**:
  - `claim1` [accepted]: Control C-91 — *is implemented through* → Procedure P-205
- **their exact source quotes**: ['Control C-91 is implemented through Procedure P-205.']

**Full facet source text:**

- `fac4d4cba8c743cb...`:

  > Control C-91 is implemented through Procedure P-205.

- **mechanical reference validity**: True

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `SUMMARY::IDENT:P-205|1ccf46cdf6b68534932b46efff0fa5f15673b3934f7aa79ec05697ce0df68f23::sentence1`

- **page**: P-205 (`IDENT:P-205`) — ctl_rev2
- **summary text**: Control C-88 is implemented through Procedure P-205 (claim1).
- **referenced claim ids**: ['claim1']
- **referenced claims, in readable form**:
  - `claim1` [accepted]: Control C-88 — *is implemented through* → Procedure P-205
- **their exact source quotes**: ['Control C-88 is implemented through Procedure P-205.']

**Full facet source text:**

- `57aae7e4f9ee474d...`:

  > Control C-88 is implemented through Procedure P-205.

- **mechanical reference validity**: True

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `SUMMARY::IDENT:P-205|cc8084b399bab8de5222c7b465033da3e77d1f85e38ccf94805d69a18126c0a4::summary1`

- **page**: P-205 (`IDENT:P-205`) — prc_rev2
- **summary text**: Procedure P-205 is identified as the current operating procedure.
- **referenced claim ids**: ['claim1']
- **referenced claims, in readable form**:
  - `claim1` [accepted]: Procedure P-205 — *is* → the current operating procedure
- **their exact source quotes**: ['Procedure P-205 is the current operating procedure.']

**Full facet source text:**

- `1528d94345257125...`:

  > Procedure P-205 is the current operating procedure.

- **mechanical reference validity**: True

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `SUMMARY::IDENT:P-301|8b2000480b7b2cf4b4b38e9f479e090137b3a978c6a7b0bfe421dbdb44322cec::summary1`

- **page**: P-301 (`IDENT:P-301`) — adj_rev1
- **summary text**: Procedure P-301 is the current operating procedure for reconciliation (claim3).
- **referenced claim ids**: ['claim3']
- **referenced claims, in readable form**:
  - `claim3` [accepted]: Procedure P-301 — *is the current operating procedure for* → reconciliation
- **their exact source quotes**: ['Procedure P-301 is the current operating procedure for reconciliation.']

**Full facet source text:**

- `ced1fc0535981101...`:

  > Application APP-330012 supports the Payment Reconciliation business service.
  > 
  > The Payment Reconciliation business service is governed by Obligation O-32.
  > 
  > Obligation O-32 is satisfied by Control C-77.
  > 
  > Control C-77 is implemented through Procedure P-301.
  > 
  > Procedure P-301 is the current operating procedure for reconciliation.

- **mechanical reference validity**: True

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `SUMMARY::PHRASE:payment settlement|56a7b958d0522a0402a16bee101ad10b41e66297129f9cb988bb65b52735e868::summary1`

- **page**: Payment Settlement (`PHRASE:payment settlement`) — svc_rev1
- **summary text**: Payment Settlement is governed by Obligation O-31 (claim1).
- **referenced claim ids**: ['claim1']
- **referenced claims, in readable form**:
  - `claim1` [accepted]: Payment Settlement — *is governed by* → Obligation O-31
- **their exact source quotes**: ['The Payment Settlement business service is governed by Obligation O-31.']

**Full facet source text:**

- `d00ddb9a8090249b...`:

  > The Payment Settlement business service is governed by Obligation O-31.

- **mechanical reference validity**: True

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `SUMMARY::PHRASE:payment settlement|895467b2b856639286818a30384b0bea8e3b16b3068770ef1c70b0c97bd364da::sentence_1`

- **page**: Payment Settlement (`PHRASE:payment settlement`) — app_rev1
- **summary text**: Application APP-224499 supports the Payment Settlement business service.
- **referenced claim ids**: ['claim_1']
- **referenced claims, in readable form**:
  - `claim_1` [out_of_page_scope]: Application APP-224499 — *supports* → Payment Settlement business service
- **their exact source quotes**: ['Application APP-224499 supports the Payment Settlement business service.']

**Full facet source text:**

- `1a5af9b5351cdb8d...`:

  > Application APP-224499 supports the Payment Settlement business service.

- **mechanical reference validity**: False
- **mechanical notes**: ['references no accepted claim on this facet']

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```

### `SUMMARY::PHRASE:payment settlement|a6441298d656c12d1a36a4ce1367d4ef5cb5ca148ef02733c68f277b96e0657a::sentence1`

- **page**: Payment Settlement (`PHRASE:payment settlement`) — app_rev2
- **summary text**: Application APP-224510 supports the Payment Settlement business service as stated in claim1.
- **referenced claim ids**: ['claim1']
- **referenced claims, in readable form**:
  - `claim1` [accepted]: Application APP-224510 — *supports* → Payment Settlement
- **their exact source quotes**: ['Application APP-224510 supports the Payment Settlement business service.']

**Full facet source text:**

- `2e409298eff569e2...`:

  > Application APP-224510 supports the Payment Settlement business service.

- **mechanical reference validity**: True

```
OWNER VERDICT (CORRECT / INCORRECT / UNVERIFIABLE):
OWNER REASON:
```
