"""
Run the manuscript code examples and print formatted output for the
Distribution and usage section.

Requires internet access for GBIF taxonomy lookups on first run.
Model artifacts are cached after the first download (~0.6 GB).

Run from repo root:
  predictive_models/.venv/bin/python scripts/run_examples.py
"""

import taxonbodymassml as tbm

# ---------------------------------------------------------------------------
# Example 1 — single species, default arguments
# ---------------------------------------------------------------------------
print("=== Example 1: predict_mass('Nucella ostrina') ===")
r1 = tbm.predict_mass("Nucella ostrina", confidence_interval=True)
print(r1[["taxon", "mass_g", "lower_bound", "upper_bound"]].to_string(index=False))

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
cols = ["taxon", "matched_name", "mass_g", "lower_bound", "upper_bound"]
print(r2[cols].to_string(index=False))

# ---------------------------------------------------------------------------
# Example 3 — include_source: show provenance of each returned mass value
# ---------------------------------------------------------------------------
print("\n=== Example 3: predict_mass() with include_source=True ===")
r3 = tbm.predict_mass(
    [
        "Nucella ostrina",  # in training data — returns empirical mass
        "Nucella lima",  # not in training data — model infers from genus
    ],
    include_source=True,
)
print(r3[["taxon", "mass_g", "source"]].to_string(index=False))
