"""Pure canonical-key helpers and framework token data (spec 026).

Shared by ingestion (``migration_oracle``, spec 025) and the per-service
planner (``migration_planner``, spec 026). Nothing here may import either
package: the planner runs in a service repo without Neo4j, LangChain or the
model clients, and the ingestion tests guard ``migration_oracle`` imports.

- :mod:`migration_keys.keys` — ``npm_key`` / ``maven_key`` / ``cfg_key`` /
  ``syntax_key`` builders, so both sides produce byte-identical keys.
- :mod:`migration_keys.angular` — the Angular entry points, template-syntax
  tokens and config prefixes the canonicalizer and the scanner both match on.
"""

from migration_keys.angular import (
    ANGULAR_CONFIG_PREFIXES,
    ANGULAR_PACKAGES,
    ANGULAR_SYNTAX_TOKENS,
    DIAGNOSTIC_RE,
)
from migration_keys.keys import (
    UNRESOLVED_PACKAGE,
    cfg_key,
    config_file_for_key,
    diag_key,
    maven_key,
    npm_key,
    syntax_key,
)

__all__ = [
    "ANGULAR_CONFIG_PREFIXES",
    "ANGULAR_PACKAGES",
    "ANGULAR_SYNTAX_TOKENS",
    "DIAGNOSTIC_RE",
    "UNRESOLVED_PACKAGE",
    "cfg_key",
    "config_file_for_key",
    "diag_key",
    "maven_key",
    "npm_key",
    "syntax_key",
]
