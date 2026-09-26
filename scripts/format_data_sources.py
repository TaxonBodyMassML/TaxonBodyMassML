"""
Generate a formatted LaTeX bibliography for the training-data-sources supplement.

Reads data/Citations_BodyMass.bib and writes a standalone
\\begin{thebibliography}...\\end{thebibliography} block to
predictive_models/results/tab_data_sources.tex.  The number of entries is the
manuscript's "number of sources" (make_numbers_tex.py counts the same file).

Entries are sorted alphabetically by first author surname and formatted
in apalike style: Author(s). (Year). Title. *Journal*, vol(num):pages.

Run from repo root:
  predictive_models/.venv/bin/python scripts/format_data_sources.py
"""

import re
from pathlib import Path

import bibtexparser
from bibtexparser.bparser import BibTexParser

REPO = Path(__file__).resolve().parents[1]
BIB_PATH = REPO / "data" / "Citations_BodyMass.bib"
RESULTS = REPO / "predictive_models" / "results"
RESULTS.mkdir(parents=True, exist_ok=True)
OUT_TEX = RESULTS / "tab_data_sources.tex"


def _escape(text: str) -> str:
    """Minimal cleanup: strip surrounding braces added by bibtexparser and
    escape bare underscores (e.g. dataset names such as VertNet_Aves_Sept2016),
    which would otherwise break the LaTeX build."""
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        text = text[1:-1]
    text = re.sub(r"(?<!\\)_", r"\\_", text)
    return text


def _strip_enclosing_braces(text: str) -> str:
    """Remove one pair of braces only if they enclose the whole string
    (``{Sarmiento-Lezcano}`` yes; ``{\\v S}egvi{\\'c}`` no)."""
    if not (text.startswith("{") and text.endswith("}")):
        return text
    depth = 0
    for i, ch in enumerate(text):
        depth += (ch == "{") - (ch == "}")
        if depth == 0 and i < len(text) - 1:
            return text
    return text[1:-1]


def _split_name(person: str) -> tuple[str, str]:
    """Return ``(surname, initials)`` for one author.

    Handles both BibTeX name forms: ``Last, First Middle`` and ``First Middle
    Last``.  In the latter, a trailing ``{...}`` group or the final word is the
    surname, so ``Airam Nauzet {Sarmiento-Lezcano}`` -> ``Sarmiento-Lezcano, A.N.``.
    """
    person = person.strip()
    if "," in person:
        last, first = (p.strip() for p in person.split(",", 1))
    else:
        m = re.match(r"^(.*?)\s*(\{[^{}]*\})$", person)
        if m:
            first, last = m.group(1), m.group(2)
        else:
            words = person.split()
            first, last = " ".join(words[:-1]), (words[-1] if words else person)
    last = _strip_enclosing_braces(last.strip())
    initials = "".join(w[0] + "." for w in first.split() if w and w[0].isalpha())
    return last, initials


def _first_surname(raw: str) -> str:
    return _split_name(_escape(raw).split(" and ")[0])[0]


def _format_authors(raw: str) -> str:
    """Format any BibTeX author list as 'Last, F., Last, F., and Last, F.'"""
    people = [a.strip() for a in _escape(raw).split(" and ") if a.strip()]
    formatted = []
    for person in people:
        if person.lower() == "others":
            formatted.append("others")
            continue
        last, initials = _split_name(person)
        formatted.append(f"{last}, {initials}" if initials else last)
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
    first_surname = _first_surname(e.get("author", e.get("editor", "Anonymous")))
    natbib_label = f"{first_surname}, {year}"

    parts = [f"{author} ({year}). {title.rstrip('.')}."]

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
        note = _escape(e.get("note", e.get("howpublished", ""))).rstrip(".")
        if note:
            parts.append(note + ".")

    # Some entries store a full resolver URL in the doi field.
    doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)\s*", "", _escape(e.get("doi", "")), flags=re.I)
    url = _escape(e.get("url", ""))
    if doi:
        parts.append(f"\\url{{https://doi.org/{doi}}}")
    elif url:
        parts.append(f"\\url{{{url}}}")

    body = " ".join(parts)
    return f"\\bibitem[{natbib_label}]{{{key}-src}}\n{body}"  # -src avoids key clashes


def main():
    parser = BibTexParser(common_strings=True)
    parser.ignore_nonstandard_types = False
    with open(BIB_PATH, encoding="utf-8") as f:
        db = bibtexparser.load(f, parser)

    entries = sorted(db.entries, key=lambda e: _first_surname(e.get("author", "zzz")).lower())

    lines = [r"\begin{thebibliography}{999}"]
    for e in entries:
        lines.append(_format_entry(e))
    lines.append(r"\end{thebibliography}")
    lines.append("")

    OUT_TEX.write_text("\n\n".join(lines))
    print(f"Wrote {len(entries)} entries to {OUT_TEX}")


if __name__ == "__main__":
    main()
