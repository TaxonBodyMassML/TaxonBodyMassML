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
.tbm_opts$disk_cache <- FALSE
.tbm_opts$progress   <- TRUE

#' Get or set TaxonBodyMassML options
#'
#' @param ... Named arguments to set options. Omit to retrieve current values.
#'   Valid option names:
#'   - `disk_cache`: logical. Persist resolved taxonomy to disk across R
#'     sessions. Default `FALSE`.
#'   - `progress`: logical. Show a progress bar when looking up more than 10
#'     species (requires the `cli` package). Default `TRUE`.
#'
#' @return A named list of current option values (invisibly when setting).
#'
#' @examples
#' tbm_options()              # get all options
#' tbm_options(progress = FALSE)  # disable progress bar
#'
#' @export
tbm_options <- function(...) {
  args <- list(...)
  valid <- c("disk_cache", "progress")

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
    assign(nm, args[[nm]], envir = .tbm_opts)
  }

  invisible(as.list(.tbm_opts))
}

#' Clear the TaxonBodyMassML taxonomy cache
#'
#' @param disk Logical. Remove the on-disk cache directory. Default `TRUE`.
#' @param session Logical. Clear the in-memory session cache. Default `TRUE`.
#'
#' @return Invisible `NULL`.
#'
#' @export
tbm_clear_cache <- function(disk = TRUE, session = TRUE) {
  if (session) {
    rm(list = ls(envir = .tbm_cache), envir = .tbm_cache)
  }
  if (disk) {
    cache_dir <- tools::R_user_dir("TaxonBodyMassML", "cache")
    tax_dir <- file.path(cache_dir, "taxonomy")
    if (dir.exists(tax_dir)) {
      unlink(tax_dir, recursive = TRUE)
    }
  }
  .model_env$artifacts_ok <- FALSE
  invisible(NULL)
}
