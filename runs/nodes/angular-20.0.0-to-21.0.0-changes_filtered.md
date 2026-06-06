# Angular — Migration Filter Report

- **Framework:** Angular
- **Range:** `20.0.0` → `21.0.0`
- **Filter applied (UTC):** 2026-06-05

---

## 🔴 Breaking Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | TypeScript < 5.9 Support Dropped | Angular 21 drops TypeScript 5.8 support. Upgrade `typescript` to `>=5.9` before starting the Angular upgrade or the build will fail outright. |
| 2 | N/A | Host Binding Type Checking Enabled by Default | `typeCheckHostBindings` is now `true` by default. Build errors will be thrown for type mismatches in host bindings that were previously silently ignored. Fix the reported host binding type errors, or set `"typeCheckHostBindings": false` in the `angularCompilerOptions` of your `tsconfig` as a temporary suppression. |
| 3 | N/A | `ignoreChangesOutsideZone` Option Removed | The `ignoreChangesOutsideZone` option in `NgZone` and `provideZoneChangeDetection` has been removed entirely. Remove it from your zone configuration and, if you were using it to suppress out-of-zone changes, migrate to `provideZonelessChangeDetection()` or handle scheduling explicitly. |
| 4 | N/A | Zone-Based Scheduler Removed from Internals by Default | Angular no longer provides a Zone-based change detection scheduler internally by default. Applications mixing `provideZoneChangeDetection` and `provideZonelessChangeDetection` will break. Run the schematic `ng generate @angular/core:zoneless-migration` to migrate. |
| 5 | N/A | `emitDeclarationOnly` TypeScript Option Disallowed | The Angular compiler now throws an error if the `emitDeclarationOnly` TypeScript compiler option is enabled. Remove `"emitDeclarationOnly": true` from any `tsconfig` that the Angular compiler processes, or move it to a separate non-Angular tsconfig. |
| 6 | N/A | `NgModuleFactory` Removed | `NgModuleFactory` has been removed. Replace any usage with `NgModule`. If you were passing `NgModuleFactory` instances to `ViewContainerRef.createComponent` or similar APIs, switch to the module-based or standalone component APIs. |
| 7 | N/A | `moduleId` Removed from `@Component` Metadata | The `moduleId` property on `@Component` has been removed. Delete any `moduleId: module.id` declarations from your component decorators — it has been a no-op for several versions. |
| 8 | N/A | `interpolation` Option Removed from `@Component` | The `interpolation` option on `@Component` (used to configure custom interpolation delimiters) has been removed. Only the default `{{ ... }}` is supported. If you were using custom delimiters, refactor your templates to use the standard syntax. |
| 9 | N/A | `ApplicationConfig` Removed from `@angular/platform-browser` | The `ApplicationConfig` export from `@angular/platform-browser` has been removed. Update imports to `import { ApplicationConfig } from '@angular/core'`. |
| 10 | N/A | `UpgradeAdapter` Removed | The `UpgradeAdapter` from `@angular/upgrade` (the legacy AngularJS-to-Angular upgrade path) has been removed. Migrate to `@angular/upgrade/static` and the `UpgradeModule` / `downgradeComponent` / `downgradeInjectable` APIs. |
| 11 | N/A | `ngModuleFactory` Input of `NgComponentOutlet` Removed | The `ngModuleFactory` input on `NgComponentOutlet` has been removed. Update usages to pass a module type or standalone component type directly. |
| 12 | N/A | `FormArrayDirective` Conflicts with Existing Directives | A new `FormArrayDirective` has been introduced in `@angular/forms`. It will conflict with any existing custom directive or component input selector named `formArray` on the same element as a `<form>`. Audit form templates and rename conflicting selectors. |

## 🟠 Mandatory Migrations — Security & CVE Fixes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | XSRF Token Leakage to Protocol-Relative URLs | Angular no longer sends XSRF tokens to protocol-relative URLs (e.g. `//example.com/api`). Adjust server-side CSRF validation if it expected tokens from these requests. Patched in 20.3.14. |
| 2 | N/A | XSS via SVG Animation `attributeName` and MathML/SVG URLs | SVG animation `attributeName` bindings and MathML/SVG URL attributes are now sanitized at runtime. Templates that bind to these attributes may need `DomSanitizer.bypassSecurityTrustResourceUrl` where the URL is verified safe. Patched in 20.3.15. |
| 3 | N/A | SVG `<script>` and Sensitive Attribute Sanitization | Namespaced SVG `<script>` elements are now stripped during template compilation. Dynamic `href`/`xlink:href` bindings on SVG `<a>` elements are sanitized. `<script>` elements are rejected as dynamic component hosts. Review any templates or dynamic-component creation using SVG script elements or `<a>` href bindings. Also fixes a DOM schema normalization issue affecting compile-time i18n attribute security validation. Patched in 20.3.16 and 20.3.22. |
| 4 | N/A | ICU Message Sensitive URI Attribute Sanitization | Angular now blocks creation of security-sensitive URI attributes from ICU messages and restricts translated ICU content to known HTML attributes. Audit i18n ICU blocks that produce `href`, `src`, or other URL attributes — unknown attributes are silently dropped. Patched in 20.3.17. |
| 5 | N/A | `iframe[src]` Translation Blocked and i18n Binding Sanitization | Translations of `iframe[src]` are now blocked. Translated attribute bindings with interpolations and translated form attributes are now sanitized. Migrate any `iframe[src]` i18n bindings to programmatic `DomSanitizer` usage. Patched in 20.3.18. |
| 6 | N/A | SSRF Bypasses via Protocol-Relative and Backslash URLs | Server-side bootstrapping now blocks SSRF and path-hijack via protocol-relative or backslash-normalized URLs in `ServerPlatformLocation`. Use the `allowedHosts` option on `renderModule`/`renderApplication` to restrict bootstrapping to trusted origins. Patched in 20.3.19 and 20.3.21. |
| 7 | N/A | Event Attribute Bindings in Host Bindings Blocked | Angular now unconditionally disallows `on*` event attribute bindings in `@Component` and `@Directive` host binding declarations. Removes a XSS injection vector. Refactor any host bindings using string event attributes to the `(event)="handler()"` host listener syntax. Also validates security-sensitive attributes in i18n bindings at compile time. Patched in 20.3.20. |

## 🟠 Mandatory Migrations — Major Component Upgrades

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | Zoneless Migration Schematic | Run `ng generate @angular/core:zoneless-migration` to migrate your application from Zone-based to zoneless change detection. Angular 21 removes the internal Zone-based scheduler by default; this migration updates providers and removes `zone.js` imports. Required for all apps still using Zone-based CD. |
| 2 | N/A | `ngClass` → `[class]` Binding Migration | Run `ng generate @angular/core:ngclass-to-class` to replace `[ngClass]` bindings with the native `[class]` binding syntax. A bug fix for this schematic was released in 21.0.0 — run the migration on Angular 21 rather than 20. |
| 3 | N/A | `ngStyle` → `[style]` Binding Migration | Run `ng generate @angular/core:ngstyle-to-style` to replace `[ngStyle]` bindings with the native `[style]` binding syntax, as part of removing the legacy structural directive APIs. |
| 4 | N/A | `CommonModule` Handling in Standalone Migration | The standalone migration (`ng generate @angular/core:standalone`) now correctly handles `CommonModule` imports. If you previously deferred standalone migration due to `CommonModule` issues, re-run the migration on Angular 21. |

## 🟠 Mandatory Migrations — Security Configuration

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | TransferCache Excludes `withCredentials` / Cookie Requests | The Angular Transfer Cache now skips `withCredentials` requests and cookie-bearing requests by default to prevent credential leakage across SSR/client boundaries. Opt back in explicitly via the transfer cache configuration if you intentionally cache credentialed responses. Patched in 20.3.22. |

## 🟡 Behavioral Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | `lastSuccessfulNavigation` Converted to Signal | `Router.lastSuccessfulNavigation` is now a signal. Update all read access from `router.lastSuccessfulNavigation` to `router.lastSuccessfulNavigation()`. |
| 2 | N/A | `Router.getCurrentNavigation()` Replaced by Signal | `Router.currentNavigation` is now a signal and `Router.getCurrentNavigation()` is deprecated. Replace `router.getCurrentNavigation()` calls with `router.currentNavigation()`. |
| 3 | N/A | ARIA Property Bindings No Longer Renamed to Attributes | Angular no longer renames ARIA property bindings (e.g. `[ariaLabel]`) to attribute bindings (`aria-label`) at compile time. Use the explicit `[attr.aria-label]` binding form to ensure ARIA attributes are rendered correctly. A schematic (`ng generate @angular/core:aria-to-attribute`) may be available. |
| 4 | N/A | Router Navigation May Take Extra Async Ticks | Router navigations now may take several additional microtasks/async ticks due to the internal `recognize` stage switching to `async/await`. Tests asserting synchronous navigation completion must be updated to await the full navigation. |
| 5 | N/A | `BootstrapContext` Eliminates Global Platform Injector in SSR | Server-side bootstrapping no longer relies on a global platform injector. Custom SSR bootstrapping code using `PlatformRef` directly or relying on singleton platform state must be updated to pass a `BootstrapContext`. Review all custom `renderModule`/`renderApplication` wrappers. |
| 6 | N/A | `@defer` Misconfiguration Produces Diagnostic | The Angular compiler now produces an error diagnostic for misconfigured `@defer` triggers (e.g. `on viewport` without a valid element reference). Fix any `@defer` blocks that produced silent runtime issues before. |
| 7 | N/A | `provideZoneChangeDetection` + Zoneless Combination Disallowed | Combining `provideZoneChangeDetection` and `provideZonelessChangeDetection` in the same injector is now detected and will trigger a runtime error or warning. Choose one scheduler per injector and remove the conflicting provider. |

## 🟡 Deprecations

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | `@angular/animations` Package Deprecated | The entire `@angular/animations` package is deprecated. Begin planning migration away from `@Component.animations` and `AnimationsModule`. New native CSS-based animation support (`animate.enter`/`animate.leave`) introduced in 20.2 is the intended replacement path. |
| 2 | N/A | `animations` Field on `@Component` Deprecated | The `animations` field on the `@Component` decorator is deprecated alongside the animations package. Migrate component animations to native CSS transitions/animations or the new `animate.*` bindings. |
| 3 | N/A | `RouterTestingModule` Deprecated | `RouterTestingModule` is deprecated. A migration schematic is available: run `ng generate @angular/core:router-testing-module` to migrate tests to the modern `provideRouter()` + `RouterTestingHarness` pattern. |
| 4 | N/A | `Router.getCurrentNavigation()` Deprecated | `Router.getCurrentNavigation()` is deprecated in favour of the `Router.currentNavigation` signal. Replace all call sites. |
| 5 | N/A | `HttpResponseBase.statusText` Deprecated | `HttpResponseBase.statusText` is deprecated. Plan removal of any code that reads this property. |

## 🔵 Notable New Capabilities

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | Experimental Signal-Based Forms | A new experimental signal-based forms API is available (`@angular/forms`). Evaluate for adoption in new feature work; the API includes `FormField`, `FormArrayDirective`, `debounce()` rule, and interoperability with reactive forms `ControlValueAccessor`. |
| 2 | N/A | Navigation API Experimental Support | Experimental integration with the browser Navigation API is available via `withNavigationApi()`. Allows Angular Router to participate in the native browser navigation lifecycle on supported browsers. |
| 3 | N/A | Regular Expressions in Templates | Template expressions now support regular expression literals (e.g. `/foo/gi`). No migration required — new syntax available for template logic. |
| 4 | N/A | `SimpleChanges` Now Generic | `SimpleChanges<T>` is now generic — `ngOnChanges(changes: SimpleChanges<MyComponent>)` gives typed access to change properties. Update `ngOnChanges` signatures incrementally for improved type safety. |
| 5 | N/A | `httpResource` Expanded Options | `httpResource()` now supports `cache`, `priority`, `timeout`, `credentials`, `mode`, `redirect`, `referrerPolicy`, and `integrity` options, aligning it with the full Fetch API surface. Evaluate for reactive data fetching patterns. |
| 6 | N/A | Zoneless Change Detection Stable (20.2) | `provideZonelessChangeDetection()` was promoted to stable in 20.2.0. Use it in production without experimental caveats. |
| 7 | N/A | `loadComponent`/`loadChildren` in Route's Injection Context | Lazy-loading functions (`loadComponent`, `loadChildren`) now run inside the route's injection context, enabling `inject()` calls within these functions. |

---

## Summary by Priority

| Priority Level | Count | Description |
| :--- | :--- | :--- |
| 🔴 **Breaking** | 12 | Must fix before migrating. |
| 🟠 **Mandatory** | 12 | Security CVEs, component upgrades, security config. |
| 🟡 **Behavioral / Deprecation** | 12 | Assess impact and adjust accordingly. |
| 🔵 **New Capabilities** | 7 | Optional but recommended to leverage. |

## 🚨 Most Critical Items for Migration
- **TypeScript < 5.9 is rejected at build time**: Angular 21 hardcodes the minimum TypeScript version to 5.9. Upgrade `typescript` to `>=5.9` as the absolute first step before any other migration work.
- **Host binding type checking is now on by default**: Any component or directive that had type-unsafe host bindings will produce build errors on upgrade. Triage by temporarily adding `"typeCheckHostBindings": false` in `angularCompilerOptions`, then fix violations before re-enabling.
- **Zone-based change detection scheduler is removed from internals**: This is the most architecturally disruptive change in Angular 21. Run `ng generate @angular/core:zoneless-migration` before upgrading; applications that remain on Zone-based CD must ensure `zone.js` is still provided and must remove `ignoreChangesOutsideZone` from their NgZone configuration.
- **Seven security CVE patches are mandatory**: Covering XSRF leakage, XSS via SVG/MathML, SSRF in SSR, ICU message injection, and i18n attribute injection — all patched in the 20.3.x series that precedes 21.0.0. Review templates binding to SVG attributes, SSR bootstrapping code, and i18n ICU blocks before deploying.
- **`@angular/animations` is now deprecated**: While not removed yet, beginning the migration away from `@Component.animations` and `AnimationsModule` to native CSS transitions or the new `animate.enter`/`animate.leave` bindings during this upgrade cycle will reduce the v22 migration burden significantly.
