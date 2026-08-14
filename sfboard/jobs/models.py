from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional
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
