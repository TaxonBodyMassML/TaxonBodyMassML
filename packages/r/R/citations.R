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
