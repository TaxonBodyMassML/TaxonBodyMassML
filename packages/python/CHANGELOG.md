# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
