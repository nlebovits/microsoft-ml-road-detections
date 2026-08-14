# Agent Guide: Microsoft ML Road Detections

Every claim in this file is quoted from Microsoft, cited to a source, or measured from the published
data. Each query below was run against the published files and its answer is inlined.

## What This Collection Holds

256,555,010 road segments detected by Microsoft from Bing Maps aerial imagery, in 235 GeoParquet
files partitioned by country code. One row is one road segment: a WKB LineString plus an approximate
width in metres. There are no dates, no road classes, and no confidence scores.

This is a mirror of [microsoft/RoadDetections](https://github.com/microsoft/RoadDetections). The
geometry is Microsoft's, unmodified.

## How To Read It

There is **no collection-level `data` asset**. This is a partitioned collection, so the access path
is `partition:glob` on `collection.json`:

```
https://data.source.coop/nlebovits/microsoft-ml-road-detections/road-detections/by_country/country=*/*.parquet
```

Name a single country directory to read one file instead of 235. That is almost always what you
want; the whole glob is 12 GB.

```sql
INSTALL spatial; LOAD spatial; INSTALL httpfs; LOAD httpfs;

SELECT count(*) AS segments
FROM read_parquet(
  'https://data.source.coop/nlebovits/microsoft-ml-road-detections/'
  || 'road-detections/by_country/country=URY/URY.parquet'
);
-- 263971
```

Counting across every partition reads footers only, so it is cheap even over HTTP:

```sql
SELECT count(*)
FROM read_parquet(
  'https://data.source.coop/nlebovits/microsoft-ml-road-detections/'
  || 'road-detections/by_country/country=*/*.parquet'
);
-- 256555010
```

Hive partitioning means the `country` value is recoverable from the path, and it is also a real
column in every file. They always agree; this was checked across all 235 files.

```sql
SELECT country, count(*) AS segments
FROM read_parquet(
  'https://data.source.coop/nlebovits/microsoft-ml-road-detections/'
  || 'road-detections/by_country/country=*/*.parquet'
)
GROUP BY country ORDER BY segments DESC LIMIT 5;
-- USA  62440047
-- IND  14889142
-- RUS  11517735
-- BRA  10439202
-- DEU   9553233
```

## Filter On bbox, Not On geometry

Every file carries a GeoParquet 1.1 `bbox` covering column with per-row-group statistics, and rows
are Hilbert-ordered. A predicate on `bbox.*` lets the reader skip row groups. A predicate on
`ST_Intersects(geometry, ...)` alone does not: it has to decode every geometry first.

```sql
SELECT count(*)
FROM read_parquet(
  'https://data.source.coop/nlebovits/microsoft-ml-road-detections/'
  || 'road-detections/by_country/country=NLD/NLD.parquet'
)
WHERE bbox.xmin > 4.85 AND bbox.xmax < 4.95
  AND bbox.ymin > 52.35 AND bbox.ymax < 52.40;
-- 8763
```

Note what that predicate means: segments **contained** in the window. For segments that merely
**intersect** it, invert the comparison, then refine with a geometry test if you need exactness:

```sql
SELECT count(*)
FROM read_parquet(
  'https://data.source.coop/nlebovits/microsoft-ml-road-detections/'
  || 'road-detections/by_country/country=NLD/NLD.parquet'
)
WHERE bbox.xmin < 4.95 AND bbox.xmax > 4.85
  AND bbox.ymin < 52.40 AND bbox.ymax > 52.35;
-- 9033
```

Row groups hold at most 100,000 rows, which is what makes that pruning fine-grained.

## Quirks That Produce Silently Wrong Answers

**The `country` column is not ISO 3166-1 alpha-3.** It is Microsoft's own code list. Six codes have
no ISO equivalent, and one collides with ISO while meaning something narrower:

| Code | Microsoft's meaning |
|---|---|
| `XKS` | Kosovo |
| `XSA` | Saba |
| `XSE` | Sint Eustatius |
| `XXG` | Gaza Strip |
| `XXH` | Golan Heights |
| `XXW` | West Bank |
| `BES` | **Bonaire alone**, where ISO `BES` is Bonaire, Sint Eustatius and Saba together |

Joining to an ISO gazetteer on `BES` double-counts Saba and Sint Eustatius, which are present
separately. All seven exist in the data:

```sql
SELECT country, count(*) AS segments
FROM read_parquet(
  'https://data.source.coop/nlebovits/microsoft-ml-road-detections/'
  || 'road-detections/by_country/country=*/*.parquet'
)
WHERE country IN ('XKS','XSA','XSE','XXG','XXH','XXW','BES')
GROUP BY country ORDER BY country;
-- BES    2426
-- XKS   97744
-- XSA     128
-- XSE     433
-- XXG   38484
-- XXH    6642
-- XXW  110601
```

**Microsoft's own code manifest is stale.** Åland is `ALA` in the data, correctly, but
[AlphaCodeToRegionName.tsv](https://raw.githubusercontent.com/microsoft/RoadDetections/main/AlphaCodeToRegionName.tsv)
on `main` still lists `ALI`. A join against that manifest drops Åland. The data-side fix is confirmed
in [issue #17](https://github.com/microsoft/RoadDetections/issues/17); the manifest was never
updated.

**`geometry_type` is constant.** It reads `LineString` in all 256,555,010 rows, in mixed case, not
`LINESTRING`. Filtering on it is always a no-op, and matching on the uppercase spelling always
returns zero.

**The CRS is OGC:CRS84, so planar functions return degrees.** `ST_Length(geometry)` gives degrees,
not metres. For a small area, project first.

**Do not use DuckDB's `ST_Length_Spheroid` on this data.** It was checked against DuckDB 1.4.1 and
1.5.5 on 2026-08-14 and is wrong in both. Malaysia returns `NaN` for every one of its 1,318,345 rows.
Uruguay returns a plausible 85,547 km, which is 9.7% below the correct 94,776 km. Per-geometry it is
erratic rather than biased: on five sampled Uruguayan segments it gave 409.59, 45.70, 58.08, 67.54
and 183.53 m where both a haversine and an independent Vincenty implementation agreed on 362.73,
42.35, 103.62, 64.97 and 205.76 m. Those two methods matched each other to within 0.2%.

A finite wrong answer is the dangerous case here, because nothing signals it. The 54,225,233 km
figure in the README was computed from WKB coordinates directly for this reason.

**There is no date column.** Vintage follows the underlying imagery, which Microsoft says it cannot
pin down per record. Any temporal analysis of this data is unfounded.

**Coverage has holes by design.** Mainland China, Japan, and Korea are absent, plus parts of
Switzerland and the United Kingdom, per
[issue #21](https://github.com/microsoft/RoadDetections/issues/21). Absence of roads is not evidence
of absence of roads.

**This is not an OpenStreetMap difference layer, despite the pipeline description.** Microsoft lists
a conflation stage that excludes "roads and parts of roads that already exist in the road network
(OSM)", which reads as though the release holds only roads OSM lacks. It does not. Measured on
2026-08-14:

```sql
SELECT count(*)
FROM read_parquet(
  'https://data.source.coop/nlebovits/microsoft-ml-road-detections/'
  || 'road-detections/by_country/country=DEU/DEU.parquet'
)
WHERE bbox.xmin > 13.36 AND bbox.xmax < 13.42
  AND bbox.ymin > 52.50 AND bbox.ymax < 52.53;
-- 2589   central Berlin, exhaustively mapped in OSM for over a decade
```

Microsoft's 2022 blog post also quotes "47.8M km of all roads and 1.16M km of missing roads from Open
Street Map (OSM)" as two separate figures, and the 54.2M km published here is of the former scale
rather than the latter. Use it as a detection set,
not as a list of what OSM is missing. Anyone wanting the latter has to compute the difference
themselves.

## Width

`width_meters` is Microsoft's `WidthMeters`, "approximate width of the road in meters". How it is
derived is undocumented. The distribution is tight and right-skewed, which matters if you bin it:

```sql
SELECT
  min(width_meters)                                    AS min,
  quantile_cont(width_meters, 0.25)                    AS p25,
  median(width_meters)                                 AS p50,
  quantile_cont(width_meters, 0.75)                    AS p75,
  quantile_cont(width_meters, 0.95)                    AS p95,
  max(width_meters)                                    AS max
FROM read_parquet(
  'https://data.source.coop/nlebovits/microsoft-ml-road-detections/'
  || 'road-detections/by_country/country=NLD/NLD.parquet'
);
-- min 4.96 | p25 7.26 | p50 9.35 | p75 10.29 | p95 13.97 | max 73.33
```

Equal-width bins put almost everything in one bucket. The catalog's own styles use quantile breaks
at 7, 9.5, 11.5, 14, and 18 m for this reason.

## Computing Total Road Length

The published total of 54,225,233 km is derived, not quoted. It is computed by summing great-circle
segment distances over all 959,867,152 vertices with a mean-latitude equirectangular approximation
on a sphere of radius 6,371,008.8 m, which lands within roughly 0.5% of a true WGS84 geodesic.

`tools/reencode.py` in the catalog repository carries the implementation as `geodesic_km`. It parses
WKB from the Arrow buffers rather than building geometry objects, which is what makes 256 million
linestrings tractable. The short version, for one partition:

```python
import numpy as np, pyarrow.parquet as pq

R = 6_371_008.8
total_km = 0.0
pf = pq.ParquetFile("URY.parquet")
for batch in pf.iter_batches(batch_size=250_000, columns=["geometry"]):
    wkb = batch.column("geometry")
    off = np.frombuffer(wkb.buffers()[1], dtype=np.int32)[: len(wkb) + 1].astype(np.int64)
    data = np.frombuffer(wkb.buffers()[2], dtype=np.uint8)
    base = off[0]
    n_points = (off[1:] - off[:-1] - 9) // 16          # 9-byte WKB LineString header
    keep = np.ones(off[-1] - base, dtype=bool)
    keep[((off[:-1] - base)[:, None] + np.arange(9)).ravel()] = False
    c = data[base : off[-1]][keep].view(np.float64).reshape(-1, 2)
    lon, lat = np.radians(c[:, 0]), np.radians(c[:, 1])
    mid = (lat[:-1] + lat[1:]) * 0.5
    seg = R * np.hypot(np.diff(lat), np.diff(lon) * np.cos(mid))
    seg[np.cumsum(n_points)[:-1] - 1] = 0.0            # drop cross-geometry joins
    total_km += seg.sum() / 1000
# URY: 94776 km
```

That this sums to 54.23 million km across all partitions, against Microsoft's stated "54.2M km", is
the check that the mirror is complete.

## Related Collections

None in this catalog. Microsoft's building footprints,
[GlobalMLBuildingFootprints](https://github.com/microsoft/GlobalMLBuildingFootprints), are a natural
companion, but note they are **CDLA-Permissive-2.0**, not ODbL. Do not carry the licensing of one
across to the other.
