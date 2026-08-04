"""
Run the manuscript code examples and print formatted output for §4.3.

Requires internet access for GBIF taxonomy lookups on first run.
Model artifacts are cached after the first download (~2 GB).

Run from repo root:
  predictive_models/.venv/bin/python scripts/run_examples.py
"""

import taxonbodymassml as tbm

# ---------------------------------------------------------------------------
# Example 1 — single species, default arguments
# ---------------------------------------------------------------------------
print("=== Example 1: predict_mass('Nucella ostrina') ===")
r1 = tbm.predict_mass("Nucella ostrina", confidence_interval=True)
print(r1[["species", "mass_g", "lower_bound", "upper_bound"]].to_string(index=False))

# ---------------------------------------------------------------------------
# Example 2 — batch with fuzzy matching and 90% conformal intervals
# ---------------------------------------------------------------------------
print("\n=== Example 2: batch with fuzzy_match_name=True, confidence_interval=0.90 ===")
r2 = tbm.predict_mass(
    [
        "Balanus glandula",  # correctly spelled; no correction
        "Nutella ostrina",  # misspelling; fuzzy-corrected to Nucella ostrina
        "Nutella glandula",  # unresolvable; returns NaN
    ],
    fuzzy_match_name=True,
    confidence_interval=0.90,
)
cols = ["species", "matched_name", "mass_g", "lower_bound", "upper_bound"]
print(r2[cols].to_string(index=False))
