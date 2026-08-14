from dataclasses import dataclass
from enum import Enum

from .models import AttemptPhase


class ErrorClass(str, Enum):
    VALIDATION = "validation"
    CANCELLED = "cancelled"
    SESSION_TRANSIENT = "session_transient"
    PROVIDER_TRANSIENT = "provider_transient"
    QUOTA_RATE_LIMIT = "quota_rate_limit"
    PERMANENT = "permanent"
    UNKNOWN_OUTCOME = "unknown_outcome"
    ACCOUNT_LOST = "account_lost"


@dataclass(frozen=True)
class ErrorFact:
    error_class: ErrorClass
    message: str
    phase: AttemptPhase
    provider_code: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.error_class, ErrorClass):
            raise TypeError("error_class phải dùng ErrorClass")
        if not isinstance(self.phase, AttemptPhase):
            raise TypeError("phase phải dùng AttemptPhase")
        if not self.message.strip():
            raise ValueError("error message không được rỗng")
        if self.error_class is ErrorClass.UNKNOWN_OUTCOME and self.phase in {
            AttemptPhase.PREPARING,
            AttemptPhase.ATTACHING,
            AttemptPhase.READY_TO_SUBMIT,
        }:
            raise ValueError("unknown outcome chỉ hợp lệ từ submit boundary")
