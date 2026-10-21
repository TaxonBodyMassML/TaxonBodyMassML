#' Package-level options for TaxonBodyMassML
#'
#' @description
#' Options are stored in a locked environment. Use `tbm_options()` to get or
#' set them, and `tbm_clear_cache()` to clear the taxonomy cache.
#'
#' @name options
NULL

# Internal options environment
.tbm_opts <- new.env(parent = emptyenv())
.tbm_opts$disk_cache     <- FALSE
.tbm_opts$progress       <- TRUE
.tbm_opts$method_version <- Sys.getenv("TAXONBODYMASSML_METHOD_VERSION", unset = "newest")

.validate_method_version <- function(v) {
  if (is.null(v)) return(invisible(NULL))
  if (identical(v, "newest") || identical(v, "cached")) return(invisible(NULL))
  if (is.numeric(v) || is.integer(v)) {
    if (length(v) == 1L && v > 0L) return(invisible(NULL))
  }
  if (is.character(v) && length(v) == 1L) {
    s <- sub("^v", "", v)
    n <- suppressWarnings(as.integer(s))
    if (!is.na(n) && n > 0L) return(invisible(NULL))
  }
  stop("Invalid method_version: ", deparse(v),
       ". Use \"newest\", \"cached\", or a positive integer (e.g. 1, \"v2\", \"2\").",
       call. = FALSE)
}

#' Get or set TaxonBodyMassML options
#'
#' @param ... Named arguments to set options. Omit to retrieve current values.
#'   Valid option names:
#'   - `disk_cache`: logical. Persist resolved taxonomy to disk across R
#'     sessions. Default `FALSE`.
#'   - `progress`: logical. Show a progress bar when looking up more than 10
#'     species (requires the `cli` package). Default `TRUE`.
#'   - `method_version`: `"newest"` (default), `"cached"`, or a positive
#'     integer version number. Controls which model version `predict_mass()`
#'     uses when `method_version` is not supplied explicitly.
#'
#' @return A named list of current option values (invisibly when setting).
#'
#' @examples
#' tbm_options()                            # get all options
#' tbm_options(progress = FALSE)            # disable progress bar
#' tbm_options(method_version = "cached")   # keep locally cached version
#'
#' @export
tbm_options <- function(...) {
  args  <- list(...)
  valid <- c("disk_cache", "progress", "method_version")

  if (length(args) == 0L) {
    return(as.list(.tbm_opts))
  }

  if (!all(names(args) %in% valid)) {
    bad <- setdiff(names(args), valid)
    stop("Unknown option(s): ", paste(sQuote(bad), collapse = ", "),
         ". Valid options: ", paste(sQuote(valid), collapse = ", "))
  }

  logical_opts <- c("disk_cache", "progress")
  for (nm in names(args)) {
    if (nm %in% logical_opts && !is.logical(args[[nm]])) {
      stop("Option '", nm, "' must be logical (TRUE or FALSE).")
    }
    if (nm == "method_version") {
      .validate_method_version(args[[nm]])
    }
    assign(nm, args[[nm]], envir = .tbm_opts)
  }

  invisible(as.list(.tbm_opts))
}

#' Clear the TaxonBodyMassML taxonomy and model cache
#'
#' @param disk Logical. Remove the on-disk taxonomy cache directory. Default `TRUE`.
#' @param session Logical. Clear the in-memory session cache. Default `TRUE`.
#' @param models Logical. If `TRUE`, remove legacy flat-root model files (left
#'   by package versions before 0.14.0) via `download_model(prune = TRUE)`.
#'   Default `FALSE`.
#'
#' @return Invisible `NULL`.
#'
#' @export
tbm_clear_cache <- function(disk = TRUE, session = TRUE, models = FALSE) {
  if (session) {
    rm(list = ls(envir = .tbm_cache), envir = .tbm_cache)
    rm(list = ls(envir = .model_env), envir = .model_env)
    rm(list = ls(envir = .VERIFIED),  envir = .VERIFIED)
    rm(list = ls(envir = .NEWER_NOTED), envir = .NEWER_NOTED)
  }
  if (disk) {
    cache_dir <- tools::R_user_dir("TaxonBodyMassML", "cache")
    tax_dir   <- file.path(cache_dir, "taxonomy")
    if (dir.exists(tax_dir)) unlink(tax_dir, recursive = TRUE)
  }
  if (models) {
    download_model(prune = TRUE)
  }
  invisible(NULL)
}
