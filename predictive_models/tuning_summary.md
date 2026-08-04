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
| Min (best) | **0.2968** |
| 25th percentile | 0.3051 |
| Median | 0.3080 |
| 75th percentile | 0.3185 |
| Max (worst) | 0.4411 |

Best trial: 94 (CV MAE 0.2968)

### Best vs. baseline parameters

| Parameter | Baseline | Best tuned | Change |
|---|---|---|---|
| `n_estimators` | 450 | 600 | +150 (ceiling hit) |
| `max_depth` | 29 | 30 | +1 |
| `learning_rate` | 0.0523 | 0.0327 | ↓ slower |
| `subsample` | 0.7846 | 0.6547 | ↓ lower |
| `colsample_bytree` | 0.8769 | 0.9007 | ↑ slightly higher |
| `gamma` | 0.2358 | 0.0561 | ↓ much lower |
| `min_child_weight` | 1 | 1 | — |

### Key observations

- `n_estimators` hit the search space ceiling (600). If a follow-up run is warranted,
  widen to 800–1,000 to check whether more trees help.
- `learning_rate` dropped (0.052 → 0.033) paired with more trees — classic shrinkage
  tradeoff: more, smaller steps improve generalization.
- `gamma` dropped sharply (0.236 → 0.056), indicating less aggressive leaf-pruning is
  preferred with the expanded dataset.
- `subsample` decreased (0.785 → 0.655) — more aggressive row subsampling per tree,
  which increases variance reduction.
