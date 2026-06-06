# WildFly 37.0.0 → 38.0.0 — Filtered Migration Report

- **Framework:** WildFly
- **Range:** 37.0.0 → 38.0.0
- **Filtered (UTC):** 2026-06-06

---

## 🔴 Breaking Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-20693 | JCA security config disappears on subsystem parse | Bug in `ResourceAdapterSubsystemParser` silently drops security configuration during parsing. If you rely on JCA resource-adapter security settings, verify they survive restart after upgrading — config may need to be re-applied. |
| 2 | WFLY-20557 | Container-interceptor priority collision on deployment | Deployments using container-interceptors fail with `IllegalArgumentException: WFLYEE0079: Can't add …, priority 0x249 is already taken`. Review interceptor priority assignments in your deployment descriptors before upgrading. |
| 3 | WFLY-20656 | `ClassNotFoundException` with CDI + Messaging on Java 22+ | Applications combining CDI and Messaging on JDK 22 or newer hit a `ClassNotFoundException` at runtime. Ensure the fix is in place before deploying on newer JDKs. |
| 4 | WFLY-20858 | JDBC driver deployment requires jdk.net module | The connector subsystem now requires `jdk.net` as a dependency for deployed JDBC drivers. If you package drivers as deployments (rather than as modules), verify the JVM module graph includes `jdk.net`, especially on modular JDK configurations. |

---

## 🟠 Mandatory Migrations — Security & CVE Fixes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-20662 | commons-beanutils 1.11.0 — resolves CVE-2025-48734 | Upgrades `commons-beanutils` from 1.10.x to 1.11.0 to fix a deserialization CVE. If your application bundles its own copy of this library, update it to 1.11.0 or later. |
| 2 | WFLY-20713 | Nimbus JOSE+JWT 10.3 — resolves CVE-2025-53864 | Upgrades `nimbus-jose-jwt` to 10.3. Applications that bundle or depend on `nimbus-jose-jwt` < 10.3 must update their dependency. JWT processing may be affected if the library version is pinned. |
| 3 | WFLY-20832 | angus-mail 2.0.4 — resolves CVE-2025-7962 | Upgrades `org.eclipse.angus:angus-mail` to 2.0.4 fixing a mail-handling vulnerability. Applications using Jakarta Mail must ensure no older version of angus-mail is bundled. |
| 4 | WFLY-20846, WFLY-20911 | Netty 4.1.124 / 4.1.127 — resolves CVE-2025-55163, CVE-2025-58056, CVE-2025-58057 | Two Netty upgrades across the release cycle address three CVEs. If you bundle Netty directly in your application (e.g. via Vert.x or Artemis client jars), upgrade to Netty 4.1.127.Final. |

---

## 🟠 Mandatory Migrations — Major Component Upgrades

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-20599, WFLY-20716, WFLY-20893 | Infinispan upgraded to 15.2 series (→15.2.6.Final) | Infinispan subsystem migrated across multiple micro releases. Applications using off-heap storage (WFLY-20772) now require a deployment-specific media type — update your Infinispan cache configuration if using off-heap stores. Distributed cache listeners and distributed managers had suspend/resume bugs (WFLY-20947, WFLY-20948) fixed in 38; validate HA behaviour post-upgrade. |
| 2 | WFLY-20600, WFLY-20894 | JGroups upgraded to 5.4 (→5.4.10.Final) | JGroups major version bump. The default TCP-based stacks no longer include `FD_SOCK2` (WFLY-20710). Review your JGroups stack configuration and remove explicit `FD_SOCK2` references if relying on default stacks. |
| 3 | WFLY-20598, WFLY-20997, WFLY-21008 | wildfly-clustering upgraded to 7.0 → 8.0 series | Clustering library moved from 7.x to 8.0. Clustering session serialisation changes may affect rolling upgrades. Plan a coordinated cluster restart rather than a rolling upgrade when moving from WildFly 37 to 38. |
| 4 | WFLY-20601, WFLY-20815 | Apache Artemis upgraded to 2.41.0 → 2.42.0 | Artemis major version change. The system property prefix `brokerconfig.` caused Artemis to fail to launch in prior versions (WFLY-20609) — this is fixed, but verify broker configuration properties are not silently ignored. |
| 5 | WFLY-20613, WFLY-20853, WFLY-20939, WFLY-21012 | WildFly Preview: Hibernate ORM upgraded to 7.x series | In WildFly Preview only, Hibernate ORM advances from 6.6 to 7.1.2.Final (plus Hibernate Search 8.1.2 and EE 11 JPA/CDI integration). This is a major ORM version upgrade with breaking API changes. Only affects WildFly Preview users; standard WildFly stays on Hibernate ORM 6.6 series. Review Hibernate ORM 7.x migration guide before upgrading Preview. |
| 6 | WFLY-20684, WFLY-20685 | MicroProfile Platform 7.1 and MP Telemetry 2.1 | WildFly 38 ships MicroProfile 7.1. Applications using MP Config, MP JWT, MP Rest Client, MP Fault Tolerance, MP Health, or MP Telemetry should review the MicroProfile 7.1 spec changes. MP Reactive Messaging is now officially supported only from `.war` deployments (WFLY-20605). |
| 7 | WFLY-20986, WFLY-20987 | RESTEasy upgraded to 6.2.14 / 7.0.0 (Preview) | Standard WildFly moves to RESTEasy 6.2.14.Final; WildFly Preview moves to RESTEasy 7.0.0.Final (Jakarta EE 11 compatible). RESTEasy 7.0 is a major version with API changes. WildFly Preview users must review RESTEasy 7 migration guide. |
| 8 | WFLY-20552, WFLY-20652, WFLY-20719, WFLY-20762, WFLY-20859, WFLY-20925, WFLY-21010 | Hibernate ORM 6.6 series upgrades (standard WildFly) | Standard WildFly advances through Hibernate ORM 6.6.13 → 6.6.31.Final. Each micro upgrade carries potential JPA behaviour fixes. If you pin Hibernate ORM in your BOM or shade it, align to 6.6.31.Final. |

---

## 🟠 Mandatory Migrations — Security Configuration

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-20211, WFLY-20950, WFLY-20955, WFLY-20951 | Jakarta Authorization 3.0 replaces JACC in WildFly Preview | In WildFly Preview, Java Policy (SecurityManager-based JACC) is removed from the default config. JACC services now call the `PolicyRegistration` SPI, and a new `jakarta-authorization` capability is registered. Standard WildFly users are unaffected. WildFly Preview users with custom JACC providers must migrate to the Jakarta Authorization 3.0 SPI. |
| 2 | WFLY-20666, WFLY-18097 | wildfly-elytron dependency removed from end-user BOMs | The `wildfly-elytron` artifact is no longer included as a transitive dependency in WildFly end-user BOMs. If your project explicitly or transitively depended on `wildfly-elytron` via the BOM, add an explicit dependency or migrate to the Elytron subsystem APIs. |

---

## 🟡 Behavioral Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-20787 | CDI Startup event cannot look up `java:comp/UserTransaction` | Applications that attempted JNDI lookup of `UserTransaction` inside a CDI `@Startup` observer method received `NamingException`. This is now fixed — verify any workarounds (e.g. programmatic transaction management in startup) are removed so the standard lookup works correctly. |
| 2 | WFLY-20754 | `TransactionUtil.isInTx` incorrect for rollback-only transactions | Transactions in `MARKED_ROLLBACK` state incorrectly returned `false` from `isInTx`. Fixed in 38. If you have defensive code that checked transaction state as a proxy for rollback-only status, re-test the logic. |
| 3 | WFLY-20772 | Off-heap Infinispan caches require deployment-specific media type | Caches configured with off-heap storage now require the deployment to declare a media type (MarshalledValue wrapping). Deployments that used off-heap storage without a media type declaration will fail to start — add the required configuration. |
| 4 | WFLY-20898 | JAX-RS: XML bind annotation incorrectly applied to JSON | When a resource method produces both XML and JSON, `@XmlRootElement` annotations were incorrectly influencing JSON serialisation. Jackson service imports have been cleaned up. Re-test REST endpoints that return both XML and JSON to ensure correct serialisation. |
| 5 | WFLY-20564 | Deploying `postgresql-42.7.5.jar` causes NPE (WF 35→36 regression) | Deploying the PostgreSQL JDBC driver as an archive caused an NPE during class-processing. Fixed in 37 GA. If you deploy JDBC drivers as archives (rather than as JBoss modules), verify deployment succeeds on 38. |
| 6 | WFLY-20617 | Deployment fails with NPE in `ExpirationMetaData.getLastAccessTime()` | NPE in session expiry path caused deployment failures in clustered configurations. Fixed in 37 GA. |
| 7 | WFLY-20727 | `ManagedScheduledExecutorService` runs tasks multiple times | Scheduled tasks executed more times than expected. Fixed in 37 GA. Validate scheduled job idempotency assumptions if this bug was silently masked in production. |
| 8 | WFLY-20873 | WSClassVerificationProcessor moved to INSTALL phase | The Web Services class verification processor now runs at the INSTALL phase rather than POST_MODULE. This may affect ordering-sensitive deployment behaviour in applications that mix JAX-WS with CDI or JPA — test WS deployments post-upgrade. |
| 9 | WFLY-20890 | JAXWS over JMS protocol configured eagerly before CXF boots | JAXWS JMS protocol is now configured before Apache CXF initialises. Applications using JAX-WS over JMS transports should see improved startup reliability but must validate that pre-existing CXF boot customisations still apply at the right lifecycle phase. |
| 10 | WFLY-20366 | JGroups custom protocols auto-prefix `org.jgroups.protocols` | JGroups protocol elements with `module="…"` now attempt to load with the `org.jgroups.protocols` package prefix if the unqualified name fails. This is a fallback behavioural change; review custom protocol class names if you see unexpected class-loading behaviour. |
| 16576 | WFLY-16576, WFLY-20999 | org.bouncycastle module removed then restored | `org.bouncycastle` was removed during the Beta phase (WFLY-16576) then restored in WFLY-20999 for the Final release. No action needed for WildFly 38 Final users; however, WildFly Preview users should verify BouncyCastle availability in their module graph. |

---

## 🟡 Deprecations

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-20591, WFLY-20624 | `ModuleIdentifier` and `ModuleIdentifierUtil` deprecated usage removed | Internal WildFly code has removed use of deprecated `ModuleIdentifier`/`ModuleIdentifierUtil` APIs. Third-party subsystem or extension authors who use these internal APIs must migrate to the replacement `ModuleName`-based APIs before those internals are removed in a future release. |
| 2 | WFLY-20667 | `AsyncFuture` return type removed from `ModelControllerClient` | `ModelControllerClient` no longer returns `AsyncFuture` from management operations. Extensions or management clients that cast the return value to `AsyncFuture` must switch to standard `Future` / `CompletableFuture` idioms. |

---

## 🔵 Notable New Capabilities

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-20512 | Artemis `commit-interval` attribute exposed for scaledown | New management attribute `commit-interval` is available on the Artemis/Messaging subsystem scaledown configuration. Operators running clustered Artemis can now tune commit intervals for scale-down scenarios without custom workarounds. |
| 2 | WFLY-20770 | `jboss-client.jar` integrates with JDK Mission Control 9+ | The WildFly remote management client JAR now works with JDK Mission Control 9 and later. Enables flight-recorder-based profiling of WildFly processes from modern JMC versions. |
| 3 | WFLY-19554, WFLY-20988 | EE 11 JPA/CDI integration in WildFly Preview | WildFly Preview now implements the Jakarta EE 11 JPA/CDI integration specification. Enables injection of `EntityManager` via CDI producers and EE 11-compliant persistence context scoping in WildFly Preview. |
| 4 | WFLY-20684, WFLY-20685 | MicroProfile 7.1 platform support | WildFly 38 certifies against MicroProfile 7.1 (including MP Telemetry 2.1). New capabilities in MP Config, MP JWT, MP Fault Tolerance, and MP Health are available without additional configuration. |

---

## Summary by Priority

| Priority Level | Count | Description |
| :--- | :--- | :--- |
| 🔴 **Breaking** | 4 | Must fix before migrating. |
| 🟠 **Mandatory** | 13 | Security CVEs, component upgrades, security config. |
| 🟡 **Behavioral / Deprecation** | 13 | Assess impact and adjust accordingly. |
| 🔵 **New Capabilities** | 4 | Optional but recommended to leverage. |

## 🚨 Most Critical Items for Migration

- **Netty CVE triple-fix (WFLY-20846, WFLY-20911):** Three CVEs in Netty (CVE-2025-55163, CVE-2025-58056, CVE-2025-58057) are patched by upgrading to Netty 4.1.127.Final. If your application bundles Netty directly (via Vert.x client, Artemis client, or gRPC), upgrade those bundled jars before deploying on WildFly 38 — the server-side Netty is patched, but your application's classpath Netty is not.
- **Infinispan 15.2 + wildfly-clustering 8.0 cluster compatibility (WFLY-20599, WFLY-21008):** The clustering stack advanced through two major library versions. Rolling upgrades between WildFly 37 and 38 nodes in the same cluster are not safe — plan a full cluster restart. Applications using off-heap cache storage must add a media type declaration to their Infinispan cache configuration or deployments will fail to start.
- **MicroProfile 7.1 upgrade (WFLY-20684):** WildFly 38 ships MP 7.1. MP Reactive Messaging is now officially only supported from `.war` deployments (not EARs). Review your MicroProfile API version constraints if you pin MP BOM versions, and test MP Fault Tolerance + OpenTelemetry integration which had intermittent test failures that were fixed in this release.
- **WildFly Preview — Jakarta EE 11 security and persistence (WFLY-20211, WFLY-19554):** WildFly Preview removes Java Policy / SecurityManager-based JACC and switches to Jakarta Authorization 3.0 SPI. Simultaneously, Hibernate ORM advances to 7.x and RESTEasy to 7.0.0.Final — both are major version changes with breaking API changes. WildFly Preview users must plan for all three changes concurrently.
- **commons-beanutils CVE-2025-48734 (WFLY-20662):** Applications that package their own `commons-beanutils` jar (common in legacy enterprise apps) are not protected by the server-side fix. Audit your application's bundled dependencies and upgrade `commons-beanutils` to 1.11.0 in your own artifact.
