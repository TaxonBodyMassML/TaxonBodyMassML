"""
Merge per-partition verification CSVs from the body mass audit and produce
audit/outlier_report.md in TaxonBodyMass_DB.

Run after the 18-agent Workflow completes and all verified_*.csv files exist.
"""

from pathlib import Path

import pandas as pd

AUDIT_DIR = Path(__file__).resolve().parent.parent.parent / "TaxonBodyMass_DB" / "audit"
FLAGGED_CSV = AUDIT_DIR / "flagged_species.csv"


NCOLS = 12  # number of columns in verified_*.csv (notes is always last)


def _read_verified_csv(filepath):
    """Read a verified_*.csv robustly, absorbing unescaped commas in the notes
    column."""
    rows = []
    header = None
    with open(filepath, newline="", encoding="utf-8") as fh:
        for line in fh:
            parts = line.rstrip("\n").split(",", NCOLS - 1)
            if header is None:
                header = parts
                continue
            if len(parts) < NCOLS:
                parts.extend([""] * (NCOLS - len(parts)))
            rows.append(parts)
    return pd.DataFrame(rows, columns=header)


def load_verifications():
    files = sorted(AUDIT_DIR.glob("verified_*.csv"))
    if not files:
        raise FileNotFoundError(f"No verified_*.csv files found in {AUDIT_DIR}")
    dfs = []
    for f in files:
        df = _read_verified_csv(f)
        df["partition"] = f.stem.replace("verified_", "")
        dfs.append(df)
    merged = pd.concat(dfs, ignore_index=True)
    # Deduplicate: if a taxon appears in multiple partitions (e.g. adversarial overlap),
    # keep the one with the most specific category (prefer non-NO_LIT_FOUND).
    priority = {
        "REMOVE": 0,
        "ERRONEOUS_MASS": 1,
        "ERRONEOUS_TAXONOMY": 2,
        "BOTH_ERRONEOUS": 3,
        "PLAUSIBLE": 4,
        "CONFIRMED": 5,
        "NO_LIT_FOUND": 6,
    }
    merged["_pri"] = merged["category"].map(priority).fillna(9)
    merged = (
        merged.sort_values(["taxon", "_pri"])
        .drop_duplicates(subset=["taxon"], keep="first")
        .drop(columns=["_pri"])
    )
    return merged


def source_audit(verifications, flagged):
    """Per-source counts of erroneous vs. total flagged records."""
    erroneous_cats = {"ERRONEOUS_MASS", "BOTH_ERRONEOUS", "REMOVE"}
    err = verifications[verifications["category"].isin(erroneous_cats)].copy()
    if err.empty:
        return pd.DataFrame()

    rows = []
    for _, rec in err.iterrows():
        taxon = rec["taxon"]
        # look up source_mass in flagged csv
        match = flagged[flagged["taxon"] == taxon]
        if match.empty:
            continue
        sources = str(match.iloc[0]["source_mass"]).split("-")
        for src in sources:
            rows.append(
                {
                    "source": src.strip(),
                    "taxon": taxon,
                    "category": rec["category"],
                }
            )
    if not rows:
        return pd.DataFrame()
    src_df = pd.DataFrame(rows)
    summary = (
        src_df.groupby("source")
        .agg(
            n_erroneous=("taxon", "nunique"),
            erroneous_taxa=("taxon", lambda x: "; ".join(sorted(set(x)))),
        )
        .sort_values("n_erroneous", ascending=False)
        .reset_index()
    )
    return summary[summary["n_erroneous"] >= 2]


def write_report(verifications, flagged, source_summary):
    cat_counts = verifications["category"].value_counts()
    action_counts = verifications["recommended_action"].value_counts()

    erroneous = verifications[
        verifications["category"].isin(
            {"ERRONEOUS_MASS", "ERRONEOUS_TAXONOMY", "BOTH_ERRONEOUS", "REMOVE"}
        )
    ].sort_values("category")

    report_lines = [
        "# Body Mass Outlier Audit Report",
        "",
        "**Dataset:** TaxonBodyMass_curated.csv  |  **Records scored:** 38,300",
        "**Flagged:** 2,082  (CRITICAL: 372, SUSPICIOUS: 1,703, TUKEY_ONLY: 7)",
        f"**Records verified in this audit:** {len(verifications)}",
        "",
        "## Summary by category",
        "",
        "| Category | Count |",
        "|----------|-------|",
    ]
    for cat, cnt in cat_counts.items():
        report_lines.append(f"| {cat} | {cnt} |")

    report_lines += [
        "",
        "## Summary by recommended action",
        "",
        "| Action | Count |",
        "|--------|-------|",
    ]
    for act, cnt in action_counts.items():
        report_lines.append(f"| {act} | {cnt} |")

    report_lines += [
        "",
        "## Records requiring correction or removal",
        "",
        "| Taxon | mass_g (dataset) | Category | Recommended action | Notes |",
        "|-------|-----------------|----------|-------------------|-------|",
    ]
    for _, row in erroneous.iterrows():
        taxon = row.get("taxon", "")
        mass = row.get("mass_g_dataset", "")
        cat = row.get("category", "")
        action = row.get("recommended_action", "")
        notes = str(row.get("notes", "")).replace("|", "/")[:120]
        try:
            mass_fmt = f"{float(mass):.3g}"
        except (ValueError, TypeError):
            mass_fmt = str(mass)
        report_lines.append(f"| {taxon} | {mass_fmt} | {cat} | {action} | {notes} |")

    if not source_summary.empty:
        report_lines += [
            "",
            "## Sources with systematic errors (≥2 erroneous records)",
            "",
            "| Source | n_erroneous_records | Taxa |",
            "|--------|--------------------|----|",
        ]
        for _, row in source_summary.iterrows():
            taxa_abbrev = row["erroneous_taxa"][:100]
            src_line = f"| {row['source']} | {row['n_erroneous']} | {taxa_abbrev} |"
            report_lines.append(src_line)

    # TUKEY_ONLY section
    tukey = flagged[flagged["severity"] == "TUKEY_ONLY"]
    if not tukey.empty:
        report_lines += [
            "",
            "## TUKEY_ONLY records (class-level outlier, model residual < 1.0)"
            " — for user review",
            "",
            "| Taxon | mass_g | taxon_class | abs_residual |",
            "|-------|--------|------------|-------------|",
        ]
        for _, row in tukey.iterrows():
            report_lines.append(
                f"| {row['taxon']} | {row['mass_g']:.3g}"
                f" | {row['taxon_class']} | {row['abs_residual']:.3f} |"
            )

    report_lines += ["", "---", "_Generated by scripts/audit_synthesis.py_", ""]
    report_path = AUDIT_DIR / "outlier_report.md"
    report_path.write_text("\n".join(report_lines))
    print(f"Report written to {report_path}")


def main():
    print("Loading verification results...")
    verifications = load_verifications()
    print(f"  {len(verifications)} unique taxa verified")
    print(verifications["category"].value_counts().to_string())

    print("\nLoading flagged_species.csv for source audit...")
    flagged = pd.read_csv(FLAGGED_CSV)

    print("\nRunning source-level audit...")
    source_summary = source_audit(verifications, flagged)
    if not source_summary.empty:
        print(f"  {len(source_summary)} sources with ≥2 erroneous records:")
        print(source_summary[["source", "n_erroneous"]].to_string())

    print("\nWriting outlier_report.md...")
    write_report(verifications, flagged, source_summary)

    # Also save the merged verifications
    out_path = AUDIT_DIR / "verifications_merged.csv"
    verifications.to_csv(out_path, index=False)
    print(f"Merged verifications written to {out_path}")


if __name__ == "__main__":
    main()
