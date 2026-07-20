"""Executor EXTRACT — cắt frame nối video bằng ffmpeg.

Thiết kế (theo ý tác giả pipeline): mọi GÓC MÁY MỚI được khai sinh ở đoạn 5–10s
của video (sau quick-cut ở giây 5). Vì vậy cắt cố định ở **giây 7.5** để lưu đúng
góc mới đó làm start-frame cho video sau. Chạy thuần tự động, không chọn/duyệt tay.

Frame lưu tên đúng bằng OUTPUT_ID: assets/<OUTPUT_ID>.png
"""
from __future__ import annotations

import os

from ..models import Task
from ..state import Store
from . import common as C

# Giây cắt mặc định (70–95% thời lượng; 7.5s cho video 10s).
EXTRACT_AT = 7.5


def run_extract(task: Task, store: Store, source_video_path: str, logger) -> str:
    """Cắt 1 frame ở giây 7.5 của video nguồn. Trả path try trong tries/."""
    dur = C.ffprobe_duration(source_video_path)

    # điểm cắt: 7.5s; nếu video ngắn hơn thì lấy 75% thời lượng.
    t = EXTRACT_AT
    if dur is not None and t >= dur:
        t = max(0.0, dur * 0.75)

    try_path, _ = store.next_try_path(task.output_id, ".png")
    if not C.ffmpeg_extract_frame(source_video_path, t, try_path):
        # thử lại vài mốc gần đó phòng khi frame lỗi
        for alt in (7.0, 8.0, 6.5, 5.5):
            if dur is not None and alt >= dur:
                continue
            if C.ffmpeg_extract_frame(source_video_path, alt, try_path):
                t = alt
                break
        else:
            raise C.ExecutorError("ffmpeg không cắt được frame nào.")

    logger.info(f"{task.id} cắt frame {task.output_id} ở giây {t:.1f} "
                f"(nguồn {os.path.basename(source_video_path)})")
    return try_path
