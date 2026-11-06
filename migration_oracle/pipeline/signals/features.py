"""Feature vocabulary (spec 027 FR-2).

One entry per feature a rule can need. Each feature carries the System-1
question text and the **evidence keys**: the profile keys (spec 026) from which
the planner can tell, without asking anybody, that a service has the feature.

This is plain data so the planner can export it unchanged. Adding, removing or
rewording a feature is a change to the question contract: bump
``SIGNAL_QUESTIONS_VERSION`` (``questions.py``).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Feature:
    """One feature a rule may depend on."""

    id: str
    # Full ``noul`` instruction sent to System-1 (FR-3).
    question: str
    # Profile keys, any one of which proves the service has the feature.
    evidence_keys: tuple[str, ...] = ()


ANGULAR_FEATURES: tuple[Feature, ...] = (
    Feature(
        "ssr",
        "Does this rule only matter for applications that use server-side "
        "rendering or prerendering?",
        ("npm:@angular/ssr", "npm:@angular/platform-server"),
    ),
    Feature(
        "hydration",
        "Does this rule only matter for applications that use client hydration?",
        ("npm:@angular/platform-browser#provideClientHydration",),
    ),
    Feature(
        "zoneless",
        "Does this rule only matter for applications that use zoneless change "
        "detection?",
        (
            "npm:@angular/core#provideZonelessChangeDetection",
            "npm:@angular/core#provideExperimentalZonelessChangeDetection",
        ),
    ),
    Feature(
        "zone",
        "Does this rule only matter for applications that rely on Zone.js for "
        "change detection?",
        ("npm:zone.js",),
    ),
    Feature(
        "animations",
        "Does this rule only matter for applications that use @angular/animations?",
        ("npm:@angular/animations",),
    ),
    Feature(
        "router",
        "Does this rule only matter for applications that use the Angular Router?",
        ("npm:@angular/router",),
    ),
    Feature(
        "forms",
        "Does this rule only matter for applications that use template-driven or "
        "reactive forms?",
        ("npm:@angular/forms",),
    ),
    Feature(
        "http",
        "Does this rule only matter for applications that use HttpClient?",
        (
            "npm:@angular/common/http#provideHttpClient",
            "npm:@angular/common/http#HttpClientModule",
        ),
    ),
    Feature(
        "i18n",
        "Does this rule only matter for applications that use @angular/localize "
        "for internationalization?",
        ("npm:@angular/localize",),
    ),
    Feature(
        "service-worker",
        "Does this rule only matter for applications that use "
        "@angular/service-worker?",
        ("npm:@angular/service-worker",),
    ),
    Feature(
        "testbed",
        "Does this rule only matter for applications with unit tests that use "
        "TestBed?",
        ("npm:@angular/core/testing#TestBed",),
    ),
    Feature(
        "karma",
        "Does this rule only matter for applications whose tests run with Karma?",
        ("npm:karma",),
    ),
    Feature(
        "ngmodule",
        "Does this rule only matter for applications with NgModule-based "
        "(non-standalone) components?",
        ("npm:@angular/core#NgModule",),
    ),
    Feature(
        "elements",
        "Does this rule only matter for applications that use Angular Elements?",
        ("npm:@angular/elements",),
    ),
    Feature(
        "upgrade",
        "Does this rule only matter for applications that run an AngularJS hybrid "
        "through @angular/upgrade?",
        ("npm:@angular/upgrade",),
    ),
    Feature(
        "cli-build",
        "Does this rule only matter for applications built with the Angular CLI "
        "build or dev-server?",
        (),
    ),
)

SPRING_BOOT_FEATURES: tuple[Feature, ...] = (
    Feature(
        "web-mvc",
        "Does this rule only matter for applications that serve HTTP with Spring "
        "MVC (spring-boot-starter-web)?",
        ("maven:org.springframework.boot:spring-boot-starter-web",),
    ),
    Feature(
        "webflux",
        "Does this rule only matter for applications that use Spring WebFlux?",
        ("maven:org.springframework.boot:spring-boot-starter-webflux",),
    ),
    Feature(
        "security",
        "Does this rule only matter for applications that use Spring Security?",
        ("maven:org.springframework.boot:spring-boot-starter-security",),
    ),
    Feature(
        "data-jpa",
        "Does this rule only matter for applications that use Spring Data JPA / "
        "Hibernate?",
        ("maven:org.springframework.boot:spring-boot-starter-data-jpa",),
    ),
    Feature(
        "data-mongodb",
        "Does this rule only matter for applications that use Spring Data MongoDB?",
        ("maven:org.springframework.boot:spring-boot-starter-data-mongodb",),
    ),
    Feature(
        "data-redis",
        "Does this rule only matter for applications that use Spring Data Redis?",
        ("maven:org.springframework.boot:spring-boot-starter-data-redis",),
    ),
    Feature(
        "kafka",
        "Does this rule only matter for applications that use Spring for Apache "
        "Kafka?",
        ("maven:org.springframework.kafka:spring-kafka",),
    ),
    Feature(
        "actuator",
        "Does this rule only matter for applications that expose Spring Boot "
        "Actuator endpoints?",
        ("maven:org.springframework.boot:spring-boot-starter-actuator",),
    ),
    Feature(
        "observability",
        "Does this rule only matter for applications that use Micrometer "
        "observability (metrics, tracing)?",
        (
            "maven:io.micrometer:micrometer-core",
            "maven:io.micrometer:micrometer-tracing",
            "maven:io.micrometer:micrometer-registry-prometheus",
        ),
    ),
    Feature(
        "jackson",
        "Does this rule only matter for applications that serialize JSON with "
        "Jackson?",
        ("maven:com.fasterxml.jackson.core:jackson-databind",),
    ),
    Feature(
        "batch",
        "Does this rule only matter for applications that use Spring Batch?",
        ("maven:org.springframework.boot:spring-boot-starter-batch",),
    ),
    Feature(
        "testing",
        "Does this rule only matter for applications with tests that use "
        "spring-boot-starter-test?",
        ("maven:org.springframework.boot:spring-boot-starter-test",),
    ),
    Feature(
        "cloud",
        "Does this rule only matter for applications that use Spring Cloud?",
        (
            "maven:org.springframework.cloud:spring-cloud-dependencies",
            "maven:org.springframework.cloud:spring-cloud-starter-config",
        ),
    ),
    Feature(
        "gradle",
        "Does this rule only matter for applications built with Gradle?",
        ("cfg:build.gradle", "cfg:build.gradle.kts"),
    ),
    Feature(
        "maven",
        "Does this rule only matter for applications built with Maven?",
        ("cfg:pom.xml",),
    ),
)

# Evidence keys arrive with a WildFly scanner (spec 027 FR-2).
WILDFLY_FEATURES: tuple[Feature, ...] = tuple(
    Feature(
        subsystem,
        f"Does this rule only matter for applications that use the {subsystem} "
        "subsystem?",
    )
    for subsystem in (
        "undertow",
        "ejb3",
        "messaging-activemq",
        "elytron",
        "jpa",
        "security",
        "jaxrs",
        "webservices",
        "batch",
        "jsf",
        "cdi",
    )
)

_FEATURES: dict[str, tuple[Feature, ...]] = {
    "angular": ANGULAR_FEATURES,
    "spring-boot": SPRING_BOOT_FEATURES,
    "wildfly": WILDFLY_FEATURES,
}


def features_for(framework_key: str = "", framework_display: str = "") -> tuple[Feature, ...]:
    """Feature vocabulary for a framework, empty when there is none yet."""
    for candidate in (framework_key.strip().lower(), framework_display.strip().lower()):
        if not candidate:
            continue
        for key, features in _FEATURES.items():
            if key in candidate or candidate in key:
                return features
    return ()


def feature_ids(framework_key: str = "", framework_display: str = "") -> list[str]:
    return [feature.id for feature in features_for(framework_key, framework_display)]
