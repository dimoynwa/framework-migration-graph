# Data Model: Framework HTTP Extractors

## Entities

### `DocumentedChange`

Represents a single documented change from a framework release or migration guide. This type is defined in `migration_oracle/models/entities.py` (established in `001-pipeline-core`). Adding `metadata: dict | None = None` is a backward-compatible amendment. The implementation task for this field must edit `models/entities.py` directly.

- **Fields**:
  - `type` (str): The classification of the change. Allowed values: `breaking`, `mandatory_migration`, `deprecation`, `dependency_upgrade`, `behavioral`, `potential_breaking`.
  - `confidence` (str): The confidence level of the extraction. Allowed values: `confirmed`, `inferred`.
  - `source_url` (str): The URL where the change was documented.
  - `statement` (str): The text describing the change.
  - `metadata` (dict | None): Optional metadata dictionary to store properties like `stability_level`. Default is `None`.

### `ExtractionResult`

Wraps the extraction output returned by `BaseExtractor.extract()`. This type lives in `migration_oracle/models/entities.py`.

- **Fields**:
  - `changes` (list[DocumentedChange]): The list of extracted changes.
  - `metadata` (dict): Metadata dictionary; empty `{}` when no framework-specific metadata is present. Used for framework-specific data like BOM diffs (Spring Boot) and blog insights (Angular). Default is `Field(default_factory=dict)`.

### `WildFlyJiraEntry`

Represents a single Jira issue fetched during WildFly enrichment.

```python
from typing import TypedDict

class WildFlyJiraEntry(TypedDict):
    summary: str
    source_url: str
    issue_type: str
    description: str
```

### `WildFlyJiraIndex`

The in-memory structure built by the Jira enrichment step for WildFly.

- **Type**: `dict[str, WildFlyJiraEntry]`
- **Structure**: Maps issue key (e.g., `WFLY-1234`) to a `WildFlyJiraEntry`.

### `EAPVersionEntry`

The fixed-table row used by the EAP extractor to map versions.

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class EAPVersionEntry:
    eap_version: str
    slug: str
    wildfly_base: str
```

### `JakartaEENamespaceMapping`

The static mapping used by the Jakarta EE extractor.

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class JakartaEENamespaceMapping:
    javax_package: str
    jakarta_package: str
    spec_version: str
```

## Storage / Cache Key Formats

The URL-level cache in `BaseExtractor` uses `dict[str, str | bytes]`. The cache key is the raw URL string exactly as requested — unmodified, with no normalisation or stripping of trailing slashes or query parameters. This is the explicit contract between `base.py`'s cache writer and any extractor that reads from it.
