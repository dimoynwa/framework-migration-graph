# Angular — documented changes (extract-only)

- **Framework key:** `angular`
- **Resolved range:** `20.2.0` → `20.3.0`
- **Generated (UTC):** 2026-11-05T10:57:16Z
- **Triage:** nimble · questions v1 · kept 3 / dropped 0 / error 0

---


## `20.2.0` → `20.3.0`

| Type | Confidence | Source | Statement | Triage | Category | Cat. prob | P(action) | Impact | Triage source |
|------|------------|--------|-----------|--------|----------|-----------|-----------|--------|---------------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | The server-side bootstrapping process has been changed to eliminate the reliance on a global platform injector. | keep | behavior_change | 0.46 | 0.65 | 0.90 | model |
| behavioral | inferred | https://github.com/angular/angular/commit/a3f808d7c8cc59a4fd69f2e4b8d21a6510efa046 | Title: fix: remove refresh button from transfer state tab (#63592) Commit: TransferState is only written into the DOM once during SSR and is not kept in sync with the runtime state on the client. Pressing the refresh button always re-reads the initial serialized script tag, which never changes after bootstrap. Release:   [a3f808d7c8](https://github.com/angular/angular/commit/a3f808d7c8cc59a4fd69f2e4b8d21a6510efa046)   fix    remove refresh button from transfer state tab ([#63592](https://github.com/angular/angular/pull/63592))   | keep | behavior_change | 0.90 | 0.61 | 0.84 | model |
| breaking | confirmed | https://github.com/angular/angular/commit/6117ccee2e1507fb00549cd70e064282645db803 | Title: feat(core): introduce `BootstrapContext` for improved server bootstrapping (#63636) Commit: This commit introduces a number of changes to the server bootstrapping process to make it more robust and less error-prone, especially for concurrent requests. Previously, the server rendering process relied on a module-level global platform injector. This could lead to issues in server-side rendering environments where multiple requests are processed concurrently, as they could inadvertently share or overwrite the global injector state. The new approach introduces a `BootstrapContext` that is passed to the `bootstrapApplication` function. This context provides a platform reference that is scoped to the individual request, ensuring that each server-side render has an isolated platform injector. This prevents state leakage between concurrent requests and makes the overall process more reliable. Breaking: The server-side bootstrapping process has been changed to eliminate the reliance on a global platform injector. Before: ```ts const bootstrap = () => bootstrapApplication(AppComponent, config); ``` After: ```ts const bootstrap = (context: BootstrapContext) => bootstrapApplication(AppComponent, config, context); ``` A schematic is provided to automatically update `main.server.ts` files to pass the `BootstrapContext` to the `bootstrapApplication` call. In addition, `getPlatform()` and `destroyPlatform()` will now return `null` and be a no-op respectively when running in a server environment. (cherry picked from commit 8bf80c9d2314b4f2bcf3df83ae01552a6fc49834) Release:   [6117ccee2e](https://github.com/angular/angular/commit/6117ccee2e1507fb00549cd70e064282645db803)   feat   introduce `BootstrapContext` for improved server bootstrapping ([#63636](https://github.com/angular/angular/pull/63636))   | keep | — | — | — | — | rule |

