#!/usr/bin/env python3
"""The GeoParquet invariants rashid does not check for a partitioned collection.

rashid validates partition files through `partition:glob`, but only for one
thing: that they share a Parquet schema (PTL-DAT-014). Its other byte checks
iterate a node's declared assets, and a partitioned collection has no `data`
asset, so nothing inspects the partitions themselves.

Verified against rashid 0.1.5 on 2026-08-14 by planting a partition with a
1,176,571-row row group, 7.8x over the PTL-DAT-008 cap of 150,000, and
confirming a clean run. Renaming a column in the same tree did produce a
PTL-DAT-014 error, so the glob is read. It is the row-group, ordering,
statistics and version rules that do not reach it.

Reported as portolan-sdi/rashid#130. Delete this file once that is fixed and
rashid covers the same ground.

This asserts those rules directly, so the guarantee comes from somewhere. The
thresholds are rashid's own, taken from its source rather than restated from
the spec:

    PTL-DAT-008  no row group over 150,000 rows
    PTL-DAT-012  geo version 1.1, 1.1.x or 2.x
    PTL-DAT-007  a bbox covering column with statistics on its leaf fields
    PTL-DAT-014  one schema across every partition

SKIPs when staging/ is absent, as in CI and a fresh clone.

Run: python3 tests/test_geoparquet.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PARTITIONS = ROOT / "staging" / "road-detections" / "by_country"

MAX_ROW_GROUP_ROWS = 150_000
ALLOWED_GEO_VERSIONS = ("1.1", "2.")

if not PARTITIONS.is_dir():
    print("SKIP: staging/ is absent, so there are no partitions to check.")
    print("      Run tools/reencode.py to rebuild it, then re-run this.")
    raise SystemExit(0)

try:
    import pyarrow.parquet as pq
except ImportError:
    print("SKIP: pyarrow is not installed.")
    raise SystemExit(0)

files = sorted(PARTITIONS.glob("country=*/*.parquet"))
if not files:
    print(f"FAILED: no partitions under {PARTITIONS}")
    raise SystemExit(1)

errors: list[str] = []
schemas: set[str] = set()
worst_row_group = 0

for path in files:
    name = path.relative_to(PARTITIONS).as_posix()
    parquet = pq.ParquetFile(path)
    meta = parquet.metadata
    schemas.add(str(parquet.schema_arrow.remove_metadata()))

    biggest = max(meta.row_group(i).num_rows for i in range(meta.num_row_groups))
    worst_row_group = max(worst_row_group, biggest)
    if biggest > MAX_ROW_GROUP_ROWS:
        errors.append(f"{name}: row group of {biggest:,} rows exceeds {MAX_ROW_GROUP_ROWS:,}")

    raw = (meta.metadata or {}).get(b"geo")
    if raw is None:
        errors.append(f"{name}: no GeoParquet 'geo' metadata")
        continue
    geo = json.loads(raw)

    version = str(geo.get("version", ""))
    if not version.startswith(ALLOWED_GEO_VERSIONS):
        errors.append(f"{name}: geo version {version!r} is not 1.1.x or 2.x")

    column = geo["columns"][geo["primary_column"]]
    covering = column.get("covering", {}).get("bbox")
    if not covering:
        errors.append(f"{name}: no bbox covering column")
        continue

    # A covering column without statistics does not qualify: the reader cannot
    # prune row groups it has no min/max for.
    leaves = {c[-1] if isinstance(c, list) else c for c in covering.values()}
    stats_ok = set()
    group = meta.row_group(0)
    for i in range(group.num_columns):
        chunk = group.column(i)
        leaf = chunk.path_in_schema.split(".")[-1]
        if leaf in leaves and chunk.statistics and chunk.statistics.has_min_max:
            stats_ok.add(leaf)
    missing = leaves - stats_ok
    if missing:
        errors.append(f"{name}: bbox covering leaves without statistics: {sorted(missing)}")

if len(schemas) != 1:
    errors.append(f"partitions carry {len(schemas)} distinct schemas; the glob needs one")

if errors:
    print(f"FAILED: {len(errors)} problem(s) across {len(files)} partition(s)")
    for line in errors[:20]:
        print(f"  error  {line}")
    if len(errors) > 20:
        print(f"  ... and {len(errors) - 20} more")
    raise SystemExit(1)

print(
    f"OK: {len(files)} partitions, one schema, largest row group "
    f"{worst_row_group:,} rows (cap {MAX_ROW_GROUP_ROWS:,})"
)
