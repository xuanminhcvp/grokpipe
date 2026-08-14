"""Turn durable runtime bug events into local Beads issues.

The bridge is the only component allowed to run the `bd` CLI, and it runs it
with a bounded timeout, no shell, and no remote/provider command. It creates or
updates one issue per fingerprint and never claims, assigns, closes or
reprioritizes an existing issue.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .runtime_journal import iter_events, journal_paths
from .runtime_redaction import redact_event


STATE_FILENAME = "bridge-state.json"
TITLE_LIMIT = 120
DESCRIPTION_LIMIT = 4_000
ERROR_LIMIT = 500
MODE_JOURNAL_ONLY = "journal-only"
MODE_AUTO_CREATE = "auto-create"


class BridgeError(RuntimeError):
    """A `bd` invocation failed; the checkpoint must stay untouched."""


@dataclass(frozen=True)
class BridgeConfig:
    repo_root: Path
    journal_path: Path
    state_path: Path
    mode: str = MODE_JOURNAL_ONLY
    timeout: float = 10.0
    batch_limit: int = 100
    priority: str = "2"
    labels: tuple[str, ...] = ("runtime-bug", "auto-reported")


@dataclass(frozen=True)
class BridgeHealth:
    mode: str
    pending: int
    created: int
    updated: int
    last_sync_at: str | None
    last_error: str
    ok: bool
    total_created: int = 0
    total_updated: int = 0

    def as_dict(self) -> dict[str, object]:
        """Stable projection: `created`/`updated` are cumulative lifetime counters."""
        return {
            "mode": self.mode,
            "pending": self.pending,
            "created": self.total_created,
            "updated": self.total_updated,
            "created_now": self.created,
            "updated_now": self.updated,
            "last_sync_at": self.last_sync_at,
            "last_error": self.last_error,
            "ok": self.ok,
        }


def default_state_path(repo_root: str | Path) -> Path:
    return Path(repo_root, ".grokpipe", "runtime-bugs", STATE_FILENAME)


def run_bd_subprocess(argv: Sequence[str], timeout: float) -> subprocess.CompletedProcess:
    """Run the real `bd` CLI without a shell and with a hard timeout."""
    return subprocess.run(
        ["bd", *argv],
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _default_state() -> dict:
    return {
        "schema_version": 1,
        "processed_event_ids": [],
        "fingerprints": {},
        "health": {"last_sync_at": None, "last_error": "", "created": 0, "updated": 0},
    }


class BeadsBridge:
    """Read the journal once per call and reconcile it with the local Beads DB."""

    def __init__(
        self,
        config: BridgeConfig,
        run_bd: Callable[[Sequence[str], float], subprocess.CompletedProcess] | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.config = config
        self._run_bd = run_bd or run_bd_subprocess
        self._clock = clock or _utc_now

    # -- public API ---------------------------------------------------------

    def sync_once(self) -> BridgeHealth:
        """Process pending events. Never raises; failures are reported as health."""
        state = self._load_state()
        read_errors: list[str] = []
        events = list(
            iter_events(journal_paths(self.config.journal_path), on_error=read_errors.append)
        )
        retained = {
            event.get("event_id")
            for event in events
            if isinstance(event.get("event_id"), str)
        }
        processed = set(state["processed_event_ids"])
        pending = [event for event in events if event.get("event_id") not in processed]

        if self.config.mode != MODE_AUTO_CREATE:
            return self._health(
                state,
                pending=len(pending),
                created=0,
                updated=0,
                last_error=self._join(read_errors),
                ok=not read_errors,
            )

        created = 0
        updated = 0
        last_error = self._join(read_errors)
        dirty = False
        for event in pending[: self.config.batch_limit]:
            event_id = event.get("event_id")
            if not isinstance(event_id, str) or not event_id:
                last_error = "journal event without event_id"
                break
            try:
                outcome = self._apply(event, state)
            except BridgeError as exc:
                last_error = self._sanitize(str(exc))
                break
            if outcome == "created":
                created += 1
            else:
                updated += 1
            processed.add(event_id)
            state["processed_event_ids"] = sorted(processed & (retained | {event_id}))
            state["health"]["created"] += 1 if outcome == "created" else 0
            state["health"]["updated"] += 1 if outcome == "updated" else 0
            state["health"]["last_sync_at"] = self._clock()
            state["health"]["last_error"] = last_error
            self._save_state(state)
            dirty = True

        if dirty:
            state["processed_event_ids"] = sorted(processed & retained)
            state["health"]["last_error"] = last_error
            self._save_state(state)

        return self._health(
            state,
            pending=len(pending) - created - updated,
            created=created,
            updated=updated,
            last_error=last_error,
            ok=not last_error,
        )

    def health(self) -> BridgeHealth:
        """Read-only projection; never runs `bd` and never writes state."""
        state = self._load_state()
        events = list(iter_events(journal_paths(self.config.journal_path)))
        processed = set(state["processed_event_ids"])
        pending = sum(1 for event in events if event.get("event_id") not in processed)
        return self._health(
            state,
            pending=pending,
            created=0,
            updated=0,
            last_error=str(state["health"].get("last_error") or ""),
            ok=not state["health"].get("last_error"),
        )

    # -- issue reconciliation ----------------------------------------------

    def _apply(self, event: Mapping[str, object], state: dict) -> str:
        fingerprint = event.get("fingerprint")
        if not isinstance(fingerprint, str) or not fingerprint:
            raise BridgeError("journal event without fingerprint")
        safe = redact_event(event, self.config.repo_root)
        entry = state["fingerprints"].get(fingerprint)

        if entry is None:
            result = self._run(
                [
                    "create",
                    "--title",
                    _title(safe),
                    "-d",
                    _description(safe, fingerprint, count=1),
                    "-t",
                    "bug",
                    "-p",
                    self.config.priority,
                    "-l",
                    ",".join(self.config.labels),
                    "--metadata",
                    json.dumps({"runtime_fingerprint": fingerprint}, sort_keys=True),
                    "--json",
                ]
            )
            issue_id = _issue_id(result.stdout)
            state["fingerprints"][fingerprint] = {
                "issue_id": issue_id,
                "count": 1,
                "first_event_id": safe.get("event_id"),
                "last_event_id": safe.get("event_id"),
                "last_seen_at": safe.get("occurred_at"),
            }
            return "created"

        issue_id = str(entry.get("issue_id") or "")
        if not issue_id:
            raise BridgeError(f"checkpoint for {fingerprint} has no issue id")
        argv = [
            "update",
            issue_id,
            "--append-notes",
            _note(safe, count=int(entry.get("count", 0)) + 1),
        ]
        if self._is_closed(issue_id):
            argv += ["--status", "open"]
        argv.append("--json")
        self._run(argv)
        entry["count"] = int(entry.get("count", 0)) + 1
        entry["last_event_id"] = safe.get("event_id")
        entry["last_seen_at"] = safe.get("occurred_at")
        return "updated"

    def _is_closed(self, issue_id: str) -> bool:
        result = self._run(["show", issue_id, "--json"])
        try:
            payload = json.loads(result.stdout)
        except ValueError as exc:
            raise BridgeError(f"bd show returned invalid JSON: {exc}") from exc
        if isinstance(payload, list):
            payload = payload[0] if payload else {}
        if not isinstance(payload, Mapping):
            raise BridgeError("bd show returned an unexpected shape")
        return str(payload.get("status") or "").lower() == "closed"

    def _run(self, argv: Sequence[str]) -> subprocess.CompletedProcess:
        try:
            result = self._run_bd(argv, self.config.timeout)
        except FileNotFoundError as exc:
            raise BridgeError(f"bd is not installed: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise BridgeError(f"bd timed out after {self.config.timeout}s") from exc
        except OSError as exc:
            raise BridgeError(f"bd could not be started: {exc}") from exc
        if result.returncode != 0:
            raise BridgeError(f"bd {argv[0]} exited {result.returncode}: {result.stderr.strip()}")
        return result

    # -- state --------------------------------------------------------------

    def _load_state(self) -> dict:
        try:
            raw = self.config.state_path.read_text(encoding="utf-8")
            state = json.loads(raw)
        except (OSError, ValueError):
            return _default_state()
        if not isinstance(state, Mapping) or state.get("schema_version") != 1:
            return _default_state()
        merged = _default_state()
        identifiers = state.get("processed_event_ids")
        if isinstance(identifiers, list):
            merged["processed_event_ids"] = [item for item in identifiers if isinstance(item, str)]
        fingerprints = state.get("fingerprints")
        if isinstance(fingerprints, Mapping):
            merged["fingerprints"] = {
                key: dict(value)
                for key, value in fingerprints.items()
                if isinstance(value, Mapping)
            }
        health = state.get("health")
        if isinstance(health, Mapping):
            merged["health"].update({key: health[key] for key in merged["health"] if key in health})
        return merged

    def _save_state(self, state: Mapping[str, object]) -> None:
        path = self.config.state_path
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".swap",
            delete=False,
        )
        try:
            with handle:
                json.dump(state, handle, ensure_ascii=False, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(handle.name, path)
        except BaseException:
            try:
                os.unlink(handle.name)
            except OSError:
                pass
            raise

    def _health(
        self,
        state: Mapping[str, object],
        pending: int,
        created: int,
        updated: int,
        last_error: str,
        ok: bool,
    ) -> BridgeHealth:
        health = state.get("health") if isinstance(state.get("health"), Mapping) else {}
        return BridgeHealth(
            mode=self.config.mode,
            pending=max(pending, 0),
            created=created,
            updated=updated,
            last_sync_at=health.get("last_sync_at"),
            last_error=self._sanitize(last_error),
            ok=ok,
            total_created=_count(health.get("created")),
            total_updated=_count(health.get("updated")),
        )

    def _join(self, errors: Sequence[str]) -> str:
        return self._sanitize("; ".join(errors))

    def _sanitize(self, message: str) -> str:
        if not message:
            return ""
        cleaned = redact_event({"message": message}, self.config.repo_root)["message"]
        return str(cleaned).replace("\n", " ")[:ERROR_LIMIT]


# -- payload shaping --------------------------------------------------------


def _title(event: Mapping[str, object]) -> str:
    job = _mapping(event.get("job"))
    exception = _mapping(event.get("exception"))
    parts = [
        str(event.get("reason_code") or "UNKNOWN"),
        str(exception.get("type") or "Error"),
        f"{job.get('kind') or '?'}/{job.get('phase') or '?'}",
    ]
    return _one_line(f"[runtime] {' · '.join(parts)}")[:TITLE_LIMIT]


def _description(event: Mapping[str, object], fingerprint: str, count: int) -> str:
    job = _mapping(event.get("job"))
    exception = _mapping(event.get("exception"))
    lines = [
        "Auto-reported by the grokpipe runtime bug journal (local only).",
        "",
        f"- fingerprint: {fingerprint}",
        f"- severity: {event.get('severity')}",
        f"- category: {event.get('category')}",
        f"- reason_code: {event.get('reason_code')}",
        f"- job: kind={job.get('kind')} phase={job.get('phase')} id={job.get('job_id')}",
        f"- source: {exception.get('source_file')}:{exception.get('source_line')}"
        f" in {exception.get('source_function')}",
        f"- exception: {exception.get('type')}",
        f"- message: {_one_line(str(exception.get('message') or ''))}",
        f"- occurrences: {count}",
        f"- first seen: {event.get('occurred_at')}",
        "",
        "Payload is redacted: no prompt, credential, URL query, or media content is stored.",
    ]
    return "\n".join(lines)[:DESCRIPTION_LIMIT]


def _note(event: Mapping[str, object], count: int) -> str:
    return _one_line(
        f"seen again at {event.get('occurred_at')} "
        f"(event {event.get('event_id')}, occurrence {count})"
    )[:TITLE_LIMIT * 2]


def _issue_id(stdout: str) -> str:
    try:
        payload = json.loads(stdout)
    except ValueError as exc:
        raise BridgeError(f"bd create returned invalid JSON: {exc}") from exc
    if isinstance(payload, list):
        payload = payload[0] if payload else {}
    issue_id = payload.get("id") if isinstance(payload, Mapping) else None
    if not isinstance(issue_id, str) or not issue_id:
        raise BridgeError("bd create returned no issue id")
    return issue_id


def _count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _one_line(text: str) -> str:
    return " ".join(text.split())
