# Runtime Bug Journal and Beads Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist severe image/video runtime evidence as redacted JSONL and optionally create or update one local Bead per fingerprint without changing production job outcomes.

**Architecture:** Pure schema, redaction, fingerprint, and classification modules feed a dedicated Loguru-backed journal. A separate bridge service reads durable events and invokes only the `bd` CLI with bounded timeouts; production defaults to journal-only and sees a no-throw reporter interface. The legacy `JOBS`, `PriorityQueue`, retry, account, worker, and UI error-book paths remain authoritative and unchanged.

**Tech Stack:** Python 3.10+, Loguru 0.7.3, stdlib dataclasses/JSON/hashlib/subprocess/threading, existing pytest/pytest-cov lifecycle gate, Beads 1.2.1.

## Global Constraints

- Pin exactly `loguru==0.7.3`; do not install similarly named packages.
- Keep Python `logging`, `LOI_SO`, `VET`, root handlers, queue behavior, retry behavior, account rotation, and lifecycle state behavior unchanged.
- Never call global `logger.remove()`; each journal removes only its own handler ID.
- Loguru sink settings are exactly `rotation="10 MB"`, `retention=10`, `compression=None`, `enqueue=False`, `serialize=False`, `backtrace=True`, `diagnose=False`, `catch=True`, with a filter requiring `runtime_bug=True`.
- Journal, bridge state, locks, and runtime logs live only under `.grokpipe/runtime-bugs/` and are Git-ignored by `.grokpipe/.gitignore`.
- Redact before journal serialization and before Beads payload creation. Never persist prompt, raw request/response, cookie, token, password, DSN, base64, image, or video content.
- Runtime paths may call only a no-throw reporter. `bd` subprocesses run only in the bridge worker or explicit CLI sync command, never in image/video workers or HTTP request handlers.
- `bd` missing, timeout, invalid JSON, non-zero exit, or unhealthy workspace must leave the checkpoint unchanged and must not alter job outcome.
- Default mode is `journal-only`. `auto-create` requires explicit local configuration and passing foundation checks. No remote sync/provider/GitHub Issue action.
- Bridge never claims, assigns, closes, or changes priority of an existing Bead. It may reopen a closed matching fingerprint as specified.
- No live Chrome/provider/network/credit test. Commit message is `update`; stage exact paths only.
- Full lifecycle gate must remain `30 passed, 5 xfailed`, coverage at least 80%, compile pass.

---

## File Map

- Create: `requirements-runtime.txt` — pinned runtime-only dependencies.
- Modify: `requirements-test.txt` — include runtime requirements for CI tests.
- Create: `.grokpipe/.gitignore` — ignore only `runtime-bugs/` local state.
- Create: `sfboard/jobs/runtime_bug.py` — schema validation, typed reason/severity/category, canonical serialization.
- Create: `sfboard/jobs/runtime_redaction.py` — secret/path/URL/media redaction and size limits.
- Create: `sfboard/jobs/runtime_fingerprint.py` — normalization and SHA-256 fingerprint.
- Create: `sfboard/jobs/runtime_classifier.py` — explicit typed report/ignore decisions.
- Create: `sfboard/jobs/runtime_journal.py` — dedicated Loguru JSONL sink, recovery, reader.
- Create: `sfboard/jobs/beads_bridge.py` — durable checkpoint, dedupe, payload, `bd` subprocess adapter, health.
- Create: `sfboard/jobs/bugtool.py` — read-only status/list/show and explicit sync CLI.
- Create: `sfboard/jobs/runtime_service.py` — no-throw facade, logging adapter, bridge daemon lifecycle.
- Modify: `sfboard/sfboard.py` — initialize/shutdown service, worker boundary signal, diagnostics projection only.
- Test: `tests/runtime_bugs/` — unit, contract, integration, and legacy-boundary tests.

### Task 1: Runtime dependency, schema, and canonical event contract

**Files:**
- Create: `requirements-runtime.txt`
- Modify: `requirements-test.txt`
- Create: `.grokpipe/.gitignore`
- Create: `sfboard/jobs/runtime_bug.py`
- Create: `tests/runtime_bugs/__init__.py`
- Create: `tests/runtime_bugs/test_schema.py`

**Interfaces:**
- Produces: `RuntimeBugValidationError`, `validate_runtime_bug_event(value: Mapping[str, object]) -> dict[str, object]`, `canonical_json(event: Mapping[str, object]) -> str`.
- Required top-level fields: `schema_version`, `event_id`, `occurred_at`, `severity`, `category`, `reason_code`, `fingerprint`, `job`, `runtime`, `exception`.

- [ ] **Step 1: Add failing schema tests**

```python
def test_schema_rejects_missing_required_field():
    event = valid_event()
    del event["reason_code"]
    with pytest.raises(RuntimeBugValidationError):
        validate_runtime_bug_event(event)

def test_schema_accepts_unknown_future_field_and_preserves_nulls():
    event = valid_event()
    event["future_field"] = {"enabled": True}
    event["job"]["attempt_id"] = None
    validated = validate_runtime_bug_event(event)
    assert validated["future_field"] == {"enabled": True}
    assert validated["job"]["attempt_id"] is None
```

- [ ] **Step 2: Run RED**

Run: `./.venv/bin/python3 -m pytest tests/runtime_bugs/test_schema.py -q`

Expected: collection/import fails because `sfboard.jobs.runtime_bug` does not exist.

- [ ] **Step 3: Add dependency and storage declarations**

```text
# requirements-runtime.txt
loguru==0.7.3

# requirements-test.txt
-r requirements-runtime.txt
pytest==9.1.1
pytest-cov==7.1.0

# .grokpipe/.gitignore
runtime-bugs/
```

- [ ] **Step 4: Implement strict version-1 validation and deterministic JSON**

```python
class RuntimeBugValidationError(ValueError):
    pass

REQUIRED_TOP_LEVEL = frozenset({
    "schema_version", "event_id", "occurred_at", "severity", "category",
    "reason_code", "fingerprint", "job", "runtime", "exception",
})

def validate_runtime_bug_event(value: Mapping[str, object]) -> dict[str, object]:
    event = copy.deepcopy(dict(value))
    missing = REQUIRED_TOP_LEVEL.difference(event)
    if missing or event.get("schema_version") != 1:
        raise RuntimeBugValidationError(f"invalid runtime event: missing={sorted(missing)}")
    UUID(str(event["event_id"]))
    datetime.fromisoformat(str(event["occurred_at"]).replace("Z", "+00:00"))
    if event["severity"] not in {"ERROR", "CRITICAL"}:
        raise RuntimeBugValidationError("severity must be ERROR or CRITICAL")
    if not all(isinstance(event[name], str) and event[name] for name in
               ("category", "reason_code", "fingerprint")):
        raise RuntimeBugValidationError("category/reason_code/fingerprint required")
    return event

def canonical_json(event: Mapping[str, object]) -> str:
    return json.dumps(validate_runtime_bug_event(event), ensure_ascii=False,
                      sort_keys=True, separators=(",", ":"))
```

- [ ] **Step 5: Run GREEN and dependency audit**

Run:

```bash
./.venv/bin/python3 -m pip install -r requirements-test.txt
./.venv/bin/python3 -m pytest tests/runtime_bugs/test_schema.py -q
./.venv/bin/python3 -m pip show loguru
git check-ignore -v .grokpipe/runtime-bugs/events.jsonl
```

Expected: schema tests pass; Loguru version is 0.7.3; runtime journal path is ignored.

- [ ] **Step 6: Commit exact paths**

```bash
git add requirements-runtime.txt requirements-test.txt .grokpipe/.gitignore sfboard/jobs/runtime_bug.py tests/runtime_bugs/__init__.py tests/runtime_bugs/test_schema.py
git commit -m "update"
```

### Task 2: Redaction, classifier, and fingerprint

**Files:**
- Create: `sfboard/jobs/runtime_redaction.py`
- Create: `sfboard/jobs/runtime_classifier.py`
- Create: `sfboard/jobs/runtime_fingerprint.py`
- Test: `tests/runtime_bugs/test_redaction.py`
- Test: `tests/runtime_bugs/test_classifier.py`
- Test: `tests/runtime_bugs/test_fingerprint.py`

**Interfaces:**
- Produces: `redact_event(event, repo_root) -> dict`, `classify_signal(signal) -> Classification`, `fingerprint_event(event) -> str`.
- `Classification` fields: `reportable: bool`, `category: str`, `reason_code: str`, `severity: str`, `why: str`.

- [ ] **Step 1: Write canary and classifier RED tests**

```python
@pytest.mark.parametrize("secret", [
    "Bearer abc-secret", "sessionid=cookie-secret", "password=pw-secret",
    "https://user:pw@example.test/path?token=query-secret#frag",
    "data:image/png;base64,AAAA-secret",
])
def test_redactor_removes_secret_canaries(secret, tmp_path):
    redacted = redact_event(valid_event(message=secret), repo_root=tmp_path)
    assert "secret" not in json.dumps(redacted)

@pytest.mark.parametrize("reason", ["VALIDATION", "CANCELLED", "EXPECTED_STOP", "QUOTA_RATE_LIMIT"])
def test_classifier_ignores_non_reportable_reason(reason):
    assert classify_signal({"reason_code": reason, "severity": "ERROR"}).reportable is False

def test_fingerprint_ignores_uuid_port_and_timestamp_but_not_phase():
    left = valid_event(message="job 123e4567-e89b-12d3-a456-426614174000 failed at :9222 12:30:11")
    right = valid_event(message="job 223e4567-e89b-12d3-a456-426614174999 failed at :9333 13:31:12")
    assert fingerprint_event(left) == fingerprint_event(right)
    right["job"]["phase"] = "downloading"
    assert fingerprint_event(left) != fingerprint_event(right)
```

- [ ] **Step 2: Run RED**

Run: `./.venv/bin/python3 -m pytest tests/runtime_bugs/test_redaction.py tests/runtime_bugs/test_classifier.py tests/runtime_bugs/test_fingerprint.py -q`

- [ ] **Step 3: Implement bounded recursive redaction**

Rules implemented in one traversal: redact credential keys; remove URL query/fragment/userinfo; replace in-repo absolute paths with repo-relative paths and outside paths with basename or `<external>`; replace prompt/body/base64/media fields with `<redacted>`; truncate message to 2,000 characters and stacktrace to 20,000 characters.

- [ ] **Step 4: Implement explicit classifier tables**

```python
REPORTABLE = {
    "WORKER_CRASH", "RETRY_EXHAUSTED", "INVARIANT_VIOLATION", "QUEUE_STALLED",
    "SESSION_TRANSIENT", "PROVIDER_TRANSIENT", "ACCOUNT_LOST", "PERMANENT",
    "UNKNOWN_OUTCOME",
}
IGNORED = {"VALIDATION", "CANCELLED", "EXPECTED_STOP", "NORMAL_RETRY", "QUOTA_RATE_LIMIT", "BRIDGE_ERROR"}
```

Unknown reason codes are ignored unless the typed category is `unhandled_exception` with an exception/source context.

- [ ] **Step 5: Implement canonical fingerprint tuple**

```python
parts = (
    exception["type"], event["reason_code"], job["kind"], job["phase"],
    exception["source_file"], exception["source_function"],
    str(exception["source_line"]), normalize_message(exception["message"]),
)
return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
```

- [ ] **Step 6: Run GREEN and commit**

Run: `./.venv/bin/python3 -m pytest tests/runtime_bugs/test_redaction.py tests/runtime_bugs/test_classifier.py tests/runtime_bugs/test_fingerprint.py -q`

Commit exact new files with `git commit -m "update"`.

### Task 3: Dedicated Loguru journal and crash-tail recovery

**Files:**
- Create: `sfboard/jobs/runtime_journal.py`
- Test: `tests/runtime_bugs/test_journal.py`

**Interfaces:**
- Produces: `RuntimeBugJournal(path: Path, repo_root: Path)`, `record(event) -> bool`, `close() -> None`, `iter_events(paths) -> Iterator[dict]`.
- `record` must never raise to its caller.

- [ ] **Step 1: Write RED tests for exact sink options, secret-free JSONL, concurrency, rotation, and truncated last line**

Tests monkeypatch `loguru.logger.add` to capture exact options; use 20 threads × 25 events and assert 500 parseable unique JSON lines; append a partial final object and assert the reader skips only that tail while preserving complete lines.

- [ ] **Step 2: Run RED**

Run: `./.venv/bin/python3 -m pytest tests/runtime_bugs/test_journal.py -q`

- [ ] **Step 3: Implement the dedicated sink**

```python
self._handler_id = logger.add(
    str(path), rotation="10 MB", retention=10, compression=None,
    enqueue=False, serialize=False, backtrace=True, diagnose=False, catch=True,
    filter=lambda record: record["extra"].get("runtime_bug") is True,
    format="{message}", encoding="utf-8", buffering=1,
)
```

`record` validates, redacts, fingerprints, serializes, then calls only `logger.bind(runtime_bug=True).log(severity, payload)`. On failure it emits one bounded line directly to injected stderr and returns `False`. `close` removes only `self._handler_id`.

- [ ] **Step 4: Implement reader recovery**

Read complete newline-terminated records in deterministic rotated-file order. A malformed complete line is yielded as a health error to the bridge; a non-newline-terminated final line is treated as a crash tail and skipped without rewriting the journal.

- [ ] **Step 5: Run GREEN and commit**

Run: `./.venv/bin/python3 -m pytest tests/runtime_bugs/test_journal.py -q`

Commit `runtime_journal.py` and `test_journal.py` with message `update`.

### Task 4: Beads bridge, checkpoint, dedupe, and fake CLI contracts

**Files:**
- Create: `sfboard/jobs/beads_bridge.py`
- Test: `tests/runtime_bugs/test_beads_bridge.py`
- Test helper: `tests/runtime_bugs/fake_bd.py`

**Interfaces:**
- Produces: `BridgeConfig`, `BridgeHealth`, `BeadsBridge.sync_once() -> BridgeHealth`, atomic `bridge-state.json`.
- Injected runner signature: `run_bd(argv: Sequence[str], timeout: float) -> CompletedProcess[str]`.

- [ ] **Step 1: Write RED fake-CLI contracts**

Cover: ten same-fingerprint events create once/update count to ten; distinct fingerprint creates separately; restart does not replay acked IDs; missing/timeout/non-zero/corrupt JSON preserves state file byte-for-byte; closed matching Bead is reopened; bridge failure creates no recursive journal event; payload contains no canary secret.

- [ ] **Step 2: Run RED**

Run: `./.venv/bin/python3 -m pytest tests/runtime_bugs/test_beads_bridge.py -q`

- [ ] **Step 3: Implement atomic local state**

```json
{
  "schema_version": 1,
  "processed_event_ids": [],
  "fingerprints": {},
  "health": {"last_sync_at": null, "last_error": "", "created": 0, "updated": 0}
}
```

Write to a sibling temporary file, `flush` + `os.fsync`, then `os.replace`. Persist only after the related `bd` command succeeds. Keep every event ID retained by the current journal segments so a restart cannot double-count.

- [ ] **Step 4: Implement bounded subprocess and payload mapping**

The real runner uses `subprocess.run(["bd", *argv], text=True, capture_output=True, timeout=10, check=False)` with no shell. Create/update/reopen use explicit issue IDs, exact labels, JSON output, sanitized title/description, and metadata fingerprint. Existing issues are never claimed/assigned/closed/reprioritized.

- [ ] **Step 5: Implement backoff health without hot loop**

`sync_once` returns sanitized health. The daemon caller owns exponential backoff capped at 300 seconds with injected jitter; a failed event leaves its ID absent from checkpoint and stops the batch.

- [ ] **Step 6: Run GREEN and commit**

Run: `./.venv/bin/python3 -m pytest tests/runtime_bugs/test_beads_bridge.py -q`

Commit exact bridge/test/helper paths with message `update`.

### Task 5: Local bug CLI and diagnostics contract

**Files:**
- Create: `sfboard/jobs/bugtool.py`
- Test: `tests/runtime_bugs/test_bugtool.py`
- Test: `tests/runtime_bugs/test_diagnostics.py`

**Interfaces:**
- CLI: `python -m sfboard.jobs.bugtool --root <repo> status|list|show <event-id>|sync`.
- Output: one stable JSON object to stdout; diagnostics shape is `{"bug_bridge": {"mode", "pending", "last_sync_at", "last_error", "created", "updated"}}`.

- [ ] **Step 1: Write RED CLI tests**

Assert status/list/show never mutate journal/checkpoint; unknown event exits 2 with JSON error; explicit sync invokes injected bridge once; output contains no secret canary.

- [ ] **Step 2: Implement CLI with no implicit sync**

`status`, `list`, and `show` are read-only. Only the literal `sync` subcommand may call `BeadsBridge.sync_once`; it still obeys local mode and never invokes remote commands.

- [ ] **Step 3: Add diagnostics projection tests and helper**

Expose a pure `diagnostics_snapshot() -> dict` from the runtime service boundary; it must return defaults when state is missing/corrupt and sanitize `last_error`.

- [ ] **Step 4: Run GREEN and commit**

Run: `./.venv/bin/python3 -m pytest tests/runtime_bugs/test_bugtool.py tests/runtime_bugs/test_diagnostics.py -q`

Commit exact paths with message `update`.

### Task 6: Runtime service facade and journal-only legacy instrumentation

**Files:**
- Create: `sfboard/jobs/runtime_service.py`
- Modify: `sfboard/sfboard.py`
- Modify: `tests/job_lifecycle/test_http_contract.py`
- Create: `tests/runtime_bugs/test_runtime_service.py`
- Create: `tests/runtime_bugs/test_legacy_instrumentation.py`

**Interfaces:**
- Produces: `start_runtime_bug_service(repo_root, mode="journal-only")`, `report_runtime_bug(signal) -> bool`, `runtime_bug_diagnostics() -> dict`, `stop_runtime_bug_service()`.
- All facade calls are safe before start, after stop, and under internal exceptions.

- [ ] **Step 1: Write RED no-throw and logging-adapter tests**

Assert ERROR/CRITICAL records are journaled only when they carry explicit `runtime_reason_code` plus exception/source context; WARNING, validation, cancellation, bridge logger, and records without typed context are ignored; existing root handler identities and `LOI_SO` behavior remain unchanged.

- [ ] **Step 2: Write RED legacy-boundary tests**

AST/characterization tests require: supervisor starts `_worker_entry` instead of `_worker`; `_worker_entry` reports only exceptions escaping `_worker`; video retry exhaustion emits one typed `RETRY_EXHAUSTED` signal; no new `_xep`, `_enqueue`, `JOBS`, `_HOAN`, account, retry, or state writer is added.

- [ ] **Step 3: Implement the no-throw facade and daemon**

The service owns journal, optional logging adapter, bounded wake event, and optional bridge thread. Default mode never starts `bd`; auto-create validates `bd context/config` and `sync.remote` absence before starting. Shutdown joins with a short timeout and never waits indefinitely on `bd`.

- [ ] **Step 4: Add minimal production hooks**

In `main`, start the service after `BOARD` is initialized and register shutdown with `atexit`. Add `_worker_entry(endpoint, kind, slot)` as a wrapper around `_worker`; do not change `_worker` scheduling/retry logic. At the existing video exhaustion branch, call the no-throw reporter with explicit typed context after the existing `_dat_job` and `_LOG.warning`. Extend `/api/chan-doan` with only `"bug_bridge": runtime_bug_diagnostics()["bug_bridge"]`.

- [ ] **Step 5: Run focused GREEN and lifecycle gate**

Run:

```bash
./.venv/bin/python3 -m pytest tests/runtime_bugs/test_runtime_service.py tests/runtime_bugs/test_legacy_instrumentation.py tests/job_lifecycle/test_http_contract.py -q
./test-job-lifecycle.command
```

Expected: focused tests pass; lifecycle remains 30 pass, 5 xfailed, coverage >=80%, compile pass.

- [ ] **Step 6: Commit exact paths**

Commit runtime service, production integration, and tests with `git commit -m "update"`.

### Task 7: Temporary-workspace integration and final rollout verification

**Files:**
- Create: `tests/runtime_bugs/test_integration.py`
- Modify: `docs/JOB-LIFECYCLE-README.md`

**Interfaces:**
- Consumes all prior tasks.
- Produces executable evidence for journal-only restart, temporary Beads auto-create, dedupe, diagnostics, and rollback mode.

- [ ] **Step 1: Write integration tests using only temp directories and fake/sandbox Beads workspace**

Test: synthetic severe event persists across service restart; journal-only makes zero `bd` calls; explicit auto-create sync creates exactly one issue for repeated fingerprint; second restart does not replay; diagnostic counters match; cancel/validation/warning create no issue; canary secret absent from JSONL, CLI, diagnostics, and Bead payload.

- [ ] **Step 2: Run integration suite**

Run: `./.venv/bin/python3 -m pytest tests/runtime_bugs -q`

- [ ] **Step 3: Document AI/operator commands**

Add a short routing section to `docs/JOB-LIFECYCLE-README.md`:

```bash
python -m sfboard.jobs.bugtool --root . status
python -m sfboard.jobs.bugtool --root . list
python -m sfboard.jobs.bugtool --root . show <event-id>
python -m sfboard.jobs.bugtool --root . sync
```

State that `sync` is explicit/local-only, auto-create is off by default, and AI investigates only when the user opens/requests a Bead.

- [ ] **Step 4: Run final security, scope, and lifecycle gates**

```bash
./.venv/bin/python3 -m pytest tests/runtime_bugs -q
./test-job-lifecycle.command
./.venv/bin/python3 -m py_compile sfboard/jobs/*.py sfboard/sfboard.py sfboard/hangdoi.py
git diff --check
git status --short
git grep -n -E 'Bearer |password=|sessionid=|SENTRY_DSN' -- ':!tests' ':!docs' || true
git check-ignore -v .grokpipe/runtime-bugs/events.jsonl
```

Expected: runtime-bug suite passes; lifecycle baseline unchanged; compile passes; no secret/runtime artifact is tracked; only approved source/test/docs/dependency files differ.

- [ ] **Step 5: Commit and handoff**

Stage exact test/doc paths and commit with `git commit -m "update"`. Final report records dependency version, sink options, journal/bridge modes, test counts, lifecycle result, local-only/no-remote status, and known rollout caveats.
