"""
Training-data statistics for the manuscript.

Reads data/TaxonBodyMass.csv (the copy of TaxonBodyMass_DB/TaxonBodyMass.csv
fetched by scripts/fetch_source_data.py; one row per species) and writes

  predictive_models/results/tab_kingdom.tex   species and mass range per kingdom
  predictive_models/results/tab_class.tex     the same for the 20 largest classes
  predictive_models/results/data_stats.json   every count quoted in the manuscript
                                              (consumed by make_numbers_tex.py)

With --db-passes DIR (default: ../TaxonBodyMass_DB/sources/passes) the
resolution chain (names submitted -> resolved -> autotrophs removed -> unique
species) is derived from the final enrichment pass file, applying the same
autotroph rule as TaxonBodyMass_DB/R/library/filter_autotrophs.r.

Run from repo root:
  predictive_models/.venv/bin/python scripts/extract_training_stats.py
"""

from __future__ import annotations

import argparse
import math
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _results_common import (  # noqa: E402
    DATA,
    REPO,
    RESULTS,
    TAXONOMY_COLS,
    fmt_int,
    write_json,
    write_tex,
)

# Mirror of TaxonBodyMass_DB/R/library/filter_autotrophs.r (v5.1.0).  Used only
# to reconstruct the count chain from the pre-filter pass file.
AUTOTROPH_KINGDOMS = {"Plantae", "Viridiplantae", "Fungi"}
AUTOTROPH_PHYLA = {
    "Ochrophyta",
    "Bacillariophyta",
    "Haptophyta",
    "Cryptophyta",
    "Chlorophyta",
    "Rhodophyta",
    "Charophyta",
    "Glaucophyta",
    "Streptophyta",
    "Euglenophyta",
    "Cyanobacteria",
    "Cyanobacteriota",
}
AUTOTROPH_GENERA = {
    "Alexandrium",
    "Amphidinium",
    "Ceratium",
    "Cochlodinium",
    "Dinophysis",
    "Fragilidium",
    "Glenodinium",
    "Gonyaulax",
    "Gymnodinium",
    "Heterocapsa",
    "Lingulodinium",
    "Parvodinium",
    "Peridinium",
    "Prorocentrum",
    "Scrippsiella",
    "Spiniferodinium",
    "Takayama",
    "Thecadinium",
    "Tripos",
    "Yihiella",
    "Euglena",
    "Eutreptiella",
    "Lepocinclis",
}


def _tabular(df_g: pd.DataFrame, label: str, n: int | None = None) -> list[str]:
    lines = [
        r"\begin{tabular}{lrrr}",
        r"\toprule",
        r" & & \multicolumn{2}{c}{Mass range ($\log_{10}$ g)} \\",
        r"\cmidrule(l){3-4}",
        f"{label} & Species & min & max \\\\",
        r"\midrule",
    ]
    rows = df_g if n is None else df_g.head(n)
    for name, row in rows.iterrows():
        lines.append(
            f"{name} & {fmt_int(row['n_species'])} & ${row['log10_min']:.1f}$ & ${row['log10_max']:.1f}$ \\\\"  # noqa: E501
        )
    lines += [r"\bottomrule", r"\end{tabular}"]
    return lines


def summarise(df: pd.DataFrame, col: str) -> pd.DataFrame:
    g = df.groupby(col)
    out = pd.DataFrame(
        {
            "n_species": g["species"].count(),
            "log10_min": g["mass_g"].min().apply(math.log10),
            "log10_med": g["mass_g"].median().apply(math.log10),
            "log10_max": g["mass_g"].max().apply(math.log10),
        }
    ).sort_values("n_species", ascending=False)
    return out


def resolution_chain(passes_dir: Path) -> dict | None:
    path = passes_dir / "TaxonBodyMass_Wikidata_pass.csv"
    if not path.exists():
        print(f"  (no {path}; resolution chain skipped)")
        return None
    p = pd.read_csv(path, low_memory=False)
    resolved = p[p["species"].notna()]
    kept = resolved[
        ~resolved["kingdom"].isin(AUTOTROPH_KINGDOMS)
        & ~resolved["phylum"].isin(AUTOTROPH_PHYLA)
        & ~resolved["genus"].isin(AUTOTROPH_GENERA)
    ]
    return {
        "pass_file": str(path),
        "n_names_submitted": int(p["taxon"].nunique()),
        "n_names_resolved": int(resolved["taxon"].nunique()),
        "n_names_autotroph": int(resolved["taxon"].nunique() - kept["taxon"].nunique()),
        "n_species_after_filter": int(kept["species"].nunique()),
        "note": "applies the v5.1.0 filter rule to the pre-filter, pre-deduplication pass file; "
        "may differ by a few records from the released CSV (later manual overrides)",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--db-passes",
        type=Path,
        default=REPO.parent / "TaxonBodyMass_DB" / "sources" / "passes",
        help="TaxonBodyMass_DB/sources/passes directory (resolution chain)",
    )
    args = ap.parse_args()

    raw = pd.read_csv(DATA / "TaxonBodyMass.csv")
    n_db = len(raw)
    used = raw.dropna(subset=TAXONOMY_COLS + ["mass_g"])
    used = used[used["mass_g"] > 0]
    n_used = len(used)
    print(f"Database rows: {n_db:,}; usable (complete taxonomy): {n_used:,}")

    # Distinct data sources: source_mass lists contributing sources separated by ';'
    src_counter: Counter = Counter()
    single_source: Counter = Counter()
    for s in raw["source_mass"].dropna():
        parts = [x.strip() for x in str(s).split(";") if x.strip()]
        src_counter.update(parts)
        if len(parts) == 1:
            single_source[parts[0]] += 1

    by_kingdom = summarise(used, "kingdom")
    by_class = summarise(used, "class")
    write_tex(RESULTS / "tab_kingdom.tex", _tabular(by_kingdom, "Kingdom"))
    write_tex(RESULTS / "tab_class.tex", _tabular(by_class, "Class", n=20))

    i_min, i_max = used["mass_g"].idxmin(), used["mass_g"].idxmax()
    smallest, largest = used.loc[i_min], used.loc[i_max]
    stats = {
        "n_db": n_db,
        "n_used": n_used,
        "n_dropped_missing_rank": n_db - n_used,
        "n_source_records": int(raw["n"].sum()) if "n" in raw.columns else None,
        "n_sources_distinct": len(src_counter),
        "top_single_source_contributors": single_source.most_common(6),
        "n_lookup_species": n_db,
        "kingdoms": {k: int(v) for k, v in by_kingdom["n_species"].items()},
        "pct_animalia": 100.0 * by_kingdom["n_species"].get("Animalia", 0) / n_used,
        "top_classes": [(k, int(v)) for k, v in by_class["n_species"].head(6).items()],
        "n_classes": int(used["class"].nunique()),
        "n_orders": int(used["order"].nunique()),
        "n_families": int(used["family"].nunique()),
        "n_genera": int(used["genus"].nunique()),
        "mass_min": {
            "species": smallest["species"],
            "mass_g": float(smallest["mass_g"]),
            "kingdom": smallest["kingdom"],
            "class": smallest["class"],
        },
        "mass_max": {
            "species": largest["species"],
            "mass_g": float(largest["mass_g"]),
            "kingdom": largest["kingdom"],
            "class": largest["class"],
        },
        "mass_median_g": float(used["mass_g"].median()),
        "orders_of_magnitude": math.log10(largest["mass_g"] / smallest["mass_g"]),
        "resolution_chain": resolution_chain(args.db_passes),
    }
    write_json(RESULTS / "data_stats.json", stats)

    print("\nKingdoms:", stats["kingdoms"])
    print("Top classes:", stats["top_classes"])
    print("Top single-source contributors:", stats["top_single_source_contributors"])
    print(
        f"Range: {smallest['species']} {smallest['mass_g']:.3g} g .. "
        f"{largest['species']} {largest['mass_g']:.4g} g "
        f"({stats['orders_of_magnitude']:.1f} orders of magnitude)"
    )
    if stats["resolution_chain"]:
        print("Resolution chain:", stats["resolution_chain"])


if __name__ == "__main__":
    main()
