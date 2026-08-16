"""Typed values đi qua worker/executor boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from .models import AttemptId, ExecutionId, JobId, JobKind


@dataclass(frozen=True)
class RuntimeLease:
    lease_id: str
    execution_id: ExecutionId
    attempt_id: AttemptId
    kind: JobKind
    queue_ident: str
    member_job_ids: Tuple[JobId, ...]
    account_id: str
    account_seat_id: str
    started_at: float
    expires_at: float


@dataclass(frozen=True)
class CancelVerdict:
    accepted: bool
    reason_code: str
    cancelled_job_ids: Tuple[JobId, ...] = ()


@dataclass(frozen=True)
class RecoverySummary:
    retried: int = 0
    needs_attention: int = 0
    untouched: int = 0
