"""The readers and extractors spec 026 ships, in one list (spec1 FR-1).

Every 026 spec adds its module here and nowhere else, so the scan loop keeps
knowing nothing about npm, Maven or Angular. A spec that has not landed yet
contributes no entry, and its profile section stays an empty list.

``install()`` registers what is not registered yet: a test that registers a
stand-in reader for one manifest kind keeps it, and the real reader fills the
remaining kinds of the same module family.
"""

from __future__ import annotations

from migration_planner.scanner import contract, npm_manifests

# ``{manifest classification: reader}`` — spec2 npm, spec6 Maven / Gradle,
# spec8 Spring config.
MANIFEST_READERS: dict[str, contract.ManifestReader] = {
    **dict.fromkeys(npm_manifests.MANIFEST_KINDS, npm_manifests.read_npm_manifests),
}

# ``{discovery language tag: extractor}`` — spec3 / spec4 TS / JS, spec5
# templates, spec7 Java.
SOURCE_EXTRACTORS: dict[str, contract.SourceExtractor] = {}

# Post-passes over the merged facts — spec4 barrels, spec7 own-package filtering.
POST_PASSES: tuple[contract.PostPass, ...] = ()


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


__all__ = [
    "MANIFEST_READERS",
    "POST_PASSES",
    "SOURCE_EXTRACTORS",
    "install",
]
