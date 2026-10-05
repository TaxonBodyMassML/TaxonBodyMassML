# Citation levels: the compilation a value was copied from ("source"), the
# study that measured the animal ("primary"), or both ("all").
.LEVELS <- c("source", "primary", "all")
# Provenance artifacts (TaxonBodyMass_DB issue #1), distributed next to lookup.json.
.PRIMARY_BIB_FILE <- "PrimaryCitations_BodyMass.bib"
.PROVENANCE_FILE  <- "TaxonBodyMass_Provenance.csv.gz"
# match_status values of a verified primary reference. Conversion-factor rows
# (provenance_type == "conversion_factor") carry no status and are always cited.
.ACCEPTED_STATUS  <- c("certain", "approved", "nodoi_approved")
.CONVERSION_TYPE  <- "conversion_factor"
.PROVENANCE_COLS  <- c("genus", "species", "taxon", "source_mass", "source_bibcite",
                       "origin", "hop", "via_cite_id", "ref_role", "provenance_type",
                       "primary_cite_id", "primary_bibcite", "primary_doi",
                       "match_status", "n_records")

#' Return path(s) to the body-mass bibliographies
#'
#' @description
#' Returns the file path to a TaxonBodyMassML bibliography. `level = "source"`
#' (the default) gives the bundled `inst/extdata/Citations_BodyMass.bib`,
#' which contains BibTeX entries for every data source (compilation, database
#' or primary study) whose body masses were used to train the model.
#' `level = "primary"` gives the generated `PrimaryCitations_BodyMass.bib` of
#' verified primary references (the studies that measured the animals the
#' compilations reproduce; TaxonBodyMass_DB issue #1). It is a model artifact,
#' fetched from Hugging Face on first use (like `lookup.json`) and verified
#' against a bundled checksum. `level = "all"` returns both paths. The files
#' can be read with `bibtex::read.bib()` (requires the `bibtex` package).
#'
#' @param level One of `"source"` (default), `"primary"` or `"all"`.
#'
#' @return Character. Absolute path to the requested bibliography; for
#'   `level = "all"` a length-2 vector `c(source = ..., primary = ...)`.
#'
#' @seealso [create_bib()] to export only the references cited by a particular
#'   set of predictions.
#'
#' @examples
#' path <- get_citations()
#' cat(path, "\n")
#'
#' \dontrun{
#' # Read with bibtex package
#' refs <- bibtex::read.bib(get_citations())
#' # The verified primary references (downloads the artifact on first use)
#' primary <- bibtex::read.bib(get_citations(level = "primary"))
#' }
#'
#' @export
get_citations <- function(level = c("source", "primary", "all")) {
  level <- .check_level(level)
  src <- system.file("extdata", "Citations_BodyMass.bib",
                     package = "TaxonBodyMassML",
                     mustWork = TRUE)
  if (level == "source") return(src)
  prim <- .primary_bib_path()
  if (level == "primary") return(prim)
  c(source = src, primary = prim)
}


#' Write a BibTeX file of the references behind a set of predictions
#'
#' @description
#' Takes the output of [predict_mass()] called with `include_source = TRUE`
#' and writes a `.bib` file containing the BibTeX entries that the dictionary
#' (training-data) rows of the result rest on. This lets users cite exactly
#' the empirical body-mass sources that contributed to their results.
#'
#' @details
#' `level = "source"` (default) cites the data sources named in the `source`
#' column. Each value is split on `";"` (a taxon recorded by several sources
#' has a value such as `"Feldman_etal_2016; Meiri_2018"`), trimmed, and
#' de-duplicated. Model-inferred rows, whose `source` begins with `"tbmML_"`,
#' and `NA` values are ignored, so an output with no dictionary hits yields a
#' bibliography with no entries. Source labels are matched to BibTeX keys
#' through the bundled `TaxonBodyMass_CitationCiteIDs.csv` (labels and keys
#' are compared after normalising whitespace, Unicode dashes and diacritics
#' to plain ASCII), and the entries are copied verbatim from the file returned
#' by [get_citations()]. A warning lists any label that has no mapping; such
#' labels are skipped.
#'
#' `level = "primary"` cites the studies that measured the animals: the
#' dictionary species of `x` are joined to the provenance table
#' (`TaxonBodyMass_Provenance.csv.gz`, a model artifact downloaded on first
#' use) and every verified primary reference (`match_status` `certain`,
#' `approved` or `nodoi_approved`) and every conversion-factor reference of
#' those species is written, taken from the primary bibliography or, for
#' references that are themselves data sources, from the compilation
#' bibliography. The join uses the `source_taxon` column (the dictionary key;
#' present when `predict_mass()` was called with `include_source = TRUE`),
#' falling back to `species_resolved` and then, with a warning, to `taxon`.
#' Coverage is partial while TaxonBodyMass_DB ingests the sources' reference
#' lists: species whose sources cite references that are not yet resolved are
#' reported in a warning, so cite `level = "source"` for them as well.
#'
#' `level = "all"` writes the union of both levels without duplicate keys. The
#' header line reports the number of entries per level.
#'
#' @param x A `data.frame` with a `source` column, as returned by
#'   `predict_mass(..., include_source = TRUE)`.
#' @param file Path of the `.bib` file to write. Default
#'   `"TaxonBodyMass_sources.bib"` in the working directory. An existing file
#'   is overwritten.
#' @param level One of `"source"` (default), `"primary"` or `"all"`; see
#'   Details.
#'
#' @return Invisibly, the normalised path to the written file.
#'
#' @seealso [predict_mass()], [get_citations()]
#'
#' @examples
#' x <- data.frame(taxon  = c("Anolis carolinensis", "Nucella lima"),
#'                 mass_g = c(4.3, 2.0),
#'                 source = c("Meiri_2018", "tbmML_genus"))
#' out <- create_bib(x, file = tempfile(fileext = ".bib"))
#' readLines(out)[1:3]
#'
#' \dontrun{
#' # Typical use: cite the sources behind your own predictions
#' res <- predict_mass(c("Nucella ostrina", "Anolis carolinensis"),
#'                     include_source = TRUE)
#' create_bib(res, file = "my_sources.bib")
#' # ... and the primary studies behind those sources, where known
#' create_bib(res, file = "my_primary_sources.bib", level = "all")
#' }
#'
#' @export
create_bib <- function(x, file = "TaxonBodyMass_sources.bib",
                       level = c("source", "primary", "all")) {
  if (!is.data.frame(x) || !"source" %in% names(x)) {
    stop("`x` must be a data.frame with a `source` column; ",
         "call predict_mass(..., include_source = TRUE).", call. = FALSE)
  }
  if (!is.character(file) || length(file) != 1L || !nzchar(file)) {
    stop("`file` must be a single, non-empty file path.", call. = FALSE)
  }
  level <- .check_level(level)

  source_keys  <- if (level %in% c("source", "all")) .source_keys(x) else character(0L)
  primary_keys <- if (level %in% c("primary", "all")) .primary_keys(x) else character(0L)

  read_bib <- function(path) {
    paste(readLines(path, encoding = "UTF-8", warn = FALSE), collapse = "\n")
  }
  source_bib  <- read_bib(get_citations("source"))
  primary_bib <- if (level == "source") "" else read_bib(.primary_bib_path())

  # Source entries come from the compilation bibliography; primary entries from
  # the primary bibliography, or from the compilation bibliography when the
  # primary reference is itself a data source (a shared key).
  written   <- character(0L)
  entries   <- character(0L)
  missing   <- character(0L)
  n_source  <- 0L
  n_primary <- 0L
  for (k in sort(unique(source_keys))) {
    e <- .extract_bib_entry(source_bib, k)
    if (is.null(e)) { missing <- c(missing, k); next }
    entries  <- c(entries, e)
    written  <- c(written, k)
    n_source <- n_source + 1L
  }
  for (k in sort(unique(primary_keys))) {
    e <- .extract_bib_entry(primary_bib, k)
    if (is.null(e)) e <- .extract_bib_entry(source_bib, k)
    if (is.null(e)) { missing <- c(missing, k); next }
    n_primary <- n_primary + 1L
    if (k %in% written) next
    entries <- c(entries, e)
    written <- c(written, k)
  }
  if (length(missing) > 0L) {
    warning("BibTeX key(s) referenced by the citation tables but absent from ",
            "the bibliographies: ", paste(sort(unique(missing)), collapse = ", "),
            call. = FALSE)
  }

  counts <- switch(level,
    source  = sprintf("%d data-source citation(s)", n_source),
    primary = sprintf("%d primary-reference citation(s)", n_primary),
    all     = sprintf("%d data-source and %d primary-reference citation(s) (%d unique)",
                      n_source, n_primary, length(entries))
  )
  header <- sprintf("%%%% TaxonBodyMassML create_bib(): %s for %d taxa", counts, nrow(x))
  body   <- if (length(entries) > 0L) paste(entries, collapse = "\n\n") else character(0L)
  writeLines(enc2utf8(c(header, "", body)), file, useBytes = TRUE)
  invisible(normalizePath(file))
}


#' @noRd
.check_level <- function(level) {
  if (!is.character(level) || length(level) == 0L || anyNA(level)) {
    stop("`level` must be one of ", paste(sQuote(.LEVELS, q = FALSE), collapse = ", "), ".",
         call. = FALSE)
  }
  if (length(level) > 1L) {
    if (identical(level, .LEVELS)) return("source")  # default of match.arg-style vector
    stop("`level` must be a single value: one of ",
         paste(sQuote(.LEVELS, q = FALSE), collapse = ", "), ".", call. = FALSE)
  }
  if (!level %in% .LEVELS) {
    stop("`level` must be one of ", paste(sQuote(.LEVELS, q = FALSE), collapse = ", "),
         "; got ", sQuote(level, q = FALSE), ".", call. = FALSE)
  }
  level
}


# BibTeX keys of the data sources named in the `source` column (level "source").
#' @noRd
.source_keys <- function(x) {
  tokens <- .split_sources(x$source)
  map    <- .read_citeids()
  hit    <- match(.normalise_label(tokens), names(map))
  unmapped <- tokens[is.na(hit)]
  if (length(unmapped) > 0L) {
    warning(length(unmapped), " source label(s) have no citation mapping ",
            "and were skipped: ", paste(sort(unmapped), collapse = ", "),
            call. = FALSE)
  }
  unname(map[hit[!is.na(hit)]])
}


# Lookup keys of the dictionary rows of `x` (unique, first-seen order). For
# each dictionary row the key is `source_taxon` (the name under which the
# species was found in the training-data dictionary), falling back to
# `species_resolved` when that is missing and then to `taxon` (the input name,
# which may differ from the dictionary key; a warning is issued once when any
# row needs this last fallback). Model-inferred and unresolved rows (`source`
# tbmML_... or NA) are skipped.
#' @noRd
.dictionary_species <- function(x) {
  src     <- as.character(x$source)
  is_dict <- !is.na(src) & nzchar(trimws(src)) &
    !grepl("^tbm_?ml_|^tbml_", trimws(src), ignore.case = TRUE, perl = TRUE)
  cols <- intersect(c("source_taxon", "species_resolved", "taxon"), names(x))
  key  <- rep(NA_character_, nrow(x))
  from <- rep(NA_character_, nrow(x))
  for (col in cols) {
    v    <- trimws(as.character(x[[col]]))
    take <- is.na(key) & !is.na(v) & nzchar(v)
    key[take]  <- v[take]
    from[take] <- col
  }
  if (any(is_dict & !is.na(from) & from == "taxon")) {
    warning("Some dictionary rows of `x` have no `source_taxon` or `species_resolved` ",
            "value; joining the provenance table on `taxon` (input names) for them, ",
            "which may differ from the dictionary keys. Call predict_mass(..., ",
            "include_source = TRUE) with this package version to get `source_taxon`.",
            call. = FALSE)
  }
  unique(key[is_dict & !is.na(key)])
}


# BibTeX keys of the verified primary (and conversion) references of the
# dictionary species of `x`, from the provenance table (level "primary").
#' @noRd
.primary_keys <- function(x) {
  species <- .dictionary_species(x)
  if (length(species) == 0L) return(character(0L))
  prov <- .read_provenance()
  rows <- prov[prov$species %in% species, , drop = FALSE]

  absent <- sort(setdiff(species, rows$species))
  if (length(absent) > 0L) {
    shown <- paste(utils::head(absent, 10L), collapse = ", ")
    if (length(absent) > 10L) shown <- paste0(shown, ", ... (", length(absent) - 10L, " more)")
    warning(length(absent), " dictionary species absent from the provenance table ",
            "(the table may predate the species dictionary): ", shown, call. = FALSE)
  }

  accepted <- rows$match_status %in% .ACCEPTED_STATUS |
    (!is.na(rows$provenance_type) & rows$provenance_type == .CONVERSION_TYPE)
  cited <- rows[accepted & !is.na(rows$primary_bibcite), , drop = FALSE]

  # Rows whose source cites a reference (hop >= 1) that is not (yet) verified:
  # the primary bibliography is incomplete for these species.
  unresolved <- rows[rows$hop >= 1L & !rows$match_status %in% .ACCEPTED_STATUS, , drop = FALSE]
  if (nrow(unresolved) > 0L) {
    status <- table(ifelse(is.na(unresolved$match_status), "none", unresolved$match_status))
    status <- sort(status, decreasing = TRUE)
    warning(length(unique(unresolved$species)), " of ", length(species),
            " dictionary species have source records whose primary reference is ",
            "not yet resolved (", nrow(unresolved), " record link(s); match_status ",
            paste(names(status), status, sep = ": ", collapse = ", "),
            "); cite these at level = \"source\".", call. = FALSE)
  }
  cited$primary_bibcite
}


# Path to the primary-source bibliography artifact (downloaded on first use).
#' @noRd
.primary_bib_path <- function() .provenance_path(.PRIMARY_BIB_FILE)


# Path to the provenance table artifact (downloaded on first use).
#' @noRd
.provenance_table_path <- function() .provenance_path(.PROVENANCE_FILE)


# Read TaxonBodyMass_Provenance.csv.gz (TaxonBodyMass_DB pipeline step 7): one
# row per species x source label x reference. All columns are character ("NA"
# -> NA) except `hop` and `n_records` (integer).
#' @noRd
.read_provenance <- function(path = .provenance_table_path()) {
  con <- gzfile(path, open = "rt", encoding = "UTF-8")
  on.exit(close(con), add = TRUE)
  df <- utils::read.csv(con, stringsAsFactors = FALSE, na.strings = "NA",
                        colClasses = "character", check.names = FALSE)
  missing <- setdiff(.PROVENANCE_COLS, names(df))
  if (length(missing) > 0L) {
    stop("Provenance table is missing column(s): ", paste(missing, collapse = ", "),
         call. = FALSE)
  }
  df$hop       <- as.integer(df$hop)
  df$n_records <- as.integer(df$n_records)
  df$hop[is.na(df$hop)]             <- 0L
  df$n_records[is.na(df$n_records)] <- 0L
  df
}


# Path to the bundled CiteID -> BibTeX-key mapping.
#' @noRd
.citeid_path <- function() {
  system.file("extdata", "TaxonBodyMass_CitationCiteIDs.csv",
              package = "TaxonBodyMassML",
              mustWork = TRUE)
}


# Normalise a source label (or CiteID) to plain ASCII so hand-typed variants
# compare equal. Mirrors NormaliseSourceLabel() in TaxonBodyMass_DB: trims
# whitespace, converts non-breaking spaces, maps Unicode dashes to '-', and
# transliterates diacritics to base letters. iconv's ASCII//TRANSLIT
# emits stray accent marks on some platforms (Cervig'on); these and '?' for
# untransliterable characters are removed. NA is preserved.
#' @noRd
.normalise_label <- function(x) {
  x <- enc2utf8(as.character(x))
  x <- gsub("\u00a0", " ", x, fixed = TRUE)
  x <- gsub("[\u2010-\u2015\u2212]", "-", x, perl = TRUE)
  x <- iconv(x, from = "UTF-8", to = "ASCII//TRANSLIT")
  x <- gsub("[^[:ascii:]]", "", x, perl = TRUE)
  x <- gsub("[?'`^~\"]", "", x, perl = TRUE)
  trimws(x)
}


# Split a vector of `source` values into unique dictionary labels: split on
# ';' only (labels themselves contain '_' and '-'), trim, drop NA/empty, and
# drop model-inferred markers ('tbmML_<rank>', matched case-insensitively;
# the shorter 'tbml_' spelling is accepted too).
#' @noRd
.split_sources <- function(x) {
  x   <- as.character(x)
  x   <- x[!is.na(x)]
  tok <- trimws(unlist(strsplit(x, ";", fixed = TRUE), use.names = FALSE))
  tok <- tok[nzchar(tok)]
  tok <- tok[!grepl("^tbm_?ml_|^tbml_", tok, ignore.case = TRUE, perl = TRUE)]
  unique(tok)
}


# Read the CiteID CSV into a named character vector: names are normalised
# CiteIDs, values are BibTeX keys. Rows with an empty/NA CiteID are dropped.
# Several CiteIDs may point to the same key (e.g. 'fishbase' and
# 'Froese_2025'); the first occurrence of a normalised CiteID wins.
#' @noRd
.read_citeids <- function(path = .citeid_path()) {
  df <- utils::read.csv(path, stringsAsFactors = FALSE, encoding = "UTF-8",
                        na.strings = c("NA", ""))
  df <- df[!is.na(df$CiteID) & !is.na(df$Bibcite), , drop = FALSE]
  key <- .normalise_label(df$CiteID)
  keep <- !duplicated(key)
  setNames(df$Bibcite[keep], key[keep])
}


# Return the verbatim text of one BibTeX entry, or NULL if `key` is absent.
# The bundled bibliography is a BibDesk export: every entry starts at column 0
# with '@type{Key,' and there are no @string/@preamble/@comment blocks, so the
# entry runs from its '@' line to the line before the next '@' line (or EOF).
# The trailing ',' after the key prevents 'Meiri:2018a' matching 'Meiri:2018aa'.
#' @noRd
.extract_bib_entry <- function(bibtext, key) {
  esc   <- gsub("([^A-Za-z0-9_])", "\\\\\\1", key, perl = TRUE)
  start <- regexpr(paste0("(?m)^@[A-Za-z]+\\{", esc, ","), bibtext, perl = TRUE)
  if (start < 0L) return(NULL)
  rest <- substring(bibtext, start)
  nxt  <- regexpr("(?m)^@", substring(rest, 2L), perl = TRUE)
  entry <- if (nxt < 0L) rest else substr(rest, 1L, nxt)
  trimws(entry, which = "right")
}
