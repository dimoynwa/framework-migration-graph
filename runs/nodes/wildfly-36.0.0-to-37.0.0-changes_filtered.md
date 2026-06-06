# WildFly Migration Filter — 36.0.0 → 37.0.0

- **Framework:** WildFly
- **Range:** 36.0.0 → 37.0.0
- **Filtered (UTC):** 2026-06-06

---

## 🔴 Breaking Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-19983, WFLY-20025 | `ModuleIdentifier` removed from public APIs | `ModuleIdentifier` has been removed from non-breaking usages across the JCA and core subsystems. Any extension, subsystem, or application code that references `org.jboss.modules.ModuleIdentifier` directly will fail to compile or deploy. Migrate to `ModuleIdentifierUtil` / string-based module names using `ModuleDependency.Builder`. |
| 2 | WFLY-17478 | Legacy security/picketlink subsystems moved under `legacy` | The old `security` and `picketlink` subsystems have been relocated under the `legacy` directory in the server configuration. Configurations or server-migration-tool scripts relying on the old subsystem path will break. Update configuration paths accordingly. |
| 3 | WFLY-19212 | Security Manager extension removed from WildFly Preview | The Security Manager extension is no longer present in WildFly Preview default configuration. Applications or provisioning scripts that reference or activate the Security Manager extension in WildFly Preview will fail on startup. Remove the reference or switch to WildFly Standard. |
| 4 | WFLY-20533 | `-Djava.security.manager=allow` no longer added by default | The server startup scripts no longer unconditionally add `-Djava.security.manager=allow` to the JVM arguments. Only when `-secmgr` is explicitly passed will this property be set. Any deployment relying on the security manager being implicitly allowed will fail at runtime unless `-secmgr` is added. |
| 5 | WFLY-20693 | JCA resource-adapter subsystem parser security config bug fixed | A bug in `ResourceAdapterSubsystemParser` caused security configuration to be silently dropped during parsing. The fix changes parsing behaviour: previously-silent misconfigurations may now surface as errors. Validate your `resource-adapter` subsystem XML after upgrade. |

---

## 🟠 Mandatory Migrations — Security & CVE Fixes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-20550 | CVE-2025-2251: additional exploit-gadget classes blocked | Additional classes identified by security researchers as useful in deserialization gadget chains are now blocked by the server's class filter. Any application that intentionally (or inadvertently) relies on unmarshalling these classes over JBoss Remoting or EJB will receive a `SecurityException` at runtime. Audit remote-invocation payloads. |
| 2 | WFLY-20403 | Netty upgraded to 4.1.118+ (CVE-2025-24970, CVE-2025-25193) | Netty is upgraded from 4.1.117.Final through to 4.1.123.Final, resolving two confirmed CVEs. Applications or modules that bundle a different Netty version may encounter classloading conflicts. Remove any vendored Netty JARs from your deployment and rely on the server-provided module. |
| 3 | WFLY-20662 | commons-beanutils 1.11.0 (CVE-2025-48734) | commons-beanutils has been upgraded to 1.11.0 to address CVE-2025-48734 (critical deserialization vulnerability). Deployments bundling an older version of commons-beanutils override the server module and remain vulnerable. Remove the bundled JAR or align to 1.11.0+. |
| 4 | WFLY-20713 | Nimbus Jose JWT 10.3 (CVE-2025-53864) | Nimbus Jose JWT is upgraded to 10.3 (and subsequently 10.3.1). CVE-2025-53864 affects JWT processing. Applications that embed their own nimbus-jose-jwt must upgrade or exclude the bundled version. |

---

## 🟠 Mandatory Migrations — Major Component Upgrades

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-20598, WFLY-20599, WFLY-20600 | wildfly-clustering 7.0 / Infinispan 15.2 / JGroups 5.4 | Major version bumps across the entire clustering stack. Infinispan 15.2 and JGroups 5.4 introduce API and configuration changes. Applications using embedded Infinispan caches, custom JGroups protocols, or directly referencing clustering internals must validate compatibility. Off-heap caches now require deployment-specific media type configuration (see WFLY-20772). |
| 2 | WFLY-20601 | Apache Artemis upgraded to 2.41.0 | Artemis 2.41.0 contains behaviour changes around broker system-property handling (`brokerconfig.` prefix now conflicts — see WFLY-20609). Review broker configuration and avoid system properties with the `brokerconfig.` prefix unless intentional. |
| 3 | WFLY-20160, WFLY-20613, WFLY-20732 | Hibernate ORM 7 available in WildFly Preview | WildFly Preview now ships with Hibernate ORM 7.0.2.Final alongside standard Hibernate 6.6.x. Hibernate ORM 7 drops legacy APIs and changes several behaviours. WildFly Standard continues on Hibernate ORM 6.6.x. If you use WildFly Preview, explicitly test all JPA functionality. |
| 4 | WFLY-20475 | JCA `elytron-enabled` attribute handling changed | The JCA subsystem's `elytron-enabled` attribute on `WorkManager`/`DistributedWorkManager` is affected by a migration-tool regression fix. When using the JBoss Server Migration Tool, verify that Elytron security settings on JCA resources are correctly migrated and not silently discarded. |
| 5 | WFLY-20772 | Off-heap Infinispan caches require media type config | Following the Infinispan 15.2 upgrade, caches using off-heap storage now require an explicit deployment-specific media type to be declared. Deployments using off-heap distributed sessions will fail at runtime without this configuration. Add the required media type configuration to cache definitions. |

---

## 🟠 Mandatory Migrations — Security Configuration

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-20542 | Security manager failures persisting EJB timers | With the security manager enabled, EJB timer persistence required additional `SocketPermission` grants. If you run with `-secmgr` and use database-backed EJB timers, add the required socket permissions to your policy file. |
| 2 | WFLY-20295 | `wildfly-elytron` direct dependency banned | Direct dependency on `org.wildfly.security:wildfly-elytron` in application code is now explicitly banned. Projects that declare this dependency in their Maven/Gradle build will fail at validation time. Remove the direct dependency and use the `wildfly-elytron-bom` or rely on the provided module. |
| 3 | WFLY-20666, WFLY-18097 | `wildfly-elytron` dependency removed from user BOMs | The `wildfly-elytron` artifact has been removed from the WildFly user-facing BOMs. Any application BOM import that previously pulled in Elytron transitively will no longer do so. Add an explicit, scoped dependency if your code compiles against Elytron APIs. |

---

## 🟡 Behavioral Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-20557 | Container-interceptors priority collision on deployment | Deployments using container-interceptors could fail with `WFLYEE0079: Can't add ..., priority 0x249 is already taken`. This is now fixed, but upgraders who worked around it (e.g. changing interceptor ordering) should validate that their workaround does not conflict with the fix. |
| 2 | WFLY-20564 | NPE deploying third-party JDBC driver JARs (e.g. PostgreSQL) | Deploying `postgresql-42.7.5.jar` (and similar driver JARs) triggered a NPE when upgrading from WildFly 35→36. Fixed in 36.0.1 and forward-ported to 37. Ensure you are not working around this via a custom DataSource XML; the standard deployment path now works correctly. |
| 3 | WFLY-20521 | CDI + Jakarta Persistence + app-defined datasources compatibility | Using CDI with Jakarta Persistence and application-defined datasources required explicitly disabling bytecode enhancement. This constraint is now resolved. If you added `<property name="hibernate.enhancer.enableDirtyTracking" value="false"/>` as a workaround, remove it and re-test. |
| 4 | WFLY-20710 | `FD_SOCK2` removed from default JGroups TCP stacks | The `FD_SOCK2` protocol has been removed from default TCP-based JGroups stacks. Clusters that explicitly referenced `FD_SOCK2` in custom stack configurations may see unexpected changes; validate cluster formation and failure detection. |
| 5 | WFLY-20682, WFLY-20718 | RESTEasy module exported dependencies restructured | RESTEasy no longer exports module dependencies from its main modules; they are now injected via Deployment Unit Processors (DUPs). Additionally, Jackson 1 annotation scanning has been removed from the JAX-RS subsystem. Deployments that relied on RESTEasy's transitively exported classpath or on Jackson 1 annotations may break. Migrate to Jakarta-namespace Jackson 2 and declare any previously-transitive dependencies explicitly. |
| 6 | WFLY-20609 | Artemis fails to launch with `brokerconfig.` system properties | If any JVM system property has the prefix `brokerconfig.`, ActiveMQ Artemis now fails on startup. Review JVM arguments and rename or remove conflicting properties. |
| 7 | WFLY-20723 | `java.sql.Date.toInstant` throws `UnsupportedOperationException` in JSON processing | JSON processing of `java.sql.Date` now fails where it previously silently produced wrong output. Adjust Jackson serializers or use `java.time.LocalDate` / `java.util.Date` instead. |
| 8 | WFLY-20727 | `ManagedScheduledExecutorService` executes tasks multiple times | A bug caused scheduled tasks to fire multiple times. The fix restores correct single-execution semantics. Workarounds (e.g. idempotency guards added specifically for this bug) should be reviewed and may be removed. |
| 9 | WFLY-20691 | 404 on JNDI lookup behind load balancer | JNDI lookups over HTTP routed through a load balancer returned 404 in certain configurations. This is now fixed. No action required unless you added a workaround routing layer. |
| 10 | WFLY-20283 | `OutOfMemoryError` in CDRInputStream on JDK 21 | An `OutOfMemoryError` due to improper byte-array size calculation in IIOP/CORBA code on JDK 21 is fixed. Deployments using IIOP that avoided JDK 21 because of this issue can now upgrade. |
| 11 | WFLY-20311 | SFSBs created but never invoked no longer fail to expire | Stateful session beans created but never invoked would never expire, causing a resource leak. The fix enables correct expiration. Monitor SFSB pool sizes after upgrade to ensure no unexpected cleanup occurs. |
| 12 | WFLY-20617 | NPE in `ExpirationMetaData.getLastAccessTime()` on deployment | Deployments could fail with a NullPointerException in `ExpirationMetaData.getLastAccessTime()`. Fixed in 36.0.1 and 37. No user action required. |

---

## 🟡 Deprecations

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-20164, WFLY-20168, WFLY-20169, WFLY-20171, WFLY-20173, WFLY-20174, WFLY-20177, WFLY-20183, WFLY-20184, WFLY-20185, WFLY-20186, WFLY-20187, WFLY-20188, WFLY-20189, WFLY-20192, WFLY-20193, WFLY-20194, WFLY-20196, WFLY-20197, WFLY-20198, WFLY-20199, WFLY-20200, WFLY-20201, WFLY-20202, WFLY-20203, WFLY-20204, WFLY-20205 | `ModuleDependency` deprecated constructor eliminated across all subsystems | The deprecated `ModuleDependency` constructor and `getIdentifier()` method have been removed from all WildFly subsystems (BATCH, IIOP, JCA, EJB, Undertow, REST, JPA, MAIL, JMS, POJO, SAR, WebServices, Weld, TXN, Micrometer, OpenTelemetry, MP Config, MP Fault Tolerance, MP Health, MP JWT, MP LRA, MP OpenAPI, MP Reactive Messaging, MP Telemetry, MP Reactive Streams). Extension code or SPIs that use these deprecated constructors must migrate to `ModuleDependency.Builder`. |
| 2 | WFLY-20591, WFLY-20224, WFLY-20230, WFLY-20348, WFLY-20623, WFLY-20624 | Deprecated `ModuleIdentifier` / `ModuleIdentifierUtil` usages removed | `Attachments.ADDITIONAL_ANNOTATION_INDEXES_BY_MODULE`, `Attachments.MODULE_IDENTIFIER`, `ModuleDependency.getIdentifier()`, `ModuleIdentifierUtil` deprecated methods, and deprecated `ServiceInstaller` start-mode methods are all removed. Extension or embedding code that references these APIs will fail to compile against WildFly internals. Migrate to the replacement APIs. |
| 3 | WFLY-20782 | `driver-name` attribute on `h2-driver` feature group deprecated | The `h2-driver` Galleon feature group no longer sets the deprecated `driver-name` resource attribute. Provisioning scripts or CLI scripts that read `driver-name` on H2 datasource resources may receive an absent attribute. Adjust scripts accordingly. |

---

## 🔵 Notable New Capabilities

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-18582, WFLY-20477 | Prometheus endpoint added to Micrometer; Undertow headers promoted | A Prometheus-compatible endpoint is now available via the Micrometer extension (community stability). Undertow's `reuse-x-forwarded` and `rewrite-host` header configurability are promoted to community stability. Teams using Micrometer for metrics can expose Prometheus scraping without additional configuration. |
| 2 | WFLY-13828 | EJB Client `remote+tls` transport supported | EJB Client now supports `remote+tls` as a transport scheme in remote outbound connection configuration, enabling TLS-secured remote EJB invocations without a separate SSL layer. Update `remote-outbound-connection` configurations to use `remote+tls` where TLS is required. |
| 3 | WFLY-20512 | Artemis `commit-interval` attribute exposed for scaledown | A new `commit-interval` attribute is exposed on the Artemis messaging subsystem to control message commit behaviour during scaledown operations. Useful for tuning clustered Artemis scaledown in WildFly. |
| 4 | WFLY-20651 | Hook to disable zstd Kafka compression | A system property hook is available to disable zstd-based Kafka compression if the native library is unavailable or incompatible with the runtime environment. No action required unless you encounter compression-related failures in reactive messaging. |
| 5 | WFLY-20770 | `jboss-client.jar` updated for JDK Mission Control 9+ | The `jboss-client.jar` has been updated to integrate with JDK Mission Control 9 and later, enabling JMC-based profiling and monitoring of WildFly. No migration action required; this is an additive improvement. |

---

## Summary by Priority

| Priority Level | Count | Description |
| :--- | :--- | :--- |
| 🔴 **Breaking** | 5 | Must fix before migrating. |
| 🟠 **Mandatory** | 12 | Security CVEs, component upgrades, security config. |
| 🟡 **Behavioral / Deprecation** | 15 | Assess impact and adjust accordingly. |
| 🔵 **New Capabilities** | 5 | Optional but recommended to leverage. |

## 🚨 Most Critical Items for Migration

- **WFLY-19983 / WFLY-20025 — `ModuleIdentifier` removed from public APIs:** Any extension, subsystem, or application that directly references `org.jboss.modules.ModuleIdentifier` will fail to compile or deploy. This is the single most impactful change for teams that extend or embed WildFly. Migrate all usages to `ModuleDependency.Builder` and string-based module names before upgrading.

- **WFLY-20533 — Security Manager no longer allowed by default:** The JVM argument `-Djava.security.manager=allow` is no longer appended unconditionally. Applications or test suites that implicitly depend on the Security Manager being silently available will fail with `SecurityException` at runtime. Audit startup scripts and add `-secmgr` explicitly if the Security Manager is required.

- **WFLY-20550 — CVE-2025-2251 exploit-gadget class blocklist expanded:** The server now blocks a larger set of classes from being unmarshalled over JBoss Remoting/EJB. Deployments that use custom serialization or pass complex object graphs over remote EJB/JBoss Remoting must verify none of their payload classes are on the new blocklist.

- **WFLY-20598 / WFLY-20599 / WFLY-20600 — wildfly-clustering 7.0 / Infinispan 15.2 / JGroups 5.4 major upgrades:** The entire clustering stack has been major-versioned. Applications using distributed sessions, clustered EJBs, or embedded Infinispan must perform a full compatibility test. Off-heap caches additionally require new media type configuration (WFLY-20772) or will fail at startup.

- **WFLY-20662 — CVE-2025-48734 in commons-beanutils:** This is a critical deserialization CVE. Deployments that bundle their own copy of commons-beanutils older than 1.11.0 remain exposed even after server upgrade. Actively audit and replace any bundled `commons-beanutils` JAR in all deployed applications.
