# ---------------------------------------------------------------------------
# CI level resolver
# ---------------------------------------------------------------------------

.resolve_interval_method <- function(method) {
  if (!method %in% c("stratified", "pooled"))
    stop(
      'interval_method must be "stratified" or "pooled". Got: ', deparse(method),
      call. = FALSE
    )
  method
}

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
# Source rank inference for model-inferred rows
# ---------------------------------------------------------------------------

.infer_source_rank <- function(taxonomy_df, cats) {
  ranks <- c("genus", "family", "order", "class", "phylum", "kingdom")
  cols  <- c("species_resolved", ranks)
  apply(taxonomy_df[, cols, drop = FALSE], 1, function(row) {
    # Genus names land in species_resolved (not genus) via NCBI lookup when
    # GBIF matches at genus rank. Check before iterating the standard ranks.
    sr <- iconv(row[["species_resolved"]], to = "ASCII//TRANSLIT")
    g  <- iconv(row[["genus"]], to = "ASCII//TRANSLIT")
    if (!is.na(sr) && (is.na(g) || identical(g, "UNK")) && sr %in% cats[["genus"]])
      return("tbmML_genus")
    for (rank in ranks) {
      val <- iconv(row[[rank]], to = "ASCII//TRANSLIT")
      if (!is.na(val) && val != "UNK" && val %in% cats[[rank]])
        return(paste0("tbmML_", rank))
    }
    "tbmML_UNK"
  })
}

# ---------------------------------------------------------------------------
# Shared output assembler
# ---------------------------------------------------------------------------

.assemble_output <- function(log_preds, taxonomy_df, level, residuals,
                              input_names, include_taxonomy, include_source,
                              cats = NULL, interval_method = "pooled",
                              by_rank_residuals = NULL) {
  result <- data.frame(
    taxon  = input_names,
    mass_g = 10^log_preds,
    stringsAsFactors = FALSE
  )

  if (!is.null(level) && !is.null(residuals)) {
    if (identical(interval_method, "stratified") && !is.null(by_rank_residuals)) {
      if (is.null(cats)) cats <- .load_categories()
      source_rnks <- .infer_source_rank(taxonomy_df, cats)
      rank_keys   <- sub("^tbmML_", "", source_rnks)
      q_vec <- vapply(rank_keys, function(r) {
        res <- by_rank_residuals[[r]]
        if (is.null(res) || length(res) < 10L)
          as.numeric(stats::quantile(residuals, level))
        else
          as.numeric(stats::quantile(res, level))
      }, numeric(1L))
      result$lower_bound <- 10^(log_preds - q_vec)
      result$upper_bound <- 10^(log_preds + q_vec)
      result$confidence  <- level
    } else {
      q <- as.numeric(stats::quantile(residuals, level))
      result$lower_bound <- 10^(log_preds - q)
      result$upper_bound <- 10^(log_preds + q)
      result$confidence  <- level
    }
  } else if (!is.null(level)) {
    result$lower_bound <- NA_real_
    result$upper_bound <- NA_real_
    result$confidence  <- level
  }

  if (include_taxonomy) {
    tax_cols <- c("kingdom", "phylum", "class", "order", "family", "genus", "species_resolved")
    result   <- cbind(result, taxonomy_df[, tax_cols, drop = FALSE])
    rownames(result) <- NULL
  }

  if (include_source) {
    if (is.null(cats)) cats <- .load_categories()
    result$source <- .infer_source_rank(taxonomy_df, cats)
  }

  result
}

# ---------------------------------------------------------------------------
# GBIF v2 → training-data taxonomy normalisation
# ---------------------------------------------------------------------------

# GBIF v2 uses clade-based kingdom names; training data was built with the
# older GBIF v1 / Catalogue of Life names.  Map the known divergences so that
# taxonomy resolved via GBIF v2 still hits the correct model categories.
.GBIF_KINGDOM_NORM <- c("Metazoa" = "Animalia", "Plantae" = "Viridiplantae")

.normalise_kingdom <- function(x) {
  norm <- .GBIF_KINGDOM_NORM[x]
  ifelse(!is.na(norm), norm, x)
}

# ---------------------------------------------------------------------------
# Shared UNK mapping for tree-based methods
# ---------------------------------------------------------------------------

.apply_unk_mapping <- function(taxonomy_df, cats) {
  COLS <- c("kingdom", "phylum", "class", "order", "family", "genus", "species")
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
  for (col in COLS) X[[col]] <- iconv(X[[col]], to = "ASCII//TRANSLIT")
  # Apply GBIF v2 kingdom remapping after transliteration, matching Python order.
  X$kingdom <- .normalise_kingdom(X$kingdom)
  # Genus names queried via NCBI land in species_resolved with genus left as
  # "UNK". Promote them to the correct slot so the model uses genus embeddings.
  promote <- (is.na(X$genus) | X$genus == "UNK") & (X$species %in% setdiff(cats[["genus"]], "UNK"))
  X$genus[promote]   <- X$species[promote]
  X$species[promote] <- "UNK"
  for (col in COLS) {
    valid    <- cats[[col]]
    X[[col]] <- ifelse(X[[col]] %in% valid, X[[col]], "UNK")
    X[[col]] <- factor(X[[col]], levels = valid)
  }
  X
}

# ---------------------------------------------------------------------------
# XGBoost inference
# ---------------------------------------------------------------------------

.predict_xgboost <- function(taxonomy_df, level, include_taxonomy,
                              input_names, include_source,
                              interval_method = "pooled") {
  cats  <- .load_categories()
  X     <- .apply_unk_mapping(taxonomy_df, cats)
  model <- .load_model()
  X     <- X[, model$feature_names]
  dmat      <- xgboost::xgb.DMatrix(data = X, enable_categorical = TRUE)
  log_preds <- stats::predict(model, dmat)
  residuals <- if (!is.null(level)) .load_calibration() else NULL
  by_rank   <- if (!is.null(level) && identical(interval_method, "stratified"))
                 .load_calibration_by_rank() else NULL
  .assemble_output(log_preds, taxonomy_df, level, residuals,
                   input_names, include_taxonomy, include_source, cats,
                   interval_method, by_rank)
}

# ---------------------------------------------------------------------------
# GPBoost inference
# ---------------------------------------------------------------------------

.predict_gpboost <- function(taxonomy_df, level, include_taxonomy,
                              input_names, include_source,
                              interval_method = "pooled") {
  if (!requireNamespace("gpboost", quietly = TRUE)) {
    stop(
      'Package "gpboost" is required for method = "GPBoost". ',
      'Install it with: install.packages("gpboost")',
      call. = FALSE
    )
  }

  cats <- .load_categories()
  X    <- .apply_unk_mapping(taxonomy_df, cats)

  # Group data for nested random effects: species -> genus -> family -> order -> class.
  # Built from promoted X so genus-level random effects use the promoted name,
  # not the raw 'UNK' that NCBI genus-rank hits carry in taxonomy_df.
  group_data <- as.matrix(data.frame(
    species = as.character(X$species),
    genus   = as.character(X$genus),
    family  = as.character(X$family),
    order   = as.character(X$order),
    class   = as.character(X$class),
    stringsAsFactors = FALSE
  ))
  group_data[is.na(group_data)] <- "UNK"

  booster   <- .load_gpboost_model()
  log_preds <- booster$predict(data = X, group_data_pred = group_data)
  residuals <- if (!is.null(level)) .load_calibration_gpboost() else NULL
  by_rank   <- if (!is.null(level) && identical(interval_method, "stratified"))
                 .load_calibration_by_rank_gpboost() else NULL
  .assemble_output(log_preds, taxonomy_df, level, residuals,
                   input_names, include_taxonomy, include_source, cats,
                   interval_method, by_rank)
}

# ---------------------------------------------------------------------------
# Entity Embeddings inference
# ---------------------------------------------------------------------------

.EE_DIMS <- c(kingdom = 4L, phylum = 8L, class = 8L, order = 16L,
              family = 16L, genus = 32L, species = 32L)
.EE_TOTAL_DIM <- sum(.EE_DIMS)  # 116L

.predict_entity_embeddings <- function(taxonomy_df, level, include_taxonomy,
                                        input_names, include_source,
                                        interval_method = "pooled") {
  embs     <- .load_embeddings()
  model_ee <- .load_model_ee()
  residuals <- if (!is.null(level)) .load_calibration_ee() else NULL

  col_map <- c(kingdom = "kingdom", phylum = "phylum", class = "class",
               order = "order", family = "family", genus = "genus",
               species = "species_resolved")

  n     <- nrow(taxonomy_df)
  X_mat <- matrix(0.0, nrow = n, ncol = .EE_TOTAL_DIM)
  offset <- 1L
  ee_promote_mask <- rep(FALSE, n)

  for (col in names(.EE_DIMS)) {
    dim      <- .EE_DIMS[[col]]
    col_embs <- embs[[col]]
    unk_vec  <- unlist(col_embs[["UNK"]])
    src_col  <- col_map[[col]]
    vals     <- iconv(as.character(taxonomy_df[[src_col]]), to = "ASCII//TRANSLIT")
    if (identical(col, "kingdom")) vals <- .normalise_kingdom(vals)
    if (identical(col, "genus")) {
      sp_vals         <- iconv(as.character(taxonomy_df$species_resolved), to = "ASCII//TRANSLIT")
      genus_vocab     <- setdiff(names(col_embs), "UNK")
      promote         <- (is.na(vals) | vals == "UNK") & !is.na(sp_vals) & (sp_vals %in% genus_vocab)
      vals[promote]   <- sp_vals[promote]
      ee_promote_mask <- promote
    }
    if (identical(col, "species") && any(ee_promote_mask)) {
      # Write UNK into species for rows whose genus was promoted from species_resolved.
      vals[ee_promote_mask] <- "UNK"
    }
    vals[is.na(vals)] <- "UNK"
    for (i in seq_len(n)) {
      vec <- if (!is.null(col_embs[[vals[i]]])) unlist(col_embs[[vals[i]]]) else unk_vec
      X_mat[i, offset:(offset + dim - 1L)] <- vec
    }
    offset <- offset + dim
  }

  dmat      <- xgboost::xgb.DMatrix(data = X_mat)
  log_preds <- stats::predict(model_ee, dmat)
  by_rank   <- if (!is.null(level) && identical(interval_method, "stratified"))
                 .load_calibration_by_rank_ee() else NULL
  .assemble_output(log_preds, taxonomy_df, level, residuals,
                   input_names, include_taxonomy, include_source,
                   interval_method = interval_method,
                   by_rank_residuals = by_rank)
}

# ---------------------------------------------------------------------------
# Method dispatch table
# ---------------------------------------------------------------------------

.METHODS <- list(
  XGBoost          = .predict_xgboost,
  GPBoost          = .predict_gpboost,
  EntityEmbeddings = .predict_entity_embeddings
)

# ---------------------------------------------------------------------------
# Public: predict_mass()
# ---------------------------------------------------------------------------

#' Predict body mass for one or more taxa
#'
#' @description
#' Predicts body mass (in grams) using the TaxonBodyMassML XGBoost model.
#' When `taxon` is a character vector, taxonomy is resolved automatically via
#' GBIF and NCBI. For taxa whose species-level mass appears directly in the
#' training data, the empirical value is returned without invoking the model.
#' Pass a `data.frame` with pre-resolved taxonomy columns to skip lookup.
#'
#' @param taxon A character vector of scientific names, or a `data.frame`
#'   with columns `kingdom`, `phylum`, `class`, `order`, `family`, `genus`,
#'   and `species_resolved` (as returned by `lookup_taxonomy()`).
#' @param confidence_interval `FALSE` (default, no interval), `TRUE` (90%
#'   conformal prediction interval), or a numeric in (0, 1) for a custom
#'   coverage level. Conformal intervals apply only to model-inferred values;
#'   rows returned from the training-data dictionary receive `NA` bounds.
#' @param interval_method Character. How the conformal half-width is computed
#'   when `confidence_interval` is not `FALSE`. `"stratified"` (default) uses
#'   rank-specific calibration residuals, providing approximate conditional
#'   coverage per taxonomic rank. `"pooled"` applies a single quantile from all
#'   calibration residuals, providing the marginal conformal guarantee.
#' @param method Character. Prediction method. Currently only `"XGBoost"`
#'   is supported.
#' @param include_taxonomy Logical. If `TRUE`, append the resolved taxonomy
#'   columns to the output. Default `FALSE`.
#' @param fuzzy_match_name Logical. If `TRUE`, species names are first
#'   corrected via the GBIF species-match API before taxonomy lookup,
#'   tolerating misspellings and minor name variants. A `matched_name` column
#'   is appended to the output: it contains the originally entered name when a
#'   correction was applied or no GBIF match was found; `NA` when the name was
#'   already canonical. Default `FALSE` (exact name matching). Ignored when
#'   `taxon` is a `data.frame`.
#' @param include_source Logical. If `TRUE`, append a `source` column
#'   identifying the provenance of each returned mass value. For taxa returned
#'   directly from the training-data dictionary the value is the original
#'   source identifier (e.g., `"fishbase"`, `"Novak_unpubl"`). For
#'   model-inferred values it is `"tbmML_"` followed by the finest taxonomic
#'   rank present in the training data (e.g., `"tbmML_genus"` if the genus
#'   was seen during training; `"tbmML_order"` if only the order was seen).
#'   Unresolvable taxa receive `NA`. Default `FALSE`.
#' @param lookup Logical. If `TRUE` (default), taxa found in the training-data
#'   dictionary are returned with their empirical mass and bypass the model. If
#'   `FALSE`, every resolved taxon is passed through the model specified by
#'   `method`. Default `TRUE`.
#'
#' @return A `data.frame` with at minimum columns `taxon` and `mass_g`
#'   (body mass in grams).
#'   - When `confidence_interval != FALSE`: also `lower_bound`, `upper_bound`,
#'     and `confidence` (NA for dictionary-sourced rows).
#'   - When `include_taxonomy = TRUE`: also `kingdom`, `phylum`, `class`,
#'     `order`, `family`, `genus`, `species_resolved`.
#'   - When `fuzzy_match_name = TRUE`: also `matched_name` (the originally
#'     entered name if corrected or unmatched; `NA` if no correction was
#'     needed).
#'   - When `include_source = TRUE`: also `source`.
#'   - Rows for unresolvable inputs contain `NA` for all numeric columns.
#'
#' @examples
#' \dontrun{
#' # Single taxon — returns empirical mass if in training data, else model
#' TaxonBodyMassML::predict_mass("Homo sapiens")
#'
#' # Multiple taxa with 90% confidence interval
#' TaxonBodyMassML::predict_mass(
#'   c("Canis lupus", "Panthera leo"),
#'   confidence_interval = TRUE
#' )
#'
#' # Show provenance of each returned value
#' TaxonBodyMassML::predict_mass(
#'   c("Nucella ostrina", "Nucella lima"),
#'   include_source = TRUE
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
predict_mass <- function(taxon,
                    confidence_interval = FALSE,
                    method = "XGBoost",
                    interval_method = "stratified",
                    include_taxonomy = FALSE,
                    fuzzy_match_name = FALSE,
                    include_source = FALSE,
                    lookup = TRUE) {

  if (!method %in% names(.METHODS)) {
    stop(sprintf(
      "Unknown method '%s'. Available: %s",
      method, paste(names(.METHODS), collapse = ", ")
    ), call. = FALSE)
  }

  interval_method <- .resolve_interval_method(interval_method)
  level <- .resolve_ci_level(confidence_interval)

  # ---- Input validation (before any network call) -------------------------
  if (is.data.frame(taxon)) {
    required <- c("kingdom", "phylum", "class", "order", "family", "genus",
                  "species_resolved")
    missing_cols <- setdiff(required, names(taxon))
    if (length(missing_cols) > 0L) {
      stop(
        "Input data.frame is missing columns: ",
        paste(sQuote(missing_cols), collapse = ", "),
        call. = FALSE
      )
    }
  }

  if ((!is.data.frame(taxon) && length(taxon) == 0L) ||
      (is.data.frame(taxon) && nrow(taxon) == 0L)) {
    empty_cols <- c("taxon", "mass_g")
    if (!is.null(level))     empty_cols <- c(empty_cols, "lower_bound", "upper_bound", "confidence")
    if (include_taxonomy)    empty_cols <- c(empty_cols, "kingdom", "phylum", "class", "order",
                                             "family", "genus", "species_resolved")
    if (include_source)      empty_cols <- c(empty_cols, "source")
    if (fuzzy_match_name && !is.data.frame(taxon)) empty_cols <- c(empty_cols, "matched_name")
    return(as.data.frame(setNames(lapply(empty_cols, function(.) character(0L)), empty_cols),
                         stringsAsFactors = FALSE))
  }

  .ensure_artifacts()

  # ---- Input handling -----------------------------------------------------
  if (is.data.frame(taxon)) {
    taxonomy_df   <- taxon
    matched_names <- NULL
    input_names <- if ("species" %in% names(taxon)) {
      as.character(taxon$species)
    } else {
      as.character(taxon$species_resolved)
    }
  } else {
    names_vec <- as.character(taxon)
    if (fuzzy_match_name) {
      tax_full    <- fuzzy_lookup_taxonomy(names_vec)
      corrected   <- !is.na(tax_full$matched_name) &
                       tax_full$matched_name != tax_full$input_name
      no_match    <- is.na(tax_full$matched_name)
      input_names   <- ifelse(corrected,  tax_full$matched_name,
                       ifelse(no_match,   NA_character_,
                                          tax_full$input_name))
      matched_names <- ifelse(corrected | no_match,
                              tax_full$input_name, NA_character_)
      taxonomy_df <- tax_full[
        , setdiff(names(tax_full), c("input_name", "matched_name")),
        drop = FALSE
      ]
    } else {
      taxonomy_df   <- lookup_taxonomy(names_vec)
      input_names   <- as.character(taxonomy_df$species)
      matched_names <- NULL
    }
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

    # ---- Dictionary lookup (optional): return empirical mass for known species ---
    if (lookup) {
      lkp      <- .load_lookup()
      hit_mask <- sub$species_resolved %in% names(lkp)
      dict_pos  <- which(hit_mask)
      model_pos <- which(!hit_mask)
    } else {
      dict_pos  <- integer(0L)
      model_pos <- seq_len(nrow(sub))
    }

    if (length(dict_pos) > 0L) {
      dict_sub   <- sub[dict_pos, , drop = FALSE]
      dict_names <- sub_names[dict_pos]
      dict_df <- data.frame(
        taxon  = dict_names,
        mass_g  = vapply(dict_sub$species_resolved,
                         function(sp) lkp[[sp]]$mass_g, numeric(1L)),
        stringsAsFactors = FALSE
      )
      if (!is.null(level)) {
        dict_df$lower_bound <- NA_real_
        dict_df$upper_bound <- NA_real_
        dict_df$confidence  <- NA_real_
      }
      if (include_taxonomy) {
        tax_cols <- c("kingdom", "phylum", "class", "order", "family",
                      "genus", "species_resolved")
        dict_df <- cbind(dict_df, dict_sub[, tax_cols, drop = FALSE])
        rownames(dict_df) <- NULL
      }
      if (include_source) {
        dict_df$source <- vapply(dict_sub$species_resolved,
                                 function(sp) lkp[[sp]]$source, character(1L))
      }
      dict_df$..orig_idx.. <- resolved_pos[dict_pos]
      rows[[length(rows) + 1L]] <- dict_df
    }

    if (length(model_pos) > 0L) {
      model_sub   <- sub[model_pos, , drop = FALSE]
      model_names <- sub_names[model_pos]
      good <- .METHODS[[method]](model_sub, level, include_taxonomy,
                                 model_names, include_source, interval_method)
      good$..orig_idx.. <- resolved_pos[model_pos]
      rows[[length(rows) + 1L]] <- good
    }
  }

  if (!all(resolved_mask)) {
    bad_names <- input_names[!resolved_mask]
    nan_df <- data.frame(
      taxon  = bad_names,
      mass_g  = NA_real_,
      stringsAsFactors = FALSE
    )
    if (!is.null(level)) {
      nan_df$lower_bound <- NA_real_
      nan_df$upper_bound <- NA_real_
      nan_df$confidence  <- NA_real_
    }
    if (include_taxonomy) {
      tax_cols <- c("kingdom", "phylum", "class", "order", "family", "genus",
                    "species_resolved")
      for (col in tax_cols) {
        nan_df[[col]] <- NA_character_
      }
    }
    if (include_source) {
      nan_df$source <- NA_character_
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
#' @param taxon A character vector of scientific names (possibly misspelled).
#' @param ... Additional arguments passed to `predict_mass()`.
#'
#' @return A `data.frame` as returned by `predict_mass()`, with the `taxon`
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
fuzzy_predict_mass <- function(taxon, ...) {
  .Deprecated(
    "predict_mass",
    msg = paste(
      "'fuzzy_predict_mass()' is deprecated.",
      "Use 'predict_mass(..., fuzzy_match_name = TRUE)' instead."
    )
  )
  predict_mass(as.character(taxon), fuzzy_match_name = TRUE, ...)
}
