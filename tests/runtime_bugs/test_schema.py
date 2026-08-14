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


@pytest.mark.parametrize(
    "occurred_at",
    [
        "2026-08-14",
        "2026-08-14T01:02:03",
        "2026-08-14T01:02:03+07:00",
    ],
)
def test_schema_rejects_non_utc_or_incomplete_rfc3339_timestamp(occurred_at):
    event = valid_event()
    event["occurred_at"] = occurred_at

    with pytest.raises(RuntimeBugValidationError):
        validate_runtime_bug_event(event)


@pytest.mark.parametrize("occurred_at", ["2026-08-14T01:02:03Z", "2026-08-14T01:02:03+00:00"])
def test_schema_accepts_rfc3339_utc_timestamp(occurred_at):
    event = valid_event()
    event["occurred_at"] = occurred_at

    assert validate_runtime_bug_event(event)["occurred_at"] == occurred_at


def test_schema_rejects_invalid_uuid_with_canonical_validation_error():
    event = valid_event()
    event["event_id"] = "not-a-uuid"

    with pytest.raises(RuntimeBugValidationError):
        validate_runtime_bug_event(event)


def test_schema_rejects_boolean_schema_version():
    event = valid_event()
    event["schema_version"] = True

    with pytest.raises(RuntimeBugValidationError):
        validate_runtime_bug_event(event)


@pytest.mark.parametrize("non_finite", [float("nan"), float("inf"), float("-inf")])
def test_canonical_json_rejects_non_finite_numbers(non_finite):
    event = valid_event()
    event["exception"]["value"] = non_finite

    with pytest.raises(RuntimeBugValidationError):
        canonical_json(event)
