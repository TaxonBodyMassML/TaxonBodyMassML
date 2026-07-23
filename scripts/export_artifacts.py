"""
Export model artifacts for the TaxonBodyMassML R and Python packages.

Run from the repository root:
    python scripts/export_artifacts.py

Outputs (in artifacts/):
    model.ubj         -- XGBoost model in binary UBJSON format (~2 GB; cross-platform/language)
    calibration.json  -- {"residuals": [<float>, ...]} full sorted calibration residuals array
    categories.json   -- {"<col>": [<str>, ...]} valid training category sets per taxonomy column
    checksums.json    -- {"model.ubj": "<sha256>", "calibration.json": "<sha256>", ...}

Upload these four files to the Hugging Face model repository:
    https://huggingface.co/marknovak/TaxonBodyMassML

Using the huggingface_hub CLI:
    pip install huggingface_hub
    huggingface-cli login
    huggingface-cli upload marknovak/TaxonBodyMassML artifacts/ . --repo-type model

The Python and R packages download these files on first use and cache them locally.
Bundle the contents of artifacts/checksums.json into the packages as the integrity constants.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pickleslicer
from sklearn.model_selection import train_test_split

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_PKL = REPO_ROOT / "regressor_microservice" / "sliced_model" / "xgboost_model.pkl"
TRAIN_CSV = REPO_ROOT / "data" / "train.csv"
OUT_DIR = REPO_ROOT / "artifacts"
OUT_DIR.mkdir(exist_ok=True)

TAXONOMY_COLS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# 1. Load pickleslicer bundle
# ---------------------------------------------------------------------------
print("Loading pickleslicer bundle...")
bundle = pickleslicer.load(str(MODEL_PKL))
model = bundle["model"]
print("  Model loaded.")

# ---------------------------------------------------------------------------
# 2. Export XGBoost model to binary UBJSON format
#    .ubj is ~25% smaller than .json and faster to load; still cross-platform
# ---------------------------------------------------------------------------
model_path = OUT_DIR / "model.ubj"
model.save_model(str(model_path))
size_gb = model_path.stat().st_size / 1e9
print(f"  Saved model → {model_path}  ({size_gb:.2f} GB)")

# ---------------------------------------------------------------------------
# 3. Rebuild calibration residuals
#    Mirrors the logic in predictive_models/decision_tree.py exactly so that
#    the residuals array is consistent with the stored model weights.
# ---------------------------------------------------------------------------
print("Rebuilding calibration residuals from train.csv...")
train = pd.read_csv(TRAIN_CSV)
train["mass_g"] = np.log10(train["mass_g"])

y_train_full = train["mass_g"]
x_train_full = train.drop(["mass_g"], axis=1)

# Replicate align_categories for training set (UNK + all training categories)
for col in TAXONOMY_COLS:
    x_train_full[col] = x_train_full[col].astype("category")
    cats = list(set(x_train_full[col].cat.categories) | {"UNK"})
    x_train_full[col] = x_train_full[col].cat.set_categories(cats)

# Same 80/20 split used during training (random_state=42 must match decision_tree.py)
x_train2, x_calib, y_train2, y_calib = train_test_split(
    x_train_full, y_train_full, test_size=0.2, random_state=42
)

y_calib_pred = model.predict(x_calib)
residuals = np.abs(y_calib.values - y_calib_pred)
residuals_sorted = sorted(float(r) for r in residuals)

calibration_path = OUT_DIR / "calibration.json"
with open(calibration_path, "w") as f:
    json.dump({"residuals": residuals_sorted}, f)
print(f"  Saved {len(residuals_sorted)} residuals → {calibration_path}")

# Sanity check: rebuilt 90th-pct q should match stored bundle value
q_rebuilt = float(np.quantile(residuals, 0.90))
q_stored = float(bundle["q"])
print(f"  q (rebuilt 90th pct): {q_rebuilt:.6f}  |  q (stored in bundle): {q_stored:.6f}")
if abs(q_rebuilt - q_stored) > 1e-4:
    raise RuntimeError(
        f"Rebuilt q ({q_rebuilt:.6f}) differs from stored q ({q_stored:.6f}) "
        "by more than 1e-4 — verify that random_state in this script matches "
        "decision_tree.py before uploading calibration.json."
    )

# ---------------------------------------------------------------------------
# 4. Extract category sets in training-time code order from model cats.enc
#    This ordering is critical: R's xgb.DMatrix uses 0-based factor codes,
#    so categories must be listed in the order the model assigned integer codes
#    during training. Alphabetical order (used before) caused wrong R predictions.
# ---------------------------------------------------------------------------
print("Extracting category sets from model (training-time code order)...")
booster = model.get_booster()
model_raw = json.loads(booster.save_raw(raw_format="json"))
cats_data = model_raw["learner"]["gradient_booster"]["model"]["cats"]
enc = cats_data["enc"]
feature_names_model = model_raw["learner"]["feature_names"]

categories = {}
for feat_idx, fname in enumerate(feature_names_model):
    e = enc[feat_idx]
    offsets = e["offsets"]
    values = e["values"]
    strings = [
        bytes(values[offsets[i] : offsets[i + 1]]).decode("utf-8") for i in range(len(offsets) - 1)
    ]
    categories[fname] = strings  # index == training-time integer code
    print(f"  {fname}: {len(strings)} categories (incl. UNK)")

categories_path = OUT_DIR / "categories.json"
with open(categories_path, "w") as f:
    json.dump(categories, f, indent=2)
print(f"  Saved categories → {categories_path}")

# ---------------------------------------------------------------------------
# 5. Compute per-file SHA256 checksums
# ---------------------------------------------------------------------------
print("Computing SHA256 checksums...")
checksums = {}
for fname, path in [
    ("model.ubj", model_path),
    ("calibration.json", calibration_path),
    ("categories.json", categories_path),
]:
    checksums[fname] = sha256_file(path)
    print(f"  {fname}: {checksums[fname]}")

checksums_path = OUT_DIR / "checksums.json"
with open(checksums_path, "w") as f:
    json.dump(checksums, f, indent=2)
print(f"  Written to {checksums_path}")

# ---------------------------------------------------------------------------
# 6. Instructions
# ---------------------------------------------------------------------------
print("""
Done. Upload the four files in artifacts/ to Hugging Face:

    pip install huggingface_hub
    huggingface-cli login
    huggingface-cli upload marknovak/TaxonBodyMassML artifacts/ . --repo-type model

Then copy the checksums from artifacts/checksums.json into the package
source files (Python: packages/python/taxonbodymassml/_checksums.py; R: packages/r/R/model.R).
""")
