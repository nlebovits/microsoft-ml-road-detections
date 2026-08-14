#!/usr/bin/env python3
"""The publish contract: only the published directory is ever uploaded.

This is the gate that turns the three-file-category model into an enforced
property. It builds a temp tree holding all three categories, asks the
publisher what it would upload, and asserts set equality — so a leak fails and
a missing file fails too.

No network, no AWS, no credentials.

Run: python3 tests/test_publish.py
"""
import hashlib
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from publish import (  # noqa: E402
    Upload,
    collect_uploads,
    content_type_for,
    is_unchanged,
    split_s3_uri,
    unedited_sentinels,
)

errors: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def write(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


# --- what gets uploaded, and what never does ---------------------------
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)

    # Category 1: tracked and published.
    write(root / "catalog/catalog.json")
    write(root / "catalog/README.md")
    write(root / "catalog/AGENTS.md")
    write(root / "catalog/roads/collection.json")
    write(root / "catalog/roads/thumbnail.png")
    write(root / "catalog/roads/styles/default.json")
    write(root / "catalog/_assets/logo.svg")

    # Category 2: tracked, never published.
    write(root / "tools/publish.py")
    write(root / "tests/test_publish.py")
    write(root / "docs/conformance.md")
    write(root / "README.md")
    write(root / "AGENTS.md")
    write(root / "CLAUDE.md")
    write(root / "catalog.publish.yaml")
    write(root / ".github/workflows/ci.yml")

    # Dotfiles inside the published directory are tracked but not uploaded.
    write(root / "catalog/_assets/.gitkeep", "")
    write(root / "catalog/.portolan/state.json")

    config = {
        "write_prefix": "s3://a-bucket/a/prefix",
        "public_base": "https://data.example.org/a/prefix",
        "publish_dir": "catalog",
    }
    keys = {u.key for u in collect_uploads(config, root)}

    expected = {
        "a/prefix/catalog.json",
        "a/prefix/README.md",
        "a/prefix/AGENTS.md",
        "a/prefix/roads/collection.json",
        "a/prefix/roads/thumbnail.png",
        "a/prefix/roads/styles/default.json",
        "a/prefix/_assets/logo.svg",
    }
    check(keys == expected, f"upload set wrong.\n  extra:   {keys - expected}"
                            f"\n  missing: {expected - keys}")

    # The bare-prefix case: no prefix at all.
    flat = dict(config, write_prefix="s3://a-bucket")
    check(
        {u.key for u in collect_uploads(flat, root)}
        == {k.removeprefix("a/prefix/") for k in expected},
        "keys are wrong when write_prefix names no prefix",
    )

# --- split_s3_uri ------------------------------------------------------
check(split_s3_uri("s3://b/a/c") == ("b", "a/c"), "plain uri")
check(split_s3_uri("s3://b/a/c/") == ("b", "a/c"), "trailing slash")
check(split_s3_uri("s3://b") == ("b", ""), "bare bucket")
check(split_s3_uri("s3://b/") == ("b", ""), "bare bucket, trailing slash")

# --- content types -----------------------------------------------------
check(content_type_for(Path("a/catalog.json")) == "application/json",
      "plain json")
check(
    content_type_for(Path("a/styles/default.json"))
    == "application/vnd.mapbox.style+json",
    "json under styles/ is a MapLibre style",
)
check(
    content_type_for(Path("a/roads.style.json"))
    == "application/vnd.mapbox.style+json",
    "*.style.json is a MapLibre style",
)
check(
    content_type_for(Path("a/d.parquet")) == "application/vnd.apache.parquet",
    "parquet",
)
check(content_type_for(Path("a/x.unknown")) == "application/octet-stream",
      "unknown suffix falls back")

# --- change detection --------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    local = write(Path(tmp) / "f.json", "hello")
    digest = hashlib.md5(b"hello").hexdigest()  # noqa: S324
    upload = Upload(local, "k", "application/json")

    check(is_unchanged(upload, {"k": (5, digest)}), "identical bytes")
    check(is_unchanged(upload, {"k": (5, f'"{digest}"')}), "quoted etag")
    check(not is_unchanged(upload, {}), "absent key")
    check(not is_unchanged(upload, {"other": (5, digest)}), "key mismatch")
    check(not is_unchanged(upload, {"k": (5, "0" * 32)}), "etag differs")
    check(not is_unchanged(upload, {"k": (9, digest)}), "size differs")
    check(is_unchanged(upload, {"k": (5, "abc-2")}), "multipart: size only")

# --- the sentinel guard ------------------------------------------------
check(
    unedited_sentinels({
        "write_prefix": "s3://EXAMPLE-BUCKET/EXAMPLE-PREFIX",
        "public_base": "https://example.invalid/EXAMPLE-PREFIX",
    }) != [],
    "an unedited config is refused",
)
check(
    unedited_sentinels({
        "write_prefix": "s3://real/prefix",
        "public_base": "https://data.example.org/prefix",
    }) == [],
    "an edited config is accepted",
)

if errors:
    print("\n".join(f"error  {e}" for e in errors))
    raise SystemExit(1)
print("OK: publish contract holds")
