#' Fuzzy species-name matching via GBIF
#'
#' @description
#' These functions wrap the existing strict taxonomy functions with a GBIF
#' fuzzy-matching pre-pass. The underlying `lookup_taxonomy()` and
#' `predict_mass()` functions assume species names are correctly spelled;
#' call these variants when names may be misspelled or non-canonical.
#'
#' @name fuzzy
NULL

# ---------------------------------------------------------------------------
# Internal: ask GBIF for its canonical match for a single name
# Returns the matched species string, or NA_character_ on no match.
# ---------------------------------------------------------------------------

.gbif_fuzzy_name <- function(name) {
  tryCatch({
    resp <- .tbm_get(.GBIF_URL, list(scientificName = name))
    if (httr2::resp_status(resp) != 200L) return(NA_character_)
    data <- httr2::resp_body_json(resp, simplifyVector = TRUE)
    match_type <- data[["matchType"]]
    if (is.null(match_type)) return(NA_character_)

    if (match_type %in% c("EXACT", "FUZZY")) {
      matched <- data[["species"]]
      if (is.null(matched) || is.na(matched) || nchar(matched) == 0L) return(NA_character_)
      return(as.character(matched))
    }

    if (match_type == "HIGHERRANK") {
      corrected_genus <- data[["genus"]]
      parts <- strsplit(trimws(name), "\\s+")[[1]]
      if (!is.null(corrected_genus) && !is.na(corrected_genus) &&
          nchar(corrected_genus) > 0L && length(parts) >= 2L) {
        candidate <- paste(corrected_genus, parts[[2]])
        if (!identical(candidate, name)) {
          resp2 <- .tbm_get(.GBIF_URL, list(scientificName = candidate))
          if (httr2::resp_status(resp2) == 200L) {
            data2 <- httr2::resp_body_json(resp2, simplifyVector = TRUE)
            if (!is.null(data2[["matchType"]]) &&
                data2[["matchType"]] %in% c("EXACT", "FUZZY")) {
              matched2 <- data2[["species"]]
              if (!is.null(matched2) && !is.na(matched2) && nchar(matched2) > 0L)
                return(as.character(matched2))
            }
          }
        }
      }
    }

    NA_character_
  }, error = function(e) NA_character_)
}

# ---------------------------------------------------------------------------
# Public: correct_species_names()
# ---------------------------------------------------------------------------

#' Suggest corrected species names using GBIF fuzzy matching
#'
#' Queries the GBIF species-match endpoint for each name and returns the
#' canonical matched name.  Use this to inspect potential corrections before
#' passing names to `lookup_taxonomy()` or `predict_mass()`.
#'
#' @param species A character vector of scientific names (possibly misspelled).
#'
#' @return A `data.frame` with columns `input_name` (the original string) and
#'   `matched_name` (GBIF's canonical name, or `NA` when no match was found).
#'
#' @examples
#' \dontrun{
#' correct_species_names(c("Ballanus glandula", "Homo sapiens"))
#' }
#'
#' @export
correct_species_names <- function(species) {
  names_vec <- as.character(species)
  n <- length(names_vec)
  limit_cores <- nzchar(Sys.getenv("_R_CHECK_LIMIT_CORES_")) &&
    !identical(toupper(Sys.getenv("_R_CHECK_LIMIT_CORES_")), "FALSE")
  workers <- if (n > 1L && .Platform$OS.type != "windows") {
    if (limit_cores) min(n, 2L) else min(n, 8L)
  } else 1L

  if (workers > 1L) {
    raw <- parallel::mclapply(names_vec, .gbif_fuzzy_name, mc.cores = workers)
    matched <- vapply(raw, function(x) {
      if (is.null(x) || inherits(x, "try-error")) NA_character_ else x
    }, character(1L))
  } else {
    matched <- vapply(names_vec, .gbif_fuzzy_name, character(1L))
  }

  data.frame(
    input_name   = names_vec,
    matched_name = matched,
    stringsAsFactors = FALSE
  )
}

# ---------------------------------------------------------------------------
# Public: fuzzy_lookup_taxonomy()
# ---------------------------------------------------------------------------

#' Look up taxonomy for potentially misspelled species names
#'
#' Runs `correct_species_names()` first to obtain GBIF-canonical names, then
#' calls `lookup_taxonomy()` with the corrected names.  A warning is issued
#' listing any names that were auto-corrected.
#'
#' @param species A character vector of scientific names (possibly misspelled).
#'
#' @return A `data.frame` with the same columns as `lookup_taxonomy()`, plus
#'   `input_name` (the original string) and `matched_name` (the GBIF canonical
#'   name used for lookup, or `NA` when no correction was found and the
#'   original name was used as-is).
#'
#' @examples
#' \dontrun{
#' fuzzy_lookup_taxonomy(c("Ballanus glandula", "Homo sapiens"))
#' }
#'
#' @export
fuzzy_lookup_taxonomy <- function(species) {
  corrections <- correct_species_names(species)

  # Use matched_name where GBIF found one; otherwise fall back to input_name
  lookup_names <- ifelse(
    is.na(corrections$matched_name),
    corrections$input_name,
    corrections$matched_name
  )

  changed <- !is.na(corrections$matched_name) &
    corrections$matched_name != corrections$input_name
  if (any(changed)) {
    pairs <- paste(
      corrections$input_name[changed], "->", corrections$matched_name[changed],
      collapse = "; "
    )
    warning(
      "Fuzzy-matched ", sum(changed), " name(s): ", pairs,
      call. = FALSE
    )
  }

  tax_df <- lookup_taxonomy(lookup_names)

  # Prepend the original input names and matched names for traceability
  tax_df$input_name   <- corrections$input_name
  tax_df$matched_name <- corrections$matched_name
  col_order <- c(
    "input_name", "matched_name",
    setdiff(names(tax_df), c("input_name", "matched_name"))
  )
  tax_df[, col_order, drop = FALSE]
}
