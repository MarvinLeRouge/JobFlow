import json

import pytest

import migrate_offres_add_message_id as migrate
from migrate_offres_add_message_id import (
    NEW_COLUMN,
    add_message_id_column,
    insert_before_array_close,
)

CONFIG_TEXT = """{
  "csv_separator": ";",
  "offres_csv_headers": [
    "ID", "Traite", "Date_decouverte",
    "Raison_exclusion", "Date_candidature", "Notes"
  ],
  "url_qualite_values": ["construite", "email", "vide"]
}
"""


def write_config(tmp_path, text=CONFIG_TEXT):
    path = tmp_path / "config.json"
    path.write_text(text, encoding="utf-8")
    return path


def write_offres_csv(tmp_path, header_line, data_lines):
    path = tmp_path / "offres.csv"
    path.write_text("\n".join([header_line, *data_lines]) + "\n", encoding="utf-8")
    return path


def use_paths(monkeypatch, config_path, csv_path):
    monkeypatch.setattr(migrate, "CONFIG_FILE", config_path)
    monkeypatch.setattr(migrate, "OFFRES_CSV", csv_path)


def test_add_message_id_column_appends_at_end():
    headers = ["ID", "Traite", "Notes"]
    rows = [{"ID": "E000001", "Traite": "FALSE", "Notes": ""}]

    new_rows, new_headers = add_message_id_column(rows, headers)

    assert new_headers == ["ID", "Traite", "Notes", "Message_ID"]
    assert new_rows == [{"ID": "E000001", "Traite": "FALSE", "Notes": "", "Message_ID": ""}]


def test_add_message_id_column_is_idempotent():
    headers = ["ID", "Message_ID"]
    rows = [{"ID": "E000001", "Message_ID": "<msg-1>"}]

    new_rows, new_headers = add_message_id_column(rows, headers)

    assert new_headers == headers
    assert new_rows == rows


def test_add_message_id_column_handles_empty_rows():
    new_rows, new_headers = add_message_id_column([], ["ID"])
    assert new_rows == []
    assert new_headers == ["ID", NEW_COLUMN]


def test_add_message_id_column_keeps_existing_values():
    """Half-migrated state: the CSV already has the column, config.json does
    not. Re-running must not wipe the values already stored."""
    headers = ["ID", "Notes"]
    rows = [{"ID": "E000001", "Notes": "", "Message_ID": "<msg-1>"}]

    new_rows, new_headers = add_message_id_column(rows, headers)

    assert new_headers == ["ID", "Notes", "Message_ID"]
    assert new_rows[0]["Message_ID"] == "<msg-1>"


def test_insert_before_array_close_appends_to_the_right_array():
    result = insert_before_array_close(CONFIG_TEXT, "offres_csv_headers", "Message_ID")

    assert json.loads(result)["offres_csv_headers"][-1] == "Message_ID"
    assert json.loads(result)["url_qualite_values"] == ["construite", "email", "vide"]


def test_insert_before_array_close_keeps_the_rest_of_the_file_byte_identical():
    result = insert_before_array_close(CONFIG_TEXT, "offres_csv_headers", "Message_ID")

    assert result.replace(', "Message_ID"', "", 1) == CONFIG_TEXT
    assert result.count("\n") == CONFIG_TEXT.count("\n")
    assert '"Notes", "Message_ID"\n' in result


def test_insert_before_array_close_handles_a_single_line_array():
    text = '{"a": ["x", "y"], "b": 1}'
    result = insert_before_array_close(text, "a", "z")
    assert result == '{"a": ["x", "y", "z"], "b": 1}'


def test_insert_before_array_close_handles_an_empty_array():
    result = insert_before_array_close('{"a": []}', "a", "z")
    assert result == '{"a": ["z"]}'
    assert json.loads(result) == {"a": ["z"]}


def test_insert_before_array_close_ignores_brackets_inside_strings():
    text = '{"a": ["x]", "y"], "b": ["z"]}'
    result = insert_before_array_close(text, "a", "w")
    assert json.loads(result) == {"a": ["x]", "y", "w"], "b": ["z"]}


def test_insert_before_array_close_escapes_the_new_item():
    result = insert_before_array_close('{"a": ["x"]}', "a", 'quote " and backslash \\')
    assert json.loads(result) == {"a": ["x", 'quote " and backslash \\']}


def test_insert_before_array_close_raises_on_unknown_key():
    with pytest.raises(ValueError):
        insert_before_array_close(CONFIG_TEXT, "does_not_exist", "Message_ID")


def test_insert_before_array_close_raises_on_unterminated_array():
    with pytest.raises(ValueError):
        insert_before_array_close('{"a": ["x"', "a", "z")


def test_main_dry_run_writes_nothing(tmp_path, monkeypatch, capsys):
    config_path = write_config(tmp_path)
    csv_path = write_offres_csv(tmp_path, "ID;Notes", ["E000001;"])
    use_paths(monkeypatch, config_path, csv_path)
    config_before = config_path.read_text(encoding="utf-8")
    csv_before = csv_path.read_text(encoding="utf-8")

    migrate.main(dry_run=True)

    assert config_path.read_text(encoding="utf-8") == config_before
    assert csv_path.read_text(encoding="utf-8") == csv_before
    assert "[DRY-RUN]" in capsys.readouterr().out


def test_main_updates_csv_and_config(tmp_path, monkeypatch):
    config_path = write_config(tmp_path)
    csv_path = write_offres_csv(
        tmp_path,
        "ID;Traite;Date_decouverte;Raison_exclusion;Date_candidature;Notes",
        ["E000001;FALSE;2026-08-01;;;"],
    )
    use_paths(monkeypatch, config_path, csv_path)

    migrate.main(dry_run=False)

    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["offres_csv_headers"][-1] == "Message_ID"
    lines = csv_path.read_text(encoding="utf-8").splitlines()
    assert lines[0].endswith(";Message_ID")
    assert lines[1] == "E000001;FALSE;2026-08-01;;;;"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["config.json", "offres.csv"]


def test_main_preserves_config_formatting(tmp_path, monkeypatch):
    config_path = write_config(tmp_path)
    csv_path = write_offres_csv(tmp_path, "ID;Notes", ["E000001;"])
    use_paths(monkeypatch, config_path, csv_path)

    migrate.main(dry_run=False)

    text = config_path.read_text(encoding="utf-8")
    assert text.replace(', "Message_ID"', "", 1) == CONFIG_TEXT


def test_main_is_idempotent(tmp_path, monkeypatch, capsys):
    config_path = write_config(tmp_path)
    csv_path = write_offres_csv(tmp_path, "ID;Notes", ["E000001;"])
    use_paths(monkeypatch, config_path, csv_path)

    migrate.main(dry_run=False)
    config_after_first = config_path.read_text(encoding="utf-8")
    capsys.readouterr()

    migrate.main(dry_run=False)

    assert config_path.read_text(encoding="utf-8") == config_after_first
    assert "déjà présent" in capsys.readouterr().out


def test_main_leaves_offres_csv_intact_when_the_write_fails(tmp_path, monkeypatch):
    """An unexpected column in the CSV makes DictWriter raise partway. The
    user's only copy of the data must survive untouched, and config.json
    must not claim a column the CSV does not have."""
    config_path = write_config(tmp_path)
    csv_path = write_offres_csv(
        tmp_path,
        "ID;Traite;Date_decouverte;Raison_exclusion;Date_candidature;Notes;Inattendu",
        ["E000001;FALSE;2026-08-01;;;;x"],
    )
    use_paths(monkeypatch, config_path, csv_path)
    config_before = config_path.read_text(encoding="utf-8")
    csv_before = csv_path.read_text(encoding="utf-8")

    with pytest.raises(ValueError):
        migrate.main(dry_run=False)

    assert csv_path.read_text(encoding="utf-8") == csv_before
    assert config_path.read_text(encoding="utf-8") == config_before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["config.json", "offres.csv"]


def test_main_writes_the_csv_before_the_config(tmp_path, monkeypatch):
    """Ordering guarantee: if the run dies between the two writes, the CSV
    already carries the column and config.json does not claim it yet, so a
    re-run can finish the job."""
    config_path = write_config(tmp_path)
    csv_path = write_offres_csv(
        tmp_path,
        "ID;Traite;Date_decouverte;Raison_exclusion;Date_candidature;Notes",
        ["E000001;FALSE;2026-08-01;;;"],
    )
    use_paths(monkeypatch, config_path, csv_path)

    def boom(*args, **kwargs):
        raise RuntimeError("interrupted")

    monkeypatch.setattr(migrate, "write_text_atomic", boom)

    with pytest.raises(RuntimeError):
        migrate.main(dry_run=False)

    assert csv_path.read_text(encoding="utf-8").splitlines()[0].endswith(";Message_ID")
    assert json.loads(config_path.read_text(encoding="utf-8"))["offres_csv_headers"][-1] == "Notes"

    # Re-running finishes the migration from that half-migrated state.
    monkeypatch.undo()
    use_paths(monkeypatch, config_path, csv_path)
    migrate.main(dry_run=False)

    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["offres_csv_headers"][-1] == "Message_ID"


def test_main_handles_a_missing_offres_csv(tmp_path, monkeypatch):
    config_path = write_config(tmp_path)
    csv_path = tmp_path / "offres.csv"
    use_paths(monkeypatch, config_path, csv_path)

    migrate.main(dry_run=False)

    assert not csv_path.exists()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["offres_csv_headers"][-1] == "Message_ID"
