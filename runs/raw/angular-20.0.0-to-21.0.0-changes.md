# Angular — documented changes (extract-only)

- **Framework key:** `angular`
- **Resolved range:** `20.0.0` → `21.0.0`
- **Generated (UTC):** 2026-06-05T14:07:47Z

---


## `20.0.0` → `20.0.1`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [66a0ec6510](https://github.com/angular/angular/commit/66a0ec6510aa7f2afc675440bd782750100f84d5)   fix    move defer trigger assertions out of parser ([#61747](https://github.com/angular/angular/pull/61747))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [8ecb1ba027](https://github.com/angular/angular/commit/8ecb1ba0275636d4ca697cd648d8c4c3a6eb27df)   fix    recover invalid parenthesized expressions ([#61815](https://github.com/angular/angular/pull/61815))     |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [8c60cbfd1c](https://github.com/angular/angular/commit/8c60cbfd1c4fe161936ea9f3b8c126083f2eae5e)   fix    `takeUntilDestroyed` completes immediately if DestroyRef already destroyed ([#61847](https://github.com/angular/angular/pull/61847))                |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [b1d960d082](https://github.com/angular/angular/commit/b1d960d082c6d0e52d45d0f1ef24102c16696fa5)   fix    produce an error when incremental hydration is expected, but not configured ([#61741](https://github.com/angular/angular/pull/61741))               |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [b4ed62ddf6](https://github.com/angular/angular/commit/b4ed62ddf60729fc4e6cfa529a9c7a455ff956d5)   fix    properly handle the case where getSignalGraph is called on a componentless NodeInjector ([#60772](https://github.com/angular/angular/pull/60772))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ddd22bea48](https://github.com/angular/angular/commit/ddd22bea4813b572bfdff15d4bc9c24589bef1bb)   fix    unregister `onDestroy` in `ResourceImpl` when `destroy()` is called ([#61870](https://github.com/angular/angular/pull/61870))                       |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [5c31e7e28d](https://github.com/angular/angular/commit/5c31e7e28d519df35b52397161e9d0cedc570304)   fix    unregister `onDestroy` when observable errors in `toSignal` ([#61596](https://github.com/angular/angular/pull/61596))                               |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [e9820a6d48](https://github.com/angular/angular/commit/e9820a6d48629df004043adc5fd6d29e37e43731)   fix    avoid trailing whitespaces in unused imports migration ([#61698](https://github.com/angular/angular/pull/61698))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [b93fa22f25](https://github.com/angular/angular/commit/b93fa22f2509578342343cc0dcf8225863def793)   fix    prevent duplicate fetches during concurrent update checks ([#61443](https://github.com/angular/angular/pull/61443))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [9743bd1317](https://github.com/angular/angular/commit/9743bd1317b7fb397bc1e799a0f9a117ee5d6698)   fix    update service worker to handle seeking better for videos ([#60029](https://github.com/angular/angular/pull/60029))   |

## `20.0.1` → `20.0.2`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [1e8158baee](https://github.com/angular/angular/commit/1e8158baee1be48747180eead8d61de328041b2c)   fix    components marked for traversal resets reactive context ([#61663](https://github.com/angular/angular/pull/61663))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [1cd23be57e](https://github.com/angular/angular/commit/1cd23be57e68c50d6c1f3f19d53d83651fa73fd1)   fix    unregister `onDestroy` in `outputToObservable` ([#61882](https://github.com/angular/angular/pull/61882))            |

## `20.0.2` → `20.0.3`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|

## `20.0.3` → `20.0.4`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [e343cdfb86](https://github.com/angular/angular/commit/e343cdfb86043e10d08aa4031b7b8d59342b37e5)   fix    Fixes template outlet hydration ([#62012](https://github.com/angular/angular/pull/62012))                |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [67f657e4a3](https://github.com/angular/angular/commit/67f657e4a3b27b968277fa63c9455e44b3e2259f)   fix    inject `APP_ID` before injector is destroyed ([#61885](https://github.com/angular/angular/pull/61885))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ae212b51ee](https://github.com/angular/angular/commit/ae212b51eef6779e70f076110085f35b684234c6)   fix    Wrap ErrorEvent with no error property ([#62081](https://github.com/angular/angular/pull/62081))         |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [82bf9848a1](https://github.com/angular/angular/commit/82bf9848a154c14f7100a1b29c5ef6aabc0a6c57)   fix    more robust trailing comma removal in unused imports migration ([#62118](https://github.com/angular/angular/pull/62118))   |

## `20.0.4` → `20.0.5`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [de0d525ad7](https://github.com/angular/angular/commit/de0d525ad7a5a9bfcc78b66ac627a507c8709064)   fix    add suggestion when pipe is missing ([#62146](https://github.com/angular/angular/pull/62146))             |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [3eb5a79a83](https://github.com/angular/angular/commit/3eb5a79a8324c96d438f4ad004a098295efad769)   fix    handle initializer APIs wrapped in type casts ([#62203](https://github.com/angular/angular/pull/62203))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [a2e6f317a7](https://github.com/angular/angular/commit/a2e6f317a732495602caf2ab871d38981a742e05)   fix    allow to set a resource in an error state ([#62253](https://github.com/angular/angular/pull/62253))                                          |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [4c00238a69](https://github.com/angular/angular/commit/4c00238a69ab7f6c5b53d12d4030cb172454ab39)   fix    avoid injecting `ErrorHandler` from a destroyed injector ([#61886](https://github.com/angular/angular/pull/61886))                           |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [369f03ad7f](https://github.com/angular/angular/commit/369f03ad7f3132240db938ea2b4de2de2e38c867)   fix    unable to retrieve defer blocks in tests when component injects ViewContainerRef ([#62156](https://github.com/angular/angular/pull/62156))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [65c59dd796](https://github.com/angular/angular/commit/65c59dd7964cd9643244b46094031e7227252875)   fix    handle scrollRestoration error in restricted environments ([#62186](https://github.com/angular/angular/pull/62186))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [144c429230](https://github.com/angular/angular/commit/144c429230c864ae7a94c6a40738a9cd1223581b)   fix    Make zoneless work with hybrid apps ([#61660](https://github.com/angular/angular/pull/61660))   |

## `20.0.5` → `20.0.6`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|

## `20.0.6` → `20.0.7`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://github.com/angular/angular/releases/tag/20.0.7 |   [![fix - 2c18043240](https://img.shields.io/badge/2c18043240-fix-green)](https://github.com/angular/angular/commit/2c18043240e8115ed47993ecddaf2232824544c7)   use proper name for diagnostic type (#62479)   |

## `20.0.7` → `20.1.0`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [58aedc37d1](https://github.com/angular/angular/commit/58aedc37d10208ca40c1b1d4468261dd9aba5356)   feat   add support for a custom EnvironmentInjector to NgComponentOutlet directive ([#54764](https://github.com/angular/angular/pull/54764))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ef10aa4005](https://github.com/angular/angular/commit/ef10aa400585fb66e1afde08be0f9fd9a70ce7f2)   feat   support decoding in NgOptimizedImage ([#61905](https://github.com/angular/angular/pull/61905))                                          |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [0dcf230d52](https://github.com/angular/angular/commit/0dcf230d52694e6d3d6e55d6e675d55f9cf236bc)   feat   add support for new binary assignment operators ([#62064](https://github.com/angular/angular/pull/62064))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [5a76826d26](https://github.com/angular/angular/commit/5a76826d266b4ed0ef863221571e4b6b1b16182f)   fix    only report parser errors on invalid expression ([#61793](https://github.com/angular/angular/pull/61793))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [089ad0ee15](https://github.com/angular/angular/commit/089ad0ee15d6be9b2493bb67519cb59e0454a1ef)   fix    produce more accurate errors for interpolations ([#62258](https://github.com/angular/angular/pull/62258))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [e9fcbb8af1](https://github.com/angular/angular/commit/e9fcbb8af12e7b4370d2e03e6004f3f2fe02c981)   fix    remove TypeScript from linker ([#61618](https://github.com/angular/angular/pull/61618))                     |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [e62fb359d6](https://github.com/angular/angular/commit/e62fb359d6da8e0458b18f24e6bff60602f93fc6)   feat   add experimental support for fast type declaration emission ([#61334](https://github.com/angular/angular/pull/61334))                                 |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [0cf1001715](https://github.com/angular/angular/commit/0cf1001715d2f528c61735108d12e29047907d98)   feat   support host directives with direct external references in fast type declaration emission ([#61469](https://github.com/angular/angular/pull/61469))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [b7ab5fa256](https://github.com/angular/angular/commit/b7ab5fa2562524a0e8dfa4f3dff740ec2d31b4c7)   fix    add signal checks to handle negated calls ([#59970](https://github.com/angular/angular/pull/59970))                                                   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [77fa204ad1](https://github.com/angular/angular/commit/77fa204ad16fef561c009fcef0ab1fb92a37f986)   fix    rename flag for enabling fast type declaration emission ([#61353](https://github.com/angular/angular/pull/61353))                                     |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [c439d6938d](https://github.com/angular/angular/commit/c439d6938de60cb132f7ae4d305efa5b3d853e36)   fix    symbol builder duplicating host directives ([#61240](https://github.com/angular/angular/pull/61240))                                                  |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [3e1baa5a95](https://github.com/angular/angular/commit/3e1baa5a9565f4930507cdf338e6f9ea7e8702a3)   fix    typo in NG2026 message ([#61325](https://github.com/angular/angular/pull/61325))                                                                      |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [8163a8995e](https://github.com/angular/angular/commit/8163a8995e36bbce74e3d852613c19e56027cc24)   feat   Add `destroyed` property on `DestroyRef` ([#61849](https://github.com/angular/angular/pull/61849))                    |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [737b35b684](https://github.com/angular/angular/commit/737b35b684663bb641939f05ae12fa11b3395159)   feat   Add `destroyed` property to `EnvironmentInjector` ([#61951](https://github.com/angular/angular/pull/61951))           |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [2e0c98bd3f](https://github.com/angular/angular/commit/2e0c98bd3f2efd1181429b486dd1cebe14385c18)   feat   support bindings in TestBed ([#62040](https://github.com/angular/angular/pull/62040))                                 |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [4356e85456](https://github.com/angular/angular/commit/4356e8545666f13033bb2c4b7fa018d0b97e6f01)   fix    fakeAsync should not depend on module import order ([#61375](https://github.com/angular/angular/pull/61375))          |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [8424b3bcd5](https://github.com/angular/angular/commit/8424b3bcd5b9c78f37dc8ba636c87775937bcc03)   fix    Fixes template outlet hydration ([#61989](https://github.com/angular/angular/pull/61989))                             |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [583b9a7be5](https://github.com/angular/angular/commit/583b9a7be56310f247dcf83dd1ce297b9c6be682)   fix    missing useExisting providers throwing for optional calls ([#61137](https://github.com/angular/angular/pull/61137))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [8f65223bd8](https://github.com/angular/angular/commit/8f65223bd83ee5cdbff6a3c8e99f85d1c69f5375)   fix    update min Node.js support to 20.19, 22.12, and 24.0 ([#61499](https://github.com/angular/angular/pull/61499))        |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [b785256b9e](https://github.com/angular/angular/commit/b785256b9e7f83c9f05fb1afd561f0af49a42e9d)   perf   avoid intermediate arrays in definition ([#61445](https://github.com/angular/angular/pull/61445))                     |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [56769de4d8](https://github.com/angular/angular/commit/56769de4d83a08b8044cd2463341cbd60d40191f)   perf   move property remapping for dom properties to compiler ([#62421](https://github.com/angular/angular/pull/62421))      |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [610bebfce9](https://github.com/angular/angular/commit/610bebfce98d879677244b2ef08b24886891ca76)   fix    Allow ControlState as reset arguments for `FormGroup`/`FormRecord` ([#55860](https://github.com/angular/angular/pull/55860))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [4f0221e193](https://github.com/angular/angular/commit/4f0221e1933675b24bdbf95be3825fdacee13c00)   fix    improve select performance ([#61949](https://github.com/angular/angular/pull/61949))                                           |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [55fa38a1e5](https://github.com/angular/angular/commit/55fa38a1e53926d114b2290c084f3540f50b7266)   feat   add cache & priority support for fetch requests in httpResource ([#62301](https://github.com/angular/angular/pull/62301))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [b6ef42843c](https://github.com/angular/angular/commit/b6ef42843c49e50239b678bb4d8f01ab30589dd3)   feat   add credentials support for fetch requests in httpResource ([#62390](https://github.com/angular/angular/pull/62390))        |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [73269cf5ce](https://github.com/angular/angular/commit/73269cf5ceb4c32473a81a101a79decd06cfe274)   feat   add keepalive support for fetch requests in httpResource ([#61833](https://github.com/angular/angular/pull/61833))          |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [27b7ec0a62](https://github.com/angular/angular/commit/27b7ec0a6219645a5af07c2d409c34311a458374)   feat   add mode & redirect for fetch request in httpResource ([#62337](https://github.com/angular/angular/pull/62337))             |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [f0965c7acd](https://github.com/angular/angular/commit/f0965c7acd2fc2a4a4c18e5a47f3447c4fc7c668)   feat   Add support for fetch credentials options in HttpClient ([#62354](https://github.com/angular/angular/pull/62354))           |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [87322449a3](https://github.com/angular/angular/commit/87322449a33fc727ad8c80b6cc6d0a87a900a6fa)   feat   add support for fetch mode and redirect options in HttpClient ([#62315](https://github.com/angular/angular/pull/62315))     |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [9791ab1b6f](https://github.com/angular/angular/commit/9791ab1b6f8694ada6a0e359003243d89d6c7c97)   feat   Add support for fetch request cache and priority options ([#61766](https://github.com/angular/angular/pull/61766))          |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [aa861c42ff](https://github.com/angular/angular/commit/aa861c42fface06563669c188327700085774e89)   feat   add timeout option on httpResource. ([#62326](https://github.com/angular/angular/pull/62326))                               |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [c4cffe2063](https://github.com/angular/angular/commit/c4cffe2063e790d2f8e4dc8b9c9817f2c4fcc4e7)   feat   Add timeout option to HTTP requests ([#57194](https://github.com/angular/angular/pull/57194))                               |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [cfbbb08437](https://github.com/angular/angular/commit/cfbbb0843727dd7959d73c496307153234ee20b9)   feat   add warning when withCredentials overrides explicit credentials ([#62383](https://github.com/angular/angular/pull/62383))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [20c1f991e6](https://github.com/angular/angular/commit/20c1f991e63b8fc3023a302964d0438bfbfba8f0)   feat   add semantic tokens for templates ([#60260](https://github.com/angular/angular/pull/60260))                                            |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [cf55d1bdd4](https://github.com/angular/angular/commit/cf55d1bdd4201ed99dd876138c50a497b611acb7)   feat   Support importing the external module's export about the angular metadata. ([#61122](https://github.com/angular/angular/pull/61122))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [5d2e85920e](https://github.com/angular/angular/commit/5d2e85920e714560e8d06bfb9c41d9312eeaae3b)   feat   support to fix missing required inputs diagnostic ([#50911](https://github.com/angular/angular/pull/50911))                            |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [9833d9ea47](https://github.com/angular/angular/commit/9833d9ea47b717293c9df0d8a5c285a3c4ad35d0)   feat   Run `loadComponent` and `loadChildren` functions in the route's injection context ([#62133](https://github.com/angular/angular/pull/62133))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [c67dbda8ff](https://github.com/angular/angular/commit/c67dbda8ff76410e0bb7e4b1719125f3197227dd)   feat   support notification closes ([#61442](https://github.com/angular/angular/pull/61442))         |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [6e1df54799](https://github.com/angular/angular/commit/6e1df5479967c2c8b0fadf75e9a9f8c33a342245)   feat   support push subscription changes ([#61856](https://github.com/angular/angular/pull/61856))   |

## `20.1.0` → `20.1.1`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [75d2a349b4](https://github.com/angular/angular/commit/75d2a349b4d0ee1ed0489f1804dc1938046eaace)   fix    incorrect spans for left side of binary operation ([#62641](https://github.com/angular/angular/pull/62641))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [70c8780c54](https://github.com/angular/angular/commit/70c8780c5443929539631a06c5e09c18d108e51b)   fix    more permissive parsing of @ characters ([#62644](https://github.com/angular/angular/pull/62644))             |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [9506cdfaad](https://github.com/angular/angular/commit/9506cdfaad2693a0350a74f4ee4bb7fa27fa3086)   fix    infer type of event target for void elements ([#62648](https://github.com/angular/angular/pull/62648))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [26ade4a337](https://github.com/angular/angular/commit/26ade4a3370911f6c8e9c0e6504d9335d637cfe1)   fix    Ensure application remains unstable during bootstrap ([#62631](https://github.com/angular/angular/pull/62631))   |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [a81f0faa1a](https://github.com/angular/angular/commit/a81f0faa1a72decf9bdd35b243486a510b9352ee)   fix    InputBinding marks component a dirty. ([#62613](https://github.com/angular/angular/pull/62613))                  |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [276836ee73](https://github.com/angular/angular/commit/276836ee7351c5d605fac5dc0abe0ae898dcfa5d)   fix    do not display warnings `Angular detected that a `HttpClient`request with the`keepalive` option was sent using XHR` when option is not true ([#62536](https://github.com/angular/angular/pull/62536))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [5949373692](https://github.com/angular/angular/commit/59493736925d27ca26f0bb041978a51c4ced975b)   fix    handle errors from view transition readiness ([#62535](https://github.com/angular/angular/pull/62535))   |

## `20.1.1` → `20.1.2`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [8ad10fd63b](https://github.com/angular/angular/commit/8ad10fd63b01a906efbfa50ccccb7914610c61bd)   fix    fix detection of directive deps in JIT ([#62666](https://github.com/angular/angular/pull/62666))   |

## `20.1.2` → `20.1.3`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [2c522efbe5](https://github.com/angular/angular/commit/2c522efbe500e7c6c9929ce76df435b3dae49c84)   fix    fix change tracking for Resource#hasValue ([#62595](https://github.com/angular/angular/pull/62595))   |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [2fd1f7beb5](https://github.com/angular/angular/commit/2fd1f7beb5e524aea8dcb24c5b87cb81689363ba)   fix    resolve component resources before bootstrapping in JIT mode ([#62758](https://github.com/angular/angular/pull/62758))   |

## `20.1.3` → `20.1.4`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [db3c5826ee](https://github.com/angular/angular/commit/db3c5826ee0b52e5b7886087b82990340a34c1ab)   fix    exclude more safe reads expression from 2way-binding ([#62852](https://github.com/angular/angular/pull/62852))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [c633b63e56](https://github.com/angular/angular/commit/c633b63e561d7142dd9a1f8631813cc47a169058)   fix    update symbols for new signals api ([#62284](https://github.com/angular/angular/pull/62284))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ab6033979a](https://github.com/angular/angular/commit/ab6033979a3b409738d55d0c01effb378473c05a)   fix    add missing http options allowed in fetch API ([#62881](https://github.com/angular/angular/pull/62881))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [15670d8417](https://github.com/angular/angular/commit/15670d8417449c5b5f2990209552a1fc61420acb)   fix    propagate plain errors when parsing fails ([#62765](https://github.com/angular/angular/pull/62765))       |

## `20.1.4` → `20.1.5`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [3b2e8efcac](https://github.com/angular/angular/commit/3b2e8efcacc5b413b03e4281fc8af297e5c81a9f)   fix    correctly type check host listeners to own outputs ([#62965](https://github.com/angular/angular/pull/62965))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [c9f3976eba](https://github.com/angular/angular/commit/c9f3976eba66d113f4a1919ee91b8833d679733a)   fix    properly recognize failed `fetch` responses when loading external resources in JIT ([#62992](https://github.com/angular/angular/pull/62992))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ae443f8eb0](https://github.com/angular/angular/commit/ae443f8eb00c047bb88527f2311e86df3bc6be35)   fix    Reset headers, progress, and statusCode when using `set()` in `HttpResource` ([#62873](https://github.com/angular/angular/pull/62873))   |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [7a5851e4b0](https://github.com/angular/angular/commit/7a5851e4b0a17da35db7fb276a3dca4909f9137b)   fix    incorrect filtering in inject migration ([#62913](https://github.com/angular/angular/pull/62913))   |

## `20.1.5` → `20.1.6`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|

## `20.1.6` → `20.1.7`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [d9e37908a5](https://github.com/angular/angular/commit/d9e37908a5f42a4226fd6e2d3493abf35ee5a99a)   fix    incorrect spans for AST inside input value with leading space ([#63082](https://github.com/angular/angular/pull/63082))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [4aa120ac00](https://github.com/angular/angular/commit/4aa120ac000a569a29e45e9c6db9e4f32c61d183)   fix    error when type checking host bindings of generic directive ([#63061](https://github.com/angular/angular/pull/63061))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [322042c5b3](https://github.com/angular/angular/commit/322042c5b30e181019bfdaa6a57fc5abaea7adc1)   fix    destroying the effect on `afterRenderEffect` ([#63001](https://github.com/angular/angular/pull/63001))   |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [5fd79424e3](https://github.com/angular/angular/commit/5fd79424e34ea4bbbfca68bf80ca5541aece829f)   fix    attempt to resolve component resources in JIT mode ([#63062](https://github.com/angular/angular/pull/63062))   |

## `20.1.7` → `20.1.8`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [691f5ed033](https://github.com/angular/angular/commit/691f5ed0332d813801f599448577a2c1d450a5ad)   fix    error when ng-content fallback has translated children ([#63156](https://github.com/angular/angular/pull/63156))               |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [b1dec9bc50](https://github.com/angular/angular/commit/b1dec9bc50f5694cfa1e3629fd48543126debd10)   fix    incorrect source span for expression AST inside template attribute ([#63175](https://github.com/angular/angular/pull/63175))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [cda402f1d8](https://github.com/angular/angular/commit/cda402f1d8bddeedc9aca1979a9bf01be32f81b2)   fix    account for expression with type arguments during HMR extraction ([#63261](https://github.com/angular/angular/pull/63261))   |

## `20.1.8` → `20.2.0`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | @angular/animations |
| deprecation | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | The Router.getCurrentNavigation method is deprecated. Use the Router.currentNavigation signal instead. |
| deprecation | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [9766116cea](https://github.com/angular/angular/commit/9766116cea69607d80144251a599f1cc1b12e02c)   refactor   deprecate the animations package ([#62795](https://github.com/angular/angular/pull/62795))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [7767aa640c](https://github.com/angular/angular/commit/7767aa640c542f5058df9322f2bbe974fa8d3c81)   fix    allow more characters in square-bracketed attribute names ([#62742](https://github.com/angular/angular/pull/62742))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [7b51728813](https://github.com/angular/angular/commit/7b517288139aec166e5e5b60e84b1e22e3d6b70f)   fix    fixes animation event host bindings not firing ([#63217](https://github.com/angular/angular/pull/63217))              |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [5abfe4a899](https://github.com/angular/angular/commit/5abfe4a8999e42ad44e6f1d4414f241094bb8fdb)   feat   add diagnostic for uninvoked functions in text interpolation ([#59191](https://github.com/angular/angular/pull/59191))              |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [c4917074f1](https://github.com/angular/angular/commit/c4917074f1e278ea24948a8810b3d4f306765174)   fix    display proper function in NG8117 message ([#62842](https://github.com/angular/angular/pull/62842))                                 |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [812463c563](https://github.com/angular/angular/commit/812463c5636effe5bd5ba5c7c7fc65c3cc08d047)   fix    Ignore diagnostics on ngTemplateContextGuard lines in TCB ([#63054](https://github.com/angular/angular/pull/63054))                 |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [45b030b5ce](https://github.com/angular/angular/commit/45b030b5ce1e116a88fe1c2fe133f654fb1f66c5)   fix    prevent dom event assertion in TCB generation on older angular versions ([#63053](https://github.com/angular/angular/pull/63053))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [6b1f4b9e8b](https://github.com/angular/angular/commit/6b1f4b9e8bb981377e271e6af0d9768ff7f765e9)   feat       add enter and leave animation instructions ([#62682](https://github.com/angular/angular/pull/62682))                          |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [cec91c0035](https://github.com/angular/angular/commit/cec91c00356ee3974c39c9471b243a2a16149f5b)   feat       add option to infer the tag names of components in tests ([#62283](https://github.com/angular/angular/pull/62283))            |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [141bb75ff2](https://github.com/angular/angular/commit/141bb75ff241425a93ce5b60b56a4247e67d7648)   feat       Promote zoneless to stable ([#62699](https://github.com/angular/angular/pull/62699))                                          |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [4138aca91f](https://github.com/angular/angular/commit/4138aca91fe828f0cfbd779d0c456cdea7703bdc)   feat       render ARIA property bindings as attributes ([#62630](https://github.com/angular/angular/pull/62630))                         |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [a409534d6c](https://github.com/angular/angular/commit/a409534d6c3d7cb4472afffd6b17df8c25e34106)   feat       support `as` aliases on `else if` blocks ([#63047](https://github.com/angular/angular/pull/63047))                            |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [745ea44394](https://github.com/angular/angular/commit/745ea4439465494ab5b7002dd1fa320cd32220fb)   feat       support TypeScript 5.9 ([#62541](https://github.com/angular/angular/pull/62541))                                              |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [593cc8a368](https://github.com/angular/angular/commit/593cc8a3684dfb163bfffa265c5efb3bc7efacd1)   fix        checks if body exists before continuing ([#62768](https://github.com/angular/angular/pull/62768))                             |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [bdc31675b7](https://github.com/angular/angular/commit/bdc31675b7e5f37d2b312c766fe4963305620bdf)   fix        ensure animate events do not have duplicate elements ([#63216](https://github.com/angular/angular/pull/63216))                |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [de3a0c5cf3](https://github.com/angular/angular/commit/de3a0c5cf3f87782fa63d30edf6ac05eb6be9fac)   fix        Fix `animate.enter` class removal when composing classes ([#62981](https://github.com/angular/angular/pull/62981))            |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [6597ac0af7](https://github.com/angular/angular/commit/6597ac0af78ac2224ec2f9a37283b53aee11abe1)   fix        fix support for space separated strings in leave animations ([#62979](https://github.com/angular/angular/pull/62979))         |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ebd622b344](https://github.com/angular/angular/commit/ebd622b3449789b72efc8295244ca924a299e7c1)   fix        fixes empty animations when recalculating styles ([#63007](https://github.com/angular/angular/pull/63007))                    |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [455b147488](https://github.com/angular/angular/commit/455b147488dc0a064c0ca13a96a4df3c3ed01152)   fix        fixes timing issues with enter animations ([#62925](https://github.com/angular/angular/pull/62925))                           |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [f9d73cc687](https://github.com/angular/angular/commit/f9d73cc6877d516da4ab4704c21bb19164123fa1)   fix        handle cases where classes added have no animations ([#63242](https://github.com/angular/angular/pull/63242))                 |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [6a1184600c](https://github.com/angular/angular/commit/6a1184600ce0fc7a3f338d6766612e9510ef5518)   fix        prevents duplicate nodes when `@if` toggles with leave animations ([#63048](https://github.com/angular/angular/pull/63048))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [063b5e166f](https://github.com/angular/angular/commit/063b5e166f66bce1abd06c258242212009e76cca)   fix        switch check to documentElement with chaining ([#62773](https://github.com/angular/angular/pull/62773))                       |
| deprecation | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [320de4e96d](https://github.com/angular/angular/commit/320de4e96d250cad1ce2c9f8c0fa2022da53b734)   refactor   deprecate animations field on component interface ([#62895](https://github.com/angular/angular/pull/62895))                   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [c353497a01](https://github.com/angular/angular/commit/c353497a01776cd702af6c5136fdae5fc6ce94d5)   feat   add support for pushing an array of controls to formarray ([#57102](https://github.com/angular/angular/pull/57102))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [0984b30388](https://github.com/angular/angular/commit/0984b30388ef51dfad66f1228f665b89b73ef3fb)   feat   Add redirected property to HttpResponse and HttpErrorResponse ([#62675](https://github.com/angular/angular/pull/62675))         |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [be811fee79](https://github.com/angular/angular/commit/be811fee7925fb482567fa7cd9d485ac28acdade)   feat   add referrer & integrity support for fetch requests in httpResource ([#62461](https://github.com/angular/angular/pull/62461))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [1cf9d9064c](https://github.com/angular/angular/commit/1cf9d9064c15c00071ece3b78c8019035a6db6ce)   feat   Add support for fetch referrer & integrity options in HttpClient ([#62417](https://github.com/angular/angular/pull/62417))      |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [1408baff45](https://github.com/angular/angular/commit/1408baff453e636da05838fa17c6e4abd86c4b72)   fix    Add missing timeout and transferCache options to `HttpClient` ([#62586](https://github.com/angular/angular/pull/62586))         |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [c81e345e72](https://github.com/angular/angular/commit/c81e345e726b5b281621159c789e6d80a9f328e2)   feat   support auto-import for attribute completions ([#62797](https://github.com/angular/angular/pull/62797))          |
| deprecation | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [d64dd27a02](https://github.com/angular/angular/commit/d64dd27a02630b631bc9890d7292d4683493cb65)   feat   support to report the deprecated API in the template ([#62054](https://github.com/angular/angular/pull/62054))   |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [591c7e2ec8](https://github.com/angular/angular/commit/591c7e2ec82c6669ffa6e0011b8a0a4fc12e9c3a)   fix    Support to resolve the re-export component. ([#62585](https://github.com/angular/angular/pull/62585))            |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [52b8e07d6e](https://github.com/angular/angular/commit/52b8e07d6e568a527fae18a8a867dacdf8053e20)   feat   Warns on conflicting hydration and blocking navigation ([#62963](https://github.com/angular/angular/pull/62963))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [d00b3fed58](https://github.com/angular/angular/commit/d00b3fed58496369d9f3a1ac0d74416a586be78b)   feat   add a `currentNavigation` signal to the `Router` service. ([#62971](https://github.com/angular/angular/pull/62971))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [687c374826](https://github.com/angular/angular/commit/687c374826c5e9ea91839c20f0df815ce085c583)   feat   add a currentNavigation signal to the Router service. ([#63011](https://github.com/angular/angular/pull/63011))       |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [9c45c322d1](https://github.com/angular/angular/commit/9c45c322d1ac3b05c916b7c956263066fb9be47f)   fix    ensure preloaded components are properly activated ([#62502](https://github.com/angular/angular/pull/62502))          |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [8255e0cf15](https://github.com/angular/angular/commit/8255e0cf15353e9eee339ae01851e32c0e5e174d)   feat   add messageerror event handling and logging ([#62834](https://github.com/angular/angular/pull/62834))               |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [5220b51e75](https://github.com/angular/angular/commit/5220b51e75e672ff41c90f4798289961973df8e0)   feat   Adds for type in provideServiceWorker ([#62831](https://github.com/angular/angular/pull/62831))                     |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [4ac6171b09](https://github.com/angular/angular/commit/4ac6171b09e449c619e0588c366861f8f3bb59be)   feat   Adds support for updateViaCache in provideServiceWorker ([#62721](https://github.com/angular/angular/pull/62721))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [b65c3d5e19](https://github.com/angular/angular/commit/b65c3d5e195267dd90b2826d4615ced1328b1709)   feat   Improves storage full detection in data caching ([#62737](https://github.com/angular/angular/pull/62737))           |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [3b214d2040](https://github.com/angular/angular/commit/3b214d20403160ab73e65dca0352545efd577c31)   feat   Logs unhandled promise rejections in service worker ([#63059](https://github.com/angular/angular/pull/63059))       |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [6d011687ec](https://github.com/angular/angular/commit/6d011687ec1fa2b8f0211379bb98adc8e02f4e9a)   feat   notify clients about version failures ([#62718](https://github.com/angular/angular/pull/62718))                     |

## `20.2.0` → `20.2.1`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [a28672fb70](https://github.com/angular/angular/commit/a28672fb7017cc62e42829c5910c3b39373d7913)   fix    Keep paraenthesis in Nullish + Boolean expression. ([#63292](https://github.com/angular/angular/pull/63292))   |

## `20.2.1` → `20.2.2`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [d7b6045d61](https://github.com/angular/angular/commit/d7b6045d61582d20a17802e769dc1441984988f0)   fix    fixes animations on elements with structural directives ([#63390](https://github.com/angular/angular/pull/63390))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [6c421ed65d](https://github.com/angular/angular/commit/6c421ed65d050765a18eafc51fe7257abc5682ce)   fix    Ensures `@for` loop animations never get cancelled ([#63328](https://github.com/angular/angular/pull/63328))      |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [9093e0e132](https://github.com/angular/angular/commit/9093e0e132f99c2b590c31b299871bcd493b7de0)   fix    fix memory leak with leaving nodes tracking ([#63328](https://github.com/angular/angular/pull/63328))             |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [c8f07daf8f](https://github.com/angular/angular/commit/c8f07daf8f2c7e8c6641eb4368379a3f5f1d1f52)   fix    Fixes `animate.leave` binding to a string with spaces ([#63366](https://github.com/angular/angular/pull/63366))   |

## `20.2.2` → `20.2.3`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [479a919f42](https://github.com/angular/angular/commit/479a919f42517193653384220adab5b89dd74e3d)   fix    fixes regression with event parsing and animate prefix ([#63470](https://github.com/angular/angular/pull/63470))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [f87fad3fff](https://github.com/angular/angular/commit/f87fad3fff62cebf2868e06cba48e0f27b719d24)   fix    avoid injecting internal error handler from a destroyed injector ([#62275](https://github.com/angular/angular/pull/62275))                                   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [114906d2d6](https://github.com/angular/angular/commit/114906d2d68d98c98961d858abd3ae714d4809a3)   fix    Fix cancellation of animation enter classes ([#63442](https://github.com/angular/angular/pull/63442))                                                        |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [596b545130](https://github.com/angular/angular/commit/596b5451309b8ce4f08a1cd36e6b3610507d52f9)   fix    Prevent an error on cleanup when an `rxResource` `stream` threw before returning an `Observable` ([#63342](https://github.com/angular/angular/pull/63342))   |

## `20.2.3` → `20.2.4`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [dc64f3e478](https://github.com/angular/angular/commit/dc64f3e478c5cc1e354a0ff7cf5965b817b345d6)   fix    Fixed inject migration schematics for migrate destructured properties ([#62832](https://github.com/angular/angular/pull/62832))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [d1d32db972](https://github.com/angular/angular/commit/d1d32db97260c1e57c2937588002feb4271c7774)   fix    prevent false warning for duplicate state serialization ([#63525](https://github.com/angular/angular/pull/63525))   |

## `20.2.4` → `20.3.0`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | The server-side bootstrapping process has been changed to eliminate the reliance on a global platform injector. |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [a3f808d7c8](https://github.com/angular/angular/commit/a3f808d7c8cc59a4fd69f2e4b8d21a6510efa046)   fix    remove refresh button from transfer state tab ([#63592](https://github.com/angular/angular/pull/63592))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [6117ccee2e](https://github.com/angular/angular/commit/6117ccee2e1507fb00549cd70e064282645db803)   feat   introduce `BootstrapContext` for improved server bootstrapping ([#63636](https://github.com/angular/angular/pull/63636))   |

## `20.3.0` → `20.3.1`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [7fb5a8087e](https://github.com/angular/angular/commit/7fb5a8087ee8fb0451cedbe6ac4ce972eca4b56e)   fix    Add support for `aria-invalid` ([#63748](https://github.com/angular/angular/pull/63748))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [8843707919](https://github.com/angular/angular/commit/88437079190cef9ee522a3e2defa6e2672c2d030)   fix    only bind inputs that are part of microsyntax to a structural directive ([#52453](https://github.com/angular/angular/pull/52453))         |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [38c9921ff3](https://github.com/angular/angular/commit/38c9921ff387d235981a79e26dc8bc7e60a2e10c)   fix    signal not invoked diagnostic not raised when input has same name in template ([#63754](https://github.com/angular/angular/pull/63754))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [802dbcc2a0](https://github.com/angular/angular/commit/802dbcc2a0c5d3784cb04b4c78ea71ed0925327c)   fix    prevent animation events from being cleaned up on destroy ([#63414](https://github.com/angular/angular/pull/63414))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [3ec8a5c753](https://github.com/angular/angular/commit/3ec8a5c7536cdd2c1db7db4bfbc2d4995156a833)   fix    Prevent leave animations on a move operation ([#63745](https://github.com/angular/angular/pull/63745))                |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [6e54bdfdcb](https://github.com/angular/angular/commit/6e54bdfdcb01522ee46865fadec911f960fff730)   fix    fix route-lazy-loading migration ([#63818](https://github.com/angular/angular/pull/63818))   |

## `20.3.1` → `20.3.2`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ba40153ac0](https://github.com/angular/angular/commit/ba40153ac07fc721585a1224fda09a654672cb74)   fix    capture metadata for undecorated fields ([#63904](https://github.com/angular/angular/pull/63904))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [1d4f81c8ee](https://github.com/angular/angular/commit/1d4f81c8eedf5ea69c51c720f8dc5c5d12a62ba2)   fix    resolve import alias in defer blocks ([#63966](https://github.com/angular/angular/pull/63966))      |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [9515a70933](https://github.com/angular/angular/commit/9515a709331883f0ca9857ed46a5262b01979a26)   fix    fix narrowing of `Resource.hasValue()` ([#63994](https://github.com/angular/angular/pull/63994))                       |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [e78451cf8a](https://github.com/angular/angular/commit/e78451cf8a48322879e83b33fecc0b5854947afb)   fix    prevent animations renderer from impacting `animate.leave` ([#63921](https://github.com/angular/angular/pull/63921))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [1fd8d5d446](https://github.com/angular/angular/commit/1fd8d5d446f909a16a127ba117a0f423c7a5db0c)   fix    Emit `FormResetEvent` when resetting control ([#64034](https://github.com/angular/angular/pull/64034))   |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [16d0d43ad4](https://github.com/angular/angular/commit/16d0d43ad4903b69b8dcd9b76c48b5089e7f82ee)   fix    handle import aliases to the same module name ([#63934](https://github.com/angular/angular/pull/63934))       |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [3ebaeccb46](https://github.com/angular/angular/commit/3ebaeccb466119ee43eeaa486f5e132c85e9caa2)   fix    handle reused templates in control flow migration ([#63996](https://github.com/angular/angular/pull/63996))   |

## `20.3.2` → `20.3.3`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [f51ab32fb3](https://github.com/angular/angular/commit/f51ab32fb3000ae34c077b049ff2f7b8e3e22d14)   fix    recover template literals with broken expressions ([#64150](https://github.com/angular/angular/pull/64150))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [542cd0019a](https://github.com/angular/angular/commit/542cd0019aa509e399282ccf7cb5fa6208cef70e)   fix    do not rename ARIA property bindings to attributes ([#64089](https://github.com/angular/angular/pull/64089))                       |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [0e928fbc4a](https://github.com/angular/angular/commit/0e928fbc4a351303c4ce081a679f4a38c0acd5e6)   fix    Fixes animations in conjunction with content projection ([#63776](https://github.com/angular/angular/pull/63776))                  |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [e5157bd933](https://github.com/angular/angular/commit/e5157bd933c41836fb431659f42dfb4cdbe0d2d1)   fix    prevents unintended early termination of leave animations and hoisting ([#64088](https://github.com/angular/angular/pull/64088))   |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [1710cbd7d4](https://github.com/angular/angular/commit/1710cbd7d484ccd5e9ab39b95a44e2d222f4262d)   fix    handle shorthand property declarations in NgModule ([#64160](https://github.com/angular/angular/pull/64160))   |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [77b6305a4b](https://github.com/angular/angular/commit/77b6305a4b5db88f9c1130acf80095b502a0eca1)   fix    skip migration for inputs with 'this' references ([#64142](https://github.com/angular/angular/pull/64142))     |

## `20.3.3` → `20.3.4`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [853ed169a8](https://github.com/angular/angular/commit/853ed169a8a1392ef2da7790181fb8e100f59519)   fix    ensure missing leave animations don't queue leave animations ([#64226](https://github.com/angular/angular/pull/64226))                     |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [6fed986b7a](https://github.com/angular/angular/commit/6fed986b7a8f22dfe81d94b1e55490a278e6d82a)   fix    Fixes animations in conjunction with content projection ([#63776](https://github.com/angular/angular/pull/63776))                          |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [76fe5599fe](https://github.com/angular/angular/commit/76fe5599fe8e034c2a5a432608785a53018e23d2)   fix    handle undefined CSS time values in parseCssTimeUnitsToMs function ([#64181](https://github.com/angular/angular/pull/64181))               |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [3b959105be](https://github.com/angular/angular/commit/3b959105be04d7b11a1eb1035f1938bd0c43fe8b)   fix    prevent early exit from leave animations when multiple transitions are present ([#64225](https://github.com/angular/angular/pull/64225))   |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [65884895ff](https://github.com/angular/angular/commit/65884895fff5bc499974849e9ec5a5792eb9e36c)   fix    preserve component imports when pruning NgModules in standalone migration ([#64186](https://github.com/angular/angular/pull/64186))   |

## `20.3.4` → `20.3.5`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [8dec92ff9f](https://github.com/angular/angular/commit/8dec92ff9f1055c6b4fc4e767d8b1b408ac28e67)   fix    capture metadata for undecorated fields ([#63957](https://github.com/angular/angular/pull/63957)) ([#64317](https://github.com/angular/angular/pull/64317))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [c2e817b0ef](https://github.com/angular/angular/commit/c2e817b0efb6f617312936b756ace2c85139d1fc)   perf   fix performance of "interpolated signal not invoked" check ([#64410](https://github.com/angular/angular/pull/64410))                                          |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [f15cfa4cc4](https://github.com/angular/angular/commit/f15cfa4cc414f1d2f4b126bdfc26d74922732672)   fix    fixes regression in `animate.leave` function bindings ([#64413](https://github.com/angular/angular/pull/64413))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [d54dd674ca](https://github.com/angular/angular/commit/d54dd674ca9db874c95027161b8080bd37250af6)   fix    Prevents early style pruning with leave animations ([#64335](https://github.com/angular/angular/pull/64335))      |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [554573e524](https://github.com/angular/angular/commit/554573e5248a72f73df1468e992da08ce5f6112d)   fix    migrating input with more than 1 usage in a method ([#64367](https://github.com/angular/angular/pull/64367))                                                                       |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [2c79ca0b57](https://github.com/angular/angular/commit/2c79ca0b579d99346c267e6b61789699e8656dc5)   fix    remove error for no matching files in control flow migration ([#64253](https://github.com/angular/angular/pull/64253)) ([#64314](https://github.com/angular/angular/pull/64314))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [6e4bcc7d22](https://github.com/angular/angular/commit/6e4bcc7d22d4699a33d6648e628fb65a38d0ad8f)   fix    Scroll restoration should use instant scroll behavior for traversals ([#64299](https://github.com/angular/angular/pull/64299))   |

## `20.3.5` → `20.3.6`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [911d6822cb](https://github.com/angular/angular/commit/911d6822cb18dabf4f72312dfc2e2ef9904bf6c2)   fix    update animation scheduling ([#64441](https://github.com/angular/angular/pull/64441))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [2ece42866d](https://github.com/angular/angular/commit/2ece42866d0ee8240e73ebcef79ba47378777368)   fix    `DomEventsPlugin` should always be the last plugin to be called for `supports()`. ([#50394](https://github.com/angular/angular/pull/50394))   |

## `20.3.6` → `20.3.7`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [bd38cd45a5](https://github.com/angular/angular/commit/bd38cd45a5fb81e92b91e582d7b13aa3b21f3839)   fix    account for `Element.animate` exceptions ([#64506](https://github.com/angular/angular/pull/64506))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [891f180262](https://github.com/angular/angular/commit/891f18026243bcf8c8b82881a73dffa283d0dd11)   fix    correctly compile long numeric HTML entities ([#64297](https://github.com/angular/angular/pull/64297))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [371274bfc6](https://github.com/angular/angular/commit/371274bfc6d5690390f90161106b60d80939fe75)   fix    missingStructuralDirective diagnostic produces false negatives ([#64470](https://github.com/angular/angular/pull/64470))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [4c89a267c3](https://github.com/angular/angular/commit/4c89a267c3b49e928332232ec2a3023f6fb4046d)   fix    pass element removal property through in all locations ([#64565](https://github.com/angular/angular/pull/64565))                         |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [2fad4d4ab6](https://github.com/angular/angular/commit/2fad4d4ab63a2a8326af02b0f2f7d285c7f42e0d)   fix    prevent duplicate nodes from being retained with fast `animate.leave`` calls ([#64592](https://github.com/angular/angular/pull/64592))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [cfd8ed3fff](https://github.com/angular/angular/commit/cfd8ed3fff02af93b3fbd2e3f3a47128bd3582bf)   fix    Fix outlet serialization and parsing with no primary children ([#64505](https://github.com/angular/angular/pull/64505))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [182fe78f91](https://github.com/angular/angular/commit/182fe78f91d04ac8d25a32bce0ea180a6fe557ce)   fix    Surface parse errors in Router.parseUrl ([#64503](https://github.com/angular/angular/pull/64503))                         |

## `20.3.7` → `20.3.9`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|

## `20.3.9` → `20.3.10`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [840db59dc1](https://github.com/angular/angular/commit/840db59dc1a9beb0b4e63799b5d56c2f096a1bab)   fix    make required inputs diagnostic less noisy   |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [a45e6b2b66](https://github.com/angular/angular/commit/a45e6b2b66f669c532d6bffbab65058edabcacd9)   fix    Prevent removal of templates referenced with preceding whitespace characters   |

## `20.3.10` → `20.3.11`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [5047849a4a](https://github.com/angular/angular/commit/5047849a4a1857471b78b7ba874f39ecd6175a6b)   fix    remove placeholder image listeners once view is removed   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [f9d0818087](https://github.com/angular/angular/commit/f9d08180876eb0aee5e5c489be734b07a7cc664e)   fix    support arbitrary nesting in :host-context()         |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [106b9040df](https://github.com/angular/angular/commit/106b9040dfe03bd8deb0eabccc29e07f734b6ab5)   fix    support commas in :host() argument                   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [9419ea348a](https://github.com/angular/angular/commit/9419ea348a296b50f13ac2e23ea9a00b336989b8)   fix    support complex selectors in :nth-child()            |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [036c5d2a07](https://github.com/angular/angular/commit/036c5d2a073f8e48704ec0d405ca997eedb721e9)   fix    support one additional level of nesting in :host()   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [dcdd1bcdbb](https://github.com/angular/angular/commit/dcdd1bcdbbd2a2fb4bd1fc4330259824d0bc8cb9)   fix    skip leave animations on view swaps   |

## `20.3.11` → `20.3.12`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|

## `20.3.12` → `20.3.13`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|

## `20.3.13` → `20.3.14`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [0276479e7d](https://github.com/angular/angular/commit/0276479e7d0e280e0f8d26fa567d3b7aa97a516f)   fix    prevent XSRF token leakage to protocol-relative URLs   |

## `20.3.14` → `20.3.15`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [d1ca8ae043](https://github.com/angular/angular/commit/d1ca8ae04390f050039fdb653a6147d75d48f81e)   fix    prevent XSS via SVG animation `attributeName` and MathML/SVG URLs   |

## `20.3.15` → `20.3.16`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [c2c2b4aaa8](https://github.com/angular/angular/commit/c2c2b4aaa84c67d2eccd4ef4f94b5ea444a7f73a)   fix   sanitize sensitive attributes on SVG script elements   |

## `20.3.16` → `20.3.17`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | Angular now only applies known attributes from HTML in translated ICU content. Unknown attributes are dropped and not rendered. |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [7f9de3c118](https://github.com/angular/angular/commit/7f9de3c118383c09fa8851708c66ec94453a9680)   fix   block creation of sensitive URI attributes from ICU messages   |

## `20.3.17` → `20.3.18`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [02fbf08890](https://github.com/angular/angular/commit/02fbf08890ec6ac2efb6c2ec4f17e56497cb81d2)   fix   disallow translations of iframe src   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [72126f9a08](https://github.com/angular/angular/commit/72126f9a08c185a9b93461bab67841c4e84c9b17)   fix   sanitize translated attribute bindings with interpolations   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [626bc8bc20](https://github.com/angular/angular/commit/626bc8bc20e485cad2094c4a5d9417fb9a71dda8)   fix   sanitize translated form attributes   |

## `20.3.18` → `20.3.19`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [303d4cd580](https://github.com/angular/angular/commit/303d4cd580dec38bfaa71a0a34965f151bab3ba8)   fix   prevent SSRF bypasses via protocol-relative and backslash URLs   |

## `20.3.19` → `20.3.20`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [a9bcffdbc7](https://github.com/angular/angular/commit/a9bcffdbc7697715f3d4fa91d924a5b905d637b0)   fix   disallow event attribute bindings in host bindings unconditionally ([#68468](https://github.com/angular/angular/pull/68468))   |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [97eeb45cfa](https://github.com/angular/angular/commit/97eeb45cfa5fbd89013d75b5d862095d34b8ba58)   fix   validate security-sensitive attributes in i18n bindings ([#68468](https://github.com/angular/angular/pull/68468))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [25e4e07238](https://github.com/angular/angular/commit/25e4e07238021a3641f96bb5f5648d74a83f1712)   fix   ensure origin has a trailing slash when parsing url ([#68468](https://github.com/angular/angular/pull/68468))   |

## `20.3.20` → `20.3.21`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [f584840e2e](https://github.com/angular/angular/commit/f584840e2e50f751397cf3fad5258e18e857427e)   fix   add `allowedHosts` option to `renderModule` and `renderApplication`   |

## `20.3.21` → `20.3.22`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [3d135ce59b](https://github.com/angular/angular/commit/3d135ce59bbf7426825bc493bc681f266846ac79)   fix   add upper bounds for digitsInfo   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [39a4b4cc8e](https://github.com/angular/angular/commit/39a4b4cc8e8d101a566a70658707bc9f53dd5883)   fix   sanitize placeholder   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [8f35b182b1](https://github.com/angular/angular/commit/8f35b182b1479ed80d652f185c2c3ee5a82ea34c)   fix   normalize tag names with custom namespaces in DomElementSchemaRegistry ([#68926](https://github.com/angular/angular/pull/68926))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [64a89e917a](https://github.com/angular/angular/commit/64a89e917a0794a3d74713bdb4c9c63d703b317b)   fix   sanitize dynamic href and xlink:href bindings on SVG a elements ([#68926](https://github.com/angular/angular/pull/68926))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [6404edfe0a](https://github.com/angular/angular/commit/6404edfe0af3f27cb96737e72907553fb924d88a)   fix   strip namespaced SVG script elements during template compilation ([#68926](https://github.com/angular/angular/pull/68926))   |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [e345a58069](https://github.com/angular/angular/commit/e345a58069ede97250af449f5b7e9b94f828d30c)   fix   normalize tag names in runtime i18n attribute security context lookup ([#68926](https://github.com/angular/angular/pull/68926))   |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [d86e4e7b2a](https://github.com/angular/angular/commit/d86e4e7b2ad0e667aeb0f8ed053e2cb2bd154b81)   fix   reject script element as a dynamic component host ([#68926](https://github.com/angular/angular/pull/68926))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [af04936045](https://github.com/angular/angular/commit/af04936045707dc871e135ebb7b8cd357ac154df)   fix   sanitize meta selectors   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [dc631efa96](https://github.com/angular/angular/commit/dc631efa96e787bee1277f324208f21c36c1fa71)   fix   support prefix-insensitive DOM schema lookups and compile-time i18n attribute validation ([#68926](https://github.com/angular/angular/pull/68926))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [909ef047b3](https://github.com/angular/angular/commit/909ef047b3f93b44a7ba390332707239af2f73fe)   fix   synchronize core sanitization schema with compiler ([#68926](https://github.com/angular/angular/pull/68926))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [de7b2a62e7](https://github.com/angular/angular/commit/de7b2a62e7eded747c2a520c177cd41f60a96dcd)   fix   exclude withCredentials requests from transfer cache   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [4233188d8e](https://github.com/angular/angular/commit/4233188d8e70283190ea87dbaa5a872269291b4a)   fix   skip TransferCache for cookie-bearing requests by default   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [49a60f6045](https://github.com/angular/angular/commit/49a60f60451a0772fb5de9e231a1872081b0467f)   fix   secure location and document initialization against SSRF and path hijack   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [5fdfd8a998](https://github.com/angular/angular/commit/5fdfd8a9983c2a19415afe26c03ffd544278a28f)   fix   preserve redirect policy on reconstructed asset requests   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [83b022f2d0](https://github.com/angular/angular/commit/83b022f2d063b6b3171c2621f3d52c11971aacff)   fix   Preserves explicit 'credentials: omit' in asset requests   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [e617fa06eb](https://github.com/angular/angular/commit/e617fa06ebad6e8495ff8f662805a24df73a78d4)   fix   Preserves HTTP cache mode in asset group requests   |

## `20.3.22` → `20.3.23`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [d40acc6431](https://github.com/angular/angular/commit/d40acc6431997b304ec54c951e55d2e52ed6f6dc)   fix   prevent namespaced SVG <style> elements from being stripped   |

## `20.3.23` → `20.3.24`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [6ca433e56b](https://github.com/angular/angular/commit/6ca433e56bcf74fdb6ad01d3afdf59628fba69b6)   fix   throw on suspicious URLs and restrict protocol-relative URLs   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [8680b5152f](https://github.com/angular/angular/commit/8680b5152fe58ebde81e331b74ba806fc86514cc)   fix   update domino to latest version   |

## `20.3.24` → `21.0.0`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| behavioral | inferred | https://github.com/angular/angular/releases/tag/21.0.0 | * Previously hidden type issues in host bindings may show up in your builds. Either resolve the type issues or set `"typeCheckHostBindings": false` in the `angularCompilerOptions` section of your tsconfig. |
| behavioral | inferred | https://github.com/angular/angular/releases/tag/21.0.0 | * TypeScript versions less than 5.9 are no longer supported. |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | [Blog post "Announcing Angular v21"](http://goo.gle/angular-v21-blog). |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | (test only) - `TestBed` now provides a fake `PlatformLocation` |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | `ngComponentOutletContent` is now of type `Node[][]   undefined` instead of `any[][]   undefined`. |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | NgModuleFactory has been removed, use NgModule instead. |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | - Previously hidden type issues in host bindings may show up in your builds. Either resolve the type issues or set `"typeCheckHostBindings": false` in the `angularCompilerOptions` section of your tsconfig. |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | The Angular compiler now produces an error when the |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | The server-side bootstrapping process has been changed to eliminate the reliance on a global platform injector. |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | Using a combination of `provideZoneChangeDetection` |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | - TypeScript versions less than 5.9 are no longer supported. |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | (test only) - Using `provideZoneChangeDetection` in the |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | `ignoreChangesOutsideZone` is no longer available as an |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | Angular no longer provides a change detection scheduler |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | `moduleId` was removed from `Component` metadata. |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | The `interpolation` option on Components has been removed. Only the default `{{ ... }}` is now supported. |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | Fix signal input getter behavior in custom elements. |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | Decorator Input: `elementRef.oldInput` |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | Signal Input: `elementRef.newInput()` |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | Signal Input: `elementRef.newInput` |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | This new directive will conflict with existing FormArray directives or formArray inputs on the same element. |
| deprecation | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | The deprecated `ApplicationConfig` export from `@angular/platform-browser` has been removed. |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | `lastSuccessfulNavigation` is now a signal and needs to be invoked |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | Router navigations may take several additional |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | `UpgradeAdapter` is no longer available. Use |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | IE/Non-Chromium Edge are not supported anymore. |
| deprecation | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md | `HttpResponseBase.statusText` is deprecated |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [c795960ada](https://github.com/angular/angular/commit/c795960ada1a7e21b8bee411e20a08c700b6e385)   feat       Add experimental support for the Navigation API ([#63406](https://github.com/angular/angular/pull/63406))        |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [9eac43cf46](https://github.com/angular/angular/commit/9eac43cf46993442e9de5764e2ccca98e3837939)   feat       Support of optional keys for the KeyValue pipe ([#48814](https://github.com/angular/angular/pull/48814))         |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [a1868c9d13](https://github.com/angular/angular/commit/a1868c9d13991d24f893499406b29a5f2e0a388b)   feat       update to cldr 47 ([#64032](https://github.com/angular/angular/pull/64032))                                      |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [196fa500a3](https://github.com/angular/angular/commit/196fa500a3c282af5158fa2873df8e2a73243493)   fix        properly type ngComponentOutlet ([#64561](https://github.com/angular/angular/pull/64561))                        |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [7a4b225c57](https://github.com/angular/angular/commit/7a4b225c57d8e390ec06731f5211d52d14da3a9c)   refactor   improve typing of `ngComponentOutletContent` ([#63674](https://github.com/angular/angular/pull/63674))           |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [25f593ce2a](https://github.com/angular/angular/commit/25f593ce2a623add0cbd4ab3bb0d4987793e4f34)   refactor   remove`ngModuleFactory` input of `NgComponentOutlet` ([#62838](https://github.com/angular/angular/pull/62838))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ecea909bcc](https://github.com/angular/angular/commit/ecea909bccc3d6a3c33e77e1feb4ad0926e72f9e)   fix    don't choke on unbalanced parens in declaration block   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [04dd75ba94](https://github.com/angular/angular/commit/04dd75ba948889601bf611254021577aba458d4c)   fix    support arbitrary nesting in :host-context()            |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [f54cc4f28a](https://github.com/angular/angular/commit/f54cc4f28abb9ded190ae33619e5ca7073df08a6)   fix    support commas in :host() argument                      |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [814b2713f5](https://github.com/angular/angular/commit/814b2713f56f94372db7e15e0a86f089a88f888d)   fix    support complex selectors in :nth-child()               |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [aad6ced0ef](https://github.com/angular/angular/commit/aad6ced0ef5e535d1a6eae7c79df4e03ea73b7f2)   fix    support one additional level of nesting in :host()      |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [563dbd998c](https://github.com/angular/angular/commit/563dbd998c86e850b3c4dde4c7cee00d7c9d7581)   feat   Adds diagnostic for misconfigured `@defer` triggers ([#64069](https://github.com/angular/angular/pull/64069))                            |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [0571b335b9](https://github.com/angular/angular/commit/0571b335b9b11459b73a19679671eae97fbe1683)   feat   enable type checking of host bindings by default ([#63654](https://github.com/angular/angular/pull/63654))                               |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [5b55200edf](https://github.com/angular/angular/commit/5b55200edfd12fa7dcdb6570885e0c52a9cc5ec0)   fix    allow value to be set on radio fields                                                                                                    |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ab98b2425f](https://github.com/angular/angular/commit/ab98b2425f4c4cb59927aa686818ecee99e634c7)   fix    capture metadata for undecorated fields ([#63957](https://github.com/angular/angular/pull/63957))                                        |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [be7110342b](https://github.com/angular/angular/commit/be7110342b61d837822524d4f60f56a7f859f594)   fix    disallow compiling with the `emitDeclarationOnly` TS compiler option enabled ([#61609](https://github.com/angular/angular/pull/61609))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [bd322ca410](https://github.com/angular/angular/commit/bd322ca4100c8e51df7c71377161c2c9412d1b83)   fix    do not flag custom control required inputs as missing when field is present                                                              |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [471da8a311](https://github.com/angular/angular/commit/471da8a311fa7f77815bdf0199943cfa50d45181)   fix    infer type of custom field controls                                                                                                      |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [96cb0cffda](https://github.com/angular/angular/commit/96cb0cffda55516e01613958d1268872f1070722)   fix    infer types of signal forms set on native inputs                                                                                         |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [71ab11ccf0](https://github.com/angular/angular/commit/71ab11ccf0f0daaffb49779d5f90b9e2da76dbd5)   fix    make field detection logic more robust                                                                                                   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [1f389b8b97](https://github.com/angular/angular/commit/1f389b8b97600ee382ff842e066abc2ca31c442f)   fix    missingStructuralDirective diagnostic produces false negatives ([#64579](https://github.com/angular/angular/pull/64579))                 |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [7fd3db0423](https://github.com/angular/angular/commit/7fd3db04232d63f1b48ec389bbb62d9ca277fcf9)   fix    remove internal syntax-related flags ([#63787](https://github.com/angular/angular/pull/63787))                                           |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [c371251e4c](https://github.com/angular/angular/commit/c371251e4c2e7bc1ab6da7c51b05e047bdfe6068)   fix    report invalid bindings on form controls                                                                                                 |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [01290ab275](https://github.com/angular/angular/commit/01290ab275599ee6887f9c2139a16f833eaa7071)   fix    use any when checking field interface conformance                                                                                        |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [809a4ed8c1](https://github.com/angular/angular/commit/809a4ed8c110ca930cb1c6bad309f8bfcaf7ceb8)   feat       Add migration for zoneless by default. ([#63042](https://github.com/angular/angular/pull/63042))                                            |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [2a7a5de53f](https://github.com/angular/angular/commit/2a7a5de53fd6fb5714c06c63dd1dad5718086083)   feat       Allow passing application providers in `bootstrapModule` options ([#64354](https://github.com/angular/angular/pull/64354))                  |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [28926ba92c](https://github.com/angular/angular/commit/28926ba92cf3da7e45a7b8938bba49febdf58eb7)   feat       introduce `BootstrapContext` for improved server bootstrapping ([#63562](https://github.com/angular/angular/pull/63562))                    |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [c2d376b85a](https://github.com/angular/angular/commit/c2d376b85aa6eea2c4d7ec3207df6767f5739945)   feat       make SimpleChanges generic ([#64535](https://github.com/angular/angular/pull/64535))                                                        |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ad2376435b](https://github.com/angular/angular/commit/ad2376435b4bcfdb695d841272f8234ab2a7cca5)   feat       support IntersectionObserver options in viewport triggers ([#64130](https://github.com/angular/angular/pull/64130))                         |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [539717f58a](https://github.com/angular/angular/commit/539717f58a9bff1f8aacc857657b7df573d0bb70)   feat       support regular expressions in templates ([#63887](https://github.com/angular/angular/pull/63887))                                          |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ab415f3d7f](https://github.com/angular/angular/commit/ab415f3d7f23cef8e00595e9cf6af2c8b764a8ae)   fix        control not recognized when input has directive injecting ViewContainerRef ([#64368](https://github.com/angular/angular/pull/64368))        |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [f008045ded](https://github.com/angular/angular/commit/f008045dedc773f70dd6f1ced73e689fb4436d6d)   fix        do not rename ARIA property bindings to attributes ([#63925](https://github.com/angular/angular/pull/63925))                                |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [1352fbdbf2](https://github.com/angular/angular/commit/1352fbdbf2542c39715045c7a6c0f6aa41516b02)   fix        Drop special-case disables automatic change detection scheduling ([#63846](https://github.com/angular/angular/pull/63846))                  |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [c0791e1887](https://github.com/angular/angular/commit/c0791e1887590b862bfed9333c5c90be3ac487d0)   fix        drop support for TypeScript 5.8 ([#63589](https://github.com/angular/angular/pull/63589))                                                   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [aa389a691b](https://github.com/angular/angular/commit/aa389a691bc2e5726a0ded73d30962c29faab680)   fix        ensure `@for` iteration over field is reactive ([#64113](https://github.com/angular/angular/pull/64113))                                    |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [fec7c288e9](https://github.com/angular/angular/commit/fec7c288e96dd32f5861124384dbef4d5350d437)   fix        Error on invalid APP_ID ([#63252](https://github.com/angular/angular/pull/63252))                                                           |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [d399d7d02b](https://github.com/angular/angular/commit/d399d7d02b66c485cc5479dabd349d017a002692)   fix        Explicit Zone CD in TestBed providers should not override TestBed error handler ([#63404](https://github.com/angular/angular/pull/63404))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [92e09adc0a](https://github.com/angular/angular/commit/92e09adc0a191ec599915e20b0835bf455bc572b)   fix        Remove ignoreChangesOutsideZone option ([#62700](https://github.com/angular/angular/pull/62700))                                            |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [45fed3d201](https://github.com/angular/angular/commit/45fed3d2011bf6feffa8ee1365a5c88d603f826c)   fix        Remove Zone-based change provider from internals by default ([#63382](https://github.com/angular/angular/pull/63382))                       |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [c9f977833e](https://github.com/angular/angular/commit/c9f977833ebed6f89afd38f65c03e9b3808f2b07)   fix        skip Angular formatting when formatting signals recursively                                                                                 |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [67fbd5ff1e](https://github.com/angular/angular/commit/67fbd5ff1eef80d98e5e9c633a15bb1ae27134bb)   fix        SSR error in signal forms                                                                                                                   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [c241038111](https://github.com/angular/angular/commit/c241038111cf602669dd68ef516f147889ab02e5)   fix        update symbols ([#64481](https://github.com/angular/angular/pull/64481))                                                                    |
| dependency_upgrade | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [a5e5dbbc16](https://github.com/angular/angular/commit/a5e5dbbc16f605cce6dd72a82ddb9110e655a89b)   refactor   remove `moduleId` from Component metadata ([#63482](https://github.com/angular/angular/pull/63482))                                         |
| deprecation | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [9a16718b13](https://github.com/angular/angular/commit/9a16718b13a03df2941c31cb968dcbfa6904a481)   refactor   remove deprecated `interpolation` option on Components. ([#63474](https://github.com/angular/angular/pull/63474))                           |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [be0455adda](https://github.com/angular/angular/commit/be0455adda7d92f741105b3599e7922f099cc024)   fix    return value on signal input getter ([#62113](https://github.com/angular/angular/pull/62113))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [a278ee358c](https://github.com/angular/angular/commit/a278ee358c4d111cf29eb8d3d8eb1fe1799c8495)   feat   add `debounce()` rule for signal forms                                                                                                      |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [b8314bd340](https://github.com/angular/angular/commit/b8314bd3409500b8540d1ce00a330fdb2f0fc83a)   feat   add experimental signal-based forms ([#63408](https://github.com/angular/angular/pull/63408))                                               |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [0dd95c503f](https://github.com/angular/angular/commit/0dd95c503f4b07b478e505b99aaa63419a340095)   feat   Add FormArrayDirective ([#55880](https://github.com/angular/angular/pull/55880))                                                            |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [d201cd2c2b](https://github.com/angular/angular/commit/d201cd2c2bdb418fd1b595320855c35eb91e1e5b)   feat   Prevents marking fields as touched/dirty when state is hidden/readonly/disabled ([#63633](https://github.com/angular/angular/pull/63633))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [9c5e969f51](https://github.com/angular/angular/commit/9c5e969f51448aad05a7e0ac83143b4b5ae477b4)   fix    bind invalid input in custom controls ([#64526](https://github.com/angular/angular/pull/64526))                                             |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [10ef96adb3](https://github.com/angular/angular/commit/10ef96adb3d989781c7ec5116a70b6518866ee27)   fix    consistent treatment of empty ([#63456](https://github.com/angular/angular/pull/63456))                                                     |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [d89e522a1f](https://github.com/angular/angular/commit/d89e522a1f07c4b2ac7fd2b926ae44658f9394d4)   fix    debounce updates from interop controls                                                                                                      |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [c0d88c37c9](https://github.com/angular/angular/commit/c0d88c37c983991236177a0337f5cab75054abf7)   fix    Emit `FormResetEvent` when resetting control ([#64024](https://github.com/angular/angular/pull/64024))                                      |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [94b0afec00](https://github.com/angular/angular/commit/94b0afec0007f0f5142a39def2849a1ba9e5030d)   fix    implement interoperability between signal forms and reactive forms ([#64471](https://github.com/angular/angular/pull/64471))                |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [a1ac9a6415](https://github.com/angular/angular/commit/a1ac9a64154c0a9206e11343b195f287dba3425d)   fix    interop supports CVAs with signals ([#64618](https://github.com/angular/angular/pull/64618))                                                |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [505bde1fed](https://github.com/angular/angular/commit/505bde1fede95ec907c6b028db4b3c9237899f30)   fix    mark field as dirty when value is changed by `ControlValueAccessor` ([#64471](https://github.com/angular/angular/pull/64471))               |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [3529877772](https://github.com/angular/angular/commit/3529877772f7a777d467c99e3d95b465b1b1d82c)   fix    mark field as dirty when value is changed by a bound control ([#64483](https://github.com/angular/angular/pull/64483))                      |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [fd9af2afaf](https://github.com/angular/angular/commit/fd9af2afaf6c239bbbba50f2f016ecf9b83133c4)   fix    only propagate schema defined properties from field to control ([#64446](https://github.com/angular/angular/pull/64446))                    |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [91d8d55a80](https://github.com/angular/angular/commit/91d8d55a80a1d1894827ef06e38e56de6e661575)   fix    Set error message of a schema error.                                                                                                        |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [f4d1017c25](https://github.com/angular/angular/commit/f4d1017c25813b290697d8e1a829983a7b1bca27)   fix    test that common field states are propagated to controls ([#63884](https://github.com/angular/angular/pull/63884))                          |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [acd7c83597](https://github.com/angular/angular/commit/acd7c83597ad376ec9a48421b3b291951ca2d75e)   fix    test that min/max properties are propagated to controls ([#63884](https://github.com/angular/angular/pull/63884))                           |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [71e8672837](https://github.com/angular/angular/commit/71e8672837eb6c2da2570eb2341e896fbf7ca5a3)   fix    test that minLength/maxLength properties are propagated to controls ([#63884](https://github.com/angular/angular/pull/63884))               |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [507b3466ee](https://github.com/angular/angular/commit/507b3466eec648a706f10d2805e67e53522e9654)   perf   implement change detection for field control bindings                                                                                       |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [781a3299f9](https://github.com/angular/angular/commit/781a3299f9e16e16902f12f7e7c80c10f15f788a)   perf   only update interop controls when bound field changes                                                                                       |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [32f86d35f7](https://github.com/angular/angular/commit/32f86d35f7cd177b6e4525a7ae97909888d9fee4)   perf   optimize `[field]` binding instructions ([#64351](https://github.com/angular/angular/pull/64351))                                           |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [2739b7975b](https://github.com/angular/angular/commit/2739b7975ba40a8cfc3b00f0c444a3a147f7f553)   feat       add referrerPolicy option to HttpResource ([#64283](https://github.com/angular/angular/pull/64283))                        |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [07e678872f](https://github.com/angular/angular/commit/07e678872f91236f5c258f98a7aea536b5a200ac)   feat       Add reponseType property to HttpResponse and HttpErrorResponse ([#63043](https://github.com/angular/angular/pull/63043))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [5cbdefcf11](https://github.com/angular/angular/commit/5cbdefcf118e9c228bc887be30114afc84a4db2a)   feat       add support for fetch referrerPolicy option in HttpClient ([#64116](https://github.com/angular/angular/pull/64116))        |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [4bed062bc9](https://github.com/angular/angular/commit/4bed062bc9f2a0a66c9af3cb8aeb42ee023c6393)   feat       Provide http services in root ([#56212](https://github.com/angular/angular/pull/56212))                                    |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [0e4e17cd97](https://github.com/angular/angular/commit/0e4e17cd97d7a5f7ccc40405ba2103a78e1e1298)   refactor   `HttpResponseBase.statusText` ([#64176](https://github.com/angular/angular/pull/64176))                                    |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [3f7111a9c3](https://github.com/angular/angular/commit/3f7111a9c38c6fd00af705a3045f2909f47b505b)   fix    fix directory renaming on Windows   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [89095946cf](https://github.com/angular/angular/commit/89095946cff051c5613b8f54ec722d08cd47c709)   fix    address potential memory leak during project creation                                                           |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [80e00ff4e5](https://github.com/angular/angular/commit/80e00ff4e5833c35e19cfca271dff51121108333)   fix    prevent interpolation from superseding block braces ([#64392](https://github.com/angular/angular/pull/64392))   |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [6ddb250391](https://github.com/angular/angular/commit/6ddb2503913fa8698a0e07e88ce49598cc7af481)   feat   add migration to convert ngClass to use class ([#62983](https://github.com/angular/angular/pull/62983))                  |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [8dc8914c8a](https://github.com/angular/angular/commit/8dc8914c8a2be44e30b512670628a558bdd7f1f4)   feat   add migration to convert ngStyle to use style ([#63517](https://github.com/angular/angular/pull/63517))                  |
| deprecation | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [861cee34e0](https://github.com/angular/angular/commit/861cee34e0e9b5562cfe70d245f30b7ddea7d8fd)   feat   Adds migration for deprecated router testing module ([#64217](https://github.com/angular/angular/pull/64217))            |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [75fc16b261](https://github.com/angular/angular/commit/75fc16b261de5312c60834330680052f07138480)   feat   Adds support for CommonModule to standalone migration ([#64138](https://github.com/angular/angular/pull/64138))          |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [655a99d0c6](https://github.com/angular/angular/commit/655a99d0c60f70bbc14968133cfe6ab251cedc92)   fix    fix bug in ngclass-to-class migration ([#63617](https://github.com/angular/angular/pull/63617))                          |
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [62bbce63b7](https://github.com/angular/angular/commit/62bbce63b7abcb22f1fd453c59e0063aae3b189c)   fix    remove error for no matching files in control flow migration ([#64253](https://github.com/angular/angular/pull/64253))   |
| deprecation | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [ce8db665f9](https://github.com/angular/angular/commit/ce8db665f984005264de0eb8b452370972823c17)   refactor   remove deprecated `ApplicationConfig` export ([#63529](https://github.com/angular/angular/pull/63529))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [4e0fc81491](https://github.com/angular/angular/commit/4e0fc81491bfe6e4eac5c59ef0bde908a3d58413)   feat   convert `lastSuccessfulNavigation` to signal ([#63057](https://github.com/angular/angular/pull/63057))                        |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [5e61e8d3c3](https://github.com/angular/angular/commit/5e61e8d3c3a80b21116e3188805de556e4f0c496)   fix    Fix memory leak through Navigation.abort and canDeactivate guards ([#64141](https://github.com/angular/angular/pull/64141))   |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [f6a73f1913](https://github.com/angular/angular/commit/f6a73f19131b2befa74f4ea3f941038603958ac0)   fix    Respect custom `UrlSerializer` handling of query parameters ([#64449](https://github.com/angular/angular/pull/64449))         |
| behavioral | inferred | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [5b53535dd1](https://github.com/angular/angular/commit/5b53535dd16af7d3ea7b0216984560fd2223d76c)   fix    Update recognize stage to use internally async/await ([#62994](https://github.com/angular/angular/pull/62994))                |
| deprecation | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [f86846555b](https://github.com/angular/angular/commit/f86846555bba44b2fb71d012fe4eebf82a0f5d00)   fix    Remove deprecated UpgradeAdapter ([#61659](https://github.com/angular/angular/pull/61659))   |

