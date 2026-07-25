# ---------------------------------------------------------------------------
# CI level resolver
# ---------------------------------------------------------------------------

.resolve_ci_level <- function(ci) {
  if (isFALSE(ci)) return(NULL)
  if (isTRUE(ci))  return(0.90)
  ci <- suppressWarnings(as.numeric(ci))
  if (is.na(ci) || ci <= 0 || ci >= 1) {
    stop(
      "confidence_interval must be FALSE, TRUE, or a numeric in (0, 1). ",
      "Got: ", deparse(ci),
      call. = FALSE
    )
  }
  ci
}

# ---------------------------------------------------------------------------
# XGBoost inference
# ---------------------------------------------------------------------------

.predict_xgboost <- function(taxonomy_df, level, include_taxonomy, input_names) {
  model <- .load_model()
  cats  <- .load_categories()

  COLS <- c("kingdom", "phylum", "class", "order", "family", "genus", "species")

  # Build feature data.frame (map species_resolved -> species column for model)
  X <- data.frame(
    kingdom = taxonomy_df$kingdom,
    phylum  = taxonomy_df$phylum,
    class   = taxonomy_df$class,
    order   = taxonomy_df$order,
    family  = taxonomy_df$family,
    genus   = taxonomy_df$genus,
    species = taxonomy_df$species_resolved,
    stringsAsFactors = FALSE
  )

  # Apply UNK mapping and set factor levels matching training categories
  for (col in COLS) {
    valid <- cats[[col]]
    X[[col]] <- ifelse(X[[col]] %in% valid, X[[col]], "UNK")
    X[[col]] <- factor(X[[col]], levels = valid)
  }

  dmat <- xgboost::xgb.DMatrix(data = X)
  log_preds <- stats::predict(model, dmat)

  result <- data.frame(
    species = input_names,
    mass_g  = 10^log_preds,
    stringsAsFactors = FALSE
  )

  if (!is.null(level)) {
    residuals <- .load_calibration()
    q <- as.numeric(stats::quantile(residuals, level))
    result$lower_bound <- 10^(log_preds - q)
    result$upper_bound <- 10^(log_preds + q)
    result$confidence  <- level
  }

  if (include_taxonomy) {
    tax_cols <- c("kingdom", "phylum", "class", "order", "family", "genus", "species_resolved")
    result <- cbind(result, taxonomy_df[, tax_cols, drop = FALSE])
    rownames(result) <- NULL
  }

  result
}

# ---------------------------------------------------------------------------
# Method dispatch table
# ---------------------------------------------------------------------------

.METHODS <- list(XGBoost = .predict_xgboost)

# ---------------------------------------------------------------------------
# Public: predict_mass()
# ---------------------------------------------------------------------------

#' Predict body mass for one or more species
#'
#' @description
#' Predicts body mass (in grams) using the TaxonBodyMassML XGBoost model.
#' When `species` is a character vector, taxonomy is resolved automatically.
#' Pass a `data.frame` with pre-resolved taxonomy columns to skip lookup.
#'
#' @param species A character vector of scientific names, or a `data.frame`
#'   with columns `kingdom`, `phylum`, `class`, `order`, `family`, `genus`,
#'   and `species_resolved` (as returned by `lookup_taxonomy()`).
#' @param confidence_interval `FALSE` (default, no interval), `TRUE` (90%
#'   conformal prediction interval), or a numeric in (0, 1) for a custom
#'   coverage level.
#' @param method Character. Prediction method. Currently only `"XGBoost"`
#'   is supported.
#' @param include_taxonomy Logical. If `TRUE`, append the resolved taxonomy
#'   columns to the output. Default `FALSE`.
#' @param fuzzy_match_name Logical. If `TRUE`, species names are first
#'   corrected via the GBIF species-match API before taxonomy lookup,
#'   tolerating misspellings and minor name variants. A `matched_name` column
#'   is appended to the output showing the GBIF-canonical name (or `NA` when
#'   no match was found). Default `FALSE` (exact name matching). Ignored when
#'   `species` is a `data.frame`.
#'
#' @return A `data.frame` with at minimum columns `species` and `mass_g`
#'   (predicted body mass in grams).
#'   - When `confidence_interval != FALSE`: also `lower_bound`, `upper_bound`,
#'     and `confidence`.
#'   - When `include_taxonomy = TRUE`: also `kingdom`, `phylum`, `class`,
#'     `order`, `family`, `genus`, `species_resolved`.
#'   - When `fuzzy_match_name = TRUE`: also `matched_name`.
#'   - Rows for unresolvable species contain `NA` for all numeric columns.
#'
#' @examples
#' \dontrun{
#' # Single species
#' TaxonBodyMassML::predict_mass("Homo sapiens")
#'
#' # Multiple species with 90% confidence interval
#' TaxonBodyMassML::predict_mass(
#'   c("Canis lupus", "Panthera leo"),
#'   confidence_interval = TRUE
#' )
#'
#' # Enable fuzzy name correction to tolerate misspellings
#' TaxonBodyMassML::predict_mass("Canis luupus", fuzzy_match_name = TRUE)
#'
#' # Skip taxonomy lookup by passing pre-resolved data.frame
#' tax <- lookup_taxonomy("Mus musculus")
#' TaxonBodyMassML::predict_mass(tax)
#' }
#'
#' @export
predict_mass <- function(species,
                    confidence_interval = FALSE,
                    method = "XGBoost",
                    include_taxonomy = FALSE,
                    fuzzy_match_name = FALSE) {

  if (!method %in% names(.METHODS)) {
    stop(sprintf(
      "Unknown method '%s'. Available: %s",
      method, paste(names(.METHODS), collapse = ", ")
    ), call. = FALSE)
  }

  level <- .resolve_ci_level(confidence_interval)

  # ---- Input validation (before any network call) -------------------------
  if (is.data.frame(species)) {
    required <- c("kingdom", "phylum", "class", "order", "family", "genus",
                  "species_resolved")
    missing_cols <- setdiff(required, names(species))
    if (length(missing_cols) > 0L) {
      stop(
        "Input data.frame is missing columns: ",
        paste(sQuote(missing_cols), collapse = ", "),
        call. = FALSE
      )
    }
  }

  .ensure_artifacts()

  # ---- Input handling -----------------------------------------------------
  if (is.data.frame(species)) {
    taxonomy_df   <- species
    matched_names <- NULL
    input_names <- if ("species" %in% names(species)) {
      as.character(species$species)
    } else {
      as.character(species$species_resolved)
    }
  } else {
    names_vec <- as.character(species)
    if (fuzzy_match_name) {
      tax_full      <- fuzzy_lookup_taxonomy(names_vec)
      matched_names <- tax_full$matched_name
      taxonomy_df   <- tax_full[
        , setdiff(names(tax_full), c("input_name", "matched_name")),
        drop = FALSE
      ]
    } else {
      taxonomy_df   <- lookup_taxonomy(names_vec)
      matched_names <- NULL
    }
    input_names <- as.character(taxonomy_df$species)
  }

  # ---- Split resolved / unresolved ----------------------------------------
  resolved_mask <- !is.na(taxonomy_df$species_resolved)

  if (!any(resolved_mask)) {
    warning("No species could be resolved; returning all-NA result.", call. = FALSE)
  }

  resolved_pos   <- which(resolved_mask)
  unresolved_pos <- which(!resolved_mask)

  rows <- list()

  if (any(resolved_mask)) {
    sub       <- taxonomy_df[resolved_mask, , drop = FALSE]
    sub_names <- input_names[resolved_mask]
    good <- .METHODS[[method]](sub, level, include_taxonomy, sub_names)
    good$..orig_idx.. <- resolved_pos
    rows[[length(rows) + 1L]] <- good
  }

  if (!all(resolved_mask)) {
    bad_names <- input_names[!resolved_mask]
    nan_df <- data.frame(
      species = bad_names,
      mass_g  = NA_real_,
      stringsAsFactors = FALSE
    )
    if (!is.null(level)) {
      nan_df$lower_bound <- NA_real_
      nan_df$upper_bound <- NA_real_
      nan_df$confidence  <- level
    }
    if (include_taxonomy) {
      tax_cols <- c("kingdom", "phylum", "class", "order", "family", "genus",
                    "species_resolved")
      for (col in tax_cols) {
        nan_df[[col]] <- NA_character_
      }
    }
    nan_df$..orig_idx.. <- unresolved_pos
    rows[[length(rows) + 1L]] <- nan_df
  }

  out <- do.call(rbind, rows)
  out <- out[order(out$..orig_idx..), , drop = FALSE]
  out$..orig_idx.. <- NULL
  rownames(out) <- NULL
  if (!is.null(matched_names)) {
    out$matched_name <- matched_names
  }
  out
}

# ---------------------------------------------------------------------------
# Public: fuzzy_predict_mass()
# ---------------------------------------------------------------------------

#' Predict body mass for potentially misspelled species names
#'
#' @description
#' `r lifecycle::badge("deprecated")`
#'
#' This function is deprecated. Use `predict_mass(..., fuzzy_match_name = TRUE)`
#' instead, which now performs GBIF name correction by default.
#'
#' @param species A character vector of scientific names (possibly misspelled).
#' @param ... Additional arguments passed to `predict_mass()`.
#'
#' @return A `data.frame` as returned by `predict_mass()`, with the `species`
#'   column reflecting the original input names and a `matched_name` column
#'   appended.
#'
#' @examples
#' \dontrun{
#' # Deprecated — use predict_mass() directly:
#' predict_mass(c("Ballanus glandula", "Canis lupus"))
#' }
#'
#' @export
fuzzy_predict_mass <- function(species, ...) {
  .Deprecated(
    "predict_mass",
    msg = paste(
      "'fuzzy_predict_mass()' is deprecated.",
      "Use 'predict_mass(..., fuzzy_match_name = TRUE)' instead."
    )
  )
  predict_mass(as.character(species), fuzzy_match_name = TRUE, ...)
}
