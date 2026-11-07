"""Canonical key builders shared by ingestion (025) and the planner (026).

The graph merges entity nodes on these keys and the scanner writes the same
keys into a service profile, so a rule entity and a codebase fact meet without
translation. Both sides build them here, which is why this module must stay
dependency-free (no ``migration_oracle``, no pydantic, no I/O).

Key forms (025 FR-1):

| kind | key |
|---|---|
| class (npm) | ``npm:<package>#<symbol>`` |
| member (npm) | ``npm:<package>#<symbol>.<member>`` |
| dependency (npm) | ``npm:<package>`` |
| class (maven) | ``maven:<FQCN>`` |
| dependency (maven) | ``maven:<groupId>:<artifactId>`` |
| property | ``cfg:<file>#<dotted key>`` |
| syntax | ``syntax:<framework>-template#<token>`` |
| diagnostic | ``diag:<code>`` |
"""

from __future__ import annotations

from typing import Mapping

# An npm symbol whose package could not be resolved keeps this placeholder so
# the key stays stable until a later resolution re-keys the node (025 FR-1).
UNRESOLVED_PACKAGE = "?"


def npm_key(package: str, symbol: str = "", member: str = "") -> str:
    """``npm:<package>``, ``npm:<package>#<symbol>`` or ``…#<symbol>.<member>``.

    ``symbol`` empty means a dependency (no ``#``). An empty ``package`` with a
    symbol gives the unresolved form ``npm:?#<symbol>``.
    """
    if not symbol:
        return f"npm:{package}"
    tail = f"{symbol}.{member}" if member else symbol
    return f"npm:{package or UNRESOLVED_PACKAGE}#{tail}"


def maven_key(name: str) -> str:
    """``maven:<FQCN>`` or ``maven:<groupId>:<artifactId>``."""
    return f"maven:{name}"


def cfg_key(file: str, key: str) -> str:
    """``cfg:<file>#<dotted key>``, or ``cfg:<dotted key>`` when the file is unknown."""
    return f"cfg:{file}#{key}" if file else f"cfg:{key}"


def syntax_key(framework: str, token: str) -> str:
    """``syntax:<framework>-template#<token>`` (``angular`` → ``angular-template``)."""
    return f"syntax:{framework}-template#{token}"


def diag_key(code: str) -> str:
    """``diag:<code>``, for example ``diag:NG8115``."""
    return f"diag:{code}"


def config_file_for_key(dotted_key: str, prefixes: Mapping[str, str]) -> str:
    """The config file a dotted key belongs to, ``""`` when no prefix matches."""
    for prefix, file in prefixes.items():
        if dotted_key.startswith(prefix):
            return file
    return ""


__all__ = [
    "UNRESOLVED_PACKAGE",
    "cfg_key",
    "config_file_for_key",
    "diag_key",
    "maven_key",
    "npm_key",
    "syntax_key",
]
