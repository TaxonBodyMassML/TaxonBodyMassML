# Run the manuscript code examples and print their output for the "Examples"
# subsection of ms/manuscript.tex (Distribution and usage).  Paste the console
# output verbatim into the corresponding lstlisting blocks.
#
# Requires internet access for GBIF taxonomy lookups on first run.
# Model artifacts are cached after the first download (~0.4 GB).
#
# Run from repo root:
#   Rscript scripts/run_examples.R

library(TaxonBodyMassML)
cat("TaxonBodyMassML", as.character(packageVersion("TaxonBodyMassML")), "\n")

# ---------------------------------------------------------------------------
# Example 1 — single-taxon queries: recorded mass vs forced model prediction
# ---------------------------------------------------------------------------
cat("\n=== Example 1a: predict_mass('Nucella ostrina') ===\n")
predict_mass("Nucella ostrina")

cat("\n=== Example 1b: predict_mass('Nucella ostrina', lookup = FALSE,",
    "confidence_interval = TRUE) ===\n")
predict_mass("Nucella ostrina", lookup = FALSE, confidence_interval = TRUE)

# ---------------------------------------------------------------------------
# Example 2 — batch with fuzzy matching and default 90% conformal intervals
# ---------------------------------------------------------------------------
cat("\n=== Example 2: batch with fuzzy_match_name = TRUE,",
    "confidence_interval = TRUE ===\n")
predict_mass(
  c("Haustrum haustorium",   # correctly spelled; mass recorded in the database
    "Nucela lima",           # misspelling; fuzzy-corrected, then model-inferred
    "Nutella haustrina"),    # unresolvable (not a true species); returns NA
  fuzzy_match_name = TRUE,
  confidence_interval = TRUE
)

# ---------------------------------------------------------------------------
# Example 3 — include_source: provenance of each returned mass value
# ---------------------------------------------------------------------------
cat("\n=== Example 3: predict_mass() with include_source = TRUE ===\n")
predict_mass(
  c("Nucella ostrina",  # mass recorded in the database; returns the measurement
    "Nucella lima"),    # not in the database; model infers from genus
  include_source = TRUE
)
