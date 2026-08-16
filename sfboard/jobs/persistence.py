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

SCHEMA_VERSION = 2


class ScheduleError(RuntimeError):
    """Lỗi của durable schedule boundary."""


class ScheduleConflict(ScheduleError):
    """Một scope đang có execution active khác."""


class ScheduleVersionConflict(ScheduleError):
    """Mutation dùng snapshot/version đã cũ."""

_SCHEMA = """
CREATE TABLE IF NOT EXISTS executions (
    execution_id TEXT PRIMARY KEY,
    kind         TEXT NOT NULL,
    queue_ident  TEXT NOT NULL,
    scope_key    TEXT NOT NULL,
    member_keys  TEXT NOT NULL,
    priority     INTEGER NOT NULL DEFAULT 0,
    not_before   REAL NOT NULL DEFAULT 0,
    state        TEXT NOT NULL,
    manual       INTEGER NOT NULL DEFAULT 0,
    forced_account TEXT,
    version      INTEGER NOT NULL DEFAULT 0,
    seq          INTEGER NOT NULL DEFAULT 0,
    lease_id     TEXT,
    lease_expires_at REAL,
    updated_at   REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_exec_state ON executions(state);
CREATE INDEX IF NOT EXISTS idx_exec_ident ON executions(kind, queue_ident);
CREATE UNIQUE INDEX IF NOT EXISTS idx_exec_active_scope
    ON executions(kind, scope_key)
    WHERE state IN ('ready', 'waiting', 'leased');
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
    scope_key: str = ""
    version: int = 0
    seq: int = 0
    lease_id: Optional[str] = None
    lease_expires_at: Optional[float] = None


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
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_version "
                "(version INTEGER NOT NULL)"
            )
            row = self._conn.execute(
                "SELECT version FROM schema_version LIMIT 1"
            ).fetchone()
            if row is None:
                self._conn.executescript(_SCHEMA)
                self._conn.execute(
                    "INSERT INTO schema_version VALUES (?)", (SCHEMA_VERSION,)
                )
            elif int(row["version"]) == 1:
                self._migrate_v1_to_v2()
            elif int(row["version"]) == SCHEMA_VERSION:
                self._conn.executescript(_SCHEMA)
            else:
                raise ScheduleError(
                    f"schema schedule không hỗ trợ: {row['version']}"
                )
            self._conn.commit()

    def _migrate_v1_to_v2(self) -> None:
        """Giữ nguyên execution cũ nhưng bỏ identity theo compatibility label."""
        columns = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(executions)")
        }
        additions = {
            "scope_key": "TEXT NOT NULL DEFAULT ''",
            "version": "INTEGER NOT NULL DEFAULT 0",
            "seq": "INTEGER NOT NULL DEFAULT 0",
            "lease_id": "TEXT",
            "lease_expires_at": "REAL",
        }
        for name, sql_type in additions.items():
            if name not in columns:
                self._conn.execute(
                    f"ALTER TABLE executions ADD COLUMN {name} {sql_type}"
                )
        self._conn.execute(
            "UPDATE executions SET scope_key=queue_ident WHERE scope_key=''"
        )
        self._conn.execute("DROP INDEX IF EXISTS idx_exec_ident")
        self._conn.executescript(_SCHEMA)
        self._conn.execute(
            "UPDATE schema_version SET version=?", (SCHEMA_VERSION,)
        )

    # ────────────────────────────── ghi ───────────────────────────────

    def _values(self, exe: DurableExecution, now: float) -> tuple:
        scope_key = exe.scope_key or exe.queue_ident
        seq = int(exe.seq)
        if seq <= 0:
            row = self._conn.execute(
                "SELECT seq FROM executions WHERE execution_id=?",
                (exe.execution_id,),
            ).fetchone()
            if row is not None:
                seq = int(row["seq"])
            else:
                maximum = self._conn.execute(
                    "SELECT COALESCE(MAX(seq), 0) AS value FROM executions"
                ).fetchone()
                seq = int(maximum["value"]) + 1
        return (
            exe.execution_id, exe.kind, exe.queue_ident, scope_key,
            ",".join(exe.member_keys), int(exe.priority),
            float(exe.not_before), exe.state, 1 if exe.manual else 0,
            exe.forced_account, int(exe.version), seq, exe.lease_id,
            exe.lease_expires_at, float(now),
        )

    def insert(self, exe: DurableExecution, now: float = 0.0) -> None:
        with self._lock:
            try:
                self._conn.execute(
                    """INSERT INTO executions
                       (execution_id, kind, queue_ident, scope_key, member_keys,
                        priority, not_before, state, manual, forced_account,
                        version, seq, lease_id, lease_expires_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    self._values(exe, now),
                )
                self._conn.commit()
            except sqlite3.IntegrityError as exc:
                self._conn.rollback()
                raise ScheduleConflict(str(exc)) from exc

    def upsert(self, exe: DurableExecution, now: float = 0.0) -> None:
        with self._lock:
            try:
                self._conn.execute(
                    """INSERT INTO executions
                       (execution_id, kind, queue_ident, scope_key, member_keys,
                        priority, not_before, state, manual, forced_account,
                        version, seq, lease_id, lease_expires_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(execution_id) DO UPDATE SET
                         kind=excluded.kind, queue_ident=excluded.queue_ident,
                         scope_key=excluded.scope_key,
                         member_keys=excluded.member_keys,
                         priority=excluded.priority,
                         not_before=excluded.not_before, state=excluded.state,
                         manual=excluded.manual,
                         forced_account=excluded.forced_account,
                         version=excluded.version, lease_id=excluded.lease_id,
                         lease_expires_at=excluded.lease_expires_at,
                         updated_at=excluded.updated_at""",
                    self._values(exe, now),
                )
                self._conn.commit()
            except sqlite3.IntegrityError as exc:
                self._conn.rollback()
                raise ScheduleConflict(str(exc)) from exc

    def get(self, execution_id: str) -> Optional[DurableExecution]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM executions WHERE execution_id=?",
                (execution_id,),
            ).fetchone()
            return self._doc(row) if row is not None else None

    def compare_and_set(
        self,
        execution_id: str,
        expected_version: int,
        *,
        state: str,
        not_before: Optional[float] = None,
        lease_id: Optional[str] = None,
        lease_expires_at: Optional[float] = None,
        now: float = 0.0,
    ) -> DurableExecution:
        with self._lock:
            updates = [
                "state=?", "version=version+1", "updated_at=?",
                "lease_id=?", "lease_expires_at=?",
            ]
            values = [state, float(now), lease_id, lease_expires_at]
            if not_before is not None:
                updates.append("not_before=?")
                values.append(float(not_before))
            values.extend((execution_id, int(expected_version)))
            try:
                cursor = self._conn.execute(
                    f"UPDATE executions SET {', '.join(updates)} "
                    "WHERE execution_id=? AND version=?",
                    tuple(values),
                )
                if cursor.rowcount != 1:
                    self._conn.rollback()
                    raise ScheduleVersionConflict(
                        f"execution={execution_id}, expected={expected_version}"
                    )
                self._conn.commit()
            except sqlite3.IntegrityError as exc:
                self._conn.rollback()
                raise ScheduleConflict(str(exc)) from exc
            updated = self.get(execution_id)
            if updated is None:  # pragma: no cover - guarded by rowcount
                raise ScheduleVersionConflict(execution_id)
            return updated

    def set_state(self, kind: str, queue_ident: str, state: str,
                  now: float = 0.0) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE executions SET state=?, version=version+1, updated_at=? "
                "WHERE execution_id=(SELECT execution_id FROM executions "
                "WHERE kind=? AND queue_ident=? "
                "ORDER BY seq DESC LIMIT 1)",
                (state, float(now), kind, queue_ident))
            self._conn.commit()

    def remove(self, kind: str, queue_ident: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM executions WHERE kind=? AND queue_ident=? "
                "AND state IN ('ready', 'waiting', 'leased')",
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
            scope_key=dong["scope_key"],
            version=int(dong["version"]),
            seq=int(dong["seq"]),
            lease_id=dong["lease_id"],
            lease_expires_at=(
                float(dong["lease_expires_at"])
                if dong["lease_expires_at"] is not None else None
            ),
        )

    def pending(self) -> Tuple[DurableExecution, ...]:
        """Việc CÒN CHỜ, theo đúng thứ tự sẽ chạy."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM executions WHERE state='ready' "
                "ORDER BY priority ASC, seq ASC")
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
            cur = self._conn.execute("SELECT * FROM executions ORDER BY seq ASC")
            return tuple(self._doc(d) for d in cur.fetchall())

    def load_active(self) -> Tuple[DurableExecution, ...]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM executions "
                "WHERE state IN ('ready', 'waiting', 'leased') "
                "ORDER BY priority ASC, seq ASC"
            )
            return tuple(self._doc(row) for row in cur.fetchall())

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
