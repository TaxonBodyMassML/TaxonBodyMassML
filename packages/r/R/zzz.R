.onAttach <- function(libname, pkgname) {
  if (!.artifacts_exist()) {
    packageStartupMessage(
      "TaxonBodyMassML: model artifacts not yet downloaded. ",
      "They will be downloaded automatically on first call to predict_mass() ",
      "or lookup_taxonomy(). ",
      "Or run TaxonBodyMassML::download_model() now."
    )
  }
}

# Suppress R CMD CHECK notes about package-level environments defined in other
# files (cache.R, options.R, http.R, model.R) that are referenced across the package.
utils::globalVariables(c(
  ".artifacts_exist",
  ".tbm_cache",
  ".tbm_opts",
  ".ncbi_rl",
  ".ARTIFACT_FILES"
))
