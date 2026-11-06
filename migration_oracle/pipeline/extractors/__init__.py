"""Framework HTTP extractor registry."""

from __future__ import annotations

from typing import Type

from migration_oracle.models.entities import DocumentedChange, ExtractionResult
from migration_oracle.pipeline.triage.markdown import (
    parse_raw_markdown,
    render_raw_markdown,
)
from migration_oracle.pipeline.extractors.angular import AngularExtractor
from migration_oracle.pipeline.extractors.base import BaseExtractor
from migration_oracle.pipeline.extractors.eap import EAPExtractor
from migration_oracle.pipeline.extractors.elytron import ElytronExtractor
from migration_oracle.pipeline.extractors.hibernate import HibernateExtractor
from migration_oracle.pipeline.extractors.infinispan import InfinispanExtractor
from migration_oracle.pipeline.extractors.jakarta_ee import JakartaEEExtractor
from migration_oracle.pipeline.extractors.resteasy import RestEasyExtractor
from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor
from migration_oracle.pipeline.extractors.stub_framework import StubFrameworkExtractor
from migration_oracle.pipeline.extractors.wildfly import WildFlyExtractor

FRAMEWORK_DISPLAY_NAMES: dict[str, str] = {
    "spring-boot": "Spring Boot",
    "angular": "Angular",
    "wildfly": "WildFly",
    "eap": "JBoss EAP",
    "hibernate": "Hibernate ORM",
    "resteasy": "RESTEasy",
    "infinispan": "Infinispan",
    "elytron": "WildFly Elytron",
    "jakarta-ee": "Jakarta EE",
}

REGISTRY_KEYS: list[str] = list(FRAMEWORK_DISPLAY_NAMES.keys())

_EXTRACTOR_CLASSES: dict[str, Type[BaseExtractor]] = {
    "stub_framework": StubFrameworkExtractor,
    "spring-boot": SpringBootExtractor,
    "angular": AngularExtractor,
    "wildfly": WildFlyExtractor,
    "eap": EAPExtractor,
    "hibernate": HibernateExtractor,
    "resteasy": RestEasyExtractor,
    "infinispan": InfinispanExtractor,
    "elytron": ElytronExtractor,
    "jakarta-ee": JakartaEEExtractor,
}


def get_extractor(framework: str) -> BaseExtractor:
    """Return a new extractor instance for the given CLI framework key."""
    key = framework.strip().lower().replace(" ", "-")
    try:
        cls = _EXTRACTOR_CLASSES[key]
    except KeyError as exc:
        supported = ", ".join(sorted(_EXTRACTOR_CLASSES))
        raise ValueError(
            f"Unknown framework {framework!r}. Supported: {supported}"
        ) from exc
    return cls()


def supported_framework_keys() -> list[str]:
    return sorted(_EXTRACTOR_CLASSES)


__all__ = [
    "BaseExtractor",
    "DocumentedChange",
    "ExtractionResult",
    "FRAMEWORK_DISPLAY_NAMES",
    "REGISTRY_KEYS",
    "get_extractor",
    "parse_raw_markdown",
    "render_raw_markdown",
    "supported_framework_keys",
]
