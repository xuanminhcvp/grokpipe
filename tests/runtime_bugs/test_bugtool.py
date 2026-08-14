import io
import json

from sfboard.jobs import bugtool
from sfboard.jobs.runtime_journal import default_journal_path

from .fake_bd import FakeBd


SECRET_MESSAGE = "login failed Bearer abc-secret cookie=sessionid=zzz-secret"


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
        "runtime": {"worker": "local"},
        "exception": {
            "type": "RuntimeError",
            "message": message,
            "source_file": "sfboard/sfboard.py",
            "source_function": "_worker",
            "source_line": 12,
        },
    }


def seed(tmp_path, events):
    path = default_journal_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for item in events:
            handle.write(json.dumps(item) + "\n")
    return path


def run(tmp_path, *args, run_bd=None):
    stdout = io.StringIO()
    code = bugtool.main(["--root", str(tmp_path), *args], stdout=stdout, run_bd=run_bd)
    return code, json.loads(stdout.getvalue())


def test_status_reports_journal_and_bridge_without_mutating_anything(tmp_path):
    journal = seed(tmp_path, [event(0), event(1, "fp-beta")])
    before = journal.read_bytes()

    code, payload = run(tmp_path, "status")

    assert code == 0
    assert payload["command"] == "status"
    assert payload["journal"]["events"] == 2
    assert payload["bug_bridge"]["mode"] == "journal-only"
    assert payload["bug_bridge"]["pending"] == 2
    assert journal.read_bytes() == before
    assert not (tmp_path / ".grokpipe" / "runtime-bugs" / "bridge-state.json").exists()


def test_list_summarizes_events_newest_last_and_redacts_secrets(tmp_path):
    seed(tmp_path, [event(0, message=SECRET_MESSAGE), event(1, "fp-beta")])

    code, payload = run(tmp_path, "list")

    assert code == 0
    assert payload["count"] == 2
    assert [item["fingerprint"] for item in payload["events"]] == ["fp-alpha", "fp-beta"]
    assert "secret" not in json.dumps(payload)


def test_list_honours_limit(tmp_path):
    seed(tmp_path, [event(index, f"fp-{index}") for index in range(5)])

    code, payload = run(tmp_path, "list", "--limit", "2")

    assert code == 0
    assert payload["count"] == 2


def test_show_returns_the_redacted_event(tmp_path):
    seed(tmp_path, [event(0, message=SECRET_MESSAGE)])

    code, payload = run(tmp_path, "show", "00000000-0000-4000-8000-000000000000")

    assert code == 0
    assert payload["event"]["fingerprint"] == "fp-alpha"
    assert "secret" not in json.dumps(payload)


def test_show_unknown_event_exits_two_with_json_error(tmp_path):
    seed(tmp_path, [event(0)])

    code, payload = run(tmp_path, "show", "11111111-1111-4111-8111-111111111111")

    assert code == 2
    assert payload["error"] == "event_not_found"


def test_read_only_commands_never_invoke_bd(tmp_path):
    seed(tmp_path, [event(0)])
    fake = FakeBd()

    for args in (["status"], ["list"], ["show", "00000000-0000-4000-8000-000000000000"]):
        run(tmp_path, *args, run_bd=fake)

    assert fake.calls == []


def test_sync_in_journal_only_mode_makes_no_bd_call(tmp_path):
    seed(tmp_path, [event(0)])
    fake = FakeBd()

    code, payload = run(tmp_path, "sync", run_bd=fake)

    assert code == 0
    assert fake.calls == []
    assert payload["bug_bridge"]["mode"] == "journal-only"
    assert payload["bug_bridge"]["pending"] == 1


def test_sync_uses_bridge_once_when_auto_create_is_configured(tmp_path):
    seed(tmp_path, [event(0)])
    config = tmp_path / ".grokpipe" / "runtime-bugs" / "config.json"
    config.write_text(json.dumps({"mode": "auto-create"}), encoding="utf-8")
    fake = FakeBd()

    code, payload = run(tmp_path, "sync", run_bd=fake)

    assert code == 0
    assert [call[0] for call in fake.calls] == ["create"]
    assert payload["bug_bridge"]["created"] == 1
    assert payload["bug_bridge"]["mode"] == "auto-create"


def test_unknown_command_exits_two_with_json_error(tmp_path):
    code, payload = run(tmp_path, "nope")

    assert code == 2
    assert payload["error"] == "unknown_command"


def test_status_on_empty_repository_is_still_valid_json(tmp_path):
    code, payload = run(tmp_path, "status")

    assert code == 0
    assert payload["journal"]["events"] == 0
    assert payload["bug_bridge"]["pending"] == 0
