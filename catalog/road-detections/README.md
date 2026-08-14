# Microsoft ML Road Detections

256,555,010 road segments detected from Bing Maps aerial imagery, covering 235 country and
territory codes, as GeoParquet partitioned by country.

This is a **mirror**. Microsoft produces the data and publishes it at
[microsoft/RoadDetections](https://github.com/microsoft/RoadDetections). This catalog reformats and
hosts it. No geometry, attribute, or record was added, removed, or altered.

## What The Detections Are

Microsoft's [README](https://github.com/microsoft/RoadDetections) describes a four-stage pipeline:

1. **Semantic segmentation.** A convolutional neural network, described as "based on UNet and
   ResNet" and trained on "20k labeled satellite images covering diverse areas worldwide",
   classifies road pixels in Bing Maps imagery.
2. **Geometry generation.** Postprocessing, thinning, connectivity, graph construction, stitching.
3. **Conflation and cutting**, which Microsoft describes as "excluding roads and parts of roads that
   already exist in the road network (OSM)". Read that stage description alongside the limitation
   below: the published files are not restricted to roads OSM lacks.
4. **Classification**, dropping low-confidence roads and predicting road type.

Microsoft reports pixel precision of 85.24% and recall of 82.81%, APLS precision of 87.53% and
recall of 79.33%, and states that after filtering "the precision is at least 95%".

The imagery behind it is Bing Maps imagery, which Microsoft's
[2022 Bing Maps blog post](https://blogs.bing.com/maps/2022-12/Bing-Maps-is-bringing-new-roads)
describes as "collected between 2020 and 2022 including sources from both Maxar and Airbus".

One row is one road segment. Microsoft does not use the word "centreline" anywhere in its
documentation, so this catalog does not claim these geometries are centrelines, even though the
thinning step and the separate width attribute both point that way.

## Coverage

Worldwide, with documented exclusions. A Microsoft collaborator states in
[issue #21](https://github.com/microsoft/RoadDetections/issues/21):

> due to aerial imagery restrictions we don't process mainland China, Japan and Korea

adding that certain areas of Switzerland and the United Kingdom are excluded too.
[Issue #23](https://github.com/microsoft/RoadDetections/issues/23) adds that company policy sourced
roads for the China, Japan, and Korea region from elsewhere, so no mining was done there. The data
bears this out: the Eastern Asia region contains only Mongolia and Taiwan.

A Japan drop reportedly still exists outside the README download table, per
[issue #37](https://github.com/microsoft/RoadDetections/issues/37). It is not part of the
`2025.04.28` release this mirror was built from, and it is not included here.

**Microsoft publishes no country count.** The figure of 235 is measured from this data: 235 distinct
values in the `country` column, one partition each. Do not attribute it to Microsoft.

## Data Vintage

Microsoft's own statement, quoted in full:

> The vintage of the roads depends on the vintage of the underlying imagery. Because Bing Imagery is
> a composite of multiple sources it is difficult to know the exact dates for individual pieces of
> data. However data is up-to-date with freshest available imagery from Microsoft Maps.

There is no per-record date, and this catalog does not invent one. The upstream drop is
`2025.04.28`, verified on 2026-08-14 as still the current release. Roads were converted to
GeoParquet in October 2025.

## Schema

| Column          | Type                                  | Description                                                                                            |
| --------------- | ------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `country`       | `string`                              | Microsoft's region code for the partition. See the warning below.                                      |
| `width_meters`  | `double`                              | Microsoft calls this `WidthMeters` and documents it only as "approximate width of the road in meters". |
| `geometry_type` | `string`                              | Constant `LineString` in every row. Note the mixed case.                                               |
| `geometry`      | `binary`                              | WKB LineString, OGC:CRS84.                                                                             |
| `bbox`          | `struct<xmin,ymin,xmax,ymax: double>` | GeoParquet 1.1 covering column.                                                                        |

`geometry_type` is redundant with the GeoParquet geometry metadata and constant across all
256,555,010 rows. It is retained because the original conversion wrote it and removing it would
change the schema consumers already query.

**How `width_meters` is derived is not documented upstream.** Microsoft states what it approximates,
not how it was computed. Measured across all 256,555,010 rows it runs from 0.04 m to 119.28 m, with a
mean of 11.26 m, a median of 10.63 m, a 25th percentile of 8.22 m, and a 95th percentile of 17.70 m.
Treat it as an ML-derived estimate, not a survey measurement.

### The Country Codes Are Not ISO 3166-1

The partition key is Microsoft's own code list, published as
[AlphaCodeToRegionName.tsv](https://raw.githubusercontent.com/microsoft/RoadDetections/main/AlphaCodeToRegionName.tsv).
It is close to ISO 3166-1 alpha-3 and diverges in ways that break a naive join:

| Code  | Microsoft's meaning | Why it matters                                                            |
| ----- | ------------------- | ------------------------------------------------------------------------- |
| `XKS` | Kosovo              | ISO assigns no alpha-3                                                    |
| `XSA` | Saba                | Carved out of ISO `BES`                                                   |
| `XSE` | Sint Eustatius      | Carved out of ISO `BES`                                                   |
| `XXG` | Gaza Strip          | Carved out of `PSE`                                                       |
| `XXH` | Golan Heights       | Disputed                                                                  |
| `XXW` | West Bank           | Carved out of `PSE`                                                       |
| `BES` | **Bonaire alone**   | ISO 3166-1 assigns `BES` to Bonaire, Sint Eustatius **and** Saba together |

`BES` is the dangerous one. Joining this data to an ISO gazetteer on `BES` silently double-counts
Saba and Sint Eustatius, which appear here separately as `XSA` and `XSE`.

There is also a live bug in Microsoft's manifest. Åland appears in the data as `ALA`, the correct
ISO code, but `AlphaCodeToRegionName.tsv` on `main` still lists the old `ALI`. Microsoft's maintainer
confirmed the data-side correction in
[issue #17](https://github.com/microsoft/RoadDetections/issues/17); the manifest was not updated.
A join against the manifest drops Åland.

## Partitioning

235 GeoParquet files in Hive-style directories, `by_country/country=<CODE>/<CODE>.parquet`. The
partition key is declared in `collection.json` as `partition:keys`, and `partition:glob` is the
bulk-access path.

Files run from 5 KB (Pitcairn, 12 roads) to 2.1 GB (United States, 62,440,047 roads). Rows are
Hilbert-ordered and every file carries a GeoParquet 1.1 `bbox` covering column with per-row-group
statistics, so a bounding-box filter skips row groups instead of scanning. Row groups hold at most
100,000 rows.

## Limitations

- **Machine detections, not an authoritative road network.** Microsoft reports at least 95% precision
  after filtering, which still leaves false positives. There is no per-record confidence score.
- **The relationship to OpenStreetMap is unclear.** Microsoft's pipeline lists a conflation stage
  that excludes "roads and parts of roads that already exist in the road network (OSM)", but the
  published release is plainly not restricted to roads missing from OSM. Central Berlin, mapped
  exhaustively in OSM for over a decade, holds 2,589 segments in a 0.06 by 0.03 degree window.
  Microsoft's 2022 blog post also quotes two separate figures, "47.8M km of all roads and 1.16M km of
  missing roads from Open Street Map (OSM)", and the 54.2M km published here is of the former scale
  rather than the latter. Treat this as all detections,
  not as an OSM difference layer. How the conflation stage relates to the released files is not
  documented upstream.
- **No road classification in this data.** Microsoft's pipeline predicts road type, but the published
  files carry only geometry and width.
- **No dates.** Vintage follows the imagery and is not recorded per record.
- **No China, Japan, or Korea**, plus parts of Switzerland and the United Kingdom.
- **Widths are estimates** of undocumented derivation.

## Access

Total road length, one country:

```sql
INSTALL spatial; LOAD spatial; INSTALL httpfs; LOAD httpfs;

SELECT count(*) AS segments
FROM read_parquet(
  'https://data.source.coop/nlebovits/microsoft-ml-road-detections/'
  || 'road-detections/by_country/country=URY/URY.parquet'
);
-- 263971
```

A bounding-box query that uses the covering column, so it reads a few row groups rather than a whole
file:

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

More recipes, including the whole-planet glob and the traps that produce wrong answers, are in
[AGENTS.md](https://source.coop/nlebovits/microsoft-ml-road-detections/road-detections/AGENTS.md).

## Derived Figures

Every measured number in this document was computed from the published files. The total road length
of 54,225,233 km was obtained by summing great-circle segment distances over all 959,867,152
vertices, using a mean-latitude equirectangular approximation on a sphere of radius 6,371,008.8 m.
That is within roughly 0.5% of a true WGS84 geodesic.

The figure is worth stating because it matches Microsoft's own claim of "54.2M km of roads
worldwide", which is the strongest available evidence that this mirror is complete and that nothing
was lost in conversion.

The method was validated against an independent Vincenty implementation, which agreed to within 0.2%
on sampled geometries. It is computed from WKB directly rather than with DuckDB's
`ST_Length_Spheroid`, which is wrong on this data in both DuckDB 1.4.1 and 1.5.5: it returns `NaN`
for some countries and silently wrong finite values for others. [AGENTS.md](https://source.coop/nlebovits/microsoft-ml-road-detections/road-detections/AGENTS.md) carries the
query and the evidence.

## License

`ODbL-1.0`, the [Open Data Commons Open Database License](https://opendatacommons.org/licenses/odbl/).
Microsoft's [LICENSE file](https://github.com/microsoft/RoadDetections/blob/main/LICENSE) reads in
full:

> Data in this repository has been licensed by Microsoft under the Open Data Commons Open Database
> License (ODbL).

ODbL is share-alike, so a Derivative Database you publish must also be ODbL. Microsoft specifies no
attribution wording; ODbL section 4.3 still requires a notice. This works:

> Contains road detections from Microsoft, mined from Bing Maps imagery, licensed under ODbL.

Microsoft's terms do not grant rights to its names, logos, or trademarks.

One caveat if you check programmatically: GitHub reports this repository's license as
`NOASSERTION`, because Microsoft's LICENSE file is a one-line pointer rather than the ODbL text. The
SPDX identifier `ODbL-1.0` is still the correct tag, and it is what this collection declares.

## Provenance

| Role               | Who                                   |
| ------------------ | ------------------------------------- |
| Producer, licensor | Microsoft                             |
| Processor          | Nissim Lebovits                       |
| Host               | Radiant Earth, via Source Cooperative |

Upstream: [microsoft/RoadDetections](https://github.com/microsoft/RoadDetections), drop `2025.04.28`.
Microsoft distributes nineteen zipped TSV files of GeoJSON, one per UN subregion, about 67 GB
unpacked. Those files are not archived here as a `source` asset, because they are per-region and this
collection is per-country, so no upstream file corresponds to any partition. The `via` link points at
the source instead.

Microsoft publishes no STAC catalog, so this collection carries no `canonical` link.
