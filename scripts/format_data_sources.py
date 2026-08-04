"""
Generate a formatted LaTeX bibliography for S4 (training data sources).

Reads data/Citations_BodyMass.bib and writes a standalone
\\begin{thebibliography}...\\end{thebibliography} block to
predictive_models/results/tab_data_sources.tex.

Entries are sorted alphabetically by first author surname and formatted
in apalike style: Author(s). (Year). Title. *Journal*, vol(num):pages.

Run from repo root:
  predictive_models/.venv/bin/python scripts/format_data_sources.py
"""

from pathlib import Path

import bibtexparser
from bibtexparser.bwriter import BibTexWriter
from bibtexparser.bparser import BibTexParser

REPO = Path(__file__).resolve().parents[1]
BIB_PATH = REPO / "data" / "Citations_BodyMass.bib"
RESULTS = REPO / "predictive_models" / "results"
RESULTS.mkdir(parents=True, exist_ok=True)
OUT_TEX = RESULTS / "tab_data_sources.tex"


def _escape(text: str) -> str:
    """Minimal cleanup: strip surrounding braces added by bibtexparser."""
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        text = text[1:-1]
    return text


def _format_authors(raw: str) -> str:
    """Format 'Last, First and Last, First ...' → 'Last, F., Last, F., ...'"""
    raw = _escape(raw)
    people = [a.strip() for a in raw.split(" and ")]
    formatted = []
    for person in people:
        if "," in person:
            parts = [p.strip() for p in person.split(",", 1)]
            last = parts[0]
            first = parts[1] if len(parts) > 1 else ""
            initials = "".join(w[0] + "." for w in first.split() if w and w[0].isalpha())
            formatted.append(f"{last}, {initials}" if initials else last)
        else:
            formatted.append(person)
    if len(formatted) == 1:
        return formatted[0]
    if len(formatted) == 2:
        return f"{formatted[0]} and {formatted[1]}"
    return ", ".join(formatted[:-1]) + ", and " + formatted[-1]


def _format_entry(e: dict) -> str:
    """Format one bib entry as an \\item line."""
    etype = e.get("ENTRYTYPE", "").lower()
    key = e.get("ID", "?")

    author = _format_authors(e.get("author", e.get("editor", "Anonymous")))
    year = _escape(e.get("year", "n.d."))
    title = _escape(e.get("title", ""))

    # natbib in author-year mode requires an optional [Author, Year] label on
    # \bibitem; without it natbib switches to numeric mode and raises an error.
    first_surname = _escape(e.get("author", e.get("editor", "Anonymous"))).split(",")[0].strip()
    natbib_label = f"{first_surname}, {year}"

    parts = [f"{author} ({year}). {title}."]

    if etype == "article":
        journal = _escape(e.get("journal", ""))
        vol = _escape(e.get("volume", ""))
        num = _escape(e.get("number", ""))
        pages = _escape(e.get("pages", ""))
        if journal:
            venue = f"\\textit{{{journal}}}"
            if vol and num:
                venue += f", {vol}({num})"
            elif vol:
                venue += f", {vol}"
            if pages:
                venue += f":{pages}"
            parts.append(venue + ".")
    elif etype == "book":
        publisher = _escape(e.get("publisher", ""))
        address = _escape(e.get("address", ""))
        edition = _escape(e.get("edition", ""))
        loc = ", ".join(filter(None, [address, publisher]))
        if edition:
            loc = edition + " ed. " + loc if loc else edition + " ed."
        if loc:
            parts.append(loc + ".")
    elif etype in ("inbook", "incollection", "inproceedings"):
        booktitle = _escape(e.get("booktitle", ""))
        publisher = _escape(e.get("publisher", ""))
        pages = _escape(e.get("pages", ""))
        if booktitle:
            chunk = f"In \\textit{{{booktitle}}}"
            if pages:
                chunk += f", pp. {pages}"
            if publisher:
                chunk += f". {publisher}"
            parts.append(chunk + ".")
    else:
        note = _escape(e.get("note", e.get("howpublished", "")))
        if note:
            parts.append(note + ".")

    doi = _escape(e.get("doi", ""))
    url = _escape(e.get("url", ""))
    if doi:
        parts.append(f"\\url{{https://doi.org/{doi}}}")
    elif url:
        parts.append(f"\\url{{{url}}}")

    body = " ".join(parts)
    return f"\\bibitem[{natbib_label}]{{{key}}}\n{body}"


def main():
    parser = BibTexParser(common_strings=True)
    parser.ignore_nonstandard_types = False
    with open(BIB_PATH, encoding="utf-8") as f:
        db = bibtexparser.load(f, parser)

    entries = sorted(
        db.entries, key=lambda e: _escape(e.get("author", "zzz")).split(",")[0].lower()
    )

    lines = [r"\begin{thebibliography}{999}"]
    for e in entries:
        lines.append(_format_entry(e))
    lines.append(r"\end{thebibliography}")
    lines.append("")

    OUT_TEX.write_text("\n\n".join(lines))
    print(f"Wrote {len(entries)} entries to {OUT_TEX}")


if __name__ == "__main__":
    main()
