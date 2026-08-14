#!/usr/bin/env python3
"""Only data assets can be uploaded, and only from the data directory.

tools/upload_data.py is the second upload path, and it needs its own boundary
for the same reason publish.py has one. An earlier version walked all of
`staging/` and would have published 45 GB of GeoJSON scratch that tippecanoe
had already consumed. This asserts the boundary it has now: opt in by path,
then again by extension.

Runs against a temporary tree, so it needs no real staging directory and no
credentials.

Run: python3 tests/test_upload_data.py
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import upload_data  # noqa: E402

CONFIG = {
    "write_prefix": "s3://example-bucket/org/product",
    "public_base": "https://data.example.org/org/product",
    "publish_dir": "catalog",
}

FIXTURE = [
    # (path relative to staging/, should it publish)
    ("road-detections/by_country/country=USA/USA.parquet", True),
    ("road-detections/by_country/country=NLD/NLD.parquet", True),
    ("road-detections/road-detections.pmtiles", True),
    # Build scratch. Enormous, already consumed, and never a distribution.
    ("tiles-src/Northern_America.geojsonl", False),
    ("tiles-src/Western_Europe.geojsonl", False),
    # Inside the data directory but not a data asset.
    ("road-detections/notes.txt", False),
    ("road-detections/build.log", False),
    ("road-detections/.hidden/scratch.parquet", False),
    # A sibling directory that is not the data directory.
    ("other/stray.parquet", False),
]

failures: list[str] = []

with tempfile.TemporaryDirectory() as tmp:
    staging = Path(tmp) / "staging"
    for rel, _ in FIXTURE:
        path = staging / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")

    upload_data.STAGING = staging
    upload_data.DATA_DIR = staging / "road-detections"

    keys = {u.local.relative_to(staging).as_posix() for u in upload_data.collect(CONFIG)}
    expected = {rel for rel, publishes in FIXTURE if publishes}

    if keys != expected:
        for rel in sorted(expected - keys):
            failures.append(f"should publish but did not: {rel}")
        for rel in sorted(keys - expected):
            failures.append(f"published but must not: {rel}")

    # Keys must land under the collection directory, not the product root.
    for upload in upload_data.collect(CONFIG):
        if not upload.key.startswith("org/product/road-detections/"):
            failures.append(f"key outside the collection directory: {upload.key}")

    # Content types have to be right, or a browser mishandles the object.
    types = {
        u.local.suffix: u.content_type for u in upload_data.collect(CONFIG)
    }
    if types.get(".parquet") != "application/vnd.apache.parquet":
        failures.append(f"wrong parquet content type: {types.get('.parquet')}")
    if types.get(".pmtiles") != "application/vnd.pmtiles":
        failures.append(f"wrong pmtiles content type: {types.get('.pmtiles')}")

if failures:
    print("\n".join(f"error  {f}" for f in failures))
    raise SystemExit(1)
print(f"OK: upload boundary holds ({len(FIXTURE)} case(s))")
