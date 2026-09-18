# TaxonBodyMassML 0.11.0

## Model and data

* Training data updated to TaxonBodyMass_DB v5.1.0 (37,255 species; was
  37,312). The database's autotroph filter now uses the rank names that GBIF
  and NCBI actually return, so 21 cyanobacteria, 33 photosynthetic
  dinoflagellates and 3 photosynthetic euglenids that had slipped through are
  gone, and one lizard that NCBI had matched to a plant genus is corrected.
  Both models were re-split, re-tuned (100 Optuna trials, 5-fold CV) and
  retrained; artifact checksums updated (Hugging Face tags `r-v0.11.0` /
  `py-v0.11.0`).

## Changed

* Taxa whose kingdom..genus classification shares no value with the training
  vocabulary (for example plants and fungi, which the training data exclude)
  now return `NA` with a warning and `source = "tbmML_UNK"` instead of a
  prediction from all-`UNK` features, which was a meaningless extrapolation
  wrapped in an ordinary-looking interval. Kingdom-level matches are still
  predicted. Golden cases of this kind are flagged `expect_na`.
* Fixed: a bare `"UNK"` species string was treated as a known genus when
  inferring the source rank (the vocabulary lists start with `UNK`), so such
  rows were labelled `tbmML_genus`.
* The web interface's prediction service now calls the Python package, so all
  three interfaces share one inference implementation.

## Documentation

* Vignette: installation from the `latest` GitHub release, refreshed example
  output, and the `interval_method` and `NA` behaviours documented.

# TaxonBodyMassML 0.10.0

## Breaking changes

* `method = "GPBoost"` has been removed (the GPBoost model, its artifacts and
  the `gpboost` Suggests dependency are gone). Use `"EntityEmbeddings"` or
  `"XGBoost"`.
* `xgboost (>= 3.1.2)` is now required (the oldest 3.x release on CRAN; verified
  to reproduce the training model exactly). Older xgboost (1.7.x) loads the
  current model files without error but silently drops the intercept, shifting
  every prediction by roughly 0.9 log10 units.

## Model changes

* Species is no longer a model feature in either method; both models are
  trained on kingdom .. genus. The training data has one body mass per
  species, so a species feature could only memorise individual rows, and every
  species the model is asked about is unseen by construction (known species are
  returned from the training-data dictionary). Removing it improved held-out
  accuracy for both methods and makes predictions reproducible. Queries for an
  unseen species and for its genus now give identical predictions by design.
* Both models were re-tuned (100 Optuna trials, 5-fold CV) on the new feature
  set and retrained. The Entity Embeddings feature vector is 84-dimensional
  (was 116) and `embeddings.json` is correspondingly smaller.

## Bug fixes

* `method = "XGBoost"` works again in R. The model is trained with native
  categorical splits on factors whose levels are exactly `categories.json`
  (`UNK` first, then sorted), and the input columns are ordered by the model's
  own feature names. Earlier failures were caused by feeding columns in the
  wrong order, not by categorical splits.
* Unseen taxa are always mapped to `UNK` (code 0) instead of an arbitrary
  neighbouring code.

## Internal

* Model artifacts regenerated (checksums updated). `categories.json` no
  longer carries a `feature_order` key.
* New golden-prediction test (`tests/testthat/test-predict.R`) checks that the
  R package reproduces the training model exactly.

# TaxonBodyMassML 0.8.0

## New features

* `predict_mass()` gains an `interval_method` argument (default `"stratified"`).
  `"stratified"` uses rank-specific conformal calibration residuals, providing
  approximate rank-conditional coverage: genus-level queries receive narrower
  intervals than family- or order-level queries. `"pooled"` reproduces the
  previous behaviour (a single quantile from all pooled calibration residuals,
  yielding the standard marginal coverage guarantee).
* New artifact `calibration_by_rank.json` distributed alongside the model on
  Hugging Face. Update checksums in `R/model.R` after running
  `scripts/export_artifacts.py`.

# TaxonBodyMassML 0.7.0

## Breaking changes

* `predict_mass()` first argument renamed from `species` to `taxon`. Code using
  positional arguments is unaffected; code using `species = ...` as a keyword
  argument must be updated to `taxon = ...`.

## New features

* `predict_mass()` now checks a built-in species dictionary derived from the
  training data before invoking the model. When the queried taxon has a
  directly measured mass in the training data, that value is returned unchanged
  instead of a model prediction.
* New `include_source` argument (default `FALSE`). When `TRUE`, a `source`
  column is appended identifying the provenance of each returned mass value:
  the original source identifier for dictionary-sourced values (e.g.,
  `"fishbase"`, `"Novak_unpubl"`), or `"tbmML_<rank>"` for model-inferred
  values, where `<rank>` is the finest taxonomic rank present in the training
  data (e.g., `"tbmML_genus"`).
* Conformal prediction intervals (CI columns) are `NA` for dictionary-sourced
  rows since empirical values carry no model-based uncertainty estimate.
* New artifact `lookup.json` distributed alongside the model on Hugging Face.
  Update checksums in `R/model.R` after running `scripts/export_artifacts.py`.

# TaxonBodyMassML 0.6.1

## Data and model

* Retrained XGBoost model on updated data from TaxonBodyMass\_DB (38,883 source
  taxa; 38,101 curated after kingdom filtering). Hyperparameters unchanged from
  0.6.0 except `max\_depth` increased from 41 to 43 following a fresh 100-trial
  Optuna search (5-fold CV, MAE in log₁₀ space, `n\_estimators` ceiling widened
  to 900). New hyperparameters: n\_estimators=550, max\_depth=43,
  learning\_rate=0.1175, subsample=0.532, colsample\_bytree=0.696, gamma=0.056,
  min\_child\_weight=2.
* Test-set performance (log₁₀ space): R²=0.9106, RMSE=0.5621, MAE=0.3384.
  Filtered to mass > 0.1 g (n=3,516): R²=0.7964, RMSE=0.5156, MAE=0.3148.
* Training set: 34,251 records; test set: 3,806 records.
* ASCII-normalised all taxonomy strings before training to prevent an XGBoost
  JSON serialisation bug triggered by multi-byte UTF-8 characters in category
  names.
* Updated all three artifact checksums (`model.ubj`, `calibration.json`,
  `categories.json`) to match the retrained model.

# TaxonBodyMassML 0.6.0

## Data and model

* Retrained XGBoost model on updated data from TaxonBodyMass\_DB following a
  fresh 100-trial Optuna hyperparameter search (5-fold CV, MAE in log₁₀ space).
  New hyperparameters: n\_estimators=550, max\_depth=41, learning\_rate=0.0835,
  subsample=0.504, colsample\_bytree=0.856, gamma=0.005, min\_child\_weight=2.
* Test-set performance (log₁₀ space): R²=0.8857, RMSE=0.6599, MAE=0.3601.
  Filtered to mass > 0.1 g (n=3,509): R²=0.7803, RMSE=0.5409, MAE=0.3221.
* Training set: 34,470 records; test set: 3,830 records.
* Updated all three artifact checksums (`model.ubj`, `calibration.json`,
  `categories.json`) to match the retrained model.

# TaxonBodyMassML 0.5.1

## Bugfixes

* `lookup_taxonomy()` now returns a zero-row `data.frame` with the expected
  8-column schema when given `character(0)`, rather than `NULL`.
* Parallel GBIF worker count is capped at 2 to comply with CRAN's
  concurrent-process limit enforced by `--as-cran` checks.

# TaxonBodyMassML 0.5.0

## Breaking changes

* `predict_mass()` output column renamed from `species` to `taxon` to avoid
  ambiguity with the taxonomy output columns (notably `species_resolved`).

# TaxonBodyMassML 0.4.0

## Data curation

* Added new data sources: Faurby et al. (2018), Fisher (2001),
  Galán-Acedo et al. (2026), Pata (2025), Pekar et al. (2021),
  Trochet (2014), Wilman et al. (2014).
* Removed genus-only taxa (no species-level identification).
* Taxonomy enrichment pipeline extended: GBIF (confidence ≥ 75) →
  NCBI → WoRMS (exact, phonetic, near\_1 match types) →
  COL ChecklistBank → Wikidata SPARQL → ITIS.
* Removed OToL TNRS from enrichment pipeline.
* 210 non-animal eukaryote records removed (Plantae, Chromista,
  Viridiplantae, Fungi); 36,566 records retained after all filters.
* Training set: 32,909 records; test set: 3,657 records.

## Model

* Retrained XGBoost model on expanded and curated data following a
  fresh 100-trial Optuna hyperparameter search (5-fold CV, MAE in
  log₁₀ space). New hyperparameters: n\_estimators=600, max\_depth=30,
  learning\_rate=0.0327, subsample=0.655, colsample\_bytree=0.901,
  gamma=0.056, min\_child\_weight=1.
* Test-set performance (log₁₀ space): R²=0.8222, RMSE=0.5420, MAE=0.2866.
  Filtered to mass > 0.1 g (n=3,573): R²=0.8238, RMSE=0.4597, MAE=0.2679.
* Updated all three artifact checksums (`model.ubj`, `calibration.json`,
  `categories.json`) to match the retrained model.

# TaxonBodyMassML 0.3.0

## Data curation

* Removed non-animal eukaryotic kingdoms (Plantae, Chromista, Fungi,
  Viridiplantae) from training and test data. These taxa are outside the
  scientific scope of the model. Prokaryotes (Bacteria, Bacillati) and
  single-celled eukaryotes (Protozoa, Metazoa) are retained.
* Training set: 33,820 records; test set: 3,747 records.

## Model

* Retrained XGBoost model on curated data following a fresh 100-trial Optuna
  hyperparameter search (5-fold CV, MAE in log₁₀ space). New hyperparameters:
  n\_estimators=500, max\_depth=37, learning\_rate=0.0399, subsample=0.742,
  colsample\_bytree=0.957, gamma=0.551, min\_child\_weight=1.
* Test-set performance (log₁₀ space): R²=0.8717, RMSE=0.5064, MAE=0.2616.
  Filtered to mass > 0.1 g (n=3,648): R²=0.8652, RMSE=0.4111, MAE=0.2473.
* Updated all three artifact checksums (`model.ubj`, `calibration.json`,
  `categories.json`) to match the retrained model.

# TaxonBodyMassML 0.2.5

## Changes

* Updated all three artifact checksums (`model.ubj`, `calibration.json`,
  `categories.json`) to match the Optuna-retrained model exported from the
  current pkl bundle.

# TaxonBodyMassML 0.2.4

## Bugfixes

* Updated `categories.json` artifact checksum to match the re-exported model
  artifacts. The previous checksum caused SHA-256 verification failure when
  downloading the new artifact.

# TaxonBodyMassML 0.2.3

## Changes

* `predict_mass()` with `fuzzy_match_name = TRUE` now reports `species` as the
  GBIF-canonical name (or `NA` when GBIF found no match), and `matched_name` as
  the originally entered name when a correction was applied or no match was
  found (`NA` when the name was already canonical).

# TaxonBodyMassML 0.2.2

## Bugfixes

* Fuzzy name matching now uses the GBIF v1 species-match endpoint (previously
  the v2 endpoint was called but v1 response fields were parsed, causing
  `matchType` to always be `NULL` and every fuzzy match to silently return
  `NA`).
* GBIF requests now include a `rank = "SPECIES"` hint and reject matches with
  confidence below 75, reducing spurious results.

## Changes

* `fuzzy_match_name` argument of `predict_mass()` now defaults to `FALSE`.
  Set it to `TRUE` to enable GBIF name correction.

# TaxonBodyMassML 0.2.1

## Changes

* `predict_mass()` gains a `fuzzy_match_name` argument (default `TRUE`) that
  controls whether GBIF name correction is applied before taxonomy lookup. This
  consolidates fuzzy matching into the primary prediction function.
* `fuzzy_predict_mass()` is deprecated. Use `predict_mass(..., fuzzy_match_name = TRUE)`
  instead.
* When `fuzzy_match_name = TRUE`, the output includes a `matched_name` column
  showing the GBIF-canonical name used for each prediction.

# TaxonBodyMassML 0.2.0

## New features

* Added `fuzzy_lookup_taxonomy()` and `fuzzy_predict_mass()` for approximate
  species-name matching using the GBIF fuzzy-match API.
* Added `correct_species_names()` to return the best-matching canonical name
  for a vector of (potentially misspelled) species names.

## Improvements

* Improved HTTP layer: connection reuse, retry on transient errors, per-host
  rate limiting, and configurable concurrency.
* XGBoost thread pool is now warmed up on package load to reduce first-prediction
  latency.

## Bugfixes

* Disk cache is now thread-safe; fixed `cache_store` backfill and an incorrect
  HTTP 512 status mapping (corrected to 422).
* `xml_missing` is now checked before XML parsing to avoid a rare crash.
* User-Agent omits the contact suffix when `TAXONBODYMASSML_EMAIL` is unset.

# TaxonBodyMassML 0.1.0

* Initial release.
