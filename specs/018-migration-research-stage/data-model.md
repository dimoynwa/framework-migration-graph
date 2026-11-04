# Data Model: Migration Research Artifact (`research.md`)

This document defines the strict schema for the `research.md` artifact produced by `/migration-research` and consumed by `/migration-plan`.

## Artifact Structure

The artifact is structured as a Markdown file. No extraneous or "future use" fields are permitted.

### 1. Header Metadata
Read by: Plan Stage (Step 1.5 Detection), Gap-Check Stage (Provenance & Truncation check), Preview Stage (Display line)

| Field | Type | Required | Description / Consumer |
|-------|------|----------|-------------------------|
| `Framework` | string | Yes | Framework name (e.g., Spring Boot, Angular). Read by Plan (version validation). |
| `From` | string | Yes | Source version. Read by Plan (version validation). |
| `To` | string | Yes | Target version. Read by Plan (version validation). |
| `Generated` | ISO 8601 Date | Yes | Generation timestamp. Read by Plan (staleness check), Gap-Check (staleness), Preview (display). |
| `Scan checksum` | string (SHA-256)| Yes | SHA-256 hash of all scanned entity names. Read by Plan (checksum match). |
| `Entity count` | integer | Yes | Total number of entities scanned. |
| `Rule count` | integer | Yes | Total number of matched rules. |
| `Truncated` | boolean | Yes | True if results capped by `top_n`. Read by Plan (file emission), Gap-Check (consistency). |

### 2. Preconditions
Read by: Plan Stage (Step 6 - File Emission)

- **Format**: Markdown checklist
- **Description**: Version-map toolchain preconditions (e.g., Java version, Node version, Spring Cloud co-migration).

### 3. Rule Results (Per-Rule Result Blocks)
Read by: Plan Stage (Step 5 - Render Classification)

Each matched rule block MUST contain:

| Field | Type | Required | Description / Consumer |
|-------|------|----------|------------------------|
| `Rule ID` | string | Yes | Unique rule identifier. |
| `Rule Type` | string | Yes | e.g., `breaking`, `behavioral`, `deprecation`. Read by Plan (Ledger, tier logic). |
| `Statement` | string | Yes | Human-readable rule description. Read by Plan (Ledger, Task Instructions). |
| `Tier` | integer | Yes | Query tier (1-4). |
| `Scope` | string | Yes | e.g., `api-surface`, `runtime`. Read by Plan (Task order). |
| `Severity` | string | Yes | e.g., `high`, `medium`. Read by Plan (Task classification). |
| `Entity Classification`| string | Yes | `actionable` or `incomplete`. Read by Plan (Render classification). |
| `Applicability` | string | Yes | `matched`, `uncertain`, `universal`. Read by Plan (Render classification). |

#### 3.1. Matched Entities (Nested under Rule Block)
Read by: Plan Stage (Step 5 - Render Classification, Step 6 - Ledger)

The list of exact matched entity names (FQCN, property key, etc.). Each entity item MUST contain its granular deprecation chain data:

| Field | Type | Required | Description / Consumer |
|-------|------|----------|------------------------|
| `Entity Name` | string | Yes | The exact matched entity name. Read by Plan. |
| `Deprecated In` | string | No | Deprecation version. Read by Plan (Ledger/Bridge notes). |
| `Removed In` | string | No | Removal version. Read by Plan (Ledger/Bridge notes). |
| `Replaced By` | string | No | Replacement entity. Read by Plan (Ledger/Bridge notes). |
| `Chain Completeness`| string | Yes | `full`, `partial`, `none`. Read by Plan. |

#### 3.2. Steps (Nested under Rule Block)
Read by: Plan Stage (Step 5 - Render Classification, Step 6 - File Emission)

| Field | Type | Required | Description / Consumer |
|-------|------|----------|------------------------|
| `Step Type` | string | Yes | e.g., `rename`, `replace`, `remove`. Read by Plan (Render Classification). |
| `Instruction` | string | Yes | **Full step instruction text**. Essential for Render Classification (concrete vs generic). |
| `Before/After`| string | Yes | Code transformation examples. Value may be empty string when no example is available. Read by Plan (Emission). |
| `Effort` | string | Yes | e.g., `mechanical`, `architectural`. Read by Plan (Render classification). |
| `Automatable` | boolean | Yes | Whether the step can be automated. Read by Plan. |
| `Recipe` | string | No | Linked OpenRewrite recipe. Read by Plan (Emission). |
| `Escalation Notes`| string | No | Notes from escalation chain. Read by Plan. |

### 4. Dependency Resolutions (Paysafe)
Read by: Plan Stage (Step 6 - File Emission)

- **Format**: Table or list of `com.paysafe` dependencies.
- **Fields**: `Service Name`, `Target Version`, `Selected Version`, `Selection Strategy`, `Status` (ok/error), `Repo URL` (for docs/fixes), `Remediation Details` (for auth/transport errors).

### 5. Recipe Plan
Read by: Plan Stage (Step 6 - File Emission)

- **Format**: Table or list of discovered OpenRewrite recipes matching the version range.
