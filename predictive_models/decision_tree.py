"""
pasquang
pasquang@oregonstate.edu
4/10/2026
"""

import datetime
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pickleslicer
import xgboost as xgb
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

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

# import training and testing data
train = pd.read_csv("./data/split/train.csv")
test = pd.read_csv("./data/split/test.csv")

# convert mass to log10 to avoid rounding error
# + reduce loss effect of large outliers
train["mass_g"] = np.log10(train["mass_g"])
test["mass_g"] = np.log10(test["mass_g"])

print("The Training Data is\n", train.head())
print("The Testing Data is\n", test.head())

# needs to remove other data when full taxonomy is created
# keep and remove labels from training and test data

y_train = train["mass_g"]
x_train = train.drop(["mass_g"], axis=1)

y_test = test["mass_g"]
x_test = test.drop(["mass_g"], axis=1)


def align_categories(train_df, test_df):
    """
    This function ensures that both the test and training set contain
    all unique categories from both sets for each column.
    It also adds

    Args:
        train_df (pandas dataframe): _description_
        test_df (pandas dataframe): _description_

    Returns:
        a tuple of the reformatted x_train and x_test with shared
        categories and UNK added
    """
    for col in train_df.select_dtypes(include="str").columns:
        train_df[col] = train_df[col].astype("category")
        test_df[col] = test_df[col].astype("category")

        # adds the UNK category and both train and test categories
        categories = list(
            set(train_df[col].cat.categories)
            | set(list(test_df[col].cat.categories))
            | {"UNK"}  # noqa: E501
        )

        train_df[col] = train_df[col].cat.set_categories(categories)
        test_df[col] = test_df[col].cat.set_categories(categories)

    return train_df, test_df


x_train, x_test = align_categories(x_train, x_test)

# define model hyperparameters
model = xgb.XGBRegressor(
    objective="reg:absoluteerror",
    enable_categorical=True,
    random_state=42,
    **BEST_PARAMS,
)

# train the model
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
    "hyperparameters": {
        "objective": "reg:absoluteerror",
        "enable_categorical": True,
        "random_state": 42,
        **BEST_PARAMS,
    },
    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
metrics_path = "predictive_models/results/metrics.json"
with open(metrics_path, "w") as f:
    json.dump(metrics, f, indent=2)
print(f"Metrics saved → {metrics_path}")

print("RMSE:", rmse)
print("R2 Score:", r2)

# need to convert log10 mass to actual mass
y_test = np.pow(10, y_test)
y_pred = np.pow(10, y_pred)

fig, ax = plt.subplots(figsize=(4.5, 4.5))
ax.scatter(
    y_test, y_pred, s=4.5, alpha=0.35, color="#0b0b0b", linewidths=0, rasterized=True
)  # noqa: E501
lims = [min(y_test.min(), y_pred.min()), max(y_test.max(), y_pred.max())]
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
    f"$R^2$ = {r2:.3f}\nRMSE = {rmse:.3f}\nMAE = {mae:.3f}"
    f"  ($\\log_{{10}}$ space)\n$n$ = {len(y_test):,}",
    transform=ax.transAxes,
    fontsize=8,
    va="top",
    color="#52514e",
)
fig.tight_layout()
fig.savefig(
    "predictive_models/results/xgboost_mass_prediction.png",
    dpi=300,
    bbox_inches="tight",
)
plt.close(fig)

mask = y_test > 0.1
y_test_f = y_test[mask]
y_pred_f = y_pred[mask]
r2_f = r2_score(np.log10(y_test_f), np.log10(y_pred_f))
rmse_f = float(np.sqrt(mean_squared_error(np.log10(y_test_f), np.log10(y_pred_f))))
mae_f = float(np.mean(np.abs(np.log10(y_test_f) - np.log10(y_pred_f))))
n_f = int(mask.sum())

print(
    f"Filtered metrics (mass > 0.1 g): "
    f"R2={r2_f:.4f}  RMSE={rmse_f:.4f}  MAE={mae_f:.4f}  n={n_f:,}"
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

fig2, ax2 = plt.subplots(figsize=(4.5, 4.5))
ax2.scatter(
    y_test_f,
    y_pred_f,
    s=4.5,
    alpha=0.35,
    color="#0b0b0b",
    linewidths=0,
    rasterized=True,  # noqa: E501
)
lims2 = [min(y_test_f.min(), y_pred_f.min()), max(y_test_f.max(), y_pred_f.max())]
ax2.plot(lims2, lims2, lw=1, color="#52514e", zorder=5)
ax2.set_xscale("log")
ax2.set_yscale("log")
ax2.set_xlabel("Actual body mass (g)", fontsize=9)
ax2.set_ylabel("Predicted body mass (g)", fontsize=9)
ax2.tick_params(labelsize=8, labelcolor="#0b0b0b", color="#c3c2b7", which="both")
for spine in ("top", "right"):
    ax2.spines[spine].set_visible(False)
ax2.spines["left"].set_color("#c3c2b7")
ax2.spines["bottom"].set_color("#c3c2b7")
ax2.text(
    0.04,
    0.96,
    f"$R^2$ = {r2_f:.3f}\nRMSE = {rmse_f:.3f}\nMAE = {mae_f:.3f}"
    f"  ($\\log_{{10}}$ space)\n$n$ = {mask.sum():,}  (mass $> 10^{{-1}}$ g)",
    transform=ax2.transAxes,
    fontsize=8,
    va="top",
    color="#52514e",
)
fig2.tight_layout()
fig2.savefig(
    "predictive_models/results/xgboost_mass_prediction_gt0.1g.png",
    dpi=300,
    bbox_inches="tight",
)
plt.close(fig2)

x_train2, x_calib, y_train2, y_calib = train_test_split(
    x_train, y_train, test_size=0.2, random_state=42
)

model.fit(x_train2, y_train2)

# compute calibration residuals
y_calib_pred = model.predict(x_calib)
calib_residuals = np.abs(y_calib - y_calib_pred)

# 90% interval
q = np.quantile(calib_residuals, 0.90)

# save BOTH model + q
pickleslicer.dump(
    {"model": model, "q": float(q)}, MODEL_WRITE_FILE, max_size=100 * 1024 * 1024
)  # noqa: E501
# pickleslicer.dump(model, MODEL_WRITE_FILE, max_size=100*1024*1024)

# Test if unknown values will cause the model to crash in eval
print("\n")
print("-" * 80)
print("\n")
for col in x_train.select_dtypes(include="category").columns:
    unk_test = x_test.iloc[[0]].copy()
    unk_test[col] = "UNK"
    unk_test[col] = pd.Categorical(
        unk_test[col], categories=x_train[col].cat.categories
    )  # noqa: E501
    print(unk_test)
    print("Ground Truth Mass:", y_test.iloc[0])
    pred = model.predict(unk_test)
    print("Predicted Log Mass:", pred)
    print("Predicted Mass:", np.pow(10, pred))
