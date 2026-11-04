"""Graph read value objects and version utilities."""

import re
from dataclasses import dataclass, field


@dataclass
class VersionNode:
    framework: str
    version: str
    sortable_version: int
    raw_md_path: str | None = None
    filtered_md_path: str | None = None
    entities_json_path: str | None = None


@dataclass
class MigrationRuleNode:
    element_id: str
    statement: str
    rule_type: str
    change_type: str
    entity_classification: str
    title: str | None = None
    jira_keys: list[str] = field(default_factory=list)
    source_url: str = ""


@dataclass
class MigrationStepNode:
    element_id: str
    step_type: str
    summary: str
    instruction: str
    effort: str
    automatable: bool
    verification_hint: str
    cli_operation: str = ""


@dataclass
class BreakingScopeNode:
    scope: str
    severity: str


@dataclass
class MigrationContextNode:
    element_id: str
    project_id: str
    from_version: str
    to_version: str
    framework: str
    status: str
    completed_steps: list[str]
    skipped_steps: list[str]
    created_at: str
    completed_at: str | None = None
    notes: str = ""


@dataclass
class VersionResolutionResult:
    resolvedVersion: str
    resolvedSortable: int
    nodeId: str
    requestedVersion: str
    rounded: bool
    aheadOfCatalogue: bool
    stubCreated: bool
    direction: str  # "exact" | "floor" | "ceil"


@dataclass
class VersionResolutionFailure:
    status: str  # always "NO_CANDIDATE"
    framework: str
    requestedVersion: str
    candidatesConsidered: list[str] = field(default_factory=list)


#: Separator + suffix of a version string, e.g. ``-RC1``, ``.Final``, ``-next.3``.
_VERSION_SUFFIX_RE = re.compile(
    r"^(\d+)\.(\d+)(?:\.(\d+))?(?:([._-])(.+))?$"
)
_FAMILIES_ONLY_RE = re.compile(r"^[A-Za-z]+")
_DIGITS_ONLY_RE = re.compile(r"\d+")

#: Prereleases sort **below** the GA release they precede by borrowing the
#: previous minor line's unused patch numbers: ``4.1.0-RC1`` lands on
#: ``4000951``, which is 4.0.951 — above every real patch of the previous line
#: (no framework in scope reaches patch 900) and immediately below 4.1.0.
#: GA integers are therefore unchanged by this scheme.
_PRE_RELEASE_WINDOW = 200

#: Ordering rank per prerelease family; the family's numeric tail is added and
#: capped at 9, so each family owns a 10-wide slice of the window.
_PRE_RELEASE_RANKS: dict[str, int] = {
    "alpha": 1, "a": 1, "dev": 1, "snapshot": 1, "nightly": 1, "trunk": 1,
    "beta": 20, "b": 20,
    "preview": 40, "ea": 40, "next": 40, "canary": 40,
    "milestone": 100, "m": 100,
    "cr": 150, "rc": 150,
}
_UNKNOWN_PRE_RELEASE_RANK = 70

#: Suffixes that mark a general-availability build, ordered as the GA release.
_GA_SUFFIXES = frozenset({"final", "ga", "release", "stable", "prod"})


def _parse_version_suffix(
    version: str,
) -> tuple[int, int, int, str | None]:
    """Return ``(major, minor, patch, prerelease_suffix)`` for a version string.

    Accepts ``3.2.1``, ``3.2``, ``4.1.0-RC1``, ``22.0.0-rc.2``, ``26.1.2.Final``,
    ``20.0.0-next.3``. Raises ValueError for anything unparseable.
    """
    match = _VERSION_SUFFIX_RE.match(version.strip())
    if not match:
        raise ValueError(f"Cannot parse version: {version!r}")
    major, minor = int(match.group(1)), int(match.group(2))
    patch = int(match.group(3)) if match.group(3) else 0
    separator, suffix = match.group(4), match.group(5)
    if suffix is None:
        return major, minor, patch, None
    family = _FAMILIES_ONLY_RE.match(suffix)
    if not family:
        # Numeric-only tail: valid after a hyphen (npm-style ``18.0.0-0``),
        # garbage after a dot (``1.2.3.4.5``).
        if separator == "-":
            return major, minor, patch, suffix
        raise ValueError(f"Cannot parse version: {version!r}")
    if family.group(0).lower() in _GA_SUFFIXES:
        return major, minor, patch, None
    return major, minor, patch, suffix


def prerelease_suffix(version: str) -> str | None:
    """Return the prerelease suffix of ``version`` ('RC1'), or None for GA."""
    return _parse_version_suffix(version)[3]


def is_prerelease(version: str) -> bool:
    """True for milestone/RC/next builds such as ``4.1.0-RC1`` or ``20.0.0-next.3``."""
    return prerelease_suffix(version) is not None


def _pre_release_rank(suffix: str) -> int:
    family_match = _FAMILIES_ONLY_RE.match(suffix)
    family = family_match.group(0).lower() if family_match else ""
    rank = _PRE_RELEASE_RANKS.get(family, _UNKNOWN_PRE_RELEASE_RANK)
    digits = _DIGITS_ONLY_RE.search(suffix)
    tail = min(int(digits.group(0)), 9) if digits else 0
    return rank + tail


def version_parts(version: str) -> tuple[int, int, int, int]:
    """Return ``(major, minor, patch, prerelease_offset)`` for a version string.

    ``prerelease_offset`` is 0 for GA builds and negative for milestone/RC
    builds, so a tuple sort orders ``4.1.0-M1 < 4.1.0-RC1 < 4.1.0`` even though
    all three share the ``(4, 1, 0)`` triple.
    """
    major, minor, patch, suffix = _parse_version_suffix(version)
    if suffix is None:
        return major, minor, patch, 0
    return major, minor, patch, _pre_release_rank(suffix) - _PRE_RELEASE_WINDOW


def sortable_version(version: str) -> int:
    """
    Compute ``major * 1_000_000 + minor * 1_000 + patch`` for GA releases.

    Accepts "3.2.1", "3.2", "17.0.0", and prereleases such as "4.1.0-RC1",
    "4.1.0-M4", "22.0.0-rc.2" or the JBoss "26.1.2.Final" spelling. The patch
    component defaults to 0 when only major.minor is given. Prereleases sort
    just below the GA release they precede (see :data:`_PRE_RELEASE_WINDOW`);
    GA values are unaffected. Raises ValueError for anything unparseable.
    """
    major, minor, patch, offset = version_parts(version)
    return major * 1_000_000 + minor * 1_000 + patch + offset
