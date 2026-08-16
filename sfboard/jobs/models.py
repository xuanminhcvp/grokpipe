from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Tuple
from uuid import UUID, uuid4


@dataclass(frozen=True)
class AssetId:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("asset_id không được rỗng")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class _UuidId:
    value: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.value, UUID):
            raise TypeError(f"{type(self).__name__}.value phải là UUID")

    @classmethod
    def new(cls):
        return cls(uuid4())

    @classmethod
    def parse(cls, value: str):
        try:
            return cls(UUID(value))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError(f"{cls.__name__} phải là UUID hợp lệ") from exc

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class JobId(_UuidId):
    pass


@dataclass(frozen=True)
class BatchId(_UuidId):
    pass


@dataclass(frozen=True)
class ExecutionId(_UuidId):
    pass


@dataclass(frozen=True)
class AttemptId(_UuidId):
    pass


class JobState(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_ATTENTION = "needs_attention"

    @property
    def is_terminal(self) -> bool:
        return self in {self.COMPLETED, self.FAILED, self.CANCELLED}


class JobKind(str, Enum):
    IMAGE = "image"
    VIDEO = "video"


class JobOrigin(str, Enum):
    MANUAL = "manual"
    AUTO = "auto"
    CLI = "cli"
    COMPATIBILITY = "compatibility"


@dataclass(frozen=True)
class Job:
    job_id: JobId
    asset_id: AssetId
    kind: JobKind
    origin: JobOrigin
    state: JobState = JobState.CREATED
    version: int = 0
    batch_id: Optional[BatchId] = None
    rerun_of: Optional[JobId] = None
    copy_index: Optional[int] = None
    replace_current: bool = False
    forced_account_id: Optional[str] = None
    allow_account_fallback: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.job_id, JobId) or not isinstance(self.asset_id, AssetId):
            raise TypeError("job_id và asset_id phải dùng đúng typed identity")
        if not isinstance(self.kind, JobKind) or not isinstance(self.origin, JobOrigin):
            raise TypeError("kind và origin phải dùng enum chuẩn")
        if not isinstance(self.state, JobState):
            raise TypeError("state phải dùng JobState")
        if self.version < 0:
            raise ValueError("version không được âm")
        if self.copy_index is not None and self.copy_index < 0:
            raise ValueError("copy_index không được âm")
        if self.allow_account_fallback and not self.forced_account_id:
            raise ValueError("fallback chỉ có nghĩa khi job ép account")


class BatchMode(str, Enum):
    IMAGE_GROUP = "image_group"
    MULTI_COPY = "multi_copy"
    BULK_VIDEO = "bulk_video"


@dataclass(frozen=True)
class Batch:
    batch_id: BatchId
    kind: JobKind
    mode: BatchMode
    member_job_ids: Tuple[JobId, ...]

    def __post_init__(self) -> None:
        if not self.member_job_ids or len(set(self.member_job_ids)) != len(
            self.member_job_ids
        ):
            raise ValueError("batch cần member duy nhất và không rỗng")
        if not all(isinstance(job_id, JobId) for job_id in self.member_job_ids):
            raise TypeError("batch member phải là JobId")
        if (
            self.mode in {BatchMode.IMAGE_GROUP, BatchMode.MULTI_COPY}
            and self.kind is not JobKind.IMAGE
        ):
            raise ValueError("image batch phải có kind=image")
        if self.mode is BatchMode.BULK_VIDEO and self.kind is not JobKind.VIDEO:
            raise ValueError("bulk_video phải có kind=video")


class ExecutionState(str, Enum):
    READY = "ready"
    LEASED = "leased"
    WAITING = "waiting"
    FINISHED = "finished"


@dataclass(frozen=True)
class Execution:
    execution_id: ExecutionId
    kind: JobKind
    member_job_ids: Tuple[JobId, ...]
    state: ExecutionState
    priority: int

    def __post_init__(self) -> None:
        if not self.member_job_ids or len(set(self.member_job_ids)) != len(
            self.member_job_ids
        ):
            raise ValueError("execution cần member duy nhất và không rỗng")
        if not all(isinstance(job_id, JobId) for job_id in self.member_job_ids):
            raise TypeError("execution member phải là JobId")


class AttemptPhase(str, Enum):
    PREPARING = "preparing"
    ATTACHING = "attaching"
    READY_TO_SUBMIT = "ready_to_submit"
    SUBMITTED = "submitted"
    WAITING_PROVIDER = "waiting_provider"
    DOWNLOADING = "downloading"
    SAVING = "saving"
    FINISHED = "finished"


class AttemptOutcome(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class CreditConsumption(str, Enum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Attempt:
    attempt_id: AttemptId
    execution_id: ExecutionId
    number: int
    account_id: str
    lease_id: str
    phase: AttemptPhase
    consumes_credit: CreditConsumption
    submitted_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    outcome: Optional[AttemptOutcome] = None

    def __post_init__(self) -> None:
        if self.number < 1 or not self.account_id or not self.lease_id:
            raise ValueError("attempt number/account/lease không hợp lệ")
        submitted_phase = self.phase in {
            AttemptPhase.SUBMITTED,
            AttemptPhase.WAITING_PROVIDER,
            AttemptPhase.DOWNLOADING,
            AttemptPhase.SAVING,
        }
        before_submit_phase = self.phase in {
            AttemptPhase.PREPARING,
            AttemptPhase.ATTACHING,
            AttemptPhase.READY_TO_SUBMIT,
        }
        if submitted_phase and self.submitted_at is None:
            raise ValueError("phase sau submit cần submitted_at")
        if before_submit_phase and self.submitted_at is not None:
            raise ValueError("phase trước submit không được có submitted_at")
        if ((submitted_phase or self.submitted_at is not None)
                and self.consumes_credit is CreditConsumption.FALSE):
            raise ValueError("submit phải consume credit hoặc unknown")
        if ((before_submit_phase or self.submitted_at is None)
                and self.consumes_credit is not CreditConsumption.FALSE):
            raise ValueError("trước submit consumes_credit phải false")
        if self.phase is AttemptPhase.FINISHED:
            if self.finished_at is None or self.outcome is None:
                raise ValueError("finished attempt cần finished_at và outcome")
        elif self.finished_at is not None or self.outcome is not None:
            raise ValueError("attempt chưa finished không được có terminal fields")


class EventActor(str, Enum):
    API = "api"
    AUTO = "auto"
    MANAGER = "manager"
    SCHEDULER = "scheduler"
    WORKER = "worker"
    USER = "user"
    RECOVERY = "recovery"


@dataclass(frozen=True)
class JobEvent:
    event_id: UUID
    job_id: JobId
    actor: EventActor
    event_type: str
    reason_code: str
    from_state: Optional[JobState] = None
    to_state: Optional[JobState] = None
    attempt_id: Optional[AttemptId] = None

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, UUID) or not isinstance(self.job_id, JobId):
            raise TypeError("event_id/job_id không đúng typed identity")
        if not isinstance(self.actor, EventActor):
            raise TypeError("actor phải dùng EventActor")
        if not self.event_type or not self.reason_code:
            raise ValueError("event_type/reason_code không được rỗng")
        if (self.from_state is None) != (self.to_state is None):
            raise ValueError("transition event cần cả from_state và to_state")


@dataclass(frozen=True)
class AccountLease:
    lease_id: str
    account_id: str
    attempt_id: AttemptId
    slot: int
    acquired_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if not self.lease_id or not self.account_id or self.slot < 0:
            raise ValueError("account lease không hợp lệ")
        if not isinstance(self.attempt_id, AttemptId):
            raise TypeError("attempt_id phải dùng AttemptId")
        if self.expires_at <= self.acquired_at:
            raise ValueError("lease expiry phải sau acquired_at")
