import json

from sfboard.jobs.bugtool import diagnostics_snapshot
from sfboard.jobs.runtime_journal import default_journal_path


DIAGNOSTIC_KEYS = {"mode", "pending", "last_sync_at", "last_error", "created", "updated"}


def test_diagnostics_returns_defaults_when_nothing_exists(tmp_path):
    snapshot = diagnostics_snapshot(tmp_path)

    assert set(snapshot) == {"bug_bridge"}
    assert set(snapshot["bug_bridge"]) == DIAGNOSTIC_KEYS
    assert snapshot["bug_bridge"] == {
        "mode": "journal-only",
        "pending": 0,
        "last_sync_at": None,
        "last_error": "",
        "created": 0,
        "updated": 0,
    }


def test_diagnostics_survives_a_corrupt_state_file(tmp_path):
    state = tmp_path / ".grokpipe" / "runtime-bugs" / "bridge-state.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text("{not json", encoding="utf-8")

    snapshot = diagnostics_snapshot(tmp_path)

    assert snapshot["bug_bridge"]["created"] == 0
    assert snapshot["bug_bridge"]["last_error"] == ""


def test_diagnostics_counts_pending_and_sanitizes_last_error(tmp_path):
    journal = default_journal_path(tmp_path)
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(
        json.dumps({"event_id": "00000000-0000-4000-8000-000000000000"}) + "\n",
        encoding="utf-8",
    )
    state = tmp_path / ".grokpipe" / "runtime-bugs" / "bridge-state.json"
    state.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "processed_event_ids": [],
                "fingerprints": {},
                "health": {
                    "last_sync_at": "2026-08-14T02:00:00Z",
                    "last_error": "bd failed with Bearer abc-secret",
                    "created": 3,
                    "updated": 4,
                },
            }
        ),
        encoding="utf-8",
    )

    snapshot = diagnostics_snapshot(tmp_path)

    assert snapshot["bug_bridge"]["pending"] == 1
    assert snapshot["bug_bridge"]["created"] == 3
    assert snapshot["bug_bridge"]["updated"] == 4
    assert snapshot["bug_bridge"]["last_sync_at"] == "2026-08-14T02:00:00Z"
    assert "secret" not in snapshot["bug_bridge"]["last_error"]


def test_diagnostics_never_runs_bd_and_never_writes_state(tmp_path):
    journal = default_journal_path(tmp_path)
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text("", encoding="utf-8")

    diagnostics_snapshot(tmp_path)

    assert not (tmp_path / ".grokpipe" / "runtime-bugs" / "bridge-state.json").exists()
