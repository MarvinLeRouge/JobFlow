from datetime import date

from login_pipeline_check import already_checked_today, mark_checked_today


def test_already_checked_today_is_false_when_marker_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("login_pipeline_check.MARKER_FILE", tmp_path / "last_pipeline_check.json")

    assert already_checked_today() is False


def test_mark_checked_today_then_already_checked_today_is_true(tmp_path, monkeypatch):
    monkeypatch.setattr("login_pipeline_check.MARKER_FILE", tmp_path / "last_pipeline_check.json")

    mark_checked_today()

    assert already_checked_today() is True


def test_already_checked_today_is_false_for_a_past_date(tmp_path, monkeypatch):
    marker = tmp_path / "last_pipeline_check.json"
    monkeypatch.setattr("login_pipeline_check.MARKER_FILE", marker)
    marker.write_text('{"last_check_date": "2020-01-01"}', encoding="utf-8")

    assert already_checked_today() is False


def test_mark_checked_today_stores_todays_local_date(tmp_path, monkeypatch):
    monkeypatch.setattr("login_pipeline_check.MARKER_FILE", tmp_path / "last_pipeline_check.json")

    mark_checked_today()

    import json

    stored = json.loads((tmp_path / "last_pipeline_check.json").read_text(encoding="utf-8"))
    assert stored["last_check_date"] == date.today().isoformat()
