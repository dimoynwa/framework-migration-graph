"""Per-framework canonicalization profiles (spec 025).

A profile holds everything the deterministic normalizer needs that is specific
to one framework family: the ecosystem, the npm entry points a package prefix
can be split on, template-syntax tokens, and config-key prefixes. The Angular
profile is ``npm``; Spring Boot and WildFly are ``maven`` and are a no-op apart
from computing ``key`` (spec 025 FR-2.7).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping

# Angular compiler / template diagnostics, for example NG8115.
DIAGNOSTIC_RE = re.compile(r"^NG\d{4}$")

_ANGULAR_PACKAGES: tuple[str, ...] = (
    "@angular/animations",
    "@angular/animations/browser",
    "@angular/common",
    "@angular/common/http",
    "@angular/common/http/testing",
    "@angular/common/testing",
    "@angular/compiler",
    "@angular/compiler-cli",
    "@angular/compiler/testing",
    "@angular/core",
    "@angular/core/primitives/event-dispatch",
    "@angular/core/primitives/signals",
    "@angular/core/rxjs-interop",
    "@angular/core/testing",
    "@angular/elements",
    "@angular/forms",
    "@angular/localize",
    "@angular/platform-browser",
    "@angular/platform-browser/animations",
    "@angular/platform-browser/animations/async",
    "@angular/platform-browser/testing",
    "@angular/platform-browser-dynamic",
    "@angular/platform-browser-dynamic/testing",
    "@angular/platform-server",
    "@angular/platform-server/init",
    "@angular/router",
    "@angular/router/testing",
    "@angular/service-worker",
    "@angular/upgrade",
    "@angular/upgrade/common",
    "@angular/upgrade/static",
)

_ANGULAR_SYNTAX_TOKENS: tuple[str, ...] = (
    "in",
    "void",
    "typeof",
    "as",
    "let",
    "@if",
    "@else",
    "@else if",
    "@for",
    "@empty",
    "@switch",
    "@case",
    "@defer",
    "@placeholder",
    "@error",
    "@loading",
    "@let",
)

# Config-key prefix → the file the key belongs to (spec 025 FR-2.6).
_ANGULAR_CONFIG_PREFIXES: Mapping[str, str] = {
    "engines.": "package.json",
    "peerDependencies.": "package.json",
    "dependencies.": "package.json",
    "devDependencies.": "package.json",
    "angularCompilerOptions.": "tsconfig.json",
    "compilerOptions.": "tsconfig.json",
    "projects.": "angular.json",
    "architect.": "angular.json",
    "schematics.": "angular.json",
}


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
        for prefix, file in self.config_prefixes.items():
            if dotted_key.startswith(prefix):
                return file
        return ""


ANGULAR_PROFILE = FrameworkProfile(
    key="angular",
    ecosystem="npm",
    known_packages=frozenset(_ANGULAR_PACKAGES),
    syntax_tokens=frozenset(_ANGULAR_SYNTAX_TOKENS),
    config_prefixes=_ANGULAR_CONFIG_PREFIXES,
)

SPRING_BOOT_PROFILE = FrameworkProfile(
    key="spring-boot",
    ecosystem="maven",
    config_file="application.properties",
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