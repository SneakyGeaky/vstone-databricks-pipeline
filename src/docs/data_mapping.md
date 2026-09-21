# Reference Project → VStone Mapping

The reference project (`src.zip`) implements a **used-car marketplace** pipeline
(Russian classifieds data — listings, catalog, geo, text descriptions, photos).
VStone implements a **Valencia smart-city traffic** pipeline (sensor counts +
citizen incident reports). Different domain, same medallion architecture and
Databricks technique-per-format requirements — this is the adaptation map.

## Dataset mapping

| Reference file | Rows | Role | VStone file | Rows | Role |
|---|---|---|---|---|---|
| `1_main.csv` | 1,083,269 | Primary fact — gets **chunked** into 4 formats | `cars.csv` | 24,681,794 | Primary fact — gets **chunked** into 4 formats |
| `1_text.csv` | — | Secondary, loaded whole (DLT) | `telegram.csv` | 128,440 | Secondary, loaded whole (DLT) — citizen messages |
| `catalogs.csv` | — | Dimension, loaded whole | `streets_list.csv` | 36 | Dimension, loaded whole — street master list |
| `final_geografic.csv` | — | Dimension, loaded whole | `node_locations.csv` | 14 | Dimension, loaded whole — sensor coordinates |
| `1_photo.csv` | — | Secondary, loaded whole | *(no VStone equivalent)* | — | Not carried over — no analogous artifact exists |
| *(none — no reference equivalent)* | — | — | `streets.csv` | ~87.8M (est.) | **VStone-only.** Per-street sensor log (noise/pollution/light/raining every 10s) — discovered after Day 1, not yet uploaded. See `requirements_and_assumptions.md`. Not chunked like `cars.csv`; loaded whole via Auto Loader in a later day, same treatment as `telegram.csv`/`node_locations.csv`/`streets_list.csv`. |

`streets.csv` has no reference-project counterpart at all — the reference
project only has one "5th/6th" style secondary file pattern (`07_remaining_4_files.py`
loads 4 whole files), which `streets.csv` will follow the *pattern* of
(explicit schema, whole-file DLT/Auto Loader load, audit columns), but there
was nothing to map a specific reference column set onto since VStone's own
5th column set (noise/pollution/light/raining) doesn't exist on the
reference side.

**Why `cars.csv` is the one that gets chunked:** it's the only VStone file large
enough and "transactional" enough to match the PDF's Day 1–3 instructions
("chunk 1... chunk 2... chunk 3 to JSON... chunk 4 to XML", later ingested via
COPY INTO / DLT / Auto Loader / PySpark XML). The other three files are
reference dimension/event tables loaded as single full files, exactly the way
the reference project treats its four non-`1_main` files in
`07_remaining_4_files.py`.

## Schema mapping (`1_main.csv` → `cars.csv`)

| Reference column | VStone column | Type | Note |
|---|---|---|---|
| `id` | `id` | STRING (bronze) | ⚠️ **Not a row key in VStone.** Reference `id` is a unique listing ID. VStone `id` cycles 0–998 — it repeats constantly. Row identity in VStone is really the tuple `(location, date)`. Documented as an assumption below — do not treat `id` as a dedup key in Silver. |
| `place` (city) | `location` | STRING (bronze) → INT (silver) | Reference is a free-text city name; VStone is a numeric sensor ID (1–14), resolved via `node_locations.csv`. |
| `date` | `date` | STRING (bronze) → TIMESTAMP (silver) | Reference: `DD.MM.YYYY`-ish. VStone: ISO-8601 with milliseconds (`2023-06-02T12:36:03.093Z`). |
| `cost` | *(none)* | — | No price/currency concept in VStone — not carried over. |
| `marka`, `model` | *(none)* | — | No brand/model concept — not carried over. |
| *(none)* | `enter` | STRING (bronze) → INT (silver) | VStone-only. **Vehicle count entering the node in the interval**, not an hour value — see assumption below. |
| *(none)* | `exit` | STRING (bronze) → INT (silver) | VStone-only. Vehicle count exiting. |

No field-for-field forcing was done — the two datasets genuinely don't share
business columns beyond `id` and a date/location concept, which is expected
and called out explicitly rather than papered over (master prompt §6/§19).

## Architecture mapping

| Reference component | VStone equivalent | Action |
|---|---|---|
| Catalog `vstone_catalog`, schemas `raw/bronze/silver/gold/security`, volumes `landing/chunks/checkpoints` | Same names | **Reused as-is.** This is a better-governed structure than the existing VStone draft's `dev_catalog` and is what Days 4–9 (bronze/silver/gold/security) will need anyway. See assumptions doc. |
| `01_data_profiling.py.py` (profiles 5 landing files, null/distinct/completeness audit) | `01_data_profiling.py` | **Adapted.** Same audit-table pattern, retargeted at `cars.csv`, `telegram.csv`, `node_locations.csv`, `streets_list.csv`. Cyrillic-catalog-specific composite-PK branch removed (not applicable). |
| `02_data_chunking.py` + `csv_splitter.py` (pure-Python, driver-side, row-exact split) | `02_data_chunking.py` | **Rewritten, not copied.** Reference's dataset is 1.08M rows — fine for single-threaded Python. `cars.csv` is 24.7M rows (23x larger, 859 MB) — driver-side Python row-by-row splitting doesn't scale. Reimplemented with `df.randomSplit()` (Spark-native, distributed) at the corrected 50/20/20/10 weights, same target-format mapping, same "reconcile chunk row counts against source" discipline. See assumptions doc for the full rationale. |
| `07_remaining_4_files.py` (DLT, loads 4 secondary files whole, per-file schema) | *(Day 3 — not built yet)* | Pattern noted for later: `telegram.csv`, `node_locations.csv`, `streets_list.csv` will load the same way — explicit STRING schema, `pathGlobFilter`, audit columns. |
| `00_catalog_setup.py.py` (creates catalog/schemas/volumes via widgets) | `00_setup_infrastructure.py` | **Adapted** — existing VStone draft only created one schema (`raw_schema` under `dev_catalog`) with no widgets. Rebuilt to create all 5 schemas + 3 volumes, fully parameterized. |

## What was *not* carried over from the reference

- Currency/price business rules, brand/model catalog logic, photo URL handling —
  no VStone equivalent exists.
- Cyrillic column-name handling (`delta.columnMapping.mode = 'name'`) — VStone
  has no non-ASCII column names.
- Pure-Python CSV→XML/JSON converter utilities (`csv_to_json.py`, `csv_to_xml.py`)
  — superseded by Spark-native writes at VStone's data volume (see assumptions).

## What was reused verbatim (pattern, not code)

- Bronze/Silver/Gold/Security schema layout and volume layout.
- Audit-column discipline (`load_dt`, `source`/`source_file`) on every bronze write.
- "Explicit STRING schema, `inferSchema=false`" rule for all bronze reads.
- Widget-driven configuration (no hardcoded catalog/schema names in notebook bodies).
- Post-write reconciliation checks as testable evidence.
