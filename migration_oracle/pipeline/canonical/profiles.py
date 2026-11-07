"""Per-framework canonicalization profiles (spec 025).

A profile holds everything the deterministic normalizer needs that is specific
to one framework family: the ecosystem, the npm entry points a package prefix
can be split on, template-syntax tokens, and config-key prefixes. The Angular
profile is ``npm``; Spring Boot and WildFly are ``maven`` and are a no-op apart
from computing ``key`` (spec 025 FR-2.7).

The data itself lives in :mod:`migration_keys` (spec 026 FR-1), because the
service scanner matches on the very same packages, tokens and config prefixes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from migration_keys.angular import (
    ANGULAR_CONFIG_PREFIXES,
    ANGULAR_PACKAGES,
    ANGULAR_SYNTAX_TOKENS,
)
from migration_keys.keys import config_file_for_key
from migration_keys.spring import SPRING_CONFIG_FILE


@dataclass(frozen=True)
class FrameworkProfile:
    """Everything the normalizer needs for one framework family."""

    key: str
    ecosystem: str  # "npm" | "maven"
    known_packages: frozenset[str] = frozenset()
    syntax_tokens: frozenset[str] = frozenset()
    config_prefixes: Mapping[str, str] = field(default_factory=dict)
    # File assumed for config keys when the LLM gave no hint. Spring Boot
    # properties live in application.properties; WildFly has none.
    config_file: str = ""

    @property
    def is_npm(self) -> bool:
        return self.ecosystem == "npm"

    def file_for_key(self, dotted_key: str) -> str:
        """Config file for a dotted key, "" when the prefix is unknown."""
        return config_file_for_key(dotted_key, self.config_prefixes)


ANGULAR_PROFILE = FrameworkProfile(
    key="angular",
    ecosystem="npm",
    known_packages=frozenset(ANGULAR_PACKAGES),
    syntax_tokens=frozenset(ANGULAR_SYNTAX_TOKENS),
    config_prefixes=ANGULAR_CONFIG_PREFIXES,
)

SPRING_BOOT_PROFILE = FrameworkProfile(
    key="spring-boot",
    ecosystem="maven",
    # Every Spring property canonicalizes under this one file name, so a rule's
    # key and the service's key (026.8 FR-8a) compare equal whichever file the
    # property is really in.
    config_file=SPRING_CONFIG_FILE,
)

WILDFLY_PROFILE = FrameworkProfile(
    key="wildfly",
    ecosystem="maven",
)

# Frameworks without a profile keep their names byte-for-byte; the default is
# the maven no-op so unknown keys still get stable `maven:` / `cfg:` keys.
DEFAULT_PROFILE = FrameworkProfile(key="default", ecosystem="maven")

_PROFILES: dict[str, FrameworkProfile] = {
    "angular": ANGULAR_PROFILE,
    "spring-boot": SPRING_BOOT_PROFILE,
    "wildfly": WILDFLY_PROFILE,
}


def profile_for(framework_key: str = "", framework_display: str = "") -> FrameworkProfile:
    """Profile by framework key, falling back to the display name."""
    for candidate in (framework_key.strip().lower(), framework_display.strip().lower()):
        if not candidate:
            continue
        for key, profile in _PROFILES.items():
            if key in candidate or candidate in key:
                return profile
        if "spring" in candidate or "boot" in candidate:
            return SPRING_BOOT_PROFILE
    return DEFAULT_PROFILE
