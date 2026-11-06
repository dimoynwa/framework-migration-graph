"""Environment configuration loaded at import time."""

import os


class ConfigurationError(ValueError):
    """Raised when a required environment variable is missing or invalid."""


def _require(name: str) -> str:
    value = os.environ.get(name)
    if value is None or value == "":
        raise ConfigurationError(f"Required env var {name!r} is not set")
    return value


def _optional(name: str, default: str) -> str:
    value = os.environ.get(name)
    if value is None:
        return default
    return value


def _parse_ssl_verify(raw: str) -> bool:
    if raw in ("false", "False", "FALSE", "0"):
        return False
    return True


NEO4J_URI: str = _require("NEO4J_URI")
NEO4J_USERNAME: str = _optional("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD: str = _require("NEO4J_PASSWORD")
MODEL_PROVIDER: str = _optional("MODEL_PROVIDER", "anthropic")
MODEL_ID: str = _optional("MODEL_ID", "")
OPENAI_BASE_URL: str = _optional("OPENAI_BASE_URL", "")
LITELLM_BASE_URL: str = _optional("LITELLM_BASE_URL", "")
OLLAMA_HOST: str = _optional("OLLAMA_HOST", "http://localhost:11434")
AWS_REGION: str = _optional("AWS_REGION", "eu-central-1")
GITHUB_TOKEN: str = _optional("GITHUB_TOKEN", "")
FINDIT_AUTH_TOKEN: str = _optional("FINDIT_AUTH_TOKEN", "")
FINDIT_BASE_URL: str = _optional("FINDIT_BASE_URL", "https://findit-api.icd.paysafe.cloud")
GITLAB_API_KEY: str = _optional("GITLAB_API_KEY", "")
SENTENCE_TRANSFORMERS_MODEL: str = _optional(
    "SENTENCE_TRANSFORMERS_MODEL", "all-mpnet-base-v2"
)
SSL_VERIFY: bool = _parse_ssl_verify(_optional("SSL_VERIFY", "true"))
MCP_TRANSPORT: str = _optional("MCP_TRANSPORT", "stdio")
MCP_HOST: str = _optional("MCP_HOST", "0.0.0.0")
MCP_PORT: int = int(_optional("MCP_PORT", "8080"))
ARTIFACT_CACHE_DIR: str = _optional("ARTIFACT_CACHE_DIR", "./artifacts")
FINDIT_SERVICE_NAME_FUZZY_THRESHOLD: float = float(
    _optional("FINDIT_SERVICE_NAME_FUZZY_THRESHOLD", "0.68")
)
LOG_LEVEL: str = _optional("LOG_LEVEL", "INFO")
EXTRACTION_RATE_LIMIT_RETRIES: int = int(
    _optional("EXTRACTION_RATE_LIMIT_RETRIES", "3")
)
EXTRACTION_RETRY_BASE_DELAY: float = float(
    _optional("EXTRACTION_RETRY_BASE_DELAY", "2.0")
)
JIRA_MAX_CONCURRENT: int = int(_optional("JIRA_MAX_CONCURRENT", "4"))
GITHUB_ENRICH_MAX_CONCURRENT: int = int(_optional("GITHUB_ENRICH_MAX_CONCURRENT", "8"))
GITHUB_ENRICH_BODY_MAX_CHARS: int = int(_optional("GITHUB_ENRICH_BODY_MAX_CHARS", "1500"))
REDHAT_DOCS_DELAY_SEC: float = float(_optional("REDHAT_DOCS_DELAY_SEC", "2.0"))


def _parse_bool_flag(raw: str) -> bool:
    return raw.strip().lower() in ("1", "true", "yes", "on")


JBOSS_SKIP_PRERELEASE: bool = _parse_bool_flag(
    _optional("JBOSS_SKIP_PRERELEASE", "1")
)
SPRING_INCLUDE_PRERELEASE: bool = _parse_bool_flag(
    _optional("SPRING_INCLUDE_PRERELEASE", "1")
)
# When false, release rows keep the one-line GitHub text.
SPRING_BOOT_GITHUB_ENRICHMENT: bool = _parse_bool_flag(
    _optional("SPRING_BOOT_GITHUB_ENRICHMENT", "true")
)
ANGULAR_GITHUB_ENRICHMENT: bool = _parse_bool_flag(
    _optional("ANGULAR_GITHUB_ENRICHMENT", "true")
)
MCP_STATELESS_HTTP: bool = _parse_bool_flag(_optional("MCP_STATELESS_HTTP", "false"))
FINDIT_CACHE_STRATEGY: str = _optional("FINDIT_CACHE_STRATEGY", "none")
# Valid values: "bulk", "paginated", "none"
FINDIT_CACHE_LOAD_TIMEOUT_SECONDS: float = float(
    _optional("FINDIT_CACHE_LOAD_TIMEOUT_SECONDS", "30")
)

# --- Pipeline hop configuration -------------------------------------------
# Version-hop granularity for export-extract-populate-framework runs.
#   minor — one hop per minor line (3.1.12 → 3.2.0 → 3.2.4). Default.
#   patch — one hop per released version (3.1.0 → 3.1.1 → … → 3.2.0)
# Overridden per run by --hop-granularity.
HOP_GRANULARITY: str = _optional("HOP_GRANULARITY", "minor").strip().lower()
# When true, the filter LLM, entity LLM, and graph population run once per
# version hop instead of once per requested range, producing one Version node
# (and one ruleset) per hop. Overridden per run by --hop-by-hop/--no-hop-by-hop.
HOP_BY_HOP: bool = _parse_bool_flag(_optional("HOP_BY_HOP", "0"))

# --- System-1 change triage ------------------------------------------------
# Triage runs only when both TRIAGE_BASE_URL and TRIAGE_MODEL are non-empty.
# Leaving either empty is the off switch: every row is kept and the raw file
# stays in the historical 4-column shape.
TRIAGE_BASE_URL: str = _optional("TRIAGE_BASE_URL", "")
TRIAGE_ENDPOINT_PATH: str = _optional("TRIAGE_ENDPOINT_PATH", "/v1/systemone")
TRIAGE_MODEL: str = _optional("TRIAGE_MODEL", "")
TRIAGE_API_KEY: str = _optional("TRIAGE_API_KEY", "")
TRIAGE_TIMEOUT_SEC: float = float(_optional("TRIAGE_TIMEOUT_SEC", "30"))
TRIAGE_MAX_CONCURRENT: int = int(_optional("TRIAGE_MAX_CONCURRENT", "2"))
TRIAGE_STATE_MAX_CHARS: int = int(_optional("TRIAGE_STATE_MAX_CHARS", "6000"))
TRIAGE_DROP_MAX_ACTION_PROB: float = float(
    _optional("TRIAGE_DROP_MAX_ACTION_PROB", "0.20")
)
TRIAGE_DROP_MIN_CATEGORY_PROB: float = float(
    _optional("TRIAGE_DROP_MIN_CATEGORY_PROB", "0.80")
)
TRIAGE_DROP_MAX_IMPACT_SCORE: float = float(
    _optional("TRIAGE_DROP_MAX_IMPACT_SCORE", "1.0")
)
FILTER_MAX_INPUT_TOKENS: int = int(_optional("FILTER_MAX_INPUT_TOKENS", "60000"))

# --- Per-change research ----------------------------------------------------
# Research runs when RESEARCH_BASE_URL and RESEARCH_MODEL_ID are non-empty.
# TAVILY_API_KEY is optional (empty = fetch_url only). The live reader is
# migration_oracle.pipeline.research.settings.load_settings.
RESEARCH_BASE_URL: str = _optional("RESEARCH_BASE_URL", "")
RESEARCH_MODEL_ID: str = _optional("RESEARCH_MODEL_ID", "")
RESEARCH_API_KEY: str = _optional("RESEARCH_API_KEY", "")
RESEARCH_ENABLE_THINKING: bool = _parse_bool_flag(
    _optional("RESEARCH_ENABLE_THINKING", "false")
)
RESEARCH_MAX_CONCURRENT: int = int(_optional("RESEARCH_MAX_CONCURRENT", "4"))
RESEARCH_MAX_TOOL_CALLS: int = int(_optional("RESEARCH_MAX_TOOL_CALLS", "12"))
RESEARCH_TIMEOUT_SEC: float = float(_optional("RESEARCH_TIMEOUT_SEC", "240"))
RESEARCH_MODEL_TIMEOUT_SEC: float = float(_optional("RESEARCH_MODEL_TIMEOUT_SEC", "60"))
RESEARCH_SEARCH_RESULTS: int = int(_optional("RESEARCH_SEARCH_RESULTS", "5"))
RESEARCH_FETCH_MAX_CHARS: int = int(_optional("RESEARCH_FETCH_MAX_CHARS", "20000"))
TAVILY_API_KEY: str = _optional("TAVILY_API_KEY", "")
ENTITY_MAX_INPUT_TOKENS: int = int(_optional("ENTITY_MAX_INPUT_TOKENS", "60000"))
