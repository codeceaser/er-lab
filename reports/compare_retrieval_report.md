# Retrieval Comparison Report

Generated: 2026-07-20 16:04:59

## Q1: What is the BCP impact of CRA-176046 going down?

### 1. Vector-only retrieved chunks

| Score | Document | Chunk text |
|---|---|---|
| 0.4714 | BCP Policy 2026 | Control C-77 mandates BCP Procedure P-100 for critical compliance applications. Procedure P-100 requires manual recovery steps and continuity validation before business restoration. |
| 0.3463 | CRA Application Declaration | Application CRA-176046 supports the Compliance Risk Assessment service. CRA-176046 is in scope for Regulatory Obligation O-22. |

**2. Did vector-only find PROC_P100 / DOC_003?** YES

### 3. Graph artifact matches (seeds)

| Score | Type | Artifact text |
|---|---|---|
| 0.5391 | single_edge | BCPProcedure BCP Procedure P-100 DEFINED_IN BCP Policy 2026. Evidence: Procedure P-100 requires manual recovery steps and continuity validation before business restoration. |
| 0.4915 | entity | Document BCP Policy 2026. Aliases: BCP Policy. |
| 0.4764 | single_edge | Control Control C-77 MANDATES BCP Procedure P-100. Evidence: Control C-77 mandates BCP Procedure P-100 for critical compliance applications. |
| 0.4371 | entity | BCPProcedure BCP Procedure P-100. Aliases: Procedure P-100. |
| 0.3841 | single_edge | Application CRA-176046 IN_SCOPE_FOR Regulatory Obligation O-22. Evidence: CRA-176046 is in scope for Regulatory Obligation O-22. |

### 4. Discovered graph lineage paths (via query-time expansion)

- BCP Procedure P-100 --[DEFINED_IN]--> BCP Policy 2026
- BCP Procedure P-100 --[MANDATES]--> Control C-77 --[SATISFIED_BY]--> Regulatory Obligation O-22 --[IN_SCOPE_FOR]--> CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment
- Control C-77 --[MANDATES]--> BCP Procedure P-100 --[DEFINED_IN]--> BCP Policy 2026
- Control C-77 --[SATISFIED_BY]--> Regulatory Obligation O-22 --[IN_SCOPE_FOR]--> CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[OWNED_BY]--> Compliance Risk Team
- Control C-77 --[SATISFIED_BY]--> Regulatory Obligation O-22 --[IN_SCOPE_FOR]--> CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[OPERATES_IN]--> APAC
- Control C-77 --[SATISFIED_BY]--> Regulatory Obligation O-22 --[IN_SCOPE_FOR]--> CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[HAS_RTO]--> RTO 4 hours
- BCP Policy 2026 --[DEFINED_IN]--> BCP Procedure P-100 --[MANDATES]--> Control C-77 --[SATISFIED_BY]--> Regulatory Obligation O-22 --[IN_SCOPE_FOR]--> CRA-176046
- Regulatory Obligation O-22 --[IN_SCOPE_FOR]--> CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[OWNED_BY]--> Compliance Risk Team
- Regulatory Obligation O-22 --[IN_SCOPE_FOR]--> CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[OPERATES_IN]--> APAC
- Regulatory Obligation O-22 --[IN_SCOPE_FOR]--> CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[HAS_RTO]--> RTO 4 hours
- Regulatory Obligation O-22 --[SATISFIED_BY]--> Control C-77 --[MANDATES]--> BCP Procedure P-100 --[DEFINED_IN]--> BCP Policy 2026
- CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[OWNED_BY]--> Compliance Risk Team
- CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[OPERATES_IN]--> APAC
- CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[HAS_RTO]--> RTO 4 hours
- CRA-176046 --[IN_SCOPE_FOR]--> Regulatory Obligation O-22 --[SATISFIED_BY]--> Control C-77 --[MANDATES]--> BCP Procedure P-100 --[DEFINED_IN]--> BCP Policy 2026

**5. Did graph-enriched find PROC_P100 / DOC_003?** YES

**6. Result:** FAIL (vector-only also found it (no gap demonstrated))

## Q2: If application 176046 is unavailable, what downstream resilience requirement should be reviewed?

### 1. Vector-only retrieved chunks

| Score | Document | Chunk text |
|---|---|---|
| 0.4664 | CRA Application Declaration | Application CRA-176046 supports the Compliance Risk Assessment service. CRA-176046 is in scope for Regulatory Obligation O-22. |
| 0.3523 | Regulatory Control Mapping | Regulatory Obligation O-22 is satisfied by Control C-77. O-22 requires continuity controls for critical compliance risk assessment services. |

**2. Did vector-only find PROC_P100 / DOC_003?** NO

### 3. Graph artifact matches (seeds)

| Score | Type | Artifact text |
|---|---|---|
| 0.4301 | single_edge | Application CRA-176046 IN_SCOPE_FOR Regulatory Obligation O-22. Evidence: CRA-176046 is in scope for Regulatory Obligation O-22. |
| 0.4174 | single_edge | Application CRA-176046 SUPPORTS Compliance Risk Assessment. Evidence: Application CRA-176046 supports the Compliance Risk Assessment service. |
| 0.3011 | single_edge | BusinessService Compliance Risk Assessment OPERATES_IN APAC. Evidence: The service operates in APAC and has an RTO of 4 hours. |
| 0.2935 | entity | BusinessService Compliance Risk Assessment. Aliases: Compliance Risk Assessment service. |
| 0.2883 | single_edge | BCPProcedure BCP Procedure P-100 DEFINED_IN BCP Policy 2026. Evidence: Procedure P-100 requires manual recovery steps and continuity validation before business restoration. |

### 4. Discovered graph lineage paths (via query-time expansion)

- BCP Procedure P-100 --[DEFINED_IN]--> BCP Policy 2026
- BCP Procedure P-100 --[MANDATES]--> Control C-77 --[SATISFIED_BY]--> Regulatory Obligation O-22 --[IN_SCOPE_FOR]--> CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment
- APAC --[OPERATES_IN]--> Compliance Risk Assessment --[OWNED_BY]--> Compliance Risk Team
- APAC --[OPERATES_IN]--> Compliance Risk Assessment --[HAS_RTO]--> RTO 4 hours
- APAC --[OPERATES_IN]--> Compliance Risk Assessment --[SUPPORTS]--> CRA-176046 --[IN_SCOPE_FOR]--> Regulatory Obligation O-22 --[SATISFIED_BY]--> Control C-77
- BCP Policy 2026 --[DEFINED_IN]--> BCP Procedure P-100 --[MANDATES]--> Control C-77 --[SATISFIED_BY]--> Regulatory Obligation O-22 --[IN_SCOPE_FOR]--> CRA-176046
- Regulatory Obligation O-22 --[IN_SCOPE_FOR]--> CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[OWNED_BY]--> Compliance Risk Team
- Regulatory Obligation O-22 --[IN_SCOPE_FOR]--> CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[OPERATES_IN]--> APAC
- Regulatory Obligation O-22 --[IN_SCOPE_FOR]--> CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[HAS_RTO]--> RTO 4 hours
- Regulatory Obligation O-22 --[SATISFIED_BY]--> Control C-77 --[MANDATES]--> BCP Procedure P-100 --[DEFINED_IN]--> BCP Policy 2026
- CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[OWNED_BY]--> Compliance Risk Team
- CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[OPERATES_IN]--> APAC
- CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[HAS_RTO]--> RTO 4 hours
- CRA-176046 --[IN_SCOPE_FOR]--> Regulatory Obligation O-22 --[SATISFIED_BY]--> Control C-77 --[MANDATES]--> BCP Procedure P-100 --[DEFINED_IN]--> BCP Policy 2026
- Compliance Risk Assessment --[OWNED_BY]--> Compliance Risk Team
- Compliance Risk Assessment --[OPERATES_IN]--> APAC
- Compliance Risk Assessment --[HAS_RTO]--> RTO 4 hours
- Compliance Risk Assessment --[SUPPORTS]--> CRA-176046 --[IN_SCOPE_FOR]--> Regulatory Obligation O-22 --[SATISFIED_BY]--> Control C-77 --[MANDATES]--> BCP Procedure P-100

**5. Did graph-enriched find PROC_P100 / DOC_003?** YES

**6. Result:** PASS (graph-enriched found it, vector-only missed it)

## Q3: If CRA-176046 fails, which recovery procedure becomes relevant through its regulatory/control dependency chain?

### 1. Vector-only retrieved chunks

| Score | Document | Chunk text |
|---|---|---|
| 0.5138 | CRA Application Declaration | Application CRA-176046 supports the Compliance Risk Assessment service. CRA-176046 is in scope for Regulatory Obligation O-22. |
| 0.4721 | BCP Policy 2026 | Control C-77 mandates BCP Procedure P-100 for critical compliance applications. Procedure P-100 requires manual recovery steps and continuity validation before business restoration. |

**2. Did vector-only find PROC_P100 / DOC_003?** YES

### 3. Graph artifact matches (seeds)

| Score | Type | Artifact text |
|---|---|---|
| 0.4863 | single_edge | Application CRA-176046 IN_SCOPE_FOR Regulatory Obligation O-22. Evidence: CRA-176046 is in scope for Regulatory Obligation O-22. |
| 0.4694 | single_edge | Application CRA-176046 SUPPORTS Compliance Risk Assessment. Evidence: Application CRA-176046 supports the Compliance Risk Assessment service. |
| 0.4474 | single_edge | BCPProcedure BCP Procedure P-100 DEFINED_IN BCP Policy 2026. Evidence: Procedure P-100 requires manual recovery steps and continuity validation before business restoration. |
| 0.3842 | single_edge | Control Control C-77 MANDATES BCP Procedure P-100. Evidence: Control C-77 mandates BCP Procedure P-100 for critical compliance applications. |
| 0.3681 | entity | Application CRA-176046. Aliases: CRA, application 176046. |

### 4. Discovered graph lineage paths (via query-time expansion)

- BCP Procedure P-100 --[DEFINED_IN]--> BCP Policy 2026
- BCP Procedure P-100 --[MANDATES]--> Control C-77 --[SATISFIED_BY]--> Regulatory Obligation O-22 --[IN_SCOPE_FOR]--> CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment
- Control C-77 --[MANDATES]--> BCP Procedure P-100 --[DEFINED_IN]--> BCP Policy 2026
- Control C-77 --[SATISFIED_BY]--> Regulatory Obligation O-22 --[IN_SCOPE_FOR]--> CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[OWNED_BY]--> Compliance Risk Team
- Control C-77 --[SATISFIED_BY]--> Regulatory Obligation O-22 --[IN_SCOPE_FOR]--> CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[OPERATES_IN]--> APAC
- Control C-77 --[SATISFIED_BY]--> Regulatory Obligation O-22 --[IN_SCOPE_FOR]--> CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[HAS_RTO]--> RTO 4 hours
- BCP Policy 2026 --[DEFINED_IN]--> BCP Procedure P-100 --[MANDATES]--> Control C-77 --[SATISFIED_BY]--> Regulatory Obligation O-22 --[IN_SCOPE_FOR]--> CRA-176046
- Regulatory Obligation O-22 --[IN_SCOPE_FOR]--> CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[OWNED_BY]--> Compliance Risk Team
- Regulatory Obligation O-22 --[IN_SCOPE_FOR]--> CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[OPERATES_IN]--> APAC
- Regulatory Obligation O-22 --[IN_SCOPE_FOR]--> CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[HAS_RTO]--> RTO 4 hours
- Regulatory Obligation O-22 --[SATISFIED_BY]--> Control C-77 --[MANDATES]--> BCP Procedure P-100 --[DEFINED_IN]--> BCP Policy 2026
- CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[OWNED_BY]--> Compliance Risk Team
- CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[OPERATES_IN]--> APAC
- CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[HAS_RTO]--> RTO 4 hours
- CRA-176046 --[IN_SCOPE_FOR]--> Regulatory Obligation O-22 --[SATISFIED_BY]--> Control C-77 --[MANDATES]--> BCP Procedure P-100 --[DEFINED_IN]--> BCP Policy 2026
- Compliance Risk Assessment --[OWNED_BY]--> Compliance Risk Team
- Compliance Risk Assessment --[OPERATES_IN]--> APAC
- Compliance Risk Assessment --[HAS_RTO]--> RTO 4 hours
- Compliance Risk Assessment --[SUPPORTS]--> CRA-176046 --[IN_SCOPE_FOR]--> Regulatory Obligation O-22 --[SATISFIED_BY]--> Control C-77 --[MANDATES]--> BCP Procedure P-100

**5. Did graph-enriched find PROC_P100 / DOC_003?** YES

**6. Result:** FAIL (vector-only also found it (no gap demonstrated))

## Q4: For an outage of application 176046, trace the related obligation, control, and procedure.

### 1. Vector-only retrieved chunks

| Score | Document | Chunk text |
|---|---|---|
| 0.5452 | CRA Application Declaration | Application CRA-176046 supports the Compliance Risk Assessment service. CRA-176046 is in scope for Regulatory Obligation O-22. |
| 0.4624 | Regulatory Control Mapping | Regulatory Obligation O-22 is satisfied by Control C-77. O-22 requires continuity controls for critical compliance risk assessment services. |

**2. Did vector-only find PROC_P100 / DOC_003?** NO

### 3. Graph artifact matches (seeds)

| Score | Type | Artifact text |
|---|---|---|
| 0.5952 | single_edge | Application CRA-176046 IN_SCOPE_FOR Regulatory Obligation O-22. Evidence: CRA-176046 is in scope for Regulatory Obligation O-22. |
| 0.4672 | single_edge | RegulatoryObligation Regulatory Obligation O-22 SATISFIED_BY Control C-77. Evidence: Regulatory Obligation O-22 is satisfied by Control C-77. |
| 0.4470 | entity | RegulatoryObligation Regulatory Obligation O-22. Aliases: O-22. |
| 0.4208 | single_edge | Application CRA-176046 SUPPORTS Compliance Risk Assessment. Evidence: Application CRA-176046 supports the Compliance Risk Assessment service. |
| 0.4028 | single_edge | BCPProcedure BCP Procedure P-100 DEFINED_IN BCP Policy 2026. Evidence: Procedure P-100 requires manual recovery steps and continuity validation before business restoration. |

### 4. Discovered graph lineage paths (via query-time expansion)

- BCP Procedure P-100 --[DEFINED_IN]--> BCP Policy 2026
- BCP Procedure P-100 --[MANDATES]--> Control C-77 --[SATISFIED_BY]--> Regulatory Obligation O-22 --[IN_SCOPE_FOR]--> CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment
- Control C-77 --[MANDATES]--> BCP Procedure P-100 --[DEFINED_IN]--> BCP Policy 2026
- Control C-77 --[SATISFIED_BY]--> Regulatory Obligation O-22 --[IN_SCOPE_FOR]--> CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[OWNED_BY]--> Compliance Risk Team
- Control C-77 --[SATISFIED_BY]--> Regulatory Obligation O-22 --[IN_SCOPE_FOR]--> CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[OPERATES_IN]--> APAC
- Control C-77 --[SATISFIED_BY]--> Regulatory Obligation O-22 --[IN_SCOPE_FOR]--> CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[HAS_RTO]--> RTO 4 hours
- BCP Policy 2026 --[DEFINED_IN]--> BCP Procedure P-100 --[MANDATES]--> Control C-77 --[SATISFIED_BY]--> Regulatory Obligation O-22 --[IN_SCOPE_FOR]--> CRA-176046
- Regulatory Obligation O-22 --[IN_SCOPE_FOR]--> CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[OWNED_BY]--> Compliance Risk Team
- Regulatory Obligation O-22 --[IN_SCOPE_FOR]--> CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[OPERATES_IN]--> APAC
- Regulatory Obligation O-22 --[IN_SCOPE_FOR]--> CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[HAS_RTO]--> RTO 4 hours
- Regulatory Obligation O-22 --[SATISFIED_BY]--> Control C-77 --[MANDATES]--> BCP Procedure P-100 --[DEFINED_IN]--> BCP Policy 2026
- CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[OWNED_BY]--> Compliance Risk Team
- CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[OPERATES_IN]--> APAC
- CRA-176046 --[SUPPORTS]--> Compliance Risk Assessment --[HAS_RTO]--> RTO 4 hours
- CRA-176046 --[IN_SCOPE_FOR]--> Regulatory Obligation O-22 --[SATISFIED_BY]--> Control C-77 --[MANDATES]--> BCP Procedure P-100 --[DEFINED_IN]--> BCP Policy 2026
- Compliance Risk Assessment --[OWNED_BY]--> Compliance Risk Team
- Compliance Risk Assessment --[OPERATES_IN]--> APAC
- Compliance Risk Assessment --[HAS_RTO]--> RTO 4 hours
- Compliance Risk Assessment --[SUPPORTS]--> CRA-176046 --[IN_SCOPE_FOR]--> Regulatory Obligation O-22 --[SATISFIED_BY]--> Control C-77 --[MANDATES]--> BCP Procedure P-100

**5. Did graph-enriched find PROC_P100 / DOC_003?** YES

**6. Result:** PASS (graph-enriched found it, vector-only missed it)

## Evaluation summary

| Question | Vector found P-100 | Graph found P-100 | Graph lineage found | Result |
|---|---|---|---|---|
| Q1 | YES | YES | YES | FAIL |
| Q2 | NO | YES | YES | PASS |
| Q3 | YES | YES | YES | FAIL |
| Q4 | NO | YES | YES | PASS |
