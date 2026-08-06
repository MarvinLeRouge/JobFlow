from migrate_offres_add_message_id import NEW_COLUMN, add_message_id_column


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
