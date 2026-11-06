"""Deterministic entity-name normalizer (spec 025 FR-2) and API-index
verification (FR-3).

Pure functions: the batch on disk is not rewritten, canonicalization runs at
populate time. Spring Boot / WildFly profiles are a no-op apart from computing
``key`` — names stay byte-for-byte as written.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from migration_oracle.models.entities import (
    AffectedEntity,
    CanonicalEntity,
    EntityKind,
    EntityRole,
    MigrationEntity,
)
from migration_oracle.pipeline.canonical.api_index import HopApiIndex
from migration_oracle.pipeline.canonical.profiles import (
    DIAGNOSTIC_RE,
    FrameworkProfile,
)

_QUOTE_CHARS = "`'\""

_CLASSY_KINDS = (EntityKind.CLASS, EntityKind.MEMBER)

# A bare option name that can be a field of an owner symbol (FR-2.4).
# Patterns such as ``ng-reflect-*`` are not identifiers and keep no owner.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_$][\w$]*$")

# Entry points that re-export or shadow the primary package's symbols. When a
# symbol is found in a primary entry point and in some of these, the primary
# one wins (``Injector`` in ``@angular/core`` and ``@angular/core/primitives/di``).
_SECONDARY_ENTRY_RE = re.compile(r"/(?:primitives(?:/|$)|testing$)")


@dataclass
class NormalizedEntity:
    """Canonical fields of one affected-entity occurrence plus its audit trail."""

    role: str
    raw_kind: str
    raw_name: str
    llm_package: str
    kind: EntityKind
    ecosystem: str
    package: str = ""
    symbol: str = ""
    member: str = ""
    file: str = ""
    name: str = ""
    key: str = ""
    verified: str = "false"
    applied: list[str] = field(default_factory=list)

    def to_canonical(self) -> CanonicalEntity:
        return CanonicalEntity(
            kind=self.kind,
            ecosystem=self.ecosystem,
            package=self.package,
            symbol=self.symbol,
            member=self.member,
            file=self.file,
            name=self.name,
            key=self.key,
            verified=self.verified,
        )


def normalize_rule(
    rule: MigrationEntity,
    profile: FrameworkProfile,
    index: HopApiIndex | None,
) -> list[NormalizedEntity]:
    """Canonical entities for one rule's occurrences, in the original order."""
    occurrences = list(rule.entities)
    if not occurrences:
        return []
    if not profile.is_npm:
        return [_normalize_maven(occurrence, profile) for occurrence in occurrences]

    normalized: list[NormalizedEntity | None] = []
    deferred: list[int] = []
    for occurrence in occurrences:
        entity, is_deferred = _normalize_shape(occurrence, profile, index)
        normalized.append(entity)
        if is_deferred:
            deferred.append(len(normalized) - 1)
    _assign_owners(normalized, deferred, index)
    _verify_rule(normalized, index)
    return [entity for entity in normalized if entity is not None]


# --- Maven / WildFly: no-op apart from key (FR-2.7) -------------------------


def _normalize_maven(occurrence: AffectedEntity, profile: FrameworkProfile) -> NormalizedEntity:
    name = occurrence.name  # byte-for-byte as written
    kind = occurrence.kind
    package = ""
    symbol = name
    member = ""
    file = ""
    if kind in _CLASSY_KINDS:
        key = f"maven:{name}"
    elif kind == EntityKind.PROPERTY:
        file = profile.config_file
        key = f"cfg:{file}#{name}" if file else f"cfg:{name}"
    elif kind == EntityKind.DEPENDENCY:
        package = name
        symbol = ""
        key = f"maven:{name}"
    elif kind == EntityKind.SYNTAX:
        key = f"syntax:{profile.key}-template#{name}"
    else:  # diagnostic
        key = f"diag:{name}"
    return NormalizedEntity(
        role=occurrence.role.value,
        raw_kind=occurrence.kind.value,
        raw_name=occurrence.name,
        llm_package=occurrence.package,
        kind=kind,
        ecosystem=profile.ecosystem,
        package=package,
        symbol=symbol,
        member=member,
        file=file,
        name=name,
        key=key,
        # No API index for maven profiles yet (spec 025 Non-Goals).
        verified="unchecked",
    )


# --- npm: clean, split, classify (FR-2.1–FR-2.6) ----------------------------


def _clean(raw: str, profile: FrameworkProfile) -> tuple[str, list[str]]:
    steps: list[str] = []
    text = raw.strip()
    while len(text) >= 2 and text[0] in _QUOTE_CHARS and text[-1] == text[0]:
        text = text[1:-1].strip()
        steps.append("clean:strip-quotes")
    if text.endswith("()"):
        text = text[:-2].strip()
        steps.append("clean:strip-call")
    # Syntax tokens are checked before the leading "@" is stripped so block
    # keywords like `@defer` survive; a decorator like `@Attribute` loses it.
    if text in profile.syntax_tokens:
        return text, steps
    if text.startswith("@") and "/" not in text and " " not in text and ":" not in text:
        text = text[1:]
        steps.append("clean:strip-decorator-at")
    return text, steps


def _known_packages(profile: FrameworkProfile, index: HopApiIndex | None) -> frozenset[str]:
    packages = set(profile.known_packages)
    if index is not None and index.usable:
        packages.update(index.packages)
    return frozenset(packages)


def _is_known_symbol(symbol: str, index: HopApiIndex | None) -> bool:
    return index is not None and index.usable and index.is_known_symbol(symbol)


def _split_package(
    text: str,
    profile: FrameworkProfile,
    index: HopApiIndex | None,
    llm_package: str,
    *,
    allow_package_only: bool,
) -> tuple[str, str, bool, list[str]]:
    """``(package, symbol_candidate, split?, steps)`` for an npm name.

    Parses ``<pkg> <sym>``, ``<pkg>:<sym>``, ``<pkg>#<sym>`` and ``<pkg>/<sym>`` where ``<pkg>``
    starts with ``@`` or matches a known package of the profile. A non-empty
    LLM ``package`` (FR-6) applies when the name itself carries no package.
    """
    known = _known_packages(profile, index)
    candidate = text
    # <pkg>:<sym> and <pkg>#<sym>
    for separator in (":", "#"):
        if separator in candidate:
            head, _, tail = candidate.partition(separator)
            if tail and (head.startswith("@") or head in known):
                return head, tail.strip(), True, ["split-package"]
    # <pkg> <sym>
    if " " in candidate:
        head, _, tail = candidate.partition(" ")
        if tail and (head.startswith("@") or head in known):
            return head, tail.strip(), True, ["split-package"]
    # @scope/a/b/<sym> (single token)
    if candidate.startswith("@") and "/" in candidate:
        for cut in range(len(candidate) - 1, 0, -1):
            if candidate[cut] != "/":
                continue
            prefix = candidate[:cut]
            if prefix in known:
                tail = candidate[cut + 1 :]
                if tail:
                    return prefix, tail, True, ["split-package"]
                if allow_package_only:
                    return prefix, "", True, ["split-package"]
    # LLM-provided package with a bare symbol in the name
    llm = llm_package.strip()
    if llm and not candidate.startswith("@") and not any(ch in candidate for ch in " :#"):
        return llm, candidate, True, ["package-from-llm"]
    return "", candidate, False, []


def _normalize_shape(
    occurrence: AffectedEntity,
    profile: FrameworkProfile,
    index: HopApiIndex | None,
) -> tuple[NormalizedEntity, bool]:
    """One occurrence to canonical shape.

    Returns ``(entity, deferred)``; ``deferred`` marks a bare lower-case
    property that waits for an owner from its rule (FR-2.4).
    """
    steps: list[str] = []
    cleaned, clean_steps = _clean(occurrence.name, profile)
    steps.extend(clean_steps)

    if (
        cleaned in profile.syntax_tokens
        or occurrence.name.strip() in profile.syntax_tokens
        or occurrence.kind == EntityKind.SYNTAX
    ):
        return (
            NormalizedEntity(
                role=occurrence.role.value,
                raw_kind=occurrence.kind.value,
                raw_name=occurrence.name,
                llm_package=occurrence.package,
                kind=EntityKind.SYNTAX,
                ecosystem=profile.ecosystem,
                symbol=cleaned,
                name=cleaned,
                key=f"syntax:{profile.key}-template#{cleaned}",
                verified="true",
                applied=steps + ["kind:syntax-token"],
            ),
            False,
        )

    if DIAGNOSTIC_RE.match(cleaned) or occurrence.kind == EntityKind.DIAGNOSTIC:
        return (
            NormalizedEntity(
                role=occurrence.role.value,
                raw_kind=occurrence.kind.value,
                raw_name=occurrence.name,
                llm_package=occurrence.package,
                kind=EntityKind.DIAGNOSTIC,
                ecosystem=profile.ecosystem,
                symbol=cleaned,
                name=cleaned,
                key=f"diag:{cleaned}",
                verified="true",
                applied=steps + ["kind:diagnostic"],
            ),
            False,
        )

    if occurrence.kind == EntityKind.DEPENDENCY:
        return (
            NormalizedEntity(
                role=occurrence.role.value,
                raw_kind=occurrence.kind.value,
                raw_name=occurrence.name,
                llm_package=occurrence.package,
                kind=EntityKind.DEPENDENCY,
                ecosystem=profile.ecosystem,
                package=cleaned,
                name=cleaned,
                key=f"npm:{cleaned}",
                verified="true",
                applied=steps,
            ),
            False,
        )

    package, candidate, split, split_steps = _split_package(
        cleaned,
        profile,
        index,
        occurrence.package,
        allow_package_only=False,
    )
    if split:
        steps.extend(split_steps)

    kind = occurrence.kind if occurrence.kind in _CLASSY_KINDS else EntityKind.CLASS
    if occurrence.kind == EntityKind.PROPERTY:
        kind = EntityKind.PROPERTY

    # Owner.member split (FR-2.3) — also when the LLM said "property".
    owner, dot, tail = candidate.partition(".")
    if dot and tail and (owner[:1].isupper() or _is_known_symbol(owner, index)):
        entity = NormalizedEntity(
            role=occurrence.role.value,
            raw_kind=occurrence.kind.value,
            raw_name=occurrence.name,
            llm_package=occurrence.package,
            kind=EntityKind.MEMBER,
            ecosystem=profile.ecosystem,
            package=package,
            symbol=owner,
            member=tail,
            name=f"{owner}.{tail}",
            key=_class_key(package, owner, tail),
            applied=steps + ["split-member"],
        )
        return entity, False

    # Config key with a known file prefix (FR-2.6)
    if kind == EntityKind.PROPERTY:
        if "." not in candidate:
            bare = candidate
            looks_lowercase = bare[:1].islower() or bare[:1] == "_"
            if not _IDENTIFIER_RE.match(bare):
                # A pattern like `ng-reflect-*` is not a field of any symbol.
                return (
                    NormalizedEntity(
                        role=occurrence.role.value,
                        raw_kind=occurrence.kind.value,
                        raw_name=occurrence.name,
                        llm_package=occurrence.package,
                        kind=EntityKind.PROPERTY,
                        ecosystem=profile.ecosystem,
                        symbol=bare,
                        name=bare,
                        key=f"cfg:{bare}",
                        verified="false",
                        applied=steps + ["owner-skipped:not-identifier"],
                    ),
                    False,
                )
            if looks_lowercase and not _is_known_symbol(bare, index):
                # A bare option: wait for the rule's owner (FR-2.4).
                entity = NormalizedEntity(
                    role=occurrence.role.value,
                    raw_kind=occurrence.kind.value,
                    raw_name=occurrence.name,
                    llm_package=occurrence.package,
                    kind=EntityKind.PROPERTY,
                    ecosystem=profile.ecosystem,
                    symbol=bare,
                    name=bare,
                    key=f"cfg:{bare}",
                    applied=steps,
                )
                return entity, True
            if _is_known_symbol(bare, index):
                # A bare symbol the LLM filed under "property" (FR-2.4).
                return (
                    NormalizedEntity(
                        role=occurrence.role.value,
                        raw_kind=occurrence.kind.value,
                        raw_name=occurrence.name,
                        llm_package=occurrence.package,
                        kind=EntityKind.CLASS,
                        ecosystem=profile.ecosystem,
                        package=package,
                        symbol=bare,
                        name=bare,
                        key=_class_key(package, bare),
                        applied=steps + ["kind:class-from-property"],
                    ),
                    False,
                )
            # Upper-case bare "property" without a known owner: keep as written.
            return (
                NormalizedEntity(
                    role=occurrence.role.value,
                    raw_kind=occurrence.kind.value,
                    raw_name=occurrence.name,
                    llm_package=occurrence.package,
                    kind=EntityKind.PROPERTY,
                    ecosystem=profile.ecosystem,
                    symbol=bare,
                    name=bare,
                    key=f"cfg:{bare}",
                    verified="false",
                    applied=steps + ["owner-unresolved"],
                ),
                False,
            )
        file = profile.file_for_key(candidate)
        if file:
            return (
                NormalizedEntity(
                    role=occurrence.role.value,
                    raw_kind=occurrence.kind.value,
                    raw_name=occurrence.name,
                    llm_package=occurrence.package,
                    kind=EntityKind.PROPERTY,
                    ecosystem=profile.ecosystem,
                    symbol=candidate,
                    file=file,
                    name=candidate,
                    key=f"cfg:{file}#{candidate}",
                    verified="true",
                    applied=steps + [f"config-file:{file}"],
                ),
                False,
            )
        return (
            NormalizedEntity(
                role=occurrence.role.value,
                raw_kind=occurrence.kind.value,
                raw_name=occurrence.name,
                llm_package=occurrence.package,
                kind=EntityKind.PROPERTY,
                ecosystem=profile.ecosystem,
                symbol=candidate,
                name=candidate,
                key=f"cfg:{candidate}",
                verified="false",
                applied=steps + ["config-file:unknown"],
            ),
            False,
        )

    # class / member with no further split
    symbol = candidate
    entity = NormalizedEntity(
        role=occurrence.role.value,
        raw_kind=occurrence.kind.value,
        raw_name=occurrence.name,
        llm_package=occurrence.package,
        kind=EntityKind.CLASS,
        ecosystem=profile.ecosystem,
        package=package,
        symbol=symbol,
        name=symbol,
        key=_class_key(package, symbol),
        applied=steps,
    )
    return entity, False


def _class_key(package: str, symbol: str, member: str = "") -> str:
    tail = f"{symbol}.{member}" if member else symbol
    return f"npm:{package or '?'}#{tail}"


# --- Owner assignment for bare options (FR-2.4) ----------------------------


def _owner_from_index(
    option: str,
    class_symbols: list[str],
    index: HopApiIndex | None,
) -> str:
    """The one class symbol of the rule whose published API has ``option``."""
    if index is None or not index.usable:
        return ""
    hits = [
        symbol
        for symbol in class_symbols
        if any(option in index.members_of(pkg, symbol) for pkg in index.entry_points(symbol))
    ]
    return hits[0] if len(hits) == 1 else ""


def _assign_owners(
    normalized: list[NormalizedEntity | None],
    deferred: list[int],
    index: HopApiIndex | None = None,
) -> None:
    """Attach bare options to an owner symbol of the same rule (FR-2.4).

    Order: the one class whose published API lists the option (index), else
    the rule's single replacement symbol, else its only class symbol.
    """
    if not deferred:
        return
    present = [entity for entity in normalized if entity is not None]
    replacement_symbols = sorted(
        {
            entity.symbol
            for entity in present
            if entity.kind == EntityKind.CLASS
            and entity.role == EntityRole.REPLACEMENT.value
            and entity.symbol
        }
    )
    class_symbols = sorted(
        {
            entity.symbol
            for entity in present
            if entity.kind == EntityKind.CLASS and entity.symbol
        }
    )
    fallback_owner = ""
    fallback_step = ""
    if len(replacement_symbols) == 1:
        fallback_owner, fallback_step = replacement_symbols[0], "owner-from-replacement"
    elif len(class_symbols) == 1:
        fallback_owner, fallback_step = class_symbols[0], "owner-from-only-class"
    for position in deferred:
        entity = normalized[position]
        if entity is None:
            continue
        option = entity.name
        owner = _owner_from_index(option, class_symbols, index)
        source_step = "owner-from-index"
        if not owner:
            owner, source_step = fallback_owner, fallback_step
        if not owner:
            entity.applied.append("owner-unresolved")
            continue
        owner_package = ""
        for candidate in present:
            if candidate.kind == EntityKind.CLASS and candidate.symbol == owner and candidate.package:
                owner_package = candidate.package
                break
        entity.kind = EntityKind.MEMBER
        entity.symbol = owner
        entity.member = option
        entity.name = f"{owner}.{option}"
        entity.package = owner_package
        entity.key = _class_key(owner_package, owner, option)
        entity.applied.append(source_step)


# --- Verification against the API index (FR-3) -----------------------------


def _verify_rule(
    normalized: list[NormalizedEntity | None],
    index: HopApiIndex | None,
) -> None:
    entities = [entity for entity in normalized if entity is not None]
    dependencies = {
        entity.name for entity in entities if entity.kind == EntityKind.DEPENDENCY and entity.name
    }
    index_ok = index is not None and index.usable
    # Owners first, so members can inherit nothing but their own resolution.
    for entity in entities:
        if entity.kind == EntityKind.CLASS:
            _verify_class(entity, index if index_ok else None, dependencies)
    for entity in entities:
        if entity.kind == EntityKind.MEMBER:
            _verify_member(entity, index if index_ok else None, dependencies)


def _primary_entry_point(entry: frozenset[str]) -> str:
    """The one primary entry point among several, or "" when there is none.

    Secondary entry points (``…/primitives/…``, ``…/testing``) lose against a
    primary one; among primaries, a single ancestor of all others wins
    (``@angular/core`` over ``@angular/core/rxjs-interop``).
    """
    primary = sorted(pkg for pkg in entry if not _SECONDARY_ENTRY_RE.search(pkg))
    if len(primary) == 1:
        return primary[0]
    ancestors = [
        pkg
        for pkg in primary
        if all(other == pkg or other.startswith(pkg + "/") for other in primary)
    ]
    return ancestors[0] if len(ancestors) == 1 else ""


def _resolve_package(
    entity: NormalizedEntity,
    index: HopApiIndex | None,
    dependencies: set[str],
) -> tuple[str, str | None, str]:
    """``(package, verdict, step)`` for the owner symbol of a class or member.

    ``verdict`` is ``"false"`` / ``"ambiguous"`` when resolution ends there and
    ``None`` when the package is resolved and verification may continue.
    """
    if index is None:
        return entity.package or "?", "false", "verify:index-unavailable"
    entry = index.entry_points(entity.symbol)
    if not entry:
        step = (
            "verify:not-in-partial-index" if index.status == "partial" else "verify:not-in-index"
        )
        return entity.package or "?", "false", step
    if entity.package and entity.package in entry:
        return entity.package, None, "verify:llm-package-kept"
    if len(entry) == 1:
        return next(iter(entry)), None, "verify:single-entry-point"
    chosen = sorted(entry & dependencies)
    if len(chosen) == 1:
        return chosen[0], None, "verify:dependency-match"
    primary = _primary_entry_point(entry)
    if primary:
        return primary, None, "verify:primary-entry-point"
    return "?", "ambiguous", "verify:ambiguous"


def _verify_class(
    entity: NormalizedEntity,
    index: HopApiIndex | None,
    dependencies: set[str],
) -> None:
    package, verdict, step = _resolve_package(entity, index, dependencies)
    entity.package = package
    entity.verified = verdict or "true"
    entity.applied.append(step)
    entity.key = _class_key(package, entity.symbol)


def _verify_member(
    entity: NormalizedEntity,
    index: HopApiIndex | None,
    dependencies: set[str],
) -> None:
    package, verdict, step = _resolve_package(entity, index, dependencies)
    entity.package = package
    entity.applied.append(step)
    if verdict is None:
        if entity.member in index.members_of(package, entity.symbol):
            verdict, step = "true", "verify:member-in-block"
        else:
            verdict, step = "false", "verify:member-not-in-block"
        entity.applied.append(step)
    entity.verified = verdict
    entity.key = _class_key(package, entity.symbol, entity.member)
