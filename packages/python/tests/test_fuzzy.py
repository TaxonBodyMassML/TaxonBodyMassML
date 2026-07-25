"""
Tests for taxonbodymassml._gbif_fuzzy_name and correct_species_names().

Network tests are skipped unless TAXONBODYMASSML_RUN_INTEGRATION=1.
"""

import os

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
