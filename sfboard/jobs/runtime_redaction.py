"""Remove sensitive runtime context before it reaches durable storage."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


REDACTED = "<redacted>"
MESSAGE_LIMIT = 2_000
STACKTRACE_LIMIT = 20_000

_CREDENTIAL_KEYS = frozenset(
    {
        "authorization",
        "apikey",
        "accesstoken",
        "refreshtoken",
        "token",
        "secret",
        "password",
        "passwd",
        "cookie",
        "cookies",
        "sessionid",
        "credential",
        "credentials",
        "dsn",
    }
)
_PAYLOAD_KEYS = frozenset(
    {
        "prompt",
        "body",
        "request",
        "response",
        "rawrequest",
        "rawresponse",
        "requestbody",
        "responsebody",
        "base64",
        "imagebase64",
        "mediabase64",
        "media",
        "mediapath",
        "mediaurl",
        "image",
        "imagepath",
        "imageurl",
        "video",
        "videopath",
        "videourl",
        "imagedata",
        "videobytes",
        "mediacontent",
    }
)
_URL = re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.-]*://[^\s'\"<>]+")
_ABSOLUTE_PATH = re.compile(r"(?<![:/A-Za-z0-9])/(?:[^\s'\"<>:,]+(?:/[^\s'\"<>:,]+)*)")
_PATH_PREFIX = re.compile(r"(?<=path:)/(?:[^\s'\"<>:,]+(?:/[^\s'\"<>:,]+)*)", re.I)
_BEARER = re.compile(r"(?i)\bbearer\s+[^\s,;]+")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(authorization|proxy[-_ ]?authorization|session(?:id)?|cookie|api[_-]?key|"
    r"access[_-]?token|refresh[_-]?token|token|password|passwd|secret|dsn)\s*(?:=|:)\s*"
    r"(?:basic\s+)?[^\s,;]+"
)


def redact_event(event: Mapping[str, object], repo_root: str | Path) -> dict[str, object]:
    """Return a new event with secrets, media, unsafe paths, and oversized text removed."""
    return _redact_mapping(event, Path(repo_root).resolve())


def _redact_mapping(value: Mapping[object, object], repo_root: Path) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, child in value.items():
        key_text = str(key)
        normalized = _normalize_key(key_text)
        if _is_credential_key(normalized) or _is_payload_key(normalized):
            result[key_text] = REDACTED
            continue
        result[key_text] = _redact_value(key_text, child, repo_root)
    return result


def _redact_value(key: str, value: object, repo_root: Path) -> object:
    if isinstance(value, Mapping):
        return _redact_mapping(value, repo_root)
    if isinstance(value, list):
        return [_redact_value(key, item, repo_root) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(key, item, repo_root) for item in value)
    if isinstance(value, str):
        text = _redact_text(value, repo_root)
        normalized = _normalize_key(key)
        if normalized == "message":
            return text[:MESSAGE_LIMIT]
        if normalized == "stacktrace":
            return text[:STACKTRACE_LIMIT]
        return text
    return value


def _redact_text(value: str, repo_root: Path) -> str:
    if value.lower().startswith("data:") or ";base64," in value.lower():
        return REDACTED

    sanitized = _URL.sub(_sanitize_url, value)
    sanitized = _BEARER.sub("Bearer <redacted>", sanitized)
    sanitized = _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}=<redacted>", sanitized)
    if Path(sanitized).is_absolute():
        return _sanitize_absolute_path(sanitized, repo_root)
    sanitized = _PATH_PREFIX.sub(
        lambda match: _sanitize_absolute_path(match.group(0), repo_root), sanitized
    )
    return _ABSOLUTE_PATH.sub(
        lambda match: _sanitize_absolute_path(match.group(0), repo_root), sanitized
    )


def _sanitize_url(match: re.Match[str]) -> str:
    raw_url = match.group(0)
    try:
        parsed = urlsplit(raw_url)
        hostname = parsed.hostname
        if not hostname:
            return REDACTED
        netloc = hostname
        if parsed.port is not None:
            netloc = f"{hostname}:{parsed.port}"
        return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))
    except ValueError:
        return REDACTED


def _sanitize_absolute_path(value: str, repo_root: Path) -> str:
    candidate = Path(value)
    if not candidate.is_absolute():
        return value
    resolved = candidate.resolve(strict=False)
    try:
        return resolved.relative_to(repo_root).as_posix()
    except ValueError:
        return candidate.name or "<external>"


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.lower())


def _is_credential_key(key: str) -> bool:
    return key in _CREDENTIAL_KEYS or key.endswith(
        ("token", "secret", "password", "credential", "apikey", "authorization", "cookie")
    )


def _is_payload_key(key: str) -> bool:
    return key in _PAYLOAD_KEYS or key.endswith(("prompt", "body")) or "base64" in key
