import datetime
import json

import numpy as np
import optuna
import pandas as pd
import xgboost as xgb
from pathlib import Path
from sklearn.model_selection import KFold

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

N_TRIALS = 100
N_FOLDS = 5
SEED = 42


def align_categories(train_df, test_df):
    """
    This function ensures that both the test and training set contain
    all unique categories from both sets for each column.
    It also adds

    Args:
        train_df (pandas dataframe): _description_
        test_df (pandas dataframe): _description_

    Returns:
        a tuple of the reformatted x_train and x_test with shared categories and UNK added
    """
    for col in train_df.select_dtypes(include="str").columns:
        train_df[col] = train_df[col].astype("category")
        test_df[col] = test_df[col].astype("category")

        # adds the UNK category and both train and test categories
        categories = list(
            set(train_df[col].cat.categories) | set(list(test_df[col].cat.categories)) | {"UNK"}
        )

        train_df[col] = train_df[col].cat.set_categories(categories)
        test_df[col] = test_df[col].cat.set_categories(categories)

    return train_df, test_df


train = pd.read_csv(REPO_ROOT / "data" / "train.csv")
test = pd.read_csv(REPO_ROOT / "data" / "test.csv")
train["mass_g"] = np.log10(train["mass_g"])

y_full = train["mass_g"]
x_full = train.drop(["mass_g"], axis=1)
x_test = test.drop(["mass_g"], axis=1)

x_full, x_test = align_categories(x_full, x_test)

kf = KFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED)


def objective(trial):
    params = dict(
        objective="reg:absoluteerror",
        enable_categorical=True,
        random_state=SEED,
        n_estimators=trial.suggest_int("n_estimators", 200, 600, step=50),
        max_depth=trial.suggest_int("max_depth", 5, 50),
        learning_rate=trial.suggest_float("learning_rate", 0.01, 0.30, log=True),
        subsample=trial.suggest_float("subsample", 0.5, 1.0),
        colsample_bytree=trial.suggest_float("colsample_bytree", 0.5, 1.0),
        gamma=trial.suggest_float("gamma", 0.0, 1.0),
        min_child_weight=trial.suggest_int("min_child_weight", 1, 10),
    )
    fold_maes = []
    for train_idx, val_idx in kf.split(x_full):
        model = xgb.XGBRegressor(**params)
        model.fit(x_full.iloc[train_idx], y_full.iloc[train_idx])
        preds = model.predict(x_full.iloc[val_idx])
        fold_maes.append(float(np.mean(np.abs(y_full.iloc[val_idx] - preds))))
    return float(np.mean(fold_maes))


sampler = optuna.samplers.TPESampler(seed=SEED)
study = optuna.create_study(
    study_name="tbml_tuning",
    storage="sqlite:///" + str(RESULTS_DIR / "tuning.db"),
    direction="minimize",
    sampler=sampler,
    load_if_exists=True,
)
study.optimize(objective, n_trials=N_TRIALS, show_progress_bar=True)

results = {
    "best_params": study.best_params,
    "best_cv_mae": study.best_value,
    "n_trials": N_TRIALS,
    "n_folds": N_FOLDS,
    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "current_params": {
        "n_estimators": 600,
        "max_depth": 40,
        "learning_rate": 0.05,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "gamma": 0,
        "min_child_weight": 1,
    },
    "all_trials": [
        {"number": t.number, "params": t.params, "cv_mae": t.value}
        for t in study.trials
        if t.state == optuna.trial.TrialState.COMPLETE
    ],
}
out = RESULTS_DIR / "tuning_study.json"
with open(out, "w") as f:
    json.dump(results, f, indent=2)
print(f"\nBest CV MAE : {study.best_value:.4f} log10")
print(f"Best params : {study.best_params}")
print(f"Saved       -> {out}")
