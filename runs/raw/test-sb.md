# Spring Boot — documented changes (extract-only)

- **Framework key:** `spring-boot`
- **Resolved range:** `3.3.0` → `3.4.0`
- **Generated (UTC):** 2026-06-04T08:44:51Z

---

- **bom_diff:** present in extraction metadata

## `3.3.0` → `3.3.1`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | SQL Server JDBC URL is malformed after adding org.springframework.boot.jdbc.parameters label |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | Git instant properties cannot be coerced following git-commit-id Maven plugin upgrade |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | Spring Boot remote restart with devtools causes 'factory already defined' Tomcat error when running with 'java -jar' |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | IllegalArgumentException when trying to use Tomcat's HttpNio2Protocol with Spring Boot-configured SSL |
| dependency_upgrade | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | Uber jar fails to start when it contains a dependency with Multi-Release: true in its manifest and unexpected file entries in META-INF/versions |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | JSP-related resources may not be found in an executable war file when using Jetty |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | The value of the tomcat.threads.config.max metric is always -1, irrespective of the configured maximum number of threads |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | The auto-configured reactiveNeo4jTransactionManager may cause a failure due to multiple TransactionManager beans |
| dependency_upgrade | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | Starter parent applies its configuration of the CycloneDX Maven plugin too broadly |
| dependency_upgrade | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | buildInfo does not work with Gradle 8.7 or later when the configuration cache is enabled |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | Extract fails due to a duplicate entry when BOOT-INF/classes contains a directory that's also present in the root of the jar |
| dependency_upgrade | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | sbom is not available to the actuator endpoint when using bootRun or bootWar |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | Document more precisely how a Container's Docker image name is used to find the matching service connection |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | Fix typos in javadoc of MockServerRestClientCustomizer and MockServerRestTemplateCustomizer |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | Document the need to switch to io.micrometer:micrometer-registry-prometheus-simpleclient to use the Prometheus push gateway |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | Improve consistency of documentation guidelines for packaging and running applications |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | @Testcontainers |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | Warn in the documentation that spring.profiles.group can only be used in non-profile-specific documents |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | ❤️ Contributors (Thank you to all the contributors who worked on this release:) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | @Eng-Fouad (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | @PiyalAhmed (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | @Seungpang (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | @asashour (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | @cmabdullah (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | @dependabot ([bot],) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | @donghoony (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | @erie0210 (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | @izeye (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | @mateusscheper (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | @onobc (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | @quaff (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.1 | @sdeleuze (, and) |

## `3.3.1` → `3.3.2`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.2 | No configuration property for defaultTimeout setting that was introduced in Spring Integration 6.2 |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.2 | NPE during auto-configuration in OnClassCondition.resolveOutcomesThreaded because firstHalf is null |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.2 | Spring Authorization Server now defaults multipleIssuersAllowed to false and it cannot be easily re-enabled |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.2 | @DataLdapTest |
| deprecation | confirmed | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.2 | @NestedConfigurationProperty (doesn't work on records) |
| deprecation | confirmed | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.2 | TestcontainersLifecycleBeanPostProcessor does not work correctly with scoped beans |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.2 | build-image failures after docker desktop update with 'Illegal char <:> at index 5: npipe:////' |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.2 | When using Jetty, filters, listeners, and servlets are not initialized with the same thread context classloader |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.2 | DirtiesContext used with Webflux, a random port and multiple contexts causes multiple contexts to misbehave |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.2 | <init> (when using spring-boot-starter-activemq in a native image) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.2 | Document the types to which each spring.mvc.format and spring.webflux.format property applies |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.2 | Update Kotlin DSL examples that configure the environment of bootBuildImage to be additive |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.2 | ❤️ Contributors (Thank you to all the contributors who worked on this release:) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.2 | @acouvreur (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.2 | @anbusampath (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.2 | @eddumelendez (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.2 | @izeye (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.2 | @jxblum (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.2 | @mateusscheper (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.2 | @opcooc (, and) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.2 | @sdeleuze |

## `3.3.2` → `3.3.3`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | Extending DefaultErrorAttributes and overriding getErrorAttributes() gets called twice |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | When using WebFlux, server.error.include-binding-errors=ALWAYS no longer has an effect when the BindingResult exception is the cause of a ResponseStatusException |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | PropertiesLauncher does not respect classpath.idx when adding jars in BOOT-INF/lib to the classpath |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | spring-boot-testcontainers causes unwanted container initialization during AOT processing |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | ReactiveElasticsearchRepositoriesAutoConfiguration should back off when Reactor is not on the classpath |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | mvn spring-boot:build-image fails when 'classifier' is set to non-default value |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | Docker publishRegistry in Maven plugin configuration is validated when publish option is false |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | Using Gradle's new file permission API is implemented in a way that prevents removal of the old API |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | @ControllerEndpoint (and) |
| deprecation | confirmed | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | @RestControllerEndpoint (infrastructure remains undeprecated) |
| dependency_upgrade | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | Javadoc of slice test annotations should describe more accurately which components are considered |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | Document the need to explicitly reset mock servers when using mock server customizers directly |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | Document more clearly that username and password are not used when spring.data.redis.url is set |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | Pulsar configuration does not have default value for several entries in the metadata |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | management.otlp.metrics.export.aggregation-temporality does not have a default value in the metadata |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | management.newrelic.metrics.export.client-provider-type does not have a default value in the metadata |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | server.error.include-path does not have a default value in the metadata |
| mandatory_migration | confirmed | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | The effect upon Actuator of defining your own SecurityFilterChain is documented inconsistently |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | "Use Spring Data repositories" How-to incorrectly refers to Repository annotations |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | "Use Spring Data repositories" How-to incorrectly refers to Repository annotations |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | @Name (to customize a property name) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | Document that spring-boot:repackage should not be run from the command-line |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | ❤️ Contributors (Thank you to all the contributors who worked on this release:) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | @PiyalAhmed (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | @Rajin9601 (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | @cms04 (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | @dreis2211 (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | @eddumelendez (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | @hyunmin0317 (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | @ivamly (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | @jmewes (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | @jxblum (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | @lamtrinhdev (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | @ngocnhan-tran1996 (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | @quaff (, and) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.3 | @ritzykey |

## `3.3.3` → `3.3.4`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.4 | management.health.db.ignore-routing-datasources=true has no effect when an AbstractRoutingDataSource has been wrapped |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.4 | ZipkinHttpClientSender fails with "Failed to introspect Class" when spring-web is not on the classpath |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.4 | @RestartScope (can cause 'Recursive update' exceptions when used with container beans) |
| deprecation | confirmed | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.4 | PropertiesMigrationListener wrongly reports property as deprecated when has group |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.4 | Using an empty string MongoDB 'replica-set-name' property will result in ClusterType=REPLICA_SET |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.4 | Links to GraphQL in the reference guide redirect to the root instead of specific sections |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.4 | Document that configuration property binding to a Kotlin value class with a default is not supported |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.4 | Remove link to “Converting a Spring Boot JAR Application to a WAR” as the guide is no longer available |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.4 | ❤️ Contributors (Thank you to all the contributors who worked on this release:) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.4 | @Alchemik (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.4 | @arefbehboudi (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.4 | @einarpehrson (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.4 | @izeye (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.4 | @martinfrancois (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.4 | @mushroom528 (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.4 | @nosan (, and) |

## `3.3.4` → `3.3.5`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.5 | Running mvn spring-boot:run with classpaths that exceeds Windows' length limits leaves temporary files |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.5 | Report produced by ConditionReportApplicationContextFailureProcessor is always empty in a failed test |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.5 | DataSourceProperties#driverClassIsLoadable should not print a stacktrace to the error stream when it fails |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.5 | @ControllerEndpoint (and) |
| deprecation | confirmed | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.5 | @RestControllerEndpoint (infrastructure remains undeprecated) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.5 | ClassNotFoundException is thrown when loading protocol resolvers from ForkJoinPool task |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.5 | Duplicate meter binding when context contains multiple registries, none are primary, and one or more is a composite |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.5 | Document that the exact behavior of the maximum HTTP request header size property is server-specific |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.5 | @Primary (is recommended when defining your own ObjectMapper that replaces JacksonAutoConfiguration's) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.5 | @ConditionalOn ((Missing)Bean will infer the type to match) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.5 | Remove note about graceful shutdown with Tomcat requiring 9.0.33 or later as we now require 10.1.x |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.5 | ❤️ Contributors (Thank you to all the contributors who worked on this release:) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.5 | @IMWoo94 (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.5 | @arefbehboudi (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.5 | @izeye (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.5 | @jeonghyeon00 (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.5 | @ngocnhan-tran1996 (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.5 | @nosan (, and) |

## `3.3.5` → `3.3.6`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.6 | this issue comment (for more details.) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.6 | Spring Boot 3.3.x dependencies do not converge for Micrometer Tracing and OpenTelemetry |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.6 | Cannot package OCI image when 'docker.io/paketobuildpacks/new-relic' is provided as a buildpack |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.6 | SslOptions.isSpecified() only returns true if ciphers and enabled protocols are set |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.6 | mvn spring-boot:run fails on Windows with "Could Not Find or Load Main Class" when path contains non-ASCII characters |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.6 | build-info doesn't support seconds since the epoch from project.build.outputTimestamp |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.6 | NPE in OnClassCondition.resolveOutcomesThreaded following thread interruption because firstHalf is null |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.6 | @SpyBean (on the output of a FactoryBean is not reset) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.6 | Rework DataSource configuration examples to separate defining an additional DataSource and defining a DataSource of a different type |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.6 | ❤️ Contributors (Thank you to all the contributors who worked on this release:) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.6 | @ahoehma (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.6 | @izeye (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.6 | @ngocnhan-tran1996 (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.6 | @nosan (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.6 | @quaff (, and @wickdynex) |

## `3.3.6` → `3.3.7`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.7 | KafkaProperties fail to build SSL properties when the bundle name is an empty string |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.7 | With multiple ResourceHandlerRegistrationCustomizer beans in the context, only one of them is used |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.7 | Failure analysis for InvalidConfigurationPropertyValueException doesn't correctly handle fuzzy matching of environment variables |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.7 | Diagnostics are poor when property resolution throws a ConversionFailedException |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.7 | @SpringBootConfiguration (results in misleading error message) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.7 | Overriding log level with an environment variable does not work when using an environment prefix |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.7 | Methods to build producer / consumer properties from KafkaProperties are inconvienenent to use without an SSL bundle |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.7 | UnsupportedOperationException when starting a Maven shaded application on Java 21 with virtual threads enabled |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.7 | Document that server.ssl.cipher and server.ssl.enabled-protocols are not fallbacks used with SSL bundles |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.7 | <annotationProcessorPaths> (in Maven examples for configuring an annotation processor) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.7 | @AutoConfiguration (javadoc) |
| deprecation | confirmed | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.7 | @EnableMethodSecurity (instead of the deprecated) |
| mandatory_migration | confirmed | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.7 | @EnableGlobalMethodSecurity |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.7 | ❤️ Contributors (Thank you to all the contributors who worked on this release:) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.7 | @BenchmarkingBuffalo (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.7 | @kgb-financial-com (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.7 | @ngocnhan-tran1996 (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.7 | @nosan (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.7 | @quaff (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.7 | @scordio (, and) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.7 | @sobychacko |

## `3.3.7` → `3.3.8`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.8 | POSTGRESQL_USERNAME and POSTGRESQL_DATABASE are ignored when using the Bitnami PostgreSQL image with Docker Compose |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.8 | docker compose ps now fails due to unknown --orphans flag with 2.23 or earlier |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.8 | @ConfigurationProperties (annotation processor cannot generate description and defaultValue metadata for external types) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.8 | Document 'base64:' prefix support |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.8 | Update OpenTelemetry section in Supported Monitoring Systems to refer to OTLP instead |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.8 | ❤️ Contributors (Thank you to all the contributors who worked on this release:) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.8 | @arefbehboudi (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.8 | @dreis2211 (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.8 | @gavarava (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.8 | @hezean (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.8 | @izeye (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.8 | @jxblum (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.8 | @ngocnhan-tran1996 (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.8 | @quaff (, and) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.8 | @tmaciejewski |

## `3.3.8` → `3.3.9`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.9 | Reactive Jetty web server does not fail fast when configured to use a server name bundle which Jetty does not support |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.9 | When web server application context refresh fails, the original failure is lost if stopping or destroying the web server throws an exception |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.9 | Maven plugin does not consistently use ArgFile for classpath argument on Windows |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.9 | WebServer is not destroyed when ReactiveWebServerApplicationContext refresh fails |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.9 | Mustache templates return with ISO-8859-1 charset rather than UTF-8 in Content-Type response header |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.9 | Logback configuration that relies on inner-classes does not work in a native image |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.9 | IllegalStateException: Unable to register SSL bundle after 3.3.8 or 3.4.2 |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.9 | Document that auto-configuration classes should be identified using their binary names |
| mandatory_migration | confirmed | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.9 | Correct typo in MVC security when explaining when UserDetailsService auto-configuration will back off |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.9 | When using observability annotations, recommend that care is taken to avoid double instrumentation |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.9 | Source snippet in Developing Your First Spring Boot Application section uses the root package |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.9 | Correct the location of MyApplication.java in "Developing Your First Spring Boot Application" |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.9 | ❤️ Contributors (Thank you to all the contributors who worked on this release:) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.9 | @Ru311 (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.9 | @ashishkujoy (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.9 | @izeye (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.9 | @jearton (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.9 | @ngocnhan-tran1996 (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.9 | @nosan (, and) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.9 | @timotheeandres |

## `3.3.9` → `3.3.10`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.10 | When loading configuration from a Resource, Log4J2LoggingSystem may not close the InputStream |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.10 | DefaultJmsListenerContainerFactoryConfigurer#setObservationRegistry should not be public |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.10 | When the main class is not proxied, native testing that uses the application's main method does not work |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.10 | ConfigDataLocationResolvers and PropertySourceLoaders are loaded using a potentially different class loader |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.10 | Kafka message sending fails with 'class SslBundleSslEngineFactory could not be found' |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.10 | @DataJpaTest (on enclosing class) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.10 | Adapt Javadoc reference of JooqExceptionTranslator to use ExceptionTranslatorExecuteListener |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.10 | ❤️ Contributors (Thank you to all the contributors who worked on this release:) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.10 | @KmYgJn (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.10 | @bekoenig (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.10 | @bernie-schelberg-invicara (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.10 | @dmitrysulman (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.10 | @izeye (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.10 | @metters (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.10 | @ngocnhan-tran1996 (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.10 | @nosan (, and) |

## `3.3.10` → `3.3.11`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.11 | Spring Boot with native image container image build fails on podman due to directory permissions |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.11 | MessageSourceMessageInterpolator does not replace a parameter when the message matches its code |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.11 | IntegrationMbeanExporter is not eligible for getting processed by all BeanPostProcessors warnings are shown when using JMX |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.11 | @ConditionalOnClass (incorrectly) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.11 | Post-processing to apply custom JdbcConnectionDetails triggers an NPE in Hikari if the JDBC URL is for an unknown driver |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.11 | DataSourceBuilder triggers an NPE in Hikari when trying to build a DataSource with a JDBC URL for an unknown driver |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.11 | spring.datasource.hikari.data-source-class-name cannot be used as a driver class name is always required and Hikari does not accept both |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.11 | DataSourceTransactionManagerAutoConfiguration should run after DataSourceAutoConfiguration |
| dependency_upgrade | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.11 | @Component (a javadoc link) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.11 | Show the use of token properties in authorization server clients configuration example |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.11 | TaskExecution documentation should describe what happens when multiple Executor beans are present |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.11 | Clarify the use of multiple profile expressions with "spring.config.activate.on-profile" |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.11 | ❤️ Contributors (Thank you to all the contributors who worked on this release:) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.11 | @EvaristeGalois11 (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.11 | @MelleD (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.11 | @ali-jalaal (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.11 | @erichaagdev (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.11 | @florgust (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.11 | @izeye (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.11 | @jonatan-ivanov (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.11 | @nenros (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.11 | @nevenc (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.11 | @ngocnhan-tran1996 (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.11 | @nosan (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.11 | @quaff (, and) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.11 | @rainboyan |

## `3.3.11` → `3.3.12`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.12 | SpringApplication.setEnvironmentPrefix is ignored when reading SPRING_PROFILES_ACTIVE |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.12 | IllegalStateException when extracting using layers a module with no code of its own |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.12 | Custom default units declared on a field are ignored when binding properties in a native image |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.12 | Suggested values for spring.jpa.hibernate.ddl-auto are not aligned with Hibernate |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.12 | JerseyWebApplicationInitializer always gets loaded, setting a ServletContext initParameter |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.12 | @ConfigurationPropertiesBinding |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.12 | Update link to "Parameter Name Retention" section of Spring Framework's release notes |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.12 | ❤️ Contributors (Thank you to all the contributors who worked on this release:) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.12 | @ahrytsiuk (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.12 | @izeye (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.12 | @ngocnhan-tran1996 (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.12 | @nosan (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.12 | @quaff (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.12 | @thecooldrop (, and) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.12 | @yybmion |

## `3.3.12` → `3.3.13`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.13 | upgrades to Tomcat 10.1.42 (which has introduced limits for part count and header size in) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.13 | multipart/form-data (requests. These limits can be customized using) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.13 | server.tomcat.max-part-count (and) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.13 | server.tomcat.max-part-header-size (respectively.) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.13 | Executable JAR application class encounters performance issues when classpath URLs reference a host |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.13 | Loading from spring.factories may fail with a ClassNotFoundException when the TCCL changes between calls |
| mandatory_migration | confirmed | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.13 | Timestamps in Retrieving Audit Events examples do not match the accompanying text |
| mandatory_migration | confirmed | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.13 | Links to Testcontainers javadoc for many classes not in the core testcontainers module do not work |
| deprecation | confirmed | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.13 | Clarify the situation with support for Prometheus PushGateway and the deprecated simpleclient |
| mandatory_migration | confirmed | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.13 | Update javadoc of Configurer classes that apply sensible defaults to describe how they're typically used |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.13 | ❤️ Contributors (Thank you to all the contributors who worked on this release:) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.13 | @chanbinme (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.13 | @davidlj95 (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.13 | @ngocnhan-tran1996 (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.13 | @nicolasgarea (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.13 | @nosan (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.13 | @quaff (, and) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.3.13 | @wonyongg |

## `3.3.13` → `3.4.0`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| dependency_upgrade | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.4.0 | Add withDefaultRequestConfigCustomizer method to HttpComponentsClientHttpRequestFactoryBuilder |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.4.0 | Improve performance of ConfigurationPropertiesBinder by storing bind handlers on first access |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.4.0 | Log warning in HikariCheckpointRestoreLifecycle if pool suspension isn't configured |
| dependency_upgrade | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.4.0 | Remove spring-boot-starter-aop dependency from spring-boot-starter-data-jpa and spring-boot-starter-integration |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.4.0 | Classes are accidentally named "structure logging" instead of "structured logging" |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.4.0 | StructuredLoggingJsonProperties customizer should be a Class reference rather than a String |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.4.0 | Cannot package OCI image when 'docker.io/paketobuildpacks/new-relic' is provided as a buildpack |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.4.0 | Incorrect Type for 'management.endpoints.access.default' defined in additional-spring-configuration-metadata.json |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.4.0 | SslOptions.isSpecified() only returns true if ciphers and enabled protocols are set |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.4.0 | SslHealthIndicator throws NullPointerException when using SslBundle with SslStoreBundle.NONE |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.4.0 | JdkClientHttpRequestFactoryBuilder and JettyClientHttpRequestFactoryBuilder do not set Ciphers or Enabled Protocols |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.4.0 | mvn spring-boot:run fails on Windows with "Could Not Find or Load Main Class" when path contains non-ASCII characters |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.4.0 | @SpyBean (on the output of a FactoryBean is not reset) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.4.0 | Bean-based conditions do not consider factory beans correctly when determining if they are a candidate |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.4.0 | HttpHostConnectException is thrown when using buildpacks with Gradle or Maven on Windows |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.4.0 | build-info doesn't support seconds since the epoch from project.build.outputTimestamp |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.4.0 | NPE in OnClassCondition.resolveOutcomesThreaded following thread interruption because firstHalf is null |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.4.0 | Default WebSocketMessageBrokerConfigurer is always overriding custom channel executor |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.4.0 | ApplicationContextRunner has inconsistent behaviour with duplicate auto-configuration class names |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.4.0 | Rework DataSource configuration examples to separate defining an additional DataSource and defining a DataSource of a different type |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.4.0 | ❤️ Contributors (Thank you to all the contributors who worked on this release:) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.4.0 | @ahoehma (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.4.0 | @deki (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.4.0 | @izeye (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.4.0 | @ngocnhan-tran1996 (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.4.0 | @nosan (,) |
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.4.0 | @quaff (, and @wickdynex) |

