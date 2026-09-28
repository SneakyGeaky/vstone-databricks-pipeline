# vstone-databricks-pipeline

End-to-end Databricks medallion pipeline (Bronze → Silver → Gold) for a
Valencia smart-city traffic dataset: sensor vehicle counts + citizen incident
reports, built on Databricks Free Edition (serverless), Unity Catalog, and
Databricks Asset Bundles.

> **Status: Day 10 of 10 — all deliverables built.** See
> `docs/day10_final_deliverables_checklist.md` for the honest final
> self-assessment (what's tested, what's still open, what needs a real
> workspace run to confirm). `docs/requirements_and_assumptions.md` has
> the full assumption log including corrections found and fixed along the
> way; `docs/data_mapping.md` covers how this project adapts the reference
> project's patterns to VStone's own datasets; `deliverables/vstone_case_study.pptx`
> is the Day 10 case study walkthrough.

## Project overview

Four raw files land in a Unity Catalog Volume and flow through Bronze → Silver
→ Gold, using four different ingestion techniques on the primary fact table
(COPY INTO, Delta Live Tables, Auto Loader, PySpark native XML) as required by
the project brief, plus governance (RLS/CLS/dynamic masking), SCD2 dimensions,
Liquid Clustering vs. partitioning benchmarking, and a Genie space on the
aggregate layer in later days.

## Data sources

| File | Rows | What it is |
|---|---|---|
| `cars.csv` | 24,681,794 | Vehicle-count events at 14 traffic sensor nodes, `2023-06-02`→`2024-03-10`. **Primary fact table — chunked into 4 formats.** |
| `telegram.csv` | 128,440 | Free-text citizen traffic/incident reports for the same period. |
| `node_locations.csv` | 14 | Sensor coordinates (lat/long) — one row per `cars.csv.location` value. |
| `streets_list.csv` | 36 | Street master list with length and a danger score — joined to `telegram.csv` by street name. |

Full profiling output, null/duplicate checks, and known data-quality issues
(one sensor with invalid coordinates, no shared key between the two dimension
files) are in `docs/requirements_and_assumptions.md`.

## Architecture

```
cars.csv (landing volume)
   │
   ├── 50% ──► cars_chunk_1.csv  ──► Bronze (COPY INTO)         [Day 2]
   ├── 20% ──► cars_chunk_2.csv  ──► Bronze (Delta Live Tables) [Day 3]
   ├── 20% ──► cars_chunk_3.json ──► Bronze (Auto Loader)       [Day 3]
   └── 10% ──► cars_chunk_4.xml  ──► Bronze (PySpark native XML)[Day 3]

telegram.csv, node_locations.csv, streets_list.csv (landing volume)
   └── loaded whole ──► Bronze (DLT)                            [Day 3]

Bronze ──► Silver (clean, dedupe, standardize, quarantine)      [Day 4-5]
       ──► Gold (star schema, SCD2 dims, aggregates)             [Day 6-7]
       ──► Governance (RLS/CLS/masking), Jobs, Dashboards        [Day 8-9]
```

Catalog: `vstone_catalog` · Schemas: `raw`, `bronze`, `silver`, `gold`,
`security` · Volumes (in `raw`): `landing`, `chunks`, `checkpoints`. All
configurable via `databricks.yml` variables — nothing is hardcoded in the
notebooks.

## Repository structure

```
vstone-databricks-pipeline/
├── .github/workflows/databricks-ci-cd.yml   # CI: validate bundle, syntax-check, deploy to dev
├── databricks.yml                           # DAB config — jobs, clusters, variables
├── src/
│   ├── Notebooks/
│   │   ├── 00_setup_infrastructure.py       # Catalog, schemas, volumes
│   │   ├── 01_data_profiling.py             # Null/distinct/completeness audit, all 4 files
│   │   └── 02_data_chunking.py              # Splits cars.csv into 4 chunks
│   └── utils/
│       └── chunk_io.py                      # Shared single-file-write + reconciliation helpers
├── tests/
│   └── test_data_chunking.py                # Schema + row-count-reconciliation evidence
├── docs/
│   ├── requirements_and_assumptions.md
│   └── data_mapping.md
└── README.md
```

## Setup

### Prerequisites
- A Databricks **Free Edition** workspace (serverless compute; do not use a
  trial workspace — see project brief).
- Databricks CLI configured locally if deploying manually (`databricks auth login`),
  or `DATABRICKS_HOST` / `DATABRICKS_TOKEN` set as GitHub Actions repo secrets
  for CI deployment.
- `databricks.yml` → `workspace.host`: replace the placeholder with your own
  workspace URL.

### Data setup
Upload the four raw files to the landing volume before running any job:
```
/Volumes/vstone_catalog/raw/landing/cars.csv
/Volumes/vstone_catalog/raw/landing/telegram.csv
/Volumes/vstone_catalog/raw/landing/node_locations.csv
/Volumes/vstone_catalog/raw/landing/streets_list.csv
```
(Volumes are created by `00_setup_infrastructure` — run that job first, or
upload after its first successful run.) Easiest path: Catalog Explorer →
navigate to the `landing` volume → Upload, or `databricks fs cp` via the CLI.

### Deploy
```bash
databricks bundle validate
databricks bundle deploy --target dev
databricks bundle run data_chunking_job --target dev
```

## Execution order (Day 1)

1. `00_setup_infrastructure` — creates catalog/schemas/volumes.
2. Upload the 4 raw files to the landing volume (manual step, see above).
3. `01_data_profiling` — audits all 4 files; confirms the assumptions in
   `docs/requirements_and_assumptions.md` (e.g. `enter`/`exit` value ranges,
   the invalid sensor coordinate).
4. `02_data_chunking` — splits `cars.csv` into the 4 named chunk files.
5. `tests/test_data_chunking` — verifies file existence, schema, and
   row-count reconciliation.

All four are wired together as the **"Data Chunking"** job in `databricks.yml`
with explicit `depends_on` ordering, so `databricks bundle run data_chunking_job`
runs the whole sequence in one go.

## Testing (Day 1)

`tests/test_data_chunking.py` checks, against the actual output of a run:
- exactly the 4 expected chunk files exist,
- chunk 1 & chunk 2 (CSV) schemas match the 5-column source schema exactly
  (`assertSchemaEqual`),
- chunk 3 (JSON) has the same 5 keys,
- the 4 chunks' row counts sum exactly to the source row count,
- the chunk 1 split ratio is within tolerance of the target 50%.

The chunking and profiling logic was also validated locally against a
300,000-row sample of `cars.csv` and the full `telegram.csv` /
`node_locations.csv` / `streets_list.csv` files before being finalized — see
"Known limitations" in `docs/requirements_and_assumptions.md` for what
still needs validating against the full file inside an actual workspace.

## What's next (Day 2)

- `feature/bronze-layer` branch.
- `03_bronze_csv_copyinto.py` — ingest `cars_chunk_1.csv` via COPY INTO with
  `load_dt`/`source` audit columns and table/column descriptions.
- Bronze ingestion job added to `databricks.yml` alongside the existing
  Data Chunking job.
