# Angular — Migration Filter Report

- **Framework:** Angular
- **Range:** `18.0.0` → `19.0.0`
- **Filter applied (UTC):** 2026-06-05

---

## 🔴 Breaking Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | TypeScript < 5.5 Support Dropped | Angular 19 drops support for TypeScript < 5.5. Your build will fail if you are on TypeScript 5.4 or below. Upgrade your `typescript` dependency to `>=5.5` before starting the Angular upgrade. |
| 2 | N/A | `this.foo` Template Property Disambiguation | `this.foo` in templates now always resolves to the component class property, never to a template context variable. Templates that used `this.someVariable` to access a template variable (e.g., inside `*ngFor` or `@for`) will silently read the wrong value. Audit all templates for `this.` usage and remove it where the intent is to read a template-local variable. |
| 3 | N/A | `Router.errorHandler` Property Removed | The `Router.errorHandler` property has been removed. Replace it with the `withNavigationErrorHandler()` provider function, or provide a custom `ErrorHandler` at the root injector level. |
| 4 | N/A | `BrowserModule.withServerTransition` Removed | The deprecated `BrowserModule.withServerTransition()` static method has been removed. Replace all call sites with the `APP_ID` DI token to set the server-rendered application ID. |
| 5 | N/A | `KeyValueDiffers.factories` Property Removed | The deprecated `factories` property on `KeyValueDiffers` has been removed. Remove any direct access to `KeyValueDiffers.factories`; use the public differ API instead. |
| 6 | N/A | RxJS 6.x Runtime Incompatibility | A confirmed breaking change affects applications using RxJS 6.x. Upgrade to RxJS 7.x before migrating to Angular 19 to prevent runtime failures. |
| 7 | N/A | `createComponent` Empty `projectableNodes` Behavior | Passing an empty array entry in `projectableNodes` to `createComponent` now renders the default `<ng-content>` fallback rather than nothing. If you depend on empty slots suppressing fallback content, pass `[document.createTextNode('')]` instead of `[]` to preserve the old behavior. |

## 🟠 Mandatory Migrations — Major Component Upgrades

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | Standalone `true` Default for All Declarations | All components, directives, and pipes are now `standalone: true` by default in Angular 19. Any declaration still registered in an `@NgModule` must be explicitly marked `standalone: false`. Run `ng update @angular/core` to apply the automatic schematic. Without this migration, `@NgModule` declarations will be treated as standalone and may fail to bootstrap. |
| 2 | N/A | `ExperimentalPendingTasks` Renamed to `PendingTasks` | The `ExperimentalPendingTasks` service has been promoted to stable and renamed `PendingTasks`. Update all imports from `@angular/core` and all constructor/injection usage. |
| 3 | N/A | `ng add @angular/localize` `name` Option Removed | The `name` option in the `ng add @angular/localize` schematic has been removed in favour of the `project` option. Update any build scripts or CI steps that pass `--name` to use `--project` instead. |

## 🟡 Behavioral Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | `effect()` Execution Timing Changed | Effects triggered outside change detection now run as part of the next application tick; effects triggered during change detection run after it completes. The `allowSignalWrites` flag is now a no-op. Review any code that depends on effect scheduling order and update tests that assert on synchronous effect execution. |
| 2 | N/A | `afterRender` / `afterNextRender` API Redesigned | The phase-flag API for `afterRender` and `afterNextRender` was redesigned in v18.1. The old API (passing a `{read, write, mixedReadWrite}` object with phase flags) is now deprecated and will be removed in a future version. Run the provided migration schematic: `ng generate @angular/core:after-render-phase`. |
| 3 | N/A | `ComponentFixture.autoDetect` Aligned with Production | `ComponentFixture.autoDetect` now triggers change detection exactly as it does in production (zone-driven), removing the previous extra synchronous check. Tests that relied on implicit eager detection may now miss updates — add explicit `fixture.detectChanges()` calls where needed. |
| 4 | N/A | CSS Pseudo-Selector Scoping Changed | Angular 19 corrects scoping for `:where()`, `:is()`, and `:host-context()` pseudo-selectors. For example, `:where(:host)` previously compiled to `:where()[ng-host]` and now compiles to `:where([ng-host])`. Verify rendered styles for components using these selectors after upgrade, especially if selector specificity is relied upon. |
| 5 | N/A | `Resolve` Interface Return Type Expanded | The `Resolve<T>` interface return type now includes `RedirectCommand` alongside `T`. Strict TypeScript implementations that do not handle `RedirectCommand` may produce type errors. Update resolver return types and add `RedirectCommand` handling if applicable. |
| 6 | N/A | `ApplicationRef.tick` Errors Rethrown in TestBed | Errors thrown during `ApplicationRef.tick()` are now rethrown and surface as test failures in `TestBed`. Tests that previously passed despite tick-time component errors will now fail. Fix the underlying component errors or wrap assertions appropriately. |

## 🟡 Deprecations

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | `afterRender` Phase Flag API Deprecated | The phase-flag style `{read, write, mixedReadWrite}` options for `afterRender` / `afterNextRender` are deprecated as of v18.1. Plan migration to the new callback-based API using `ng generate @angular/core:after-render-phase` before the API is removed. |
| 2 | N/A | `ignoreChangesOutsideZone` Option Deprecated | The `ignoreChangesOutsideZone` option in `NgZone` configuration is deprecated as of v18.2. Remove it from your zone configuration; changes outside the zone are now managed by the zoneless scheduler. |

## 🔵 Notable New Capabilities

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | Signal APIs Stabilized (`input`, `output`, `model`, queries) | `input()`, `output()`, `model()`, and signal-based query APIs (`viewChild`, `viewChildren`, `contentChild`, `contentChildren`) are now stable in Angular 19. Use the `ng generate` schematics (`@angular/core:signal-input-migration`, `@angular/core:output-migration`, `@angular/core:signal-queries-migration`) to incrementally migrate `@Input`, `@Output`, and `@ViewChild` decorators. |
| 2 | N/A | `@let` Template Syntax Stabilized | The `@let` declaration syntax for template-local variables is now stable. No migration required; continue using it or adopt it to replace complex `as` bindings in templates. |
| 3 | N/A | Incremental Hydration Public API | A public API for on-demand SSR hydration is available. Configure it by adding `withIncrementalHydration()` to `provideClientHydration()` and use `hydrate on <trigger>` or `hydrate when <condition>` on `@defer` blocks. |
| 4 | N/A | `linkedSignal` Reactive Primitive | The `linkedSignal()` API provides a writable signal that stays linked to (and can reset from) a source signal. Available as a stable primitive in Angular 19. |
| 5 | N/A | `resource()` and `rxResource()` Experimental APIs | New experimental APIs for managing async resource dependencies are available in v19. These are developer previews — evaluate for future adoption but do not use in production without acknowledging the instability. |

---

## Summary by Priority

| Priority Level | Count | Description |
| :--- | :--- | :--- |
| 🔴 **Breaking** | 7 | Must fix before migrating. |
| 🟠 **Mandatory** | 3 | Security CVEs, component upgrades, security config. |
| 🟡 **Behavioral / Deprecation** | 8 | Assess impact and adjust accordingly. |
| 🔵 **New Capabilities** | 5 | Optional but recommended to leverage. |

## 🚨 Most Critical Items for Migration
- **TypeScript must be upgraded to ≥5.5 before Angular 19**: The build toolchain will reject TypeScript 5.4 and below outright — upgrade TypeScript first as a prerequisite step.
- **All `@NgModule` declarations must be marked `standalone: false`**: With `standalone: true` as the new default, any component, directive, or pipe still declared in an `@NgModule` will be misinterpreted and fail to bootstrap. Run `ng update @angular/core` to apply the automatic migration schematic.
- **Audit all templates for `this.foo` property reads**: Angular 19 always resolves `this.foo` to the component class property — templates relying on `this.` to access `*ngFor`/`@for` context variables will silently read the wrong value, causing subtle runtime bugs.
- **Replace `BrowserModule.withServerTransition()` and `Router.errorHandler`**: Both APIs have been hard-removed. Compile errors will appear immediately on upgrade; migrate to `APP_ID` token and `withNavigationErrorHandler()` respectively before cutting over.
- **RxJS 6.x users must upgrade to RxJS 7.x first**: A confirmed breaking change makes Angular 19 incompatible with RxJS 6.x at runtime — treat this as a prerequisite migration alongside the TypeScript upgrade.
