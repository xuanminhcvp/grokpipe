"""Durable JSONL journal for severe runtime bug events.

The journal owns one dedicated Loguru handler. It never touches the root
``logging`` handlers, never calls the global ``logger.remove()``, and never
raises into the production caller: ``record`` returns ``False`` instead.
"""

from __future__ import annotations

import json
import sys
import uuid
from collections.abc import Callable, Iterable, Iterator, Mapping
from pathlib import Path

from loguru import logger

from .runtime_bug import RuntimeBugValidationError, canonical_json
from .runtime_fingerprint import fingerprint_event
from .runtime_redaction import redact_event


JOURNAL_DIRNAME = "runtime-bugs"
JOURNAL_FILENAME = "events.jsonl"
STDERR_LINE_LIMIT = 512


def _private_logger():
    """Một Loguru core RIÊNG cho sổ lỗi.

    Dùng chung `loguru.logger` thì sink stderr mặc định (handler 0) cũng nhận
    mọi bản ghi và in nguyên cục JSON ra Terminal của board. Không được xoá
    handler 0 (luật: không bao giờ gọi `logger.remove()` toàn cục), nên cách
    sạch là tự dựng core riêng. Hỏng thì lùi về logger chung — mất sự yên tĩnh
    chứ không mất sổ."""
    try:
        from loguru._logger import Core, Logger

        return Logger(Core(), None, 0, False, False, False, False, True, [], {})
    except Exception:  # noqa: BLE001 - loguru đổi API thì vẫn phải ghi được sổ
        return logger


JOURNAL_LOGGER = _private_logger()


def default_journal_path(repo_root: str | Path) -> Path:
    """Return the only supported on-disk journal location for a repository."""
    return Path(repo_root, ".grokpipe", JOURNAL_DIRNAME, JOURNAL_FILENAME)


class RuntimeBugJournal:
    """Append redacted, canonical runtime bug events to a rotating JSONL file."""

    def __init__(
        self,
        path: str | Path,
        repo_root: str | Path,
        stderr: object | None = None,
    ) -> None:
        self.path = Path(path)
        self.repo_root = Path(repo_root)
        self.journal_id = uuid.uuid4().hex
        self._stderr = stderr if stderr is not None else sys.stderr
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handler_id: int | None = JOURNAL_LOGGER.add(
            str(self.path),
            rotation="10 MB",
            retention=10,
            compression=None,
            enqueue=False,
            serialize=False,
            backtrace=True,
            diagnose=False,
            catch=True,
            filter=self._accepts,
            format="{message}",
            encoding="utf-8",
            buffering=1,
        )

    def _accepts(self, record: Mapping[str, object]) -> bool:
        extra = record.get("extra")
        if not isinstance(extra, Mapping):
            return False
        return (
            extra.get("runtime_bug") is True
            and extra.get("journal_id") == self.journal_id
        )

    def record(self, event: object) -> bool:
        """Redact, fingerprint and persist one event. Never raises to the caller."""
        try:
            if not isinstance(event, Mapping):
                raise RuntimeBugValidationError("runtime event must be a mapping")
            redacted = redact_event(event, self.repo_root)
            redacted["fingerprint"] = fingerprint_event(redacted)
            payload = canonical_json(redacted)
            severity = redacted.get("severity")
            level = severity if severity in {"ERROR", "CRITICAL"} else "ERROR"
            JOURNAL_LOGGER.bind(runtime_bug=True, journal_id=self.journal_id).log(level, payload)
            return True
        except Exception as exc:  # noqa: BLE001 - journaling must never break a job
            self._warn(f"runtime bug journal dropped one event: {type(exc).__name__}: {exc}")
            return False

    def close(self) -> None:
        """Remove only this journal's handler; safe to call more than once."""
        handler_id, self._handler_id = self._handler_id, None
        if handler_id is None:
            return
        try:
            JOURNAL_LOGGER.remove(handler_id)
        except ValueError:
            pass

    def _warn(self, message: str) -> None:
        try:
            self._stderr.write(message[:STDERR_LINE_LIMIT].replace("\n", " ") + "\n")
            self._stderr.flush()
        except Exception:  # noqa: BLE001 - a broken stderr must stay silent
            pass


def journal_paths(path: str | Path) -> list[Path]:
    """Return rotated segments in chronological order followed by the live file."""
    live = Path(path)
    parent = live.parent
    if not parent.is_dir():
        return []
    rotated = sorted(
        candidate
        for candidate in parent.glob(f"{live.stem}.*{live.suffix}")
        if candidate != live and candidate.is_file()
    )
    return [*rotated, live] if live.is_file() else rotated


def iter_events(
    paths: Iterable[str | Path],
    on_error: Callable[[str], None] | None = None,
) -> Iterator[dict]:
    """Yield complete JSON records, skipping only a truncated crash tail."""
    for raw_path in paths:
        path = Path(raw_path)
        try:
            handle = path.open("r", encoding="utf-8", errors="replace")
        except OSError as exc:
            _report(on_error, f"{path}: unreadable journal segment: {exc}")
            continue
        with handle:
            for number, line in enumerate(handle, start=1):
                if not line.endswith("\n"):
                    # Crash tail: the process died mid-write. Skip without rewriting.
                    break
                text = line.strip()
                if not text:
                    continue
                try:
                    parsed = json.loads(text)
                except ValueError as exc:
                    _report(on_error, f"{path}:{number}: malformed journal line: {exc}")
                    continue
                if isinstance(parsed, dict):
                    yield parsed
                else:
                    _report(on_error, f"{path}:{number}: journal line is not an object")


def _report(on_error: Callable[[str], None] | None, message: str) -> None:
    if on_error is None:
        return
    try:
        on_error(message)
    except Exception:  # noqa: BLE001 - health reporting must never break reading
        pass
