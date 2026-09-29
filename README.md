# vstone-databricks-pipeline

End-to-end Databricks medallion pipeline (Bronze → Silver → Gold) for a
Valencia smart-city traffic dataset: street sensor readings, vehicle
counts, and citizen incident reports, built on Databricks Free Edition
(serverless), Unity Catalog, Delta Live Tables, and Databricks Asset
Bundles.

> **Status: Day 10 of 10 — all deliverables built.** See
> `docs/day10_final_deliverables_checklist.md` for the honest final
> self-assessment (what's tested, what's still open, what needs a real
> workspace run to confirm). `docs/requirements_and_assumptions.md` has
> the full assumption log, including every correction found and fixed
> along the way with real numbers, not smoothed over.
> `deliverables/vstone_case_study.pptx` is the Day 10 case study walkthrough.

## Project overview

Five raw files land in a Unity Catalog Volume and flow through Bronze →
Silver → Gold. `streets.csv` (the largest file, ~87.8M rows) is split into
4 chunks to demonstrate all 4 required ingestion techniques — COPY INTO,
Delta Live Tables, Auto Loader, PySpark native XML. `cars.csv`,
`telegram.csv`, `node_locations.csv`, `streets_list.csv` are loaded whole
via DLT. Gold is a star schema with SCD2 dimensions, business rules, ACID/
time-travel evidence, Liquid Clustering vs. partitioning benchmarking,
churn-style metrics, row/column-level security, and two dashboards.

## Data sources

| File | Rows | What it is |
|---|---|---|
| `streets.csv` | 87,820,725 | Street sensor readings (noise, pollution, light, rain), every 10s. **Primary fact table — chunked into 4 formats.** |
| `cars.csv` | 24,681,794 | Vehicle-count events at 14 traffic sensor nodes. Whole-load. |
| `telegram.csv` | 128,440 | Free-text citizen traffic/incident reports. Whole-load. |
| `streets_list.csv` | 36 | Street dimension — length, coordinates, danger score. SCD2 in Gold. |
| `node_locations.csv` | 14 | Sensor-node dimension — coordinates. SCD2 in Gold. |

Full profiling output, every data-quality issue found, and every
assumption (including ones later proven wrong and corrected with real
evidence) are in `docs/requirements_and_assumptions.md`.

## Architecture

```
streets.csv (landing volume)
   │
   ├── 50% ──► streets_chunk_1.csv  ──► Bronze (COPY INTO)          [Day 2]
   ├── 20% ──► streets_chunk_2.csv  ──► Bronze (Delta Live Tables)  [Day 3]
   ├── 20% ──► streets_chunk_3.json ──► Bronze (Auto Loader)        [Day 3]
   └── 10% ──► streets_chunk_4.xml  ──► Bronze (PySpark native XML) [Day 3]

cars.csv, telegram.csv, node_locations.csv, streets_list.csv (landing volume)
   └── loaded whole ──► Bronze (DLT, streaming cloudFiles + pathGlobFilter) [Day 3]

Bronze ──► Silver (clean, dedupe on CONFIRMED grains, quarantine, pandas UDFs)  [Day 4]
       ──► streets_business (raining clipped to [0,100], ACID/time-travel demo) [Day 5]
       ──► Gold (star schema: 3 dims incl. 2 SCD2, 3 facts, 4 aggregates)        [Day 6]
       ──► Liquid Clustering vs. Partition+Z-Order benchmark, MERGE, churn      [Day 7]
       ──► Governance (RLS/CLS), resource usage dashboard, job orchestration   [Day 8-9]
       ──► Case study, traffic insights dashboard, full pipeline integration test [Day 10]
```

Catalog: `vstone_catalog` · Schemas: `raw`, `bronze`, `silver`, `gold`,
`security` · Volumes (in `raw`): `landing`, `chunks`, `checkpoints`. All
configurable via `databricks.yml` variables — nothing hardcoded in the
notebooks. **Compute is serverless throughout** — no job defines a classic
cluster (Free Edition doesn't support them; this was a real bug caught and
fixed on Day 10, see the assumptions doc).

## Repository structure

```
vstone-databricks-pipeline/
├── .github/workflows/databricks-ci-cd.yml   # CI: validate, deploy to dev, run full pipeline
├── databricks.yml                           # DAB config — 10 jobs, 3 DLT pipelines, variables
├── src/
│   ├── Notebooks/                           # 22 files, Day 1 through Day 10
│   │   ├── 00-02   Setup, profiling, chunking                        (Day 1)
│   │   ├── 03      Bronze COPY INTO                                  (Day 2)
│   │   ├── 04-07   Bronze Auto Loader / XML / DLT                    (Day 3)
│   │   ├── 09-10   Silver: streets, cars/telegram/dimensions         (Day 4)
│   │   ├── 11-12   Business rules (raining clip) + ACID/time-travel  (Day 5)
│   │   ├── 13-15   Gold: dimensions, facts, aggregates               (Day 6)
│   │   ├── 16-18   Performance benchmark, MERGE, churn metrics       (Day 7)
│   │   ├── 19-21   RLS, CLS, resource usage dashboard queries        (Day 8-9)
│   │   └── 22      Traffic insights dashboard queries                (Day 10, optional)
│   └── utils/
│       └── chunk_io.py                      # Shared single-file-write + reconciliation helpers
├── tests/                                   # 9 files, 60+ test methods, one per delivery day
│   └── test_final_integration_day9.py       # Cross-layer reconciliation — the important one
├── docs/                                    # 10 files — assumptions, data model, glossary,
│                                             #   git workflow, dashboard setup guides, checklist
├── deliverables/
│   └── vstone_case_study.pptx               # Day 10 case study deck
└── README.md
```

## Setup

### Prerequisites
- A Databricks **Free Edition** workspace (serverless compute; do not use a
  trial workspace — see project brief).
- Databricks CLI, authenticated: `databricks auth login --host <your-workspace-url>`
- `databricks.yml` → `workspace.host`: replace the placeholder with your
  real workspace URL. This is the one manual edit required before deploying.
- (Optional, for RLS/CLS to actually restrict anyone) workspace groups:
  `admin_group`, `safety_team`, `public_dashboard_group`.

### Deploy
```bash
databricks bundle validate
databricks bundle deploy --target dev
```
Syncs all notebooks/tests and creates all 10 jobs + 3 DLT pipelines as
resources. Does **not** create the catalog or upload data — that's next.

### Create infrastructure (run once)
```bash
databricks bundle run data_chunking_job --target dev
```
Its first task creates `vstone_catalog` (all 5 schemas, 3 volumes). This
run will fail at the profiling/chunking tasks the first time — expected,
since the raw files aren't uploaded yet.

### Upload the 5 raw files
```
/Volumes/vstone_catalog/raw/landing/streets.csv
/Volumes/vstone_catalog/raw/landing/cars.csv
/Volumes/vstone_catalog/raw/landing/telegram.csv
/Volumes/vstone_catalog/raw/landing/node_locations.csv
/Volumes/vstone_catalog/raw/landing/streets_list.csv
```
Via Catalog Explorer → the `landing` volume → Upload, or `databricks fs cp`.

### Run the full pipeline
```bash
databricks bundle run end_to_end_pipeline_job --target dev
```
Chains all 9 required-day jobs via `run_job_task`, ending in
`test_final_integration_day9` — the cross-layer reconciliation test that
actually catches things like orphaned dimension rows or wrong grain
assumptions, not just per-table schema checks.

### Dashboards (manual UI step, by design)
- **Resource usage** (PDF-required): `21_usage_analysis.py` →
  `docs/day8_dashboard_setup.md`
- **Traffic insights** (optional, strengthens the demo): `22_traffic_insights_queries.py`
  → `docs/day10_traffic_insights_dashboard_setup.md`

Both are guides, not checked-in `.lvdash.json` files — that JSON schema
can't be validated without a live workspace to render it in, and a subtly
wrong dashboard spec fails silently rather than erroring clearly. The SQL
is the tested part; building the widgets is a ~5-10 minute UI task.

### Genie space
`docs/day6_genie_space_setup.md` — manual setup (reliable) plus a
best-effort bundle-resource YAML block (flagged as unverified — `genie_space`
is a very recent DAB resource type I don't have confirmed field syntax for).

## Testing

9 test files, one per delivery day, 60+ test methods total. Two kinds:
- **Per-day tests** check one layer's output in isolation (schema, nulls,
  row counts, quarantine reasons).
- **`test_final_integration_day9.py`** is different in kind — it
  reconciles row counts *across* Bronze → Silver → Gold and checks every
  fact/dimension pair for orphan FKs at once. This is the test that would
  catch the two real bugs found during this build (see below) immediately,
  instead of one test run at a time across separate days.

## Real bugs found and fixed during this build

Documented in full, with real numbers, in `docs/requirements_and_assumptions.md`:

1. **Orphaned dimension member.** `node_locations.csv` location=7 had
   invalid `(0,0)` coordinates and was fully quarantined — but it was a
   real sensor with 2.37M rows of valid data in `cars.csv`, a different
   file. Orphaned 1,626,982 fact rows. Fixed by keeping the entity, nulling
   only the bad attribute.
2. **Wrong grain assumption.** `cars.csv` was assumed to dedupe on
   `(location, date)`. Real data showed 0 true duplicates on that grain —
   every "duplicate" was a distinct reading with a different `id`.
   746,345 real rows were being silently dropped at one location alone.
   Corrected grain: `(location, date, id)`.
3. **Serverless compute violation.** Every job defined a classic
   `new_cluster`, which Free Edition doesn't support at all — would have
   failed on the first run of every single job. Fixed by removing all
   cluster config; Databricks Jobs use serverless automatically.

## Known limitations — not hidden

See `docs/day10_final_deliverables_checklist.md`, section G, for the full
list — including that `end_to_end_pipeline_job` has not yet been run
start-to-finish as one continuous execution, only as individually-fixed
pieces.
