"""
Export model artifacts for the TaxonBodyMassML R and Python packages.

Run from the repository root after training. Each method writes its files into
a versioned sub-folder of ``artifacts/models/``.

Usage::

    # Export both methods at the next auto-incremented version
    python scripts/export_artifacts.py

    # Export only XGBoost at the next version
    python scripts/export_artifacts.py --method XGBoost

    # Export EntityEmbeddings at an explicit version number
    python scripts/export_artifacts.py --method EntityEmbeddings --version 3

    # Export with a custom note
    python scripts/export_artifacts.py --notes "Retrain on DB v7.0.0"

Prerequisites
-------------
XGBoost:
    python predictive_models/decision_tree.py
    (writes the pickleslicer bundle to regressor_microservice/sliced_model/)

EntityEmbeddings:
    python predictive_models/entity_embeddings_model.py
    (writes artifacts to artifacts/staging/EntityEmbeddings/)

Outputs (in ``artifacts/models/<Method>/v<n>/``)
-------------------------------------------------
Both methods:
    model.ubj                    XGBoost booster (binary UBJSON)
    calibration.json             Pooled conformal residuals
    calibration_by_rank.json     Rank-stratified residuals
    categories.json              Per-feature category lists (index == training code)
    lookup.json                  species -> {mass_g, source} dictionary

EntityEmbeddings only:
    embeddings.json              Per-column embedding lookup tables

The manifest at ``artifacts/manifest.json`` is updated with the new entry.
Golden predictions at ``predictive_models/results/golden_predictions.json``
are updated with the new (method, version) entries.

Publishing (``make publish``, requires explicit approval from the repo owner)
uploads the new version folders + manifest to Hugging Face and tags the release.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pickleslicer
import xgboost as xgb

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "predictive_models"))
from taxonomy_encoding import (  # noqa: E402
    MODEL_FEATURES,
    RANKS_FINER,
    TAXONOMY_COLS,
    UNK,
    encode_categorical,
    validate_vocab,
)

sys.path.insert(0, str(REPO_ROOT))
from scripts._db_version import db_version as resolve_db_version  # noqa: E402
from scripts.manifest import newest  # noqa: E402
from scripts.manifest import add_model, empty  # noqa: E402
from scripts.manifest import load as load_manifest  # noqa: E402
from scripts.manifest import save as save_manifest  # noqa: E402
from scripts.manifest import sha256_file, validate  # noqa: E402

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
MODEL_PKL = REPO_ROOT / "regressor_microservice" / "sliced_model" / "xgboost_model.pkl"
RAW_CSV = REPO_ROOT / "data" / "TaxonBodyMass.csv"
TEST_CSV = REPO_ROOT / "data" / "split" / "test.csv"
ARTIFACTS_DIR = REPO_ROOT / "artifacts"
MANIFEST_PATH = ARTIFACTS_DIR / "manifest.json"
EE_STAGING_DIR = ARTIFACTS_DIR / "staging" / "EntityEmbeddings"
GOLDEN_PATH = REPO_ROOT / "predictive_models" / "results" / "golden_predictions.json"

# Bundled manifest in the Python package (source of truth for "newest" version).
PY_MANIFEST = REPO_ROOT / "packages" / "python" / "taxonbodymassml" / "data" / "manifest.json"

METRICS_JSON = REPO_ROOT / "predictive_models" / "results" / "metrics.json"
METRICS_EE_JSON = REPO_ROOT / "predictive_models" / "results" / "metrics_ee.json"


# ---------------------------------------------------------------------------
# Version resolution
# ---------------------------------------------------------------------------


def _next_version(manifest: dict, method: str, version_arg: str | None) -> int:
    """Return the version integer to write for *method*.

    If ``version_arg`` is ``None`` or ``"auto"``, return newest+1.
    Otherwise parse the integer from the argument.
    """
    if version_arg is None or version_arg == "auto":
        current = newest(manifest, method)
        return 1 if current is None else current + 1
    try:
        return int(version_arg.lstrip("v"))
    except ValueError:
        sys.exit(f"ERROR: --version must be 'auto' or an integer, got {version_arg!r}")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _load_vocab_from_train() -> dict:
    """Build the training vocabulary from data/split/train.csv."""
    from taxonomy_encoding import build_vocab  # type: ignore[import]

    train = pd.read_csv(REPO_ROOT / "data" / "split" / "train.csv")
    return build_vocab(train)


def _load_lookup_from_csv() -> dict:
    """Build the species -> {mass_g, source} dictionary from data/TaxonBodyMass.csv."""
    raw = pd.read_csv(RAW_CSV, usecols=["species", "mass_g", "CiteID"])
    lookup = {}
    for row in raw.itertuples(index=False):
        if row.species and str(row.species).strip():
            lookup[str(row.species)] = {
                "mass_g": float(row.mass_g),
                "source": str(row.CiteID) if not pd.isna(row.CiteID) else "",
            }
    return lookup


def _write_calibration(residuals: list[float], out_dir: Path) -> None:
    with open(out_dir / "calibration.json", "w") as f:
        json.dump({"residuals": list(residuals)}, f)


def _write_calibration_by_rank(by_rank: dict, out_dir: Path) -> None:
    with open(out_dir / "calibration_by_rank.json", "w") as f:
        json.dump(by_rank, f)


def _write_categories(vocab: dict, out_dir: Path) -> None:
    categories = {col: vocab[col] for col in MODEL_FEATURES}
    with open(out_dir / "categories.json", "w") as f:
        json.dump(categories, f, indent=2)


def _write_lookup(lookup: dict, out_dir: Path) -> None:
    with open(out_dir / "lookup.json", "w") as f:
        json.dump(lookup, f)


def _read_metrics(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path) as f:
        d = json.load(f)
    return {
        "r2": round(float(d.get("r2", 0)), 6),
        "rmse": round(float(d.get("rmse", 0)), 6),
        "mae": round(float(d.get("mae", 0)), 6),
        "n_train": int(d.get("n_train", 0)),
        "n_test": int(d.get("n_test", 0)),
    }


# ---------------------------------------------------------------------------
# Golden predictions
# ---------------------------------------------------------------------------


def _load_golden() -> dict:
    if GOLDEN_PATH.exists():
        with open(GOLDEN_PATH) as f:
            g = json.load(f)
        # Upgrade schema v1 (flat cases list) to schema v2
        if "models" not in g:
            g = {"schema_version": 2, "models": {}}
    else:
        g = {"schema_version": 2, "models": {}}
    return g


def _save_golden(golden: dict) -> None:
    GOLDEN_PATH.parent.mkdir(exist_ok=True)
    with open(GOLDEN_PATH, "w") as f:
        json.dump(golden, f, indent=2)
    print(f"  Saved golden predictions → {GOLDEN_PATH}")


def _build_cases() -> list[dict]:
    """Build the fixed set of golden test cases from test.csv."""
    test = pd.read_csv(TEST_CSV)
    cases = []
    for i in range(min(5, len(test))):
        cases.append({"label": f"test_row_{i}", **{c: str(test[c].iloc[i]) for c in TAXONOMY_COLS}})
    row0 = {c: str(test[c].iloc[0]) for c in TAXONOMY_COLS}
    for rank, finer in RANKS_FINER.items():
        cases.append(
            {
                "label": f"{rank}_level",
                **{**row0, "species": UNK, **{c: UNK for c in finer}},
            }
        )
    cases.append({"label": "all_unk", **{c: UNK for c in TAXONOMY_COLS}})
    cases.append({"label": "unseen_species_known_genus", **{**row0, "species": "Zzzz notaspecies"}})
    cases.append({"label": "unseen_everything", **{c: f"Zz{c}" for c in TAXONOMY_COLS}})
    return cases


def _golden_xgboost(model_path: Path, vocab: dict) -> tuple[list[dict], str]:
    cases = _build_cases()
    exported = xgb.Booster()
    exported.load_model(str(model_path))
    X_golden = encode_categorical(pd.DataFrame(cases), vocab)[exported.feature_names]
    preds = exported.predict(xgb.DMatrix(X_golden, enable_categorical=True))
    for case, pred in zip(cases, preds):
        case["log10_mass_g"] = float(pred)
        case["expect_na"] = all(case[c] == UNK or case[c] not in vocab[c] for c in MODEL_FEATURES)
    return cases, sha256_file(model_path)


def _golden_ee(model_path: Path, emb_path: Path, vocab: dict) -> tuple[list[dict], str]:
    cases = _build_cases()
    with open(emb_path) as f:
        embeddings = json.load(f)
    assert set(embeddings) == set(MODEL_FEATURES), sorted(embeddings)
    rows = []
    for case in cases:
        vec = []
        for col in MODEL_FEATURES:
            table = embeddings[col]
            vec.extend(table.get(case[col], table[UNK]))
        rows.append(vec)
    ee_booster = xgb.Booster()
    ee_booster.load_model(str(model_path))
    preds = ee_booster.predict(xgb.DMatrix(np.asarray(rows, dtype=np.float32)))
    for case, pred in zip(cases, preds):
        case["log10_mass_g"] = float(pred)
        case["expect_na"] = all(case[c] == UNK or case[c] not in vocab[c] for c in MODEL_FEATURES)
    return cases, sha256_file(model_path)


# ---------------------------------------------------------------------------
# Export methods
# ---------------------------------------------------------------------------


def export_xgboost(version: int, db_ver: str, package_min: str, notes: str) -> None:
    print(f"\n=== Exporting XGBoost v{version} ===")
    out_dir = ARTIFACTS_DIR / "models" / "XGBoost" / f"v{version}"
    if out_dir.exists():
        sys.exit(
            f"ERROR: {out_dir} already exists. "
            "Use a higher --version or remove the directory first."
        )
    out_dir.mkdir(parents=True)

    print("Loading pickleslicer bundle …")
    bundle = pickleslicer.load(str(MODEL_PKL))
    required = {"model", "q", "vocab", "calib_residuals", "calib_residuals_by_rank", "lookup"}
    missing = required - set(bundle)
    if missing:
        sys.exit(f"Bundle missing keys {sorted(missing)}; retrain with decision_tree.py")

    model = bundle["model"]
    vocab = bundle["vocab"]
    validate_vocab(vocab)

    booster = model.get_booster()
    _mf = list(booster.feature_names or [])
    assert _mf == MODEL_FEATURES, f"feature_names {_mf} != {MODEL_FEATURES}"
    assert booster.feature_types == ["c"] * len(MODEL_FEATURES)

    model_path = out_dir / "model.ubj"
    model.save_model(str(model_path))
    print(f"  model.ubj  ({model_path.stat().st_size / 1e6:.1f} MB)")

    _write_categories(vocab, out_dir)
    print(f"  categories.json  ({len(MODEL_FEATURES)} features)")

    _write_calibration(bundle["calib_residuals"], out_dir)
    q = float(bundle["q"])
    print(f"  calibration.json  (q90={q:.4f})")

    _write_calibration_by_rank(bundle["calib_residuals_by_rank"], out_dir)
    print(f"  calibration_by_rank.json  ({len(bundle['calib_residuals_by_rank'])} ranks)")

    # Build lookup.json from TaxonBodyMass.csv (also in the bundle, kept in sync)
    lookup_from_csv = _load_lookup_from_csv()
    _write_lookup(lookup_from_csv, out_dir)
    print(f"  lookup.json  ({len(lookup_from_csv)} species)")

    # Golden predictions
    golden = _load_golden()
    cases, model_sha = _golden_xgboost(model_path, vocab)
    golden.setdefault("models", {}).setdefault("XGBoost", {})[f"v{version}"] = {
        "model_sha256": model_sha,
        "cases": cases,
    }
    for case in cases:
        print(f"  {case['label']:<30s}  {case['log10_mass_g']:.6f}")
    _save_golden(golden)

    # Update manifest
    manifest = load_manifest(MANIFEST_PATH) if MANIFEST_PATH.exists() else empty()
    metrics = _read_metrics(METRICS_JSON)
    trained = metrics.pop("trained", "")
    # Read trained timestamp from metrics.json if available
    try:
        import json as _json

        with open(METRICS_JSON) as _f:
            _m = _json.load(_f)
        trained = _m.get("timestamp", "")
    except Exception:
        trained = ""
    add_model(
        manifest,
        "XGBoost",
        version,
        out_dir,
        db_version=db_ver,
        trained=trained,
        package_min=package_min,
        metrics=metrics,
        notes=notes,
    )
    save_manifest(manifest, MANIFEST_PATH)
    print(f"  manifest updated: XGBoost v{version}")


def export_entity_embeddings(version: int, db_ver: str, package_min: str, notes: str) -> None:
    print(f"\n=== Exporting EntityEmbeddings v{version} ===")
    out_dir = ARTIFACTS_DIR / "models" / "EntityEmbeddings" / f"v{version}"
    if out_dir.exists():
        sys.exit(
            f"ERROR: {out_dir} already exists. "
            "Use a higher --version or remove the directory first."
        )
    out_dir.mkdir(parents=True)

    # Source files from staging (written by entity_embeddings_model.py)
    staging = EE_STAGING_DIR
    if not staging.exists():
        sys.exit(
            f"ERROR: staging dir {staging} not found. "
            "Run predictive_models/entity_embeddings_model.py first."
        )

    # Expected files in staging (with their canonical destination names)
    # entity_embeddings_model.py writes: model_ee.ubj, embeddings.json,
    # calibration_ee.json, calibration_by_rank_ee.json
    rename_map = {
        "model_ee.ubj": "model.ubj",
        "embeddings.json": "embeddings.json",
        "calibration_ee.json": "calibration.json",
        "calibration_by_rank_ee.json": "calibration_by_rank.json",
    }
    for src_name, dst_name in rename_map.items():
        src = staging / src_name
        if not src.exists():
            sys.exit(
                f"ERROR: {src} not found. "
                "Run predictive_models/entity_embeddings_model.py first."
            )
        shutil.copy2(src, out_dir / dst_name)
        print(f"  {dst_name}  ({(out_dir / dst_name).stat().st_size / 1e6:.1f} MB)")

    # Build categories.json and lookup.json from training data (not from the
    # pickleslicer bundle, so EE export is self-contained).
    vocab = _load_vocab_from_train()
    validate_vocab(vocab)

    # Verify vocab matches embeddings keys
    emb_path = out_dir / "embeddings.json"
    with open(emb_path) as f:
        embeddings = json.load(f)
    for col in MODEL_FEATURES:
        emb_vals = set(embeddings.get(col, {}).keys())
        vocab_vals = set(vocab[col])
        if not vocab_vals.issubset(emb_vals | {UNK}):
            extra = vocab_vals - emb_vals - {UNK}
            print(f"  WARNING: {col} vocab has values not in embeddings: {sorted(extra)[:5]}")

    _write_categories(vocab, out_dir)
    print(f"  categories.json  ({len(MODEL_FEATURES)} features)")

    lookup = _load_lookup_from_csv()
    _write_lookup(lookup, out_dir)
    print(f"  lookup.json  ({len(lookup)} species)")

    # Golden predictions
    golden = _load_golden()
    cases, model_sha = _golden_ee(out_dir / "model.ubj", emb_path, vocab)
    golden.setdefault("models", {}).setdefault("EntityEmbeddings", {})[f"v{version}"] = {
        "model_sha256": model_sha,
        "cases": cases,
    }
    for case in cases:
        print(f"  {case['label']:<30s}  {case['log10_mass_g']:.6f}")
    _save_golden(golden)

    # Update manifest
    manifest = load_manifest(MANIFEST_PATH) if MANIFEST_PATH.exists() else empty()
    metrics = _read_metrics(METRICS_EE_JSON)
    trained = ""
    try:
        with open(METRICS_EE_JSON) as _f:
            _m = json.load(_f)
        trained = _m.get("timestamp", "")
    except Exception:
        trained = ""
    add_model(
        manifest,
        "EntityEmbeddings",
        version,
        out_dir,
        db_version=db_ver,
        trained=trained,
        package_min=package_min,
        metrics=metrics,
        notes=notes,
    )
    save_manifest(manifest, MANIFEST_PATH)
    print(f"  manifest updated: EntityEmbeddings v{version}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--method",
        choices=["XGBoost", "EntityEmbeddings", "all"],
        default="all",
        help="Which model to export (default: all)",
    )
    ap.add_argument(
        "--version",
        default="auto",
        help=(
            "Version to write: 'auto' (default) = newest in manifest + 1; "
            "or an explicit integer."
        ),
    )
    ap.add_argument(
        "--db-version",
        default=None,
        metavar="TAG",
        help="TaxonBodyMass_DB version tag (default: auto-detected from git describe)",
    )
    ap.add_argument(
        "--package-min",
        default=None,
        metavar="SEMVER",
        help=(
            "Minimum package version that understands this artifact format "
            "(default: read from packages/python/pyproject.toml)"
        ),
    )
    ap.add_argument("--notes", default="", help="Free-text note for the manifest entry")
    args = ap.parse_args()

    # Resolve DB version
    db_ver = resolve_db_version(args.db_version)
    print(f"DB version: {db_ver}")

    # Resolve package_min
    if args.package_min:
        pkg_min = args.package_min
    else:
        import tomllib

        pyproject = REPO_ROOT / "packages" / "python" / "pyproject.toml"
        with open(pyproject, "rb") as f:
            pkg_min = tomllib.load(f)["project"]["version"]
    print(f"package_min: {pkg_min}")

    # Load current manifest (or start fresh)
    manifest = load_manifest(MANIFEST_PATH) if MANIFEST_PATH.exists() else empty()

    methods = ["XGBoost", "EntityEmbeddings"] if args.method == "all" else [args.method]
    for method in methods:
        v = _next_version(manifest, method, args.version)
        # Reload manifest after each export so add_model sees the updated state
        manifest = load_manifest(MANIFEST_PATH) if MANIFEST_PATH.exists() else empty()
        if method == "XGBoost":
            export_xgboost(v, db_ver, pkg_min, args.notes)
        else:
            export_entity_embeddings(v, db_ver, pkg_min, args.notes)

    # Final validation
    manifest = load_manifest(MANIFEST_PATH)
    try:
        validate(manifest)
        print("\n✓ Manifest validates OK")
    except ValueError as exc:
        print(f"\n⚠ Manifest validation warning:\n{exc}")

    print("""
Done. Next steps (see packages/UpdatingModelGuide.md):
  1. python scripts/sync_manifest.py     # copy manifest into both packages
  2. (cd packages/r && R CMD INSTALL .)  # reinstall R package with new manifest
  3. python scripts/check_parity.py --sync-cache --no-service
  4. python scripts/publish_artifacts.py # dry run first; then --yes with owner approval
""")


if __name__ == "__main__":
    main()
