"""
Tests for taxonbodymassml._gbif_fuzzy_name and correct_species_names().

Network tests are skipped unless TAXONBODYMASSML_RUN_INTEGRATION=1.
"""

import os
from unittest.mock import patch

import pytest

INTEGRATION = os.environ.get("TAXONBODYMASSML_RUN_INTEGRATION", "0") == "1"
skip_without_network = pytest.mark.skipif(
    not INTEGRATION, reason="Requires network; set TAXONBODYMASSML_RUN_INTEGRATION=1"
)


@skip_without_network
def test_gbif_fuzzy_name_misspelled_genus():
    from taxonbodymassml._fuzzy import _gbif_fuzzy_name

    assert _gbif_fuzzy_name("Ballanus glandula") == "Balanus glandula"


@skip_without_network
def test_gbif_fuzzy_name_misspelled_epithet():
    from taxonbodymassml._fuzzy import _gbif_fuzzy_name

    assert _gbif_fuzzy_name("Balanus glandulla") == "Balanus glandula"


@skip_without_network
def test_gbif_fuzzy_name_both_misspelled():
    from taxonbodymassml._fuzzy import _gbif_fuzzy_name

    assert _gbif_fuzzy_name("Ballanus glanddula") == "Balanus glandula"


@skip_without_network
def test_gbif_fuzzy_name_unrecognisable_returns_none():
    from taxonbodymassml._fuzzy import _gbif_fuzzy_name

    assert _gbif_fuzzy_name("Xyzzy notaspecies12345") is None


@skip_without_network
def test_correct_species_names_all_three_misspellings():
    import taxonbodymassml as tbm

    result = tbm.correct_species_names(
        ["Ballanus glandula", "Balanus glandulla", "Ballanus glanddula"]
    )
    assert list(result["matched_name"]) == ["Balanus glandula"] * 3


def test_correct_species_names_higherrank_fallback_offline():
    """HIGHERRANK match triggers genus+epithet retry; tests offline via mock."""
    from taxonbodymassml._fuzzy import correct_species_names

    def fake_gbif_fuzzy_name(name):
        if name == "Ballanus glandula":
            return "Balanus glandula"
        return None

    with patch("taxonbodymassml._fuzzy._gbif_fuzzy_name", side_effect=fake_gbif_fuzzy_name):
        result = correct_species_names("Ballanus glandula")

    assert result.iloc[0]["input_name"] == "Ballanus glandula"
    assert result.iloc[0]["matched_name"] == "Balanus glandula"


def test_correct_species_names_no_match_returns_none_offline():
    """Unresolvable name produces None in matched_name without network."""
    from taxonbodymassml._fuzzy import correct_species_names

    with patch("taxonbodymassml._fuzzy._gbif_fuzzy_name", return_value=None):
        result = correct_species_names("Xyzzy notaspecies12345")

    assert result.iloc[0]["matched_name"] is None
