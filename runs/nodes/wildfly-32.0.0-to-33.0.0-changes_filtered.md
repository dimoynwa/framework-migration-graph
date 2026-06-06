# WildFly Migration Filter — 32.0.0 → 33.0.0

- **Framework:** `wildfly`
- **Source range:** `32.0.0` → `33.0.0`
- **Filter phase:** Phase 5 (filter-and-group)
- **Generated (UTC):** 2026-06-06

---

## 🔴 Breaking Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-19287 | Boot fails with EE 11 APIs + Security Manager | WildFly 33 will refuse to start if EE 11 APIs are present in the deployment and the Java Security Manager is enabled simultaneously. If your server is running with the Security Manager, you must disable it before adopting any EE 11 (Jakarta EE 11) APIs. Review your server launch arguments and remove `-Djava.security.manager` or equivalent policy flags before upgrading. |
| 2 | WFLY-5820 | Messaging schema namespace renamed | The EJB messaging schema namespace `urn:delivery-active` has been renamed to `urn:delivery`. Any XML descriptor or configuration file that references the old namespace will fail to parse after the upgrade. Scan your deployment descriptors and server configuration files for `urn:delivery-active` and replace it with `urn:delivery`. |
| 3 | WFLY-19133 | Undertow mod_cluster + legacy security realm now rejected | Using the Undertow mod_cluster filter with a legacy security realm now throws `OperationFailedException` at boot instead of silently proceeding. Migrate the mod_cluster filter to use an Elytron SSL context. Legacy security realms are no longer accepted in this context. |
| 4 | WFLY-19098 | Custom Galleon provisioning creates unsecured http-invoker | Servers provisioned with custom Galleon configurations (without the default security layers) left the `http-invoker` endpoint unauthenticated (CVE-2023-4503). After upgrading you must explicitly include the appropriate Elytron security layer in your custom Galleon provisioning descriptor to secure the http-invoker. |

---

## 🟠 Mandatory Migrations — Security & CVE Fixes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-18520 | CXF upgraded to 4.0.4 — CVE-2024-28752 | Apache CXF was upgraded to 4.0.4 to resolve CVE-2024-28752 (XML signature wrapping attack). If your application uses WS-Security with CXF, verify that your existing WS-Security configurations remain compatible with CXF 4.0.4 semantics and test your SOAP endpoints after the upgrade. |
| 2 | WFLY-19032 | Snappy Java upgraded — 4 CVEs resolved | Snappy Java was upgraded to 1.1.10.5, resolving CVE-2023-34453, CVE-2023-34454, CVE-2023-34455, and CVE-2023-43642. No application-level changes are needed, but if your application bundles snappy-java directly you must align to 1.1.10.5 or later to avoid duplicate CVE exposure. |
| 3 | WFLY-19034 | nimbus-jose-jwt upgraded — CVE-2023-52428 | nimbus-jose-jwt was upgraded to 9.37.3 to resolve CVE-2023-52428. Applications that rely on JWT processing via the Elytron subsystem or the OIDC client should test JWT validation flows after upgrading to confirm no regressions. |
| 4 | WFLY-19088 | Apache James Mime4j upgraded — CVE-2024-21742 | Apache James Mime4j was upgraded to 0.8.10 to fix CVE-2024-21742 (MIME header injection). If your application parses MIME messages using the WildFly-bundled Mime4j, no action is required beyond the upgrade; however, applications that bundle Mime4j independently must upgrade their own copy. |
| 5 | WFLY-19193 | Netty upgraded to 4.1.108.Final — CVE-2024-29025 | Netty was upgraded to 4.1.108.Final to address CVE-2024-29025. If your application adds Netty as a deployment dependency, update that dependency to at least 4.1.108.Final. |
| 6 | WFLY-19226 | JWT JKU allow-list system property documented — CVE-2024-1233 | CVE-2024-1233 (JWT `jku` header injection) is addressed by a new system property `wildfly.elytron.jwt.allowed.jku.values.<realm-name>`. After upgrading, set this system property to an explicit allow-list of trusted JKU URLs for every Elytron JWT realm that validates JWTs from external issuers. Leaving it unset retains permissive behaviour and may remain exploitable. |
| 7 | WFLY-19225 | OIDC multi-tenancy token isolation — CVE-2023-6236 | CVE-2023-6236 allowed a valid JWT from one OIDC tenant to be accepted by another tenant. WildFly 33 enforces tenant isolation; review your `elytron-oidc-client` multi-tenant configurations to confirm that each tenant's realm configuration is correctly scoped. |
| 8 | WFLY-19494 | Undertow CVE-2024-6162 resolved (Undertow 2.3.14.Final) | CVE-2024-6162 is fixed in the Undertow version bundled with WildFly 33. No configuration change is required, but if you maintain a CVE suppression list in your security tooling, update it to record that CVE-2024-6162 is resolved in Undertow 2.3.14.Final. |

---

## 🟠 Mandatory Migrations — Major Component Upgrades

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-19472, WFLY-19471 | WildFly Preview: Jakarta Security 4.0 + Servlet 6.1 | WildFly Preview now ships Jakarta Security Enterprise API 4.0.0 and jakarta-servlet-api 6.1.0 for EE 11. Applications running on WildFly Preview that use Jakarta Security or Servlet APIs must update their compile-time dependencies to the 4.0 / 6.1 API JARs and retest all authentication/authorisation flows and servlet lifecycle behaviour. Standard WildFly (EE 10) is unaffected. |
| 2 | WFLY-19312 | WildFly Preview: Jakarta REST 4.0 + RESTEasy 7.0 | WildFly Preview upgrades to Jakarta REST 4.0 and RESTEasy 7.0 for EE 11. REST applications on WildFly Preview must re-compile against the `jakarta.ws.rs` 4.0 API and validate that REST resources, providers, and clients are compatible with RESTEasy 7.0. Standard WildFly uses RESTEasy 6.2.9.Final and is unaffected. |
| 3 | WFLY-19400, WFLY-19401, WFLY-19402, WFLY-19403, WFLY-19404 | WildFly Preview: EE 11 API suite upgrades | WildFly Preview moves to Jakarta Faces 4.1.0, Jakarta Persistence 3.2.0, Jakarta Validation 3.1.0, and Jakarta WebSocket 2.2.0. Applications on WildFly Preview depending on these APIs must update their pom.xml/build.gradle dependency declarations and retest persistence mappings, JSF views, bean validation constraints, and WebSocket endpoints. |
| 4 | WFLY-19166, WFLY-19437 | Apache Artemis upgraded to 2.35.0 | Apache Artemis progressed from 2.32.0 to 2.35.0 through this release range. If you customise Artemis configuration (address settings, HA policies, AMQP connectors), review the Artemis 2.33–2.35 changelogs for any removed or changed defaults. The `AddressSettings` default value handling was corrected (WFLY-19517/WFLY-18547); verify that your `#` default address settings still produce the expected behaviour. |
| 5 | WFLY-19313, WFLY-19338, WFLY-19388, WFLY-19443, WFLY-19480 | WildFly Core upgraded to 25.0.0.Final | WildFly Core advanced from 24.0.0.Final to 25.0.0.Final. If you author WildFly subsystem extensions or use WildFly Core APIs directly, review WildFly Core 25 release notes for any removed or changed internal APIs. General application deployments are not expected to require changes. |
| 6 | WFLY-19353, WFLY-19031 | RESTEasy upgraded to 6.2.9.Final | RESTEasy was upgraded from 6.2.7.Final to 6.2.9.Final in standard WildFly. Test your JAX-RS endpoints after the upgrade; verify message-body reader/writer selection and exception-mapping behaviour is unchanged. |
| 7 | WFLY-19278, WFLY-19279, WFLY-19382, WFLY-19474, WFLY-19516 | Infinispan + JGroups major point upgrades | Infinispan progressed to 14.0.29.Final and JGroups to 5.2.27.Final. Clustered deployments using distributed caches or session replication should perform rolling-upgrade testing to verify cluster formation, cache replication, and failover behaviour remain correct. |
| 8 | WFLY-18997, WFLY-19006, WFLY-19007, WFLY-19008, WFLY-19009, WFLY-19012, WFLY-19051 | Legacy security capability removed from subsystems | The `org.wildfly.legacy-security` capability's Stage.RUNTIME usage has been removed from the connector, EJB3, EE, Undertow, WebServices, and messaging subsystems. If any of those subsystems in your server configuration still reference legacy `<security-domain>` elements rather than Elytron security domains, the server will fail to boot. Migrate all remaining legacy security domain references in those subsystems to Elytron `<security-domain>` backed by an Elytron security realm. |
| 9 | WFLY-18985 | Filesystem Security Realm key-store reload required | Updating key-store attributes on a Filesystem Security Realm now requires a server reload to take effect. Document this operational requirement in your runbooks; automated provisioning or configuration management scripts that update key-store attributes must issue a `:reload` operation immediately after. |
| 10 | WFLY-19110 | Connector application security configuration restored | The application security configuration for the JCA connector subsystem was restored after it was unintentionally removed. If you provisioned a server without the application security configuration in the connector subsystem during WildFly 32, verify that your datasource/resource adapter security settings are correctly applied after upgrading to WildFly 33. |

---

## 🟠 Mandatory Migrations — Security Configuration

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-18163 | JaasSecurityRealm now usable via custom-realm | It is now possible to reference `JaasSecurityRealm` through the Elytron `custom-realm` resource. If your application previously worked around the absence of this capability with a different configuration, you can now migrate to the supported `custom-realm` approach. Existing configurations are not broken, but the new path is the recommended one going forward. |
| 2 | WFLY-19315 | Jakarta XML namespace entries in deployment descriptors | Deployment descriptors (web.xml, ejb-jar.xml, etc.) must use Jakarta EE XML namespaces (`xmlns="https://jakarta.ee/xml/ns/jakartaee"`) rather than the older `javax` namespace forms. WildFly 33's deployment transformer enforces this more strictly. Scan all WEB-INF and META-INF XML descriptors and update any remaining `javax`-prefixed namespace URIs to the Jakarta equivalents. |

---

## 🟡 Behavioral Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-19326 | Netty LinkageError on deployment fixed | A `LinkageError: loader constraint violation for class io.netty.*` that occurred when deploying applications that included their own Netty dependency alongside WildFly's Netty module has been resolved. Applications that previously failed to deploy for this reason should now deploy cleanly, but verify your module dependency declarations are still correct. |
| 2 | WFLY-18174 | Jakarta Faces FACELETS_BUFFER_SIZE default changed to -1 | The default value of `jakarta.faces.FACELETS_BUFFER_SIZE` was changed from a fixed positive value to `-1` (auto-sizing). JSF applications that relied on the previous fixed buffer size for rendering large Facelets pages may see memory allocation changes. Test rendering of large views and explicitly set this context parameter in `web.xml` if you need the previous behaviour. |
| 3 | WFLY-19392 | Hibernate enhancer properties activate class transformer | `jboss.as.jpa.classtransformer` is now implicitly activated if any `hibernate.enhancer.*` property is set to `true` in `persistence.xml`. Previously you had to set both. If you relied on enabling Hibernate bytecode enhancement without the WildFly class transformer being involved, review your persistence unit configuration and test JPA entity proxying and lazy loading. |
| 4 | WFLY-19355 | OpenAPI multiple-endpoint NPE fixed | Deploying multiple applications that each expose an OpenAPI endpoint no longer throws a `NoSuchElementException`. No action required, but if you previously worked around this with a single aggregated deployment, you can revert to separate deployments. |
| 5 | WFLY-19305 | Artemis live-only HA ClassCastException fixed | A `ClassCastException` when running the live-only HA policy in the `messaging-activemq` subsystem has been fixed. No configuration change required; clusters using live-only HA policies should verify correct failover behaviour after the upgrade. |
| 6 | WFLY-19147 | MicroProfile Health disable-default-procedures now respected | Setting `mp.health.disable-default-procedures=true` in `microprofile-config.properties` at application level now correctly disables all built-in WildFly health procedures. If your application previously relied on this property having no effect to ensure default health checks ran, add explicit health check implementations before upgrading. |
| 7 | WFLY-19339 | DNS/RMI naming dependencies added to deployments | When the Naming subsystem is active, WildFly now automatically adds `jdk.naming.dns` and `jdk.naming.rmi` module dependencies to deployments. This resolves `InitialContextFactory com.sun.jndi.dns.DnsContextFactory` failures but may change classloading visibility for applications that previously worked around the absence of these modules. |
| 8 | WFLY-17324 | OIDC query parameter preservation on redirect | Query parameters are now preserved when the Elytron OIDC client redirects to Keycloak for authentication (via the new `wildfly.elytron.oidc.allow.query.params` system property). If your application depends on query parameters being stripped during the OIDC redirect flow, review the new system property documentation and set it explicitly. |
| 9 | WFLY-18547, WFLY-19517 | Artemis AddressSettings default value handling corrected | Default values for Artemis `AddressSettings` (the `#` pattern) are now correctly applied and merged. If you relied on the previous buggy behaviour where defaults were not merged, review your messaging configuration after upgrading to ensure address-level overrides still behave as expected. |
| 10 | WFLY-19441 | HotRod SNI hostname auto-configuration for Kubernetes | HotRod client SNI hostname validation is now automatically disabled in Kubernetes environments where hostnames cannot be resolved. If you required explicit SNI configuration to work around this, verify that the automatic detection works correctly in your cluster before removing manual workarounds. |

---

## 🟡 Deprecations

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-19303 | EJB remote `cluster` attribute deprecated | The `cluster` attribute on the EJB remote service is deprecated. The EJB remote service now declares a capability dependency on the deprecated attribute, which may produce warnings in server logs. Plan to migrate to the replacement configuration before the attribute is removed in a future release. Review WildFly EJB clustering documentation for the updated configuration approach. |
| 2 | WFLY-19352 | Deprecated MSC API removed from example code | The MSC (JBoss Modular Service Container) deprecated API is no longer used in the `ha-singleton-service` quickstart. If your production code directly uses deprecated MSC `ServiceController` APIs that were present in the quickstart, plan to migrate to the current MSC API. |

---

## 🔵 Notable New Capabilities

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-19366 | OpenTelemetry auto-added to deployment classpath | The `io.smallrye.opentelemetry` module is now automatically added to the deployment classpath when the OpenTelemetry subsystem is present. Deployments that previously required a manual `jboss-deployment-structure.xml` entry for OpenTelemetry can remove that workaround. |
| 2 | WFLY-16532 | OIDC client: configurable additional scopes (Preview) | The `elytron-oidc-client` subsystem (Preview stability) now supports configuring additional OAuth2 scopes in the authentication request. If you need fine-grained scope control in OIDC flows, configure the `scope` attribute in the `elytron-oidc-client` subsystem configuration. Requires running at Preview stability level. |
| 3 | WFLY-17143 | OIDC `request` / `request_uri` parameters (Preview) | The OIDC client (Preview) now supports including `request` and `request_uri` parameters in authentication requests, enabling JAR (JWT Secured Authorization Requests). Configure the new attributes in the `elytron-oidc-client` subsystem. Requires Preview stability. |
| 4 | WFLY-14255, WFLY-15452 | Undertow AJP + X-Forwarded configurable (Preview) | Two Undertow configuration options are now available at Preview stability: the AJP listener's `AJP_ALLOWED_REQUEST_ATTRIBUTES_PATTERN` can be specified, and `reuseXForwarded` / `rewriteHost` are now configurable. If you run behind a reverse proxy and need fine-grained AJP or X-Forwarded header control, these options are now available. |
| 5 | WFLY-18763 | Example standalone-core-microprofile.xml config added | A new example configuration file `standalone-core-microprofile.xml` is included in the WildFly distribution. This provides a starting point for deploying MicroProfile applications on a minimal WildFly Core server without the full EE profile. Use it as a base for building slim MicroProfile-only server configurations. |
| 6 | WFLY-19438 | Snappy compression disable hook for Kafka connector | A new hook is available to disable Snappy compression in the MicroProfile Reactive Messaging Kafka connector, useful on environments where native Snappy libraries are unavailable. Set the documented configuration property to disable Snappy before deploying reactive messaging Kafka applications on constrained environments. |

---

## Summary by Priority

| Priority Level | Count | Description |
| :--- | :--- | :--- |
| 🔴 **Breaking** | 4 | Must fix before migrating. |
| 🟠 **Mandatory** | 20 | Security CVEs, component upgrades, security config. |
| 🟡 **Behavioral / Deprecation** | 12 | Assess impact and adjust accordingly. |
| 🔵 **New Capabilities** | 6 | Optional but recommended to leverage. |

## 🚨 Most Critical Items for Migration

- **Legacy security capability removal (WFLY-18997, WFLY-19006–19012, WFLY-19051):** Seven subsystems — connector, EJB3, EE, Undertow, WebServices, and messaging — no longer accept the `org.wildfly.legacy-security` capability at runtime. Any server still using legacy `<security-domain>` references in these subsystems will fail to boot. Complete the Elytron migration for all affected subsystems before upgrading.
- **Boot failure with EE 11 APIs + Security Manager (WFLY-19287):** WildFly 33 explicitly rejects combinations of EE 11 APIs and the Java Security Manager. Servers running with `-Djava.security.manager` must disable the Security Manager prior to adopting any EE 11 libraries, or the server will refuse to start.
- **CVE-2024-1233 JWT JKU allow-list (WFLY-19226):** A new system property `wildfly.elytron.jwt.allowed.jku.values.<realm-name>` must be set to an explicit allow-list for every Elytron JWT realm that processes externally-issued JWTs. Without configuration the fix is not effective against JKU injection attacks.
- **Custom Galleon provisioning exposes http-invoker (WFLY-19098 / CVE-2023-4503):** Servers built with custom Galleon feature packs that omit the default security layers have had an unauthenticated http-invoker. Ensure the relevant Elytron security layer is included in every custom provisioning descriptor and redeploy affected servers immediately.
- **WildFly Preview EE 11 API breaking changes (WFLY-19287, WFLY-19312, WFLY-19400–19404, WFLY-19471–19472):** WildFly Preview ships Jakarta Security 4.0, Servlet 6.1, REST 4.0/RESTEasy 7.0, Faces 4.1, Persistence 3.2, Validation 3.1, and WebSocket 2.2. Applications on WildFly Preview must recompile against all updated APIs and perform full regression testing before production deployment.
