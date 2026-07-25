"""
Unit tests for _gbif_fuzzy_name in lookup_table.py.

These mock _http_get so no network access is required.
"""

import sys
import os
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import lookup_table


def _resp(json_data, status=200):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_data
    return r


HIGHERRANK_BALANUS = {"matchType": "HIGHERRANK", "genus": "Balanus"}
EXACT_BALANUS = {"matchType": "EXACT", "species": "Balanus glandula"}
FUZZY_BALANUS = {"matchType": "FUZZY", "species": "Balanus glandula"}


@patch("lookup_table._http_get")
def test_misspelled_genus_higherrank_fallback(mock_get):
    mock_get.side_effect = [_resp(HIGHERRANK_BALANUS), _resp(EXACT_BALANUS)]
    name, matched = lookup_table._gbif_fuzzy_name("Ballanus glandula")
    assert name == "Ballanus glandula"
    assert matched == "Balanus glandula"
    assert mock_get.call_count == 2


@patch("lookup_table._http_get")
def test_misspelled_epithet_direct_fuzzy(mock_get):
    mock_get.return_value = _resp(FUZZY_BALANUS)
    name, matched = lookup_table._gbif_fuzzy_name("Balanus glandulla")
    assert name == "Balanus glandulla"
    assert matched == "Balanus glandula"
    assert mock_get.call_count == 1


@patch("lookup_table._http_get")
def test_both_misspelled_higherrank_then_fuzzy(mock_get):
    mock_get.side_effect = [_resp(HIGHERRANK_BALANUS), _resp(FUZZY_BALANUS)]
    name, matched = lookup_table._gbif_fuzzy_name("Ballanus glanddula")
    assert name == "Ballanus glanddula"
    assert matched == "Balanus glandula"
    assert mock_get.call_count == 2


@patch("lookup_table._http_get")
def test_no_match_returns_none(mock_get):
    mock_get.return_value = _resp({"matchType": "NONE"})
    name, matched = lookup_table._gbif_fuzzy_name("Xyzzy notaspecies12345")
    assert name == "Xyzzy notaspecies12345"
    assert matched is None


@patch("lookup_table._http_get")
def test_higherrank_without_genus_returns_none(mock_get):
    mock_get.return_value = _resp({"matchType": "HIGHERRANK", "genus": None})
    _, matched = lookup_table._gbif_fuzzy_name("Xyzzy something")
    assert matched is None
    assert mock_get.call_count == 1


@patch("lookup_table._http_get")
def test_higherrank_second_call_fails_returns_none(mock_get):
    mock_get.side_effect = [_resp(HIGHERRANK_BALANUS), _resp({"matchType": "NONE"})]
    _, matched = lookup_table._gbif_fuzzy_name("Ballanus glandula")
    assert matched is None
