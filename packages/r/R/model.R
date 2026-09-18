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

# HuggingFace revision that hosts the current model artifacts (r-v<version>).
# Only advances when make publish is run with new artifacts. Intentionally
# independent of the package version so code-only releases work without a
# new HuggingFace upload. Updated automatically by scripts/publish_artifacts.py.
.MODEL_ARTIFACT_VERSION <- "0.10.0"

.CHECKSUMS <- list(
  # XGBoost (original method)
  "model.ubj"               = "7ea10b33634f42d81bc566a1986880e59701ef479e052eea78c80a5149aa0b12",
  "calibration.json"        = "cc0204bd5391b8cc37273443a62c79d5b9b92e4f7e82b141066f726ca156666d",
  "calibration_by_rank.json" = "232decdce8e29fbda4bd1835c0151d478bd07bbb508a423c3a8a8316cd8e14c9",
  "categories.json"         = "ac2ab3af8f6d7078ac1c98c57868c4c3eb989bc007028887d8a4449e271f56ec",
  "lookup.json"             = "ba530ab9b34eb5a0c236fd6c1ebba0e6fa04ec3287011887681146282dd6cd46",
  # Entity Embeddings
  "embeddings.json"              = "eeb1ad2e37cb93324823376581ad6e45da37efcffbc367266168d62d9c3b2a39",
  "model_ee.ubj"                 = "b4c6be58111d6d6b8ffecb82c918bcbe83c2b4c274754722cece42d7d6dc4310",
  "calibration_ee.json"          = "415a0dd395611574892efec2b4b54585fabee551b3a5ab7925398c19f8fb027f",
  "calibration_by_rank_ee.json"  = "59cbf182f4efcf10c7739ef678f45b4af51aca05a285253eb7dd60ac9bc75a48"
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
#' Downloads all model artifacts (~0.6 GB in total) to the local user cache
#' directory: the XGBoost model (`model.ubj`) with its pooled and
#' rank-stratified calibration residuals (`calibration.json`,
#' `calibration_by_rank.json`), the category lists that define the model's
#' factor levels (`categories.json`), the training-data species dictionary
#' (`lookup.json`), and the Entity Embeddings model (`embeddings.json`,
#' `model_ee.ubj`, `calibration_ee.json`, `calibration_by_rank_ee.json`).
#' Every file is verified against a SHA256 checksum bundled with the package.
#' On subsequent calls the files are skipped unless `force = TRUE` or the
#' checksum does not match.
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
    paste0("r-v", .MODEL_ARTIFACT_VERSION)
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
      "TaxonBodyMassML: downloading model artifacts on first use (~0.6 GB)...\n",
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
