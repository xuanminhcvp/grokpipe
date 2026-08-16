"""Coordinator duy nhất áp command/fact lên lifecycle core.

Không có DOM/provider ở đây. Worker nhận `RuntimeLease`, executor phát phase,
success hoặc `ErrorFact`; runtime mới được quyền transition, retry, account và
result commit.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import threading
import time
from typing import Callable, Mapping, Optional, Tuple
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from .accounts import AccountAllocator, NoAccountAvailable
from .compat import LegacyPlan
from .errors import ErrorClass, ErrorFact
from .facts import CancelVerdict, RuntimeLease
from .manager import JobManager, TransitionCommand
from .models import (
    Attempt,
    AttemptId,
    AttemptOutcome,
    AttemptPhase,
    CreditConsumption,
    EventActor,
    ExecutionState,
    JobId,
    JobKind,
    JobState,
)
from .producer import (
    CreateBatchRequest,
    ProducerResult,
    ProducerService,
)
from .results import CommitVerdict, ResultCommit, ResultFact
from .retry import AttemptHistory, RetryAction, RetryDecision, RetryPolicy
from .scheduler import Scheduler
from .sqlite_store import SQLiteLifecycleRepository


def _event_id(base: UUID | str, job_id: JobId, suffix: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"grokpipe:{base}:{job_id}:{suffix}")


def _moment(timestamp: float) -> datetime:
    return datetime.fromtimestamp(float(timestamp), tz=timezone.utc)


class RuntimeLeaseNotFound(RuntimeError):
    pass


class LifecycleRuntime:
    """Một lock điều phối policy; repository giữ transaction/CAS bền vững."""

    def __init__(
        self,
        repository: SQLiteLifecycleRepository,
        *,
        retry_policy: Optional[RetryPolicy] = None,
        accounts: Optional[AccountAllocator] = None,
        results: Optional[ResultCommit] = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.repository = repository
        self.manager = JobManager(repository)
        self.producer = ProducerService(repository)
        self.scheduler = Scheduler(repository)
        self.retry = retry_policy or RetryPolicy()
        self.accounts = accounts or AccountAllocator()
        self.results = results or ResultCommit()
        self.clock = clock
        self._lock = threading.RLock()
        self._leases: dict[str, RuntimeLease] = {}
        self._fact_results: dict[UUID, object] = {}
        self._preferred_account: dict[object, str] = {}
        self._avoid_account: dict[object, str] = {}
        self._restore_constraints()

    def _restore_constraints(self) -> None:
        for execution in self.scheduler.ready(float("inf")):
            jobs = tuple(
                self.repository.get(JobId.parse(value))
                for value in execution.member_keys
            )
            jobs = tuple(job for job in jobs if job is not None)
            forced = next(
                (job.forced_account_id for job in jobs
                 if job.forced_account_id), None)
            if forced:
                fallback = any(job.allow_account_fallback for job in jobs)
                self.accounts.force(
                    str(execution.execution_id), forced, fallback)

    def _reset_scheduler_after_rollback(self) -> None:
        self.scheduler = Scheduler(self.repository)
        self._restore_constraints()

    def _transition(
        self,
        job_id: JobId,
        to_state: JobState,
        *,
        event_id: UUID,
        actor: EventActor,
        event_type: str,
        reason_code: str,
    ):
        job = self.manager.get(job_id)
        if job.state is to_state:
            return job
        return self.manager.transition(TransitionCommand(
            job_id=job_id,
            expected_version=job.version,
            to_state=to_state,
            actor=actor,
            event_type=event_type,
            reason_code=reason_code,
            event_id=event_id,
        )).job

    def submit(
        self,
        request_or_batch,
        idempotency_key: str,
        plan_factory: Callable[[ProducerResult], LegacyPlan],
    ) -> ProducerResult:
        with self._lock:
            try:
                with self.repository.transaction():
                    result = (
                        self.producer.create_batch(
                            request_or_batch, idempotency_key)
                        if isinstance(request_or_batch, CreateBatchRequest)
                        else self.producer.create_job(
                            request_or_batch, idempotency_key)
                    )
                    plan = plan_factory(result)
                    for action in plan.actions:
                        execution = self.scheduler.schedule(
                            JobKind.IMAGE if action.queue_kind == "img"
                            else JobKind.VIDEO,
                            action.queue_ident,
                            tuple(str(job_id) for job_id in action.job_ids),
                            scope_key=(
                                f"{result.idempotency_key}:{action.action_id}"),
                        )
                        jobs = tuple(
                            self.manager.get(job_id) for job_id in action.job_ids)
                        for job in jobs:
                            if job.state is JobState.CREATED:
                                self._transition(
                                    job.job_id, JobState.QUEUED,
                                    event_id=_event_id(
                                        result.idempotency_key, job.job_id,
                                        "queued"),
                                    actor=EventActor.SCHEDULER,
                                    event_type="execution.scheduled",
                                    reason_code="producer.accepted",
                                )
                        forced = next(
                            (job.forced_account_id for job in jobs
                             if job.forced_account_id), None)
                        if forced:
                            self.accounts.force(
                                str(execution.execution_id), forced,
                                any(job.allow_account_fallback for job in jobs),
                            )
                    self.producer.mark_delivered(result.idempotency_key)
                return replace(
                    result,
                    jobs=tuple(self.manager.get(job.job_id) for job in result.jobs),
                )
            except Exception:
                self._reset_scheduler_after_rollback()
                raise

    def job(self, job_id: JobId):
        return self.manager.get(job_id)

    def _member_job_ids(self, execution) -> Tuple[JobId, ...]:
        return tuple(JobId.parse(value) for value in execution.member_keys)

    def lease_next(
        self, kind: JobKind, *, now: float, ttl: float,
    ) -> Optional[RuntimeLease]:
        with self._lock:
            ready = tuple(
                execution for execution in self.scheduler.ready(now)
                if execution.kind is kind
            )
            if not ready:
                return None
            execution = ready[0]
            work_key = str(execution.execution_id)
            try:
                seat = self.accounts.allocate(
                    kind,
                    work_key,
                    now,
                    preferred_account_id=self._preferred_account.get(
                        execution.execution_id),
                    avoid_account_ids=(self._avoid_account[
                        execution.execution_id],)
                    if execution.execution_id in self._avoid_account else (),
                )
            except NoAccountAvailable:
                return None
            try:
                with self.repository.transaction():
                    lease = self.scheduler.lease_next(kind, now, ttl)
                    if lease is None:
                        self.accounts.release(seat.lease_id)
                        return None
                    attempts = self.repository.attempts_for_execution(
                        execution.execution_id)
                    attempt = Attempt(
                        AttemptId.new(), execution.execution_id,
                        len(attempts) + 1, seat.account_id, lease.lease_id,
                        AttemptPhase.PREPARING, CreditConsumption.FALSE,
                    )
                    self.repository.insert_attempt(attempt)
                    member_job_ids = self._member_job_ids(execution)
                    for job_id in member_job_ids:
                        current = self.manager.get(job_id)
                        if current.state is JobState.RETRY_WAIT:
                            current = self._transition(
                                job_id, JobState.QUEUED,
                                event_id=uuid4(),
                                actor=EventActor.SCHEDULER,
                                event_type="retry.due",
                                reason_code="retry.not_before_reached",
                            )
                        if current.state is JobState.QUEUED:
                            self._transition(
                                job_id, JobState.RUNNING,
                                event_id=uuid4(),
                                actor=EventActor.SCHEDULER,
                                event_type="execution.leased",
                                reason_code="worker.accepted",
                            )
                runtime_lease = RuntimeLease(
                    lease_id=lease.lease_id,
                    execution_id=lease.execution_id,
                    attempt_id=attempt.attempt_id,
                    kind=lease.kind,
                    queue_ident=lease.queue_ident,
                    member_job_ids=member_job_ids,
                    account_id=seat.account_id,
                    account_seat_id=seat.lease_id,
                    started_at=float(now),
                    expires_at=lease.expires_at,
                )
                self._leases[lease.lease_id] = runtime_lease
                self._preferred_account.pop(execution.execution_id, None)
                self._avoid_account.pop(execution.execution_id, None)
                self.results.open_lease(lease.lease_id)
                return runtime_lease
            except Exception:
                self.accounts.release(seat.lease_id)
                self._reset_scheduler_after_rollback()
                raise

    def _active_lease(self, lease_id: str) -> RuntimeLease:
        lease = self._leases.get(lease_id)
        if lease is None:
            raise RuntimeLeaseNotFound(lease_id)
        return lease

    def attempt_phase(
        self,
        lease_id: str,
        phase: AttemptPhase,
        *,
        now: float,
        consumes_credit: Optional[CreditConsumption] = None,
    ) -> Attempt:
        with self._lock:
            lease = self._active_lease(lease_id)
            attempt = self.repository.attempt_for_lease(lease_id)
            if attempt is None:
                raise RuntimeLeaseNotFound(lease_id)
            submitted_at = attempt.submitted_at
            credit = consumes_credit or attempt.consumes_credit
            if phase in {
                AttemptPhase.SUBMITTED,
                AttemptPhase.WAITING_PROVIDER,
                AttemptPhase.DOWNLOADING,
                AttemptPhase.SAVING,
            } and submitted_at is None:
                submitted_at = _moment(now)
            updated = replace(
                attempt, phase=phase, consumes_credit=credit,
                submitted_at=submitted_at,
            )
            self.repository.update_attempt(updated)
            return updated

    def _finish_attempt(
        self,
        attempt: Attempt,
        *,
        now: float,
        outcome: AttemptOutcome,
        success_implies_submit: bool = False,
    ) -> Attempt:
        submitted_at = attempt.submitted_at
        credit = attempt.consumes_credit
        if success_implies_submit and submitted_at is None:
            submitted_at = _moment(now)
            credit = CreditConsumption.TRUE
        finished = replace(
            attempt,
            phase=AttemptPhase.FINISHED,
            consumes_credit=credit,
            submitted_at=submitted_at,
            finished_at=_moment(now),
            outcome=outcome,
        )
        self.repository.update_attempt(finished)
        return finished

    def _release_runtime_lease(self, lease: RuntimeLease) -> None:
        self.accounts.release(lease.account_seat_id)
        self.results.close_lease(lease.lease_id)
        self._leases.pop(lease.lease_id, None)

    def attempt_succeeded(
        self,
        lease_id: str,
        *,
        outputs: Tuple[str, ...],
        event_id: UUID,
        now: Optional[float] = None,
    ) -> Mapping[JobId, CommitVerdict]:
        with self._lock:
            if not outputs:
                raise ValueError("success fact cần ít nhất một output")
            replay = self._fact_results.get(event_id)
            if replay is not None:
                return replay  # type: ignore[return-value]
            lease = self._active_lease(lease_id)
            attempt = self.repository.attempt_for_lease(lease_id)
            if attempt is None:
                raise RuntimeLeaseNotFound(lease_id)
            timestamp = self.clock() if now is None else float(now)
            verdicts = {}
            with self.repository.transaction():
                for job_id in lease.member_job_ids:
                    job = self.manager.get(job_id)
                    verdict = self.results.commit(ResultFact(
                        work_key=str(job.asset_id),
                        lease_id=lease_id,
                        outputs=outputs,
                        job_state=job.state,
                        replace_current=job.replace_current,
                        started_at=lease.started_at,
                    ))
                    verdicts[job_id] = verdict
                    self._transition(
                        job_id, JobState.COMPLETED,
                        event_id=_event_id(event_id, job_id, "success"),
                        actor=EventActor.WORKER,
                        event_type="attempt.succeeded",
                        reason_code=verdict.reason_code,
                    )
                self._finish_attempt(
                    attempt, now=timestamp,
                    outcome=AttemptOutcome.SUCCESS,
                    success_implies_submit=True,
                )
                self.scheduler.finish(lease_id)
            self._release_runtime_lease(lease)
            self._fact_results[event_id] = verdicts
            return verdicts

    def attempt_failed(
        self,
        lease_id: str,
        error: ErrorFact,
        *,
        event_id: UUID,
        now: float,
    ) -> RetryDecision:
        with self._lock:
            replay = self._fact_results.get(event_id)
            if replay is not None:
                return replay  # type: ignore[return-value]
            lease = self._active_lease(lease_id)
            attempt = self.repository.attempt_for_lease(lease_id)
            if attempt is None:
                raise RuntimeLeaseNotFound(lease_id)
            history_items = self.repository.attempts_for_execution(
                lease.execution_id)
            submitted_attempts = sum(
                item.submitted_at is not None for item in history_items)
            history = AttemptHistory(
                attempts=max(len(history_items) - 1, submitted_attempts),
                submitted_attempts=submitted_attempts,
            )
            decision = self.retry.decide(error, history, lease.kind)
            outcome = (
                AttemptOutcome.CANCELLED
                if decision.action is RetryAction.CANCEL
                else AttemptOutcome.UNKNOWN
                if decision.action is RetryAction.NEEDS_ATTENTION
                else AttemptOutcome.ERROR
            )
            with self.repository.transaction():
                self._finish_attempt(
                    attempt, now=now, outcome=outcome)
                for job_id in lease.member_job_ids:
                    self._transition(
                        job_id, decision.to_state,
                        event_id=_event_id(event_id, job_id, decision.action.value),
                        actor=EventActor.WORKER,
                        event_type="attempt.failed",
                        reason_code=decision.reason_code,
                    )
                if decision.action is RetryAction.RETRY:
                    self.scheduler.release(
                        lease_id, not_before=float(now) + decision.delay)
                else:
                    self.scheduler.finish(lease_id)
            if decision.cooldown_account:
                self.accounts.cooldown(lease.account_id, float(now) + 300.0)
            if error.error_class is ErrorClass.ACCOUNT_LOST:
                self.accounts.report_error(
                    lease.account_id, fatal=True, now=now)
            if decision.reason_code == "session.reconnect":
                self._preferred_account[lease.execution_id] = lease.account_id
            elif decision.rotate_account:
                self._avoid_account[lease.execution_id] = lease.account_id
            self._release_runtime_lease(lease)
            self._fact_results[event_id] = decision
            return decision

    def cancel(
        self,
        job_id: JobId,
        *,
        event_id: UUID,
        now: float,
    ) -> CancelVerdict:
        with self._lock:
            replay = self._fact_results.get(event_id)
            if replay is not None:
                return replay  # type: ignore[return-value]
            job = self.manager.get(job_id)
            if job.state.is_terminal or job.state is JobState.NEEDS_ATTENTION:
                verdict = CancelVerdict(False, "job.not_cancellable")
                self._fact_results[event_id] = verdict
                return verdict

            runtime_lease = next(
                (lease for lease in self._leases.values()
                 if job_id in lease.member_job_ids),
                None,
            )
            if runtime_lease is not None:
                attempt = self.repository.attempt_for_lease(
                    runtime_lease.lease_id)
                if attempt is None:
                    raise RuntimeLeaseNotFound(runtime_lease.lease_id)
                if (runtime_lease.kind is JobKind.VIDEO
                        and attempt.submitted_at is not None):
                    verdict = CancelVerdict(
                        False, "video.already_submitted")
                    self._fact_results[event_id] = verdict
                    return verdict
                member_job_ids = runtime_lease.member_job_ids
                with self.repository.transaction():
                    self._finish_attempt(
                        attempt, now=now, outcome=AttemptOutcome.CANCELLED)
                    cancelled = []
                    for member_job_id in member_job_ids:
                        current = self.manager.get(member_job_id)
                        if (not current.state.is_terminal
                                and current.state is not JobState.NEEDS_ATTENTION):
                            self._transition(
                                member_job_id, JobState.CANCELLED,
                                event_id=_event_id(
                                    event_id, member_job_id, "cancel"),
                                actor=EventActor.USER,
                                event_type="job.cancelled",
                                reason_code="user.cancelled",
                            )
                            cancelled.append(member_job_id)
                    self.scheduler.finish(runtime_lease.lease_id)
                self.results.revoke_lease(runtime_lease.lease_id)
                self._release_runtime_lease(runtime_lease)
                verdict = CancelVerdict(
                    True, "execution.cancelled", tuple(cancelled))
                self._fact_results[event_id] = verdict
                return verdict

            executions = self.scheduler.executions_for_member(str(job_id))
            cancellable = tuple(
                execution for execution in executions
                if execution.state in {
                    ExecutionState.READY, ExecutionState.WAITING,
                }
            )
            if not cancellable:
                verdict = CancelVerdict(False, "execution.not_cancellable")
                self._fact_results[event_id] = verdict
                return verdict
            member_job_ids = tuple(dict.fromkeys(
                JobId.parse(member)
                for execution in cancellable
                for member in execution.member_keys
            ))
            with self.repository.transaction():
                self.scheduler.cancel_member(str(job_id))
                cancelled = []
                for member_job_id in member_job_ids:
                    current = self.manager.get(member_job_id)
                    if (not current.state.is_terminal
                            and current.state is not JobState.NEEDS_ATTENTION):
                        self._transition(
                            member_job_id, JobState.CANCELLED,
                            event_id=_event_id(
                                event_id, member_job_id, "cancel"),
                            actor=EventActor.USER,
                            event_type="job.cancelled",
                            reason_code="user.cancelled",
                        )
                        cancelled.append(member_job_id)
            verdict = CancelVerdict(
                True, "execution.cancelled", tuple(cancelled))
            self._fact_results[event_id] = verdict
            return verdict

    def note_user_mutation(self, asset_id: str, *, now: float) -> None:
        self.results.note_user_mutation(asset_id, now)
