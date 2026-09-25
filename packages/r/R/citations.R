#' Return path to the body-mass data-source bibliography
#'
#' @description
#' Returns the file path to `inst/extdata/Citations_BodyMass.bib`, which
#' contains BibTeX entries for all data sources used to train the
#' TaxonBodyMassML model. The file can be read with
#' `bibtex::read.bib()` (requires the `bibtex` package).
#'
#' @return Character. Absolute path to `Citations_BodyMass.bib`.
#'
#' @seealso [create_bib()] to export only the sources cited by a particular
#'   set of predictions.
#'
#' @examples
#' path <- get_citations()
#' cat(path, "\n")
#'
#' \dontrun{
#' # Read with bibtex package
#' refs <- bibtex::read.bib(get_citations())
#' }
#'
#' @export
get_citations <- function() {
  system.file("extdata", "Citations_BodyMass.bib",
              package = "TaxonBodyMassML",
              mustWork = TRUE)
}


#' Write a BibTeX file of the data sources behind a set of predictions
#'
#' @description
#' Takes the output of [predict_mass()] called with `include_source = TRUE`
#' and writes a `.bib` file containing the BibTeX entries for every
#' training-data source cited in its `source` column. This lets users cite
#' exactly the empirical body-mass sources that contributed to their results.
#'
#' @details
#' Each `source` value is split on `";"` (a taxon recorded by several sources
#' has a value such as `"Feldman_etal_2016; Meiri_2018"`), trimmed, and
#' de-duplicated. Model-inferred rows, whose `source` begins with `"tbmML_"`,
#' and `NA` values are ignored, so an output with no dictionary hits yields a
#' bibliography with no entries.
#'
#' Source labels are matched to BibTeX keys through the bundled
#' `TaxonBodyMass_CitationCiteIDs.csv`, and the corresponding entries are
#' copied verbatim from the file returned by [get_citations()]. Labels and
#' keys are compared after normalising whitespace, Unicode dashes and
#' diacritics to plain ASCII, so minor typographic variants still match.
#' A warning lists any label that has no mapping; such labels are skipped.
#'
#' @param x A `data.frame` with a `source` column, as returned by
#'   `predict_mass(..., include_source = TRUE)`.
#' @param file Path of the `.bib` file to write. Default
#'   `"TaxonBodyMass_sources.bib"` in the working directory. An existing file
#'   is overwritten.
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
#' }
#'
#' @export
create_bib <- function(x, file = "TaxonBodyMass_sources.bib") {
  if (!is.data.frame(x) || !"source" %in% names(x)) {
    stop("`x` must be a data.frame with a `source` column; ",
         "call predict_mass(..., include_source = TRUE).", call. = FALSE)
  }
  if (!is.character(file) || length(file) != 1L || !nzchar(file)) {
    stop("`file` must be a single, non-empty file path.", call. = FALSE)
  }

  tokens <- .split_sources(x$source)
  map    <- .read_citeids()
  hit    <- match(.normalise_label(tokens), names(map))

  unmapped <- tokens[is.na(hit)]
  if (length(unmapped) > 0L) {
    warning(length(unmapped), " source label(s) have no citation mapping ",
            "and were skipped: ", paste(sort(unmapped), collapse = ", "),
            call. = FALSE)
  }

  keys    <- sort(unique(unname(map[hit[!is.na(hit)]])))
  bibtext <- paste(readLines(get_citations(), encoding = "UTF-8", warn = FALSE),
                   collapse = "\n")
  entries <- lapply(keys, function(k) .extract_bib_entry(bibtext, k))
  found   <- !vapply(entries, is.null, logical(1L))
  if (any(!found)) {
    warning("BibTeX key(s) listed in TaxonBodyMass_CitationCiteIDs.csv but ",
            "absent from Citations_BodyMass.bib: ",
            paste(keys[!found], collapse = ", "), call. = FALSE)
  }
  entries <- unlist(entries[found], use.names = FALSE)

  header <- sprintf("%%%% TaxonBodyMassML create_bib(): %d data-source citation(s) for %d taxa",
                    length(entries), nrow(x))
  body   <- if (length(entries) > 0L) paste(entries, collapse = "\n\n") else character(0L)
  writeLines(enc2utf8(c(header, "", body)), file, useBytes = TRUE)
  invisible(normalizePath(file))
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
