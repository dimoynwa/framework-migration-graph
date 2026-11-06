# Angular 19.1.0 → 19.2.0 — Filtered Migration Report

- **Framework:** Angular
- **Range:** 19.1.0 → 19.2.0
- **Entity source:** dossier

---

## 🔴 Breaking Changes

| # | JIRA | Title | Impact | Sources |
| :--- | :--- | :--- | :--- | :--- |
| 1 | N/A | feat(core): support streaming resources (#59573) | `resource()` gains a streaming variant: `ResourceOptions<T, R>` is now a union of `PromiseResourceOptions` and `StreamingResourceOptions` extending a new `BaseResourceOptions`, and `RxResourceOptions` no longer extends `Omit<ResourceOptions, 'loader'>`. | https://github.com/angular/angular/commit/bc2ad7bfd37a61992b550943de5da0eab2eec98b, https://github.com/angular/angular/pull/59573 |

## 🟡 Behavioral Changes

| # | JIRA | Title | Impact | Sources |
| :--- | :--- | :--- | :--- | :--- |
| 1 | N/A | Skip Hydration diagnostic NG8108 is now active | The extended diagnostic skipHydrationNotStatic (NG8108) existed but was never registered in the list of diagnostics that run, so referencing it in extendedDiagnostics. | https://github.com/angular/angular/commit/5b20bab96d20fe89b5cc4b4af28edbaae2604da1, https://github.com/angular/angular/pull/59576 |
| 2 | N/A | setThrowInvalidWriteToSignalError handler receives the signal node | throwInvalidWriteToSignalError now takes the SignalNode<T> being written and forwards it to the handler, so setThrowInvalidWriteToSignalError's callback signature changed from () => never to <T>(node: SignalNode<T>) => never. | https://github.com/angular/angular/commit/2588985f433b20a6a5a8d239347291f5d6fb2451, https://github.com/angular/angular/pull/59600 |
| 3 | N/A | Defer afterRender until after first CD | Angular re-applied the fix that defers registration of view-associated afterRender/afterNextRender hooks until after the view's first render pass, storing the sequences on the LView and adding them via addAfterRenderSequencesForView during refreshView. | https://github.com/angular/angular/commit/6789c7ef947952551d7598fe37a3d86093b75720, https://github.com/angular/angular/pull/59455, https://github.com/angular/angular/pull/59551 |
| 4 | N/A | platform-server decoupled from animations; animations auto-disable on server | On the server, `provideAnimations()` now resolves `AnimationDriver` to `NoopAnimationDriver` and `ANIMATION_MODULE_TYPE` to `'NoopAnimations'` because `ngServerMode` is set, so `@angular/platform-server` no longer imports `NoopAnimationsModule` and drops its `@angular/animations` peer dependency. | https://github.com/angular/angular/commit/e6cb411e4393a4b1f5852d3d7c5b9622504399b1, https://github.com/angular/angular/pull/59762, https://github.com/angular/angular/commit/fc5d187da5e8895d60caa35b7b59e234998eddf0 |
