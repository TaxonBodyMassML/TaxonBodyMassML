"""
Copy artifacts/checksums.json into the two package source files that embed
the SHA-256 constants:

    packages/python/taxonbodymassml/_checksums.py
    packages/r/R/model.R

Run from the repository root after scripts/export_artifacts.py:
    python scripts/sync_checksums.py

MODEL_ARTIFACT_VERSION is *not* touched here; scripts/publish_artifacts.py
advances it when the artifacts are actually uploaded.
"""

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKSUMS_JSON = REPO_ROOT / "artifacts" / "checksums.json"
PY_CHECKSUMS = REPO_ROOT / "packages" / "python" / "taxonbodymassml" / "_checksums.py"
R_MODEL = REPO_ROOT / "packages" / "r" / "R" / "model.R"


def _sub_all(text: str, pattern_for, checksums: dict[str, str], label: str) -> str:
    for fname, sha in checksums.items():
        pattern = pattern_for(re.escape(fname))
        text, n = re.subn(pattern, lambda m, sha=sha: m.group(1) + sha + m.group(3), text)
        if n != 1:
            sys.exit(f"{label}: expected exactly one entry for {fname!r}, found {n}")
    return text


def main() -> None:
    checksums = json.loads(CHECKSUMS_JSON.read_text())
    py = _sub_all(
        PY_CHECKSUMS.read_text(),
        lambda f: rf'("{f}":\s*")([0-9a-f]{{64}})(")',
        checksums,
        "_checksums.py",
    )
    r = _sub_all(
        R_MODEL.read_text(),
        lambda f: rf'("{f}"\s*=\s*")([0-9a-f]{{64}})(")',
        checksums,
        "model.R",
    )
    PY_CHECKSUMS.write_text(py)
    R_MODEL.write_text(r)
    for fname, sha in checksums.items():
        print(f"  {fname:<28s} {sha}")
    print(f"Updated {PY_CHECKSUMS.relative_to(REPO_ROOT)} and {R_MODEL.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
