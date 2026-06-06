# WildFly 30.0.0 → 31.0.0 — Filtered Migration Guide

- **Framework:** `wildfly`
- **Range:** `30.0.0` → `31.0.0`
- **Filtered:** 2026-06-06

---

## 🔴 Breaking Changes

| # | JIRA | Title | Impact |
| --- | --- | --- | --- |
| 1 | WFLY-17842 | Removal of `sun.jdk` implicit module | The `sun.jdk` module is no longer implicitly added to deployments. Applications relying on internal JDK APIs via this module will fail to deploy. Audit your deployments and add explicit module dependencies if required, or migrate to supported public JDK APIs. |
| 2 | WFLY-16168, WFLY-18047, WFLY-18311, WFLY-18644 | Removal of Legacy Xerces Dependency | WildFly has removed legacy Xerces from its distribution, migrating RestEasy, WebServices, and Hibernate Validator to use JDK JAXP instead. Remove any references or expectations of the legacy Xerces implementation from your application configuration and packaging. |
| 3 | WFLY-18635 | Removal of Scattered Cache Support | Support for the scattered cache topology in Infinispan has been dropped. Update your clustering configurations to use distributed or replicated caches instead to ensure successful server boot and clustering operations. |
| 4 | WFLY-18245 | `org.apache.avro` Module Moved to Preview | The `org.apache.avro` module has been moved from the standard `wildfly-ee` feature pack to `wildfly-preview`. Applications requiring Apache Avro must provision the preview feature pack or bundle the Avro dependency directly in their deployment. |

## 🟠 Mandatory Migrations — Security & CVE Fixes

| # | JIRA | Title | Impact |
| --- | --- | --- | --- |
| 1 | WFLY-18704 | Upgrade Artemis to 2.31.2 (CVE-2023-46604) | Apache ActiveMQ Artemis has been upgraded to 2.31.2 to resolve CVE-2023-46604, a critical remote code execution vulnerability. Update your client dependencies and verify that remote clients using JMS or native protocols are patched to compatible, secure versions. |
| 2 | WFLY-18625, WFLY-18729 | Upgrade Netty to 4.1.104.Final (CVE-2023-44487) | Netty has been upgraded to address the HTTP/2 Rapid Reset vulnerability. Ensure your dependencies, BOMs, and custom server provisions pull the updated Netty version to mitigate denial-of-service risks against HTTP/2 endpoints. |
| 3 | WFLY-18685 | Upgrade Santuario to 3.0.3 (CVE-2023-44483) | Apache Santuario has been upgraded to 3.0.3 to patch CVE-2023-44483. Validate your XML security integrations and web services endpoints to ensure compatibility with the updated library. |
| 4 | WFLY-18301 | Upgrade `com.squareup.okio` (CVE-2023-3635) | The `com.squareup.okio` component has been upgraded to 3.4.0 to resolve a security vulnerability. Update any standalone client dependencies or BOM references to ensure you are protected. |

## 🟠 Mandatory Migrations — Major Component Upgrades

| # | JIRA | Title | Impact |
| --- | --- | --- | --- |
| 1 | WFLY-18399, WFLY-18542, WFLY-18609, WFLY-18629, WFLY-18555, WFLY-18927, WFLY-18374, WFLY-18583, WFLY-18804 | Upgrade to Hibernate ORM 6.4 & Search 7.0 | WildFly now provides Hibernate ORM 6.4.2.Final and Hibernate Search 7.0. Review the official Hibernate 6.x and 7.x migration guides for potential API and query language changes, and test your persistence layer extensively. |
| 2 | WFLY-18277, WFLY-18377, WFLY-18416, WFLY-18630, WFLY-18774 | Upgrade to Infinispan 14.0.21.Final | The Infinispan clustering subsystem has been updated to the 14.0.21.Final stream. Verify your distributed caching behavior, custom marshallers, and HotRod client configurations against this new baseline. |
| 3 | WFLY-18291, WFLY-18319, WFLY-18442, WFLY-18443, WFLY-18693, WFLY-18732, WFLY-18735, WFLY-18750, WFLY-18760, WFLY-18797, WFLY-18826 | MicroProfile and SmallRye Upgrades | Extensive upgrades have been applied across SmallRye Config, Fault Tolerance, Health, OpenTelemetry, OpenAPI, and Reactive Messaging. Audit your MicroProfile implementations to ensure compliance with updated specifications and verify metric/telemetry exports. |
| 4 | WFLY-18376, WFLY-18713, WFLY-18916, WFLY-18378, WFLY-18917 | Upgrade to RESTEasy 6.2.7.Final | RESTEasy and its MicroProfile integration have been bumped to the 6.2.x stream. Execute your JAX-RS test suites to catch any API behavioral shifts, updated content-type handling, or deprecations introduced in this release line. |

## 🟡 Behavioral Changes

| # | JIRA | Title | Impact |
| --- | --- | --- | --- |
| 1 | WFLY-18233, WFLY-18315, WFLY-18572, WFLY-18727 | Distributed Session Manager Adjustments | Revisions to metadata mapping and replication mean that `ATTRIBUTE` granularity distributed sessions will now consistently trigger replication upon calling `setAttribute(...)`. Review your session manipulation logic to avoid excessive network traffic from unnecessary mutations. |
| 2 | WFLY-18389, WFLY-18404, WFLY-18869 | `max-active-sessions` Expiration Fixes | Resolved bugs where the HotRod-based session manager would prematurely expire sessions and spawn excessive threads when `max-active-sessions` was set. Setting `max-active-sessions=-1` no longer triggers `ISPN000424` errors. Verify your web application expiration and concurrency thresholds. |
| 3 | WFLY-18240 | Explicit Artemis Dependency Requirement | Deployments that interact directly with Artemis APIs must now declare an explicit module dependency on `org.apache.activemq.artemis`. Check your `jboss-deployment-structure.xml` or manifest to ensure the dependency is properly declared. |
| 4 | WFLY-18540 | Auto-update to `FD_ALL2` Protocol | WildFly will automatically update legacy JGroups Failure Detection (`FD`) configurations to the newer `FD_ALL2` protocol. Cluster node discovery and failure communication behavior will change slightly during partitions; execute cluster failover tests to confirm stable network topologies. |
| 5 | WFLY-18306 | Adjusted Infinispan Remote Timeout | The default Infinispan remote-timeout has been corrected so it will not be less than the default lock-timeout. If you override these values in your configuration, verify that the remote timeout remains equal to or greater than the configured lock timeout. |
| 6 | WFLY-18324 | Empty JCA Recovery Passwords | JCA recovery configurations now cleanly support empty username and password values. If you previously utilized workarounds to handle empty credentials during recovery mapping, you may simplify your configuration files. |

## 🔵 Notable New Capabilities

| # | JIRA | Title | Impact |
| --- | --- | --- | --- |
| 1 | WFLY-15405 | AMQP Connector Support | MicroProfile Reactive Messaging now natively supports the AMQP connector. You can configure deployments to bridge reactive streams directly to AMQP-compatible message brokers without building or bundling custom extensions. |
| 2 | WFLY-18838, WFLY-18930 | Preview Support for Jakarta MVC 2.1 | WildFly Preview now includes support for Jakarta MVC 2.1 via the Krazo integration. Developers can begin writing and evaluating standard MVC-based views natively within the preview application server. |
| 3 | WFLY-18009 | Support for LZ4 Compression | WildFly now provisions native support for LZ4 compression. Deployments using native Kafka clients can now seamlessly produce and consume LZ4-compressed topics without needing to bundle the compression codec manually. |

---

## Summary by Priority

| Priority Level | Count | Description |
| --- | --- | --- |
| 🔴 **Breaking** | 4 | Must fix before migrating. |
| 🟠 **Mandatory** | 8 | Security CVEs, component upgrades, security config. |
| 🟡 **Behavioral / Deprecation** | 6 | Assess impact and adjust accordingly. |
| 🔵 **New Capabilities** | 3 | Optional but recommended to leverage. |

## 🚨 Most Critical Items for Migration

* The implicit module dependency on `sun.jdk` has been removed; audit your codebase and explicitly declare the dependency if your application relies on internal JDK APIs.
* Legacy Xerces has been removed entirely from the distribution; any deployment or internal code assuming the presence of the JBoss Xerces module will break and must be updated to use the standard JDK JAXP implementation.
* Netty, Artemis, and Santuario require mandatory updates to patch serious CVEs (including the HTTP/2 Rapid Reset and Artemis RCE); ensure your environment and clients utilize the updated BOMs.
* The platform shifts heavily to Hibernate ORM 6.4 and Infinispan 14; verify all entity mappings, queries, and HotRod client implementations against the respective component migration guides.