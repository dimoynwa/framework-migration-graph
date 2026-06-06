# WildFly 31.0.0 → 32.0.0 — Filtered Migration Guide

- **Framework:** `wildfly`
- **Range:** `31.0.0` → `32.0.0`
- **Filtered:** 2026-06-06

---

## 🔴 Breaking Changes

| # | JIRA | Title | Impact |
| --- | --- | --- | --- |
| 1 | WFLY-18997, WFLY-19006, WFLY-19007, WFLY-19008, WFLY-19009, WFLY-19012, WFLY-19051 | Removal of legacy security capability | Support for the `org.wildfly.legacy-security` capability is removed. Applications or configurations relying on this legacy security framework must be migrated to the Elytron security framework to avoid deployment or runtime failures. |
| 2 | WFLY-19133 | Undertow mod_cluster filter restriction | Using the Undertow `mod_cluster` filter with legacy security realms is no longer permitted. This will trigger an `OperationFailedException`. You must transition to Elytron-based security configurations for these filters. |

## 🟠 Mandatory Migrations — Security & CVE Fixes

| # | JIRA | Title | Impact |
| --- | --- | --- | --- |
| 1 | WFLY-19032 | Upgrade Snappy Java (CVE-2023-34453/4/5, CVE-2023-43642) | Vulnerable Snappy Java versions are replaced. Ensure your environment uses version `1.1.10.5` or later to mitigate these CVEs. |
| 2 | WFLY-19034 | Upgrade nimbus-jose-jwt (CVE-2023-52428) | Update `nimbus-jose-jwt` to `9.37.3` to patch a security vulnerability. |
| 3 | WFLY-19224 | Suppress Undertow CVE-2023-1973 | WildFly no longer uses Undertow's authentication mechanisms, so CVE-2023-1973 is no longer applicable. Update security scanning suppressions to reflect this change. |
| 4 | WFLY-19225 | Multi-tenancy JWT security (CVE-2023-6236) | To prevent tenant cross-access, ensure your multi-tenancy configuration prevents token reuse across tenants. Add tests to verify this isolation. |
| 5 | WFLY-19088 | Upgrade Apache James Mime4j (CVE-2024-21742) | Update `mime4j` to `0.8.10` to mitigate CVE-2024-21742. |
| 6 | WFLY-19237 | Suppress CVE-2024-23080 | Add a security scan suppression for CVE-2024-23080. |
| 7 | WFLY-18685 | Upgrade Santuario (CVE-2023-44483) | Upgrade to Apache Santuario `3.0.3` to address potential XML security vulnerabilities. |
| 8 | WFLY-18704 | Upgrade ActiveMQ Artemis (CVE-2023-46604) | Upgrade Artemis to `2.31.2` or higher to resolve the remote code execution vulnerability. |

## 🟠 Mandatory Migrations — Major Component Upgrades

| # | JIRA | Title | Impact |
| --- | --- | --- | --- |
| 1 | WFLY-18520 | Upgrade Apache CXF to 4.0.4 | CXF is upgraded to `4.0.4` to fix security issues. Review web services for compatibility with CXF 4.x features. |
| 2 | WFLY-18804, WFLY-19105 | Upgrade Hibernate Search to 7.1 | Hibernate Search is upgraded to `7.1`. Check your search indexing configurations and mapping implementations for breaking API changes. |

## 🟠 Mandatory Migrations — Security Configuration

| # | JIRA | Title | Impact |
| --- | --- | --- | --- |
| 1 | WFLY-18985 | Reload required for Filesystem Security Realm | Updating key-store attributes in a Filesystem Security Realm now requires a server `reload` operation to apply changes. Update your automation scripts to perform a reload after modifying these attributes. |
| 2 | WFLY-19226 | New system property for JWT validation (CVE-2024-1233) | Use the new `wildfly.elytron.jwt.allowed.jku.values.<realm-name>` system property to restrict allowed `jku` values and mitigate CVE-2024-1233. |

## 🟡 Behavioral Changes

| # | JIRA | Title | Impact |
| --- | --- | --- | --- |
| 1 | WFLY-18808 | Removal of deprecated ModuleSpecification API | The `ModuleSpecification` API has been cleaned up. If you have custom extensions or modules using these deprecated methods, replace them with the current API equivalents. |
| 2 | WFLY-19184 | Optional `jakarta.annotation.ManagedBean` usage | Usage of the `ManagedBean` annotation is now optional. This may affect how certain CDI-based deployments are scanned or initialized; verify behavior if relying on this annotation. |

## 🟡 Deprecations

| # | JIRA | Title | Impact |
| --- | --- | --- | --- |
| 1 | WFLY-18808 | Deprecated `ModuleSpecification` usage removed | Obsolete methods within the `ModuleSpecification` class have been removed. Applications utilizing these must be updated to avoid `NoSuchMethodError` during runtime. |

## 🔵 Notable New Capabilities

| # | JIRA | Title | Impact |
| --- | --- | --- | --- |
| 1 | WFLY-18163 | `JaasSecurityRealm` via custom-realm | `JaasSecurityRealm` can now be configured using the `custom-realm` resource, offering greater flexibility in security integration. |

---

## Summary by Priority

| Priority Level | Count | Description |
| --- | --- | --- |
| 🔴 **Breaking** | 2 | Must fix before migrating. |
| 🟠 **Mandatory** | 14 | Security CVEs, component upgrades, security config. |
| 🟡 **Behavioral / Deprecation** | 3 | Assess impact and adjust accordingly. |
| 🔵 **New Capabilities** | 1 | Optional but recommended to leverage. |

## 🚨 Most Critical Items for Migration

* The legacy `org.wildfly.legacy-security` capability has been removed; you must migrate all security configurations to use Elytron.
* Mod_cluster filters using legacy security realms will now fail; migrate these configurations to Elytron-based security.
* Multiple CVEs in core dependencies like Netty, Snappy Java, and ActiveMQ Artemis require immediate dependency version updates.
* Updating filesystem security realm key-store attributes now strictly requires a server `reload` to persist changes.
* Ensure multi-tenant JWT security is configured to prevent cross-tenant access, as required by CVE-2023-6236 mitigation.