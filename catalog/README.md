# Microsoft ML Road Detections

A cloud-native mirror of the road detections Microsoft mines from Bing Maps aerial imagery.

Microsoft publishes this data at [microsoft/RoadDetections](https://github.com/microsoft/RoadDetections)
as nineteen zipped TSV files of GeoJSON, one per UN subregion, totalling about 67 GB unpacked. That
format is fine for a bulk download and useless for a query. This catalog carries the same roads as
GeoParquet partitioned by country, so a reader can pull one country, one bounding box, or the whole
planet without unpacking anything.

One collection:

| Collection | What it holds |
|---|---|
| [road-detections](https://source.coop/nlebovits/microsoft-ml-road-detections/road-detections/README.md) | 256,555,010 road segments in 235 country partitions, worldwide |

## Provenance

**This is a mirror, not the source.** Microsoft produces the data. This catalog reformats and hosts
it, and adds nothing to it. Geometries, widths, and country assignments are exactly as Microsoft
published them.

Upstream drop: `2025.04.28`, the current release as of 2026-08-14. Roads were converted to
GeoParquet in October 2025. If Microsoft publishes a newer drop, this mirror will lag it until it is
re-synced; the `updated` field on the catalog and the collection records the last sync.

For what the detections are, how they were produced, what they do not cover, and the traps in the
country codes, read the [collection README](https://source.coop/nlebovits/microsoft-ml-road-detections/road-detections/README.md).

## License

`ODbL-1.0`, the [Open Data Commons Open Database License](https://opendatacommons.org/licenses/odbl/).

Microsoft's [LICENSE file](https://github.com/microsoft/RoadDetections/blob/main/LICENSE) reads in
full:

> Data in this repository has been licensed by Microsoft under the Open Data Commons Open Database
> License (ODbL).

ODbL is share-alike. A Derivative Database you publish has to be offered under ODbL as well, and
this mirror is. Microsoft states no required attribution wording, so ODbL section 4.3 obliges you to
supply one. This works:

> Contains road detections from Microsoft, mined from Bing Maps imagery, licensed under ODbL.

Microsoft's terms do not grant rights to its names, logos, or trademarks, which is why no Microsoft
branding appears anywhere in this catalog.

## Access

Every partition, read as one table:

```sql
INSTALL spatial; LOAD spatial; INSTALL httpfs; LOAD httpfs;

-- The glob needs s3://, because expanding it requires a listing and plain HTTP
-- cannot list. The bucket reads anonymously; path style is required because the
-- bucket name contains dots.
CREATE OR REPLACE SECRET source_coop (
  TYPE s3, PROVIDER config, KEY_ID '', SECRET '',
  REGION 'us-west-2', URL_STYLE 'path',
  ENDPOINT 's3.us-west-2.amazonaws.com'
);

SELECT count(*)
FROM read_parquet(
  's3://us-west-2.opendata.source.coop/nlebovits/microsoft-ml-road-detections/'
  || 'road-detections/by_country/country=*/*.parquet'
);
-- 256555010
```

One country, which reads one file instead of 235:

```sql
SELECT width_meters, geometry
FROM read_parquet(
  'https://data.source.coop/nlebovits/microsoft-ml-road-detections/'
  || 'road-detections/by_country/country=NLD/NLD.parquet'
)
LIMIT 10;
```

Agents should start at [AGENTS.md](https://source.coop/nlebovits/microsoft-ml-road-detections/AGENTS.md), which carries the tested query recipes, the join
keys, and the quirks that otherwise produce confident wrong answers.

## Maintenance

Catalog metadata lives in
[nlebovits/microsoft-ml-road-detections](https://github.com/nlebovits/microsoft-ml-road-detections)
and is validated on every pull request. Corrections are welcome as
[issues](https://github.com/nlebovits/microsoft-ml-road-detections/issues) or pull requests. Problems
with the road data itself belong upstream, at
[microsoft/RoadDetections](https://github.com/microsoft/RoadDetections/issues).

Contact: nissim.lebovits@radiant.earth
