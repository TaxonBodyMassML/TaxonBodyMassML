# Hyperparameter Tuning Summary — TaxonBodyMassML

**Script**: `predictive_models/tune_hyperparameters.py` (`--model xgb` | `--model ee`); search spaces are the module constants `XGB_SPACE` / `EE_SPACE`, which `scripts/extract_hyperparameters.py` reads for the manuscript tables.
**Results files**: `predictive_models/results/tuning_study.json`, `predictive_models/results/tuning_study_ee.json`
**Study databases**: `predictive_models/results/tuning.db`, `tuning_ee.db` (Optuna SQLite backend; resumable; git-ignored)

Both studies below were run on 2026-09-18 on the training split drawn from
TaxonBodyMass_DB v5.1.0 (37,248 species with complete kingdom..genus
classification; 33,523 train / 3,725 test), after the autotroph-filter fix.
Species is not a feature in either model (`predictive_models/taxonomy_encoding.py`).
An earlier study that included species as a feature reached a lower CV MAE
(0.2968) but that value is not comparable: with one training row per species
the species feature memorises rows that reappear in the CV validation folds
through shared genera, and the resulting fits were not reproducible across
category orderings.

---

## Method

| Setting | Value |
|---|---|
| Tool | Optuna 4.9.0, TPE sampler (`seed=42`) |
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

### Trial distribution (CV MAE, log₁₀ space, 100 trials)

| Statistic | Value |
|---|---|
| Min (best) | **0.3441** |
| 25th percentile | 0.3463 |
| Median | 0.3517 |
| 75th percentile | 0.3577 |
| Max (worst) | 0.4573 |

Best trial: 35.

### Top five trials

| Trial | `n_estimators` | `max_depth` | `learning_rate` | `subsample` | `colsample_bytree` | `gamma` | `min_child_weight` | CV MAE |
|---|---|---|---|---|---|---|---|---|
| 35 | 750 | 32 | 0.1049 | 0.5052 | 0.6951 | 0.7939 | 2 | 0.3441 |
| 98 | 600 | 48 | 0.114 | 0.7097 | 0.8067 | 0.2288 | 2 | 0.3450 |
| 26 | 700 | 46 | 0.0649 | 0.6883 | 0.7777 | 0.9147 | 2 | 0.3451 |
| 73 | 450 | 50 | 0.0603 | 0.8375 | 0.8258 | 0.4188 | 2 | 0.3452 |
| 55 | 600 | 34 | 0.0858 | 0.8282 | 0.6332 | 0.0601 | 2 | 0.3453 |

### Observations

- The best trials cluster at 700–850 trees and depths in the 30s; none of the tuned
  parameters sits at a search bound.
- `subsample` ≈ 0.5 and `gamma` ≈ 0.8 in the best trial: strong row subsampling and
  leaf pruning compensate for the depth.
- Held-out test set after retraining with the best parameters
  (`predictive_models/results/metrics.json`): MAE 0.353, RMSE 0.611, R² 0.896.
  `model.ubj` is 394 MB.

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
| Min (best) | **0.3169** |
| 25th percentile | 0.3178 |
| Median | 0.3187 |
| 75th percentile | 0.3207 |
| Max (worst) | 0.4281 |

Best trial: 41.

### Top five trials

| Trial | `n_estimators` | `max_depth` | `learning_rate` | `subsample` | `colsample_bytree` | `min_child_weight` | CV MAE |
|---|---|---|---|---|---|---|---|
| 41 | 750 | 12 | 0.0506 | 0.6858 | 0.7481 | 10 | 0.3169 |
| 88 | 800 | 13 | 0.0736 | 0.6918 | 0.7955 | 10 | 0.3169 |
| 26 | 800 | 13 | 0.0688 | 0.6207 | 0.866 | 10 | 0.3170 |
| 82 | 800 | 13 | 0.0516 | 0.6646 | 0.7709 | 10 | 0.3170 |
| 59 | 750 | 12 | 0.0622 | 0.7168 | 0.7096 | 10 | 0.3170 |

### Observations

- Unlike the previous study, `n_estimators` and `max_depth` no longer sit at their
  ceilings; only `min_child_weight` is at its upper bound (10), so the Stage 2 model
  prefers strong smoothing over the continuous embedding features.
- The spread between the best and the 25th-percentile trial is small, so the
  optimum is flat.
- Held-out test set after retraining with the best parameters
  (`predictive_models/results/metrics_ee.json`): MAE 0.323, RMSE 0.528, R² 0.922;
  Stage 1 MLP alone MAE 0.362.

---

## Applying the results

Both training scripts read `best_params` from their tuning JSON at import time
(`decision_tree.py` from `tuning_study.json`, `entity_embeddings_model.py` from
`tuning_study_ee.json`) and fall back to hard-coded defaults if the file is absent.
Re-running `make train` after a tuning run therefore applies the new parameters
without a code change; `make clean-tune` discards the studies when the data change.
