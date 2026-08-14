"""Version-1 validation and canonical serialization for runtime bug events."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from datetime import datetime
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


def validate_runtime_bug_event(value: Mapping[str, object]) -> dict[str, object]:
    """Return an independent, validated copy while retaining forward-compatible fields."""
    event = copy.deepcopy(dict(value))
    missing = REQUIRED_TOP_LEVEL.difference(event)
    if missing or type(event.get("schema_version")) is not int or event["schema_version"] != 1:
        raise RuntimeBugValidationError(f"invalid runtime event: missing={sorted(missing)}")

    try:
        UUID(str(event["event_id"]))
        datetime.fromisoformat(str(event["occurred_at"]).replace("Z", "+00:00"))
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
    return json.dumps(
        validate_runtime_bug_event(event),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
