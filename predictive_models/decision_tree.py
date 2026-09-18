"""
pasquang
pasquang@oregonstate.edu
4/10/2026

Train the TaxonBodyMassML XGBoost model on native categorical taxonomy
features (kingdom .. genus; see taxonomy_encoding.MODEL_FEATURES) and write the
pickleslicer bundle consumed by regressor_microservice/ and
scripts/export_artifacts.py.  The bundle also carries the species -> mass
dictionary so the microservice can return recorded masses for known species.

Run from the repository root:
    python predictive_models/decision_tree.py
"""

import datetime
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pickleslicer
import xgboost as xgb
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

sys.path.insert(0, str(Path(__file__).resolve().parent))
from taxonomy_encoding import (  # noqa: E402
    MODEL_FEATURES,
    RANKS_FINER,
    UNK,
    build_vocab,
    encode_categorical,
    validate_vocab,
)

MODEL_WRITE_FILE = "./regressor_microservice/sliced_model/xgboost_model.pkl"

_RESULTS_DIR = Path(__file__).resolve().parent / "results"
_TUNING_JSON = _RESULTS_DIR / "tuning_study.json"
_DEFAULT_PARAMS = {
    "n_estimators": 550,
    "max_depth": 43,
    "learning_rate": 0.11750844291262583,
    "subsample": 0.5320937649781214,
    "colsample_bytree": 0.6955159036504461,
    "gamma": 0.05647956497022174,
    "min_child_weight": 2,
}


def _load_best_params():
    if _TUNING_JSON.exists():
        with open(_TUNING_JSON) as f:
            return json.load(f)["best_params"]
    return dict(_DEFAULT_PARAMS)


BEST_PARAMS = _load_best_params()
FIXED_PARAMS = {"objective": "reg:absoluteerror", "enable_categorical": True, "random_state": 42}

# import training and testing data
train = pd.read_csv("./data/split/train.csv")
test = pd.read_csv("./data/split/test.csv")

# convert mass to log10 to avoid rounding error
# + reduce loss effect of large outliers
train["mass_g"] = np.log10(train["mass_g"])
test["mass_g"] = np.log10(test["mass_g"])

print("The Training Data is\n", train.head())
print("The Testing Data is\n", test.head())

# Vocabulary comes from the training split only; test-only taxa become UNK.
vocab = build_vocab(train)
validate_vocab(vocab)

y_train = train["mass_g"]
x_train = encode_categorical(train, vocab)  # columns in MODEL_FEATURES order

y_test = test["mass_g"]
x_test = encode_categorical(test, vocab)

assert list(x_train.columns) == MODEL_FEATURES


def make_model():
    return xgb.XGBRegressor(**FIXED_PARAMS, **BEST_PARAMS)


def mask_to_unk(x, cols):
    """Return a copy of x with the given columns set to UNK (same categories)."""
    x = x.copy()
    for col in cols:
        x[col] = pd.Categorical([UNK] * len(x), categories=vocab[col])
    return x


# ---------------------------------------------------------------------------
# 1. Conformal calibration on an 80/20 split of the training data.
#    Residuals must come from a model that has not seen the calibration rows,
#    so this fit happens first and the full-data fit below is the only other one.
# ---------------------------------------------------------------------------
x_train2, x_calib, y_train2, y_calib = train_test_split(
    x_train, y_train, test_size=0.2, random_state=42
)

calib_model = make_model()
calib_model.fit(x_train2, y_train2)

y_calib_pred = calib_model.predict(x_calib)
calib_residuals = np.abs(y_calib.values - y_calib_pred)
q = float(np.quantile(calib_residuals, 0.90))  # 90% interval half-width
calib_residuals_sorted = sorted(float(r) for r in calib_residuals)

# Per-rank residuals: mask finer ranks to UNK and re-predict, matching the
# inference condition for rank-level queries.
calib_by_rank = {}
for rank, finer_cols in RANKS_FINER.items():
    y_pred_rank = calib_model.predict(mask_to_unk(x_calib, finer_cols))
    res_rank = np.abs(y_calib.values - y_pred_rank)
    calib_by_rank[rank] = sorted(float(r) for r in res_rank)
    print(f"  calibration {rank:<8s} q90={np.quantile(res_rank, 0.90):.4f}")

del calib_model

# ---------------------------------------------------------------------------
# 2. Final model on the full training split.  Using the 80%-model's residuals
#    with the stronger full-data model makes intervals slightly conservative
#    (over-covers rather than under-covers).
# ---------------------------------------------------------------------------
model = make_model()
model.fit(x_train, y_train)

# evaluate the test set
y_pred = model.predict(x_test)

# evaluate in log space
rmse = np.sqrt(mean_squared_error(y_test, y_pred))
r2 = r2_score(y_test, y_pred)
mae = np.mean(np.abs(y_test - y_pred))

metrics = {
    "r2": float(r2),
    "rmse": float(rmse),
    "mae": float(mae),
    "n_train": len(y_train),
    "n_test": len(y_test),
    "log10_space": True,
    "features": MODEL_FEATURES,
    "encoding": "native categorical (enable_categorical=True); vocab = UNK + sorted train values",
    "q90": q,
    "hyperparameters": {**FIXED_PARAMS, **BEST_PARAMS},
    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
metrics_path = "predictive_models/results/metrics.json"

print("RMSE:", rmse)
print("R2 Score:", r2)
print("MAE:", mae)

# need to convert log10 mass to actual mass
y_test = np.pow(10, y_test)
y_pred = np.pow(10, y_pred)


def scatter_plot(y_true, y_hat, r2_v, rmse_v, mae_v, n_label, path):
    fig, ax = plt.subplots(figsize=(4.5, 4.5))
    ax.scatter(y_true, y_hat, s=4.5, alpha=0.35, color="#0b0b0b", linewidths=0, rasterized=True)
    lims = [min(y_true.min(), y_hat.min()), max(y_true.max(), y_hat.max())]
    ax.plot(lims, lims, lw=1, color="#52514e", zorder=5)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Actual body mass (g)", fontsize=9)
    ax.set_ylabel("Predicted body mass (g)", fontsize=9)
    ax.tick_params(labelsize=8, labelcolor="#0b0b0b", color="#c3c2b7", which="both")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#c3c2b7")
    ax.spines["bottom"].set_color("#c3c2b7")
    ax.text(
        0.04,
        0.96,
        f"$R^2$ = {r2_v:.3f}\nRMSE = {rmse_v:.3f}\nMAE = {mae_v:.3f}"
        f"  ($\\log_{{10}}$ space)\n{n_label}",
        transform=ax.transAxes,
        fontsize=8,
        va="top",
        color="#52514e",
    )
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


scatter_plot(
    y_test,
    y_pred,
    r2,
    rmse,
    mae,
    f"$n$ = {len(y_test):,}",
    "predictive_models/results/xgboost_mass_prediction.png",
)

mask = y_test > 0.1
y_test_f = y_test[mask]
y_pred_f = y_pred[mask]
r2_f = r2_score(np.log10(y_test_f), np.log10(y_pred_f))
rmse_f = float(np.sqrt(mean_squared_error(np.log10(y_test_f), np.log10(y_pred_f))))
mae_f = float(np.mean(np.abs(np.log10(y_test_f) - np.log10(y_pred_f))))
n_f = int(mask.sum())

print(
    f"Filtered metrics (mass > 0.1 g): R2={r2_f:.4f}  RMSE={rmse_f:.4f}  MAE={mae_f:.4f}  n={n_f:,}"
)
metrics["filtered_gt0p1g"] = {
    "r2": float(r2_f),
    "rmse": rmse_f,
    "mae": mae_f,
    "n": n_f,
    "filter": "mass_g > 0.1",
    "log10_space": True,
}
with open(metrics_path, "w") as f:
    json.dump(metrics, f, indent=2)
print(f"Metrics saved → {metrics_path}")

scatter_plot(
    y_test_f,
    y_pred_f,
    r2_f,
    rmse_f,
    mae_f,
    f"$n$ = {n_f:,}  (mass $> 10^{{-1}}$ g)",
    "predictive_models/results/xgboost_mass_prediction_gt0.1g.png",
)

# ---------------------------------------------------------------------------
# 3. Save the bundle: model, q, vocab, calibration residuals and the species
#    dictionary (species -> {mass_g, source}) built from the raw training data,
#    keyed by space-normalised species name exactly like artifacts/lookup.json.
#    pickleslicer only writes the slices it needs and never removes older ones,
#    so clear stale slices first or pickleslicer.load will concatenate them.
# ---------------------------------------------------------------------------
write_path = Path(MODEL_WRITE_FILE)
write_path.parent.mkdir(parents=True, exist_ok=True)
for stale in write_path.parent.glob(write_path.name + ".*"):
    stale.unlink()

raw = pd.read_csv("./data/TaxonBodyMass.csv")
raw["_key"] = raw["taxon"].astype(str).str.replace("_", " ", regex=False)
raw = raw.drop_duplicates(subset="_key", keep="first")
lookup = {
    row["_key"]: {"mass_g": float(row["mass_g"]), "source": str(row["source_mass"])}
    for _, row in raw.iterrows()
}

pickleslicer.dump(
    {
        "model": model,
        "q": q,
        "vocab": vocab,
        "calib_residuals": calib_residuals_sorted,
        "calib_residuals_by_rank": calib_by_rank,
        "lookup": lookup,
    },
    MODEL_WRITE_FILE,
    max_size=100 * 1024 * 1024,
)
print(f"Bundle saved → {MODEL_WRITE_FILE}.*  (q90={q:.4f})")

# Test if unknown values will cause the model to crash in eval
print("\n" + "-" * 80 + "\n")
for col in MODEL_FEATURES:
    unk_test = mask_to_unk(x_test.iloc[[0]], [col])
    print(unk_test)
    print("Ground Truth Mass:", y_test.iloc[0])
    pred = model.predict(unk_test)
    print("Predicted Log Mass:", pred)
    print("Predicted Mass:", np.pow(10, pred))
