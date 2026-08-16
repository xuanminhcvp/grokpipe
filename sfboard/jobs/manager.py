from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from uuid import UUID

from .models import EventActor, Job, JobEvent, JobId, JobOrigin, JobState
from .store import JobNotFound, JobStore, StoreWriteResult, VersionConflict


LEGAL_TRANSITIONS = MappingProxyType({
    JobState.CREATED: frozenset(
        {JobState.QUEUED, JobState.FAILED, JobState.CANCELLED}
    ),
    JobState.QUEUED: frozenset(
        {JobState.RUNNING, JobState.FAILED, JobState.CANCELLED}
    ),
    JobState.RUNNING: frozenset({
        JobState.COMPLETED,
        JobState.RETRY_WAIT,
        JobState.FAILED,
        JobState.CANCELLED,
        JobState.NEEDS_ATTENTION,
    }),
    JobState.RETRY_WAIT: frozenset({
        JobState.QUEUED,
        JobState.FAILED,
        JobState.CANCELLED,
    }),
    JobState.NEEDS_ATTENTION: frozenset({
        JobState.COMPLETED,
        JobState.FAILED,
        JobState.CANCELLED,
    }),
    JobState.COMPLETED: frozenset(),
    JobState.FAILED: frozenset(),
    JobState.CANCELLED: frozenset(),
})


class IllegalTransition(RuntimeError):
    pass


@dataclass(frozen=True)
class TransitionCommand:
    job_id: JobId
    expected_version: int
    to_state: JobState
    actor: EventActor
    event_type: str
    reason_code: str
    event_id: UUID


class JobManager:
    def __init__(self, store: JobStore) -> None:
        self.store = store

    def get(self, job_id: JobId) -> Job:
        job = self.store.get(job_id)
        if job is None:
            raise JobNotFound(str(job_id))
        return job

    def create_job(
        self,
        job: Job,
        event_id: UUID,
        actor: EventActor,
        reason_code: str,
    ) -> StoreWriteResult:
        if job.state is not JobState.CREATED or job.version != 0:
            raise ValueError("create_job chỉ nhận CREATED version 0")
        event = JobEvent(
            event_id,
            job.job_id,
            actor,
            "job.created",
            reason_code,
        )
        return self.store.create(job, event)

    def bootstrap_shadow(
        self,
        job: Job,
        event_id: UUID,
        reason_code: str,
    ) -> StoreWriteResult:
        if job.origin is not JobOrigin.COMPATIBILITY or job.version != 0:
            raise ValueError("bootstrap chỉ dành cho compatibility shadow")
        event = JobEvent(
            event_id,
            job.job_id,
            EventActor.MANAGER,
            "legacy.bootstrap",
            reason_code,
        )
        return self.store.create(job, event)

    def transition(self, command: TransitionCommand) -> StoreWriteResult:
        current = self.get(command.job_id)
        if current.version != command.expected_version:
            raise VersionConflict(
                f"expected={command.expected_version}, actual={current.version}"
            )
        if command.to_state not in LEGAL_TRANSITIONS[current.state]:
            raise IllegalTransition(
                f"{current.state.value}->{command.to_state.value}"
            )
        event = JobEvent(
            command.event_id,
            command.job_id,
            command.actor,
            command.event_type,
            command.reason_code,
            from_state=current.state,
            to_state=command.to_state,
        )
        return self.store.transition(
            command.job_id,
            command.expected_version,
            command.to_state,
            event,
        )

    def record_progress(
        self,
        job_id: JobId,
        event_id: UUID,
        actor: EventActor,
        event_type: str,
        reason_code: str,
    ) -> StoreWriteResult:
        event = JobEvent(event_id, job_id, actor, event_type, reason_code)
        return self.store.append_event(job_id, event)
