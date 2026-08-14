# microsoft-ml-road-detections

Catalog metadata for a [Portolan](https://www.portolan-sdi.org/) cloud-native mirror of
[Microsoft's ML road detections](https://github.com/microsoft/RoadDetections): 256,555,010 road
segments detected from Bing Maps aerial imagery, republished as GeoParquet partitioned into 235
country files.

Published at
[source.coop/nlebovits/microsoft-ml-road-detections](https://source.coop/nlebovits/microsoft-ml-road-detections).

This repository holds the metadata. The data lives in object storage and is never committed.

## Layout

| Path                  | What it is                                                                    |
| --------------------- | ----------------------------------------------------------------------------- |
| `catalog/`            | The published catalog. Everything in it publishes; nothing outside it does.   |
| `staging/`            | Generated data assets, gitignored. 12 GB of GeoParquet plus the tile archive. |
| `tools/`              | Build and publish scripts.                                                    |
| `tests/`              | The gates.                                                                    |
| `docs/conformance.md` | Accepted validator deviations. Empty, and meant to stay that way.             |

## Rebuilding

The source is the pre-migration conversion tree, by default
`~/Documents/dev/output/by_region`. Override with `--source`.

```bash
# 1. Re-encode into staging/. About 20 minutes across 8 workers.
python3 tools/reencode.py
python3 tools/reencode.py --verify

# 2. Build the tile archive. Hours, and about 45 GB of intermediate.
python3 tools/make_tiles.py

# 3. Regenerate the legend and the collection metadata.
python3 tools/make_legend.py
python3 tools/build_collection.py
```

`tools/build_collection.py` owns every derived number in `collection.json`: the extent, the row
count, the partition count, and the size and checksum of each asset. Do not hand-edit that file.
`--check` fails when it is stale, which is what CI runs.

`catalog/**/README.md` and `catalog/**/AGENTS.md` are the opposite: hand-written, and not generated
by anything. Do not run `portolan readme` over them.

## Validating

```bash
python3 tests/run_all.py
rashid check catalog/ --no-data
```

Rashid is the conformance gate. `stac-check` is advisory, and its `rel: "self"` recommendation is
deliberately not followed, because Portolan forbids a self link.

The full data pass reads every asset, so run it against a tree that mirrors the published layout,
or against the published URLs once the data is up.

## Publishing

Two uploads, because the catalog and the data live on different sides of the publish boundary.

```bash
export AWS_PROFILE=source-coop

python3 tools/publish.py               # dry run: the catalog
python3 tools/publish.py --confirm

python3 tools/upload_data.py           # dry run: the GeoParquet and tiles
python3 tools/upload_data.py --confirm
```

Neither deletes. Removing a file locally leaves the object in the bucket, so a rename or a format
change needs a deliberate `aws s3 rm` afterwards.

## License

Apache-2.0 covers the tooling in this repository. The road data carries its own license, ODbL, which
is stated in [catalog/README.md](catalog/README.md) along with the attribution notice it requires.
