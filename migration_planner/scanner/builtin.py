"""The readers and extractors spec 026 ships, in one list (spec1 FR-1).

Every 026 spec adds its module here and nowhere else, so the scan loop keeps
knowing nothing about npm, Maven or Angular. A spec that has not landed yet
contributes no entry, and its profile section stays an empty list.

Registration happens **on import of this module**, and the scanner package
imports it, so ``migration-scan`` works with no setup step. ``scan()`` does not
install anything: a caller that cleared the registry gets exactly what it
registered. That keeps :func:`contract.reset_registry` honest, which is what
spec1's "no facts by default" test relies on.
"""

from __future__ import annotations

from migration_planner.scanner import (
    contract,
    gradle,
    java,
    maven,
    npm_manifests,
    spring_config,
    templates,
    ts,
    ts_resolve,
)

# ``{manifest classification: reader}`` — spec2 npm, spec6 Maven / Gradle,
# spec8 Spring config.
MANIFEST_READERS: dict[str, contract.ManifestReader] = {
    **dict.fromkeys(npm_manifests.MANIFEST_KINDS, npm_manifests.read_npm_manifests),
    **dict.fromkeys(maven.MANIFEST_KINDS, maven.read_maven_manifests),
    **dict.fromkeys(gradle.MANIFEST_KINDS, gradle.read_gradle_manifests),
    **dict.fromkeys(spring_config.MANIFEST_KINDS, spring_config.read_spring_config),
}

# ``{discovery language tag: extractor}`` — spec3 TS / JS, spec5 Angular
# templates, spec7 Java.
SOURCE_EXTRACTORS: dict[str, contract.SourceExtractor] = {
    **dict.fromkeys(ts.GRAMMARS, ts.extract_ts),
    "html": templates.extract_html_template,
    **dict.fromkeys(java.GRAMMARS, java.extract_java),
}

# Post-passes over the merged facts — spec4 barrels, spec7 own-package filtering.
POST_PASSES: tuple[contract.PostPass, ...] = (
    java.filter_own_packages,
    ts_resolve.resolve_barrels,
)


def install() -> None:
    """Register the shipped readers, extractors and post-passes (idempotent)."""
    registered = contract.manifest_readers()
    for kind, reader in MANIFEST_READERS.items():
        if kind not in registered:
            contract.register_manifest_reader(kind, reader)

    installed = contract.source_extractors()
    for language, extractor in SOURCE_EXTRACTORS.items():
        if language not in installed:
            contract.register_source_extractor(language, extractor)

    present = contract.post_passes()
    for post_pass in POST_PASSES:
        if post_pass not in present:
            contract.register_post_pass(post_pass)


#: Installed on import, so ``migration-scan`` works without a separate setup
#: step. ``scan()`` deliberately does *not* install: a caller that cleared the
#: registry (a test, or a 030 command supplying its own readers) gets exactly
#: what it registered, and can call :func:`install` to get the shipped set back.
install()


__all__ = [
    "MANIFEST_READERS",
    "POST_PASSES",
    "SOURCE_EXTRACTORS",
    "install",
]
