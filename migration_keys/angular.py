"""Angular data shared by the canonicalizer (025) and the scanner (026).

Entry points, template-syntax tokens and config-key prefixes live here so the
two sides cannot drift: a rule entity and a scanner fact must land on the same
package / token / config file.

Pure data and one compiled regex — no imports beyond :mod:`re`.
"""

from __future__ import annotations

import re

# Angular compiler / template diagnostics, for example NG8115.
DIAGNOSTIC_RE = re.compile(r"^NG\d{4}$")

ANGULAR_PACKAGES: tuple[str, ...] = (
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

ANGULAR_SYNTAX_TOKENS: tuple[str, ...] = (
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

# Config-key prefix → the file the key belongs to (025 FR-2.6).
ANGULAR_CONFIG_PREFIXES: dict[str, str] = {
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

__all__ = [
    "ANGULAR_CONFIG_PREFIXES",
    "ANGULAR_PACKAGES",
    "ANGULAR_SYNTAX_TOKENS",
    "DIAGNOSTIC_RE",
]
