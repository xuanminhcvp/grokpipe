"""Lịch BỀN VỮNG — hàng chờ sống sót qua restart board.

Hôm nay hàng đợi nằm trong RAM. Restart board giữa chừng là mất sạch: việc đang
chờ biến mất không dấu vết, việc đang chạy dở không kịp lưu thành bản chính.
`CLAUDE.md` phải dặn "kiểm `/api/jobs` trước khi khởi động lại board" chính vì
thế — một lời dặn là dấu hiệu của một lỗ hổng chưa vá.

Ở đây lịch được ghi xuống SQLite ngay lúc xếp, và đọc lại lúc khởi động:

  · `queued` → xếp lại vào hàng, giữ nguyên thứ tự ưu tiên và `not_before`;
  · `leased` → lượt đó đang chạy khi board chết. **Không tự chạy lại**: với
    video, lượt cũ có thể đã bấm gửi rồi và tự gửi lại là trừ credit lần nữa.
    Nó được trả về cho tầng trên tự quyết theo `RetryPolicy`.

File DB nằm ngoài Git, cạnh dữ liệu runtime của dự án. Không đụng `sf-board.json`.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import sqlite3
import threading
from typing import Optional, Tuple

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS executions (
    execution_id TEXT PRIMARY KEY,
    kind         TEXT NOT NULL,
    queue_ident  TEXT NOT NULL,
    member_keys  TEXT NOT NULL,
    priority     INTEGER NOT NULL DEFAULT 0,
    not_before   REAL NOT NULL DEFAULT 0,
    state        TEXT NOT NULL,
    manual       INTEGER NOT NULL DEFAULT 0,
    forced_account TEXT,
    updated_at   REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_exec_state ON executions(state);
CREATE UNIQUE INDEX IF NOT EXISTS idx_exec_ident ON executions(kind, queue_ident);
CREATE TABLE IF NOT EXISTS intents (
    key         TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    delivered   INTEGER NOT NULL DEFAULT 0,
    created_at  REAL NOT NULL DEFAULT 0
);
"""


@dataclass(frozen=True)
class DurableExecution:
    execution_id: str
    kind: str
    queue_ident: str
    member_keys: Tuple[str, ...]
    priority: int
    not_before: float
    state: str
    manual: bool = False
    forced_account: Optional[str] = None


class SqliteSchedule:
    """Lịch ghi xuống đĩa. Mỗi thao tác là một transaction, không nửa vời."""

    def __init__(self, path: str) -> None:
        self.path = path
        thu_muc = os.path.dirname(os.path.abspath(path))
        if thu_muc:
            os.makedirs(thu_muc, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            # WAL: đọc không chặn ghi. Board vừa xếp việc vừa vẽ giao diện.
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(_SCHEMA)
            cur = self._conn.execute("SELECT version FROM schema_version")
            if cur.fetchone() is None:
                self._conn.execute("INSERT INTO schema_version VALUES (?)",
                                   (SCHEMA_VERSION,))
            self._conn.commit()

    # ────────────────────────────── ghi ───────────────────────────────

    def upsert(self, exe: DurableExecution, now: float = 0.0) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO executions
                   (execution_id, kind, queue_ident, member_keys, priority,
                    not_before, state, manual, forced_account, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(kind, queue_ident) DO UPDATE SET
                     state=excluded.state, priority=excluded.priority,
                     not_before=excluded.not_before, member_keys=excluded.member_keys,
                     manual=excluded.manual, forced_account=excluded.forced_account,
                     updated_at=excluded.updated_at""",
                (exe.execution_id, exe.kind, exe.queue_ident,
                 ",".join(exe.member_keys), int(exe.priority),
                 float(exe.not_before), exe.state, 1 if exe.manual else 0,
                 exe.forced_account, float(now)),
            )
            self._conn.commit()

    def set_state(self, kind: str, queue_ident: str, state: str,
                  now: float = 0.0) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE executions SET state=?, updated_at=? "
                "WHERE kind=? AND queue_ident=?",
                (state, float(now), kind, queue_ident))
            self._conn.commit()

    def remove(self, kind: str, queue_ident: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM executions WHERE kind=? AND queue_ident=?",
                (kind, queue_ident))
            self._conn.commit()

    def remember_intent(self, key: str, fingerprint: str,
                        now: float = 0.0) -> bool:
        """Ghi khoá ý định. Trả False nếu khoá đã dùng cho nội dung KHÁC.

        Đây là phần làm cho chống-trùng sống qua restart: bấm tạo, board chết,
        bật lại, trình duyệt gửi lại đúng key — không được xếp lượt thứ hai."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT fingerprint FROM intents WHERE key=?", (key,))
            dong = cur.fetchone()
            if dong is not None:
                return dong["fingerprint"] == fingerprint
            self._conn.execute(
                "INSERT INTO intents (key, fingerprint, delivered, created_at) "
                "VALUES (?,?,0,?)", (key, fingerprint, float(now)))
            self._conn.commit()
            return True

    def mark_intent_delivered(self, key: str) -> None:
        with self._lock:
            self._conn.execute("UPDATE intents SET delivered=1 WHERE key=?", (key,))
            self._conn.commit()

    def intent_delivered(self, key: str) -> Optional[bool]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT delivered FROM intents WHERE key=?", (key,))
            dong = cur.fetchone()
            return None if dong is None else bool(dong["delivered"])

    # ────────────────────────────── đọc ───────────────────────────────

    def _doc(self, dong) -> DurableExecution:
        return DurableExecution(
            execution_id=dong["execution_id"],
            kind=dong["kind"],
            queue_ident=dong["queue_ident"],
            member_keys=tuple(x for x in dong["member_keys"].split(",") if x),
            priority=int(dong["priority"]),
            not_before=float(dong["not_before"]),
            state=dong["state"],
            manual=bool(dong["manual"]),
            forced_account=dong["forced_account"],
        )

    def pending(self) -> Tuple[DurableExecution, ...]:
        """Việc CÒN CHỜ, theo đúng thứ tự sẽ chạy."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM executions WHERE state='ready' "
                "ORDER BY priority ASC, updated_at ASC")
            return tuple(self._doc(d) for d in cur.fetchall())

    def in_flight(self) -> Tuple[DurableExecution, ...]:
        """Việc ĐANG CHẠY lúc board chết — không được tự chạy lại."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM executions WHERE state='leased' "
                "ORDER BY updated_at ASC")
            return tuple(self._doc(d) for d in cur.fetchall())

    def all_executions(self) -> Tuple[DurableExecution, ...]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM executions")
            return tuple(self._doc(d) for d in cur.fetchall())

    def close(self) -> None:
        with self._lock:
            self._conn.commit()
            self._conn.close()


@dataclass(frozen=True)
class RecoveryPlan:
    """Khởi động lại thì làm gì với những gì còn sót."""
    requeue: Tuple[DurableExecution, ...]        # xếp lại y như cũ
    needs_attention: Tuple[DurableExecution, ...]  # đang chạy dở → hỏi người
    forced: Tuple[Tuple[str, str], ...]          # (ident, cổng bị ép)


def build_recovery_plan(store: SqliteSchedule) -> RecoveryPlan:
    """Đọc lịch cũ và nói rõ phải làm gì — KHÔNG tự làm.

    Việc `leased` không tự xếp lại: với video, lượt cũ có thể đã bấm gửi và
    kết quả đang nằm trên máy chủ Grok; tự chạy lại là trừ credit lần nữa cho
    đúng shot đó."""
    cho = store.pending()
    dang_chay = store.in_flight()
    ep = tuple((e.queue_ident, e.forced_account)
               for e in cho + dang_chay if e.forced_account)
    return RecoveryPlan(requeue=cho, needs_attention=dang_chay, forced=ep)
