"""SQLite implementation của JobStore với transaction/CAS thật.

Module này chỉ lưu lifecycle facts. Nó không import board, queue, browser hay
executor và không có quyền tự retry/enqueue.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
import json
import os
import sqlite3
import threading
from typing import Iterator, Optional, Tuple
from uuid import UUID

from .models import (
    AssetId,
    AttemptId,
    Batch,
    BatchId,
    BatchMode,
    EventActor,
    Job,
    JobEvent,
    JobId,
    JobKind,
    JobOrigin,
    JobState,
)
from .persistence import (
    DurableExecution,
    ScheduleConflict,
    ScheduleVersionConflict,
)
from .store import (
    ActiveJobConflict,
    EventConflict,
    IdempotencyConflict,
    IdempotencyRecord,
    IntentWriteResult,
    JobAlreadyExists,
    JobNotFound,
    StaleScopeParent,
    StoreInvariantError,
    StoreWriteResult,
    VersionConflict,
)


SCHEMA_VERSION = 1


class SQLiteLifecycleError(RuntimeError):
    pass


class UnsupportedSchemaVersion(SQLiteLifecycleError):
    pass


class LifecycleDatabaseBusy(SQLiteLifecycleError):
    pass


_SCHEMA = """
CREATE TABLE IF NOT EXISTS lifecycle_jobs (
    job_id TEXT PRIMARY KEY,
    doc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lifecycle_events (
    event_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES lifecycle_jobs(job_id),
    seq INTEGER NOT NULL,
    doc TEXT NOT NULL,
    result_job_doc TEXT NOT NULL,
    UNIQUE(job_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_lifecycle_events_job
    ON lifecycle_events(job_id, seq);
CREATE TABLE IF NOT EXISTS lifecycle_batches (
    batch_id TEXT PRIMARY KEY,
    doc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lifecycle_intent_records (
    canonical_key TEXT PRIMARY KEY,
    doc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lifecycle_intent_aliases (
    alias_key TEXT PRIMARY KEY,
    canonical_key TEXT NOT NULL
        REFERENCES lifecycle_intent_records(canonical_key)
);
CREATE TABLE IF NOT EXISTS lifecycle_scope_intents (
    scope_fingerprint TEXT PRIMARY KEY,
    canonical_key TEXT NOT NULL
        REFERENCES lifecycle_intent_records(canonical_key)
);
CREATE TABLE IF NOT EXISTS lifecycle_executions (
    execution_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    queue_ident TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    member_keys TEXT NOT NULL,
    priority INTEGER NOT NULL,
    not_before REAL NOT NULL,
    state TEXT NOT NULL,
    manual INTEGER NOT NULL DEFAULT 0,
    forced_account TEXT,
    version INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    lease_id TEXT,
    lease_expires_at REAL,
    updated_at REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_lifecycle_exec_state
    ON lifecycle_executions(state, priority, seq);
CREATE INDEX IF NOT EXISTS idx_lifecycle_exec_ident
    ON lifecycle_executions(kind, queue_ident);
CREATE UNIQUE INDEX IF NOT EXISTS idx_lifecycle_exec_active_scope
    ON lifecycle_executions(kind, scope_key)
    WHERE state IN ('ready', 'waiting', 'leased');
"""


def _dump(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _job_doc(job: Job) -> str:
    return _dump({
        "job_id": str(job.job_id),
        "asset_id": str(job.asset_id),
        "kind": job.kind.value,
        "origin": job.origin.value,
        "state": job.state.value,
        "version": job.version,
        "batch_id": str(job.batch_id) if job.batch_id else None,
        "rerun_of": str(job.rerun_of) if job.rerun_of else None,
        "copy_index": job.copy_index,
        "replace_current": job.replace_current,
        "forced_account_id": job.forced_account_id,
        "allow_account_fallback": job.allow_account_fallback,
    })


def _job_from(doc: str) -> Job:
    data = json.loads(doc)
    return Job(
        JobId.parse(data["job_id"]),
        AssetId(data["asset_id"]),
        JobKind(data["kind"]),
        JobOrigin(data["origin"]),
        state=JobState(data["state"]),
        version=int(data["version"]),
        batch_id=BatchId.parse(data["batch_id"]) if data["batch_id"] else None,
        rerun_of=JobId.parse(data["rerun_of"]) if data["rerun_of"] else None,
        copy_index=data["copy_index"],
        replace_current=bool(data["replace_current"]),
        forced_account_id=data["forced_account_id"],
        allow_account_fallback=bool(data["allow_account_fallback"]),
    )


def _event_doc(event: JobEvent) -> str:
    return _dump({
        "event_id": str(event.event_id),
        "job_id": str(event.job_id),
        "actor": event.actor.value,
        "event_type": event.event_type,
        "reason_code": event.reason_code,
        "from_state": event.from_state.value if event.from_state else None,
        "to_state": event.to_state.value if event.to_state else None,
        "attempt_id": str(event.attempt_id) if event.attempt_id else None,
    })


def _event_from(doc: str) -> JobEvent:
    data = json.loads(doc)
    return JobEvent(
        UUID(data["event_id"]),
        JobId.parse(data["job_id"]),
        EventActor(data["actor"]),
        data["event_type"],
        data["reason_code"],
        from_state=(JobState(data["from_state"])
                    if data["from_state"] else None),
        to_state=JobState(data["to_state"]) if data["to_state"] else None,
        attempt_id=(AttemptId.parse(data["attempt_id"])
                    if data["attempt_id"] else None),
    )


def _batch_doc(batch: Batch) -> str:
    return _dump({
        "batch_id": str(batch.batch_id),
        "kind": batch.kind.value,
        "mode": batch.mode.value,
        "member_job_ids": [str(job_id) for job_id in batch.member_job_ids],
    })


def _batch_from(doc: str) -> Batch:
    data = json.loads(doc)
    return Batch(
        BatchId.parse(data["batch_id"]),
        JobKind(data["kind"]),
        BatchMode(data["mode"]),
        tuple(JobId.parse(value) for value in data["member_job_ids"]),
    )


def _intent_doc(record: IdempotencyRecord) -> str:
    return _dump({
        "key": record.key,
        "fingerprint": record.fingerprint,
        "scope_fingerprint": record.scope_fingerprint,
        "job_ids": [str(job_id) for job_id in record.job_ids],
        "batch_id": str(record.batch_id) if record.batch_id else None,
        "delivered": record.delivered,
    })


def _intent_from(doc: str) -> IdempotencyRecord:
    data = json.loads(doc)
    return IdempotencyRecord(
        key=data["key"],
        fingerprint=data["fingerprint"],
        scope_fingerprint=data["scope_fingerprint"],
        job_ids=tuple(JobId.parse(value) for value in data["job_ids"]),
        batch_id=BatchId.parse(data["batch_id"]) if data["batch_id"] else None,
        delivered=bool(data["delivered"]),
    )


class SQLiteLifecycleRepository:
    """JobStore bền vững; nested calls dùng chung một SQLite transaction."""

    def __init__(self, path: str, *, timeout: float = 5.0) -> None:
        self.path = path
        directory = os.path.dirname(os.path.abspath(path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._lock = threading.RLock()
        self._tx_depth = 0
        self._closed = False
        self._conn = sqlite3.connect(
            path, timeout=float(timeout), check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        try:
            with self._lock:
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA foreign_keys=ON")
                self._conn.execute(
                    "CREATE TABLE IF NOT EXISTS lifecycle_schema_version "
                    "(version INTEGER NOT NULL)"
                )
                row = self._conn.execute(
                    "SELECT version FROM lifecycle_schema_version LIMIT 1"
                ).fetchone()
                if row is None:
                    self._conn.execute(
                        "INSERT INTO lifecycle_schema_version VALUES (?)",
                        (SCHEMA_VERSION,),
                    )
                elif int(row["version"]) != SCHEMA_VERSION:
                    raise UnsupportedSchemaVersion(
                        f"lifecycle schema={row['version']}, supported={SCHEMA_VERSION}"
                    )
                self._conn.executescript(_SCHEMA)
                self._conn.commit()
        except Exception:
            self._conn.close()
            self._closed = True
            raise

    @contextmanager
    def transaction(self) -> Iterator["SQLiteLifecycleRepository"]:
        with self._lock:
            outer = self._tx_depth == 0
            if outer:
                try:
                    self._conn.execute("BEGIN IMMEDIATE")
                except sqlite3.OperationalError as exc:
                    if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                        raise LifecycleDatabaseBusy(str(exc)) from exc
                    raise
            self._tx_depth += 1
            try:
                yield self
            except BaseException:
                self._tx_depth -= 1
                if outer:
                    self._conn.rollback()
                raise
            else:
                self._tx_depth -= 1
                if outer:
                    self._conn.commit()

    def _record_for_alias(self, key: str) -> Optional[IdempotencyRecord]:
        row = self._conn.execute(
            """SELECT records.doc AS doc
               FROM lifecycle_intent_aliases AS aliases
               JOIN lifecycle_intent_records AS records
                 ON records.canonical_key=aliases.canonical_key
               WHERE aliases.alias_key=?""",
            (key,),
        ).fetchone()
        return _intent_from(row["doc"]) if row is not None else None

    @staticmethod
    def _execution_from(row: sqlite3.Row) -> DurableExecution:
        return DurableExecution(
            execution_id=row["execution_id"],
            kind=row["kind"],
            queue_ident=row["queue_ident"],
            member_keys=tuple(json.loads(row["member_keys"])),
            priority=int(row["priority"]),
            not_before=float(row["not_before"]),
            state=row["state"],
            manual=bool(row["manual"]),
            forced_account=row["forced_account"],
            scope_key=row["scope_key"],
            version=int(row["version"]),
            seq=int(row["seq"]),
            lease_id=row["lease_id"],
            lease_expires_at=(
                float(row["lease_expires_at"])
                if row["lease_expires_at"] is not None else None
            ),
        )

    @staticmethod
    def _execution_values(execution: DurableExecution) -> tuple:
        return (
            execution.execution_id,
            execution.kind,
            execution.queue_ident,
            execution.scope_key or execution.queue_ident,
            json.dumps(execution.member_keys, ensure_ascii=False),
            int(execution.priority),
            float(execution.not_before),
            execution.state,
            1 if execution.manual else 0,
            execution.forced_account,
            int(execution.version),
            int(execution.seq),
            execution.lease_id,
            execution.lease_expires_at,
            0.0,
        )

    def insert_execution(self, execution: DurableExecution) -> None:
        with self.transaction():
            try:
                self._conn.execute(
                    """INSERT INTO lifecycle_executions
                       (execution_id, kind, queue_ident, scope_key, member_keys,
                        priority, not_before, state, manual, forced_account,
                        version, seq, lease_id, lease_expires_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    self._execution_values(execution),
                )
            except sqlite3.IntegrityError as exc:
                raise ScheduleConflict(str(exc)) from exc

    def update_execution(
        self, execution: DurableExecution, *, expected_version: int,
    ) -> None:
        values = self._execution_values(execution)
        with self.transaction():
            try:
                cursor = self._conn.execute(
                    """UPDATE lifecycle_executions SET
                         kind=?, queue_ident=?, scope_key=?, member_keys=?,
                         priority=?, not_before=?, state=?, manual=?,
                         forced_account=?, version=?, seq=?, lease_id=?,
                         lease_expires_at=?, updated_at=?
                       WHERE execution_id=? AND version=?""",
                    values[1:] + (values[0], int(expected_version)),
                )
            except sqlite3.IntegrityError as exc:
                raise ScheduleConflict(str(exc)) from exc
            if cursor.rowcount != 1:
                raise ScheduleVersionConflict(
                    f"execution={execution.execution_id}, "
                    f"expected={expected_version}"
                )

    def load_active_execution_records(self) -> Tuple[DurableExecution, ...]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM lifecycle_executions "
                "WHERE state IN ('ready', 'waiting', 'leased') "
                "ORDER BY priority ASC, seq ASC"
            ).fetchall()
            return tuple(self._execution_from(row) for row in rows)

    def all_execution_records(self) -> Tuple[DurableExecution, ...]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM lifecycle_executions ORDER BY seq ASC"
            ).fetchall()
            return tuple(self._execution_from(row) for row in rows)

    def _intent_result(
        self, record: IdempotencyRecord, *, replayed: bool,
    ) -> IntentWriteResult:
        jobs = tuple(self.get(job_id) for job_id in record.job_ids)
        if any(job is None for job in jobs):
            raise StoreInvariantError("intent trỏ tới job không tồn tại")
        batch = self.get_batch(record.batch_id) if record.batch_id else None
        return IntentWriteResult(record, jobs, batch, replayed)  # type: ignore[arg-type]

    def _replay(
        self, job_id: JobId, event: JobEvent, job: Optional[Job] = None,
    ) -> Optional[StoreWriteResult]:
        row = self._conn.execute(
            "SELECT doc, result_job_doc FROM lifecycle_events WHERE event_id=?",
            (str(event.event_id),),
        ).fetchone()
        if row is None:
            return None
        stored_event = _event_from(row["doc"])
        stored_job = _job_from(row["result_job_doc"])
        if (
            stored_job.job_id != job_id
            or stored_event != event
            or (job is not None and stored_job != job)
        ):
            raise EventConflict(f"event_id {event.event_id} đã mang payload khác")
        return StoreWriteResult(stored_job, stored_event, False)

    def _next_event_seq(self, job_id: JobId) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(MAX(seq), -1) AS value "
            "FROM lifecycle_events WHERE job_id=?",
            (str(job_id),),
        ).fetchone()
        return int(row["value"]) + 1

    def _insert_event(self, event: JobEvent, result_job: Job) -> None:
        try:
            self._conn.execute(
                """INSERT INTO lifecycle_events
                   (event_id, job_id, seq, doc, result_job_doc)
                   VALUES (?,?,?,?,?)""",
                (str(event.event_id), str(event.job_id),
                 self._next_event_seq(event.job_id), _event_doc(event),
                 _job_doc(result_job)),
            )
        except sqlite3.IntegrityError as exc:
            raise EventConflict(str(exc)) from exc

    def _validate_intent(
        self,
        record: IdempotencyRecord,
        batch: Optional[Batch],
        jobs_and_events: Tuple[Tuple[Job, JobEvent], ...],
    ) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (record.key, record.fingerprint, record.scope_fingerprint)
        ):
            raise StoreInvariantError("intent cần key và fingerprint không rỗng")
        if not record.job_ids or not all(
            isinstance(job_id, JobId) for job_id in record.job_ids
        ):
            raise StoreInvariantError("intent cần job_ids hợp lệ")
        jobs = tuple(job for job, _ in jobs_and_events)
        events = tuple(event for _, event in jobs_and_events)
        if record.job_ids != tuple(job.job_id for job in jobs):
            raise StoreInvariantError("intent job_ids không khớp jobs")
        if len(set(record.job_ids)) != len(record.job_ids):
            raise StoreInvariantError("intent không được có JobId trùng")
        if len({event.event_id for event in events}) != len(events):
            raise StoreInvariantError("intent không được có EventId trùng")
        if any(job.state is not JobState.CREATED or job.version != 0 for job in jobs):
            raise StoreInvariantError("intent chỉ tạo job CREATED version 0")
        if any(
            event.job_id != job.job_id
            or event.from_state is not None
            or event.to_state is not None
            for job, event in jobs_and_events
        ):
            raise StoreInvariantError("create event không khớp job")
        if batch is None:
            if record.batch_id is not None or any(job.batch_id for job in jobs):
                raise StoreInvariantError("intent không batch không được mang batch_id")
        elif (
            record.batch_id != batch.batch_id
            or batch.member_job_ids != record.job_ids
            or any(job.batch_id != batch.batch_id for job in jobs)
            or any(job.kind is not batch.kind for job in jobs)
        ):
            raise StoreInvariantError("batch không khớp intent jobs")
        if any(self.get(job_id) is not None for job_id in record.job_ids):
            raise JobAlreadyExists("intent chứa job đã tồn tại")
        if batch is not None and self.get_batch(batch.batch_id) is not None:
            raise StoreInvariantError("batch đã tồn tại")
        if any(
            self._conn.execute(
                "SELECT 1 FROM lifecycle_events WHERE event_id=?",
                (str(event.event_id),),
            ).fetchone() is not None
            for event in events
        ):
            raise EventConflict("intent chứa event đã tồn tại")

    def create_intent(
        self,
        record: IdempotencyRecord,
        batch: Optional[Batch],
        jobs_and_events: Tuple[Tuple[Job, JobEvent], ...],
        *,
        expected_scope_job_ids: Optional[Tuple[JobId, ...]] = None,
        check_scope_parent: bool = False,
    ) -> IntentWriteResult:
        with self.transaction():
            exact = self._record_for_alias(record.key)
            if exact is not None:
                if exact.fingerprint != record.fingerprint:
                    raise IdempotencyConflict(record.key)
                return self._intent_result(exact, replayed=True)

            self._validate_intent(record, batch, jobs_and_events)
            scope_row = self._conn.execute(
                "SELECT canonical_key FROM lifecycle_scope_intents "
                "WHERE scope_fingerprint=?",
                (record.scope_fingerprint,),
            ).fetchone()
            scoped = (
                self._record_for_alias(scope_row["canonical_key"])
                if scope_row is not None else None
            )
            if check_scope_parent:
                actual_terminal_parent = None
                if scoped is not None:
                    scoped_jobs = tuple(self.get(job_id) for job_id in scoped.job_ids)
                    if all(job is not None and job.state.is_terminal
                           for job in scoped_jobs):
                        actual_terminal_parent = scoped.job_ids
                if actual_terminal_parent != expected_scope_job_ids:
                    raise StaleScopeParent(record.scope_fingerprint)
            if scoped is not None:
                scoped_jobs = tuple(self.get(job_id) for job_id in scoped.job_ids)
                if any(job is None for job in scoped_jobs):
                    raise StoreInvariantError("scope intent trỏ tới job mất")
                incoming_origin = jobs_and_events[0][0].origin
                blocks_new = incoming_origin is JobOrigin.AUTO or any(
                    job.state in {
                        JobState.CREATED, JobState.QUEUED, JobState.RUNNING,
                        JobState.RETRY_WAIT, JobState.NEEDS_ATTENTION,
                    }
                    for job in scoped_jobs if job is not None
                )
                if blocks_new:
                    if scoped.fingerprint != record.fingerprint:
                        raise ActiveJobConflict(record.scope_fingerprint)
                    self._conn.execute(
                        "INSERT INTO lifecycle_intent_aliases VALUES (?,?)",
                        (record.key, scoped.key),
                    )
                    return self._intent_result(scoped, replayed=True)

            for job, event in jobs_and_events:
                try:
                    self._conn.execute(
                        "INSERT INTO lifecycle_jobs VALUES (?,?)",
                        (str(job.job_id), _job_doc(job)),
                    )
                except sqlite3.IntegrityError as exc:
                    raise JobAlreadyExists(str(job.job_id)) from exc
                self._insert_event(event, job)
            if batch is not None:
                self._conn.execute(
                    "INSERT INTO lifecycle_batches VALUES (?,?)",
                    (str(batch.batch_id), _batch_doc(batch)),
                )
            self._conn.execute(
                "INSERT INTO lifecycle_intent_records VALUES (?,?)",
                (record.key, _intent_doc(record)),
            )
            self._conn.execute(
                "INSERT INTO lifecycle_intent_aliases VALUES (?,?)",
                (record.key, record.key),
            )
            self._conn.execute(
                """INSERT INTO lifecycle_scope_intents VALUES (?,?)
                   ON CONFLICT(scope_fingerprint) DO UPDATE SET
                     canonical_key=excluded.canonical_key""",
                (record.scope_fingerprint, record.key),
            )
            return IntentWriteResult(
                record, tuple(job for job, _ in jobs_and_events), batch, False,
            )

    def get_intent(self, key: str) -> Optional[IdempotencyRecord]:
        with self._lock:
            return self._record_for_alias(key)

    def mark_intent_delivered(self, key: str) -> IdempotencyRecord:
        with self.transaction():
            record = self._record_for_alias(key)
            if record is None:
                raise JobNotFound(key)
            delivered = replace(record, delivered=True)
            self._conn.execute(
                "UPDATE lifecycle_intent_records SET doc=? WHERE canonical_key=?",
                (_intent_doc(delivered), record.key),
            )
            return delivered

    def get_batch(self, batch_id: BatchId) -> Optional[Batch]:
        with self._lock:
            row = self._conn.execute(
                "SELECT doc FROM lifecycle_batches WHERE batch_id=?",
                (str(batch_id),),
            ).fetchone()
            return _batch_from(row["doc"]) if row is not None else None

    def latest_for_scope(
        self, scope_fingerprint: str,
    ) -> Optional[IdempotencyRecord]:
        with self._lock:
            row = self._conn.execute(
                "SELECT canonical_key FROM lifecycle_scope_intents "
                "WHERE scope_fingerprint=?",
                (scope_fingerprint,),
            ).fetchone()
            return self._record_for_alias(row["canonical_key"]) if row else None

    def create(self, job: Job, event: JobEvent) -> StoreWriteResult:
        with self.transaction():
            replay = self._replay(job.job_id, event, job)
            if replay is not None:
                return replay
            if self.get(job.job_id) is not None:
                raise JobAlreadyExists(str(job.job_id))
            if event.job_id != job.job_id or event.from_state is not None:
                raise StoreInvariantError("create event không khớp job")
            self._conn.execute(
                "INSERT INTO lifecycle_jobs VALUES (?,?)",
                (str(job.job_id), _job_doc(job)),
            )
            self._insert_event(event, job)
            return StoreWriteResult(job, event, True)

    def get(self, job_id: JobId) -> Optional[Job]:
        with self._lock:
            row = self._conn.execute(
                "SELECT doc FROM lifecycle_jobs WHERE job_id=?",
                (str(job_id),),
            ).fetchone()
            return _job_from(row["doc"]) if row is not None else None

    def events_for(self, job_id: JobId) -> Tuple[JobEvent, ...]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT doc FROM lifecycle_events WHERE job_id=? ORDER BY seq ASC",
                (str(job_id),),
            ).fetchall()
            return tuple(_event_from(row["doc"]) for row in rows)

    def append_event(self, job_id: JobId, event: JobEvent) -> StoreWriteResult:
        with self.transaction():
            replay = self._replay(job_id, event)
            if replay is not None:
                return replay
            job = self.get(job_id)
            if job is None:
                raise JobNotFound(str(job_id))
            if event.job_id != job_id or event.from_state is not None:
                raise StoreInvariantError("progress event không hợp lệ")
            self._insert_event(event, job)
            return StoreWriteResult(job, event, True)

    def transition(
        self,
        job_id: JobId,
        expected_version: int,
        to_state: JobState,
        event: JobEvent,
    ) -> StoreWriteResult:
        with self.transaction():
            replay = self._replay(job_id, event)
            if replay is not None:
                return replay
            current = self.get(job_id)
            if current is None:
                raise JobNotFound(str(job_id))
            if current.version != expected_version:
                raise VersionConflict(
                    f"expected={expected_version}, actual={current.version}"
                )
            if (
                event.job_id != job_id
                or event.from_state != current.state
                or event.to_state != to_state
            ):
                raise StoreInvariantError("transition event không khớp snapshot")
            updated = replace(
                current, state=to_state, version=current.version + 1,
            )
            cursor = self._conn.execute(
                "UPDATE lifecycle_jobs SET doc=? WHERE job_id=? AND "
                "json_extract(doc, '$.version')=?",
                (_job_doc(updated), str(job_id), int(expected_version)),
            )
            if cursor.rowcount != 1:
                raise VersionConflict(str(job_id))
            self._insert_event(event, updated)
            return StoreWriteResult(updated, event, True)

    def close(self) -> None:
        with getattr(self, "_lock", threading.RLock()):
            if getattr(self, "_closed", True):
                return
            if self._tx_depth:
                self._conn.rollback()
                self._tx_depth = 0
            self._conn.commit()
            self._conn.close()
            self._closed = True
