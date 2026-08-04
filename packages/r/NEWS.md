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

## Bug fixes

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

## Bug fixes

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

## Bug fixes

* Disk cache is now thread-safe; fixed `cache_store` backfill and an incorrect
  HTTP 512 status mapping (corrected to 422).
* `xml_missing` is now checked before XML parsing to avoid a rare crash.
* User-Agent omits the contact suffix when `TAXONBODYMASSML_EMAIL` is unset.

# TaxonBodyMassML 0.1.0

* Initial release.
