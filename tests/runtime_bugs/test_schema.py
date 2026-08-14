import pytest

from sfboard.jobs.runtime_bug import (
    RuntimeBugValidationError,
    canonical_json,
    validate_runtime_bug_event,
)


def valid_event():
    return {
        "schema_version": 1,
        "event_id": "123e4567-e89b-12d3-a456-426614174000",
        "occurred_at": "2026-08-14T01:02:03Z",
        "severity": "ERROR",
        "category": "runtime",
        "reason_code": "unexpected_error",
        "fingerprint": "abc123",
        "job": {"job_id": "job-1"},
        "runtime": {"worker": "local"},
        "exception": {"type": "ValueError"},
    }


def test_schema_rejects_missing_required_field():
    event = valid_event()
    del event["reason_code"]

    with pytest.raises(RuntimeBugValidationError):
        validate_runtime_bug_event(event)


def test_schema_accepts_unknown_future_field_and_preserves_nulls():
    event = valid_event()
    event["future_field"] = {"enabled": True}
    event["job"]["attempt_id"] = None

    validated = validate_runtime_bug_event(event)

    assert validated["future_field"] == {"enabled": True}
    assert validated["job"]["attempt_id"] is None


def test_canonical_json_is_sorted_compact_and_preserves_unicode():
    event = valid_event()
    event["category"] = "lỗi"

    assert canonical_json(event) == (
        '{"category":"lỗi","event_id":"123e4567-e89b-12d3-a456-426614174000",'
        '"exception":{"type":"ValueError"},"fingerprint":"abc123",'
        '"job":{"job_id":"job-1"},"occurred_at":"2026-08-14T01:02:03Z",'
        '"reason_code":"unexpected_error","runtime":{"worker":"local"},'
        '"schema_version":1,"severity":"ERROR"}'
    )
