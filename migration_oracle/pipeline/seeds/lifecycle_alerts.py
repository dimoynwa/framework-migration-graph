"""Curated seed data for Spring Boot 4.x lifecycle alerts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class _LifecycleAlert:
    message: str
    category: str
    phase: str
    framework: str
    version: str


SPRING_BOOT_4X_ALERTS: list[_LifecycleAlert] = [
    _LifecycleAlert(
        message="Spring Security 7 changes the default CSRF policy — review all state-changing endpoints.",
        category="security",
        phase="pre-migration",
        framework="Spring Boot",
        version="4.0.0",
    ),
    _LifecycleAlert(
        message="Spring Boot 4 drops Java 8/11 support — migrate to Java 17+ before upgrading.",
        category="dependency",
        phase="pre-migration",
        framework="Spring Boot",
        version="4.0.0",
    ),
    _LifecycleAlert(
        message="Spring MVC and WebFlux auto-configuration have been restructured — review custom WebMvcConfigurer implementations.",
        category="api",
        phase="migration",
        framework="Spring Boot",
        version="4.0.0",
    ),
    _LifecycleAlert(
        message="Property namespaces changed in Spring Boot 4 — run the properties migrator during upgrade.",
        category="config",
        phase="migration",
        framework="Spring Boot",
        version="4.0.0",
    ),
    _LifecycleAlert(
        message="Actuator endpoints have moved to /actuator/** by default — update health-check URLs post-migration.",
        category="config",
        phase="post-migration",
        framework="Spring Boot",
        version="4.0.0",
    ),
]
