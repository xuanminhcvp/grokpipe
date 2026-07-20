"""Tiện ích dùng chung cho các executor."""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys


class ExecutorError(Exception):
    """Lỗi chạy executor -> task FAILED."""


class UserQuit(Exception):
    """Người dùng chọn thoát toàn bộ."""


class UserSkip(Exception):
    """Người dùng bỏ qua task này (đánh dấu FAILED, không dừng cả pipeline)."""


def ffprobe_duration(path: str) -> float | None:
    """Thời lượng (giây) của video, None nếu không đọc được."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        return float(out)
    except (subprocess.CalledProcessError, ValueError):
        return None


def ffmpeg_extract_frame(video: str, t: float, out_png: str) -> bool:
    """Cắt 1 frame chính xác tại giây t. -ss SAU -i để chính xác."""
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", video, "-ss", f"{t:.3f}",
             "-frames:v", "1", "-q:v", "2", out_png],
            capture_output=True, check=True,
        )
        return os.path.exists(out_png) and os.path.getsize(out_png) > 0
    except subprocess.CalledProcessError:
        return False


def open_file(path: str) -> None:
    """Mở file bằng app mặc định của HĐH (best-effort).

    Đặt GROKPIPE_NO_OPEN=1 để tắt (hữu ích khi test/headless)."""
    if os.environ.get("GROKPIPE_NO_OPEN"):
        return
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        elif sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", path], check=False)
    except Exception:
        pass


def ask(prompt: str, choices: str = "") -> str:
    """Đọc 1 dòng từ người dùng. Trả chuỗi (đã strip)."""
    suffix = f" [{choices}]" if choices else ""
    try:
        return input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        raise UserQuit()


def human_gate(path: str, label: str) -> str:
    """Hiện file, hỏi duyệt. Trả 'ok' | 'retry' | (raise UserSkip/UserQuit)."""
    open_file(path)
    print(f"\n  >>> Kiểm tra {label}: {path}")
    while True:
        a = ask("    Duyệt? (Enter/o=OK, r=Retry, s=Skip, q=Quit)").lower()
        if a in ("", "o", "ok"):
            return "ok"
        if a in ("r", "retry"):
            return "retry"
        if a in ("s", "skip"):
            raise UserSkip()
        if a in ("q", "quit"):
            raise UserQuit()
        print("    (không hiểu — nhập Enter/o/r/s/q)")


def find_dropped(inbox: str, output_id: str, exts: tuple[str, ...]) -> str | None:
    """Tìm file người dùng thả vào inbox cho output_id này.

    Ưu tiên tên khớp <output_id>.<ext>; nếu không, lấy file mới nhất đúng đuôi.
    """
    # 1) tên khớp chính xác
    for ext in exts:
        p = os.path.join(inbox, f"{output_id}{ext}")
        if os.path.exists(p) and os.path.getsize(p) > 0:
            return p
    # 2) file mới nhất đúng đuôi trong inbox
    cands: list[str] = []
    for ext in exts:
        cands += glob.glob(os.path.join(inbox, f"*{ext}"))
    cands = [c for c in cands if os.path.getsize(c) > 0]
    if not cands:
        return None
    return max(cands, key=os.path.getmtime)


def copy_to(src: str, dst: str) -> str:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    return dst
