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

None.

<!--
When you accept one, add a row and a section explaining it, like this:

| Rule | Where | Why accepted | Tracking |
|---|---|---|---|
| PTL-VIZ-001 | all thumbnails | WebP is not yet permitted; the size saving is 4x | portolan-spec#121 |

Then add the rule id to ACCEPTED in tests/test_conformance.py. Both, or
neither.
-->
