"""Cấp tài khoản cho một lượt chạy — và giữ ràng buộc ép qua MỌI lần thử.

Ba thứ hôm nay đang lẫn vào nhau, ở đây tách hẳn:

  · **`enabled`** là công tắc của USER. Chỉ user bật/tắt.
  · **`health`** là tình trạng do hệ thống quan sát (hết hạn mức → nghỉ tạm,
    mất phiên → hỏng). Hệ thống KHÔNG được tắt `enabled` thay user: tắt rồi thì
    user mở board lên thấy tài khoản của mình bị tắt mà không hiểu vì sao.
  · **`capabilities`** là việc gì máy này làm được. Video chỉ chạy trên profile
    đã mở Grok — bản cũ không phân biệt nên job video rơi sang cửa sổ ChatGPT
    rồi chết với "Không nối được Grok".

Module thuần: không Chrome, không hàng đợi, không đọc đồng hồ (`now` truyền vào).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import threading
from typing import Optional, Tuple
from uuid import uuid4

from .models import JobKind


class AccountError(RuntimeError):
    pass


class NoAccountAvailable(AccountError):
    """Không có chỗ chạy hợp lệ — nói ra, KHÔNG lặng lẽ dùng bừa máy khác.

    Dùng bừa là thứ sinh ra hai lỗi khó tìm nhất: video chạy trên profile chưa
    đăng nhập Grok, và lô bị ép tài khoản lại mở chat trắng ở máy khác."""


class AccountHealth(str, Enum):
    HEALTHY = "healthy"
    COOLDOWN = "cooldown"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class AccountSeat:
    lease_id: str
    account_id: str
    slot: int
    work_key: str
    acquired_at: float


@dataclass
class _Account:
    account_id: str
    allow_video: bool
    max_slots: int
    enabled: bool = True
    cooldown_until: float = 0.0
    broken: bool = False


class AccountAllocator:
    """Chọn tài khoản theo capability · sức khoẻ · chỗ trống · ràng buộc ép."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._accounts: dict[str, _Account] = {}
        self._seats: dict[str, AccountSeat] = {}          # lease_id -> seat
        self._forced: dict[str, Tuple[str, bool]] = {}    # work_key -> (acct, fallback)

    # ──────────────────────────── đăng ký ─────────────────────────────

    def register(self, account_id: str, allow_video: bool = False,
                 max_slots: int = 1) -> None:
        with self._lock:
            cu = self._accounts.get(account_id)
            self._accounts[account_id] = _Account(
                account_id=account_id,
                allow_video=bool(allow_video),
                max_slots=max(1, int(max_slots)),
                enabled=cu.enabled if cu else True,
                cooldown_until=cu.cooldown_until if cu else 0.0,
                broken=cu.broken if cu else False,
            )

    def forget(self, account_id: str) -> None:
        with self._lock:
            self._accounts.pop(account_id, None)

    def accounts(self) -> Tuple[str, ...]:
        with self._lock:
            return tuple(self._accounts)

    # ─────────────────────────── ép tài khoản ─────────────────────────

    def force(self, work_key: str, account_id: str,
              allow_fallback: bool = False) -> None:
        """Ghim việc này vào một tài khoản. Ràng buộc của CẢ JOB, không của một lần."""
        if not work_key or not account_id:
            raise ValueError("work_key/account_id không được rỗng")
        with self._lock:
            self._forced[work_key] = (account_id, bool(allow_fallback))

    def unforce(self, work_key: str) -> None:
        with self._lock:
            self._forced.pop(work_key, None)

    def forced_account_for(self, work_key: str) -> Optional[str]:
        """Tài khoản bị ép của việc này — tầng xếp-lại đọc để trả về đúng hàng riêng."""
        with self._lock:
            rang = self._forced.get(work_key)
            return rang[0] if rang else None

    def allows_fallback(self, work_key: str) -> bool:
        with self._lock:
            rang = self._forced.get(work_key)
            return bool(rang and rang[1])

    # ───────────────────────────── sức khoẻ ───────────────────────────

    def set_enabled(self, account_id: str, enabled: bool) -> None:
        with self._lock:
            acc = self._accounts.get(account_id)
            if acc:
                acc.enabled = bool(enabled)

    def enabled(self, account_id: str) -> bool:
        with self._lock:
            acc = self._accounts.get(account_id)
            return bool(acc and acc.enabled)

    def cooldown(self, account_id: str, until: float) -> None:
        """Cho nghỉ tới mốc `until`. KHÔNG đụng `enabled` của user."""
        with self._lock:
            acc = self._accounts.get(account_id)
            if acc:
                acc.cooldown_until = float(until)

    def report_error(self, account_id: str, fatal: bool, now: float) -> None:
        """Lỗi phiên/cửa sổ mới đánh dấu hỏng. Lỗi dữ liệu KHÔNG phạt tài khoản."""
        del now
        if not fatal:
            return
        with self._lock:
            acc = self._accounts.get(account_id)
            if acc:
                acc.broken = True

    def recover(self, account_id: str) -> None:
        with self._lock:
            acc = self._accounts.get(account_id)
            if acc:
                acc.broken = False
                acc.cooldown_until = 0.0

    def health(self, account_id: str, now: float = 0.0) -> AccountHealth:
        with self._lock:
            acc = self._accounts.get(account_id)
            if acc is None or acc.broken:
                return AccountHealth.UNAVAILABLE
            if acc.cooldown_until > now:
                return AccountHealth.COOLDOWN
            return AccountHealth.HEALTHY

    # ──────────────────────────── cấp chỗ ─────────────────────────────

    def _dang_dung(self, account_id: str) -> int:
        return sum(1 for s in self._seats.values() if s.account_id == account_id)

    def _dung_duoc(self, acc: _Account, kind: JobKind, now: float) -> bool:
        if not acc.enabled or acc.broken or acc.cooldown_until > now:
            return False
        if kind is JobKind.VIDEO and not acc.allow_video:
            return False
        return self._dang_dung(acc.account_id) < acc.max_slots

    def allocate(
        self,
        kind: JobKind,
        work_key: str,
        now: float,
        *,
        preferred_account_id: Optional[str] = None,
        avoid_account_ids: Tuple[str, ...] = (),
    ) -> AccountSeat:
        """Cấp một chỗ ngồi. Ném `NoAccountAvailable` chứ không trả bừa."""
        with self._lock:
            rang = self._forced.get(work_key)
            if rang:
                acct_id, fallback = rang
                acc = self._accounts.get(acct_id)
                if acc is not None and self._dung_duoc(acc, kind, now):
                    return self._ngoi(acc, work_key, now)
                if not fallback:
                    raise NoAccountAvailable(
                        f"{work_key} bị ép vào {acct_id} nhưng máy đó chưa dùng được")
            if rang is None and preferred_account_id is not None:
                preferred = self._accounts.get(preferred_account_id)
                if preferred is not None and self._dung_duoc(preferred, kind, now):
                    return self._ngoi(preferred, work_key, now)
            # Rải đều: chọn máy đang ít việc nhất, hoà thì theo tên cho ổn định.
            san = [a for a in self._accounts.values()
                   if self._dung_duoc(a, kind, now)
                   and a.account_id not in avoid_account_ids]
            # Rotate là ưu tiên đổi máy, không phải lý do để làm việc kẹt mãi
            # khi hệ thống chỉ còn đúng một tài khoản hợp lệ.
            if not san and avoid_account_ids:
                san = [a for a in self._accounts.values()
                       if self._dung_duoc(a, kind, now)]
            if not san:
                raise NoAccountAvailable(
                    f"không có tài khoản hợp lệ cho {kind.value}")
            acc = sorted(san, key=lambda a: (self._dang_dung(a.account_id),
                                             a.account_id))[0]
            return self._ngoi(acc, work_key, now)

    def _ngoi(self, acc: _Account, work_key: str, now: float) -> AccountSeat:
        dang = {s.slot for s in self._seats.values() if s.account_id == acc.account_id}
        slot = next(i for i in range(acc.max_slots) if i not in dang)
        seat = AccountSeat(uuid4().hex, acc.account_id, slot, work_key, float(now))
        self._seats[seat.lease_id] = seat
        return seat

    def release(self, lease_id: str) -> None:
        with self._lock:
            self._seats.pop(lease_id, None)

    def seats_of(self, account_id: str) -> Tuple[AccountSeat, ...]:
        with self._lock:
            return tuple(s for s in self._seats.values()
                         if s.account_id == account_id)

    def diagnostics(self, now: float = 0.0) -> dict:
        with self._lock:
            return {
                "accounts": len(self._accounts),
                "dang_ban": len(self._seats),
                "bi_ep": len(self._forced),
                "suc_khoe": {a: self.health(a, now).value for a in self._accounts},
            }
