"""Version-1 validation and canonical serialization for runtime bug events."""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping
from datetime import datetime, timedelta
from uuid import UUID


class RuntimeBugValidationError(ValueError):
    """Raised when a runtime bug event violates the version-1 contract."""


REQUIRED_TOP_LEVEL = frozenset(
    {
        "schema_version",
        "event_id",
        "occurred_at",
        "severity",
        "category",
        "reason_code",
        "fingerprint",
        "job",
        "runtime",
        "exception",
    }
)
RFC3339_UTC = re.compile(
    r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)\Z"
)


def validate_runtime_bug_event(value: Mapping[str, object]) -> dict[str, object]:
    """Return an independent, validated copy while retaining forward-compatible fields."""
    event = copy.deepcopy(dict(value))
    missing = REQUIRED_TOP_LEVEL.difference(event)
    if missing or type(event.get("schema_version")) is not int or event["schema_version"] != 1:
        raise RuntimeBugValidationError(f"invalid runtime event: missing={sorted(missing)}")

    try:
        UUID(str(event["event_id"]))
        occurred_at = event["occurred_at"]
        if not isinstance(occurred_at, str) or not RFC3339_UTC.fullmatch(occurred_at):
            raise ValueError("occurred_at must be RFC3339 UTC")
        parsed_occurred_at = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
        if parsed_occurred_at.utcoffset() != timedelta(0):
            raise ValueError("occurred_at must use UTC")
    except (TypeError, ValueError) as exc:
        raise RuntimeBugValidationError("event_id and occurred_at must be valid") from exc

    if event["severity"] not in {"ERROR", "CRITICAL"}:
        raise RuntimeBugValidationError("severity must be ERROR or CRITICAL")
    if not all(
        isinstance(event[name], str) and event[name]
        for name in ("category", "reason_code", "fingerprint")
    ):
        raise RuntimeBugValidationError("category/reason_code/fingerprint required")
    return event


def canonical_json(event: Mapping[str, object]) -> str:
    """Serialize a validated runtime bug event deterministically."""
    try:
        return json.dumps(
            validate_runtime_bug_event(event),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise RuntimeBugValidationError("runtime event must be canonical JSON") from exc
