"""
Merge verified_susp_*.csv files plus SUSPICIOUS records from the 4 early
verified_*.csv partitions, and produce audit/outlier_report_2.md.

Run after the SUSPICIOUS verification workflow completes.
"""

from pathlib import Path

import pandas as pd

AUDIT_DIR = Path(__file__).resolve().parent.parent.parent / "TaxonBodyMass_DB" / "audit"
FLAGGED_CSV = AUDIT_DIR / "flagged_species.csv"

NCOLS = 12


def _read_csv(filepath):
    """Read a verified CSV robustly, absorbing unescaped commas in the notes column."""
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
    if header is None:
        return pd.DataFrame()
    return pd.DataFrame(rows, columns=header)


def load_suspicious_verifications():
    # 1. New SUSPICIOUS-specific files — may live in audit/ or audit/verified/
    VERIFIED_DIR = AUDIT_DIR / "verified"
    new_files = sorted(AUDIT_DIR.glob("verified_susp_*.csv")) + sorted(
        VERIFIED_DIR.glob("verified_susp_*.csv")
    )
    # deduplicate by stem in case files exist in both locations
    seen_stems = set()
    deduped = []
    for f in new_files:
        if f.stem not in seen_stems:
            seen_stems.add(f.stem)
            deduped.append(f)
    new_files = sorted(deduped, key=lambda f: f.stem)
    if not new_files:
        raise FileNotFoundError(
            f"No verified_susp_*.csv files found in {AUDIT_DIR} or {VERIFIED_DIR}"
        )

    dfs = []
    for f in new_files:
        df = _read_csv(f)
        if not df.empty:
            df["partition"] = f.stem
            dfs.append(df)

    # 2. SUSPICIOUS records from the 4 early partitions (which covered all severities)
    early_files = sorted(AUDIT_DIR.glob("verified_*.csv")) + sorted(
        VERIFIED_DIR.glob("verified_*.csv")
    )
    susp_prefix = "verified_susp_"
    early_files = [
        f
        for f in early_files
        if not f.stem.startswith(susp_prefix) and "verifications_merged" not in f.stem
    ]
    seen_early = set()
    deduped_early = []
    for f in early_files:
        if f.stem not in seen_early:
            seen_early.add(f.stem)
            deduped_early.append(f)
    early_files = sorted(deduped_early, key=lambda f: f.stem)
    for f in early_files:
        df = _read_csv(f)
        if not df.empty and "severity" in df.columns:
            susp_rows = df[df["severity"] == "SUSPICIOUS"].copy()
            if not susp_rows.empty:
                susp_rows["partition"] = f.stem + "_early"
                dfs.append(susp_rows)

    if not dfs:
        raise ValueError("No SUSPICIOUS verification data found.")

    merged = pd.concat(dfs, ignore_index=True)

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
    erroneous_cats = {"ERRONEOUS_MASS", "BOTH_ERRONEOUS", "REMOVE"}
    err = verifications[verifications["category"].isin(erroneous_cats)].copy()
    if err.empty:
        return pd.DataFrame()
    rows = []
    for _, rec in err.iterrows():
        taxon = rec["taxon"]
        match = flagged[flagged["taxon"] == taxon]
        if match.empty:
            continue
        for src in str(match.iloc[0]["source_mass"]).split("-"):
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


def write_report(verifications, source_summary):
    cat_counts = verifications["category"].value_counts()
    action_counts = verifications["recommended_action"].value_counts()

    erroneous = verifications[
        verifications["category"].isin(
            {"ERRONEOUS_MASS", "ERRONEOUS_TAXONOMY", "BOTH_ERRONEOUS", "REMOVE"}
        )
    ].sort_values("category")

    report_lines = [
        "# Body Mass Outlier Audit Report — SUSPICIOUS Tier",
        "",
        "**Dataset:** TaxonBodyMass_curated.csv  |  **Records scored:** 38,300",
        "**SUSPICIOUS flagged (abs_residual 1.0–2.0):** 1,703",
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
            "## Sources with systematic errors (SUSPICIOUS tier, ≥2 erroneous records)",
            "",
            "| Source | n_erroneous_records | Taxa |",
            "|--------|--------------------|----|",
        ]
        for _, row in source_summary.iterrows():
            taxa_abbrev = row["erroneous_taxa"][:100]
            src_line = f"| {row['source']} | {row['n_erroneous']} | {taxa_abbrev} |"
            report_lines.append(src_line)

    report_lines += [
        "",
        "---",
        "_Generated by scripts/audit_synthesis_suspicious.py_",
        "",
    ]
    report_path = AUDIT_DIR / "outlier_report_2.md"
    report_path.write_text("\n".join(report_lines))
    print(f"Report written to {report_path}")


def main():
    print("Loading SUSPICIOUS verification results...")
    verifications = load_suspicious_verifications()
    print(f"  {len(verifications)} unique taxa verified")
    print(verifications["category"].value_counts().to_string())

    print("\nLoading flagged_species.csv for source audit...")
    flagged = pd.read_csv(FLAGGED_CSV)

    print("\nRunning source-level audit...")
    source_summary = source_audit(verifications, flagged)
    if not source_summary.empty:
        print(f"  {len(source_summary)} sources with ≥2 erroneous records:")
        print(source_summary[["source", "n_erroneous"]].to_string())

    print("\nWriting outlier_report_2.md...")
    write_report(verifications, source_summary)

    out_path = AUDIT_DIR / "verifications_suspicious_merged.csv"
    verifications.to_csv(out_path, index=False)
    print(f"Merged SUSPICIOUS verifications written to {out_path}")


if __name__ == "__main__":
    main()
