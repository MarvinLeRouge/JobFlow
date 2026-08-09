import pytest

import run_pipeline


def test_run_pipeline_calls_steps_in_order(monkeypatch):
    calls = []
    monkeypatch.setattr(
        run_pipeline.fetch_gmail,
        "run",
        lambda dry_run, since_days: calls.append(("fetch", dry_run)),
    )
    monkeypatch.setattr(
        run_pipeline.rename_eml,
        "run",
        lambda dry_run, purge: calls.append(("rename", dry_run, purge)),
    )
    monkeypatch.setattr(
        run_pipeline.extract_eml, "main", lambda dry_run: calls.append(("extract", dry_run))
    )
    monkeypatch.setattr(run_pipeline.sheets_sync, "check_error_gate", lambda: None)
    monkeypatch.setattr(
        run_pipeline.sheets_sync, "run", lambda dry_run: calls.append(("sheets_sync", dry_run))
    )

    run_pipeline.run_pipeline(dry_run=True)

    assert calls == [
        ("fetch", True),
        ("rename", True, False),
        ("extract", True),
        ("sheets_sync", True),
    ]


def test_run_pipeline_passes_since_days_to_fetch(monkeypatch):
    calls = []
    monkeypatch.setattr(
        run_pipeline.fetch_gmail,
        "run",
        lambda dry_run, since_days: calls.append(("fetch", dry_run, since_days)),
    )
    monkeypatch.setattr(run_pipeline.rename_eml, "run", lambda dry_run, purge: None)
    monkeypatch.setattr(run_pipeline.extract_eml, "main", lambda dry_run: None)

    run_pipeline.run_pipeline(dry_run=True, since_days=30)

    assert calls == [("fetch", True, 30)]


def test_run_pipeline_defaults_since_days_to_none(monkeypatch):
    calls = []
    monkeypatch.setattr(
        run_pipeline.fetch_gmail,
        "run",
        lambda dry_run, since_days: calls.append(since_days),
    )
    monkeypatch.setattr(run_pipeline.rename_eml, "run", lambda dry_run, purge: None)
    monkeypatch.setattr(run_pipeline.extract_eml, "main", lambda dry_run: None)

    run_pipeline.run_pipeline(dry_run=True)

    assert calls == [None]


def test_run_pipeline_stops_on_fetch_failure(monkeypatch):
    def failing_fetch(dry_run, since_days):
        raise RuntimeError("network error")

    calls = []
    monkeypatch.setattr(run_pipeline.sheets_sync, "check_error_gate", lambda: None)
    monkeypatch.setattr(run_pipeline.fetch_gmail, "run", failing_fetch)
    monkeypatch.setattr(
        run_pipeline.rename_eml, "run", lambda dry_run, purge: calls.append("rename")
    )
    monkeypatch.setattr(run_pipeline.extract_eml, "main", lambda dry_run: calls.append("extract"))

    with pytest.raises(RuntimeError):
        run_pipeline.run_pipeline(dry_run=False)

    assert calls == []


def test_run_pipeline_calls_sheets_sync_last(monkeypatch):
    calls = []
    monkeypatch.setattr(
        run_pipeline.fetch_gmail,
        "run",
        lambda dry_run, since_days=None: calls.append(("fetch", dry_run)),
    )
    monkeypatch.setattr(
        run_pipeline.rename_eml,
        "run",
        lambda dry_run, purge: calls.append(("rename", dry_run, purge)),
    )
    monkeypatch.setattr(
        run_pipeline.extract_eml, "main", lambda dry_run: calls.append(("extract", dry_run))
    )
    monkeypatch.setattr(run_pipeline.sheets_sync, "check_error_gate", lambda: None)
    monkeypatch.setattr(
        run_pipeline.sheets_sync, "run", lambda dry_run: calls.append(("sheets_sync", dry_run))
    )

    run_pipeline.run_pipeline(dry_run=True)

    assert calls == [
        ("fetch", True),
        ("rename", True, False),
        ("extract", True),
        ("sheets_sync", True),
    ]


def test_run_pipeline_checks_error_gate_before_anything_else(monkeypatch):
    calls = []

    def failing_gate():
        calls.append("gate_checked")
        raise SystemExit("blocked")

    monkeypatch.setattr(run_pipeline.sheets_sync, "check_error_gate", failing_gate)
    monkeypatch.setattr(
        run_pipeline.fetch_gmail, "run", lambda dry_run, since_days=None: calls.append("fetch")
    )

    with pytest.raises(SystemExit, match="blocked"):
        run_pipeline.run_pipeline(dry_run=True)

    assert calls == ["gate_checked"]
