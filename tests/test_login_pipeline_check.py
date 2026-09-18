from datetime import date
from unittest.mock import patch

import login_pipeline_check as login_check
from login_pipeline_check import (
    already_checked_today,
    main,
    mark_checked_today,
    prompt_and_maybe_run,
)


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


def test_prompt_and_maybe_run_launches_the_pipeline_on_a_yes_answer(tmp_path, monkeypatch):
    monkeypatch.setattr(login_check, "MARKER_FILE", tmp_path / "last_pipeline_check.json")
    with (
        patch("builtins.input", side_effect=["oui", ""]),
        patch.object(login_check.subprocess, "run") as fake_run,
    ):
        prompt_and_maybe_run()

    fake_run.assert_called_once()
    assert already_checked_today() is True


def test_prompt_and_maybe_run_skips_the_pipeline_on_a_no_answer(tmp_path, monkeypatch):
    monkeypatch.setattr(login_check, "MARKER_FILE", tmp_path / "last_pipeline_check.json")
    with (
        patch("builtins.input", side_effect=["non", ""]),
        patch.object(login_check.subprocess, "run") as fake_run,
    ):
        prompt_and_maybe_run()

    fake_run.assert_not_called()


def test_main_with_prompt_flag_calls_prompt_and_maybe_run_and_skips_the_date_gate(monkeypatch):
    monkeypatch.setattr("sys.argv", ["login_pipeline_check.py", "--prompt"])
    with (
        patch.object(login_check, "prompt_and_maybe_run") as fake_prompt,
        patch.object(login_check, "already_checked_today") as fake_checked,
        patch.object(login_check.subprocess, "Popen") as fake_popen,
    ):
        main()

    fake_prompt.assert_called_once()
    fake_checked.assert_not_called()
    fake_popen.assert_not_called()


def test_main_without_prompt_flag_does_nothing_when_already_checked_today(monkeypatch):
    monkeypatch.setattr("sys.argv", ["login_pipeline_check.py"])
    with (
        patch.object(login_check, "already_checked_today", return_value=True),
        patch.object(login_check.subprocess, "Popen") as fake_popen,
    ):
        main()

    fake_popen.assert_not_called()


def test_main_without_prompt_flag_relaunches_itself_in_a_terminal_when_not_yet_checked(monkeypatch):
    monkeypatch.setattr("sys.argv", ["login_pipeline_check.py"])
    with (
        patch.object(login_check, "already_checked_today", return_value=False),
        patch.object(login_check.subprocess, "Popen") as fake_popen,
    ):
        main()

    fake_popen.assert_called_once()
    args = fake_popen.call_args[0][0]
    assert args[0] == "x-terminal-emulator"
    assert args[-1] == "--prompt"
