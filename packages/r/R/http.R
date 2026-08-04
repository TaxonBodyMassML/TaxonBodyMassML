#' HTTP helpers for TaxonBodyMassML
#'
#' @description
#' All outbound HTTP requests go through `.tbm_req()`. An NCBI-specific
#' wrapper `.ncbi_get()` enforces rate limiting (3 req/s, or 10 req/s when
#' `NCBI_API_KEY` is set).
#'
#' @name http
NULL

# ---------------------------------------------------------------------------
# NCBI rate limiter
# ---------------------------------------------------------------------------
.ncbi_rl <- new.env(parent = emptyenv())
.ncbi_rl$last_call <- 0
.ncbi_rl$min_interval <- 1 / 3   # seconds between calls (3 req/s default)

.ncbi_wait <- function() {
  api_key <- Sys.getenv("NCBI_API_KEY", "")
  rate <- if (nchar(api_key) > 0) 10 else 3
  .ncbi_rl$min_interval <- 1 / rate

  now <- proc.time()[["elapsed"]]
  elapsed <- now - .ncbi_rl$last_call
  if (elapsed < .ncbi_rl$min_interval) {
    Sys.sleep(.ncbi_rl$min_interval - elapsed)
  }
  .ncbi_rl$last_call <- proc.time()[["elapsed"]]
}

# ---------------------------------------------------------------------------
# Base request builder
# ---------------------------------------------------------------------------

#' Build a base httr2 request with User-Agent and retry settings
#'
#' @param url Character. The URL for the request.
#' @return An `httr2_request` object.
#' @keywords internal
.tbm_req <- function(url) {
  email <- Sys.getenv("TAXONBODYMASSML_EMAIL", "")
  ua <- if (nzchar(email)) {
    paste0("TaxonBodyMassML/", utils::packageVersion("TaxonBodyMassML"),
           " (contact: ", email, ")")
  } else {
    paste0("TaxonBodyMassML/", utils::packageVersion("TaxonBodyMassML"))
  }
  httr2::request(url) |>
    httr2::req_user_agent(ua) |>
    httr2::req_timeout(seconds = 30) |>
    httr2::req_retry(
      max_tries = 3L,
      is_transient = ~ httr2::resp_status(.x) %in% c(429L, 500L, 502L, 503L, 504L),
      backoff = ~ 2^(.x - 1)
    )
}

# ---------------------------------------------------------------------------
# Generic GET helper
# ---------------------------------------------------------------------------

#' Perform a GET request with query parameters
#'
#' @param url Character. Base URL.
#' @param params Named list of query parameters.
#' @return An `httr2_response` object.
#' @keywords internal
.tbm_get <- function(url, params = list()) {
  req <- .tbm_req(url)
  if (length(params) > 0L) {
    req <- do.call(httr2::req_url_query, c(list(req), params))
  }
  httr2::req_perform(req)
}

# ---------------------------------------------------------------------------
# NCBI-specific GET (rate limited, API key appended if set)
# ---------------------------------------------------------------------------

#' Perform a rate-limited GET request to an NCBI Entrez endpoint
#'
#' @param url Character. Entrez URL.
#' @param params Named list of query parameters.
#' @return An `httr2_response` object.
#' @keywords internal
.ncbi_get <- function(url, params = list()) {
  .ncbi_wait()
  api_key <- Sys.getenv("NCBI_API_KEY", "")
  if (nchar(api_key) > 0L) {
    params[["api_key"]] <- api_key
  }
  .tbm_get(url, params)
}
