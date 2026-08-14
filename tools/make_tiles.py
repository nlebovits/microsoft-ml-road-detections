#!/usr/bin/env python3
"""Build the PMTiles overview archive from the staged GeoParquet partitions.

Two stages. First every partition is written out as GeoJSON text sequence,
grouped into one file per UN subregion so tippecanoe can read them in
parallel. Then tippecanoe builds a single global archive.

The intermediate is roughly 45 GB, which is why it is grouped rather than
written per country, and why `--keep-intermediate` is off by default.

Only `width_meters` is carried into the tiles. `geometry_type` is constant, and
`country` would add about 6 GB to the intermediate and compete for room inside
tiles that are already being thinned at low zoom. Filtering by country is a
GeoParquet operation, not a tile one.

    python3 tools/make_tiles.py --stage geojson
    python3 tools/make_tiles.py --stage tiles
    python3 tools/make_tiles.py                  both, then clean up
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = ROOT.parent / "output" / "by_region"
STAGING = ROOT / "staging" / "road-detections"
INTERMEDIATE = ROOT / "staging" / "tiles-src"
OUTPUT = STAGING / "road-detections.pmtiles"

LAYER = "road-detections"
MAX_ZOOM = 10
MIN_ZOOM = 0
SIMPLIFICATION = 10
COORD_PRECISION = 6  # About 11 cm at the equator, far finer than zoom 10 needs.


def region_of(path: Path) -> str:
    """The UN subregion a staged partition came from, via the source tree."""
    iso3 = path.parent.name.split("=", 1)[1]
    for region in sorted(SOURCE_ROOT.iterdir()):
        if (region / "by_country" / f"country={iso3}").is_dir():
            return region.name
    return "other"


def partitions() -> list[Path]:
    root = STAGING / "by_country"
    out = []
    for part in sorted(root.iterdir()):
        if part.name.startswith("country="):
            out.extend(sorted(part.glob("*.parquet")))
    return out


def features(path: Path):
    """Yield GeoJSON Feature lines, parsing WKB coordinates with numpy.

    Going through the Arrow buffers directly avoids building 256 million
    shapely objects. Every record is a little-endian WKB LineString with a
    nine-byte header, so the coordinate block for record i runs from
    offset[i] + 9 to offset[i + 1].
    """
    parquet = pq.ParquetFile(path)
    fmt = f"%.{COORD_PRECISION}f"
    for batch in parquet.iter_batches(batch_size=100_000, columns=["geometry", "width_meters"]):
        wkb = batch.column("geometry")
        offsets = np.frombuffer(wkb.buffers()[1], dtype=np.int32)
        offsets = offsets[: len(wkb) + 1].astype(np.int64)
        data = np.frombuffer(wkb.buffers()[2], dtype=np.uint8)
        base = offsets[0]

        n_points = (offsets[1:] - offsets[:-1] - 9) // 16
        keep = np.ones(offsets[-1] - base, dtype=bool)
        keep[((offsets[:-1] - base)[:, None] + np.arange(9)).ravel()] = False
        coords = data[base : offsets[-1]][keep].view(np.float64).reshape(-1, 2)

        widths = batch.column("width_meters").to_numpy(zero_copy_only=False)
        bounds = np.concatenate([[0], np.cumsum(n_points)])
        rounded = np.round(coords, COORD_PRECISION)

        for i in range(len(wkb)):
            block = rounded[bounds[i] : bounds[i + 1]]
            pairs = ",".join(
                "[%s,%s]" % (fmt % x, fmt % y) for x, y in block
            )
            yield (
                '{"type":"Feature","properties":{"width_meters":%.2f},'
                '"geometry":{"type":"LineString","coordinates":[%s]}}\n'
                % (widths[i], pairs)
            )


def stage_geojson() -> int:
    INTERMEDIATE.mkdir(parents=True, exist_ok=True)
    files = partitions()
    if not files:
        print(f"no partitions under {STAGING / 'by_country'}; run reencode.py first")
        return 1

    grouped: dict[str, list[Path]] = {}
    for path in files:
        grouped.setdefault(region_of(path), []).append(path)

    print(f"writing {len(files)} partitions into {len(grouped)} regional files")
    started = time.time()
    total_rows = 0
    for region, paths in sorted(grouped.items()):
        target = INTERMEDIATE / f"{region}.geojsonl"
        rows = 0
        with target.open("w") as handle:
            for path in paths:
                for line in features(path):
                    handle.write(line)
                    rows += 1
        total_rows += rows
        size = target.stat().st_size
        print(f"  {region:<24} {rows:>12,} features  {size / 1e9:6.2f} GB")
    elapsed = time.time() - started
    print(f"\n{total_rows:,} features in {elapsed / 60:.1f} min")
    print(f"intermediate total: {sum(p.stat().st_size for p in INTERMEDIATE.glob('*.geojsonl')) / 1e9:.1f} GB")
    return 0


def stage_tiles() -> int:
    inputs = sorted(INTERMEDIATE.glob("*.geojsonl"))
    if not inputs:
        print(f"no input under {INTERMEDIATE}; run --stage geojson first")
        return 1
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "tippecanoe",
        "-o", str(OUTPUT),
        "--force",
        "--read-parallel",  # The inputs are newline-delimited and seekable.
        "--layer", LAYER,
        "--minimum-zoom", str(MIN_ZOOM),
        "--maximum-zoom", str(MAX_ZOOM),
        "--drop-densest-as-needed",
        "--simplification", str(SIMPLIFICATION),
        "--no-tile-stats",
        *[str(p) for p in inputs],
    ]
    print(" ".join(command[:14]), f"... {len(inputs)} input files")
    started = time.time()
    result = subprocess.run(command)
    if result.returncode != 0:
        print(f"tippecanoe failed with exit code {result.returncode}")
        return result.returncode
    print(f"\nbuilt {OUTPUT.name} in {(time.time() - started) / 60:.1f} min")
    print(f"  size {OUTPUT.stat().st_size / 1e9:.2f} GB")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["geojson", "tiles"], help="run one stage only")
    parser.add_argument(
        "--keep-intermediate",
        action="store_true",
        help="leave staging/tiles-src in place after tiling",
    )
    args = parser.parse_args()

    if shutil.which("tippecanoe") is None and args.stage != "geojson":
        print("tippecanoe is not on PATH")
        return 1

    if args.stage == "geojson":
        return stage_geojson()
    if args.stage == "tiles":
        return stage_tiles()

    if (code := stage_geojson()) != 0:
        return code
    if (code := stage_tiles()) != 0:
        return code
    if not args.keep_intermediate:
        shutil.rmtree(INTERMEDIATE)
        print(f"removed {INTERMEDIATE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
