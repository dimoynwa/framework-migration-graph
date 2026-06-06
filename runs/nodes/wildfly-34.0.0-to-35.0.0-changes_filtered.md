# WildFly 34.0.0 → 35.0.0 — Filtered Migration Report

- **Framework:** WildFly
- **Range:** `34.0.0` → `35.0.0`
- **Filtered (UTC):** 2026-06-06

---

## 🔴 Breaking Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-20005, WFLY-20007, WFLY-20008, WFLY-20009, WFLY-20011, WFLY-20014, WFLY-20015, WFLY-20017, WFLY-20018, WFLY-20019, WFLY-20020, WFLY-20021, WFLY-20022, WFLY-20023, WFLY-20024, WFLY-20152 | `ModuleIdentifier` removed from multiple subsystems | `ModuleIdentifier` has been removed from JPA/Persistence, Messaging, Pojo, MP Config, Naming, Weld, Web Services, IIOP, XTS, EE (×2), Application Client, Undertow, JSF, Concurrency, and SAR subsystems. Any extension, SPI implementation, or custom subsystem code that imports or passes `org.jboss.modules.ModuleIdentifier` into these subsystem APIs will fail to compile or deploy. Replace all usages with the string-based or `ModuleLoader` equivalents as required by the updated public API. |
| 2 | WFLY-19888 | Minimum Java SE version raised to 17 | WildFly 35 requires Java SE 17 as the minimum runtime. Applications or CI pipelines still running on Java 11 will not start. Update JDK and any toolchain configuration to Java 17 or newer before upgrading. |

---

## 🟠 Mandatory Migrations — Security & CVE Fixes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-19730 | CVE-2024-8391 — Vert.x upgraded to 4.5.10 | Vert.x was upgraded to resolve CVE-2024-8391 (remote code execution). If your application bundles or pins Vert.x independently, update to 4.5.10 or later to avoid a conflicting dependency. |
| 2 | WFLY-19757 | CVE-2024-7254 — protobuf-java upgraded to 3.25.5 | protobuf-java was upgraded to resolve CVE-2024-7254 (denial of service via recursive protobuf parsing). If your application explicitly declares `com.google.protobuf:protobuf-java`, align the version to ≥ 3.25.5. |
| 3 | WFLY-20027, WFLY-20118 | CVE-2024-51127 — HornetQ upgraded to 2.4.11.Final | HornetQ was upgraded twice (2.4.10 then 2.4.11) to fully remediate CVE-2024-51127. If you use the legacy HornetQ subsystem or depend on `org.hornetq` artifacts, verify compatibility with 2.4.11.Final. |
| 4 | WFLY-19969, WFLY-20100 | CVE-2024-10234 — HAL upgraded to 3.7.7.Final | CVE-2024-10234 (XSS in the management console) is addressed via HAL 3.7.7.Final. No user code change is required, but ensure your WildFly installation is updated to pick up the patched console. |

---

## 🟠 Mandatory Migrations — Major Component Upgrades

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-19588, WFLY-19591, WFLY-19592, WFLY-19846, WFLY-19866 | MicroProfile Platform 7 promoted to standard | WildFly 35 ships MicroProfile Platform 7 in the standard (non-preview) distribution. This includes MicroProfile OpenAPI 4.0, Fault Tolerance 4.1, Telemetry 2.0, and REST Client 4.0. Review the MP 7 migration guides for each spec — particularly MP OpenAPI 4.0 annotation changes and MP REST Client 4.0 interface changes — and update your application code accordingly. |
| 2 | WFLY-19905, WFLY-19904, WFLY-19903 | Infinispan 15.x and JGroups 5.3.x upgrade | Infinispan was upgraded from 14.0.x to 15.0.x and JGroups from 5.2.x to 5.3.x. These are major version jumps that may affect custom cache configurations, programmatic Infinispan API usage, and serialization/marshalling compatibility in clustered deployments. Review Infinispan 15 migration notes and verify cluster rolling-upgrade compatibility. |
| 3 | WFLY-19776 | Jakarta Data promoted from Preview to Standard WildFly | Jakarta Data support (previously Preview-only) is now included in the standard WildFly distribution. If your application was using the Preview feature pack to access Jakarta Data, review the standard inclusion for any configuration changes. |
| 4 | WFLY-19859 | Narayana upgraded to 7.1.0.Final | Narayana (JTA/JTS transaction manager) was upgraded to 7.1.0.Final. Applications relying on Narayana-internal APIs or advanced XA/JTS configurations should be validated against this release. |
| 5 | WFLY-19936 | Woodstox upgraded from 6.4.0 to 7.0.0 | Woodstox (StAX parser used throughout WildFly) was upgraded to 7.0.0. This is a major version bump; any application that ships its own Woodstox jar may experience classpath conflicts or API incompatibility. Align to Woodstox 7.0.0 or rely on the server-provided version. |
| 6 | WFLY-19991, WFLY-19993 | WildFly Preview switches to Jakarta Authentication 3.1.0 | WildFly Preview now uses Jakarta Authentication 3.1.0 (elytron-ee 4.0.x). Applications running on WildFly Preview that use custom `ServerAuthModule` implementations or JASPI configuration must be updated for the Jakarta Authentication 3.1 API. |

---

## 🟠 Mandatory Migrations — Security Configuration

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-20001 | Security Policy access switched to Elytron PolicyUtil | WildFly now accesses `java.security.Policy` exclusively via `PolicyUtil` from Elytron EE, removing the previous direct Security Manager API call. If you have custom security policy integrations or SPI implementations that directly call `java.security.Policy.getPolicy()` in subsystem code, update to the Elytron EE `PolicyUtil` approach. |
| 2 | WFLY-20120, WFLY-20122, WFLY-20124 | Security Manager support dropped for Java SE 24+ | The `-Djava.security.manager=allow` JVM flag is no longer passed on SE 24+, and Security Manager-dependent tests have been disabled. If your deployment or startup scripts explicitly set the Security Manager for WildFly, this will fail silently or produce warnings on SE 24+. Remove Security Manager configuration for SE 24 environments. |
| 3 | WFLY-19994, WFLY-20035, WFLY-20043 | Security Manager regressions fixed in Micrometer, Reactive Messaging, and SmallRye OTel | Micrometer 1.14.1, SmallRye Reactive Messaging, and SmallRye OpenTelemetry all had Security Manager regressions that required fixes in WildFly. If you run with Security Manager enabled (SE 17–23), ensure you are on this WildFly 35 release to pick up the fixes; earlier 35.0.0.Beta1 builds had broken behaviour. |

---

## 🟡 Behavioral Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-19393 | Persistence bytecode enhancement enabled by default (then reverted) | Bytecode enhancement for JPA entities was enabled by default in Beta1 (WFLY-19393) but subsequently disabled again in the final release (WFLY-20078). Net effect for 35.0.0.Final: no change vs. WildFly 34. No action required unless you were testing against a Beta build. |
| 2 | WFLY-19981 | New `resteasy-patchfilter-disabled` attribute in jaxrs subsystem | A new `resteasy-patchfilter-disabled` attribute was added to the `jaxrs` subsystem. If you rely on RESTEasy's PATCH filter behaviour and it no longer works as expected, check this new attribute's default. |
| 3 | WFLY-13412 | JSON Merge Patch (RFC 7396) support added to RESTEasy | RESTEasy now supports `application/merge-patch+json` (RFC 7396). If your REST endpoints currently handle `PATCH` requests manually, you may see changed content-type negotiation. Verify PATCH endpoint behaviour. |
| 4 | WFLY-19835, WFLY-19836 | OpenTelemetry integrated with MP Reactive Messaging Kafka and AMQP connectors | OpenTelemetry tracing is now automatically active in Reactive Messaging Kafka and AMQP connectors. If you run without a configured OTel exporter, verify that missing-exporter warnings are acceptable or configure an exporter endpoint. |
| 5 | WFLY-19869 | `@WithSpan` annotations broken in WildFly 34, fixed in 35 | `@WithSpan` (SmallRye OpenTelemetry) stopped producing spans in WildFly 34; this is fixed in WildFly 35. No code change required, but re-enable any tests or monitoring that were disabled due to this regression. |
| 6 | WFLY-20048 | Graceful shutdown freeze with active transactions fixed | A bug causing graceful shutdown to freeze when active transactions were present has been resolved. No configuration change needed, but verify shutdown timeouts in production environments. |
| 7 | WFLY-19883 | JMS XA crash recovery with JTS fixed | JMS XA transaction crash recovery was not working correctly with JTS. If your deployments use JMS XA + JTS, validate recovery behaviour after upgrading. |
| 8 | WFLY-20078 | Persistence bytecode enhancement disabled by default | JPA container bytecode enhancement is disabled by default in 35.0.0.Final (reverting the Beta1 change). If you explicitly relied on automatic bytecode enhancement being active, configure it explicitly in `persistence.xml` via `<shared-cache-mode>` or Hibernate properties. |

---

## 🟡 Deprecations

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-20150 | `javax.servlet.jstl.api` module replaced by `jakarta.servlet.jstl.api` | The legacy `javax.servlet.jstl.api` module reference is deprecated; use `jakarta.servlet.jstl.api` instead. Update any `module.xml` or `jboss-deployment-structure.xml` files that reference the old module name to avoid warnings or breakage in a future release. |
| 2 | WFLY-20165, WFLY-20166, WFLY-20167, WFLY-20170, WFLY-20172, WFLY-20175, WFLY-20176, WFLY-20182 | `ModuleDependency` constructor deprecated — use `ModuleDependency.Builder` | The `ModuleDependency` constructor used throughout TXN, NAMING, APPCLIENT, EE, CLUSTERING, JAKARTA DATA, JSF, and SECURITY subsystems is deprecated. If you write custom WildFly extensions or subsystems that create `ModuleDependency` objects directly, switch to the `ModuleDependency.Builder` API to avoid compile warnings and future removal. |

---

## 🔵 Notable New Capabilities

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-19954 | Vert.x extension added to WildFly Preview | The Vert.x extension/subsystem from `wildfly-vertx-feature-pack` is now available in WildFly Preview. Applications on WildFly Preview can leverage native Vert.x integration. No action required unless you want to opt in. |
| 2 | WFLY-19871 | Channel configuration added to WildFly User BOMs | WildFly User BOMs now include channel configuration metadata, enabling automated version management via WildFly Channels. Update your Maven BOM import to `org.wildfly.bom` in WildFly 35 to take advantage of channel-based provisioning. |
| 3 | WFLY-20072 | Non-shaded `wildfly-cli` artifact added to tools user BOM | The non-shaded `wildfly-cli` artifact is now included in the WildFly tools user BOM, making it easier to depend on the CLI library without fat-jar classpath conflicts. |
| 4 | WFLY-19745 | Systemd service unit documentation added | Community documentation for running WildFly as a systemd service is now available. Useful for bare-metal or VM deployments on systemd-based Linux distributions. |

---

## Summary by Priority

| Priority Level | Count | Description |
| :--- | :--- | :--- |
| 🔴 **Breaking** | 2 | Must fix before migrating. |
| 🟠 **Mandatory** | 13 | Security CVEs, component upgrades, security config. |
| 🟡 **Behavioral / Deprecation** | 10 | Assess impact and adjust accordingly. |
| 🔵 **New Capabilities** | 4 | Optional but recommended to leverage. |

## 🚨 Most Critical Items for Migration

- **ModuleIdentifier API removal across 15+ subsystems (WFLY-20005 et al.):** Any custom WildFly extension, SPI, or subsystem code that passes `org.jboss.modules.ModuleIdentifier` into WildFly subsystem APIs must be refactored to use string-based alternatives before deploying on WildFly 35. Failure to do so will cause compile or deployment failures.

- **Java SE 17 minimum required (WFLY-19888):** WildFly 35 will not run on Java 11. Verify your production JDK, CI toolchain, and any `<maven.compiler.source>` / `<maven.compiler.target>` configurations are aligned to Java 17 or newer.

- **MicroProfile Platform 7 now standard (WFLY-19588):** MP OpenAPI 4.0, Fault Tolerance 4.1, Telemetry 2.0, and REST Client 4.0 are all promoted to standard stability. Review each component's migration guide; MP OpenAPI 4.0 has annotation and schema changes, and MP REST Client 4.0 has interface changes that can cause compile-time or runtime failures.

- **Infinispan 14 → 15 and JGroups 5.2 → 5.3 major upgrade (WFLY-19905, WFLY-19904):** These are major version bumps in the clustering stack. Custom cache configurations, serialization codecs, or programmatic Infinispan API usage require validation. In mixed-version cluster rolling upgrades, verify that the Infinispan serialisation format is compatible before upgrading all nodes.

- **CVE-2024-51127 in HornetQ — upgrade mandatory (WFLY-20027, WFLY-20118):** The HornetQ upgrade to 2.4.11.Final resolves an actively tracked CVE. Deployments that use the legacy HornetQ client or pin HornetQ artifacts must align to 2.4.11.Final to avoid exposure.
