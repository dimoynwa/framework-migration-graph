"""Lightweight framework name constants — no config dependency."""

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
