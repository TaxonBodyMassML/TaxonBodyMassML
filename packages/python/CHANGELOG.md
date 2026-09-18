# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.10.0] - 2026-09-17

### Breaking

- The default `method` is now `"EntityEmbeddings"`, matching the R package.
  It is the more accurate model on held-out data (MAE 0.329 vs 0.357 log10).
  Pass `method="XGBoost"` to keep the previous behaviour.
- `method="GPBoost"` has been removed (model, artifacts and the `gpboost`
  extra are gone). Use `"EntityEmbeddings"` or `"XGBoost"`.
- `xgboost>=3.2` is now required. xgboost 3.0.x loads the model files without
  error but silently drops the intercept (predictions offset by ~0.9 log10);
  3.1.x fails on the categorical pandas path; 3.2.0 and later are verified to
  reproduce the training model exactly.

### Model

- Species is no longer a model feature in either method; both models are
  trained on kingdom .. genus. The training data has one body mass per
  species, so a species feature could only memorise individual rows, and every
  species the model is asked about is unseen by construction (known species are
  returned from the training-data dictionary). Removing it improved held-out
  accuracy for both methods and makes predictions reproducible. Queries for an
  unseen species and for its genus now give identical predictions by design.
- Both models were re-tuned (100 Optuna trials, 5-fold CV) on the new feature
  set and retrained. The Entity Embeddings feature vector is 84-dimensional
  (was 116).

### Fixed

- The XGBoost method builds its `DMatrix` from `pd.Categorical` columns whose
  categories are exactly `categories.json` (`UNK` first, then sorted) and
  orders columns by the model's own `feature_names`. A model without feature
  names now raises instead of silently mispredicting.
- Unseen taxa are always mapped to `UNK` (code 0).

### Changed

- Model artifacts regenerated; checksums updated. `categories.json` no longer
  carries a `feature_order` key.
- New golden-prediction integration test for both methods
  (`tests/test_predict.py::test_matches_golden_predictions`).

---

## [0.7.0] - 2026-08-27

### Breaking

- `predict_mass()` first argument renamed from `species` to `taxon`. Code
  passing the argument positionally is unaffected; code using `species=...` as
  a keyword argument must be updated to `taxon=...`.

### Added

- `predict_mass()` now checks a built-in species dictionary derived from the
  training data before invoking the model. When the queried taxon has a
  directly measured mass in the training data, that empirical value is returned
  instead of a model prediction.
- New `include_source` argument (default `False`). When `True`, a `source`
  column is appended identifying the provenance of each returned mass value:
  the original source identifier for dictionary-sourced values (e.g.,
  `"fishbase"`, `"Novak_unpubl"`), or `"tbmML_<rank>"` for model-inferred
  values, where `<rank>` is the finest taxonomic rank present in the training
  data (e.g., `"tbmML_genus"`).
- Conformal prediction interval columns (`lower_bound`, `upper_bound`,
  `confidence`) are `NaN` for dictionary-sourced rows since empirical values
  carry no model-based uncertainty estimate.
- New artifact `lookup.json` distributed alongside the model on Hugging Face.
  Update the checksum in `_checksums.py` after running
  `scripts/export_artifacts.py`.

---

## [0.6.1] - 2026-08-26

### Changed

- Retrained XGBoost model on updated data from TaxonBodyMass_DB (38,883 source
  taxa; 38,101 curated after kingdom filtering). Hyperparameters unchanged from
  0.6.0 except `max_depth` increased from 41 to 43 following a fresh 100-trial
  Optuna search (5-fold CV, MAE in log₁₀ space, `n_estimators` ceiling widened
  to 900). New hyperparameters: n_estimators=550, max_depth=43,
  learning_rate=0.1175, subsample=0.532, colsample_bytree=0.696, gamma=0.056,
  min_child_weight=2.
- Test-set performance (log₁₀ space): R²=0.9106, RMSE=0.5621, MAE=0.3384.
  Filtered to mass > 0.1 g (n=3,516): R²=0.7964, RMSE=0.5156, MAE=0.3148.
- Training set: 34,251 records; test set: 3,806 records.
- ASCII-normalised all taxonomy strings before training to prevent an XGBoost
  JSON serialisation bug triggered by multi-byte UTF-8 characters in category
  names.
- Updated all three artifact checksums (`model.ubj`, `calibration.json`,
  `categories.json`) to match the retrained model.

---

## [0.6.0] - 2026-08-22

### Changed

- Retrained XGBoost model on updated data from TaxonBodyMass_DB following a
  fresh 100-trial Optuna hyperparameter search (5-fold CV, MAE in log₁₀ space).
  New hyperparameters: n_estimators=550, max_depth=41, learning_rate=0.0835,
  subsample=0.504, colsample_bytree=0.856, gamma=0.005, min_child_weight=2.
- Test-set performance (log₁₀ space): R²=0.8857, RMSE=0.6599, MAE=0.3601.
  Filtered to mass > 0.1 g (n=3,509): R²=0.7803, RMSE=0.5409, MAE=0.3221.
- Training set: 34,470 records; test set: 3,830 records.
- Updated all three artifact checksums (`model.ubj`, `calibration.json`,
  `categories.json`) to match the retrained model.

## [0.5.1] - 2026-08-04

### Fixed

- `lookup_taxonomy([])` now returns a zero-row `DataFrame` with the correct
  8-column schema (`species`, `kingdom`, `phylum`, `class`, `order`, `family`,
  `genus`, `species_resolved`) instead of a zero-column `DataFrame`.
- `predict_mass([])` and `predict_mass(empty_df)` now return a zero-row
  `DataFrame` with the correct output schema instead of raising `KeyError`
  or `ValueError`.

## [0.5.0] - 2026-08-03

### Changed

- `predict_mass()` output column renamed from `species` to `taxon` to avoid
  ambiguity with the taxonomy output columns (notably `species_resolved`).

## [0.4.0] - 2026-08-03

### Changed

- Taxonomy enrichment pipeline extended: GBIF (confidence ≥ 75) → NCBI → WoRMS (exact,
  phonetic, near\_1 match types) → COL ChecklistBank → Wikidata SPARQL → ITIS.
- Removed OToL TNRS from enrichment pipeline.
- 210 non-animal eukaryote records removed (Plantae, Chromista, Viridiplantae, Fungi);
  36,566 records retained after all filters. Training set: 32,909 records; test set:
  3,657 records.
- Retrained XGBoost model following a fresh 100-trial Optuna hyperparameter search
  (5-fold CV, MAE in log₁₀ space). New hyperparameters: n\_estimators=600, max\_depth=30,
  learning\_rate=0.0327, subsample=0.655, colsample\_bytree=0.901, gamma=0.056,
  min\_child\_weight=1.
- Test-set performance (log₁₀ space): R²=0.8222, RMSE=0.5420, MAE=0.2866. Filtered to
  mass > 0.1 g (n=3,573): R²=0.8238, RMSE=0.4597, MAE=0.2679.
- Updated all three artifact checksums (`model.ubj`, `calibration.json`, `categories.json`)
  to match the retrained model.

## [0.2.5] - 2026-07-27

### Changed

- Updated all three artifact checksums (`model.ubj`, `calibration.json`,
  `categories.json`) to match the Optuna-retrained model exported from the
  current pkl bundle.

## [0.2.4] - 2026-07-27

### Fixed

- Updated `categories.json` artifact checksum to match the re-exported model
  artifacts. The previous checksum caused SHA-256 verification failure when
  downloading the new artifact.

## [0.2.3] - 2026-07-25

### Changed

- `predict_mass()` with `fuzzy_match_name=True` now reports `species` as the
  GBIF-canonical name (`None` when GBIF found no match), and `matched_name` as
  the originally entered name when a correction was applied or no match was
  found (`None` when the name was already canonical).

## [0.2.2] - 2026-07-25

### Fixed

- Fuzzy name matching now uses the GBIF v1 species-match endpoint (previously
  the v2 endpoint was called but v1 response fields were parsed, causing
  `matchType` to always be `None` and every fuzzy match to silently return
  `None`).
- GBIF requests now include a `rank=SPECIES` hint and reject matches with
  confidence below 75, reducing spurious results.

### Changed

- `fuzzy_match_name` argument of `predict_mass()` now defaults to `False`.
  Set it to `True` to enable GBIF name correction.

## [0.2.1] - 2026-07-24

### Changed

- `predict_mass()` gains a `fuzzy_match_name` argument (default `True`) that
  controls whether GBIF name correction is applied before taxonomy lookup. This
  consolidates fuzzy matching into the primary prediction function.
- When `fuzzy_match_name=True`, the output includes a `matched_name` column
  showing the GBIF-canonical name used for each prediction.

### Deprecated

- `fuzzy_predict_mass()` is deprecated. Use `predict_mass(..., fuzzy_match_name=True)`
  instead.

## [0.2.0] - 2026-07-24

### Added

- `correct_species_names()`, `fuzzy_lookup_taxonomy()`, and `fuzzy_predict_mass()`
  for approximate species-name matching via the GBIF fuzzy-match API.

### Changed

- Improved HTTP layer: connection reuse, retry on transient errors, per-host
  rate limiting, and configurable concurrency.
- XGBoost thread pool is warmed up on import to reduce first-prediction latency.

### Fixed

- Disk cache is now thread-safe; fixed `cache_store` backfill and an incorrect
  HTTP 512 status mapping (corrected to 422).
- `xml_missing` is checked before XML parsing to avoid a rare crash.
- User-Agent omits the contact suffix when `TAXONBODYMASSML_EMAIL` is unset.

## [0.1.0] - 2026-06-24

- Initial release.
