"""
Copy source data files from the sibling TaxonBodyMass_DB repository into data/.

Run from the TaxonBodyMassML root:
    python scripts/fetch_source_data.py

TaxonBodyMass_DB must be a sibling of TaxonBodyMassML (i.e. both sit inside
the same parent directory, as in the FracFeed workspace layout).
"""

import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
TBM_DB_ROOT = REPO_ROOT.parent / "TaxonBodyMass_DB"
DST_DIR = REPO_ROOT / "data"

SOURCES = [
    (TBM_DB_ROOT / "TaxonBodyMass.csv", DST_DIR / "TaxonBodyMass.csv"),
    (
        TBM_DB_ROOT / "bib" / "TaxonBodyMass_CitationCiteIDs.csv",
        DST_DIR / "TaxonBodyMass_CitationCiteIDs.csv",
    ),
    (
        TBM_DB_ROOT / "bib" / "TaxonBodyMass_Citations.bib",
        DST_DIR / "Citations_BodyMass.bib",
    ),
]

for src, dst in SOURCES:
    if not src.exists():
        raise FileNotFoundError(f"Source not found: {src}")
    shutil.copy2(src, dst)
    print(f"  {src}\n  -> {dst}\n")

print("Done.")
