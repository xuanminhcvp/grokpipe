"""Explicit, typed policy for deciding whether a runtime signal is reportable."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


REPORTABLE = frozenset(
    {
        "WORKER_CRASH",
        "RETRY_EXHAUSTED",
        "INVARIANT_VIOLATION",
        "QUEUE_STALLED",
        "SESSION_TRANSIENT",
        "PROVIDER_TRANSIENT",
        "ACCOUNT_LOST",
        "PERMANENT",
        "UNKNOWN_OUTCOME",
    }
)
IGNORED = frozenset(
    {"VALIDATION", "CANCELLED", "EXPECTED_STOP", "NORMAL_RETRY", "QUOTA_RATE_LIMIT", "BRIDGE_ERROR"}
)


@dataclass(frozen=True)
class Classification:
    reportable: bool
    category: str
    reason_code: str
    severity: str
    why: str


def classify_signal(signal: Mapping[str, object]) -> Classification:
    """Classify only typed fields; message content never changes the decision."""
    reason_code = _text(signal.get("reason_code"), "UNKNOWN")
    category = _text(signal.get("category"), "runtime")
    severity = _text(signal.get("severity"), "ERROR")

    if reason_code in IGNORED:
        return Classification(False, category, reason_code, severity, "ignored_reason")
    if reason_code in REPORTABLE:
        return Classification(True, category, reason_code, severity, "reportable_reason")
    if category == "unhandled_exception" and _has_exception_or_source_context(signal):
        return Classification(True, category, reason_code, severity, "typed_unhandled_exception")
    return Classification(False, category, reason_code, severity, "unknown_reason")


def _text(value: object, default: str) -> str:
    if not isinstance(value, str) or not value.strip():
        return default
    return value.strip().upper() if default == "UNKNOWN" else value.strip()


def _has_exception_or_source_context(signal: Mapping[str, object]) -> bool:
    exception = signal.get("exception")
    if isinstance(exception, Mapping) and any(
        exception.get(name) for name in ("type", "source_file", "source_function", "source_line")
    ):
        return True
    return any(signal.get(name) for name in ("source_file", "source_function", "source_line"))
