# Ingestion команди

Формат: `uv run export-extract-populate-framework --framework <key> <FROM> <TO> [флагове]`
Framework ключове: `spring-boot`, `angular`, `wildfly`.
`.env` трябва да е зареден (NEO4J_URI и др.), иначе CLI-ят гърми още при старт.

---

```
cd /Users/dimo.drangov/paysafe-version-migration-graph && set -a && source .env && set +a
```

## 1. Само extraction (raw changelog)

```bash
uv run export-extract-populate-framework --framework spring-boot 4.0.0 4.1.2 \
  --hop-by-hop --hop-granularity minor --extract-only
```
Тегли changelog-а по HTTP → `runs/raw/`. Без LLM и без запис в графа.

## 2. Extraction + triage + research, после стоп

```bash
uv run export-extract-populate-framework --framework spring-boot 4.0.0 4.1.2 \
  --hop-by-hop --hop-granularity minor --stop-after-research
```
Extraction → System-1 triage (`runs/triage/`) → research на всеки ред (`runs/research/`). Без entity LLM и без граф.

## 3. До clusters, после стоп

```bash
uv run export-extract-populate-framework --framework spring-boot 4.0.0 4.1.2 \
  --hop-by-hop --hop-granularity minor --stop-after-clusters
```
Всичко до research + action gate и клъстеризация → `runs/clusters/`. Без entity извиквания (не трябва `MODEL_*`).

## 4. Пълен pipeline, dry-run (без граф)

```bash
uv run export-extract-populate-framework --framework spring-boot 4.0.0 4.1.2 \
  --hop-by-hop --hop-granularity minor --dry-run
```
Целият pipeline до entities JSON (`runs/json/`), но без запис в Neo4j.

## 5. Пълен pipeline + populate на графа

```bash
uv run export-extract-populate-framework --framework spring-boot 4.0.0 4.1.2 \
  --hop-by-hop --hop-granularity minor
```
Extraction → triage → research → entities (dossier) → Version нод за всеки hop в Neo4j.

## 6. Patch-level hops (всеки release)

```bash
uv run export-extract-populate-framework --framework spring-boot 3.4.0 3.4.5 \
  --hop-by-hop --hop-granularity patch --stop-after-research
```
Същото като горе, но по един hop на patch версия (3.4.0→3.4.1→…).

## 7. Стар път: filter LLM → entity LLM (без dossier)

```bash
uv run export-extract-populate-framework --framework spring-boot 4.0.0 4.1.2 \
  --hop-by-hop --hop-granularity minor --entity-source filter
```
Entities идват от filter LLM + entity LLM вместо от research dossier-и.

## 8. Без triage / без research

```bash
# Пази всички редове, не вика classifier-а
uv run export-extract-populate-framework --framework spring-boot 4.0.0 4.1.2 \
  --hop-by-hop --skip-triage --stop-after-research

# Пропуска research; entity стъпката вижда само filtered MD
uv run export-extract-populate-framework --framework spring-boot 4.0.0 4.1.2 \
  --hop-by-hop --skip-research
```

## 8a. Milestone / RC / SNAPSHOT / latest

```bash
# Milestone и RC се подават директно (SPRING_INCLUDE_PRERELEASE=1, по подразбиране)
uv run export-extract-populate-framework --framework spring-boot 4.1.2 4.2.0-RC2 \
  --hop-by-hop --hop-granularity minor --stop-after-research

# SNAPSHOT → най-новият публикуван build на тази версия (4.2.0-SNAPSHOT → 4.2.0-RC2)
uv run export-extract-populate-framework --framework spring-boot 4.0.0 4.2.0-SNAPSHOT \
  --hop-by-hop --hop-granularity minor --stop-after-research

# latest → най-новата публикувана версия (вкл. RC/M); latest-ga → най-новата GA
uv run export-extract-populate-framework --framework spring-boot 4.0.0 latest \
  --hop-by-hop --hop-granularity minor --stop-after-research
```
CLI-ят печата `Resolved 4.2.0-SNAPSHOT → 4.2.0-RC2`; файловете и Version нодовете са с конкретната версия.
Minor hop чете release notes на всички releases от целевата линия (`4.0.0 → 4.1.0` чете `4.1.0-M1 … RC1` и `4.1.0`).
Стари raw файлове от предишния формат (цял range в един файл) се засичат и се re-extract-ват автоматично.

## 9. Angular примери

```bash
uv run export-extract-populate-framework --framework angular 19.0.0 20.0.0 \
  --hop-by-hop --hop-granularity minor --stop-after-research

uv run export-extract-populate-framework --framework angular 20.0.0 21.0.0 \
  --hop-by-hop --hop-granularity minor
```

### 9a. Rule signals (spec 027)

Стъпката върви автоматично след canonicalize и преди записа в графа, вътре в
`populate_graph`. Ползва същия System-1 endpoint като triage (`TRIAGE_BASE_URL`,
`TRIAGE_MODEL`) и пише `runs/signals/<fw>-<from>-to-<to>-signals.jsonl` +
`-summary.json`.

```bash
# само signals (без граф), с кеша
uv run export-extract-populate-framework --framework angular 19.2.0 20.0.0 \
  --hop-by-hop --hop-granularity minor --dry-run

# игнорирай кеша на отговорите и питай наново
uv run export-extract-populate-framework --framework angular 19.2.0 20.0.0 \
  --force-signals

# не класифицирай; правилата се записват без signal свойства (planner чете behavioral)
uv run export-extract-populate-framework --framework angular 19.2.0 20.0.0 \
  --skip-signals
```

Backfill за хопове, които вече са в графа (не се пре-популват):

```bash
uv run python scripts/classify_signals.py --framework angular --all --dry-run
uv run python scripts/classify_signals.py --framework spring-boot 3.5.0 4.0.0
```

## 10. WildFly пример

```bash
uv run export-extract-populate-framework --framework wildfly 35.0.0 36.0.0 \
  --hop-by-hop --hop-granularity minor --stop-after-research
```

---

## Re-run / кеш флагове (добавят се към която и да е команда)

| Флаг | Какво прави |
|---|---|
| `--force` | Пуска наново extraction + двете LLM стъпки |
| `--force-extract` | Пуска наново само HTTP extraction-а |
| `--force-llm` | Пуска наново filter/entity LLM (в dossier режим игнорира per-cluster кеша) |
| `--force-triage` | Игнорира triage кеша и triage колоните в raw файла |
| `--retriage-from-cache` | Преизчислява keep/drop от кеширани вероятности, без HTTP |
| `--force-research` | Игнорира research кеша и съществуващия `research.jsonl` |
| `--skip-signals` | Без System-1 класификация на правилата; без `signal` свойства в графа |
| `--force-signals` | Игнорира кеша на signal отговорите |
| `--skip-existing` | Пропуска hop, ако raw MD, filtered MD и Version нод вече съществуват |

Пример — преизчисли triage-а от кеша и спри след research:
```bash
uv run export-extract-populate-framework --framework spring-boot 4.0.0 4.1.2 \
  --hop-by-hop --retriage-from-cache --stop-after-research
```

## Изходни пътища (по избор)

`--output-md PATH`, `--output-filtered-md PATH`, `--output-json PATH` — override на пътищата за raw MD, filtered MD и entities JSON.

## Env defaults

`HOP_BY_HOP=1`, `HOP_GRANULARITY=minor|patch`, `ENTITY_SOURCE=dossier|filter` в `.env` заместват съответните флагове.
