# TaxonBodyMassML 0.2.1

## Changes

* `predict_mass()` gains a `fuzzy_match_name` argument (default `FALSE`) that
  controls whether GBIF name correction is applied before taxonomy lookup. This
  consolidates fuzzy matching into the primary prediction function. Set to
  `TRUE` to enable name correction.
* `fuzzy_predict_mass()` is deprecated. Use `predict_mass(..., fuzzy_match_name = TRUE)`
  instead.
* When `fuzzy_match_name = TRUE`, the output includes a `matched_name` column
  showing the GBIF-canonical name used for each prediction.
* Fuzzy name matching now uses the GBIF v1 species-match endpoint with a
  `rank = "SPECIES"` hint and a minimum confidence threshold of 75, improving
  match accuracy and eliminating spurious results.

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
