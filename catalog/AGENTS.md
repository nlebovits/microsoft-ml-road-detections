# Agent Guide

Every claim in this file is quoted from a source, cited to one, or measured from the data. If a fact
here has no traceable origin, it does not belong in this file.

## What This Catalog Holds

One collection, `road-detections`: 256,555,010 road segments that Microsoft detected from Bing Maps
aerial imagery, as GeoParquet partitioned into 235 country files, about 12 GB in total.

This is a **mirror**. Microsoft produces the data; this catalog reformats and hosts it. Producer and
host differ in `providers`, which is how Portolan derives mirror status. The `via` link on both the
catalog and the collection points at
[microsoft/RoadDetections](https://github.com/microsoft/RoadDetections). There is no `canonical`
link because Microsoft publishes no STAC catalog.

## How To Read It

Start at `catalog.json`, follow the `child` link to `road-detections/collection.json`, and read
`partition:glob` from it. That is the bulk-access path.

```
https://data.source.coop/nlebovits/microsoft-ml-road-detections/road-detections/by_country/country=*/*.parquet
```

**There is no collection-level `data` asset.** A partitioned collection declares its access path
through `partition:glob` rather than through an asset, so code that looks for `assets.data` will
find nothing and should not conclude the collection is empty. The assets that do exist are the
PMTiles (`visual`), three styles, a legend, and a thumbnail.

`collection.json` also carries the full schema in `table:columns`, with a description per column, so
the column semantics can be read without touching a Parquet footer.

## Two Hostnames, Two Purposes

Source Cooperative serves the same objects under two names, and they behave differently.

- `source.coop` renders a page a person reads. Use it for links in prose.
- `data.source.coop` returns raw bytes. Use it for asset hrefs, `curl`, and `read_parquet`.

Opening a `data.source.coop` link in a browser gives unformatted JSON. Fetching a `source.coop` URL
programmatically gives HTML.

## Where The Detail Lives

This catalog holds one dataset, so the substance is one level down. Before querying, read
[road-detections/AGENTS.md](road-detections/AGENTS.md). It carries tested queries with their answers
inlined, and four traps that produce confident wrong answers:

- the `country` column is not ISO 3166-1 alpha-3, and `BES` in particular means something narrower
  than ISO says it does;
- DuckDB's `ST_Length_Spheroid` is wrong on this data in 1.4.1 and 1.5.5, sometimes returning `NaN`
  and sometimes a plausible but incorrect number;
- coverage excludes mainland China, Japan, and Korea by design;
- this is not an OpenStreetMap difference layer, despite a pipeline stage that reads like one.

## Join Keys

There is one collection, so there is nothing to join within this catalog. Joining outward, the only
candidate key is `country`, and it is the trap above: it is Microsoft's code list, not ISO 3166-1.
Reconcile `XKS`, `XSA`, `XSE`, `XXG`, `XXH`, `XXW`, and especially `BES` before joining to any
gazetteer.

## Structure

Catalogs here carry no `self` link, because a static catalog has to survive being mirrored or moved,
so a client tracks its own location. Structural links are relative. The `vcs` and `issues` links on
`catalog.json` are absolute, because the repository sits outside the published catalog.
