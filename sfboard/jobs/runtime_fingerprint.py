"""Stable fingerprints for deduplicating sanitized runtime bug events."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping


_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
_PORT = re.compile(r"(?<![A-Za-z0-9_]):\d{1,5}\b")
_TIMESTAMP = re.compile(
    r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?\b"
)
_CLOCK_TIME = re.compile(r"\b(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?\b")
_RETRY_DELAY = re.compile(r"\b(retry\s+after\s+)\d+(\s+seconds?\b)", re.I)
_IDENTIFIER = re.compile(
    r"\b(?:job|attempt|execution)(?:[_ -]?id)?\s*(?:=|:|#|\s+)\s*"
    r"(?!(?:failed|failure|crashed|stalled|cancelled|started|completed)\b)[a-z0-9][a-z0-9_-]*\b",
    re.I,
)
_WHITESPACE = re.compile(r"\s+")


def fingerprint_event(event: Mapping[str, object]) -> str:
    """Hash the canonical failure tuple while discarding volatile message identifiers."""
    job = _mapping(event.get("job"))
    exception = _mapping(event.get("exception"))
    parts = (
        _string(exception.get("type")),
        _string(event.get("reason_code")),
        _string(job.get("kind")),
        _string(job.get("phase")),
        _string(exception.get("source_file")),
        _string(exception.get("source_function")),
        _string(exception.get("source_line")),
        normalize_message(_string(exception.get("message"))),
    )
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def normalize_message(message: str) -> str:
    """Convert volatile runtime values into stable placeholders for deduplication."""
    normalized = _UUID.sub("<uuid>", message)
    normalized = _TIMESTAMP.sub("<timestamp>", normalized)
    normalized = _CLOCK_TIME.sub("<time>", normalized)
    normalized = _RETRY_DELAY.sub(r"\1<delay>\2", normalized)
    normalized = _PORT.sub(":<port>", normalized)
    normalized = _IDENTIFIER.sub("<identifier>", normalized)
    return _WHITESPACE.sub(" ", normalized).strip()


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _string(value: object) -> str:
    return "" if value is None else str(value)
