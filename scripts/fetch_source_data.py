"""
Copy source data files from the sibling TaxonBodyMass_DB repository into data/,
copy the citation files on into the R and Python packages, which bundle them
for get_citations() and create_bib(), and stage the provenance artifacts.

Run from the TaxonBodyMassML root:
    python scripts/fetch_source_data.py

TaxonBodyMass_DB must be a sibling of TaxonBodyMassML (i.e. both sit inside
the same parent directory, as in the FracFeed workspace layout).

Files (TaxonBodyMass_DB -> data/):
    TaxonBodyMass.csv                     -> TaxonBodyMass.csv
    Bib/TaxonBodyMass_CitationCiteIDs.csv -> TaxonBodyMass_CitationCiteIDs.csv
    Bib/TaxonBodyMass_Citations.bib       -> Citations_BodyMass.bib
    Bib/TaxonBodyMass_PrimaryCitations.bib -> PrimaryCitations_BodyMass.bib
    TaxonBodyMass_Provenance.csv.gz       -> TaxonBodyMass_Provenance.csv.gz

The CiteID map and the compilation bibliography are bundled by both packages
(the CiteID CSV has gained `doi`, `role` and `bib_file` columns; the packages
read only `Bibcite` and `CiteID`, so "first occurrence wins" is unaffected).
The primary bibliography and the provenance table are NOT bundled: they are
distributed as Hugging Face artifacts next to lookup.json (issue #21 /
TaxonBodyMass_DB#1), so they are also staged into artifacts/ for
scripts/export_artifacts.py (which checksums them) and
scripts/publish_artifacts.py (which uploads them, only with explicit approval).
"""

import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
TBM_DB_ROOT = REPO_ROOT.parent / "TaxonBodyMass_DB"
DST_DIR = REPO_ROOT / "data"
ARTIFACTS_DIR = REPO_ROOT / "artifacts"
PKG_DATA_DIRS = [
    REPO_ROOT / "packages" / "r" / "inst" / "extdata",
    REPO_ROOT / "packages" / "python" / "taxonbodymassml" / "data",
]

SOURCES = [
    (TBM_DB_ROOT / "TaxonBodyMass.csv", DST_DIR / "TaxonBodyMass.csv"),
    (
        TBM_DB_ROOT / "Bib" / "TaxonBodyMass_CitationCiteIDs.csv",
        DST_DIR / "TaxonBodyMass_CitationCiteIDs.csv",
    ),
    (
        TBM_DB_ROOT / "Bib" / "TaxonBodyMass_Citations.bib",
        DST_DIR / "Citations_BodyMass.bib",
    ),
    (
        TBM_DB_ROOT / "Bib" / "TaxonBodyMass_PrimaryCitations.bib",
        DST_DIR / "PrimaryCitations_BodyMass.bib",
    ),
    (
        TBM_DB_ROOT / "TaxonBodyMass_Provenance.csv.gz",
        DST_DIR / "TaxonBodyMass_Provenance.csv.gz",
    ),
]
# Citation files that each package bundles (copied from data/ after the sync).
PACKAGED = ["TaxonBodyMass_CitationCiteIDs.csv", "Citations_BodyMass.bib"]
for pkg_dir in PKG_DATA_DIRS:
    SOURCES += [(DST_DIR / name, pkg_dir / name) for name in PACKAGED]
# Provenance artifacts: staged for export/publish, downloaded by the packages.
PROVENANCE_ARTIFACTS = ["PrimaryCitations_BodyMass.bib", "TaxonBodyMass_Provenance.csv.gz"]
ARTIFACTS_DIR.mkdir(exist_ok=True)
SOURCES += [(DST_DIR / name, ARTIFACTS_DIR / name) for name in PROVENANCE_ARTIFACTS]

for src, dst in SOURCES:
    if not src.exists():
        raise FileNotFoundError(f"Source not found: {src}")
    shutil.copy2(src, dst)
    print(f"  {src}\n  -> {dst}\n")

print("Done.")
