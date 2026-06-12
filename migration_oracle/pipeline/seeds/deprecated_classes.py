"""Curated seed data for well-known Spring Boot 3.x deprecated classes."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class _DeprecatedClass:
    name: str
    framework: str
    deprecated_in: str
    replacement: str | None = None


SPRING_BOOT_3X_DEPRECATED: list[_DeprecatedClass] = [
    _DeprecatedClass(
        name="RestTemplate",
        framework="Spring Boot",
        deprecated_in="3.2.0",
        replacement="RestClient",
    ),
    _DeprecatedClass(
        name="WebSecurityConfigurerAdapter",
        framework="Spring Boot",
        deprecated_in="3.0.0",
        replacement=None,
    ),
    _DeprecatedClass(
        name="WebMvcConfigurerAdapter",
        framework="Spring Boot",
        deprecated_in="3.0.0",
        replacement=None,
    ),
    _DeprecatedClass(
        name="WebMvcConfigurer",
        framework="Spring Boot",
        deprecated_in="3.0.0",
        replacement=None,
    ),
    _DeprecatedClass(
        name="EnvironmentPostProcessor",
        framework="Spring Boot",
        deprecated_in="3.0.0",
        replacement=None,
    ),
]
