"""Sổ trạng thái (JSON) + kho asset. Cho phép resume."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict
from typing import Iterator

from .models import Status


@dataclass
class TaskState:
    task_id: str
    output_id: str
    status: str = Status.PENDING.value
    output_path: str | None = None   # đường dẫn tương đối trong project
    attempts: int = 0
    updated_at: str = ""
    note: str = ""


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


class Store:
    """Quản lý thư mục project: assets/, tries/, candidates/, inbox/, state.json, run.log."""

    def __init__(self, project_dir: str):
        self.dir = os.path.abspath(project_dir)
        self.assets = os.path.join(self.dir, "assets")
        self.tries = os.path.join(self.dir, "tries")
        self.candidates = os.path.join(self.dir, "candidates")
        self.inbox = os.path.join(self.dir, "inbox")
        self.state_path = os.path.join(self.dir, "state.json")
        self.log_path = os.path.join(self.dir, "run.log")
        for d in (self.dir, self.assets, self.tries, self.candidates, self.inbox):
            os.makedirs(d, exist_ok=True)
        self._states: dict[str, TaskState] = {}
        self._load()

    # ---------- persistence ----------
    def _load(self) -> None:
        if os.path.exists(self.state_path):
            with open(self.state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for tid, d in data.get("tasks", {}).items():
                self._states[tid] = TaskState(**d)

    def save(self) -> None:
        data = {"updated_at": _now(),
                "tasks": {tid: asdict(s) for tid, s in self._states.items()}}
        tmp = self.state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.state_path)

    # ---------- truy vấn ----------
    def get(self, task_id: str, output_id: str) -> TaskState:
        if task_id not in self._states:
            self._states[task_id] = TaskState(task_id=task_id, output_id=output_id)
        return self._states[task_id]

    def all(self) -> Iterator[TaskState]:
        return iter(self._states.values())

    def set_status(self, task_id: str, output_id: str, status: Status,
                   output_path: str | None = None, note: str = "") -> None:
        st = self.get(task_id, output_id)
        st.status = status.value
        if output_path is not None:
            st.output_path = output_path
        if note:
            st.note = note
        st.updated_at = _now()
        self.save()

    # ---------- asset ----------
    def asset_path(self, output_id: str) -> str:
        """Đường dẫn chuẩn của một output (chưa chắc tồn tại)."""
        # tìm file có sẵn với bất kỳ đuôi nào
        for name in os.listdir(self.assets):
            stem, _ = os.path.splitext(name)
            if stem == output_id:
                return os.path.join(self.assets, name)
        return os.path.join(self.assets, output_id)  # chưa có đuôi

    def asset_exists(self, output_id: str) -> bool:
        for name in os.listdir(self.assets):
            if os.path.splitext(name)[0] == output_id:
                p = os.path.join(self.assets, name)
                if os.path.getsize(p) > 0:
                    return True
        return False

    def resolve_input(self, output_id: str) -> str | None:
        """Đường dẫn file thực của một input, hoặc None nếu chưa có."""
        for name in os.listdir(self.assets):
            if os.path.splitext(name)[0] == output_id:
                p = os.path.join(self.assets, name)
                if os.path.getsize(p) > 0:
                    return p
        return None

    def next_try_path(self, output_id: str, ext: str) -> tuple[str, int]:
        """tries/<id>_tryN.<ext> — N tăng dần, không ghi đè."""
        n = 1
        while True:
            p = os.path.join(self.tries, f"{output_id}_try{n}{ext}")
            if not os.path.exists(p):
                return p, n
            n += 1

    def promote(self, try_path: str, output_id: str, ext: str) -> str:
        """Sao chép bản được duyệt thành assets/<id>.<ext>. Trả đường dẫn tương đối."""
        import shutil
        dst = os.path.join(self.assets, f"{output_id}{ext}")
        # dọn asset cũ khác đuôi
        for name in list(os.listdir(self.assets)):
            if os.path.splitext(name)[0] == output_id:
                os.remove(os.path.join(self.assets, name))
        shutil.copy2(try_path, dst)
        return os.path.relpath(dst, self.dir)
