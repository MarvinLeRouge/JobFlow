from unittest.mock import MagicMock, patch

import pytest

import extract.geo as geo
from extract.geo import get_dept


def test_get_dept_returns_empty_string_for_an_empty_ville():
    assert get_dept("", {}) == ""


def test_get_dept_matches_the_map_exactly_ignoring_case_and_accents():
    assert get_dept("Toulon", {"toulon": "83"}) == "83"
    assert get_dept("HYERES", {"hyeres": "83"}) == "83"


def test_get_dept_matches_by_the_first_word_when_no_exact_match():
    assert get_dept("Toulon centre-ville", {"toulon": "83"}) == "83"


def test_get_dept_falls_back_to_nominatim_when_nothing_matches(monkeypatch):
    monkeypatch.setattr(geo, "_nominatim_cache", {})
    monkeypatch.setattr(geo, "_last_nominatim_call", 0.0)
    with patch.object(geo, "_nominatim_dept", return_value="83") as fake_nominatim:
        result = get_dept("Unknown Place", {})

    assert result == "83"
    fake_nominatim.assert_called_once_with("Unknown Place")


def test_nominatim_dept_returns_the_cached_value_without_a_new_request(monkeypatch):
    monkeypatch.setattr(geo, "_nominatim_cache", {"Toulon": "83"})
    with patch("requests.get") as fake_get:
        result = geo._nominatim_dept("Toulon")

    assert result == "83"
    fake_get.assert_not_called()


def test_nominatim_dept_extracts_the_postcode_prefix_from_a_successful_response(monkeypatch):
    monkeypatch.setattr(geo, "_nominatim_cache", {})
    monkeypatch.setattr(geo, "_last_nominatim_call", 0.0)
    fake_response = MagicMock()
    fake_response.json.return_value = [{"address": {"postcode": "83000"}}]
    with (
        patch("requests.get", return_value=fake_response) as fake_get,
        patch.object(geo.time, "sleep") as fake_sleep,
    ):
        result = geo._nominatim_dept("Toulon")

    assert result == "83"
    assert geo._nominatim_cache["Toulon"] == "83"
    fake_get.assert_called_once()
    fake_sleep.assert_not_called()


def test_nominatim_dept_caches_an_empty_string_when_no_results(monkeypatch):
    monkeypatch.setattr(geo, "_nominatim_cache", {})
    monkeypatch.setattr(geo, "_last_nominatim_call", 0.0)
    fake_response = MagicMock()
    fake_response.json.return_value = []
    with patch("requests.get", return_value=fake_response):
        result = geo._nominatim_dept("Nowhereville")

    assert result == ""
    assert geo._nominatim_cache["Nowhereville"] == ""


def test_nominatim_dept_caches_an_empty_string_on_a_request_failure(monkeypatch):
    monkeypatch.setattr(geo, "_nominatim_cache", {})
    monkeypatch.setattr(geo, "_last_nominatim_call", 0.0)
    with patch("requests.get", side_effect=ConnectionError("boom")):
        result = geo._nominatim_dept("Toulon")

    assert result == ""
    assert geo._nominatim_cache["Toulon"] == ""


def test_nominatim_dept_throttles_requests_less_than_1_1_seconds_apart(monkeypatch):
    monkeypatch.setattr(geo, "_nominatim_cache", {})
    monkeypatch.setattr(geo, "_last_nominatim_call", 100.0)
    fake_response = MagicMock()
    fake_response.json.return_value = []
    with (
        patch.object(geo.time, "time", return_value=100.5),
        patch("requests.get", return_value=fake_response),
        patch.object(geo.time, "sleep") as fake_sleep,
    ):
        geo._nominatim_dept("Toulon")

    fake_sleep.assert_called_once()
    assert fake_sleep.call_args[0][0] == pytest.approx(0.6)
