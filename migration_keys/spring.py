"""Spring Boot config data shared by ingestion (025) and the scanner (026.8).

Two sides must agree on Spring property keys, or a rule and a service fact never
meet: 025 writes the key of a rule's property entity, 026 FR-8a writes the key of
the property a service really sets. The data therefore lives here, next to the
Angular lists, and both import it:

- :data:`SPRING_CONFIG_FILE` — the canonical config file of a Spring property.
  Every Spring property canonicalizes to this one name, whichever file it is
  actually in (``application-prod.yml``, ``bootstrap.properties``), because a
  rule names the property, not the file. ``config[].file`` keeps the real path.
- :data:`SPRING_MAP_PREFIXES` — prefixes whose remaining segments are *map keys*
  rather than property names, so they keep their case under relaxed binding
  (``logging.level.com.Foo.BarService``).
- :func:`canonical_key`, :func:`is_secret_key`, :func:`redact_value` — Spring's
  canonical (kebab-case) form and the secret rules the profile must apply before
  it is written anywhere a CI artifact can reach.

Pure data and regexes — no I/O, no pydantic, no ``migration_oracle``.
"""

from __future__ import annotations

import re

#: The file name a Spring property key names (025 FR-2.6, 026.8 FR-8a).
SPRING_CONFIG_FILE = "application.properties"

#: Prefixes after which a segment is a **map key**, not a property name, so
#: relaxed binding leaves its case alone. ``[*]`` stands for a list index of
#: the segment before it (``spring.cloud.gateway.routes[0].metadata``).
SPRING_MAP_PREFIXES: tuple[str, ...] = (
    "logging.level",
    "spring.jpa.properties",
    "spring.kafka.properties",
    "spring.kafka.consumer.properties",
    "spring.kafka.producer.properties",
    "spring.kafka.streams.properties",
    "spring.kafka.admin.properties",
    "spring.datasource.hikari.data-source-properties",
    "management.metrics.tags",
    "spring.cloud.gateway.routes[*].metadata",
)

#: What a secret value becomes. Never the value itself.
REDACTED = "<redacted>"

#: Value length cap: a profile records facts, not file contents.
MAX_VALUE_LENGTH = 200

#: Last-segment words that make a value a secret (FR-8a). Compared token by
#: token, so ``client-secret`` and ``spring.datasource.password`` both match.
SECRET_WORDS: frozenset[str] = frozenset(
    {
        "apikey",
        "clientsecret",
        "credential",
        "credentials",
        "passphrase",
        "passwd",
        "password",
        "privatekey",
        "pwd",
        "secret",
        "token",
    }
)

#: Last tokens that make a secret-named key a setting *about* the secret, not
#: the secret itself: ``token-uri`` is a public URL, ``access-token-validity-
#: seconds`` a duration, ``jwt.secret-header-name`` a header name. Their value is
#: a fact a rule may compare, so it is kept. ``hmac-secret-key`` still ends in
#: ``key`` and stays redacted.
NON_SECRET_SUFFIXES: frozenset[str] = frozenset(
    {
        "algorithm",
        "enabled",
        "endpoint",
        "expiration",
        "expiry",
        "header",
        "issuer",
        "length",
        "location",
        "name",
        "path",
        "seconds",
        "size",
        "timeout",
        "ttl",
        "type",
        "uri",
        "url",
        "validity",
    }
)

#: A list index at the end of a segment: ``routes[0]``.
_INDEX_RE = re.compile(r"^(?P<name>.*?)(?P<index>\[\d+\])$")

#: ``HTMLContent`` → ``HTML-Content``, then ``authenticationDatabase`` →
#: ``authentication-Database``.
_UPPER_RUN_RE = re.compile(r"([A-Z]+)([A-Z][a-z])")
_LOWER_UPPER_RE = re.compile(r"([a-z0-9])([A-Z])")

#: One or more placeholders and nothing else: ``${PORT:8080}``.
_PLACEHOLDER_RE = re.compile(r"(?:\$\{[^}]*\})+")

#: A URL that carries a user name and a password: ``scheme://user:pass@host``.
_USERINFO_URL_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*://[^/@\s]+:[^/@\s]*@")

#: Token separators inside one dotted segment.
_TOKEN_SPLIT_RE = re.compile(r"[-_.\s]+")


def split_index(segment: str) -> tuple[str, str]:
    """``routes[0]`` → ``("routes", "[0]")``; a plain segment keeps ``""``."""
    match = _INDEX_RE.match(segment)
    if match is None:
        return segment, ""
    return match.group("name"), match.group("index")


def kebab(segment: str) -> str:
    """One property-name segment in Spring's canonical form.

    ``authenticationDatabase`` → ``authentication-database``,
    ``authentication_database`` → the same, ``SERVER_PORT`` → ``server-port``.
    A segment already in canonical form is returned unchanged, so running this
    twice is harmless.
    """
    if not segment:
        return segment
    name, index = split_index(segment)
    if not name:
        return segment
    if any(character.isupper() for character in name) or "_" in name:
        name = _UPPER_RUN_RE.sub(r"\1-\2", name)
        name = _LOWER_UPPER_RE.sub(r"\1-\2", name)
        name = re.sub(r"[\s_]+", "-", name).lower()
        name = re.sub(r"-{2,}", "-", name)
    return name + index


def _segments(key: str) -> list[str]:
    return [segment for segment in key.strip().split(".")]


def _pattern_matches(pattern_segment: str, segment: str) -> bool:
    """``routes[*]`` matches ``routes[0]``; anything else is an exact match."""
    if pattern_segment.endswith("[*]"):
        name, index = split_index(segment)
        return bool(index) and name == pattern_segment[:-3]
    return pattern_segment == segment


def map_prefix_length(key: str) -> int:
    """How many leading segments of ``key`` are property names, not map keys.

    ``logging.level.com.Foo.BarService`` gives ``2``: ``logging`` and ``level``
    are property names, everything after is the map key as written.
    """
    segments = _segments(key)
    best = 0
    for prefix in SPRING_MAP_PREFIXES:
        pattern = _segments(prefix)
        if len(pattern) > len(segments):
            continue
        if len(pattern) <= best:
            continue
        if all(
            _pattern_matches(pattern[index], segments[index])
            for index in range(len(pattern))
        ):
            best = len(pattern)
    return best


def canonical_key(key: str) -> str:
    """Spring's canonical form of a dotted property key (FR-8a).

    Property-name segments become lower-case kebab-case; segments after a
    map-valued prefix, and list indices, keep what the service wrote::

        spring.data.mongodb.authenticationDatabase  →  …authentication-database
        logging.level.com.Foo.BarService            →  logging.level.com.Foo.BarService
        spring.cloud.gateway.routes[0].metadata.Key →  unchanged after metadata
    """
    segments = _segments(key)
    prefix = map_prefix_length(key)
    # ``prefix == 0`` means no map-valued prefix applies: every segment is a
    # property name and is canonicalized. Otherwise only the segments inside the
    # prefix are property names; everything after it is a map key as written.
    canonical = (
        [kebab(segment) for segment in segments]
        if prefix == 0
        else [kebab(segment) for segment in segments[:prefix]] + segments[prefix:]
    )
    return ".".join(canonical)


def is_secret_key(key: str) -> bool:
    """Whether the key's last segment names a credential (FR-8a)."""
    segments = _segments(canonical_key(key))
    if not segments:
        return False
    name, _ = split_index(segments[-1])
    collapsed = re.sub(r"[-_]", "", name.lower())
    if collapsed in SECRET_WORDS:
        return True
    tokens = [token.lower() for token in _TOKEN_SPLIT_RE.split(name) if token]
    if not any(token in SECRET_WORDS for token in tokens):
        return False
    # ``token-uri``, ``access-token-validity-seconds``: a setting about the
    # secret, whose value is public and a fact a rule may compare.
    return tokens[-1] not in NON_SECRET_SUFFIXES or tokens[-1] in SECRET_WORDS


def has_userinfo_url(value: str) -> bool:
    """Whether a value is a URL with ``user:pass@`` in it (``jdbc:postgresql://u:p@h/db``)."""
    return bool(_USERINFO_URL_RE.search(value))


def redact_value(key: str, value: str | None) -> str | None:
    """The value the profile may store, or ``None`` when there is none.

    A placeholder is kept exactly as written: ``${DB_PASSWORD}`` is a reference,
    not a credential, and resolving it is not the scanner's job. A secret-looking
    key or a URL that carries user info is ``"<redacted>"``. Every other value is
    truncated to :data:`MAX_VALUE_LENGTH`, so the profile stays a set of facts
    and never becomes a copy of the config files.
    """
    if value is None:
        return None
    text = value.strip()
    if not text:
        return ""
    if _PLACEHOLDER_RE.fullmatch(text):
        return text
    if is_secret_key(key) or has_userinfo_url(text):
        return REDACTED
    return text[:MAX_VALUE_LENGTH]


def config_file_for_spring_key(dotted_key: str) -> str:
    """The canonical file of a Spring property — always :data:`SPRING_CONFIG_FILE`."""
    return SPRING_CONFIG_FILE if dotted_key else ""


__all__ = [
    "MAX_VALUE_LENGTH",
    "NON_SECRET_SUFFIXES",
    "REDACTED",
    "SECRET_WORDS",
    "SPRING_CONFIG_FILE",
    "SPRING_MAP_PREFIXES",
    "canonical_key",
    "config_file_for_spring_key",
    "has_userinfo_url",
    "is_secret_key",
    "kebab",
    "map_prefix_length",
    "redact_value",
    "split_index",
]
