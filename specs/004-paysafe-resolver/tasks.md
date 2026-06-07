# Tasks: Paysafe Internal Library Version Resolver

**Input**: Design documents from `specs/004-paysafe-resolver/`

**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓, quickstart.md ✓

**Format**: `[ID] [P?] [Story?] Description — file path`

- **[P]**: Parallelizable (different files, no incomplete dependencies)
- **[Story]**: User story label (US1–US5)
- All paths are relative to repo root

---

## Phase 1: Setup (Infrastructure & Package Skeleton)

**Purpose**: Create config, dependencies, shared data-model types, and module skeletons before
any business logic is written. The data-model types task (T005) MUST precede all implementation
tasks so that findit.py, gitlab.py, and resolver.py share a single definition of every return type.

- [x] T001 Correct `FINDIT_BASE_URL` default from `findit.paysafe.com` to `findit-api.icd.paysafe.cloud` in `migration_oracle/config.py`
- [x] T002 Add `GITLAB_API_KEY: str = _optional("GITLAB_API_KEY", "")` to `migration_oracle/config.py` (after `FINDIT_AUTH_TOKEN`)
- [x] T003 Add `"packaging>=24.0"` to `[project] dependencies` in `pyproject.toml` and run `uv sync`
- [x] T004 [P] Create `tests/paysafe/__init__.py` (empty) so pytest discovers the test package
- [x] T005 Define shared Python types (TypedDict or dataclass) for `ResolverResult`, `NameResolution`, `CompatibilityInfo`, `ErrorResponse`, `ResolveRequest` matching `data-model.md` exactly — all implementations import from this file in `migration_oracle/paysafe/_types.py`
- [x] T006 Create `migration_oracle/paysafe/__init__.py` with stub: `from migration_oracle.paysafe.resolver import resolve; __all__ = ["resolve"]`
- [x] T007 [P] Create `migration_oracle/paysafe/resolver.py` with empty `resolve()` stub (imports `_types`) returning `{"status": "error", "error": {"error_code": "not_implemented"}}`
- [x] T008 [P] Create `migration_oracle/paysafe/findit.py` with empty `lookup()` stub (imports `_types`) raising `NotImplementedError`
- [x] T009 [P] Create `migration_oracle/paysafe/gitlab.py` with empty `list_tags()`, `fetch_framework_version()`, `detect_framework_at_head()` stubs (imports `_types`)
- [x] T010 [P] Verify `uv run pytest tests/paysafe/ -v` collects zero tests and exits 0; verify `from migration_oracle.paysafe import resolve` imports without error

**Checkpoint**: Package importable; `_types.py` exists and all module stubs import it; pytest runs clean.

---

## Phase 2: Foundational (findit.py + gitlab.py Core — Parallel)

**Purpose**: Implement the two leaf modules that `resolver.py` delegates to.
`findit.py` and `gitlab.py` tracks run concurrently; resolver.py helpers are written alongside.

**⚠️ CRITICAL**: No user story phases can begin until T011–T026 are complete.

### FindIt Client — `migration_oracle/paysafe/findit.py` [P with gitlab.py tasks]

- [x] T011 [P] Implement module-level cache dict declaration: `_cache: dict[str, tuple[list[dict], datetime]] = {}` keyed by `FINDIT_BASE_URL` in `migration_oracle/paysafe/findit.py`
- [x] T012 [P] Implement 30-day TTL check at the top of `lookup()`: compare `datetime.now(timezone.utc)` to stored `fetched_at`; if elapsed ≥ 30 days (or key absent), invalidate and re-fetch; store `(services, datetime.now(timezone.utc))` on cache miss in `migration_oracle/paysafe/findit.py`
- [x] T013 [P] Implement `_fetch_services(base_url: str) -> list[dict]` — GET `{base_url}/services` with `Authorization: Bearer {FINDIT_AUTH_TOKEN}` header, `httpx.Client`, timeout 10s, 2 retries (1s, 3s backoff); raise `_FindItError("http_timeout")` on timeout, `_FindItError("http_request_failed")` on non-2xx in `migration_oracle/paysafe/findit.py`
- [x] T014 [P] Implement exact and case-insensitive matching levels in `_match(name, services)` in `migration_oracle/paysafe/findit.py`
- [x] T015 [P] Implement alphanumeric-normalization matching level (`re.sub(r'[^a-z0-9]', '', name.lower())`) in `_match()` in `migration_oracle/paysafe/findit.py`
- [x] T016 Implement `lookup(service_name: str) -> dict` — reads cache via T012, calls `_fetch_services`, calls `_match`, returns the matched service record dict (which may or may not contain `codeRepoLink` — caller is responsible for checking); raises `_FindItError("service_not_found")` when no level matches; raises only HTTP error codes on fetch failure; does NOT raise `no_repo_url` in `migration_oracle/paysafe/findit.py`

### GitLab Client — `migration_oracle/paysafe/gitlab.py` [P with findit.py tasks]

- [x] T017 [P] Implement `_https_to_scp(url: str) -> str` — convert GitLab HTTPS URLs to SCP-style `git@gitlab.paysafe.com:...` in `migration_oracle/paysafe/gitlab.py`
- [x] T018 [P] Implement `list_tags(repo_url: str) -> list[str]` — `git ls-remote --tags`, strip `refs/tags/` prefix and `^{}` suffix; raise `_GitError("git_ls_remote_failed")` on non-zero exit or subprocess failure; raise `_GitError("no_tags_found")` when the command succeeds but returns zero refs; strip leading `v`/`V` before `packaging.version.Version` parse, skip unparseable silently; raise `_GitError("no_parseable_tags")` when refs existed but zero parsed successfully; return list sorted descending by semver in `migration_oracle/paysafe/gitlab.py`
- [x] T019 [P] Implement `fetch_framework_version(repo_url: str, tag: str) -> CompatibilityInfo | None` — `git archive {tag}` to extract build file; parse Spring Boot (starter-parent → `spring-boot.version` property → Gradle plugin) or Angular (`@angular/core` dep); return `CompatibilityInfo(framework_version, source_file, source_precedence)` or `None` in `migration_oracle/paysafe/gitlab.py`
- [x] T020 [P] Implement `detect_framework_at_head(repo_url: str) -> str | None` — probe HEAD in order: `pom.xml` first → `build.gradle`/`build.gradle.kts` second → `package.json` third; return `"spring-boot"`, `"angular"`, or `None` in `migration_oracle/paysafe/gitlab.py`
- [x] T021 Implement `_is_compatible(declared: str, target: str) -> bool` — same major AND `(major, minor, patch)` tuple ≥ target tuple, using `packaging.version.Version` in `migration_oracle/paysafe/gitlab.py`
- [x] T022 Add retry wrapper (2 retries, 1s/3s backoff, `timeout=30`) around all `subprocess.run` calls; on exhaustion raise `_GitError("git_ls_remote_failed")` in `migration_oracle/paysafe/gitlab.py`

### Resolver Helpers — `migration_oracle/paysafe/resolver.py` [P with both tracks]

- [x] T023 [P] Implement `_build_effective_settings(max_tags: int) -> dict` — returns `{"max_tags_returned": max_tags, "git_timeout_seconds": 30, "retries": 2, "backoff_seconds": [1.0, 3.0]}` in `migration_oracle/paysafe/resolver.py`
- [x] T024 [P] Implement `_build_error(error_code, message, recoverable, actionable_hint, details) -> dict` — returns `{"status": "error", "error": {"error_code": ..., "message": ..., "recoverable": ..., "actionable_hint": ..., "details": ...}}` in `migration_oracle/paysafe/resolver.py`
- [x] T025 [P] Implement `_build_result(**kwargs) -> dict` — assembles a full `ResolverResult` dict using `_types.ResolverResult` field names; enforces all required keys present and no extra keys in `migration_oracle/paysafe/resolver.py`
- [x] T026 Verify `migration_oracle/paysafe/` contains no import from `migration_oracle.pipeline.*` or `migration_oracle.graph.*` after foundational work: `grep -r "from migration_oracle.pipeline\|from migration_oracle.graph" migration_oracle/paysafe/`

**Checkpoint**: `list_tags()` with mocked subprocess returns tags sorted descending, v-prefix stripped; `lookup()` with mocked httpx returns correct service record; both raise typed errors on failure.

---

## Phase 3: User Story 2 — Pinned Version Bypass (Priority: P1) 🎯

**Goal**: `resolve()` returns immediately when `pinned_version` is supplied — no FindIt or GitLab calls, exact pinned shape.

**Independent Test**: `resolve("any-name", pinned_version="3.5.10", pinned_tag="3.5.10.A")` → `selection_strategy="pinned"`, `compatibility=null`, `name_resolution` key absent, `effective_settings` dict present. Verified with `findit.lookup` patched to raise — must not raise.

- [x] T027 [US2] Implement pinned short-circuit at the TOP of `resolve()`, before any validation or network calls: if `pinned_version` is truthy, return `_build_result(status="ok", service_name=service_name, selected_tag=pinned_tag, selected_version=pinned_version, framework=None, framework_version=None, selection_strategy="pinned", target_version=target_version, code_repo_link=None, compatibility=None, effective_settings=_build_effective_settings(max_tags))` — `name_resolution` key must be absent in `migration_oracle/paysafe/resolver.py`
- [x] T028 [US2] Validate pinned-mode response: assert all 11 `ResolverResult` fields present and `name_resolution` key is absent (use `assert "name_resolution" not in result` as inline guard) in `migration_oracle/paysafe/resolver.py`
- [x] T029 [US2] Write pinned-mode E2E test in `tests/paysafe/test_resolver.py`: call `resolve("any-name", pinned_version="3.5.10", pinned_tag="3.5.10.A")` with `findit.lookup` and `gitlab.list_tags` both patched to raise `AssertionError`; assert `result["selection_strategy"] == "pinned"` AND `result["status"] == "ok"` — both conditions required (neither patch must fire)

**Checkpoint**: `uv run pytest tests/paysafe/test_resolver.py -k pinned -v` all pass.

---

## Phase 4: User Story 5 — Structured Error on Any Failure (Priority: P1)

**Goal**: Every failure path in `resolve()` returns a structured `{"status": "error", "error": {...}}` dict — no exceptions escape.

**Independent Test**: Simulate each error code by patching dependencies; assert `result["status"] == "error"` and `result["error"]["error_code"]` matches expected value; no exception raised.

- [x] T030 [US5] Implement `invalid_service_name` guard in `resolve()` (step 2 of seven-step flow): blank/whitespace `service_name` → `_build_error("invalid_service_name", ..., recoverable=False, ...)` in `migration_oracle/paysafe/resolver.py`
- [x] T031 [US5] Map `_FindItError` codes from `findit.lookup()` to structured error responses in `resolve()`: `service_not_found`, `http_timeout`, `http_request_failed` each become `_build_error(...)` returns; `no_repo_url` is NOT a `_FindItError` — it is detected in resolver.py when extracting `codeRepoLink` (step 4, handled in T037) in `migration_oracle/paysafe/resolver.py`
- [x] T032 [US5] Map `_GitError("git_ls_remote_failed")` from `gitlab.list_tags()` to the `git_ls_remote_failed` structured error response in `resolve()` — this code fires when the `git ls-remote` subprocess itself fails (non-zero exit, auth error, network failure) in `migration_oracle/paysafe/resolver.py`
- [x] T033 [US5] Catch `_GitError("no_tags_found")` and `_GitError("no_parseable_tags")` from `gitlab.list_tags()` and map each to the corresponding structured error response — these two codes are distinct because `list_tags()` raises typed errors (see T018), not empty lists in `migration_oracle/paysafe/resolver.py`
- [x] T034 [US5] Implement `no_compatible_version` and `compatibility_unknown` error paths in strategy-selection (step 7) of `resolve()` in `migration_oracle/paysafe/resolver.py`
- [x] T035 [US5] Wrap entire `resolve()` body in top-level `try/except Exception` safety net that returns `_build_error("internal_error", ...)` — ensures no uncaught exception escapes in `migration_oracle/paysafe/resolver.py`
- [x] T036 [US5] Write error-shape tests in `tests/paysafe/test_resolver.py` — one test function per error code, explicitly covering all eight required codes: `invalid_service_name`, `service_not_found`, `no_repo_url`, `no_tags_found`, `no_compatible_version`, `compatibility_unknown`, `http_timeout`, `http_request_failed`; each test asserts `result["error"]["error_code"] == <expected>` and `result["status"] == "error"` and no exception raised; `http_timeout` and `http_request_failed` are distinct test cases

**Checkpoint**: `uv run pytest tests/paysafe/test_resolver.py -k error -v` all pass; 8 test functions present, one per canonical error code.

---

## Phase 5: User Story 1 — Compatible Version Resolution (Priority: P1)

**Goal**: End-to-end: given `service_name` + `target_version`, resolver contacts FindIt, lists tags, scans build files, and returns the newest compatible tag with full `ResolverResult` shape including `CompatibilityInfo` object.

**Independent Test**: With `findit.lookup` mocked (returns `{"codeRepoLink": "..."}`) and `gitlab.list_tags` mocked (returns `["3.5.10", "3.4.0"]`) and `gitlab.fetch_framework_version` mocked (returns `CompatibilityInfo("3.5.10", "pom.xml", "spring-boot-starter-parent")` for `3.5.10`, `CompatibilityInfo("3.4.0", ...)` for `3.4.0`): `resolve("my-lib", target_version="3.5.6")` → `selected_tag="3.5.10"`, `selection_strategy="latest_compatible"`, `compatibility` is a dict with `source_precedence` key.

- [x] T037 [US1] Implement steps 3–5 of the seven-step flow in `resolve()`: call `findit.lookup()`, extract `codeRepoLink` (→ `no_repo_url` if absent), call `gitlab.list_tags()`, handle `no_tags_found` / `no_parseable_tags` / `git_ls_remote_failed` in `migration_oracle/paysafe/resolver.py`
- [x] T038 [US1] Implement tag scan loop (step 6): iterate tags newest-first up to `max_tags`; call `gitlab.fetch_framework_version()` for each; call `_is_compatible()` on result; accumulate into three buckets: `compatible_tags`, `unknown_tags`, `overall_tags` in `migration_oracle/paysafe/resolver.py`
- [x] T039 [US1] Implement `latest_compatible` strategy selection (step 7): pick newest from `compatible_tags`, build full `ResolverResult` with `compatibility=dataclasses.asdict(best_info)`, `code_repo_link` from FindIt record, `target_version` echo, `effective_settings` in `migration_oracle/paysafe/resolver.py`
- [x] T040 [US1] Implement `latest_overall` fallback in `resolve()`: when `allow_latest_overall=True` and no compatible tag found, select newest tag from `overall_tags`; set `compatibility=None` in `migration_oracle/paysafe/resolver.py`
- [x] T041 [US1] Write E2E happy-path test in `tests/paysafe/test_resolver.py`: full flow from `service_name="my-lib"` input → `selected_tag="3.5.10"` output with mocked `findit.lookup`, `gitlab.list_tags`, and `gitlab.fetch_framework_version`; assert `result["compatibility"]["source_precedence"] == "spring-boot-starter-parent"` and `result["effective_settings"]["max_tags_returned"] == 100`
- [x] T042 [US1] Write resolver unit tests in `tests/paysafe/test_resolver.py`: (a) `latest_overall` fallback when no compatible found, (b) `effective_settings` present in result, (c) `compatibility` is a dict not a boolean, (d) `code_repo_link` echoed from FindIt record
- [x] T043 [US1] [P] Write `tests/paysafe/test_gitlab.py` tag-parsing tests: (a) v-prefix stripped (`v3.5.10` → parses as `3.5.10`), (b) alphabetic suffix handled (`3.5.10.A` parses and sorts as `3.5.10`), (c) unparseable tags silently skipped, (d) tags returned descending
- [x] T044 [US1] [P] Write `tests/paysafe/test_gitlab.py` compatibility boundary tests: (a) same major, declared minor > target minor → `_is_compatible` returns `True`, (b) same major, declared minor < target minor → `_is_compatible` returns `False`, (c) different major (e.g. declared 4.x, target 3.x) → `_is_compatible` returns `False`; cover ≥20 (declared, target) version pairs
- [x] T045 [US1] [P] Write `tests/paysafe/test_gitlab.py` build-file parsing tests: Spring Boot POM starter-parent parse, `spring-boot.version` property parse, Gradle plugin version parse, Angular `@angular/core` from `dependencies`, Angular from `devDependencies`; verify `source_precedence` matches expected value for each
- [x] T046 [US1] [P] Write `tests/paysafe/test_findit.py` cache tests: (a) cache hit within 30 days returns cached data without HTTP call, (b) cache miss after 30 days triggers re-fetch, (c) `http_timeout` error shape — `result["error"]["error_code"] == "http_timeout"`, (d) `http_request_failed` error shape, (e) retry behavior (2 retries before error)

**Checkpoint**: `uv run pytest tests/paysafe/ -v` — all US1, US2, US5 tests pass; T041 E2E test passes end-to-end.

---

## Phase 6: User Story 3 — Fuzzy Name Matching (Priority: P2)

**Goal**: FindIt lookup succeeds even when the service name differs from the registry by casing, separators, or minor spelling; `name_resolution` metadata (with `method`, `matched_name`, and fuzzy-only fields) is included in the response.

**Independent Test**: Mock FindIt to return `[{"name": "payment-gateway-service", ...}]`; call `resolve("PaymentGatewayService")` → `result["name_resolution"]["method"] == "alphanumeric_normalized"` and `result["name_resolution"]["matched_name"] == "payment-gateway-service"`.

- [x] T047 [US3] Add fuzzy matching (4th level) to `_match()` using `rapidfuzz.fuzz.ratio(norm_input, norm_candidate) / 100.0 >= FINDIT_SERVICE_NAME_FUZZY_THRESHOLD`; collect top-3 candidates for `alternatives` list; include `similarity` and `threshold_used` in returned metadata in `migration_oracle/paysafe/findit.py`
- [x] T048 [US3] Return `NameResolution` metadata from `lookup()` when match level is non-exact: `{"method": ..., "matched_name": ...}` for non-fuzzy; add `similarity`, `threshold_used`, `alternatives` when `method="fuzzy"` in `migration_oracle/paysafe/findit.py`
- [x] T049 [US3] Wire `name_resolution` from `findit.lookup()` result into `ResolverResult` in `resolve()` — include only when present; absent on exact match and always absent in pinned mode in `migration_oracle/paysafe/resolver.py`
- [x] T050 [US3] Write test for exact match level in `tests/paysafe/test_findit.py`: call `lookup("payment-service")` with FindIt returning `"payment-service"` → result has no `name_resolution` key
- [x] T051 [US3] Write test for case-insensitive match level in `tests/paysafe/test_findit.py`: call `lookup("Payment-Service")` with FindIt returning `"payment-service"` → `name_resolution.method == "case_insensitive"` and `matched_name == "payment-service"`
- [x] T052 [US3] Write test for alphanumeric-normalized match level in `tests/paysafe/test_findit.py`: call `lookup("PaymentService")` with FindIt returning `"payment-service"` → `name_resolution.method == "alphanumeric_normalized"`
- [x] T053 [US3] Write test for fuzzy match above threshold in `tests/paysafe/test_findit.py`: call `lookup("paymentservize")` with FindIt returning `"payment-service"` and similarity above threshold → `name_resolution.method == "fuzzy"`, `similarity` is a float, `alternatives` is a list
- [x] T054 [US3] Write test for fuzzy match below threshold in `tests/paysafe/test_findit.py`: call `lookup("xyz")` with no match above threshold → `result["error"]["error_code"] == "service_not_found"`

**Checkpoint**: `uv run pytest tests/paysafe/test_findit.py -k match -v` — 5 tests pass, one per matching level plus below-threshold.

---

## Phase 7: User Story 4 — Latest Without Target Constraint (Priority: P2)

**Goal**: When `target_version` is omitted and the MCP layer passes `allow_latest_overall=True`, resolver returns the newest tag with `latest_with_known_compatibility` (readable build file) or `latest_overall` (unreadable).

**Independent Test**: `resolve("my-lib", allow_latest_overall=True)` (no `target_version`) with mocked GitLab returning `"3.5.10"` with readable `CompatibilityInfo` → `selection_strategy="latest_with_known_compatibility"` and `framework_version` is populated.

- [x] T055 [US4] Implement `latest_with_known_compatibility` branch in `resolve()`: when `target_version is None` and newest tag's `fetch_framework_version()` returns a `CompatibilityInfo`, use `selection_strategy="latest_with_known_compatibility"`, populate `framework_version` in `migration_oracle/paysafe/resolver.py`
- [x] T056 [US4] Implement `latest_overall` branch for no-target case: when `target_version is None` and build file unreadable (returns `None`), use `selection_strategy="latest_overall"` with `framework_version=None` in `migration_oracle/paysafe/resolver.py`
- [x] T057 [US4] Document `allow_latest_overall` boundary in `resolve()` signature: add inline comment `# The MCP layer sets allow_latest_overall — resolver never defaults this to True`; do NOT add an assertion (`allow_latest_overall` is typed `bool`, it can never be `None`, so the assertion would always pass and provide no protection — the behavioral test in T059 is the correct guard) in `migration_oracle/paysafe/resolver.py`
- [x] T058 [US4] Wire `detect_framework_at_head()` call: when `target_version is None`, call `gitlab.detect_framework_at_head(repo_url)` to populate `framework` field in `ResolverResult` in `migration_oracle/paysafe/resolver.py`
- [x] T059 [US4] Write US4 tests in `tests/paysafe/test_resolver.py`: (a) `latest_with_known_compatibility` when build file readable, (b) `latest_overall` when build file unreadable, (c) behavioral no-default guard — call `resolve("my-lib", target_version="3.5.6")` without `allow_latest_overall` argument, with no compatible tag found, and assert `result["error"]["error_code"] == "no_compatible_version"` (proving the resolver did not silently fall back to `latest_overall`), (d) `framework` field populated from HEAD detection

**Checkpoint**: `uv run pytest tests/paysafe/ -v` — all US1–US5 tests pass.

---

## Final Phase: Polish & Cross-Cutting Concerns

**Purpose**: Validation, smoke tests, and hardening that span all user stories.

- [x] T060 [P] Run quickstart.md pinned smoke test: `uv run python -c "from migration_oracle.paysafe.resolver import resolve; result = resolve('any-name', pinned_version='3.5.10', pinned_tag='3.5.10.A'); assert result['selection_strategy'] == 'pinned'"` — must exit 0
- [x] T061 [P] Verify `uv run pytest tests/paysafe/ -v` exits 0 with all tests green
- [x] T062 Run full test suite `uv run pytest tests/ -v` to confirm no regressions in existing `test_000_foundations/` and `test_002_pipeline_core/`
- [x] T063 Verify no `datetime.utcnow()` calls anywhere in `migration_oracle/paysafe/`: `grep -r "utcnow" migration_oracle/paysafe/`
- [x] T064 Confirm `FINDIT_BASE_URL` default in `migration_oracle/config.py` is `https://findit-api.icd.paysafe.cloud` (not `findit.paysafe.com`)
- [x] T065 [P] If `FINDIT_AUTH_TOKEN` is available: run quickstart.md live FindIt smoke test and confirm response includes `effective_settings` dict and `compatibility` object (not boolean)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No prerequisites — start immediately. T005 (`_types.py`) MUST complete before any Phase 2 implementation.
- **Phase 2 (Foundational)**: Requires T005 complete; `findit.py` and `gitlab.py` tracks are **parallel**; resolver helpers (T023–T025) run alongside either track.
- **Phase 3 (US2)**: Requires T023 (`_build_effective_settings`) and T025 (`_build_result`) from Phase 2 (pinned mode calls both helpers). Cannot start until those two resolver helpers are complete.
- **Phase 4 (US5)**: Requires Phase 2 complete (error paths call `_build_error` from T024).
- **Phase 5 (US1)**: Requires Phase 2 + Phase 4 complete.
- **Phase 6 (US3)**: Requires Phase 2 complete; `findit.py` fuzzy extension builds on T011–T016.
- **Phase 7 (US4)**: Requires Phase 5 complete (adds strategy branches to resolver.py).
- **Final Phase**: Requires all user story phases complete.

### User Story Dependencies

| Story | Depends on | Can start after |
|-------|-----------|-----------------|
| US2 (P1) | Phase 1 (T010) | T010 |
| US5 (P1) | Phase 2 (T026) | T026 |
| US1 (P1) | Phase 2 + US5 | T036 |
| US3 (P2) | Phase 2 (T026) | T026 |
| US4 (P2) | US1 complete | T042 |

### Within Each Phase

- T005 (`_types.py`) before all module implementation tasks
- `_build_error()` helper (T024) before error path tasks (T030–T035)
- `_build_effective_settings()` helper (T023) before any `ResolverResult` construction (T027, T039)

---

## Parallel Opportunities

### Phase 2: Three concurrent tracks

```
Track A (findit.py):    T011 → T012 → T013 → T014 → T015 → T016
Track B (gitlab.py):    T017 → T018 → T019 → T020 → T021 → T022
Track C (resolver.py):  T023, T024, T025 (independent helpers)
```

### After Phase 2: US2 and US3 start concurrently

```
Track A: T027 → T028 → T029 (US2 pinned mode)
Track B: T047 → T048 → T049 → T050 → T051 → T052 → T053 → T054 (US3 fuzzy)
```

### Phase 5: Test files are parallel

```
Parallel: T043 (test_gitlab tag-parsing) + T044 (compatibility boundary) + T045 (build-file parsing) + T046 (test_findit cache)
Sequential: T037 → T038 → T039 → T040 → T041 → T042 (resolver.py orchestration)
```

---

## Implementation Strategy

### MVP: US2 + US5 + US1 (all three P1 stories)

1. Complete Phase 1 (Setup) — T001–T010
2. Complete Phase 2 (Foundational — parallel) — T011–T026
3. Complete Phase 3 (US2 — Pinned Mode) — T027–T029; smoke-test T060 immediately
4. Complete Phase 4 (US5 — Error Isolation) — T030–T036
5. Complete Phase 5 (US1 — Compatible Resolution) — T037–T046
6. **STOP and VALIDATE**: `uv run pytest tests/paysafe/ -v`
7. **Ship MVP** — pinned bypass + full compatible resolution + error safety

### Incremental Delivery

1. Setup + Foundational → Importable package with shared types
2. + US2 → Pinned calls work offline, smoke-testable
3. + US5 → All failures are structured, no crashes
4. + US1 → Core resolution working **(MVP!)**
5. + US3 → Tolerates sloppy service names
6. + US4 → Works without a target version
7. Final Phase → Verified, polished

### Parallel Team Strategy (2 developers)

| Dev A | Dev B |
|-------|-------|
| Phase 1 (together) | Phase 1 (together) |
| `findit.py` (T011–T016) | `gitlab.py` (T017–T022) |
| Resolver helpers (T023–T025) | T026 boundary check |
| US2 pinned mode (T027–T029) | US3 fuzzy matching (T047–T054) |
| US5 errors (T030–T036) | US1 gitlab tests (T043–T046) |
| US1 orchestration (T037–T042) | US4 (T055–T059) |
| Final Phase (together) | Final Phase (together) |

---

## Notes

- **[P]** = different files, no incomplete dependencies; safe to run concurrently
- **[Story]** maps each task to the user story it delivers
- T005 (`_types.py`) is the single source of truth for all data-model types; every implementation file imports from it — never redefine types inline
- T003 must be committed (`uv.lock` updated) before any `import packaging` in tests
- `effective_settings` must appear in every `ResolverResult`, including pinned mode (T027)
- `compatibility` is `CompatibilityInfo | None` — always a dict or null, never a boolean; T041 asserts `isinstance(result["compatibility"], dict)`
- All `subprocess.run` calls in `gitlab.py` must use `timeout=30` — never block indefinitely (T022)
- `FINDIT_BASE_URL` in tests should be overridden via env var to point at the `respx` mock URL (`https://findit-api.icd.paysafe.cloud`)
- T036 requires exactly 7 test functions, one per canonical error code; `internal_error` from T035 is additional and may be tested separately
