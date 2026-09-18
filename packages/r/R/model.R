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
.MODEL_ARTIFACT_VERSION <- "0.11.0"

.CHECKSUMS <- list(
  # XGBoost (original method)
  "model.ubj"               = "832ceb0a18d6225f09eeabf78cb311d5c5ef5f60f69c50e792c38b248751b16c",
  "calibration.json"        = "81f4d24973f9cc9c6ef5fea226e6d63d5c8c50cdd295d7bc4d9ef378372b51ce",
  "calibration_by_rank.json" = "6689d267b78375d2eee89ceb464f1b3f882a47eb3247781dba7ba11b97e8d8da",
  "categories.json"         = "aec5460c2a00cfec8926e8f2adea58970e70da9e05fba4973f1c7175f2f21ceb",
  "lookup.json"             = "8f03b6bdbb1c16391f8620e6ae86b6afa57007fa486ecca468bd6eba8509a933",
  # Entity Embeddings
  "embeddings.json"              = "08ff12d50f27a375143026079d33c1e8e4821c81ff841999589ddc4c864133be",
  "model_ee.ubj"                 = "083ba16385fb7496426d6e5110a8e2d13c9da9d8cc568dc1d207601787155006",
  "calibration_ee.json"          = "227865b3ef6e48576025316402959b7c50c8ad1d362d273acdccf731f767d8ca",
  "calibration_by_rank_ee.json"  = "aaa60bb1b813f715d867d8fa0c926bab65083203e57783cbdc7c057ade79cd9a"
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
#' Downloads all model artifacts (~0.4 GB in total) to the local user cache
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
      "TaxonBodyMassML: downloading model artifacts on first use (~0.4 GB)...\n",
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
