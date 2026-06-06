# Angular — Migration Filter Report: `21.0.0` → `22.0.0`

---

## 🔴 Breaking Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | TypeScript 5.x support dropped | TypeScript versions older than 6.0 are no longer supported. Upgrade `typescript` in your project to `>=6.0` before migrating to Angular 22. Update `tsconfig.json` compiler options and validate your codebase compiles cleanly against TypeScript 6.0 stricter defaults. |
| 2 | N/A | Default `changeDetection` changed to `OnPush` | Components that do not explicitly declare a `changeDetection` strategy now default to `ChangeDetectionStrategy.OnPush`. This is a silent, wide-impact behavioral change — components relying on the previous default (`Default`/Eager) will stop updating on non-signal async events. Run `ng update` to apply the provided migration schematic that adds `changeDetection: ChangeDetectionStrategy.Eager` to all affected components before updating. |
| 3 | N/A | `ComponentFactoryResolver` and `ComponentFactory` removed | Both classes are removed from the Angular API surface. Replace all usages of `ViewContainerRef.createComponent(factory)` with `ViewContainerRef.createComponent(ComponentClass)`. Remove all injection of `ComponentFactoryResolver` from constructors and providers. |
| 4 | N/A | `createNgModuleRef` removed | Replace every call to `createNgModuleRef(module, parentInjector?)` with `createNgModule(module, parentInjector?)`. |
| 5 | N/A | `ChangeDetectorRef.checkNoChanges` removed | This method no longer exists on `ChangeDetectorRef`. In unit tests, replace usages with `fixture.detectChanges()`. In production code, remove or replace with appropriate signal-based patterns. |
| 6 | N/A | `data-*` attributes no longer bind inputs/outputs | Angular 22 stops treating `data-*` prefixed attributes as input/output bindings. Any template that used `data-myProp` to bind to a component input will silently stop working. Audit all templates for `data-*` usage and replace with standard `[myProp]` or `myProp=` bindings. |
| 7 | N/A | Duplicate input/output bindings throw at compile time | The compiler now throws an error when the same name is bound as both an input and an output (or multiple times). Audit templates for duplicate `[foo]` / `(foo)` / `[(foo)]` bindings and resolve naming conflicts. |
| 8 | N/A | `in` operator throws in template expressions | Using the JavaScript `in` operator inside Angular template expressions now results in a compile-time error. Refactor any template expressions that use `in` (e.g., `'key' in obj`) to use explicit property access or helper methods. |
| 9 | N/A | Multiple matching selectors throw at compile time (NG8023) | When two or more directives or components match the same element selector, Angular 22 throws diagnostic NG8023 at compile time instead of silently applying both. Identify and resolve all ambiguous selector conflicts in your module declarations and component imports. |
| 10 | N/A | Hammer.js integration removed | All Hammer.js gesture integration code (`HammerGestureConfig`, touch event bindings) is removed from `@angular/platform-browser`. If your app depends on swipe, pinch, or other Hammer.js gestures, implement your own gesture handling library or use the Pointer Events API directly. |
| 11 | N/A | `FetchBackend` is now the default `HttpBackend` | The HTTP client now uses `FetchBackend` instead of `XhrBackend` by default. Applications using `reportProgress: true` for upload progress events will no longer receive them. To restore XHR-based upload progress, add `withXhr()` to `provideHttpClient(...)`. A migration schematic is available via `ng update`. |
| 12 | N/A | `min`/`max` validators reject string arguments | The built-in Angular `min` and `max` form validators no longer accept string values. Audit all reactive and template-driven form configurations that pass string values to `Validators.min(...)` or `Validators.max(...)` and convert them to `number`. |
| 13 | N/A | `appRef.bootstrap` requires non-nullable element | The second argument of `ApplicationRef.bootstrap()` no longer accepts `any` or nullable types. Ensure the element reference you pass is explicitly typed as non-nullable; add a null guard before calling bootstrap if the element may not exist. |
| 14 | N/A | `AnimationCallbackEvent.animationComplete` signature changed | The `animationComplete` property of `AnimationCallbackEvent` has a new signature. Update any code that accesses, types, or subscribes to `animationComplete` on animation callback events to match the new interface. |
| 15 | N/A | `paramsInheritanceStrategy` defaults to `'always'` | Router's `paramsInheritanceStrategy` now defaults to `'always'` (child routes inherit all parent params). Previously it was `'emptyOnly'`. If your route hierarchy depends on isolated param scopes, explicitly set `paramsInheritanceStrategy: 'emptyOnly'` in `provideRouter(routes, withRouterConfig({ paramsInheritanceStrategy: 'emptyOnly' }))`. |
| 16 | N/A | `currentSnapshot` required in `CanMatchFn` | The `currentSnapshot` (third parameter) is now required in `CanMatchFn` function signatures and in `CanMatch.canMatch()` class implementations. Existing class-based guards missing this parameter will fail TypeScript compilation. Run `ng update` to apply the provided migration schematic. |
| 17 | N/A | `provideRoutes()` removed | `provideRoutes(routes)` has been deleted. Replace all usages with `provideRouter(routes)`, or if you need multi-provider token behavior, use the `ROUTES` token directly as `{ provide: ROUTES, useValue: routes, multi: true }`. |
| 18 | N/A | Unused host styles removed from DOM | Angular 22 removes component styles from the DOM when the associated host element is destroyed. Pages that relied on Angular component styles persisting beyond the component's lifetime, or applying to non-Angular DOM elements, may appear unstyled after upgrade. Audit component styles for unintentional cross-boundary leakage and use `ViewEncapsulation.None` explicitly where global styles are intended. |
| 19 | N/A | Shadow CSS polyfills and legacy selectors removed | Deprecated shadow DOM encapsulation polyfills and legacy selectors (`::shadow`, `/deep/`, `>>>`) are fully removed. Replace all remaining `::ng-deep` workarounds and deep-selector patterns with component-level style scoping or globally scoped stylesheets. |
| 20 | N/A | `TitleStrategy.getResolvedTitleForRoute` return type changed | Custom `TitleStrategy` implementations must be updated to match the new return type of `getResolvedTitleForRoute`. TypeScript will fail to compile implementations that return the old type. Check the Angular 22 API reference for the updated signature. |

---

## 🟠 Mandatory Migrations — Security & CVE Fixes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | #67797 | SVG animation attribute XSS hardening | Angular 22 registers SVG animation attributes (`attributeName`, `href`, `xlink:href` on `<animate>`, `<set>`, `<animateTransform>`) in the URL security context and blocks unsafe bindings. Bindings to these attributes now go through the sanitizer. If your application legitimately needs to bind dynamic values to SVG animation attributes, wrap them with `bypassSecurityTrustResourceUrl`. Failure to act may result in runtime sanitization stripping bound values. |
| 2 | #68925, #68868 | i18n translation security hardening | Multiple security fixes tighten i18n template security: (1) Angular now drops unknown HTML attributes in translated ICU content — non-standard attributes in ICU messages will no longer render; (2) creation of `src`/`href`/`action` and other sensitive URI attributes from ICU messages is blocked; (3) `<iframe src>` bindings inside i18n translations are disallowed; (4) security-sensitive attributes in i18n bindings are now validated at compile time. Audit your i18n translation files for ICU blocks containing custom attributes or sensitive URL bindings and refactor them to avoid these patterns. |
| 3 | N/A | SSRF and URL spoofing hardening in HttpClient | Multiple patches across 21.x hardened the Angular HTTP client against SSRF: backslash URL bypasses, protocol-relative URL leakage, and multiple leading slashes are now blocked or normalized. If your application passes user-controlled URLs to `HttpClient`, the sanitizer may now reject previously accepted inputs. Review URL construction logic and ensure server-side inputs are validated before passing to Angular's HTTP client. |
| 4 | N/A | Transfer cache excludes credential-bearing requests | The SSR transfer cache now automatically excludes requests that include credentials: `withCredentials: true` requests are excluded, and cookie-bearing requests are skipped by default. If your SSR setup relied on transfer-caching authenticated API responses, those responses will now be re-fetched on the client. Explicitly configure `transferCache` options in `provideClientHydration()` if you need to re-enable caching for specific authenticated endpoints (with appropriate security review). |

---

## 🟠 Mandatory Migrations — Major Component Upgrades

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | `ng update` migration schematics required | Angular 22's `ng update @angular/core @angular/cli` applies several mandatory code transformations: (1) adds `changeDetection: ChangeDetectionStrategy.Eager` to all components missing an explicit strategy; (2) updates all `CanMatchFn` signatures to include the required `currentSnapshot` parameter; (3) adds `strictTemplates: true` to `tsconfig.json` if absent; (4) migrates `model()` and `output()` call patterns; (5) disables `nullishCoalescingNotNullable` and `optionalChainNotNullable` diagnostics in `tsconfig.json` to avoid false positives from template narrowing changes; (6) migrates `provideHttpClient` to include `withXhr()` where upload progress is used. Run `ng update` in a clean branch before making manual changes. |

---

## 🟠 Mandatory Migrations — Security Configuration

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | `provideHttpClient` XHR upload progress opt-in | Upload progress events (`reportProgress: true` with type `UploadProgress`) no longer work out of the box because `FetchBackend` does not support them. Add `withXhr()` to `provideHttpClient(withXhr())` in your application config and switch the deprecated `reportProgress` option to `reportUploadProgress: true` / `reportDownloadProgress: true`. |

---

## 🟡 Behavioral Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | `nullishCoalescingNotNullable` / `optionalChainNotNullable` diagnostics triggered | The improved template type checker in Angular 22 enables `nullishCoalescingNotNullable` and `optionalChainNotNullable` diagnostics on existing templates. This may surface new compile-time errors in templates that use `??` or `?.` on types Angular can now prove are non-nullable. Review and fix reported diagnostics, or run `ng update` to have them suppressed in `tsconfig.json` until you address them incrementally. |
| 2 | N/A | `SignalFormsConfig.classes` shape changed | The shape of `SignalFormsConfig.classes` changed across 21.x patch releases. If you use signal forms with custom class configurations, verify your class config object matches the latest `SignalFormsConfig` interface. |
| 3 | N/A | `[field]` renamed to `[formField]` on signal forms | The signal forms field directive binding was renamed from `[field]` to `[formField]` in 21.0.8. Update all templates that use `[field]="..."` on signal form field elements to `[formField]="..."`. |
| 4 | N/A | Leave animations now extend beyond removed element | Leave animations in Angular 22 are no longer scoped to the element being removed. Nested elements can now also animate on leave. If your animation tests or visual designs assumed leave animations were isolated to the removing element, review them for unintended cascades. |
| 5 | N/A | `paramsInheritanceStrategy` behavioral shift | As a consequence of the default change to `'always'`, child route components may now receive params they did not previously see. Verify that child-route components do not accidentally consume parent-level params that were previously invisible to them. |
| 6 | N/A | Incremental hydration enabled by default | Incremental (deferred) hydration is now the default in Angular SSR. Pages that previously hydrated eagerly may now hydrate components progressively on scroll/interaction. Verify hydration behavior in SSR integration tests and ensure SSR-rendered markup is compatible with deferred hydration. |

---

## 🟡 Deprecations

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | `withFetch` deprecated and removable | `withFetch()` in `provideHttpClient(withFetch())` is deprecated because `FetchBackend` is now the default. Safely remove `withFetch()` from all `provideHttpClient` calls. |
| 2 | N/A | `reportProgress` → `reportUploadProgress`/`reportDownloadProgress` | The `reportProgress` option on `HttpRequest` is deprecated. Replace with `reportUploadProgress: true` and/or `reportDownloadProgress: true` to explicitly target the desired progress event type. |
| 3 | N/A | `getAngularLib`/`setAngularLib` removed | These functions are fully removed from `@angular/upgrade`. Replace all usages with `getAngularJSGlobal()` and `setAngularJSGlobal()` from the same package. |
| 4 | N/A | `VERSION` from `@angular/upgrade` deprecated | `VERSION` exported from `@angular/upgrade` is deprecated. Use the `VERSION` export from `@angular/upgrade/static` instead. |

---

## 🔵 Notable New Capabilities

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | TypeScript 6.0 and Node.js 26 support | Angular 22 officially supports TypeScript 6.0 and Node.js 26.0.0. You can now leverage TypeScript 6.0 language features in Angular templates and application code. |
| 2 | N/A | `@Service` decorator introduced | A new `@Service` decorator is available as a simpler alternative to `@Injectable`. Mark singleton services with `@Service` instead of `@Injectable({ providedIn: 'root' })` for cleaner syntax. |
| 3 | N/A | Signal Forms APIs graduated to public API | Signal Forms (previously developer preview) are now part of Angular's stable public API. Stable APIs include `FormRoot`, `FormField`, `FieldState`, `SignalFormControl`, `validateAsync`, `validateHttp`, and `reloadValidation`. Safe to adopt in production code. |
| 4 | N/A | Arrow functions supported in template expressions | Angular templates now support arrow function syntax in expressions, removing the need to define helper methods on the component class for simple inline callbacks in `@for`, event handlers, and other bindings. |
| 5 | N/A | `@defer` idle timeout and customization | `@defer` blocks now support idle timeout configuration and optional timeout for idle triggers. Use `on idle(timeout: 3000)` or the new `IdleService` options to control deferred loading behavior in resource-constrained environments. |
| 6 | N/A | Multiple `@switch` case matching | A single `@case` block can now match multiple values. Use `@case(a, b, c)` syntax to consolidate switch branches that share the same template, eliminating fallthrough workarounds. |
| 7 | N/A | `injectAsync` helper | A new `injectAsync()` helper function allows asynchronous injection of dependencies (e.g., lazily loaded tokens) within injection context. Useful for deferring expensive initialization to first use. |
| 8 | N/A | `provideWebMcpTools` / AI debugging tools | Angular 22 ships experimental `provideWebMcpTools()` and `declareWebMcpTool` primitives for exposing Angular DI graph information to AI tools. Optional — adopt only if you are integrating Angular apps with AI-assisted debugging workflows. |

---

## Summary by Priority

| Priority Level | Count | Description |
| :--- | :--- | :--- |
| 🔴 **Breaking** | 20 | Must fix before migrating. |
| 🟠 **Mandatory** | 6 | Security CVEs, component upgrades, security config. |
| 🟡 **Behavioral / Deprecation** | 10 | Assess impact and adjust accordingly. |
| 🔵 **New Capabilities** | 8 | Optional but recommended to leverage. |

---

## 🚨 Most Critical Items for Migration

- **Default `OnPush` change detection is the highest-risk item.** Every component in your application that does not explicitly declare `changeDetection` will silently switch from `Default` to `OnPush`, breaking async UI updates that are not signal- or `markForCheck()`-based. Always run `ng update` to apply the Eager migration schematic before any other changes.
- **`ComponentFactoryResolver` and `ComponentFactory` are fully removed.** Any code that injects `ComponentFactoryResolver` or holds a `ComponentFactory<T>` reference will fail at runtime. This commonly affects dynamic component creation, lazy-loaded modals, and micro-frontend shells — audit all `createComponent` call sites before upgrading.
- **TypeScript 6.0 is required.** If your build chain (IDE, CI, webpack/esbuild config) pins TypeScript to 5.x, the Angular 22 compiler will refuse to compile. Upgrade TypeScript first and resolve any new strict-mode compilation errors before touching Angular packages.
- **The HTTP backend switch to `FetchBackend` breaks XHR upload progress.** Applications using `reportProgress: true` for file uploads will silently stop receiving `UploadProgress` events. Add `provideHttpClient(withXhr())` and migrate to `reportUploadProgress: true` before upgrading — the regression is invisible at compile time and only manifests at runtime.
- **i18n and SVG security hardening may break existing templates.** If your templates bind dynamically to SVG animation attributes, use custom attributes in ICU messages, or translate `<iframe src>`, these will be blocked or silently dropped after upgrade. Run a full i18n and SVG audit before deploying to production.
