# Version Map

**Last Updated**: 2026-06-13
**Upstream schedules**: [Spring Boot](https://spring.io/projects/spring-boot) · [Angular](https://angular.io/guide/releases)

Quick reference for converting version strings to sortable integers.
Formula: `MAJOR * 1_000_000 + MINOR * 1_000 + PATCH`

---

## Spring Boot

| Version | Sortable | Status      | Min Java |
| ------- | -------- | ----------- | -------- |
| 2.5.0   | 2005000  | EOL         | 8        |
| 2.5.14  | 2005014  | EOL         | 8        |
| 2.6.0   | 2006000  | EOL         | 8        |
| 2.6.15  | 2006015  | EOL         | 8        |
| 2.7.0   | 2007000  | EOL         | 8        |
| 2.7.18  | 2007018  | EOL         | 8        |
| 3.0.0   | 3000000  | EOL         | 17       |
| 3.0.13  | 3000013  | EOL         | 17       |
| 3.1.0   | 3001000  | EOL         | 17       |
| 3.1.12  | 3001012  | EOL         | 17       |
| 3.2.0   | 3002000  | Maintenance | 17       |
| 3.2.4   | 3002004  | Maintenance | 17       |
| 3.3.0   | 3003000  | Active      | 17       |
| 3.3.4   | 3003004  | Active      | 17       |
| 3.4.0   | 3004000  | Active      | 17       |
| 3.4.2   | 3004002  | Active      | 17       |
| 4.0.0   | 4000000  | Active      | 21       |
| 4.0.2   | 4000002  | Active      | 21       |
| 4.1.0   | 4001000  | Active      | 21       |


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

| Version | Sortable  | Status | Min Node |
| ------- | --------- | ------ | -------- |
| 14.0.0  | 14000000  | EOL    | 14.15    |
| 14.3.0  | 14003000  | EOL    | 14.15    |
| 15.0.0  | 15000000  | EOL    | 14.20    |
| 15.2.0  | 15002000  | EOL    | 14.20    |
| 16.0.0  | 16000000  | EOL    | 16.14    |
| 16.2.0  | 16002000  | EOL    | 16.14    |
| 17.0.0  | 17000000  | Active | 18.13    |
| 17.3.0  | 17003000  | Active | 18.13    |
| 18.0.0  | 18000000  | Active | 18.19    |
| 18.2.0  | 18002000  | Active | 18.19    |
| 19.0.0  | 19000000  | Active | 20.x     |
| 20.0.0  | 20000000  | Active | 20.x     |
| 21.0.0  | 21000000  | Active | 20.x     |
| 22.0.0  | 22000000  | Active | 20.x     |

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
