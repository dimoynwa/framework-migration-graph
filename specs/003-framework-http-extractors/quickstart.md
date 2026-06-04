# Quickstart: Framework HTTP Extractors

## Running a Single Extractor in Isolation

You can run a single extractor directly from Python to inspect its output:

```bash
uv run python -c "
import asyncio
from migration_oracle.pipeline.extractors import get_extractor

async def main():
    extractor = get_extractor('spring-boot')
    result = await extractor.extract('3.3.0', '3.4.0')
    print(f'Found {len(result.changes)} changes')

asyncio.run(main())
"
```

## Running the Full CLI (Dry Run)

To run the full pipeline for a framework without writing to the database:

```bash
uv run python -m migration_oracle.cli export-extract-populate-framework \
  --framework spring-boot 3.3.0 3.4.0 --dry-run
```

## Running Tests

To run the tests specifically for the extractors:

```bash
uv run pytest tests/extractors/ -v
```

## Environment Variables

- **Real HTTP Calls**:
  - `GITHUB_TOKEN`: (Optional) Used to increase rate limits for GitHub API calls.
  - `SSL_VERIFY`: Set to `False` to disable certificate validation (default is `True`).
  - `JIRA_MAX_CONCURRENT`: Controls concurrent Jira requests (default `4`).
- **Mocked Tests**:
  - No specific environment variables are required for mocked tests, as the HTTP client will be patched or mocked using `pytest-httpx` or `respx`.
