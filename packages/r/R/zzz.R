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
