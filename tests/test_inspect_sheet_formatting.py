import json
from unittest.mock import MagicMock, patch

import inspect_sheet_formatting as inspect_mod
from inspect_sheet_formatting import get_sheets_service, inspect, main


def test_get_sheets_service_builds_the_sheets_client_from_credentials():
    fake_creds = object()
    with (
        patch.object(
            inspect_mod.auth, "get_credentials", return_value=fake_creds
        ) as fake_get_creds,
        patch.object(inspect_mod, "build") as fake_build,
    ):
        service = get_sheets_service()

    fake_get_creds.assert_called_once_with(
        scopes=inspect_mod.SHEETS_SCOPES, token_file=inspect_mod.TOKEN_SHEETS_FILE
    )
    fake_build.assert_called_once_with("sheets", "v4", credentials=fake_creds)
    assert service is fake_build.return_value


def test_inspect_requests_the_sample_range_and_returns_the_raw_response():
    fake_service = MagicMock()
    fake_service.spreadsheets.return_value.get.return_value.execute.return_value = {"sheets": []}

    with patch.object(inspect_mod, "get_sheets_service", return_value=fake_service):
        result = inspect("sheet-id", "OffresTest")

    assert result == {"sheets": []}
    fake_service.spreadsheets.return_value.get.assert_called_once_with(
        spreadsheetId="sheet-id",
        ranges=["OffresTest!A1:Z3"],
        fields=(
            "sheets(properties,conditionalFormats,"
            "data.rowData.values(userEnteredValue,dataValidation,userEnteredFormat))"
        ),
        includeGridData=True,
    )


def test_main_prints_the_inspection_result_as_indented_json(capsys):
    with patch.object(inspect_mod, "inspect", return_value={"a": "é"}) as fake_inspect:
        main("sheet-id", "OffresTest")

    fake_inspect.assert_called_once_with("sheet-id", "OffresTest")
    out = capsys.readouterr().out
    assert json.loads(out) == {"a": "é"}
    assert "\\u" not in out
