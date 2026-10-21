#' Model artifact management
#'
#' @description
#' Downloads, verifies, and loads model artifacts from Hugging Face Hub.
#' Artifacts are cached in the user's data directory.
#'
#' @name model
NULL

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

.HF_REPO_ID      <- "marknovak/TaxonBodyMassML"
.DEFAULT_METHOD  <- "EntityEmbeddings"

# In-memory memoisation of loaded artifacts and verification state.
.model_env       <- new.env(parent = emptyenv())

# Per-session set of (method, version) pairs for which we have already printed
# the "newer version available" note.
.NEWER_NOTED     <- new.env(parent = emptyenv())
# Per-session set of (method, version, name) tuples already SHA256-verified.
.VERIFIED        <- new.env(parent = emptyenv())

# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

.manifest <- function() {
  if (!exists("manifest", envir = .model_env, inherits = FALSE)) {
    path <- system.file("extdata", "manifest.json", package = "TaxonBodyMassML",
                        mustWork = TRUE)
    m <- jsonlite::fromJSON(path, simplifyVector = FALSE)
    assign("manifest", m, envir = .model_env)
  }
  .model_env$manifest
}

.revision <- function() {
  paste0("artifacts-", .manifest()[["release"]])
}

# ---------------------------------------------------------------------------
# Version resolution helpers
# ---------------------------------------------------------------------------

# Accept integer, "v2", "2" → integer; "newest" / "cached" pass through.
.normalise_version <- function(v) {
  if (is.null(v) || identical(v, "newest") || identical(v, "cached")) return(v)
  if (is.numeric(v) && length(v) == 1L) return(as.integer(v))
  if (is.integer(v) && length(v) == 1L) return(v)
  if (is.character(v) && length(v) == 1L) {
    s <- sub("^v", "", v)
    n <- suppressWarnings(as.integer(s))
    if (!is.na(n) && n > 0L) return(n)
  }
  stop("Invalid method_version: ", deparse(v),
       ". Use \"newest\", \"cached\", or a positive integer (e.g. 1, \"v2\", \"2\").",
       call. = FALSE)
}

# Highest integer version key present for a method in the manifest.
.newest_version <- function(method) {
  mfest <- .manifest()
  entries <- mfest[["models"]][[method]]
  if (is.null(entries) || length(entries) == 0L)
    stop("Unknown method \"", method, "\" in bundled manifest.", call. = FALSE)
  keys <- names(entries)
  nums <- suppressWarnings(as.integer(sub("^v", "", keys)))
  max(nums[!is.na(nums)])
}

# All locally cached and checksum-valid versions for a method.
.cached_versions <- function(method) {
  mfest  <- .manifest()
  entries <- mfest[["models"]][[method]]
  if (is.null(entries)) return(integer(0L))
  keys <- names(entries)
  nums <- suppressWarnings(as.integer(sub("^v", "", keys)))
  valid_nums <- nums[!is.na(nums)]
  ok <- vapply(valid_nums, function(n) {
    spec <- .make_spec(method, n)
    isTRUE(.ensure_files(spec$path, spec$files, download = FALSE))
  }, logical(1L))
  sort(valid_nums[ok], decreasing = TRUE)
}

# Build a simple list acting as a ModelSpec (method, version, path, files, db_version).
.make_spec <- function(method, version) {
  mfest <- .manifest()
  entry <- mfest[["models"]][[method]][[paste0("v", version)]]
  if (is.null(entry))
    stop("Version v", version, " of method \"", method, "\" is not in the bundled manifest.",
         call. = FALSE)
  list(
    method     = method,
    version    = version,
    path       = entry[["path"]],
    files      = entry[["files"]],
    db_version = entry[["db_version"]]
  )
}

# ---------------------------------------------------------------------------
# Public: resolve_model
# ---------------------------------------------------------------------------

.resolve_model <- function(method, method_version = NULL) {
  mv <- .normalise_version(method_version)
  if (is.null(mv)) {
    mv <- tbm_options()[["method_version"]]
    mv <- .normalise_version(mv)
  }
  if (is.null(mv)) mv <- "newest"

  if (identical(mv, "newest")) {
    v <- .newest_version(method)
    return(.make_spec(method, v))
  }

  if (identical(mv, "cached")) {
    cached <- .cached_versions(method)
    if (length(cached) == 0L) {
      message("TaxonBodyMassML: no locally cached version of \"", method,
              "\" found; falling back to newest.")
      mv <- "newest"
      v  <- .newest_version(method)
    } else {
      v      <- cached[[1L]]
      newest <- .newest_version(method)
      key    <- paste0(method, "_noted")
      if (v < newest && !exists(key, envir = .NEWER_NOTED, inherits = FALSE)) {
        message("TaxonBodyMassML: using cached \"", method, "\" v", v,
                "; v", newest, " is available (set method_version = \"newest\" to upgrade).")
        assign(key, TRUE, envir = .NEWER_NOTED)
      }
    }
    return(.make_spec(method, v))
  }

  # Explicit integer version
  spec <- .make_spec(method, mv)
  newest <- .newest_version(method)
  if (mv < newest) {
    key <- paste0(method, "_v", mv, "_noted")
    if (!exists(key, envir = .NEWER_NOTED, inherits = FALSE)) {
      message("TaxonBodyMassML: using \"", method, "\" v", mv,
              "; v", newest, " is the newest available.")
      assign(key, TRUE, envir = .NEWER_NOTED)
    }
  }
  spec
}

# ---------------------------------------------------------------------------
# Cache directory
# ---------------------------------------------------------------------------

.cache_dir <- function() {
  tools::R_user_dir("TaxonBodyMassML", "cache")
}

.model_dir <- function(spec) {
  file.path(.cache_dir(), spec$path)
}

# ---------------------------------------------------------------------------
# SHA256 verification
# ---------------------------------------------------------------------------

.sha256_file <- function(path) {
  con <- file(path, "rb")
  on.exit(close(con), add = TRUE)
  as.character(openssl::sha256(con))
}

# ---------------------------------------------------------------------------
# HuggingFace URL
# ---------------------------------------------------------------------------

.hf_url <- function(hub_path, revision = "main") {
  paste0("https://huggingface.co/", .HF_REPO_ID, "/resolve/", revision, "/", hub_path)
}

# ---------------------------------------------------------------------------
# Single-file download choke point
# ---------------------------------------------------------------------------

.fetch_file <- function(hub_path, dest, force = FALSE) {
  revision <- .revision()
  if (!force && file.exists(dest)) return(invisible(dest))
  dir.create(dirname(dest), recursive = TRUE, showWarnings = FALSE)
  message("  Downloading ", hub_path, " from ", .HF_REPO_ID, " on Hugging Face...")
  req <- .tbm_req(.hf_url(hub_path, revision)) |>
    httr2::req_timeout(7200) |>
    httr2::req_progress()
  not_found <- FALSE
  tryCatch(
    httr2::req_perform(req, path = dest),
    httr2_http_404 = function(e) not_found <<- TRUE
  )
  if (not_found) {
    if (file.exists(dest)) unlink(dest)
    return(NULL)
  }
  invisible(dest)
}

# ---------------------------------------------------------------------------
# Verify and optionally download a set of files for a Hub relative directory.
# Returns TRUE if all files are present and verified, FALSE otherwise.
# download = FALSE: existence + checksum check only (no network).
# ---------------------------------------------------------------------------

.ensure_files <- function(rel_dir, files, download = TRUE, force = FALSE,
                           optional = FALSE) {
  dest_dir <- file.path(.cache_dir(), rel_dir)
  all_ok <- TRUE
  for (name in names(files)) {
    dest      <- file.path(dest_dir, name)
    expected  <- files[[name]][["sha256"]]
    vkey      <- paste0(rel_dir, "/", name)
    if (!force && exists(vkey, envir = .VERIFIED, inherits = FALSE)) next
    if (!force && file.exists(dest) &&
        .sha256_file(dest) == expected) {
      assign(vkey, TRUE, envir = .VERIFIED)
      next
    }
    if (!download) { all_ok <- FALSE; next }
    hub_path <- paste0(rel_dir, "/", name)
    result   <- .fetch_file(hub_path, dest, force = force)
    if (is.null(result)) {
      if (!optional)
        stop("File not found on Hub: ", hub_path, call. = FALSE)
      all_ok <- FALSE
      next
    }
    if (.sha256_file(dest) != expected) {
      stop("SHA256 mismatch for ", hub_path,
           ". Re-run download_model(force = TRUE) to retry.", call. = FALSE)
    }
    assign(vkey, TRUE, envir = .VERIFIED)
    message("  ", name, " OK.")
  }
  all_ok
}

# ---------------------------------------------------------------------------
# Ensure model and provenance artifacts
# ---------------------------------------------------------------------------

.ensure_model <- function(spec, force = FALSE) {
  ekey <- paste0("model_", spec$method, "_v", spec$version)
  if (!force && exists(ekey, envir = .model_env, inherits = FALSE)) return(invisible(NULL))
  if (!.ensure_files(spec$path, spec$files, download = FALSE) || force) {
    n_files <- length(spec$files)
    total_mb <- sum(vapply(spec$files, function(f) {
      sz <- f[["size"]]
      if (is.null(sz) || sz == 0L) 0.0 else sz / 1e6
    }, numeric(1L)))
    size_msg <- if (total_mb > 1) sprintf(" (~%.0f MB)", total_mb) else ""
    message("TaxonBodyMassML: downloading \"", spec$method, "\" v", spec$version,
            " artifacts", size_msg, "...")
    .ensure_files(spec$path, spec$files, download = TRUE, force = force)
  }
  assign(ekey, TRUE, envir = .model_env)
  invisible(NULL)
}

.ensure_provenance <- function(db_version, force = FALSE) {
  ekey <- paste0("prov_", db_version)
  if (!force && exists(ekey, envir = .model_env, inherits = FALSE)) return(invisible(NULL))
  mfest    <- .manifest()
  prov_map <- mfest[["provenance"]]
  entry    <- prov_map[[db_version]]
  if (is.null(entry)) {
    stop(
      "Provenance artifacts for db_version \"", db_version,
      "\" are not available in the bundled manifest. ",
      "Use get_citations()/create_bib() with level = \"source\", or upgrade ",
      "the package once a revision with provenance artifacts is published.",
      call. = FALSE
    )
  }
  ok <- .ensure_files(entry[["path"]], entry[["files"]],
                      download = TRUE, force = force, optional = TRUE)
  if (!ok)
    stop(
      "Provenance artifacts for db_version \"", db_version,
      "\" could not be downloaded. ",
      "Use get_citations()/create_bib() with level = \"source\".",
      call. = FALSE
    )
  assign(ekey, TRUE, envir = .model_env)
  invisible(NULL)
}

# ---------------------------------------------------------------------------
# Provenance path helper
# ---------------------------------------------------------------------------

#' @noRd
.provenance_path <- function(filename, db_version = NULL) {
  if (is.null(db_version)) {
    spec <- .resolve_model(.DEFAULT_METHOD)
    db_version <- spec$db_version
  }
  .ensure_provenance(db_version)
  mfest <- .manifest()
  entry <- mfest[["provenance"]][[db_version]]
  file.path(.cache_dir(), entry[["path"]], filename)
}

# ---------------------------------------------------------------------------
# Backward-compat wrappers (used by ~35 skip_if() calls in tests)
# ---------------------------------------------------------------------------

# TRUE if all files for the given spec exist in the cache (existence only).
.artifacts_exist <- function(spec = .resolve_model(.DEFAULT_METHOD)) {
  dest_dir <- .model_dir(spec)
  all(file.exists(file.path(dest_dir, names(spec$files))))
}

# TRUE if all files are present and checksum-valid in the cache.
.artifacts_cached <- function(spec = .resolve_model(.DEFAULT_METHOD)) {
  isTRUE(.ensure_files(spec$path, spec$files, download = FALSE))
}

# ---------------------------------------------------------------------------
# Artifact loader (generic, memoised by method/version/name)
# ---------------------------------------------------------------------------

.load_artifact <- function(spec, name, reader) {
  mkey <- paste0(spec$method, "_v", spec$version, "_", name)
  if (!exists(mkey, envir = .model_env, inherits = FALSE)) {
    path <- file.path(.model_dir(spec), name)
    obj  <- reader(path)
    assign(mkey, obj, envir = .model_env)
  }
  get(mkey, envir = .model_env, inherits = FALSE)
}

# ---------------------------------------------------------------------------
# Typed loaders (each takes a spec)
# ---------------------------------------------------------------------------

.load_model <- function(spec) {
  .load_artifact(spec, "model.ubj", xgboost::xgb.load)
}

.load_calibration <- function(spec) {
  .load_artifact(spec, "calibration.json",
                 function(p) jsonlite::fromJSON(p)[["residuals"]])
}

.load_calibration_by_rank <- function(spec) {
  .load_artifact(spec, "calibration_by_rank.json", jsonlite::fromJSON)
}

.load_categories <- function(spec) {
  .load_artifact(spec, "categories.json", jsonlite::fromJSON)
}

.load_lookup <- function(spec) {
  .load_artifact(spec, "lookup.json",
                 function(p) jsonlite::fromJSON(p, simplifyDataFrame = FALSE))
}

.load_embeddings <- function(spec) {
  .load_artifact(spec, "embeddings.json", jsonlite::fromJSON)
}

# ---------------------------------------------------------------------------
# Public: download_model
# ---------------------------------------------------------------------------

#' Download TaxonBodyMassML model artifacts from Hugging Face Hub
#'
#' Downloads model artifacts for the requested method and version to the local
#' user cache directory.  Every file is verified against a SHA256 checksum
#' bundled with the package.  On subsequent calls files are skipped unless
#' `force = TRUE` or the checksum does not match.
#'
#' @param method Character. Which method(s) to download: `"EntityEmbeddings"`,
#'   `"XGBoost"`, or `"all"`. Default `NULL` (resolves to the default method
#'   `"EntityEmbeddings"`).
#' @param method_version `NULL` (default, uses the package option which
#'   defaults to `"newest"`), `"newest"`, `"cached"`, or a positive integer
#'   version number.
#' @param force Logical. If `TRUE`, re-download even if a valid cached copy
#'   exists. Default `FALSE`.
#' @param prune Logical. If `TRUE`, remove legacy flat-root cache files left
#'   by package versions before 0.14.0. Default `FALSE`.
#'
#' @return Invisible `NULL`. Called for its side-effect.
#'
#' @examples
#' \dontrun{
#' download_model()                     # default method, newest version
#' download_model("all")                # all methods
#' download_model(force = TRUE)         # force re-download
#' }
#'
#' @export
download_model <- function(method = NULL, method_version = NULL,
                            force = FALSE, prune = FALSE) {
  # Handle legacy call: first arg was a Hub revision string like "r-v0.13.0"
  if (!is.null(method) && is.character(method) &&
      !method %in% c("EntityEmbeddings", "XGBoost", "all") &&
      !identical(method, "newest") && !identical(method, "cached")) {
    warning("The first positional argument to download_model() is now `method`, not a ",
            "Hub revision. Ignoring \"", method, "\".", call. = FALSE)
    method <- NULL
  }

  methods_to_dl <- if (identical(method, "all")) {
    names(.manifest()[["models"]])
  } else if (!is.null(method)) {
    method
  } else {
    .DEFAULT_METHOD
  }

  mfest <- .manifest()
  prov  <- mfest[["provenance"]]

  for (m in methods_to_dl) {
    spec <- .resolve_model(m, method_version)
    .ensure_model(spec, force = force)
    if (length(prov) > 0L) {
      db_v <- spec$db_version
      if (!is.null(prov[[db_v]])) {
        .ensure_files(prov[[db_v]][["path"]], prov[[db_v]][["files"]],
                      download = TRUE, force = force, optional = TRUE)
      }
    }
  }

  if (prune) {
    legacy <- c("model.ubj", "model_ee.ubj", "calibration.json", "calibration_ee.json",
                "calibration_by_rank.json", "calibration_by_rank_ee.json",
                "categories.json", "lookup.json", "embeddings.json", "checksums.json")
    cache <- .cache_dir()
    for (f in legacy) {
      p <- file.path(cache, f)
      if (file.exists(p)) {
        unlink(p)
        message("  Removed legacy file: ", f)
      }
    }
  }
  invisible(NULL)
}

# ---------------------------------------------------------------------------
# Public: list_models
# ---------------------------------------------------------------------------

#' List all model versions known to this package
#'
#' @return A data frame with one row per (method, version) combination,
#'   containing columns `method`, `version`, `newest`, `db_version`,
#'   `trained`, `package_min`, `cached`, `r2`, `mae`.
#'
#' @examples
#' \dontrun{
#' list_models()
#' }
#'
#' @export
list_models <- function() {
  mfest <- .manifest()
  rows  <- list()
  for (m in names(mfest[["models"]])) {
    newest_v  <- .newest_version(m)
    cached_vs <- .cached_versions(m)
    entries   <- mfest[["models"]][[m]]
    for (vk in names(entries)) {
      v     <- as.integer(sub("^v", "", vk))
      entry <- entries[[vk]]
      metrics <- entry[["metrics"]]
      rows[[length(rows) + 1L]] <- data.frame(
        method      = m,
        version     = v,
        newest      = v == newest_v,
        db_version  = entry[["db_version"]],
        trained     = entry[["trained"]],
        package_min = entry[["package_min"]],
        cached      = v %in% cached_vs,
        r2          = if (!is.null(metrics[["r2"]]))  metrics[["r2"]]  else NA_real_,
        mae         = if (!is.null(metrics[["mae"]])) metrics[["mae"]] else NA_real_,
        stringsAsFactors = FALSE
      )
    }
  }
  do.call(rbind, rows)
}
