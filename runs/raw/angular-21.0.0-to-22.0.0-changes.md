# Angular — documented changes (extract-only)

- **Framework key:** `angular`
- **Resolved range:** `21.0.0` → `22.0.0`
- **Generated (UTC):** 2026-06-05T14:08:03Z

---


## `21.0.0` → `21.0.1`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [39c577bc36](https://github.com/angular/angular/commit/39c577bc362b263896b38c9486131d4342b8f1a8)   fix    do not type check native controls with ControlValueAccessor   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [8d3a89a477](https://github.com/angular/angular/commit/8d3a89a477e273b9b2223b6db775955e35105963)   fix    escape angular control flow in jsdoc                          |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [bc34083d34](https://github.com/angular/angular/commit/bc34083d349a7d30efb43df97de0509fd85a1996)   fix    ignore non-existent files                                     |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [0ea1e07174](https://github.com/angular/angular/commit/0ea1e071742a031d9afb7a39f8e23082cd88ca2e)   fix    apply bootstrap-options migration to `platformBrowserDynamic`   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [70507b8c1c](https://github.com/angular/angular/commit/70507b8c1ce733b8232a12fa45037ee219b5b102)   fix    debug data causing memory leak for root effects                 |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [a55482fca3](https://github.com/angular/angular/commit/a55482fca3b7e4f39d95f8ff236b6619e59b8190)   fix    notify profiler events in case of errors                        |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [49ad7c6508](https://github.com/angular/angular/commit/49ad7c650818ee7db321a24c89282dbf9bb250f3)   fix    use injected `DOCUMENT` for `CSP_NONCE`                         |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [cc1ec09931](https://github.com/angular/angular/commit/cc1ec099315b0f429d0b0f07c9b1bf686668db6b)   perf   avoid repeat searches for field directive                       |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [7d5c7cf99a](https://github.com/angular/angular/commit/7d5c7cf99aa5c6490f8bea950b04bd56073582a1)   feat   add DI option for classes on `Field` directive          |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [8acf5d2756](https://github.com/angular/angular/commit/8acf5d27563ec51cc76971732d50e1f4142a3fe3)   fix    allow dynamic `type` bindings on signal form controls   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [de5fca94c5](https://github.com/angular/angular/commit/de5fca94c5cfafa9098d9ee270f448b90d4ac06f)   fix    run reset as untracked                                  |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [3240d856d9](https://github.com/angular/angular/commit/3240d856d942727372a705252f7c8c115394a41e)   fix    prevent XSRF token leakage to protocol-relative URLs   |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [f394215b14](https://github.com/angular/angular/commit/f394215b14d59c49e1433472ecdd2fd5547cc769)   fix    detect structural ngTemplateOutlet and ngComponentOutlet   |

## `21.0.1` → `21.0.2`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [78fd159b78](https://github.com/angular/angular/commit/78fd159b78d32cb8b94891e3fc6013076d7838af)   fix    prevent XSS via SVG animation `attributeName` and MathML/SVG URLs   |

## `21.0.2` → `21.0.3`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [5a80a48e96](https://github.com/angular/angular/commit/5a80a48e962f72825050202198b32abbfee66714)   fix    avoid allocating an object for signals in production mode   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [1f1856e897](https://github.com/angular/angular/commit/1f1856e897e0a10e2ca6d934c80fd69d1ac06210)   fix    check that field radio button values are strings            |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [8c3304c766](https://github.com/angular/angular/commit/8c3304c766131b031b736ee3fe2ec9c9a42fbe07)   fix    run animation queue in environment injector context                                                                  |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [4bb085311e](https://github.com/angular/angular/commit/4bb085311e24966ef2dd673f23746988c449c7ff)   fix    unable to inject viewProviders when host directive with providers is present                                         |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [609699ae17](https://github.com/angular/angular/commit/609699ae1781a9160b0f474b7ebe0998221c0722)   perf   tree shake unused dynamic `[field]` binding instructions ([#65599](https://github.com/angular/angular/pull/65599))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [6b4ab876e8](https://github.com/angular/angular/commit/6b4ab876e811b4e3a6f9617a2b379f62cf187403)   feat   Allows transforms on `FormUiControl` signals                                                   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [a5dbd4b382](https://github.com/angular/angular/commit/a5dbd4b382417fc111d6a622862a015c47027a41)   fix    support dynamic `[field]` bindings ([#65599](https://github.com/angular/angular/pull/65599))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [20474d3f0f](https://github.com/angular/angular/commit/20474d3f0fd7c64071add6e84acf720627e5c19b)   fix    enable XSRF protection for same-origin absolute URLs   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [48b89f9fbe](https://github.com/angular/angular/commit/48b89f9fbe16acff8b2f3f37853e745ed43d3a32)   fix    handle errors from view transition finished promise   |

## `21.0.3` → `21.0.4`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [f901cc9eb32](https://github.com/angular/angular/commit/f901cc9eb328bed74fd7f09607e54154254d4a97)   perf   chain query creation instructions   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [65297c62011](https://github.com/angular/angular/commit/65297c62011ae353f8555738688a83a5fba5ea4e)   fix    expand type for native controls with a dynamic type   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [f254ff4f2e0](https://github.com/angular/angular/commit/f254ff4f2e014064b4d6073341dec0c5a7a754bf)   feat   expose element on signal forms `Field` directive                                                          |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [5880fbc73c6](https://github.com/angular/angular/commit/5880fbc73c6ac42976b3ada9803965bc20d047db)   feat   redo the signal forms metadata API                                                                        |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [55fc677cef4](https://github.com/angular/angular/commit/55fc677cef4409302bc474ff316d392097a034e7)   fix    add signals for dirty, hidden, and pending states in custom controls                                      |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [cbb10179c80](https://github.com/angular/angular/commit/cbb10179c8098f6a20b0bc365a492f14e4d2a51a)   fix    allow resetting with empty string                                                                         |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [bf1c12cd932](https://github.com/angular/angular/commit/bf1c12cd932028dc4bb50914c64bbb6d882b6ec1)   fix    memoize reads of child fields in signal forms ([#65802](https://github.com/angular/angular/pull/65802))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [6d7475582f9](https://github.com/angular/angular/commit/6d7475582f95720b4487f663d339a18a25374481)   fix    Reuse key in parent in compat structure                                                                   |

## `21.0.4` → `21.0.5`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| deprecation | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [69d243abb74](https://github.com/angular/angular/commit/69d243abb7438c37b9ef763755f8fb7fdee165be)   fix    avoid false-positive deprecation when using `InjectionToken` with factory only   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [4fd2b722b40](https://github.com/angular/angular/commit/4fd2b722b4054181a6e5f09a3cc657ae05541782)   fix    fix signal forms type error   |

## `21.0.5` → `21.0.6`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | The shape of `SignalFormsConfig.classes` has changed |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | (cherry picked from commit ae0c59028a2f393ea5716bf222db2c38e7a3989f) |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [4c8fb3631d](https://github.com/angular/angular/commit/4c8fb3631d58e22d693aba0b89243f2e9ecb0807)   fix   throw better errors for potential circular references   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [48492524ea](https://github.com/angular/angular/commit/48492524ea4adfa232b0daee0d955924be31ebea)   fix   use mutable ResponseInit type for RESPONSE_INIT token   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [81772b420d](https://github.com/angular/angular/commit/81772b420dcda2cbe2a8cb75e50c6da2e1ecdc68)   feat   pass field directive to class config   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [729b96476b](https://github.com/angular/angular/commit/729b96476b73f1670a0f7c6ab3f36be9d38ebcac)   refactor   rename field to fieldTree in FieldContext and ValidationError   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [e0694df3ec](https://github.com/angular/angular/commit/e0694df3eccae3d31a4ea537dffe1db1368ef34a)   fix   avoid interpolation highlighting inside @let   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [5047be4bc1](https://github.com/angular/angular/commit/5047be4bc1c6f6016263703c743f8033f669f0ee)   fix   Prevent language service from crashing on suggestion diagnostic errors   |

## `21.0.6` → `21.0.7`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [8e808740c9](https://github.com/angular/angular/commit/8e808740c9311daa0f1c9bab8596ed5e54bdcc6a)   fix   better types for a few expression AST nodes   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [63b1cdcf70](https://github.com/angular/angular/commit/63b1cdcf70e6de448e8fa4ba1732d7bd7b5400d1)   fix   produce accurate span for typeof and void expressions   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [3c3ae0cb64](https://github.com/angular/angular/commit/3c3ae0cb64bb112d7167fd9b0bf7739f0c9e6a39)   fix   provide location information for literal map keys   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [523dbaf1c3](https://github.com/angular/angular/commit/523dbaf1c3646ce27f1cf2e4cfc84c730fea8da9)   fix   stop ThisReceiver inheritance from ImplicitReceiver   |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [4d9c4567ed](https://github.com/angular/angular/commit/4d9c4567edfb8dd424a3336ef54ffdfc6ca7c15f)   fix   ensure component import diagnostics are reported within the `imports` expression   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [cd405685af](https://github.com/angular/angular/commit/cd405685afbfad530de7fb841ad352d2b702a9a4)   fix   fix up spelling of diagnostic   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [778460fcca](https://github.com/angular/angular/commit/778460fccac13d8667bb53fa24ba977a930c0253)   fix   support qualified names in `typeof` type references   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [7c74674eb0](https://github.com/angular/angular/commit/7c74674eb07491f808f79976e3e21787a841aefb)   fix   avoid leaking view data in animations   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [0edbee4550](https://github.com/angular/angular/commit/0edbee4550e85b933e9bd2ba3c5511ef6fbf7304)   fix   explicitly cast signal node value to String   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [f9c29572d2](https://github.com/angular/angular/commit/f9c29572d28feef878c73edad562b3a6451825a6)   fix   sanitize sensitive attributes on SVG script elements   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [e3fba182f9](https://github.com/angular/angular/commit/e3fba182f90a2673040cf267a970c54c07d4840f)   feat   add `[formField]` directive   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [561772b152](https://github.com/angular/angular/commit/561772b152458e1d91d4bf3ef45d9645a731f2b1)   fix   allow custom controls to require `dirty` input   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [f0fb1d8581](https://github.com/angular/angular/commit/f0fb1d8581671ca499bcb4790b0549825eb36a91)   fix   allow custom controls to require `hidden` input   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ec110f170b](https://github.com/angular/angular/commit/ec110f170bbba95f023c8ae0e4429c35bfedc572)   fix   allow custom controls to require `pending` input   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ae1dc16bb0](https://github.com/angular/angular/commit/ae1dc16bb0d30b6e87b0f98b7989e6685d856e31)   fix   clean up abort listener after timeout   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [9748b0d5da](https://github.com/angular/angular/commit/9748b0d5da6ffb1fd2498b23cc452240f46e0549)   fix   support custom controls with non signal-based models   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [6bd22df987](https://github.com/angular/angular/commit/6bd22df987e433a9e3cb759e35eb6403991cf4b7)   fix   Support readonly arrays in signal forms   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [41cd4a6af8](https://github.com/angular/angular/commit/41cd4a6af800cf7807c46862c99ae036457d8fa7)   fix   Fix RouterLink href not updating with `queryParamsHandling`   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [5e9e09aee0](https://github.com/angular/angular/commit/5e9e09aee0c08901d2a4d48b60bd13692c73e76e)   fix   handle errors from view transition `updateCallbackDone` promise   |

## `21.0.7` → `21.0.8`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [a6a2621bf9](https://github.com/angular/angular/commit/a6a2621bf9df02584e4079f4a804278fc2060a9c)   fix   fix memory leak with event replay   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [5239e471a1](https://github.com/angular/angular/commit/5239e471a1f887574c6703c0497e5854304cce4e)   fix   handle cancelled traversals in fake navigation   |

## `21.0.8` → `21.0.9`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [82d556a8fb](https://github.com/angular/angular/commit/82d556a8fb38cd2024e3d098c55254305ba12b6b)   fix   Ensure the control instruction comes after the other bindings   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [0055f3cc79](https://github.com/angular/angular/commit/0055f3cc79f387b8dec6ce5e1a33fad5486f9341)   fix   Rename signal form [field] to [formField]   |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [e4bfa5c9e7](https://github.com/angular/angular/commit/e4bfa5c9e7feec48d3c4e9425a21a2ccf6532bdb)   fix   prevent duplicate imports in common-to-standalone migration   |

## `21.0.9` → `21.1.0`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| deprecation | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | `VERSION` from `@angular/upgrade` is deprecated. Please use the entry from `@angular/upgrade/static` instead. |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [d8790972be](https://github.com/angular/angular/commit/d8790972bea4c59a208219dd36d158b5d7e4fdde)   feat   Add custom transformations for Cloudflare and Cloudinary image loaders   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [a6b8cb68af](https://github.com/angular/angular/commit/a6b8cb68afaded6999ee68f495512be1a9932ae4)   feat   support custom transformations in ImageKit and Imgix loaders   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [640693da8e](https://github.com/angular/angular/commit/640693da8e667c015662246152236585d9b24e7f)   feat   Add support for multiple swich cases matching   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [0ad3adc7c6](https://github.com/angular/angular/commit/0ad3adc7c6d4094f1e3432a3f2e3bdc9862cb4fa)   fix   Support empty cases   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [99ad18a4ee](https://github.com/angular/angular/commit/99ad18a4ee82ecc5524106d1d403ccfa9bae2304)   feat   Add stability debugging utility   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [a0dfa5fa86](https://github.com/angular/angular/commit/a0dfa5fa86f40520b0e368a021b3c72009a45e8e)   feat   support rest arguments in function calls   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [6e18fa8bc9](https://github.com/angular/angular/commit/6e18fa8bc9d7e6801e2e89e635c2f759dc422317)   feat   support spread elements in array literals   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [e407280ab5](https://github.com/angular/angular/commit/e407280ab53cde5f93c3a643457c848845c6ec8b)   feat   support spread expressions in object literals   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [06be8034bb](https://github.com/angular/angular/commit/06be8034bb9b9adfc07ab0d40cd87c6ae5de02de)   fix   Microtask scheduling should be used after any application synchronization   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [b4f584cf42](https://github.com/angular/angular/commit/b4f584cf42235c94bb8389fa55bc634e23d7b010)   fix   return `StaticProvider` for `providePlatformInitializer`   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [1ea5c97703](https://github.com/angular/angular/commit/1ea5c97703ad3c6d8e4cb1b4297eec57629ce117)   feat   allow focusing bound control from field state   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ec9dc94cee](https://github.com/angular/angular/commit/ec9dc94ceeb3c026c64e01c6889b7f5c6fd25a66)   feat   add `context` to `createApplication`   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ab67988d2e](https://github.com/angular/angular/commit/ab67988d2e5242eff0034483f984428d684acd02)   feat   resolve JIT resources in `createApplication`   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [5edceffd04](https://github.com/angular/angular/commit/5edceffd0431f5a25e111a731db521e966b91f86)   feat   add controls for route cleanup   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [a03c82564d](https://github.com/angular/angular/commit/a03c82564da6824e199ff48d5249ea8708040951)   feat   Add scroll behavior controls on router navigation   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [e44839b016](https://github.com/angular/angular/commit/e44839b01640505e554fff16f24e08f282a557c0)   feat   Add standalone function to create a comptued for isActive   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [c25d749d85](https://github.com/angular/angular/commit/c25d749d85374fff7745980cd9bb2673c661105a)   feat   Execute RunGuardsAndResolvers function in injection context   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [1c00ab42f8](https://github.com/angular/angular/commit/1c00ab42f8714f2775ed75bbf3cdf0fd44ee32c3)   feat   extend paramters of RedirectFunction to include paramMap and queryParamMap   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [7003e8d241](https://github.com/angular/angular/commit/7003e8d2417660f71b3a2a017aff3e650c8d9646)   feat   Publish Router's integration with platform Navigation API as experimental   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [c84d372778](https://github.com/angular/angular/commit/c84d37277874cf7cbd7582a295d796ff113b9cc1)   feat   Support wildcard params with segments trailing ([#64737](https://github.com/angular/angular/pull/64737))   |
| deprecation | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [75fe8f8af9](https://github.com/angular/angular/commit/75fe8f8af9488bae6f7068b64d44500643c5d63f)   refactor   deprecate `VERSION` export   |

## `21.1.0` → `21.1.1`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [0e1f1ed573](https://github.com/angular/angular/commit/0e1f1ed5732f3bb4d5dfbd1f0ee5a5be840594e4)   fix   drop .tsx extension for generated relative imports   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [05adfcf8f2](https://github.com/angular/angular/commit/05adfcf8f26013ac20c38f2b08847b5142e4fd85)   fix   handle Set in class bindings   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [d89a80a970](https://github.com/angular/angular/commit/d89a80a970d9590df0509d8b94090904a99b7aca)   feat   Ability to manually register a form field binding in signal forms   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [cb75f9ce85](https://github.com/angular/angular/commit/cb75f9ce85160b2e4359610c06294929ac1169c0)   fix   fix control value syncing on touch   |

## `21.1.1` → `21.1.2`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [9f99b14882](https://github.com/angular/angular/commit/9f99b14882bc4f883aa33295856010a8bca900fa)   fix   only touch visible, interactive fields on submit   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [c57b0355b5](https://github.com/angular/angular/commit/c57b0355b51f5aee5abd822f203fc3bcc3e85acd)   fix   Detect local project version on creation   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [21ecdc036a](https://github.com/angular/angular/commit/21ecdc036a46c487d6c5b6bd25c2bbc3e53a60f9)   fix   Do not intercept reload events with Navigation integration   |

## `21.1.2` → `21.1.3`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [2b254bc050](https://github.com/angular/angular/commit/2b254bc0508b73aab8991c3b1a9a703c339cb735)   fix   `linkedSignal.update` should propagate errors   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [e5110b4fa1](https://github.com/angular/angular/commit/e5110b4fa155e4669ed507f3460d2d29026a28ab)   fix   export DirectiveWithBindings   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [2cf4da0ea1](https://github.com/angular/angular/commit/2cf4da0ea11f5746eb7ae4dfd775f757576e4d98)   fix   hold constructors weakly in DepsTracker cache   |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [70a5b651be](https://github.com/angular/angular/commit/70a5b651be29f1421eb25150b560bfe154aad6bc)   fix   prevent element duplication with dynamic components   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [6f75b6e3f6](https://github.com/angular/angular/commit/6f75b6e3f60dc2a4f33e13562649931dc95eb52b)   fix   Resolves debounce promise on abort in debounceForDuration   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [4c7126d23b](https://github.com/angular/angular/commit/4c7126d23be3e43b1d5bd6f2fb13119d185c3682)   fix   add support for unit-test builder in ng-add schematic   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [d6268c0bbb](https://github.com/angular/angular/commit/d6268c0bbbdc92abaaaeb8eebee3bc45decab9c9)   fix   limit UrlParser recursion depth to prevent stack overflow   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [49a36f4cc7](https://github.com/angular/angular/commit/49a36f4cc7254420bc34fff4e0f0242e00970280)   perf   Use .bind to avoid holding other closures in memory   |

## `21.1.3` → `21.1.4`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [caab23dfe6](https://github.com/angular/angular/commit/caab23dfe6acf06c3b859af091f5e078b08f1c4c)   fix   add geolocation element to schema   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [2b99eaa019](https://github.com/angular/angular/commit/2b99eaa019b5551a2e2fcf9ff8cd0a796e1e857b)   fix   capture animation dependencies eagerly to avoid destroyed injector   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [d6aeac504c](https://github.com/angular/angular/commit/d6aeac504c6181f15e5d8afdca3d9c3e3b32652c)   fix   Fix flakey test due to document injection   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [0d1acd0165](https://github.com/angular/angular/commit/0d1acd0165511b57ce853f29486d9b92d0215959)   feat   support signal-based schemas in validateStandardSchema   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [3905015ccc](https://github.com/angular/angular/commit/3905015ccc53399a606dd8e4f3c4d0cce628a08e)   fix   correctly parse ArrayBuffer and Blob in transfer cache   |

## `21.1.4` → `21.1.5`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | <a name="21.1.5"></a> (# 21.1.5 (2026-02-18)) |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | <!-- CHANGELOG SPLIT MARKER --> |

## `21.1.5` → `21.1.6`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | Angular now only applies known attributes from HTML in translated ICU content. Unknown attributes are dropped and not rendered. |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [31d3d56496](https://github.com/angular/angular/commit/31d3d564961b701bda96d94731fbed72c01975fa)   fix   fix LCP image detection with duplicate URLs   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [24b578ce90](https://github.com/angular/angular/commit/24b578ce90ed50022f62584671aef01d4c5dd7b2)   fix   detect uninvoked functions in defer trigger expressions   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [b858309532](https://github.com/angular/angular/commit/b85830953281ff3a1a77bbfe69019d352d509c93)   fix   block creation of sensitive URI attributes from ICU messages   |

## `21.1.6` → `21.2.0`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [18003a33bb](https://github.com/angular/angular/commit/18003a33bb0d6bb09def8a0e5939fa24069696eb)   feat   add an 'outlet' injector option for ngTemplateOutlet   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [8bbe6dc46c](https://github.com/angular/angular/commit/8bbe6dc46c9dc13bafa81a60c7613b84b5ca3761)   feat   Add Location strategies to manage trailing slash on write   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [51cc914807](https://github.com/angular/angular/commit/51cc91480761b7275c15b5600381207f8ca00ee5)   feat   support height in ImageLoaderConfig and built-in loaders   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [72534e2a34](https://github.com/angular/angular/commit/72534e2a3458df4e1bb097973872f00bbb92be42)   feat   Add support for the `instanceof` binary operator   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [95b3f37d4a](https://github.com/angular/angular/commit/95b3f37d4a7d9a38f616d56df746dfcda3c2139b)   feat   Exhaustive checks for switch blocks   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [04ba09a8d9](https://github.com/angular/angular/commit/04ba09a8d9454013bebdd643eacb737642161952)   feat   support `AstVisitor.visitEmptyExpr()`   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ce80136e7b](https://github.com/angular/angular/commit/ce80136e7b9f0024d49fce835cffa024c4505855)   fix   optimize away unnecessary restore/reset view calls   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [3242a61bae](https://github.com/angular/angular/commit/3242a61bae02253d13abb510b666376c665e61ac)   fix   variable counter visiting some expressions twice   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [473dd3e1cb](https://github.com/angular/angular/commit/473dd3e1cbd4fe3fa88ae4d5358eee35c11acb1b)   fix   attach source spans to object literal keys in TCB   |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [a904d9f77b](https://github.com/angular/angular/commit/a904d9f77b56feab407f75f8d0527fa512d5dafb)   fix   support nested component declaration   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [2ea6dfc6c9](https://github.com/angular/angular/commit/2ea6dfc6c9ca11e96a2654510c980419899f8d04)   fix   update diagnostic to flag no-op arrow functions in listeners   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [8d5210c9fe](https://github.com/angular/angular/commit/8d5210c9fedd8abdd810d7a89ec7ee9a1234f5c1)   feat   add ChangeDetectionStrategy.Eager alias for Default   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [92d2498910](https://github.com/angular/angular/commit/92d2498910caed06c182b67e39726e1441418698)   feat   add host node to DeferBlockData ([#66546](https://github.com/angular/angular/pull/66546))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ea2016a6dc](https://github.com/angular/angular/commit/ea2016a6dce58f95ecab7c773d5dcde274354e1a)   feat   add support for nested animations   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [81cabc1477](https://github.com/angular/angular/commit/81cabc14777a3b4966c29d60e1505aca8c29b71c)   feat   add support for TypeScript 6   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [1ba9b7ac50](https://github.com/angular/angular/commit/1ba9b7ac5001b315cc9df78c518964dbf479d647)   feat   resource composition via snapshots   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [d9923b72a2](https://github.com/angular/angular/commit/d9923b72a20972ba6bf728d78f1afac6936ade18)   feat   support arrow functions in expressions   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [a7e8abbb7e](https://github.com/angular/angular/commit/a7e8abbb7e738ba338c3f50c76934c99925954e5)   fix   correctly handle SkipSelf when resolving from embedded view injector   |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [0806ee3826](https://github.com/angular/angular/commit/0806ee38269b664f535e10d4d501b88370d3b44c)   fix   prevent animated element duplication with dynamic components in zoneless mode   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ed78fa05c7](https://github.com/angular/angular/commit/ed78fa05c710ebafb355ae00a85b190a118b6cc4)   fix   Remove note to skip arrow functions in best practices   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [f56bb07d83](https://github.com/angular/angular/commit/f56bb07d83a015b0ac12e74fdb0cf1550ff36b97)   feat   add field param to submit action and onInvalid   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ba009b6031](https://github.com/angular/angular/commit/ba009b603119299a03f9d844f93882d42d47d150)   feat   add form directive   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [22afbb2f36](https://github.com/angular/angular/commit/22afbb2f36be89c2ae575df343571a918dec5985)   feat   add parsing support to native inputs ([#66917](https://github.com/angular/angular/pull/66917))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [95c386469c](https://github.com/angular/angular/commit/95c386469c7a2f09dd731601c2061bdb10d25717)   feat   Add passing focus options to form field   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [95ecce8334](https://github.com/angular/angular/commit/95ecce8334299defe55fb2b74264e5258ffd137c)   feat   allow setting submit options at form-level   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ebae211add](https://github.com/angular/angular/commit/ebae211add37700858adeb8fc5d87bf503a59721)   feat   introduce parse errors in signal forms   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [3937afc316](https://github.com/angular/angular/commit/3937afc3167ce409eebb06d91d5fb122eea4e33d)   feat   introduce SignalFormControl for Reactive Forms compatibility   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [30f0914754](https://github.com/angular/angular/commit/30f09147545b67185f93efb9796e37c1db76733a)   feat   support binding null to number input ([#66917](https://github.com/angular/angular/pull/66917))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [dd208ca259](https://github.com/angular/angular/commit/dd208ca2595258fcd1e289374f812ce0b56c7011)   feat   update submit function to accept options object   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [27397b3f4f](https://github.com/angular/angular/commit/27397b3f4f3182ce00d6e2f8690285c316e2a274)   fix   clear parse errors when model updates ([#66917](https://github.com/angular/angular/pull/66917))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [63d8005703](https://github.com/angular/angular/commit/63d80057039928b3e878b59c1fe6b93ef1c6b701)   fix   preserve custom-control focus context in signal forms   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [631f60d1f9](https://github.com/angular/angular/commit/631f60d1f9be72cb68330308a6ff18cc195babb8)   fix   preserve parse errors when parse returns value   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [adfb83146b](https://github.com/angular/angular/commit/adfb83146b0c149734f43961563b389e00cc1d85)   fix   simplify design of parse errors   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [fb05fc86d0](https://github.com/angular/angular/commit/fb05fc86d0f12ffafd94c7c1420118d8a79f7e59)   fix   sort error summary by DOM order   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [567f292e8e](https://github.com/angular/angular/commit/567f292e8e0f9d2b5ddebadfa1c6d6dd6c456f39)   fix   support custom controls as host directives   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [bdfb60f3e3](https://github.com/angular/angular/commit/bdfb60f3e33065e047183dc1890c36e527e2b304)   fix   use consistent error format returned from parse   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [d75046bc09](https://github.com/angular/angular/commit/d75046bc091699bbadcb5f2032be627e983ee6fa)   fix   warn when showing hidden field state   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ebc90c26f5](https://github.com/angular/angular/commit/ebc90c26f5ff1ba1e0ca9b775a44e301ebfb9473)   feat   Add completions and hover info for inline styles   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [26fd0839c3](https://github.com/angular/angular/commit/26fd0839c32d2ebeaa5e3ecc10ed70ab9ca17749)   feat   Add folding range support for inline styles   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [573aadef7e](https://github.com/angular/angular/commit/573aadef7eb8b6b5e83b82a16f95d2a556f27c01)   feat   Add quick info for inline styles   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [6fb39d9b62](https://github.com/angular/angular/commit/6fb39d9b62cbb634e95ec00fe5ef85d84da3bdbd)   feat   Support client-side file watching via `onDidChangeWatchedFiles`   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [496967e7b1](https://github.com/angular/angular/commit/496967e7b13dfe1ebdde69724cd62880914beb60)   feat   add JSON schema for angularCompilerOptions   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [8c21866f49](https://github.com/angular/angular/commit/8c21866f49ff74344551395ae0a5df1841d54c0d)   feat   add linked editing ranges for HTML tag synchronization   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [d2137928e8](https://github.com/angular/angular/commit/d2137928e8f075527016a3c011dd8efc4d4e1ebd)   perf   use lightweight project warmup for Angular analysis   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [b51bab583d](https://github.com/angular/angular/commit/b51bab583d84e38f16dea489e4119edc34e2a491)   feat   Add partial ActivatedRouteSnapshot information to `canMatch` params   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [cf9620f7d0](https://github.com/angular/angular/commit/cf9620f7d072897f13b7f281b7bca6f51f69cfd0)   feat   Make match options optional in isActive   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [907a94dcec](https://github.com/angular/angular/commit/907a94dcec2926a5c7d0c4d36249bd62e31a2ae3)   feat   Update `IsActiveMatchOptions` APIs to accept a Partial   |

## `21.2.0` → `21.2.1`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [e2e9a9a531](https://github.com/angular/angular/commit/e2e9a9a531c9e9a69701e549f28354cc5d5edd77)   fix   adds transfer cache to httpResource to fix hydration   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [b4ec3cc4e4](https://github.com/angular/angular/commit/b4ec3cc4e41f2948ad0830eb14aa05d14fa3a9ed)   fix   prevent child animation elements from being orphaned   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [e923d88398](https://github.com/angular/angular/commit/e923d8839868c79989502ab3503e13d93c78516a)   fix   Prevent removal of elements during drag and drop   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [277ade97ac](https://github.com/angular/angular/commit/277ade97ac2a3a7f2a5b513acaa93e7663cdc55f)   fix   correctly cache blob responses in transfer cache ([#67002](https://github.com/angular/angular/pull/67002))   |

## `21.2.1` → `21.2.2`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [1df1697c6e](https://github.com/angular/angular/commit/1df1697c6e3a6b1d302f7692b495146943faa12f)   fix   prevent mutation of children array in RecursiveVisitor   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [c822bf8e76](https://github.com/angular/angular/commit/c822bf8e76611afde332b6625f5e7bae2fe9c3f3)   fix   always parenthesize object literals in TCB   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [05d022d5e6](https://github.com/angular/angular/commit/05d022d5e61cca7ac90d5b2b2ba3fc738b364ad9)   fix   ignore generated ngDevMode signal branch for code coverage   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [670d1660c4](https://github.com/angular/angular/commit/670d1660c40504e3f55e094c3ebbcccad14163f3)   feat   add 'blur' option to debounce rule   |

## `21.2.2` → `21.2.3`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [62a97f7e4b](https://github.com/angular/angular/commit/62a97f7e4b896b4b03a1ef25764db387ffecebe1)   fix   ensure definitions compile   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [21b1c3b2ee](https://github.com/angular/angular/commit/21b1c3b2ee2c8423782b111b93bd60eb6b453259)   fix   include signal debug names in their `toString()` representation   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [224e60ecb1](https://github.com/angular/angular/commit/224e60ecb1b90115baa702f1c06edc1d64d86187)   fix   sanitize translated attribute bindings with interpolations   |

## `21.2.3` → `21.2.4`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ed2d324f9c](https://github.com/angular/angular/commit/ed2d324f9cc12aab6cfa0569ef10b73243a62c65)   fix   disallow translations of iframe src   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [abbd8797bb](https://github.com/angular/angular/commit/abbd8797bbd3ae53a10033c39bd895b5b85a4fae)   fix   reverts "feat(core): add support for nested animations"   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [d1dcd16c5b](https://github.com/angular/angular/commit/d1dcd16c5b40291aa3fa2dc84d22842cd657b201)   fix   sanitize translated form attributes   |

## `21.2.4` → `21.2.5`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [334ae10168](https://github.com/angular/angular/commit/334ae10168fdad15cd1390180e2994b4eb65349b)   fix   ensure generated code compiles   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [23ea431c4e](https://github.com/angular/angular/commit/23ea431c4ec45cbb4a7db9839969e7cb23b07f58)   fix   parse named HTML entities containing digits   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [26c43d14ba](https://github.com/angular/angular/commit/26c43d14baad1a6b3629a77825e702a97a4f8482)   fix   escape template literal in TCB   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [67e0ba7e03](https://github.com/angular/angular/commit/67e0ba7e03bb940639f0eafb3af45015e9727eac)   fix   generic types not filled out correctly in type check block   |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [1890c3008b](https://github.com/angular/angular/commit/1890c3008bbb41b7143b7ede09bed1f7704744fb)   fix   clean up dehydrated views during HMR component replacement   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [bf948be4c2](https://github.com/angular/angular/commit/bf948be4c2c88c604e428cba35e3b9e532bfe5b0)   fix   run linked signal equality check without reactive consumer   |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [076d41c3f6](https://github.com/angular/angular/commit/076d41c3f6496eb6c6f84b54e2d2ca85c1b35e64)   fix   prevent trailing comma syntax errors after removing NgStyle   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [e19150d2b5](https://github.com/angular/angular/commit/e19150d2b596e87c69bee61f478c3e9c7cbc8f67)   fix   preserve redirect policy on reconstructed asset requests   |

## `21.2.5` → `21.2.6`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [b4ab6ba2e8](https://github.com/angular/angular/commit/b4ab6ba2e84a18309b0bb5dd68311ff1776b1cb4)   fix   avoid redundant image fetch on destroy with auto sizes   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [880a57d4b3](https://github.com/angular/angular/commit/880a57d4b34af5aa27cd5bee11fa218ade6444bb)   fix   prevent shimCssText from adding extra blank lines per CSS comment   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ad0156e056](https://github.com/angular/angular/commit/ad0156e056e60ffebfeb804fda70dce88d9475a8)   fix   fixes a regression with animate.leave and reordering   |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [73d6b01b47](https://github.com/angular/angular/commit/73d6b01b47bb6762d182f1cd891f8ad4d7f688e1)   fix   inject migration not work in multi-project workspace with option path   |

## `21.2.6` → `21.2.7`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [fea25d1a60](https://github.com/angular/angular/commit/fea25d1a60ecaba1599d9cd9b8df27109ed195c5)   fix   register SVG animation attributes in URL security context ([#67797](https://github.com/angular/angular/pull/67797))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [bba5ed8e64](https://github.com/angular/angular/commit/bba5ed8e643b9c3f680e7e539c3d744ad6905e59)   fix   prevent recursive scope checks for invalid NgModule imports   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [d04ddd73df](https://github.com/angular/angular/commit/d04ddd73dfc03f420afbdde964c5119f338af135)   fix   prevent binding unsafe attributes on SVG animation elements ([#67797](https://github.com/angular/angular/pull/67797))   |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [8fd896e99a](https://github.com/angular/angular/commit/8fd896e99a13855c6569f29efe7e578c301e13ee)   fix   resolve component import by exact specifier in route lazy-loading schematic   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [b682c62873](https://github.com/angular/angular/commit/b682c628731b86a4884e50abb2f5fa73ac0ad057)   fix   treat `object[data]` as resource URL context ([#67797](https://github.com/angular/angular/pull/67797))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [3c41e74fdd](https://github.com/angular/angular/commit/3c41e74fdd279f683156b654699a9312a850add0)   fix   validate locale in getOutputPathFn to prevent path traversal   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [0960592d3d](https://github.com/angular/angular/commit/0960592d3d4fad110d5598144fda9f2488520826)   fix   pass outlet context to split to fix empty path named outlets   |

## `21.2.7` → `21.2.8`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [e40d378f3e](https://github.com/angular/angular/commit/e40d378f3e3e7e57a45c8fbd9565ee06a3a6a13f)   fix   handle nested brackets in host object bindings   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [2c6781071f](https://github.com/angular/angular/commit/2c6781071f52d6378a002fba6611bb283fbb2fde)   fix   error for type parameter declarations   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [82192deda9](https://github.com/angular/angular/commit/82192deda9c07113835e6c85af3f2c8c8218cda0)   fix   handle missing serialized container hydration data   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [057cc6d09d](https://github.com/angular/angular/commit/057cc6d09d234f401a810cfdd3ad14127652b88b)   fix   remove obsolete iOS cursor pointer hack in event delegation   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [7797671257](https://github.com/angular/angular/commit/7797671257350665e8b3ceb2bc6a0201829dd338)   fix   get quick info at local var location to align with TS semantics and support type narrowing   |

## `21.2.8` → `21.2.9`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [f603d4714f](https://github.com/angular/angular/commit/f603d4714fa184aad34a6f7f9ea4e79c8af3afac)   fix   escape forward slashes in transfer state to prevent crawler indexing   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [540536c386](https://github.com/angular/angular/commit/540536c386f2c735a700c2c9e2697a88dcb3d4ec)   fix   add CSP nonce support to JsonpClientBackend   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [63a857b874](https://github.com/angular/angular/commit/63a857b874172766451aa75ed3347ba50f0ee229)   fix   Don't on Passthru outside of reactive context   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [e0b5078cf2](https://github.com/angular/angular/commit/e0b5078cf2ebe79a6de85e9123148ae948b3d81d)   fix   prevent SSRF bypasses via protocol-relative and backslash URLs   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [684e9fd53d](https://github.com/angular/angular/commit/684e9fd53daacb9e910f42d98c6017f9e5cb4180)   fix   normalize multiple leading slashes in URL parser   |

## `21.2.9` → `21.2.10`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [0d5ee9ae1b](https://github.com/angular/angular/commit/0d5ee9ae1ba4b7acd8f27a059a778f0b4bd8a5bd)   fix   link formatting in "Animating your Application with CSS"   |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [5533ab4f56](https://github.com/angular/angular/commit/5533ab4f56f574bc9365cf0573c4a34a3ab5aaf1)   fix   fix NgClass leaving trailing comma after removal   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [580212c995](https://github.com/angular/angular/commit/580212c995751c4bf4ce8a49df4167498743e0ea)   fix   restore internal URL on popstate when `browserUrl` is used   |

## `21.2.10` → `21.2.11`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [10ad3c0692](https://github.com/angular/angular/commit/10ad3c06923453ae0ec06b06e664ce05900a4ff6)   fix   prevent focus from scrollToAnchor   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [4f5d8a2c0b](https://github.com/angular/angular/commit/4f5d8a2c0b5e38d4debc4293945270cea4a9590d)   fix   let declaration span not including end character   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [a40e2cebc8](https://github.com/angular/angular/commit/a40e2cebc878965c3e21bfb61658f3f80cbd2ebf)   fix   fix ordering of view queries metadata in JIT mode   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [885a1a1d97](https://github.com/angular/angular/commit/885a1a1d9757adfa8766d9b369c848a277438c31)   fix   guard against non-object events and avoid listener wrapper identity mismatch   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [7a64aff9b5](https://github.com/angular/angular/commit/7a64aff9b59999077ea915486a7fa0b97a286659)   fix   prevent event replay double-invocation when element hydrates before app stability   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [be1f80a253](https://github.com/angular/angular/commit/be1f80a253b8ee27ed7d8de2287d6895c4821909)   fix   ensure origin has a trailing slash when parsing url   |

## `21.2.11` → `21.2.12`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [fe13bb669d](https://github.com/angular/angular/commit/fe13bb669d2bfab4713623d17b41c430aa0a61d8)   fix   allow explicit read generic with signal input transforms   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [3430251fef](https://github.com/angular/angular/commit/3430251fef93f6aec1fa9c7867e85df23f67c9a0)   fix   i18n flags leaking on errors   |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [1aeebbe304](https://github.com/angular/angular/commit/1aeebbe3048b5aa612dd0a5448de9883ed51e7e8)   fix   respect ngSkipHydration on components with projectable nodes in LContainers   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [9e38ed7d57](https://github.com/angular/angular/commit/9e38ed7d5773a9193ba07afdba3f7a9f2fe02d18)   fix   sanitizer typings   |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [7a05a9a71a](https://github.com/angular/angular/commit/7a05a9a71a5ab75042ec5560c01526de6e61e062)   fix   validate security-sensitive attributes in i18n bindings   |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [c37f6ca42f](https://github.com/angular/angular/commit/c37f6ca42f263353cb9563fa90d7b31d3c7837ca)   fix   visit ng-let expression value in signal migration schematics   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [03ad53863b](https://github.com/angular/angular/commit/03ad53863bf3c368f0f02a4322d4141e8f70f674)   fix   prohibit concurrent submits in signal forms   |

## `21.2.12` → `21.2.13`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [1c6553e97d](https://github.com/angular/angular/commit/1c6553e97d9655d8c48fbf625987fae86f9cd947)   fix   disallow event attribute bindings in host bindings unconditionally   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [629905d537](https://github.com/angular/angular/commit/629905d537f59dc3c264c49f6347e3599dea0215)   fix   add `allowedHosts` option to `renderModule` and `renderApplication`   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [0b7192f441](https://github.com/angular/angular/commit/0b7192f4410d055191ac9b15bff57d1d0b9a644f)   fix   forward BEFORE_APP_SERIALIZED errors to ErrorHandler   |

## `21.2.13` → `21.2.14`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [68282dff9f](https://github.com/angular/angular/commit/68282dff9f9ef46540cca4bd38fc1ab739c8a783)   fix   strip namespaced SVG script elements during template compilation   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [c0f52272ed](https://github.com/angular/angular/commit/c0f52272ed337d4776bd4178cbbdc7f32037500f)   fix   do not insert todo when migrating void @Output   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [938a7f3edd](https://github.com/angular/angular/commit/938a7f3eddda97a39edb9edcc8b4dd970858b3a2)   fix   makes resource URL sanitizer lookup case-insensitive   |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [0fb2724194](https://github.com/angular/angular/commit/0fb272419407a64a0a47096b03a911f4e7e83d79)   fix   reject script element as a dynamic component host   |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [49113ac0ef](https://github.com/angular/angular/commit/49113ac0eff852d987b5acb28a9bbda0242842cd)   fix   visit ICU expressions in signal migration schematics   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [099bf577ee](https://github.com/angular/angular/commit/099bf577ee8f0bab60593a8fd2a1de7d298e3cd6)   fix   skip scroll-to-top on initial navigation when hydrating   |

## `21.2.14` → `21.2.15`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [7f4ac78994](https://github.com/angular/angular/commit/7f4ac78994bff1576ab33f3ce48f95c17f40b4d8)   fix   add upper bounds for digitsInfo   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [300f61feb3](https://github.com/angular/angular/commit/300f61feb3a534bfddf16fcbd240f97b32249699)   fix   sanitize placeholder   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [0b07f47bd6](https://github.com/angular/angular/commit/0b07f47bd6598ae6bd5b75a375e2c817a3c0f243)   fix   normalize tag names with custom namespaces in DomElementSchemaRegistry ([#68925](https://github.com/angular/angular/pull/68925))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [eb1cbbf2eb](https://github.com/angular/angular/commit/eb1cbbf2eb5833219a367a61c04eb07aaa36cc29)   fix   prevent namespaced SVG <style> elements from being stripped   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [cc1378d54b](https://github.com/angular/angular/commit/cc1378d54bd93f3882d732261be8e66720eb71b2)   fix   sanitize dynamic href and xlink:href bindings on SVG a elements ([#68925](https://github.com/angular/angular/pull/68925))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [782e01594e](https://github.com/angular/angular/commit/782e01594e2ad9134c7385dcf3b518101b23ccab)   fix   strip namespaced SVG script elements during template compilation ([#68925](https://github.com/angular/angular/pull/68925))   |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ff12fe55ac](https://github.com/angular/angular/commit/ff12fe55ace5e861ba261afb4c0480ff3c40a192)   fix   normalize tag names in runtime i18n attribute security context lookup ([#68925](https://github.com/angular/angular/pull/68925))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [e6fe77cc97](https://github.com/angular/angular/commit/e6fe77cc97fd10351687416f938bf754aff4eb9f)   fix   sanitize meta selectors   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [daaf32937f](https://github.com/angular/angular/commit/daaf32937fd5c46e411b26f7c082613716fe9550)   fix   support prefix-insensitive DOM schema lookups and compile-time i18n attribute validation ([#68925](https://github.com/angular/angular/pull/68925))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [dada86e43d](https://github.com/angular/angular/commit/dada86e43d847204f714d1a933084617ab941c0a)   fix   synchronize core sanitization schema with compiler ([#68925](https://github.com/angular/angular/pull/68925))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [582a417bd2](https://github.com/angular/angular/commit/582a417bd27fdaf989e5065dbcdf1ad752faf70c)   fix   exclude withCredentials requests from transfer cache   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [5c6d6df34b](https://github.com/angular/angular/commit/5c6d6df34bbeff3ce98f3b35875444f925cc8f51)   fix   skip TransferCache for cookie-bearing requests by default   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [37e8aadf87](https://github.com/angular/angular/commit/37e8aadf87b4facfcaf002a1557f8c393a362d97)   fix   prevent SSRF bypasses via backslash URLs in HttpClient   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [72696e244e](https://github.com/angular/angular/commit/72696e244ed7646cca9ab9afc7769a2163943bda)   fix   secure location and document initialization against SSRF and path hijack   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [b8bd49341d](https://github.com/angular/angular/commit/b8bd49341ddcee10d119a9d4aa8e5736e4e5da53)   fix   Preserves explicit 'credentials: omit' in asset requests   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ca32fc1000](https://github.com/angular/angular/commit/ca32fc10001301e6174804f9abcfba62252334f4)   fix   Preserves HTTP cache mode in asset group requests   |

## `21.2.15` → `21.2.16`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [f6d8e642b0](https://github.com/angular/angular/commit/f6d8e642b0b215d2f9dbf1060abd24348c6cbf66)   fix   only strip a literal /index.html suffix from URLs   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ae1c8a1f7a](https://github.com/angular/angular/commit/ae1c8a1f7a7f1d4832da3b22e3763864fa5ff098)   fix   move projection attributes into constants   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [3fd6897a67](https://github.com/angular/angular/commit/3fd6897a67fd6acdc01fcde0452a98c3e0f81e21)   fix   harden inherit definition feature against polluted prototypes   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [7e38336dc7](https://github.com/angular/angular/commit/7e38336dc73e14d98cc6465f54e1b7d6271facb2)   fix   use Object.create(null) for LOCALE_DATA as a hardening measure   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [66821c4ed5](https://github.com/angular/angular/commit/66821c4ed5f580912a1609fc1e06a86f8793c2cf)   fix   throw on suspicious URLs and restrict protocol-relative URLs   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [d3170031b6](https://github.com/angular/angular/commit/d3170031b6f35508f960cba18586843925bb61ec)   fix   update domino to latest version   |

## `21.2.16` → `22.0.0`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | [Blog post "Announcing Angular v22"](https://goo.gle/angular-v22-blog). |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | This change will trigger the `nullishCoalescingNotNullable` and `optionalChainNotNullable` diagnostics on exisiting projects. |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | data prefixed attribute no-longer bind inputs nor outputs. |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | The compiler will throw when there a when inputs, outputs or model are binding to the same input/outputs. |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | `in` variables will throw in template expressions. |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | Elements with multiple matching selectors will now throw at compile time. |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | The second arguement of appRef.bootstrap does not accept `any` anymore. Make sure the element you pass is not nullable. |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | * TypeScript versions older than 6.0 are no longer supported. |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | Leave animations are no longer limited to the element being removed. |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | Component with undefined `changeDetection` property are now `OnPush` by default. Specify `changeDetection: ChangeDetectionStrategy.Eager` to keep the previous behavior. |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | change AnimationCallbackEvent.animationComplete signature |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | `ChangeDetectorRef.checkNoChanges` was removed. In tests use `fixture.detectChanges()` instead. |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | `createNgModuleRef` was removed, use `createNgModule` instead |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | `ComponentFactoryResolver` and `ComponentFactory` are no longer available. Pass the component class directly to APIs that previously required a factory, such as `ViewContainerRef.createComponent` or use the standalone `createComponentFunction`. |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | `ComponentFactoryResolver` and `ComponentFactory` are no longer available. Pass the component class directly to APIs that previously required a factory, such as `ViewContainerRef.createComponent` or use the standalone `createComponent` function. |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | `min` and `max` validation rules no longer support |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | Use the `HttpXhrBackend` with `provideHttpClient(withXhr)` if you want to keep supporting upload progress reports. |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | This removes styles when they appear to no longer be used by an associated `host`. However other DOM on the page may still be affected by those styles if not leveraging `ViewEncapsulation.Emulated` or if those styles are used by elements outside of Angular, potentially causing other DOM to appear unstyled. |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | Hammer.js integration has been removed. Use your own implementation. |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | The return type for `TitleStrategy.getResolvedTitleForRoute` |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | The `currentSnapshot` parameter in `CanMatchFn` and the `canMatch` method of the `CanMatch` interface is now required. While this was already the behavior of the Router at runtime, existing class implementations of `CanMatch` must now include the third argument to satisfy the interface. |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | paramsInheritanceStrategy now defaults to 'always' |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | `provideRoutes()` has been removed. Use `provideRouter()` or `ROUTES` as multi token if necessary. |
| deprecation | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | Deprecated `getAngularLib`/`setAngularLib` have been removed use `getAngularJSGlobal`/`setAngularJSGlobal` instead. |
| deprecation | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | `withFetch` is now deprecated, it can be safely removed. |
| deprecation | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | The `reportProgress` option is deprecated please use `reportUploadProgress` &  `reportDownloadProgress` instead. |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [47fcbc4704](https://github.com/angular/angular/commit/47fcbc470462192c4f9e273d8dce8b353d5baaa2)   feat   allow safe navigation to correctly narrow down nullables   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [2896c93cc1](https://github.com/angular/angular/commit/2896c93cc1077e1306acd91f4ed62fed4204a26b)   feat   Angular expressions with optional chaining returns `undefined`   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [e850643b1b](https://github.com/angular/angular/commit/e850643b1b8dca8cfdc12705be51441197cd987a)   feat   Support comments in html element.   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [96be4f429b](https://github.com/angular/angular/commit/96be4f429ba316c75d2d4a39ececcc529ec10943)   fix   abstract emitter producing incorrect code for dynamic imports   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [488d962bc7](https://github.com/angular/angular/commit/488d962bc700fb7189749c63ba63eac50a54e363)   fix   Don't bind inputs/outputs for `data-` attributes   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [2c5aabb9da](https://github.com/angular/angular/commit/2c5aabb9daf5da3ad539381ef1e430c77583e3bf)   fix   don't escape dollar sign in literal expression   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [c7aef8ec5d](https://github.com/angular/angular/commit/c7aef8ec5dd12b5b1d4c703a61bd1dd43f998e18)   fix   enforce parentheses containing arguments for :host-context   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [b225a5d902](https://github.com/angular/angular/commit/b225a5d902f0ee1f6f68cde42266748cb1f2b1f8)   fix   invalid type checking code if field name needs to be quoted   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ab9154ab75](https://github.com/angular/angular/commit/ab9154ab75bdd36759c77917216b57285b243ea4)   fix   normalize tag names with custom namespaces in DomElementSchemaRegistry ([#68868](https://github.com/angular/angular/pull/68868))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [8a1533c9ad](https://github.com/angular/angular/commit/8a1533c9ad7c306e03d7c50676f87b56bade5bf6)   fix   preserve leading commas in animation definitions   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [194f723f66](https://github.com/angular/angular/commit/194f723f6620ea3cdf490b762ecbef8df6bb2c8a)   fix   remove dedicated support for legacy shadow DOM selectors   |
| deprecation | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [4c25a42e98](https://github.com/angular/angular/commit/4c25a42e988e7a59d4d4dc3121cd77f7b344c048)   fix   remove deprecated shadow CSS encapsulation polyfills   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [6ff620a033](https://github.com/angular/angular/commit/6ff620a03364d6ab60cea47de942a04ec5a26c50)   fix   sanitize dynamic href and xlink:href bindings on SVG a elements ([#68868](https://github.com/angular/angular/pull/68868))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [7dc1017e51](https://github.com/angular/angular/commit/7dc1017e517c077a6aa8fd749392a2af1277e1b7)   fix   simplify handling of colon host with a selector list   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [d99ab0e040](https://github.com/angular/angular/commit/d99ab0e0400d256021d6cc601e2a6e16f784a406)   fix   stop generating unused field   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [03db2aefaa](https://github.com/angular/angular/commit/03db2aefaa88bc73b6af6ed1c9c722b65079ab3b)   fix   throw on duplicate input/outputs   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [786ef8261f](https://github.com/angular/angular/commit/786ef8261f4faca0693ef73938d3a6275b5baf7f)   fix   throw on invalid in expressions   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ccb7d427e4](https://github.com/angular/angular/commit/ccb7d427e4f07506c14c50ce0cbe87c57930ebb5)   fix   type check invalid for loops   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [b8d3f36ed9](https://github.com/angular/angular/commit/b8d3f36ed962bd4f5abd6bf6e55078b56ce9fffa)   feat   add support for Node.js 26.0.0   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [7f9450219f](https://github.com/angular/angular/commit/7f9450219f5c30d1ce0a90061864e8c844c8807c)   feat   Adds warning for prefetch without main defer trigger   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [2eae497a04](https://github.com/angular/angular/commit/2eae497a04a6a9b34397181dcd64dbd103f76c47)   feat   support external TCBs with copied content in specific mode   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [e5f96c2d88](https://github.com/angular/angular/commit/e5f96c2d8813f95c91761ae3080065575ca3b536)   fix   animation events not type checked properly when bound through HostListener decorator   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [9218140348](https://github.com/angular/angular/commit/9218140348cb2e3ad301c1e7f37db4b0cdad4f9d)   fix   resolve TCB mapping failure for safe property reads with as any   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [7a0d6b8df2](https://github.com/angular/angular/commit/7a0d6b8df21ca6a407e5c63dc0af753bc39c90c5)   fix   transform dropping exclamationToken from properties   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ca67828ee2](https://github.com/angular/angular/commit/ca67828ee247bdff46736661e51f43f2ca736a24)   refactor   introduce NG8023 compile-time diagnostic for duplicate selectors   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [17d3ea44e2](https://github.com/angular/angular/commit/17d3ea44e25e077b18178aa8108828f36eb821f4)   feat   add `IdleRequestOptions` support to `IdleService`   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [3b0ae5fef0](https://github.com/angular/angular/commit/3b0ae5fef0328477ee0f5d51980217e7c583a606)   feat   add `provideWebMcpTools`   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [444b024d49](https://github.com/angular/angular/commit/444b024d49725afc8b40aec67cfdb63a1f7f23ea)   feat   Add a `injectAsync` helper function   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [3bc095d508](https://github.com/angular/angular/commit/3bc095d508653982a48b337afd51bfedbbde1f87)   feat   Add a schematics to migrate `provideHttpClient` to keep using the `HttpXhrBackend` implementation.   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [5a7c1e62dc](https://github.com/angular/angular/commit/5a7c1e62dc2a4fa199b85150eca66914c107a6f4)   feat   add ability to cache resources for SSR   |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [cb4cb77053](https://github.com/angular/angular/commit/cb4cb77053a817fe800af6395783720761e29ada)   feat   Add migration to add `ChangeDetectionStrategy.Eager` where applicable   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [2206efa55f](https://github.com/angular/angular/commit/2206efa55fc1de160333d62680f8893c47525335)   feat   add special return statuses for resource params   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [246a984a5d](https://github.com/angular/angular/commit/246a984a5df0006bc5f4025baf918345aa38499c)   feat   add TestBed.getFixture   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [b918beda32](https://github.com/angular/angular/commit/b918beda323eefef17bf1de03fde3d402a3d4af0)   feat   allow debouncing signals   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [8bc31a515f](https://github.com/angular/angular/commit/8bc31a515ff6e8edda6ea5786a47ae5a788acd36)   feat   Allow other expression for exhaustive typechecking   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [4e331062e8](https://github.com/angular/angular/commit/4e331062e8385e066102c3bbb8be439eabfdf8c9)   feat   allow synchronous values for stream Resources   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [a0aa8304cd](https://github.com/angular/angular/commit/a0aa8304cd78a58a990c3b648e41f6888b50b1b3)   feat   bootstrap via `ApplicationRef` with config   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [9c55fcb3e6](https://github.com/angular/angular/commit/9c55fcb3e65ffcde32d7ac438ea40a69ffc2b3b6)   feat   de-duplicate host directives   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [8fe025f514](https://github.com/angular/angular/commit/8fe025f5149d7eb460e784a5a17bb467f85b9080)   feat   drop support for TypeScript 5.9   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [2f5ab541ea](https://github.com/angular/angular/commit/2f5ab541eafba72bc0079a8650d0b96b0ddfde2f)   feat   enhance profiling with documentation URLs   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ef1810197b](https://github.com/angular/angular/commit/ef1810197b679bfcbf21a139b930984302cbe77f)   feat   export experimental `declareWebMcpTool` support   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [75f2cb8f56](https://github.com/angular/angular/commit/75f2cb8f566de43a5f2fd27bb2982c796b93490d)   feat   implement Angular DI graph in-page AI tool   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [8f3d0b9d97](https://github.com/angular/angular/commit/8f3d0b9d97424e058eb7bce57d80833fb68dec4a)   feat   introduce `@Service` decorator   |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [df659b8d0c](https://github.com/angular/angular/commit/df659b8d0cf64eeed418c60bc16cae5630086401)   feat   re-introduce nested leave animations scoped to component boundaries   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [8ce9cc4f6b](https://github.com/angular/angular/commit/8ce9cc4f6b10d60300dedb6571822ce77a96f2ce)   feat   register AI runtime debugging tools   |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [eae8f7e30b](https://github.com/angular/angular/commit/eae8f7e30b9f8bebdcdb535bd86260199c34274b)   feat   Set default Component changeDetection strategy to OnPush   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [cdda51a3b2](https://github.com/angular/angular/commit/cdda51a3b2f48d5623acef0c6f54afb7af921b58)   feat   support bootstrapping Angular applications underneath shadow roots   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [a5981b83a6](https://github.com/angular/angular/commit/a5981b83a60577d9068d2429bcbed969edca581b)   feat   support customization of @defer's on idle behavior   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [98eb24cea0](https://github.com/angular/angular/commit/98eb24cea0498382cc7cf7d7b85cd9ead5ad99ad)   feat   Support optional timeout for idle deferred triggers   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [dc3131c639](https://github.com/angular/angular/commit/dc3131c639542ad6a463bff3da5ca84c6f8ecb6f)   feat   TestBed.getFixture -> TestBed.getLastFixture and update implementation   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [9f479ae964](https://github.com/angular/angular/commit/9f479ae9641a5c928f8eeab9c7846245002b3eff)   feat   Update Testability to use PendingTasks for stability indicator   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [8ebae1de33](https://github.com/angular/angular/commit/8ebae1de330729f945391283e25661aada11b4ed)   fix   allow service with factory on abstract classes   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [f9d8da6924](https://github.com/angular/angular/commit/f9d8da69243ae1cd0eb1ab197fdd80e9a34107c1)   fix   bind global context to idle callback shims in @defer's idle service   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [61a48e99aa](https://github.com/angular/angular/commit/61a48e99aad1152e9ffb2fd0b4e1b472f06649e8)   fix   do not register dom triggers when defer blocks are in manual mode   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [49748b5c79](https://github.com/angular/angular/commit/49748b5c7989b4e27686798ea7935e87d804eece)   fix   enforce return type for service factory   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [16adbbf423](https://github.com/angular/angular/commit/16adbbf4234cc67507f578e588a8500fc5d31013)   fix   ensure custom controls resolve transitive host directives   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [50e599e73e](https://github.com/angular/angular/commit/50e599e73ec5bb8f483e749d76fff579e33b1670)   fix   lazy-initialize debounced state to prevent computation cycle   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [7aad302c3e](https://github.com/angular/angular/commit/7aad302c3ee6e9c711ab10ae0a9e8bc66d35291c)   fix   mark service decorator as stable   |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [a08e4fb93c](https://github.com/angular/angular/commit/a08e4fb93c371252da16b3b22cbf78f4ac180fa2)   fix   normalize tag names in runtime i18n attribute security context lookup ([#68868](https://github.com/angular/angular/pull/68868))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [b20f0fe078](https://github.com/angular/angular/commit/b20f0fe07820362f7e3bddb892a2a229a820a028)   fix   prevent rxResource from leaking a subscription   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [22f8b0a500](https://github.com/angular/angular/commit/22f8b0a500807e69b323378b843465a949e08abf)   fix   resolver function not matching expected type   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [88d138ccc8](https://github.com/angular/angular/commit/88d138ccc84b839784f59575fddcda3fcaf18d35)   fix   support prefix-insensitive DOM schema lookups and compile-time i18n attribute validation   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [bfe6f6c2a5](https://github.com/angular/angular/commit/bfe6f6c2a5570cd669afa3dd8b1cd9e2d91e393a)   fix   synchronize core sanitization schema with compiler   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [5e99ae9f00](https://github.com/angular/angular/commit/5e99ae9f00fb119cac93a19bbf36aee71299cae1)   fix   widen type for directive inputs/outputs   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [b9b5c279b4](https://github.com/angular/angular/commit/b9b5c279b444ab2684fe911982930dc7c31ed43c)   refactor   enhance AnimationCallbackEvent.animationComplete signature   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [69fb1614ef](https://github.com/angular/angular/commit/69fb1614eff6e40bb7dcca81f275ac32b9cbd28a)   refactor   remove `checkNoChanges` from the public API.   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [36936872c9](https://github.com/angular/angular/commit/36936872c962b2073c8f44080684701068866691)   refactor   remove `createNgModuleRef`   |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [9d76ac8229](https://github.com/angular/angular/commit/9d76ac82290e047f1481fb38bd95233e951a77de)   refactor   remove ComponentFactoryResolver & ComponentFactory from the api surface   |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [b1f5181ffd](https://github.com/angular/angular/commit/b1f5181ffd8e9906affd486d9e2f655eb144f175)   refactor   remove ComponentFactoryResolver & ComponentFactory from the api surface""   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [74f76d8075](https://github.com/angular/angular/commit/74f76d8075d03b1271aef37b974c9e15f9c7d3af)   feat   add `reloadValidation` to Signal Forms to manually trigger async validation   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [24e52d450d](https://github.com/angular/angular/commit/24e52d450d201e3da90bb64f84358f9eccd7877d)   feat   add debounce option to validateAsync and validateHttp   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [709f5a390c](https://github.com/angular/angular/commit/709f5a390ca0de04f8066012a5cb36999f2fd4a6)   feat   add FieldState.getError()   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [7745365910](https://github.com/angular/angular/commit/7745365910771d97c91e9b640c2c26a99bfa5a6d)   feat   graduate signal forms APIs to public API   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [f9f24fc669](https://github.com/angular/angular/commit/f9f24fc6699b762d17127d0412343041ecdea70e)   feat   shim legacy NG_VALIDATORS into parseErrors for CVA mode ([#67943](https://github.com/angular/angular/pull/67943))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [41b1410cb8](https://github.com/angular/angular/commit/41b1410cb8a333a2ce6569483cd10866effc154d)   feat   support binding `number null` to `<input type="text">`   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [3983080236](https://github.com/angular/angular/commit/3983080236e348ecc17ab4e65a6a5cc0a16aa315)   feat   support ngNoCva as an opt-out for ControlValueAccessors   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [c4ce3f345f](https://github.com/angular/angular/commit/c4ce3f345fdb14595f0991dff488c4043a0fc71c)   feat   template & reactive support for FVC   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [3524de29f3](https://github.com/angular/angular/commit/3524de29f34bef5df941e08e88920dffe4f880c8)   fix   Add support for range type with outside of native bounds   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [de56d74da3](https://github.com/angular/angular/commit/de56d74da39178308b81a2d94c8eb4488cb0cbab)   fix   align FormField CVA selection priority with standard forms   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [0eeb1b5f03](https://github.com/angular/angular/commit/0eeb1b5f03395ea0ddb047790af4cf1440655a07)   fix   allow `FormRoot` to be used without submission options ([#67727](https://github.com/angular/angular/pull/67727))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [394ad0c2a2](https://github.com/angular/angular/commit/394ad0c2a26eec8a8f7136b1b7971420b30a117e)   fix   allow late-bound input types for signals forms   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ee8d2098cb](https://github.com/angular/angular/commit/ee8d2098cb3cdce1589c462cd9a66eae490477f9)   fix   change FieldState optional properties to non-optional   undefined   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [df8b020299](https://github.com/angular/angular/commit/df8b020299b5e579956578d9137cab93a8065045)   fix   clear native date inputs correctly in signal forms when changed via native UI   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [2e9aeea0fe](https://github.com/angular/angular/commit/2e9aeea0fed1a2eae261b95cb1479519d0428b83)   fix   deduplicate writeValue calls in CVA interop   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [0ea50ffe5a](https://github.com/angular/angular/commit/0ea50ffe5adb07515867e8bf30d1abee49413003)   fix   ensure debounced async validators produce pending status during debounce   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [3c44d7c90b](https://github.com/angular/angular/commit/3c44d7c90b2392f7307d1b1dd0734db10ede63f5)   fix   fix orphan field error on blur during array removal   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [849dba6c65](https://github.com/angular/angular/commit/849dba6c6506c2696a43a3fad6ee459e17b4b6c8)   fix   implement custom control reset propagation   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [5835a5e3a7](https://github.com/angular/angular/commit/5835a5e3a73686473ad064f53f93d9d9acb541a6)   fix   prevent orphan field crashes in debounceSync and async validation   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [3e7ce0dafc](https://github.com/angular/angular/commit/3e7ce0dafcf1c0b9ed7a8c528f7120f5c796a668)   fix   restrict `SignalFormsConfig` to a readonly API   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [fb166772d2](https://github.com/angular/angular/commit/fb166772d2e987c0145bdd5bbe83b2a29d74f31c)   fix   split the `touched` model into an input and `touch` output   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [83032e3605](https://github.com/angular/angular/commit/83032e36059ad0fc61cde2ac26c1eb0cede14e8c)   fix   support generic unions in signal form schemas   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [68c3abbe09](https://github.com/angular/angular/commit/68c3abbe09f1937081b83af3c7d82ed1a044974f)   fix   synchronize controls with the model on reset   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [2061fd8253](https://github.com/angular/angular/commit/2061fd8253882a46336aae8d73a79a1b176449e0)   fix   Untrack `setValue` in reactive forms   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [72d3ace03c](https://github.com/angular/angular/commit/72d3ace03c1292ba9d6fdf7b418ba3287bf54316)   fix   use controlValue in NgControl for CVA interop ([#67943](https://github.com/angular/angular/pull/67943))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [3b4ef1e2ff](https://github.com/angular/angular/commit/3b4ef1e2ffa7f33583b9d6c5d927e2148a507921)   perf   avoid redundant invalidations in parser errors signal   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [07a9358157](https://github.com/angular/angular/commit/07a935815782eb58a2109bcaacde33896e8d5d76)   perf   avoid spurious recomputation in FormField.parseErrors   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [98c5afdb02](https://github.com/angular/angular/commit/98c5afdb02192f99c886fc3fda13ec6f39018f23)   perf   lazily instantiate signal form fields   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [e0536091f5](https://github.com/angular/angular/commit/e0536091f5f6c2033e377998eea3bf65b14f5ac6)   perf   optimize reactivity by using shallow array equality   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [9b9769479b](https://github.com/angular/angular/commit/9b9769479b295bf34bae9a938ee758a256bd4b32)   perf   shortcut deepSignal writes if value is unchanged   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [592a12d6c9](https://github.com/angular/angular/commit/592a12d6c947a0210020b00fd98ffa9fdaca2c20)   refactor   remove string support from min and max validation rules ([#68001](https://github.com/angular/angular/pull/68001))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [5c432fb8bb](https://github.com/angular/angular/commit/5c432fb8bb69343ef2633811c37c0c6c0fd65126)   feat   Use `FetchBackend` as default for the `HttpBackend` implementation   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [f7b3ed8db2](https://github.com/angular/angular/commit/f7b3ed8db28c69ee0de9144465da351bda7e85e4)   fix   Introduce a max buffer size for fetch requests on SSR   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [e6cfaf5672](https://github.com/angular/angular/commit/e6cfaf567256f5e89903f6b5625540e5a4a3bde3)   fix   prevent `httpResource` from leaking a subscription   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [7c8c3347ef](https://github.com/angular/angular/commit/7c8c3347efc1be2b5967b9481e3a2a3a23c24977)   refactor   Add `reportUploadProgress` &  `reportDownloadProgress` options   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [5a6d88626b](https://github.com/angular/angular/commit/5a6d88626b604db937287a501cb723c088412a7e)   feat   add angular template inlay hints support   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [cfd0f9950c](https://github.com/angular/angular/commit/cfd0f9950c08324e1c56f16d98a2e3081feeda58)   feat   add Document Symbols support for Angular templates   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [c6f98c723c](https://github.com/angular/angular/commit/c6f98c723cdd2c209092927855f8cbaf63ecce30)   feat   Add support for idle timeout in defer blocks   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [dc9c72da9b](https://github.com/angular/angular/commit/dc9c72da9b4ca499eebf6e78d7ccc31ea6f63580)   fix   Add support for `@Input` with transforms   |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [8216d34976](https://github.com/angular/angular/commit/8216d349768687ed0cf9ef6e1d737e7db9c9e28b)   feat   Add migration for CanMatchFn snapshot parameter ([#67452](https://github.com/angular/angular/pull/67452))   |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [682aaf943f](https://github.com/angular/angular/commit/682aaf943fea3d99f9f834b0bad4d165b4b28071)   feat   add strictTemplates to tsconfig during ng update   |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [6a435658e2](https://github.com/angular/angular/commit/6a435658e25f9c81ddeaaa72d9c9694fc02bbef1)   feat   Disabling nullishCoalescingNotNullable & optionalChainNotNullable on ng update   |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [8f8972b0fd](https://github.com/angular/angular/commit/8f8972b0fdea2020800e7df5c6d85938602cb7e7)   feat   model + output migrations   |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [f01901d766](https://github.com/angular/angular/commit/f01901d7668ab926bd7a786f43dbb18f2bb8a5b7)   fix   avoid generating invalid code in ChangeDetectionStrategy.Eager migration   |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [1415d86980](https://github.com/angular/angular/commit/1415d869804729e50ed4bcdc829da870b4a70206)   fix   Fix typo for strict-template migration   |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [9d9855a415](https://github.com/angular/angular/commit/9d9855a41597c116ca102e672867047ddf7b4545)   fix   Make the safe optional chaining idempotent   |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [0f2160c410](https://github.com/angular/angular/commit/0f2160c4105a53ef6488d2c799dda9c0959ce7dc)   fix   remove compiler import from safe optional chaining migration   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [68628dd45b](https://github.com/angular/angular/commit/68628dd45bfcf4ea33bc00798bab1e4ab9da804c)   feat   make incremental hydration default behavior   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [d45b7a91f9](https://github.com/angular/angular/commit/d45b7a91f961ee40e3ea0f0ae837bf543bddb520)   fix   remove unused styles when associated `host` is dropped   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [f99e7ed20f](https://github.com/angular/angular/commit/f99e7ed20f0b1a26fd275fcf5befd589bb4e5d31)   refactor   remove Hammer integration   |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [89c9a4de30](https://github.com/angular/angular/commit/89c9a4de308a087ce95246ee259f32c8a927e39e)   feat   Add `options` optional parameter for `withComponentInputBinding`   |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [c84642ac16](https://github.com/angular/angular/commit/c84642ac16bf3588c071bbdcc684daa8d4e494b3)   feat   add unmatchedInputBehavior option to componentInputBinding   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [3683902234](https://github.com/angular/angular/commit/3683902234acf74c7047337bda4db937e93f93d7)   feat   adds browserUrl input support to router links   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [3e7117d690](https://github.com/angular/angular/commit/3e7117d690386b079c18b435545dab96fc183305)   fix   Add strict typing on 'getResolvedTitleForRoute'   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [579440170b](https://github.com/angular/angular/commit/579440170b372f8348cf3e5b5ce9f9f430093947)   fix   make currentSnapshot required in CanMatchFn ([#67452](https://github.com/angular/angular/pull/67452))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [17d10f7a99](https://github.com/angular/angular/commit/17d10f7a9921429d0192df6925d20d7236425c9a)   fix   set default paramsInheritanceStrategy to 'always'   |
| deprecation | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [bdb6ae9dbc](https://github.com/angular/angular/commit/bdb6ae9dbc080cd6ce4f5058c65f6b2bd853beda)   refactor   remove deprecated `provideRoutes` function.   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [836094c072](https://github.com/angular/angular/commit/836094c072cb0f6cdbd35469ee02158667a9ba51)   fix   resolve TS 6.0 compatibility for messageerror listener   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [01a179577b](https://github.com/angular/angular/commit/01a179577b5a250f5801f6d9a04378aea73c4251)   refactor   remove `getAngularLib`/`setAngularLib`   |

