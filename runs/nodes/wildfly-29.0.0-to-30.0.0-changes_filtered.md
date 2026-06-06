# WildFly 29.0.0 → 30.0.0 — Filtered Migration Guide

- **Framework:** `wildfly`
- **Range:** `29.0.0` → `30.0.0`
- **Filtered:** 2026-06-06

---

## 🔴 Breaking Changes & Deprecations

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-18635 | Drop support for scattered cache | Scattered cache configurations are no longer supported. If your distributed caching strategies rely on scattered caches, you must migrate to standard distributed or replicated cache modes in Infinispan. |
| 2 | WFLY-17931, WFLY-17932, WFLY-17933, WFLY-17934 | Elimination of legacy `javax` and `sun.jdk` modules | WildFly has eliminated internal usage of the deprecated `javax.api`, `javax.sql.api`, `javax.xml.stream.api`, and `sun.jdk` modules. Deployments still relying on these legacy aliases must update to the standard `jakarta.*` or standard Java module equivalents. |
| 3 | WFLY-18159, WFLY-16168, WFLY-18047, WFLY-18311 | Legacy Xerces deprecation and JAXP adoption | The `org.apache.xerces` module is deprecated. Core subsystems (RESTEasy, WebServices, Hibernate Validator) have been migrated to use standard JDK JAXP instead. Ensure your application XML parsers are compatible with the JDK-provided JAXP implementation. |
| 4 | WFLY-18039, WFLY-18045, WFLY-18053 | Removal of deprecated extension APIs | Internal management APIs such as `AttributeDefinition`, `ManagementResourceRegistration`, and `ConfigurationPersister` have had their deprecated usages removed. Authors of custom WildFly extensions must migrate to current Builder-based APIs. |

## 🟠 Mandatory Migrations — Security & CVE Fixes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-18625 | Upgrade Netty to address HTTP/2 Rapid Reset (CVE-2023-44487) | Netty has been aggressively upgraded to `4.1.100.Final` to mitigate the critical HTTP/2 Rapid Reset vulnerability. Ensure any bundled Netty dependencies in your application are also updated to this version. |
| 2 | WFLY-18301 | Upgrade Okio to patch CVE-2023-3635 | Okio has been upgraded to `3.4.0` to address a security vulnerability. Update your project BOMs to inherit this safe version. |
| 3 | WFLY-18345, WFLY-18158 | Oracle JDBC driver deployment requires `jdk.security.jgss` | Oracle JDBC drivers deployed as standard deployments may throw `ClassNotFoundException: com.sun.security.jgss.InquireType`. You must manually add a dependency on the `jdk.security.jgss` module in your `jboss-deployment-structure.xml` or MANIFEST. |
| 4 | WFLY-18208, WFLY-18622 | Security Manager testing and permission fixes | Several internal modules (like BouncyCastle and SimpleTimerMDB) have been hardened to run correctly under a Security Manager. Review custom applications using the Java Security Manager for proper policy declarations. |

## 🟠 Mandatory Migrations — Major Component Upgrades

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-18262 | Narayana upgraded to 7.0.0.Final | The transaction manager has undergone a major version bump. Validate your JTA and distributed transaction implementations, particularly those leveraging advanced XTS or LRA features. |
| 2 | WFLY-18555, WFLY-18609 | Hibernate ORM upgrades | Hibernate ORM has been updated to the `6.3.x` stream (ending at `6.3.1.Final` for 30.0.0). Review Hibernate 6.3 migration notes for slight query, mapping, and behavioral enhancements. |
| 3 | WFLY-18416 | Infinispan upgraded to 14.0.17.Final | Underlying clustered data grids are bumped to Infinispan 14.0.17. Ensure custom Infinispan client configurations match the updated server protocol versions. |
| 4 | WFLY-18449 | JGroups upgraded to 5.2.19.Final | The clustering communication layer is updated. Retest node discovery and state transfer in clustered and domain-mode setups. |

## 🟡 Behavioral Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-18389, WFLY-18404, WFLY-18568 | HotRod session manager optimizations | Bugs causing premature session expiration (`max-active-sessions`) and excessive thread creation during expiration events in HotRod-backed web sessions have been resolved. Distributed web applications will see more stable memory and thread usage. |
| 2 | WFLY-18306 | Infinispan remote-timeout validations | The default Infinispan `remote-timeout` will no longer be allowed to be set lower than the `lock-timeout`. Configuration parsing will now fail or auto-adjust if this logical constraint is violated. |
| 3 | WFLY-18360 | Improved bytecode enhancement logs | When a Persistence unit deployment fails due to bytecode enhancement issues, the container now outputs significantly clearer diagnostic logs to aid in troubleshooting. |
| 4 | WFLY-18237 | Dynamic connector addition | Adding a new connector to the server no longer requires a full server reload, reducing downtime for networking topology changes. |
| 5 | WFLY-16522 | Podman support on RHEL | Testing and development scripts have been optimized to evaluate and support `podman` instead of `docker` on RHEL systems, aligning with modern Linux container standards. |

## 🔵 Notable New Capabilities

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-17614 | Cloud documentation section | WildFly now features a dedicated Cloud section in the official documentation, providing best practices for Kubernetes, OpenShift, and containerized deployments. |
| 2 | WFLY-18612 | Advanced provisioning profiles | Support has been added for optional `provisioned-server`, `bootable-jar`, and `openshift` profile build testing, easing the CI/CD pipeline creation for custom WildFly distributions. |

---

## Summary by Priority

| Priority Level | Count | Description |
| :--- | :--- | :--- |
| 🔴 **Breaking / Deprecation** | 4 | Dropped cache modes, legacy JDK/javax module removal. |
| 🟠 **Mandatory Migration** | 8 | Critical CVEs (Netty, Okio), major version bumps (Narayana 7). |
| 🟡 **Behavioral Changes** | 5 | HotRod optimizations, dynamic connectors, logging improvements. |
| 🔵 **New Capabilities** | 2 | Cloud documentation, advanced build profiles. |

## 🚨 Most Critical Items for Migration
- **HTTP/2 Rapid Reset (CVE-2023-44487):** Update all instances of Netty to `4.1.100.Final`. This is a critical network-level security fix.
- **Narayana 7.0 Upgrade:** Exhaustively test transaction lifecycles, especially in complex distributed environments or when integrating with external resource managers.
- **Scattered Cache Removal:** If your clustering configuration relies on `<scattered-cache>`, you must refactor your Infinispan subsystem configuration to use `<distributed-cache>` or `<replicated-cache>` before starting the server.
- **JDBC Driver Module Updates:** If utilizing Oracle JDBC, explicitly map the `jdk.security.jgss` module to prevent runtime `ClassNotFoundException` errors.