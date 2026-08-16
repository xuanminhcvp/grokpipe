"""Lịch chạy theo `execution_id` và lease atomic.

Hàng đợi legacy mang TÊN ASSET (`LO:a,b`, `V-S1-01`), nên nó không phân biệt
được "việc" với "thứ việc đó tạo ra", và không trả lời được hai câu hỏi:

  · thành viên `A` đang nằm trong lô vật lý nào? — `JOBS` chỉ có nhãn từng
    thành viên lúc lô mới xếp, khoá `LO:a,b` chưa tồn tại;
  · việc này đã có thợ nhận chưa? — legacy nhấc việc rồi mới ghi nhãn
    `running`, khoảng giữa là lúc người gác tưởng việc mồ côi và xếp lại.

Module này thuần dữ liệu: KHÔNG hàng đợi thật, KHÔNG Chrome, KHÔNG tài khoản,
KHÔNG đọc đồng hồ — `now` do người gọi truyền vào để test không phải ngủ và để
phase sau cắm được đồng hồ bền vững (SQLite) mà không sửa logic.

Trong Phase 4 đây vẫn là bản sao quan sát: `PriorityQueue` legacy vẫn là thứ
thực sự đưa việc tới thợ.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
import itertools
import threading
from typing import Optional, Tuple
from uuid import uuid4

from .models import ExecutionId, ExecutionState, JobKind


class SchedulerError(RuntimeError):
    pass


class LeaseNotFound(SchedulerError):
    pass


class StaleLease(SchedulerError):
    """Lease đã bị thu hồi (hết hạn hoặc release) rồi mới có người dùng lại.

    Đây là chỗ chặn thợ zombie: cửa sổ Chrome treo 10 phút rồi tỉnh dậy báo
    "xong" cho một lượt mà việc đã được thuê lại từ lâu."""


@dataclass(frozen=True)
class ScheduledExecution:
    execution_id: ExecutionId
    kind: JobKind
    queue_ident: str
    member_keys: Tuple[str, ...]
    priority: int
    not_before: float
    seq: int
    state: ExecutionState
    scope_key: str = ""
    version: int = 0
    lease_id: Optional[str] = None
    lease_expires_at: Optional[float] = None


@dataclass(frozen=True)
class ExecutionLease:
    lease_id: str
    execution_id: ExecutionId
    kind: JobKind
    queue_ident: str
    member_keys: Tuple[str, ...]
    expires_at: float
    version: int


class Scheduler:
    """Lịch trong bộ nhớ. Mọi thao tác đổi trạng thái nằm trong một lock."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._seq = itertools.count()
        self._by_id: dict[ExecutionId, ScheduledExecution] = {}
        self._by_ident: dict[Tuple[str, str], ExecutionId] = {}
        self._by_scope: dict[Tuple[str, str], ExecutionId] = {}
        self._by_lease: dict[str, ExecutionId] = {}
        # Lease ĐÃ TỪNG có thật rồi bị thu hồi. Giữ lại để phân biệt "token của
        # thợ zombie" (StaleLease — có thật, đã hết hiệu lực) với "token bịa"
        # (LeaseNotFound). Hai ca này cần xử lý khác nhau, gộp lại là mất dấu.
        self._da_thu_hoi: "deque[str]" = deque(maxlen=512)
        self._thu_hoi_set: set[str] = set()

    # ─────────────────────────── xếp lịch ────────────────────────────

    def schedule(
        self,
        kind: JobKind,
        queue_ident: str,
        member_keys: Tuple[str, ...],
        priority: int = 0,
        not_before: float = 0.0,
        scope_key: Optional[str] = None,
    ) -> ScheduledExecution:
        """Đặt lịch cho một execution. Cùng ident đang sống thì trả lại bản cũ.

        Idempotent theo `queue_ident` vì tầng trên có thể giao lại cùng một ý
        định (replay, người gác, restart adapter) — tạo execution thứ hai là
        đúng lỗi hai-lượt-render mà Phase 3 vừa chặn ở cửa producer."""
        if not queue_ident or not queue_ident.strip():
            raise ValueError("queue_ident không được rỗng")
        if not member_keys or any(not k or not k.strip() for k in member_keys):
            raise ValueError("member_keys không được rỗng")
        with self._lock:
            khoa = (kind.value, queue_ident)
            pham_vi = (kind.value, (scope_key or queue_ident).strip())
            scope_id = self._by_scope.get(pham_vi)
            if scope_id is not None:
                cu = self._by_id[scope_id]
                if cu.state in (ExecutionState.READY, ExecutionState.LEASED,
                                ExecutionState.WAITING):
                    return cu
            cu_id = self._by_ident.get(khoa)
            if cu_id is not None:
                cu = self._by_id[cu_id]
                if cu.state in (ExecutionState.READY, ExecutionState.LEASED,
                                ExecutionState.WAITING):
                    return cu
            exe = ScheduledExecution(
                execution_id=ExecutionId.new(),
                kind=kind,
                queue_ident=queue_ident,
                member_keys=tuple(member_keys),
                priority=int(priority),
                not_before=float(not_before),
                seq=next(self._seq),
                state=ExecutionState.READY,
                scope_key=pham_vi[1],
            )
            self._by_id[exe.execution_id] = exe
            self._by_ident[khoa] = exe.execution_id
            self._by_scope[pham_vi] = exe.execution_id
            return exe

    # ──────────────────────────── tra cứu ────────────────────────────

    def get(self, execution_id: ExecutionId) -> Optional[ScheduledExecution]:
        with self._lock:
            return self._by_id.get(execution_id)

    def get_by_ident(self, queue_ident: str,
                     kind: JobKind = JobKind.IMAGE) -> Optional[ScheduledExecution]:
        with self._lock:
            exe_id = self._by_ident.get((kind.value, queue_ident))
            return self._by_id.get(exe_id) if exe_id else None

    def ready(self, now: float) -> Tuple[ScheduledExecution, ...]:
        """Việc đã tới giờ và chưa ai nhận, theo đúng thứ tự sẽ được thuê."""
        with self._lock:
            san = [e for e in self._by_id.values()
                   if e.state is ExecutionState.READY and e.not_before <= now]
        return tuple(sorted(san, key=lambda e: (e.priority, e.seq)))

    def execution_for_member(
        self, member_key: str, kind: JobKind = JobKind.IMAGE
    ) -> Optional[ScheduledExecution]:
        """Thành viên này đang nằm trong execution nào (READY hoặc LEASED)?

        Đây là câu trả lời cho `/api/huy-viec`: huỷ một ảnh trong lô phải tra ra
        được lô VẬT LÝ, thứ mà quét `JOBS` không làm được lúc lô mới xếp."""
        with self._lock:
            song = [e for e in self._by_id.values()
                    if e.kind is kind
                    and member_key in e.member_keys
                    and e.state in (ExecutionState.READY, ExecutionState.LEASED,
                                    ExecutionState.WAITING)]
        return sorted(song, key=lambda e: e.seq)[0] if song else None

    def executions_for_member(
        self, member_key: str
    ) -> Tuple[ScheduledExecution, ...]:
        with self._lock:
            song = [e for e in self._by_id.values()
                    if member_key in e.member_keys
                    and e.state in (ExecutionState.READY, ExecutionState.WAITING)]
        return tuple(sorted(song, key=lambda e: e.seq))

    # ───────────────────────────── lease ─────────────────────────────

    def lease_next(self, kind: JobKind, now: float,
                   ttl: float) -> Optional[ExecutionLease]:
        """Nhận việc kế tiếp. CHỌN và ĐỔI TRẠNG THÁI trong cùng một lock.

        Legacy làm hai nhịp (`_lay()` rồi mới `_dat_job(running)`); khoảng giữa
        là chỗ người gác xếp lại việc đang có thợ cầm."""
        with self._lock:
            san = [e for e in self._by_id.values()
                   if e.kind is kind
                   and e.state is ExecutionState.READY
                   and e.not_before <= now]
            if not san:
                return None
            exe = sorted(san, key=lambda e: (e.priority, e.seq))[0]
            return self._cho_thue(exe, now, ttl)

    def lease_ident(self, kind: JobKind, queue_ident: str, now: float,
                    ttl: float) -> Optional[ExecutionLease]:
        """Thợ legacy đã nhấc ident này — gắn lease vào đúng execution của nó."""
        with self._lock:
            exe = self.get_by_ident(queue_ident, kind)
            if exe is None or exe.state is not ExecutionState.READY:
                return None
            return self._cho_thue(exe, now, ttl)

    def _cho_thue(self, exe: ScheduledExecution, now: float,
                  ttl: float) -> ExecutionLease:
        lease_id = uuid4().hex
        moi = replace(
            exe,
            state=ExecutionState.LEASED,
            version=exe.version + 1,
            lease_id=lease_id,
            lease_expires_at=now + float(ttl),
        )
        self._by_id[moi.execution_id] = moi
        self._by_lease[lease_id] = moi.execution_id
        return ExecutionLease(
            lease_id=lease_id,
            execution_id=moi.execution_id,
            kind=moi.kind,
            queue_ident=moi.queue_ident,
            member_keys=moi.member_keys,
            expires_at=moi.lease_expires_at,
            version=moi.version,
        )

    def _thu_hoi(self, lease_id: str) -> None:
        self._by_lease.pop(lease_id, None)
        if lease_id in self._thu_hoi_set:
            return
        if len(self._da_thu_hoi) == self._da_thu_hoi.maxlen:
            self._thu_hoi_set.discard(self._da_thu_hoi[0])
        self._da_thu_hoi.append(lease_id)
        self._thu_hoi_set.add(lease_id)

    def _doc_lease(self, lease_id: str) -> ScheduledExecution:
        exe_id = self._by_lease.get(lease_id)
        if exe_id is None:
            if lease_id in self._thu_hoi_set:
                raise StaleLease(lease_id)
            raise LeaseNotFound(lease_id)
        exe = self._by_id[exe_id]
        if exe.lease_id != lease_id:
            raise StaleLease(lease_id)
        return exe

    def heartbeat(self, lease_id: str, now: float, ttl: float = 30.0) -> None:
        with self._lock:
            exe = self._doc_lease(lease_id)
            self._by_id[exe.execution_id] = replace(
                exe, lease_expires_at=now + float(ttl))

    def finish(self, lease_id: str) -> ScheduledExecution:
        with self._lock:
            exe = self._doc_lease(lease_id)
            xong = replace(exe, state=ExecutionState.FINISHED,
                           version=exe.version + 1,
                           lease_id=None, lease_expires_at=None)
            self._by_id[exe.execution_id] = xong
            self._thu_hoi(lease_id)
            return xong

    def release(self, lease_id: str,
                not_before: float = 0.0) -> ScheduledExecution:
        """Trả việc về hàng — dùng khi thợ bỏ dở, chưa phải là thất bại cuối."""
        with self._lock:
            exe = self._doc_lease(lease_id)
            tra = replace(exe, state=ExecutionState.READY,
                          version=exe.version + 1,
                          not_before=float(not_before),
                          lease_id=None, lease_expires_at=None)
            self._by_id[exe.execution_id] = tra
            self._thu_hoi(lease_id)
            return tra

    def expire_leases(self, now: float) -> Tuple[ScheduledExecution, ...]:
        """Thu hồi lease quá hạn. Token cũ sau đó thành `StaleLease`."""
        with self._lock:
            het = [e for e in self._by_id.values()
                   if e.state is ExecutionState.LEASED
                   and e.lease_expires_at is not None
                   and e.lease_expires_at <= now]
            ra = []
            for exe in het:
                self._thu_hoi(exe.lease_id)
                tra = replace(exe, state=ExecutionState.READY,
                              version=exe.version + 1,
                              lease_id=None, lease_expires_at=None)
                self._by_id[exe.execution_id] = tra
                ra.append(tra)
        return tuple(ra)

    # ────────────────────────────── huỷ ──────────────────────────────

    def cancel_member(self, member_key: str) -> Tuple[ScheduledExecution, ...]:
        """Huỷ mọi execution ĐANG CHỜ có chứa thành viên này.

        Execution đang được thuê KHÔNG bị gỡ ngầm: thợ đang nằm trong lượt chờ
        provider, cắt sau lưng nó là mất ảnh đã sinh mà không thu lại được."""
        with self._lock:
            bo = [e for e in self._by_id.values()
                  if member_key in e.member_keys
                  and e.state in (ExecutionState.READY, ExecutionState.WAITING)]
            ra = []
            for exe in sorted(bo, key=lambda e: e.seq):
                huy = replace(exe, state=ExecutionState.FINISHED,
                              version=exe.version + 1,
                              lease_id=None, lease_expires_at=None)
                self._by_id[exe.execution_id] = huy
                ra.append(huy)
        return tuple(ra)

    def cancel_execution(self, execution_id: ExecutionId) -> bool:
        with self._lock:
            exe = self._by_id.get(execution_id)
            if exe is None or exe.state is not ExecutionState.READY:
                return False
            self._by_id[execution_id] = replace(
                exe, state=ExecutionState.FINISHED, version=exe.version + 1)
            return True

    def diagnostics(self) -> dict:
        with self._lock:
            dem: dict[str, int] = {}
            for exe in self._by_id.values():
                dem[exe.state.value] = dem.get(exe.state.value, 0) + 1
            return {"executions": len(self._by_id), "theo_trang_thai": dem}
