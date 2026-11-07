"""Pure canonical-key helpers and framework token data (spec 026).

Shared by ingestion (``migration_oracle``, spec 025) and the per-service
planner (``migration_planner``, spec 026). Nothing here may import either
package: the planner runs in a service repo without Neo4j, LangChain or the
model clients, and the ingestion tests guard ``migration_oracle`` imports.

- :mod:`migration_keys.keys` — ``npm_key`` / ``maven_key`` / ``cfg_key`` /
  ``syntax_key`` builders, so both sides produce byte-identical keys.
- :mod:`migration_keys.angular` — the Angular entry points, template-syntax
  tokens and config prefixes the canonicalizer and the scanner both match on.
- :mod:`migration_keys.specifiers` — the import-specifier rules: which package a
  specifier belongs to, and whether it names the service's own code.
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
from migration_keys.spring import (
    REDACTED,
    SPRING_CONFIG_FILE,
    SPRING_MAP_PREFIXES,
    canonical_key,
    config_file_for_spring_key,
    has_userinfo_url,
    is_secret_key,
    redact_value,
)
from migration_keys.specifiers import (
    dependency_name,
    is_node_builtin,
    is_own_code,
    is_relative_specifier,
    matches_path_alias,
    package_of_specifier,
    resolve_path_alias,
)

__all__ = [
    "ANGULAR_CONFIG_PREFIXES",
    "ANGULAR_PACKAGES",
    "ANGULAR_SYNTAX_TOKENS",
    "DIAGNOSTIC_RE",
    "REDACTED",
    "SPRING_CONFIG_FILE",
    "SPRING_MAP_PREFIXES",
    "UNRESOLVED_PACKAGE",
    "canonical_key",
    "cfg_key",
    "config_file_for_key",
    "config_file_for_spring_key",
    "dependency_name",
    "diag_key",
    "has_userinfo_url",
    "is_node_builtin",
    "is_own_code",
    "is_relative_specifier",
    "is_secret_key",
    "matches_path_alias",
    "maven_key",
    "npm_key",
    "package_of_specifier",
    "redact_value",
    "resolve_path_alias",
    "syntax_key",
]
