**MIGRATION ORACLE**
 
Extractor Research Report
 
WildFly Bug Fixes  •  Spring Boot Improvements  •  Angular Improvements
 
Spec 002-extractors  |  Branch: 003-framework-http-extractors
 
June 2026
 
# Executive Summary
 
This report documents all findings from the code review and research phase conducted on the three primary framework extractors in the Migration Oracle pipeline: WildFly, Spring Boot, and Angular. The research covered live URL verification, actual release body structures, code review against the pipeline specification, and root-cause analysis of identified defects.
 
The central finding is that all three extractors produce valid output in the happy path, but each has at least one critical defect that causes migration-relevant content to be silently absent from the raw Markdown artifact — the document the filter LLM depends on to produce accurate migration guidance.
 
| **Framework** | **Issues Found** |
| --- | --- |
| WildFly (enrich_with_jira) | 3 bugs — HIGH; 2 spec deviations — MED/LOW |
| Spring Boot | 2 bugs — HIGH; 1 quality issue — LOW |
| Angular | 1 bug — HIGH; 1 quality issue — MED |
 
The most impactful finding across all three frameworks: the extractors fetch the GitHub API release body but do not fetch the secondary sources where the actual migration-relevant content lives. For Spring Boot this is the wiki release notes page; for Angular this is the CHANGELOG.md file. The WildFly Jira enrichment fetches the correct secondary source but has three defects in how it applies the enriched data.
 
# 1. WildFly — enrich_with_jira Bug Fixes
 
The WildFly extractor is the most complex of the nine due to Jira enrichment. The enrichment function (enrich_with_jira) fetches full issue descriptions from the Red Hat Atlassian Jira instance and replaces terse GitHub release one-liners with structured, context-rich statements. Three bugs were identified in the current implementation.
 
## 1.1 Bug Detail
 
| **Bug 1** | **HIGH** | **Issue Index issue_type Fallback Never Consulted** build_release_index(body) is called and builds an in-memory index of every Jira key found in the release body, including the issue type inferred from surrounding HTML section headers (Bug, Enhancement, Feature Request). However, when the Jira REST API response does not include an issue_type field — which happens regularly for WildFly issues — the code does not fall back to the index. The issue_type is simply omitted from DocumentedChange.metadata. **Impact: **The filter LLM receives fewer type signals, reducing its ability to distinguish Bug fixes from Enhancement entries in the migration severity ranking. Fix: After jira = cache.get(key), check index.get(key, {}).get('issue_type') as a secondary source when the REST response does not populate it. |
| --- | --- | --- |
| **Bug 2** | **HIGH** | **Only the First Jira Key in a Statement Is Tried** re.search() is used to find the Jira key in each statement, which returns only the first match. A statement containing multiple keys (e.g. '[WFLY-18341] Supersedes [WFCORE-4892]') uses WFLY-18341 exclusively. If that key's Jira fetch failed, the cache hit on WFCORE-4892 is never attempted even though it may contain richer description data. **Impact: **Statements whose primary key had a network failure produce a bare browse URL instead of full Jira description, when an alternative key in the same statement was successfully fetched. Fix: Use re.finditer() to collect all keys in the statement, then pick the first one that has a cache hit: key = next((k for k in all_keys if k in cache), all_keys[0]). |
| **Bug 3** | **HIGH** | **metadata Passed by Reference in No-Jira-Data Branch** In the branch where a Jira key is found but no Jira data exists in the cache, meta = change.metadata assigns the original dict by reference, not by copy. The Jira-data branch correctly copies it with dict(change.metadata or {}), but the else branch does not. Any downstream mutation of meta on the enriched DocumentedChange will mutate the metadata of the original change object. **Impact: **Silent data corruption if the orchestrator or populator modifies DocumentedChange.metadata after enrichment. The bug is latent today but will activate as soon as any downstream code adds a key to the metadata dict. Fix: Apply dict(change.metadata or {}) consistently in both branches. |
 
## 1.2 Spec Deviations
 
| **Deviation 1** | **MED** | **Partial Jira Entry Produces Raw Statement Instead of Title/Jira: N/A/Release Block** The spec defines the enriched text format as: Title: {jira summary} / Jira: {full jira description or N/A} / Release: {release body one-liner or N/A}. The current code checks if jira and jira.get('description'), which means a Jira entry with a summary but an empty description string falls through to the else branch and produces the raw change.statement — no Title prefix at all. Fix: Split the condition. Produce the formatted block whenever jira['summary'] exists, using 'N/A' for missing description. This matches the spec's intent that the structured format is always used when any Jira data is available. |
| --- | --- | --- |
| **Deviation 2** | **LOW** | **priority Field Fetched but Never Stored** The Jira REST call fetches fields=summary,description,issuetype,priority,status. Only issue_type is propagated to DocumentedChange.metadata. The priority field (e.g. Critical, Major, Minor) is fetched, stored in the local cache, and then silently dropped. This data is available and costs no additional HTTP call. Fix: Store jira_priority in metadata when present. This gives the filter LLM a signal to elevate Critical bugs in the severity ranking. |
 
## 1.3 What is Working Correctly
 
- Async concurrency via asyncio.Semaphore with JIRA_MAX_CONCURRENT cap — correctly prevents flooding the Jira API.
 
- Best-effort failure handling — individual key fetch failures are silently skipped, the pipeline never aborts.
 
- Host normalisation — issues.redhat.com browse links are converted to redhat.atlassian.net before any REST call, as required.
 
- Three-format Jira key regex — HTML export anchors, PR-merge style, and migration guide bullets all matched. Compiled once at module level.
 
- collect_jira_keys correctly implements step 3b — the union of release-body index keys and statement-text keys.
 
- Changes without a Jira key are passed through unchanged — no data is lost.
 
# 2. Spring Boot — Extractor Improvements
 
The Spring Boot extractor is structurally correct: version discovery, tag resolution, BOM diff computation, and ExtractionResult wrapping all follow the spec. However, two critical issues cause the raw Markdown artifact to contain almost no migration-relevant content, despite a successful extraction run.
 
## 2.1 Root Cause: GitHub Release Body Does Not Contain Migration Content
 
Inspecting the actual GitHub API release body for Spring Boot releases (tested against v3.4.0, v3.3.0, v3.2.0) reveals that the body contains only four sections:
 
| **Section in Release Body** | **Migration Value** |
| --- | --- |
| ⭐ New Features | Low — feature additions, not migration requirements |
| 🐞 Bug Fixes | Very Low — one-liner titles without context |
| 📝 Documentation | None |
| 🔨 Dependency Upgrades | Redundant — covered by BOM diff |
 
The actual migration-relevant content — breaking changes, behavioural differences, upgrading instructions, deprecations — lives on the Spring Boot wiki release notes page:
 
*  https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-{major}.{minor}-Release-Notes*
 
For example, the Spring Boot 3.4 wiki page contains sections including: RestClient and RestTemplate order-of-precedence changes, Bean Validation of @ConfigurationProperties behaviour change, @ConditionalOnBean semantic change, and multiple property key changes. None of these appear in the GitHub release body that the extractor currently fetches.
 
## 2.2 Bug Detail
 
| **Bug 1** | **HIGH** | **Wiki Release Notes Page Never Fetched** The extractor calls fetch_github_release() which returns the GitHub API release body. This body does not contain breaking changes or upgrade instructions — it is a changelog summary intended for users browsing the GitHub UI, not a migration document. The wiki page at Spring-Boot-{major}.{minor}-Release-Notes is the canonical migration guide for each minor release series and must be fetched as a second source. **Impact: **The raw Markdown artifact for a Spring Boot upgrade range will contain bug fix one-liners and dependency upgrade lines only. The filter LLM correctly discards most of this as noise but never sees the actual breaking changes. The entities JSON will have few or no mandatory_migration or breaking entities for Spring Boot. Fix: After fetching the GitHub release body, also fetch the wiki page using the major.minor derived from to_version. Append wiki content to body before calling parse_github_release_text. For patch releases (e.g. 3.4.2), the wiki page covers the entire 3.4 minor series and is still the correct source. |
| --- | --- | --- |
| **Bug 2** | **HIGH** | **BOM Diff Called Per Hop Instead of Once Per Range** The spec states the BOM diff is range-level, not per-hop. build_range_metadata(from_version, to_version) is called inside extract(), which is invoked once per hop. For a range 3.3.0 to 3.5.0 with hops 3.3.0→3.3.1, 3.3.1→3.4.0, 3.4.0→3.5.0, the extractor fetches and diffs three POM pairs. The hop-level diffs are also semantically wrong: the 3.3.0→3.3.1 diff shows only patch-level dependency changes, not the full picture of what changed across the user-requested range. **Impact: **Three times the HTTP calls for POM fetches. BOM diff metadata in each hop's ExtractionResult is scoped to that hop only, not the full upgrade range. The orchestrator has no single artifact containing the complete BOM comparison. Fix: Move build_range_metadata out of extract() and call it once from the orchestrator with the original from_version and final to_version. Attach the result to the combined ExtractionResult for the whole range. |
 
## 2.3 Quality Issue
 
| **Quality** | **LOW** | **Dependency Upgrade Lines Are Redundant Once BOM Diff Exists** The GitHub release body for patch releases is dominated by 'Upgrade to X' lines (e.g. 'Upgrade to Tomcat 10.1.16 #38421'). Each becomes a DocumentedChange with type=dependency_upgrade. For a multi-hop range these accumulate into hundreds of low-value rows in the raw Markdown, all of which the filter LLM must process and discard. The BOM diff in metadata already covers dependency changes with full coordinate precision. Once Bug 1 is fixed and the wiki content is included, the dependency upgrade lines from the release body add noise rather than signal. Suppressing the Dependency Upgrades section in parse_github_release_text for Spring Boot would reduce artifact size and improve filter LLM accuracy. |
| --- | --- | --- |
 
## 2.4 What is Working Correctly
 
- Version discovery correctly fetches Maven Central maven-metadata.xml.
 
- Pre-release filter is_spring_boot_ga_version correctly excludes -M*, -RC*, -SNAPSHOT versions (including the new 4.x milestones now on Maven Central).
 
- Tag candidate order v{version} then {version} — confirmed correct against live GitHub tags.
 
- BOM POM URL pattern is structurally correct and the parsing logic is sound.
 
- ExtractionResult.metadata correctly holds bom_diff and not the changes list.
 
- Empty release body raises RuntimeError with descriptive hop range — correct error propagation.
 
# 3. Angular — Extractor Improvements
 
The Angular extractor is the simplest of the three and has the cleanest implementation. One critical defect and one quality issue were identified, both stemming from the same root cause as Spring Boot: the GitHub API release body for Angular is minimal and does not contain the structured migration content.
 
## 3.1 Root Cause: Angular Breaking Changes Live in CHANGELOG.md
 
The Angular team maintains a monolithic CHANGELOG.md in the repository root. Each version entry has a clearly structured format with dedicated Breaking Changes and Deprecations sections organized by package (compiler, core, router, forms, etc.). This file is accessible via raw.githubusercontent.com and is updated with every release.
 
The GitHub API release body for Angular is frequently minimal — either a brief summary or a blog link. The structured per-package changes exist only in CHANGELOG.md. The current extractor fetches the release body but never fetches CHANGELOG.md.
 
Example from the actual Angular 22.0.0 CHANGELOG.md entry (confirmed via live fetch):
 
- Breaking Changes / core: TypeScript versions older than 6.0 are no longer supported.
 
- Breaking Changes / core: Component with undefined changeDetection property are now OnPush by default.
 
- Breaking Changes / core: ChangeDetectorRef.checkNoChanges was removed.
 
- Breaking Changes / router: paramsInheritanceStrategy now defaults to 'always'.
 
- Breaking Changes / platform-browser: Hammer.js integration has been removed.
 
- Deprecations / http: withFetch is now deprecated.
 
None of this content would appear in the current extractor's output.
 
## 3.2 Bug Detail
 
| **Bug 1** | **HIGH** | **CHANGELOG.md Breaking Changes and Deprecations Never Fetched** The extractor calls fetch_github_release() which returns the GitHub API release body. For Angular, this body is typically minimal. The actual per-package breaking changes and deprecations live in CHANGELOG.md at raw.githubusercontent.com/angular/angular/main/CHANGELOG.md. Each version section starts with a named anchor <a name="{version}"></a> and contains Breaking Changes and Deprecations subsections that are exactly what the pipeline needs. **Impact: **The raw Markdown artifact for an Angular upgrade range will contain almost no breaking change or deprecation entries. The filter LLM will produce a sparse or empty mandatory_migration section. The entities JSON will underrepresent Angular's breaking changes significantly. Fix: Fetch the CHANGELOG.md once per extractor instance (cached by the URL-level cache in base.py). For each hop's to_version, extract the corresponding version section using the <a name="{version}"></a> anchor pattern. Append the extracted section to body before parsing. The CHANGELOG is large (~several hundred KB) but is fetched once and reused across all hops in a range. *URL: https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md* |
| --- | --- | --- |
 
## 3.3 Quality Issue
 
| **Quality** | **MED** | **Blog Insights Stored as URLs Only — Content Never Fetched** The blog insight extraction regex (_BLOG_LINK_RE) correctly identifies angular.dev links in the release body and stores them in metadata. However, a URL alone is useless to the filter LLM. The blog posts themselves contain step-by-step migration guides for Angular-specific patterns (NgModule migration, signals interop, component harness changes) that are not captured anywhere else in the extraction pipeline. **Impact: **The metadata['blog_insights'] field contains a list of URLs that the filter LLM cannot use. This is better than nothing (a developer can follow the links manually) but represents missed extraction opportunity for Angular-specific migration guidance. Fix: Fetch each blog URL best-effort and extract the meta description or first substantive paragraph as a summary. Store summaries keyed by URL in metadata. The URL-level cache ensures each blog page is fetched at most once per pipeline run. Failures are silently swallowed. |
| --- | --- | --- |
 
## 3.4 What is Working Correctly
 
- Version discovery correctly fetches from the npm registry and the filter_release_versions function correctly excludes prerelease tags.
 
- The stable version filter \d+\.\d+\.\d+$ correctly excludes rc, next, and vsix tags (e.g. vsix-22.0.0 was observed in the live tag list).
 
- Tag candidate order v{version} then {version} — confirmed correct against live Angular GitHub tags.
 
- Blog insight URL extraction using _BLOG_LINK_RE is correctly scoped to metadata and does not pollute the changes list — matching the spec requirement.
 
- Empty release body raises RuntimeError with descriptive message — correct error propagation.
 
# 4. URL and Tag Format Verification
 
All extractor URLs were verified against live endpoints during the research phase. Four discrepancies between the reference specification and actual GitHub tag formats were identified and corrected in the runbook.
 
## 4.1 Tag Format Corrections
 
| **Framework** | **Spec (old)** | **Corrected (actual)** | **Status** |
| --- | --- | --- | --- |
| **WildFly** | {major}.0.0.Final | {version}.Final (full semver, e.g. 39.0.1.Final) | **FIXED** |
| **Infinispan** | {version}.Final first, then {version} | {version} first, then {version}.Final (16.x dropped .Final) | **FIXED** |
| **Hibernate** | {version} then {version}.Final | {version} only — .Final never used in Hibernate tags | **NOTED** |
| **Spring Boot** | Assumed 3.x max | 4.x exists (v4.0.0, v4.1.0) — no version cap | **FIXED** |
 
## 4.2 Pre-Release Filter Gaps
 
A separate audit found that four Maven-based extractors had no pre-release version filter. Maven Central publishes Alpha, Beta, CR, and Dev builds alongside GA releases for all four frameworks. Without filtering, a user requesting a version range would receive hops through pre-release versions, producing empty or misleading extraction output.
 
| **Framework** | **Pre-release Versions Found on Maven Central / Filter Applied** |
| --- | --- |
| Spring Boot | 4.1.0-M4, 4.1.0-RC1, etc. (4.x onward). Filter: is_spring_boot_ga_version ^d+.d+.d+$ |
| Hibernate ORM | 6.0.0.Alpha1-Alpha9, 6.0.0.Beta1-3, 6.0.0.CR1-2, 7.2.0.CR1, etc. Filter: is_jboss_ga_version (.Final only) |
| RESTEasy | 7.0.0.Beta1-Beta5, 6.2.14.Beta1. Filter: is_jboss_ga_version (.Final only) |
| Infinispan | 16.2.0.Dev01-Dev02 (16.x), non-.Final on 15.x. Filter: is_infinispan_ga_version (both patterns) |
| WildFly Elytron | 2.9.0.CR1, 2.9.0.CR2. Filter: is_jboss_ga_version (.Final only) |
| WildFly | Already handled: .Final filter + JBOSS_SKIP_PRERELEASE env var. No change needed. |
| Angular | Already handled: npm \d+\.\d+\.\d+$ filter. No change needed. |
 
# 5. Consolidated Action Items
 
Issues are ordered by implementation priority. All HIGH items must be resolved before the extractor layer can produce reliable raw Markdown artifacts for the filter LLM.
 
| **#** | **Framework** | **P** | **Action** |
| --- | --- | --- | --- |
| **1** | Spring Boot | **HIGH** | Fetch the wiki release notes page (Spring-Boot-{M}.{m}-Release-Notes) and append to body before parsing. This is the canonical source for breaking changes and upgrade instructions. |
| **2** | Angular | **HIGH** | Fetch CHANGELOG.md from raw.githubusercontent.com, extract the version section by anchor, and append to body. The CHANGELOG contains all Breaking Changes and Deprecations by package. |
| **3** | WildFly | **HIGH** | Fix enrich_with_jira Bug 2: use re.finditer() to collect all Jira keys per statement and try the first cache hit, not just the first key found. |
| **4** | WildFly | **HIGH** | Fix enrich_with_jira Bug 3: apply dict(change.metadata or {}) in both branches of the enrichment loop, not just the Jira-data-present branch. |
| **5** | WildFly | **HIGH** | Fix enrich_with_jira Bug 1: after jira = cache.get(key), fall back to index.get(key, {}).get('issue_type') when the REST response does not include issue_type. |
| **6** | All Maven | **HIGH** | Apply pre-release version filters to Hibernate, RESTEasy, Infinispan, Elytron (spec 002-extractors-prerelease-filter). Spring Boot filter is_spring_boot_ga_version already implemented. |
| **7** | Spring Boot | **MED** | Move build_range_metadata (BOM diff) out of extract() and call it once from the orchestrator. The current per-hop call is semantically wrong and three times as expensive. |
| **8** | WildFly | **MED** | Fix enrich_with_jira Deviation 1: produce the Title/Jira/Release block whenever jira['summary'] exists, using 'N/A' for absent description. |
| **9** | Angular | **MED** | Fetch blog insight URLs and store content summaries in metadata, not just URLs. Use the URL-level cache; swallow failures silently. |
| **10** | WildFly | **LOW** | Fix enrich_with_jira Deviation 2: store jira_priority in DocumentedChange.metadata when present in the REST response. |
| **11** | Spring Boot | **LOW** | Suppress the Dependency Upgrades section in parse_github_release_text for Spring Boot; the BOM diff in metadata is the canonical source for this data. |
 
Migration Oracle — Extractor Research Report — June 2026
 
Migration Oracle — Extractor Research Report  |  Page