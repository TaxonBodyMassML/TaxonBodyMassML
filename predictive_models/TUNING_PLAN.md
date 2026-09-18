# Plan: Automated Hyperparameter Tuning (Option A: Optuna, 5-fold CV)

## Context

`predictive_models/decision_tree.py` uses manually chosen XGBoost hyperparameters with no
automated tuning. This plan adds a standalone tuning script that searches the hyperparameter
space using Optuna (Bayesian TPE sampler) with 5-fold cross-validation scored by MAE in
log₁₀ space — matching the training objective (`reg:absoluteerror`). The best parameters
are saved to a JSON file for review; `decision_tree.py` is then updated manually with the
chosen values.

---

## Files to Create or Modify

| Action | File |
|---|---|
| **Create** | `predictive_models/tune_hyperparameters.py` |
| **Create** | `predictive_models/requirements.txt` |
| **Update** | `ms/XGBoost_Training_Summary.md` — document the tuning procedure |
| **Update** | `predictive_models/decision_tree.py` — apply best params after reviewing results |
| **Output** | `predictive_models/results/tuning_study_ee.json` — Entity Embeddings Stage 2 tuning results |

---

## 1. `predictive_models/requirements.txt` (new)

The training virtualenv currently lacks `sklearn` and `optuna` (both absent from the
default env per environment check). Create a dedicated requirements file for the
`predictive_models/` scripts:

```
numpy>=1.24
pandas>=1.5
xgboost>=3.2
scikit-learn>=1.3
optuna>=3.0
pickleslicer
matplotlib
```

Install via: `pip install -r predictive_models/requirements.txt`

---

## 2. `predictive_models/tune_hyperparameters.py` (new)

### Paths and constants (top of file)

```python
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

N_TRIALS = 100
N_FOLDS  = 5
SEED     = 42
```

Use `Path(__file__).resolve()` throughout — the current script uses bare relative paths
(`"./data/train.csv"`) that only work when invoked from the repo root; the new script
should be runnable from anywhere.

### Data loading and category alignment

```python
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import KFold
import optuna, json, datetime

train = pd.read_csv(REPO_ROOT / "data" / "train.csv")
test  = pd.read_csv(REPO_ROOT / "data" / "test.csv")
train["mass_g"] = np.log10(train["mass_g"])

y_full = train["mass_g"]
x_full = train.drop(["mass_g"], axis=1)
x_test = test.drop(["mass_g"], axis=1)
```

**Copy `align_categories` verbatim from `decision_tree.py`** and call it once:

```python
x_full, x_test = align_categories(x_full, x_test)
```

This is correct for KFold: after the call every column is dtype `category` carrying the
full-training-set union vocabulary (including `"UNK"`). KFold slices of `x_full` inherit
that vocabulary via pandas `Categorical` dtype preservation, so XGBoost sees the same
integer encoding on every fold without any per-fold re-alignment. Do **not** call
`align_categories` inside the fold loop — after the first call it would silently no-op
(all columns are already dtype `category`, not `object`).

### KFold setup

```python
kf = KFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED)
```

### Optuna objective function

```python
def objective(trial):
    params = dict(
        objective          = "reg:absoluteerror",  # fixed — matches training
        enable_categorical = True,                  # fixed — native encoding of kingdom..genus (taxonomy_encoding.py)
        random_state       = SEED,
        n_estimators       = trial.suggest_int  ("n_estimators",     200, 900, step=50),
        max_depth          = trial.suggest_int  ("max_depth",           5,  50),
        learning_rate      = trial.suggest_float("learning_rate",    0.01, 0.30, log=True),
        subsample          = trial.suggest_float("subsample",         0.5,  1.0),
        colsample_bytree   = trial.suggest_float("colsample_bytree",  0.5,  1.0),
        gamma              = trial.suggest_float("gamma",             0.0,  1.0),
        min_child_weight   = trial.suggest_int  ("min_child_weight",    1,  10),
    )
    fold_maes = []
    for train_idx, val_idx in kf.split(x_full):
        model = xgb.XGBRegressor(**params)
        model.fit(x_full.iloc[train_idx], y_full.iloc[train_idx])
        preds = model.predict(x_full.iloc[val_idx])
        fold_maes.append(float(np.mean(np.abs(y_full.iloc[val_idx] - preds))))
    return float(np.mean(fold_maes))
```

**Why `n_estimators` tops out at 900**: the first study (ceiling 600) selected the
ceiling, so the range was widened. The species-free study (September 2026) selected
850 with the top five trials spread over 600–850, so the ceiling is no longer binding.
Searching further would double per-trial wall time for little likely gain.

**Why `gamma` and `min_child_weight` are included**: `max_depth=40` is unusually large
and may overfit; these regularization parameters can offset that without forcing a lower
depth.

`reg_alpha` and `reg_lambda` are excluded to keep the search space manageable.

### Study creation and optimization

```python
sampler = optuna.samplers.TPESampler(seed=SEED)
study = optuna.create_study(direction="minimize", sampler=sampler)
study.optimize(objective, n_trials=N_TRIALS, show_progress_bar=True)
```

### Save results

```python
results = {
    "best_params":    study.best_params,
    "best_cv_mae":    study.best_value,
    "n_trials":       N_TRIALS,
    "n_folds":        N_FOLDS,
    "timestamp":      datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "current_params": {          # baseline for comparison
        "n_estimators": 600, "max_depth": 40, "learning_rate": 0.05,
        "subsample": 0.8, "colsample_bytree": 0.8, "gamma": 0,
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
```

---

## 3. After the tuning run — applying best parameters

1. Review `predictive_models/results/tuning_study.json`. Compare `best_cv_mae` against
   the current model's test MAE (in `predictive_models/results/metrics.json` after the
   next training run).
2. If the tuned parameters improve MAE, update the `xgb.XGBRegressor(...)` block in
   `decision_tree.py` and re-run training to regenerate all artifacts.
3. Run `scripts/export_artifacts.py` to rebuild the model bundle.

---

## 4. `ms/XGBoost_Training_Summary.md` — updates

Add a new **Hyperparameter Tuning** section (after the Hyperparameters table):

- Tool: Optuna 3.x, TPE sampler, `seed=42`
- Folds: 5-fold CV (`sklearn.model_selection.KFold`, `shuffle=True`, `random_state=42`)
- Metric: mean absolute error in log₁₀ space (matches `reg:absoluteerror`)
- Trials: 100
- Fixed parameters: `objective`, `enable_categorical`, `random_state`
- Search space: the seven parameters and ranges listed in Section 2 above
- Results file: `predictive_models/results/tuning_study.json`

---

## Runtime estimate

Each fold fit: ~34,055 × 0.8 rows, up to 600-tree XGBoost ≈ 30–90 s on a laptop CPU.
100 trials × 5 folds × ~60 s/fold ≈ **8–25 hours**.

To do a quick feasibility check first, temporarily set `N_TRIALS = 3, N_FOLDS = 2` and
verify the script runs without error before committing to the full study.

Optuna studies are resumable: save the study to an SQLite backend and re-launch with
the same `study_name` to continue from where a previous run stopped:

```python
study = optuna.create_study(
    study_name="tbml_tuning",
    storage="sqlite:///predictive_models/results/tuning.db",
    direction="minimize",
    sampler=sampler,
    load_if_exists=True,
)
```

---

## Verification

1. `pip install -r predictive_models/requirements.txt` — no errors.
2. Temporarily set `N_TRIALS=3, N_FOLDS=2`; run `python predictive_models/tune_hyperparameters.py`
   from the repo root — completes without error and writes
   `predictive_models/results/tuning_study.json` with the expected structure.
3. Restore `N_TRIALS=100, N_FOLDS=5` and run the full study.
4. Review the JSON output; if best params differ materially from current, apply them
   to `decision_tree.py`, re-train, confirm `predictive_models/results/metrics.json`
   shows improved MAE.

---

## 5. Entity Embeddings Stage 2 Hyperparameter Tuning

### Context

`entity_embeddings_model.py` uses a fixed XGBoost configuration for Stage 2 (the head
trained on embedding features). Stage 1 (the PyTorch MLP) is expensive to run repeatedly,
so the tuner pre-trains it once on the full training set, extracts the 116-dimensional
embedding feature matrix, and then runs KFold CV solely on Stage 2. This correctly
isolates Stage 2 parameters while keeping wall time reasonable.

### Running the tuner

```bash
python predictive_models/tune_hyperparameters.py --model ee
```

Stage 1 MLP training (~100 epochs) runs once at startup and is printed as progress.
All 100 × 5 Optuna trials operate on the cached embedding matrix.

### Search space

| Parameter | Type | Range | Fixed |
|---|---|---|---|
| `n_estimators` | int (step 50) | 200 – 800 | |
| `max_depth` | int | 4 – 15 | |
| `learning_rate` | float (log) | 0.01 – 0.30 | |
| `subsample` | float | 0.5 – 1.0 | |
| `colsample_bytree` | float | 0.5 – 1.0 | |
| `min_child_weight` | int | 1 – 10 | |
| `objective` | — | — | `"reg:absoluteerror"` |
| `random_state` | — | — | `42` |

`colsample_bytree` is added relative to the current `STAGE2_PARAMS` because with 84
continuous embedding features (kingdom..genus; species is not a feature) it is a
meaningful regularizer. `enable_categorical` is
not set (features are continuous floats).

### Current baseline (from `entity_embeddings_model.py`)

```python
STAGE2_PARAMS = {
    "n_estimators":  400,
    "max_depth":     8,
    "learning_rate": 0.1,
    "subsample":     0.8,
}
```

### Output files

- `predictive_models/results/tuning_ee.db` — resumable Optuna SQLite study
- `predictive_models/results/tuning_study_ee.json` — best params, CV MAE, all trials

### Applying results

1. Review `tuning_study_ee.json`. Compare `best_cv_mae` against test MAE in
   `predictive_models/results/metrics_ee.json`.
2. If improved, update `STAGE2_PARAMS` in `entity_embeddings_model.py` (add
   `colsample_bytree` and `min_child_weight` if they appear in the best params).
3. Re-run `python predictive_models/entity_embeddings_model.py` to regenerate artifacts.

### Runtime estimate

Stage 1 MLP pre-train: ~5–10 minutes on CPU (or ~1–2 min on GPU).
100 trials × 5 folds × ~10–30 s/fold ≈ **1–3 hours** on a laptop CPU.
Use `N_TRIALS=3, N_FOLDS=2` for a smoke test first.
