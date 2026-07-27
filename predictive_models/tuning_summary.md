# Hyperparameter Tuning Summary — TaxonBodyMassML

**Script**: `predictive_models/tune_hyperparameters.py`
**Results file**: `predictive_models/results/tuning_study.json`
**Study database**: `predictive_models/results/tuning.db` (Optuna SQLite backend; resumable)

---

## Method

| Setting | Value |
|---|---|
| Tool | Optuna 4.9.0, TPE sampler (`seed=42`) |
| Folds | 5-fold CV (`sklearn.model_selection.KFold`, `shuffle=True`, `random_state=42`) |
| Metric | Mean absolute error in log₁₀ space (matches `reg:absoluteerror` training objective) |
| Trials | 100 |
| Fixed parameters | `objective`, `enable_categorical`, `random_state` |

---

## Search Space

| Parameter | Range | Notes |
|---|---|---|
| `n_estimators` | 200–600 (step 50) | Upper bound = current hand-tuned value; widen if best trial consistently hits 600 |
| `max_depth` | 5–50 | Current value (40) is unusually large; included to explore regularization tradeoff |
| `learning_rate` | 0.01–0.30 (log scale) | |
| `subsample` | 0.5–1.0 | Row sampling per tree |
| `colsample_bytree` | 0.5–1.0 | Feature sampling per tree |
| `gamma` | 0.0–1.0 | Minimum loss reduction to split; can offset large `max_depth` |
| `min_child_weight` | 1–10 | |

`reg_alpha` and `reg_lambda` excluded to keep the search space manageable.

---

## Results

### Trial distribution (CV MAE, log₁₀ space, 100 trials)

| Statistic | Value |
|---|---|
| Min (best) | **0.2703** |
| 25th percentile | 0.2802 |
| Median | 0.3049 |
| 75th percentile | 0.3318 |
| Max (worst) | 0.4802 |

### Best vs. baseline parameters

| Parameter | Baseline | Best tuned | Change |
|---|---|---|---|
| `n_estimators` | 600 | 600 | — |
| `max_depth` | 40 | 42 | +2 |
| `learning_rate` | 0.05 | 0.0278 | ↓ slower |
| `subsample` | 0.8 | 0.9808 | ↑ higher |
| `colsample_bytree` | 0.8 | 0.9339 | ↑ higher |
| `gamma` | 0 (default) | 0.8239 | ↑ much higher |
| `min_child_weight` | 1 (default) | 1 | — |

### Key observations

- `n_estimators` hit the search space ceiling (600). If a follow-up run is warranted,
  widen to 800–1,000 to check whether more trees help.
- `gamma` increased sharply from 0 to 0.824 — the tuner found that enforcing a
  minimum loss reduction per split is beneficial, likely compensating for the large
  `max_depth`.
- `learning_rate` dropped from 0.05 to 0.028, consistent with the higher-density
  row/column sampling (subsample and colsample_bytree both increased): slower steps
  are more stable when sampling is denser.

---

## Next Steps

1. Apply the best parameters to `predictive_models/decision_tree.py`.
2. Re-run training; compare test-set MAE from `predictive_models/results/metrics.json`
   against the CV MAE reported here (0.2703 is a cross-validated estimate on the
   training set, not the held-out test set).
3. Run `scripts/export_artifacts.py` to rebuild the model bundle for distribution.
