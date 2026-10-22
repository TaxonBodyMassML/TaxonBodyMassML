"""
Upload new model version folders and the manifest to HuggingFace.

Run from the repository root after export_artifacts.py and sync_manifest.py:

    python scripts/publish_artifacts.py          # dry run: prints what would happen
    python scripts/publish_artifacts.py --yes    # upload and tag (requires owner approval)

What it does
------------
1. Downloads the current ``manifest.json`` from HF ``main`` (if it exists).
2. Compares with ``artifacts/manifest.json``:
   - Refuses if any local model/version folder already exists on the Hub
     (version folders are immutable).
   - Refuses if a Hub entry is missing locally (would indicate a local regression).
   - Computes ``release = hub_release + 1`` (or 1 if no Hub manifest exists yet).
3. Uploads only new folders + ``manifest.json`` + a regenerated ``README.md``.
4. Deletes legacy root-level files that are now superseded by the folder layout.
5. Creates an HF tag ``artifacts-<release>``.
6. Runs ``sync_manifest.py`` to copy the updated manifest into both packages.

Prerequisites::

    pip install huggingface_hub
    hf auth login

Publishing is irreversible for downstream users, so this script refuses to run
without ``--yes``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download
from huggingface_hub.utils import EntryNotFoundError

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = REPO_ROOT / "artifacts"
HF_REPO_ID = "marknovak/TaxonBodyMassML"

# Root-level legacy files to delete once the folder layout is in place.
# Listed by exact name (never use glob patterns here: hf upload --delete
# fnmatches '*' across '/' and would wipe model sub-folders).
LEGACY_ROOT_FILES = [
    "model.ubj",
    "model_ee.ubj",
    "calibration.json",
    "calibration_by_rank.json",
    "calibration_ee.json",
    "calibration_by_rank_ee.json",
    "categories.json",
    "lookup.json",
    "embeddings.json",
    "checksums.json",
]
# Glob patterns that are safe (no '/' in them → match only root files).
STALE_GLOB_PATTERNS = ["*gpboost*"]


def _download_hub_manifest(api: HfApi) -> dict | None:
    """Download manifest.json from HF main; return None if it does not exist."""
    try:
        path = hf_hub_download(
            repo_id=HF_REPO_ID,
            filename="manifest.json",
            repo_type="model",
            revision="main",
        )
        with open(path) as f:
            return json.load(f)
    except EntryNotFoundError:
        return None


def _check_consistency(local: dict, hub: dict | None) -> None:
    """Raise SystemExit if the local manifest would overwrite or lose Hub data."""
    if hub is None:
        return
    errors: list[str] = []
    for method, versions in hub.get("models", {}).items():
        for vkey, entry in versions.items():
            local_entry = local.get("models", {}).get(method, {}).get(vkey)
            if local_entry is None:
                errors.append(
                    f"{method}/{vkey} exists on the Hub but is missing locally — "
                    "do not lose published data."
                )
            elif local_entry["files"] != entry["files"]:
                errors.append(
                    f"{method}/{vkey} file checksums differ from the Hub — "
                    "version folders are immutable; use a new version number."
                )
    for dbv, entry in hub.get("provenance", {}).items():
        local_prov = local.get("provenance", {}).get(dbv)
        if local_prov is None:
            errors.append(f"provenance/{dbv} exists on the Hub but is missing locally.")
        elif local_prov["files"] != entry["files"]:
            errors.append(
                f"provenance/{dbv} file checksums differ from the Hub — "
                "provenance entries are immutable."
            )
    if errors:
        sys.exit("Consistency check failed:\n" + "\n".join(f"  - {e}" for e in errors))


def _new_folders(local: dict, hub: dict | None) -> list[str]:
    """Return HF-relative paths of folders that are new in the local manifest."""
    folders: list[str] = []
    hub_models = (hub or {}).get("models", {})
    hub_prov = (hub or {}).get("provenance", {})
    for method, versions in local.get("models", {}).items():
        for vkey, entry in versions.items():
            if vkey not in hub_models.get(method, {}):
                folders.append(entry["path"])
    for dbv, entry in local.get("provenance", {}).items():
        if dbv not in hub_prov:
            folders.append(entry["path"])
    return folders


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--yes", action="store_true", help="Actually upload and tag (default: dry run)")
    args = ap.parse_args()

    local_manifest_path = ARTIFACTS_DIR / "manifest.json"
    if not local_manifest_path.exists():
        sys.exit(
            f"ERROR: {local_manifest_path} not found.\n"
            "Run scripts/export_artifacts.py (or scripts/migrate_v1_manifest.py) first,\n"
            "then scripts/sync_manifest.py."
        )

    sys.path.insert(0, str(REPO_ROOT))
    from scripts.manifest import load as load_manifest
    from scripts.manifest import render_model_card
    from scripts.manifest import save as save_manifest
    from scripts.manifest import validate

    local = load_manifest(local_manifest_path)
    validate(local)

    api = HfApi()
    print(f"Fetching current manifest from {HF_REPO_ID} …")
    hub = _download_hub_manifest(api)
    if hub is None:
        print("  (no manifest on Hub yet — this is the first publish)")
        hub_release = 0
    else:
        hub_release = hub.get("release", 0)
        print(f"  Hub release: {hub_release}")

    _check_consistency(local, hub)

    new_folders = _new_folders(local, hub)
    if not new_folders:
        sys.exit("Nothing to publish: all local folders already exist on the Hub.")

    release = hub_release + 1
    local["release"] = release
    validate(local)

    # Regenerate the model card
    readme_content = render_model_card(local)

    if not args.yes:
        print("\nDry run — would:")
        for folder in new_folders:
            print(f"  upload  {folder}/")
        print(f"  upload  manifest.json  (release {release})")
        print("  upload  README.md")
        for name in LEGACY_ROOT_FILES:
            print(f"  delete  {name}  (if it exists)")
        for pat in STALE_GLOB_PATTERNS:
            print(f"  delete  {pat}  (glob)")
        print(f"  tag     artifacts-{release}")
        print("\nRe-run with --yes to publish (requires owner approval).")
        return

    # Write the updated manifest locally before uploading
    save_manifest(local, local_manifest_path)

    # Write the model card to a temp file alongside the manifest upload
    readme_path = ARTIFACTS_DIR / "README.md"
    readme_path.write_text(readme_content, encoding="utf-8")

    print(f"\nUploading to {HF_REPO_ID} (release {release}) …")

    # Build allow_patterns: new folders + manifest + README
    allow_patterns = ["manifest.json", "README.md"]
    for folder in new_folders:
        allow_patterns.append(f"{folder}/*")

    # Build ignore_patterns: everything else in artifacts/
    ignore_patterns = ["staging/**"]

    api.upload_folder(
        repo_id=HF_REPO_ID,
        repo_type="model",
        folder_path=str(ARTIFACTS_DIR),
        allow_patterns=allow_patterns,
        ignore_patterns=ignore_patterns,
        commit_message=f"artifacts-{release}: {', '.join(new_folders)}",
    )
    print("  Upload complete.")

    # Delete legacy root files (by exact name to avoid wiping sub-folders)
    files_on_hub = {
        f.rfilename
        for f in api.list_repo_tree(HF_REPO_ID, repo_type="model", recursive=True)
        if hasattr(f, "rfilename")
    }
    to_delete = [f for f in LEGACY_ROOT_FILES if f in files_on_hub]
    for pat in STALE_GLOB_PATTERNS:
        import fnmatch

        to_delete += [f for f in files_on_hub if fnmatch.fnmatch(f, pat) and f not in to_delete]
    if to_delete:
        api.delete_files(
            repo_id=HF_REPO_ID,
            repo_type="model",
            delete_patterns=to_delete,
            commit_message="Remove legacy root files superseded by folder layout",
        )
        print(f"  Deleted: {to_delete}")

    # Create the immutable release tag
    tag = f"artifacts-{release}"
    print(f"Creating HuggingFace tag {tag!r} …")
    api.create_tag(HF_REPO_ID, tag=tag, repo_type="model", exist_ok=False)

    print(f"\nDone. Artifacts published at {HF_REPO_ID} tagged {tag}")
    print("Now run: python scripts/sync_manifest.py")
    print("Then bump both package versions in pyproject.toml and DESCRIPTION, commit and push.")


if __name__ == "__main__":
    main()
