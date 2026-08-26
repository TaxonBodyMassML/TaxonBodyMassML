# Pipeline: Re-import data → retune hyperparameters → fit model

## Context

The TaxonBodyMass_DB has undergone significant cleaning (fix_nontaxa.r, fix_misspellings.r, fix_outliers.r). The trained model and all downstream artifacts must be regenerated from the cleaned database. This plan covers everything through artifact export. Results, figures, tables, and manuscript updates are explicitly out of scope until the user approves them separately.

**Stop condition:** After `export_artifacts.py` produces the four artifact files. Do NOT upload to Hugging Face, do not update package checksums, do not run manuscript update scripts.

---

## Phase 1 — R pipeline (regenerate TaxonBodyMass.csv)

**Working dir:** `/Users/novakm/Git/FracFeed/TaxonBodyMass_DB/R/`

**Action:** Run `RunMe.r` with `recompile = TRUE` so that the cleaning functions (fix_formatting, fix_misspellings, fix_nontaxa, fix_body_mass_errors, fix_outliers) are applied to the raw per-source `.Rdata` files. `DataRetrieve` should remain `FALSE` (no re-download from rdataretriever).

```r
# Set at the top of RunMe.r before sourcing:
recompile   <- TRUE
DataRetrieve <- FALSE
```

**Output:** `TaxonBodyMass_DB/TaxonBodyMass.csv` (species-level body masses: `taxon`, `mass_g`, `source_mass`, `n`).

**Verify:** Row count and modification timestamp changed; spot-check that removed taxa (e.g. `Glyptotherium_cylindricum`, `Omnivorous_nematodes`) are absent, and corrected names (e.g. `Squalius_cephalus` not `Squalinus_cephalus`) appear.

---

## Phase 2 — Fetch source data into ML project

**Working dir:** `/Users/novakm/Git/FracFeed/TaxonBodyMassML/`

```bash
python scripts/fetch_source_data.py
```

Copies `TaxonBodyMass_DB/TaxonBodyMass.csv` → `data/TaxonBodyMass.csv`. Raises immediately if source is missing.

---

## Phase 3 — Taxonomy enrichment (6 passes) + kingdom filter + train/test split

All scripts run from `/Users/novakm/Git/FracFeed/TaxonBodyMassML/`. Run sequentially; each pass reads the previous pass's output.

```bash
python data-combination/combination_api.py       # Pass 1: GBIF (threaded, ~minutes)
python data-combination/ncbi_fallback.py         # Pass 2: NCBI Entrez (rate-limited, ~hours)
python data-combination/worms_fallback.py        # Pass 3: WoRMS (batched)
python data-combination/col_fallback.py          # Pass 4: COL ChecklistBank (sequential)
python data-combination/wikidata_fallback.py     # Pass 5: Wikidata SPARQL (batched 10)
python data-combination/itis_fallback.py         # Pass 6: ITIS JSON (sequential)
python data-combination/filter_kingdoms.py       # Kingdom filter → TaxonBodyMass_curated.csv
python data_partition/data_split_visualization.py  # 90/10 train/test split
```

**Outputs:**

- `data/passes/TaxonBodyMass_curated.csv` (~38,000 rows)
- `data/split/train.csv`, `data/split/test.csv`

**Verify:** `TaxonBodyMass_curated.csv` row count plausible (~38,000 ± 500). Check `data/split/train.csv` and `test.csv` exist with expected column set (`mass_g`, `kingdom` … `species`).

---

## Phase 4 — Hyperparameter tuning (Optuna)

**Working dir:** `/Users/novakm/Git/FracFeed/TaxonBodyMassML/`

The previous best hit the `n_estimators` ceiling (600). Before running, widen the search space in `predictive_models/tune_hyperparameters.py`:

```python
# Change:
n_estimators = trial.suggest_int("n_estimators", 200, 600, step=50)
# To:
n_estimators = trial.suggest_int("n_estimators", 200, 900, step=50)
```

Delete both the SQLite study and the JSON results so the run starts completely fresh — stale trials from different data are invalid:

```bash
rm predictive_models/results/tuning.db
rm predictive_models/results/tuning_study.json
```

Then run:

```bash
python predictive_models/tune_hyperparameters.py
```

100 TPE trials, 5-fold CV MAE in log₁₀ space. Takes ~30–60 min on CPU.

**Output:** `predictive_models/results/tuning_study.json` — contains `best_params` dict and full trial list.

**Verify:** `tuning_study.json` has a `best_params` entry. Check whether `n_estimators` is now below the new ceiling (900); if it is still at the ceiling, note it and consider a second widening pass before training.

---

## Phase 5 — Model fit

**Working dir:** `/Users/novakm/Git/FracFeed/TaxonBodyMassML/`

Update `predictive_models/decision_tree.py` with the best params from `tuning_study.json`. The relevant constructor call:

```python
xgb.XGBRegressor(
    objective="reg:absoluteerror",
    n_estimators=<best>,
    max_depth=<best>,
    learning_rate=<best>,
    subsample=<best>,
    colsample_bytree=<best>,
    gamma=<best>,
    min_child_weight=<best>,
    enable_categorical=True,
    random_state=42
)
```

Then run:

```bash
python predictive_models/decision_tree.py
```

**Outputs:**

- `regressor_microservice/sliced_model/xgboost_model.pkl` (pickleslicer bundle: model + conformal `q`)
- `predictive_models/results/metrics.json` (R², RMSE, MAE on test set)

**Verify:** `metrics.json` R² is plausible (prior run: check `tuning_summary.md` for reference MAE ≈ 0.297 log₁₀). If markedly worse, investigate before proceeding.

---

## Phase 6 — Artifact export

```bash
python scripts/export_artifacts.py
```

**Outputs (all in `artifacts/`):**

- `model.ubj` — XGBoost UBJSON binary
- `calibration.json` — sorted conformal residuals; sanity-checks rebuilt `q` (errors if delta > 1e-4)
- `categories.json` — taxonomy category lists in training-time integer-code order (**do not sort alphabetically** — order must match training-time codes for correct predictions)
- `checksums.json` — SHA-256 hashes of the three files above

**Verify:** All four files exist and `checksums.json` is non-empty. Run a quick sanity prediction using `scripts/run_examples.py` or `run_examples.R` against the new `model.ubj` to confirm it loads and returns a plausible value.

---

## STOP HERE — await user approval

Inspect `predictive_models/results/metrics.json` (R², RMSE, MAE) and confirm the model quality is satisfactory before proceeding to any of the steps below.

---

## Subsequent phases — DO NOT EXECUTE until approved

### Phase 7 — Rebuild microservice and publish artifacts

The Flask microservice (`regressor_microservice/`) bakes `sliced_model/xgboost_model.pkl` into the Docker image at build time (no volume mount). After Phase 5 updates the pkl, rebuild and restart the container:

```bash
cd regressor_microservice
docker compose up --build -d
```

Verify with the `/health` endpoint and a test prediction against `/xgb_pred_single` before publishing externally.

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

Run the extraction/formatting scripts that feed the manuscript:

```bash
python scripts/extract_test_metrics.py       # test-set metrics → LaTeX
python scripts/extract_training_stats.py     # training statistics → LaTeX
python scripts/extract_feature_importance.py # feature importance → figure data
python scripts/extract_unk_errors.py         # UNK prediction errors → analysis
bash ms/copy_results.sh                      # copy into ms/ directory
```

### Phase 9 — Update manuscript

**Requires Phase 7 to be complete first** (Hugging Face upload + package checksum update), because the R/Python packages download the model from Hugging Face on first use.

**9a — Regenerate numeric results and figures** (same scripts as Phase 8 if not already run), then update all values in `ms/manuscript.tex` that depend on:

- Model performance metrics (R², RMSE, MAE)
- Training dataset statistics (n taxa, class breakdown)
- Feature importance rankings
- Hyperparameter values
- Conformal prediction interval width (`q`)

**9b — Regenerate R example output (lines 504–529 of `manuscript.tex`):**

The manuscript contains two `lstlisting` R code blocks with hardcoded expected output (`mass_g`, `lower_bound`, `upper_bound`) for `Nucella ostrina`, `Haustrum haustorium`, and the unresolvable `Nutella haustrina`. A `\MN{Be sure to rerun these numbers}` note already flags these as needing refresh.

Run the example script with the updated package (which must already be pointing to the new Hugging Face model):

```bash
Rscript scripts/run_examples.R
```

Manually paste the console output into the two `lstlisting` blocks in `ms/manuscript.tex` (there is no automated back-write).

**9c — Compile and verify:**

Compile `ms/manuscript.tex` to confirm no broken references, changed labels, or layout regressions from updated table/figure content.
