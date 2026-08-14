# Portolan Conformance

Conformance means passing [rashid](https://github.com/portolan-sdi/rashid),
not claiming to conform, so it runs in CI:

```bash
python3 tests/test_conformance.py
```

That gate fails on any error-severity finding whose rule is not listed below.
The list starts empty and it must never grow without a row here. A known
deviation with an issue number is a debt someone can pay off. A silently
widened allow-list is a false claim about what this catalog conforms to.

## Accepted deviations

None. `ACCEPTED` in `tests/test_conformance.py` is empty and this catalog passes
rashid outright.

## What rashid does not check here

Passing rashid does not prove this catalog's GeoParquet is conformant, and it is
worth knowing why before trusting a green run.

For a partitioned collection with no `data` asset, which is the layout
`PORTO-FMT-022` prescribes once partitions run to hundreds, rashid inspects the
partitions for one thing only: that they share a Parquet schema
(`PTL-DAT-014`). Its row-group, spatial-ordering, per-row-group-statistics and
GeoParquet-version checks iterate a node's declared assets, and there is no
`data` asset to iterate.

Confirmed against rashid 0.1.5 on 2026-08-14 by planting a partition with a
1,176,571-row row group, 7.8x over the `PTL-DAT-008` cap, and getting a clean
run. Reported as [portolan-sdi/rashid#130](https://github.com/portolan-sdi/rashid/issues/130).

`tests/test_geoparquet.py` asserts those four invariants directly against the
staged partitions, so the guarantee comes from somewhere. It currently reports
235 partitions, one schema, and a largest row group of 100,000 rows. Remove that
gate only once rashid covers the same ground.

## Advisory gate

`tests/test_stac_valid.py` runs stac-check, which answers a different question:
is this valid STAC, rather than does it conform to Portolan. It is advisory, and
two of its best-practice notes are ignored on purpose. It wants a `rel: "self"`
link, which Portolan forbids so a static catalog can be mirrored or moved, and it
wants a title on every link, which is only required on `child` and `item`.

One crash is tolerated, and only one.

| What | Where | Why accepted | Tracking |
|---|---|---|---|
| stac-validator raises `AttributeError: 'list' object has no attribute 'get'` | every Portolan Collection | Validator defect, not a metadata defect. Diagnosed below. | Not yet filed |

The Portolan profile schema declares draft-07, in which `items` may be an array
of schemas. Its `valid_bbox` definition uses that form twice, once for a
four-element bbox and once for six. stac-validator ignores the declared draft
and pushes every schema through `Draft202012Validator`, where `items` must be a
single schema; `referencing` then calls `.get("$id")` on the list and raises.

Checked on 2026-08-14 against stac-check 1.14.0, the current release:

- `jsonschema.validate()` against the same schema **passes** this collection.
- The portolan-spec reference collection and its own
  `vector-partitioned-collection.json` example crash identically, so the defect
  is not specific to this catalog.
- `catalog.json` passes, because only a Collection reaches `valid_bbox`.

The tolerance in `test_stac_valid.py` is narrow on purpose. It matches that one
error string, requires the Portolan schema to be declared, and re-validates the
document against that schema directly before letting it through. Any other
stac-check error still fails the build.

This is worth fixing upstream rather than carrying. Either stac-validator should
honour a schema's declared `$schema`, or the Portolan schema should move to
2020-12 and use `prefixItems`.

<!--
When you accept one, add a row and a section explaining it, like this:

| Rule | Where | Why accepted | Tracking |
|---|---|---|---|
| PTL-VIZ-001 | all thumbnails | WebP is not yet permitted; the size saving is 4x | portolan-spec#121 |

Then add the rule id to ACCEPTED in tests/test_conformance.py. Both, or
neither.
-->
