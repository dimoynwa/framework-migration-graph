# WildFly 39.0.0 → 40.0.0 — Filtered Migration Report

- **Framework:** WildFly
- **Range:** 39.0.0 → 40.0.0
- **Filtered (UTC):** 2026-06-06

---

## 🔴 Breaking Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-21722, WFLY-21698 | Standard WildFly moves to Jakarta EE 11; EE 10 variant added | WildFly 40's main distribution is now Jakarta EE 11. A separate `wildfly-ee` (EE 10) feature-pack is provided for EE 10 consumers. If you deploy to standard WildFly, your application now runs on EE 11 APIs. Review your `pom.xml` dependencies — all `jakarta.*` API coordinates must align with EE 11 versions. Projects explicitly targeting EE 10 must switch to the `wildfly-ee-10` feature-pack and update provisioning configs accordingly. |
| 2 | WFLY-21667, WFLY-21671 | JGroups default stacks switch from NAKACK4/UNICAST4 to NAKACK2/UNICAST3 | The default JGroups protocol stacks now use `NAKACK2`/`UNICAST3` instead of `NAKACK4`/`UNICAST4`, and revert to the transfer-queue bundler. If you customised your stack based on the previous defaults, or rely on specific message-ordering and bundling guarantees from NAKACK4/UNICAST4, review your JGroups configuration. Rolling upgrades between WildFly 39 and 40 nodes in a mixed cluster may behave differently during the transition window. |
| 3 | WFLY-21514 | AppClient module isolation fixed to match EE spec | AppClient module resources are no longer visible to the web container, EJB container, or other AppClient modules. Applications that exploited this leakage (e.g. sharing classes across AppClient and WAR via classpath bleed) will break. Audit your EAR deployments and make any shared code available through the correct deployment mechanism. |
| 4 | WFLY-21528 | WebSocket client endpoint scanning disabled by default | `UndertowJSRWebSocketDeploymentProcessor` no longer scans for `@ClientEndpoint`-annotated types by default. If you deployed WebSocket client endpoints via annotation scanning rather than programmatic registration, they will no longer be discovered. Programmatically register client endpoints via `WebSocketContainer.connectToServer(...)` instead. |

---

## 🟠 Mandatory Migrations — Security & CVE Fixes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-21862, WFLY-21694 | Netty upgraded to 4.1.133.Final (CVE-2026-33870/33871, CVE-2026-41417, CVE-2026-42578–42587, CVE-2026-44248) | Multiple CVEs in Netty resolved across two upgrade steps ending at 4.1.133.Final. If you manage `io.netty` versions in your project BOM, update to `4.1.133.Final`. Run HTTP and HTTP/2 integration tests after upgrading. |
| 2 | WFLY-21816 | Apache Artemis 2.53.0 (CVE-2026-32642) | CVE-2026-32642 in Apache Artemis addressed by upgrade to 2.53.0. If you override `artemis` versions in your build, update to `2.53.0`. Validate messaging and MDB-based tests post-upgrade. |
| 3 | WFLY-21586 | Jackson components 2.21.x (CVE-2026-29062) | CVE-2026-29062 patched by upgrading Jackson to 2.21.x. Update `com.fasterxml.jackson:jackson-bom` to `2.21.3` if you manage it directly. Re-run JSON serialisation tests. |
| 4 | WFLY-21848 | Apache Neethi upgrade (CVE-2026-42402/3/4) | Three CVEs in `org.apache.neethi:neethi` addressed by upgrading to 3.2.2. If you depend on Neethi directly in JAX-WS projects, update to `3.2.2`. |
| 5 | WFLY-21415 | Vert.x 4.5.24 (CVE-2026-1002) | CVE-2026-1002 in Vert.x addressed. If you override `version.io.vertx.vertx`, update to at least `4.5.24`. |
| 6 | WFLY-20765 | Elytron brute-force authentication attack (CVE-2025-23368) | WildFly Elytron now includes brute-force authentication protection. Review the new documentation and configure the brute-force protection policy in your security realm configuration if the default threshold (increased maximum failed attempts) is not appropriate for your environment. Applications that test authentication failures programmatically may need adjustments. |
| 7 | WFLY-21647 | Jakarta Authorization: missing `WebRoleRefPermission` | Implicit security roles were missing from Web App metadata, causing `WebRoleRefPermission` checks to fail. If your application relies on `<security-role-ref>` mappings in `web.xml` for authorization decisions, re-test role-based access control after upgrading. |
| 8 | WFLY-21896 | WAR JACC `WebResourcePermission` wrong actions value | `WarJACCService` was emitting an incorrect `actions` value in `WebResourcePermission` for all-methods constraints. If you use JACC policies that inspect permission actions for wildcard HTTP method constraints, verify the policy behaviour after upgrade. |

---

## 🟠 Mandatory Migrations — Major Component Upgrades

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-21718, WFLY-21782, WFLY-21781 | Hibernate ORM 7.3.2.Final (EE 11) / 6.6.49.Final (EE 10) | Standard WildFly (EE 11) ships Hibernate ORM 7.3.2.Final; the EE 10 variant ships 6.6.49.Final. The jump to Hibernate ORM 7.x is a major API change. Review the Hibernate ORM 7 migration guide: `EntityManager` and `*Query` interfaces now implement new Jakarta Persistence 3.2 methods (WFLY-21780). Bidirectional association management is also now disabled when bytecode enhancement is active (WFLY-21644) — test entities with bidirectional relationships. |
| 2 | WFLY-19558, WFLY-21791 | Jakarta Authorization 3.0 in standard WildFly | Standard WildFly (EE 11) now uses Jakarta Authorization 3.0. The `PolicyConfigurationFactory` resolver pattern has changed (WFLY-21746), and `WebPolicyContextRegistrationUtility` is now used for policy context registration (WFLY-21790). If you have custom JACC/Jakarta Authorization policy providers or use the `jacc` subsystem with custom implementations, update to the Jakarta Authorization 3.0 API and the new registration model. |
| 3 | WFLY-21147, WFLY-21836, WFLY-21837 | Jakarta Security 4.0 + Elytron EE 4.0.0.Final (EE 11) | Standard WildFly ships Elytron EE 4.0.0.Final implementing Jakarta Security 4.0 and Authorization 3.0. The EE 10 variant ships Elytron EE 3.2.1.Final. If you use `@SecurityDomain`, `@RememberMe`, `@LoginToContinue`, CDI-based authentication mechanisms, or custom `IdentityStore` implementations, verify compatibility with Jakarta Security 4.0. The `RunAs` handling in EJB now delegates to elytron-ee (WFLY-21766). |
| 4 | WFLY-21831, WFLY-21832, WFLY-21913 | Undertow EE 2.0.0.Final + Undertow Core 2.4.1.Final | Undertow has been split into `undertow-core` (2.4.1.Final) and `undertow-ee` (2.0.0.Final) for Jakarta Servlet/WebSocket in WildFly 40. If you have custom Undertow extensions, handlers, or build against Undertow directly, update your dependency coordinates. The binary incompatibility between `ServletSessionConfig`/`SessionCookieConfig` in Undertow 2.3 and 2.4 was previously worked around via reflection; verify your session cookie configuration still behaves correctly. |
| 5 | WFLY-19555, WFLY-21152 | Jakarta Pages 4.0 integrated in standard WildFly | Standard WildFly now integrates Jakarta Pages 4.0. Update your `jakarta.pages:jakarta.pages-api` dependency to 4.0.x. Review JSP/tag-file behaviour under the new spec, especially EL expression evaluation changes. |
| 6 | WFLY-21808, WFLY-21833 | Jastow upgraded to 2.3.0.Final | Jastow (the JSP/JSF implementation) has moved to 2.3.0.Final. If you have JSP-specific configurations or use Jastow APIs directly, verify compatibility. |
| 7 | WFLY-21693, WFLY-21740 | wildfly-clustering 10.0.x (major version) | The clustering library has advanced to 10.0.7.Final, a new major version series. Review your distributable-web and distributable-ejb configurations. Session reuse across recreated sessions is now fixed (WFLY-21894/21895), which may change session ID behaviour under failover — re-test session failover scenarios. |
| 8 | WFLY-21521, WFLY-21816 | Apache Artemis 2.52.0–2.53.0 | Apache Artemis has been upgraded across two steps to 2.53.0 (which also includes the CVE-2026-32642 fix). If you override the Artemis version, update to `2.53.0`. Test messaging failover and MDB clustering, particularly the clustered singleton MDB deployment fix (WFLY-21815). |
| 9 | WFLY-21585 | Kafka client upgraded to 4.2.0 | The Kafka client has been upgraded to a new major version (4.2.0). If you use MicroProfile Reactive Messaging with Kafka, review the Kafka 4.x migration guide for any API or protocol-level changes. The `vertx-kafka-client` artifact has also been removed (WFLY-21434). |
| 10 | WFLY-21721, WFLY-21751 | RESTEasy 6.2.16.Final / 7.0.2.Final (Preview) | Standard WildFly ships RESTEasy 6.2.16.Final; WildFly Preview ships 7.0.2.Final. The `resteasy-2-0-request-matching` attribute in the `jaxrs` subsystem is now deprecated (WFLY-19876) — remove it from your configuration. Verify REST endpoint behaviour under the new versions. |

---

## 🟠 Mandatory Migrations — Security Configuration

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-21444 | Caching Security Realm — missing test coverage fixed | The caching security realm had missing coverage exposed; if you use a caching security realm wrapping a filesystem or other realm, verify that authentication caching and invalidation behave correctly after the upgrade. |
| 2 | WFLY-21574 | KUBE_PING fails after Kubernetes service account token rotation | KUBE_PING now correctly handles service account token rotation. If you run WildFly on Kubernetes and experienced split-brain or discovery failures after token rotation, this fix should address it — review your KUBE_PING configuration after upgrading to confirm discovery resumes properly after rotation. |
| 3 | WFLY-21637 | Jakarta Authorization Context-ID missing for `ServletContextListener` | The Jakarta Authorization Context-ID was not being set when invoking `ServletContextListener`. If you use JACC-protected resources that are initialised during `contextInitialized(...)`, verify that authorization checks now correctly receive the context ID. |
| 4 | WFLY-21640 | EE 11 Preview: default Policy + system property overrides | Policy handling for the default policy combined with system property overrides was incorrect in WildFly Preview. If you use WildFly Preview with custom Jakarta Authorization policy overrides via system properties, re-test policy resolution behaviour. |

---

## 🟡 Behavioral Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-21644 | Hibernate bidirectional association management disabled with bytecode enhancement | When Hibernate bytecode enhancement is active (now on by default), bidirectional association management is automatically disabled. This prevents double-synchronisation issues but may change how orphan removal and cascade behave in your entity model. Review and test your bidirectional `@OneToMany`/`@ManyToOne` associations. |
| 2 | WFLY-21780 | `EntityManager` and `*Query` implement new Persistence 3.2 methods | The JPA subsystem implementations of `EntityManager` and all `*Query` interfaces now implement new methods added in Jakarta Persistence 3.2. If you subclass or wrap these interfaces, add implementations for the new methods. If you use WildFly's EE 10 variant, these APIs remain at Persistence 3.1. |
| 3 | WFLY-21615, WFLY-21616 | MP Config `config-source` restart levels corrected; safe-read timing | `config-source:add/remove` management operations now carry correct restart-level metadata, and a new capability service ensures MP Config is fully available before services read from it. If your application reads MP Config during boot (e.g. from an `@Observes ProcessBeanAttributes` or subsystem activation), verify the ordering still works correctly. |
| 4 | WFLY-21597 | Datasource `recovery` schema 7.0 parsing fixed | Datasource `recovery` configuration was failing to parse under schema version 7.0. If you use `<datasource>` recovery elements in `standalone.xml` or `domain.xml` and upgraded to schema 7.0, verify the configuration parses and recovery functions correctly. |
| 5 | WFLY-21461 | Jakarta Data `StatelessSession` `unwrap()` now works | WildFly's `TransactionScopedStatelessSession` now correctly implements all public interfaces of Hibernate's `StatelessSessionImpl`, so `unwrap(SharedSessionContractImplementor.class)` no longer fails in Jakarta Data 1.0 repositories. Remove any workarounds for this issue in your repositories. |
| 6 | WFLY-21469 | Contextual proxy no longer wraps runtime exceptions in `UndeclaredThrowableException` | CDI contextual proxies were wrapping certain runtime exceptions in `UndeclaredThrowableException`. This is fixed. If you catch `UndeclaredThrowableException` to detect CDI proxy errors, update your exception handling to catch the underlying type directly. |
| 7 | WFLY-21629 | Auto-generated server entries now use port-offset | In domain mode, server entries auto-generated from listener socket bindings now correctly reflect the port-offset. If you relied on the previous (incorrect) zero-offset behaviour to compute ports, adjust your port calculations. |
| 8 | WFLY-21383 | `RequestTooBigException` on upload fixed | Uploads to WildFly 39.0.0.Final were failing with `RequestTooBigException`. This regression is fixed. If you added temporary workarounds (increased `max-post-size` or chunked upload logic), verify they are still appropriate and can be removed. |
| 9 | WFLY-21390 | Memory leak in `ComponentConfiguration` via `BinderService` lambda | A memory leak where `ComponentConfiguration` was retained after undeployment by `ViewBindingConfigurator` lambdas has been fixed. No configuration change is needed, but if you observed post-undeploy memory growth in WildFly 39, this should be resolved. |
| 10 | WFLY-21577, WFLY-21664 | Micrometer application metrics missing; admin-only mode fix | Micrometer application metrics were missing in WildFly 39.0.1.Final. Additionally, the Micrometer subsystem was creating an unmanaged meter registry in admin-only mode. Both are fixed. If you work around the metrics gap, remove the workaround. |
| 11 | WFLY-21651 | Prometheus endpoint now returns correct `Content-Type` | The Prometheus metrics endpoint was missing the `Content-Type: text/plain; version=0.0.4` header. If your Prometheus scraper or a proxy validates the content-type, re-test scraping. |
| 12 | WFLY-21548 | Deployment `ConcurrentModificationException` with mod_cluster capabilities | Deployments using mod_cluster capabilities were failing with a `ConcurrentModificationException`. This is fixed. If you worked around it by disabling capabilities, re-enable them. |
| 13 | WFLY-21809 | NPE during messaging-activemq failover activation check | A null pointer exception when checking `messaging-activemq` activation state during failover has been fixed. If you observed spurious NPE log entries during HA failover events, this should stop. |
| 14 | WFLY-21815 | Clustered singleton MDB deployment regression fixed | Clustered singleton MDBs failed to deploy following the `ejb3` subsystem API deprecation cleanup. The deployment regression has been resolved. Re-test singleton MDB deployments. |
| 15 | WFLY-21894, WFLY-21895 | Distributed session manager reuses ID for recreated sessions | Session IDs were reused for recreated sessions in the distributed session manager, and recreated sessions never completed. Both are now fixed. Re-test session failover and session recreation scenarios in your distributed web applications. |
| 16 | WFLY-21757 | EJB proxy class hierarchy no longer causes metaspace inflation | Deep EJB class hierarchies caused massive metaspace inflation due to proxy validation strategy. The EJB proxy validation now uses a class registry. No config change needed, but monitor metaspace usage in applications with deep EJB inheritance after upgrade. |
| 17 | WFLY-21825 | JGroups channel fork `remove/protocol.add` operations fixed | `jgroups.channel.fork` `remove` and `protocol.add` management operations were failing with `IllegalStateException`. This is fixed. If you use dynamic JGroups fork channel management, re-test these operations. |
| 18 | WFLY-21719 | `web-app_6_1.xsd` now supported in `web.xml` | The `WebParsingDeploymentProcessor` now accepts `https://jakarta.ee/xml/ns/jakartaee/web-app_6_1.xsd` as a valid schema declaration in `web.xml`. EE 11 deployments using schema version 6.1 will now deploy correctly. |
| 19 | WFLY-21789 | Hibernate Validator now finds Expressly in deployment classloader | Hibernate Validator 9.x requires `Expressly` on the classpath to create a `ValidatorFactory`. WildFly now exports `Expressly` from the Hibernate Validator module. If you saw `ValidatorFactory` creation failures, this should be resolved. |
| 20 | WFLY-21080 | Jakarta Data promoted to `community` stability | The `jakarta-data` subsystem has been promoted from `preview` to `community` stability. Configure `--stability=community` in your server launch options to use it. If you were already using it with `--stability=preview`, update the flag. |
| 21 | WFLY-19808 | `AJP_ALLOWED_REQUEST_ATTRIBUTES_PATTERN` promoted to default stability | The AJP listener `allowed-request-attributes-pattern` attribute is now at default stability. Remove any `--stability=community` flag you previously needed to configure it, or verify it still functions as expected without the flag. |
| 22 | WFLY-21525 | `reuseXForwarded` and `rewriteHost` promoted to default stability | These Undertow proxy configuration attributes are now at default stability. Remove any community/preview stability flags you needed to configure them. |
| 23 | WFLY-21807, WFLY-21373 | JVM minimum version enforced at JDK 17 | The `jboss.require-java-version` constraint is now aligned with the JDK 17 compiler target. Attempts to run WildFly 40 on JDK below 17 will fail at boot. Ensure all your environments are on JDK 17+. |
| 24 | WFLY-19120 | EJB proxies no longer invoke constructor on creation | EJB proxy creation no longer calls the constructor of the proxy class, aligning with spec requirements and avoiding unintended constructor side effects. If your EJB proxy subclasses relied on constructor logic being called on proxy instantiation, this behaviour has changed. |
| 25 | WFLY-21434 | `vertx-kafka-client` artifact removed | The `vertx-kafka-client` artifact has been removed from the WildFly distribution. If you explicitly depend on it via a Galleon provisioning or module reference, remove the dependency. Kafka connectivity through MP Reactive Messaging continues to work through the updated Kafka client (4.2.0). |

---

## 🟡 Deprecations

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-19876 | `resteasy-2-0-request-matching` attribute deprecated in `jaxrs` subsystem | This attribute is now deprecated and will be removed in a future release. Remove it from your `jaxrs` subsystem configuration. |
| 2 | WFLY-21589 | `ManagementServerSetupTask.ContainerConfigurationBuilder#tearDownScript` deprecated | The `tearDownScript` approach for test setup teardown is superseded by snapshot restoration. If you author WildFly test suites using this API, migrate to the snapshot-restore approach. |
| 3 | WFLY-21244 | `mod_cluster` uses deprecated `ServerActivity` API | `mod_cluster`'s `UndertowEventHandlerAdapterService` has been migrated away from the deprecated `org.jboss.as.server.suspend.ServerActivity` interface to `SuspendableActivity`. If you have custom extensions that depend on `ServerActivity` implementations from mod_cluster, update to the new `SuspendableActivity` SPI. |

---

## 🔵 Notable New Capabilities

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-21698, WFLY-21763 | New EE 10 feature-pack (`wildfly-ee`) for legacy consumers | An `org.wildfly:wildfly-ee` feature-pack providing Jakarta EE 10 compliance is now available alongside the main EE 11 distribution. Use `wildfly-ee` as your Galleon feature-pack coordinate to provision an EE 10–compliant server and defer the EE 11 migration. |
| 2 | WFLY-21572 | HashiCorp Vault as a credential source (community stability) | WildFly now supports HashiCorp Vault as an Elytron credential store source at `community` stability. Launch with `--stability=community` and configure the new `vault-credential-store` in the Elytron subsystem to retrieve credentials from Vault. |
| 3 | WFLY-19314 | OIDC logout support in WildFly Preview | WildFly Preview now supports server-side OIDC logout. Configure the `logout` endpoint in your OIDC subsystem configuration to enable RP-initiated logout flows. |
| 4 | WFLY-21080 | Jakarta Data 1.0 at `community` stability | Jakarta Data repositories are now available at `community` stability in standard WildFly (not just Preview). Add `--stability=community` and use the `jakarta-data` layer to enable Jakarta Data repositories with Hibernate ORM backing. |
| 5 | WFLY-21525 | `reuseXForwarded` and `rewriteHost` now configurable at default stability | These Undertow reverse-proxy header attributes are now part of the default stability API. Configure them in the `undertow` subsystem's `http-listener` or `https-listener` to correctly handle forwarded headers behind a load balancer. |

---

## Summary by Priority

| Priority Level | Count | Description |
| :--- | :--- | :--- |
| 🔴 **Breaking** | 4 | Must fix before migrating. |
| 🟠 **Mandatory** | 22 | Security CVEs, component upgrades, security config. |
| 🟡 **Behavioral / Deprecation** | 28 | Assess impact and adjust accordingly. |
| 🔵 **New Capabilities** | 5 | Optional but recommended to leverage. |

## 🚨 Most Critical Items for Migration

- **Jakarta EE 11 is now the default in standard WildFly:** This is the single largest change in WildFly 40. All `jakarta.*` API coordinates, subsystem schema versions, and feature-pack references must be reviewed. EE 10 consumers must explicitly opt into the new `wildfly-ee` (EE 10) feature-pack or face compile/runtime failures from EE 11 API changes.
- **Hibernate ORM 7.x (EE 11 variant) is a major API break:** The `EntityManager` and `*Query` interfaces gain new Persistence 3.2 methods, bidirectional association management is disabled with bytecode enhancement, and `unwrap()` behaviour has changed. Comprehensive JPA integration testing is essential before going to production.
- **Jakarta Authorization 3.0 changes how JACC policies are registered and resolved:** The `PolicyConfigurationFactory` resolver model has changed, `WebRoleRefPermission` generation was previously broken, and the `WarJACCService` was emitting wrong permission actions. Any application using JACC or custom Jakarta Authorization providers must be re-tested end-to-end.
- **Netty CVE cluster (target: 4.1.133.Final) and Apache Artemis (2.53.0) security fixes:** Multiple critical CVEs have been patched across both libraries. If you override `io.netty` or `artemis` versions in your build, update to the stated targets before deploying to production.
- **JGroups default stack change (NAKACK4/UNICAST4 → NAKACK2/UNICAST3):** The protocol default stack has been reverted. Mixed-version clusters during rolling upgrades may see transient topology inconsistencies. Plan a full-cluster restart rather than a rolling upgrade if protocol compatibility is a concern.
