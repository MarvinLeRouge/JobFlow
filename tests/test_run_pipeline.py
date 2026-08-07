import pytest

import run_pipeline


def test_run_pipeline_calls_steps_in_order(monkeypatch):
    calls = []
    monkeypatch.setattr(
        run_pipeline.fetch_gmail, "run", lambda dry_run: calls.append(("fetch", dry_run))
    )
    monkeypatch.setattr(
        run_pipeline.rename_eml,
        "run",
        lambda dry_run, purge: calls.append(("rename", dry_run, purge)),
    )
    monkeypatch.setattr(
        run_pipeline.extract_eml, "main", lambda dry_run: calls.append(("extract", dry_run))
    )

    run_pipeline.run_pipeline(dry_run=True)

    assert calls == [("fetch", True), ("rename", True, False), ("extract", True)]


def test_run_pipeline_stops_on_fetch_failure(monkeypatch):
    def failing_fetch(dry_run):
        raise RuntimeError("network error")

    calls = []
    monkeypatch.setattr(run_pipeline.fetch_gmail, "run", failing_fetch)
    monkeypatch.setattr(
        run_pipeline.rename_eml, "run", lambda dry_run, purge: calls.append("rename")
    )
    monkeypatch.setattr(run_pipeline.extract_eml, "main", lambda dry_run: calls.append("extract"))

    with pytest.raises(RuntimeError):
        run_pipeline.run_pipeline(dry_run=False)

    assert calls == []
