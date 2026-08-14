#!/usr/bin/env python3
"""Generate catalog/road-detections/collection.json.

The prose lives in this file and is hand-written. Everything a machine can
measure is measured: the spatial extent, the row count, the partition file
count, and the size and checksum of every asset. Those have to be generated
rather than typed, because Rashid treats a stale `file:checksum` as a
conformance failure, not a warning, and they change every time an asset is
rebuilt.

    python3 tools/build_collection.py            write collection.json
    python3 tools/build_collection.py --check    exit 1 if it is stale

Assets that do not exist yet are skipped with a note, so this runs before the
tiles and the thumbnail are built.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import struct
import sys
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
STAGING = ROOT / "staging" / "road-detections"
COLLECTION_DIR = ROOT / "catalog" / "road-detections"
OUTPUT = COLLECTION_DIR / "collection.json"

PUBLIC_BASE = "https://data.source.coop/nlebovits/microsoft-ml-road-detections"
PMTILES_NAME = "road-detections.pmtiles"

# --------------------------------------------------------------------------
# Prose. Every sentence here is quoted from Microsoft, cited to a source, or
# measured from the data. See catalog/road-detections/README.md for the
# citations behind each claim.
# --------------------------------------------------------------------------

TITLE = "Microsoft ML Road Detections"

DESCRIPTION = (
    "Road geometries that Microsoft detected from Bing Maps aerial imagery with a "
    "convolutional neural network, republished as country-partitioned GeoParquet. "
    "Microsoft states it has detected 54.2M km of roads worldwide and distributes them "
    "as nineteen zipped TSV files of GeoJSON at "
    "[microsoft/RoadDetections](https://github.com/microsoft/RoadDetections); this "
    "collection carries the same roads in a form a query engine can read directly. "
    "Each row is one road segment with an approximate width in metres. "
    "Coverage is worldwide except mainland China, Japan, and Korea, which Microsoft "
    "does not process, citing aerial imagery restrictions. "
    "Read every partition at once with the glob "
    "`https://data.source.coop/nlebovits/microsoft-ml-road-detections/road-detections/by_country/country=*/*.parquet`, "
    "or one country by naming its directory. "
    "The partition key is Microsoft's own region code, which is close to but not the "
    "same as ISO 3166-1 alpha-3; see [AGENTS.md](AGENTS.md) before joining on it."
)

KEYWORDS = [
    "roads",
    "transportation",
    "road network",
    "machine learning",
    "remote sensing",
    "bing maps",
    "global",
]

PROVIDERS = [
    {
        "name": "Microsoft",
        "description": (
            "Detected the roads from Bing Maps aerial imagery and publishes the "
            "source dataset under ODbL."
        ),
        "url": "https://github.com/microsoft/RoadDetections",
        "roles": ["producer", "licensor"],
    },
    {
        "name": "Nissim Lebovits",
        "description": (
            "Converted the source TSV/GeoJSON releases to partitioned GeoParquet "
            "and maintains this catalog."
        ),
        "email": "nissim.lebovits@radiant.earth",
        "roles": ["processor"],
    },
    {
        "name": "Radiant Earth",
        "description": "Publishes and hosts this cloud-native mirror through Source Cooperative.",
        "url": "https://radiant.earth",
        "email": "nissim.lebovits@radiant.earth",
        "roles": ["host"],
    },
]

COLUMN_DESCRIPTIONS = {
    "country": (
        "Microsoft's region code for the partition. Mostly ISO 3166-1 alpha-3, but "
        "not reliably so: XKS is Kosovo, XSA is Saba, XSE is Sint Eustatius, XXG is "
        "the Gaza Strip, XXH is the Golan Heights, and XXW is the West Bank. BES here "
        "means Bonaire alone, where ISO 3166-1 assigns BES to Bonaire, Sint Eustatius "
        "and Saba together. Codes are defined in Microsoft's AlphaCodeToRegionName.tsv."
    ),
    "width_meters": (
        "Microsoft calls this WidthMeters and documents it only as 'approximate width "
        "of the road in meters'. How it is derived is not documented upstream. Observed "
        "range is 0.04 to 119.28 m, with a median of 10.44 m."
    ),
    "geometry_type": (
        "Constant 'LineString' in all 256,555,010 rows. Redundant with the GeoParquet "
        "geometry metadata and retained only because the original conversion wrote it. "
        "Note the value is mixed case, not 'LINESTRING'."
    ),
    "geometry": (
        "The road geometry, WKB LineString in OGC:CRS84. Microsoft does not state "
        "whether these are road centrelines, so this catalog does not claim they are."
    ),
    "bbox": (
        "GeoParquet 1.1 covering column. Filter on bbox.xmin/ymin/xmax/ymax before "
        "touching geometry; it is what makes a spatial query skip row groups."
    ),
}

PARTITION_KEY_DESCRIPTION = (
    "Microsoft region code, one GeoParquet file per code. Hive-style directory "
    "naming, so a query engine can prune on it without reading any footers."
)

# --------------------------------------------------------------------------


def multihash(path: Path) -> str:
    """sha2-256 as a multihash: 0x12 for the function, 0x20 for the length."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return "1220" + digest.hexdigest()


def file_fields(path: Path) -> dict:
    return {"file:size": path.stat().st_size, "file:checksum": multihash(path)}


def partitions() -> list[Path]:
    root = STAGING / "by_country"
    if not root.is_dir():
        return []
    out = []
    for part in sorted(root.iterdir()):
        if part.name.startswith("country="):
            out.extend(sorted(part.glob("*.parquet")))
    return out


def scan_partitions(files: list[Path]) -> dict:
    """Row count, spatial extent, and the Arrow schema, from footers only."""
    rows = 0
    minx = miny = float("inf")
    maxx = maxy = float("-inf")
    schema = None
    for path in files:
        parquet = pq.ParquetFile(path)
        rows += parquet.metadata.num_rows
        if schema is None:
            schema = parquet.schema_arrow
        geo = json.loads(parquet.metadata.metadata[b"geo"])
        bbox = geo["columns"][geo["primary_column"]]["bbox"]
        minx, miny = min(minx, bbox[0]), min(miny, bbox[1])
        maxx, maxy = max(maxx, bbox[2]), max(maxy, bbox[3])
    return {
        "rows": rows,
        "bbox": [minx, miny, maxx, maxy],
        "schema": schema,
        "file_count": len(files),
    }


def table_columns(schema) -> list[dict]:
    out = []
    for field in schema:
        entry = {"name": field.name, "type": str(field.type)}
        if field.name in COLUMN_DESCRIPTIONS:
            entry["description"] = COLUMN_DESCRIPTIONS[field.name]
        out.append(entry)
    return out


class NotReady(Exception):
    """The archive exists but is still being written."""


def pmtiles_header(path: Path) -> dict:
    """Zoom range and vector layer names, read from the PMTiles v3 header.

    tippecanoe creates the output file early and writes its header last, so an
    existence check is not enough to know the archive is usable.
    """
    with path.open("rb") as handle:
        head = handle.read(127)
        if head[:7] != b"PMTiles":
            raise NotReady(f"{path.name} has no PMTiles header yet")
        meta_offset, meta_length = struct.unpack_from("<QQ", head, 24)
        internal_compression = head[97]
        min_zoom, max_zoom = head[100], head[101]
        handle.seek(meta_offset)
        blob = handle.read(meta_length)
    if internal_compression == 2:
        blob = gzip.decompress(blob)
    meta = json.loads(blob)
    layers = [layer["id"] for layer in meta.get("vector_layers", [])]
    return {"min_zoom": min_zoom, "max_zoom": max_zoom, "layers": layers}


def style_assets(notes: list[str]) -> dict:
    """Every styles/*.json, with default.json carrying the default role."""
    styles_dir = COLLECTION_DIR / "styles"
    if not styles_dir.is_dir():
        notes.append("no styles/ directory yet; style assets omitted")
        return {}
    assets = {}
    for path in sorted(styles_dir.glob("*.json")):
        stem = path.stem
        doc = json.loads(path.read_text())
        roles = ["style", "default"] if stem == "default" else ["style"]
        key = "style" if stem == "default" else f"style-{stem}"
        asset = {
            "href": f"./styles/{path.name}",
            "type": "application/vnd.mapbox.style+json",
            "title": doc.get("name", stem),
            "roles": roles,
            **file_fields(path),
        }
        if doc.get("description"):
            asset["description"] = doc["description"]
        assets[key] = asset
    return assets


def build() -> tuple[dict, list[str]]:
    notes: list[str] = []
    files = partitions()
    if not files:
        raise SystemExit(f"no partitions found under {STAGING / 'by_country'}")
    scan = scan_partitions(files)

    assets: dict = {}

    pmtiles = STAGING / PMTILES_NAME
    pmtiles_link = None
    extensions = [
        "https://schemas.portolan-sdi.org/portolan/v0.1.0/schema.json",
        "https://schemas.portolan-sdi.org/incubating/partition/v1.0.0/schema.json",
        "https://stac-extensions.github.io/table/v1.2.0/schema.json",
        "https://stac-extensions.github.io/file/v2.1.0/schema.json",
    ]
    if not pmtiles.exists():
        header = None
        notes.append(f"{pmtiles.name} not built yet; visual asset and pmtiles link omitted")
    else:
        try:
            header = pmtiles_header(pmtiles)
        except NotReady as exc:
            header = None
            notes.append(f"{exc}; visual asset and pmtiles link omitted")
    if header:
        extensions.insert(
            2, "https://stac-extensions.github.io/web-map-links/v1.3.0/schema.json"
        )
        href = f"{PUBLIC_BASE}/road-detections/{PMTILES_NAME}"
        assets["visual"] = {
            "href": href,
            "type": "application/vnd.pmtiles",
            "title": "Vector tiles, zoom 0 to %d" % header["max_zoom"],
            "description": (
                "Overview tiles for browsing. Built at zoom %d to %d with feature "
                "dropping, so they are not a substitute for the GeoParquet at street "
                "level." % (header["min_zoom"], header["max_zoom"])
            ),
            "roles": ["visual"],
            **file_fields(pmtiles),
        }
        pmtiles_link = {
            "rel": "pmtiles",
            "href": href,
            "type": "application/vnd.pmtiles",
            "title": "Vector tiles",
            "pmtiles:layers": header["layers"],
        }

    assets.update(style_assets(notes))

    legend = COLLECTION_DIR / "legends" / "width.png"
    if legend.exists():
        assets["legend"] = {
            "href": "./legends/width.png",
            "type": "image/png",
            "title": "Road width classes",
            "roles": ["legend"],
            **file_fields(legend),
        }
    else:
        notes.append("legends/width.png not built yet; legend asset omitted")

    thumbnail = COLLECTION_DIR / "thumbnail.png"
    if thumbnail.exists():
        assets["thumbnail"] = {
            "href": "./thumbnail.png",
            "type": "image/png",
            "title": "Preview rendered with the default style. © OpenStreetMap contributors © CARTO.",
            "roles": ["thumbnail"],
            **file_fields(thumbnail),
        }
    else:
        notes.append("thumbnail.png not built yet; thumbnail asset omitted")

    links = [
        {"rel": "root", "href": "../catalog.json", "type": "application/json"},
        {"rel": "parent", "href": "../catalog.json", "type": "application/json"},
        {
            "rel": "describedby",
            "href": "./README.md",
            "type": "text/markdown",
            "title": "Collection README",
        },
        {
            "rel": "agents",
            "href": "./AGENTS.md",
            "type": "text/markdown",
            "title": "Collection agent guide",
        },
        {
            "rel": "license",
            "href": "https://opendatacommons.org/licenses/odbl/",
            "type": "text/html",
            "title": "Open Data Commons Open Database License (ODbL) v1.0",
        },
        {
            "rel": "via",
            "href": "https://github.com/microsoft/RoadDetections",
            "type": "text/html",
            "title": "microsoft/RoadDetections, the upstream source",
        },
    ]
    if pmtiles_link:
        links.append(pmtiles_link)

    collection = {
        "type": "Collection",
        "stac_version": "1.1.0",
        "stac_extensions": extensions,
        "id": "road-detections",
        "title": TITLE,
        "description": DESCRIPTION,
        "license": "ODbL-1.0",
        "keywords": KEYWORDS,
        "updated": "2026-08-14T00:00:00Z",
        "providers": PROVIDERS,
        "extent": {
            "spatial": {"bbox": [scan["bbox"]]},
            "temporal": {"interval": [["2020-01-01T00:00:00Z", None]]},
        },
        "partition:scheme": "hive",
        "partition:strategy": "attribute",
        "partition:keys": [
            {
                "name": "country",
                "type": "string",
                "description": PARTITION_KEY_DESCRIPTION,
            }
        ],
        "partition:file_count": scan["file_count"],
        "partition:glob": (
            f"{PUBLIC_BASE}/road-detections/by_country/country=*/*.parquet"
        ),
        "table:row_count": scan["rows"],
        "table:primary_geometry": "geometry",
        "table:columns": table_columns(scan["schema"]),
        "assets": assets,
        "links": links,
    }
    return collection, notes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="exit 1 if collection.json is stale"
    )
    args = parser.parse_args()

    collection, notes = build()
    rendered = json.dumps(collection, indent=2, ensure_ascii=False) + "\n"

    if args.check:
        if not OUTPUT.exists():
            print(f"STALE: {OUTPUT} does not exist")
            return 1
        if OUTPUT.read_text() != rendered:
            print(f"STALE: {OUTPUT} does not match tools/build_collection.py")
            print("       run: python3 tools/build_collection.py")
            return 1
        print(f"current: {OUTPUT.relative_to(ROOT)}")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered)
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    print(f"  partitions   {collection['partition:file_count']}")
    print(f"  rows         {collection['table:row_count']:,}")
    print(f"  bbox         {['%.6f' % v for v in collection['extent']['spatial']['bbox'][0]]}")
    print(f"  assets       {', '.join(collection['assets']) or 'none yet'}")
    for note in notes:
        print(f"  note: {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
