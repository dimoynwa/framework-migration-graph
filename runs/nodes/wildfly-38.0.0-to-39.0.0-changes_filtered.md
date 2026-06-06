# WildFly 38.0.0 → 39.0.0 — Filtered Migration Report

- **Framework:** WildFly
- **Range:** 38.0.0 → 39.0.0
- **Filtered (UTC):** 2026-06-06

---

## 🔴 Breaking Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-20836 | Non-breaking spaces removed from documentation | Documentation source files had non-breaking spaces replaced with regular spaces. If you have any tooling or scripts that parse WildFly documentation or configuration files and rely on specific whitespace characters, verify they still function correctly after upgrade. |

---

## 🟠 Mandatory Migrations — Security & CVE Fixes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-21274 | Upgrade Netty to 4.1.130.Final (CVE-2025-67735) | Netty 4.1.130.Final patches CVE-2025-67735. If you declare a direct or BOM-managed dependency on `io.netty` in your project, update it to `4.1.130.Final`. Verify HTTP and HTTP/2 integration tests pass after the upgrade. |
| 2 | WFLY-21262, WFLY-21240, WFLY-21290 | Upgrade lz4-java (CVE-2025-66566, CVE-2025-12183) | Multiple CVEs addressed by upgrading `at.yawk.lz4:lz4-java` from 1.8.1 through 1.10.1 to 1.10.2. If you override lz4-java in your dependency management, update to `1.10.2`. |
| 3 | WFLY-20911 | Upgrade Netty to 4.1.127.Final (CVE-2025-58056, CVE-2025-58057) | Two CVEs in Netty patched at 4.1.127.Final. Superseded by WFLY-21274 (4.1.130.Final) — ensure your Netty version is at minimum 4.1.130.Final. |
| 4 | WFLY-20846 | Upgrade Netty to 4.1.124.Final (CVE-2025-55163) | CVE-2025-55163 patched in Netty 4.1.124.Final. Superseded by WFLY-21274 — update to 4.1.130.Final as the final target. |
| 5 | WFLY-20832 | Upgrade angus-mail 2.0.4 (CVE-2025-7962) | CVE-2025-7962 in `org.eclipse.angus:angus-mail` addressed by upgrading to 2.0.4. If you manage this dependency directly, update it. |
| 6 | WFLY-20895 | Security alert: upgrade com.nimbusds:jose-jwt | Old `com.nimbusds:jose-jwt` version in Quickstarts triggered security alerts. If your project bundles or depends on `jose-jwt`, ensure you are using a non-vulnerable version. |

---

## 🟠 Mandatory Migrations — Major Component Upgrades

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-21163, WFLY-21164, WFLY-21266, WFLY-21307 | Infinispan 16.0 and JGroups 5.5 | Infinispan upgraded to 16.0.x and JGroups to 5.5, along with wildfly-clustering 9.0. These are major version jumps in the clustering stack. Review your Infinispan cache configurations, serialization/marshalling customizations, and JGroups protocol stacks. Distributed cache behaviour and listener wiring may have changed; validate failover and session clustering tests. |
| 2 | WFLY-19307, WFLY-20982, WFLY-20211, WFLY-20213, WFLY-20980 | Jakarta EE 11 Security Specs (WildFly Preview) | WildFly Preview now implements Jakarta Security / Authorization / Authentication for EE 11, including removal of `Java Policy` from default config and clean-up of the Security Manager subsystem. Applications on WildFly Preview using legacy `java.security.Policy`, `SecurityManager`, or pre-EE 11 security annotations must migrate to Elytron-based or Jakarta Security 4.x APIs. The security manager subsystem is being removed — audit `standalone*.xml` / `domain.xml` for `<subsystem xmlns="urn:jboss:domain:security-manager:*">` and migrate per WFLY-20213. |
| 3 | WFLY-21103 | CXF DelayedCachedOutputStreamCleaner thread leak | After the CVE-2025-23184 fix in Apache CXF, a background thread accumulation regression was introduced. This requires an upgrade to CXF 4.0.10 (included in this release). If you deploy JAX-WS services under high concurrency, verify that background CXF threads are released correctly and no thread-pool exhaustion occurs after upgrade. |
| 4 | WFLY-20853, WFLY-21227, WFLY-21012, WFLY-21200, WFLY-21313 | Hibernate ORM upgrades (6.6.x standard / 7.1.x Preview) | Standard WildFly ships Hibernate ORM 6.6.40; WildFly Preview ships 7.1.x. If you use Hibernate ORM APIs directly or rely on bytecode enhancement, review the Hibernate ORM 6.6→7.1 migration guide for WildFly Preview users. Particularly: bytecode provider caching behaviour changed (WFLY-20299), and `hibernate.statistics.query_max_size` now defaults to 200 (WFLY-20960) — override if you previously relied on a higher default. |
| 5 | WFLY-20684, WFLY-20685, WFLY-21139 | MicroProfile Platform 7.1 and OpenAPI 4.1.1 | WildFly now implements MicroProfile Platform 7.1 including MP Telemetry 2.1 and MP OpenAPI 4.1.1. Review your MP-annotated classes and `@OpenAPIDefinition` configurations for compatibility with the new spec versions. If you depend on `org.eclipse.microprofile.openapi:microprofile-openapi-api`, align to version 4.1.1. |
| 6 | WFLY-19556, WFLY-21082, WFLY-21088 | Jakarta Servlet 6.1 in WildFly Preview | WildFly Preview integrates Jakarta Servlet 6.1 (via Undertow 2.4.x alpha). If you are using WildFly Preview, update any compile-time dependencies on `jakarta.servlet:jakarta.servlet-api` to 6.1.x and verify your web application's `web.xml` version attribute. Binary incompatibilities between Undertow 2.3 and 2.4 in `ServletSessionConfig`/`SessionCookieConfig` are worked around internally, but custom Undertow extensions may be affected. |
| 7 | WFLY-19560, WFLY-21148 | Jakarta Concurrency 3.1 in WildFly Preview | WildFly Preview now includes a Jakarta Concurrency 3.1 implementation. If you are targeting WildFly Preview and use `@Asynchronous`, `ManagedExecutorService`, or `ContextService` from Jakarta EE, ensure you compile against `jakarta.enterprise.concurrent:jakarta.enterprise.concurrent-api` 3.1.x. |
| 8 | WFLY-20986, WFLY-20987, WFLY-21250, WFLY-21251 | RESTEasy upgrade (6.2.15 / 7.0.1 Preview) | Standard WildFly ships RESTEasy 6.2.15.Final; WildFly Preview ships 7.0.1.Final. If you have direct RESTEasy API dependencies or use any internal RESTEasy extension points, verify compatibility with the new versions. |
| 9 | WFLY-21198 | Jackson components upgraded to 2.20.x | Jackson upgraded from 2.18.x to 2.20.x. If you override Jackson in your BOM or use Jackson internals, update to `2.20.1` and run your serialisation tests. |

---

## 🟠 Mandatory Migrations — Security Configuration

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-21216 | Broken docs.jboss.org links in Elytron migration guide | If you have followed the legacy Elytron migration documentation (from `docs.jboss.org`), the links were broken and have now been corrected. Re-validate any Elytron configuration steps taken from the old documentation, as guidance may have changed. |
| 2 | WFLY-20806, WFLY-20285 | SecurityManager issues resolved for JDK 24 | Tests and configurations failing on JDK 24 EA related to SecurityManager have been fixed. If you run WildFly on JDK 24+, the SecurityManager-related failures should no longer occur; however, the overall direction is SecurityManager removal — plan to eliminate any `security-manager` subsystem usage. |

---

## 🟡 Behavioral Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-19393, WFLY-20299 | JPA bytecode enhancement enabled by default | Persistence container bytecode enhancement is now enabled by default and the bytecode provider is cached. This improves performance but may change runtime class structure. Test your JPA entity proxies, lazy loading, and instrumented state carefully. If enhancement causes issues, you can disable it explicitly via `hibernate.enhancer.enableDirtyTracking=false` etc. |
| 2 | WFLY-21267 | Jakarta Data shares StatelessSession — now scoped per tx | Jakarta Data repositories were improperly sharing `StatelessSession` instances across calls; each repository now uses a transaction-scoped `StatelessSession`. If you relied on any session-level state being shared across Jakarta Data calls, that state will no longer persist. |
| 3 | WFLY-20918 | Idle time-based eviction for distributed sessions/SFSBs | New idle time-based eviction is now configurable for distributed `HttpSession`, `SFSB`, and `Timer` stores. Review your `distributable-web` and clustering subsystem configurations if you were relying solely on max-entries-based eviction. |
| 4 | WFLY-20850, WFLY-20839 | Local caches auto-configured with single segment; max-active-timers removed | Local caches are now auto-configured with a single segment. `max-active-timers` has been removed from the default EJB configuration. If you relied on multi-segment local caches or the `max-active-timers` attribute, update your standalone/domain XML configuration. |
| 5 | WFLY-21058 | JAX-RS subsystem schema and model versions bumped | The `jaxrs` subsystem schema version has been incremented. If you provision WildFly via Galleon or test subsystem model transformers, update any transformer tests or provisioning configs that reference the previous schema version. |
| 6 | WFLY-14559 | New `resteasy-original-webapplicationexception-behavior` attribute | The `jaxrs` subsystem gains a new attribute `resteasy-original-webapplicationexception-behavior`. If you rely on RESTEasy's current `WebApplicationException` handling, verify behaviour under the new attribute default and set it explicitly if needed. |
| 7 | WFLY-20041 | Warning logged when multiple metrics systems enabled | WildFly now logs a warning if both Micrometer and MicroProfile Metrics (or multiple metrics systems) are active simultaneously. Review your server configuration and deployment to ensure you intentionally enable only one metrics subsystem. |
| 8 | WFLY-20947, WFLY-20948 | Distributed cache listeners and managers after suspend/resume | Distributed cache listeners no longer missed events after server suspend/resume, and distributed managers no longer require a restart. If you had workarounds in place for these issues, they can be removed. |
| 9 | WFLY-20754 | `TransactionUtil.isInTx` fix for rollback-only state | `TransactionUtil.isInTx()` was returning `false` when a transaction was in `rollback-only` state. This has been corrected. If your application logic branched on this return value specifically to detect rollback-only transactions, re-test the affected flows. |
| 10 | WFLY-20787 | `java:comp/UserTransaction` available during CDI `@Startup` | `java:comp/UserTransaction` was not accessible during CDI `@Startup` events; this is now fixed. If you worked around this by lazily looking up `UserTransaction`, the workaround is no longer needed. |
| 11 | WFLY-20366, WFLY-21099 | JGroups protocol module load with `org.jgroups.protocols` prefix | JGroups protocols configured with `module=".."` now attempt to load using the `org.jgroups.protocols` prefix as fallback. If you have custom JGroups protocol configurations specifying a module, verify the module resolution still works as intended. |
| 12 | WFLY-15836 | TLS support added to JGroups TCP-based transports | JGroups TCP-based transports now support TLS. If you use TCP or TCP_NIO2 transports in a security-sensitive clustering environment, review the new TLS configuration options and consider enabling them. |
| 13 | WFLY-18403 | IIOP `server-ssl-context` and `client-ssl-context` independent | In the `iiop-openjdk` subsystem, `server-ssl-context` can now be configured without requiring `client-ssl-context`. If you previously had to set both, you can remove the unnecessary one. |
| 14 | WFLY-20960 | `hibernate.statistics.query_max_size` defaults to 200 | The default value for `hibernate.statistics.query_max_size` has been lowered to 200 (was higher). Applications that relied on an unlimited or larger query statistics cache may see statistics truncated. Override the property in `persistence.xml` if you need a higher value. |
| 15 | WFLY-20251 | OpenTelemetry logs capture formatted messages | OpenTelemetry log export now captures log messages after formatting (with substituted arguments). If you process raw log messages from OTel exports and expected unformatted templates, update your log processing logic. |
| 16 | WFLY-20567 | MicroProfile OpenAPI allows multiple deployments per endpoint | Multiple deployments can now share the same base path with OpenAPI. If you had a workaround for this limitation (e.g. unique prefixes), revisit your OpenAPI configuration. |
| 17 | WFLY-20983 | `@Resource` injection works in WebSocket endpoints | `@Resource`-annotated fields in `@ServerEndpoint` classes now get injected correctly. If you had workarounds (manual JNDI lookups) in WebSocket endpoints, they can be cleaned up. |
| 18 | WFLY-21131 | Hibernate `hibernate.jndi.class` class loading restored | A regression caused Hibernate configured with `hibernate.jndi.class` to fail loading classes. This is fixed. If you temporarily removed this property as a workaround, re-add it. |
| 19 | WFLY-21188 | Bytecode enhancement works in EJB JAR within EAR | Hibernate runtime bytecode enhancement was silently skipped for `EJB JAR` modules packaged inside an EAR. This is now fixed. Test EAR deployments with JPA entities to confirm enhancement and lazy loading work correctly. |
| 20 | WFLY-21044 | Transactions not recovered after MDB-triggered crash | A bug where transactions were not recovered after a server crash with an active MDB has been fixed. If you had compensating logic for this recovery gap, verify it is still correct under the fixed behaviour. |
| 21 | WFLY-21206 | `FD_SOCK2` restored to default TCP-based stacks | `FD_SOCK2` failure detection protocol was removed and has been restored to the default TCP-based JGroups stacks. If you customized your TCP stack to re-add it as a workaround, review for duplication. |
| 22 | WFLY-21349 | `require-host-http11` attribute deprecated and ignored | The `require-host-http11` attribute in the Undertow subsystem is now deprecated and its value is ignored at runtime. Remove it from your configuration to avoid deprecation warnings. |
| 23 | WFLY-20605 | MicroProfile Reactive Messaging: only `.war` deployments supported | Documentation clarifies that MP Reactive Messaging must be deployed from `.war` archives only. If you deploy reactive messaging code from an EJB JAR or EAR module, restructure as a WAR. |

---

## 🟡 Deprecations

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-21041, WFLY-21242, WFLY-21299 | JGroups and clustering deprecated concept references | The `JGroups` subsystem documentation and `mod_cluster`/`undertow` subsystems referenced deprecated `org.jboss.as.clustering.controller.CommonUnaryRequirement` concepts; these are being removed. Review any custom extensions or subsystems that reference `CommonUnaryRequirement` and migrate to the replacement API. |
| 2 | WFLY-21349 | `require-host-http11` in Undertow subsystem deprecated | See Behavioral Changes #22. The attribute is now deprecated; remove it from `standalone.xml` / `domain.xml`. |
| 3 | WFLY-21033, WFLY-16576, WFLY-20999 | `org.bouncycastle` module removal and restoration history | The `org.bouncycastle` module was removed (WFLY-16576), restored (WFLY-20999), then targeted for removal again (WFLY-21033). In WildFly 39, the module's long-term status is removal. Do not depend on the bundled BouncyCastle module; declare `bouncycastle` as an explicit application dependency instead. |

---

## 🔵 Notable New Capabilities

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-15836 | TLS for JGroups TCP transports | JGroups TCP-based transports now support TLS-secured cluster communication. Optional: configure `ssl-context` on your TCP or TCP_NIO2 transport to encrypt intra-cluster traffic. |
| 2 | WFLY-20918 | Idle eviction for distributed sessions and SFSBs | Idle time-based eviction is now configurable for distributable `HttpSession`, `SFSB`, and timer stores. Use the new `<idle-timeout>` element in `distributable-web` configuration to reclaim memory from idle sessions automatically. |
| 3 | WFLY-14559 | New RESTEasy `WebApplicationException` behavior attribute | The `jaxrs` subsystem exposes `resteasy-original-webapplicationexception-behavior` to control legacy vs. spec-compliant `WebApplicationException` propagation. Useful when migrating from older RESTEasy behavior. |
| 4 | WFLY-21122 | WildFly feature-packs use Galleon feature-pack families | WildFly feature-packs now use Galleon feature-pack family descriptors. This simplifies multi-feature-pack provisioning. Review your Galleon provisioning XML / WildFly Glow configuration if you compose multiple feature-packs. |
| 5 | WFLY-21189 | JDBC_PING2 datasource injection support | JGroups `JDBC_PING2` (available since JGroups 5.3.7) can now be configured with datasource injection, eliminating the need for manual JDBC URL configuration in the ping protocol. |

---

## Summary by Priority

| Priority Level | Count | Description |
| :--- | :--- | :--- |
| 🔴 **Breaking** | 1 | Must fix before migrating. |
| 🟠 **Mandatory** | 17 | Security CVEs, component upgrades, security config. |
| 🟡 **Behavioral / Deprecation** | 26 | Assess impact and adjust accordingly. |
| 🔵 **New Capabilities** | 5 | Optional but recommended to leverage. |

## 🚨 Most Critical Items for Migration

- **Infinispan 16.0 + JGroups 5.5 (major version jump):** Both clustering libraries have undergone major version upgrades with potential breaking changes to serialization, protocol stacks, and cache configuration. Validate all distributed caching, session failover, and clustering scenarios before promoting to production.
- **Jakarta EE 11 Security in WildFly Preview (Security Manager removal + new auth specs):** The `SecurityManager` subsystem is being phased out and Jakarta Authorization/Security/Authentication specs have moved to EE 11 versions in WildFly Preview. Any application using legacy security policies, `java.security.Policy`, or pre-EE 11 JACC/JASPIC must migrate to the Elytron or Jakarta Security 4.x model.
- **Multiple Netty CVE upgrades (target: 4.1.130.Final):** Three rounds of Netty CVE patches culminate in 4.1.130.Final. If you override `io.netty` versions in your BOM or parent POM, ensure the final override lands at `4.1.130.Final` to address CVE-2025-67735, CVE-2025-58056, and CVE-2025-55163.
- **lz4-java CVE upgrades (CVE-2025-66566, CVE-2025-12183 — target: 1.10.2):** Two CVEs in `at.yawk.lz4:lz4-java` require upgrading to 1.10.2. If your project explicitly pins lz4-java (common via Kafka or Infinispan transitive dependencies), update immediately.
- **JPA bytecode enhancement now enabled by default:** Hibernate persistence container bytecode enhancement is now on by default. Applications with complex entity hierarchies, custom proxies, or instrumentation-sensitive code must be tested for lazy-loading correctness and proxy behavior regressions before upgrading.
