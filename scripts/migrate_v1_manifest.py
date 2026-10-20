"""
One-off migration: register the 0.13.0 artifacts as v1 of XGBoost and
EntityEmbeddings in the manifest, then write the manifest to artifacts/.

Run from the repository root BEFORE scripts/publish_artifacts.py:

    python scripts/migrate_v1_manifest.py [--dry-run]

What it does
------------
1. Downloads all 0.13.0 model files from ``py-v0.13.0`` on Hugging Face into
   ``artifacts/models/XGBoost/v1/`` and ``artifacts/models/EntityEmbeddings/v1/``
   with normalised file names (strips the ``_ee`` suffix from the EE files).
2. Verifies each file against the known 0.13.0 SHA-256 checksums.
3. Builds a manifest entry for each model using the 0.13.0 metrics.
4. Writes ``artifacts/manifest.json``.

The generated ``artifacts/manifest.json`` is then synced into both packages by
``scripts/sync_manifest.py``, and uploaded by ``scripts/publish_artifacts.py``.

The old flat files (``model.ubj``, ``model_ee.ubj``, …) at the root of HF
``main`` are left untouched by this script; ``publish_artifacts.py`` deletes
them in the same commit that uploads the new layout.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = REPO_ROOT / "artifacts"

# ---- Known 0.13.0 checksums (py-v0.13.0 / r-v0.13.0) --------------------
# Source: git show 63b9698^:packages/python/taxonbodymassml/_checksums.py
V1_CHECKSUMS_XGB = {
    "model.ubj": "6bad674b79ccab14ed721c311ad47349f0530a7fddc3f3cb25fdf2b025fa5dbd",
    "calibration.json": "890527f72e80b25d93d15e136c9ee7b9fe424113770743e0f800b8f8f08b8ff9",
    "calibration_by_rank.json": "73f933218adb4353f3812d6f97e092945aabecb938d39e40db167895b1ab5aa0",
    "categories.json": "f9495c6f6b9c4411512f8083faed0e40bcffe548b1bf12e7b9f7656382df9218",
    "lookup.json": "e49b971caa4d7b9078a59a0681a8cb9cde78e67f4244bc0e3c689eaf43255784",
}
# EE files on HF have the _ee suffix; we rename them to normalised names.
# Hub name -> normalised name
V1_EE_RENAME = {
    "model_ee.ubj": "model.ubj",
    "embeddings.json": "embeddings.json",  # no rename needed
    "calibration_ee.json": "calibration.json",
    "calibration_by_rank_ee.json": "calibration_by_rank.json",
    # categories.json and lookup.json are shared with XGBoost (identical files)
    "categories.json": "categories.json",
    "lookup.json": "lookup.json",
}
# Original (Hub) SHA-256 for EE files
V1_CHECKSUMS_EE_HUB = {
    "model_ee.ubj": "9b27e77101ee5559e8e58e8d1ebbbea4ee23b92606ce9c7ff2025a8b522f2eb6",
    "embeddings.json": "9abc38faff6ac490f27480d1c19698c19d8e3a934acd76919c95bf366ac8ec17",
    "calibration_ee.json": "cd68beb482bc1427e7163f0665260ef2a13b9dd47e6f353bac46172aa1519200",
    "calibration_by_rank_ee.json": "1c12da9c75e261240ff34867e99081277c62744f20ef432748a86d5dc3268083",  # noqa: E501
    "categories.json": "f9495c6f6b9c4411512f8083faed0e40bcffe548b1bf12e7b9f7656382df9218",
    "lookup.json": "e49b971caa4d7b9078a59a0681a8cb9cde78e67f4244bc0e3c689eaf43255784",
}

# ---- 0.13.0 metrics -------------------------------------------------------
V1_XGB_METRICS = {
    "r2": 0.8936,
    "rmse": 0.6078,
    "mae": 0.3535,
    "n_train": 32916,
    "n_test": 3657,
}
V1_EE_METRICS = {
    "r2": 0.9104,
    "rmse": 0.5578,
    "mae": 0.3237,
    "n_train": 32916,
    "n_test": 3657,
}

HF_REPO_ID = "marknovak/TaxonBodyMassML"
HF_REVISION = "py-v0.13.0"
DB_VERSION = "v6.0.0"  # TaxonBodyMass_DB version at time of 0.13.0 release
PACKAGE_MIN = "0.14.0"  # first package version that understands the manifest
XGB_TRAINED = "2026-09-25T23:42:41+00:00"
EE_TRAINED = "2026-09-26T22:53:07+00:00"


def download_file(hub_name: str, dest: Path, dry_run: bool) -> None:
    from huggingface_hub import hf_hub_download

    if dry_run:
        print(f"  [dry-run] would download {hub_name} → {dest}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  Downloading {hub_name} …")
    local = hf_hub_download(
        repo_id=HF_REPO_ID,
        filename=hub_name,
        repo_type="model",
        revision=HF_REVISION,
        local_dir=str(dest.parent),
        local_dir_use_symlinks=False,
    )
    # hf_hub_download may write to a flat local_dir using the filename alone
    dl_path = Path(local)
    if dl_path != dest:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(dl_path.read_bytes())
        if dl_path != dest:
            dl_path.unlink(missing_ok=True)


def verify(path: Path, expected_sha: str) -> None:
    from scripts.manifest import sha256_file

    got = sha256_file(path)
    if got != expected_sha:
        raise RuntimeError(
            f"SHA-256 mismatch for {path.name}:\n"
            f"  expected {expected_sha}\n"
            f"  got      {got}"
        )
    print(f"  ✓ {path.name}")


def build_xgb_v1(dry_run: bool) -> Path:
    folder = ARTIFACTS_DIR / "models" / "XGBoost" / "v1"
    folder.mkdir(parents=True, exist_ok=True)
    for hub_name, sha in V1_CHECKSUMS_XGB.items():
        dest = folder / hub_name  # XGBoost names are already normalised
        if not dry_run and dest.exists():
            from scripts.manifest import sha256_file

            if sha256_file(dest) == sha:
                print(f"  ✓ {hub_name} (already cached)")
                continue
        download_file(hub_name, dest, dry_run)
        if not dry_run:
            verify(dest, sha)
    return folder


def build_ee_v1(dry_run: bool) -> Path:
    folder = ARTIFACTS_DIR / "models" / "EntityEmbeddings" / "v1"
    folder.mkdir(parents=True, exist_ok=True)
    # Download into a temp subdir first (hub names), then rename
    tmp = folder / "_tmp_hub"
    tmp.mkdir(exist_ok=True)
    for hub_name, sha in V1_CHECKSUMS_EE_HUB.items():
        tmp_dest = tmp / hub_name
        if not dry_run and tmp_dest.exists():
            from scripts.manifest import sha256_file

            if sha256_file(tmp_dest) == sha:
                print(f"  ✓ {hub_name} (already cached)")
            else:
                download_file(hub_name, tmp_dest, dry_run)
                if not dry_run:
                    verify(tmp_dest, sha)
        else:
            download_file(hub_name, tmp_dest, dry_run)
            if not dry_run:
                verify(tmp_dest, sha)
        # Rename to normalised name in the final folder
        norm_name = V1_EE_RENAME[hub_name]
        dest = folder / norm_name
        if not dry_run:
            dest.write_bytes(tmp_dest.read_bytes())
    if not dry_run:
        import shutil

        shutil.rmtree(tmp)
    else:
        print(f"  [dry-run] would rename EE files and remove {tmp}")
    return folder


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen without downloading or writing",
    )
    args = ap.parse_args()

    sys.path.insert(0, str(REPO_ROOT))  # allow `from scripts.manifest import ...`
    from scripts.manifest import add_model, empty, save, validate

    print("=== Building XGBoost v1 ===")
    xgb_folder = build_xgb_v1(args.dry_run)

    print("\n=== Building EntityEmbeddings v1 ===")
    ee_folder = build_ee_v1(args.dry_run)

    print("\n=== Building manifest ===")
    manifest = empty()
    manifest["release"] = 0  # publish_artifacts.py sets this to remote.release + 1

    if not args.dry_run:
        add_model(
            manifest,
            "XGBoost",
            1,
            xgb_folder,
            db_version=DB_VERSION,
            trained=XGB_TRAINED,
            package_min=PACKAGE_MIN,
            metrics=V1_XGB_METRICS,
            notes="0.13.0 release artifacts (py-v0.13.0 / r-v0.13.0)",
        )
        add_model(
            manifest,
            "EntityEmbeddings",
            1,
            ee_folder,
            db_version=DB_VERSION,
            trained=EE_TRAINED,
            package_min=PACKAGE_MIN,
            metrics=V1_EE_METRICS,
            notes="0.13.0 release artifacts (py-v0.13.0 / r-v0.13.0)",
        )
        validate(manifest)
        out = ARTIFACTS_DIR / "manifest.json"
        save(manifest, out)
        print(f"\nWrote {out}")
        print("Next: python scripts/sync_manifest.py && python scripts/publish_artifacts.py")
    else:
        print("[dry-run] would write artifacts/manifest.json with XGBoost v1 + EntityEmbeddings v1")


if __name__ == "__main__":
    main()
