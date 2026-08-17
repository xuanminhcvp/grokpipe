"""Bộ đếm submit bền vững cho live provider có tính credit.

Reservation xảy ra trước thao tác DOM và không hoàn lại. Đếm bảo thủ như vậy
đảm bảo click thật không thể vượt trần dù process chết hoặc nút submit báo lỗi.
"""

from __future__ import annotations

from dataclasses import dataclass
import fcntl
import json
import os
from pathlib import Path
import tempfile
from typing import Optional, Union


class SubmitBudgetError(RuntimeError):
    pass


class BudgetConfigurationError(SubmitBudgetError):
    pass


class BudgetScopeConflict(SubmitBudgetError):
    pass


class BudgetExhausted(SubmitBudgetError):
    pass


@dataclass(frozen=True)
class SubmitBudgetSnapshot:
    scope: str
    limit: int
    reserved: int

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.reserved)


class PersistentSubmitBudget:
    """Atomic counter dùng lock file ổn định và replace state file."""

    VERSION = 1

    def __init__(
        self,
        path: Union[str, Path],
        *,
        scope: str,
        limit: Optional[Union[int, str]],
    ) -> None:
        scope = str(scope).strip()
        if not scope:
            raise BudgetConfigurationError("Grok live budget cần scope")
        try:
            parsed_limit = int(limit)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise BudgetConfigurationError(
                "Grok live budget cần limit nguyên dương") from None
        if parsed_limit <= 0:
            raise BudgetConfigurationError(
                "Grok live budget cần limit nguyên dương")
        self.path = Path(path)
        self.scope = scope
        self.limit = parsed_limit
        self.lock_path = self.path.with_name(self.path.name + ".lock")

    def _empty(self) -> SubmitBudgetSnapshot:
        return SubmitBudgetSnapshot(self.scope, self.limit, 0)

    def _read(self) -> SubmitBudgetSnapshot:
        if not self.path.exists():
            return self._empty()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if int(raw.get("version", 0)) != self.VERSION:
                raise ValueError("version")
            current = SubmitBudgetSnapshot(
                str(raw["scope"]), int(raw["limit"]), int(raw["reserved"]))
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise BudgetConfigurationError(
                f"Grok live budget hỏng/không đọc được: {self.path}") from exc
        if current.reserved < 0 or current.reserved > current.limit:
            raise BudgetConfigurationError(
                f"Grok live budget có counter không hợp lệ: {current.reserved}")
        if current.scope != self.scope or current.limit != self.limit:
            raise BudgetScopeConflict(
                "Không được đổi scope/limit của Grok live budget hiện có: "
                f"đang là {current.scope}/{current.limit}, "
                f"yêu cầu {self.scope}/{self.limit}")
        return current

    def _write(self, snapshot: SubmitBudgetSnapshot) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=self.path.name + ".", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({
                    "version": self.VERSION,
                    "scope": snapshot.scope,
                    "limit": snapshot.limit,
                    "reserved": snapshot.reserved,
                }, handle, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.path)
            dir_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def _locked(self, mutate: bool) -> SubmitBudgetSnapshot:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            try:
                current = self._read()
                if not mutate:
                    return current
                if current.reserved >= current.limit:
                    raise BudgetExhausted(
                        f"Đã dùng hết {current.limit} Grok live submit")
                updated = SubmitBudgetSnapshot(
                    current.scope, current.limit, current.reserved + 1)
                self._write(updated)
                return updated
            finally:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    def snapshot(self) -> SubmitBudgetSnapshot:
        return self._locked(False)

    def reserve(self) -> SubmitBudgetSnapshot:
        return self._locked(True)
