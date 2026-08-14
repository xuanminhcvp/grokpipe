"""Read-only inspection CLI for the local runtime bug journal.

`status`, `list` and `show` never mutate the journal, never write the bridge
checkpoint and never invoke `bd`. Only the literal `sync` subcommand may talk to
Beads, and only when the local config explicitly enables `auto-create`.

    python -m sfboard.jobs.bugtool --root . status
    python -m sfboard.jobs.bugtool --root . list [--limit N]
    python -m sfboard.jobs.bugtool --root . show <event-id>
    python -m sfboard.jobs.bugtool --root . sync
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from .beads_bridge import (
    MODE_AUTO_CREATE,
    MODE_JOURNAL_ONLY,
    BeadsBridge,
    BridgeConfig,
    default_state_path,
)
from .runtime_journal import default_journal_path, iter_events, journal_paths
from .runtime_redaction import redact_event


CONFIG_FILENAME = "config.json"
DIAGNOSTIC_KEYS = ("mode", "pending", "last_sync_at", "last_error", "created", "updated")


def config_path(repo_root: str | Path) -> Path:
    return Path(repo_root, ".grokpipe", "runtime-bugs", CONFIG_FILENAME)


def resolve_mode(repo_root: str | Path) -> str:
    """Auto-create requires an explicit local opt-in; anything else is journal-only."""
    try:
        config = json.loads(config_path(repo_root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return MODE_JOURNAL_ONLY
    if isinstance(config, Mapping) and config.get("mode") == MODE_AUTO_CREATE:
        return MODE_AUTO_CREATE
    return MODE_JOURNAL_ONLY


def build_config(repo_root: str | Path, mode: str | None = None) -> BridgeConfig:
    root = Path(repo_root)
    return BridgeConfig(
        repo_root=root,
        journal_path=default_journal_path(root),
        state_path=default_state_path(root),
        mode=mode or resolve_mode(root),
    )


def diagnostics_snapshot(repo_root: str | Path) -> dict[str, object]:
    """Pure projection for `/api/chan-doan`; safe when state is missing or corrupt."""
    try:
        bridge = BeadsBridge(build_config(repo_root))
        health = bridge.health().as_dict()
        return {"bug_bridge": {key: health[key] for key in DIAGNOSTIC_KEYS}}
    except Exception:  # noqa: BLE001 - diagnostics must never break the board
        return {
            "bug_bridge": {
                "mode": MODE_JOURNAL_ONLY,
                "pending": 0,
                "last_sync_at": None,
                "last_error": "",
                "created": 0,
                "updated": 0,
            }
        }


def _read_events(repo_root: Path) -> tuple[list[dict], list[str], list[Path]]:
    errors: list[str] = []
    paths = journal_paths(default_journal_path(repo_root))
    events = list(iter_events(paths, on_error=errors.append))
    return events, errors, paths


def _summary(event: Mapping[str, object]) -> dict[str, object]:
    job = event.get("job") if isinstance(event.get("job"), Mapping) else {}
    exception = event.get("exception") if isinstance(event.get("exception"), Mapping) else {}
    return {
        "event_id": event.get("event_id"),
        "occurred_at": event.get("occurred_at"),
        "severity": event.get("severity"),
        "category": event.get("category"),
        "reason_code": event.get("reason_code"),
        "fingerprint": event.get("fingerprint"),
        "job_kind": job.get("kind"),
        "job_phase": job.get("phase"),
        "exception_type": exception.get("type"),
        "message": exception.get("message"),
    }


def main(
    argv: Sequence[str] | None = None,
    stdout=None,
    run_bd=None,
) -> int:
    parser = argparse.ArgumentParser(prog="bugtool", add_help=True)
    parser.add_argument("--root", default=".")
    parser.add_argument("command", nargs="?", default="status")
    parser.add_argument("event_id", nargs="?", default=None)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args(list(argv) if argv is not None else None)

    stream = stdout if stdout is not None else sys.stdout
    repo_root = Path(args.root).resolve()
    command = args.command

    if command == "status":
        events, errors, paths = _read_events(repo_root)
        health = diagnostics_snapshot(repo_root)["bug_bridge"]
        return _emit(
            stream,
            {
                "command": "status",
                "root": str(repo_root),
                "journal": {
                    "path": str(default_journal_path(repo_root)),
                    "segments": len(paths),
                    "events": len(events),
                    "read_errors": errors[:10],
                },
                "bug_bridge": health,
            },
        )

    if command == "list":
        events, _, _ = _read_events(repo_root)
        limited = events[: max(args.limit, 0)]
        summaries = [_summary(redact_event(item, repo_root)) for item in limited]
        return _emit(
            stream,
            {"command": "list", "count": len(summaries), "events": summaries},
        )

    if command == "show":
        if not args.event_id:
            return _emit(stream, {"command": "show", "error": "event_id_required"}, code=2)
        events, _, _ = _read_events(repo_root)
        for item in events:
            if item.get("event_id") == args.event_id:
                return _emit(
                    stream,
                    {"command": "show", "event": redact_event(item, repo_root)},
                )
        return _emit(
            stream,
            {"command": "show", "error": "event_not_found", "event_id": args.event_id},
            code=2,
        )

    if command == "sync":
        config = build_config(repo_root)
        bridge = BeadsBridge(config, run_bd=run_bd)
        health = bridge.sync_once().as_dict()
        return _emit(
            stream,
            {
                "command": "sync",
                "bug_bridge": {key: health[key] for key in DIAGNOSTIC_KEYS},
                "ok": health["ok"],
            },
            code=0 if health["ok"] else 1,
        )

    return _emit(stream, {"command": command, "error": "unknown_command"}, code=2)


def _emit(stream, payload: Mapping[str, object], code: int = 0) -> int:
    stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    return code


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
