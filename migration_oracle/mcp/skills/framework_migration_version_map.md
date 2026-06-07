# Version Map

Quick reference for converting version strings to sortable integers.
Formula: `MAJOR * 10000 + MINOR * 100 + PATCH`

---

## Spring Boot

| Version | Sortable | Status      | Min Java |
| ------- | -------- | ----------- | -------- |
| 2.5.0   | 20500    | EOL         | 8        |
| 2.5.14  | 20514    | EOL         | 8        |
| 2.6.0   | 20600    | EOL         | 8        |
| 2.6.15  | 20615    | EOL         | 8        |
| 2.7.0   | 20700    | EOL         | 8        |
| 2.7.18  | 20718    | EOL         | 8        |
| 3.0.0   | 30000    | EOL         | 17       |
| 3.0.13  | 30013    | EOL         | 17       |
| 3.1.0   | 30100    | EOL         | 17       |
| 3.1.12  | 30112    | EOL         | 17       |
| 3.2.0   | 30200    | Maintenance | 17       |
| 3.2.4   | 30204    | Maintenance | 17       |
| 3.3.0   | 30300    | Active      | 17       |
| 3.3.4   | 30304    | Active      | 17       |
| 3.4.0   | 30400    | Active      | 17       |
| 3.4.2   | 30402    | Active      | 17       |
| 4.0.0   | 40000    | Active      | 21       |
| 4.0.2   | 40002    | Active      | 21       |
| 4.1.0   | 40100    | Active      | 21       |


**Important version boundary:** 
- 2.x → 3.x requires Java 17 and migrates `javax.*` → `jakarta.*`.
    Always flag this if the range spans this boundary.
- 3.x → 4.x Requires Java 21
    Further Jakarta EE alignment and removal of deprecated 3.x APIs

**Recommended incremental path for large jumps:**
- 2.5.x → 2.7.x → 3.0.x → 3.2.x (current latest maintenance)
- Never skip more than one major version in a single migration pass.

---

## Angular

| Version | Sortable | Status | Min Node |
| ------- | -------- | ------ | -------- |
| 14.0.0  | 140000   | EOL    | 14.15    |
| 14.3.0  | 140300   | EOL    | 14.15    |
| 15.0.0  | 150000   | EOL    | 14.20    |
| 15.2.0  | 150200   | EOL    | 14.20    |
| 16.0.0  | 160000   | EOL    | 16.14    |
| 16.2.0  | 160200   | EOL    | 16.14    |
| 17.0.0  | 170000   | Active | 18.13    |
| 17.3.0  | 170300   | Active | 18.13    |
| 18.0.0  | 180000   | Active | 18.19    |
| 18.2.0  | 180200   | Active | 18.19    |
| 19.0.0  | 190000   | Active | 20.x     |
| 20.0.0  | 200000   | Active | 20.x     |
| 21.0.0  | 210000   | Active | 20.x     |
| 22.0.0  | 220000   | Active | 20.x     |

**Important version boundary:** 15 → 16 

Important version boundaries:

- 15 → 16 introduces standalone components as default.
- 16 → 17 introduces the new control flow syntax (`@if`, `@for`). Flag both.
- 16 → 17 New control flow syntax (@if, @for)
- 17 → 18 Signals become stable and widely adopted
- 18 → 19+ Continued shift toward zoneless change detection and signal-based APIs

---

## Framework Detection Heuristics

When `FRAMEWORK` is not stated by the user, detect from project files:

| File present                                          | Detected framework      |
| ----------------------------------------------------- | ----------------------- |
| `pom.xml` with `spring-boot`                          | Spring Boot             |
| `build.gradle` with `org.springframework.boot` plugin | Spring Boot             |
| `angular.json`                                        | Angular                 |
| `package.json` with `@angular/core`                   | Angular                 |
| Both present (monorepo)                               | Ask the user to clarify |

---

## Version String Normalisation

| User says       | Interpret as                      |
| --------------- | --------------------------------- |
| "3.2"           | 3.2.0                             |
| "Spring Boot 3" | 3.0.0 (or latest 3.x if target)   |
| "Angular 17"    | 17.0.0 (or latest 17.x if target) |
| "latest"        | Highest available sortable        |
