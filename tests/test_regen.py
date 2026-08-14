#!/usr/bin/env python3
"""collection.json matches what tools/build_collection.py would write.

Every derived number in that file, the extent, the row count, the partition
count, and each asset's size and checksum, is generated. A hand-edit or a
rebuilt asset silently desynchronises it, and rashid treats a stale
`file:checksum` as a conformance failure rather than a warning, so the drift
surfaces at publish time instead of here.

SKIPs when staging/ is absent, which is the normal state of a fresh clone and
of CI. The generator reads the staged partitions to compute the extent and the
row count, and they are 12 GB that never enter git.

Run: python3 tests/test_regen.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENERATOR = ROOT / "tools" / "build_collection.py"
PARTITIONS = ROOT / "staging" / "road-detections" / "by_country"

if not PARTITIONS.is_dir():
    print("SKIP: staging/ is absent, so the generator cannot run.")
    print("      Run tools/reencode.py to rebuild it, then re-run this.")
    raise SystemExit(0)

result = subprocess.run(
    [sys.executable, str(GENERATOR), "--check"],
    capture_output=True,
    text=True,
)
sys.stdout.write(result.stdout)
sys.stderr.write(result.stderr)

if result.returncode != 0:
    print("\nFAILED: collection.json is stale.")
    print("        Run: python3 tools/build_collection.py")
    raise SystemExit(1)
print("OK: collection.json matches its generator")
