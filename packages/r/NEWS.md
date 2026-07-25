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
