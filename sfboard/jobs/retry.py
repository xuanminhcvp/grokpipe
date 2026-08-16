"""MỘT nơi quyết định có thử lại hay không.

Hôm nay quyền này nằm rải ở năm chỗ — thợ, bộ hẹn giờ, auto, người gác và
`chay-anh.py` — mỗi chỗ một bộ đếm riêng. Hậu quả không phải "thử hơi nhiều":
một việc có thể được thử lại 3 lần bởi 3 người khác nhau mà mỗi người tưởng đó
là lần đầu, còn ngân sách thì không ai cộng lại được.

Ở đây chỉ có phép quyết định thuần: vào là (lớp lỗi · lịch sử attempt · loại
việc), ra là một `RetryDecision`. Module này KHÔNG xếp hàng, KHÔNG ghi state,
KHÔNG xoay tài khoản — nó chỉ trả lời, còn ai áp quyết định là việc của tầng
trên.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .errors import ErrorClass, ErrorFact
from .models import AttemptPhase, JobKind, JobState


class RetryAction(str, Enum):
    RETRY = "retry"                     # thử lại sau `delay` giây
    FAIL = "fail"                       # hết đường, kết thúc bằng thất bại
    NEEDS_ATTENTION = "needs_attention"  # KHÔNG chắc đã tốn credit → để user quyết
    CANCEL = "cancel"                   # user đã huỷ, không phải lỗi


@dataclass(frozen=True)
class AttemptHistory:
    """Đã thử bao nhiêu, trong đó bao nhiêu lần thật sự bấm gửi."""
    attempts: int = 0
    submitted_attempts: int = 0
    whole_execution_retries: int = 0

    def __post_init__(self) -> None:
        if min(self.attempts, self.submitted_attempts,
               self.whole_execution_retries) < 0:
            raise ValueError("lịch sử attempt không được âm")
        if self.submitted_attempts > self.attempts:
            raise ValueError("số lần đã gửi không thể lớn hơn số lần thử")


@dataclass(frozen=True)
class RetryDecision:
    action: RetryAction
    delay: float = 0.0
    reason_code: str = ""
    to_state: Optional[JobState] = None
    cooldown_account: bool = False
    rotate_account: bool = False


# TRẦN NGÂN SÁCH — đếm theo số lần ĐÃ BẤM GỬI, không theo số exception.
#
# Đếm exception là cách cũ và nó sai ở đúng chỗ tốn tiền: mười lần rớt mạng
# trước khi bấm gửi chẳng tốn gì, còn hai lần bấm gửi là hai lần trừ credit.
TRAN_GUI = {JobKind.IMAGE: 8, JobKind.VIDEO: 5}
# Lô ảnh chạy lại NGUYÊN LƯỢT tối đa 2 lần (thiếu ảnh giữa lô, lệch số ảnh).
TRAN_CHAY_LAI_CA_LO = 2
BACKOFF_DAU = 20.0
BACKOFF_TRAN = 180.0


def _backoff(lan: int) -> float:
    """Giãn dần rồi chạm trần. Thử lại bắn liền tay thì một việc hỏng vì dữ
    liệu quay vòng vài lần mỗi giây, ngập log và chiếm chỗ việc chạy được."""
    return min(BACKOFF_DAU * max(1, lan), BACKOFF_TRAN)


def _da_bam_gui(phase: AttemptPhase) -> bool:
    return phase in {
        AttemptPhase.SUBMITTED,
        AttemptPhase.WAITING_PROVIDER,
        AttemptPhase.DOWNLOADING,
        AttemptPhase.SAVING,
        AttemptPhase.FINISHED,
    }


class RetryPolicy:
    """Quyết định thuần — không side effect, gọi bao nhiêu lần cũng cùng kết quả."""

    def __init__(self, tran_gui=None,
                 tran_chay_lai=TRAN_CHAY_LAI_CA_LO) -> None:
        self.tran_gui = dict(tran_gui or TRAN_GUI)
        self.tran_chay_lai = int(tran_chay_lai)

    def decide(self, error: ErrorFact, history: AttemptHistory,
               kind: JobKind) -> RetryDecision:
        lop = error.error_class

        # 1. User huỷ — không phải lỗi, không tính ngân sách.
        if lop is ErrorClass.CANCELLED:
            return RetryDecision(RetryAction.CANCEL, reason_code="user.cancelled",
                                 to_state=JobState.CANCELLED)

        # 2. Lỗi DỮ LIỆU: prompt sai, thiếu ref, thiếu start frame. Thử lại ở
        #    máy nào cũng hỏng y hệt — và KHÔNG được phạt tài khoản.
        if lop is ErrorClass.VALIDATION:
            return RetryDecision(RetryAction.FAIL, reason_code="validation.permanent",
                                 to_state=JobState.FAILED)
        if lop is ErrorClass.PERMANENT:
            return RetryDecision(RetryAction.FAIL, reason_code="permanent",
                                 to_state=JobState.FAILED)

        # 3. KHÔNG BIẾT có tốn credit hay không → để user quyết. Đây là luật
        #    quan trọng nhất của video: mất kết nối SAU khi bấm gửi mà tự gửi
        #    lại là trừ credit lần nữa cho đúng shot có thể đã dựng xong.
        if lop is ErrorClass.UNKNOWN_OUTCOME or (
            _da_bam_gui(error.phase) and lop in {ErrorClass.SESSION_TRANSIENT,
                                                 ErrorClass.ACCOUNT_LOST}
        ):
            return RetryDecision(RetryAction.NEEDS_ATTENTION,
                                 reason_code="outcome.unknown",
                                 to_state=JobState.NEEDS_ATTENTION)

        # 4. Hết ngân sách gửi.
        tran = self.tran_gui.get(kind, 5)
        if history.submitted_attempts >= tran:
            return RetryDecision(RetryAction.FAIL,
                                 reason_code=f"budget.exhausted.{tran}",
                                 to_state=JobState.FAILED)
        if history.whole_execution_retries >= self.tran_chay_lai:
            return RetryDecision(RetryAction.FAIL,
                                 reason_code="budget.whole_execution",
                                 to_state=JobState.FAILED)

        # 5. Còn ngân sách: thử lại, có giãn cách.
        cho = _backoff(history.attempts + 1)
        if lop is ErrorClass.QUOTA_RATE_LIMIT:
            # Hết hạn mức là chuyện của TÀI KHOẢN, không phải của việc: cho máy
            # đó nghỉ, việc vẫn chạy được ngay ở máy khác.
            return RetryDecision(RetryAction.RETRY, delay=cho,
                                 reason_code="quota.cooldown",
                                 to_state=JobState.RETRY_WAIT,
                                 cooldown_account=True, rotate_account=True)
        if lop is ErrorClass.ACCOUNT_LOST:
            return RetryDecision(RetryAction.RETRY, delay=cho,
                                 reason_code="account.lost",
                                 to_state=JobState.RETRY_WAIT,
                                 rotate_account=True)
        if lop is ErrorClass.SESSION_TRANSIENT:
            # TRƯỚC submit: thử lại NGAY trên chính tài khoản đó một lần —
            # nối lại phiên rẻ hơn nhiều so với mở chat trắng ở máy khác.
            if history.attempts == 0:
                return RetryDecision(RetryAction.RETRY, delay=0.0,
                                     reason_code="session.reconnect",
                                     to_state=JobState.RETRY_WAIT)
            return RetryDecision(RetryAction.RETRY, delay=cho,
                                 reason_code="session.transient",
                                 to_state=JobState.RETRY_WAIT,
                                 rotate_account=True)
        return RetryDecision(RetryAction.RETRY, delay=cho,
                             reason_code="provider.transient",
                             to_state=JobState.RETRY_WAIT,
                             rotate_account=True)

    def decide_partial(
        self, history: AttemptHistory, kind: JobKind,
    ) -> RetryDecision:
        """Retry cả execution khi lô trả thiếu, không hồi sinh member đã xong."""
        tran = self.tran_gui.get(kind, 5)
        if history.submitted_attempts >= tran:
            return RetryDecision(
                RetryAction.FAIL,
                reason_code=f"budget.exhausted.{tran}",
                to_state=JobState.FAILED,
            )
        if history.whole_execution_retries >= self.tran_chay_lai:
            return RetryDecision(
                RetryAction.FAIL,
                reason_code="budget.whole_execution",
                to_state=JobState.FAILED,
            )
        return RetryDecision(
            RetryAction.RETRY,
            delay=_backoff(history.whole_execution_retries + 1),
            reason_code="batch.partial",
            to_state=JobState.RETRY_WAIT,
        )
