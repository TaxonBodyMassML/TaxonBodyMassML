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
.MODEL_ARTIFACT_VERSION <- "0.13.0"

.CHECKSUMS <- list(
  # XGBoost (original method)
  "model.ubj"               = "8d4364a5f6451ccc457392faa80e761ede0c6ab7f58fdd34b49cca6df30f5e23",
  "calibration.json"        = "4903078978c6aa1432dfbddbf46fe67ef6839cca5baa6395f070bf4536c5e6bb",
  "calibration_by_rank.json" = "ccd5d4f29606174038c1ac8d62d91395eb909257dfd1eb6478bb72926c6740e7",
  "categories.json"         = "6cd53c20b129ace0be8d3546487174caffc095242794d6f4452e3dd827e2708c",
  "lookup.json"             = "4a1c0b037556f499c4264bf8cd6d5005ef3bf1a96c4e859236afad7074970570",
  # Entity Embeddings
  "embeddings.json"              = "b6c5bec4334653c247353054da1ad75592cf6bc6e146d07cb5a5f5cb575062cd",
  "model_ee.ubj"                 = "de95816c6184d2a7979136c700ce91bdaa41974fc6f8927bb294bcad9693452a",
  "calibration_ee.json"          = "2abbf251382e08e283f49aaf3a3681e03d554df82ecd576d36e264a831ff0bae",
  "calibration_by_rank_ee.json"  = "43f21b33c208166afafd2a6c8d3d3ddc8b9dab1520231de6324d53ee9ca05e86"
)

# Provenance artifacts (TaxonBodyMass_DB issue #1): the generated primary-source
# bibliography and the species x source x reference provenance table, built from
# the same TaxonBodyMass_DB snapshot as lookup.json. Downloaded by
# download_model() together with the model artifacts, and on first use by
# get_citations(level = "primary") / create_bib(level = "primary").
# predict_mass() does not need them.
.PROVENANCE_CHECKSUMS <- list(
  "PrimaryCitations_BodyMass.bib"   = "bfef580ef0be5c139186b3d68a0bd1c262d34646940be6a3e3ed3248f47da8ef",
  "TaxonBodyMass_Provenance.csv.gz" = "9e6e76bc4fb0691ddd660367074ce548c87743959f6bd8a5ef8eeb06bc79eaee"
)

# Model artifacts (needed by predict_mass) and provenance artifacts are
# verified and downloaded as two groups so a prediction never waits for, or
# fails on, the citation files.
.ARTIFACT_FILES   <- names(.CHECKSUMS)
.PROVENANCE_FILES <- names(.PROVENANCE_CHECKSUMS)
.ALL_CHECKSUMS    <- c(.CHECKSUMS, .PROVENANCE_CHECKSUMS)

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
  expected <- .ALL_CHECKSUMS[[filename]]
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
#' @param files Character. The artifact files to check; default the model
#'   artifacts (`.ARTIFACT_FILES`). Pass `.PROVENANCE_FILES` for the
#'   provenance artifacts.
#' @return Logical `TRUE` if all artifacts are present and pass SHA256 verification.
#' @keywords internal
.artifacts_cached <- function(files = .ARTIFACT_FILES) {
  cache <- .cache_dir()
  all(vapply(files, function(f) {
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
#' (`lookup.json`), the Entity Embeddings model (`embeddings.json`,
#' `model_ee.ubj`, `calibration_ee.json`, `calibration_by_rank_ee.json`), and
#' the provenance artifacts used by `get_citations(level = "primary")` and
#' `create_bib(level = "primary")`: the generated primary-source bibliography
#' (`PrimaryCitations_BodyMass.bib`) and the species x source x reference
#' provenance table (`TaxonBodyMass_Provenance.csv.gz`). Every file is
#' verified against a SHA256 checksum bundled with the package. On subsequent
#' calls the files are skipped unless `force = TRUE` or the checksum does not
#' match. A provenance file that the requested revision does not carry (a
#' revision published before the provenance artifacts existed) is reported
#' with a warning; the model artifacts are always required.
#'
#' @param version Character. HuggingFace revision to download. `"latest"`
#'   resolves to the revision matching the bundled checksums
#'   (`r-v<version>`). Pass a specific tag or commit SHA to pin a version.
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
  .download_files(.ARTIFACT_FILES, version = version, force = force)
  .download_files(.PROVENANCE_FILES, version = version, force = force,
                  optional = TRUE)
  invisible(NULL)
}

# Download `files` into the cache unless a verified copy exists. With
# `optional = TRUE` a file absent from the revision (HTTP 404) is reported
# with a warning instead of an error.
#' @noRd
.download_files <- function(files, version = "latest", force = FALSE,
                            optional = FALSE) {
  dir.create(.cache_dir(), recursive = TRUE, showWarnings = FALSE)
  revision <- if (identical(version, "latest")) {
    paste0("r-v", .MODEL_ARTIFACT_VERSION)
  } else {
    version
  }

  for (filename in files) {
    dest <- file.path(.cache_dir(), filename)
    if (!force && file.exists(dest) && isTRUE(.verify_file(dest, filename))) {
      next
    }
    message("  Downloading ", filename, " from ", .HF_REPO_ID, " on Hugging Face...")
    req <- .tbm_req(.hf_url(filename, revision)) |>
      httr2::req_timeout(7200) |>
      httr2::req_progress()
    not_found <- FALSE
    tryCatch(
      httr2::req_perform(req, path = dest),
      httr2_http_404 = function(e) {
        if (!optional) stop(e)
        not_found <<- TRUE
      }
    )
    if (not_found) {
      if (file.exists(dest)) unlink(dest)
      warning(filename, " is not part of artifact revision '", revision, "'; ",
              "primary-source citations are unavailable until a newer artifact ",
              "revision is published.", call. = FALSE)
      next
    }
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
    .download_files(.ARTIFACT_FILES)
  }
  .model_env$artifacts_ok <- TRUE
}

# Download the provenance artifacts on first use; stop when the artifact
# revision does not carry them.
.ensure_provenance_artifacts <- function() {
  if (isTRUE(.model_env$provenance_ok)) return(invisible(NULL))
  if (!.artifacts_cached(.PROVENANCE_FILES)) {
    message(
      "TaxonBodyMassML: downloading provenance artifacts on first use...\n",
      "  Files: ", paste(.PROVENANCE_FILES, collapse = ", ")
    )
    .download_files(.PROVENANCE_FILES, optional = TRUE)
    if (!.artifacts_cached(.PROVENANCE_FILES)) {
      stop(
        "Provenance artifacts are not available (artifact revision r-v",
        .MODEL_ARTIFACT_VERSION, "). Use get_citations()/create_bib() with ",
        "level = \"source\", or upgrade the package once a revision with ",
        "provenance artifacts is published.",
        call. = FALSE
      )
    }
  }
  .model_env$provenance_ok <- TRUE
}

# Path of a verified provenance artifact in the cache (downloads on first use).
#' @noRd
.provenance_path <- function(filename) {
  .ensure_provenance_artifacts()
  file.path(.cache_dir(), filename)
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
