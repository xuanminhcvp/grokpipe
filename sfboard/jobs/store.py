from __future__ import annotations

from dataclasses import dataclass, replace
from threading import RLock
from typing import Optional, Protocol, Tuple
from uuid import UUID

from .models import Job, JobEvent, JobId, JobState


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


class StoreInvariantError(JobStoreError):
    pass


@dataclass(frozen=True)
class StoreWriteResult:
    job: Job
    event: JobEvent
    applied: bool


class JobStore(Protocol):
    def create(self, job: Job, event: JobEvent) -> StoreWriteResult: ...

    def get(self, job_id: JobId) -> Optional[Job]: ...

    def events_for(self, job_id: JobId) -> Tuple[JobEvent, ...]: ...

    def append_event(self, job_id: JobId, event: JobEvent) -> StoreWriteResult: ...

    def transition(
        self,
        job_id: JobId,
        expected_version: int,
        to_state: JobState,
        event: JobEvent,
    ) -> StoreWriteResult: ...


class MemoryJobStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._jobs: dict[JobId, Job] = {}
        self._events: dict[JobId, list[JobEvent]] = {}
        self._event_results: dict[UUID, StoreWriteResult] = {}

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
