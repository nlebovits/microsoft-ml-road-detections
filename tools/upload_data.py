#!/usr/bin/env python3
"""Upload the data assets that live outside the published catalog directory.

`tools/publish.py` syncs `catalog/` and nothing else, which is what keeps a
scratch file from reaching a public bucket. The GeoParquet partitions and the
PMTiles archive are far too large for git, so they live in `staging/` and are
uploaded by this script instead. Both write into the same bucket prefix, and
between them they produce the published tree.

Change detection, content types, and the sentinel guard are reused from
publish.py rather than reimplemented, so the two paths cannot drift.

Like publish.py, this never deletes. Removing a file from `staging/` leaves the
object in the bucket.

    AWS_PROFILE=source-coop python3 tools/upload_data.py             # dry run
    AWS_PROFILE=source-coop python3 tools/upload_data.py --confirm   # upload
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from publish import (  # noqa: E402
    ROOT,
    Upload,
    content_type_for,
    is_unchanged,
    load_config,
    remote_index,
    split_s3_uri,
    unedited_sentinels,
)

STAGING = ROOT / "staging"

# Only this subtree uploads. `staging/` also holds build scratch, and
# `staging/tiles-src` alone is 45 GB of GeoJSON that tippecanoe consumes and
# nobody should ever download. Publishing is opt-in by path, then again by
# extension, for the same reason publish.py refuses to widen publish_dir: a
# boundary that lists what may pass is safe against new scratch appearing, and
# one that lists exclusions is not.
DATA_DIR = STAGING / "road-detections"
PUBLISHABLE_SUFFIXES = {".parquet", ".pmtiles"}


def collect(config: dict[str, str]) -> list[Upload]:
    """Every publishable file under staging/road-detections/."""
    if not DATA_DIR.is_dir():
        return []
    _, prefix = split_s3_uri(config["write_prefix"])
    uploads = []
    for path in sorted(DATA_DIR.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(STAGING)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if path.suffix not in PUBLISHABLE_SUFFIXES:
            continue
        key = f"{prefix.rstrip('/')}/{rel.as_posix()}"
        uploads.append(Upload(path, key, content_type_for(path)))
    return uploads


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} GB"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true", help="actually upload")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--force",
        action="store_true",
        help="skip the remote listing and re-upload everything",
    )
    args = parser.parse_args()

    config = load_config()
    if stale := unedited_sentinels(config):
        print(f"refusing to upload: catalog.publish.yaml still holds {', '.join(stale)}")
        return 1

    bucket, prefix = split_s3_uri(config["write_prefix"])
    uploads = collect(config)
    if not uploads:
        print(f"nothing to upload: {DATA_DIR} is empty or missing")
        return 0

    index = {} if args.force else remote_index(bucket, prefix)
    changed = [u for u in uploads if args.force or not is_unchanged(u, index)]
    skipped = len(uploads) - len(changed)
    total = sum(u.local.stat().st_size for u in changed)

    print(f"staging:  {DATA_DIR}")
    print(f"target:   s3://{bucket}/{prefix}")
    print(f"files:    {len(uploads)} found, {skipped} already current, {len(changed)} to upload")
    print(f"bytes:    {human(total)}")

    if not changed:
        print("\neverything is already published")
        return 0

    by_suffix: dict[str, int] = {}
    for u in changed:
        by_suffix[u.local.suffix] = by_suffix.get(u.local.suffix, 0) + 1
    print("breakdown:", ", ".join(f"{n}x {s}" for s, n in sorted(by_suffix.items())))

    if not args.confirm:
        print("\ndry run. re-run with --confirm to upload.")
        for u in changed[:10]:
            print(f"  would upload {u.key}")
        if len(changed) > 10:
            print(f"  ... and {len(changed) - 10} more")
        return 0

    import boto3

    client = boto3.client("s3")

    def put(upload: Upload) -> tuple[str, str | None]:
        try:
            client.upload_file(
                str(upload.local),
                bucket,
                upload.key,
                ExtraArgs={"ContentType": upload.content_type},
            )
            return upload.key, None
        except Exception as exc:  # noqa: BLE001 - reported per file, run continues
            return upload.key, repr(exc)

    done = 0
    failures = []
    with cf.ThreadPoolExecutor(args.workers) as pool:
        for key, error in pool.map(put, changed):
            done += 1
            if error:
                failures.append((key, error))
                print(f"  [{done}/{len(changed)}] FAILED {key}: {error}")
            elif done % 20 == 0 or done == len(changed):
                print(f"  [{done}/{len(changed)}] uploaded")

    if failures:
        print(f"\n{len(failures)} uploads failed; re-run to retry")
        return 1
    print(f"\nuploaded {len(changed)} files, {human(total)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
