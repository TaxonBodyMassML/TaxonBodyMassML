#' Session-level taxonomy cache
#'
#' @description
#' In-memory key/value store for resolved taxonomy. Populated by
#' `lookup_taxonomy()` and optionally backed by an on-disk cache when
#' `tbm_options(disk_cache = TRUE)`.
#'
#' @name cache
NULL

# Session cache: key = normalised name, value = named list of 7 taxonomy fields
.tbm_cache <- new.env(parent = emptyenv())
