#' Model artifact management
#'
#' @description
#' Downloads, verifies, and loads the XGBoost model artifacts from
#' Hugging Face Hub. Artifacts are cached in the user's data directory.
#'
#' @name model
NULL

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

.HF_REPO_ID <- "marknovak/TaxonBodyMassML"

.CHECKSUMS <- list(
  # XGBoost (original method)
  "model.ubj"               = "0fdb5d375e6158cd8eed635330f9f06d1d3054af65ee3857ff6890d2e15e94ed",
  "calibration.json"        = "814fd4dde6421e0509de77d778dfb62f5beab9d129af1744b5f1aa59095bc1bd",
  "calibration_by_rank.json" = "dd409f4d0f7e544d36309328c89135d8669539e365bd93076b639e5f8be01280",
  "categories.json"         = "910394f7a8fa2d4d34b3a559ad170f7d6d4909f9ad88167d3820e6701ca0b377",
  "lookup.json"             = "ba530ab9b34eb5a0c236fd6c1ebba0e6fa04ec3287011887681146282dd6cd46",
  # Entity Embeddings
  "embeddings.json"              = "cce9b15b709e72a7caf6b1c0d771ea3e0b629085a88de6bf2bc761e5cc9b74c0",
  "model_ee.ubj"                 = "3bff6e3218f949744f4d1bcbe2cee5cf2bbe60b3886543d7e0c85629502683cc",
  "calibration_ee.json"          = "cba32526436d1eb3f8f2965bf4f6e12ad105e9baf4d038a44fc5a03937dde1b2",
  "calibration_by_rank_ee.json"  = "8a1579dd5f3fbf1ab063819f6d8304c60a30064f5bbeb938d2b3ae3217e34fd6"
)

.ARTIFACT_FILES <- names(.CHECKSUMS)

# ---------------------------------------------------------------------------
# Cache directory
# ---------------------------------------------------------------------------

.cache_dir <- function() {
  tools::R_user_dir("TaxonBodyMassML", "cache")
}

# ---------------------------------------------------------------------------
# SHA256 verification
# ---------------------------------------------------------------------------

.verify_file <- function(path, filename) {
  expected <- .CHECKSUMS[[filename]]
  con <- file(path, "rb")
  on.exit(close(con), add = TRUE)
  as.character(openssl::sha256(con)) == expected
}

# ---------------------------------------------------------------------------
# HuggingFace URL
# ---------------------------------------------------------------------------

.hf_url <- function(filename, revision = "main") {
  paste0("https://huggingface.co/", .HF_REPO_ID, "/resolve/", revision, "/", filename)
}

# ---------------------------------------------------------------------------
# Artifact status checks
# ---------------------------------------------------------------------------

#' Check whether all model artifacts are present in the local cache (existence only)
#'
#' @return Logical `TRUE` if all artifact files exist.
#' @keywords internal
.artifacts_exist <- function() {
  cache <- .cache_dir()
  all(file.exists(file.path(cache, .ARTIFACT_FILES)))
}

#' Check whether all model artifacts are present and valid in the local cache
#'
#' @return Logical `TRUE` if all artifacts are present and pass SHA256 verification.
#' @keywords internal
.artifacts_cached <- function() {
  cache <- .cache_dir()
  all(vapply(.ARTIFACT_FILES, function(f) {
    p <- file.path(cache, f)
    file.exists(p) && isTRUE(.verify_file(p, f))
  }, logical(1L)))
}

# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

#' Download TaxonBodyMassML model artifacts from Hugging Face Hub
#'
#' Downloads the XGBoost model (`model.ubj`, ~2 GB), calibration residuals
#' (`calibration.json`), and category lists (`categories.json`) to the
#' local user cache directory. On subsequent calls the files are skipped
#' unless `force = TRUE` or the SHA256 checksum does not match.
#'
#' @param version Character. HuggingFace revision to download. `"latest"`
#'   resolves to the default branch (`main`). Pass a specific tag or commit
#'   SHA to pin a version.
#' @param force Logical. If `TRUE`, re-download even if a valid cached copy
#'   already exists. Default `FALSE`.
#'
#' @return Invisible `NULL`. Called for its side-effect of populating the
#'   cache directory.
#'
#' @examples
#' \dontrun{
#' download_model()          # download once
#' download_model(force = TRUE)  # force re-download
#' }
#'
#' @export
download_model <- function(version = "latest", force = FALSE) {
  dir.create(.cache_dir(), recursive = TRUE, showWarnings = FALSE)
  revision <- if (identical(version, "latest")) {
    paste0("r-v", utils::packageVersion("TaxonBodyMassML"))
  } else {
    version
  }

  for (filename in .ARTIFACT_FILES) {
    dest <- file.path(.cache_dir(), filename)
    if (!force && file.exists(dest) && isTRUE(.verify_file(dest, filename))) {
      next
    }
    message("  Downloading ", filename, " from ", .HF_REPO_ID, " on Hugging Face...")
    req <- .tbm_req(.hf_url(filename, revision)) |>
      httr2::req_timeout(7200) |>
      httr2::req_progress()
    httr2::req_perform(req, path = dest)
    if (!isTRUE(.verify_file(dest, filename))) {
      stop(
        "SHA256 mismatch for ", filename,
        ". Re-run download_model(force = TRUE) to retry.",
        call. = FALSE
      )
    }
    message("  ", filename, " OK.")
  }
  invisible(NULL)
}

# ---------------------------------------------------------------------------
# Auto-download on first use
# ---------------------------------------------------------------------------

.ensure_artifacts <- function() {
  if (isTRUE(.model_env$artifacts_ok)) return(invisible(NULL))
  if (!.artifacts_cached()) {
    message(
      "TaxonBodyMassML: downloading model artifacts on first use (~2 GB)...\n",
      "  Files: ", paste(.ARTIFACT_FILES, collapse = ", ")
    )
    download_model()
  }
  .model_env$artifacts_ok <- TRUE
}

# ---------------------------------------------------------------------------
# In-memory model cache
# ---------------------------------------------------------------------------

.model_env <- new.env(parent = emptyenv())

.load_model <- function() {
  if (!exists("model", envir = .model_env, inherits = FALSE)) {
    m <- xgboost::xgb.load(file.path(.cache_dir(), "model.ubj"))
    assign("model", m, envir = .model_env)
  }
  .model_env$model
}

.load_calibration <- function() {
  if (!exists("residuals", envir = .model_env, inherits = FALSE)) {
    cal <- jsonlite::fromJSON(file.path(.cache_dir(), "calibration.json"))
    assign("residuals", cal$residuals, envir = .model_env)
  }
  .model_env$residuals
}

.load_calibration_by_rank <- function() {
  if (!exists("residuals_by_rank", envir = .model_env, inherits = FALSE)) {
    cal <- jsonlite::fromJSON(file.path(.cache_dir(), "calibration_by_rank.json"))
    assign("residuals_by_rank", cal, envir = .model_env)
  }
  .model_env$residuals_by_rank
}

.load_calibration_by_rank_gpboost <- function() {
  if (!exists("residuals_by_rank_gpboost", envir = .model_env, inherits = FALSE)) {
    cal <- jsonlite::fromJSON(
      file.path(.cache_dir(), "calibration_by_rank_gpboost.json")
    )
    assign("residuals_by_rank_gpboost", cal, envir = .model_env)
  }
  .model_env$residuals_by_rank_gpboost
}

.load_calibration_by_rank_ee <- function() {
  if (!exists("residuals_by_rank_ee", envir = .model_env, inherits = FALSE)) {
    cal <- jsonlite::fromJSON(
      file.path(.cache_dir(), "calibration_by_rank_ee.json")
    )
    assign("residuals_by_rank_ee", cal, envir = .model_env)
  }
  .model_env$residuals_by_rank_ee
}

.load_categories <- function() {
  if (!exists("categories", envir = .model_env, inherits = FALSE)) {
    cats <- jsonlite::fromJSON(file.path(.cache_dir(), "categories.json"))
    assign("categories", cats, envir = .model_env)
  }
  .model_env$categories
}

.load_lookup <- function() {
  if (!exists("lookup", envir = .model_env, inherits = FALSE)) {
    lkp <- jsonlite::fromJSON(file.path(.cache_dir(), "lookup.json"),
                              simplifyDataFrame = FALSE)
    assign("lookup", lkp, envir = .model_env)
  }
  .model_env$lookup
}

.require_method_file <- function(filename, method, training_script) {
  path <- file.path(.cache_dir(), filename)
  if (!file.exists(path))
    stop(
      sprintf(
        paste0(
          "Artifacts for method = \"%s\" are not yet available (\"%s\" not found ",
          "in cache). Generate them first:\n",
          "  python predictive_models/%s\n",
          "Then run scripts/export_artifacts.py and copy the new SHA-256 ",
          "checksums into packages/r/R/model.R."
        ),
        method, filename, training_script
      ),
      call. = FALSE
    )
}

.load_gpboost_model <- function() {
  if (!exists("gpboost_model", envir = .model_env, inherits = FALSE)) {
    .require_method_file("model_gpboost.json", "GPBoost", "gpboost_model.py")
    bst <- gpboost::gpb.load(
      file.path(.cache_dir(), "model_gpboost.json")
    )
    assign("gpboost_model", bst, envir = .model_env)
  }
  .model_env$gpboost_model
}

.load_calibration_gpboost <- function() {
  if (!exists("residuals_gpboost", envir = .model_env, inherits = FALSE)) {
    .require_method_file("calibration_gpboost.json", "GPBoost", "gpboost_model.py")
    cal <- jsonlite::fromJSON(
      file.path(.cache_dir(), "calibration_gpboost.json")
    )
    assign("residuals_gpboost", cal$residuals, envir = .model_env)
  }
  .model_env$residuals_gpboost
}

.load_embeddings <- function() {
  if (!exists("embeddings", envir = .model_env, inherits = FALSE)) {
    .require_method_file("embeddings.json", "EntityEmbeddings",
                         "entity_embeddings_model.py")
    embs <- jsonlite::fromJSON(file.path(.cache_dir(), "embeddings.json"))
    assign("embeddings", embs, envir = .model_env)
  }
  .model_env$embeddings
}

.load_model_ee <- function() {
  if (!exists("model_ee", envir = .model_env, inherits = FALSE)) {
    .require_method_file("model_ee.ubj", "EntityEmbeddings",
                         "entity_embeddings_model.py")
    m <- xgboost::xgb.load(file.path(.cache_dir(), "model_ee.ubj"))
    assign("model_ee", m, envir = .model_env)
  }
  .model_env$model_ee
}

.load_calibration_ee <- function() {
  if (!exists("residuals_ee", envir = .model_env, inherits = FALSE)) {
    .require_method_file("calibration_ee.json", "EntityEmbeddings",
                         "entity_embeddings_model.py")
    cal <- jsonlite::fromJSON(
      file.path(.cache_dir(), "calibration_ee.json")
    )
    assign("residuals_ee", cal$residuals, envir = .model_env)
  }
  .model_env$residuals_ee
}
