import json

import pytest

from sfboard.jobs.beads_bridge import BeadsBridge, BridgeConfig

from .fake_bd import FakeBd


def event(index=0, fingerprint="fp-alpha", message="worker died"):
    return {
        "schema_version": 1,
        "event_id": f"00000000-0000-4000-8000-{index:012d}",
        "occurred_at": "2026-08-14T01:02:03Z",
        "severity": "ERROR",
        "category": "unhandled_exception",
        "reason_code": "WORKER_CRASH",
        "fingerprint": fingerprint,
        "job": {"job_id": "job-1", "kind": "video", "phase": "submitting"},
        "runtime": {"worker": "local", "port": 9222},
        "exception": {
            "type": "RuntimeError",
            "message": message,
            "source_file": "sfboard/sfboard.py",
            "source_function": "_worker",
            "source_line": 12,
        },
    }


def write_journal(tmp_path, events):
    path = tmp_path / "events.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        for item in events:
            handle.write(json.dumps(item) + "\n")
    return path


def make_bridge(tmp_path, runner, mode="auto-create"):
    config = BridgeConfig(
        repo_root=tmp_path,
        journal_path=tmp_path / "events.jsonl",
        state_path=tmp_path / "bridge-state.json",
        mode=mode,
    )
    return BeadsBridge(config, run_bd=runner, clock=lambda: "2026-08-14T02:00:00Z")


def test_repeated_fingerprint_creates_once_and_updates_the_rest(tmp_path):
    write_journal(tmp_path, [event(index) for index in range(10)])
    fake = FakeBd()

    health = make_bridge(tmp_path, fake).sync_once()

    creates = [call for call in fake.calls if call[0] == "create"]
    updates = [call for call in fake.calls if call[0] == "update"]
    assert len(creates) == 1
    assert len(updates) == 9
    assert (health.created, health.updated, health.pending) == (1, 9, 0)
    state = json.loads((tmp_path / "bridge-state.json").read_text(encoding="utf-8"))
    assert state["fingerprints"]["fp-alpha"]["count"] == 10
    assert state["fingerprints"]["fp-alpha"]["issue_id"] == "fake-001"


def test_distinct_fingerprints_create_separate_issues(tmp_path):
    write_journal(tmp_path, [event(0, "fp-alpha"), event(1, "fp-beta")])
    fake = FakeBd()

    health = make_bridge(tmp_path, fake).sync_once()

    assert health.created == 2
    assert len([call for call in fake.calls if call[0] == "create"]) == 2


def test_restart_does_not_replay_acknowledged_events(tmp_path):
    write_journal(tmp_path, [event(0), event(1, "fp-beta")])
    first = FakeBd()
    make_bridge(tmp_path, first).sync_once()

    second = FakeBd()
    health = make_bridge(tmp_path, second).sync_once()

    assert second.calls == []
    assert (health.created, health.updated, health.pending) == (0, 0, 0)


@pytest.mark.parametrize("mode", ["missing", "timeout", "nonzero", "corrupt"])
def test_failed_bd_call_preserves_state_file_byte_for_byte(tmp_path, mode):
    write_journal(tmp_path, [event(0)])
    state_path = tmp_path / "bridge-state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "processed_event_ids": [],
                "fingerprints": {},
                "health": {
                    "last_sync_at": None,
                    "last_error": "",
                    "created": 0,
                    "updated": 0,
                },
            }
        ),
        encoding="utf-8",
    )
    before = state_path.read_bytes()
    fake = FakeBd()
    fake.fail_next(mode)

    health = make_bridge(tmp_path, fake).sync_once()

    assert state_path.read_bytes() == before
    assert health.ok is False
    assert health.last_error
    assert health.created == 0
    assert list(tmp_path.glob("*.tmp")) == []


def test_batch_stops_at_the_first_failure_and_keeps_later_events_pending(tmp_path):
    write_journal(tmp_path, [event(0, "fp-alpha"), event(1, "fp-beta")])
    fake = FakeBd()

    bridge = make_bridge(tmp_path, fake)
    first_health = bridge.sync_once()
    assert first_health.created == 2

    write_journal(tmp_path, [event(2, "fp-gamma"), event(3, "fp-delta")])
    fake.fail_next("nonzero")
    second_health = bridge.sync_once()

    assert second_health.created == 0
    assert second_health.pending == 2
    assert second_health.ok is False


def test_closed_matching_issue_is_reopened_but_never_claimed_or_closed(tmp_path):
    write_journal(tmp_path, [event(0)])
    fake = FakeBd()
    bridge = make_bridge(tmp_path, fake)
    bridge.sync_once()
    fake.issues["fake-001"]["status"] = "closed"

    write_journal(tmp_path, [event(1)])
    bridge.sync_once()

    update = [call for call in fake.calls if call[0] == "update"][-1]
    assert "--status" in update and update[update.index("--status") + 1] == "open"
    assert fake.issues["fake-001"]["status"] == "open"
    forbidden = {"--claim", "--assignee", "-a", "--priority", "-p", "close"}
    assert not any(forbidden.intersection(call) for call in fake.calls if call[0] != "create")


def test_journal_only_mode_never_touches_bd_but_still_counts_pending(tmp_path):
    write_journal(tmp_path, [event(0), event(1, "fp-beta")])
    fake = FakeBd()

    health = make_bridge(tmp_path, fake, mode="journal-only").sync_once()

    assert fake.calls == []
    assert health.pending == 2
    assert health.mode == "journal-only"
    assert not (tmp_path / "bridge-state.json").exists()


def test_bridge_payload_is_redacted_and_bounded(tmp_path):
    write_journal(
        tmp_path,
        [event(0, message="login failed Bearer abc-secret at https://user:pw@x.test?token=q-secret")],
    )
    fake = FakeBd()

    make_bridge(tmp_path, fake).sync_once()

    payload = json.dumps(fake.calls)
    assert "secret" not in payload
    created = fake.issues["fake-001"]
    assert len(created["title"]) <= 120
    assert "\n" not in created["title"]
    assert created["metadata"]["runtime_fingerprint"] == "fp-alpha"
    assert created["labels"] == ["auto-reported", "runtime-bug"]
    assert created["issue_type"] == "bug"


def test_bridge_failure_writes_no_recursive_journal_entry(tmp_path):
    journal = write_journal(tmp_path, [event(0)])
    before = journal.read_bytes()
    fake = FakeBd()
    fake.fail_next("timeout")

    make_bridge(tmp_path, fake).sync_once()

    assert journal.read_bytes() == before


def test_missing_journal_reports_healthy_empty_state(tmp_path):
    fake = FakeBd()

    health = make_bridge(tmp_path, fake).sync_once()

    assert fake.calls == []
    assert (health.pending, health.created, health.updated) == (0, 0, 0)
    assert health.ok is True


def test_corrupt_state_file_is_replaced_by_defaults_without_replaying_twice(tmp_path):
    write_journal(tmp_path, [event(0)])
    (tmp_path / "bridge-state.json").write_text("{broken", encoding="utf-8")
    fake = FakeBd()

    health = make_bridge(tmp_path, fake).sync_once()

    assert health.created == 1
    state = json.loads((tmp_path / "bridge-state.json").read_text(encoding="utf-8"))
    assert state["processed_event_ids"] == ["00000000-0000-4000-8000-000000000000"]
