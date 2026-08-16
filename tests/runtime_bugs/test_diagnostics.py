import json

from helpers import load_sfboard, reset_legacy_state
from sfboard.jobs.bugtool import diagnostics_snapshot
from sfboard.jobs.models import JobKind
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


def test_board_invariants_bao_queue_co_viec_ma_lich_thieu():
    board = load_sfboard()
    reset_legacy_state(board)
    board._xep(board.IMG_QUEUE, ("img", "LO:A", 0, False))

    payload = board._job_invariant_diagnostics(now=0)

    assert payload["theo_ma"] == {"lich.thieu": 1}
    assert payload["findings"][0]["doi_tuong"] == "LO:A"


def test_board_invariants_khong_bao_sai_khi_retry_dang_cho_not_before():
    board = load_sfboard()
    reset_legacy_state(board)
    execution = board._JOB_SCHEDULER.schedule(
        JobKind.IMAGE, "LO:A", ("A",), not_before=0)
    lease = board._JOB_SCHEDULER.lease_ident(
        JobKind.IMAGE, "LO:A", now=0, ttl=30)
    board._JOB_SCHEDULER.release(lease.lease_id, not_before=100)
    board._dat_job("A", {"state": "running", "msg": "thử lại sau"})

    payload = board._job_invariant_diagnostics(now=50)

    assert payload["tong"] == 0
    assert payload["theo_ma"] == {}
    assert board._JOB_SCHEDULER.get(execution.execution_id).not_before == 100
