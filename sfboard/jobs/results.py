"""MỘT cửa nhận kết quả — và quyền từ chối kết quả về muộn.

Ca đã cắn thật: một lượt render treo 10 phút, user sốt ruột tự dán ảnh khác vào
thẻ, rồi lượt cũ tỉnh dậy và ghi đè lên ảnh user vừa dán. Không có lỗi nào được
in ra: về mặt kỹ thuật lượt đó "thành công".

Cửa này trả lời đúng một câu: *kết quả này còn thuộc về ý định hiện tại không?*
Bốn lý do từ chối:

  · lease đã bị thu hồi (thợ zombie tỉnh dậy sau khi việc đã được giao lại);
  · job đã kết thúc (huỷ, hoặc một lượt khác đã xong trước);
  · người dùng đã tự thay ảnh/video sau khi lượt này bắt đầu;
  · job không mang quyền `replace_current` (bản chạy thêm để so, không phải để đè).

Module thuần: không đụng file, không hàng đợi, không provider. Nó QUYẾT ĐỊNH,
còn ai ghi đĩa là việc của tầng trên.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import threading
from typing import Optional, Tuple

from .models import JobState


class CommitDecision(str, Enum):
    ACCEPT = "accept"                   # ghi đè bản đang dùng
    STORE_AS_VERSION = "store_as_version"  # giữ lại để so, KHÔNG đè
    REJECT = "reject"                   # bỏ hẳn


@dataclass(frozen=True)
class ResultFact:
    """Một kết quả do executor mang về."""
    work_key: str
    lease_id: str
    outputs: Tuple[str, ...]
    job_state: JobState = JobState.RUNNING
    replace_current: bool = True
    started_at: float = 0.0

    def __post_init__(self) -> None:
        if not self.work_key.strip() or not self.lease_id.strip():
            raise ValueError("work_key/lease_id không được rỗng")


@dataclass(frozen=True)
class CommitVerdict:
    decision: CommitDecision
    reason_code: str
    outputs: Tuple[str, ...] = ()

    @property
    def ghi_de(self) -> bool:
        return self.decision is CommitDecision.ACCEPT


@dataclass
class _TrangThai:
    lease_hop_le: set = field(default_factory=set)
    user_sua_luc: dict = field(default_factory=dict)


class ResultCommit:
    """Nhận hoặc loại kết quả theo lease · trạng thái job · dấu tay người dùng."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._s = _TrangThai()

    # ─────────────────────── ghi nhận bối cảnh ────────────────────────

    def open_lease(self, lease_id: str) -> None:
        with self._lock:
            self._s.lease_hop_le.add(lease_id)

    def revoke_lease(self, lease_id: str) -> None:
        """Thu hồi — lượt cũ từ giờ không ghi đè được nữa."""
        with self._lock:
            self._s.lease_hop_le.discard(lease_id)

    def note_user_mutation(self, work_key: str, now: float) -> None:
        """User vừa TỰ dán/xoá/chọn bản khác cho thẻ này.

        Ảnh user tự đưa vào là bản chuẩn tuyệt đối — không lượt render nào đang
        chạy dở được phép đè lên nó."""
        with self._lock:
            self._s.user_sua_luc[work_key] = float(now)

    def last_user_mutation(self, work_key: str) -> Optional[float]:
        with self._lock:
            return self._s.user_sua_luc.get(work_key)

    # ──────────────────────────── phán quyết ──────────────────────────

    def commit(self, fact: ResultFact) -> CommitVerdict:
        with self._lock:
            if fact.lease_id not in self._s.lease_hop_le:
                return CommitVerdict(CommitDecision.REJECT, "lease.revoked")
            if fact.job_state.is_terminal:
                return CommitVerdict(CommitDecision.REJECT, "job.terminal")
            if not fact.outputs:
                return CommitVerdict(CommitDecision.REJECT, "no_output")
            sua = self._s.user_sua_luc.get(fact.work_key)
            if sua is not None and sua >= fact.started_at:
                # Kết quả vẫn giữ lại làm bản để so — nó tốn lượt thật rồi, vứt
                # đi là mất trắng; nhưng KHÔNG được đè lên bản user đã chọn.
                return CommitVerdict(CommitDecision.STORE_AS_VERSION,
                                     "user_mutation_wins", fact.outputs)
            if not fact.replace_current:
                return CommitVerdict(CommitDecision.STORE_AS_VERSION,
                                     "extra_copy", fact.outputs)
            return CommitVerdict(CommitDecision.ACCEPT, "accepted", fact.outputs)

    def close_lease(self, lease_id: str) -> None:
        self.revoke_lease(lease_id)

    def diagnostics(self) -> dict:
        with self._lock:
            return {
                "lease_dang_mo": len(self._s.lease_hop_le),
                "the_user_da_sua": len(self._s.user_sua_luc),
            }
