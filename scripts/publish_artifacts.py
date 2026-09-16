"""
Upload artifacts to HuggingFace and create a versioned release tag.

Run from the repository root after export_artifacts.py has been run:
    python scripts/publish_artifacts.py

The R package version in packages/r/DESCRIPTION is used as the tag name:
    r-v<version>   (e.g. r-v0.7.0)

Prerequisites:
    pip install huggingface_hub
    hf auth login
"""

import re
import subprocess
import sys
from pathlib import Path

from huggingface_hub import HfApi

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = REPO_ROOT / "artifacts"
HF_REPO_ID = "marknovak/TaxonBodyMassML"
DESCRIPTION = REPO_ROOT / "packages" / "r" / "DESCRIPTION"


def _r_version() -> str:
    for line in DESCRIPTION.read_text().splitlines():
        m = re.match(r"^Version:\s*(\S+)", line)
        if m:
            return m.group(1)
    raise RuntimeError(f"Version not found in {DESCRIPTION}")


PY_CHECKSUMS = REPO_ROOT / "packages" / "python" / "taxonbodymassml" / "_checksums.py"
R_MODEL = REPO_ROOT / "packages" / "r" / "R" / "model.R"


def _update_model_artifact_version(version: str) -> None:
    """Rewrite MODEL_ARTIFACT_VERSION / .MODEL_ARTIFACT_VERSION in both source files."""
    for path, pattern in (
        (
            PY_CHECKSUMS,
            r'(MODEL_ARTIFACT_VERSION\s*=\s*")[^"]+(")',
        ),
        (
            R_MODEL,
            r'(\.MODEL_ARTIFACT_VERSION\s*<-\s*")[^"]+(")',
        ),
    ):
        text = path.read_text()
        new_text, n = re.subn(pattern, rf"\g<1>{version}\g<2>", text)
        if n == 0:
            sys.exit(f"Could not find MODEL_ARTIFACT_VERSION pattern in {path}")
        path.write_text(new_text)
        rel = path.relative_to(REPO_ROOT)
        print(f"  Updated MODEL_ARTIFACT_VERSION → {version!r} in {rel}")


def main() -> None:
    version = _r_version()

    print(f"Uploading {ARTIFACTS_DIR} → {HF_REPO_ID} ...")
    result = subprocess.run(
        ["hf", "upload", HF_REPO_ID, str(ARTIFACTS_DIR), ".", "--repo-type", "model"],
        check=False,
    )
    if result.returncode != 0:
        sys.exit(f"Upload failed (exit {result.returncode}). Aborting tag creation.")

    api = HfApi()
    for tag in (f"r-v{version}", f"py-v{version}"):
        print(f"Creating HuggingFace tag {tag!r} ...")
        api.create_tag(HF_REPO_ID, tag=tag, repo_type="model", exist_ok=True)

    print("Updating MODEL_ARTIFACT_VERSION in package source files ...")
    _update_model_artifact_version(version)

    print(f"Done. Artifacts published at {HF_REPO_ID} (r-v{version}, py-v{version})")
    print("Commit _checksums.py and model.R, then bump the package version and push.")


if __name__ == "__main__":
    main()
