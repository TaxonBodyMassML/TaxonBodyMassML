"""
Export model artifacts for the TaxonBodyMassML R and Python packages.

Run from the repository root (after `python predictive_models/decision_tree.py`):
    python scripts/export_artifacts.py

Outputs (in artifacts/):
    model.ubj                -- XGBoost model (binary UBJSON; native categorical
                                splits on kingdom..genus)
    calibration.json         -- pooled XGBoost conformal calibration residuals
    calibration_by_rank.json -- rank-stratified XGBoost calibration residuals
    categories.json          -- per-feature category lists (kingdom..genus); index == training code
    lookup.json              -- species -> {mass_g, source} lookup
    checksums.json           -- SHA-256 for all artifact files (incl. EE files if present)

Also writes predictive_models/results/golden_predictions.json: reference
log10 predictions for a small fixed set of inputs, used by scripts/check_parity.py
and the package test suites to confirm every consumer reproduces the training
model exactly.

Entity Embeddings artifacts (embeddings.json, model_ee.ubj, calibration_ee.json,
calibration_by_rank_ee.json) are produced by predictive_models/entity_embeddings_model.py
and only checksummed here.

Publishing (`make publish`, requires explicit approval) uploads artifacts/ to
https://huggingface.co/marknovak/TaxonBodyMassML and tags the release; the
checksums then go into packages/python/taxonbodymassml/_checksums.py and
packages/r/R/model.R.
"""

import hashlib
import json
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

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
MODEL_PKL = REPO_ROOT / "regressor_microservice" / "sliced_model" / "xgboost_model.pkl"
RAW_CSV = REPO_ROOT / "data" / "TaxonBodyMass.csv"
TEST_CSV = REPO_ROOT / "data" / "split" / "test.csv"
OUT_DIR = REPO_ROOT / "artifacts"
GOLDEN_PATH = REPO_ROOT / "predictive_models" / "results" / "golden_predictions.json"
OUT_DIR.mkdir(exist_ok=True)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# 1. Load pickleslicer bundle and check the encoding contract
# ---------------------------------------------------------------------------
print("Loading pickleslicer bundle...")
bundle = pickleslicer.load(str(MODEL_PKL))
missing = {"model", "q", "vocab", "calib_residuals", "calib_residuals_by_rank", "lookup"} - set(
    bundle
)
if missing:
    sys.exit(
        f"Bundle is missing keys {sorted(missing)}; retrain with predictive_models/decision_tree.py"
    )
model = bundle["model"]
vocab = bundle["vocab"]
validate_vocab(vocab)
print("  Model loaded.")

booster = model.get_booster()
_model_features = list(booster.feature_names or [])
assert _model_features == MODEL_FEATURES, (
    f"Model feature_names {_model_features} != MODEL_FEATURES {MODEL_FEATURES}. "
    "Retrain via decision_tree.py."
)
assert booster.feature_types == ["c"] * len(MODEL_FEATURES), (
    f"Model feature_types {booster.feature_types} are not all categorical; "
    "decision_tree.py must train with enable_categorical=True."
)

# ---------------------------------------------------------------------------
# 2. Export XGBoost model to binary UBJSON format
# ---------------------------------------------------------------------------
model_path = OUT_DIR / "model.ubj"
model.save_model(str(model_path))
print(f"  Saved model → {model_path}  ({model_path.stat().st_size / 1e6:.1f} MB)")

# ---------------------------------------------------------------------------
# 3. categories.json: exactly the training vocabulary.  Each list starts with
#    UNK and is otherwise sorted, and index == training integer code, so R
#    factor levels / pandas categories built from it reproduce the codes.
#    Feature order is NOT stored here: consumers read model.feature_names.
#    There is no species list: species is not a model feature.
# ---------------------------------------------------------------------------
categories = {col: vocab[col] for col in MODEL_FEATURES}
for col in MODEL_FEATURES:
    print(f"  {col}: {len(vocab[col])} categories (incl. UNK)")
categories_path = OUT_DIR / "categories.json"
with open(categories_path, "w") as f:
    json.dump(categories, f, indent=2)
print(f"  Saved categories → {categories_path}")

# ---------------------------------------------------------------------------
# 4. Calibration residuals from the bundle (computed in decision_tree.py from
#    the 80%-fit model on its held-out calibration split; the shipped model is
#    refit on all training data so they cannot be recomputed here).
# ---------------------------------------------------------------------------
residuals_sorted = bundle["calib_residuals"]
calibration_path = OUT_DIR / "calibration.json"
with open(calibration_path, "w") as f:
    json.dump({"residuals": residuals_sorted}, f)
q_stored = float(bundle["q"])
q_rebuilt = float(np.quantile(residuals_sorted, 0.90))
assert abs(q_stored - q_rebuilt) < 1e-6, f"q mismatch: bundle {q_stored} vs residuals {q_rebuilt}"
print(f"  Saved {len(residuals_sorted)} residuals → {calibration_path}  (q90={q_stored:.4f})")

by_rank_residuals = bundle["calib_residuals_by_rank"]
assert set(by_rank_residuals) == set(RANKS_FINER), sorted(by_rank_residuals)
by_rank_path = OUT_DIR / "calibration_by_rank.json"
with open(by_rank_path, "w") as f:
    json.dump(by_rank_residuals, f)
for rank, res in by_rank_residuals.items():
    print(f"  {rank}: {len(res)} samples, q90={np.quantile(res, 0.90):.4f}")
print(f"  Saved rank-stratified residuals → {by_rank_path}")

# ---------------------------------------------------------------------------
# 5. species -> {mass_g, source} lookup.  Built by decision_tree.py from the
#    raw training data and stashed in the bundle so the microservice and the
#    packages share one dictionary.
# ---------------------------------------------------------------------------
lookup = bundle["lookup"]
lookup_path = OUT_DIR / "lookup.json"
with open(lookup_path, "w") as f:
    json.dump(lookup, f)
print(f"  Saved {len(lookup)} species → {lookup_path}")

# ---------------------------------------------------------------------------
# 6. Golden predictions: re-load the exported model.ubj as a plain Booster and
#    score a fixed set of raw string inputs.  Consumers (Python package, R
#    package, microservice) must reproduce these log10 values exactly.
# ---------------------------------------------------------------------------
print("Writing golden predictions...")
test = pd.read_csv(TEST_CSV)
cases = []
for i in range(5):  # full taxonomy, species level
    cases.append({"label": f"test_row_{i}", **{c: str(test[c].iloc[i]) for c in TAXONOMY_COLS}})
row0 = {c: str(test[c].iloc[0]) for c in TAXONOMY_COLS}
for rank, finer in RANKS_FINER.items():  # rank-level queries (species is always UNK)
    cases.append({"label": f"{rank}_level", **{**row0, "species": UNK, **{c: UNK for c in finer}}})
cases.append({"label": "all_unk", **{c: UNK for c in TAXONOMY_COLS}})
cases.append({"label": "unseen_species_known_genus", **{**row0, "species": "Zzzz notaspecies"}})
cases.append({"label": "unseen_everything", **{c: f"Zz{c}" for c in TAXONOMY_COLS}})

exported = xgb.Booster()
exported.load_model(str(model_path))
X_golden = encode_categorical(pd.DataFrame(cases), vocab)[exported.feature_names]
golden_preds = exported.predict(xgb.DMatrix(X_golden, enable_categorical=True))
for case, pred in zip(cases, golden_preds):
    case["log10_mass_g"] = float(pred)

# Entity Embeddings golden values (if its artifacts are present): features are
# the concatenated per-rank embedding vectors, unseen values -> UNK vector.
ee_model_path = OUT_DIR / "model_ee.ubj"
ee_emb_path = OUT_DIR / "embeddings.json"
if ee_model_path.exists() and ee_emb_path.exists():
    with open(ee_emb_path) as f:
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
    ee_booster.load_model(str(ee_model_path))
    ee_preds = ee_booster.predict(xgb.DMatrix(np.asarray(rows, dtype=np.float32)))
    for case, pred in zip(cases, ee_preds):
        case["log10_mass_g_ee"] = float(pred)
else:
    print("  (EE artifacts missing; golden file will not include log10_mass_g_ee)")

for case in cases:
    ee = f"  ee={case['log10_mass_g_ee']:.6f}" if "log10_mass_g_ee" in case else ""
    print(f"  {case['label']:<30s} xgb={case['log10_mass_g']:.6f}{ee}")
GOLDEN_PATH.parent.mkdir(exist_ok=True)
with open(GOLDEN_PATH, "w") as f:
    json.dump({"model_sha256": sha256_file(model_path), "cases": cases}, f, indent=2)
print(f"  Saved golden predictions → {GOLDEN_PATH}")

# ---------------------------------------------------------------------------
# 7. Checksums
# ---------------------------------------------------------------------------
print("Computing SHA256 checksums...")
checksums = {}
for fname in [
    "model.ubj",
    "calibration.json",
    "calibration_by_rank.json",
    "categories.json",
    "lookup.json",
]:
    checksums[fname] = sha256_file(OUT_DIR / fname)
    print(f"  {fname}: {checksums[fname]}")

for fname in [
    "embeddings.json",
    "model_ee.ubj",
    "calibration_ee.json",
    "calibration_by_rank_ee.json",
]:
    path = OUT_DIR / fname
    if path.exists():
        checksums[fname] = sha256_file(path)
        print(f"  {fname}: {checksums[fname]}")
    else:
        print(f"  {fname}: MISSING — run predictive_models/entity_embeddings_model.py first")

checksums_path = OUT_DIR / "checksums.json"
with open(checksums_path, "w") as f:
    json.dump(checksums, f, indent=2)
print(f"  Written to {checksums_path}")

print("""
Done. Next steps (see packages/UpdatingModelGuide.md):
  1. python scripts/check_parity.py      # Python package / R package / microservice vs golden
  2. Copy checksums into packages/python/taxonbodymassml/_checksums.py and packages/r/R/model.R
  3. make publish                        # only with explicit approval; uploads + tags on HF
""")
