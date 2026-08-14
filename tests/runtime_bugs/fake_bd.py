"""In-memory stand-in for the `bd` CLI used by bridge contract tests."""

from __future__ import annotations

import json
import subprocess
from collections import deque


class FakeBd:
    """Record every argv and answer create/show/update like Beads 1.2.1 does."""

    def __init__(self):
        self.calls: list[list[str]] = []
        self.issues: dict[str, dict] = {}
        self.failures: deque[str] = deque()
        self._counter = 0

    def fail_next(self, mode: str) -> None:
        """Queue one failure: missing, timeout, nonzero or corrupt."""
        self.failures.append(mode)

    def __call__(self, argv, timeout):
        self.calls.append(list(argv))
        if self.failures:
            mode = self.failures.popleft()
            if mode == "missing":
                raise FileNotFoundError("bd not installed")
            if mode == "timeout":
                raise subprocess.TimeoutExpired(cmd=["bd", *argv], timeout=timeout)
            if mode == "nonzero":
                return _completed(argv, 1, "", "bd: workspace unhealthy")
            if mode == "corrupt":
                return _completed(argv, 0, "{not json", "")
            raise AssertionError(f"unknown failure mode: {mode}")

        command = argv[0]
        if command == "create":
            return _completed(argv, 0, json.dumps(self._create(argv)), "")
        if command == "show":
            issue = self.issues.get(argv[1])
            if issue is None:
                return _completed(argv, 1, "", f"issue not found: {argv[1]}")
            return _completed(argv, 0, json.dumps([issue]), "")
        if command == "update":
            issue = self.issues.get(argv[1])
            if issue is None:
                return _completed(argv, 1, "", f"issue not found: {argv[1]}")
            self._update(issue, argv[2:])
            return _completed(argv, 0, json.dumps(issue), "")
        return _completed(argv, 1, "", f"unsupported command: {command}")

    def _create(self, argv) -> dict:
        options = _options(argv[1:])
        self._counter += 1
        issue_id = f"fake-{self._counter:03d}"
        issue = {
            "id": issue_id,
            "title": options.get("--title", ""),
            "description": options.get("-d", options.get("--description", "")),
            "status": "open",
            "priority": int(options.get("-p", "2")),
            "issue_type": options.get("-t", "task"),
            "labels": sorted(filter(None, options.get("-l", "").split(","))),
            "metadata": json.loads(options.get("--metadata", "{}")),
            "notes": "",
        }
        self.issues[issue_id] = issue
        return issue

    def _update(self, issue: dict, rest) -> None:
        options = _options(rest)
        if "--status" in options:
            issue["status"] = options["--status"]
        if "--append-notes" in options:
            existing = issue.get("notes", "")
            issue["notes"] = f"{existing}\n{options['--append-notes']}".strip()


def _options(argv) -> dict[str, str]:
    options: dict[str, str] = {}
    index = 0
    while index < len(argv):
        token = argv[index]
        if token.startswith("-") and "=" in token:
            name, value = token.split("=", 1)
            options[name] = value
            index += 1
            continue
        if token.startswith("-") and index + 1 < len(argv) and not argv[index + 1].startswith("--"):
            options[token] = argv[index + 1]
            index += 2
            continue
        options[token] = ""
        index += 1
    return options


def _completed(argv, returncode, stdout, stderr):
    return subprocess.CompletedProcess(["bd", *argv], returncode, stdout, stderr)
