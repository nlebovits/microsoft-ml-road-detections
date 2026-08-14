# Agent Guide

This repository holds the metadata for a Portolan catalog that mirrors
Microsoft's ML road detections. The data itself lives in object storage at
Source Cooperative and never enters git.

## The publish boundary

`catalog/` is the published catalog. Everything in it is published, and
nothing outside it ever is. Do not move a file into `catalog/` to make it
publish, and do not add a path outside `publish_dir` to `tools/publish.py`.
The boundary is the only thing standing between a scratch file and a public
bucket, and it holds because it is structural rather than a list of
exclusions.

## Data never enters git

Never commit a GeoParquet or PMTiles file. The 235 country partitions total
about 12 GB and the tile archive adds several more. Git keeps every version of
a binary forever and deleting it later reclaims nothing.

Two upload paths exist, and they are not interchangeable:

- `tools/publish.py` syncs `catalog/` and only `catalog/`.
- `tools/upload_data.py` uploads the GeoParquet partitions and the PMTiles
  from `staging/`, which is gitignored.

Neither deletes. Removing a file locally leaves the object in the bucket, so a
rename or a format change needs a deliberate `aws s3 rm` afterwards.

## Regenerating the data assets

`tools/reencode.py` rebuilds `staging/` from the source tree. It exists
because Rashid rule PTL-DAT-008 caps a row group at 150,000 rows and the
original conversion wrote one row group per file, up to 3,593,665 rows. Run
`--verify` after any change to it: the gate is that row count, geometry
length, country values, `geo` metadata, and schema all stay identical.

## The conformance allow-list

`ACCEPTED` in `tests/test_conformance.py` ships empty and is still empty.
Never add an entry without a matching row in `docs/conformance.md` giving the
rule, where it fires, why it is accepted, and the issue tracking its removal.

`stac-check` is advisory. It recommends a `rel: "self"` link, which Portolan
forbids because a static catalog has to survive being mirrored or moved. Do
not add one to silence the warning. Rashid is the conformance gate.

## Published documentation is hand-written

`catalog/README.md` and `catalog/**/README.md` are authored in this
repository, not generated. Do not run `portolan readme` over them; it would
overwrite them from `.portolan/metadata.yaml`, which this catalog does not
use. The repository is the source of truth.

Every claim in a `catalog/**/AGENTS.md` or `README.md` is quoted from a
source, cited to one, or measured from the data. An invented join key or
column name produces a confident wrong answer that nothing downstream
catches. Where a fact could not be established, the documentation says so
rather than guessing.

## How this catalog points back at this repository

[portolan-spec#145](https://github.com/portolan-sdi/portolan-spec/issues/145)
is open and the template ships nothing. This catalog uses absolute `vcs` and
`issues` links on the root `catalog.json`, following the `git-backed-catalog`
skill. They are absolute because the repository sits outside the published
catalog, so a relative href would resolve against the bucket. Rashid does not
require either link, so this is a convention rather than conformance. If
spec#145 settles on a different encoding, change it here.
