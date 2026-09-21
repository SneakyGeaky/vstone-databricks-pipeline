# Day 5 — Delta Lake ACID & Time Travel Evidence

## Business rules applied (`11_silver_business_rules.py`)

`vstone_catalog.silver.streets_business`, built from `streets_silver`:

1. **`raining` clipped to `[0,100]`** into a new `raining_clipped` column —
   original `raining` is preserved unchanged. Justified by the real
   profiling run in Day 1-3 work: 49.29% of all 87.8M rows are negative,
   ranging continuously down to ~‑1.0 — symmetric simulator noise around a
   0 baseline, not a rare artifact. Max observed ~101, so both bounds are
   clipped.
2. **`reading_date` / `reading_hour`** derived from `reading_ts` — the
   VStone equivalent of the PDF's "date standardization" business rule
   (there's no currency in this dataset, so no equivalent to "currency
   normalization").

## Why a separate table, not an UPDATE on `streets_silver` directly

`streets_silver` is a DLT-managed streaming table. Databricks rejects
external writes to pipeline-managed datasets
(`STREAMING_TABLE_OPERATION_NOT_ALLOWED`) — confirmed via Databricks' own
docs and multiple community threads describing the same error for both
`UPDATE` and even `COMMENT ON TABLE` against DLT streaming tables. The
reference project's Day 5 notebook runs `UPDATE` directly against its own
DLT table (`listings_silver_merged`) — that would very likely fail the
same way if actually run. `streets_business` is a **plain Delta table**
(created by a regular batch write, not `@dlt.table`), which fully supports
`UPDATE`/`MERGE`/time travel — that's what this demo runs against instead.

## ACID / time travel demo (`12_delta_acid_timetravel_demo.py`)

**Scenario (illustrative, not a real finding from the data):** street_id=1's
sensor is treated as miscalibrated, over-reporting pollution by 5% — a
`-5%` correction is applied via `UPDATE`.

**Atomicity:** the `UPDATE` is a single Delta transaction — it either fully
applies or fully fails; Delta never leaves the table in a partially-updated
state.

**Durability / audit trail:** `DESCRIBE HISTORY` (via `DeltaTable.history()`)
shows the `UPDATE` operation and its `operationParameters` (predicate, set
clause). First attempt tagged the commit via
`spark.conf.set("spark.databricks.delta.commitInfo.userMetadata", ...)` for
idempotency on rerun — that config isn't in serverless compute's allow-list
(`CONFIG_NOT_AVAILABLE.WITHOUT_SUGGESTION`, hit when actually running this
in Free Edition). Fixed to check `history()` for an existing `operation =
'UPDATE'` entry instead — this table is created by a full-overwrite `WRITE`
in `11_silver_business_rules.py`, and the only `UPDATE` that should ever
land on it is this demo's, so that check needs no config permissions at all.

**Time travel:** the notebook captures the table's version number
*before* the update programmatically (not hardcoded, unlike the reference
project's `VERSION AS OF 33` / `VERSION AS OF 35`), then queries
`VERSION AS OF <that version>` against the *current* state side by side.

### Evidence — fill in after running `12_delta_acid_timetravel_demo.py`

| Field | Value |
|---|---|
| Version before update | *(paste from notebook output)* |
| Version after update | *(paste)* |
| `avg_pollution` @ version before (street_id=1) | *(paste)* |
| `avg_pollution` @ current version (street_id=1) | *(paste)* |
| `DESCRIBE HISTORY` — last 5 versions | *(paste the displayed table)* |

I can't run this against your actual Databricks workspace, so this table
is a template — run the notebook once, then paste the real output here as
the deliverable evidence, not a filled-in guess.

## Testing (`tests/test_business_rules_day5.py`)

- `raining_clipped` always in `[0,100]`.
- Original `raining` column still contains out-of-range values (confirms
  the clip added a new column rather than overwriting).
- `reading_date`/`reading_hour` fully populated.
- Table has more than 1 Delta version (confirms the ACID demo actually ran).
- The demo's `UPDATE` operation is present in history (checked via
  `operation = 'UPDATE'`, not a custom tag — see notebook comments for why).
- `VERSION AS OF 0` differs from current for street_id=1 (confirms time
  travel actually returns a different historical state, not just that the
  syntax runs without error).
