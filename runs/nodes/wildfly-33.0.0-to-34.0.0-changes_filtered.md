# WildFly Migration Guide — 33.0.0 → 34.0.0

- **Framework:** `wildfly`
- **Resolved range:** `33.0.0` → `34.0.0`
- **Generated (UTC):** 2026-06-06

---

## 🔴 Breaking Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-19287 | EE 11 APIs + Security Manager causes boot failure | WildFly 33 introduced a hard boot failure when EE 11 APIs are combined with the deprecated Java Security Manager. If your deployment uses EE 11 APIs (Jakarta EE 11 namespaces), remove all Security Manager configuration (`-Djava.security.manager`, policy files) before upgrading. Running with Security Manager enabled on Java 17+ is no longer supported. |
| 2 | WFLY-19709 | Java Security Manager broken on Java 17+ | Tests and production deployments relying on the Java Security Manager fail on Java 17 and later. Remove all Security Manager usage from your startup scripts and configuration. This is a hard incompatibility — the server will not function correctly with Security Manager on modern JDKs. |
| 3 | WFLY-19843 | EJB application security domain capability leak | An EJB application security domain does not properly deregister its capability on removal, causing stale capability registration failures on subsequent deploys or redeployments. Ensure you are not relying on hot-undeploy behaviour of the `application-security-domain` resource without a server restart in your pipelines. |

---

## 🟠 Mandatory Migrations — Security & CVE Fixes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-19720, WFLY-19732 | CVE-2024-7885 Undertow HTTP/2 RST_STREAM fix | Undertow was upgraded to 2.3.17+ to address CVE-2024-7885 (UNDERTOW-2429), a remotely exploitable vulnerability in HTTP/2 RST_STREAM handling. WildFly 33.0.2 carries this fix. If you are deploying WildFly 33 as an intermediate step, upgrade to at least 33.0.2 first; WildFly 34 includes this fix. No application-level action required, but verify any custom Undertow configs are compatible with 2.3.17+. |
| 2 | WFLY-19730 | CVE-2024-8391 Vert.x upgrade to 4.5.10 | CVE-2024-8391 in Vert.x is addressed by upgrading to Vert.x 4.5.10. Applications that package their own Vert.x dependency must align to 4.5.10 or later to avoid a conflicting classpath. Remove any overriding Vert.x version in your BOM or `pom.xml` and rely on the WildFly-managed version. |
| 3 | WFLY-19757 | CVE-2024-7254 protobuf-java upgrade to 3.25.5 | CVE-2024-7254 (protobuf parsing stack overflow) is fixed by upgrading `protobuf-java` to 3.25.5. If your application bundles `protobuf-java`, upgrade your dependency to 3.25.5 or remove the bundled copy and rely on the server-provided module. |
| 4 | WFLY-19549 | OIDC SecurityContext deserialization failure | `OIDCSecurityContext` deserialization fails under certain conditions (WildFly 33.0.1 fix). If you use OIDC and replicate security contexts across nodes or persisted sessions, verify session serialization is functioning after upgrade. No configuration change required if upgrading directly to 34. |

---

## 🟠 Mandatory Migrations — Major Component Upgrades

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-19312 | Jakarta REST 4.0 and RESTEasy 7.0 in WildFly Preview | WildFly Preview now ships Jakarta REST 4.0 (EE 11) and RESTEasy 7.0 for EE 11 preview. Applications targeting WildFly Preview must migrate JAX-RS imports from `javax.ws.rs` to `jakarta.ws.rs` (4.0 API) and verify compatibility with RESTEasy 7.0 changes. Standard WildFly continues on RESTEasy 6.2.x. |
| 2 | WFLY-19589 | MicroProfile REST Client 4.0 in WildFly Preview | WildFly Preview upgrades MicroProfile REST Client to 4.0 (MP Platform 7). Review the MicroProfile REST Client 4.0 changelog for breaking API changes, particularly around SSL configuration and providers, and update client proxy code accordingly. |
| 3 | WFLY-19590 | MicroProfile Telemetry 2.0 | MicroProfile Telemetry is upgraded to 2.0. The `MicrometerSetupTask` package was relocated. If you reference this class in tests or custom setup, update the import path. Application code using MP Telemetry APIs should be reviewed for 2.0 API changes. |
| 4 | WFLY-19472 | Jakarta Security Enterprise API 4.0.0 in WildFly Preview | WildFly Preview upgrades to `jakarta.security.enterprise-api` 4.0.0. Applications on WildFly Preview using `jakarta.security.enterprise` must verify API compatibility with 4.0.0; EE 11 security annotations and interfaces have breaking changes compared to 3.x. |
| 5 | WFLY-19306, WFLY-19632 | Hibernate ORM 6.6.1 and Hibernate Search 7.2 | Hibernate ORM is upgraded to 6.6.1.Final and Hibernate Search to 7.2.1.Final. Review the Hibernate ORM 6.6 migration guide for any persistence unit configuration or HQL/Criteria API changes. Check that your second-level cache providers are compatible. Hibernate Commons Annotations is also bumped to 7.0.1.Final. |
| 6 | WFLY-19636, WFLY-19437, WFLY-19166 | Apache Artemis upgraded to 2.37.0 | Apache Artemis is upgraded from 2.34 → 2.35 → 2.37.0. Review the Artemis 2.37 changelog for broker configuration, protocol, and security changes. Deployments using embedded messaging or `messaging-activemq` subsystem configuration should validate broker settings and address-settings merge behaviour (see WFLY-19517). |
| 7 | WFLY-19397 | Jakarta Data support in WildFly Preview | Jakarta Data is now available in WildFly Preview as a preview-stability feature. If you provision WildFly Preview with Galleon and want to use Jakarta Data, include the Jakarta Data layer. Note: provisioning `preview`-stability Jakarta Data modules in a higher-stability context is now blocked (WFLY-19777); ensure your Galleon stability configuration matches. |
| 8 | WFLY-19574 | Arquillian BOM version incompatibility with JUnit 5 | The Arquillian version specified in user-facing BOMs was incompatible with JUnit 5. If you use WildFly's managed Arquillian BOM in your test `pom.xml`, update to the corrected BOM and verify your JUnit 5 test runner still resolves correctly. |
| 9 | WFLY-19464 | User BOMs realigned with WildFly distributions | The WildFly user BOMs (`wildfly-ee`, `wildfly-expansion`, etc.) are now properly aligned with the actual server distributions. If your project imports these BOMs, refresh your dependency management section — versions of managed artifacts may have shifted. Also note the BOM rename: `org.wildfly.bom:wildfly-microprofile` is now `org.wildfly.bom:wildfly-expansion` (WFLY-19756). |

---

## 🟠 Mandatory Migrations — Security Configuration

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-19255 | Legacy SSL realm removed from Undertow tests | Legacy security realm SSL configuration is no longer used in Undertow subsystem tests; the subsystem itself enforces use of Elytron-based SSL contexts. If any of your deployments or configurations still reference legacy `<security-realm>` for SSL on Undertow listeners, migrate to Elytron `<ssl-context>` references. |
| 2 | WFLY-19311 | SCA: wildfly-plugin-tools CVE false-positive suppressed | The `wildfly-plugin-tools` artifact was incorrectly mapped to WildFly server CVEs by OWASP Dependency Check. A suppression was added. If you run Dependency Check as part of your pipeline, update your OWASP suppression configuration to avoid false positives; upgrade OWASP Dependency Check plugin to 10.0.2. |

---

## 🟡 Behavioral Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-19441 | HotRod SNI hostname auto-configuration changed | SNI hostname validation for HotRod/Infinispan remote cache is now decoupled from physical hostnames. Hostname validation is auto-disabled when no SNI hostname is explicitly configured. In Kubernetes/OpenShift environments that previously relied on implicit hostname validation, review your `<remote-cache-container>` configuration and set explicit SNI hostnames if validation is required. |
| 2 | WFLY-19147 | MicroProfile Health disable-default-procedures fix | Setting `mp.health.disable-default-procedures=true` in `microprofile-config.properties` at the application level now correctly disables all default health procedures. If your application previously relied on this property being silently ignored (and default procedures were always enabled), add explicit `@Liveness`/`@Readiness` checks or remove the property if you want defaults. |
| 3 | WFLY-19271, WFLY-19419, WFLY-19514 | Distributed EJB timer reliability improvements | Distributed timer service: timeouts that would fire in the past are now consolidated (WFLY-19419); calendar-based timers coalesce missed timeouts (WFLY-19514); timeout events are no longer dropped when the server is suspended (WFLY-19271). Applications with distributed timers should validate that timer execution counts and timing are as expected after upgrade — coalescing behaviour may collapse what were previously multiple missed firings into a single invocation. |
| 4 | WFLY-19610 | @PostConstruct on Servlet called twice — fixed | A regression caused `@PostConstruct` lifecycle methods on Servlets to be invoked twice. This is fixed in WildFly 34. If you added workarounds (idempotency guards) for this bug, they are safe to keep but no longer required. |
| 5 | WFLY-19613 | HttpSession.getAttribute performance regression — fixed | A performance regression in `HttpSession.getAttribute` (clustering immutability optimisations) is resolved. No application change required; throughput for session-heavy applications should improve. |
| 6 | WFLY-19304 | Datasource XML configuration schema corrected | The datasource subsystem XML schema was incorrectly validating some valid configurations. The model definition and schema are corrected and bumped. Validate your existing datasource XML against the updated schema; configurations that were previously accepted despite being invalid may now be rejected. |
| 7 | WFLY-19664 | Hibernate second-level cache factory ignored — now warns | If `hibernate.cache.region.factory_class` is set in a persistence unit but the JPA provider ignores it (because WildFly manages the cache), a warning is now logged. Review your persistence unit properties and remove `hibernate.cache.region.factory_class` if it is redundant to avoid confusion. |
| 8 | WFLY-19802 | jboss-client.jar missing SASL anonymous provider | `jboss-client.jar` was missing the `wildfly-elytron-sasl-anonymous` provider, causing client-side authentication failures when anonymous SASL was in use. This is fixed. If you distribute `jboss-client.jar` separately, refresh it from WildFly 34. |
| 9 | WFLY-19806 | Clustered singleton MDB broken — fixed | Singleton MDBs in a cluster stopped working due to a regression. This is fixed in WildFly 34. If you worked around this by disabling singleton deployment, re-enable it and retest. |
| 10 | WFLY-19583 | Undertow deployment metrics not exported | Deployment-related Undertow metrics were not exported by the metrics subsystem. This is corrected; no configuration change needed. Verify that your monitoring dashboards now see the expected per-deployment HTTP metrics. |
| 11 | WFLY-19567 | Virtual thread pinning in AbstractJMSContext — fixed | `AbstractJMSContext` used a `ConcurrentHashMap` which caused virtual thread pinning. This is replaced with a non-pinning alternative. Applications using JMS with Java 21 virtual threads will see improved throughput without any code change required. |

---

## 🟡 Deprecations

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-19303 | EJB remote service `cluster` attribute deprecated | The `cluster` attribute on the EJB remote service resource is deprecated. Review your EJB remote service configuration and migrate to the non-deprecated clustering configuration. The attribute still works but will be removed in a future release. |
| 2 | WFLY-19352 | Deprecated MSC API removed from ha-singleton-service | Deprecated MSC (Modular Service Container) API usage is removed from the ha-singleton-service implementation. If you extend or integrate with `ha-singleton-service` internals, update your code to the current MSC API. |

---

## 🔵 Notable New Capabilities

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-19715 | HTTP Management Interface resource limits | New attributes are available on the HTTP management interface to define resource limits (connection count, request rate, etc.). Review the updated admin guide and consider configuring these limits to protect the management interface in production deployments. |
| 2 | WFLY-19573 | WeldCapability includes build compatible extensions | The `WeldCapability` SPI is expanded to include CDI Build Compatible Extensions (BCEs), enabling portable integration of BCE-based libraries with the WildFly subsystem SPI. Extensions that use BCEs can now be registered correctly via the WeldCapability. |
| 3 | WFLY-19235 | Simplified singleton service installation | Singleton service installation API is simplified. Review the updated WildFly documentation for `SingletonServiceConfiguratorFactory` usage if you implement custom HA singleton services. |
| 4 | WFLY-19692 | CLI `read-config-as-xml-file` operation documented | The new `read-config-as-xml-file` CLI operation (from WildFly Core WFCORE-6960) is now documented with updated CLI recipes. This allows exporting the running server configuration as an XML file directly from the CLI without a server restart. |

---

## Summary by Priority

| Priority Level | Count | Description |
| :--- | :--- | :--- |
| 🔴 **Breaking** | 3 | Must fix before migrating. |
| 🟠 **Mandatory** | 15 | Security CVEs, component upgrades, security config. |
| 🟡 **Behavioral / Deprecation** | 13 | Assess impact and adjust accordingly. |
| 🔵 **New Capabilities** | 4 | Optional but recommended to leverage. |

---

## 🚨 Most Critical Items for Migration

- **Java Security Manager must be removed (WFLY-19287, WFLY-19709).** WildFly 34 (and WildFly 33 with EE 11 APIs) will fail to boot or behave incorrectly if the Security Manager is enabled on Java 17+. Audit all startup scripts and server configuration for `-Djava.security.manager` or policy file references and remove them before upgrading.

- **CVE-2024-7885 in Undertow and CVE-2024-8391 in Vert.x require immediate attention (WFLY-19720, WFLY-19730).** Both are remotely exploitable. WildFly 34 includes the fixes; if you upgrade via 33.0.x intermediaries, go to at least 33.0.2. Ensure no internal BOM overrides pin Undertow or Vert.x to a vulnerable version.

- **CVE-2024-7254 in protobuf-java (WFLY-19757).** If your application bundles `protobuf-java`, you must upgrade to 3.25.5. The server-provided module is patched, but a bundled older version will still expose the vulnerability.

- **WildFly Preview users face EE 11 API breaking changes (WFLY-19312, WFLY-19472, WFLY-19589).** Jakarta REST 4.0, MicroProfile REST Client 4.0, and Jakarta Security Enterprise 4.0 are all breaking upgrades. Compile and integration-test your application against WildFly Preview before deploying to production.

- **User BOM rename and realignment (WFLY-19464, WFLY-19756).** The `org.wildfly.bom:wildfly-microprofile` artifact is renamed to `org.wildfly.bom:wildfly-expansion`. Update your `pom.xml` BOM imports to avoid missing dependency management entries that will silently result in wrong transitive versions being resolved.
