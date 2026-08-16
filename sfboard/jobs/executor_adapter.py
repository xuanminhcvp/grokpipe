"""Biên executor: chạy đúng một attempt và chỉ phát lifecycle fact.

Module không biết hàng đợi, browser hay provider. DOM executor được tiêm vào;
mọi retry/state/account/result decision đều quay về `LifecycleRuntime`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Callable, Mapping, Optional, Tuple
from uuid import uuid4

from .errors import ErrorClass, ErrorFact
from .facts import RuntimeLease
from .models import AttemptPhase, CreditConsumption, JobId
from .results import CommitVerdict
from .retry import RetryDecision
from .runtime import LifecycleRuntime


@dataclass(frozen=True)
class ExecutorAttemptResult:
    outputs: Mapping[JobId, Tuple[str, ...]]


@dataclass(frozen=True)
class ExecutorRunOutcome:
    verdicts: Mapping[JobId, CommitVerdict] = field(default_factory=dict)
    decision: Optional[RetryDecision] = None


PhaseEmitter = Callable[..., object]
AttemptExecutor = Callable[
    [RuntimeLease, PhaseEmitter], ExecutorAttemptResult,
]
ExceptionClassifier = Callable[[Exception, AttemptPhase], ErrorFact]


def _default_classifier(exc: Exception, phase: AttemptPhase) -> ErrorFact:
    submitted = phase in {
        AttemptPhase.SUBMITTED,
        AttemptPhase.WAITING_PROVIDER,
        AttemptPhase.DOWNLOADING,
        AttemptPhase.SAVING,
    }
    return ErrorFact(
        ErrorClass.UNKNOWN_OUTCOME if submitted
        else ErrorClass.PROVIDER_TRANSIENT,
        str(exc).strip() or type(exc).__name__,
        phase,
    )


class LegacyExecutorAdapter:
    """Adapter một-attempt; không vòng lặp và không tự xếp lại."""

    def __init__(
        self,
        runtime: LifecycleRuntime,
        *,
        classify_exception: ExceptionClassifier = _default_classifier,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.runtime = runtime
        self.classify_exception = classify_exception
        self.clock = clock

    def run_once(
        self,
        lease: RuntimeLease,
        execute: AttemptExecutor,
    ) -> ExecutorRunOutcome:
        phase_now = AttemptPhase.PREPARING

        def emit_phase(
            phase: AttemptPhase,
            *,
            consumes_credit: Optional[CreditConsumption] = None,
        ):
            nonlocal phase_now
            phase_now = phase
            credit = consumes_credit
            if credit is None and phase in {
                AttemptPhase.SUBMITTED,
                AttemptPhase.WAITING_PROVIDER,
                AttemptPhase.DOWNLOADING,
                AttemptPhase.SAVING,
            }:
                credit = CreditConsumption.UNKNOWN
            return self.runtime.attempt_phase(
                lease.lease_id,
                phase,
                now=self.clock(),
                consumes_credit=credit,
            )

        try:
            result = execute(lease, emit_phase)
        except Exception as exc:
            decision = self.runtime.attempt_failed(
                lease.lease_id,
                self.classify_exception(exc, phase_now),
                event_id=uuid4(),
                now=self.clock(),
            )
            return ExecutorRunOutcome(decision=decision)
        verdicts = self.runtime.attempt_succeeded(
            lease.lease_id,
            outputs=result.outputs,
            event_id=uuid4(),
            now=self.clock(),
        )
        return ExecutorRunOutcome(verdicts=verdicts)
