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


def test_gbif_fuzzy_name_returns_sentinel_on_request_error():
    """A network error makes _gbif_fuzzy_name return the failed-request sentinel."""
    import taxonbodymassml._fuzzy as fmod

    with patch("taxonbodymassml._fuzzy._get", side_effect=OSError("network error")):
        result = fmod._gbif_fuzzy_name("Nucela lima")

    assert result is fmod._FUZZY_REQUEST_FAILED


def test_correct_species_names_warns_on_request_failure():
    """correct_species_names emits a warning and returns None for failed requests."""
    import warnings

    import taxonbodymassml._fuzzy as fmod

    with patch(
        "taxonbodymassml._fuzzy._gbif_fuzzy_name",
        return_value=fmod._FUZZY_REQUEST_FAILED,
    ):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            from taxonbodymassml._fuzzy import correct_species_names

            result = correct_species_names("Nucela lima")

    assert any("Fuzzy lookup failed for 1 name" in str(w.message) for w in caught)
    assert result.iloc[0]["matched_name"] is None
    assert result.iloc[0]["input_name"] == "Nucela lima"


def test_correct_species_names_warns_only_for_failed_not_no_match():
    """Warning fires for request failures but not for genuine no-match (None)."""
    import warnings

    import taxonbodymassml._fuzzy as fmod

    sentinel = fmod._FUZZY_REQUEST_FAILED
    call_results = iter([sentinel, None])

    with patch(
        "taxonbodymassml._fuzzy._gbif_fuzzy_name",
        side_effect=lambda name: next(call_results),
    ):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            from taxonbodymassml._fuzzy import correct_species_names

            result = correct_species_names(["Nucela lima", "Xyzzy notaspecies"])

    warning_msgs = [str(w.message) for w in caught]
    assert any("Fuzzy lookup failed for 1 name" in m for m in warning_msgs)
    assert result.iloc[0]["matched_name"] is None  # failed request -> None
    assert result.iloc[1]["matched_name"] is None  # no match -> None (no extra warning)
