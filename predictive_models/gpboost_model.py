"""
Train a GPBoost model (LightGBM trees + nested taxonomic random effects).

Run from any directory:
    python predictive_models/gpboost_model.py

Outputs (in artifacts/):
    model_gpboost.json              -- GPBoost model (tree + GP parameters + BLUPs)
    calibration_gpboost.json         -- pooled conformal calibration residuals
    calibration_by_rank_gpboost.json -- rank-stratified calibration residuals

Requirements:
    pip install gpboost>=1.5
"""

import datetime
import json
from pathlib import Path

import gpboost as gpb
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

REPO_ROOT = Path(__file__).resolve().parents[1]
TRAIN_CSV = REPO_ROOT / "data" / "split" / "train.csv"
TEST_CSV = REPO_ROOT / "data" / "split" / "test.csv"
OUT_DIR = REPO_ROOT / "artifacts"
RESULTS_DIR = REPO_ROOT / "predictive_models" / "results"
OUT_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)

TAXONOMY_COLS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
# 5 nested random effect levels (finest → coarsest): species RE shrinks toward genus RE, etc.  # noqa: E501
GROUP_COLS = ["species", "genus", "family", "order", "class"]

_TUNING_JSON = RESULTS_DIR / "tuning_study_gpboost.json"
_DEFAULT_BOOST_PARAMS = {
    "learning_rate": 0.05,
    "max_depth": 12,
    "num_leaves": 127,
    "min_data_in_leaf": 1,
}
_DEFAULT_NBR = 500


def _load_best_params():
    if _TUNING_JSON.exists():
        with open(_TUNING_JSON) as f:
            best = json.load(f)["best_params"]
        nbr = best.pop("num_boost_round", _DEFAULT_NBR)
        return best, nbr
    return dict(_DEFAULT_BOOST_PARAMS), _DEFAULT_NBR


_best_lgbm, NUM_BOOST_ROUND = _load_best_params()
PARAMS = {
    "objective": "regression_l1",
    "verbose": -1,
    **_best_lgbm,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_split(train_csv: Path, test_csv: Path):
    train = pd.read_csv(train_csv)
    test = pd.read_csv(test_csv)
    train["mass_g"] = np.log10(train["mass_g"])
    test["mass_g"] = np.log10(test["mass_g"])
    return train, test


def align_and_prepare(train_df: pd.DataFrame, test_df: pd.DataFrame):
    """Align categorical levels across train and test; fill missing with UNK."""
    X_train = train_df[TAXONOMY_COLS].copy()
    X_test = test_df[TAXONOMY_COLS].copy()
    for col in TAXONOMY_COLS:
        X_train[col] = X_train[col].fillna("UNK")
        X_test[col] = X_test[col].fillna("UNK")
        all_cats = list(
            set(X_train[col].unique()) | set(X_test[col].unique()) | {"UNK"}
        )  # noqa: E501
        X_train[col] = pd.Categorical(X_train[col], categories=all_cats)
        X_test[col] = pd.Categorical(X_test[col], categories=all_cats)
    return X_train, X_test


def build_group_data(df: pd.DataFrame, species_col: str = "species") -> np.ndarray:
    """Return (n, 5) string array for the 5 nested random effect grouping levels."""
    cols = [species_col, "genus", "family", "order", "class"]
    gd = df[cols].fillna("UNK").astype(str)
    return gd.to_numpy()


def train_gpboost(X: pd.DataFrame, y: np.ndarray, group_data: np.ndarray):
    gp_model = gpb.GPModel(group_data=group_data, likelihood="gaussian")
    gp_model.set_optim_params({"optimizer_cov": "lbfgs", "use_nesterov_acc": True})
    dataset = gpb.Dataset(X, label=y, group_data=group_data, free_raw_data=False)
    booster = gpb.train(
        params=PARAMS,
        train_set=dataset,
        gp_model=gp_model,
        num_boost_round=NUM_BOOST_ROUND,
    )
    return booster


# ---------------------------------------------------------------------------
# 1. Load and prepare data
# ---------------------------------------------------------------------------
print("Loading data...")
train, test = load_split(TRAIN_CSV, TEST_CSV)

y_train = train["mass_g"].values
y_test = test["mass_g"].values
X_train, X_test = align_and_prepare(train, test)

gd_train = build_group_data(train)
gd_test = build_group_data(test)

print(f"  Training: {len(y_train):,}  Test: {len(y_test):,}")


# ---------------------------------------------------------------------------
# 2. Conformal calibration (80/20 split of training set)
#    Train on 80%, evaluate on 20% to get calibration residuals.
# ---------------------------------------------------------------------------
print("Computing conformal calibration residuals (80/20 split)...")
idx_all = np.arange(len(y_train))
idx_tr2, idx_calib = train_test_split(idx_all, test_size=0.2, random_state=42)

X_tr2 = X_train.iloc[idx_tr2].reset_index(drop=True)
X_calib = X_train.iloc[idx_calib].reset_index(drop=True)
y_tr2 = y_train[idx_tr2]
y_calib = y_train[idx_calib]
gd_tr2 = gd_train[idx_tr2]
gd_cal = gd_train[idx_calib]

booster_calib = train_gpboost(X_tr2, y_tr2, gd_tr2)
calib_preds = booster_calib.predict(data=X_calib, group_data_pred=gd_cal)
calib_residuals = sorted(float(r) for r in np.abs(y_calib - calib_preds))

calibration_path = OUT_DIR / "calibration_gpboost.json"
with open(calibration_path, "w") as f:
    json.dump({"residuals": calib_residuals}, f)
print(f"  {len(calib_residuals)} residuals → {calibration_path}")
print(f"  q90 = {float(np.quantile(calib_residuals, 0.90)):.4f} log10 units")

# Rank-stratified calibration: mask finer-rank columns and group_data levels.
# GROUP_COLS = ["species", "genus", "family", "order", "class"] (indices 0-4).
print("Building rank-stratified calibration residuals for GPBoost...")
RANKS_FINER_GPB = {
    "genus": (["species"], [0]),
    "family": (["genus", "species"], [0, 1]),
    "order": (["family", "genus", "species"], [0, 1, 2]),
    "class": (["order", "family", "genus", "species"], [0, 1, 2, 3]),
    "phylum": (["class", "order", "family", "genus", "species"], [0, 1, 2, 3, 4]),
    "kingdom": (
        ["phylum", "class", "order", "family", "genus", "species"],
        [0, 1, 2, 3, 4],
    ),  # noqa: E501
}
by_rank_gpb = {}
for rank, (finer_cols, gd_cols) in RANKS_FINER_GPB.items():
    X_masked = X_calib.copy()
    for col in finer_cols:
        if col in X_masked.columns:
            X_masked[col] = pd.Categorical(
                ["UNK"] * len(X_masked), categories=X_calib[col].cat.categories
            )
    gd_masked = gd_cal.copy()
    for idx in gd_cols:
        gd_masked[:, idx] = "MASKED_UNK"
    rank_preds = booster_calib.predict(data=X_masked, group_data_pred=gd_masked)
    res_rank = np.abs(y_calib - rank_preds)
    by_rank_gpb[rank] = sorted(float(r) for r in res_rank)
    print(f"  {rank}: q90={float(np.quantile(res_rank, 0.90)):.4f}")

by_rank_gpb_path = OUT_DIR / "calibration_by_rank_gpboost.json"
with open(by_rank_gpb_path, "w") as f:
    json.dump(by_rank_gpb, f)
print(f"  Saved → {by_rank_gpb_path}")


# ---------------------------------------------------------------------------
# 3. Train final model on full training set
# ---------------------------------------------------------------------------
print("Training final GPBoost model on full training set...")
booster = train_gpboost(X_train, y_train, gd_train)


# ---------------------------------------------------------------------------
# 4. Evaluate on test set
# ---------------------------------------------------------------------------
log_preds_test = booster.predict(data=X_test, group_data_pred=gd_test)
mae = float(mean_absolute_error(y_test, log_preds_test))
rmse = float(np.sqrt(mean_squared_error(y_test, log_preds_test)))
r2 = float(r2_score(y_test, log_preds_test))
print(f"Test  MAE={mae:.4f}  RMSE={rmse:.4f}  R²={r2:.4f}  (log10 space)")


# ---------------------------------------------------------------------------
# 5. Save model
# ---------------------------------------------------------------------------
model_path = OUT_DIR / "model_gpboost.json"
booster.save_model(str(model_path))
print(f"Saved model → {model_path}")


# ---------------------------------------------------------------------------
# 6. Save metrics
# ---------------------------------------------------------------------------
metrics = {
    "method": "GPBoost",
    "r2": r2,
    "rmse": rmse,
    "mae": mae,
    "n_train": int(len(y_train)),
    "n_test": int(len(y_test)),
    "log10_space": True,
    "num_boost_round": NUM_BOOST_ROUND,
    "params": PARAMS,
    "group_cols": GROUP_COLS,
    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
metrics_path = RESULTS_DIR / "metrics_gpboost.json"
with open(metrics_path, "w") as f:
    json.dump(metrics, f, indent=2)
print(f"Metrics → {metrics_path}")
print("Done.")
