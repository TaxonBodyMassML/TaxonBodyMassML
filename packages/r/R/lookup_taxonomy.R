#' Resolve species names to 7-rank taxonomy
#'
#' @description
#' Looks up taxonomy for one or more scientific names using the GBIF
#' fuzzy-match API, with an NCBI Entrez fallback for names that GBIF cannot
#' resolve. Results are cached in-memory for the R session and optionally
#' on disk when `tbm_options(disk_cache = TRUE)`.
#'
#' @name lookup_taxonomy
NULL

# API endpoints
.GBIF_URL  <- "https://api.gbif.org/v2/species/match"
.NCBI_ESEARCH <- "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
.NCBI_EFETCH  <- "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# The 7 standard taxonomy ranks (column names)
.TAX_COLS <- c("kingdom", "phylum", "class", "order", "family", "genus", "species")

# ---------------------------------------------------------------------------
# Name normalisation
# ---------------------------------------------------------------------------

.normalise_name <- function(name) {
  tolower(trimws(gsub("_", " ", name)))
}

.safe_name <- function(name) {
  gsub("[^a-z0-9_]", "_", .normalise_name(name))
}

# ---------------------------------------------------------------------------
# Disk cache helpers
# ---------------------------------------------------------------------------

.tax_cache_dir <- function() {
  file.path(tools::R_user_dir("TaxonBodyMassML", "cache"), "taxonomy")
}

.disk_cache_path <- function(norm_name) {
  file.path(.tax_cache_dir(), paste0(.safe_name(norm_name), ".rds"))
}

.read_disk_cache <- function(norm_name) {
  p <- .disk_cache_path(norm_name)
  if (file.exists(p)) readRDS(p) else NULL
}

.write_disk_cache <- function(norm_name, value) {
  dir.create(.tax_cache_dir(), recursive = TRUE, showWarnings = FALSE)
  saveRDS(value, .disk_cache_path(norm_name))
}

# ---------------------------------------------------------------------------
# GBIF lookup
# ---------------------------------------------------------------------------

.gbif_lookup <- function(name) {
  tryCatch({
    resp <- .tbm_get(.GBIF_URL, list(scientificName = name))
    if (httr2::resp_status(resp) != 200L) return(NULL)
    data <- httr2::resp_body_json(resp, simplifyVector = TRUE)
    # GBIF returns kingdom, phylum, class, order, family, genus, species
    result <- lapply(.TAX_COLS, function(col) {
      v <- data[[col]]
      if (is.null(v) || is.na(v) || nchar(v) == 0L) NA_character_ else as.character(v)
    })
    names(result) <- .TAX_COLS
    result
  }, error = function(e) NULL)
}

# ---------------------------------------------------------------------------
# NCBI lookup
# ---------------------------------------------------------------------------

.parse_ncbi_xml <- function(xml_text) {
  tryCatch({
    doc <- xml2::read_xml(xml_text)
    taxons <- list()

    # Parse LineageEx taxa
    lineage_nodes <- xml2::xml_find_all(doc, ".//LineageEx/Taxon")
    for (node in lineage_nodes) {
      rank <- xml2::xml_text(xml2::xml_find_first(node, "Rank"))
      sname <- xml2::xml_text(xml2::xml_find_first(node, "ScientificName"))
      if (!is.na(rank) && nchar(rank) > 0 && rank %in% .TAX_COLS) {
        taxons[[rank]] <- sname
      }
    }

    # Species from top-level ScientificName
    sp_node <- xml2::xml_find_first(doc, ".//ScientificName")
    if (!inherits(sp_node, "xml_missing")) {
      taxons[["species"]] <- xml2::xml_text(sp_node)
    }

    taxons
  }, error = function(e) list())
}

.ncbi_lookup <- function(name) {
  tryCatch({
    resp <- .ncbi_get(.NCBI_ESEARCH, list(
      db = "taxonomy", term = name, retmode = "json"
    ))
    if (httr2::resp_status(resp) != 200L) return(NULL)
    ids <- httr2::resp_body_json(resp)[["esearchresult"]][["idlist"]]
    if (length(ids) == 0L) return(NULL)

    resp2 <- .ncbi_get(.NCBI_EFETCH, list(
      db = "taxonomy", id = ids[[1L]], retmode = "xml"
    ))
    if (httr2::resp_status(resp2) != 200L) return(NULL)

    taxons <- .parse_ncbi_xml(httr2::resp_body_string(resp2))
    if (length(taxons) == 0L) return(NULL)

    result <- lapply(.TAX_COLS, function(col) {
      v <- taxons[[col]]
      if (is.null(v) || is.na(v)) NA_character_ else as.character(v)
    })
    names(result) <- .TAX_COLS
    result
  }, error = function(e) NULL)
}

# ---------------------------------------------------------------------------
# Cache helpers shared by both resolution paths
# ---------------------------------------------------------------------------

.cache_lookup <- function(key) {
  # Returns cached result (list) or NULL if not in any cache.
  if (exists(key, envir = .tbm_cache, inherits = FALSE)) {
    return(get(key, envir = .tbm_cache, inherits = FALSE))
  }
  if (isTRUE(.tbm_opts$disk_cache)) {
    cached <- .read_disk_cache(key)
    if (!is.null(cached)) {
      assign(key, cached, envir = .tbm_cache)
      return(cached)
    }
  }
  NULL
}

.cache_store <- function(key, tax) {
  assign(key, tax, envir = .tbm_cache)
  if (isTRUE(.tbm_opts$disk_cache)) {
    .write_disk_cache(key, tax)
  }
}

.apply_unk <- function(tax) {
  for (col in .TAX_COLS) {
    if (is.na(tax[[col]])) tax[[col]] <- "UNK"
  }
  tax
}

# ---------------------------------------------------------------------------
# GBIF-only resolution (used in parallel pass; no NCBI)
#
# Returns the complete taxonomy list if GBIF resolves all 7 ranks, or NULL
# if the result is missing any field (caller will do NCBI serially).
# ---------------------------------------------------------------------------

.resolve_gbif_only <- function(name) {
  key <- .normalise_name(name)

  cached <- .cache_lookup(key)
  if (!is.null(cached)) return(cached)

  tax <- .gbif_lookup(name)

  # Only accept a fully-resolved GBIF result here; leave partials for NCBI
  if (is.null(tax) || any(is.na(unlist(tax)))) return(NULL)

  tax <- .apply_unk(tax)
  if (all(unlist(tax) == "UNK")) return(NULL)

  .cache_store(key, tax)
  tax
}

# ---------------------------------------------------------------------------
# Full resolution with NCBI fallback (used serially for GBIF misses)
# ---------------------------------------------------------------------------

.resolve_one <- function(name) {
  key <- .normalise_name(name)

  cached <- .cache_lookup(key)
  if (!is.null(cached)) return(cached)

  tax <- .gbif_lookup(name)

  # NCBI fallback for any missing fields
  if (is.null(tax) || any(is.na(unlist(tax)))) {
    ncbi <- .ncbi_lookup(name)
    if (!is.null(ncbi)) {
      if (is.null(tax)) {
        tax <- ncbi
      } else {
        for (col in .TAX_COLS) {
          if (is.na(tax[[col]]) && !is.na(ncbi[[col]])) {
            tax[[col]] <- ncbi[[col]]
          }
        }
      }
    }
  }

  if (!is.null(tax)) {
    tax <- .apply_unk(tax)
  }

  if (!is.null(tax) && all(unlist(tax) == "UNK")) {
    tax <- NULL
  }

  if (!is.null(tax)) {
    .cache_store(key, tax)
  }

  tax
}

# ---------------------------------------------------------------------------
# Public: lookup_taxonomy()
# ---------------------------------------------------------------------------

#' Look up 7-rank taxonomy for scientific names
#'
#' Resolves species names via the GBIF fuzzy-match API with an NCBI Entrez
#' fallback. Results are cached in memory for the current R session.
#'
#' When looking up more than one name, GBIF queries are run in parallel
#' (Unix/macOS only). Any names GBIF cannot fully resolve are then passed to
#' NCBI Entrez serially so that NCBI rate limits are respected.
#'
#' @param species A character vector of scientific names.
#'
#' @return A `data.frame` with columns `species`, `kingdom`, `phylum`,
#'   `class`, `order`, `family`, `genus`, and `species_resolved`. Rows for
#'   names that could not be resolved contain `NA` in all taxonomy columns and
#'   trigger a `warning()`.
#'
#' @examples
#' \dontrun{
#' lookup_taxonomy("Homo sapiens")
#' lookup_taxonomy(c("Canis lupus", "Panthera leo"))
#' }
#'
#' @export
lookup_taxonomy <- function(species) {
  names_vec <- as.character(species)
  n <- length(names_vec)

  show_progress <- (
    isTRUE(.tbm_opts$progress) &&
    n > 10L &&
    requireNamespace("cli", quietly = TRUE)
  )

  # Parallel GBIF pass (Unix/macOS only; Windows uses lapply).
  # GBIF does not require rate limiting, so parallel workers are safe.
  # Any names that GBIF cannot fully resolve are collected for a serial
  # NCBI pass below, keeping NCBI rate limiting effective.
  workers <- if (n > 1L && .Platform$OS.type != "windows") min(n, 8L) else 1L

  if (workers > 1L) {
    if (show_progress) {
      message("Resolving taxonomy for ", n, " species in parallel (",
              workers, " workers, GBIF pass)...")
    }
    # Pass 1: parallel GBIF-only
    results <- parallel::mclapply(names_vec, .resolve_gbif_only, mc.cores = workers)

    # Backfill session cache: mclapply uses fork(), so child-process cache
    # writes are invisible to the parent.
    for (i in seq_len(n)) {
      if (!is.null(results[[i]])) {
        .cache_store(.normalise_name(names_vec[[i]]), results[[i]])
      }
    }

    # Pass 2: serial NCBI fallback for names not resolved by GBIF
    ncbi_needed <- which(vapply(results, is.null, logical(1L)))
    if (length(ncbi_needed) > 0L) {
      if (show_progress) {
        message("  NCBI fallback (serial) for ", length(ncbi_needed), " species...")
      }
      for (i in ncbi_needed) {
        results[[i]] <- .resolve_one(names_vec[[i]])
      }
    }

  } else if (show_progress) {
    pb <- cli::cli_progress_bar("Resolving taxonomy", total = n)
    results <- vector("list", n)
    for (i in seq_len(n)) {
      results[[i]] <- .resolve_one(names_vec[[i]])
      cli::cli_progress_update(id = pb)
    }
    cli::cli_progress_done(id = pb)
  } else {
    results <- lapply(names_vec, .resolve_one)
  }

  # Build output data.frame
  unresolvable <- character(0L)
  rows <- vector("list", n)

  for (i in seq_len(n)) {
    nm <- names_vec[[i]]
    tax <- results[[i]]
    if (is.null(tax)) {
      unresolvable <- c(unresolvable, nm)
      rows[[i]] <- data.frame(
        species          = nm,
        kingdom          = NA_character_,
        phylum           = NA_character_,
        class            = NA_character_,
        order            = NA_character_,
        family           = NA_character_,
        genus            = NA_character_,
        species_resolved = NA_character_,
        stringsAsFactors = FALSE
      )
    } else {
      rows[[i]] <- data.frame(
        species          = nm,
        kingdom          = tax[["kingdom"]],
        phylum           = tax[["phylum"]],
        class            = tax[["class"]],
        order            = tax[["order"]],
        family           = tax[["family"]],
        genus            = tax[["genus"]],
        species_resolved = tax[["species"]],
        stringsAsFactors = FALSE
      )
    }
  }

  if (length(unresolvable) > 0L) {
    warning(
      "Could not resolve taxonomy for: ",
      paste(sQuote(unresolvable), collapse = ", "),
      ". Predictions for these species will be NA.",
      call. = FALSE
    )
  }

  do.call(rbind, rows)
}
