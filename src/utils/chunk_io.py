"""
Shared I/O helpers for chunking and bronze notebooks.

Spark's distributed writers produce a directory of part-files by default
(`part-00000-....csv`, a `_SUCCESS` marker, etc). Downstream COPY INTO and
Auto Loader steps can read directory paths fine, but the project's naming
convention (and the reference project's own convention) calls for exactly-
named single files in the chunks volume, e.g. `streets_chunk_1.csv`. This module
coalesces to one partition, writes to a temp dir, then renames the single
part-file up to the clean target name and removes the temp dir.

Importable both from a Databricks notebook (where `dbutils` exists in the
global namespace) and unit-tested locally by passing an explicit `dbutils`
reference.
"""


def write_single_file(df, dbutils, output_dir, final_name, fmt, write_options=None):
    """
    Write `df` as a single output file named `final_name` inside `output_dir`.

    Parameters
    ----------
    df : pyspark.sql.DataFrame
    dbutils : the notebook's dbutils object (for dbutils.fs.ls / mv / rm)
    output_dir : str — target directory, e.g. "/Volumes/cat/raw/chunks"
    final_name : str — target filename, e.g. "streets_chunk_1.csv"
    fmt : "csv" or "json"
    write_options : dict of extra .option(...) calls, e.g. {"header": "true"}

    Returns
    -------
    str : full path to the written file
    """
    if fmt not in ("csv", "json"):
        raise ValueError(f"write_single_file supports csv/json only, got: {fmt}")

    write_options = write_options or {}
    tmp_dir = f"{output_dir}/_tmp_{final_name}"

    writer = df.coalesce(1).write.mode("overwrite")
    for k, v in write_options.items():
        writer = writer.option(k, v)
    getattr(writer, fmt)(tmp_dir)

    # Find the single part-file Spark produced and rename it to final_name
    part_files = [
        f.path for f in dbutils.fs.ls(tmp_dir)
        if f.name.startswith("part-") and f.name.endswith(f".{fmt}")
    ]
    if len(part_files) != 1:
        raise RuntimeError(
            f"Expected exactly 1 part-file in {tmp_dir}, found {len(part_files)}. "
            f"Did coalesce(1) run? Files: {part_files}"
        )

    final_path = f"{output_dir}/{final_name}"
    dbutils.fs.mv(part_files[0], final_path)
    dbutils.fs.rm(tmp_dir, recurse=True)
    return final_path


def reconcile_chunks(source_total, chunk_counts):
    """
    Verify that chunk row counts sum exactly to the source row count.
    Returns (passed: bool, summary: dict) — never silently swallows a mismatch.
    """
    total_chunked = sum(chunk_counts.values())
    passed = total_chunked == source_total
    summary = {
        "source_total": source_total,
        "total_chunked": total_chunked,
        "gap": source_total - total_chunked,
        "passed": passed,
        **chunk_counts,
    }
    return passed, summary
