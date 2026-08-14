import json
import threading
from pathlib import Path

import pytest
from loguru import logger

from sfboard.jobs.runtime_journal import (
    JOURNAL_LOGGER,
    RuntimeBugJournal,
    default_journal_path,
    iter_events,
    journal_paths,
)


def valid_event(**overrides):
    event = {
        "schema_version": 1,
        "event_id": "123e4567-e89b-12d3-a456-426614174000",
        "occurred_at": "2026-08-14T01:02:03Z",
        "severity": "ERROR",
        "category": "unhandled_exception",
        "reason_code": "WORKER_CRASH",
        "fingerprint": "placeholder",
        "job": {"job_id": "job-1", "kind": "video", "phase": "submitting"},
        "runtime": {"worker": "local"},
        "exception": {
            "type": "RuntimeError",
            "message": "worker died",
            "source_file": "sfboard/sfboard.py",
            "source_function": "_worker",
            "source_line": 12,
        },
    }
    event.update(overrides)
    return event


@pytest.fixture
def journal(tmp_path):
    made = RuntimeBugJournal(tmp_path / "runtime-bugs" / "events.jsonl", repo_root=tmp_path)
    try:
        yield made
    finally:
        made.close()


def test_sink_is_created_with_the_exact_required_options(tmp_path, monkeypatch):
    captured = {}
    original_add = JOURNAL_LOGGER.add

    def spy(sink, **kwargs):
        captured["sink"] = sink
        captured.update(kwargs)
        return original_add(sink, **kwargs)

    monkeypatch.setattr(JOURNAL_LOGGER, "add", spy)
    made = RuntimeBugJournal(tmp_path / "events.jsonl", repo_root=tmp_path)
    made.close()

    assert captured["rotation"] == "10 MB"
    assert captured["retention"] == 10
    assert captured["compression"] is None
    assert captured["enqueue"] is False
    assert captured["serialize"] is False
    assert captured["backtrace"] is True
    assert captured["diagnose"] is False
    assert captured["catch"] is True
    assert captured["format"] == "{message}"
    assert captured["encoding"] == "utf-8"
    assert captured["buffering"] == 1
    assert captured["filter"]({"extra": {"runtime_bug": True, "journal_id": made.journal_id}})
    assert not captured["filter"]({"extra": {}})


def test_record_writes_one_redacted_json_line_with_computed_fingerprint(journal):
    event = valid_event()
    event["exception"]["message"] = "auth failed Bearer abc-secret"

    assert journal.record(event) is True

    lines = journal.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    stored = json.loads(lines[0])
    assert "secret" not in lines[0]
    assert stored["fingerprint"] != "placeholder"
    assert len(stored["fingerprint"]) == 64
    assert stored["event_id"] == event["event_id"]


def test_record_never_raises_and_reports_bounded_stderr_line(tmp_path):
    written = []

    class Sink:
        def write(self, text):
            written.append(text)

        def flush(self):
            return None

    made = RuntimeBugJournal(tmp_path / "events.jsonl", repo_root=tmp_path, stderr=Sink())
    try:
        broken = valid_event()
        del broken["runtime"]

        assert made.record(broken) is False
        assert made.record("not-a-mapping") is False
    finally:
        made.close()

    assert written
    assert all(len(text) <= 512 for text in written)
    assert not (tmp_path / "events.jsonl").exists() or not (
        tmp_path / "events.jsonl"
    ).read_text(encoding="utf-8").strip()


def test_concurrent_records_write_complete_unique_lines(journal):
    def work(thread_index):
        for step in range(25):
            event = valid_event()
            event["event_id"] = f"00000000-0000-4000-8000-{thread_index:06d}{step:06d}"
            journal.record(event)

    threads = [threading.Thread(target=work, args=(index,)) for index in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    lines = journal.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 500
    identifiers = {json.loads(line)["event_id"] for line in lines}
    assert len(identifiers) == 500


def test_reader_skips_truncated_crash_tail_without_rewriting_the_journal(journal):
    journal.record(valid_event())
    journal.close()
    with journal.path.open("a", encoding="utf-8") as handle:
        handle.write('{"schema_version": 1, "event_id": "trunc')
    before = journal.path.read_bytes()

    events = list(iter_events([journal.path]))

    assert len(events) == 1
    assert journal.path.read_bytes() == before


def test_reader_surfaces_malformed_complete_line_as_health_error(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text('{"broken": ,}\n{"ok": 1}\n', encoding="utf-8")
    errors = []

    events = list(iter_events([path], on_error=errors.append))

    assert events == [{"ok": 1}]
    assert len(errors) == 1
    assert "events.jsonl" in errors[0]


def test_close_removes_only_its_own_handler(tmp_path):
    other = tmp_path / "other.log"
    other_id = JOURNAL_LOGGER.add(str(other), format="{message}", filter=lambda record: True)
    try:
        made = RuntimeBugJournal(tmp_path / "events.jsonl", repo_root=tmp_path)
        made.record(valid_event())
        made.close()
        made.close()

        JOURNAL_LOGGER.info("still alive")
        assert "still alive" in other.read_text(encoding="utf-8")
    finally:
        JOURNAL_LOGGER.remove(other_id)


def test_journal_uses_a_private_core_so_the_default_stderr_sink_stays_quiet(tmp_path, capsys):
    shared = tmp_path / "shared.log"
    shared_id = logger.add(str(shared), format="{message}", filter=lambda record: True)
    made = RuntimeBugJournal(tmp_path / "events.jsonl", repo_root=tmp_path)
    try:
        made.record(valid_event())
    finally:
        made.close()
        logger.remove(shared_id)

    assert shared.read_text(encoding="utf-8") == ""
    assert "worker died" not in capsys.readouterr().err


def test_journal_paths_order_rotated_segments_before_the_live_file(tmp_path):
    live = tmp_path / "events.jsonl"
    live.write_text("", encoding="utf-8")
    second = tmp_path / "events.2026-08-14_02-00-00_000000.jsonl"
    second.write_text("", encoding="utf-8")
    first = tmp_path / "events.2026-08-14_01-00-00_000000.jsonl"
    first.write_text("", encoding="utf-8")

    assert journal_paths(live) == [first, second, live]


def test_default_journal_path_is_local_runtime_bug_storage(tmp_path):
    assert default_journal_path(tmp_path) == Path(
        tmp_path, ".grokpipe", "runtime-bugs", "events.jsonl"
    )
