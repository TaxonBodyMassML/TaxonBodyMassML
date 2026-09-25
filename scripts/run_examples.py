"""
Run the manuscript code examples (Python mirror of scripts/run_examples.R) and
print their output.  The manuscript quotes the R output; this script checks
that the Python package gives the same answers.

Requires internet access for GBIF taxonomy lookups on first run.
Model artifacts are cached after the first download (~0.4 GB).

Run from repo root:
  predictive_models/.venv/bin/python scripts/run_examples.py
"""

import tempfile
from importlib import metadata
from pathlib import Path

import taxonbodymassml as tbm

print("taxonbodymassml", metadata.version("taxonbodymassml"))

# ---------------------------------------------------------------------------
# Example 1 — single-taxon queries: recorded mass vs forced model prediction
# ---------------------------------------------------------------------------
print("\n=== Example 1a: predict_mass('Nucella ostrina') ===")
print(tbm.predict_mass("Nucella ostrina").to_string(index=False))

print(
    "\n=== Example 1b: predict_mass('Nucella ostrina', lookup=False, confidence_interval=True) ==="
)
print(
    tbm.predict_mass("Nucella ostrina", lookup=False, confidence_interval=True).to_string(
        index=False
    )
)

# ---------------------------------------------------------------------------
# Example 2 — batch with fuzzy matching and default 90% conformal intervals
# ---------------------------------------------------------------------------
print("\n=== Example 2: batch with fuzzy_match_name=True, confidence_interval=True ===")
r2 = tbm.predict_mass(
    [
        "Haustrum haustorium",  # correctly spelled; mass recorded in the database
        "Nucela lima",  # misspelling; fuzzy-corrected, then model-inferred
        "Nutella haustrina",  # unresolvable (not a true species); returns NaN
    ],
    fuzzy_match_name=True,
    confidence_interval=True,
)
print(r2.to_string(index=False))

# ---------------------------------------------------------------------------
# Example 3 — include_source: provenance of each returned mass value
# ---------------------------------------------------------------------------
print("\n=== Example 3: predict_mass() with include_source=True ===")
r3 = tbm.predict_mass(
    [
        "Haustrum haustorium",  # mass recorded in the database; returns the measurement
        "Nucella lima",  # not in the database; model infers from genus
    ],
    include_source=True,
)
print(r3.to_string(index=False))

# ---------------------------------------------------------------------------
# Example 4 — create_bib(): BibTeX file of the sources behind the predictions
# ---------------------------------------------------------------------------
print("\n=== Example 4: create_bib() on the Example 3 result ===")
bib_file = tbm.create_bib(r3, Path(tempfile.gettempdir()) / "my_sources.bib")
print(bib_file.read_text(encoding="utf-8"))
