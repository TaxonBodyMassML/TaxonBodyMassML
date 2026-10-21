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
distributed as Hugging Face artifacts in ``provenance/<db_version>/`` (issue #21 /
TaxonBodyMass_DB#1), staged here for scripts/export_artifacts.py (which
checksums them) and scripts/publish_artifacts.py (which uploads them, only with
explicit approval).
"""

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

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

# Provenance artifacts: staged into artifacts/provenance/<db_version>/
# so publish_artifacts.py can upload them as a versioned folder.
PROVENANCE_FILES = ["PrimaryCitations_BodyMass.bib", "TaxonBodyMass_Provenance.csv.gz"]

for src, dst in SOURCES:
    if not src.exists():
        raise FileNotFoundError(f"Source not found: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"  {src.name} -> {dst.relative_to(REPO_ROOT)}")

# Stage provenance into artifacts/provenance/<db_version>/
# and update artifacts/manifest.json
from scripts._db_version import db_version as resolve_db_version  # noqa: E402
from scripts.manifest import validate  # noqa: E402
from scripts.manifest import add_provenance, empty  # noqa: E402
from scripts.manifest import load as load_manifest  # noqa: E402
from scripts.manifest import save as save_manifest  # noqa: E402

db_ver = resolve_db_version()
prov_dir = ARTIFACTS_DIR / "provenance" / db_ver
prov_dir.mkdir(parents=True, exist_ok=True)

for name in PROVENANCE_FILES:
    src = DST_DIR / name
    if not src.exists():
        print(f"  WARNING: {name} not found in data/ — skipping provenance staging")
        continue
    shutil.copy2(src, prov_dir / name)
    print(f"  {name} -> artifacts/provenance/{db_ver}/{name}")

# Update manifest.json with the provenance entry
manifest_path = ARTIFACTS_DIR / "manifest.json"
manifest = load_manifest(manifest_path) if manifest_path.exists() else empty()
try:
    add_provenance(manifest, db_ver, prov_dir)
    validate(manifest)
    save_manifest(manifest, manifest_path)
    print(f"  Manifest updated: provenance/{db_ver}")
except (FileNotFoundError, ValueError) as exc:
    print(f"  WARNING: could not update manifest: {exc}")

print("\nDone.")
