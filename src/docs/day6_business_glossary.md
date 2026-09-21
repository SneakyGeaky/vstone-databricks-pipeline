# Day 6 — Business Glossary

| Term | Definition | Source / Table |
|---|---|---|
| **Reading** | One sensor measurement event — either a street sensor (`fact_street_readings`) or a traffic node (`fact_traffic_counts`), captured every 10 seconds (streets) or at variable intervals (traffic nodes). | `fact_street_readings`, `fact_traffic_counts` |
| **Street** | A named street segment in the Valencia road network. Some physical streets have two directional sensors (suffix A/B in `street_name`, e.g. "Aben FerriA"). | `dim_street` |
| **Node / Location** | A fixed traffic-counting sensor position (1–14), distinct from a street — a node counts vehicles at a point, a street reports ambient conditions along a segment. | `dim_node_location` |
| **Noise** | Not a decibel measurement — defined by the source simulator as (count of cars on the street) ÷ (street length). A density proxy, not a physical acoustic reading. | `fact_street_readings.noise` |
| **Pollution** | Car emissions on the street ÷ street length — same density-style formula as Noise, different underlying quantity. | `fact_street_readings.pollution` |
| **Raining (raw)** | Cast, unclipped rain-intensity value. Confirmed via full profiling: 49.29% of all readings are negative (down to ~‑1.0), simulator noise around a 0 baseline — kept for auditability, not used directly in analysis. | `fact_street_readings.raining` |
| **Raining (clipped)** | The `raining` value clamped to `[0, 100]` — the business-rule-corrected value; this is what aggregates and dashboards should use. | `fact_street_readings.raining_clipped` |
| **Enter Count / Exit Count** | Number of vehicles entering/exiting a traffic node in the logging interval. Confirmed via Day 1 profiling to be counts (values exceed 23, ruling out an hour-of-day interpretation) — not "hour vehicle entered/exited" as an earlier draft mistakenly assumed. | `fact_traffic_counts.enter_count` / `exit_count` |
| **Citizen Report** | A free-text message from a citizen reporting a traffic or parking incident, with a date and hour. No unique identifier exists in the source — grain is the full `(message, date, hour)` tuple. | `fact_citizen_reports` |
| **Danger Score** | A 0–1 risk score per street, source-provided (not derived by this pipeline). | `dim_street.danger_score` |
| **Active dimension row** | For SCD2 dimensions (`dim_street`, `dim_node_location`), the current version of a record: `__END_AT IS NULL`. All Gold aggregates join dimensions on this filter. | `dim_street`, `dim_node_location` |
| **Quarantined record** | A Bronze/Silver row that failed a validity check (missing grain key, malformed value, or a known bad value such as `node_locations` location=7's `(0,0)` coordinates) and was routed to a `*_silver_quarantine` table instead of the main Silver table. Not present anywhere in Gold. | `*_silver_quarantine` tables |
| **Best-effort FK** | A foreign key resolved by inference (text matching) rather than present as an explicit key in the source data. Currently applies only to `fact_citizen_reports.street_id`. Nullable, and not guaranteed correct when a message is ambiguous. | `fact_citizen_reports.street_id` |
