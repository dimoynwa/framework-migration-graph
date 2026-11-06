# Angular 20.0.0 → 20.1.0 — Filtered Migration Report

- **Framework:** Angular
- **Range:** 20.0.0 → 20.1.0
- **Entity source:** dossier

---

## 🔴 Breaking Changes

| # | JIRA | Title | Impact | Sources |
| :--- | :--- | :--- | :--- | :--- |
| 1 | N/A | Minimum Node.js support raised to 20.19, 22.12, and 24.0 | Angular 20. | https://github.com/angular/angular/commit/8f65223bd83ee5cdbff6a3c8e99f85d1c69f5375, https://github.com/angular/angular-cli/pull/30349, https://github.com/angular/angular/pull/61499 |

## 🟠 Mandatory Migrations — Major Component Upgrades

| # | JIRA | Title | Impact | Sources |
| :--- | :--- | :--- | :--- | :--- |
| 1 | N/A | TypeScript removed from @angular/compiler linker; now an optional peer dependency | The linker inside @angular/compiler no longer imports TypeScript barrel files, removing a 500ms to 1s compilation overhead, and TypeScript was dropped from the compiler package's dependencies (only tslib remains) and made an optional peer dependency. | https://github.com/angular/angular/commit/e9fcbb8af12e7b4370d2e03e6004f3f2fe02c981, https://github.com/angular/angular/pull/61618 |

## 🟡 Behavioral Changes

| # | JIRA | Title | Impact | Sources |
| :--- | :--- | :--- | :--- | :--- |
| 1 | N/A | Compiler reports parser errors only on the invalid expression | The compiler's Parser previously kept a single instance-level errors array shared by all expression ASTs, so one invalid binding propagated duplicate errors to every other AST in the template. | https://github.com/angular/angular/commit/5a76826d266b4ed0ef863221571e4b6b1b16182f, https://github.com/angular/angular/pull/61793 |
| 2 | N/A | NG8109 diagnostic now flags negated signal references in templates | The compiler-cli extended diagnostic interpolatedSignalNotInvoked (NG8109) now unwraps a PrefixNot AST node, so signals referenced with `! | https://github.com/angular/angular/commit/b7ab5fa2562524a0e8dfa4f3dff740ec2d31b4c7, https://github.com/angular/angular/pull/59970 |
| 3 | N/A | Rename `_geminiAllowEmitDeclarationOnly` to `_experimentalAllowEmitDeclarationOnly` | The experimental compiler-cli flag that enables fast type declaration emission was renamed from `_geminiAllowEmitDeclarationOnly` to `_experimentalAllowEmitDeclarationOnly` in the compiler options. | https://github.com/angular/angular/commit/77fa204ad16fef561c009fcef0ab1fb92a37f986, https://github.com/angular/angular/pull/61353 |
| 4 | N/A | fix(forms): Allow ControlState as reset arguments for FormGroup/FormRecord | Typed FormGroup and FormRecord reset() now accept ControlState (FormControlState) objects per control instead of only standalone values, via the new internal type ɵFormGroupArgumentValue / ɵFormRecordArgumentValue. | https://github.com/angular/angular/commit/610bebfce98d879677244b2ef08b24886891ca76, https://github.com/angular/angular/pull/55860 |
| 5 | N/A | fix(forms): improve select performance (#61949) | SelectControlValueAccessor no longer writes the select value synchronously while option elements are created, removed, or re-valued; NgSelectOption instead queues a single deferred write via _writeValueAfterRender(), which removes the exponential _compareWith/_compareValue calls and fixes delayed option removal with @angular/animations. | https://github.com/angular/angular/commit/4f0221e1933675b24bdbf95be3825fdacee13c00, https://github.com/angular/angular/pull/61949 |

## 🔵 Notable New Capabilities

| # | JIRA | Title | Impact | Sources |
| :--- | :--- | :--- | :--- | :--- |
| 1 | N/A | NgOptimizedImage adds decoding input with auto and sync defaults | NgOptimizedImage from @angular/common now exposes a decoding input and proxies it onto the host <img> element. | https://github.com/angular/angular/commit/ef10aa400585fb66e1afde08be0f9fd9a70ce7f2, https://github.com/angular/angular/pull/61905 |
| 2 | N/A | Compiler support for new binary assignment operators in templates | The Angular template expression parser and the `Binary` AST node in `@angular/compiler` now support the assignment operators `+=`, `-=`, `*=`, `/=`, `%=`, `**=`, `&&=`, ` =`, and `? | https://github.com/angular/angular/commit/0dcf230d52694e6d3d6e55d6e675d55f9cf236bc, https://github.com/angular/angular/pull/62064 |
| 3 | N/A | Experimental fast type declaration emission in compiler-cli | @angular/compiler-cli 20. | https://github.com/angular/angular/commit/e62fb359d6da8e0458b18f24e6bff60602f93fc6, https://github.com/angular/angular/pull/61334 |
