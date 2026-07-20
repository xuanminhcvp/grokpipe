"""Kiểu dữ liệu chung: Task và các hằng."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TaskType(str, Enum):
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    EXTRACT = "EXTRACT"


class Status(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"


# Đuôi file mặc định theo loại kết quả.
EXT_BY_TYPE = {
    TaskType.IMAGE: ".png",
    TaskType.VIDEO: ".mp4",
    TaskType.EXTRACT: ".png",
}


@dataclass
class Task:
    """Một block trong file pipeline."""
    id: str                       # T001
    type: TaskType                # IMAGE / VIDEO / EXTRACT
    output_id: str                # REF_ANDREA_PORTRAIT, VID_001, FRM_S1_WIDE...
    name: str                     # tên gợi nhớ
    prompt: str = ""              # nguyên văn giữa --- PROMPT --- / --- HẾT PROMPT ---

    # các trường KEY : value (đã chuẩn hóa, NONE -> None / [])
    base_image: str | None = None
    ref_images: list[str] = field(default_factory=list)
    start_frame: str | None = None
    duration_s: float = 10.0
    srt_range: str | None = None
    source_video: str | None = None
    frame_need: str | None = None  # FRAME_CẦN_CÓ

    raw_fields: dict[str, str] = field(default_factory=dict)  # giữ nguyên bản gốc

    @property
    def input_ids(self) -> list[str]:
        """Mọi OUTPUT_ID mà task này cần đã tồn tại trước khi chạy."""
        ids: list[str] = []
        if self.base_image:
            ids.append(self.base_image)
        ids.extend(self.ref_images)
        if self.start_frame:
            ids.append(self.start_frame)
        if self.source_video:
            ids.append(self.source_video)
        # loại NONE / trùng, giữ thứ tự
        seen: set[str] = set()
        out: list[str] = []
        for i in ids:
            if i and i.upper() != "NONE" and i not in seen:
                seen.add(i)
                out.append(i)
        return out

    @property
    def ext(self) -> str:
        return EXT_BY_TYPE[self.type]
