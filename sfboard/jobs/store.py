from __future__ import annotations

from dataclasses import dataclass, replace
from threading import RLock
from typing import Optional, Protocol, Tuple
from uuid import UUID

from .models import Batch, BatchId, Job, JobEvent, JobId, JobOrigin, JobState


class JobStoreError(RuntimeError):
    pass


class JobNotFound(JobStoreError):
    pass


class JobAlreadyExists(JobStoreError):
    pass


class VersionConflict(JobStoreError):
    pass


class EventConflict(JobStoreError):
    pass


class IdempotencyConflict(JobStoreError):
    pass


class ActiveJobConflict(JobStoreError):
    pass


class StaleScopeParent(JobStoreError):
    pass


class StoreInvariantError(JobStoreError):
    pass


@dataclass(frozen=True)
class StoreWriteResult:
    job: Job
    event: JobEvent
    applied: bool


@dataclass(frozen=True)
class IdempotencyRecord:
    key: str
    fingerprint: str
    scope_fingerprint: str
    job_ids: Tuple[JobId, ...]
    batch_id: Optional[BatchId]
    delivered: bool


@dataclass(frozen=True)
class IntentWriteResult:
    record: IdempotencyRecord
    jobs: Tuple[Job, ...]
    batch: Optional[Batch]
    replayed: bool


class JobStore(Protocol):
    def create(self, job: Job, event: JobEvent) -> StoreWriteResult: ...

    def get(self, job_id: JobId) -> Optional[Job]: ...

    def all_jobs(self) -> Tuple[Job, ...]: ...

    def events_for(self, job_id: JobId) -> Tuple[JobEvent, ...]: ...

    def append_event(self, job_id: JobId, event: JobEvent) -> StoreWriteResult: ...

    def transition(
        self,
        job_id: JobId,
        expected_version: int,
        to_state: JobState,
        event: JobEvent,
    ) -> StoreWriteResult: ...

    def create_intent(
        self,
        record: IdempotencyRecord,
        batch: Optional[Batch],
        jobs_and_events: Tuple[Tuple[Job, JobEvent], ...],
        *,
        expected_scope_job_ids: Optional[Tuple[JobId, ...]] = None,
        check_scope_parent: bool = False,
    ) -> IntentWriteResult: ...

    def get_intent(self, key: str) -> Optional[IdempotencyRecord]: ...

    def mark_intent_delivered(self, key: str) -> IdempotencyRecord: ...

    def get_batch(self, batch_id: BatchId) -> Optional[Batch]: ...

    def latest_for_scope(
        self, scope_fingerprint: str
    ) -> Optional[IdempotencyRecord]: ...


class MemoryJobStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._jobs: dict[JobId, Job] = {}
        self._events: dict[JobId, list[JobEvent]] = {}
        self._event_results: dict[UUID, StoreWriteResult] = {}
        self._batches: dict[BatchId, Batch] = {}
        self._intents: dict[str, IdempotencyRecord] = {}
        self._scope_intents: dict[str, str] = {}

    def _intent_result(
        self, record: IdempotencyRecord, *, replayed: bool
    ) -> IntentWriteResult:
        return IntentWriteResult(
            record=record,
            jobs=tuple(self._jobs[job_id] for job_id in record.job_ids),
            batch=self._batches.get(record.batch_id) if record.batch_id else None,
            replayed=replayed,
        )

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
        job_ids = tuple(job.job_id for job in jobs)
        if record.job_ids != job_ids:
            raise StoreInvariantError("intent job_ids không khớp jobs")
        if len(set(job_ids)) != len(job_ids):
            raise StoreInvariantError("intent không được có JobId trùng")
        if len({event.event_id for event in events}) != len(events):
            raise StoreInvariantError("intent không được có EventId trùng")
        if any(
            job.state is not JobState.CREATED or job.version != 0 for job in jobs
        ):
            raise StoreInvariantError("intent chỉ tạo job CREATED version 0")
        if any(
            event.job_id != job.job_id
            or event.from_state is not None
            or event.to_state is not None
            for job, event in jobs_and_events
        ):
            raise StoreInvariantError("create event không khớp job")

        if batch is None:
            if record.batch_id is not None or any(job.batch_id is not None for job in jobs):
                raise StoreInvariantError("intent không batch không được mang batch_id")
        else:
            if (
                record.batch_id != batch.batch_id
                or batch.member_job_ids != record.job_ids
                or any(job.batch_id != batch.batch_id for job in jobs)
                or any(job.kind is not batch.kind for job in jobs)
            ):
                raise StoreInvariantError("batch không khớp intent jobs")

        if any(job_id in self._jobs for job_id in job_ids):
            raise JobAlreadyExists("intent chứa job đã tồn tại")
        if batch is not None and batch.batch_id in self._batches:
            raise StoreInvariantError("batch đã tồn tại")
        if any(event.event_id in self._event_results for event in events):
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
        with self._lock:
            exact = self._intents.get(record.key)
            if exact is not None:
                if exact.fingerprint != record.fingerprint:
                    raise IdempotencyConflict(record.key)
                return self._intent_result(exact, replayed=True)

            self._validate_intent(record, batch, jobs_and_events)
            scope_key = self._scope_intents.get(record.scope_fingerprint)
            if check_scope_parent:
                actual_terminal_parent = None
                if scope_key is not None:
                    scoped = self._intents[scope_key]
                    scoped_jobs = tuple(self._jobs[job_id] for job_id in scoped.job_ids)
                    if all(job.state.is_terminal for job in scoped_jobs):
                        actual_terminal_parent = scoped.job_ids
                if actual_terminal_parent != expected_scope_job_ids:
                    raise StaleScopeParent(record.scope_fingerprint)
            if scope_key is not None:
                scoped = self._intents[scope_key]
                scoped_jobs = tuple(self._jobs[job_id] for job_id in scoped.job_ids)
                incoming_origin = jobs_and_events[0][0].origin
                blocks_new = incoming_origin is JobOrigin.AUTO or any(
                    job.state
                    in {
                        JobState.CREATED,
                        JobState.QUEUED,
                        JobState.RUNNING,
                        JobState.RETRY_WAIT,
                        JobState.NEEDS_ATTENTION,
                    }
                    for job in scoped_jobs
                )
                if blocks_new:
                    if scoped.fingerprint != record.fingerprint:
                        raise ActiveJobConflict(record.scope_fingerprint)
                    self._intents[record.key] = scoped
                    return IntentWriteResult(
                        scoped,
                        scoped_jobs,
                        self._batches.get(scoped.batch_id) if scoped.batch_id else None,
                        True,
                    )

            for job, event in jobs_and_events:
                self._jobs[job.job_id] = job
                self._events[job.job_id] = [event]
                self._event_results[event.event_id] = StoreWriteResult(job, event, True)
            if batch is not None:
                self._batches[batch.batch_id] = batch
            self._intents[record.key] = record
            self._scope_intents[record.scope_fingerprint] = record.key
            return IntentWriteResult(
                record, tuple(job for job, _ in jobs_and_events), batch, False
            )

    def get_intent(self, key: str) -> Optional[IdempotencyRecord]:
        with self._lock:
            return self._intents.get(key)

    def mark_intent_delivered(self, key: str) -> IdempotencyRecord:
        with self._lock:
            record = self._intents.get(key)
            if record is None:
                raise JobNotFound(key)
            delivered = replace(record, delivered=True)
            for intent_key, value in tuple(self._intents.items()):
                if value.key == record.key:
                    self._intents[intent_key] = delivered
            return delivered

    def get_batch(self, batch_id: BatchId) -> Optional[Batch]:
        with self._lock:
            return self._batches.get(batch_id)

    def latest_for_scope(
        self, scope_fingerprint: str
    ) -> Optional[IdempotencyRecord]:
        with self._lock:
            key = self._scope_intents.get(scope_fingerprint)
            return self._intents.get(key) if key is not None else None

    def _replay(
        self,
        job_id: JobId,
        event: JobEvent,
        job: Optional[Job] = None,
    ) -> Optional[StoreWriteResult]:
        result = self._event_results.get(event.event_id)
        if result is None:
            return None
        if (
            result.job.job_id != job_id
            or result.event != event
            or (job is not None and result.job != job)
        ):
            raise EventConflict(f"event_id {event.event_id} đã mang payload khác")
        return replace(result, applied=False)

    def create(self, job: Job, event: JobEvent) -> StoreWriteResult:
        with self._lock:
            replay = self._replay(job.job_id, event, job)
            if replay is not None:
                return replay
            if job.job_id in self._jobs:
                raise JobAlreadyExists(str(job.job_id))
            if event.job_id != job.job_id or event.from_state is not None:
                raise StoreInvariantError("create event không khớp job")
            result = StoreWriteResult(job, event, True)
            self._jobs[job.job_id] = job
            self._events[job.job_id] = [event]
            self._event_results[event.event_id] = result
            return result

    def get(self, job_id: JobId) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def all_jobs(self) -> Tuple[Job, ...]:
        with self._lock:
            return tuple(self._jobs.values())

    def events_for(self, job_id: JobId) -> Tuple[JobEvent, ...]:
        with self._lock:
            return tuple(self._events.get(job_id, ()))

    def append_event(self, job_id: JobId, event: JobEvent) -> StoreWriteResult:
        with self._lock:
            replay = self._replay(job_id, event)
            if replay is not None:
                return replay
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFound(str(job_id))
            if event.job_id != job_id or event.from_state is not None:
                raise StoreInvariantError("progress event không hợp lệ")
            result = StoreWriteResult(job, event, True)
            self._events[job_id].append(event)
            self._event_results[event.event_id] = result
            return result

    def transition(
        self,
        job_id: JobId,
        expected_version: int,
        to_state: JobState,
        event: JobEvent,
    ) -> StoreWriteResult:
        with self._lock:
            replay = self._replay(job_id, event)
            if replay is not None:
                return replay
            current = self._jobs.get(job_id)
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
            updated = replace(current, state=to_state, version=current.version + 1)
            result = StoreWriteResult(updated, event, True)
            self._jobs[job_id] = updated
            self._events[job_id].append(event)
            self._event_results[event.event_id] = result
            return result
