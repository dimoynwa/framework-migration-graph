# WildFly 28.0.0 → 29.0.0 — Filtered Migration Guide

- **Framework:** `wildfly`
- **Range:** `28.0.0` → `29.0.0`
- **Filtered:** 2026-06-06

---

## 🔴 Breaking Changes

| # | JIRA | Title | Impact |
| --- | --- | --- | --- |
| 1 | WFLY-17932, WFLY-17909 | Removal of implicit JDK module dependencies | The `sun.jdk` and `ibm.jdk` modules are no longer implicitly available. Deployments relying on internal JDK APIs via these modules will fail. Audit your code for internal JDK imports and replace them with supported standard Java or third-party APIs before upgrading. |
| 2 | WFLY-17666 | Explicit module dependency required for RMI | Deployments using the RMI Java Naming provider no longer have implicit access to it. You must define an explicit dependency on the `jdk.naming.rmi` JPMS module in your deployment configuration (e.g., via `jboss-deployment-structure.xml` or MANIFEST.MF). |
| 3 | WFLY-17290 | TXFramework removal | The TXFramework has been completely removed. If your application relies on this legacy framework for transaction management, you must migrate to standard Jakarta Transactions (JTA) APIs. |
| 4 | WFLY-18152 | Renaming of Jakarta Faces module | The module `jakarta.faces` has been renamed to `jakarta.faces.impl`. Update any explicit module dependencies in your `jboss-deployment-structure.xml` to use the new module name to prevent deployment failures. |
| 5 | WFLY-18164, WFLY-18141, WFLY-18134, WFLY-18145, WFLY-18153 | Internal modules marked as private | Modules including `org.apache.activemq.artemis.*`, clustering internals, Angus, RESTEasy tracing, and XTS have been marked as private. Remove any explicit dependencies on these modules from your applications and utilize standard APIs instead. |

## 🟠 Mandatory Migrations — Security & CVE Fixes

| # | JIRA | Title | Impact |
| --- | --- | --- | --- |
| 1 | WFLY-17455, WFLY-18180 | Upgrade Netty to address HTTP/2 CVEs | Netty has been upgraded to 4.1.94.Final to patch CVE-2022-41881 and CVE-2023-34462. Ensure any direct or BOM-managed Netty dependencies in your applications are updated to at least `4.1.94.Final` to mitigate denial-of-service vulnerabilities. |
| 2 | WFLY-18007 | Upgrade Xalan to patch CVE-2022-34169 | Xalan has been updated to version 2.7.3 to resolve an integer truncation issue. Update your application BOMs and direct dependencies to utilize Xalan 2.7.3. |
| 3 | WFLY-17654 | Upgrade Kafka Clients to patch CVE-2023-25194 | Kafka clients have been upgraded to 3.4.0 to resolve a vulnerability. Update your Maven dependencies for `kafka-clients` to 3.4.0 or higher. |
| 4 | WFLY-18243 | Upgrade Guava to patch CVE-2023-2976 | Guava is upgraded to 32.1.1 to mitigate CVE-2023-2976. Applications bundling Guava should update their dependencies to version 32.1.1 or later. |
| 5 | WFLY-17499 | Upgrade Apache Mime4J to patch CVE-2022-45787 | Mime4J has been upgraded to 0.8.9 to resolve CVE-2022-45787. Ensure any bundled usage of this library in your deployments is updated accordingly. |
| 6 | WFLY-17845 | Upgrade Nimbus JOSE JWT to patch CVE-2023-1370 | Nimbus JOSE JWT is upgraded to 9.24.4 (and later 9.31) to address CVE-2023-1370. Update your JWT processing library dependencies to incorporate this security fix. |

## 🟠 Mandatory Migrations — Major Component Upgrades

| # | JIRA | Title | Impact |
| --- | --- | --- | --- |
| 1 | WFLY-17602 | IronJacamar upgraded to 3.0.x (Jakarta EE 10) | IronJacamar has undergone a major version bump to 3.0.0.Final to align with Jakarta EE 10. Resource adapters and JCA deployments must be updated to the new Jakarta namespace (`jakarta.resource.*`). |
| 2 | WFLY-18083, WFLY-18200 | Hibernate ORM upgrades | Hibernate ORM is upgraded to 6.2.6.Final. Review the Hibernate 6.2 migration guides for API, mapping, and behavioral changes affecting your JPA implementations (specifically around array mappings for Character[] and Byte[]). |

## 🟠 Mandatory Migrations — Security Configuration

| # | JIRA | Title | Impact |
| --- | --- | --- | --- |
| 1 | WFLY-15487 | PicketBox Vault replaced by Elytron | Legacy PicketBox Vault integration is replaced. You must convert existing vaults to Elytron Credential Stores. Use the provided CLI tools to migrate your credentials and update any encrypted expressions (e.g., `${VAULT::...}`) in your server configuration to the new Elytron syntax. |
| 2 | WFLY-16764, WFLY-16857 | Legacy security domain migration | Legacy security has been purged from several subsystems. Migrate your application security configurations from legacy security domains to Elytron security domains. |
| 3 | WFLY-18161 | AdvancedSecurityMetaData implementation change | Internal representations of security metadata have moved from web common to server security (`org.jboss.as.server.security.AdvancedSecurityMetaData`). Custom server extensions relying on the old web-common classes must be refactored to use the new package. |

## 🟡 Behavioral Changes

| # | JIRA | Title | Impact |
| --- | --- | --- | --- |
| 1 | WFLY-17958 | Persistence container bytecode enhancement disabled | Bytecode enhancement by the persistence container is no longer enabled by default. If your JPA entities rely on load-time weaving (e.g., for lazy loading of non-collection properties), you must explicitly configure enhancement in your `persistence.xml`. |
| 2 | WFLY-14387 | Resource adapters wm-security expression rejection | The `wm-security` attribute in the resource adapters subsystem no longer accepts expressions. Hardcode this configuration value or handle dynamic security assignment within your adapter implementation. |
| 3 | WFLY-18023, WFLY-18024, WFLY-18036, WFLY-18065 | Optimization of distributed Stateful Session Beans | Caching, marshaling, and replication for distributed `@SessionScoped` `@Stateful` EJBs have been optimized, reducing unnecessary proxy placeholder replication and cache transactions. Retest stateful failover in your clustered deployments to ensure expected state continuity. |
| 4 | WFLY-17703 | PersistentSubsystemSchema adoption | Numerous subsystems (health, metrics, validation, JWT, openapi) have migrated their parsers to `PersistentSubsystemSchema`. Configuration exported via `read-config-as-xml` will use the latest schema versions. Ensure automation expects the updated schema layouts. |

## 🟡 Deprecations

| # | JIRA | Title | Impact |
| --- | --- | --- | --- |
| 1 | WFLY-17334, WFLY-17473, WFLY-17475 | Deprecation of legacy MSC injection APIs | Internal legacy JBoss Modular Service Container (MSC) injection classes (`ValueInjectionService`, `MapInjector`, `AbstractService`) are deprecated and being eliminated. Custom WildFly extensions should migrate to the modern ServiceBuilder APIs. |
| 2 | WFLY-17941, WFLY-17942, WFLY-18045 | Deprecation of subsystem definition APIs | Management API definitions like `SimpleOperationDefinition`, `AttributeDefinition`, and `ManagementResourceRegistration` have been deprecated in favor of their builder-based counterparts. Authors of custom subsystems must update their resource definitions. |
| 3 | WFLY-17931, WFLY-17933, WFLY-17934 | Deprecation of legacy javax API modules | The `javax.api`, `javax.sql.api`, and `javax.xml.stream.api` modules are officially deprecated. Update your deployments to depend on the appropriate Jakarta (`jakarta.*`) namespace modules. |
| 4 | WFLY-17288 | Deprecation of JDBC `driver-name` attribute | The `driver-name` attribute for JDBC drivers is deprecated. Update your datasource definitions to utilize standard driver resolution mechanisms or updated attributes. |

## 🔵 Notable New Capabilities

| # | JIRA | Title | Impact |
| --- | --- | --- | --- |
| 1 | WFLY-15260 | Secure management console with OIDC | You can now secure the WildFly management console using OpenID Connect (OIDC). This allows you to integrate management authentication with modern identity providers like Keycloak. |
| 2 | WFLY-13978 | YAML support for system properties and config | System properties and configuration customizations can now be supplied via YAML files, providing a cleaner, more modern alternative to standard XML configurations for cloud-native deployments. |
| 3 | WFLY-17144, WFLY-17681 | Micrometer integration | WildFly now offers integrated support for Micrometer, including support for MicroProfile Fault Tolerance metrics, enabling seamless metrics collection for systems like Prometheus and Datadog. |
| 4 | WFLY-14869 | MicroProfile LRA support | Support for MicroProfile Long Running Actions (LRA) has been added, allowing you to implement Saga-pattern distributed transactions in your microservices architecture. |

---

## Summary by Priority

| Priority Level | Count | Description |
| --- | --- | --- |
| 🔴 **Breaking** | 5 | Must fix before migrating. |
| 🟠 **Mandatory** | 11 | Security CVEs, component upgrades, security config. |
| 🟡 **Behavioral / Deprecation** | 8 | Assess impact and adjust accordingly. |
| 🔵 **New Capabilities** | 4 | Optional but recommended to leverage. |

## 🚨 Most Critical Items for Migration

* Implicit dependencies on internal JDK modules (`sun.jdk`, `ibm.jdk`) have been removed; any code using internal JVM classes will fail to deploy and must be refactored to use standard APIs.
* Legacy PicketBox Vaults have been completely removed. You must migrate all vaulted credentials to Elytron Credential Stores and update your XML configurations accordingly.
* IronJacamar has undergone a major version bump; ensure resource adapters are updated to Jakarta EE 10 standards (`jakarta.resource.*`).
* Netty, Guava, and Kafka clients contain critical CVE patches; verify that your application dependencies and BOMs are updated to the patched versions.