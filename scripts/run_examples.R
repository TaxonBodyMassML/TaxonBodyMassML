# Run the manuscript code examples and print formatted output for §4.3.
#
# Requires internet access for GBIF taxonomy lookups on first run.
# Model artifacts are cached after the first download (~2 GB).
#
# Run from repo root:
#   Rscript scripts/run_examples.R

library(TaxonBodyMassML)

# ---------------------------------------------------------------------------
# Example 1 — single species, default arguments
# ---------------------------------------------------------------------------
cat("=== Example 1: predict_mass('Nucella ostrina') ===\n")
predict_mass("Nucella ostrina")

# ---------------------------------------------------------------------------
# Example 2 — batch with fuzzy matching and 90% conformal intervals
# ---------------------------------------------------------------------------
cat("\n=== Example 2: batch with fuzzy_match_name = TRUE,",
    "confidence_interval = 0.90 ===\n")
predict_mass(
  c("Haustrum haustorium",  # correctly spelled; no correction
    "Nutella ostrina",       # misspelling; fuzzy-corrected to Nucella ostrina
    "Nutella haustrina"),    # unresolvable; returns NA
  fuzzy_match_name = TRUE,
  confidence_interval = 0.90
)
