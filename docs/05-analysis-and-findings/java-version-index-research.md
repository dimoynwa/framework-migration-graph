# Java (JDK) Version Index — Feasibility Research

Status: **research only — nothing implemented.** No code, schema, or skill was changed to produce this document.
Date: 2026-11-06 · Author: research pass over HEAD `573565d` + four focused research briefs (codebase onboarding surface, migration-flow attach points, JDK knowledge sources, OpenRewrite automation coverage).

Question: we already migrate Spring Boot, Angular, and WildFly/JBoss services. Can we add a **Java version index**, so a hop like `Java 17 → 21` is plannable and executable the same way?

---

## 1. Answer in short

**Yes — and the graph layer is the cheap part.** The pipeline, populator, and the whole MCP tool/query layer are framework-parameterised: `framework` is a free string, there is no framework enum in any tool schema, and index DDL is label-scoped, so a tenth framework needs **zero DDL and zero Cypher changes**.

Three things are genuinely hard, and none of them is ingestion:

1. **Semantics.** A JDK hop is not shaped like a framework hop. `17 → 21` is four upstream release deltas (18, 19, 20, 21), the version people *name* (`21`) is not the version the graph can *parse* (`21.0.0`), the meaningful cadence is LTS-to-LTS not minor-line, and the answer is a runtime + toolchain + bytecode change, not an API change.
2. **A missing concept in the schema.** There is no relationship anywhere that says *"framework X version V runs on / requires platform R"*. Today "Boot 4 ⇒ Java 21" lives in hand-written skill prose — and that prose is already **wrong** (see §3.1).
3. **Applicability.** The Oracle's core loop is *scan entities → match `AFFECTS_*` → actionable task*. Most real JDK breakage has no source-code symbol to match (JVM flags, base images, bytecode level, TLS/trust, tzdata), and the scanning reference explicitly declares the JDK out of scope: *"the JDK (`java.*`) … has no node in the graph and can never match a rule"* ([migration_oracle/mcp/skills/framework-migration/scanning.md:316-319](../../migration_oracle/mcp/skills/framework-migration/scanning.md), repeated in [framework-migration-scanning-results.md](framework-migration-scanning-results.md)).

Recommendation (§7): **stage it** — (1) make Java a first-class *platform axis* (compatibility matrix + runtime gate driven from the graph instead of prose), (2) add `framework: "Java"` LTS hops as a real index with curated, entity-anchored rules, (3) add compound runs so a `Spring Boot 3.5 → 4.0` plan can *contain* the `Java 17 → 21` hop instead of mentioning it in a bullet.

---

## 2. "Upgrade Java 17 → 21" is four different migrations

Worth naming before modelling, because the graph currently has a home for only the first:

| Axis | Example | Matchable today? |
| --- | --- | --- |
| **Language / JDK API** | `new URL(String)` deprecated → `URI.create().toURL()`; `SortedSet.first()` → `getFirst()` (JEP 431); removed `java.lang.Compiler` | **Yes** — this is exactly `Class`/`Member` + `REPLACED_BY` + OpenRewrite |
| **Toolchain** | `maven.compiler.release`, `java.version` property, Gradle `toolchain.languageVersion`, Gradle ≥ 8.5, JaCoCo/ByteBuddy/AspectJ/Kotlin must support class-file 65 | Partially — `ApplicationProperty`/`Dependency` shapes fit, but nothing reads these keys from a repo (§4) |
| **Runtime / platform** | UTF-8-by-default (JEP 400), strong encapsulation (`--add-opens`), JVM flags removed/obsoleted, agent attach (JEP 451), generational ZGC | **No** — no entity kind, no scan channel |
| **Policy / data drift** | container base image, TLS/trust + `cacerts` per CPU, tzdata/CLDR changes | **No** — not source code at all |

Rough coverage split observed for a 17→21 hop (research brief on JDK sources, judgement-based): **~35 % source-detectable, ~55 % jar/flag/config/runtime, ~10 % data drift invisible to any static scan.** An index that only covers the first row will systematically under-report and burn agent credibility.

---

## 3. Where Java lives today

### 3.1 Three hand-maintained places (and one is wrong)

| Place | What it says | Evidence |
| --- | --- | --- |
| `migration_oracle/mcp/skills/framework-migration/version-map.md:19-55` | "Min Java" column per Boot release; *"3.x → 4.x Requires Java 21"*; a heuristic "check only when the minor changes" | hand-typed markdown shipped as a skill reference |
| `migration_oracle/mcp/skills/templates/plan.md:13` | `- [ ] Runtime gate: e.g. Java 17 for Boot 3 / Java 21 for Boot 4` | an unchecked box in a template; nothing verifies it |
| `migration_oracle/pipeline/seeds/lifecycle_alerts.py:26` | `"Spring Boot 4 drops Java 8/11 support — migrate to Java 17+ before upgrading."` | seed data that **nothing in the pipeline calls** (only tests import the seed functions) |

**The prose is already stale.** `version-map.md` records Boot 4.x min Java = 21. [Spring Boot's own system requirements](https://docs.spring.io/spring-boot/system-requirements.html) (checked 2026-11-06, 4.1.2 and 4.0.9) state: *"requires at least **Java 17** and is compatible with versions up to and including Java 27"*. A fact this load-bearing, hand-copied into a skill file, drifts. That is the argument for putting it in the graph with a `sourceUrl` and a fetch date.

There is also a **dormant precedent**: `scripts/seed_013_versions.py:19` writes `Version {framework:"Spring Boot"}.minJava = 21`, and `:81-97` seeds Spring Cloud `compatibleBoot` / `train` / `importMode`. **Nothing reads any of those properties** and they are not in [graph-schema.md](../01-foundation/graph-schema.md). Someone already tried the matrix idea in spec 013 and it never got a consumer.

### 3.2 Java facts *are* already in the graph — attached to the wrong thing

The pipeline already extracts JDK rules while ingesting WildFly, because WildFly release notes mention them (verified in `runs/json/`):

```
wildfly-34.0.0-to-35.0.0  "Minimum Java SE version raised to 17; Java 11 no longer supported"   entities: []
wildfly-39.0.0-to-40.0.0  "JVM minimum version enforced at JDK 17"          severity critical    entities: []
wildfly-35.0.0-to-36.0.0  "-Djava.security.manager=allow no longer set by default"              entities: []
wildfly-34.0.0-to-35.0.0  "Security Manager support dropped for Java SE 24 and later"           entities: []
```

Two problems visible in one line each: the same fact is duplicated per WildFly hop (it is a *JDK* fact and a *platform-support matrix* fact, not a WildFly changelog fact), and `entities: []` means it cannot be matched.

### 3.3 What happens to such a rule at plan time

`analyze_upgrade_path` computes applicability with `affected_count = 0 → 'informational'` *before* the high-severity safety net ([mcp/graph/queries/upgrade.py:228-235](../../migration_oracle/mcp/graph/queries/upgrade.py)), and the plan render table maps `informational` → **IGNORED (not relevant to current project)** ([plan.md:251](../../migration_oracle/mcp/skills/framework-migration/plan.md)).

Confirmed against a real run: in `probe-results/wallet-customer-levels-skill-flow-2026-07-31/ps-migration/spring-boot-3.5.0-to-4.0.0/`, Java appears **once**, as prose:

```
plan.md:13  - Java 21 required for Spring Boot 4 target.
```

`tasks.md` has no Java/JDK task; `verification.md` has no runtime-gate level. A critical platform requirement, correctly known to the system, produced zero executable work and zero verification.

### 3.4 Nothing in the discovery layer knows a service's Java version

- `migration_planner/scanner/` (spec 026) registers **one** manifest reader — npm ([builtin.py](../../migration_planner/scanner/builtin.py)). `pom.xml` / `build.gradle` are *classified at discovery* but unread, so scanning a Spring Boot service yields `framework: None, dependencies: [], config: []`. Verified empirically against `tests/fixtures/scanner/polyglot`.
- The keys **are already specified**, just not built: `cfg:pom.xml#properties.java.version` ([specs/026-service-scanner/spec6.md:41](../../specs/026-service-scanner/spec6.md)) and `cfg:build.gradle#java.toolchain.languageVersion` / `#sourceCompatibility` (`spec6.md:57-58`).
- The legacy harness scanner (`framework_scanner.py`) reads pom/gradle **dependencies** and Java imports, but never `java.version` / `maven.compiler.*`, and deliberately filters `java.*` imports out as noise.
- FindIT provides only `name` + `codeRepoLink`; the GitLab resolver parses Spring Boot / Angular versions only. **No JDK field, no base image, no runtime info** in the Paysafe inventory.

So "which of our services are on Java 8 / 11 / 17?" is currently unanswerable *by the Oracle's code* — and that query, not the rule catalogue, is what makes a Java index worth building.

> **Correction, verified later the same day (see §10).** It *is* answerable today, just not through the Oracle: **`application_java_version` in `gradle.properties` is a de-facto Paysafe convention.** Across the ~62 `paysafe-*` repos checked out locally, **65 files declare it: 57 → 21, 5 → 17, 3 → 11**, and `build.gradle` feeds it straight into `java { toolchain { languageVersion = JavaLanguageVersion.of(application_java_version) } }`. One GitLab raw-file read per repo (already implemented at `migration_oracle/paysafe/gitlab.py:191-212`) yields the whole census. The blocker is not the data, it is that `paysafe/findit.py:103-117` (the fleet list) is a `NotImplementedError` stub.

---

## 4. Cost map: what a `framework: "Java"` entry actually touches

Verified by reading each site. Details in the two codebase research briefs; the short version:

### Needs no change (already generic)
CLI `export-extract-populate-framework --framework <key>`, hop machinery, triage / per-change research / entity-extraction stages, the populator, `rule_id_for()` (`pipeline://{framework}/{version}/{title}` namespaces naturally), `Version (framework, version)` uniqueness, [graph/indexes.py](../../migration_oracle/graph/indexes.py) DDL, and **every MCP tool and Cypher query** (`framework` is a parameter; `mcp-surface.json` has no framework enum).

### Small, mechanical
| Touch point | Where |
| --- | --- |
| Extractor registry + display name | [extractors/__init__.py:24-49](../../migration_oracle/pipeline/extractors/__init__.py), duplicated in `extractors/_names.py` and `streamlit_app/_constants.py` (three copies), plus `tests/extractors/test_registry.py` which enumerates keys literally |
| Extractor class | one `BaseExtractor` subclass; static version tables already have precedent (`eap.py:EAP_VERSION_TABLE`, `jakarta_ee.py:JAKARTA_EE_SPEC_VERSIONS`) |
| Canonicalisation profile | unknown frameworks fall back to `DEFAULT_PROFILE` (maven no-op) — works, degrades `verified: "unchecked"` ([profiles.py:69-88](../../migration_oracle/pipeline/canonical/profiles.py)) |
| Signal feature vocabulary | `features_for()` returns `()` for unknown frameworks — **silent degradation**, no warning ([features.py:241-256](../../migration_oracle/pipeline/signals/features.py)) |
| Skill version map | needs a JDK section; `plan.md` Step 3 currently treats Java only as a Boot *gate* |
| Docs / run scripts | supported-framework tables in `docs/02-extraction-pipeline/`, `scripts/run_raw_extractions.sh` |

### Real blockers
1. **Version grammar.** `sortable_version()` requires ≥ `major.minor`: `"21"` and `"11"` raise `ValueError`; `"1.8.0_452"`, `"17.0.12+7"`, `"25-ea+32"` all raise. Verified by running it. `"1.8"` → 1008000 but `"8"` → 8000000, so the two JDK spellings **sort inconsistently**. Mitigation: normalise to `X.Y.Z` at the extractor boundary (what EAP/Jakarta already do) and canonicalise user input `"21"` → `21.0.0` in the framework-alias layer.
2. **Hop granularity.** `HOP_GRANULARITIES = ("patch", "minor")` ([extractors/parsing.py:227](../../migration_oracle/pipeline/extractors/parsing.py)). JDK wants **major/LTS**: `17.0.x → 21.0.0` is one hop; `21.0.4 → 21.0.5` is a security update, not a migration. A third granularity value ("major"/"lts") is needed, or an LTS-only version list.
3. **Ecosystem is `npm | maven`.** `ecosystem: Literal["npm", "maven"]` ([models/entities.py:93](../../migration_oracle/models/entities.py)); entity keys are `maven:` / `npm:` / `cfg:` / `syntax:` / `diag:` ([migration_keys/keys.py](../../migration_keys/keys.py)). `maven:java.lang.SecurityManager` is wrong and it breaks matching (below).
4. **Applicability matching cannot express JDK facts.** `normalize_entities()` buckets a scanned string by shape: uppercase-last-segment → FQCN, colon → `groupId:artifactId`, all-lowercase-dotted → property ([mcp/tools/upgrade.py:91-130](../../migration_oracle/mcp/tools/upgrade.py)). So a *JVM flag* (`--illegal-access=deny`, `-XX:+UseZGC`), a *module* (`java.se`, `jdk.unsupported`), a *tool version* (Gradle 8.5), a *base image* (`eclipse-temurin:21`) and a *class-file target* (`65`) all collapse into the "bare lowercase → artifact ID" bucket and match nothing. The `AFFECTS_*` CASE in the Cypher covers only `Class`, `ApplicationProperty`, `Dependency` — `TemplateSyntax` and `DiagnosticCode` already fall into `ELSE false`; a JDK would land in the same hole.
5. **One framework per run.** `framework` is a scalar in the tool signature, in `Version`, in `ps-migration/{framework}-{from}-to-{to}/` (which *is* the state identity), in the plan header, and in the scanner profile (`choose_framework` picks a single winner). `MigrationStep-[:REQUIRES]->MigrationStep` is scoped to a single `ruleId` ([populator.py:421-432](../../migration_oracle/pipeline/populator.py)), so a Boot task cannot depend on a Java task. Spring Cloud co-migration — the closest existing analogue — is handled **entirely as prose**. `docs/05-analysis-and-findings/issues-round-2.md` ISSUE-024 recorded "no Boot↔Cloud compatibility mapping, unenforced" and was closed in spec 013 **by adding a prose Spring Cloud section to `version-map.md`** — i.e. the same class of gap was previously fixed with more markdown.
6. **`check_version_availability` is Spring-Boot-only.** `_FRAMEWORK_ALIASES = {"springboot": …}` and `_MAVEN_COORDS = {"spring-boot": …}` ([mcp/tools/upgrade.py:61-67](../../migration_oracle/mcp/tools/upgrade.py)); anything else returns `unsupported_framework`. A JDK needs a different authority (Adoptium / OpenJDK GA calendar), not Maven Central.
7. **Name is identity.** `Version (framework, version)` uniqueness + `ruleId = pipeline://{display}/…` mean the display name ("Java"? "JDK"? "OpenJDK"?) must be chosen before the first populate; renaming later requires a graph migration.

### New entity kinds a real JDK index needs
`JvmOption` (flags, with added/removed/obsoleted semantics), `Distribution` / base image, `BytecodeTarget` (class-file major), and a `SupportsRuntime` edge `(Version)-[:SUPPORTS_RUNTIME {min,max,verified,sourceUrl}]->(Version)`. Minimum-effort alternative: keep five labels and encode these as `ApplicationProperty` with `cfg:Dockerfile#…` / `cfg:build.gradle#…` keys plus a curated `Class` watch-list — cheaper, but every consumer has to know the convention.

---

## 5. Where the change information comes from (the real blocker — resolved)

This section is the answer to the objection that decides whether the index gets built. Short version: **for a JDK hop the change information is *better* sourced than what we ingest for Spring Boot today** — but not from the place everyone looks (Oracle's release-notes pages). It is anonymous, structured, REST-queryable Jira data, and Oracle's pages are only a rendering of it.

### 5.1 Baseline for comparison

Our current Spring Boot raw feed is a scrape of GitHub issues per release. Look at a real artifact (`runs/raw/spring-boot-3.0.0-to-3.0.1-changes.md`): nearly every row is `| behavioral | inferred | …/issues/33615 | Title: Fix typo in LocalDevToolsAutoConfiguration logging …`. That is *noise* that only becomes useful after triage + LLM research. A JDK hop can be ingested from a feed where each row is **written specifically to describe an upgrade-impacting change**, is **component-tagged**, and **71 % of rows carry a machine-readable breaking-ness classification**.

### 5.2 Primary feed — JBS release notes (anonymous REST, no auth)

[bugs.openjdk.org](https://bugs.openjdk.org) is a public Jira (Server 11.3.12) whose `/rest/api/2/*` endpoints answer anonymous queries. The trap: **there is no `Release Note` issue type** (`issuetype="Release Note"` → HTTP 400 *"The value 'Release Note' does not exist"*). Release notes are **Sub-tasks whose summary begins `Release Note:`**:

```
GET https://bugs.openjdk.org/rest/api/2/search?jql=
    project=JDK AND issuetype=Sub-task AND summary ~ "Release Note:"
    AND fixVersion in (18,19,20,21)
        &fields=summary,description,resolution,fixVersions,components,parent
        &maxResults=100&startAt=<n>
```

| Hop slice | Release notes | Verified |
| --- | --- | --- |
| JDK 18 / 19 / 20 / 21 | 75 / 58 / 50 / 87 | **270** total (queried directly) |
| description present | 270 / 270 | mean ≈ 556 chars, ~150 k chars of prose for the hop |
| component-tagged | 270 / 270 | core-libs 114, security-libs 64, hotspot 40, tools 36 … ; 44 subcomponents |
| usable after hygiene | ~264 | drop 5 `Withdrawn` + 1 `Duplicate`; attribute multi-`fixVersion` issues to the earliest release |

Two operational traps: the WAF **403s a spoofed browser User-Agent but 200s an honest one** (`curl/8.7.1` → 200, Chrome string → 403 — hit this personally), and `search?filterId=<id>` **silently ignores the filter** for anonymous callers (returns all 385,961 issues) — resolve `/rest/api/2/filter/<id>` to its `jql` and re-issue it.

Record shape is ideal for the schema: `summary` = rule title, `description` = rule statement + often the workaround, `components`/`Subcomponent` = the same `core-libs/java.lang`-style area tag Oracle prints, `fixVersions` → `Version`, and `sourceUrl` = the stable `browse/JDK-XXXXXXX` permalink.

### 5.3 Severity comes from CSRs, not from headings

The CSR (Compatibility Specification Review) issue type carries the field we have no equivalent for anywhere else, confirmed via `/rest/api/2/field`:

| Jira field | id | values → our use |
| --- | --- | --- |
| **Compatibility Kind** | `customfield_11600` | `source` / `binary` / `behavioral` → `BreakingScope` kind + whether a compile break or a runtime surprise |
| **Compatibility Risk** | `customfield_11300` | `minimal` / `low` / `medium` → `severity` |
| Compatibility Risk Description | `customfield_11301` | free text, i.e. pre-written `MigrationRule.reason` |
| **Interface Kind** | `customfield_11601` | `Java API` / `System or security property` / `command line option` / `Class file construct` / `wire format` → **which entity label to anchor to** |

Join path (proved): release-note sub-task → `parent` (270/270 have one) → parent's `issuelinks` of type *CSR* (186/265 = **70 %**) → the fields above. Net: **191 of 270 hop notes (71 %) inherit real severity**; the residual 30 % falls back to section/title heuristics.

Over the hop, approved CSRs number 634-667 (per-release 160/178/134/195) but the actionable funnel is small and human-reviewable:

| Filter (18-21, approved) | count |
| --- | --- |
| Compatibility Risk = **Medium** | **22** |
| Compatibility Kind contains **binary** | ~34 |
| Compatibility Kind contains **source** | ~130 |

Those 22 Medium-risk items *are* the seed rule set for 17→21, and reading them is the argument for the whole project: `UTF-8 by Default` (JDK-8260266), `Sequenced Collections` (8266572), `Support for GB18030-2022` (8301559), `JNDI LDAP/RMI object-factory filters` (8291556), `com.sun.jndi.ldap.object.trustSerialData` default (8290369), `Degrade Thread.stop` (8293843), `URL.openConnection() syntax checks moved earlier` (8294592), `Obsoleted parallel-class-loading workaround` flag `-XX:+EnableWaitForParallelLoad` (8304056/8295848), `DateTimeFormatter` pattern-symbol `F` fix (8282377), `ProcessBuilder` quoted args on Windows (8282989), HTTP DIGEST MD5 disabled (8282649).

**Never derive severity from Oracle's section names**: the JDK 21 change that raises default TLS DH key size from 1024→2048 bits (JDK-8301700, a server-to-server handshake breaker) sits under *"Other Notes"*.

### 5.4 Skeleton: JEPs, with numbers that deflate the hype

| Filter | count |
| --- | --- |
| JEPs delivered in 18/19/20/21 (`issuetype=JEP`) | **38** (9/7/7/15) — all `Type=Feature`; there are no Research/Spark rows in a release |
| minus `jep-superseded` label (repeated previews: Pattern Matching 4×, FFM 3×) | **22** (queried directly) |
| pre-deduplicated by upstream on the curated hop page [`openjdk.org/projects/jdk/21/jeps-since-jdk-17`](https://openjdk.org/projects/jdk/21/jeps-since-jdk-17) | **22**, bucketed *Additions 13 / Preview & Incubating 7 / Deprecations 2* (fetched; 21→25 and 17→11 pages also exist) |
| plausibly relevant to a Spring Boot / WildFly server | ~12 |
| genuinely actionable | **6** — JEP 400 (UTF-8 default), 421 (finalization), 416 (core reflection via Method Handles), 418 (Internet-Address Resolution SPI), 451 (dynamic agent-attach warning → your APM javaagent), 431 (Sequenced Collections default methods) |

So JEPs are ~4 % of the corpus: the hop *skeleton*, never the payload. `openjdk.org/jeps/0` is parseable static XHTML (semantics in `title` attributes), but there is **no per-release endpoint** — `?release=21` returns a byte-identical page (filter is client JS) and `/jeps/21` 404s. Use the curated hop page or JBS.

### 5.5 A hop must fan out — the single most important ingestion rule

`17 → 21` spans four release-note sets. **Fetching only release 21 sees 87 of 270 notes (32 %)** and silently drops:

1. **JEP 400 UTF-8 by default** (release 18, plus three follow-on notes 8276137 / 8277357 / 8275343) — the biggest silent breaker of the hop; no compile error, no startup error, and JDK 19/20 pages contain zero mentions of it.
2. `-Djava.security.manager` default → `disallow` (18) and the whole `Subject.doAs` → `Subject.current/callAs` arc (18→20) that WildFly security config rides on.
3. The networking cluster: `java.net.URL` constructors deprecated (20), malformed-URL now throwing earlier (20), `InetAddress` rejecting ambiguous IPv4 literals (19), JEP 418 SPI (18) — every `URL`-based resource load and JDBC URL in a Boot app.
4. The TLS/crypto cluster — **64 of 270 notes are `security-libs`**, the densest breakage group and the one the 21 page covers least (3DES out of defaults in 19, DTLS 1.0 + `TLS_ECDH:*` disabled in 20, `SSLSocketImpl` finalizer removal in 19, SHA-1-signed JARs + JKS→PKCS12 cacerts in 18).
5. Threading/reflection/JMX/JNDI: TCCL becoming an inheritable thread-local (19, hits WildFly classloader-leak detection hard), `ForkJoinPool`/`ThreadPoolExecutor` no longer calling `Thread::start` (19, breaks agents/tests), remote JMX getting an `ObjectInputFilter` by default (20), JNDI factory filters (20).

Cheap entity seeds: of the 270 notes, 134 contain a qualified API name, 104 mention a `jdk.*`/`sun.*`/`java.*` system property, 51 mention a JVM flag → ~82 % yield at least one deterministic anchor without an LLM, which is exactly what §4's applicability hole needs.

### 5.6 Oracle's pages: cross-check only, and legally off the automated path

`https://www.oracle.com/java/technologies/javase/{18,19,20,21}-relnote-issues.html` (note: the commonly-cited URL *without* `/javase/` 404s) has for JDK 21 exactly **11 Removed + 4 Deprecated** records — i.e. Oracle's own page is ~3× less complete than the JBS feed for the hop. `robots.txt` allows these paths (even for AI crawlers), **but the site terms forbid "any robot, spider, scraper or other automated means … without Oracle's express written permission"**, and forbid redistribution of the Materials. It is unnecessary anyway: 15/15 of Oracle's JDK-21 *Removed* + *Known* records join to a JBS sub-task by title. Keep Oracle URLs in `sourceUrl` for humans; ingest from JBS. (CPU-level need? `…/javase/21all-relnotes.html` consolidates all 21.x notes; the licence-clean alternative is the JBS dump at [`builds.shipilev.net/backports-monitor/release-notes-21.txt`](https://builds.shipilev.net/backports-monitor/), 261 releases, MIT.)

### 5.7 The novel feeds: runtime policy, generated deterministically, zero overlap with OpenRewrite

These produce *rule instances* with no LLM and no prose parsing, and they cover the class of breakage that has no changelog at all. Both were run/verified here:

**(a) `java.security` diff between the two JDKs a service actually runs.** Fetch per tag from the OpenJDK repo (`src/java.base/share/conf/security/java.security`; tags `jdk-17-ga` … `jdk-25-ga` all resolve; `jdk-21+35` ≡ `jdk-21-ga`). Normalise `security.provider.tbd.*` placeholders, join `\`-continuations, token-diff. My own 17→21 diff yields exactly **6 rules**: `jdk.tls.disabledAlgorithms` +`DTLSv1.0`, +`ECDH`; new key `http.auth.digest.disabledAlgorithms=MD5, SHA-1`; `jdk.certpath.disabledAlgorithms` +`SHA1 usage SignedJAR & denyAfter 2019-01-01`; `jdk.jar.disabledAlgorithms` +`SHA1 denyAfter 2019-01-01`; `jdk.security.legacyAlgorithms` +`DES, DESede, MD5, RC2, ARCFOUR`; `jdk.tls.keyLimits` +`ChaCha20-Poly1305 KeyUpdate 2^37`. Grep of OpenRewrite's `recipes.csv` for `disabledAlgorithms|DTLS|ECDH|truststore` → **0 hits**. Diff the *shipped* `$JAVA_HOME/conf/security/java.security` of source and target JDK (patch releases back-port policy: Corretto 21.0.10 already carries 21→25-era TLS restrictions the GA tag lacks).

**(b) JVM flag lifecycle, two agreeing sources.** Upstream table `src/hotspot/share/runtime/arguments.cpp::special_jvm_flags[]` = `{name, deprecated_in, obsolete_in, expired_in}` — diff 17-ga→21-ga. Independently: run `java -XX:+PrintFlagsFinal -version` (**on stderr**) on both JDKs, set-diff, then validate each candidate with `java -XX:+<Flag> -version`. Measured 17→21: **18 flags hard-fail** (`Unrecognized VM option`) = the service **will not boot** (`UseBiasedLocking`, `UseHeavyMonitors`, `G1RSetRegionEntries`, `AliasLevel`, …) and **9 are silently swallowed** with `Ignoring option X; support was removed in 21.0` = boots with different behaviour (`UseSharedSpaces` 19.0, `G1UseAdaptiveConcRefinement` 20.0, `MetaspaceReclaimPolicy` 21.0 — the warning text itself names the removal release). Caveat: a service carrying `-XX:+IgnoreUnrecognizedVMOptions` will not fail on a removed flag, so the detector must read the service's JVM args, not rely on startup failure. No vendor publishes a machine-readable version of this table.

**(c) Per-service detectors:** `jdeps -jdkinternals` (also prints a *"JDK Internal API → Suggested Replacement"* table that is free `MigrationStep.instruction` text and is **not in the man page** — pin the parser to captured output; `-dotoutput` gives graph-shaped output), `jdeprscan --for-removal`, and the bonus `jdeprscan --release N -l` list diff (**51 newly deprecated, 26 gone** between 17 and 21; watch for `forRemoval` escalations rather than line diffs). Class-file majors from primary sources (JVMS 21 Table 4.1-A: 8=52, 17=61, 21=65, 25=69; rule `major = 44 + N`; or enumerate `java.lang.reflect.ClassFileFormatVersion`), computed over `mvn dependency:build-classpath` / Gradle `runtimeClasspath` by reading bytes 6-7 of each jar's classes (skip `META-INF/versions/**` for MR-jars).

**Do not trust Oracle tool documentation for output formats** — the JDK 21 `jdeprscan` man page still says `--release 6|7|8|9` and shows a stale output shape, and legacy `docs.oracle.com/javase/8|9/…` URLs **soft-404 to the JDK 27 home page with HTTP 200**, so status codes are meaningless there.

### 5.8 The support matrix as data (which is not a changelog problem at all)

| Need | Feed | Status |
| --- | --- | --- |
| Framework ↔ Java, as **JSON fields** | [`endoflife.date/api/spring-boot.json`](https://endoflife.date/api/spring-boot.json) → `supportedJavaVersions`: `"4.0": "17 - 25"`, `"3.4": "17 - 24"`, `"2.7": "8 - 21"`; also `spring-framework.json`, `tomcat.json` (`minJavaVersion`), `gradle.json` (`runningJavaVersions`/`testedJavaVersions`/`testedKotlinVersions`) | **verified 200, no auth, CORS `*`** — cheapest matrix feed found; cycle-granular, third-party, check its data licence before redistribution |
| Framework ↔ Java, vendor-authored + **patch-pinned** | per-tag `system-requirements.adoc` in the Boot repo: v2.7.0 *"Java 8 … up to Java 18"*, v3.2.0 *"17 … 21"*, v3.4.0 *"17 … 23"*, v4.0.0 *"17 … 25"* — one regex works across generations | verified per tag. Path moved 3× (`documentation/…` ≥4.0.0, `spring-boot-project/…antora…/pages/` 3.3-3.5, `…asciidoc/getting-started/` ≤3.2) — which is exactly why a hand-copied table rots |
| WildFly ↔ Java | per-tag `pom.xml`: `required.java.build.version=[17,)`, `required.java.deploy.version=[17,18)`, `recommended.java.version=25`, `recommended.java.version.legacy=21`; CI matrix `.github/workflows/jdk-jre-build.yml` (`java: ['17','21']`, `temurin`) | verified at `41.0.0.Final`; not present on tags ≤ ~30 |
| Dependency floors per Boot release | `spring-boot-dependencies-<v>.pom` diff: 3.3.0→3.4.0 = **113 changed properties** (`byte-buddy 1.14.16→1.15.10`, `mockito 5.11.0→5.14.2`); 3.5.0→4.0.0 = 116 + 252 new managed coords (Jackson 2/3 split) | verified. BOM contains **no** `java.version` property → floors only, never the baseline. Also: "removed from BOM" is its own change class |
| JDK lifecycle / LTS / EOL | `endoflife.date/api/oracle-jdk.json` (28 cycles; **17 EOL 2026-09-30 — already past**, 21 → 2028-09-30, 25 → 2030-09-30) + per-vendor slugs (`eclipse-temurin`, `amazon-corretto`, `redhat-build-of-openjdk`). `api/java.json` is a 404 — slugs are per-vendor | verified |
| "is 21.0.x GA / latest patch" (replaces the Maven-Central-only `check_version_availability`) | `api.adoptium.net/v3/assets/feature_releases/21/ga?…&sort_order=DESC` → `jdk-21.0.13+9, 2026-10-22` | verified. The declared exact-version endpoint 404s — compare `release_name`s. Never GET `/v3/binary/latest/…`, it streams the whole JDK (~207 MB, measured) |
| Toolchain ceilings | Gradle per-version docs table; JaCoCo per-tag `changes.html` ("officially supports Java N" vs "experimental"); AspectJ **release name** = "supporting Java 27"; ByteBuddy per-tag `ClassFileVersion.java`; Mockito per-tag release body | all verified per tag |
| Maven core, Kotlin `jvmTarget`, Lombok, Scala | **prose only** | keep as curated editorial rows |
| Runtime JDK of a deployed service | anonymous registry manifest + config blob: **`org.opencontainers.image.version` on Temurin images is the *Ubuntu* version (22.04), not the JDK**; the JDK is `ENV JAVA_VERSION=jdk-21.0.9+10` + an OCI *index* annotation, with a `.source` git SHA for provenance | verified; pin on digest, not tag |
| **JBoss EAP ↔ JDK** | `docs.redhat.com` → **403 on every path** (incl. `api/v1/documentation/*`, UA-proof); `access.redhat.com` errata → SSO; the one anonymous 200 is the lifecycle page (dates only) | **hard blocker** — needs an entitled account or human capture with fetch date |

Still true: **do not model the matrix as `MigrationRule`s.** `Spring Boot 4.0 supports Java 17-25` has no steps and no affected symbol; it is an edge with `sourceUrl` + `fetchedAt`, because these pages drift under you (Boot's own max-Java sentence moves *within* a patch line: 4.0.0 says "up to 25", the live 4.0.9 page says "up to 27").

### 5.9 Internal channels — the half with no public feed

Roughly a third of real JDK-upgrade breakage has no public feed at all. What we already own:

| Channel | State | What it sources |
| --- | --- | --- |
| **Fleet Java census** | **works today** — `application_java_version` in `gradle.properties` (65 files locally: 57×21, 5×17, 3×11) via `paysafe/gitlab.py:191-212` raw-file-at-ref | the "which services are on 11/17/21" query; blocked only by the `findit.py:103-117` stub fleet list |
| **Past runs** | `runs/json` 24 files / 715 rules; `artifacts/research` **2,857 dossiers**; 105 mention JDK-adjacent topics; **openjdk.org appears exactly once in 6,379 cited sources** | JDK rules *already extracted*, attached to WildFly/Boot hops (JVM flags in `standalone.sh`, `-secmgr` `SocketPermission`, jOOQ-requires-Java-21, default OCI `…-java-tiny` base image, Elytron keystore/TLS) → **project and de-duplicate, don't re-scrape** |
| **Community insights** | full write/dedup/vote/verify path + 59 real curated insights on disk; **but** no `entityClassification` → unanchored ones become `informational` → IGNORED | the human JDK-gotcha channel |
| **Git history** | ~57 services already at `application_java_version = 21` | the largest untapped 17→21 corpus we own: those commits are ground-truth "what actually had to change" |
| **PVG (vulnerability graph)** | exists, models resolved `runtimeClasspath` per service per commit; zero bytecode facts; zero references from this repo | substrate for "transitive jar compiled at Java 8" |
| **Helm chart** (`paysafe-microservice-chart`) | the only deploy-visible source: JVM args/`-Xlog`, GC toggles, AppDynamics javaagent mount, **and `/usr/share/zoneinfo` + `/etc/localtime` mounts** (the tzdata channel) | per-service JVM flags — currently read by nothing |
| Internal Jira | no client (WildFly's is Red-Hat-hosted, single-issue GET, no JQL — and note it sends the `GITHUB_TOKEN` bearer to `redhat.atlassian.net`, `extractors/base.py:186-194` + `251-269`); the research agent's SSRF guard (`research/tools.py:300-344`) refuses private ranges **by design**, so internal systems must be a *pipeline extractor*, never a research tool | `jiraKeys` already reserved in the schema (`graph-schema.md:144` says "Paysafe Jira keys"; 0 readers today, every value is a vendor key) |

**Biggest structural hole:** there is no "what actually broke" loop. `execute.md:237-239` states `submit_migration_insight` is *"user-initiated only … never auto-submits"*, and the Levels 0-5 verification ladder dies as markdown in `verification.md`. `ignored-rules.md` is a *rejection* ledger, not a breakage ledger. Any Java index will be wrong in ways only production can teach us, so an auto-captured run-outcome record is a prerequisite, not a nice-to-have.

### 5.10 Licensing of the knowledge itself

| Source | Licence | Consequence |
| --- | --- | --- |
| JBS issues / openjdk.org / OpenJDK repo files | open-community (GPLv2+CE code, CC-ish docs) | ingest + transform internally, fine |
| Oracle.com release-note prose | site terms forbid scrapers and redistribution | cross-check only (§5.6) |
| `rewrite-migrate-java` recipe YAML | **Moderne Source Available License**, *not* Apache-2.0 (verified: `LICENSE/moderne-source-available-license.md`, POM `<license>`, per-file headers). Internal use/derivative works allowed; **may not be offered to third parties as a service** | keep recipe nodes as **pointers** (name+artifact+version+`license='MSAL'`) rather than copying descriptions |
| OpenRewrite *docs/guides* prose | **Apache-2.0** (`openrewrite/rewrite-docs`, default branch `master`) — includes the Spring 3 and Jakarta EE 10 guides | safe for `MigrationStep.instruction` text |
| endoflife.date | data licence unverified | check before republishing in Paysafe artifacts |

**Coverage honesty.** For a code+build+runtime index: ~70-80 % of the *rule instances* for a hop can be produced from deterministic artifacts (recipe corpus + BOM/vendor matrices + the detector trio). What stays prose-only is the *why* (JEP rationale, severity judgement), the known-limitation text, ecosystem churn OpenRewrite excludes, and operational behaviour (GC tuning, tzdata/CLDR, vendor/CPU choice). Rough split for 17→21: **~35 % source-detectable, ~55 % jar/flag/config/runtime, ~10 % invisible data drift** — so the index must ship with a verification ladder, not just a rule list.

### 5.11 Dead ends (verified, don't chase)

`doc/unsupported-modules`, `jcake`, `jetp` (a JetBrains *plugin*, not an analyzer), animal-sniffer `java18-signature` (**means Java 1.8**; no official Java 9+ signatures exist), IBM `modernizer-core` (404), `codegenomeproject.org/api/recipes` (404 — the `RSC: 1` flight header is the only structured route), `cacerts` is **not** in the openjdk/jdk repo so there is no upstream truststore diff (and vendor variance is huge: GraalVM 17/21 = 98 certs each, Corretto 19 = 215), GitHub code-search requires auth, and `wildfly.org/news/…` 404s consistently even though the sitemap lists those URLs.


---

## 6. Automation: `AUTOMATED_BY` can be populated today, with caveats

**Read this first — three verified facts that change how we wire it:**

1. **The licence is not Apache-2.0.** `rewrite-migrate-java` ships under the **Moderne Source Available License** (verified: `LICENSE/moderne-source-available-license.md`, the released POM's `<license>`, and per-file headers). Internal ingestion and derivative works are permitted; offering it to third parties as a service is not. The *docs/guides* repo (`openrewrite/rewrite-docs`, branch `master`) is Apache-2.0 — so prefer the prose for instruction text and keep recipes as pointers.
2. **The corpus differs by channel — pin it.** `UpgradeToJava21.recipeList` is **18 entries on `main`** but **19 in the released 3.42.1 jar** (extra `RemoveIllegalSemicolons`); Maven Central's `maven-metadata.xml` says `3.42.1` (lastUpdated 2026-08-19) while GitHub released `v3.53.0` on 2026-11-06 and the recipe site documents 3.53.0, which **does not resolve from Central**. So `AUTOMATED_BY` edges must carry `recipeVersion`, and the spine should be the **jar at a pinned version** (`META-INF/rewrite/*.yml` + `recipes.csv`, 577 rows, one HTTP GET) rather than `main`.
3. **Scale for one hop:** `UpgradeToJava21` = 445 transitive recipes vs `UpgradeToJava17` = 399 ⇒ **~46 net steps for 17→21**; the codegenome catalogue (`RSC: 1` flight payload — verified working, no auth) adds `options[].required`, `estimatedEffortSeconds`, `license`, and one-hop `recipeList` with GAV strings embedded in `instanceName`; its `/recipes/index` flight payload yields **5,081 recipe FQNs** in one request, and the sitemap lists 8,809 recipe pages.

Verified `UpgradeToJava21` (git `main`) chains: `UpgradeToJava17`, `UpgradeBuildToJava21`, `RemoveExtraSemicolons`, `ThreadStopUnsupported`, `URLConstructorToURICreate`, `SequencedCollection`, `UseLocaleOf`, `ReplaceDeprecatedRuntimeExecMethods`, `SetupJavaUpgradeJavaVersion`, `UpgradePluginsForJava21`, `DeleteDeprecatedFinalize`, `RemovedSubjectMethods`, six switch/pattern-matching recipes, and `SwitchPatternMatching` — plus one entry **commented out with a human reason** (`URLConstructorsToNewURI`, "fails to introduce new exception handling" + issue link: ingest that as `auto=false` evidence). `UpgradePluginsForJava21` is a ready-made dependency-floor table: Gradle wrapper **8.5**, `clm-maven-plugin 2.47.8-01`, `guava 29.0` (`versionPattern: -jre`), `byte-buddy 1.14.11`, `modelmapper 3.2.x`; the inherited 17-chain adds ~12 more (gradle 7.3, maven-wrapper 3.9.x, guice 5.x, mapstruct 1.6.x, spotbugs 4.9.x …). Some recipes carry **`DependencyInsight` preconditions** (e.g. lombok+mapstruct) — that is a rule *condition* expressible directly as a graph guard.

OpenRewrite's own 17-guide has a **Known Limitations** section listing 11 gaps ("does not cover all deprecations listed by `jdeprscan`", CORBA/`javax.transaction`/`javax.batch`/JavaFX/Web Start/JAXB runtime choice) — i.e. **the vendor states the recipe corpus is not the full change set**, which is the justification for the detector channels in §5.7. `java-version-25.yml` also exists and handles the Security-Manager removal (`RemoveSecurityManager`, `SystemGetSecurityManagerToNull`, `RemoveSecurityPolicy`).

**Manual-only** (`MigrationStep` with `automatable: false`, no recipe anywhere in the corpus): JVM flags per §5.7(b), TLS/algorithm policy per §5.7(a), `--add-opens` *removal* after the fact, GC tuning, custom `SecurityManager` subclasses/policy files, `-javaagent`/APM attach behaviour (JEP 451), `--enable-preview` unwinding, CI fleet rollout, base-image change, and runtime regression proof.


---

## 7. Recommended shape (three stages)

### Stage 1 — Java as a platform axis (small, immediately useful)
Do not add a Java "framework" yet. Add what the matrix needs and close the credibility hole:

- **Model the matrix**: `(:Version {framework:"Spring Boot"|"WildFly"|…})-[:SUPPORTS_RUNTIME {min, max, verified, sourceUrl, fetchedAt}]->(:Version {framework:"Java", version:"21.0.0"})`, seeded deterministically from vendor docs + BOM diffs (no LLM). Replaces `version-map.md`'s Min Java column and the stale Boot-4 note; gives `minJava`/`compatibleBoot` (already half-exists in `seed_013_versions.py`) a consumer.
- **Fix the platform-rule drop**: rules with `scope=runtime`/`build` and **no affected entity** must render as a *precondition/verification item*, not `IGNORED`. That means (a) making `signal: "universal"` (spec 027, already computed for exactly the analogous "minimum Node/TS" rules) an honoured render outcome, and (b) a plan/verification template change so "Runtime gate" is filled **from the graph**, with an executable check.
- **Answer "what Java are we on?"**: land spec **026.6** (Maven/Gradle manifests — it already specifies `properties.java.version`, `toolchain.languageVersion`, `sourceCompatibility`) plus a *toolchain facts* channel: `Dockerfile FROM`, `.sdkmanrc`/`.java-version`/`.tool-versions`, CI image, `maven-enforcer requireJavaVersion`. This alone is the highest-value deliverable for a fleet rollout.

### Stage 2 — `framework: "Java"` as a real index (LTS hops)
- One `JdkExtractor`, **LTS-only** version list (`8 → 11 → 17 → 21 → 25`), normalised to `X.Y.Z`, with a `major`/`lts` hop granularity.
- Rules **curated, not scraped prose**: for each LTS hop, seed from JEP index + release-notes Removed/Deprecated sections + OpenRewrite recipe tree, and — critically — **anchor every rule to an entity** (config key, dependency + version floor, curated `java.*`/`sun.*` `Class` watch-list, JVM flag) or it will be dropped by applicability. Do not blanket-enable `java.*` scanning; every `java.util.List` import is noise.
- Add `jdk` as a third ecosystem value (or accept `maven:` keys knowingly and document it), plus `JDK_FEATURES` in `features.py` and a `SIGNAL_QUESTIONS_VERSION` bump.
- Populate `AUTOMATED_BY` from recipe YAML; mark the MSAL caveat on the edge (e.g. `license`, `availability`) so an "automatable" claim can't silently rot.

### Stage 3 — compound runs
`Spring Boot 3.5 → 4.0` and `Java 17 → 21` are one *change set* for one service, executed in one branch. Today that is two `ps-migration/` folders with no ordering and no shared ledger. Options: a `ps-migration/{change-set}/` parent with per-framework sub-plans, and cross-run prerequisite edges (generalise `REQUIRES` beyond one `ruleId`, or record ordering in `tasks.md`). This is the expensive part and is what ISSUE-024 (Spring Cloud co-migration) also needs — do it once, for all three frameworks.

**Sequencing note:** Stage 2 without Stage 1 produces a beautiful rule catalogue whose platform rules still get IGNORED. Stage 1 without Stage 2 already fixes the Boot-4/Java-21 class of failure.

---

## 8. Open decisions before any spec

1. Display name and canonical spelling — `Java` vs `JDK` vs `OpenJDK`, and `21.0.0` vs `21` (identity is unbreakable once populated).
2. LTS-only, or do we index feature releases (18/19/20/22/23/24) we never deploy?
3. Do we model the **vendor/distribution** (Temurin vs Red Hat build vs Corretto) and CPU floors (e.g. "≥ 21.0.4", since 21.0.0 had a real defect)? `Version` has no patch-line concept today.
4. Third ecosystem value, or `maven:` keys for JDK APIs as a documented convention?
5. New entity kinds (`JvmOption`, base image, bytecode target) vs `cfg:<file>#<key>` convention over `ApplicationProperty`.
6. Is the support matrix vendor truth (per upstream docs) or a **Paysafe policy** decision (approved images, approved JDK vendors) that we own and publish? Probably both, and they must not be merged.
7. Scope of the scan: build-time JDK ≠ runtime JDK. Do we accept repo-only scope (current spec-026 non-goal) and lose base-image truth, or extend the scan contract?
8. OpenRewrite MSAL licensing sign-off before automating at fleet scale.

---

## 9. Sources

Primary: [openjdk.org/jeps/0](https://openjdk.org/jeps/0) · [JEP 1 (process)](https://openjdk.org/jeps/1) · [JDK 21 release notes / important changes](https://www.oracle.com/java/technologies/21-relnote-issues.html) · [release-notes index](https://www.oracle.com/java/technologies/jdk-relnotes-index.html) · [bugs.openjdk.org JDK-8313765 (ZIP64)](https://bugs.openjdk.org/browse/JDK-8313765) · [Spring Boot system requirements](https://docs.spring.io/spring-boot/system-requirements.html) · [Gradle Java compatibility](https://docs.gradle.org/current/userguide/compatibility.html) · [OpenRewrite migrate-to-Java-21](https://docs.openrewrite.org/running-recipes/popular-recipe-guides/migrate-to-java-21.md) · [rewrite-migrate-java recipe YAML](https://github.com/openrewrite/rewrite-migrate-java/tree/main/src/main/resources/META-INF/rewrite) · [Code Genome recipe catalogue](https://codegenomeproject.org/recipes/org.openrewrite.java.migrate.UpgradeToJava21) · [actions/setup-java](https://github.com/actions/setup-java/blob/main/README.md) · [Stripe: Modern Java at Stripe](https://stripe.dev/blog/modern-java-at-stripe-language-upgrades-as-a-service.md) · [LinkedIn's journey to Java 11](https://www.linkedin.com/blog/engineering/infrastructure/linkedin-s-journey-to-java-11) · [JaCoCo changelog](https://www.jacoco.org/jacoco/trunk/doc/changes.html) · [Azul Java 8→17 guide](https://www.azul.com/articles/java-8-to-java-17-migration-a-step-by-step-guide-for-teams-mid-upgrade/).

Repo evidence: [graph-schema.md](../01-foundation/graph-schema.md) · [migration-model.md](../03-mcp-and-agent-harness/migration-model.md) · [export-extract-populate-framework-pipeline.md](../02-extraction-pipeline/export-extract-populate-framework-pipeline.md) · [service-scanner.md](../02-extraction-pipeline/service-scanner.md) · `specs/026-service-scanner/spec6.md` · `migration_oracle/mcp/skills/framework-migration/{version-map,plan,scanning}.md` · `runs/json/wildfly-3*-entities.json` · `probe-results/wallet-customer-levels-skill-flow-2026-07-31/` · `docs/05-analysis-and-findings/issues-round-2.md` (ISSUE-024, toolchain-gate decoupling).

*JEP-level claims in §2/§5 were cross-checked against the JEP index; where a research note could not be re-verified it is marked as judgement or omitted. The Spring Boot system-requirements contradiction (§3.1) and every repo citation were verified first-hand in this session.*
