"""Tiện ích dùng chung cho các executor."""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys


class DauVetBuoc:
    """Sổ TỪNG BƯỚC của một lượt render, để lỗi nói được nó chết ở đâu.

    Sổ lỗi runtime chỉ ghi KẾT CỤC ("không trả ảnh nào", "hết 600s chờ render").
    Đọc nó không biết lượt ấy chết ở bước nào: chưa về được trang soạn, không
    bấm được mode Video, chip thời lượng không chốt, upload rơi, submit không
    ăn, hay render xong mà tải hỏng. Dấu vết này lấp đúng khoảng đó.

    Nó là thứ PHỤ TRỢ: mọi lời gọi đều nuốt lỗi của chính mình. Bộ ghi dấu vết
    làm chết một lượt render thật thì tệ hơn hẳn việc thiếu vài dòng chẩn đoán.
    """

    def __init__(self, gioi_han: int = 40, dong_ho=None):
        import time as _t
        self._dong_ho = dong_ho or _t.monotonic
        self._gioi_han = max(1, gioi_han)
        self._buoc: list[dict] = []
        # Mốc lấy NGAY lúc dựng, không để None: bước đầu tiên cũng phải đo được
        # thời gian. "Chưa về được trang soạn 600s" và "chờ render 600s" là hai
        # bệnh khác hẳn nhau, mà thiếu con số thì đọc ra như một.
        self._moc = self._gio()

    def bat_dau(self) -> None:
        """Xoá sạch trước mỗi lượt. Tab được dùng lại cho việc kế tiếp, sót dấu
        vết lượt trước là chẩn đoán nhầm lượt này."""
        self._buoc = []
        self._moc = self._gio()

    # HAI HÀM PHẢI CÙNG CHỮ KÝ. Nơi gọi hay chọn hàm rồi mới truyền tham số —
    # `(self.vet.xong if ok else self.vet.hong)("nhan_anh", "về 4/4")`. Lệch chữ
    # ký thì nhánh này chạy, nhánh kia nổ TypeError, mà nhánh nổ lại là nhánh
    # THÀNH CÔNG nên test đường lỗi không thấy gì. Đã trả giá 2026-08-15: mọi lô
    # về đủ ảnh đều chết, 11 tài khoản bị xoay tắt sạch trong 7 phút.
    def xong(self, ten: str, chi_tiet: str = "") -> None:
        self._them(ten, True, chi_tiet)

    def hong(self, ten: str, chi_tiet: str = "") -> None:
        self._them(ten, False, chi_tiet)

    def lay(self) -> list[dict]:
        """Giữ khúc CUỐI khi quá dài — chỗ gần lỗi nhất mới là chỗ đáng đọc."""
        return list(self._buoc[-self._gioi_han:])

    # ---- nội bộ ----------------------------------------------------------
    def _gio(self):
        try:
            return self._dong_ho()
        except Exception:       # noqa: BLE001 - xem docstring lớp
            return None

    def _them(self, ten: str, ok: bool, chi_tiet: str) -> None:
        try:
            gio = self._gio()
            giay = round(gio - self._moc, 1) if (gio is not None and self._moc is not None) else None
            self._moc = gio
            b = {"buoc": str(ten)[:40], "ok": bool(ok)}
            if giay is not None:
                b["giay"] = giay
            if chi_tiet:
                b["chi_tiet"] = str(chi_tiet)[:200]
            self._buoc.append(b)
            if len(self._buoc) > self._gioi_han * 3:
                del self._buoc[:-self._gioi_han]
        except Exception:       # noqa: BLE001
            pass


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
