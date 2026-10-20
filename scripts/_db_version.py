"""
Shared helper: resolve the TaxonBodyMass_DB version string.

Extracted from scripts/make_numbers_tex.py so other scripts (export_artifacts,
manifest) can import it without pulling in matplotlib / bibtexparser.

Usage::

    from scripts._db_version import db_version
    ver = db_version(override=None)  # e.g. "v7.0.0"
"""

from __future__ import annotations

import subprocess
from pathlib import Path

# Repo root is the directory that contains this file's parent (scripts/).
_REPO_ROOT = Path(__file__).resolve().parent.parent


def db_version(override: str | None = None, repo_root: Path | None = None) -> str:
    """Return the TaxonBodyMass_DB git tag that describes the current data.

    Looks for a sibling ``TaxonBodyMass_DB/`` checkout next to this repository.
    Returns ``"unknown"`` if the checkout is not found or git fails.

    Parameters
    ----------
    override:
        If given, return this string verbatim (e.g. ``"v6.0.0"``).
    repo_root:
        Root of the TaxonBodyMassML repo; defaults to the directory two levels
        above this file.  The DB is expected at ``repo_root.parent /
        "TaxonBodyMass_DB"``.
    """
    if override:
        return override
    root = repo_root or _REPO_ROOT
    db = root.parent / "TaxonBodyMass_DB"
    try:
        exact = subprocess.run(
            ["git", "-C", str(db), "describe", "--tags", "--exact-match"],
            capture_output=True,
            text=True,
        )
        if exact.returncode == 0:
            return exact.stdout.strip()

        # HEAD is past the last tag. Report the tag when the released CSVs are
        # unchanged since it (commits touching only scripts, docs or the
        # bibliography do not change the data).
        last_tag = subprocess.run(
            ["git", "-C", str(db), "describe", "--tags", "--abbrev=0"],
            capture_output=True,
            text=True,
        ).stdout.strip()
        data_unchanged = (
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(db),
                    "diff",
                    "--quiet",
                    last_tag,
                    "HEAD",
                    "--",
                    "TaxonBodyMass.csv",
                    "TaxonBodyMass_GenusLevel.csv",
                ]
            ).returncode
            == 0
        )
        if last_tag and data_unchanged:
            print(
                f"  TaxonBodyMass_DB HEAD is past {last_tag} but the released " "CSVs are unchanged"
            )
            return last_tag
        near = subprocess.run(
            ["git", "-C", str(db), "describe", "--tags"], capture_output=True, text=True
        )
        tag = near.stdout.strip()
        print(
            f"  WARNING: TaxonBodyMass_DB data changed since {last_tag} ({tag}); "
            "tag a new DB release or pass --db-version"
        )
        return tag
    except FileNotFoundError:
        return "unknown"
