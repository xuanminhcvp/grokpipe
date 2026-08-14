import pytest

from sfboard.jobs.runtime_classifier import classify_signal


@pytest.mark.parametrize(
    "reason",
    ["VALIDATION", "CANCELLED", "EXPECTED_STOP", "QUOTA_RATE_LIMIT"],
)
def test_classifier_ignores_non_reportable_reason(reason):
    assert classify_signal({"reason_code": reason, "severity": "ERROR"}).reportable is False


@pytest.mark.parametrize(
    "reason",
    ["WORKER_CRASH", "RETRY_EXHAUSTED", "INVARIANT_VIOLATION", "QUEUE_STALLED"],
)
def test_classifier_reports_explicit_reportable_reason(reason):
    classification = classify_signal(
        {"reason_code": reason, "category": "runtime", "severity": "CRITICAL"}
    )

    assert classification.reportable is True
    assert classification.reason_code == reason
    assert classification.category == "runtime"
    assert classification.severity == "CRITICAL"


def test_classifier_reports_unknown_reason_only_for_typed_unhandled_exception_context():
    classification = classify_signal(
        {
            "reason_code": "NEW_TYPED_REASON",
            "category": "unhandled_exception",
            "severity": "ERROR",
            "exception": {"type": "RuntimeError", "source_file": "sfboard/worker.py"},
        }
    )

    assert classification.reportable is True
    assert classification.why == "typed_unhandled_exception"


def test_classifier_ignores_unknown_reason_without_typed_exception_context():
    classification = classify_signal(
        {"reason_code": "NEW_TYPED_REASON", "category": "runtime", "severity": "ERROR"}
    )

    assert classification.reportable is False
    assert classification.why == "unknown_reason"
