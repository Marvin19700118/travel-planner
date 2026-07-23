import shutil

import storage


def test_save_and_load_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "RUN_LOG_DIR", tmp_path / "run_logs")
    request = {"city": "testville", "start_date": "2026-08-01", "days": 2, "preferences": ["museum"]}
    events = [{"type": "thought", "content": {"text": "hi"}}, {"type": "final", "content": {"status": "done"}}]

    storage.save_run("abc123", request, events)
    loaded = storage.load_run("abc123")

    assert loaded["run_id"] == "abc123"
    assert loaded["request"] == request
    assert loaded["events"] == events


def test_load_missing_run_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "RUN_LOG_DIR", tmp_path / "run_logs")
    assert storage.load_run("does-not-exist") is None


def test_list_runs_reports_status_from_final_event(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "RUN_LOG_DIR", tmp_path / "run_logs")
    storage.save_run(
        "run1",
        {"city": "testville", "start_date": "2026-08-01", "days": 1, "preferences": ["museum"]},
        [{"type": "final", "content": {"status": "done"}}],
    )

    runs = storage.list_runs()

    assert len(runs) == 1
    assert runs[0]["run_id"] == "run1"
    assert runs[0]["status"] == "done"
