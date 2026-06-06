# WildFly — Filtered Migration Changes

- **Framework:** `wildfly`
- **Range:** `35.0.0` → `36.0.0`
- **Filter phase:** Phase 5 (filter-and-group)
- **Generated:** 2026-06-06

---

## 🔴 Breaking Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-19983, WFLY-20005, WFLY-20007, WFLY-20008, WFLY-20009, WFLY-20011, WFLY-20014, WFLY-20015, WFLY-20017, WFLY-20018, WFLY-20019, WFLY-20020, WFLY-20021, WFLY-20022, WFLY-20023, WFLY-20024, WFLY-20025, WFLY-20152 | ModuleIdentifier removed across all subsystems | `ModuleIdentifier` API removed from JPA, Messaging, Pojo, MP Config, Naming, Weld, Web Services, IIOP, XTS, EE, Application Client, Undertow, JSF, Concurrency, SAR, and JCA subsystems. Any extension or SPI code that directly references `org.jboss.modules.ModuleIdentifier` will fail to compile or deploy. Migrate all usages to the `ModuleName`-based APIs provided by WildFly Core 28. |

---

## 🟠 Mandatory Migrations — Security & CVE Fixes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-19969, WFLY-20100 | CVE-2024-10234 fixed in WildFly and HAL | CVE-2024-10234 (Cross-Site Scripting in HAL management console) resolved by upgrading HAL to 3.7.7.Final. Upgrade immediately; exposed management interfaces are at risk. Ensure the management console is not publicly accessible until patched. |
| 2 | WFLY-20027, WFLY-20118 | HornetQ upgraded to fix CVE-2024-51127 | HornetQ upgraded to 2.4.11.Final resolving CVE-2024-51127. Any deployment that bundles HornetQ client libraries should also upgrade its own dependency. |
| 3 | WFLY-20403 | Netty upgraded for CVE-2025-24970 and CVE-2025-25193 | Netty upgraded to 4.1.118.Final, resolving two 2025 CVEs affecting HTTP/2 and SSL handling. If your application directly depends on Netty, align its version with 4.1.118+. |
| 4 | WFLY-20550 | CVE-2025-2251 gadget class blocklist extended | Additional classes identified by security researchers as exploit gadgets are now blocked. If your application uses any of the affected class paths for legitimate deserialization, you must add an explicit allowlist or refactor. |

---

## 🟠 Mandatory Migrations — Major Component Upgrades

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-20421, WFLY-20422 | Infinispan upgraded to 15.1; wildfly-clustering 6.0 | Infinispan moved from 15.0.x to 15.1 and wildfly-clustering to 6.0.0.Final. API and SPI changes exist in the clustering tier. Custom Infinispan cache configurations or programmatic cache access may require updates. Review the Infinispan 15.1 migration guide. |
| 2 | WFLY-20490 | Apache Artemis upgraded to 2.40.0 | Major jump in Apache Artemis version. Configuration schema and client API changes may affect applications that interact directly with the Artemis broker API or use advanced messaging configuration. Validate JMS/messaging configurations. |
| 3 | WFLY-17478 | Legacy security and PicketLink subsystems moved under `legacy/` | The old `security` and `picketlink` subsystems have been relocated under the `legacy/` directory in the server layout. Any scripts, JBoss CLI operations, or tooling (including JBoss Server Migration Tool) that reference these subsystems by absolute path must be updated. |
| 4 | WFLY-19212 | Security Manager extension removed from WildFly Preview default config | WildFly Preview no longer includes the Security Manager extension in its default configuration. Applications relying on the Security Manager subsystem in WildFly Preview must either switch to WildFly standard, re-add the extension manually, or remove the Security Manager dependency. |
| 5 | WFLY-20533 | `-Djava.security.manager=allow` no longer set by default | The JVM flag `-Djava.security.manager=allow` is no longer passed by default at startup; it is only added when `-secmgr` is explicitly supplied. Deployments that relied on this flag being present without passing `-secmgr` will no longer run under the Security Manager. Audit startup scripts. |
| 6 | WFLY-20393, WFLY-19393 | JPA bytecode enhancement enabled by default | Persistence/JPA bytecode enhancement is now enabled by default (previously disabled). This affects lazy loading behavior, equals/hashCode semantics, and class instrumentation. Existing applications may experience runtime behavior changes. Test JPA entities thoroughly; disable explicitly if needed via `<property name="wildfly.jpa.bytecodeenhancement" value="false"/>`. |
| 7 | WFLY-20313 | Datasource subsystem XA config 5.0/6.0 parsing fixed | The datasource subsystem failed to parse XA DataSource configurations written in schema 5.0 and 6.0. This is now fixed. Verify existing XA datasource configurations load correctly after upgrade. |

---

## 🟠 Mandatory Migrations — Security Configuration

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-20475 | JCA `elytron-enabled` attribute writeable via Migration Tool | The `elytron-enabled` attribute on the JCA workmanager was not properly writable when using the JBoss Server Migration Tool. Fixed in 36. If migrating from an older server using the migration tool, re-run or validate JCA security configuration post-migration. |
| 2 | WFLY-20001 | PolicyUtil from Elytron EE now used to access `java.security.Policy` | WildFly has switched to `PolicyUtil` from Elytron EE for `java.security.Policy` access. Custom Security Manager policy setups or direct `Policy.setPolicy()` calls may break. Migrate to the Elytron EE API. |

---

## 🟡 Behavioral Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-20041 | Warning logged when multiple metrics systems are enabled | If both Micrometer and the legacy Metrics subsystem are active simultaneously, a warning is now logged. Review your metrics configuration to avoid conflicts and ensure only one metrics provider is enabled. |
| 2 | WFLY-20120, WFLY-20533 | `java.security.manager=allow` restricted to SE 18–23 | The Security Manager JVM flag is now only passed for Java SE 18–23. On SE 24+ the Security Manager is fully removed by the JDK. Applications running on SE 24+ that previously used Security Manager features will not have them available at all. |
| 3 | WFLY-19888, WFLY-19878 | Minimum Java SE version raised to 17 | WildFly 36 requires Java SE 17 as the minimum runtime. Java SE 11 is no longer supported. Update all build toolchains, CI pipelines, and runtime environments to SE 17+. |
| 4 | WFLY-20395 | EJB interceptor bindings now check superclass methods | `DeploymentDescriptorInterceptorBindingsProcessor` now correctly applies `ejb-jar.xml` interceptor bindings to superclass methods and `String[]` parameters. Deployments that previously failed to deploy or had incorrect interceptor behavior may now behave differently. |
| 5 | WFLY-20311 | SFSBs created but never invoked now expire correctly | Stateful Session Beans (SFSBs) that are created but never invoked will now be scheduled for expiration correctly. Applications that depended on such beans not expiring should review their SFSB lifecycle management. |
| 6 | WFLY-20325 | MicroProfile Health CDI extension resets on undeploy | The MP Health CDI extension now correctly resets `disabled default procedures` configuration on application undeploy. Previously, the state leaked between redeploys, potentially causing incorrect health check behavior. |
| 7 | WFLY-20283 | OutOfMemoryError fixed in IIOP CDRInputStream on JDK 21 | A bug causing incorrect byte array size calculation in CORBA/IIOP CDRInputStream on JDK 21 is fixed. Applications using IIOP on JDK 21 should see improved stability. |
| 8 | WFLY-13828 | EJB remote+tls protocol now supported | `remote+tls` is now a supported protocol for EJBClient and `remote-outbound-connection`. If you previously had to work around missing TLS support in remote EJB connections, this workaround can now be removed. |
| 9 | WFLY-20380 | `log4j-api` added to wildfly-ee BOM | `org.apache.logging.log4j:log4j-api` is now included in the WildFly EE BOM. Applications that previously needed to manually declare this dependency can now rely on managed version alignment via the BOM. |

---

## 🟡 Deprecations

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-20164, WFLY-20165, WFLY-20166, WFLY-20167, WFLY-20168, WFLY-20169, WFLY-20170, WFLY-20171, WFLY-20172, WFLY-20173, WFLY-20174, WFLY-20175, WFLY-20176, WFLY-20177, WFLY-20182, WFLY-20183, WFLY-20184, WFLY-20185, WFLY-20186, WFLY-20187, WFLY-20188, WFLY-20189, WFLY-20192, WFLY-20193, WFLY-20194, WFLY-20196, WFLY-20197, WFLY-20198, WFLY-20199, WFLY-20200, WFLY-20201, WFLY-20202, WFLY-20203, WFLY-20204, WFLY-20205 | `ModuleDependency` deprecated constructor removed from all subsystems | The deprecated `ModuleDependency(...)` constructor has been replaced by `ModuleDependency.Builder` across all subsystems (TXN, NAMING, APPCLIENT, EE, CLUSTERING, JAKARTA DATA, JSF, SECURITY, BATCH, IIOP, BEAN VALIDATION, JCA, EJB, UNDERTOW, REST, JPA, MAIL, JMS, POJO, SAR, WEBSERVICES, WELD, MICROMETER, OPENTELEMETRY, MP CONFIG, MP FT, MP HEALTH, MP JWT, MP LRA, MP OPENAPI, MP REACTIVE MESSAGING, MP TELEMETRY, MP REACTIVE STREAMS). Any extension that calls the old constructor directly will produce compilation or runtime warnings. Migrate to `ModuleDependency.Builder` API before the constructor is removed entirely. |
| 2 | WFLY-20150 | JSTL module now uses non-deprecated `jakarta.servlet.jstl.api` | The deprecated `javax.servlet.jstl.api` module alias is replaced by `jakarta.servlet.jstl.api`. Any module descriptor (`module.xml`) that explicitly references the old module name must be updated. |
| 3 | WFLY-20230, WFLY-20224, WFLY-20348 | Deprecated deployment attachment APIs removed | `Attachments.MODULE_IDENTIFIER`, `Attachments.ADDITIONAL_ANNOTATION_INDEXES_BY_MODULE`, and `ModuleDependency.getIdentifier()` are removed. Custom deployment processors or subsystem extensions using these APIs must migrate to the replacement `ADDITIONAL_INDEX_MODULES` attachment and name-based API. |
| 4 | WFLY-20424 | EJB marshaller attribute deprecated value warning | The `marshaller` attribute in EJB subsystem configuration warns when set to a deprecated value. Review and update EJB subsystem configuration to remove deprecated marshaller settings. |

---

## 🔵 Notable New Capabilities

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | WFLY-18582 | Prometheus endpoint added to Micrometer extension | The Micrometer extension now exposes a `/metrics` Prometheus-compatible scrape endpoint at community stability level. Teams using Prometheus-based monitoring can now scrape metrics directly without requiring a separate OpenTelemetry collector bridge. |
| 2 | WFLY-20476, WFLY-20477 | Undertow AJP and reverse proxy attributes promoted to community | `AJP_ALLOWED_REQUEST_ATTRIBUTES_PATTERN`, `reuse-x-forwarded-header`, and `rewrite-host-header` are promoted from preview to community stability. These can now be used in production configurations without stability warnings. |
| 3 | WFLY-19588, WFLY-19591, WFLY-19592, WFLY-19846, WFLY-19866 | MicroProfile Platform 7 fully implemented | WildFly 36 implements MicroProfile Platform 7, including MicroProfile OpenAPI 4.0, Fault Tolerance 4.1, Telemetry 2.0 (promoted to standard), and REST Client 4.0 (promoted to default stability). Applications targeting MP 7 specifications can now use these APIs without preview caveats. |
| 4 | WFLY-20160, WFLY-20326 | Hibernate ORM 7 and Hibernate Search 8 in WildFly Preview | WildFly Preview now includes Hibernate ORM 7.x and Hibernate Search 8.0. Developers can begin evaluating and migrating JPA applications to the next Hibernate generation. Not yet available in standard WildFly. |

---

## Summary by Priority

| Priority Level | Count | Description |
| :--- | :--- | :--- |
| 🔴 **Breaking** | 1 | Must fix before migrating. |
| 🟠 **Mandatory** | 13 | Security CVEs, component upgrades, security config. |
| 🟡 **Behavioral / Deprecation** | 13 | Assess impact and adjust accordingly. |
| 🔵 **New Capabilities** | 4 | Optional but recommended to leverage. |

## 🚨 Most Critical Items for Migration

- **ModuleIdentifier API removal (WFLY-19983 et al.):** The `ModuleIdentifier` class has been removed from all WildFly subsystem SPIs. Any custom extension, subsystem, or deployment processor that directly references this class will fail. Audit all custom WildFly extensions against the new `ModuleName`-based API before upgrading.

- **JPA bytecode enhancement enabled by default (WFLY-19393/WFLY-20393):** Bytecode enhancement is now on by default. This changes lazy loading semantics, equals/hashCode behavior on unenhanced proxies, and class structure at load time. Run full JPA integration tests and explicitly disable enhancement (`wildfly.jpa.bytecodeenhancement=false`) if incompatibilities are found.

- **Legacy security subsystems relocated (WFLY-17478):** The `security` and `picketlink` subsystems have moved to the `legacy/` directory. Any automation, CLI scripts, or migration tooling that constructs absolute paths to these subsystem resources will break silently or fail at runtime. Update all operational scripts before the upgrade.

- **Netty CVE-2025-24970 / CVE-2025-25193 (WFLY-20403):** Two exploitable Netty CVEs affecting HTTP/2 and SSL are patched in this release. If you cannot upgrade immediately, ensure WildFly management and application ports are firewalled, and prioritize this upgrade in your security patch cycle.

- **Security Manager startup flag removed by default (WFLY-20533):** `-Djava.security.manager=allow` is no longer injected automatically. Any deployment that previously activated Security Manager behavior implicitly (without `-secmgr`) will run without it after upgrade. Validate Security Manager-dependent permission configurations and update startup scripts to explicitly pass `-secmgr` where required.
