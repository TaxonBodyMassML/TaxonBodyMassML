from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_DIR = REPO_ROOT.parent / "TaxonBodyMass_DB" / "audit"
CURATED = REPO_ROOT / "data" / "passes" / "TaxonBodyMass_curated.csv"
MODEL = REPO_ROOT / "artifacts" / "model.ubj"

FEATURES = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]

df = pd.read_csv(CURATED)
df = df.dropna(subset=FEATURES + ["mass_g"])
df = df[df["mass_g"] > 0].copy()
df["log10_mass"] = np.log10(df["mass_g"])
print(f"Records after filter: {len(df)}", flush=True)

model = xgb.XGBRegressor()
model.load_model(str(MODEL))
X = df[FEATURES].copy()
for col in FEATURES:
    X[col] = X[col].astype("category")
df["log10_pred"] = model.predict(X)
df["residual"] = df["log10_mass"] - df["log10_pred"]
df["abs_residual"] = df["residual"].abs()


# Rename 'class' to 'taxon_class' to avoid Python keyword conflicts
df = df.rename(columns={"class": "taxon_class"})

tukey_flags = []
for cls, grp in df.groupby("taxon_class"):
    q1, q3 = grp["log10_mass"].quantile([0.25, 0.75])
    iqr = q3 - q1
    outer = 3 * iqr
    flag = (grp["log10_mass"] < q1 - outer) | (grp["log10_mass"] > q3 + outer)
    tukey_flags.append(flag)
df["class_outlier"] = pd.concat(tukey_flags).reindex(df.index)

df["severity"] = "OK"
df.loc[df["abs_residual"] > 1.0, "severity"] = "SUSPICIOUS"
df.loc[df["abs_residual"] > 2.0, "severity"] = "CRITICAL"
df.loc[df["class_outlier"] & (df["severity"] == "OK"), "severity"] = "TUKEY_ONLY"

AUDIT_DIR.mkdir(parents=True, exist_ok=True)
df.to_csv(AUDIT_DIR / "residuals_full.csv", index=False)
flagged = df[df["severity"] != "OK"].sort_values("abs_residual", ascending=False)
flagged.to_csv(AUDIT_DIR / "flagged_species.csv", index=False)

print(f"\nTotal records scored: {len(df)}")
print(f"Flagged records: {len(flagged)}")
print("\nSeverity counts:")
print(flagged["severity"].value_counts().to_string())
print("\nTop 30 by abs_residual:")
cols = [
    "taxon",
    "mass_g",
    "log10_mass",
    "log10_pred",
    "residual",
    "severity",
    "taxon_class",
    "source_mass",
]
print(flagged[cols].head(30).to_string())
print(f"\nFiles written to {AUDIT_DIR}")
