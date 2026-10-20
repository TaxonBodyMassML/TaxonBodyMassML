"""
Copy artifacts/manifest.json into the two package source trees:

    packages/python/taxonbodymassml/data/manifest.json
    packages/r/inst/extdata/manifest.json

Run from the repository root after scripts/export_artifacts.py (or after
scripts/migrate_v1_manifest.py for the first-time migration):

    python scripts/sync_manifest.py

The manifest is validated before copying; the script exits non-zero if
validation fails so a bad manifest is never silently installed.

This script replaces scripts/sync_checksums.py now that the manifest is
the single source of truth for artifact checksums and version metadata.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS_MANIFEST = REPO_ROOT / "artifacts" / "manifest.json"
PY_DATA_DIR = REPO_ROOT / "packages" / "python" / "taxonbodymassml" / "data"
R_EXTDATA_DIR = REPO_ROOT / "packages" / "r" / "inst" / "extdata"

DESTINATIONS = [
    PY_DATA_DIR / "manifest.json",
    R_EXTDATA_DIR / "manifest.json",
]


def main() -> None:
    if not ARTIFACTS_MANIFEST.exists():
        sys.exit(
            f"ERROR: {ARTIFACTS_MANIFEST} not found.\n"
            "Run scripts/export_artifacts.py (or scripts/migrate_v1_manifest.py) first."
        )

    sys.path.insert(0, str(REPO_ROOT))
    from scripts.manifest import load, validate

    manifest = load(ARTIFACTS_MANIFEST)
    try:
        validate(manifest)
    except ValueError as exc:
        sys.exit(f"ERROR: {exc}")

    for dest in DESTINATIONS:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ARTIFACTS_MANIFEST, dest)
        print(f"  Copied → {dest.relative_to(REPO_ROOT)}")

    methods = list(manifest.get("models", {}))
    release = manifest.get("release", "?")
    print(
        f"Manifest (release={release}, methods={methods}) "
        f"synced to {len(DESTINATIONS)} package locations."
    )


if __name__ == "__main__":
    main()
