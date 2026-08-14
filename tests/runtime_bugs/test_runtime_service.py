import json
import logging

import pytest

from sfboard.jobs import runtime_service
from sfboard.jobs.runtime_journal import default_journal_path

from .fake_bd import FakeBd


@pytest.fixture(autouse=True)
def stopped_service():
    runtime_service.stop_runtime_bug_service()
    yield
    runtime_service.stop_runtime_bug_service()


def crash_signal(**overrides):
    signal = {
        "reason_code": "WORKER_CRASH",
        "category": "unhandled_exception",
        "severity": "ERROR",
        "job": {"job_id": "LO:S1", "kind": "img", "phase": "generating"},
        "runtime": {"endpoint": "127.0.0.1:9222"},
        "exception": {
            "type": "RuntimeError",
            "message": "tab died",
            "source_file": "sfboard/sfboard.py",
            "source_function": "_worker",
            "source_line": 1500,
        },
    }
    signal.update(overrides)
    return signal


def journal_lines(tmp_path):
    path = default_journal_path(tmp_path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_facade_is_safe_before_start_and_after_stop(tmp_path):
    assert runtime_service.report_runtime_bug(crash_signal()) is False
    assert runtime_service.runtime_bug_diagnostics()["bug_bridge"]["mode"] == "journal-only"

    runtime_service.start_runtime_bug_service(tmp_path)
    runtime_service.stop_runtime_bug_service()
    runtime_service.stop_runtime_bug_service()

    assert runtime_service.report_runtime_bug(crash_signal()) is False


def test_reportable_signal_is_journaled_with_fingerprint(tmp_path):
    runtime_service.start_runtime_bug_service(tmp_path)

    assert runtime_service.report_runtime_bug(crash_signal()) is True

    events = journal_lines(tmp_path)
    assert len(events) == 1
    assert events[0]["reason_code"] == "WORKER_CRASH"
    assert len(events[0]["fingerprint"]) == 64
    assert events[0]["schema_version"] == 1


@pytest.mark.parametrize("reason", ["VALIDATION", "CANCELLED", "EXPECTED_STOP", "NORMAL_RETRY"])
def test_non_reportable_signals_are_dropped(tmp_path, reason):
    runtime_service.start_runtime_bug_service(tmp_path)

    assert runtime_service.report_runtime_bug(crash_signal(reason_code=reason)) is False
    assert journal_lines(tmp_path) == []


def test_report_never_raises_on_a_broken_signal(tmp_path):
    runtime_service.start_runtime_bug_service(tmp_path)

    assert runtime_service.report_runtime_bug(None) is False
    assert runtime_service.report_runtime_bug({"reason_code": object()}) is False


def test_report_accepts_a_live_exception_and_derives_source_context(tmp_path):
    runtime_service.start_runtime_bug_service(tmp_path)
    try:
        raise ValueError("grok CDP đứt")
    except ValueError as exc:
        assert runtime_service.report_runtime_bug(
            {
                "reason_code": "SESSION_TRANSIENT",
                "category": "provider",
                "job": {"job_id": "V-S1-01", "kind": "vid", "phase": "submitting"},
                "exc": exc,
            }
        ) is True

    event = journal_lines(tmp_path)[0]
    assert event["exception"]["type"] == "ValueError"
    assert event["exception"]["source_function"] == (
        "test_report_accepts_a_live_exception_and_derives_source_context"
    )
    assert event["exception"]["source_file"].endswith("test_runtime_service.py")


def test_journal_only_mode_starts_no_bridge_and_never_runs_bd(tmp_path):
    fake = FakeBd()
    service = runtime_service.start_runtime_bug_service(tmp_path, run_bd=fake)

    runtime_service.report_runtime_bug(crash_signal())
    runtime_service.stop_runtime_bug_service()

    assert fake.calls == []
    assert service.bridge_thread is None
    assert runtime_service.runtime_bug_diagnostics()["bug_bridge"]["mode"] == "journal-only"


def test_logging_adapter_journals_only_typed_error_records(tmp_path):
    runtime_service.start_runtime_bug_service(tmp_path, attach_logging=True)
    log = logging.getLogger("sfboard.test-adapter")
    log.setLevel(logging.DEBUG)

    log.warning("chỉ là cảnh báo", extra={"runtime_reason_code": "WORKER_CRASH"})
    log.error("lỗi không có ngữ cảnh kiểu")
    log.error("huỷ theo yêu cầu", extra={"runtime_reason_code": "CANCELLED"})
    try:
        raise RuntimeError("thợ chết")
    except RuntimeError:
        log.error("thợ chết", exc_info=True, extra={"runtime_reason_code": "WORKER_CRASH"})

    events = journal_lines(tmp_path)
    assert len(events) == 1
    assert events[0]["reason_code"] == "WORKER_CRASH"
    assert events[0]["exception"]["type"] == "RuntimeError"


def test_logging_adapter_leaves_existing_root_handlers_untouched(tmp_path):
    root = logging.getLogger()
    before = list(root.handlers)

    runtime_service.start_runtime_bug_service(tmp_path, attach_logging=True)
    during = list(root.handlers)
    runtime_service.stop_runtime_bug_service()

    assert all(handler in during for handler in before)
    assert len(during) == len(before) + 1
    assert list(root.handlers) == before


def test_diagnostics_shape_is_stable_while_running(tmp_path):
    runtime_service.start_runtime_bug_service(tmp_path)
    runtime_service.report_runtime_bug(crash_signal())

    snapshot = runtime_service.runtime_bug_diagnostics()

    assert set(snapshot) == {"bug_bridge"}
    assert set(snapshot["bug_bridge"]) == {
        "mode",
        "pending",
        "last_sync_at",
        "last_error",
        "created",
        "updated",
    }
    assert snapshot["bug_bridge"]["pending"] == 1


def test_auto_create_mode_runs_the_bridge_and_stops_cleanly(tmp_path):
    config = tmp_path / ".grokpipe" / "runtime-bugs" / "config.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps({"mode": "auto-create"}), encoding="utf-8")
    fake = FakeBd()

    service = runtime_service.start_runtime_bug_service(tmp_path, run_bd=fake)
    runtime_service.report_runtime_bug(crash_signal())
    service.sync_now(timeout=5.0)
    runtime_service.stop_runtime_bug_service()

    assert [call[0] for call in fake.calls] == ["create"]
    assert service.bridge_thread is None or not service.bridge_thread.is_alive()
