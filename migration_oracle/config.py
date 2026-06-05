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
FINDIT_BASE_URL: str = _optional("FINDIT_BASE_URL", "https://findit.paysafe.com")
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
REDHAT_DOCS_DELAY_SEC: float = float(_optional("REDHAT_DOCS_DELAY_SEC", "2.0"))


def _parse_bool_flag(raw: str) -> bool:
    return raw.strip().lower() in ("1", "true", "yes", "on")


JBOSS_SKIP_PRERELEASE: bool = _parse_bool_flag(
    _optional("JBOSS_SKIP_PRERELEASE", "0")
)
SPRING_INCLUDE_PRERELEASE: bool = _parse_bool_flag(
    _optional("SPRING_INCLUDE_PRERELEASE", "1")
)
