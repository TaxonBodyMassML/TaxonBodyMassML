# Hyperparameter Tuning Summary — TaxonBodyMassML

**Script**: `predictive_models/tune_hyperparameters.py` (`--model xgb` | `--model ee`)
**Results files**: `predictive_models/results/tuning_study.json`, `predictive_models/results/tuning_study_ee.json`
**Study databases**: `predictive_models/results/tuning.db`, `tuning_ee.db` (Optuna SQLite backend; resumable; git-ignored)

Both studies below were run on 2026-09-17 after species was removed from the
feature set of both models (features are `kingdom` .. `genus`; see
`predictive_models/taxonomy_encoding.py`). An earlier study that included
species as a feature reached a lower CV MAE (0.2968) but that value is not
comparable: with one training row per species the species feature memorises
rows that reappear in the CV validation folds through shared genera, and the
resulting fits were not reproducible across category orderings.

---

## Method

| Setting | Value |
|---|---|
| Tool | Optuna 4.x, TPE sampler (`seed=42`) |
| Folds | 5-fold CV (`sklearn.model_selection.KFold`, `shuffle=True`, `random_state=42`) |
| Metric | Mean absolute error in log₁₀ space (matches `reg:absoluteerror` training objective) |
| Trials | 100 per model (`TBM_N_TRIALS` overrides) |
| Data | `data/split/train.csv` only; the test split is never seen by the tuner |

---

## XGBoost (direct, native categorical splits)

Fixed parameters: `objective="reg:absoluteerror"`, `enable_categorical=True`, `random_state=42`.

### Search space

| Parameter | Range |
|---|---|
| `n_estimators` | 200–900 (step 50) |
| `max_depth` | 5–50 |
| `learning_rate` | 0.01–0.30 (log scale) |
| `subsample` | 0.5–1.0 |
| `colsample_bytree` | 0.5–1.0 |
| `gamma` | 0.0–1.0 |
| `min_child_weight` | 1–10 |

`reg_alpha` and `reg_lambda` excluded to keep the search space manageable.

### Trial distribution (CV MAE, log₁₀ space, 100 trials)

| Statistic | Value |
|---|---|
| Min (best) | **0.3438** |
| 25th percentile | 0.3462 |
| Median | 0.3494 |
| 75th percentile | 0.3583 |
| Max (worst) | 0.4574 |

Best trial: 82.

### Best vs. baseline parameters

| Parameter | Baseline (`current_params`) | Best tuned |
|---|---|---|
| `n_estimators` | 600 | 850 |
| `max_depth` | 40 | 39 |
| `learning_rate` | 0.05 | 0.0682 |
| `subsample` | 0.8 | 0.5418 |
| `colsample_bytree` | 0.8 | 0.7663 |
| `gamma` | 0 | 0.4689 |
| `min_child_weight` | 1 | 2 |

### Observations

- The top five trials span `n_estimators` 600–850 and `max_depth` 36–39 with CV MAE
  within 0.0005 of each other, so the optimum is flat and the `n_estimators` ceiling
  (900) is not binding.
- Deep trees remain preferred. With native categorical splits on genus (thousands of
  levels) each split can isolate a set of genera, so depth acts as the main capacity
  control and is what makes `model.ubj` large (~0.6 GB).
- `subsample` dropped to 0.54 and `gamma` rose to 0.47: stronger row subsampling and
  leaf pruning compensate for the depth.
- Held-out test set after retraining with the best parameters
  (`predictive_models/results/metrics.json`): MAE 0.357, RMSE 0.607, R² 0.906.

---

## Entity Embeddings (Stage 2 XGBoost on 84-dim embedding vectors)

Stage 1 (embedding MLP) is trained once with fixed settings and its embedding matrix is
cached; all trials tune the Stage 2 regressor. Fixed parameters:
`objective="reg:absoluteerror"`, `random_state=42`.

### Search space

| Parameter | Range |
|---|---|
| `n_estimators` | 200–800 (step 50) |
| `max_depth` | 4–15 |
| `learning_rate` | 0.01–0.30 (log scale) |
| `subsample` | 0.5–1.0 |
| `colsample_bytree` | 0.5–1.0 |
| `min_child_weight` | 1–10 |

### Trial distribution (CV MAE, log₁₀ space, 100 trials)

| Statistic | Value |
|---|---|
| Min (best) | **0.3199** |
| 25th percentile | 0.3210 |
| Median | 0.3225 |
| 75th percentile | 0.3248 |
| Max (worst) | 0.4254 |

Best trial: 67.

### Best vs. baseline parameters

| Parameter | Baseline (`current_params`) | Best tuned |
|---|---|---|
| `n_estimators` | 400 | 800 |
| `max_depth` | 8 | 15 |
| `learning_rate` | 0.1 | 0.0366 |
| `subsample` | 0.8 | 0.7151 |
| `colsample_bytree` | — | 0.7468 |
| `min_child_weight` | — | 10 |

### Observations

- The best trial sits at the ceiling of both `n_estimators` (800) and `max_depth`
  (15), and the top five trials all use `max_depth` 15 with `n_estimators` 750–800.
  A follow-up study could widen both ranges, though the gap between the best and the
  25th-percentile trial is only 0.001, so the expected gain is small.
- `min_child_weight` at its maximum (10) with a low learning rate indicates the
  Stage 2 model benefits from smoothing over the continuous embedding features.
- Held-out test set after retraining with the best parameters
  (`predictive_models/results/metrics_ee.json`): MAE 0.329, RMSE 0.564, R² 0.918;
  Stage 1 MLP alone MAE 0.368.

---

## Applying the results

Both training scripts read `best_params` from their tuning JSON at import time
(`decision_tree.py` from `tuning_study.json`, `entity_embeddings_model.py` from
`tuning_study_ee.json`) and fall back to hard-coded defaults if the file is absent.
Re-running `make train-xgboost` / `make train-ee` after a tuning run therefore
applies the new parameters without a code change.
