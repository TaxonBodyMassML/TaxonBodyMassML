# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.1] - 2026-07-24

### Changed

- `predict_mass()` gains a `fuzzy_match_name` argument (default `True`) that
  controls whether GBIF name correction is applied before taxonomy lookup. This
  consolidates fuzzy matching into the primary prediction function.
- When `fuzzy_match_name=True`, the output includes a `matched_name` column
  showing the GBIF-canonical name used for each prediction.

### Deprecated

- `fuzzy_predict_mass()` is deprecated. Use `predict_mass(..., fuzzy_match_name=True)`
  instead (which is now the default behaviour).

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
