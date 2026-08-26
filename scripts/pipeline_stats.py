"""
pipeline_stats.py
Compute per-pass taxonomy enrichment statistics for the TaxonBodyMassML pipeline.
Run from the repo root:
    predictive_models/.venv/bin/python scripts/pipeline_stats.py
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent
PASSES = ROOT / "data" / "passes"
DATA = ROOT / "data"

TAXONOMY_FIELDS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def load_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False)


def has_any_missing_taxonomy(df: pd.DataFrame) -> pd.Series:
    """Boolean mask: rows with at least one NaN among the 7 taxonomy fields."""
    cols = [c for c in TAXONOMY_FIELDS if c in df.columns]
    return df[cols].isnull().any(axis=1)


def all_taxonomy_filled(df: pd.DataFrame) -> pd.Series:
    """Boolean mask: rows with ALL 7 taxonomy fields filled."""
    cols = [c for c in TAXONOMY_FIELDS if c in df.columns]
    if len(cols) < len(TAXONOMY_FIELDS):
        # Columns not yet present => nothing is filled
        return pd.Series(False, index=df.index)
    return df[cols].notnull().all(axis=1)


def read_missed(path: Path) -> int:
    """Count non-empty lines in a missed-species txt file."""
    if not path.exists():
        return 0
    lines = [ln.strip() for ln in path.read_text().splitlines() if ln.strip()]
    return len(lines)


def pct(count: int, total: int) -> str:
    if total == 0:
        return "N/A"
    return f"{100 * count / total:.1f}%"


def fmt(n: int) -> str:
    return f"{n:,}"


# ---------------------------------------------------------------------------
# Load files
# ---------------------------------------------------------------------------

src = load_csv(DATA / "TaxonBodyMass.csv")
gbif_out = load_csv(PASSES / "TaxonBodyMass_GBIF_pass.csv")
ncbi_out = load_csv(PASSES / "TaxonBodyMass_NCBI_pass.csv")
worms_out = load_csv(PASSES / "TaxonBodyMass_WoRMS_pass.csv")
col_out = load_csv(PASSES / "TaxonBodyMass_COL_pass.csv")
wiki_out = load_csv(PASSES / "TaxonBodyMass_Wikidata_pass.csv")
itis_out = load_csv(PASSES / "TaxonBodyMass_ITIS_pass.csv")
curated = load_csv(PASSES / "TaxonBodyMass_curated.csv")

missed_gbif = read_missed(PASSES / "missed_species_gbif.txt")
missed_ncbi = read_missed(PASSES / "missed_species_ncbi.txt")
missed_worms = read_missed(PASSES / "missed_species_worms.txt")
missed_col = read_missed(PASSES / "missed_species_col.txt")
missed_wiki = read_missed(PASSES / "missed_species_wikidata.txt")
missed_itis = read_missed(PASSES / "missed_species_itis.txt")

# ---------------------------------------------------------------------------
# Compute per-pass statistics
# ---------------------------------------------------------------------------

# Pass 1 — GBIF
# All unique taxa in source are submitted (GBIF initialises taxonomy columns).
gbif_queried = src["taxon"].nunique()
gbif_resolved = gbif_queried - missed_gbif
gbif_complete_rows = int(all_taxonomy_filled(gbif_out).sum())
gbif_total_rows = len(gbif_out)

# Pass 2 — NCBI
# Input is GBIF output; queried = unique taxa with >=1 missing field
ncbi_queried = gbif_out.loc[has_any_missing_taxonomy(gbif_out), "taxon"].nunique()
ncbi_resolved = ncbi_queried - missed_ncbi
ncbi_complete_rows = int(all_taxonomy_filled(ncbi_out).sum())
ncbi_total_rows = len(ncbi_out)

# Pass 3 — WoRMS
worms_queried = ncbi_out.loc[has_any_missing_taxonomy(ncbi_out), "taxon"].nunique()
worms_resolved = worms_queried - missed_worms
worms_complete_rows = int(all_taxonomy_filled(worms_out).sum())
worms_total_rows = len(worms_out)

# Pass 4 — COL
col_queried = worms_out.loc[has_any_missing_taxonomy(worms_out), "taxon"].nunique()
col_resolved = col_queried - missed_col
col_complete_rows = int(all_taxonomy_filled(col_out).sum())
col_total_rows = len(col_out)

# Pass 5 — Wikidata
wiki_queried = col_out.loc[has_any_missing_taxonomy(col_out), "taxon"].nunique()
wiki_resolved = wiki_queried - missed_wiki
wiki_complete_rows = int(all_taxonomy_filled(wiki_out).sum())
wiki_total_rows = len(wiki_out)

# Pass 6 — ITIS
itis_queried = wiki_out.loc[has_any_missing_taxonomy(wiki_out), "taxon"].nunique()
itis_resolved = itis_queried - missed_itis
itis_complete_rows = int(all_taxonomy_filled(itis_out).sum())
itis_total_rows = len(itis_out)

# filter_kingdoms
curated_rows = len(curated)
removed_rows = itis_total_rows - curated_rows

# ---------------------------------------------------------------------------
# Print report
# ---------------------------------------------------------------------------

passes = [
    (
        "1 GBIF",
        "GBIF species/match",
        gbif_queried,
        gbif_resolved,
        missed_gbif,
        gbif_complete_rows,
        gbif_total_rows,
    ),
    (
        "2 NCBI",
        "NCBI Entrez",
        ncbi_queried,
        ncbi_resolved,
        missed_ncbi,
        ncbi_complete_rows,
        ncbi_total_rows,
    ),
    (
        "3 WoRMS",
        "WoRMS AphiaRecordsByMatch",
        worms_queried,
        worms_resolved,
        missed_worms,
        worms_complete_rows,
        worms_total_rows,
    ),
    (
        "4 COL",
        "COL ChecklistBank",
        col_queried,
        col_resolved,
        missed_col,
        col_complete_rows,
        col_total_rows,
    ),
    (
        "5 Wikidata",
        "Wikidata SPARQL",
        wiki_queried,
        wiki_resolved,
        missed_wiki,
        wiki_complete_rows,
        wiki_total_rows,
    ),
    (
        "6 ITIS",
        "ITIS JSON service",
        itis_queried,
        itis_resolved,
        missed_itis,
        itis_complete_rows,
        itis_total_rows,
    ),
]

print()
print("=" * 80)
print("TaxonBodyMassML — Pipeline Enrichment Statistics")
print("=" * 80)
print()
print(f"Source CSV total rows      : {fmt(len(src))}")
print(f"Source CSV unique taxa     : {fmt(src['taxon'].nunique())}")
print()

# Table header
col_w = [10, 26, 14, 12, 10, 20]
header = (
    f"{'Pass':<{col_w[0]}} {'API':<{col_w[1]}} "
    f"{'Taxa queried':>{col_w[2]}} {'Resolved':>{col_w[3]}} "
    f"{'Missed':>{col_w[4]}} {'Cumulative % complete':>{col_w[5]}}"
)
print(header)
print("-" * sum(col_w))

for pass_label, api, queried, resolved, missed, complete, total in passes:
    cumul = pct(complete, total)
    row = (
        f"{pass_label:<{col_w[0]}} "
        f"{api:<{col_w[1]}} "
        f"{fmt(queried):>{col_w[2]}} "
        f"{fmt(resolved):>{col_w[3]}} "
        f"{fmt(missed):>{col_w[4]}} "
        f"{cumul:>{col_w[5]}}"
    )
    print(row)

print()
print("filter_kingdoms step")
print("-" * 40)
print(f"  Input rows  (ITIS pass) : {fmt(itis_total_rows)}")
print(f"  Output rows (curated)   : {fmt(curated_rows)}")
print(f"  Rows removed            : {fmt(removed_rows)}")
print()
print("Missed-species logs written to data/passes/:")
for name in [
    "missed_species_gbif.txt",
    "missed_species_ncbi.txt",
    "missed_species_worms.txt",
    "missed_species_col.txt",
    "missed_species_wikidata.txt",
    "missed_species_itis.txt",
]:
    print(f"  {name}")
print()
print("=" * 80)
