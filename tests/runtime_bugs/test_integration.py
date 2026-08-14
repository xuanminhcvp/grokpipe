"""Đầu-tới-cuối trong thư mục tạm: ghi sổ → restart → sync → Bead, không mạng."""

import io
import json

import pytest

from sfboard.jobs import bugtool, runtime_service
from sfboard.jobs.runtime_journal import default_journal_path

from .fake_bd import FakeBd


CANARY = "https://user:pw@grok.test/x?token=shhh9x7q Bearer shhh9x7q"


@pytest.fixture(autouse=True)
def stopped_service():
    runtime_service.stop_runtime_bug_service()
    yield
    runtime_service.stop_runtime_bug_service()


def crash(**overrides):
    signal = {
        "reason_code": "PROVIDER_TRANSIENT",
        "category": "provider",
        "severity": "ERROR",
        "job": {"job_id": "V-S1-07", "kind": "vid", "phase": "submitting"},
        "runtime": {"endpoint": "127.0.0.1:9222"},
        "exception": {
            "type": "TimeoutError",
            "message": f"không nối được Grok — {CANARY}",
            "source_file": "grokpipe/video_grok.py",
            "source_function": "submit",
            "source_line": 88,
        },
    }
    signal.update(overrides)
    return signal


def enable_auto_create(root):
    config = bugtool.config_path(root)
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps({"mode": "auto-create"}), encoding="utf-8")


def cli(root, *args, run_bd=None):
    stream = io.StringIO()
    code = bugtool.main(["--root", str(root), *args], stdout=stream, run_bd=run_bd)
    return code, json.loads(stream.getvalue())


def test_event_survives_a_service_restart_and_stays_readable(tmp_path):
    runtime_service.start_runtime_bug_service(tmp_path)
    assert runtime_service.report_runtime_bug(crash()) is True
    runtime_service.stop_runtime_bug_service()

    runtime_service.start_runtime_bug_service(tmp_path)
    code, payload = cli(tmp_path, "list")

    assert code == 0
    assert payload["count"] == 1
    assert payload["events"][0]["reason_code"] == "PROVIDER_TRANSIENT"


def test_journal_only_end_to_end_never_calls_bd(tmp_path):
    fake = FakeBd()
    runtime_service.start_runtime_bug_service(tmp_path, run_bd=fake)

    for _ in range(3):
        runtime_service.report_runtime_bug(crash())
    cli(tmp_path, "status", run_bd=fake)
    cli(tmp_path, "sync", run_bd=fake)

    assert fake.calls == []
    assert runtime_service.runtime_bug_diagnostics()["bug_bridge"]["pending"] == 3


def test_auto_create_sync_files_one_bead_for_a_repeated_fingerprint(tmp_path):
    enable_auto_create(tmp_path)
    fake = FakeBd()
    runtime_service.start_runtime_bug_service(tmp_path, run_bd=fake)
    for _ in range(4):
        runtime_service.report_runtime_bug(crash())
    runtime_service.stop_runtime_bug_service()

    code, payload = cli(tmp_path, "sync", run_bd=fake)

    assert code == 0
    assert len([call for call in fake.calls if call[0] == "create"]) == 1
    assert len(fake.issues) == 1
    assert payload["bug_bridge"]["created"] == 1
    assert payload["bug_bridge"]["updated"] == 3
    assert payload["bug_bridge"]["pending"] == 0


def test_second_run_does_not_replay_and_counters_stay_stable(tmp_path):
    enable_auto_create(tmp_path)
    fake = FakeBd()
    runtime_service.start_runtime_bug_service(tmp_path, run_bd=fake)
    runtime_service.report_runtime_bug(crash())
    runtime_service.stop_runtime_bug_service()
    cli(tmp_path, "sync", run_bd=fake)
    calls_after_first = len(fake.calls)

    code, payload = cli(tmp_path, "sync", run_bd=fake)

    assert code == 0
    assert len(fake.calls) == calls_after_first
    assert payload["bug_bridge"]["created"] == 1
    assert payload["bug_bridge"]["pending"] == 0
    assert bugtool.diagnostics_snapshot(tmp_path)["bug_bridge"]["created"] == 1


@pytest.mark.parametrize("reason", ["CANCELLED", "VALIDATION", "EXPECTED_STOP", "NORMAL_RETRY"])
def test_expected_stops_never_reach_the_journal_or_beads(tmp_path, reason):
    enable_auto_create(tmp_path)
    fake = FakeBd()
    runtime_service.start_runtime_bug_service(tmp_path, run_bd=fake)

    assert runtime_service.report_runtime_bug(crash(reason_code=reason)) is False
    runtime_service.stop_runtime_bug_service()
    cli(tmp_path, "sync", run_bd=fake)

    assert fake.calls == []
    assert fake.issues == {}
    assert not default_journal_path(tmp_path).read_text(encoding="utf-8").strip()


def test_canary_secret_never_appears_in_any_surface(tmp_path):
    enable_auto_create(tmp_path)
    fake = FakeBd()
    runtime_service.start_runtime_bug_service(tmp_path, run_bd=fake)
    runtime_service.report_runtime_bug(crash())
    runtime_service.stop_runtime_bug_service()
    cli(tmp_path, "sync", run_bd=fake)

    surfaces = [
        default_journal_path(tmp_path).read_text(encoding="utf-8"),
        (tmp_path / ".grokpipe" / "runtime-bugs" / "bridge-state.json").read_text(encoding="utf-8"),
        json.dumps(cli(tmp_path, "list")[1]),
        json.dumps(cli(tmp_path, "status")[1]),
        json.dumps(bugtool.diagnostics_snapshot(tmp_path)),
        json.dumps(fake.calls),
        json.dumps(fake.issues),
    ]

    for surface in surfaces:
        assert "shhh9x7q" not in surface
        assert "user:pw" not in surface


def test_runtime_state_stays_inside_the_ignored_local_folder(tmp_path):
    enable_auto_create(tmp_path)
    fake = FakeBd()
    runtime_service.start_runtime_bug_service(tmp_path, run_bd=fake)
    runtime_service.report_runtime_bug(crash())
    runtime_service.stop_runtime_bug_service()
    cli(tmp_path, "sync", run_bd=fake)

    produced = {path.relative_to(tmp_path).parts[0] for path in tmp_path.rglob("*") if path.is_file()}

    assert produced == {".grokpipe"}


def test_rollback_to_journal_only_stops_beads_without_losing_events(tmp_path):
    enable_auto_create(tmp_path)
    fake = FakeBd()
    runtime_service.start_runtime_bug_service(tmp_path, run_bd=fake)
    runtime_service.report_runtime_bug(crash())
    runtime_service.stop_runtime_bug_service()
    cli(tmp_path, "sync", run_bd=fake)

    bugtool.config_path(tmp_path).write_text(json.dumps({"mode": "journal-only"}), encoding="utf-8")
    runtime_service.start_runtime_bug_service(tmp_path, run_bd=fake)
    runtime_service.report_runtime_bug(crash(job={"job_id": "V-S1-08", "kind": "vid"}))
    calls_before = len(fake.calls)
    code, payload = cli(tmp_path, "sync", run_bd=fake)

    assert code == 0
    assert len(fake.calls) == calls_before
    assert payload["bug_bridge"]["mode"] == "journal-only"
    assert cli(tmp_path, "list")[1]["count"] == 2
