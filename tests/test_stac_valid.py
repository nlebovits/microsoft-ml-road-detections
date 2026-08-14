#!/usr/bin/env python3
"""STAC validity, via stac-check.

Validates every STAC object under the published directory against the official
STAC 1.1.0 schemas. This answers a different question from rashid: stac-check
asks whether the JSON is valid STAC, rashid asks whether the catalog conforms
to Portolan. A catalog can pass one and fail the other, so both run.

Two notes on how this is wired:

- Per-file, with recursive=False. stac-validator's recursive mode trips over
  relative links in a directory tree, and per-file gives a usable error anyway.
- Best-practice notes print as warnings and never fail the build. Some of them
  contradict Portolan on purpose: stac-check recommends a rel:'self' link,
  which Portolan forbids, because a static catalog that hardcodes its own
  location cannot be mirrored or moved. rashid is the gate; this is advisory.

SKIPs when stac-check is not installed, so a clean checkout needs no setup.

Run: python3 tests/test_stac_valid.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from publish import load_config  # noqa: E402

try:
    from stac_check.lint import Linter
except ImportError:
    print("SKIP: stac-check is not installed; STAC validity not checked here.")
    print("      CI installs it and enforces this.")
    raise SystemExit(0)

config = load_config()
BASE = ROOT / config["publish_dir"]

STAC_TYPES = {"Catalog", "Collection", "Feature"}
errors: list[str] = []
checked = 0

for path in sorted(BASE.rglob("*.json")):
    rel = path.relative_to(BASE)
    if any(part.startswith(".") for part in rel.parts):
        continue
    if path.name.endswith(".style.json") or "styles" in path.parts:
        continue
    try:
        doc = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        errors.append(f"{rel}: invalid JSON ({exc})")
        continue
    if not isinstance(doc, dict) or doc.get("type") not in STAC_TYPES:
        continue

    checked += 1
    linter = Linter(str(path), recursive=False)
    if not linter.valid_stac:
        errors.append(f"{rel}: {linter.error_msg}")
        continue
    for note in linter.best_practices_msg[1:]:
        if note.strip():
            print(f"note   {rel}: {note.strip()}")

if errors:
    print("\n".join(f"error  {e}" for e in errors))
    raise SystemExit(1)
print(f"OK: {checked} STAC object(s) valid")
