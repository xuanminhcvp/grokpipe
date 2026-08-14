import copy
import json

import pytest

from sfboard.jobs.runtime_redaction import redact_event


def valid_event(message="worker failed"):
    return {
        "schema_version": 1,
        "event_id": "123e4567-e89b-12d3-a456-426614174000",
        "occurred_at": "2026-08-14T01:02:03Z",
        "severity": "ERROR",
        "category": "unhandled_exception",
        "reason_code": "WORKER_CRASH",
        "fingerprint": "abc123",
        "job": {"job_id": "job-1", "kind": "image", "phase": "submitted"},
        "runtime": {"worker": "local"},
        "exception": {"type": "ValueError", "message": message},
    }


@pytest.mark.parametrize(
    "secret",
    [
        "Bearer abc-secret",
        "sessionid=cookie-secret",
        "password=pw-secret",
        "https://user:pw@example.test/path?token=query-secret#frag",
        "data:image/png;base64,AAAA-secret",
    ],
)
def test_redactor_removes_secret_canaries(secret, tmp_path):
    redacted = redact_event(valid_event(message=secret), repo_root=tmp_path)

    assert "secret" not in json.dumps(redacted)


def test_redactor_scrubs_nested_sensitive_values_without_mutating_input(tmp_path):
    event = valid_event()
    event["runtime"]["credentials"] = {"api_key": "nested-secret"}
    event["exception"]["context"] = [
        {"prompt": "never persist this"},
        {"response_body": "body-secret"},
        {"media_url": "https://example.test/media.mp4"},
    ]
    original = copy.deepcopy(event)

    redacted = redact_event(event, repo_root=tmp_path)

    assert event == original
    assert redacted["runtime"]["credentials"] == "<redacted>"
    assert redacted["exception"]["context"] == [
        {"prompt": "<redacted>"},
        {"response_body": "<redacted>"},
        {"media_url": "<redacted>"},
    ]
    assert "secret" not in json.dumps(redacted)


def test_redactor_sanitizes_urls_paths_and_bounded_text(tmp_path):
    in_repo = tmp_path / "sfboard" / "worker.py"
    in_repo.parent.mkdir()
    in_repo.touch()
    event = valid_event(message="m" * 2_050)
    event["exception"].update(
        {
            "source_file": str(in_repo),
            "outside_path": "/private/worker/profile.json",
            "url": "https://user:pw@example.test/path?token=query-secret#fragment",
            "stacktrace": "s" * 20_050,
        }
    )

    redacted = redact_event(event, repo_root=tmp_path)

    assert redacted["exception"]["source_file"] == "sfboard/worker.py"
    assert redacted["exception"]["outside_path"] == "profile.json"
    assert redacted["exception"]["url"] == "https://example.test/path"
    assert len(redacted["exception"]["message"]) == 2_000
    assert len(redacted["exception"]["stacktrace"]) == 20_000
    assert "secret" not in json.dumps(redacted)


def test_redactor_sanitizes_absolute_paths_embedded_in_stacktrace(tmp_path):
    event = valid_event()
    event["exception"]["stacktrace"] = (
        f'File "{tmp_path}/sfboard/worker.py", line 7\n'
        'File "/private/worker/profile.py", line 9'
    )

    redacted = redact_event(event, repo_root=tmp_path)

    assert str(tmp_path) not in redacted["exception"]["stacktrace"]
    assert "/private/worker/profile.py" not in redacted["exception"]["stacktrace"]
    assert "sfboard/worker.py" in redacted["exception"]["stacktrace"]
    assert "profile.py" in redacted["exception"]["stacktrace"]
