# Requirements Documentation & Assumptions — Day 1

## Datasets (profiled 2026-09-10)

| File | Rows | Size | Description |
|---|---|---|---|
| `cars.csv` | 24,681,794 | 859 MB | Traffic-sensor event log. Columns: `enter, exit, date, id, location`. Date range `2023-06-02` → `2024-03-10`. |
| `telegram.csv` | 128,440 | 55 MB | Free-text citizen traffic/incident reports. Columns: `message, date, hour`. Same date range as `cars.csv`. Fields are quoted/multi-line — needs real CSV parsing (`multiLine`, `escape='"'`), not naive comma-split. |
| `node_locations.csv` | 14 | <1 KB | Sensor dimension: `latitude, longitude, location`. `location` values 1–14, matching `cars.csv.location` exactly. |
| `streets_list.csv` | 36 | 2 KB | Street dimension: `street, long, latitude, longitude, dangerous, street_id`. `long` = street length in meters, `dangerous` = a 0–1 risk score. |

## Dataset discovered after Day 1: `streets.csv` (not yet uploaded)

Source: [Kaggle — "Data from a traffic simulator" (xxjcaxx/trafficsimulator)](https://www.kaggle.com/datasets/xxjcaxx/trafficsimulator),
the same source dataset behind `cars.csv`, `telegram.csv`, `node_locations.csv`,
and `streets_list.csv` (confirmed via the Kaggle listing's own description).
The file itself (7.79 GB) has not been uploaded. **Column names confirmed
correct by the project owner (2026-09-10).** Row count, data ranges/types,
and the light/raining hypothesis below are still reconstructed from Kaggle's
preview histograms only, not from profiling actual data — do not write
Bronze/Silver transformation logic that depends on exact value ranges or
distributions without a real sample first.

**Schema (6 columns — names confirmed, per Kaggle's file description):**

| Column | Type (inferred) | Description (Kaggle's own wording, paraphrased) |
|---|---|---|
| `noise` | float | Not a physical measure — sum of cars on the street divided by street length. |
| `pollution` | float | Pollution from cars on the street divided by street length. |
| `date` | timestamp | Sample timestamp, ISO-8601 with milliseconds — same format as `cars.csv.date`. |
| `light` | float, 0–100 | Ambient light level; depends on rain and hour of day. |
| `raining` | float, 0–100% | Rain intensity. |
| `street_id` | int, 1–36 | **Explicit FK to `streets_list.csv.street_id`** — Kaggle states this directly. |

**Row count:** cross-checked two independent histograms from the Kaggle
preview (weekly date buckets vs. per-`street_id` buckets) — both land at
**~86–88 million rows** (street_id buckets: 36 × ~2,439,465 ≈ 87,820,725,
the more reliable of the two since it's a uniform per-street count).
7.79 GB ÷ 87.8M rows ≈ 95 bytes/row, consistent with 2 floats + 1 timestamp
+ 1 float + 1 float + 1 small int.

**Sampling cadence:** "Each 10 seconds of simulation, all the sensors of a
street send their information" (Kaggle's own description) — same
2023-06-02 → 2024-03-10/11 window as `cars.csv`.

**Assumption — `light`/`raining` are likely city-wide per-tick values, not
truly street-specific.** In the raw row preview, `light` and `raining`
values are near-identical across different `street_id`s sharing the same
10-second timestamp (e.g. all ~69–70 and ~30–32 respectively at
`2023-06-02T12:35:53.093Z`), while `noise`/`pollution` vary widely per
street as expected from their per-street formula. This reads as a shared
weather/time condition replicated onto every street's row rather than a
true per-street measurement. **Not confirmed against real data** — worth
checking once a sample is available, since it affects whether `light`/
`raining` belong in a separate weather fact table instead of being repeated
87M times.

**Assumption — this file is NOT a fifth chunk of `cars.csv`, and is not
itself re-chunked into 4 formats.** The Day 1–3 "chunk into 4
formats/techniques" requirement was satisfied by `cars.csv` — that
requirement calls for demonstrating COPY INTO / DLT / Auto Loader / PySpark
XML once, not applying it to every large file. At ~87.8M rows (3.5x
`cars.csv`), `streets.csv` is treated as an **additional Bronze source**,
landed whole and ingested with a single technique — Auto Loader is the
natural fit given the volume and its continuously-arriving-sensor-log
shape, matching how the reference project treats its secondary files in
`07_remaining_4_files.py`. This is scoped for a later day (Day 3, alongside
`telegram.csv`/`node_locations.csv`/`streets_list.csv`), not folded into the
already-delivered Day 1 chunking notebook, which was scoped and validated
against `cars.csv` only.

**Updated join model:** `streets.csv.street_id` → `streets_list.csv.street_id`
is a **clean, explicit foreign key** (unlike `cars.csv.location` →
`node_locations.csv.location`, which is a real value match but has no
declared FK in the source, and unlike `telegram.csv` → `streets_list.csv`,
which only joins by matching street name text). This is the strongest join
in the whole dataset and should anchor the Gold-layer street dimension.

## Assumptions (explicit — flagged rather than silently guessed, per project instructions)

1. **`enter` / `exit` are vehicle counts, not clock-hour values.**
   The existing VStone draft's bronze notebook commented these as
   "hour vehicle entered/exited." Profiling shows both columns have up to 36
   distinct values with observed values >23 (e.g. `35`), which rules out a
   0–23 hour interpretation. Treated as **counts of vehicles entering/exiting
   the node during the logging interval**. This will matter for Silver/Gold
   business rules (Day 4+) — flagging now so it isn't silently carried forward
   as a wrong assumption.

2. **`id` (0–998, cycling) is not a row-level primary key on its own — but
   combined with `(location, date)`, it completes the true grain.**
   `id` alone repeats constantly across the 24.7M rows and cannot be used
   for dedup by itself. The original version of this assumption claimed
   the grain was `(location, date)` alone — **that was wrong, confirmed via
   real Bronze data on 2026-09-17**: at `location=7` alone, `(location,
   date)` had 746,345 duplicate rows, and every single one was a genuinely
   distinct reading (different `enter`/`exit` values), not log duplication
   — 0 true full-row duplicates existed. `(location, date, id)` has zero
   duplicates. `cars_silver`'s dedup key (`10_silver_other.py`) and
   `fact_traffic_counts`'s grain (`14_gold_facts.py`) were both corrected
   to `(location, reading_ts, reading_id)` — see the Day 6 correction
   entry below for the fuller investigation.

3. **`node_locations.csv` has one row with invalid coordinates.**
   `location = 7` has `latitude = 0.0, longitude = 0.0` — not a real Valencia
   coordinate (all others cluster around `38.98–38.99°N, -0.51 to -0.54°E`).
   Not corrected or fabricated — carried through Bronze as-is and flagged as a
   Silver-layer data-quality/quarantine candidate.

4. **`streets_list.csv` and `node_locations.csv` do not share a key.**
   `node_locations.location` (1–14, sensor IDs) and `streets_list.street_id`
   (1–36, street segments) are different grains — no direct FK. They are only
   related by approximate geographic proximity (lat/long). `telegram.csv`
   messages, however, **do** reference `streets_list.street` by exact name
   text (e.g. *"Maulets"*, *"Aben FerriA"*), so that join is name-based, not
   spatial. No forced key was invented — this is documented so Silver/Gold
   design (Day 4+) starts from a correct join model instead of a guessed one.

5. **Chunk split ratio: 50/20/20/10, matching technique-per-chunk from the PDF.**
   The PDF doesn't specify exact percentages, only the technique mapping
   (chunk 1 → COPY INTO first load, chunk 2 → incremental/DLT, chunk 3 → JSON/
   Auto Loader, chunk 4 → XML/PySpark). The reference project uses 50/20/20/10
   for the same four-way split; adopted for consistency rather than inventing
   a new ratio. The existing VStone draft used 50/30/10/10 (i.e. wrong weights
   on chunks 2 and 4) — corrected here so the split matches the reference
   pattern and the two smaller chunks (JSON, XML) stay proportionate.

6. **Chunking implemented in Spark, not driver-side Python.**
   The reference project's `csv_splitter.py` reads/writes CSV rows one at a
   time in pure Python on the driver — workable for its 1.08M-row file, not
   for `cars.csv`'s 24.7M rows / 859 MB. Rewritten using `df.randomSplit()`
   (distributed, reproducible via a fixed seed) instead. `randomSplit`
   percentages are statistically close but not row-exact; at this volume
   (24.7M rows) the deviation from target is well under 0.2 percentage points
   in local testing, and every chunk's row count is verified and summed
   against the source count as an explicit test, not just assumed correct.

7. **XML chunk written via Databricks' native `xml` format, not `spark-xml` jar
   or pure-Python `xml.etree`.** Databricks Runtime 14.3+ has built-in native
   XML read/write (`format("xml")`), requiring no external library — confirmed
   current as of this writing. This avoids depending on attaching a Maven
   library to a cluster, which matters because **Databricks Free Edition is
   serverless-only** (per the project brief) and classic JAR-attachment
   workflows may not apply the same way. If native XML is for any reason
   unavailable in your workspace, the fallback is `xml.etree` (driver-side, on
   the 10% XML chunk only — ~2.47M rows, not the full file), same as the
   reference project's approach; a commented alternative is left in the
   notebook.

8. **Catalog/schema naming: adopted `vstone_catalog` (reference convention),
   not `dev_catalog` (existing VStone draft).**
   The existing draft's `00_setup_infrastructure.py` only created one schema
   (`raw_schema`) under `dev_catalog`. Days 4–9 require `bronze`, `silver`,
   `gold`, and `security` schemas under a single governed catalog per the
   Unity Catalog requirement in the PDF — `dev_catalog` reads as a personal/
   scratch catalog, not a governed project catalog. Standardized on the
   reference's `vstone_catalog` / `raw,bronze,silver,gold,security` / `landing,
   chunks,checkpoints` naming so every later day builds on the same
   foundation instead of a rename mid-project. All of it is a DAB variable
   with this as the default, not hardcoded, so it's a one-line override if you
   want a different name.

9. **`databricks.yml` workspace host and notebook paths were placeholders in
   the existing draft** (a specific personal workspace URL, a personal Gmail-
   based `/Workspace/Users/...` path, and a typo — `vtsone` instead of
   `vstone` — that would have made the job fail to find its notebook).
   Replaced the hardcoded user path with DABs' `${workspace.current_user.userName}`
   substitution so the bundle deploys correctly for whoever runs it, and left
   the `workspace.host` as a placeholder you fill in with your own Free
   Edition workspace URL.

10. **`1_photo.csv` (reference) has no VStone equivalent** — no photo/image
    artifact exists in the VStone datasets, so nothing was invented in its
    place (master prompt §19: don't fabricate data for missing fields).

## Known limitations at end of Day 1

- Chunking has been logic-tested against a 300K-row sample of `cars.csv` and
  the full `telegram.csv` / `node_locations.csv` / `streets_list.csv` files
  (see `tests/`), not yet run against the full 24.7M-row file inside an actual
  Databricks workspace — that requires the files to be landed in a real Unity
  Catalog Volume, which only you can do (see README "Data Setup").
- Native XML write (`format("xml")`) could not be locally validated — it's a
  Databricks Runtime–specific feature not present in open-source Spark. Logic
  mirrors the reference project's proven `05_bronze_xml_pyspark.py` pattern.

## Correction found at Day 6 — quarantine scope was too broad (not a PDF requirement, a bug)

**This is not dictated anywhere in the project requirements.** The PDF says
to quarantine malformed records and doesn't say anything about excluding
facts when a *different file's* metadata about the same key is bad — that
consequence came from my own Day 4 design choice, not the spec, and I
didn't trace it through to Gold at the time.

**What happened:** `node_locations.csv` has `location=7` with invalid
`(0.0, 0.0)` coordinates (flagged back in Day 1 profiling). In Day 4,
`node_locations_silver` quarantined that row entirely — treating "the
coordinates are bad" as "this location doesn't exist." But `location=7` is
a real sensor with ~2.37M real rows in `cars.csv`/`cars_silver`, which
never got quarantined (its own validity check only looks at
`location`/`date`, not an unrelated file's coordinate quality). Dropping
`location=7` from the dimension meant `dim_node_location` in Gold had 13
locations while `fact_traffic_counts` still had all 14 — every
`location=7` fact row became an orphan FK: 1,626,982 rows, caught by
`test_fact_traffic_counts_fk_integrity` in `test_gold_day6.py`.

**The actual bug:** conflating two different questions — *does this
location exist as a valid entity* vs. *do we trust one specific attribute
(coordinates) about it*. A dimension shouldn't lose a member because one
non-key attribute about it happens to be bad.

**Fix (`10_silver_other.py`):** `location=7` now stays in
`node_locations_silver` / `dim_node_location`. Its `latitude`/`longitude`
are NULLed (not kept as the misleading raw `0.0`), and a new
`has_valid_coordinates` boolean flags the issue so it's visible rather than
silently hidden. `node_locations_silver_quarantine` is now an audit copy
for this specific issue, not a mutually-exclusive removal — `location=7` is
correctly in *both* tables (main, with nulled coordinates; quarantine, for
audit visibility), which is a deliberate deviation from the mutually
exclusive valid/quarantine pattern used everywhere else in this project
(`cars_silver`, `telegram_silver`, `streets_silver` — those all quarantine
on missing/malformed *key* columns, not on a non-key attribute, so
mutual exclusivity is still the right call for them).

## Correction found at Day 6 (during the above investigation) — cars.csv grain was wrong

Investigating the `location=7` orphan-FK issue above led to checking
whether `cars_silver`'s dedup key was actually correct — it wasn't.

**Original assumption (Day 1):** grain is `(location, date)`, `id` unused.

**What the real data showed:** `location=7` alone had 746,345 rows where
`(location, date)` repeated — but `SELECT ... GROUP BY *` (every column)
found **zero** true full-row duplicates among them. Sample:

| location | date | enter | exit | id |
|---|---|---|---|---|
| 7 | 2024-02-10T05:39:13.093Z | 34 | 18 | 754 |
| 7 | 2024-02-10T05:39:13.093Z | 1 | 18 | 922 |

Same location, same timestamp, **different `enter` and different `id`** —
two genuinely distinct sensor readings, not the same reading logged twice.
`dropDuplicates(["location","reading_ts"])` was arbitrarily keeping one
and silently discarding the other. `(location, date, id)` has zero
duplicates — confirmed the actual grain.

**Fix:** `cars_silver`/`cars_silver_quarantine` (`10_silver_other.py`) and
`fact_traffic_counts` (`14_gold_facts.py`) now dedup/key on `(location,
reading_ts, reading_id)`. The passthrough column was renamed `raw_id` →
`reading_id` since it's now an active grain component, not a "kept but
unused" field — the old name implied otherwise.

**Process takeaway, applied going forward:** before quarantining or
excluding anything based on an assumed grain, check whether "duplicates"
on that grain are true full-row duplicates or rows that differ elsewhere —
`GROUP BY <assumed_key>` catching rows is not the same evidence as `GROUP
BY *` finding zero variation among them. The first only tells you the key
is incomplete; only the second tells you collapsing them is actually safe.
