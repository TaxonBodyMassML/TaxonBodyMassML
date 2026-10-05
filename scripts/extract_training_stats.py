"""
Training-data statistics for the manuscript.

Reads data/TaxonBodyMass.csv (the copy of TaxonBodyMass_DB/TaxonBodyMass.csv
fetched by scripts/fetch_source_data.py; one row per species) and, when present,
data/TaxonBodyMass_Provenance.csv.gz (the species x source x reference table of
TaxonBodyMass_DB issue #1; the primary-source coverage numbers) and writes

  predictive_models/results/tab_kingdom.tex   species and mass range per kingdom
  predictive_models/results/tab_class.tex     the same for the 20 largest classes
  predictive_models/results/data_stats.json   every count quoted in the manuscript
                                              (consumed by make_numbers_tex.py)

The resolution chain (names submitted -> resolved -> autotrophs removed ->
species before the range filter) is NOT derived here: the enrichment pass files
in TaxonBodyMass_DB/sources/passes hold only the names enriched on the last
(incremental) run.  TaxonBodyMass_DB/R/RunMe.r writes those counts directly to
ms/numbers_db.tex.

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
    RESULTS,
    TAXONOMY_COLS,
    fmt_int,
    write_json,
    write_tex,
)


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


def sources_contributing(labels: set[str]) -> int | None:
    """Number of bibliography entries with at least one CiteID present in the
    ``source_mass`` labels of the released CSV.  The bibliography lists every
    source consulted; sources whose records were all removed downstream (range
    filter, unresolved names, sheet overrides) contribute no species."""
    path = DATA / "TaxonBodyMass_CitationCiteIDs.csv"
    if not path.exists():
        print(f"  (no {path}; sources_contributing skipped)")
        return None
    cite = pd.read_csv(path)
    keys = cite.groupby("Bibcite")["CiteID"].apply(set)
    return int(sum(bool(ids & labels) for ids in keys))


# match_status values of a verified primary reference (TaxonBodyMass_DB issue #1).
ACCEPTED_STATUS = {"certain", "approved", "nodoi_approved"}


def provenance_stats() -> dict:
    """Primary-source coverage from data/TaxonBodyMass_Provenance.csv.gz.

    One row per species x source label x reference, weighted by ``n_records``
    (the records behind the row; a record citing two references counts twice).

    * ``n_primary_refs``: distinct verified primary references (``primary_bibcite``
      of rows with an accepted ``match_status``; conversion-factor references
      are not primary measurements and are excluded).
    * ``pct_records_hop_resolved``: of the record links whose source cites a
      reference (``hop >= 1``), the percentage resolved to a verified primary
      reference.  This is the per-source ``pct_resolved`` of
      TaxonBodyMass_DB/reports/warnings_citations.md pooled over sources.
    * ``pct_records_primary``: of all record links except conversion factors,
      the percentage that end at a primary measurement: the source measured
      the animal itself (``measured_in_source``) or cites a verified reference.
    """
    path = DATA / "TaxonBodyMass_Provenance.csv.gz"
    if not path.exists():
        print(f"  (no {path}; provenance stats skipped)")
        return {
            "n_primary_refs": None,
            "pct_records_hop_resolved": None,
            "pct_records_primary": None,
        }
    prov = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=["NA"])
    hop = pd.to_numeric(prov["hop"], errors="coerce").fillna(0).astype(int)
    n = pd.to_numeric(prov["n_records"], errors="coerce").fillna(0).astype(int)
    accepted = prov["match_status"].isin(ACCEPTED_STATUS)
    cites = hop >= 1
    not_conv = prov["provenance_type"] != "conversion_factor"
    primary = not_conv & ((prov["provenance_type"] == "measured_in_source") | accepted)
    return {
        "n_primary_refs": int(prov.loc[accepted, "primary_bibcite"].nunique()),
        "pct_records_hop_resolved": float(
            100.0 * n[cites & accepted].sum() / max(n[cites].sum(), 1)
        ),
        "pct_records_primary": float(100.0 * n[primary].sum() / max(n[not_conv].sum(), 1)),
        "n_provenance_rows": int(len(prov)),
        "n_provenance_species": int(prov["species"].nunique()),
    }


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()

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
        # n_independent (TaxonBodyMass_DB issue #5): values left per species after
        # collapsing copies of the same datum across sources; n_source_records is
        # duplicate-inflated.
        "n_independent_values": (
            int(raw["n_independent"].sum()) if "n_independent" in raw.columns else None
        ),
        **provenance_stats(),
        "n_sources_distinct": len(src_counter),
        "n_sources_contributing": sources_contributing(set(src_counter)),
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
    print(
        f"Sources: {stats['n_sources_distinct']} distinct labels; "
        f"{stats['n_sources_contributing']} bibliography entries contributing"
    )
    if stats["n_primary_refs"] is not None:
        print(
            f"Primary sources: {stats['n_primary_refs']} verified references; "
            f"{stats['pct_records_hop_resolved']:.2f}% of citing record links resolved; "
            f"{stats['pct_records_primary']:.1f}% of record links end at a primary measurement"
        )


if __name__ == "__main__":
    main()
