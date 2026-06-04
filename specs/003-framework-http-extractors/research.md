# Research: Framework HTTP Extractors

## AsciiDoc Parser for Hibernate

- **Decision**: Use a custom pure-Python regex-based approach.
- **Rationale**: The `asciidoc` CLI tool is not available in the execution environment, and there is no robust, actively maintained pure-Python AsciiDoc library that fits our needs without adding significant bloat. Given the highly structured and predictable nature of the Hibernate migration guides (specific heading levels and list formats), a custom regex-based extractor is the most reliable and lightweight solution.
- **Alternatives considered**: Using the `asciidoc` CLI tool (rejected because it's not available in the environment) or a third-party Python AsciiDoc parser (rejected due to lack of a clear, standard, lightweight option).

## HTTP Client for Concurrency (WildFly Jira Enrichment)

- **Decision**: Use `httpx.AsyncClient` with `anyio` (or `asyncio`) event loop.
- **Rationale**: `httpx` is already the standard HTTP client for the pipeline. Using `httpx.AsyncClient` allows for efficient concurrent fetches during WildFly Jira enrichment. We will use `anyio.create_task_group` (or `asyncio.gather`) to manage up to `JIRA_MAX_CONCURRENT` concurrent fetches.
- **Alternatives considered**: `aiohttp` (rejected to avoid introducing a second HTTP client library when `httpx` already supports async).

## Maven Metadata XML Parsing

- **Decision**: Use the standard library `xml.etree.ElementTree`.
- **Rationale**: It is built-in and avoids adding external dependencies like `lxml`. To handle namespace-qualified XML from Maven Central mirrors robustly, implementations must strip or ignore namespaces when searching for the `<version>` elements within `<versioning><versions>`.
- **Alternatives considered**: `lxml` (rejected because it introduces an extra C-extension dependency, which is unnecessary for simple XML parsing).

## BeautifulSoup Parser Backend

- **Decision**: Use `html.parser`.
- **Rationale**: `html.parser` is part of the Python standard library, meaning no extra dependencies are required. Given the moderate document sizes of the EAP migration guides and release notes, the performance of `html.parser` is completely sufficient.
- **Alternatives considered**: `lxml` (rejected because it introduces an extra C-extension dependency, which is unnecessary for our moderate parsing needs).
