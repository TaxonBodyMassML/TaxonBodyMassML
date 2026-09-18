"""
Cross-check ms/manuscript.tex against the generated numbers.tex macros.

Reports
  * macros defined in numbers.tex but never used (information),
  * macro-like control words used in the manuscript that numbers.tex does not
    define (error),
  * author margin notes (\\MN{...}, \\ToDo{...}) that must be removed before
    submission (error with --strict),
  * hard-coded numerals in the prose that might belong in numbers.tex
    (information; years, the ZIP code, ORCID, nominal coverage levels and
    listings/comments are ignored).

Exit status is non-zero on errors.

Run from repo root:
  predictive_models/.venv/bin/python scripts/check_manuscript_numbers.py [--strict]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANUSCRIPT = REPO / "ms" / "manuscript.tex"
NUMBERS = [REPO / "ms" / "numbers.tex", REPO / "predictive_models" / "results" / "numbers.tex"]

# Control words starting with these prefixes are treated as numbers macros.
MACRO_PREFIXES = (
    "ee",
    "xgb",
    "nDb",
    "nRecords",
    "nDropped",
    "nSource",
    "nSources",
    "nLookup",
    "nKingdoms",
    "nAnimalia",
    "nChromista",
    "nBacteria",
    "nProtozoa",
    "nArchaea",
    "nViridiplantae",
    "pct",
    "nClasses",
    "nOrders",
    "nFamilies",
    "nGenera",
    "topClass",
    "nTopClass",
    "srcLabel",
    "nUniqueSrc",
    "mass",
    "ordersOf",
    "nNames",
    "nSpecies",
    "nTrain",
    "nTest",
    "nCalib",
    "splitSeed",
    "vocab",
    "embDim",
    "stageOne",
    "nTrials",
    "nFolds",
    "tuneSeed",
    "pkgVersion",
    "artifactVersion",
    "hfTag",
    "dbVersion",
    "xgboost",
    "torch",
    "optuna",
    "sklearn",
    "pythonVersion",
    "nArtifacts",
    "artifactsTotal",
    "modelUbj",
    "modelEe",
    "embeddingsMB",
    "lookupMB",
    "numbersGenerated",
)
ALLOW_NUMERALS = re.compile(r"^(1[89]\d\d|20\d\d|97331|0\.(80|90|95|75)|0000-0002-7881-4253)$")


def strip_comments_and_listings(text: str) -> str:
    out, in_listing = [], False
    for line in text.splitlines():
        if r"\begin{lstlisting}" in line:
            in_listing = True
        if in_listing:
            if r"\end{lstlisting}" in line:
                in_listing = False
            continue
        code = re.sub(r"(?<!\\)%.*$", "", line)
        out.append(code)
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="fail on margin notes too")
    args = ap.parse_args()

    numbers = next((p for p in NUMBERS if p.exists()), None)
    if numbers is None:
        print("numbers.tex not found; run scripts/make_numbers_tex.py first")
        return 2
    defined = set(re.findall(r"\\newcommand\{\\([A-Za-z]+)\}", numbers.read_text()))
    tex = MANUSCRIPT.read_text()
    body = strip_comments_and_listings(tex)

    used = set(re.findall(r"\\([A-Za-z]+)(?![A-Za-z])", body))
    macro_like = {u for u in used if u.startswith(MACRO_PREFIXES)}
    undefined = sorted(macro_like - defined)
    unused = sorted(defined - used)
    notes = re.findall(r"\\(MN|ToDo)\{", body)
    placeholders = re.findall(r"<<OUTPUT-[A-Za-z0-9]+>>", tex)  # example listings not yet pasted

    numerals = []
    for i, line in enumerate(body.splitlines(), 1):
        for m in re.finditer(
            r"(?<![\w\\{])(\d{1,3}(?:,\d{3})+|\d+\.\d{2,}|\d+\s*\\times\s*10)", line
        ):
            token = m.group(1)
            if not ALLOW_NUMERALS.match(token.replace(",", "")):
                numerals.append((i, token, line.strip()[:90]))

    print(f"numbers.tex: {len(defined)} macros defined ({numbers.relative_to(REPO)})")
    print(
        f"manuscript: {len(macro_like & defined)} macros used, {len(unused)} unused, {len(undefined)} undefined"  # noqa: E501
    )
    if unused:
        print("  unused: " + ", ".join(unused))
    status = 0
    if undefined:
        status = 1
        print("  UNDEFINED (fix these): " + ", ".join(undefined))
    if placeholders:
        status = 1
        print(f"  example output placeholders still present: {sorted(set(placeholders))}")
    if notes:
        print(f"  margin notes remaining: {len(notes)} (\\MN/\\ToDo)")
        if args.strict:
            status = 1
    if numerals:
        print(f"  hard-coded numerals to review ({len(numerals)}):")
        for i, tok, ctx in numerals[:60]:
            print(f"    L{i}: {tok:>12s}  | {ctx}")
    return status


if __name__ == "__main__":
    sys.exit(main())
