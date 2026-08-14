from sfboard.jobs.runtime_fingerprint import fingerprint_event


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
        "exception": {
            "type": "ValueError",
            "message": message,
            "source_file": "sfboard/worker.py",
            "source_function": "run",
            "source_line": 42,
        },
    }


def test_fingerprint_ignores_uuid_port_and_timestamp_but_not_phase():
    left = valid_event(
        message="job 123e4567-e89b-12d3-a456-426614174000 failed at :9222 12:30:11"
    )
    right = valid_event(
        message="job 223e4567-e89b-12d3-a456-426614174999 failed at :9333 13:31:12"
    )

    assert fingerprint_event(left) == fingerprint_event(right)
    right["job"]["phase"] = "downloading"
    assert fingerprint_event(left) != fingerprint_event(right)


def test_fingerprint_changes_when_source_location_or_error_type_changes():
    event = valid_event(message="fixed failure")
    different_type = valid_event(message="fixed failure")
    different_source = valid_event(message="fixed failure")
    different_line = valid_event(message="fixed failure")
    different_type["exception"]["type"] = "TimeoutError"
    different_source["exception"]["source_file"] = "sfboard/other_worker.py"
    different_line["exception"]["source_line"] = 43

    assert fingerprint_event(event) != fingerprint_event(different_type)
    assert fingerprint_event(event) != fingerprint_event(different_source)
    assert fingerprint_event(event) != fingerprint_event(different_line)


def test_fingerprint_ignores_retry_delay_alphabetic_job_id_and_one_digit_port():
    left = valid_event(message="job alpha retry after 12 seconds at :7")
    right = valid_event(message="job beta retry after 13 seconds at :8")

    assert fingerprint_event(left) == fingerprint_event(right)


def test_fingerprint_preserves_error_codes_in_messages():
    not_found = valid_event(message="provider returned status:404")
    unavailable = valid_event(message="provider returned status:500")

    assert fingerprint_event(not_found) != fingerprint_event(unavailable)
