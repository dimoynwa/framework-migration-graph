# Angular — Migration Filter Report

- **Framework:** Angular
- **Range:** `19.0.0` → `20.0.0`
- **Filter applied (UTC):** 2026-06-05

---

## 🔴 Breaking Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | TypeScript < 5.8 Support Dropped | Angular 20 drops support for TypeScript versions below 5.8. Upgrade `typescript` to `>=5.8` before starting the Angular upgrade or the build will fail outright. |
| 2 | N/A | Node.js 18 and 22.0–22.10 No Longer Supported | Node.js v18 is no longer supported, and Node.js 22.0–22.10 is also unsupported. Minimum supported versions are Node.js 20.19, 22.12, or 24.0. Update your runtime environment before upgrading. |
| 3 | N/A | `afterRender` Renamed to `afterEveryRender` | The `afterRender` lifecycle hook has been renamed to `afterEveryRender`. Replace all usages of `afterRender` with `afterEveryRender` in your application code. `afterNextRender` is unchanged. |
| 4 | N/A | `InjectFlags` Enum Removed | The `InjectFlags` enum has been removed from the public API. `inject()`, `Injector.get()`, `EnvironmentInjector.get()`, `TestBed.inject()`, and `TestBed.get()` no longer accept `InjectFlags`. Replace `InjectFlags.Optional` with `{ optional: true }`, and `InjectFlags.SkipSelf` with `{ skipSelf: true }`. Run the provided migration: `ng generate @angular/core:inject-migration`. |
| 5 | N/A | `TestBed.get` Removed | `TestBed.get()` has been removed. Replace all calls with `TestBed.inject()`. |
| 6 | N/A | `TestBed.flushEffects` Removed | `TestBed.flushEffects()` has been removed. Use `TestBed.tick()` (the new stable API introduced in Angular 20) to synchronize test state. |
| 7 | N/A | `provideExperimentalCheckNoChangesForDebug` Renamed | `provideExperimentalCheckNoChangesForDebug` has been renamed to `provideCheckNoChangesConfig`. Additionally, the `useNgZoneOnStable` option has been removed from this API. Update call sites and remove `useNgZoneOnStable` references. |
| 8 | N/A | `provideExperimentalZonelessChangeDetection` Renamed | `provideExperimentalZonelessChangeDetection` has been renamed. Update your provider calls to use the new stable name (`provideZonelessChangeDetection`). |
| 9 | N/A | `PendingTasks.run` Return Type Changed | `PendingTasks.run()` no longer returns the result of the inner async function. If you rely on the returned value, capture the result inside the callback before the `run()` call resolves. |
| 10 | N/A | `ApplicationRef.tick` Error Propagation Changed | `ApplicationRef.tick()` will no longer silently catch and report errors — they propagate to the caller. Tests or code that swallowed tick errors may now fail; update error handling accordingly. |
| 11 | N/A | Security — XSRF Token Leakage to Protocol-Relative URLs Fixed | Angular no longer sends XSRF tokens to protocol-relative URLs. Applications that relied on this (inadvertently or intentionally) must adjust their server-side CSRF validation accordingly. |
| 12 | N/A | Security — XSS via SVG `attributeName` and MathML/SVG URLs | Angular now sanitizes SVG animation `attributeName` bindings and MathML/SVG URL attributes to prevent XSS. Templates that set these attributes dynamically via binding may need to use `DomSanitizer.bypassSecurityTrustResourceUrl` where the URL is verified safe. |

## 🟠 Mandatory Migrations — Security & CVE Fixes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | ICU Translation Attribute Sanitization | Angular now only allows known HTML attributes in translated ICU content; unknown attributes are dropped. Applications using ICU translation blocks that bind security-sensitive attributes (e.g. custom `data-*` or script-like attributes) must audit their i18n translations and templates. Sensitive `i18n` attribute bindings are now validated at compile time — build errors will surface unsafe usage. |
| 2 | N/A | SSRF / URL Injection Fixes in SSR Bootstrapping | Multiple server-side bootstrapping paths were hardened against SSRF and path-hijack attacks (`ServerPlatformLocation`, backslash URL normalization, protocol-relative URL restrictions). Review custom `renderModule`/`renderApplication` integrations. An `allowedHosts` option is now available on these APIs to restrict bootstrapping to trusted origins. |
| 3 | N/A | SVG `<script>` Element Sanitization | Angular now strips namespaced SVG `<script>` elements during template compilation and rejects `<script>` elements as dynamic component hosts. Templates or dynamic component creation patterns that used SVG script elements must be refactored. |
| 4 | N/A | `iframe` `src` Translation Blocked | Translations of `iframe[src]` attributes are now blocked to prevent injection. If you relied on i18n for `iframe[src]` values, migrate those bindings to a programmatic sanitized approach using `DomSanitizer`. |

## 🟠 Mandatory Migrations — Major Component Upgrades

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | `InjectFlags` to Options Object Migration | Run `ng generate @angular/core:inject-migration` to automatically replace all `InjectFlags` usage with the equivalent options-object form accepted by `inject()`, `Injector.get()`, etc. |
| 2 | N/A | `ng-reflect-*` Attributes No Longer Produced by Default | Angular 20 stops emitting `ng-reflect-*` DOM attributes by default. Any application or E2E/unit test that selects DOM elements by `ng-reflect-*` attribute will break silently. Audit test selectors and component interaction code — replace `ng-reflect` selectors with `data-testid` attributes or component property queries. |
| 3 | N/A | `DOCUMENT` Token Moved to `@angular/core` | The `DOCUMENT` injection token has moved from `@angular/common` to `@angular/core`. Update imports to `import { DOCUMENT } from '@angular/core'`. The old export in `@angular/common` is still present but will be removed in a future release. |

## 🟠 Mandatory Migrations — Security Configuration

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | TransferCache Skips Cookie-Bearing Requests by Default | `withCredentials` HTTP requests and cookie-bearing requests are now excluded from the Angular Transfer Cache by default to prevent credential leakage across SSR/client boundaries. If you intentionally cache credentialed responses, opt back in explicitly via the transfer cache configuration. |

## 🟡 Behavioral Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | `AsyncPipe` Catches Unhandled Errors Directly | `AsyncPipe` now directly catches and reports unhandled errors in Observable/Promise subscriptions rather than letting them propagate silently. Audit components using `AsyncPipe` with error-prone streams — add `catchError` where appropriate rather than relying on global error handling. |
| 2 | N/A | `in` and `void` Operators Available in Templates | The `in` keyword and `void` operator now resolve to their JavaScript semantics in Angular template expressions. Existing templates that used `in` or `void` as identifiers (e.g. property names) may now parse differently — review and rename conflicting identifiers if needed. |
| 3 | N/A | Uncaught Listener Errors Surface to `ErrorHandler` | Uncaught errors in event listeners that were previously only logged to the console now go through Angular's `ErrorHandler`. Custom error handlers that were not expecting listener errors may receive new error events. |
| 4 | N/A | Suspicious `Y` Date Pattern Throws | Using the `Y` date format specifier (week-numbering year) without `w` (week number) is now detected as a suspicious pattern and throws an error. Replace `Y` with `y` where the calendar year is intended. |
| 5 | N/A | `provideExperimentalZonelessChangeDetection` → `provideZonelessChangeDetection` | The experimental zoneless change detection provider has been promoted to developer preview and renamed. Replace `provideExperimentalZonelessChangeDetection()` with `provideZonelessChangeDetection()`. |
| 6 | N/A | `setInput` Blocked on `inputBinding`-managed Components | Calling `ComponentRef.setInput()` is now disallowed on components created with the new `inputBinding`/`twoWayBinding` dynamic component API. Use `inputBinding` to manage those inputs instead. |
| 7 | N/A | Route Guard `any` Type Removed | The `any` overload has been removed from route guard arrays on the `Route` interface. Strict TypeScript projects may see new type errors — update guard types to use the concrete guard interfaces (`CanActivateFn`, `CanDeactivateFn`, etc.). |

## 🟡 Deprecations

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | `ngIf`, `ngFor`, `ngSwitch` Deprecated | The structural directives `NgIf`, `NgFor`, and `NgSwitch` are deprecated. Migrate to the built-in control flow syntax (`@if`, `@for`, `@switch`). Use `ng generate @angular/core:control-flow` to auto-migrate. |
| 2 | N/A | `@angular/platform-browser-dynamic` Package Deprecated | The `@angular/platform-browser-dynamic` package is deprecated. Migrate bootstrapping from `bootstrapModule()` to `bootstrapApplication()` with `provideRouter()`, `provideHttpClient()`, etc. |
| 3 | N/A | HammerJS Integration Deprecated | HammerJS gesture support in `@angular/platform-browser` is deprecated and will be removed in a future major version. Remove `HammerModule` imports and migrate to native pointer events or a standalone gesture library. |
| 4 | N/A | `@angular/platform-server/testing` Entry Point Deprecated | The `@angular/platform-server/testing` entry point is deprecated. Update server-side tests to use the standard `@angular/core/testing` APIs. |
| 5 | N/A | `ng-reflect-*` Attributes Deprecated | `ng-reflect-*` DOM debug attributes are deprecated and no longer emitted by default. Remove reliance on these in tests and application code. |

## 🔵 Notable New Capabilities

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | Dynamic Components: Input Bindings, Outputs, Directives | `createComponent` now supports `inputBinding()`, `twoWayBinding()`, and `outputBinding()` for dynamically created components, enabling full declarative binding without manual `setInput` calls or wrapper components. |
| 2 | N/A | `TestBed.tick()` Introduced | A new `TestBed.tick()` API is available to synchronize test state and flush effects. Use it as a stable replacement for `TestBed.flushEffects()` and manual tick sequences in tests. |
| 3 | N/A | `linkedSignal` and `toSignal` / `toObservable` Stabilized | `linkedSignal()`, `toSignal()`, and `toObservable()` are now stable APIs. Adopt them without experimental caveats. |
| 4 | N/A | Incremental Hydration Stabilized | Incremental (on-demand) SSR hydration is now stable. `withIncrementalHydration()` and `withI18nSupport()` are production-ready. |
| 5 | N/A | `httpResource` Experimental API | The `httpResource()` experimental API provides reactive HTTP data fetching backed by signals. Evaluate for adoption; it remains a developer preview. |

---

## Summary by Priority

| Priority Level | Count | Description |
| :--- | :--- | :--- |
| 🔴 **Breaking** | 12 | Must fix before migrating. |
| 🟠 **Mandatory** | 8 | Security CVEs, component upgrades, security config. |
| 🟡 **Behavioral / Deprecation** | 12 | Assess impact and adjust accordingly. |
| 🔵 **New Capabilities** | 5 | Optional but recommended to leverage. |

## 🚨 Most Critical Items for Migration
- **TypeScript < 5.8 and Node.js < 20.19 (or unsupported 22.x) must be upgraded first**: Angular 20 has hard runtime and build-time requirements on these versions — the build fails and the application won't start without them.
- **`afterRender` is renamed to `afterEveryRender` and `InjectFlags` is removed**: Both are compile-time breaking changes that cause immediate build failures. `afterRender` usage in component code will not compile, and any `InjectFlags` usage in DI calls will produce type errors — run `ng generate @angular/core:inject-migration` to handle the DI changes automatically.
- **`ng-reflect-*` attributes are no longer emitted by default**: E2E and unit tests selecting DOM elements via `ng-reflect-*` will silently fail — audit all test selectors now and replace with `data-testid` or semantic queries before upgrading.
- **Multiple security patches are mandatory**: XSS via SVG `attributeName`, XSRF token leakage to protocol-relative URLs, SSRF in SSR bootstrapping, and ICU translation injection are all patched. Review any templates or SSR setups that bind to SVG/MathML attributes, use protocol-relative URLs, or rely on ICU-translated attribute bindings.
- **`ngIf` / `ngFor` / `ngSwitch` deprecation and `@angular/platform-browser-dynamic` deprecation begin**: While not removed yet, both are on the removal path. Start migrating to `@if`/`@for`/`@switch` and `bootstrapApplication()` during this upgrade cycle to reduce the v21 migration burden.
