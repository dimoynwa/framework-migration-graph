"""Seed Version nodes required by the 013-real-run-hardening scenario.

Seeds:
  - Spring Boot 4.0.6 (sortableVersion=4000006, status="active")
  - Spring Cloud trains: Hoxton through Oakwood (6 calVer trains)

Run: python scripts/seed_013_versions.py
"""

from __future__ import annotations

from migration_oracle.graph.driver import write_session

_SPRING_BOOT_406 = """
MERGE (v:Version {framework: "Spring Boot", version: "4.0.6"})
ON CREATE SET
  v.sortableVersion = 4000006,
  v.status          = "active",
  v.minJava         = 21,
  v.createdAt       = datetime()
ON MATCH SET
  v.sortableVersion = 4000006,
  v.status          = "active",
  v.minJava         = 21
RETURN v.version AS version, v.sortableVersion AS sortable
"""

# Spring Cloud calVer formula: YEAR * 1_000_000 + MINOR * 1_000 + PATCH
# "2025.1.0" → 2025 * 1_000_000 + 1 * 1_000 + 0 = 2_025_001_000
_SPRING_CLOUD_TRAINS = [
    {
        "version": "2020.0.0",
        "train": "Hoxton",
        "sortableVersion": 2020 * 1_000_000 + 0 * 1_000 + 0,
        "compatibleBoot": "2.3.x",
        "importMode": "spring-cloud-starter-parent",
        "status": "eol",
    },
    {
        "version": "2021.0.0",
        "train": "Jubilee",
        "sortableVersion": 2021 * 1_000_000 + 0 * 1_000 + 0,
        "compatibleBoot": "2.4-2.5",
        "importMode": "spring-cloud-starter-parent",
        "status": "eol",
    },
    {
        "version": "2022.0.0",
        "train": "Kilburn",
        "sortableVersion": 2022 * 1_000_000 + 0 * 1_000 + 0,
        "compatibleBoot": "2.7-3.0",
        "importMode": "spring-cloud-starter-parent",
        "status": "eol",
    },
    {
        "version": "2023.0.0",
        "train": "Leyton",
        "sortableVersion": 2023 * 1_000_000 + 0 * 1_000 + 0,
        "compatibleBoot": "3.1-3.2",
        "importMode": "spring-cloud-starter-parent",
        "status": "maintenance",
    },
    {
        "version": "2024.0.0",
        "train": "Moorgate",
        "sortableVersion": 2024 * 1_000_000 + 0 * 1_000 + 0,
        "compatibleBoot": "3.3-3.4",
        "importMode": "spring-cloud-starter-parent",
        "status": "active",
    },
    {
        "version": "2025.1.0",
        "train": "Oakwood",
        "sortableVersion": 2025 * 1_000_000 + 1 * 1_000 + 0,
        "compatibleBoot": "4.0.x",
        "importMode": "spring-cloud-dependencies (BOM-only)",
        "status": "active",
    },
]

_UPSERT_SPRING_CLOUD = """
MERGE (v:Version {framework: "Spring Cloud", version: $version})
ON CREATE SET
  v.sortableVersion  = $sortableVersion,
  v.train            = $train,
  v.status           = $status,
  v.compatibleBoot   = $compatibleBoot,
  v.importMode       = $importMode,
  v.createdAt        = datetime()
ON MATCH SET
  v.sortableVersion  = $sortableVersion,
  v.train            = $train,
  v.status           = $status,
  v.compatibleBoot   = $compatibleBoot,
  v.importMode       = $importMode
RETURN v.version AS version, v.sortableVersion AS sortable
"""


def seed_spring_boot_406() -> None:
    with write_session() as session:
        record = session.run(_SPRING_BOOT_406).single()
    print(f"[T001] Seeded Spring Boot {record['version']} (sortable={record['sortable']})")


def seed_spring_cloud_trains() -> None:
    for train in _SPRING_CLOUD_TRAINS:
        with write_session() as session:
            record = session.run(_UPSERT_SPRING_CLOUD, **train).single()
        print(
            f"[T002] Seeded Spring Cloud {record['version']} "
            f"({train['train']}, sortable={record['sortable']})"
        )


if __name__ == "__main__":
    seed_spring_boot_406()
    seed_spring_cloud_trains()
    print("Done. Seeded 1 Spring Boot + 6 Spring Cloud Version nodes.")
