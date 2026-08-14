#!/usr/bin/env python3
"""Every relative link and asset href resolves to a file that exists.

This catches the most common hand-edit mistake: adding a child link before the
directory it points at exists. Dependency-free and offline, so it runs in
milliseconds on a clean checkout.

Run: python3 tests/test_links.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from publish import load_config  # noqa: E402

config = load_config()
BASE = ROOT / config["publish_dir"]

errors: list[str] = []


def is_remote(href: str) -> bool:
    return "://" in href or href.startswith(("#", "mailto:"))


def stac_documents() -> list[Path]:
    """Every STAC object under the published directory."""
    out = []
    for path in sorted(BASE.rglob("*.json")):
        if any(part.startswith(".") for part in path.relative_to(BASE).parts):
            continue
        if path.name.endswith(".style.json") or "styles" in path.parts:
            continue
        try:
            doc = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            errors.append(f"{path.relative_to(ROOT)}: invalid JSON ({exc})")
            continue
        if isinstance(doc, dict) and doc.get("type") in {
            "Catalog", "Collection", "Feature"
        }:
            out.append(path)
    return out


documents = stac_documents()
checked = 0

for path in documents:
    doc = json.loads(path.read_text())
    rel_path = path.relative_to(ROOT)

    for link in doc.get("links", []):
        href = link.get("href", "")
        if not href or is_remote(href):
            continue
        checked += 1
        if not (path.parent / href).resolve().exists():
            errors.append(
                f"{rel_path}: rel:{link.get('rel')} -> {href} does not exist"
            )

    for key, asset in (doc.get("assets") or {}).items():
        href = asset.get("href", "")
        if not href or is_remote(href):
            continue
        checked += 1
        if not (path.parent / href).resolve().exists():
            errors.append(f"{rel_path}: asset {key} -> {href} does not exist")

if errors:
    print("\n".join(f"error  {e}" for e in errors))
    raise SystemExit(1)

print(f"OK: {checked} relative href(s) across {len(documents)} object(s)")
