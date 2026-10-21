.onAttach <- function(libname, pkgname) {
  if (!.artifacts_exist(.resolve_model(.DEFAULT_METHOD))) {
    packageStartupMessage(
      "TaxonBodyMassML: model artifacts not yet downloaded. ",
      "They will be downloaded automatically on first call to predict_mass() ",
      "or lookup_taxonomy(). ",
      "Or run TaxonBodyMassML::download_model() now."
    )
  }
}
