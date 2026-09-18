# Pipeline: Re-import data → retune hyperparameters → fit models → export

## Context

`TaxonBodyMass_DB` is the single source of truth for enriched, deduplicated species-level body masses. After any update to the DB (new sources, enrichment re-run, cleaning fixes), the ML pipeline must be re-run from Phase 1 to regenerate training data and retrain all models.

Two model architectures are trained and exported:
- **XGBoost** — native categorical encoding of kingdom .. genus (`decision_tree.py`); vocabulary and feature contract in `predictive_models/taxonomy_encoding.py`
- **Entity Embeddings** — PyTorch MLP (Stage 1) + XGBoost on embedding features (Stage 2) (`entity_embeddings_model.py`), also on kingdom .. genus

Species is not a model feature in either model: the training table has one row per species, every queried species is unseen by construction, and known species are served from the `lookup.json` dictionary. See `taxonomy_encoding.MODEL_FEATURES`.

**Stop condition after Phase 6:** inspect `predictive_models/results/metrics*.json` for all models and confirm quality before proceeding to Phases 7–9.

---

## Quick start

From `/Users/novakm/Git/FracFeed/TaxonBodyMassML/`:

```bash
make clean-tune      # discard stale tuning state when training data has changed
make all             # fetch → split → tune (sequential) → train → export
```

To tune both models concurrently (requires ~2× CPU):

```bash
make clean-tune
make split
make tune -j2        # both tuners in parallel
make train
make artifacts
```

Individual targets: `make split`, `make tune-xgboost`, `make train-ee`, etc.

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
make tune          # sequential: xgboost → ee
make tune -j2      # concurrent: both in parallel
```

100 Optuna TPE trials, 5-fold CV MAE in log₁₀ space per model. SQLite backends are resumable (`load_if_exists=True`) — interrupted runs can be continued without losing completed trials.

Run `make clean-tune` first whenever training data has changed; stale trials from a different dataset are invalid.

**Outputs:**
- `predictive_models/results/tuning_study.json` — XGBoost best params
- `predictive_models/results/tuning_study_ee.json` — Entity Embeddings Stage 2 best params

---

## Phase 5 — Model training

```bash
make train   # trains both sequentially after tuning JSONs exist
```

Each script loads `best_params` from its tuning JSON and falls back to built-in defaults if absent.

**Outputs:**
- `regressor_microservice/sliced_model/xgboost_model.pkl.*` — XGBoost pickleslicer bundle (model, conformal `q`, vocabulary, pooled and per-rank calibration residuals, species dictionary); stale slices are removed first. This is a git-ignored local handoff to Phase 6; the microservice no longer reads it
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
- `categories.json` — per-feature (kingdom .. genus) training vocabulary, `UNK` first then sorted (this **is** the training-time code order; never reorder). Feature order is read from the model's own `feature_names`, not from this file
- `lookup.json` — species → `{mass_g, source}` lookup table
- `checksums.json` — SHA-256 hashes for all artifacts

**Verify:** `checksums.json` is non-empty; all artifact files for all models are present. Run `python scripts/sync_checksums.py` first (the packages re-download the published artifacts when their compiled-in checksums do not match the cache, so parity must be checked with the new checksums in place), reinstall the R package, then run `scripts/check_parity.py --sync-cache` to confirm the Python package, R package and microservice all reproduce `predictive_models/results/golden_predictions.json` (golden cases flagged `expect_na` have no rank in the vocabulary and must come back NA/null from every consumer), then a quick sanity prediction with `scripts/run_examples.py` or `scripts/run_examples.R`.

---

## STOP HERE — await user approval

Inspect `predictive_models/results/metrics.json`, `metrics_ee.json`. Confirm R², RMSE, and MAE are satisfactory before proceeding to Phases 7–9.

Prior XGBoost baseline (old data): R²=0.9106, RMSE=0.5621, MAE=0.3384 (log₁₀, n_test=3,806)

---

## Subsequent phases — DO NOT EXECUTE until approved

### Phase 7 — Publish artifacts, release the packages, redeploy the microservice

The Flask microservice (`regressor_microservice/`) serves predictions through the released Python package: its image installs the package wheel pinned in `regressor_microservice/dockerfile` and downloads the matching Hugging Face artifacts at build time. The order therefore matters (**explicit approval required at every release step**):

1. Bump the version in `packages/r/DESCRIPTION` and `packages/python/pyproject.toml`
   (the publish script refuses to reuse an existing Hugging Face tag) and add the
   `NEWS.md` / `CHANGELOG.md` entries.
2. Copy the new SHA-256 values into both packages: `python scripts/sync_checksums.py`.
3. Upload to Hugging Face and tag (rewrites `MODEL_ARTIFACT_VERSION` in both packages):
   ```bash
   python scripts/publish_artifacts.py        # dry run
   python scripts/publish_artifacts.py --yes  # publish
   ```
4. Commit and push; CI creates the `python-v<version>` and `r-v<version>` GitHub releases and updates `latest`.
5. Bump the `TBM_WHEEL` default in `regressor_microservice/dockerfile` to the new wheel URL and commit.
6. On the deployment host, follow the runbook in `regressor_microservice/README.md`:
   `docker compose up --build -d`, check `/health`, read the new tunnel URL from the
   `cloudflared` logs, paste it into `web_dev/index.js`, push (CI syncs `web_dev/` to the
   Pages repository).

### Phase 8 — Regenerate results (tables, figures, numbers)

```bash
python scripts/check_parity.py --sync-cache   # the package cache must hold the artifacts being evaluated
make results
```

`make results` runs, in order: `scripts/extract_training_stats.py` (kingdom/class tables, `data_stats.json`), `scripts/evaluate_models.py` (both models through `taxonbodymassml.predict_mass`: metrics, scatter figures, rank-masking errors, empirical conformal coverage; Entity Embeddings tables for the main text and `*_cmp.tex` comparison tables for the supplement), `scripts/extract_feature_importance.py`, `scripts/extract_hyperparameters.py` (search ranges are read from `predictive_models/tune_hyperparameters.py`), `scripts/format_data_sources.py`, `scripts/make_numbers_tex.py` (one `\newcommand` per quoted number) and finally `ms/copy_results.sh`, which copies everything into `ms/`.

### Phase 9 — Update manuscript

**Requires Phase 7 complete first** (Hugging Face upload + package checksum update), because `numbers.tex` records the package and artifact versions.

- All numbers in `ms/manuscript.tex` come from `numbers.tex` macros; edit prose only. `make check-ms` lists unused/undefined macros, remaining margin notes and any hard-coded numerals.
- Regenerate the R example output by running `Rscript scripts/run_examples.R` with the released package and pasting the console output into the `lstlisting` blocks of the Examples subsection.
- `make -C ms pdf` builds the development PDF; `make submission` writes the single-file, macro-free `ms/submission/manuscript_submission.tex` (tables and bibliography inlined) and verifies with `pdftotext` that it renders identically. Submit that file, not the development source.
