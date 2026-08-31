# Pipeline: Re-import data → retune hyperparameters → fit models → export

## Context

`TaxonBodyMass_DB` is the single source of truth for enriched, deduplicated species-level body masses. After any update to the DB (new sources, enrichment re-run, cleaning fixes), the ML pipeline must be re-run from Phase 1 to regenerate training data and retrain all three models.

Three model architectures are trained and exported:
- **XGBoost** — native categorical encoding (`decision_tree.py`)
- **GPBoost** — LightGBM trees + nested Gaussian process random effects (`gpboost_model.py`)
- **Entity Embeddings** — PyTorch MLP (Stage 1) + XGBoost on embedding features (Stage 2) (`entity_embeddings_model.py`)

**Stop condition after Phase 6:** inspect `predictive_models/results/metrics*.json` for all three models and confirm quality before proceeding to Phases 7–9.

---

## Quick start

From `/Users/novakm/Git/FracFeed/TaxonBodyMassML/`:

```bash
make clean-tune      # discard stale tuning state when training data has changed
make all             # fetch → split → tune (sequential) → train → export
```

To tune all three models concurrently (requires ~3× CPU):

```bash
make clean-tune
make split
make tune -j3        # all three tuners in parallel
make train
make artifacts
```

Individual targets: `make split`, `make tune-xgboost`, `make train-gpboost`, etc.

Each training script reads best hyperparameters from its tuning JSON at runtime and falls back to built-in defaults if the JSON is absent.

---

## Phase 1 — R pipeline (regenerate TaxonBodyMass.csv)

**Working dir:** `/Users/novakm/Git/FracFeed/TaxonBodyMass_DB/R/`

Run `RunMe.r` with `recompile = TRUE` to apply all cleaning functions to raw per-source `.Rdata` files and re-run the full enrichment pipeline.

**Output:** `TaxonBodyMass_DB/TaxonBodyMass.csv` — enriched, deduplicated species-level body masses with full taxonomy (`kingdom`–`species`), provenance (`taxon_provided`, `source_mass`, `taxonomy_source`), and QC columns (`log10_range`, `gbif_confidence`, `gbif_status`, `species_changed`). QC reports written to `TaxonBodyMass_DB/reports/errors.md` and `reports/warnings.md`.

---

## Phase 2 — Fetch source data into ML project

```bash
make data/TaxonBodyMass.csv   # or triggered automatically by make split / make all
```

Copies `TaxonBodyMass_DB/TaxonBodyMass.csv` → `data/TaxonBodyMass.csv` (and bib files). Make skips this step if the local copy is newer than the DB source.

---

## Phase 3 — Train/test split

```bash
make split   # or triggered automatically by make tune / make all
```

Drops all provenance/QC columns, ASCII-normalises taxonomy strings, produces a 90/10 split.

**Output:** `data/split/train.csv`, `data/split/test.csv`

---

## Phase 4 — Hyperparameter tuning

```bash
make tune          # sequential: xgboost → gpboost → ee
make tune -j3      # concurrent: all three in parallel
```

100 Optuna TPE trials, 5-fold CV MAE in log₁₀ space per model. SQLite backends are resumable (`load_if_exists=True`) — interrupted runs can be continued without losing completed trials.

Run `make clean-tune` first whenever training data has changed; stale trials from a different dataset are invalid.

**Outputs:**
- `predictive_models/results/tuning_study.json` — XGBoost best params
- `predictive_models/results/tuning_study_gpboost.json` — GPBoost best params
- `predictive_models/results/tuning_study_ee.json` — Entity Embeddings Stage 2 best params

---

## Phase 5 — Model training

```bash
make train   # trains all three sequentially after tuning JSONs exist
```

Each script loads `best_params` from its tuning JSON and falls back to built-in defaults if absent.

**Outputs:**
- `regressor_microservice/sliced_model/xgboost_model.pkl.*` — XGBoost pickleslicer bundle (model + conformal `q`)
- `artifacts/model_gpboost.json` — GPBoost model
- `artifacts/model_ee.ubj` — Entity Embeddings Stage 2 XGBoost
- `artifacts/embeddings.json` — Entity Embeddings lookup tables
- `artifacts/calibration_*.json` — conformal calibration residuals (pooled + rank-stratified) for each model
- `predictive_models/results/metrics*.json` — test-set R², RMSE, MAE for each model

---

## Phase 6 — Artifact export

```bash
make artifacts   # or triggered automatically by make all
```

**Outputs (all in `artifacts/`):**
- `model.ubj` — XGBoost UBJSON binary
- `calibration.json` — sorted conformal residuals (XGBoost)
- `calibration_by_rank.json` — rank-stratified residuals (XGBoost)
- `categories.json` — taxonomy category lists in **training-time integer-code order** (do not sort alphabetically — order must match training-time codes)
- `lookup.json` — species → `{mass_g, source}` lookup table
- `checksums.json` — SHA-256 hashes for all artifacts

**Verify:** `checksums.json` is non-empty; all artifact files for all three models are present. Run a quick sanity prediction with `scripts/run_examples.py` or `scripts/run_examples.R`.

---

## STOP HERE — await user approval

Inspect `predictive_models/results/metrics.json`, `metrics_gpboost.json`, `metrics_ee.json`. Confirm R², RMSE, and MAE are satisfactory before proceeding to Phases 7–9.

Prior XGBoost baseline (old data): R²=0.9106, RMSE=0.5621, MAE=0.3384 (log₁₀, n_test=3,806)

---

## Subsequent phases — DO NOT EXECUTE until approved

### Phase 7 — Rebuild microservice and publish artifacts

The Flask microservice (`regressor_microservice/`) bakes `sliced_model/xgboost_model.pkl` into the Docker image at build time. After Phase 5 updates the pkl, rebuild and restart:

```bash
cd regressor_microservice
docker compose up --build -d
```

Then publish artifacts:

1. Upload to Hugging Face:
   ```bash
   huggingface-cli upload marknovak/TaxonBodyMassML artifacts/ .
   ```
2. Copy the new SHA-256 from `artifacts/checksums.json` into:
   - `packages/python/taxonbodymassml/_checksums.py`
   - `packages/r/R/model.R`
3. Tag and release both packages (version bump per semver).

### Phase 8 — Regenerate results (figures and tables)

```bash
python scripts/extract_test_metrics.py
python scripts/extract_training_stats.py
python scripts/extract_feature_importance.py
python scripts/extract_unk_errors.py
bash ms/copy_results.sh
```

### Phase 9 — Update manuscript

**Requires Phase 7 complete first** (Hugging Face upload + package checksum update).

Update all values in `ms/manuscript.tex` that depend on model performance metrics, training dataset statistics, feature importance rankings, hyperparameter values, and conformal interval width (`q`).

Regenerate R example output (lines 504–529 of `manuscript.tex`) by running `Rscript scripts/run_examples.R` with the updated package and pasting the console output into the two `lstlisting` blocks.

Compile `ms/manuscript.tex` to confirm no broken references or layout regressions.
