# Task 1 — Atomic Intent and Batch Store

## Status

Completed. Phase 2 remains shadow-only and legacy remains the production
authority. This task adds no queue, provider, retry, account-assignment, or
legacy writer.

## Files

- `sfboard/jobs/store.py`: immutable intent records, conflict types, atomic
  intent/batch write API, read APIs, scope replay/conflict handling, and
  delivered alias update.
- `sfboard/jobs/__init__.py`: exports the new intent records and conflict
  types.
- `tests/job_lifecycle/test_store.py`: regression coverage for exact-key
  replay, key conflict, all-or-nothing invalid batch, delivery via scope alias,
  and active-scope payload conflict.

## RED evidence

Command:

```bash
./.venv/bin/python3 -m pytest tests/job_lifecycle/test_store.py -q
```

Before the implementation, collection failed with the expected missing-API
error:

```text
ImportError: cannot import name 'ActiveJobConflict' from 'sfboard.jobs.store'
```

## GREEN evidence

Targeted validation:

```text
13 passed in 0.07s
```

`./.venv/bin/python3 -m compileall -q sfboard/jobs` exited 0.

Full lifecycle gate:

```text
398 passed, 4 xfailed
Job lifecycle gate: PASS
```

## Commit(s)

`f036161cf4aa3b3b4ae2433cf89a427920ba83aa feat: add atomic producer intent store`

## Self-review

- `create_intent` keeps validation before all writes to jobs, events, batches,
  intents, and scope indexes.
- Exact idempotency-key replay returns persisted jobs/batch; changed payload
  raises `IdempotencyConflict` without creating a job.
- An active scope with another fingerprint raises `ActiveJobConflict`; same
  fingerprint aliases the original immutable record.
- `mark_intent_delivered` replaces the immutable original and every alias.
- `latest_for_scope` is read-only and reads under the store `RLock`.
- Structural search found intent-index assignments only in `MemoryJobStore`;
  no additional lifecycle writer or re-enqueue authority was introduced.

## Concerns

None for Task 1. Producer delivery and legacy enqueue remain intentionally out
of scope for later Phase 3 tasks.
