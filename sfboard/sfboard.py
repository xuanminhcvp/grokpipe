#!/usr/bin/env python3
"""
SF BOARD v2 — bảng duyệt & tạo Start Frame cho từng kịch bản phim.

Chạy:
    python3 sfboard.py "/duong/dan/THU-MUC-PHIM" [--cdp http://localhost:9222] [--port 8777]

Dữ liệu (nằm trong thư mục phim, đi theo từng kịch bản):
    sf-board.json     ← toàn bộ SF + trạng thái duyệt + prompt + refs
    assets/           ← ảnh đang dùng của mỗi SF  (<SF-ID>.png)
    versions/         ← mọi lần tạo lại  (<SF-ID>_vN.png) để so sánh, chọn lại

Tính năng:
    · Tạo ảnh thẳng từ bảng (ChatGPT qua Chrome CDP) — không cần copy prompt tay
    · Sửa prompt / tên / mô tả ngay trên thẻ rồi Tạo lại
    · Chọn ảnh tham chiếu (nhân vật + bối cảnh) bằng dropdown, tự đính đúng file
    · Lịch sử phiên bản: mọi lần roll đều giữ, bấm để đổi bản đang dùng
    · Duyệt / Cần sửa / Loại · Copy SF sang scene khác · Nhân bản · Kéo-thả ảnh tay

Chỉ dùng thư viện chuẩn (Playwright chỉ cần khi bấm Tạo ảnh).
"""
from __future__ import annotations

import atexit
import collections
import datetime
import subprocess
import itertools
import json
import logging
import os
import re
import shutil
import sys
import queue
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

PORT = 8777
CDP = "http://localhost:9222"
# Thư mục trung chuyển: MỌI ảnh ChatGPT sinh ra đều rơi xuống đây trước khi được
# ghép vào SF. Xem khối "CHỜ PHÂN LOẠI" ở dưới để biết vì sao.
PL_TEN = "cho-phan-loai"
IMAGE_EXT = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
             ".webp": "image/webp", ".gif": "image/gif"}

# cho phép import executor ChatGPT của grokpipe
_HERE = os.path.dirname(os.path.abspath(__file__))
for cand in (os.path.join(_HERE, "..", "grokpipe"), os.path.join(_HERE, "grokpipe")):
    if os.path.isdir(os.path.join(cand, "grokpipe")):
        sys.path.insert(0, os.path.abspath(cand))
        break


# ---------------------------------------------------------------- state
class Board:
    def __init__(self, film_dir: str):
        self.dir = os.path.abspath(film_dir)
        self.assets = os.path.join(self.dir, "assets")
        self.versions = os.path.join(self.dir, "versions")
        self.videos = os.path.join(self.dir, "videos")
        self.vversions = os.path.join(self.dir, "videos", "versions")
        self.path = os.path.join(self.dir, "sf-board.json")
        self.pl = os.path.join(self.dir, PL_TEN)          # ảnh chờ phân loại
        self.nk_path = os.path.join(self.pl, "nhat-ky.json")
        self._nk = {"mtime": -1.0, "data": {}}
        self._nk_lock = threading.Lock()   # sổ lượt: bốn thợ ghi cùng lúc
        os.makedirs(self.assets, exist_ok=True)
        os.makedirs(self.versions, exist_ok=True)
        os.makedirs(self.videos, exist_ok=True)
        os.makedirs(self.vversions, exist_ok=True)
        os.makedirs(self.pl, exist_ok=True)
        if not os.path.exists(self.path):
            self._write({"film": os.path.basename(self.dir), "updated_at": "", "scenes": []})

    # ---- SỔ LƯỢT: bản nào trong versions/ ra từ LƯỢT ChatGPT nào -----------
    # Ghi ra file riêng, KHÔNG nhét vào sf-board.json: sf-board.json là kịch bản
    # phim (được backup sang repo riêng), còn đây là nhật ký kỹ thuật của máy —
    # trộn vào nhau thì mỗi lần render lại là một dòng diff rác trong kịch bản.
    def turn_log(self) -> dict:
        try:
            m = os.path.getmtime(self.nk_path)
        except OSError:
            return {}
        if m != self._nk["mtime"]:
            try:
                with open(self.nk_path, "r", encoding="utf-8") as f:
                    self._nk = {"mtime": m, "data": json.load(f)}
            except Exception:
                self._nk = {"mtime": m, "data": {}}
        return self._nk["data"]

    def turn_log_ghi(self, ten_file: str, info: dict) -> None:
        # MỘT KHOÁ CHO CẢ ĐỌC-SỬA-GHI, và tên file tạm RIÊNG theo luồng.
        #
        # Bản cũ hỏng hai tầng khi bốn thợ cùng ghi (log ALTAR 2026-08-15):
        #   · tên tạm cố định `nhat-ky.json.tmp` dùng chung → thợ nào `os.replace`
        #     trước thì mang file tạm đi, thợ sau replace vào chỗ trống và văng
        #     "[Errno 2] No such file or directory";
        #   · nặng hơn và KHÔNG hiện trong log: cả hai đọc `turn_log()` từ trước
        #     rồi ghi đè NGUYÊN file, nên dòng của thợ này xoá dòng của thợ kia.
        #     Đo bằng test: 60 dòng ghi vào, 14 sống sót.
        #
        # Sổ lượt là thứ duy nhất trả lời "bản trong versions/ ra từ lượt ChatGPT
        # nào" — mất là mất hẳn, không dựng lại được từ đâu.
        with self._nk_lock:
            d = dict(self.turn_log())
            d[ten_file] = info
            # Cắt bớt dòng của file đã biến mất, để sổ không phình mãi.
            if len(d) > 4000:
                con = set(os.listdir(self.versions))
                d = {k: v for k, v in d.items() if k in con}
            tmp = f"{self.nk_path}.{os.getpid()}.{threading.get_ident()}.tmp"
            try:
                os.makedirs(self.pl, exist_ok=True)
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(d, f, ensure_ascii=False, indent=1, sort_keys=True)
                os.replace(tmp, self.nk_path)
                self._nk = {"mtime": os.path.getmtime(self.nk_path), "data": d}
            except OSError as e:
                _LOG.warning("không ghi được sổ lượt: %s", e)
                # Ghi hỏng thì dọn file tạm của CHÍNH MÌNH, đừng để rơi vãi
                # trong thư mục ảnh chờ phân loại.
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    def read(self) -> dict:
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["mtime"] = int(os.path.getmtime(self.path))
        nk = self.turn_log()
        # Bốn lượt quét đĩa cho CẢ board, thay cho gần 1900 lượt của bản cũ.
        d_as, d_ve = self._quet(self.assets), self._quet(self.versions)
        d_vi, d_vv = self._quet(self.videos), self._quet(self.vversions)
        ds_ve = sorted(n for ns in d_ve.values() for n in ns)
        ds_vv = sorted(n for ns in d_vv.values() for n in ns)
        for sc in data.get("scenes", []):
            sc.setdefault("shots", [])
            for sf in sc.get("sfs", []):
                sf["image"] = self._img_url(self.assets, sf["id"], d_as)
                sf["versions"] = self._versions(sf["id"], nk, ds_ve)
                # LƯỢT nào đẻ ra ảnh ĐANG DÙNG — để lúc tải lỗi còn lần ngược
                # được về đúng lượt trong log và trong thư mục Chờ phân loại.
                _cur = sf.get("picked") or (sf["versions"][-1]["file"]
                                            if sf["versions"] else "")
                _t = nk.get(_cur) or {}
                if _t.get("turn"):
                    sf["turn"] = _t["turn"]
                    sf["turn_o"] = _t.get("o") or 0
                    sf["turn_port"] = _t.get("port") or 0
            for sh in sc["shots"]:
                sh["video"] = self._vid_url(sh["id"], d_vi)
                sh["vversions"] = self._vversions(sh["id"], ds_vv)
        return data

    # ---- video
    def _vid_url(self, sid: str, ds: dict | None = None) -> str | None:
        ten = ds.get(sid, []) if ds is not None else \
            [n for n in sorted(os.listdir(self.videos)) if os.path.splitext(n)[0] == sid]
        for name in ten:
            s, ext = os.path.splitext(name)
            if ext.lower() == ".mp4":
                p = os.path.join(self.videos, name)
                return f"/videos/{name}?t={int(os.path.getmtime(p))}"
        return None

    def video_file(self, sid: str) -> str | None:
        p = os.path.join(self.videos, sid + ".mp4")
        return p if os.path.isfile(p) else None

    def _vversions(self, sid: str, ds: list | None = None) -> list[dict]:
        out = []
        for name in (ds if ds is not None else sorted(os.listdir(self.vversions))):
            s, ext = os.path.splitext(name)
            if ext.lower() == ".mp4" and re.match(rf"^{re.escape(sid)}_v\d+$", s):
                p = os.path.join(self.vversions, name)
                out.append({"file": name, "url": f"/vversions/{name}",
                            "at": time.strftime("%d/%m %H:%M", time.localtime(os.path.getmtime(p)))})
        out.sort(key=lambda x: int(x["file"].rsplit("_v", 1)[1].split(".")[0]))
        return out

    def next_vversion(self, sid: str) -> str:
        n = len(self._vversions(sid)) + 1
        while os.path.exists(os.path.join(self.vversions, f"{sid}_v{n}.mp4")):
            n += 1
        return os.path.join(self.vversions, f"{sid}_v{n}.mp4")

    def set_video(self, sid: str, src: str) -> None:
        dst = os.path.join(self.videos, sid + ".mp4")
        shutil.copy2(src, dst)
        os.utime(dst, None)      # xem lý do ở set_current — video cũng dính y hệt

    def delete_video(self, sid: str) -> None:
        for folder in (self.videos, self.vversions):
            for name in list(os.listdir(folder)):
                if not os.path.isfile(os.path.join(folder, name)):
                    continue
                s = os.path.splitext(name)[0]
                if s == sid or s.startswith(sid + "_v"):
                    os.remove(os.path.join(folder, name))

    def get_shot(self, sid: str):
        data = self.read()
        for sc in data["scenes"]:
            for sh in sc.get("shots", []):
                if sh["id"] == sid:
                    return sh, sc
        return None, None

    def write(self, data: dict) -> None:
        data["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self._write(data)

    def _write(self, data: dict) -> None:
        # TỰ LẤY KHOÁ Ở ĐÂY, không trông vào bên gọi. Có 10 chỗ gọi write và 3
        # chỗ quên bọc `with BOARD_LOCK` — mà chỉ cần một chỗ quên là hỏng cả
        # file kịch bản. Khoá là RLock nên chỗ nào đã cầm rồi vẫn vào được.
        with BOARD_LOCK:
            self._write_ruot(data)

    def _write_ruot(self, data: dict) -> None:
        clean = json.loads(json.dumps(data))
        clean.pop("mtime", None)
        for sc in clean.get("scenes", []):
            for sf in sc.get("sfs", []):
                sf.pop("image", None)
                sf.pop("versions", None)
                # Nhãn lượt là dữ liệu KỸ THUẬT do read() gắn vào, sổ riêng đã
                # giữ — để lọt vào sf-board.json là mỗi lần render lại đẻ một
                # dòng diff rác trong kịch bản phim.
                for _k in ("turn", "turn_o", "turn_port"):
                    sf.pop(_k, None)
            for sh in sc.get("shots", []):
                sh.pop("video", None)
                sh.pop("vversions", None)
        # FILE TẠM RIÊNG CHO TỪNG LUỒNG. Bản cũ dùng chung đúng một tên
        # `<path>.tmp`, nên hai thợ ghi cùng lúc là: A mở tmp ghi được nửa, B mở
        # CHÍNH file đó (truncate) ghi từ đầu, A ghi nốt phần đuôi của mình vào
        # sau → tmp thành "JSON của B + đuôi thừa của A". `os.replace` xong thì
        # sf-board.json mang đúng hình đó, và mọi lần đọc sau đều chết với
        # "Extra data: line … column …". Càng nhiều thợ càng dễ dính.
        tmp = f"{self.path}.{os.getpid()}.{threading.get_ident()}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(clean, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())     # chốt xuống đĩa trước khi tráo tên
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    # ---- ảnh
    # QUÉT MỘT LẦN, TRA NHIỀU LẦN.
    #
    # Bản cũ để `read()` gọi listdir CHO TỪNG THẺ: 509 SF × 2 thư mục + 437 shot
    # × 2 = gần 1900 lượt quét đĩa cho MỘT lần đọc board (đo 2026-08-12: 299 ms).
    # Mà `get_sf()` lại gọi `read()`, nên tích 10 ảnh rồi bấm Tạo là 3,2 GIÂY
    # đứng hình trước khi việc kịp vào hàng đợi.
    # Giờ quét mỗi thư mục ĐÚNG MỘT LẦN rồi tra map {tên gốc: [file]}.
    def _quet(self, folder: str) -> dict:
        ra: dict[str, list[str]] = {}
        try:
            for name in sorted(os.listdir(folder)):
                ra.setdefault(os.path.splitext(name)[0], []).append(name)
        except OSError:
            pass
        return ra

    def _img_url(self, folder: str, stem: str, ds: dict | None = None) -> str | None:
        ten = ds.get(stem, []) if ds is not None else \
            [n for n in sorted(os.listdir(folder)) if os.path.splitext(n)[0] == stem]
        for name in ten:
            if os.path.splitext(name)[1].lower() in IMAGE_EXT:
                p = os.path.join(folder, name)
                base = "assets" if folder == self.assets else "versions"
                return f"/{base}/{name}?t={int(os.path.getmtime(p))}"
        return None

    def find_file(self, stem: str) -> str | None:
        for name in sorted(os.listdir(self.assets)):
            s, ext = os.path.splitext(name)
            if s == stem and ext.lower() in IMAGE_EXT:
                return os.path.join(self.assets, name)
        return None

    def _versions(self, sf_id: str, nk: dict | None = None,
                  ds: list | None = None) -> list[dict]:
        nk = self.turn_log() if nk is None else nk
        out = []
        for name in (ds if ds is not None else sorted(os.listdir(self.versions))):
            s, ext = os.path.splitext(name)
            if ext.lower() in IMAGE_EXT and re.match(rf"^{re.escape(sf_id)}_v\d+$", s):
                p = os.path.join(self.versions, name)
                if os.path.getsize(p) < 1024:
                    continue      # file rỗng đang được một luồng khác giữ chỗ
                t = nk.get(name) or {}
                out.append({"file": name, "url": f"/versions/{name}?t={int(os.path.getmtime(p))}",
                            "turn": t.get("turn") or 0, "turn_o": t.get("o") or 0,
                            "at": time.strftime("%d/%m %H:%M", time.localtime(os.path.getmtime(p)))})
        out.sort(key=lambda x: int(x["file"].rsplit("_v", 1)[1].split(".")[0]))
        return out

    def next_version_path(self, sf_id: str, reserve: bool = False) -> str:
        """Đường dẫn bản kế tiếp.

        reserve=True tạo ngay một file rỗng để GIỮ CHỖ — bắt buộc khi nhiều luồng
        cùng tạo một SF (tạo nhiều bản song song), nếu không hai luồng sẽ nhận
        cùng một tên file và ghi đè nhau."""
        n = 1
        while os.path.exists(os.path.join(self.versions, f"{sf_id}_v{n}.png")):
            n += 1
        p = os.path.join(self.versions, f"{sf_id}_v{n}.png")
        if reserve:
            open(p, "wb").close()
        return p

    def set_current(self, sf_id: str, src: str) -> None:
        for name in list(os.listdir(self.assets)):
            if os.path.splitext(name)[0] == sf_id:
                os.remove(os.path.join(self.assets, name))
        ext = os.path.splitext(src)[1].lower() or ".png"
        dst = os.path.join(self.assets, sf_id + ext)
        shutil.copy2(src, dst)
        # ĐÓNG DẤU GIỜ MỚI CHO ẢNH CHÍNH.
        #
        # `copy2` bê nguyên mtime của bản nguồn sang. Chọn một bản CŨ thì mtime
        # của ảnh chính LÙI VỀ QUÁ KHỨ, và hai thứ hỏng theo:
        #   · `_thumb()` thấy bản thu nhỏ đã cache MỚI HƠN nguồn nên trả lại
        #     đúng bản cũ — thẻ vẫn hiện ảnh trước đó dù đã đổi;
        #   · `?t=<mtime>` cũng lùi theo nên trình duyệt có thể dùng lại cache.
        # Đã đo 2026-08-07: SF-S3-01 ảnh chính mtime 09:27 trong khi thumb cache
        # 20:29–21:41 — bấm chọn bản khác xong, ngoài board không đổi gì.
        os.utime(dst, None)

    def save_upload(self, sf_id: str, raw: bytes, filename: str) -> None:
        ext = os.path.splitext(filename)[1].lower()
        if ext not in IMAGE_EXT:
            ext = ".png"
        vp = self.next_version_path(sf_id).replace(".png", ext)
        with open(vp, "wb") as f:
            f.write(raw)
        self.set_current(sf_id, vp)

    def delete_sf_files(self, sf_id: str) -> None:
        for folder in (self.assets, self.versions):
            for name in list(os.listdir(folder)):
                s = os.path.splitext(name)[0]
                if s == sf_id or s.startswith(sf_id + "_v"):
                    os.remove(os.path.join(folder, name))

    def get_sf(self, sf_id: str, data: dict | None = None):
        """Một thẻ SF. TRUYỀN `data` VÀO khi đang lặp nhiều thẻ.

        Không truyền thì hàm phải đọc lại cả board — vòng lặp 10 thẻ là 10 lần
        đọc, đúng thứ làm nút "Tạo ảnh đã chọn" đứng hình mấy giây.
        """
        data = self.read() if data is None else data
        for sc in data["scenes"]:
            for sf in sc["sfs"]:
                if sf["id"] == sf_id:
                    return sf
        return None


BOARD: Board | None = None
CDP_ENDPOINTS: list[str] = [CDP]         # cờ --cdp (chỉ dùng để KHỞI TẠO file accounts lần đầu)
GROK_ENDPOINTS: list[str] = []           # cờ --cdp-grok (như trên)

# ----------------------------------------------------------------- accounts
# Quản lý tài khoản tập trung: mỗi tài khoản = 1 profile Chrome + 1 port debug.
# Lưu ở ~/.grokpipe-accounts.json — bật/tắt/mở Chrome ngay từ giao diện board,
# không phải sửa lệnh khởi động hay tự tay mở Chrome với đúng cờ nữa.
ACCOUNTS: list[dict] = []      # {id, kind: img|vid, port, profile, enabled, tabs}
MAX_TABS = 6                   # trần tab đồng thời trên MỘT tài khoản
# Trần thử lại cho VIỆC VIDEO. Ảnh vẫn thử lại vô hạn (user chốt 2026-08-14);
# video thì không, vì mỗi lượt Grok là credit thật — xem lý do đầy đủ ở nhánh
# `except` của `_worker`.
VID_MAX_TRY = 5
ACC_PATH = os.path.expanduser("~/.grokpipe-accounts.json")
PROJECTS_ROOT = ""       # thư mục chứa các *.project (bộ chọn dự án)
SERVE_PORT = 0           # cổng board này đang phục vụ
ACC_LOCK = threading.RLock()
WORKERS: dict[tuple, threading.Thread] = {}   # (port, kind) -> luồng thợ

_CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
# Bó .app — `open -g` nhận app bundle chứ không nhận binary bên trong.
_CHROME_APP = "/Applications/Google Chrome.app"
_KIND_URL = {"img": "https://chatgpt.com/", "vid": "https://grok.com/"}
_KIND_NAME = {"img": "ChatGPT (ảnh)", "vid": "Grok (video)"}


def _ep(a: dict) -> str:
    return f"http://localhost:{a['port']}"


# TRẦN REF MỖI LÔ — chỉnh được trên board vì NGƯỠNG THẬT CHƯA AI ĐO.
# Log ALTAR 2026-08-15: lô 5 ref chạy sạch, lô 9 hỏng 2/2, lô 14-17 hỏng mọi
# lượt. Vách nằm đâu đó giữa 5 và 9, nhưng chỉ có 4 mốc quan sát nên đừng đóng
# cứng — user tự dò 8 hay 12 hợp hơn mà không cần sửa mã.
TRAN_REF = 10
TRAN_REF_MAX = 30


def _dat_tran_ref(n) -> int:
    """Đặt trần ref và lưu lại. Tách khỏi handler vì `do_POST` đã ĐỌC `TRAN_REF`
    ở nhánh tạo lô phía trên — khai `global` sau lần đọc đầu là SyntaxError."""
    global TRAN_REF
    try:
        TRAN_REF = max(1, min(TRAN_REF_MAX, int(str(n).strip() or TRAN_REF)))
    except ValueError:
        pass
    _save_accounts()
    _LOG.info("Trần ref mỗi lô: %d.", TRAN_REF)
    return TRAN_REF


def _save_accounts():
    with ACC_LOCK:
        with open(ACC_PATH, "w", encoding="utf-8") as f:
            json.dump({"accounts": ACCOUNTS, "tran_ref": TRAN_REF},
                      f, ensure_ascii=False, indent=2)
    _sync_runtime_accounts()


# ---- Bộ đếm bản/ngày cho từng tài khoản ---------------------------------
# ChatGPT và Grok KHÔNG công bố trần mỗi ngày là bao nhiêu, và trần còn đổi theo
# gói với theo thời điểm. Nên cách duy nhất biết được là ĐẾM THẬT: ngày nào chạy
# tới lúc bị chặn thì con số của đúng ngày đó chính là trần. Vì vậy cột đáng đọc
# là KỶ LỤC, không phải số hôm nay.
#
# Lưu ở HOME chứ không lưu trong project: một tài khoản chạy cho nhiều phim, trần
# tính theo tài khoản chứ không theo phim.
DEM_PATH = os.path.expanduser("~/.grokpipe-dem-ngay.json")
DEM_LOCK = threading.RLock()
DEM: dict[str, dict[str, int]] = {}     # "9222" -> {"2026-08-05": 37}
DEM_GIU = 60                            # giữ 60 ngày gần nhất, cắt bớt cho gọn


def _ngay() -> str:
    return time.strftime("%Y-%m-%d")


def _dem_nap():
    global DEM
    try:
        DEM = json.load(open(DEM_PATH, encoding="utf-8"))
    except Exception:
        DEM = {}


def _dem_cong(port: int | None = None):
    """Cộng 1 cho tài khoản vừa tạo xong một bản.

    PHẢI gọi lúc file ĐÃ nằm trên đĩa. Đếm lúc gửi lệnh thì mọi lần thất bại đều
    bị tính, và con số kỷ lục thành vô nghĩa — mà kỷ lục mới là thứ ta cần."""
    if port is None:
        ep = getattr(_TL, "endpoint", "") or ""
        try:
            port = int(ep.rstrip("/").rsplit(":", 1)[1])
        except Exception:
            return
    with DEM_LOCK:
        d = DEM.setdefault(str(port), {})
        hn = _ngay()
        d[hn] = d.get(hn, 0) + 1
        for cu in sorted(d)[:-DEM_GIU]:
            d.pop(cu, None)
        try:
            with open(DEM_PATH, "w", encoding="utf-8") as f:
                json.dump(DEM, f, ensure_ascii=False, indent=1, sort_keys=True)
        except Exception as e:
            _LOG.warning("không ghi được bộ đếm ngày: %s", e)


def _dem_xem(port: int) -> dict:
    """{hom_nay, ky_luc, ky_luc_ngay} của một tài khoản."""
    with DEM_LOCK:
        d = dict(DEM.get(str(port), {}))
    if not d:
        return {"hom_nay": 0, "ky_luc": 0, "ky_luc_ngay": ""}
    ngay, cao = max(d.items(), key=lambda x: (x[1], x[0]))
    return {"hom_nay": d.get(_ngay(), 0), "ky_luc": cao, "ky_luc_ngay": ngay}


def _init_accounts():
    """Nạp accounts từ file; lần đầu chạy thì dựng từ cờ --cdp/--cdp-grok rồi lưu lại."""
    global ACCOUNTS, TRAN_REF
    if os.path.exists(ACC_PATH):
        try:
            _d = json.load(open(ACC_PATH, encoding="utf-8"))
            ACCOUNTS = _d["accounts"]
            TRAN_REF = max(1, min(TRAN_REF_MAX, int(_d.get("tran_ref") or TRAN_REF)))
            return
        except Exception:
            pass
    legacy = {9222: "~/.grokpipe-chrome", 9223: "~/.grokpipe-chrome-2",
              9224: "~/.grokpipe-chrome-3", 9225: "~/.grokpipe-chrome-4",
              9226: "~/.grokpipe-chrome-5", 9227: "~/.grokpipe-chrome-6",
              9228: "~/.grokpipe-grok-7", 9229: "~/.grokpipe-grok-8"}
    accs = []
    for i, ep in enumerate(CDP_ENDPOINTS, 1):
        port = int(ep.rstrip("/").rsplit(":", 1)[1])
        accs.append({"id": f"gpt-{i}", "kind": "img", "port": port,
                     "profile": legacy.get(port, f"~/.grokpipe-chrome-p{port}"), "enabled": True})
    for i, ep in enumerate(GROK_ENDPOINTS, 1):
        port = int(ep.rstrip("/").rsplit(":", 1)[1])
        accs.append({"id": f"grok-{i}", "kind": "vid", "port": port,
                     "profile": legacy.get(port, f"~/.grokpipe-grok-p{port}"), "enabled": True})
    for _a in accs:
        _a["tabs"] = max(1, min(MAX_TABS, int(_a.get("tabs") or 1)))
    ACCOUNTS = accs
    _save_accounts()


def _pool(kind: str) -> list[str]:
    """Endpoint các tài khoản ĐANG BẬT cho loại việc này.

    Video fallback sang tài khoản ChatGPT nếu chưa khai báo tài khoản Grok nào."""
    with ACC_LOCK:
        pool = [_ep(a) for a in ACCOUNTS if a["kind"] == kind and a["enabled"]]
        if kind == "vid" and not pool:
            # Dự phòng: mở grok.com ngay trong cửa sổ ChatGPT. Chỉ chạy được nếu
            # profile đó CŨNG đã đăng nhập grok.com.
            #
            # KHÔNG CẢNH BÁO Ở ĐÂY (user chốt 2026-08-13). Hàm này được gọi mỗi
            # vòng thợ và mỗi lần đếm tài khoản, nên một dòng warning ở đây là
            # vài chục dòng mỗi phút — ngập hộp 🐞 và che mất lỗi thật. Tắt Grok
            # là chuyện bình thường: user bật khi nào cần dựng video.
            # Việc video chạy nhờ mà không nối được Grok vẫn báo lỗi rõ ràng ở
            # đúng job đó ("Không nối được Grok"), nên không có gì bị giấu.
            pool = [_ep(a) for a in ACCOUNTS if a["kind"] == "img" and a["enabled"]]
        return pool


# Cờ giảm RAM cho các cửa sổ Chrome tự động. Mỗi cửa sổ vốn ngốn ~1.5GB vì
# Chrome tách rất nhiều tiến trình con và chạy đủ thứ dịch vụ nền không cần cho
# việc tạo ảnh/video. Các cờ này cắt phần thừa, giữ nguyên phần dùng thật.
_LOW_RAM_FLAGS = [
    "--renderer-process-limit=2",        # gộp tab vào ít tiến trình render
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-sync",
    "--disable-component-update",
    "--disable-features=Translate,MediaRouter,OptimizationHints,CalculateNativeWinOcclusion",
    # 1024MB thay vì 512: trần 512 làm tab ChatGPT (chat dài + ảnh sinh ra) chạm
    # trần V8 rồi tự sập với "Target crashed". Đổi lại mỗi cửa sổ tốn RAM hơn —
    # máy 16GB nên chạy ít cửa sổ cùng lúc.
    "--js-flags=--max-old-space-size=1024",
    "--disable-backgrounding-occluded-windows=false",
    # TẮT QUIC/HTTP3 (2026-08-12). grok.com phục vụ qua QUIC, và một phiên QUIC
    # hỏng giữa chừng thì Chrome KHÔNG tự lùi về TCP: mọi lần điều hướng sau đó
    # chết ngay với ERR_QUIC_PROTOCOL_ERROR, kể cả khi mạng vẫn tốt và trang mở
    # bình thường ở Chrome khác. Đúng ca "chạy được mấy video rồi lỗi liên tục,
    # xong không vào nổi grok.com". Chạy trên TCP chậm hơn không đáng kể.
    "--disable-quic",
]


def _launch_chrome(a: dict) -> bool:
    """Mở cửa sổ Chrome cho tài khoản này (kèm tab đệm about:blank).

    MỞ Ở PHÍA SAU, KHÔNG CƯỚP FOCUS (user chốt 2026-08-14). Gọi thẳng binary thì
    macOS coi là khởi động app và bật cửa sổ lên trước mặt — trước đây hiếm nên
    chịu được, nhưng từ lúc có luật xoay vòng thì mỗi lỗi là một lần mở cửa sổ,
    và user đang gõ ở app khác sẽ mất chữ liên tục.

    PHẢI CÓ CẢ `-g` LẪN `-j`, `-g` MỘT MÌNH KHÔNG ĐỦ.
    `-g` chỉ chặn activate khi app KHỞI ĐỘNG. Chrome cá nhân của user gần như
    luôn đang chạy, nên `open -n` không phải là khởi động app mà là thêm một
    tiến trình vào app đang active — và cửa sổ mới vẫn nhảy lên trước mặt. Đo
    thật 2026-08-14: đưa Finder lên foreground rồi mở bằng `-g -n` → foreground
    đổi sang Google Chrome. Thêm `-j` (launch hidden) thì Finder giữ nguyên,
    lặp lại hai lần đều vậy.
    `-n` buộc tạo instance mới; thiếu nó thì cờ debug rơi vào cửa sổ có sẵn.

    Cửa sổ vẫn mở thật, chỉ là bị GIẤU: Cmd+Tab hoặc bấm Dock là thấy. Đã đo
    Chrome ẩn KHÔNG bị bóp hiệu năng — `visibilityState` vẫn `visible`, timer
    100ms × 10 chạy đúng 1,01s, không hề bị throttle như tab nền.

    `_kill_chrome` vẫn tìm được tiến trình: `open` chỉ là bệ phóng rồi thoát,
    còn tiến trình Chrome thật vẫn mang đủ cờ `--remote-debugging-port=<port>`.
    """
    import subprocess
    if not os.path.exists(_CHROME_BIN):
        return False
    profile = os.path.abspath(os.path.expanduser(a["profile"]))
    os.makedirs(profile, exist_ok=True)
    co = [f"--remote-debugging-port={a['port']}", f"--user-data-dir={profile}",
          *_LOW_RAM_FLAGS, "about:blank", _KIND_URL[a["kind"]]]
    try:
        subprocess.Popen(["open", "-g", "-j", "-n", "-a", _CHROME_APP, "--args", *co],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        # `open` hỏng (thiếu app bundle, quyền lạ) thì vẫn phải mở được Chrome —
        # thà nhảy lên màn hình còn hơn board đứng im không có cửa sổ nào.
        _LOG.warning("mở Chrome nền không được (%s) — mở kiểu thường.", str(e)[:60])
        subprocess.Popen([_CHROME_BIN, *co],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def _wipe_profile(profile: str) -> tuple[str, str]:
    """Xóa hẳn thư mục profile Chrome của một tài khoản.

    Chặn nhiều lớp vì đây là xóa vĩnh viễn: đường dẫn phải nằm trong thư mục
    home của user VÀ tên thư mục phải bắt đầu bằng '.grokpipe' — đúng dạng do
    board tự tạo. Bất cứ đường dẫn nào khác đều bị từ chối, kể cả khi file
    cấu hình bị sửa tay thành '/' hay '~'."""
    import shutil
    p = os.path.abspath(os.path.expanduser(profile or ""))
    home = os.path.abspath(os.path.expanduser("~"))
    name = os.path.basename(p)
    if not p.startswith(home + os.sep) or not name.startswith(".grokpipe"):
        return "", f"từ chối xóa đường dẫn không an toàn: {p}"
    if not os.path.isdir(p):
        return "", ""
    try:
        size = sum(os.path.getsize(os.path.join(r, f))
                   for r, _, fs in os.walk(p) for f in fs
                   if os.path.exists(os.path.join(r, f)))
    except OSError:
        size = 0
    try:
        shutil.rmtree(p, ignore_errors=True)
    except Exception as e:
        return "", str(e)[:120]
    return f"{size / 1024 / 1024:.0f} MB", ""


# Đếm số lần Chrome bị đóng. Mỗi luồng thợ giữ bản sao con số này; khi lệch
# nghĩa là Chrome nó đang bám vào đã chết, phải nhả sạch Playwright rồi nối lại.
# Thiếu bộ đếm này thì luồng thợ vẫn dùng context cũ và mọi job chết ở bước mở
# tab với "Target page, context or browser has been closed".
CHROME_GEN = {"n": 0}


# Bấm nút dừng ngay trên trang. Bám data-testid trước, aria-label chỉ để dự
# phòng — và phải loại nút đọc chính tả/giọng nói, chúng cũng mang chữ "stop".
_JS_BAM_STOP = """() => {
  const hien = [...document.querySelectorAll('button')]
    .filter(e => e.getBoundingClientRect().width > 0);
  const nhan = e => (e.getAttribute('aria-label') || '');
  const n = hien.find(e => e.getAttribute('data-testid') === 'stop-button')
    || hien.find(e => /stop|dừng/i.test(nhan(e))
                 && !/dictation|voice|đọc|nói/i.test(nhan(e)));
  if (!n) return 0;
  n.click();
  return 1;
}"""


def _bam_stop_tren_tab(port: int) -> int:
    """Bấm 'Stop answering' trên mọi tab ChatGPT/Grok của một cửa sổ Chrome.

    ĐÓNG CHROME KHÔNG DỪNG ĐƯỢC ĐOẠN CHAT. Việc sinh ảnh chạy ở phía máy chủ
    OpenAI, không phải trong trình duyệt: giết cửa sổ chỉ làm mình hết nhìn thấy,
    còn lượt đó vẫn vẽ tiếp, vẫn tính vào hạn mức, và mở lại Chrome là thấy nó
    vẫn đang chạy. Muốn cắt thật thì phải bấm đúng cái nút dừng — chính là nút
    Submit đã đổi hình lúc đang sinh.

    Mở kết nối CDP RIÊNG cho luồng HTTP này, không dùng ké _TL của thợ: thợ đang
    nằm trong vòng chờ và có phiên riêng, hai luồng chung một page thì cái này
    giẫm lên cái kia."""
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    try:
        b = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=15000)
        n = 0
        for ctx in b.contexts:
            for p in list(ctx.pages):
                url = p.url or ""
                if "chatgpt.com" not in url and "grok.com" not in url:
                    continue
                try:
                    n += int(p.evaluate(_JS_BAM_STOP) or 0)
                except Exception as e:
                    _LOG.warning("không bấm được nút dừng trên %s: %s", url[:50], e)
        b.close()
        return n
    finally:
        try:
            pw.stop()
        except Exception:
            pass


def _kill_chrome(port: int):
    """Đóng cửa sổ Chrome của tài khoản này.

    Mỗi tài khoản là một tiến trình Chrome riêng (user-data-dir riêng), nhận diện
    được qua cờ --remote-debugging-port nên không đụng vào Chrome cá nhân của user.
    Phiên đăng nhập nằm trong profile trên đĩa, đóng cửa sổ không mất."""
    import subprocess
    ep = f"http://127.0.0.1:{port}"
    subprocess.run(["pkill", "-f", f"remote-debugging-port={port}"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # CHỜ CỔNG NHẢ THẬT, đừng bắn xong đi luôn.
    #
    # `pkill` chỉ gửi TERM; Chrome còn hàng chục tiến trình con và có thể giữ cổng
    # thêm vài giây. Mở lại ngay sau đó là trúng lúc cổng còn bận — cửa sổ mới im
    # lặng không lên, và ta lại có một cổng "treo" phải bấm tay.
    for _ in range(10):                       # tối đa ~5 giây
        if not _ping_http(ep):
            break
        time.sleep(0.5)
    else:
        subprocess.run(["pkill", "-9", "-f", f"remote-debugging-port={port}"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _LOG.warning("Chrome cổng %s không chịu tắt sau 5s — đã buộc dừng (kill -9).", port)
        time.sleep(1)
    # Chrome để lại SingletonLock trong profile khi bị giết ngang; còn file này
    # thì lần mở sau bị chính Chrome từ chối ("profile đang được dùng").
    try:
        with ACC_LOCK:
            a = next((x for x in ACCOUNTS if x["port"] == port), None)
        if a:
            prof = os.path.abspath(os.path.expanduser(a["profile"]))
            for ten in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
                p = os.path.join(prof, ten)
                if os.path.islink(p) or os.path.exists(p):
                    os.remove(p)
    except OSError as e:
        _LOG.warning("không dọn được khoá profile cổng %s: %s", port, str(e)[:60])
    CHROME_GEN["n"] += 1
    _WS_HONG.pop(ep, None)                    # cửa sổ đã đóng → dấu nửa vời hết nghĩa


_THUMB_W = {240, 320, 420, 640}          # chỉ cho phép vài cỡ, tránh sinh cache vô hạn


def _thumb(src: str, w: int) -> str | None:
    """Trả đường dẫn bản thu nhỏ (tạo và cache nếu chưa có). None nếu không làm được."""
    if w not in _THUMB_W:
        w = min(_THUMB_W, key=lambda x: abs(x - w))
    d = os.path.join(os.path.dirname(os.path.dirname(src)), ".thumbs")
    base = os.path.splitext(os.path.basename(src))[0]
    tag = os.path.basename(os.path.dirname(src))
    tp = os.path.join(d, f"{tag}__{base}__{w}.jpg")
    try:
        if os.path.isfile(tp) and os.path.getmtime(tp) >= os.path.getmtime(src):
            return tp
        from PIL import Image
        os.makedirs(d, exist_ok=True)
        im = Image.open(src)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        if im.width > w:
            im = im.resize((w, max(1, round(im.height * w / im.width))), Image.LANCZOS)
        im.save(tp, "JPEG", quality=82, optimize=True)
        return tp
    except Exception as e:
        _LOG.debug("không tạo được thumbnail cho %s: %s", src, e)
        return None


def _is_quota_error(e: Exception) -> bool:
    """Lỗi thuộc loại 'hết lượt tạo ảnh/video' — đáng để đổi sang tài khoản khác."""
    m = str(e).lower()
    return any(k in m for k in (
        "hết lượt", "het luot", "rate limit", "limit reached", "quota",
        "you've reached", "upgrade to", "try again later", "không sinh ảnh",
        "nghi-den",
    ))


# ---- LỖI DỮ LIỆU: ĐỔI CHROME BAO NHIÊU LẦN CŨNG VÔ ÍCH ---------------------
# Board xoay vòng Chrome cho MỌI lỗi render (user chốt 2026-08-14), nhưng lỗi
# nằm trong sf-board.json thì xoay là quay tít vô nghĩa: ref chưa pick ảnh, shot
# chưa có prompt, SF trỏ vào id đã chết. Đúng loại vừa gây ra 148 việc lỗi cùng
# một câu "thẻ địa điểm CHƯA CÓ ẢNH (picked)" — cho chúng thử lại vô hạn là đốt
# sạch hạn mức của mọi tài khoản trong khi không ảnh nào có thể ra.
_LOI_DU_LIEU = (
    "chưa có ảnh", "chua co anh", "chưa có prompt", "chua co prompt",
    "không tìm thấy", "khong tim thay", "thiếu ref", "thieu ref",
    "đã huỷ", "đã dừng", "chưa chạy",
)


def _loi_du_lieu(e: Exception) -> bool:
    """Lỗi ở dữ liệu board, không phải ở Chrome — báo ngay, đừng xoay tài khoản."""
    m = str(e).lower()
    return any(k in m for k in _LOI_DU_LIEU)


# Lỗi gốc → MỘT CÂU NGẮN đọc là hiểu. Thông báo thật của Playwright/ChatGPT dài
# vài dòng, có ngoặc lồng ngoặc; cắt cứng 60 ký tự thì ra những dòng cụt kiểu
# "…sau 2 lượt up cả loạt (có )" — vừa xấu vừa không nói được điều gì.
# THỨ TỰ CÓ Ý NGHĨA: khớp từ trên xuống, nên NGUYÊN NHÂN phải đứng trước
# TRIỆU CHỨNG. "Target crashed" luôn đi kèm câu "không bấm được ô soạn" — để
# "ô soạn" lên trước thì mọi cú tab sập đều bị ghi thành "không bấm được ô
# nhập", giấu mất việc máy đang hết RAM.
_LOI_GON = [
    ("target crashed", "tab Chrome sập (máy hết RAM)"),
    ("page crashed", "tab Chrome sập (máy hết RAM)"),
    ("has been closed", "cửa sổ Chrome đã đóng"),
    ("target closed", "cửa sổ Chrome đã đóng"),
    ("không đính nổi", "không đính được ảnh ref"),
    ("hết hạn mức đính tệp", "hết lượt đính ảnh"),
    ("plan limit", "hết lượt tạo ảnh (giới hạn gói)"),
    ("limit reached", "hết lượt tạo ảnh"),
    ("you've reached", "hết lượt tạo ảnh"),
    ("rate limit", "bị chặn tốc độ"),
    ("hết lượt", "hết lượt tạo ảnh"),
    ("ô soạn", "không bấm được ô nhập"),
    ("connect_over_cdp", "không nối được Chrome"),
    ("không nối được", "không nối được Chrome"),
    ("cloudflare", "Cloudflare chặn"),
    ("conversation-turn", "không đọc được câu trả lời"),
    ("không trả ảnh", "ChatGPT không trả ảnh"),
    ("err_quic", "mạng lỗi (QUIC)"),
    ("timeout", "chờ quá lâu"),
]


def _loi_gon(e) -> str:
    """Câu ngắn mô tả lỗi, để ghi log và hiện lên thẻ."""
    m = str(e).lower()
    for khoa, gon in _LOI_GON:
        if khoa in m:
            return gon
    return (str(e).split("\n")[0].strip() or "lỗi không rõ")[:70]


# ---- KHÔNG CÒN "NGHỈ TỚI GIỜ" (bỏ 2026-08-14) ---------------------------
# ChatGPT chặn đính tệp theo giờ và nói thẳng giờ mở lại ("…until 3:45 PM");
# board từng đọc mốc đó rồi cho tài khoản nghỉ tới đúng lúc ấy. Đã bỏ: user chốt
# mọi lỗi đều xoay sang tài khoản kế tiếp, không treo ai ngoài vòng. Tài khoản
# cạn lượt vẫn được vào vòng — nó lỗi lại thì xoay tiếp, rẻ hơn nhiều so với
# đứng ngoài mấy tiếng trong khi ChatGPT có thể mở lượt sớm hơn giờ nó nói.
# `image_chatgpt.py` vẫn gắn nhãn `[NGHI-DEN:…]` vào chuỗi lỗi; board giờ chỉ
# ghi log cho biết, không hành động theo.


# ---- LỖI RENDER → MỘT REASON CODE CÓ KIỂU ---------------------------------
# Chỉ để GHI SỔ. Không nhánh nào ở `_worker` đọc giá trị này để quyết định xoay
# hay thử lại — luật "mọi lỗi đều xoay" (user chốt 2026-08-14) giữ nguyên.
#
# Thứ tự khớp có ý nghĩa: HUỶ đứng trước LỖI DỮ LIỆU, vì `_LOI_DU_LIEU` chứa cả
# "đã huỷ"/"đã dừng" — user bấm dừng KHÔNG phải bug, ghi vào sổ là báo động giả.
_LY_DO_HUY = ("đã huỷ", "đã dừng", "chưa chạy")

# Cùng một lỗi phải lặp đủ số lần này mới được ghi sổ.
LAP_MOI_GHI = 3

# Cờ huỷ mà việc vẫn 'đang chạy' quá ngần này giây thì coi là vi phạm bất biến.
# Phải lớn hơn một nhịp người gác (30s) để không bắt nhầm cửa sổ đua lúc thợ vừa
# nhấc việc: cờ được đánh và việc được nhấc gần như cùng lúc là chuyện bình thường.
CHO_HUY_TOI_DA = 90


def _soat_co_huy(da_huy, jobs, thay_tu: dict, da_bao: set, bay_gio=None) -> list:
    """Ident nào vừa mang cờ huỷ vừa 'đang chạy' đủ lâu để coi là VI PHẠM?

    Trả về `[(ident, số giây)]` cần ghi sổ; mỗi ident chỉ trả MỘT lần cho tới khi
    tình trạng tự hết. `thay_tu` và `da_bao` là bộ nhớ của người gác, hàm này cập
    nhật tại chỗ để cả hai bên nhìn cùng một sự thật.

    KHÔNG gọi `bi_huy()` ở đây: hàm đó ĂN cờ khi đọc, người gác gọi vào là cướp
    mất cờ của thợ và làm hỏng chính cơ chế huỷ mà nó đang canh."""
    bay_gio = time.time() if bay_gio is None else bay_gio
    sai = {k for k in da_huy if (jobs.get(k) or {}).get("state") == "running"}
    for k in list(thay_tu):
        if k not in sai:                 # đã tự hết — quên đi, cho báo lại lần sau
            thay_tu.pop(k, None)
            da_bao.discard(k)
    can_bao = []
    for k in sorted(sai):
        lau = int(bay_gio - thay_tu.setdefault(k, bay_gio))
        if lau < CHO_HUY_TOI_DA or k in da_bao:
            continue                     # còn trong cửa sổ đua lúc thợ nhấc việc
        da_bao.add(k)
        can_bao.append((k, lau))
    return can_bao


def _loai_viec(ident: str) -> str:
    """'vid' hay 'img' — đọc SỔ SHOT của board, không đoán theo tiền tố tên.

    Chỉ dùng để gắn nhãn cho sổ lỗi; đọc hỏng thì trả '' chứ không được ném."""
    try:
        return "vid" if BOARD.get_shot(ident)[0] is not None else "img"
    except Exception:                                # noqa: BLE001
        return ""


def _dau_vet_buoc(kind: str) -> list:
    """Dấu vết TỪNG BƯỚC của lượt vừa hỏng, lấy từ phiên của chính luồng thợ này.

    Sổ lỗi trước đây chỉ ghi kết cục ("hết 600s chờ render"), nên đọc sổ không
    biết lượt ấy chết ở bước nào. Đính danh sách này vào sự kiện là biến câu hỏi
    "có bug video" thành câu trả lời "chết ở `chip_thoi_luong`, sau 8 giây".

    Không bao giờ ném: đây là phần phụ trợ của một thông báo lỗi.
    """
    try:
        sess = getattr(_TL, "gsess" if kind == "vid" else "sess", None)
        vet = getattr(sess, "vet", None)
        return vet.lay() if vet is not None else []
    except Exception:                       # noqa: BLE001
        return []


def _phanh_ghi_so(kind: str) -> int:
    """Bao nhiêu lần lặp mới ghi sổ — VIDEO ghi ngay lần đầu.

    Phanh sinh ra để sổ khỏi thành rác: với ẢNH, xoay tài khoản là chuyện thường
    ngày nên chỉ lần thứ 3 mới đáng lưu. Với VIDEO thì ngược hẳn — Grok trừ
    credit theo TỪNG submit, nên "chờ hỏng 3 lần" nghĩa là đốt 3 lần tiền rồi
    mới có dòng đầu tiên. Bug tab-trôi-sang-post-cũ im lặng suốt cũng vì thế.
    """
    return 1 if kind == "vid" else LAP_MOI_GHI


def _ly_do_lo(vi: str | None, chi_tiet: str = "") -> str:
    """Lô hỏng → reason code cho sổ lỗi runtime. Hàm thuần, không ghi state.

    Khác `_ly_do_loi`: chỗ kia phân loại EXCEPTION của thợ, chỗ này phân loại
    một lô KHÔNG ném lỗi — nó tính ra câu `_vi` rồi dán nhãn và tự gửi lại. Vì
    không ai ném nên trước đây không có gì vào sổ: sổ 15 sự kiện trong khi log
    Terminal đặc kín lỗi cả ngày (đo 2026-08-15).

    `chi_tiet` là văn bản ChatGPT trả kèm, nếu có. Nó là thứ DUY NHẤT phân biệt
    được ba ca trông giống hệt nhau ở mức `_vi` ("không trả ảnh nào") mà hướng
    xử lý ngược nhau: hết quota → đổi tài khoản · guardrail → sửa prompt · không
    rõ → chưa biết, đừng đoán.
    """
    v = f"{vi or ''} {chi_tiet or ''}".lower()
    if any(k in v for k in _LY_DO_HUY):
        return "CANCELLED"                  # user dừng — không phải bug
    if "chế độ" in v:
        return "MODE_UNSET"                 # selector chết, chặn cả board
    if "send bị nuốt" in v or "chưa gửi được tin" in v:
        return "SEND_SWALLOWED"
    if "không đính được" in v or "thiếu" in v and "ref" in v:
        return "REF_UPLOAD_FAILED"
    # Quota phải soi TRƯỚC guardrail: câu quota cũng nằm trong nhánh "không trả
    # ảnh nào", mà đổ nhầm sang guardrail là đẩy user đi sửa prompt vô can.
    if "limit" in v and ("image gen" in v or "hạn mức" in v):
        return "ACCOUNT_LOST"
    if "content polic" in v or "guardrail" in v:
        return "GUARDRAIL"
    if "trả kèm chữ" in v:
        return "TEXT_INSTEAD_OF_IMAGE"
    if "thừa" in v and "ảnh" in v:
        return "COUNT_EXTRA"
    if "chỉ về" in v:
        return "COUNT_SHORT"
    if "không trả ảnh nào" in v:
        return "NO_IMAGES"
    return "LO_FAILED"


def _ghi_so_lo_hong(ident: str, viec, vi: str, chi_tiet: str, n_ve: int) -> None:
    """Ghi một sự kiện vào sổ runtime khi LÔ hỏng hẳn (đã thử hết lượt).

    CHỈ ghi ở lần hỏng CUỐI, không ghi mỗi lần gửi lại: lô nào cũng thử 2 lượt
    nên ghi cả hai là sổ nhân đôi mà không thêm tin gì. Lượt giữa vẫn nằm trong
    log Terminal và trong dấu vết `VET` của từng thẻ.

    Không ném ra ngoài trong mọi trường hợp — `report_runtime_bug` đã cam kết
    thế, nhưng chỗ này đứng SAU khi nhãn đã dán, nên kể cả nó đổi ý thì lô vẫn
    phải đi tiếp bình thường.
    """
    ly_do = _ly_do_lo(vi, chi_tiet)
    if ly_do == "CANCELLED":
        return                              # user bấm dừng, không phải bug
    try:
        report_runtime_bug({
            "reason_code": ly_do,
            "category": "lo_that_bai",
            "severity": "ERROR",
            "job": {"job_id": ident, "kind": "img", "phase": "lo",
                    "so_anh": len(viec), "ve_duoc": n_ve},
            "runtime": {"buoc": _dau_vet_buoc("img")},
            "exc": RuntimeError(f"{vi} · {(chi_tiet or '')[:200]}".strip(" ·")),
        })
    except Exception as e:                  # noqa: BLE001
        _LOG.warning("không ghi được sổ lỗi cho lô (%s)", str(e)[:80])


def _ly_do_loi(e: Exception) -> str:
    """Lỗi render → reason code cho sổ lỗi runtime. Hàm thuần, không ghi state."""
    m = str(e).lower()
    if any(k in m for k in _LY_DO_HUY):
        return "CANCELLED"              # user dừng — bộ phân loại sẽ bỏ qua
    if _loi_du_lieu(e):
        return "PERMANENT"              # sai dữ liệu board, xoay Chrome vô ích
    if _is_dead_session_error(e):
        return "SESSION_TRANSIENT"      # tab/cửa sổ Chrome chết
    if _is_quota_error(e):
        return "ACCOUNT_LOST"           # hết lượt / bị chặn
    return "PROVIDER_TRANSIENT"         # còn lại: phía Grok/ChatGPT


def _is_dead_session_error(e: Exception) -> bool:
    """Tab/cửa sổ Chrome đã đóng — nhả phiên rồi thử lại trên CÙNG tài khoản."""
    m = str(e).lower()
    return any(k in m for k in (
        "has been closed", "target closed", "browser has been closed",
        "connection closed", "websocket", "target page, context or browser",
        # renderer bị hệ thống giết vì hết bộ nhớ ("Aw, Snap! Error code: 5").
        # Thiếu hai khoá này thì job chết luôn thay vì mở lại phiên và thử lại.
        "target crashed", "page crashed",
    ))


def _nhan_tien_trinh(cmd: str, cong_theo_prof: dict) -> str:
    """Tên dễ đọc của một tiến trình, để gộp RAM theo APP chứ không theo tiến trình.

    Chrome đẻ hàng chục tiến trình con (mỗi tab, mỗi GPU, mỗi tiện ích một cái);
    liệt kê thô thì bảng đầy Google Chrome Helper mà không ai biết cái nào của cửa
    sổ nào. Gộp theo `--user-data-dir` mới ra được "cửa sổ pipeline cổng 9222"
    tách khỏi "Chrome cá nhân" — và đó chính là câu hỏi cần trả lời: chỗ ngốn RAM
    có phải do board không.
    """
    m = re.search(r"--user-data-dir=(\S+)", cmd)
    if m and m.group(1) in cong_theo_prof:
        return f"Chrome pipeline :{cong_theo_prof[m.group(1)]}"
    if "Google Chrome" in cmd:
        return "Chrome (cá nhân)"
    m = re.search(r"sfboard\.py\s+(\S+)", cmd)
    if m:
        return f"board {m.group(1).replace('PIPELINE-', '').replace('.project', '')}"
    if "playwright" in cmd and "node" in cmd:
        return "Playwright (driver)"
    # Bó .app ở BẤT KỲ đâu trong đường dẫn, không riêng /Applications: app cài
    # trong ~/Library hay /System cũng phải ra tên app, nếu không bảng đầy những
    # nhãn vô nghĩa kiểu "Application" (cắt từ "Application Support").
    m = re.search(r"/([^/]+)\.app/", cmd)
    if m:
        return m.group(1)
    return os.path.basename((cmd.split() or [""])[0])[:28]


def _anh_chup_may(port: int = 0, top: int = 8) -> str:
    """Ảnh chụp bộ nhớ máy NGAY LÚC NÀY — đính vào log khi tab chết.

    Chrome báo "Aw, Snap! Error code: 5" khi renderer bị HỆ ĐIỀU HÀNH thu hồi,
    không phải khi phần mềm sập: sập thật thì để lại file .ips trong
    ~/Library/Logs/DiagnosticReports, còn bị thu hồi vì cạn bộ nhớ thì KHÔNG để
    lại gì cả. Nghĩa là sau khi tab chết, không còn dấu vết nào để lần ngược —
    trừ khi chụp lại đúng lúc nó chết. Đó là việc của hàm này.

    Chụp ĐỦ chứ không chỉ tổng: có bảng ai đang giữ bao nhiêu, vì "hết RAM" chưa
    phải kết luận — còn phải biết hết vì cái gì. Nếu thủ phạm không phải Chrome
    pipeline thì hạ số tab của board là chữa nhầm chỗ.

    Chỉ đọc, không đổi gì. Hỏng thì trả chuỗi báo hỏng, không ném lỗi ra ngoài
    (nó chạy trong nhánh xử lý lỗi — ném tiếp là che mất lỗi gốc).
    """
    try:
        import subprocess as _sp
        ra = []
        vm = _sp.run(["vm_stat"], capture_output=True, text=True, timeout=5).stdout
        psz = int(re.search(r"page size of (\d+)", vm).group(1))
        free = int(re.search(r"Pages free:\s+(\d+)", vm).group(1)) * psz / 1024**3
        tong = int(_sp.run(["sysctl", "-n", "hw.memsize"], capture_output=True,
                           text=True, timeout=5).stdout or 0) / 1024**3
        ra.append(f"RAM trống {free:.2f}/{tong:.0f} GB")
        sw = _sp.run(["sysctl", "-n", "vm.swapusage"], capture_output=True,
                     text=True, timeout=5).stdout
        m = re.search(r"total = ([\d.]+)M.*used = ([\d.]+)M", sw)
        if m:
            t, u = float(m.group(1)) / 1024, float(m.group(2)) / 1024
            ra.append(f"swap {u:.1f}/{t:.1f} GB ({u / max(t, .01) * 100:.0f}%)")

        # MỘT lần đọc ps cho tất cả — gọi nhiều lần thì mỗi lần là một thời điểm
        # khác nhau, và bảng sẽ mô tả một cái máy không có thật.
        dong = _sp.run(["ps", "-axo", "rss,command"], capture_output=True,
                       text=True, timeout=8).stdout.splitlines()[1:]
        cong_theo_prof = {}
        for d in dong:
            mp = re.search(r"--remote-debugging-port=(\d+)", d)
            mu = re.search(r"--user-data-dir=(\S+)", d)
            if mp and mu:
                cong_theo_prof[mu.group(1)] = mp.group(1)

        gom: dict[str, float] = {}
        for d in dong:
            p = d.split(None, 1)
            if len(p) < 2 or not p[0].isdigit():
                continue
            ten = _nhan_tien_trinh(p[1], cong_theo_prof)
            gom[ten] = gom.get(ten, 0) + int(p[0]) / 1024

        if port and str(port) in cong_theo_prof.values():
            mb = gom.get(f"Chrome pipeline :{port}", 0)
            ra.append(f"cửa sổ vừa chết (cổng {port}) giữ {mb:.0f} MB")
        xep = sorted(gom.items(), key=lambda x: -x[1])[:top]
        bang = " · ".join(f"{k} {v:.0f}MB" for k, v in xep if v >= 50)
        ra.append(f"ai đang giữ RAM: {bang}")
        return " · ".join(ra)
    except Exception as e:
        return f"không đọc được hiện trạng máy ({str(e)[:60]})"


# CHROME "SỐNG NỬA VỜI": HTTP trả lời nhưng WebSocket CDP treo.
#
# Ping `/json/version` KHÔNG chứng minh được gì trong ca này — nó trả 200 bình
# thường trong khi `connect_over_cdp` treo 180 giây ở bước `<ws connecting>`.
# Board tin là sống nên không mở lại, không báo lỗi, và mọi job đẩy vào đều chết:
# đúng cái "treo cổng" phải ngồi bấm tay xưa nay.
#
# Không đi viết WebSocket client để tự đoán. Dùng BẰNG CHỨNG THẬT: thợ nào nối
# CDP hụt thì đánh dấu endpoint đó hỏng, và giữ dấu tới khi cửa sổ được mở lại.
# Fail-closed — thà báo chết oan (board mở lại, mất vài giây) còn hơn báo sống
# nhầm (job chết hàng loạt, log sạch bong).
_WS_HONG: dict[str, int] = {}      # endpoint -> thế hệ Chrome lúc bị đánh dấu


def _ping_http(url: str) -> bool:
    """Cổng debug có TRẢ LỜI HTTP không — chỉ là tầng vận chuyển, KHÔNG đồng
    nghĩa dùng được. Tách riêng để phân biệt 'cửa sổ đã đóng hẳn' với 'cửa sổ còn
    đó nhưng CDP treo'."""
    import urllib.request
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/json/version", timeout=3):
            return True
    except Exception:
        return False


def _bao_ws_hong(endpoint: str, vi: str = "") -> None:
    if not endpoint:
        return
    if _WS_HONG.get(endpoint) != CHROME_GEN["n"]:
        _WS_HONG[endpoint] = CHROME_GEN["n"]
        _LOG.warning("Chrome %s SỐNG NỬA VỜI — HTTP trả lời nhưng CDP không nối "
                     "được%s. Coi như chết để board mở lại.",
                     endpoint, f" ({vi[:70]})" if vi else "")


def _endpoint_alive(url: str) -> bool:
    """Cửa sổ Chrome debug ở endpoint này còn DÙNG ĐƯỢC không.

    Không chỉ là "có mở": cửa sổ nửa vời bị coi là chết cho tới khi mở lại.
    """
    # Dấu chỉ hết hiệu lực khi Chrome được đóng/mở lại (thế hệ tăng).
    if _WS_HONG.get(url) == CHROME_GEN["n"]:
        return False
    return _ping_http(url)


def _release_tl():
    """Nhả phiên + Playwright CỦA LUỒNG NÀY.

    KHÔNG đóng tab: tab ChatGPT thường là tab duy nhất của cửa sổ, đóng nó
    sẽ tắt luôn Chrome và mất phiên đăng nhập của tài khoản đó."""
    try:
        pw = getattr(_TL, "pw", None)
        if pw is not None:
            pw.stop()
    except Exception:
        pass
    _TL.pw = None
    _TL.browser = None
    _TL.ctx = None
    _TL.sess = None
    _TL.gsess = None

# ---------------------------------------------------------------- generation
# CƠ KHÍ HÀNG ĐỢI Ở hangdoi.py (tách 2026-08-12) — hàng đợi, thứ tự ưu tiên,
# trạng thái job, cờ huỷ, khoá địa điểm. Ở đó không có Playwright nên viết được
# phép thử mà không cần dựng board lẫn Chrome. Import thẳng tên vào đây: dict/
# set/Queue là đối tượng dùng chung nên mọi điểm gọi cũ vẫn trỏ đúng một chỗ.
from hangdoi import (                                          # noqa: E402
    IMG_QUEUE, VID_QUEUE, JOBS, DA_HUY, HUY_LOCK, DUNG_RIENG, TAY_SF,
    CHO_RIENG, CR_LOCK as _CR_LOCK, _HOAN,
    TRAN_MAY_TU_GOM, xep as _xep, lay as _lay, y_trong_hang as _y_trong_hang,
    vet_hang, dat_job as _dat_job, bi_huy as _bi_huy, uu_tien as _uu_tien,
    thu_tu_shot, thu_tu_hang, dung_gen, tang_dung_gen, bo_co_huy, VET, vet_don)
import hangdoi                                                 # noqa: E402

# SỔ LỖI RUNTIME (2026-08-14) — ghi lỗi nặng ra .grokpipe/runtime-bugs/ để AI đọc
# lại được sau khi board restart. Import phải CHỊU ĐƯỢC THIẾU loguru: board vẫn
# phải chạy trên máy chưa cài requirements-runtime.txt, chỉ mất phần ghi sổ.
try:                                                           # noqa: E402
    from jobs.runtime_service import (                         # noqa: E402
        report_runtime_bug, runtime_bug_diagnostics,
        start_runtime_bug_service, stop_runtime_bug_service)
except Exception as _e:                                        # noqa: BLE001,E402
    _BUG_IMPORT_ERROR = str(_e)[:120]

    def report_runtime_bug(signal) -> bool:                    # type: ignore[misc]
        return False

    def runtime_bug_diagnostics() -> dict:                     # type: ignore[misc]
        return {"bug_bridge": {"mode": "journal-only", "pending": 0,
                               "last_sync_at": None, "last_error": "",
                               "created": 0, "updated": 0}}

    def start_runtime_bug_service(*_a, **_k):                  # type: ignore[misc]
        return None

    def stop_runtime_bug_service() -> None:                    # type: ignore[misc]
        return None

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BOARD_LOCK = threading.RLock()      # nhiều thợ cùng ghi sf-board.json
_LOG = logging.getLogger("sfboard")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")

_JOB_MODE = "legacy"
_JOB_SHADOW = None
_JOB_PRODUCER = None
_JOB_ADAPTER = None
_JOB_ACCOUNTS = None
_JOB_REPOSITORY = None
_JOB_RUNTIME = None
_JOB_EXECUTOR_ADAPTER = None
_LIVE_WORKERS = {}
_LIVE_WORKERS_LOCK = threading.Lock()
_LIVE_STOP_EVENT = threading.Event()
_LIVE_CHROME_RELAUNCH_LOCK = threading.Lock()
_LIVE_CHROME_RELAUNCH_AFTER = {}
_LIVE_CHROME_RELAUNCH_COOLDOWN = 30.0


def _live_cleanup_empty_video_reservations():
    """Dọn placeholder version 0 byte còn lại sau crash; giữ mọi file có dữ liệu."""
    folder = getattr(BOARD, "vversions", "")
    if not folder or not os.path.isdir(folder):
        return 0
    removed = 0
    for entry in os.scandir(folder):
        if (not entry.is_file(follow_symlinks=False)
                or not re.match(r"^.+_v\d+\.mp4$", entry.name, re.IGNORECASE)):
            continue
        try:
            if entry.stat(follow_symlinks=False).st_size == 0:
                os.remove(entry.path)
                removed += 1
        except OSError:
            continue
    if removed:
        _LOG.warning("đã dọn %d placeholder video 0 byte sau crash", removed)
    return removed
_RESULT_APPLY_LOCK = threading.RLock()
# Lịch theo execution_id. Ở Phase 4 nó CHỈ QUAN SÁT: `PriorityQueue` legacy vẫn
# là thứ đưa việc tới thợ. Giá trị dùng được ngay là quan hệ "thành viên ⇢ lô
# vật lý" (xem `_lo_chua`) và số liệu lease trong `/api/chan-doan`.
_JOB_SCHEDULER = None


class LifecycleStartupError(RuntimeError):
    pass


def _classify_live_exception(exc, phase):
    """Phân loại ở đúng phase; sau submit luôn fail-safe UNKNOWN_OUTCOME."""
    from jobs.errors import ErrorClass, ErrorFact
    from jobs.models import AttemptPhase
    from jobs.live_budget import BudgetConfigurationError, BudgetExhausted
    from live_executor import LiveValidationError

    message = str(exc).strip() or type(exc).__name__
    if phase in {
        AttemptPhase.SUBMITTED,
        AttemptPhase.WAITING_PROVIDER,
        AttemptPhase.DOWNLOADING,
        AttemptPhase.SAVING,
    }:
        error_class = ErrorClass.UNKNOWN_OUTCOME
    elif isinstance(exc, LiveValidationError) or _loi_du_lieu(exc):
        error_class = ErrorClass.VALIDATION
    elif isinstance(exc, (BudgetConfigurationError, BudgetExhausted)):
        error_class = ErrorClass.PERMANENT
    elif _is_quota_error(exc):
        error_class = ErrorClass.QUOTA_RATE_LIMIT
    elif _is_dead_session_error(exc):
        _release_tl()
        error_class = ErrorClass.SESSION_TRANSIENT
    else:
        error_class = ErrorClass.PROVIDER_TRANSIENT
    return ErrorFact(error_class, message, phase)


def _lifecycle_db_path():
    project_dir = getattr(BOARD, "dir", None)
    if not project_dir:
        project_dir = os.path.dirname(os.path.abspath(BOARD.path))
    return os.path.join(project_dir, ".grokpipe", "job-lifecycle.sqlite3")


def _make_lifecycle_repository(path):
    from jobs.sqlite_store import SQLiteLifecycleRepository
    return SQLiteLifecycleRepository(path)


def _shutdown_job_lifecycle():
    global _JOB_REPOSITORY, _JOB_RUNTIME, _JOB_EXECUTOR_ADAPTER
    global _JOB_ADAPTER, _JOB_PRODUCER, _JOB_SCHEDULER, _JOB_ACCOUNTS
    # Chặn supervisor đẻ thêm worker, đánh thức worker idle rồi đợi chúng rời
    # vòng lặp TRƯỚC KHI xoá runtime/repository. Nếu làm ngược, worker thức thêm
    # một nhịp sau Ctrl-C sẽ gọi vào `_JOB_RUNTIME = None`; Playwright/Node đang
    # nối CDP cũng bị rút pipe giữa chừng và in EPIPE.
    _LIVE_STOP_EVENT.set()
    deadline = time.monotonic() + 5.0
    with _LIVE_WORKERS_LOCK:
        workers = tuple(_LIVE_WORKERS.items())
    current = threading.current_thread()
    for _key, thread in workers:
        if thread is current or not thread.is_alive():
            continue
        thread.join(max(0.0, deadline - time.monotonic()))
    with _LIVE_WORKERS_LOCK:
        for key, thread in tuple(_LIVE_WORKERS.items()):
            if not thread.is_alive():
                _LIVE_WORKERS.pop(key, None)
    repository = _JOB_REPOSITORY
    _JOB_REPOSITORY = None
    _JOB_RUNTIME = None
    _JOB_EXECUTOR_ADAPTER = None
    _JOB_ADAPTER = None
    _JOB_PRODUCER = None
    _JOB_SCHEDULER = None
    _JOB_ACCOUNTS = None
    if repository is not None:
        try:
            repository.close()
        except Exception:                   # noqa: BLE001
            pass


def _sync_runtime_accounts():
    if _JOB_RUNTIME is None:
        return
    with ACC_LOCK:
        accounts = [dict(account) for account in ACCOUNTS]
    has_enabled_video = any(
        account.get("kind") == "vid" and account.get("enabled")
        for account in accounts
    )
    known = set()
    for account in accounts:
        account_id = str(account.get("port") or "").strip()
        if not account_id:
            continue
        known.add(account_id)
        _JOB_RUNTIME.accounts.register(
            account_id,
            allow_video=(
                account.get("kind") == "vid"
                or (account.get("kind") == "img" and not has_enabled_video)
            ),
            max_slots=max(1, int(account.get("tabs") or 1)),
        )
        _JOB_RUNTIME.accounts.set_enabled(
            account_id, bool(account.get("enabled")))
    for account_id in set(_JOB_RUNTIME.accounts.accounts()) - known:
        _JOB_RUNTIME.accounts.forget(account_id)


def _job_shadow_diagnostics() -> dict:
    if _JOB_SHADOW is None:
        return {
            "mode": _JOB_MODE,
            "observed_writes": 0,
            "tracked_jobs": 0,
            "mismatches": 0,
            "recent_mismatches": [],
        }
    return _JOB_SHADOW.diagnostics()


def _lich_diagnostics() -> dict:
    if _JOB_SCHEDULER is None:
        return {"executions": 0, "theo_trang_thai": {}}
    try:
        return _JOB_SCHEDULER.diagnostics()
    except Exception:                       # noqa: BLE001
        return {"executions": 0, "theo_trang_thai": {}}


def _runtime_queue_snapshot() -> dict:
    if _JOB_MODE != "authoritative" or _JOB_SCHEDULER is None:
        return {
            "anh": thu_tu_hang(IMG_QUEUE),
            "video": thu_tu_hang(VID_QUEUE),
        }
    from jobs.models import ExecutionState, JobKind

    active = tuple(
        execution for execution in _JOB_SCHEDULER.active_executions()
        if execution.state in {ExecutionState.READY, ExecutionState.WAITING}
    )
    return {
        "anh": [execution.queue_ident for execution in active
                if execution.kind is JobKind.IMAGE],
        "video": [execution.queue_ident for execution in active
                  if execution.kind is JobKind.VIDEO],
    }


def _runtime_lifecycle_snapshot() -> dict:
    """DTO chỉ-đọc cho UI mới; không dựng lifecycle từ projection `JOBS`."""
    if (_JOB_MODE != "authoritative" or _JOB_RUNTIME is None
            or _JOB_REPOSITORY is None):
        return {
            "source": "legacy",
            "mode": _JOB_MODE,
            "jobs": [],
            "executions": [],
            "attempts": [],
        }

    # Lifecycle giữ toàn bộ lịch sử, còn `JOBS` chỉ là projection đang được UI
    # hiển thị. Clear chỉ bỏ projection này; không được xoá fact bền vững.
    # Gửi danh sách terminal đã bị ẩn để client không dựng chúng sống lại ở
    # nhịp poll kế tiếp.
    with JOBS.shadow_order_lock:
        projected_job_ids = set()
        for value in tuple(JOBS.values()):
            if not isinstance(value, dict):
                continue
            raw_ids = value.get("job_ids") or (
                [value.get("job_id")] if value.get("job_id") else [])
            projected_job_ids.update(str(raw) for raw in raw_ids if raw)

    jobs = []
    hidden_terminal_job_ids = []
    for job in _JOB_REPOSITORY.all_jobs():
        if job.state.is_terminal and str(job.job_id) not in projected_job_ids:
            hidden_terminal_job_ids.append(str(job.job_id))
        jobs.append({
            "job_id": str(job.job_id),
            "asset_id": str(job.asset_id),
            "kind": job.kind.value,
            "origin": job.origin.value,
            "state": job.state.value,
            "version": job.version,
            "batch_id": str(job.batch_id) if job.batch_id else None,
            "rerun_of": str(job.rerun_of) if job.rerun_of else None,
            "copy_index": job.copy_index,
            "replace_current": job.replace_current,
            "forced_account_id": job.forced_account_id,
            "allow_account_fallback": job.allow_account_fallback,
        })

    executions = []
    attempts = []
    from jobs.models import ExecutionId
    for execution in _JOB_REPOSITORY.all_execution_records():
        executions.append({
            "execution_id": execution.execution_id,
            "kind": execution.kind,
            "state": execution.state,
            "queue_ident": execution.queue_ident,
            "member_job_ids": list(execution.member_keys),
            "priority": execution.priority,
            "not_before": execution.not_before,
            "manual": execution.manual,
            "forced_account": execution.forced_account,
            "version": execution.version,
            "lease_id": execution.lease_id,
            "lease_expires_at": execution.lease_expires_at,
        })
        for attempt in _JOB_REPOSITORY.attempts_for_execution(
                ExecutionId.parse(execution.execution_id)):
            attempts.append({
                "attempt_id": str(attempt.attempt_id),
                "execution_id": str(attempt.execution_id),
                "number": attempt.number,
                "account_id": attempt.account_id,
                "lease_id": attempt.lease_id,
                "phase": attempt.phase.value,
                "consumes_credit": attempt.consumes_credit.value,
                "submitted_at": (
                    attempt.submitted_at.isoformat()
                    if attempt.submitted_at else None),
                "finished_at": (
                    attempt.finished_at.isoformat()
                    if attempt.finished_at else None),
                "outcome": attempt.outcome.value if attempt.outcome else None,
            })
    return {
        "source": "runtime",
        "mode": _JOB_MODE,
        "jobs": jobs,
        "hidden_terminal_job_ids": hidden_terminal_job_ids,
        "executions": executions,
        "attempts": attempts,
    }


def _job_state_for_asset(asset_id):
    """Trạng thái hiện tại cho producer; runtime thắng projection legacy."""
    if (_JOB_MODE != "authoritative" or _JOB_REPOSITORY is None):
        return (JOBS.get(str(asset_id)) or {}).get("state")
    jobs = tuple(
        job for job in _JOB_REPOSITORY.all_jobs()
        if str(job.asset_id) == str(asset_id)
    )
    if not jobs:
        return None
    latest = jobs[-1]
    marker = latest.batch_id
    current = tuple(
        job for job in jobs
        if ((marker is not None and job.batch_id == marker)
            or (marker is None and job.job_id == latest.job_id))
    )
    states = {job.state.value for job in current}
    if "running" in states:
        return "running"
    if states & {"created", "queued", "retry_wait"}:
        return "queued"
    if states == {"completed"}:
        return "done"
    return "error"


def _job_is_active(asset_id):
    return _job_state_for_asset(asset_id) in {"running", "queued"}


def _job_invariant_diagnostics(now=None) -> dict:
    """So snapshot queue/scheduler/UI và chỉ trả báo cáo, không tự sửa."""
    try:
        if _JOB_SCHEDULER is None:
            raise RuntimeError("scheduler chưa khởi tạo")
        from jobs.monitor import InvariantMonitor

        timestamp = time.time() if now is None else float(now)
        schedule = _JOB_SCHEDULER.invariant_snapshot(timestamp)
        # Retry chưa tới `not_before` đang nằm ở transport timer chứ chưa ở
        # PriorityQueue. Coi nó là transport-wait để monitor không báo mất việc
        # giả, đồng thời dùng nó che nhãn `running · thử lại sau` hợp lệ.
        waiting = tuple(schedule["waiting_idents"])
        if _JOB_MODE == "authoritative":
            # Durable scheduler CHÍNH LÀ transport; queue RAM legacy phải rỗng.
            queue_idents = set(schedule["scheduled_idents"] + waiting)
        else:
            queue_idents = _y_trong_hang(IMG_QUEUE) | _y_trong_hang(VID_QUEUE)
            with _CR_LOCK:
                queue_idents.update(
                    ident for idents in CHO_RIENG.values()
                    for ident in tuple(idents)
                )
            queue_idents.update(waiting)
        with JOBS.shadow_order_lock:
            labels = {
                str(key): str(value.get("state") or "")
                for key, value in tuple(JOBS.items())
                if isinstance(value, dict)
            }
        monitor = InvariantMonitor()
        findings = monitor.check(
            sorted(queue_idents),
            schedule["scheduled_idents"] + waiting,
            labels,
            schedule["leased_idents"] + waiting,
        )
        payload = monitor.summary(findings)
        payload["findings"] = [
            {
                "ma": finding.code,
                "muc": finding.severity.value,
                "doi_tuong": finding.subject,
                "chi_tiet": finding.detail,
            }
            for finding in findings[:20]
        ]
        return payload
    except Exception as exc:                # noqa: BLE001
        return {
            "tong": 1,
            "nang_nhat": "error",
            "theo_ma": {"monitor.error": 1},
            "findings": [{
                "ma": "monitor.error",
                "muc": "error",
                "doi_tuong": "lifecycle",
                "chi_tiet": f"không đọc được snapshot: {type(exc).__name__}",
            }],
        }


def _legacy_enqueue_private_image(port, ident, manual, _action_key):
    del manual
    port = int(port)
    with _CR_LOCK:
        private_queue = CHO_RIENG.setdefault(port, [])
        private_queue.append(ident)
        private_queue.sort(key=_uu_tien)


def _make_legacy_adapter(projection=None, producer=None):
    from jobs.compat import LegacyEnqueueAdapter

    return LegacyEnqueueAdapter(
        set_job_state=lambda ident, state, _action_key: _dat_job(
            ident, dict(state)
        ),
        enqueue_image=lambda ident, manual, _action_key: _xep(
            IMG_QUEUE, ("img", ident, 0, manual)
        ),
        enqueue_video=lambda ident, manual, _action_key: _xep(
            VID_QUEUE, ("vid", ident, 0, manual)
        ),
        enqueue_private_image=_legacy_enqueue_private_image,
        bind_projection=(
            projection.bind if projection else lambda _key, _ids: None
        ),
        mark_delivered=(
            producer.mark_delivered if producer else lambda _key: None
        ),
    )


def _make_scheduler():
    try:
        from jobs.scheduler import Scheduler
        return Scheduler()
    except Exception as exc:                # noqa: BLE001
        _LOG.warning("không dựng được lịch execution (%s)", type(exc).__name__)
        return None


def _make_accounts():
    """Sổ tài khoản: capability · sức khoẻ · ràng buộc ép.

    Ở Phase 5 nó CHƯA chọn tài khoản thay `_pool` — thứ dùng ngay là ràng buộc
    ÉP, để đường xếp-lại-sau-lỗi trả việc về đúng cổng thay vì thả vào hàng
    chung (chat sống trong profile của đúng máy đã mở nó)."""
    try:
        from jobs.accounts import AccountAllocator
        return AccountAllocator()
    except Exception as exc:                # noqa: BLE001
        _LOG.warning("không dựng được sổ tài khoản (%s)", type(exc).__name__)
        return None


def _init_job_shadow(mode=None):
    global _JOB_MODE, _JOB_SHADOW, _JOB_PRODUCER, _JOB_ADAPTER
    global _JOB_SCHEDULER, _JOB_ACCOUNTS, _JOB_REPOSITORY, _JOB_RUNTIME
    global _JOB_EXECUTOR_ADAPTER
    selected = str(
        mode or os.environ.get("GROKPIPE_JOB_MODE", "authoritative")
    ).strip().lower()
    if (_JOB_MODE == "authoritative" and selected != "authoritative"
            and _JOB_RUNTIME is not None
            and _JOB_RUNTIME.scheduler.active_executions()):
        raise LifecycleStartupError(
            "không rollback khi còn execution authoritative active")
    _shutdown_job_lifecycle()
    hangdoi.gan_shadow_observer(None)
    _JOB_SHADOW = None
    _JOB_PRODUCER = None
    _JOB_MODE = "legacy"
    _JOB_ADAPTER = _make_legacy_adapter()
    # Lịch dựng ở CẢ HAI mode: nó không cầm quyền gì, chỉ ghi lại việc nào đang
    # chờ để `/api/huy-viec` tra ra lô vật lý và để board có số liệu.
    _JOB_SCHEDULER = _make_scheduler()
    _JOB_ACCOUNTS = _make_accounts()
    if selected == "authoritative":
        _live_cleanup_empty_video_reservations()
        repository = None
        try:
            from jobs.executor_adapter import LegacyExecutorAdapter
            from jobs.runtime import LifecycleRuntime

            repository = _make_lifecycle_repository(_lifecycle_db_path())
            runtime = LifecycleRuntime(repository)
            runtime.recover(now=time.time(), event_id=uuid.uuid4())
            executor_adapter = LegacyExecutorAdapter(
                runtime, classify_exception=_classify_live_exception)
        except Exception as exc:
            if repository is not None:
                try:
                    repository.close()
                except Exception:           # noqa: BLE001
                    pass
            _JOB_MODE = "legacy"
            _JOB_REPOSITORY = None
            _JOB_RUNTIME = None
            _JOB_EXECUTOR_ADAPTER = None
            raise LifecycleStartupError(
                f"không khởi tạo được authoritative lifecycle: "
                f"{type(exc).__name__}"
            ) from exc
        _JOB_MODE = "authoritative"
        _JOB_REPOSITORY = repository
        _JOB_RUNTIME = runtime
        _JOB_EXECUTOR_ADAPTER = executor_adapter
        _JOB_PRODUCER = runtime.producer
        _JOB_SCHEDULER = runtime.scheduler
        _JOB_ACCOUNTS = runtime.accounts
        _sync_runtime_accounts()
        _restore_runtime_projection()
        _LIVE_STOP_EVENT.clear()
        return runtime

    if selected != "shadow":
        if selected != "legacy":
            _LOG.warning(
                "job mode %r chưa được Phase 2 hỗ trợ — giữ legacy",
                selected,
            )
        return None

    try:
        from jobs.manager import JobManager
        from jobs.models import JobKind
        from jobs.producer import ProducerService
        from jobs.projection import LegacyShadowProjection
        from jobs.store import MemoryJobStore

        def kind_of(legacy_key):
            if legacy_key.startswith("LO:"):
                return JobKind.IMAGE
            if _loai_viec(legacy_key) == "vid":
                return JobKind.VIDEO
            return JobKind.IMAGE

        def log_mismatch(item):
            _LOG.warning(
                "shadow lifecycle lệch %s: %s → %s (%s)",
                item.legacy_key,
                item.current_state.value,
                item.target_state.value,
                item.reason_code,
            )

        store = MemoryJobStore()
        manager = JobManager(store)
        projection = LegacyShadowProjection(
            manager,
            kind_of,
            log_mismatch,
        )
        producer = ProducerService(store)
        adapter = _make_legacy_adapter(projection, producer)
        hangdoi.gan_shadow_observer(projection.observe)
    except Exception as exc:
        hangdoi.gan_shadow_observer(None)
        _JOB_SHADOW = None
        _JOB_PRODUCER = None
        _JOB_MODE = "legacy"
        _JOB_ADAPTER = _make_legacy_adapter()
        _LOG.warning(
            "không khởi tạo được job shadow (%s) — giữ legacy",
            type(exc).__name__,
        )
        return None

    _JOB_MODE = "shadow"
    _JOB_SHADOW = projection
    _JOB_PRODUCER = producer
    _JOB_ADAPTER = adapter
    return projection


def _request_idempotency_key(handler, query, raw):
    header = (handler.headers.get("Idempotency-Key") or "").strip()
    if header:
        return header
    query_key = (query.get("idempotency_key", [""])[0] or "").strip()
    if query_key:
        return query_key
    if raw:
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        if isinstance(body, dict):
            return str(body.get("idempotency_key") or "").strip() or None
    return None


def _dang_ky_lich(plan):
    """Ghi mỗi action đã giao thành một execution trong lịch.

    Fail-open: lịch mới là bản quan sát, hỏng nó KHÔNG được làm hỏng việc giao
    xuống hàng đợi legacy."""
    if _JOB_SCHEDULER is None or plan is None:
        return
    try:
        from jobs.models import JobKind
        for action in plan.actions:
            _JOB_SCHEDULER.schedule(
                kind=JobKind.IMAGE if action.queue_kind == "img" else JobKind.VIDEO,
                queue_ident=action.queue_ident,
                member_keys=tuple(action.state_idents or action.legacy_keys),
                priority=_uu_tien(action.queue_ident),
            )
            # RÀNG BUỘC ÉP đi theo việc, không theo lần chạy.
            if action.forced_account_id and _JOB_ACCOUNTS is not None:
                _JOB_ACCOUNTS.force(action.queue_ident, action.forced_account_id)
    except Exception as exc:                # noqa: BLE001
        _LOG.warning("không ghi được lịch execution (%s)", type(exc).__name__)


LEASE_TTL = 900.0       # giây: một lượt ảnh/video lâu nhất còn coi là đang sống


def _lich_nhan(kind, ident):
    """Thợ vừa nhấc ident này — gắn lease. Trả None nếu lịch chưa biết việc đó.

    Fail-open tuyệt đối: đây là tầng quan sát, không được chặn thợ."""
    if _JOB_SCHEDULER is None:
        return None
    try:
        from jobs.models import JobKind
        return _JOB_SCHEDULER.lease_ident(
            JobKind.IMAGE if kind == "img" else JobKind.VIDEO,
            ident, now=time.time(), ttl=LEASE_TTL)
    except Exception:                       # noqa: BLE001
        return None


def _lich_tra(lease, outcome="finished", not_before=0.0):
    """Đóng hoặc trả lease theo KẾT QUẢ THẬT của lượt.

    Retry không phải terminal: execution giữ nguyên identity và quay về READY
    với `not_before`. Đánh FINISHED rồi để timer xếp lén vào queue làm lịch mất
    dấu đúng lúc cần quan sát retry nhất.
    """
    if lease is None or _JOB_SCHEDULER is None:
        return
    try:
        if outcome == "retry":
            _JOB_SCHEDULER.release(
                lease.lease_id, not_before=float(not_before))
        else:
            _JOB_SCHEDULER.finish(lease.lease_id)
    except Exception:                       # noqa: BLE001
        pass


def _lich_huy_ident(kind, ident):
    """Kết thúc execution đang chờ khi timer bị stop/cancel/stale."""
    if _JOB_SCHEDULER is None:
        return
    try:
        from jobs.models import JobKind
        exe = _JOB_SCHEDULER.get_by_ident(
            ident, JobKind.IMAGE if kind == "img" else JobKind.VIDEO)
        if exe is not None:
            _JOB_SCHEDULER.cancel_execution(exe.execution_id)
    except Exception:                       # noqa: BLE001
        pass


def _authoritative_submit(request_or_batch, idempotency_key, plan_factory):
    if _JOB_RUNTIME is None:
        raise RuntimeError("authoritative lifecycle chưa khởi tạo")
    planned = []

    def capture_plan(result):
        plan = plan_factory(result)
        planned.append(plan)
        return plan

    result = _JOB_RUNTIME.submit(
        request_or_batch, idempotency_key, capture_plan)
    plan = planned[0]
    label_jobs = {}
    for action in plan.actions:
        state_idents = tuple(action.state_idents or action.legacy_keys)
        bindings = dict(action.member_bindings or ())
        for index, ident in enumerate(state_idents):
            bound = tuple(bindings.get(ident) or ())
            if not bound:
                bound = ((action.job_ids[index],)
                         if len(state_idents) == len(action.job_ids)
                         and index < len(action.job_ids)
                         else action.job_ids)
            label_jobs.setdefault(ident, []).extend(bound)
    for ident, bound in label_jobs.items():
        unique = tuple(dict.fromkeys(bound))
        payload = {"state": "queued", "msg": "chờ lịch bền vững"}
        if unique:
            payload["job_id"] = str(unique[0])
            payload["job_ids"] = [str(job_id) for job_id in unique]
        _dat_job(ident, payload)
    _runtime_project_jobs(tuple(
        job_id for bound in label_jobs.values() for job_id in bound
    ))
    return result


def _producer_submit(request_or_batch, idempotency_key, plan_factory):
    global _JOB_ADAPTER
    if _JOB_ADAPTER is None:
        _init_job_shadow(_JOB_MODE)
    if _JOB_MODE == "authoritative" and _JOB_RUNTIME is not None:
        return _authoritative_submit(
            request_or_batch, idempotency_key, plan_factory)
    if _JOB_MODE == "shadow" and _JOB_PRODUCER is not None:
        from jobs.producer import CreateBatchRequest

        result = (
            _JOB_PRODUCER.create_batch(request_or_batch, idempotency_key)
            if isinstance(request_or_batch, CreateBatchRequest)
            else _JOB_PRODUCER.create_job(request_or_batch, idempotency_key)
        )
        plan = plan_factory(result)
        _JOB_ADAPTER.deliver(result, plan)
        _dang_ky_lich(plan)
        return result
    plan = plan_factory(None)
    _JOB_ADAPTER.deliver_legacy(plan)
    _dang_ky_lich(plan)
    return None


def _run_authoritative_once(kind, execute, *, now=None, ttl=LEASE_TTL):
    """Lease và chạy đúng một attempt qua adapter; không chạm queue legacy."""
    if (_JOB_MODE != "authoritative" or _JOB_RUNTIME is None
            or _JOB_EXECUTOR_ADAPTER is None):
        raise RuntimeError("authoritative lifecycle chưa khởi tạo")
    _sync_runtime_accounts()
    timestamp = time.time() if now is None else float(now)
    lease = _JOB_RUNTIME.lease_next(
        kind, now=timestamp, ttl=float(ttl))
    if lease is None:
        return None
    _runtime_project_jobs(lease.member_job_ids)
    try:
        return _JOB_EXECUTOR_ADAPTER.run_once(lease, execute)
    finally:
        _runtime_project_jobs(lease.member_job_ids)


def _live_bind_lease(lease):
    """Gắn thread-local browser vào đúng account/slot mà runtime đã cấp."""
    endpoint = str(lease.account_id).strip()
    if not endpoint.startswith(("http://", "https://")):
        endpoint = f"http://localhost:{endpoint}"
    kind = "img" if lease.kind.value == "image" else "vid"
    changed = (
        getattr(_TL, "endpoint", None) != endpoint
        or getattr(_TL, "slot", None) != lease.account_slot
        or getattr(_TL, "kind", None) != kind
    )
    if changed:
        _release_tl()
    _TL.endpoint = endpoint
    _TL.slot = lease.account_slot
    _TL.kind = kind
    _TL.gen = CHROME_GEN["n"]


def _live_cancel_requested(lease):
    if _JOB_RUNTIME is None:
        return True
    from jobs.models import JobState
    return any(
        _JOB_RUNTIME.job(job_id).state is not JobState.RUNNING
        for job_id in lease.member_job_ids
    )


def _live_image_request(lease):
    from jobs.models import JobState
    from live_executor import (
        ImageAttemptItem, ImageAttemptRequest, LiveValidationError)

    if _JOB_RUNTIME is None:
        raise RuntimeError("authoritative runtime đã đóng")
    data = BOARD.read()
    items = []
    members = []
    attach, attach_ids, missing = [], [], []
    for job_id in lease.member_job_ids:
        job = _JOB_RUNTIME.job(job_id)
        if job.state is not JobState.RUNNING:
            continue
        asset_id = str(job.asset_id)
        sf = BOARD.get_sf(asset_id, data)
        prompt = ((sf or {}).get("prompt") or "").strip()
        if not sf or not prompt:
            missing.append(f"{asset_id}(thiếu prompt)")
            continue
        items.append(ImageAttemptItem(job_id, asset_id, prompt))
        members.append((asset_id, sf))
    internal_refs = {asset_id for asset_id, _sf in members}
    for asset_id, sf in members:
        # Khi portrait và FULL cùng một live execution, chúng được yêu cầu trong
        # đúng một message. Portrait là output nội bộ của message, không phải file
        # đầu vào đã tồn tại; đòi attach nó sẽ tự khoá cả lô trước submit.
        paths, absent, ref_ids = _sf_attachments(
            sf, skip_ids=internal_refs)
        if absent:
            missing.extend(f"{asset_id}:{ref}" for ref in absent)
        for path, ref_id in zip(paths, ref_ids):
            if path not in attach:
                attach.append(path)
                attach_ids.append(ref_id)
    if missing:
        raise LiveValidationError(
            "image attempt thiếu dữ liệu/ref: " + ", ".join(missing[:6]))
    if not items:
        raise LiveValidationError("image attempt không còn member đang chạy")

    master = _nhom_cua(items[0].asset_id, data) or ""
    root_only = all(
        _la_the_dia_diem(BOARD.get_sf(item.asset_id, data)
                         or {"id": item.asset_id})
        for item in items
    )
    if not root_only:
        blocked = _cong_master(master, data)
        if blocked:
            raise LiveValidationError(f"chưa chạy được: {blocked}")
    kept = set(_ha_ref_nhan_vat_phu(attach_ids, TRAN_REF))
    attachments = tuple(
        path for path, ref_id in zip(attach, attach_ids) if ref_id in kept)
    master_sf = BOARD.get_sf(master, data) if master else None
    common_rules = ((master_sf or {}).get("luatchung") or "").strip()
    return ImageAttemptRequest(
        tuple(items), attachments, common_rules,
        _dan_ma_doc() and not any(
            item.asset_id.startswith("REF_") for item in items),
        master,
    )


def _live_image_attempt(lease, emit_phase):
    """Một ChatGPT message; không ghi state/retry/JOBS."""
    from live_executor import ImageProviderResponse, run_image_attempt

    _live_bind_lease(lease)
    request = _live_image_request(lease)
    session = _session()
    context = {"meta": None}
    viec = [(item.asset_id, item.prompt) for item in request.items]
    port = int(str(lease.account_id).rsplit(":", 1)[-1] or 0)

    def provider(_request, *, on_submitted, on_waiting_provider):
        sources, chat_url, notes = session.generate_lo(
            viec,
            list(request.attachments),
            chat_url="",
            luat_chung=request.common_rules,
            dan_ma=request.stamp_codes,
            nen_dung=lambda: _live_cancel_requested(lease),
            on_submitted=on_submitted,
            on_waiting_provider=on_waiting_provider,
        )
        return ImageProviderResponse(
            tuple(sources), chat_url, dict(notes or {}))

    def downloader(response):
        meta = _pl_tai_ve(
            session, list(response.sources), viec,
            request.master_id or None, port, response.chat_url,
            dict(response.notes),
        )
        context["meta"] = meta
        if not meta:
            return ()
        folder = _pl_duong(int(meta["turn"]))
        return tuple(
            os.path.join(folder, image["ten"])
            for image in meta.get("anh", ())
        )

    def saver(item, source_path):
        with BOARD_LOCK:
            output_path = BOARD.next_version_path(
                item.asset_id, reserve=True)
        try:
            shutil.copy2(source_path, output_path)
        except OSError:
            _drop_reserved(output_path)
            raise
        meta = context.get("meta") or {}
        index = next(
            (i for i, candidate in enumerate(request.items)
             if candidate.job_id == item.job_id), 0)
        images = meta.get("anh") or []
        if index < len(images):
            images[index]["gan"] = item.asset_id
        BOARD.turn_log_ghi(os.path.basename(output_path), {
            "turn": int(meta.get("turn") or 0),
            "o": index + 1,
            "port": port,
            "at": meta.get("at") or "",
        })
        return output_path

    try:
        result = run_image_attempt(
            request, emit_phase, provider=provider,
            downloader=downloader, saver=saver)
        return result
    finally:
        meta = context.get("meta")
        if meta:
            if meta.get("so_anh") == len(request.items) \
                    and not str(meta.get("loi_text") or "").strip():
                meta["ly_do"] = (
                    f"live authoritative ghép đủ {len(request.items)} ảnh")
            else:
                meta["ly_do"] = (
                    f"live authoritative giữ lượt lệch "
                    f"{meta.get('so_anh', 0)}/{len(request.items)} để retry")
            _pl_ghi_meta(meta)
            _pl_don_bot()


def _live_grok_budget():
    from jobs.live_budget import (
        BudgetConfigurationError, PersistentSubmitBudget)

    raw_limit = os.environ.get("GROKPIPE_LIVE_GROK_LIMIT")
    try:
        limit = int(raw_limit or "")
    except ValueError:
        raise BudgetConfigurationError(
            "GROKPIPE_LIVE_GROK_LIMIT phải là số 1..20") from None
    if not 1 <= limit <= 20:
        raise BudgetConfigurationError(
            "GROKPIPE_LIVE_GROK_LIMIT phải nằm trong 1..20")
    scope = (os.environ.get("GROKPIPE_LIVE_GROK_SCOPE") or
             f"{_board_identity()}:live-canary")
    path = os.path.join(
        BOARD.dir, ".grokpipe", "live-grok-canary.json")
    return PersistentSubmitBudget(path, scope=scope, limit=limit)


def _live_grok_reserve():
    snapshot = _live_grok_budget().reserve()
    _LOG.warning(
        "Grok live canary: đã giữ submit %d/%d, còn %d",
        snapshot.reserved, snapshot.limit, snapshot.remaining)
    return snapshot


def _live_video_request(lease):
    from jobs.models import JobState
    from live_executor import LiveValidationError, VideoAttemptRequest

    if _JOB_RUNTIME is None:
        raise RuntimeError("authoritative runtime đã đóng")
    active = tuple(
        _JOB_RUNTIME.job(job_id) for job_id in lease.member_job_ids
        if _JOB_RUNTIME.job(job_id).state is JobState.RUNNING
    )
    if len(active) != 1:
        raise LiveValidationError(
            "mỗi video execution phải có đúng một member đang chạy")
    job = active[0]
    shot_id = str(job.asset_id)
    shot, _scene = BOARD.get_shot(shot_id)
    prompt = ((shot or {}).get("prompt") or "").strip()
    start_frame = BOARD.find_file((shot or {}).get("sf") or "")
    if not shot or not prompt:
        raise LiveValidationError(f"video {shot_id} chưa có prompt")
    if not start_frame:
        raise LiveValidationError(
            f"Start frame {(shot or {}).get('sf') or ''} chưa có ảnh")
    with BOARD_LOCK:
        output_path = BOARD.next_vversion(shot_id)
        open(output_path, "ab").close()
    return VideoAttemptRequest(
        job.job_id, shot_id, prompt, start_frame,
        float(shot.get("dur") or 10), output_path)


def _live_video_attempt(lease, emit_phase):
    """Một Grok submit; reservation bền vững xảy ra sát trước click."""
    from live_executor import run_video_attempt

    _live_bind_lease(lease)
    request = _live_video_request(lease)
    reserved_paths = [request.output_path]

    def provider(_request, **callbacks):
        extras = []

        def next_extra():
            with BOARD_LOCK:
                path = BOARD.next_vversion(request.shot_id)
                open(path, "ab").close()
            extras.append(path)
            reserved_paths.append(path)
            return path

        ok = session.generate(
            request.prompt,
            request.start_frame,
            request.output_path,
            duration_s=request.duration_s,
            duong_them=next_extra,
            nen_dung=lambda: _live_cancel_requested(lease),
            **callbacks,
        )
        if not ok or not os.path.isfile(request.output_path) \
                or os.path.getsize(request.output_path) <= 0:
            return ()
        _dem_cong()
        return (request.output_path, *(
            path for path in extras
            if os.path.isfile(path) and os.path.getsize(path) > 0))

    try:
        session = _grok()
        return run_video_attempt(
            request, emit_phase, provider=provider,
            reserve_submit=_live_grok_reserve)
    finally:
        for path in reserved_paths:
            try:
                if os.path.isfile(path) and os.path.getsize(path) == 0:
                    os.remove(path)
            except OSError:
                pass


def _live_apply_outcome(lease, outcome):
    """Áp CommitVerdict lên current file; version đã được lưu từ trước."""
    if outcome is None or _JOB_RUNTIME is None:
        return
    from jobs.models import JobKind
    from jobs.results import CommitDecision

    for job_id, verdict in outcome.verdicts.items():
        if verdict.decision is not CommitDecision.ACCEPT or not verdict.outputs:
            continue
        job = _JOB_RUNTIME.job(job_id)
        asset_id = str(job.asset_id)
        output_path = verdict.outputs[0]
        with _RESULT_APPLY_LOCK:
            user_changed_at = _JOB_RUNTIME.results.last_user_mutation(asset_id)
            if (user_changed_at is not None
                    and user_changed_at >= lease.started_at):
                _LOG.info(
                    "giữ %s làm version: user đã đổi current sau khi attempt bắt đầu",
                    asset_id)
                continue
            with BOARD_LOCK:
                if job.kind is JobKind.IMAGE:
                    BOARD.set_current(asset_id, output_path)
                    _mark_picked(
                        asset_id, "picked", os.path.basename(output_path))
                    TAY_SF.discard(asset_id)
                else:
                    BOARD.set_video(asset_id, output_path)
                    _mark_picked(
                        asset_id, "vpicked", os.path.basename(output_path))


def _live_execute_once(kind):
    context = {}

    def execute(lease, emit_phase):
        context["lease"] = lease
        if lease.kind.value == "image":
            return _live_image_attempt(lease, emit_phase)
        return _live_video_attempt(lease, emit_phase)

    outcome = _run_authoritative_once(kind, execute)
    if outcome is not None and "lease" in context:
        _live_apply_outcome(context["lease"], outcome)
    return outcome


def _live_authoritative_worker(kind):
    """Worker trung lập account: runtime lease quyết account/slot từng attempt."""
    while _live_executor_enabled() and not _LIVE_STOP_EVENT.is_set():
        try:
            outcome = _live_execute_once(kind)
            if outcome is None and _LIVE_STOP_EVENT.wait(0.5):
                break
        except Exception as exc:                     # noqa: BLE001
            _LOG.exception("live authoritative worker lỗi ngoài attempt: %s", exc)
            report_runtime_bug({
                "reason_code": "LIVE_WORKER_CRASH",
                "category": "authoritative_worker",
                "severity": "CRITICAL",
                "job": {"kind": getattr(kind, "value", str(kind)),
                        "phase": "worker_loop", "job_id": ""},
                "runtime": {"mode": "authoritative-live"},
                "exc": exc,
            })
            if _LIVE_STOP_EVENT.wait(2):
                break
    _release_tl()


def _live_restore_enabled_chrome(*, now=None):
    """Mở lại Chrome enabled bị chết, có cooldown chống mở cửa sổ liên tục.

    Đây chỉ là browser health: không ghi job, không lease và không quyết retry.
    Runtime vẫn là authority duy nhất quyết định attempt kế tiếp.
    """
    timestamp = time.monotonic() if now is None else float(now)
    with ACC_LOCK:
        accounts = [dict(account) for account in ACCOUNTS
                    if account.get("enabled")]
    enabled_ports = {int(account.get("port") or 0) for account in accounts}
    with _LIVE_CHROME_RELAUNCH_LOCK:
        for port in tuple(_LIVE_CHROME_RELAUNCH_AFTER):
            if port not in enabled_ports:
                _LIVE_CHROME_RELAUNCH_AFTER.pop(port, None)
    for account in accounts:
        port = int(account.get("port") or 0)
        endpoint = _ep(account)
        if _endpoint_alive(endpoint):
            with _LIVE_CHROME_RELAUNCH_LOCK:
                _LIVE_CHROME_RELAUNCH_AFTER.pop(port, None)
            continue
        with _LIVE_CHROME_RELAUNCH_LOCK:
            if timestamp < _LIVE_CHROME_RELAUNCH_AFTER.get(port, 0.0):
                continue
            _LIVE_CHROME_RELAUNCH_AFTER[port] = (
                timestamp + _LIVE_CHROME_RELAUNCH_COOLDOWN)
        if _launch_chrome(account):
            _LOG.warning(
                "live supervisor mở lại Chrome %s (:%s) sau khi mất CDP",
                account.get("id") or "account", port)


def _live_authoritative_supervisor():
    from jobs.models import JobKind

    while _live_executor_enabled() and not _LIVE_STOP_EVENT.is_set():
        _live_restore_enabled_chrome()
        _sync_runtime_accounts()
        with ACC_LOCK:
            accounts = [dict(account) for account in ACCOUNTS
                        if account.get("enabled")]
        image_slots = sum(
            max(1, int(account.get("tabs") or 1))
            for account in accounts if account.get("kind") == "img")
        video_accounts = [
            account for account in accounts if account.get("kind") == "vid"]
        video_slots = sum(
            max(1, int(account.get("tabs") or 1))
            for account in (video_accounts or [
                account for account in accounts
                if account.get("kind") == "img"])
        )
        desired = {
            JobKind.IMAGE: image_slots,
            JobKind.VIDEO: video_slots,
        }
        with _LIVE_WORKERS_LOCK:
            if _LIVE_STOP_EVENT.is_set():
                break
            for key, thread in tuple(_LIVE_WORKERS.items()):
                if not thread.is_alive():
                    _LIVE_WORKERS.pop(key, None)
            for kind, count in desired.items():
                for slot in range(count):
                    key = (kind.value, slot)
                    if key in _LIVE_WORKERS:
                        continue
                    thread = threading.Thread(
                        target=_live_authoritative_worker,
                        args=(kind,), daemon=True,
                        name=f"live-{kind.value}-{slot}")
                    _LIVE_WORKERS[key] = thread
                    thread.start()
        if _LIVE_STOP_EVENT.wait(2):
            break


def _runtime_job_ids_for_label(label):
    if _JOB_RUNTIME is None:
        return ()
    from jobs.models import JobId

    if _JOB_MODE == "authoritative" and _JOB_REPOSITORY is not None:
        jobs = tuple(
            job for job in _JOB_REPOSITORY.all_jobs()
            if str(job.asset_id) == str(label)
        )
        if jobs:
            latest = jobs[-1]
            marker = latest.batch_id
            return tuple(
                job.job_id for job in jobs
                if ((marker is not None and job.batch_id == marker)
                    or (marker is None and job.job_id == latest.job_id))
            )

    payload = JOBS.get(label) or {}
    raw_ids = payload.get("job_ids") or (
        [payload.get("job_id")] if payload.get("job_id") else [])
    parsed = []
    for raw in raw_ids:
        try:
            parsed.append(JobId.parse(str(raw)))
        except (TypeError, ValueError):
            continue
    return tuple(dict.fromkeys(parsed))


def _runtime_labels_in_states(*states):
    if _JOB_MODE != "authoritative" or _JOB_REPOSITORY is None:
        wanted = set(states)
        return tuple(
            str(label) for label, value in tuple(JOBS.items())
            if isinstance(value, dict) and value.get("state") in wanted
        )
    wanted = set(states)
    return tuple(dict.fromkeys(
        str(job.asset_id) for job in _JOB_REPOSITORY.all_jobs()
        if job.state.value in wanted
    ))


def _runtime_cancel_label(label, *, now=None):
    if _JOB_MODE != "authoritative" or _JOB_RUNTIME is None:
        raise RuntimeError("authoritative lifecycle chưa khởi tạo")
    timestamp = time.time() if now is None else float(now)
    verdicts = []
    for job_id in _runtime_job_ids_for_label(label):
        verdicts.append(_JOB_RUNTIME.cancel(
            job_id, event_id=uuid.uuid4(), now=timestamp))
    return tuple(verdicts)


def _runtime_cancel_target(label="", job_id_text="", *, now=None):
    """Cancel theo durable `job_id`; asset label chỉ là fallback API cũ."""
    if _JOB_MODE != "authoritative" or _JOB_RUNTIME is None:
        raise RuntimeError("authoritative lifecycle chưa khởi tạo")
    if job_id_text:
        from jobs.models import JobId
        try:
            job_id = JobId.parse(str(job_id_text))
            job = _JOB_RUNTIME.job(job_id)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("job_id không tồn tại hoặc không hợp lệ") from exc
        timestamp = time.time() if now is None else float(now)
        verdict = _JOB_RUNTIME.cancel(
            job_id, event_id=uuid.uuid4(), now=timestamp)
        return str(job.asset_id), str(job_id), (verdict,)
    if not label:
        raise ValueError("thiếu job_id hoặc sf")
    return str(label), None, _runtime_cancel_label(label, now=now)


def _runtime_project_state(label, state):
    payload = dict(state)
    current = JOBS.get(label) or {}
    for key in ("job_id", "job_ids"):
        if key in current:
            payload[key] = current[key]
    _dat_job(label, payload)


def _runtime_project_jobs(job_ids):
    """Chiếu durable state ra nhãn cũ; tuyệt đối không quyết transition."""
    if _JOB_RUNTIME is None:
        return
    from jobs.models import JobState

    wanted = set(job_ids)
    with JOBS.shadow_order_lock:
        labels = tuple(
            (str(label), _runtime_job_ids_for_label(label))
            for label, value in tuple(JOBS.items())
            if isinstance(value, dict)
        )
    rank = {
        JobState.NEEDS_ATTENTION: 6,
        JobState.FAILED: 5,
        JobState.RUNNING: 4,
        JobState.RETRY_WAIT: 3,
        JobState.QUEUED: 2,
        JobState.CREATED: 1,
        JobState.CANCELLED: 0,
        JobState.COMPLETED: 0,
    }
    projection = {
        JobState.CREATED: {"state": "queued", "msg": "chờ lịch bền vững"},
        JobState.QUEUED: {"state": "queued", "msg": "chờ lịch bền vững"},
        JobState.RUNNING: {"state": "running", "msg": "đang chạy"},
        JobState.RETRY_WAIT: {"state": "queued", "msg": "lỗi → chờ thử lại"},
        JobState.NEEDS_ATTENTION: {
            "state": "error", "msg": "cần kiểm tra — không tự gửi lại",
        },
        JobState.COMPLETED: {"state": "done", "msg": "xong"},
        JobState.FAILED: {"state": "error", "msg": "thất bại"},
        JobState.CANCELLED: {"state": "error", "msg": "đã dừng"},
    }
    for label, bound_ids in labels:
        relevant = tuple(job_id for job_id in bound_ids if job_id in wanted)
        if not relevant:
            continue
        states = tuple(_JOB_RUNTIME.job(job_id).state for job_id in bound_ids)
        if states and all(state is JobState.COMPLETED for state in states):
            state = JobState.COMPLETED
        elif states and all(state is JobState.CANCELLED for state in states):
            state = JobState.CANCELLED
        else:
            state = max(states, key=lambda item: rank[item])
        _runtime_project_state(label, projection[state])


def _runtime_note_user_mutation(asset_id, *, now=None):
    """Đánh dấu thao tác tay để late provider result không đè current."""
    if _JOB_MODE != "authoritative" or _JOB_RUNTIME is None or not asset_id:
        return
    timestamp = time.time() if now is None else float(now)
    with _RESULT_APPLY_LOCK:
        _JOB_RUNTIME.note_user_mutation(str(asset_id), now=timestamp)


def _restore_runtime_projection():
    """Dựng lại nhãn UI từ identity bền vững sau startup recovery."""
    if _JOB_RUNTIME is None or _JOB_REPOSITORY is None:
        return
    by_asset = {}
    for job in _JOB_REPOSITORY.all_jobs():
        by_asset.setdefault(str(job.asset_id), []).append(job)
    projected = []
    for label, jobs in by_asset.items():
        latest = jobs[-1]
        marker = latest.batch_id
        current = tuple(
            job for job in jobs
            if ((marker is not None and job.batch_id == marker)
                or (marker is None and job.job_id == latest.job_id))
        )
        # Chỉ phục hồi việc còn cần xử lý. Một NEEDS_ATTENTION cũ đã có rerun
        # terminal mới hơn không được sống lại thành nhãn "chờ" sau restart.
        if current and all(job.state.is_terminal for job in current):
            continue
        unique = tuple(dict.fromkeys(job.job_id for job in current))
        if not unique:
            continue
        _dat_job(label, {
            "state": "queued",
            "msg": "khôi phục từ lịch bền vững",
            "job_id": str(unique[0]),
            "job_ids": [str(job_id) for job_id in unique],
        })
        projected.extend(unique)
    _runtime_project_jobs(tuple(projected))


def _runtime_cancel_labels(labels, *, message, now=None):
    labels = tuple(dict.fromkeys(str(label) for label in labels if label))
    before = {label: _job_state_for_asset(label) for label in labels}
    verdicts_by_label = {}
    for label in labels:
        verdicts_by_label[label] = _runtime_cancel_label(label, now=now)
    cancelled = []
    if _JOB_RUNTIME is not None:
        for label in labels:
            accepted = any(
                verdict.accepted for verdict in verdicts_by_label[label])
            if accepted:
                _runtime_project_state(
                    label, {"state": "error", "msg": message})
                cancelled.append(label)
    return tuple(cancelled), before


def _board_identity() -> str:
    """Khoá phân biệt DỰ ÁN, để scope của intent không đụng nhau giữa hai phim.

    Hai board khác nhau có thể có cùng SF id (`SF-S1-01` ở đâu cũng có), nên
    fingerprint scope phải mang theo đường dẫn board — nếu không thì dedupe của
    phim này chặn nhầm việc của phim kia khi chạy nhiều board một máy."""
    try:
        return os.path.abspath(getattr(BOARD, "path", "") or "")
    except Exception:
        return ""


def _yeu_cau_anh(sf_id, scope, *, ep=0):
    """Một CreateJobRequest ảnh do user bấm tay."""
    from jobs.models import AssetId, JobKind, JobOrigin
    from jobs.producer import CreateJobRequest

    return CreateJobRequest(
        AssetId(sf_id),
        JobKind.IMAGE,
        JobOrigin.MANUAL,
        request_scope=f"{_board_identity()}:{scope}",
        manual=True,
        replace_current=True,
        forced_account_id=str(ep) if ep else None,
    )


def _yeu_cau_video(shot_id, scope):
    from jobs.models import AssetId, JobKind, JobOrigin
    from jobs.producer import CreateJobRequest

    return CreateJobRequest(
        AssetId(shot_id),
        JobKind.VIDEO,
        JobOrigin.MANUAL,
        request_scope=f"{_board_identity()}:{scope}",
        manual=True,
        replace_current=True,
    )


def _tk_bi_ep(ident):
    """Cổng tài khoản mà việc này bị ghim vào — None nếu chạy hàng chung."""
    if _JOB_ACCOUNTS is None:
        return None
    try:
        return _JOB_ACCOUNTS.forced_account_for(ident)
    except Exception:                       # noqa: BLE001
        return None


def _lo_chua(sf):
    """Các ident lô ĐANG CHỜ có chứa SF này — hỏi đúng nơi biết sự thật.

    Thứ tự nguồn:

    1. **Scheduler** — nơi duy nhất giữ quan hệ "thành viên ⇢ execution".
    2. **HÀNG ĐỢI THẬT** (`IMG_QUEUE` và các hàng giao đích danh). Đây là chỗ
       biết việc gì đang chờ; `JOBS` chỉ là NHÃN để hiển thị.
    3. `JOBS` — giữ lại vì lô đang chờ khoá địa điểm có ghi khoá `LO:` ở đó.

    Bản cũ chỉ có nguồn 3, mà lúc lô vừa được xếp thì `JOBS` mới chỉ có nhãn
    của TỪNG THÀNH VIÊN — khoá `LO:a,b` chưa tồn tại. Nên bấm huỷ đúng lúc đó
    trả về "đã huỷ 0 lô" trong khi lô vẫn nằm nguyên trong hàng và vẫn chạy.
    """
    ra = []

    def _them(ident):
        if ident and ident.startswith("LO:") and ident not in ra:
            if sf in [x for x in ident[3:].split(",") if x]:
                ra.append(ident)

    if _JOB_SCHEDULER is not None:
        try:
            for exe in _JOB_SCHEDULER.executions_for_member(sf):
                _them(exe.queue_ident)
        except Exception:                   # noqa: BLE001
            pass                            # lịch hỏng không được chặn việc huỷ
    for ident in _y_trong_hang(IMG_QUEUE):
        _them(ident)
    with _CR_LOCK:
        for ds in CHO_RIENG.values():
            for ident in list(ds):
                _them(ident)
    for k, v in list(JOBS.items()):
        if v.get("state") == "queued":
            _them(k)
    return ra


def _da_nhan_key(khoa):
    """Key này đã được nhận trước đó chưa?

    Chốt nhãn `running/queued` là phép chặn bấm-hai-lần của thời legacy: nó
    dùng TRẠNG THÁI để đoán ý định. Khi request mang idempotency key thì ý định
    đã có định danh thật — bấm lại cùng key là CÙNG một ý định, phải trả về
    đúng job cũ thay vì báo 'đã nằm trong hàng chờ'. Ý định KHÁC mà mượn cùng
    key thì `create_*` ném `IdempotencyConflict` → 409, không lọt qua đây."""
    if (not khoa or _JOB_MODE not in ("shadow", "authoritative")
            or _JOB_PRODUCER is None):
        return False
    try:
        return _JOB_PRODUCER.store.get_intent(khoa) is not None
    except Exception:                       # noqa: BLE001
        return False


def _nhan_cho_video(them=0):
    """Nhãn 'chờ' của video — GIỮ NGUYÊN cách đếm của `_enqueue`.

    `_enqueue` đọc độ dài hàng TRƯỚC khi xếp, nên việc thứ k trong một loạt
    thấy `qsize()+k`. Plan được dựng trước khi giao nên `qsize()` ở đây cũng là
    số trước khi xếp — cộng thêm `them` là ra đúng con số cũ."""
    n = VID_QUEUE.qsize() + them
    return {"state": "queued",
            "msg": "chờ · sắp tới lượt" if n == 0 else f"chờ · {n} việc trước"}


def _job_ids_cua(result, chi_so):
    """JobId của các member theo vị trí — rỗng khi đang chạy mode legacy."""
    if result is None:
        return ()
    return tuple(result.jobs[i].job_id for i in chi_so if i < len(result.jobs))


def _producer_metadata(result):
    if result is None:
        return {
            "job_id": None,
            "job_ids": [],
            "batch_id": None,
            "replayed": False,
        }
    job_ids = [str(job.job_id) for job in result.jobs]
    return {
        "job_id": job_ids[0] if len(job_ids) == 1 else None,
        "job_ids": job_ids,
        "batch_id": str(result.batch.batch_id) if result.batch else None,
        "replayed": bool(result.replayed),
    }


# ---- SỔ LỖI CHO GIAO DIỆN ------------------------------------------------
# Mọi WARNING/ERROR chảy vào đây, để hộp 🐞 trên board đọc được mà không phải
# mở Terminal. Trước đây log chỉ ra stdout: user đóng cửa sổ chạy board là mất
# sạch dấu vết, mà đúng những lỗi cần nhìn (selector chết, ERR_QUIC, tab kẹt)
# lại chỉ nằm ở đó — job trên board chỉ hiện một dòng tóm tắt cụt.
LOI_SO: collections.deque = collections.deque(maxlen=800)
LOI_LOCK = threading.Lock()
_LOI_STT = [0]


class _ThuLoi(logging.Handler):
    """Gom cảnh báo/lỗi vào LOI_SO. Không bao giờ được ném lỗi ra ngoài — một
    handler hỏng làm hỏng luôn lời gọi log ở giữa vòng render."""

    def emit(self, rec: logging.LogRecord) -> None:
        try:
            with LOI_LOCK:
                _LOI_STT[0] += 1
                LOI_SO.append({
                    "n": _LOI_STT[0],
                    "luc": time.strftime("%H:%M:%S", time.localtime(rec.created)),
                    "muc": rec.levelname,
                    "nguon": rec.name,
                    "text": rec.getMessage()[:2000],
                })
        except Exception:
            pass


_thu = _ThuLoi()
_thu.setLevel(logging.WARNING)
logging.getLogger().addHandler(_thu)          # bắt cả log của executor grokpipe

# Mọi việc chuyển sang trạng thái LỖI đều chảy vào sổ, kể cả những nhánh không
# tự gọi log — xem `_Jobs` trong hangdoi.py.
JOBS.__class__.khi_loi = staticmethod(
    lambda ident, msg: _LOG.warning("việc %s LỖI: %s", ident, msg[:500]))


def _ten_tk(endpoint: str) -> str:
    """Tên đọc được của một cửa sổ: 'gpt-5' thay cho 'http://localhost:9226'.

    Log cũ in nguyên endpoint — đọc lướt không ra tài khoản nào, mà cổng thì
    phải nhẩm mới khớp được với bảng Tài khoản.
    """
    try:
        port = int((endpoint or ":0").rsplit(":", 1)[1])
    except Exception:
        return endpoint or "?"
    with ACC_LOCK:
        a = next((x for x in ACCOUNTS if x["port"] == port), None)
    if not a:
        return f":{port}"
    return f"{a['ten']} ({a['id']})" if a.get("ten") else a["id"]


def _nhan_tk() -> str:
    """'gpt-4 :9225' của luồng thợ đang chạy — rỗng nếu không ở trong luồng thợ."""
    ep = getattr(_TL, "endpoint", "") or ""
    if not ep:
        return ""
    try:
        port = int(ep.rsplit(":", 1)[1])
    except Exception:
        return ""
    with ACC_LOCK:
        a = next((x for x in ACCOUNTS if x["port"] == port), None)
    if not a:
        return f":{port}"
    # Có tên riêng thì hiện KÈM mã, không thay: user đọc tên để biết tài khoản
    # nào, còn mã là thứ khớp được với tên thư mục profile và log cũ.
    return (f"{a['ten']} · {a['id']} :{port}" if a.get("ten")
            else f"{a['id']} :{port}")


def _dan_nhan_tk(msg: str) -> str:
    """Gắn '[gpt-4 :9225]' vào đầu thông báo lỗi.

    Bốn cửa sổ Chrome đều cùng URL chatgpt.com, nên lỗi kiểu "Page crashed" hay
    "ô soạn aria-hidden" không chỉ ra nổi cửa sổ nào cần chữa. Nhãn này trả lời
    đúng câu đó. Bỏ qua khi lỗi đến từ luồng HTTP (không thuộc tài khoản nào) và
    khi nhãn đã có sẵn — tránh dán chồng lúc việc bị đặt lỗi nhiều lần.
    """
    nhan = _nhan_tk()
    if not nhan or msg.startswith("["):
        return msg
    return f"[{nhan}] {msg}"


JOBS.__class__.dan_nhan = staticmethod(_dan_nhan_tk)
# …và hàm trả nhãn tài khoản trần, để MỌI trạng thái (không chỉ lỗi) ghi được
# việc này đang chạy trên cửa sổ nào. Không có nó thì soi lại một job xong
# vẫn không biết tài khoản nào đã làm, mà đó là thứ quyết định đi chữa ở đâu.
JOBS.__class__.nhan_tk = staticmethod(_nhan_tk)

# Mỗi luồng thợ giữ Playwright + phiên RIÊNG của nó (sync_playwright không dùng chung
# được giữa các luồng, nhưng mỗi luồng có một instance riêng thì hoàn toàn hợp lệ).
_TL = threading.local()

DEAD: dict[str, str] = {}           # endpoint -> lý do (hết lượt / cửa sổ Chrome đã đóng)
DEAD_DEN: dict[str, float] = {}     # endpoint -> mốc epoch được phép chạy lại
_DEAD_LOCK = threading.Lock()


def _mark_dead(endpoint: str, reason: str, kind: str = "img", den: float = 0.0):
    pool = _pool(kind)
    with _DEAD_LOCK:
        DEAD[endpoint] = reason
        if den:
            # Giữ hẹn XA hơn: hai thợ cùng một cổng ngã liên tiếp thì cú sau
            # không được rút ngắn kỳ nghỉ cú trước vừa đặt.
            DEAD_DEN[endpoint] = max(den, DEAD_DEN.get(endpoint, 0.0))
        else:
            DEAD_DEN.pop(endpoint, None)
        alive = [e for e in pool if e not in DEAD]
    _LOG.warning("%s: %s — còn %d/%d tài khoản %s chạy được",
                 _ten_tk(endpoint), reason, len(alive), len(pool),
                 "Grok" if kind == "vid" else "ChatGPT")
    # KHÔNG CÒN NHÁNH "HẾT LƯỢT" Ở ĐÂY (bỏ 2026-08-14 cùng cơ chế nghỉ).
    # Tài khoản cạn lượt giờ đi chung đường với mọi lỗi khác: `_xoay_chrome()`
    # tắt nó và bật cái kế tiếp trong vòng ngay lập tức. Không còn "nghỉ tới
    # HH:MM", không còn "dự bị chờ bù người".


def _dang_nghi(endpoint: str) -> float:
    """Mốc epoch tài khoản này được chạy lại; 0 = không phải đang nghỉ có hẹn."""
    with _DEAD_LOCK:
        return DEAD_DEN.get(endpoint, 0.0) if DEAD.get(endpoint) else 0.0


# ───────── GIỮ ĐÚNG SỐ TÀI KHOẢN ẢNH CHẠY ĐỒNG THỜI ──────────────────────────
# User đặt một con số (mặc định 3): board luôn cố giữ ĐÚNG bấy nhiêu tài khoản
# ChatGPT đang chạy được. Thừa thì tắt bớt, thiếu thì bật thêm từ danh sách.
#
# Cái này khác "số tab": tab là nhiều việc song song TRONG một tài khoản (chung
# một hạn mức), còn đây là nhiều tài khoản (mỗi cái một hạn mức riêng).
#
# Điểm gặp nhau với cơ chế nghỉ: tài khoản bị ChatGPT chặn sẽ vào DEAD kèm giờ
# mở lại, tức không còn "chạy được" — supervisor thấy hụt số và tự bật một tài
# khoản khác thay chỗ. Tới giờ hết chặn nó hồi sinh, lúc đó có thể thành thừa và
# bị tắt bớt. Nhờ vậy số cửa sổ Chrome (và RAM) luôn ổn định.
SO_TK_PATH = os.path.expanduser("~/.grokpipe-so-tk.json")
SO_TK_MAC_DINH = 3

# Tài khoản do CHÍNH BOARD tắt vì thừa số mang cờ `auto_off` trong hồ sơ tài
# khoản. Cần bật lại thì bật đúng chúng, đừng đụng tài khoản user chủ động tắt.
# Cờ nằm trong ~/.grokpipe-accounts.json chứ không phải biến trong RAM: restart
# board là mất biến, và board sẽ lại đi bật nhầm tài khoản user để dành.


def _so_tk_doc() -> int:
    try:
        with open(SO_TK_PATH, encoding="utf-8") as f:
            return max(1, min(12, int(json.load(f).get("so") or SO_TK_MAC_DINH)))
    except Exception:
        return SO_TK_MAC_DINH


def _so_tk_ghi(n: int) -> int:
    n = max(1, min(12, int(n or SO_TK_MAC_DINH)))
    try:
        with open(SO_TK_PATH, "w", encoding="utf-8") as f:
            json.dump({"so": n}, f)
    except OSError as e:
        _LOG.warning("không ghi được số tài khoản: %s", e)
    return n


def _tk_dang_chay() -> list:
    """Tài khoản ảnh ĐANG CHẠY ĐƯỢC = đang bật và không bị chặn."""
    with ACC_LOCK:
        return [a for a in ACCOUNTS
                if a["kind"] == "img" and a["enabled"] and not DEAD.get(_ep(a))]


# Sổ đếm việc ĐANG CHẠY trên từng cửa sổ: endpoint -> số thợ đang làm.
#
# JOBS không trả lời được câu hỏi này: nhãn tài khoản chỉ được dán vào thông báo
# LỖI, còn việc đang chạy thì chỉ mang "[tk 2/3]" — không truy ra cổng nào. Mà
# đó đúng là câu hỏi phải trả lời trước khi đóng một cửa sổ.
BAN: dict[str, int] = {}
_BAN_LOCK = threading.Lock()


def _ban_vao(endpoint: str) -> None:
    with _BAN_LOCK:
        BAN[endpoint] = BAN.get(endpoint, 0) + 1


def _ban_ra(endpoint: str) -> None:
    with _BAN_LOCK:
        n = BAN.get(endpoint, 0) - 1
        if n > 0:
            BAN[endpoint] = n
        else:
            BAN.pop(endpoint, None)


def _dang_ban(endpoint: str) -> int:
    with _BAN_LOCK:
        return BAN.get(endpoint, 0)


def _giu_du_tai_khoan() -> None:
    """Giữ số tài khoản ảnh KHÔNG VƯỢT trần user đặt. Chỉ tắt bớt, không bật thêm.

    Con số là TRẦN, không phải mức phải đạt (user chốt 2026-08-13): chạy 1–2 tài
    khoản cũng được, miễn đừng quá trần. Vì vậy vòng này TUYỆT ĐỐI không tự bật
    thêm — user tắt tay một cửa sổ là có lý do (để dành, chưa đăng nhập, biết nó
    sắp hết lượt), board đi bật cái khác thế vào là cãi lại ý user.

    Ngoại lệ duy nhất nằm ở `_xoay_chrome()`: cửa sổ lỗi thì board TẮT nó và BẬT
    cái kế tiếp trong vòng — đổi danh tính, không đổi số lượng, nên trần vẫn giữ.
    """
    muon = _so_tk_doc()
    song = _tk_dang_chay()
    if len(song) <= muon:
        return
    # TẮT CÁI ĐANG RẢNH TRƯỚC — tắt tài khoản đang vẽ dở là giết luôn lượt đó.
    #
    # Bắt được 10:26:41 ngày 2026-08-14: vòng này tắt gpt-8 đúng lúc ChatGPT vừa
    # trả đủ 10/10 ảnh và board đang tải về. Chrome bị đóng giữa chừng nên cả 10
    # ảnh mất sạch ("Target page… has been closed"), lượt coi như đốt bỏ — trong
    # khi tắt một cửa sổ đang nằm không thì chẳng mất gì.
    #
    # Trong nhóm cùng trạng thái vẫn giữ luật cũ: tắt từ CUỐI danh sách lên, vì
    # tài khoản đầu thường là cái user dùng lâu nhất và đã đăng nhập chắc chắn.
    xep_tat = sorted(reversed(song), key=lambda a: _dang_ban(_ep(a)))
    for a in xep_tat[:len(song) - muon]:
        if _dang_ban(_ep(a)):
            _LOG.info("vượt trần %d tài khoản nhưng %s đang chạy việc — "
                      "để nó làm nốt, vòng sau tính lại.", muon, a["id"])
            continue
        with ACC_LOCK:
            a["enabled"] = False
            a["auto_off"] = True
        _kill_chrome(a["port"])
        _LOG.info("vượt trần %d tài khoản: TẮT bớt %s (:%s)", muon, a["id"], a["port"])
    _save_accounts()


def _alive_count(kind: str = "img") -> int:
    with _DEAD_LOCK:
        return len([e for e in _pool(kind) if e not in DEAD])


# ───────────────────────────── XOAY VÒNG CHROME ──────────────────────────────
# User chốt 2026-08-14: CỨ LỖI LÀ ĐỔI CHROME. Không phân biệt lỗi nặng nhẹ, không
# đếm số lần — việc được thử lại mãi tới khi ra ảnh, chỉ "Dừng tất cả" mới cắt.
#
# Lý do: hỏng ở khâu render gần như luôn là hỏng ở MỘT cửa sổ Chrome cụ thể
# (selector trượt vì giao diện A/B, CDP "sống nửa vời" — HTTP còn trả lời mà
# WebSocket đã treo, tab ngốn RAM tới mức renderer bị thu hồi). Cùng một prompt
# chạy sang cửa sổ khác thì ra ảnh ngay. Xoay vòng liên tục nên tự tìm ra cửa sổ
# nào đang vẽ ngon, thay vì đứng lại ở cái đầu tiên bị hỏng.
#
# Chrome bị tắt hẳn chứ không chỉ đánh dấu chết: profile nằm trên đĩa nên phiên
# đăng nhập không mất, mà tắt–mở là cách DUY NHẤT dọn được một CDP đã treo.
#
# XOAY THEO VÒNG TRÒN QUA CẢ DANH SÁCH (user chốt 2026-08-14, bỏ hẹn giờ nghỉ):
# tk 1 lỗi → sang 2, 2 lỗi → sang 3, 3 lỗi mà 4 đang chạy → nhảy sang 5, tới cuối
# danh sách thì quay về đầu. Mọi cửa sổ đều có lượt, không cửa sổ nào bị loại.
#
# SỐ CỬA SỔ MỞ CÙNG LÚC KHÔNG ĐỔI — tắt cái hỏng TRƯỚC rồi mới bật cái kế tiếp.
# Xoay vòng là đổi DANH TÍNH tài khoản đang chạy, không phải mở thêm cửa sổ; trần
# RAM user đặt (mục Tài khoản) vì thế vẫn nguyên.


def _ke_tiep_trong(ds: list, endpoint: str) -> dict | None:
    """Phần thuần của `_tk_ke_tiep` — KHÔNG tự lấy khoá, nhận sẵn danh sách.

    Tách ra để `_xoay_chrome()` chọn–tắt–bật trong CÙNG một khối `ACC_LOCK`.
    Chọn ngoài khoá rồi mới vào khoá để sửa là một cửa sổ đua: hai tài khoản
    KHÁC NHAU cùng ngã sẽ cùng nhìn thấy một "người kế tiếp", cùng tắt mình,
    mà chỉ một cái được bật — số cửa sổ đang chạy tụt dần sau mỗi cơn lỗi chùm.
    """
    if len(ds) < 2:
        return None
    i = next((k for k, a in enumerate(ds) if _ep(a) == endpoint), -1)
    for b in range(1, len(ds) + 1):
        a = ds[(i + b) % len(ds)]
        if _ep(a) == endpoint or a.get("enabled"):
            continue            # chính nó, hoặc đang chạy → nhường, đi tiếp
        # KHÔNG lọc theo "đang nghỉ vì hết lượt" nữa — user chốt bỏ hẳn cơ chế
        # nghỉ (2026-08-14). Tài khoản cạn lượt vẫn được vào vòng: nó lỗi lại
        # thì xoay tiếp, rẻ hơn nhiều so với treo nó ngoài vòng mấy tiếng đồng
        # hồ trong khi ChatGPT có thể mở lượt sớm hơn giờ nó nói.
        return a
    return None


def _tk_ke_tiep(endpoint: str, kind: str) -> dict | None:
    """Tài khoản kế tiếp trong vòng, tính từ `endpoint`, BỎ QUA cái đang chạy.

    Trả None khi mọi tài khoản khác đều đang chạy — lúc đó không bật thêm ai,
    việc cứ chảy sang các cửa sổ đang mở.
    """
    with ACC_LOCK:
        return _ke_tiep_trong([dict(a) for a in ACCOUNTS if a["kind"] == kind],
                              endpoint)


def _xoay_chrome(endpoint: str, kind: str, ly_do: str) -> None:
    """Tắt cửa sổ vừa lỗi, bật cửa sổ KẾ TIẾP trong vòng, đẩy việc sang đó.

    Không hẹn giờ nghỉ: tài khoản vừa lỗi được TẮT hẳn nên rơi khỏi `_pool()`
    và thợ của nó tự thoát. Đường về của nó là vòng xoay — cái sau lỗi thì tới
    lượt nó được bật lại. `auto_off` chỉ còn là dấu vết "board tắt, không phải
    user tắt" — hiện lên giao diện, không còn cơ chế nào đọc để quyết định.
    """
    port = int((endpoint or ":0").rsplit(":", 1)[1] or 0)
    # ⛔ KHÔNG XOAY KHI CỬA SỔ NÀY KHÔNG THUỘC LOẠI VIỆC ĐANG LỖI.
    #
    # `_pool("vid")` cho việc video chạy nhờ trên cửa sổ ChatGPT khi chưa bật
    # tài khoản Grok nào. Cửa sổ đó gần như chắc chắn lỗi ("Không nối được
    # Grok"), và bản cũ mang endpoint ChatGPT vào đây với kind="vid": danh sách
    # ứng viên chỉ gồm tài khoản Grok nên nó hoặc TẮT cửa sổ ChatGPT để bật một
    # cửa sổ Grok, hoặc — khi chỉ có một tài khoản Grok — rơi vào nhánh "cửa sổ
    # duy nhất" và `_kill_chrome(port)` chính cái cửa sổ ChatGPT đang vẽ ảnh dở.
    # Một việc video xếp nhầm giết cả lô ảnh, im lặng.
    # So theo CỔNG, không so chuỗi endpoint: `_ep()` dựng "http://localhost:<p>"
    # còn log/cấu hình chỗ khác hay dùng "127.0.0.1" — so chuỗi là chốt này im
    # lặng bỏ qua đúng lúc cần nó nhất.
    with ACC_LOCK:
        _loai = next((x.get("kind") for x in ACCOUNTS if int(x.get("port") or 0) == port), None)
    if _loai is not None and _loai != kind:
        _LOG.warning("%s là cửa sổ %s nhưng đang chạy việc %s (chạy nhờ) — KHÔNG "
                     "đóng/xoay cửa sổ này. Bật một tài khoản Grok để việc video "
                     "chạy đúng chỗ.", _ten_tk(endpoint), _loai, kind)
        return
    # CHỌN — TẮT — BẬT TRONG MỘT KHỐI KHOÁ, không tách ra ba nhịp.
    #
    # Hai chốt chống đua nằm cả ở đây:
    #  · cùng một tài khoản ngã nhiều lần (nhiều tab) → thợ sau thấy `enabled`
    #    đã tắt là biết có người xoay rồi, bỏ lượt. Không có chốt này thì board
    #    bật hai–ba cửa sổ thay cho một, vọt qua trần RAM, rồi
    #    `_giu_du_tai_khoan()` tắt bớt từ cuối danh sách và giết đúng tài khoản
    #    đang chạy tốt (bắt được 09:57:49 ngày 2026-08-14: gpt-3 ngã hai lần
    #    cùng giây → bật cả gpt-4 lẫn gpt-5 → gpt-10 đang vẽ dở bị tắt ngang).
    #  · hai tài khoản KHÁC NHAU cùng ngã → nếu chọn "người kế tiếp" ngoài khoá
    #    rồi mới vào khoá để sửa, cả hai cùng nhắm một người, cùng tắt mình, mà
    #    chỉ một cái được bật — số cửa sổ đang chạy tụt dần sau mỗi cơn lỗi chùm.
    with ACC_LOCK:
        cu = next((x for x in ACCOUNTS if _ep(x) == endpoint), None)
        if cu is not None and not cu.get("enabled"):
            _LOG.info("%s: tab khác đã xoay rồi, bỏ qua lượt này.",
                      _ten_tk(endpoint))
            return
        ke = _ke_tiep_trong([dict(a) for a in ACCOUNTS if a["kind"] == kind],
                            endpoint)
        if ke is not None:
            if cu:
                cu["enabled"] = False
                cu["auto_off"] = True
            moi = next((x for x in ACCOUNTS if _ep(x) == _ep(ke)), None)
            if moi:
                moi["enabled"] = True
                moi.pop("auto_off", None)
    if ke is None:
        # Cửa sổ duy nhất (hoặc mọi cái khác đang chạy): tắt–mở lại chính nó.
        # Tắt–mở vẫn có giá trị — đó là cách duy nhất dọn một CDP đã treo.
        with _DEAD_LOCK:
            if str(DEAD.get(endpoint, "")).startswith("đổi cửa sổ"):
                return          # thợ khác trên cùng cửa sổ vừa xoay xong
        _mark_dead(endpoint, f"đổi cửa sổ ({ly_do})", kind, time.time() + 20)
        try:
            _kill_chrome(port)
        except Exception as e:
            _LOG.warning("%s: không đóng được Chrome — %s", _ten_tk(endpoint), _loi_gon(e))
        if _alive_count(kind) == 0:
            with ACC_LOCK:
                a = next((dict(x) for x in ACCOUNTS if _ep(x) == endpoint), None)
            if a:
                _launch_chrome(a)
                with _DEAD_LOCK:
                    DEAD.pop(endpoint, None)
                    DEAD_DEN.pop(endpoint, None)
                _LOG.info("%s: không còn cửa sổ nào khác, mở lại để chạy tiếp.", _ten_tk(endpoint))
        else:
            _LOG.info("%s lỗi (%s) — mọi tài khoản khác đang bận, việc dồn "
                      "sang chúng.", _ten_tk(endpoint), ly_do)
        return

    # Tắt/bật đã làm xong trong khối khoá trên; còn lại là phần chậm (đóng–mở
    # Chrome, ghi đĩa) — cố ý để NGOÀI khoá, đừng giữ ACC_LOCK qua 5 giây chờ
    # cổng nhả, mọi luồng khác sẽ nghẽn theo.
    with _DEAD_LOCK:
        DEAD.pop(endpoint, None)        # tắt rồi thì không cần dấu chết nữa
        DEAD_DEN.pop(endpoint, None)
    try:
        _kill_chrome(port)
    except Exception as e:
        _LOG.warning("%s: không đóng được Chrome — %s", _ten_tk(endpoint), _loi_gon(e))
    if not _endpoint_alive(_ep(ke)):
        _launch_chrome(ke)
    _save_accounts()
    _LOG.warning("XOAY: %s lỗi (%s) → tắt, chuyển sang %s.",
                 _ten_tk(endpoint), ly_do, _ten_tk(_ep(ke)))


def _so_tab_theo_viec(a: dict, k: str) -> int:
    """Tài khoản này mở bao nhiêu tab cho loại việc `k`?

    SỐ TAB USER ĐẶT CHỈ ÁP CHO VIỆC CHÍNH CỦA TÀI KHOẢN (vá 2026-08-14).
    Khi chưa có tài khoản Grok nào bật, thợ ảnh KIÊM luôn video — bản cũ nhân
    số tab cho cả hai loại, nên đặt 2 tab lại thấy Chrome mở 4 tab: `cgslot0`,
    `cgslot1` của ChatGPT cộng `gpslot0`, `gpslot1` của Grok. Hai không gian tên
    khác nhau nên không dùng chung tab được, và RAM thì nhân đôi thật — đúng thứ
    đẩy máy tới "Aw, Snap!".

    Việc kiêm nhiệm là đường DỰ PHÒNG, cho đúng MỘT tab là đủ. Bật một tài khoản
    Grok riêng thì tài khoản ảnh hết kiêm nhiệm và số tab lại đúng bằng user đặt."""
    so_tab = max(1, min(MAX_TABS, int(a.get("tabs") or 1)))
    return so_tab if k == a.get("kind") else 1


def _cho_ngoi_con_dung(endpoint: str, kind: str, slot: int) -> bool:
    """Supervisor còn muốn một thợ ngồi ở chỗ này không?

    Dùng CHUNG một phép tính với supervisor, nên hạ số tab trên giao diện là thợ
    thừa tự thấy mình dôi ra và nghỉ — không phải khởi động lại board. Trước đây
    vòng dọn của supervisor chỉ XOÁ KHOÁ khỏi sổ `WORKERS`, mà `_worker` chỉ tự
    thoát khi tài khoản rời pool hoặc bị đánh dấu chết: luồng thừa cứ chạy tiếp,
    giữ nguyên tab của nó."""
    a = next((x for x in ACCOUNTS if _ep(x) == endpoint and x.get("enabled")), None)
    if a is None:
        return False
    kinds = [a["kind"]]
    if a["kind"] == "img" and not any(x["kind"] == "vid" and x["enabled"] for x in ACCOUNTS):
        kinds.append("vid")             # chưa có tài khoản Grok → kiêm nhiệm
    if kind not in kinds:
        return False
    return slot < _so_tab_theo_viec(a, kind)


def _dat_nhan_lo(viec, nhan: dict) -> int:
    """Dán nhãn của LÔ cho từng thành viên — TRỪ thẻ đã có ảnh. Trả về số thẻ bỏ qua.

    Một lô là MỘT tin nhắn, nhưng kết quả về theo từng thẻ: lượt này có thể trả
    ảnh cho 9/10 thẻ. Chín thẻ ấy xong thật, ảnh đã nằm trong `assets/`. Lượt sau
    của cùng lô đó mà dán đè nhãn cho cả 10 thì chín thẻ có ảnh bị kéo ngược về
    `queued`, rồi chết `error` theo lượt hỏng — user nhìn thấy thẻ đỏ cho ảnh
    đang có thật (dấu vết ALTAR 2026-08-15: cả 8 thẻ scene 21).

    Chỉ soi đúng nhãn `done`, và chỉ ở đây: `done → queued` là chiều HỢP LỆ khi
    user bấm Tạo lại, nên không chặn được ở tầng ghi trạng thái. Chỗ này thì
    biết chắc đây là lượt sau của cùng một lô, không phải ý định mới của user.
    """
    bo_qua = 0
    for i, _ in viec:
        if (JOBS.get(i) or {}).get("state") == "done":
            bo_qua += 1
            continue
        JOBS[i] = dict(nhan)
    return bo_qua


def _xep_ghe_cho_tai_khoan(a: dict, kinds: list, mo_tho) -> None:
    """Cấp ghế còn thiếu và thu ghế dôi ra cho MỘT tài khoản, đúng một vòng.

    Tách khỏi thân `_supervisor` để kiểm được: vòng kia ngủ 4 giây mỗi nhịp và
    mở luồng thợ thật, nên không có cách nào bắn nó một cách xác định.

    `mo_tho(kind, slot)` trả về đối tượng luồng đã chạy — nơi gọi quyết định là
    luồng thật hay bản giả.
    """
    for k in kinds:
        so_tab = _so_tab_theo_viec(a, k)
        for slot in range(so_tab):
            key = (a["port"], k, slot)
            th = WORKERS.get(key)
            if th is None or not th.is_alive():
                WORKERS[key] = mo_tho(k, slot)
        # Hạ số tab thì cho các luồng thừa tự nghỉ ở vòng lặp kế tiếp — nhưng
        # CHỈ XOÁ KHOÁ KHI LUỒNG ĐÃ CHẾT THẬT.
        #
        # Bản cũ xoá ngay. Mà `_worker` chỉ soi chỗ ngồi ở ĐẦU VÒNG: tới 2 giây
        # nếu đang rỗi, tới vài phút nếu đang giữa lượt vẽ. Nâng số tab lại
        # trong quãng đó thì `WORKERS.get(key)` trả None và vòng trên mở THÊM
        # một luồng nữa cho đúng ghế ấy. Ghế không phải sổ sách — nó là danh
        # tính tab (`window.name == "cgslot<N>"`), nên hai luồng cùng slot gõ
        # vào cùng một tab Chrome; rồi luồng cũ tới lượt nghỉ gọi
        # `_dong_tab_cho_ngoi` đóng tab, giật khỏi tay luồng mới đang làm dở.
        #
        # Giữ khoá lại là đủ: luồng còn sống thì vòng cấp ghế ở trên bỏ qua,
        # luồng chết rồi thì vòng này dọn ở nhịp sau.
        for key in [x for x in list(WORKERS)
                    if x[0] == a["port"] and x[1] == k and len(x) > 2 and x[2] >= so_tab]:
            th = WORKERS.get(key)
            if th is None or not th.is_alive():
                WORKERS.pop(key, None)


def _dong_tab_cho_ngoi(slot: int) -> None:
    """Đóng tab riêng của chỗ ngồi này khi thợ nghỉ vì dôi ra.

    HAI CHỐT AN TOÀN, thiếu cái nào cũng mất phiên đăng nhập:
      · `slot >= 1` — tab của slot 0 thường là tab DUY NHẤT của cửa sổ;
      · cửa sổ phải còn tab khác — đóng tab cuối là tắt luôn Chrome.
    Đó cũng là lý do `_release_tl` không bao giờ đóng tab. Nhưng ở đây không
    đóng thì tab thừa nằm lại ăn RAM tới tận lần mở lại Chrome."""
    if slot < 1:
        return
    for s in (getattr(_TL, "sess", None), getattr(_TL, "gsess", None)):
        pg = getattr(s, "page", None)
        if pg is None:
            continue
        try:
            if pg.is_closed() or len(pg.context.pages) <= 1:
                continue
            pg.evaluate("n => { window.name = n }", "")      # nhả dấu chỗ ngồi
            pg.close()
        except Exception:                                    # noqa: BLE001
            pass


def _quyet_xep_lai(ident: str, gen: int) -> str:
    """Tới giờ bắn — việc này còn được xếp lại không? `xep` · `dung` · `huy`.

    Tách khỏi bộ hẹn giờ để thử được mà không phải chờ đồng hồ thật.

    ĐỌC CỜ HUỶ MÀ KHÔNG ĂN. Ăn cờ ở đây là thợ nhấc việc lên sau đó không thấy
    gì và chạy thật — đúng việc user vừa bấm huỷ."""
    if dung_gen() != gen:
        return "dung"
    if _bi_huy(ident, an=False):
        return "huy"
    return "xep"


def _xep_lai_sau(kind: str, item: tuple, giay: float) -> None:
    """Xếp lại việc sau `giay` giây, trừ khi user đã bấm 'Dừng tất cả'.

    CÓ GIÃN CÁCH, không xếp lại tức thì: thử lại vô hạn mà bắn liền tay thì một
    việc hỏng vì dữ liệu quay vòng vài lần mỗi giây, ngập log và chiếm chỗ của
    việc chạy được. `dung_gen` soi ở thời điểm BẮN chứ không phải lúc hẹn — user
    bấm dừng trong lúc chờ thì việc này biến mất theo.
    """
    gen = dung_gen()
    # DẤU SỞ HỮU. Thợ vừa dán nhãn 'đang chạy · thử lại sau…' ngay trên dòng gọi
    # này, và `_dong_dau` đóng một `t` mới vào mỗi lần ghi trạng thái. Cầm theo
    # `t` đó là cầm theo câu "nhãn hiện tại là nhãn của TÔI" — xem `_ban_xep_lai`.
    dau = (JOBS.get(item[1]) or {}).get("t")
    t = threading.Timer(max(1.0, giay), _ban_xep_lai, args=(kind, item, gen, dau))
    t.daemon = True
    t.start()


def _ban_xep_lai(kind: str, item: tuple, gen: int, dau: float | None) -> str:
    """THÂN của bộ hẹn giờ — tới giờ rồi thì làm gì. Trả về quyết định đã chọn.

    Tách khỏi closure để máy trạng thái Hypothesis bắn được nó một cách xác
    định, thay vì phải chờ đồng hồ thật mỗi bước."""
    # VIỆC CÒN LÀ CỦA MÌNH KHÔNG? Chuông này hẹn từ tối đa 180 giây trước
    # (`cho = min(20 + 20*tries, 180)`); trong quãng đó user tạo lại được, thợ
    # khác nhận và làm xong được. Nhãn hiện tại khác dấu đã cầm nghĩa là có
    # người ghi đè rồi — việc không còn của mình, im lặng là đúng.
    #
    # Bỏ phép gác này thì chuông cũ ghi `error` lên việc đang render thật, mà cả
    # ba đường tạo (`/api/generate`, nhánh tạo nhiều SF, chốt video của auto)
    # đều đọc nhãn để biết "còn chạy không" — nên nhãn sai mở lại chốt chống
    # trùng và auto đẩy lệnh thứ hai sang Grok, trừ credit lần nữa. Gác cả nhánh
    # xếp lại chứ không riêng nhánh ghi nhãn: xếp lại một việc đã xong cũng là
    # một lượt render thừa.
    if (JOBS.get(item[1]) or {}).get("t") != dau:
        _lich_huy_ident(kind, item[1])
        return "nhuong"
    quyet = _quyet_xep_lai(item[1], gen)
    if quyet == "xep":
        # ÉP TÀI KHOẢN LÀ RÀNG BUỘC CỦA CẢ VIỆC, KHÔNG CHỈ CỦA LẦN CHẠY ĐẦU.
        #
        # Bản cũ luôn thả về hàng CHUNG. Nhưng chat sống trong profile Chrome
        # của đúng tài khoản đã mở nó, nên lần thử sau chạy ở máy khác là mở
        # chat trắng — đúng thứ user ép tài khoản để tránh. Ép xong mà lỗi một
        # lượt là ràng buộc bay mất, im lặng.
        _ep = _tk_bi_ep(item[1])
        if kind == "img" and _ep:
            _legacy_enqueue_private_image(_ep, item[1], True, "retry")
            return quyet
        _xep(IMG_QUEUE if kind == "img" else VID_QUEUE, item)
        return quyet
    # NHÃN PHẢI NÓI CÙNG SỰ THẬT VỚI HÀNG ĐỢI (vá 2026-08-14).
    # Bản cũ chỉ `return`: thợ đã dán nhãn 'đang chạy · thử lại sau 20s'
    # TRƯỚC khi hẹn giờ, nên việc bị từ chối xếp lại nằm lại vĩnh viễn với
    # nhãn đó. Hai cái hỏng theo, đúng cặp triệu chứng user gặp:
    #   · board hiện "đang chạy" mãi cho việc sẽ KHÔNG BAO GIỜ chạy nữa;
    #   · `/api/generate` và nhánh tạo nhiều SF đều BỎ QUA ident đang
    #     'running', nên bấm Tạo lại đúng những SF đó là im lặng không đẩy
    #     gì vào Chrome.
    _dat_job(item[1], {"state": "error",
                       "msg": "đã dừng" if quyet == "dung" else "đã huỷ"})
    _lich_huy_ident(kind, item[1])
    return quyet


def _acct_label() -> str:
    """Nhãn '[tk 2/6]' của luồng thợ đang chạy, để hiện lên board."""
    ep = getattr(_TL, "endpoint", None)
    pool = _pool(getattr(_TL, "kind", "img"))
    if ep is None or ep not in pool or len(pool) < 2:
        return ""
    return f" [tk {pool.index(ep) + 1}/{len(pool)}]"


def _worker_entry(endpoint: str, kind: str, slot: int = 0):
    """Vỏ bọc DUY NHẤT của `_worker` — chỉ để ghi sổ lỗi, không có logic việc.

    `_worker` tự nuốt mọi lỗi của từng việc và xoay tài khoản; cái lọt ra tới
    đây là lỗi làm CHẾT CẢ LUỒNG THỢ (supervisor sẽ mở luồng mới ở vòng sau).
    Đúng loại lỗi cần lưu lại để đọc sau khi board restart."""
    try:
        _worker(endpoint, kind, slot)
    except BaseException as e:                      # noqa: BLE001
        report_runtime_bug({
            "reason_code": "WORKER_CRASH",
            "category": "unhandled_exception",
            "severity": "CRITICAL",
            "job": {"kind": kind, "phase": "worker_loop", "job_id": ""},
            "runtime": {"endpoint": endpoint, "slot": slot},
            "exc": e,
        })
        raise


def _worker(endpoint: str, kind: str, slot: int = 0):
    """Một luồng thợ gắn cứng với MỘT tài khoản.

    kind='img' → lấy việc từ IMG_QUEUE, chạy trên tài khoản ChatGPT.
    kind='vid' → lấy việc từ VID_QUEUE, chạy trên tài khoản Grok.
    Tự nghỉ khi tài khoản bị tắt trên giao diện hoặc bị đánh dấu chết;
    supervisor sẽ mở thợ mới khi tài khoản được bật/hồi sinh."""
    if _JOB_MODE == "authoritative":
        # Executor cũ tự retry/ghi terminal. Cho nó chạy trong mode mới sẽ tạo
        # authority thứ hai; fail-closed tới khi worker gọi adapter một-attempt.
        _LOG.error("legacy worker bị chặn trong authoritative mode")
        return
    _TL.endpoint = endpoint
    _TL.kind = kind
    _TL.slot = slot          # chỗ ngồi: quyết định thợ này lái TAB NÀO
    QUEUE = IMG_QUEUE if kind == "img" else VID_QUEUE
    while True:
        if endpoint not in _pool(kind) or DEAD.get(endpoint):
            _release_tl()
            return
        # Soi Ở ĐẦU VÒNG, tức GIỮA hai việc — không bao giờ bỏ dở việc đang chạy.
        if not _cho_ngoi_con_dung(endpoint, kind, slot):
            _LOG.info("%s: chỗ ngồi %s·%d dôi ra (số tab đã hạ) — thợ nghỉ, đóng tab.",
                      _ten_tk(endpoint), kind, slot)
            _dong_tab_cho_ngoi(slot)
            _release_tl()
            return
        # VIỆC GIAO ĐÍCH DANH ĐI TRƯỚC: lô của địa điểm mà chat nằm ở tài khoản
        # NÀY. Không lấy từ hàng chung — requeue vào hàng chung là trò xổ số:
        # hai thợ sai cứ chuyền nhau nhặt-thả cùng một lô, thợ đúng đói vĩnh viễn.
        item, tu_hang = None, False
        if kind == "img":
            _my_port = int(endpoint.rsplit(":", 1)[1] or 0)
            with _CR_LOCK:
                _rieng = CHO_RIENG.get(_my_port) or []
                if _rieng:
                    item = ("img", _rieng.pop(0), 0, True)
        if item is None:
            try:
                item = _lay(QUEUE, timeout=2)
                tu_hang = True
            except queue.Empty:
                continue
        _, ident, tries = item[0], item[1], item[2]
        manual = item[3] if len(item) > 3 else False
        # ĐÁNH DẤU 'ĐANG CHẠY' NGAY KHI NHẤC, trước cả bước nối Chrome.
        #
        # Từ lúc `_lay()` rút việc khỏi hàng tới lúc `_generate_lo` kịp ghi nhãn
        # 'running' có vài giây (đọc board, mở tab, đính ref). Trong khoảng đó
        # việc KHÔNG còn trong hàng mà nhãn vẫn là 'chờ' — đúng định nghĩa "mồ
        # côi" của người gác, nên nó xếp lại và một thợ thứ hai nhấc luôn.
        # Hậu quả: CÙNG MỘT LÔ GỬI HAI LẦN, đốt gấp đôi lượt. Bắt được tận tay
        # 2026-08-12 với lô SF-S22 — log có hai dòng "đã gửi lô 4 khung" cách
        # nhau 2 giây, ngay sau một dòng "đã xếp lại (lần 1)".
        _dat_job(ident, {"state": "running", "msg": "đang khởi động…"})
        # GẮN LEASE cho lượt này. Ở Phase 4 lease chỉ để QUAN SÁT — hàng đợi
        # legacy vẫn là thứ đưa việc tới đây. Nó trả lời được câu mà `JOBS`
        # không trả lời nổi: việc này đang do ai cầm, cầm từ bao giờ.
        _lease = _lich_nhan(kind, ident)
        _lease_outcome = "finished"
        _lease_not_before = 0.0
        # Ghi sổ NGAY khi nhận việc, gỡ ở `finally` — để `_giu_du_tai_khoan()`
        # biết cửa sổ này đang bận mà đừng đóng ngang.
        _ban_vao(endpoint)
        # Chrome đã bị đóng/mở lại từ lần chạy trước (ngủ khi rảnh, user tắt-bật,
        # supervisor hồi sinh)? Nhả sạch Playwright của luồng này rồi nối lại từ
        # đầu — nếu không, mọi job sẽ chết ở bước mở tab.
        if getattr(_TL, "gen", None) != CHROME_GEN["n"]:
            _release_tl()
            _TL.gen = CHROME_GEN["n"]
        stop = False
        try:
            # CỜ HUỶ ÁP CHO CẢ HAI LOẠI VIỆC. Bản cũ đặt phép kiểm này BÊN TRONG
            # nhánh `kind == "img"`, nên việc video đã bị user huỷ vẫn được thợ
            # nhấc lên chạy — mà mỗi lượt Grok là credit thật (vá 2026-08-14).
            if _bi_huy(ident):
                _dat_job(ident, {"state": "error", "msg": "đã huỷ"})
            elif kind == "img":
                # ident "LO:sf1,sf2,…" = một LÔ ảnh cùng địa điểm, gửi trong MỘT
                # lượt của MỘT đoạn chat. Đường lô nằm cạnh đường một-ảnh, không
                # thay thế nó: sửa lẻ vẫn phải dùng đường một-ảnh.
                if ident.startswith("LO:"):
                    _generate_lo([x for x in ident[3:].split(",") if x], tay=manual)
                    # DỌN JOB CỦA IDENT LÔ khi lô đã xong hẳn. `_dat_job` đặt
                    # JOBS["LO:a,b,c"] lúc lô phải chờ khoá địa điểm, nhưng
                    # đường CHẠY XONG không đụng tới nó — nên nó kẹt 'queued'
                    # vĩnh viễn. Giao diện giấu dòng LO: nên không ai thấy, còn
                    # mọi phép kiểm "có việc nào đang chạy không" thì đọc phải
                    # con ma đó (đã lừa đúng một lần khi kiểm trước lúc restart).
                    # Chỉ dọn khi KHÔNG còn thành viên nào chờ/chạy — lô tự hoãn
                    # rồi xếp lại vẫn phải giữ nguyên dòng trạng thái của nó.
                    _tv = [x for x in ident[3:].split(",") if x]
                    if not any(JOBS.get(x, {}).get("state") in ("queued", "running")
                               for x in _tv):
                        JOBS.pop(ident, None)
                else:
                    # Ident lẻ (không có tiền tố LO:) vẫn phải đi ĐÚNG đường tin
                    # nhắn, để còn gửi `luatchung`. Đường `_generate` cũ không
                    # gửi luật chung nên ảnh mất neo look — hỏng câm. Không còn
                    # chỗ nào xếp ident lẻ nữa, nhưng bịt luôn để sau này có
                    # xếp nhầm thì cũng ra ảnh đúng.
                    _generate_lo([ident], tay=manual)
            else:
                _gen_video(ident)
        except Exception as e:
            # TAB/CỬA SỔ CHẾT THÌ CHỤP NGAY HIỆN TRẠNG MÁY, trước khi làm gì khác.
            # "Aw, Snap! Error code: 5" là renderer bị hệ điều hành thu hồi vì cạn
            # bộ nhớ — nó KHÔNG để lại báo cáo sự cố nào, nên qua thời điểm này là
            # mất hẳn bằng chứng và chỉ còn nước đoán.
            if _is_dead_session_error(e):
                _LOG.warning("TAB/CỬA SỔ CHẾT khi chạy %s trên %s — %s | lỗi gốc: %s",
                             ident, endpoint,
                             _anh_chup_may(int((endpoint or ":0").rsplit(":", 1)[1] or 0)),
                             str(e)[:120])
            # MỌI LỖI ĐỀU XOAY SANG TÀI KHOẢN KẾ TIẾP (user chốt 2026-08-14).
            # Không phân loại nặng nhẹ, không đếm số lần, không có lỗi nào
            # "dừng tại chỗ" — chỉ "Dừng tất cả" mới cắt được.
            #
            # Gồm cả "cửa sổ Chrome đã đóng" (tab chết cũng là cửa sổ hỏng) và
            # cả HẾT LƯỢT — user chốt bỏ hẳn cơ chế cho tài khoản nghỉ. Trước
            # đây hai ca này đi đường riêng và tài khoản bị treo khỏi vòng: cái
            # thì vĩnh viễn, cái thì tới giờ ChatGPT hẹn (có khi 4 tiếng). Giờ
            # cả hai xoay như mọi lỗi khác — tài khoản cạn lượt sẽ lỗi lại ở
            # vòng sau và tự xoay tiếp, không cần ai canh đồng hồ.
            #
            # Giãn cách tăng dần tới trần 3 phút. KHÔNG phải giới hạn số lần
            # (vẫn vô hạn), chỉ là cái phanh: xoay qua một tài khoản chưa đăng
            # nhập thì lỗi bật lại tức thì, không phanh là quay hết cả danh sách
            # trong vài giây và mở–đóng chục cửa sổ Chrome.
            cho = min(20 + 20 * tries, 180)
            _xoay_chrome(endpoint, kind, _loi_gon(e))
            _release_tl()
            stop = True
            # Lỗi nằm trong sf-board.json thì đổi cửa sổ không chữa được — vẫn
            # xoay theo đúng luật, nhưng nói thẳng trên thẻ để khỏi ngồi đợi một
            # việc không bao giờ ra ảnh.
            ghi_chu = " ⚠ lỗi DỮ LIỆU — đổi cửa sổ không chữa được" if _loi_du_lieu(e) else ""
            # ═══ VIDEO CÓ TRẦN, ẢNH THÌ KHÔNG ══════════════════════════════
            # Luật "thử lại vô hạn" (user chốt 2026-08-14) viết cho ẢNH và đúng
            # với ảnh: hỏng thì mất lượt, xoay tài khoản là chữa được.
            #
            # VIDEO khác về bản chất TIỀN: Grok trừ credit theo từng submit và
            # trả 2 biến thể mỗi lượt. Một shot hỏng ở bước tải (CDN Grok ngắt —
            # chuyện thường) mà thử lại vô hạn thì cứ ~3 phút lại tiêu ~2 credit,
            # chạy qua đêm là cạn ví, còn trên giao diện nó chỉ hiện "đang chạy".
            # Nên video dừng sau VID_MAX_TRY lượt và BÁO LỖI để user nhìn thấy.
            if kind == "vid" and tries + 1 >= VID_MAX_TRY:
                _dat_job(ident, {"state": "error",
                                 "msg": f"{_loi_gon(e)} — đã thử {VID_MAX_TRY} lượt, "
                                        f"dừng để khỏi đốt credit. Bấm 'Tạo lại' nếu "
                                        f"muốn thử tiếp.{ghi_chu}"})
                _LOG.warning("video %s dừng sau %d lượt: %s", ident, VID_MAX_TRY, _loi_gon(e))
                # Ghi sổ runtime SAU khi đã đặt nhãn lỗi + log như cũ. Không đổi
                # trạng thái job, không xếp lại, không ném lỗi ra ngoài.
                report_runtime_bug({
                    "reason_code": "RETRY_EXHAUSTED",
                    "category": "video_retry",
                    "severity": "ERROR",
                    "job": {"job_id": ident, "kind": "vid", "phase": "retry_exhausted",
                            "tries": VID_MAX_TRY},
                    "runtime": {"endpoint": endpoint, "slot": slot,
                                "buoc": _dau_vet_buoc("vid")},
                    "exc": e,
                })
            else:
                _lease_outcome = "retry"
                _lease_not_before = time.time() + cho
                _dat_job(ident, {"state": "running",
                                 "msg": f"{_loi_gon(e)} → đổi tài khoản, thử lại "
                                        f"sau {cho}s (lần {tries + 1}){ghi_chu}"})
                _xep_lai_sau(kind, (kind, ident, tries + 1, manual), cho)
                # Ghi sổ SAU khi đã đặt nhãn và xếp lại — không đổi gì ở trên.
                # `min_repeats` là cái phanh: xoay tài khoản là chuyện bình
                # thường, chỉ khi CÙNG một lỗi lặp lại lần thứ 3 mới đáng lưu.
                report_runtime_bug({
                    "reason_code": _ly_do_loi(e),
                    "category": "render_rotate",
                    "severity": "ERROR",
                    "job": {"job_id": ident, "kind": kind, "phase": "rotate",
                            "tries": tries + 1},
                    "runtime": {"endpoint": endpoint, "slot": slot,
                                "buoc": _dau_vet_buoc(kind)},
                    "min_repeats": _phanh_ghi_so(kind),
                    "exc": e,
                })
        finally:
            _ban_ra(endpoint)
            _lich_tra(
                _lease, outcome=_lease_outcome,
                not_before=_lease_not_before)
            if tu_hang:                 # việc lấy từ CHO_RIENG không qua queue
                QUEUE.task_done()
        if stop:
            _LOG.info("%s: ngừng nhận việc.", _ten_tk(endpoint))
            return


def _enqueue(kind: str, ident: str, copies: int = 1, manual: bool = False):
    """Xếp việc vào hàng. copies>1 = tạo nhiều bản SONG SONG cho cùng một SF,
    mỗi bản chạy trên một tài khoản khác nhau, kết quả vào versions/ để chọn."""
    q = IMG_QUEUE if kind == "img" else VID_QUEUE
    copies = max(1, min(int(copies or 1), 6))
    n = q.qsize()
    if copies > 1:
        with _BATCH_LOCK:
            BATCH[ident] = {"total": copies, "done": 0, "err": 0}
        JOBS[ident] = {"state": "running", "msg": f"đang tạo 0/{copies} bản…"}
    else:
        with _BATCH_LOCK:
            BATCH.pop(ident, None)
        # NHÃN 'CHỜ' CHỨ KHÔNG PHẢI 'ĐANG CHẠY' (vá 2026-08-14). Bản cũ đóng dấu
        # `running` ngay lúc XẾP, nên xếp 307 video là 307 dòng "đang chạy" trong
        # khi chỉ một thợ Grok làm thật. Ba thứ hỏng theo nó:
        #   · `/api/huy` và `/api/huy-viec` chỉ nhận việc nhãn 'queued' → không
        #     có cách nào huỷ hàng đợi video ngoài "Dừng tất cả";
        #   · người gác chỉ cứu việc nhãn 'queued' → video rơi khỏi hàng là kẹt;
        #   · `/api/jobs` đếm thợ bận theo nhãn → báo 307 thợ video đang bận.
        # Thợ tự đóng dấu `running` ngay khi nhấc việc, nên không mất thông tin.
        JOBS[ident] = {"state": "queued",
                       "msg": "chờ · sắp tới lượt" if n == 0 else f"chờ · {n} việc trước"}
    for _ in range(copies):
        _xep(q, (kind, ident, 0, manual))


BATCH: dict[str, dict] = {}      # sf_id -> {total, done, err} khi tạo nhiều bản
_BATCH_LOCK = threading.Lock()


def _drop_reserved(path):
    """Nhả chỗ đã giữ nếu bản đó tạo hỏng (file còn rỗng)."""
    try:
        if path and os.path.exists(path) and os.path.getsize(path) < 1024:
            os.remove(path)
    except OSError:
        pass


def _batch_tick(ident: str, ok: bool) -> bool:
    """Ghi nhận một bản trong lô đã xong. Trả True nếu ident đang chạy theo lô."""
    with _BATCH_LOCK:
        b = BATCH.get(ident)
        if not b:
            return False
        b["done" if ok else "err"] += 1
        done, err, total = b["done"], b["err"], b["total"]
        finished = done + err >= total
        if finished:
            BATCH.pop(ident, None)
    if finished:
        JOBS[ident] = ({"state": "done", "msg": f"xong {done}/{total} bản"} if done else
                       {"state": "error", "msg": f"cả {total} bản đều lỗi"})
    else:
        JOBS[ident] = {"state": "running",
                       "msg": f"đang tạo {done + err}/{total} bản…" +
                              (f" ({err} lỗi)" if err else "")}
    return True


# Chrome KHÔNG BAO GIỜ tự đóng. Trước đây có luồng ngủ-khi-rảnh đóng hết cửa sổ
# sau 10 phút không việc; user bỏ hẳn vì đang dùng dở mà Chrome tự tắt rất phiền.
# Muốn đóng thì tắt tài khoản trên board (/api/acct?op=toggle).


def _gac_hang_doi():
    """Bắt việc mang nhãn 'chờ' mà KHÔNG còn ai nhặt, rồi xếp lại vào hàng.

    Vì sao cần: giao diện đọc JOBS, mà JOBS chỉ là DẤU VẾT ĐÃ GHI, không phải
    hàng đợi thật. Hai thứ này lệch nhau được — đã đo tận tay một lần: giao diện
    báo 22 việc 'chờ' trong khi hàng đợi RAM chỉ còn 3 mục. Việc rơi khỏi hàng
    (thợ chết đúng nhịp xếp lại, 'Dừng tất cả' vét hàng trong lúc một lô đang nằm
    giữa vòng chờ khoá địa điểm) thì nhãn 'chờ' nằm lại vĩnh viễn: board im như
    thóc, user nhìn thấy hàng dài việc chờ mà không gì chạy, bấm dừng-chạy lại
    cũng vô ích vì lô mới lại kẹt sau đúng cái nhãn ma đó.

    Chỉ xếp lại, KHÔNG đánh lỗi: việc user đã bấm thì phải chạy được, đừng bắt
    họ bấm lại. Có trần 3 lần cho mỗi ident để một lô hỏng thật không quay vòng
    mãi mãi."""
    cuu: dict[str, int] = {}
    huy_ma_chay: dict[str, float] = {}   # ident sai bất biến -> lúc đầu tiên thấy
    da_bao_huy: set[str] = set()         # đã ghi sổ rồi, đừng ghi lại mỗi 30s
    gen_truoc = dung_gen()
    while True:
        time.sleep(30)
        if not _legacy_execution_enabled():
            continue
        try:
            # "DỪNG TẤT CẢ" PHẢI THẮNG NGƯỜI GÁC. Người gác sinh ra để cứu việc
            # rơi khỏi hàng, nhưng sau cú bấm dừng thì việc rơi khỏi hàng là
            # ĐÚNG Ý USER — cứu nó lên là board tự chạy lại sau khi đã tắt, đúng
            # thứ khó chịu nhất: giao diện nói đã dừng, máy vẫn vẽ.
            if dung_gen() != gen_truoc:
                gen_truoc = dung_gen()
                cuu.clear()
                continue
            trong_hang = _y_trong_hang(IMG_QUEUE) | _y_trong_hang(VID_QUEUE)
            with _CR_LOCK:
                for ds in CHO_RIENG.values():
                    trong_hang.update(ds)
            # Lô đang chạy dở phủ bóng lên chính các SF thành viên của nó: chúng
            # mang nhãn 'chờ' một cách hợp lệ, không phải mồ côi.
            dang_chay = set()
            for k, v in list(JOBS.items()):
                if v.get("state") == "running":
                    dang_chay.add(k)
                    if k.startswith("LO:"):
                        dang_chay.update(x for x in k[3:].split(",") if x)
            for k in trong_hang:
                if k.startswith("LO:"):
                    dang_chay.update(x for x in k[3:].split(",") if x)

            mo_coi = [k for k, v in list(JOBS.items())
                      if v.get("state") == "queued"
                      and k not in trong_hang and k not in dang_chay]
            # Việc user đã huỷ thì để yên — DA_HUY là ý user, không phải sự cố.
            with HUY_LOCK:
                da_huy = set(DA_HUY)
            mo_coi = [k for k in mo_coi if k not in da_huy]

            # ── CHỐT BẤT BIẾN: CỜ HUỶ PHẢI ĐƯỢC TÔN TRỌNG ────────────────
            # `/api/huy` và `/api/huy-viec` đều TỪ CHỐI huỷ việc đang chạy, nên
            # không đường nào hợp lệ đưa một ident vừa mang cờ huỷ vừa mang nhãn
            # 'running'. Thấy cả hai cùng lúc và KÉO DÀI là thợ đã không soi được
            # cờ — đúng triệu chứng "bấm dừng rồi mà nó vẫn chạy, credit vẫn trừ".
            #
            # CHỈ ĐỌC bản sao `da_huy`, KHÔNG gọi `bi_huy()`: hàm đó ĂN cờ khi
            # đọc, người gác gọi vào là cướp mất cờ của thợ và làm hỏng chính cơ
            # chế huỷ mà nó đang canh.
            for k, lau in _soat_co_huy(da_huy, JOBS, huy_ma_chay, da_bao_huy):
                _LOG.warning("việc %s mang cờ huỷ nhưng vẫn 'đang chạy' sau %ds", k, lau)
                report_runtime_bug({
                    "reason_code": "INVARIANT_VIOLATION",
                    "category": "cancel_not_honoured",
                    "severity": "ERROR",
                    "job": {"job_id": k, "kind": _loai_viec(k), "phase": "cancel_watchdog"},
                    # Số giây để Ở ĐÂY, không nhét vào message: message đi vào
                    # fingerprint, mỗi mốc giây khác nhau là một Bead khác nhau.
                    "runtime": {"giu_lau_giay": lau},
                    "exception": {
                        "type": "CancelNotHonoured",
                        "message": "ident mang cờ huỷ nhưng vẫn ở trạng thái running",
                        "source_file": "sfboard/sfboard.py",
                        "source_function": "_gac_hang_doi",
                        "source_line": 0,
                    },
                })

            # TÁCH VIỆC VIDEO RA TRƯỚC KHI GOM LÔ.
            #
            # Từ 2026-08-14 việc video cũng mang nhãn 'queued' nên nó lọt vào đây
            # — trước đó nó đội nhãn 'running' nên vô hình với người gác (và vì
            # thế rơi khỏi hàng là kẹt mãi). Nhưng nhánh gom bên dưới coi MỌI
            # ident không có tiền tố "LO:" là ảnh lẻ, gom thành lô rồi ném vào
            # IMG_QUEUE — video mà đi đường đó thì thợ ChatGPT nhận một ident
            # shot và cố vẽ ảnh cho nó.
            #
            # Nhận diện bằng SỔ SHOT của board, không bằng tiền tố "V-": tiền tố
            # là quy ước đặt tên, mà quy ước thì dự án cũ có thể khác.
            _shot_ids = {sh["id"] for sc in BOARD.read().get("scenes", [])
                         for sh in sc.get("shots", [])} if mo_coi else set()
            vid_mo_coi = [k for k in mo_coi if k in _shot_ids]
            mo_coi = [k for k in mo_coi if k not in _shot_ids]
            for k in vid_mo_coi:
                if cuu.get(k, 0) >= 12:
                    JOBS[k] = {"state": "error", "msg": "rơi khỏi hàng đợi 12 lần — bấm chạy lại"}
                    continue
                cuu[k] = cuu.get(k, 0) + 1
                _xep(VID_QUEUE, ("vid", k, 0, False))
                _LOG.warning("video %s mang nhãn 'chờ' mà không còn trong hàng đợi "
                             "— đã xếp lại (lần %d)", k, cuu[k])

            # GOM LẠI THÀNH LÔ THEO ĐỊA ĐIỂM RỒI MỚI XẾP.
            # Xếp từng SF lẻ là hỏng: mỗi ảnh thành một lô một ảnh, tức mỗi ảnh
            # một lượt chat riêng — mất hết cái lợi của việc gom lô (ảnh cùng lô
            # vẽ một lượt nên đồng bộ nhất) và đốt gấp mấy lần hạn mức.
            can_xep = sorted(k for k in mo_coi if k.startswith("LO:"))
            trong_lo = {x for k in can_xep for x in k[3:].split(",") if x}
            le = [k for k in mo_coi if not k.startswith("LO:") and k not in trong_lo]
            if le:
                _dl = BOARD.read()
                theo_nhom: dict[str, list] = {}
                for k in le:
                    theo_nhom.setdefault(_nhom_cua(k, _dl) or "", []).append(k)
                for xs in theo_nhom.values():
                    xs.sort(key=_uu_tien)
                    for lo in _chia_lo(xs, lambda i: _ref_id_cua_sf(i, _dl),
                                       TRAN_MAY_TU_GOM, TRAN_REF):
                        can_xep.append("LO:" + ",".join(lo))

            for k in can_xep:
                # Trần nới 3 → 12 (2026-08-14) cho hợp với luật thử-lại-vô-hạn.
                # KHÔNG bỏ hẳn: đây là guard cho lỗi hàng đợi, không phải cho
                # lỗi render. Bỏ trần thì một việc mồ côi do bug sẽ quay vòng
                # lặng lẽ mãi mãi, không ai thấy — đúng thứ trần này sinh ra để
                # phơi bày.
                if cuu.get(k, 0) >= 12:
                    for x in k[3:].split(","):
                        if x:
                            JOBS[x] = {"state": "error",
                                       "msg": "rơi khỏi hàng đợi 12 lần — bấm chạy lại"}
                    continue
                cuu[k] = cuu.get(k, 0) + 1
                # GIỮ NGUYÊN CỜ TAY CỦA VIỆC GỐC. Xếp lại là KHÔI PHỤC một việc
                # đã mất, không phải sinh việc mới — hạ cờ xuống False là đổi ý
                # user thành ý máy, và lô user vừa bấm tạo lại bị bộ lọc "đã có
                # ảnh" gạt sạch ngay ở lượt xếp lại đầu tiên.
                _tay = any(x in TAY_SF for x in k[3:].split(",") if x)
                _xep(IMG_QUEUE, ("img", k, 0, _tay))
                _LOG.warning("việc %s mang nhãn 'chờ' mà không còn trong hàng đợi "
                             "— đã xếp lại (lần %d%s)", k, cuu[k],
                             ", giữ cờ tạo-tay" if _tay else "")
        except Exception as e:
            # Không nuốt im: người gác mà chết lặng thì bệnh nó phải chữa quay lại
            # y như cũ, lần sau lại mất cả buổi để lần ra.
            _LOG.warning("người gác hàng đợi vấp: %s", e)


def _supervisor():
    """Bảo đảm mỗi tài khoản đang bật luôn có luồng thợ sống.

    - Tài khoản bật mà chưa có thợ (mới bật lại, hoặc thợ đã chết) → mở thợ mới.
    - Tài khoản 'cửa sổ Chrome đã đóng' mà Chrome đã mở lại → tự hồi sinh.
    - Tài khoản 'hết lượt' giữ nguyên đến khi user bấm 'Thử lại' trên giao diện."""
    while True:
        if not _legacy_execution_enabled():
            time.sleep(2)
            continue
        try:
            _giu_du_tai_khoan()      # số tài khoản chạy được luôn bằng con số user đặt
        except Exception as e:
            _LOG.warning("giữ đủ tài khoản lỗi: %s", str(e)[:90])
        try:
            with ACC_LOCK:
                accs = [dict(a) for a in ACCOUNTS]
            has_vid = any(a["kind"] == "vid" and a["enabled"] for a in accs)
            for a in accs:
                if not a["enabled"]:
                    continue
                ep = _ep(a)
                if DEAD.get(ep) == "cửa sổ Chrome đã đóng" and _endpoint_alive(ep):
                    with _DEAD_LOCK:
                        DEAD.pop(ep, None)
                    _LOG.info("Chrome %s đã mở lại — hồi sinh tài khoản.", ep)
                # Hết kỳ chặn ngắn của `_xoay_chrome()` → gỡ dấu, cho chạy lại.
                _den = _dang_nghi(ep)
                if _den and time.time() >= _den:
                    _ly = DEAD.get(ep) or ""
                    with _DEAD_LOCK:
                        DEAD.pop(ep, None)
                        DEAD_DEN.pop(ep, None)
                    # Chỉ còn một ca vào được đây: "đổi cửa sổ" khi KHÔNG có ai
                    # để xoay sang (cửa sổ duy nhất). Board vừa tắt nó, phải mở
                    # lại thì mới có người làm.
                    if _ly.startswith("đổi cửa sổ") and not _endpoint_alive(ep):
                        _launch_chrome(a)
                        _LOG.info("mở lại cửa sổ %s (:%s) — không có tài khoản "
                                  "nào khác để xoay sang.", a["id"], a["port"])
                if DEAD.get(ep):
                    continue
                kinds = [a["kind"]]
                if a["kind"] == "img" and not has_vid:
                    kinds.append("vid")     # chưa có tài khoản Grok → thợ ảnh kiêm video
                # Một tài khoản có thể chạy NHIỀU TAB song song: mỗi tab một luồng
                # thợ riêng, cùng trỏ vào một cửa sổ Chrome. Số tab do user đặt ở
                # mục Tài khoản trên board (mặc định 1 = như cũ).
                def _mo_tho(k, slot, _ep=ep):
                    t = threading.Thread(target=_worker_entry,
                                         args=(_ep, k, slot), daemon=True)
                    t.start()
                    return t

                _xep_ghe_cho_tai_khoan(a, kinds, _mo_tho)
        except Exception:
            pass
        time.sleep(4)


# ───────────────────────── CHẠY TỰ ĐỘNG CẢ SCENE ─────────────────────────────
# Bật cho một scene rồi để đó: thiếu ảnh SF nào thì tạo ảnh, ảnh xong tới đâu
# thì đẩy video tới đó, cái nào lỗi thì tự bắn lại. Xong cả scene thì tự tắt.

AUTO: dict[str, dict] = {}       # scene_id -> {"try": {ident: số lần}, "last": {ident: vòng}}
AUTO_LOCK = threading.Lock()

# CỔNG KHÓA TẠO VIDEO đã BỎ 2026-08-09 theo yêu cầu user. Trước đó video chỉ chạy
# khi user tự bấm nút trên giao diện, cờ nằm ở <project>/.video-gate. Giờ bấm "Tạo
# video" hay chạy hàng loạt đều đi thẳng, không còn lớp chặn nào.
#
# Thay vào đó là CÔNG TẮC AUTO-VIDEO: chỉ chi phối vòng quét tự động (_auto_scene),
# KHÔNG chặn thao tác tay. Tắt = auto chỉ lo ảnh SF, video để user tự bấm. Đây là
# thuộc tính của từng phim (phim đang ở chặng vẽ ảnh khác phim đã sang chặng dựng
# video) nên cờ nằm trong thư mục dự án, không phải ở HOME như cờ dán mã.
def _auto_vid_path() -> str:
    return os.path.join(BOARD.dir, ".auto-video.json")


def _auto_vid_doc() -> bool:
    try:
        return bool(json.load(open(_auto_vid_path(), encoding="utf-8"))["on"])
    except Exception:
        return False               # mặc định TẮT — auto tự dựng video là việc tốn


def _auto_vid_ghi(on: bool) -> None:
    try:
        with open(_auto_vid_path(), "w", encoding="utf-8") as f:
            json.dump({"on": bool(on)}, f)
    except OSError as e:
        _LOG.warning("không ghi được cờ auto-video: %s", e)


AUTO_PERIOD = 20                 # giây mỗi vòng quét

# ĐÁNH THỨC VÒNG QUÉT NGAY khi user vừa bật "Chạy hết".
#
# Nhãn trên nút ("12/17 ảnh") do chính vòng quét ghi ra, nên bản cũ bấm xong phải
# ngồi nhìn "⏳ đang quét…" tới 20 giây mới thấy số — mà trong 20 giây đó cũng
# chưa việc nào vào hàng đợi, trông như bấm hụt.
_AUTO_WAKE = threading.Event()
AUTO_MAX_TRY = 0                 # 0 = KHÔNG GIỚI HẠN (user chốt 2026-08-14)
AUTO_COOLDOWN = 6                # số vòng phải chờ trước khi bắn lại cùng ident (~2 phút)


def _auto_allow(st: dict, ident: str, cyc: int, ghi: bool = True) -> bool:
    """Còn lượt thử và đã hết thời gian chờ thì cho bắn.

    `ghi=False` là CHỈ HỎI, không tính một lần thử. Bắt buộc dùng khi mới đang
    lọc xem thẻ nào đủ điều kiện: auto đẩy lần lượt từng task, nên phần lớn thẻ
    trong danh sách lọc sẽ KHÔNG được đẩy vòng này. Tính lượt cho chúng là mỗi
    task chưa tới lượt đã ăn sẵn một cooldown 6 vòng (~2 phút) — auto bò từng
    task một, chậm gấp mấy lần mà nhìn log không ra vì sao.
    """
    # AUTO_MAX_TRY = 0 → thử lại mãi. Việc chỉ dừng khi user bấm "Dừng tất cả"
    # (vét hàng đợi + tăng thế hệ dừng) hoặc khi lỗi thuộc loại dữ liệu, mà lỗi
    # dữ liệu đã bị chặn ngay ở `_worker` nên không quay lại đây.
    if AUTO_MAX_TRY and st["try"].get(ident, 0) >= AUTO_MAX_TRY:
        return False
    if cyc - st["last"].get(ident, -999) < AUTO_COOLDOWN:
        return False
    if ghi:
        st["try"][ident] = st["try"].get(ident, 0) + 1
        st["last"][ident] = cyc
    return True


def _auto_giao_anh(sc, m, lo, data):
    """Giao MỘT lô ảnh của auto qua command boundary.

    Scope gắn với scene + địa điểm + đúng danh sách SF, nên hai vòng quét liên
    tiếp sinh cùng một key: lần sau chỉ là replay, không xếp thêm lượt. Ở mode
    legacy hàm này vẫn ghi `JOBS` và `_xep` y hệt bản cũ, chỉ đi qua adapter."""
    from jobs.compat import LegacyAction, LegacyPlan
    from jobs.models import AssetId, BatchMode, JobKind, JobOrigin
    from jobs.producer import CreateBatchRequest, CreateJobRequest

    ident = "LO:" + ",".join(lo)
    nhan = {"state": "queued",
            "msg": f"chờ · {len(lo)} ảnh · {_ten_gon(m, data)}"}
    scope = f"{_board_identity()}:auto:{sc['id']}:image:{m}:{','.join(lo)}"
    yeu_cau = CreateBatchRequest(
        tuple(
            CreateJobRequest(AssetId(i), JobKind.IMAGE, JobOrigin.AUTO,
                             request_scope=scope, replace_current=True)
            for i in lo
        ),
        BatchMode.IMAGE_GROUP,
    )

    def _plan(ket_qua):
        ids = tuple(job.job_id for job in ket_qua.jobs) if ket_qua else ()
        return LegacyPlan((
            LegacyAction(
                action_id=f"auto-img:{sc['id']}:{ident}",
                legacy_keys=(ident,),
                job_ids=ids,
                queue_kind="img",
                queue_ident=ident,
                manual=False,
                state=nhan,
                state_idents=tuple(lo),
                member_bindings=tuple(
                    (sf, (ids[k],)) for k, sf in enumerate(lo) if k < len(ids)
                ),
            ),
        ))

    return _producer_submit(yeu_cau, None, _plan)


def _auto_giao_video(sc, sh):
    """Giao một shot video của auto qua command boundary."""
    from jobs.compat import LegacyAction, LegacyPlan
    from jobs.models import AssetId, JobKind, JobOrigin
    from jobs.producer import CreateJobRequest

    shot_id = sh["id"]
    yeu_cau = CreateJobRequest(
        AssetId(shot_id), JobKind.VIDEO, JobOrigin.AUTO,
        request_scope=f"{_board_identity()}:auto:{sc['id']}:video:{shot_id}",
        replace_current=True,
    )

    def _plan(ket_qua):
        return LegacyPlan((
            LegacyAction(
                action_id=f"auto-vid:{shot_id}",
                legacy_keys=(shot_id,),
                job_ids=_job_ids_cua(ket_qua, (0,)),
                queue_kind="vid",
                queue_ident=shot_id,
                manual=False,
                state=_nhan_cho_video(0),
            ),
        ))

    return _producer_submit(yeu_cau, None, _plan)


def _auto_scene(sc: dict, st: dict, cyc: int) -> tuple[int, int, int, int]:
    """Quét một scene, xếp việc còn thiếu. Trả (ảnh thiếu, ảnh tổng, video thiếu, video tổng)."""
    # Snapshot này thuộc THẾ HỆ NÀO? `_auto_runner` thả AUTO_LOCK trong lúc đọc
    # board và tính task, nên user có thể bấm Dừng tất cả đúng giữa quãng đó.
    # Chụp generation ở cửa vào rồi kiểm lại NGAY TẠI chỗ commit dưới cùng
    # AUTO_LOCK với `/api/dung-het`: hoặc auto commit trước và cú dừng vét nó,
    # hoặc cú dừng thắng và snapshot cũ không được ghi JOBS/enqueue nữa.
    auto_gen = dung_gen()
    sfs, shots = sc.get("sfs", []), sc.get("shots", [])

    # 1) ảnh SF còn thiếu — CHẠY THEO LÔ, GOM THEO ĐỊA ĐIỂM.
    #    Đường _enqueue đơn lẻ không có chat_url nên KHÔNG gửi luatchung; prompt
    #    bây giờ đã cắt hết phần bối cảnh nên chạy kiểu đó là ảnh mất bối cảnh.
    #    ẢNH GỐC TRƯỚC: SF con đính master làm refs.bg, master chưa có ảnh thì cả
    #    lô dừng vì "thiếu ref". Nên vòng này chỉ xếp master còn thiếu; SF con bám
    #    nó đợi vòng sau, lúc master đã có ảnh.
    # CHẶN THEO MỌI REF, KHÔNG CHỈ `bg`.
    #
    # Bản cũ chỉ xét thẻ địa điểm. Đủ cho scene thường, nhưng KHÔNG đủ cho scene
    # REF: thẻ trang phục `REF_X_..._FULL` trỏ `chars: [REF_X_PORTRAIT]`, mà
    # portrait chưa có ảnh thì cả lô dừng vì "thiếu ref". Xét cả `chars` thì
    # portrait tự động chạy trước, trang phục đợi vòng sau — đúng thứ tự phải có.
    def _ref_cua(f: dict) -> list:
        r = f.get("refs") or {}
        return [x for x in ([r.get("bg")] + list(r.get("chars") or [])) if x]

    thieu_bg = sorted({x for f in sfs for x in _ref_cua(f) if not BOARD.find_file(x)})
    san_sang = [f["id"] for f in sfs
                if not BOARD.find_file(f["id"])
                and not any(x in thieu_bg for x in _ref_cua(f))]
    miss_img = [f["id"] for f in sfs if not BOARD.find_file(f["id"])]
    # KHỬ TRÙNG, GIỮ THỨ TỰ. Một thẻ vừa là "ref mà thẻ khác đang đợi" vừa là
    # "sẵn sàng chạy" — chân dung REF là ca điển hình: nó nằm trong `thieu_bg`
    # (mấy thẻ trang phục đợi nó) và cũng nằm trong `san_sang` (bản thân nó
    # không đợi ai). Không khử thì lô có hai lần cùng một SF, xin ChatGPT 2 ảnh
    # cho 1 thẻ và board đếm lệch ngay từ đầu.
    xep = [i for i in dict.fromkeys(thieu_bg + san_sang)
           if not _job_is_active(i)
           and _auto_allow(st, i, cyc, ghi=False)]
    if xep:
        _data = BOARD.read()
        nhom: dict[str, list[str]] = {}
        for i in xep:
            nhom.setdefault(_nhom_auto_cua(i, sc.get("id", ""), _data), []).append(i)
        # Dựng danh sách TASK theo đúng thứ tự sẽ chạy: mỗi task ≤ TRAN_MAY_TU_GOM
        # ảnh và CÙNG MỘT ĐỊA ĐIỂM (một tin nhắn chỉ mang được một `luatchung`).
        tasks: list[tuple[str, list[str]]] = []
        for m, xs in sorted(nhom.items(), key=lambda kv: min(map(_uu_tien, kv[1]))):
            xs.sort(key=_uu_tien)
            for lo in _chia_lo(xs, lambda i: _ref_id_cua_sf(i, _data),
                               TRAN_MAY_TU_GOM, TRAN_REF,
                               allow_internal_dependencies=_live_executor_enabled()):
                tasks.append((m, lo))

        # ĐẨY HẾT MỌI TASK VÀO HÀNG CHỜ NGAY, theo đúng thứ tự T1 → T2 → T3.
        #
        # Từng thử cách giữ hàng chờ mỏng (chỉ đủ việc cho số tab đang rảnh) rồi
        # đẩy dần. User chốt 2026-08-12: KHÔNG. Việc nào đã quyết chạy thì phải
        # nằm trong hàng chờ để theo dõi được — hàng chờ mỏng thì nhìn vào không
        # biết còn bao nhiêu việc phía sau, mà chờ ngoài hàng thì không đếm được,
        # không huỷ được, không biết thứ tự.
        # Chi phí gần như bằng không: một việc trong hàng chỉ tốn ~700 byte, và
        # thứ chặn tốc độ vẫn là số tab chứ không phải độ dài hàng.
        da_xep: list[list[str]] = []
        for m, lo in tasks:
            with AUTO_LOCK:
                if dung_gen() != auto_gen or AUTO.get(sc["id"]) is not st:
                    break
                ket_qua = _auto_giao_anh(sc, m, lo, _data)
                if ket_qua is not None and ket_qua.replayed:
                    # Ý định này đã được nhận từ vòng quét trước — auto không
                    # được tính thêm lượt thử, cũng không xếp lại. Việc thử lại
                    # là của RetryPolicy, không phải của người quét.
                    continue
                for i in lo:
                    _auto_allow(st, i, cyc)  # tính một lần thử: task này đi thật
                da_xep.append(lo)
        if da_xep:
            _LOG.info("[auto %s] đẩy %d task (%d ảnh) vào hàng chờ",
                      sc["id"], len(da_xep), sum(map(len, da_xep)))

    # 2) video còn thiếu, nhưng chỉ khi ảnh SF của shot đó đã có
    #    VÀ chỉ khi công tắc auto-video đang bật (mặc định tắt).
    miss_vid = [sh["id"] for sh in shots if not BOARD.video_file(sh["id"])]
    for sh in (shots if _auto_vid_doc() else []):
        if BOARD.video_file(sh["id"]) or not BOARD.find_file(sh.get("sf", "")):
            continue
        with AUTO_LOCK:
            if dung_gen() != auto_gen or AUTO.get(sc["id"]) is not st:
                break
            # CHẶN CẢ 'queued'. Chỉ chặn 'running' thì shot đang nằm chờ được
            # xếp thêm lượt nữa — với video, lượt thừa là một lần trừ credit cho
            # đúng shot sắp dựng xong.
            if _job_is_active(sh["id"]):
                continue
            if not _auto_allow(st, sh["id"], cyc, ghi=False):
                continue
            ket_qua = _auto_giao_video(sc, sh)
            if ket_qua is not None and ket_qua.replayed:
                continue
            _auto_allow(st, sh["id"], cyc)
            _LOG.info("[auto %s] video %s (lần %d)",
                      sc["id"], sh["id"], st["try"][sh["id"]])

    return len(miss_img), len(sfs), len(miss_vid), len(shots)


def _auto_runner():
    cyc = 0
    while True:
        # Chờ tới vòng sau, NHƯNG tỉnh ngay nếu user vừa bật một scene.
        _AUTO_WAKE.wait(AUTO_PERIOD)
        _AUTO_WAKE.clear()
        if not _browser_execution_enabled():
            continue
        cyc += 1
        try:
            with AUTO_LOCK:
                if not AUTO:
                    continue
                ids = set(AUTO)
            with open(BOARD.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for sc in data.get("scenes", []):
                if sc["id"] not in ids:
                    continue
                with AUTO_LOCK:
                    st = AUTO.get(sc["id"])
                if st is None:
                    continue
                mi, ni, mv, nv = _auto_scene(sc, st, cyc)
                st["stat"] = {"img": [ni - mi, ni], "vid": [nv - mv, nv]}
                if not mi and not mv and (ni or nv):
                    with AUTO_LOCK:
                        AUTO.pop(sc["id"], None)
                    _LOG.info("[auto %s] XONG — %d ảnh, %d video. Tự tắt.", sc["id"], ni, nv)
        except Exception as e:
            _LOG.warning("auto lỗi: %s", e)


def _auto_status() -> dict:
    """Trạng thái cho giao diện: scene_id -> {img:[xong,tổng], vid:[xong,tổng]}"""
    with AUTO_LOCK:
        return {k: v.get("stat", {}) for k, v in AUTO.items()}



# ───────────────────────── LƯU BẢN HÀNG NGÀY ────────────────────────────────
# macOS chặn launchd/cron truy cập thư mục Desktop, nên việc chạy theo lịch được
# gắn vào chính board — tiến trình vốn đã mở suốt lúc làm việc.
# Qua 23:00 mà hôm nay chưa có bản nào thì lưu; board tắt cả ngày thì lần mở
# tiếp theo sẽ lưu bù, không mất ngày nào.

LUU_GIO = 23          # giờ trong ngày để chốt bản
_luu_lock = threading.Lock()


def _ngay_da_luu() -> set:
    snap = os.path.join(BOARD.dir, ".snapshots")
    if not os.path.isdir(snap):
        return set()
    return {n[:10] for n in os.listdir(snap) if len(n) >= 10}


def _chay_luu_ban(ghi_chu: str) -> tuple[bool, str]:
    sh = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "luu-ban.sh")
    if not os.path.isfile(sh):
        return False, "không tìm thấy luu-ban.sh"
    with _luu_lock:
        try:
            r = subprocess.run(["/bin/bash", sh, ghi_chu], capture_output=True, text=True,
                               timeout=600, cwd=os.path.dirname(sh))
            ok = r.returncode == 0
            return ok, (r.stdout or r.stderr).strip()[-400:]
        except Exception as e:
            return False, str(e)[:200]


def _luu_ban_runner():
    while True:
        try:
            now = datetime.datetime.now()
            hom_nay = now.strftime("%Y-%m-%d")
            if hom_nay not in _ngay_da_luu():
                # qua giờ chốt HÔM NAY, hoặc board vừa mở mà hôm qua bị lỡ
                if now.hour >= LUU_GIO:
                    ok, msg = _chay_luu_ban("bản tự động cuối ngày")
                    _LOG.info("[luu-ban] %s — %s", "xong" if ok else "LỖI",
                              msg.replace("\n", " · "))
        except Exception as e:
            _LOG.warning("[luu-ban] lỗi: %s", e)
        time.sleep(600)        # 10 phút một lần


def _accounts_status() -> list[dict]:
    """Trạng thái từng tài khoản cho giao diện."""
    out = []
    with ACC_LOCK:
        accs = [dict(a) for a in ACCOUNTS]
    for a in accs:
        ep = _ep(a)
        chrome = _endpoint_alive(ep)
        songs = sum(1 for k, t in WORKERS.items() if k[0] == a["port"] and t.is_alive())
        out.append({**a, "endpoint": ep, "chrome": chrome,
                    "dead": DEAD.get(ep, ""), "worker": songs > 0,
                    "nghi_den": DEAD_DEN.get(ep, 0),
                    "tabs": max(1, int(a.get("tabs") or 1)), "tho_song": songs,
                    **_dem_xem(a["port"])})
    return out


def _alive(sess) -> bool:
    """Phiên còn sống thật không, hay chỉ còn cờ ready từ trước khi tab bị đóng."""
    try:
        return sess is not None and getattr(sess, "ready", False) and sess.page is not None \
               and not sess.page.is_closed()
    except Exception:
        return False


# Playwright/CDP dùng chung cho cả ChatGPT lẫn Grok TRONG CÙNG một luồng thợ —
# hai sync_playwright().start() độc lập trong cùng 1 luồng sẽ xung đột ngầm
# (bài học từ grokpipe/runner.py). Mỗi luồng thợ có instance riêng qua _TL,
# nhờ vậy N tài khoản chạy song song mà không giẫm chân nhau.


def _bo_hub():
    """Vứt Playwright của luồng này cho SẠCH, kể cả khi stop() ném lỗi.

    Mỗi sync_playwright().start() dựng một asyncio loop ĐANG CHẠY trong luồng.
    Còn sót một cái là lần start() sau ném "Playwright Sync API inside the
    asyncio loop" — thông báo đó che mất lỗi thật, thường là Chrome debug chết.
    """
    pw = getattr(_TL, "pw", None)
    if pw is not None:
        try:
            pw.stop()
        except Exception as e:
            _LOG.warning("không dừng gọn được Playwright cũ: %s", e)
    _TL.pw = None
    _TL.browser = None
    _TL.ctx = None
    _TL.sess = None
    _TL.gsess = None


def _hub():
    ctx = getattr(_TL, "ctx", None)
    if ctx is not None:
        try:
            # ⚠ `ctx.pages` KHÔNG chứng minh được context còn sống: nó đọc bộ nhớ
            # đệm trong tiến trình nên context đã chết vẫn trả về list (rỗng) mà
            # không ném. Chrome debug đóng/mở lại là board ôm context zombie, rồi
            # ngã tận trong `new_page()` với "Target page, context or browser has
            # been closed" — và người dùng nhận thông báo sai địa chỉ "chưa đăng
            # nhập". `is_connected()` mới thật sự hỏi tới Chrome.
            br = getattr(_TL, "browser", None)
            if br is not None and not br.is_connected():
                raise RuntimeError("Chrome debug đã ngắt kết nối")
            ctx.pages
            return ctx
        except Exception:
            # Context chết → PHẢI dừng hẳn Playwright cũ trước khi start cái mới.
            # Bỏ qua bước này là hai sync_playwright() cùng sống trong một luồng,
            # đúng cái xung đột ngầm mà ghi chú phía trên đã cảnh báo.
            _bo_hub()
    elif getattr(_TL, "pw", None) is not None:
        # ctx rỗng mà pw còn sống = lần trước start() xong rồi mới ngã ở
        # connect_over_cdp, để lại một Playwright mồ côi. Không dọn ở đây thì
        # mọi lần bấm sau đều báo lỗi asyncio loop thay vì lỗi Chrome thật.
        _bo_hub()

    from playwright.sync_api import sync_playwright
    _TL.pw = sync_playwright().start()
    try:
        browser = _TL.pw.chromium.connect_over_cdp(_TL.endpoint)
        _TL.browser = browser  # giữ lại để lần sau còn hỏi được is_connected()
        _TL.ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    except Exception as e:
        # Trả luồng về trạng thái sạch rồi mới ném, để lần bấm sau còn báo đúng
        # bệnh chứ không đổ sang lỗi asyncio loop khó hiểu.
        _bo_hub()
        # Nối hụt TRONG KHI cổng vẫn trả lời HTTP = cửa sổ nửa vời. Đánh dấu để
        # `_endpoint_alive` ngừng báo sống, supervisor mới chịu mở lại.
        if _ping_http(_TL.endpoint):
            _bao_ws_hong(_TL.endpoint, str(e))
        raise RuntimeError(
            f"Không nối được Chrome debug ở {_TL.endpoint} ({e}). "
            "Mở lại cửa sổ Chrome debug của tài khoản này rồi thử lại."
        ) from e
    return _TL.ctx


def _session():
    """Tạo/tái dùng phiên ChatGPT của LUỒNG NÀY — tự mở lại nếu phiên cũ đã chết."""
    s = getattr(_TL, "sess", None)
    if _alive(s):
        return s
    _TL.sess = None
    from grokpipe.executors.image_chatgpt import ChatGPTSession
    # slot = chỗ ngồi của thợ này. Mỗi slot một TAB riêng trong cùng cửa sổ
    # Chrome, nhờ vậy một tài khoản chạy được nhiều việc song song mà hai luồng
    # không giẫm lên ô soạn của nhau (Grok đã làm vậy từ trước).
    s = ChatGPTSession(user_data_dir=os.path.expanduser("~/.grokpipe-chrome"),
                       logger=_LOG, headless=False, cdp_endpoint=None,
                       shared_ctx=_hub(), slot=getattr(_TL, "slot", 0))
    if not s.start():
        vi = getattr(s, "loi_cuoi", "") or "không rõ lý do — xem log board"
        raise RuntimeError(f"Không nối được ChatGPT ở {_TL.endpoint} ({vi}). "
                           "Mở Chrome debug và đăng nhập rồi thử lại.")
    _TL.sess = s
    return s


def _grok():
    """Phiên Grok của LUỒNG NÀY."""
    s = getattr(_TL, "gsess", None)
    if _alive(s):
        return s
    _TL.gsess = None
    from grokpipe.executors.video_grok import GrokSession
    s = GrokSession(cdp_endpoint=None, logger=_LOG, resolution="720p",
                    shared_ctx=_hub(), slot=getattr(_TL, "slot", 0))
    if not s.start():
        raise RuntimeError(f"Không nối được Grok ở {_TL.endpoint}. "
                           "Mở Chrome debug và đăng nhập grok.com rồi thử lại.")
    _TL.gsess = s
    return s


def _giu_dau_ban(data: dict) -> int:
    """Giữ lại `picked`/`vpicked` của bản trên ĐĨA khi giao diện ghi đè board.

    CỬA SỔ ĐUA THẬT, đã tính ra được: giao diện gom thao tác rồi POST NGUYÊN cả
    board sau 450ms. Trong 450ms đó thợ có thể ghi xong một ảnh — `set_current`
    + `_mark_picked` — và bản POST (chụp từ trước) không có dấu ấy, nên ghi đè là
    xoá mất. Ảnh không mất (nó đã nằm trong assets/ và versions/), nhưng board
    quên bản nào đang dùng: dãy bản không tô đúng ô, và mọi phép kiểm dựa vào
    `picked` đọc ra chỗ trống.

    HAI TRƯỜNG NÀY THUỘC VỀ THỢ, không thuộc giao diện. Người dùng đổi bản đang
    dùng bằng đường riêng (`/api/pick-version`, `/api/pick-vversion`) chứ không
    qua đây, nên lấy theo đĩa là luôn đúng.
    """
    try:
        cu = BOARD.read()
    except Exception:
        return 0
    dau_sf = {f["id"]: f.get("picked") for s in cu.get("scenes", [])
              for f in s.get("sfs", []) if f.get("picked")}
    dau_sh = {sh["id"]: sh.get("vpicked") for s in cu.get("scenes", [])
              for sh in s.get("shots", []) if sh.get("vpicked")}
    n = 0
    for s in data.get("scenes", []):
        for f in s.get("sfs", []):
            v = dau_sf.get(f.get("id"))
            if v and f.get("picked") != v:
                f["picked"] = v; n += 1
        for sh in s.get("shots", []):
            v = dau_sh.get(sh.get("id"))
            if v and sh.get("vpicked") != v:
                sh["vpicked"] = v; n += 1
    if n:
        _LOG.info("giữ lại %d dấu bản-đang-dùng mà giao diện chưa kịp thấy", n)
    return n


def _sync_startframe(data: dict) -> int:
    """Dòng 'Start frame: X' trong prompt video PHẢI luôn khớp shot['sf'].

    Đổi SF bằng ô chọn trên giao diện chỉ sửa shot['sf'], không đụng tới prompt —
    thế là ảnh mang đi tạo video một đằng, prompt tả một nẻo. Đồng bộ ở đây, chỗ
    duy nhất mọi thay đổi từ giao diện đều đi qua.
    """
    n = 0
    for sc in data.get("scenes", []):
        for sh in sc.get("shots", []):
            sf, pr = sh.get("sf"), sh.get("prompt") or ""
            if not sf or not pr:
                continue
            m = re.search(r"Start frame:\s*(\S+)", pr)
            if m and m.group(1) != sf:
                sh["prompt"] = pr.replace(m.group(0), "Start frame: " + sf, 1)
                n += 1
    if n:
        _LOG.info("đồng bộ %d prompt video theo SF mới trên giao diện", n)
    return n


def _mark_picked(ident: str, key: str, filename: str) -> None:
    """Ghi lại BẢN NÀO đang được dùng làm bản hiển thị/tải về.

    key='picked' cho ảnh SF, key='vpicked' cho video. Không có nó thì sau một
    lần render nữa là không ai biết bản đang hiện là bản nào trong dãy.
    """
    try:
        data = BOARD.read()
        hit = False
        for sc in data.get("scenes", []):
            for it in list(sc.get("sfs", [])) + list(sc.get("shots", [])):
                if it.get("id") == ident:
                    it[key] = filename; hit = True
        if hit:
            BOARD.write(data)
    except Exception as e:
        _LOG.warning("không ghi được %s cho %s: %s", key, ident, e)


def can_touch_image(sf_id: str) -> bool:
    """Ảnh user ĐÃ DUYỆT thì không được xoá/ghi đè — kể cả khi nghi ngờ sai ref.
    Nghi ngờ thì BÁO user và để user quyết, không tự ghi đè quyết định của họ."""
    try:
        for sc in BOARD.read().get("scenes", []):
            for f in sc.get("sfs", []):
                if f.get("id") == sf_id:
                    return f.get("status") != "approved"
    except Exception:
        pass
    return True


def _nguoi_cua_ref(rid: str) -> str:
    """Tên nhân vật trong id ref, '' nếu ref này không phải của nhân vật.

    Nhận diện bằng ĐUÔI `_PORTRAIT` / `_FULL` — đó là thứ duy nhất phân biệt ref
    nhân vật với bối cảnh (`REF_NHATHOTIEC_CHIEU`) và đạo cụ (`REF_PROP_VONGCO`),
    hai loại không bao giờ được đụng tới khi hạ ref.
    """
    if not (rid.endswith("_PORTRAIT") or rid.endswith("_FULL")):
        return ""
    phan = rid.split("_")
    return phan[1] if len(phan) > 1 else ""


def _ha_ref_nhan_vat_phu(ids: list[str], tran: int, tu_nguoi_thu: int = 5) -> list[str]:
    """Tràn trần thì nhân vật PHỤ chỉ gửi `_FULL`, bỏ `_PORTRAIT`. Giữ thứ tự.

    Nhân vật phụ = từ người thứ `tu_nguoi_thu` trở đi theo THỨ TỰ XUẤT HIỆN trong
    danh sách ref (user chốt 2026-08-15). Bốn người đầu là nhân vật chính và phản
    diện chính, luôn giữ đủ cặp.

    Vì sao bỏ portrait chứ không bỏ full: full mang cả DÁNG lẫn TRANG PHỤC, còn
    portrait chỉ neo khuôn mặt. Ca S5 (xem `_generate_lo_ruot`) đã cho thấy chiều
    ngược lại hỏng ra sao — chỉ gửi portrait thì model tự bịa áo. Giữ full là dồn
    hết rủi ro vào khuôn mặt của nhân vật nền, thứ khán giả không nhớ mặt.

    Người phụ mà KHÔNG có bản `_FULL` thì giữ nguyên portrait: bỏ nốt là mất hẳn
    nhân vật khỏi tin, model bịa ra cả người chứ không riêng khuôn mặt.

    Hàm này chỉ HẠ, không cắt tới trần bằng mọi giá. Hạ xong vẫn tràn thì việc
    còn lại là chốt lô sớm — xem `_chia_lo`.
    """
    if len(ids) <= tran:
        return list(ids)
    thu_tu: list[str] = []
    for rid in ids:
        ng = _nguoi_cua_ref(rid)
        if ng and ng not in thu_tu:
            thu_tu.append(ng)
    phu = set(thu_tu[tu_nguoi_thu - 1:])
    co_full = {_nguoi_cua_ref(r) for r in ids if r.endswith("_FULL")}
    return [r for r in ids
            if not (r.endswith("_PORTRAIT")
                    and _nguoi_cua_ref(r) in phu
                    and _nguoi_cua_ref(r) in co_full)]


def _ref_id_cua_sf(sf_id: str, data: dict) -> list[str]:
    """ID ref của một SF, dùng để đếm khi chia lô. Thiếu file thì vẫn tính —
    ref thiếu là lượt hỏng, không phải lượt nhẹ ref."""
    try:
        return _sf_attachments(BOARD.get_sf(sf_id, data) or {"id": sf_id})[2]
    except Exception:
        return []


def _chia_lo(
        sf_ids: list[str], ref_cua, tran_sf: int, tran_ref: int, *,
        allow_internal_dependencies: bool = False) -> list[list[str]]:
    """Chia danh sách SF thành các lô ≤ `tran_sf` ảnh VÀ ≤ `tran_ref` ref.

    Trần ref mới là trần ràng buộc thật (log ALTAR 2026-08-15: lô 5 ref chạy
    sạch, lô 14–17 ref hỏng mọi lượt và tắt sạch 6 tài khoản). Số SF rơi ra từ
    đó: 6 SF mà đã chạm 10 ref thì lô đó chỉ 6 SF.

    Đi ĐÚNG THỨ TỰ SHOT, đầy thì chốt — không xếp lại cho lô đầy hơn. Shot liền
    nhau nằm cùng lô thì đoạn liền mạch nhất được sinh trong cùng một lượt.

    Ref dùng chung giữa các SF chỉ tính MỘT lần, nên thêm một SF dùng lại đúng bộ
    ref cũ là miễn phí. Lô đắt ref là lô đông nhân vật — đúng loại lô đang hỏng.

    Một SF mà tự nó đã vượt trần vẫn được gửi: lô một ảnh không chẻ nhỏ hơn được
    nữa, chặn là chặn việc của user (user chốt 2026-08-15).
    """
    ra: list[list[str]] = []
    lo: list[str] = []
    for i in sf_ids:
        thu = _ha_ref_nhan_vat_phu(
            list(dict.fromkeys([r for x in lo + [i] for r in ref_cua(x)])), tran_ref)
        # PHỤ THUỘC CẮT LÔ TRƯỚC CẢ TRẦN.
        #
        # Thẻ trang phục đính chân dung của chính nhân vật đó làm ref. Nhét cả
        # hai vào MỘT tin thì lúc gửi, chân dung chưa có ảnh → `_sf_attachments`
        # báo thiếu ref → `_generate_lo_ruot` dán lỗi cho CẢ LÔ và ném. Chân dung
        # chết theo, nên lần sau chạy lại vẫn thiếu đúng nó: lô tự khoá chính
        # mình, chạy bao nhiêu lần cũng thế (đo trên AISLE-SEVEN 2026-08-15: 14
        # task kẹt kiểu này).
        #
        # Board đã gác quan hệ y hệt cho ĐỊA ĐIỂM bằng `_cong_master`; nhân vật
        # thì chưa có cổng nào. Chặn ở đây là chặn cho mọi loại phụ thuộc, không
        # riêng nhân vật.
        if (lo and not allow_internal_dependencies
                and set(ref_cua(i)) & set(lo)):
            ra.append(lo)
            lo = []
        elif lo and (len(lo) >= tran_sf or len(thu) > tran_ref):
            ra.append(lo)
            lo = []
        lo.append(i)
    if lo:
        ra.append(lo)
    return ra
def _sf_attachments(
        sf: dict, *, skip_ids=()) -> tuple[list[str], list[str], list[str]]:
    """Resolve refs của SF; tự kèm full-body khi nhân vật có sẵn ảnh FULL.

    MỖI NHÂN VẬT CHỈ ĐÍNH TỐI ĐA 1 PORTRAIT + 1 FULL. Nếu SF đã chỉ định sẵn một
    bản full-body theo trạng thái trang phục của cảnh (REF_MAYA_OFFICE_FULL,
    REF_HELEN_HOSPITAL_FULL...) thì KHÔNG tự thêm bản mặc định REF_MAYA_FULL nữa —
    đính thừa một full-body vừa làm ChatGPT tạo ảnh lâu hơn, vừa dễ lẫn trang phục."""
    refs = sf.get("refs") or {}
    chars = list(refs.get("chars") or [])
    def person(rid: str) -> str:
        parts = rid.split("_")
        return parts[1] if len(parts) > 1 else rid

    explicit_full = {person(c) for c in chars if c.endswith("_FULL")}
    # ẢNH BỐI CẢNH ĐÍNH ĐẦU TIÊN: khi upload rớt file thì file CUỐI rụng trước,
    # mà mất bối cảnh là hỏng cả khung (nhân vật còn có thể đoán, bối cảnh thì
    # model bịa ra một căn phòng khác hẳn).
    requested: list[str] = [refs["bg"]] if refs.get("bg") else []
    for rid in chars:
        requested.append(rid)
        if rid.endswith("_PORTRAIT") and person(rid) not in explicit_full:
            full_id = rid.removesuffix("_PORTRAIT") + "_FULL"
            if BOARD.find_file(full_id):
                requested.append(full_id)
    # Giữ đúng thứ tự portrait → full-body của từng nhân vật, không đính trùng.
    skipped = {str(ref_id) for ref_id in skip_ids}
    ids = [ref_id for ref_id in dict.fromkeys(requested)
           if ref_id not in skipped]
    attach, missing = [], []
    for rid in ids:
        p = BOARD.find_file(rid)
        (attach.append(p) if p else missing.append(rid))
    return attach, missing, ids


def _gen_video(shot_id: str) -> bool:
    """Chạy trong một luồng thợ. Lỗi hết lượt / cửa sổ chết được ném lên cho
    worker phân loại và chuyển việc sang tài khoản khác.

    Trả False khi user bấm DỪNG RIÊNG — worker đọc cờ này để KHÔNG xếp lại.
    Ném exception cho mọi lỗi thật."""
    # NÚT ■ DỪNG RIÊNG PHẢI ĂN CẢ Ở ĐƯỜNG VIDEO (vá 2026-08-14). Trước đây
    # `/api/dung-viec` vẫn nhận và vẫn ghi vào DUNG_RIENG, nhưng cờ đó chỉ được
    # đọc trong `_generate_lo_ruot` — tức đường ẢNH. Thợ video không soi bao giờ,
    # nên job nằm mãi ở "đang dừng…" trong khi Grok vẫn render và vẫn trừ credit.
    if shot_id in DUNG_RIENG:
        with HUY_LOCK:
            DUNG_RIENG.discard(shot_id)
        JOBS[shot_id] = {"state": "error", "msg": "đã dừng riêng — chưa tiêu credit"}
        _LOG.info("video %s bị user dừng riêng trước khi chạy", shot_id)
        return False
    sh, sc = BOARD.get_shot(shot_id)
    if not sh:
        raise RuntimeError("Không tìm thấy video này")
    prompt = (sh.get("prompt") or "").strip()
    if not prompt:
        raise RuntimeError("Chưa có prompt video")
    sf_file = BOARD.find_file(sh.get("sf") or "")
    if not sf_file:
        raise RuntimeError(f"Start frame {sh.get('sf')} chưa có ảnh")

    dur = float(sh.get("dur") or 10)
    ok, out = False, None
    for attempt in range(2):        # 1 lần mở lại phiên nếu tab (không phải cửa sổ) chết
        JOBS[shot_id] = {"state": "running",
                         "msg": f"Grok đang dựng {int(dur)}s…{_acct_label()}"}
        try:
            g = _grok()
            with BOARD_LOCK:
                out = BOARD.next_vversion(shot_id)
            # Grok đẻ nhiều clip cho MỘT submit và trừ credit từng bản. Đưa hàm
            # xin đường dẫn xuống để bản thừa cũng vào versions/ — đã trả tiền
            # thì phải có mà so, đừng vứt.
            def _duong_them():
                with BOARD_LOCK:
                    return BOARD.next_vversion(shot_id)
            ok = g.generate(prompt, sf_file, out, duration_s=dur,
                            duong_them=_duong_them,
                            nen_dung=lambda: shot_id in DUNG_RIENG)
            if ok and os.path.exists(out):
                _dem_cong()
                break
            # PHÂN BIỆT "USER DỪNG" VỚI "GROK HỎNG". Cả hai đều cho ok=False,
            # nhưng ném lỗi cho ca thứ nhất là vừa báo sai vừa đẩy việc vào vòng
            # thử lại — đúng thứ user vừa bấm dừng để tránh.
            if shot_id in DUNG_RIENG:
                with HUY_LOCK:
                    DUNG_RIENG.discard(shot_id)
                JOBS[shot_id] = {"state": "error", "msg": "đã dừng riêng — chưa tiêu credit"}
                _LOG.info("video %s: user bấm dừng trước lúc submit", shot_id)
                return False
            raise RuntimeError("Grok không trả về video")
        except Exception as e:
            if attempt == 0 and _is_dead_session_error(e) and _endpoint_alive(_TL.endpoint):
                _release_tl()
                JOBS[shot_id] = {"state": "running", "msg": "tab đã đóng → mở lại phiên…"}
                continue
            raise
    if not ok or not out or not os.path.exists(out):
        raise RuntimeError("Grok không trả về video")
    with BOARD_LOCK:
        # VIDEO MỚI VỀ THÌ ĐÈ, KỂ CẢ SHOT ĐÃ DUYỆT (user chốt 2026-08-14, cùng
        # luật với ảnh SF). `vstatus: approved` là DẤU để user quản lý, không
        # phải khoá kỹ thuật. Bản cũ vẫn nằm trong videos/versions/ nên chọn lại
        # được. Giữ bản cũ như trước là đốt credit Grok mà màn hình không đổi gì
        # — hỏng câm, đúng thứ khó lần nhất.
        BOARD.set_video(shot_id, out)
        _mark_picked(shot_id, "vpicked", os.path.basename(out))
    with HUY_LOCK:               # lượt này xong rồi, cờ dừng không còn ý nghĩa
        DUNG_RIENG.discard(shot_id)
    JOBS[shot_id] = {"state": "done", "msg": "xong"}
    return True


def _ten_gon(khoa: str | None, data: dict | None = None) -> str:
    """Tên ngắn của một nhóm, để nhét vào dòng trạng thái.

    ĐỪNG cắt cứng `khoa[5:]`: phép đó viết cho tiền tố `SF-M-` thời còn master,
    nay tên thẻ địa điểm là `SF-S6-01` nên cắt 5 ký tự ra chuỗi rác '6-01'.
    Lấy `label` của thẻ; không có thì trả nguyên id."""
    if not khoa:
        return "lẻ"
    if khoa.startswith("NV:"):
        return khoa[3:]
    if khoa == "PROP":
        return "đạo cụ"
    try:
        f = (BOARD.get_sf(khoa) or {}) if data is None else \
            {x["id"]: x for s in data.get("scenes", []) for x in s.get("sfs", [])}.get(khoa, {})
        return (f.get("label") or khoa).split("—")[0].strip()[:28] or khoa
    except Exception:
        return khoa


def _khoa_la_the(khoa: str | None) -> bool:
    """Khoá nhóm này có trỏ vào MỘT THẺ SF thật không?

    Hai loại khoá cùng tồn tại: id thẻ địa điểm (`SF-S6-01`) và khoá tổng hợp
    ('NV:TÊN' cho nhân vật, 'PROP' cho đạo cụ) — loại sau không có thẻ nào để
    bám nên chat của chúng lưu ở gốc file."""
    return bool(khoa) and not khoa.startswith("NV:") and khoa != "PROP"


def _la_the_dia_diem(f: dict) -> bool:
    """Thẻ này có phải THẺ ĐỊA ĐIỂM không — tức chỗ dừng khi leo refs.bg.

    Dấu hiệu chuẩn là **có `luatchung`**: khối luật chung chỉ đặt trên thẻ địa
    điểm, và board gửi nó một lần lúc mở chat. Đó cũng là định nghĩa của 'một
    địa điểm = một đoạn chat'.

    Tiền tố `SF-M-` là quy ước CŨ (bỏ 2026-08-07). Vẫn nhận để dự án cũ chạy
    được — ở đó master nối vào master (`BATH → FOYER → MANSION-EXT`), nên nếu
    chỉ leo tới gốc thì cả toà nhà gộp thành MỘT nhóm: `luatchung` của phòng
    ĐẦU TIÊN sẽ khoá look cho mọi phòng còn lại, vì board chỉ gửi nó một lần
    lúc mở chat. Bếp thừa hưởng bảng màu và ánh sáng của phòng ngủ, im lặng."""
    return bool((f.get("luatchung") or "").strip()) or f["id"].startswith("SF-M-")


def _master_cua(sf_id: str, data: dict | None = None) -> str | None:
    """Leo chuỗi refs.bg lên tới THẺ ĐỊA ĐIỂM — đó chính là ĐOẠN CHAT.

    Không tìm thấy thẻ nào mang dấu hiệu địa điểm thì lấy GỐC của chuỗi: thẻ
    đầu tiên không còn `refs.bg` nào để leo tiếp."""
    data = data or BOARD.read()
    tat = {f["id"]: f for s in data.get("scenes", []) for f in s.get("sfs", [])}
    f, da = tat.get(sf_id), set()
    while f and not _la_the_dia_diem(f) and f["id"] not in da:
        da.add(f["id"])
        ke = tat.get((f.get("refs") or {}).get("bg") or "")
        if not ke:
            break            # hết chuỗi → chính f là gốc
        f = ke
    return f["id"] if f else None


def _lan_dia_diem(nhom: dict, data: dict) -> str:
    """Các SF được tích có thuộc NHIỀU địa điểm không? Trả lời dạng câu lỗi, '' = ổn.

    Chỉ đếm nhóm CÓ `luatchung` (địa điểm thật). Nhân vật và đạo cụ không mang
    luật chung nên tích mấy nhóm cũng không đá nhau."""
    dd = {m: xs for m, xs in nhom.items()
          if m and _la_the_dia_diem(BOARD.get_sf(m) or {"id": m})}
    if len(dd) < 2:
        return ""
    mo = " · ".join(f"{_ten_gon(m, data)}: {', '.join(sorted(xs))}"
                    for m, xs in list(dd.items())[:4])
    return (f"Đang tích lẫn {len(dd)} địa điểm — {mo}. "
            "Mỗi lần chỉ tích các ảnh CÙNG MỘT địa điểm: một tin nhắn chỉ mang "
            "được một khối luật chung (nội thất · bảng màu · ánh sáng · trục).")


def _cong_master(master: str | None, data: dict | None = None) -> str:
    """CỔNG CHẶN: SF con của một địa điểm chỉ được chạy khi THẺ ĐỊA ĐIỂM ĐÃ CÓ
    ẢNH (picked). Trả '' nếu được đi tiếp, ngược lại trả lý do.

    Vì sao chặn cứng chứ không chỉ nhắc: ảnh thẻ địa điểm là BẢN NEO — board đính
    nó làm `refs.bg` cho mọi khung trong địa điểm, nên nó khoá bảng màu, ánh sáng
    và trục cho cả cụm. Chạy khung con khi chưa có neo là mỗi khung tự bịa một
    look, và sai kiểu đó chỉ lộ ra khi đã dựng xong cả scene.

    Nếu thẻ đầu chuỗi không phải là thẻ địa điểm (tức thiếu `luatchung`),
    nó cũng sẽ bị chặn cứng, không cho chạy lọt lưới.

    Nhóm nhân vật (`NV:`) và đạo cụ (`PROP`) không có thẻ địa điểm nên không gác.
    """
    if not master or not _khoa_la_the(master):
        return ""
    if data is None:
        f = BOARD.get_sf(master) or {}
    else:
        f = {x["id"]: x for s in data.get("scenes", [])
             for x in s.get("sfs", [])}.get(master) or {}
    
    if not f:
        return f"không tìm thấy thẻ gốc {master}"
    if not _la_the_dia_diem(f):
        return f"thẻ gốc {master} thiếu luatchung (không phải thẻ địa điểm)"
    
    # KIỂM ĐÚNG PHÉP MÀ BÊN XẾP VIỆC DÙNG: `find_file()`, tức có ảnh trong
    # `assets/` hay không — KHÔNG chỉ đọc `picked`.
    #
    # Hai phép kiểm lệch nhau là một vòng lặp vô tận (bắt được 2026-08-14 với
    # 148 việc lỗi cùng một câu): `_auto_scene` xếp việc theo `find_file()` nên
    # thấy ảnh và cho chạy, còn cổng này đọc `picked` nên chặn — auto xếp lại,
    # cổng chặn lại, mãi mãi. Ảnh nằm trong `assets/` mà `picked` rỗng là chuyện
    # bình thường: ảnh user tự dán vào là bản chuẩn tuyệt đối và không đi qua
    # đường chọn bản bao giờ.
    if not f.get("picked") and not BOARD.find_file(master):
        return f"thẻ địa điểm {master} CHƯA CÓ ẢNH"

    return ""


def _nhom_cua(sf_id: str, data: dict | None = None) -> str:
    """Khoá NHÓM của một thẻ — nhóm chính là ĐOẠN CHAT sẽ vẽ nó.

    Trước đây chỉ có MỘT khái niệm nhóm: leo refs.bg tới thẻ SF-M-… (địa điểm).
    Mọi thẻ không leo tới đâu rơi hết vào một thùng vô danh chung — thực tế là
    chân dung, trang phục và đạo cụ bị trộn làm một đống mấy chục thẻ, vừa khó
    hiểu vừa SAI VỀ NGHỀ: các bộ trang phục của một nhân vật bị rải ra nhiều chat
    trắng nên khuôn mặt trôi dần, trong khi lẽ ra chúng phải vẽ chung một chat với
    chân dung của chính người đó.

    Ba loại nhóm:
      · 'SF-M-…'  ĐỊA ĐIỂM  — leo được tới master (giữ nguyên hành vi cũ)
      · 'NV:TÊN'  NHÂN VẬT  — chân dung + mọi bộ trang phục của cùng một người
      · 'PROP'    ĐẠO CỤ    — ảnh gốc đồ vật, không dính nhân vật nào
      · ''        LẺ        — không xếp được, mỗi thẻ một chat riêng
    """
    # `_master_cua` TRẢ VỀ CHÍNH THẺ ĐÓ khi không leo được đi đâu (nó coi thẻ
    # cụt là "gốc của chuỗi"). Nhận bừa giá trị đó là mọi thẻ REF thành một
    # "địa điểm" của riêng nó, và hai nhánh NV:/PROP bên dưới thành CODE CHẾT.
    # Hậu quả đúng bằng thứ docstring này viết ra để tránh: chân dung và từng bộ
    # trang phục của một người mỗi cái một chat trắng, mặt trôi dần qua các bộ.
    # Đã đo 2026-08-07: 3 thẻ WARREN ra 3 nhóm 'dia_diem' riêng.
    # Nên: chỉ nhận `m` khi nó là thẻ ĐỊA ĐIỂM thật, hoặc là thẻ KHÁC (leo được).
    m = _master_cua(sf_id, data)
    if m and (m != sf_id or _la_the_dia_diem(
            ({x["id"]: x for s in (data or {}).get("scenes", [])
              for x in s.get("sfs", [])}.get(m) if data else BOARD.get_sf(m))
            or {"id": m})):
        return m
    if sf_id.startswith("REF_PROP_"):
        return "PROP"
    # Mọi REF_<TÊN>_… còn lại là ảnh của MỘT nhân vật: chân dung, toàn thân theo
    # trang phục, hay biến thể theo tuổi (REF_BABY_NEWBORN / REF_BABY_MONTHS).
    # Bắt theo tiền tố tên chứ đừng liệt kê hậu tố — mỗi lần thêm loại ảnh mới mà
    # quên cập nhật danh sách hậu tố là thẻ đó lại rơi ra thùng lẻ, im lặng.
    mt = re.match(r"^REF_([A-Z0-9]+)_", sf_id)
    if mt:
        return "NV:" + mt.group(1)
    return ""


def _nhom_auto_cua(sf_id: str, scene_id: str, data: dict) -> str:
    """Khoá gom lô RIÊNG cho auto; không đổi nhóm chat của đường chạy tay.

    Trong REF, portrait là các ảnh độc lập nên có thể sinh chung. Bốn nhân vật
    đầu giữ `_FULL` theo từng người để bảo toàn nhất quán; từ người thứ năm là
    nhân vật phụ và có thể gom `_FULL` chung một lô (vẫn qua `_chia_lo`).
    """
    if scene_id != "REF":
        return _nhom_cua(sf_id, data)
    if sf_id.startswith("REF_PROP_"):
        return "PROP"
    if sf_id.endswith("_PORTRAIT"):
        return "REF:PORTRAIT"
    if sf_id.endswith("_FULL"):
        mt = re.match(r"^REF_([A-Z0-9]+)_", sf_id)
        if mt:
            scene = next(
                (s for s in data.get("scenes", []) if s.get("id") == "REF"),
                {},
            )
            thu_tu: list[str] = []
            for f in scene.get("sfs", []):
                rid = f.get("id", "")
                portrait = re.match(r"^REF_([A-Z0-9]+)_PORTRAIT$", rid)
                if portrait and portrait.group(1) not in thu_tu:
                    thu_tu.append(portrait.group(1))
            return "NV:PHU" if mt.group(1) in thu_tu[4:] else "NV:" + mt.group(1)
    return "REF:BOI_CANH"


def _ten_nhom(khoa: str, tat: dict | None = None) -> tuple[str, str]:
    """(biểu tượng, tên đọc được) của một khoá nhóm — dùng chung cho mọi giao diện."""
    if not khoa:
        return "⚠️", "Thẻ lẻ — mỗi cái một chat riêng"
    if khoa == "PROP":
        return "🎬", "Đạo cụ"
    if khoa.startswith("NV:"):
        return "👤", "Nhân vật " + khoa[3:]
    nhan = ((tat or {}).get(khoa) or {}).get("label") or khoa
    return "📍", nhan


def _dan_ma_doc() -> bool:
    return False


def _dan_ma_ghi(on: bool) -> None:
    try:
        with open(MA_PATH, "w", encoding="utf-8") as f:
            json.dump({"on": bool(on)}, f)
    except OSError as e:
        _LOG.warning("không ghi được cờ dán mã: %s", e)


def _pl_ten(turn: int) -> str:
    return f"turn-{turn:04d}"


# Lệch bao nhiêu ảnh thì VẪN GIỮ nguyên lượt cho user bấm chọn tay, thay vì đốt
# thêm một lượt để mua lại thứ đã có trong tay.
PL_LECH_TOI_DA = 2

# Số lần gửi lại NGUYÊN TASK khi lượt về không trọn vẹn (0 ảnh · thiếu · kèm
# chữ). Hết số lần: còn ảnh thì ghép bấy nhiêu, không ảnh nào thì báo lỗi.
# User chốt 2 (2026-08-12) — mỗi lần thử lại là một lượt credit thật.
LO_THU_LAI = 2

# Giữ bao nhiêu lượt trong hộp chờ. Chỉ dọn lượt ĐÃ GẮN HẾT, cũ nhất trước —
# ảnh của lượt đó vẫn còn nguyên trong `versions/` nên không mất gì.
PL_GIU_TOI_DA = 40

PL_LOCK = threading.RLock()

# Cache đếm ảnh đang treo trong hộp chờ — xem `_pl_cho_dem()`.
_PL_DEM = {"luc": 0.0, "cho": 0}

# Bật/tắt in mã SF lên ảnh. Lưu ở HOME chứ không trong project: đây là thói quen
# làm việc của user, không phải thuộc tính của một bộ phim.
MA_PATH = os.path.expanduser("~/.grokpipe-dan-ma.json")


def _pl_duong(turn: int) -> str:
    return os.path.join(BOARD.pl, _pl_ten(turn))


def _pl_so_moi() -> int:
    """Số lượt kế tiếp. Lấy max(bộ đếm trên đĩa, số thư mục đang có) + 1 để user
    xoá sạch thư mục cũng không làm số quay vòng."""
    with PL_LOCK:
        os.makedirs(BOARD.pl, exist_ok=True)
        p = os.path.join(BOARD.pl, ".so-luot")
        try:
            n = int((open(p, encoding="utf-8").read() or "0").strip())
        except Exception:
            n = 0
        for ten in os.listdir(BOARD.pl):
            m = re.match(r"^turn-(\d+)$", ten)
            if m:
                n = max(n, int(m.group(1)))
        n += 1
        try:
            with open(p, "w", encoding="utf-8") as f:
                f.write(str(n))
        except OSError as e:
            _LOG.warning("không ghi được bộ đếm lượt: %s", e)
        return n


def _pl_meta(turn: int) -> dict:
    try:
        with open(os.path.join(_pl_duong(turn), "meta.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _pl_ghi_meta(meta: dict) -> None:
    # Mọi thay đổi của hộp chờ đều đi qua đây → hạ cache đếm ngay, để dải ảnh
    # trên thẻ hiện đúng ở vòng poll kế tiếp thay vì đợi hết 5 giây.
    _PL_DEM["luc"] = 0.0
    d = _pl_duong(int(meta["turn"]))
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, "meta.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(d, "meta.json"))


def _pl_xoa(turn: int) -> bool:
    """Xoá hẳn một lượt (ảnh + meta + thumbnail cache)."""
    d = _pl_duong(turn)
    if not os.path.isdir(d):
        return False
    shutil.rmtree(d, ignore_errors=True)
    tk = os.path.join(BOARD.pl, ".thumbs")
    if os.path.isdir(tk):
        for ten in list(os.listdir(tk)):
            if ten.startswith(_pl_ten(turn) + "__"):
                try:
                    os.remove(os.path.join(tk, ten))
                except OSError:
                    pass
    return True


def _pl_don_bot() -> None:
    """Giữ hộp chờ ở mức `PL_GIU_TOI_DA` lượt ĐÃ GẮN HẾT, xoá dần từ lượt cũ nhất.

    Lượt còn ảnh chưa gắn thì KHÔNG BAO GIỜ bị chạm (luật 4). Ảnh của lượt đã
    gắn hết đều có bản trong `versions/` nên xoá không mất ảnh — chỉ mất khả
    năng kéo-thả lại của mấy lượt xa nhất.

    Dọn cái gì thì GHI RA LOG. Dọn im lặng thì lần sau user tìm một lượt cũ
    không thấy sẽ tưởng board mất ảnh."""
    try:
        xong = [m for m in _pl_ds() if m.get("anh") and not (m.get("con_lai") or 0)]
    except Exception as e:
        _LOG.warning("hộp chờ: không đọc được danh sách để dọn: %s", e)
        return
    xong.sort(key=lambda m: int(m.get("turn") or 0))          # cũ nhất trước
    for m in xong[:max(0, len(xong) - PL_GIU_TOI_DA)]:
        t = int(m.get("turn") or 0)
        if t and _pl_xoa(t):
            _LOG.info("hộp chờ: dọn lượt %d (đã gắn hết, vượt mức giữ %d lượt) — "
                      "ảnh vẫn còn trong versions/", t, PL_GIU_TOI_DA)


def _pl_ds() -> list[dict]:
    """Mọi lượt còn treo, lượt mới nhất lên đầu."""
    out = []
    try:
        tens = os.listdir(BOARD.pl)
    except OSError:
        return out
    for ten in tens:
        m = re.match(r"^turn-(\d+)$", ten)
        if not m:
            continue
        meta = _pl_meta(int(m.group(1)))
        if not meta:
            continue
        con = []
        for a in meta.get("anh", []):
            p = os.path.join(BOARD.pl, ten, a.get("ten", ""))
            if not os.path.isfile(p):
                continue        # user đã xoá riêng ảnh này
            con.append({**a, "url": f"/pl/{ten}/{a['ten']}",
                        "kb": round(os.path.getsize(p) / 1024)})
        meta["anh"] = con
        meta["con_lai"] = sum(1 for a in con if not a.get("gan"))
        out.append(meta)
    out.sort(key=lambda x: -int(x.get("turn") or 0))
    return out


def _pl_cho_dem() -> int:
    """Số ảnh còn treo trong hộp chờ (chưa gắn vào thẻ nào).

    Giao diện dùng con số này làm tín hiệu "có gì đó đổi, nạp lại dải" — nên nó
    chạy mỗi vòng poll (1,5 giây). Đọc meta của mấy chục lượt với nhịp đó là phí,
    vì vậy cache 5 giây: chậm nhất 5 giây dải mới hiện, đủ nhanh với thao tác tay.
    """
    now = time.time()
    if now - _PL_DEM["luc"] < 5:
        return _PL_DEM["cho"]
    n = 0
    try:
        for ten in os.listdir(BOARD.pl):
            if not re.match(r"^turn-\d+$", ten):
                continue
            meta = _pl_meta(int(ten.split("-")[1]))
            for a in meta.get("anh", []):
                if not a.get("gan") and os.path.isfile(os.path.join(BOARD.pl, ten, a.get("ten") or "")):
                    n += 1
    except OSError:
        return _PL_DEM["cho"]
    _PL_DEM.update(luc=now, cho=n)
    return n


def _pl_dem() -> dict:
    """{số lần gắn còn lùi được · số ảnh đang treo trong hộp chờ}.

    `cho` là tín hiệu cho dải ẢNH CHỜ trên thẻ: giao diện chỉ gọi `/api/luot`
    khi con số này đổi, chứ không mỗi vòng poll."""
    with HT_LOCK:
        ht = len(HOAN_TAC)
        cuoi = dict(HOAN_TAC[-1]) if HOAN_TAC else {}
    return {"ht": ht, "cho": _pl_cho_dem(),
            "ht_cuoi": f"{cuoi.get('sf','')} · {cuoi.get('luc','')}" if cuoi else ""}


def _pl_tai_ve(sess, srcs: list[str], viec: list[tuple[str, str]],
               master: str | None, port: int, chat_url: str, ghi: dict) -> dict:
    """Tải TẤT CẢ ảnh của một lượt xuống thư mục lượt, theo đúng thứ tự hiển thị.

    Chạy TRƯỚC mọi phép đối chiếu số lượng: ảnh đã sinh là lượt đã tiêu, phải
    nằm trên đĩa trước khi board dám phán lượt này đúng hay sai."""
    turn = _pl_so_moi()
    d = _pl_duong(turn)
    os.makedirs(d, exist_ok=True)
    with ACC_LOCK:
        acct = next((a["id"] for a in ACCOUNTS if a["port"] == port), "")
    tat = {f["id"]: f for s in BOARD.read().get("scenes", []) for f in s.get("sfs", [])}
    bt, nhan = _ten_nhom(master or "", tat)
    meta = {
        "turn": turn,
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "port": port, "acct": acct,
        "master": master or "", "bieu_tuong": bt, "nhan": nhan,
        "chat_url": chat_url or "",
        "so_prompt": len(viec),
        "so_anh": 0,
        "loi_text": (ghi.get("loi_text") or "")[:600],
        # DỰ KIẾN, không phải kết luận: ảnh thứ k của lượt LẼ RA là SF thứ k.
        # Giữ lại để user có điểm bắt đầu khi gắn tay, kể cả khi lượt lệch.
        "du_kien": [{"o": k, "sf": i,
                     "nhan": (tat.get(i) or {}).get("label") or ""}
                    for k, (i, _) in enumerate(viec, 1)],
        "anh": [],
        "ly_do": "",
    }
    _pl_ghi_meta(meta)
    for k, src in enumerate(srcs, 1):
        ten = f"{k:02d}.png"
        if sess._tai_ve(src, os.path.join(d, ten)):
            _dem_cong(port or None)
            meta["anh"].append({"ten": ten, "o": k, "gan": "",
                                "du_kien": viec[k - 1][0] if k <= len(viec) else ""})
        else:
            _LOG.warning("lượt %d: KHÔNG tải được ảnh thứ %d (%s)", turn, k, src[:80])
    meta["so_anh"] = len(meta["anh"])
    _pl_ghi_meta(meta)
    _LOG.info("lượt %d: đã tải %d/%d ảnh về %s", turn, meta["so_anh"], len(srcs), d)
    # Lượt KHÔNG tải nổi ảnh nào thì thư mục rỗng — giao diện bỏ qua lượt không
    # có ảnh nên nó nằm lại vô hình và cứ thế chất đống. Dọn ngay; số lượt vẫn
    # tiêu, không dùng lại, nên log vẫn lần ngược được.
    if not meta["anh"]:
        _pl_xoa(turn)
        _LOG.info("lượt %d không tải được ảnh nào — đã dọn thư mục rỗng", turn)
    return meta


# ---- HOÀN TÁC MỘT LẦN GẮN ------------------------------------------------
# Gắn không xoá gì: nó THÊM một bản rồi đặt bản đó làm ảnh chính. Nhưng với thẻ
# VỐN CHƯA CÓ ẢNH thì không có bản cũ nào để bấm quay lại, và nút xoá bản từ chối
# xoá "bản đang dùng" — nên gắn nhầm là kẹt, phải vào Finder dọn tay. Đã xảy ra
# thật 2026-08-07: 10 ảnh mẫu gắn nhầm vào 5 thẻ trống, phải chạy script mới gỡ.
# Sổ này ghi đủ để lùi đúng một nấc: bản vừa thêm, và bản đang dùng TRƯỚC đó.
HOAN_TAC: list[dict] = []
HT_LOCK = threading.Lock()


def _ht_ghi(muc: dict) -> None:
    with HT_LOCK:
        HOAN_TAC.append(muc)
        del HOAN_TAC[:-100]


def _ban_dang_dung(sf_id: str) -> tuple[str, bool]:
    """(tên bản trong versions/ của ẢNH ĐANG DÙNG, có phải bản tự tạo không).

    Ưu tiên cờ `picked`. Không có (ảnh dán tay từ đời nào đó, chưa vào versions/)
    thì dò theo nội dung; vẫn không thấy thì CHÉP ảnh đang dùng vào versions/ —
    thà thừa một bản còn hơn để nó biến mất lúc bị thay.

    Cờ thứ hai để lúc hoàn tác còn DỌN bản giữ hộ đó đi: thẻ vốn không có bản nào
    thì lùi xong cũng phải không có bản nào, đừng để nó mọc thêm thứ user không
    tạo ra."""
    cur = BOARD.find_file(sf_id)
    if not cur:
        return "", False
    sf = BOARD.get_sf(sf_id) or {}
    p = sf.get("picked") or ""
    if p and os.path.isfile(os.path.join(BOARD.versions, p)):
        return p, False
    try:
        raw = open(cur, "rb").read()
        for v in BOARD._versions(sf_id):
            vp = os.path.join(BOARD.versions, v["file"])
            if os.path.getsize(vp) == len(raw) and open(vp, "rb").read() == raw:
                return v["file"], False
    except OSError:
        return "", False
    with BOARD_LOCK:
        giu = BOARD.next_version_path(sf_id, reserve=True)
    try:
        shutil.copy2(cur, giu)
    except OSError:
        _drop_reserved(giu)
        return "", False
    _LOG.info("giữ hộ ảnh đang dùng của %s vào %s trước khi thay",
              sf_id, os.path.basename(giu))
    return os.path.basename(giu), True


# ---- GẮN TAY ẢNH TỪ HỘP CHỜ ----------------------------------------------
# DỰNG LẠI 2026-08-12. Bỏ hàm này 2026-08-09 cùng dải phân loại để lại một lỗ
# câm: nhánh LƯỢT LỆCH vẫn báo "N ảnh ĐÃ TẢI VỀ, bấm chọn ngay trên thẻ" trong
# khi KHÔNG CÒN đường nào đưa ảnh từ hộp chờ lên thẻ — không route ảnh, không
# API liệt kê, không nút. Ảnh có thật trên đĩa mà user không thấy gì, nên đọc ra
# thành "board không tải được ảnh nào". Lượt lệch là ca thường gặp (guardrail
# chặn một ảnh giữa lô), nên lỗ này nuốt cả lượt đã tiêu tiền.
def _pl_gan(sf_id: str, turn: int, o: int) -> tuple[bool, str]:
    """Gắn ảnh thứ `o` của lượt `turn` vào thẻ `sf_id`. Trả (ok, lý do hỏng).

    Đi đúng đường của ghép tự động: thêm một bản vào `versions/` rồi đặt làm ảnh
    chính — KHÔNG đụng ảnh gốc trong hộp chờ, nên gắn nhầm thì lùi được bằng ↩.
    """
    meta = _pl_meta(turn)
    if not meta:
        return False, f"không thấy lượt {turn} trong hộp chờ"
    anh = next((a for a in meta.get("anh", []) if int(a.get("o") or 0) == o), None)
    if not anh:
        return False, f"lượt {turn} không có ảnh #{o:02d}"
    src = os.path.join(_pl_duong(turn), anh.get("ten") or "")
    if not os.path.isfile(src):
        return False, "ảnh này đã bị xoá khỏi hộp chờ"
    if BOARD.get_sf(sf_id) is None:
        return False, f"không có thẻ {sf_id}"
    # ẢNH ĐÃ DUYỆT LÀ BẢN USER ĐÃ CHỐT — không thay, kể cả khi user bấm nhầm.
    if (BOARD.get_sf(sf_id) or {}).get("status") == "approved" and BOARD.find_file(sf_id):
        return False, f"{sf_id} ĐÃ DUYỆT — bỏ duyệt trước nếu thật sự muốn thay"
    cu, tu_tao = _ban_dang_dung(sf_id)
    with BOARD_LOCK:
        out = BOARD.next_version_path(sf_id, reserve=True)
    try:
        shutil.copy2(src, out)
    except OSError as e:
        _drop_reserved(out)
        return False, f"chép vào versions/ lỗi: {str(e)[:100]}"
    BOARD.turn_log_ghi(os.path.basename(out),
                       {"turn": turn, "o": o, "port": meta.get("port") or 0,
                        "at": meta.get("at") or ""})
    _runtime_note_user_mutation(sf_id)
    with BOARD_LOCK:
        BOARD.set_current(sf_id, out)
        _mark_picked(sf_id, "picked", os.path.basename(out))
    _ht_ghi({"sf": sf_id, "moi": os.path.basename(out), "cu": cu,
             "cu_tu_tao": tu_tao, "turn": turn, "ten": anh.get("ten") or "",
             "luc": time.strftime("%H:%M:%S")})
    anh["gan"] = sf_id
    _pl_ghi_meta(meta)
    JOBS[sf_id] = {"state": "done", "msg": f"gắn tay (lượt {turn} #{o:02d})"}
    _LOG.info("gắn tay ảnh #%02d của lượt %d vào %s", o, turn, sf_id)
    return True, ""


def _ht_lui(n: int = 1) -> tuple[int, list[str]]:
    """Lùi `n` lần gắn gần nhất. Trả (số lần đã lùi, mô tả từng lần).

    Lùi = xoá bản vừa thêm, trả ảnh chính về đúng bản trước đó (hoặc về TRỐNG
    nếu thẻ vốn chưa có ảnh), và bỏ dấu 'đã gắn' để ảnh quay lại thanh chờ phân
    loại. Ảnh gốc trong `cho-phan-loai/` không bị đụng, nên gắn lại được ngay."""
    ra = []
    con = max(1, n)
    while con > 0:
        con -= 1
        with HT_LOCK:
            m = HOAN_TAC.pop() if HOAN_TAC else None
            # MỘT CÚ TRÁO LÙI TRỌN CẶP. Hai dòng của cùng một lần tráo mang cùng
            # `cap`; lùi một nửa thì hai thẻ đeo chung một ảnh — hỏng hơn lúc đầu.
            if m and m.get("cap") and HOAN_TAC and HOAN_TAC[-1].get("cap") == m["cap"]:
                con += 1
        if not m:
            break
        i, moi, cu = m["sf"], m["moi"], m.get("cu") or ""
        try:
            p = os.path.join(BOARD.versions, moi)
            if os.path.isfile(p):
                os.remove(p)
        except OSError as e:
            _LOG.warning("hoàn tác: không xoá được %s: %s", moi, e)
        if not m.get("duyet"):
            _runtime_note_user_mutation(i)
        with BOARD_LOCK:
            if m.get("duyet"):
                pass                      # bản đã duyệt chưa bao giờ bị thay
            elif cu and os.path.isfile(os.path.join(BOARD.versions, cu)):
                BOARD.set_current(i, os.path.join(BOARD.versions, cu))
                if m.get("cu_tu_tao"):
                    # Bản này do board tự chép ra để giữ hộ, không phải bản user
                    # tạo. Trả ảnh xong thì dọn, để thẻ về ĐÚNG như trước.
                    try:
                        os.remove(os.path.join(BOARD.versions, cu))
                    except OSError:
                        pass
                    cu = ""
            else:
                for ten in list(os.listdir(BOARD.assets)):
                    if os.path.splitext(ten)[0] == i:
                        os.remove(os.path.join(BOARD.assets, ten))
        if not m.get("duyet"):
            if cu:
                _mark_picked(i, "picked", cu)
            else:
                # GỠ HẲN key, đừng ghi chuỗi rỗng: `"picked": ""` là rác nằm lại
                # trong sf-board.json — file kịch bản phim, không phải sổ tạm.
                with BOARD_LOCK:
                    dl = BOARD.read(); doi = False
                    for sc in dl.get("scenes", []):
                        for sfd in sc.get("sfs", []):
                            if sfd.get("id") == i and sfd.pop("picked", None) is not None:
                                doi = True
                    if doi:
                        BOARD.write(dl)
        nk = dict(BOARD.turn_log())
        if nk.pop(moi, None) is not None:
            try:
                with open(BOARD.nk_path, "w", encoding="utf-8") as f:
                    json.dump(nk, f, ensure_ascii=False, indent=1, sort_keys=True)
                BOARD._nk = {"mtime": os.path.getmtime(BOARD.nk_path), "data": nk}
            except OSError:
                pass
        meta = _pl_meta(int(m.get("turn") or 0))
        if meta:
            for a in meta.get("anh", []):
                if a.get("ten") == m.get("ten") and a.get("gan") == i:
                    a["gan"] = ""
            _pl_ghi_meta(meta)
        JOBS.pop(i, None)
        ra.append(f"{i} ← lượt {m.get('turn')}/{m.get('ten')}"
                  + (" (về bản " + cu + ")" if cu and not m.get("duyet")
                     else " (về trạng thái chưa có ảnh)" if not m.get("duyet") else ""))
        _LOG.info("hoàn tác gắn: %s", ra[-1])
    return len(ra), ra


def _generate_lo(sf_ids: list[str], tay: bool = False):
    """Gửi các SF ĐƯỢC TÍCH trong MỘT tin nhắn, vào MỘT đoạn chat mới.

    Đơn giản hoá 2026-08-12 theo yêu cầu user: bỏ hết tầng "board tự gom lô theo
    địa điểm rồi tự nhớ đoạn chat". Trước đây tầng đó kéo theo khoá địa điểm,
    hàng chờ khoá, giao việc đích danh theo tài khoản giữ chat, cân bằng chat
    giữa các tài khoản — nhiều luật ngầm, khó lần khi hỏng.

    Giờ: TÍCH GÌ GỬI NẤY. User tự chọn các thẻ muốn vẽ cùng nhau (thường là cùng
    một địa điểm), board gửi đúng chừng ấy trong một tin nhắn của một chat trắng,
    kèm luật chung và đủ ref. Chat không lưu lại, nên lần sau lại chat trắng.

    Đánh đổi đã biết và chấp nhận: mỗi lần chạy phải đính lại ref (tốn lượt đính
    tệp hơn), và ảnh lần này KHÔNG đồng bộ với ảnh đã vẽ lần trước ở cùng địa
    điểm — chỉ những thẻ tích CHUNG MỘT LẦN mới đồng bộ với nhau."""
    # Không tin thứ tự checkbox/request: chính thứ tự này quyết định thứ tự ghép
    # ảnh ChatGPT trả về. Luôn chuẩn hoá theo thứ tự shot ngay tại cửa cuối để
    # mọi đường gọi (auto, tạo tay, retry) cùng một hành vi.
    sf_ids = sorted((i for i in sf_ids if i), key=_uu_tien)
    if not sf_ids:
        return
    data = BOARD.read()
    master = _nhom_cua(sf_ids[0], data) or None
    return _generate_lo_ruot(sf_ids, data, master, tay)


def _generate_lo_ruot(sf_ids: list[str], data: dict, master: str | None, tay: bool = False):
    """Ruột của _generate_lo — chỉ được gọi khi đã cầm khoá của master (nếu cần)."""
    # LỌC LẠI NGAY TRƯỚC KHI GỬI: bỏ SF đã có ảnh. Hàng đợi nằm trong RAM và có
    # thể ôm việc cũ hàng chục phút; trong khoảng đó ảnh có thể đã về bằng đường
    # khác (user dán tay vào thẻ, vớt tay từ chat, job trùng). Không lọc thì board
    # render lại thứ đã có — tốn lượt mà không ai thấy sai.
    # CHỈ áp cho lô CHẠY NỀN (tay=False). Lô do user bấm vẫn được đè, vì bấm
    # "Tạo ảnh" trên thẻ đã có ảnh là chủ động muốn bản mới.
    if not tay:
        da_co = [i for i in sf_ids if BOARD.find_file(i)]
        if da_co:
            for i in da_co:
                JOBS[i] = {"state": "done", "msg": "đã có ảnh — bỏ qua, không render lại"}
            _LOG.info("bỏ %d SF đã có ảnh khỏi lô: %s", len(da_co), ", ".join(da_co))
            sf_ids = [i for i in sf_ids if i not in da_co]
            if not sf_ids:
                return

    # MỘT lần đọc board cho cả lô. get_sf() không tham số sẽ đọc lại toàn bộ
    # cho TỪNG thẻ — lô 10 ảnh là 10 lần đọc, mỗi lần ~300ms.
    _d = BOARD.read()
    viec, attach, attach_id, thieu = [], [], [], []
    for i in sf_ids:
        sf = BOARD.get_sf(i, _d)
        if not sf or not (sf.get("prompt") or "").strip():
            thieu.append(i); continue
        viec.append((i, sf["prompt"].strip()))
        a, mis, rid = _sf_attachments(sf)
        if mis:
            thieu.append(f"{i}(thiếu ref)"); continue
        # Giữ SONG SONG đường dẫn và id: phép hạ ref bên dưới quyết định theo id
        # (đuôi _PORTRAIT/_FULL) nhưng thứ đem đính là đường dẫn.
        for x, r in zip(a, rid):
            if x not in attach:
                attach.append(x); attach_id.append(r)
    if thieu:
        for i in sf_ids:
            JOBS[i] = {"state": "error", "msg": "lô dừng: " + ", ".join(thieu[:4])}
        raise RuntimeError("lô có SF hỏng: " + ", ".join(thieu[:4]))

    # LÔ CHỈ CÓ ẢNH GỐC thì chạy CHAT TRẮNG và KHÔNG chốt chat của địa điểm.
    # Chat của một địa điểm chỉ được chốt khi bắt đầu chạy SF CON, vì lúc đó mới
    # có ảnh master ĐÃ DUYỆT để đính làm bối cảnh. Chốt từ lô master là gắn cả
    # địa điểm vào một tài khoản trước khi biết bản master nào được chọn, và để
    # lại trong chat những bản master hỏng.
    chi_anh_goc = all(_la_the_dia_diem(BOARD.get_sf(i, _d) or {"id": i}) for i in sf_ids)

    # CỔNG CHẶN — đứng ở đây, TRƯỚC khi mở phiên Chrome và trước khi chốt chat.
    # Chặn ở server chứ không chỉ ở giao diện: auto-runner, hàng giao đích danh
    # và mọi lệnh gọi API đều đi qua chỗ này, còn nút bấm thì chỉ là một đường.
    if not chi_anh_goc:
        _ly = _cong_master(master)
        if _ly:
            for i in sf_ids:
                JOBS[i] = {"state": "error",
                           "msg": f"CHƯA CHẠY: {_ly}. Ảnh thẻ địa điểm là bản neo "
                                  f"khoá màu · ánh sáng · trục cho cả địa điểm — "
                                  f"chạy nó trước, rồi hãy chạy khung con."}
            _HOAN.pop("LO:" + ",".join(sf_ids), None)
            _LOG.info("chặn lô %d ảnh: %s", len(sf_ids), _ly)
            return

    # LUÔN CHAT TRẮNG. Board không còn nhớ đoạn chat của địa điểm nữa (bỏ
    # 2026-08-12): mỗi lần chạy là một chat mới, gửi lại luật chung và đính lại
    # đủ ref. Nhờ vậy không còn "chat này chỉ mở được ở tài khoản kia", nên cũng
    # không cần giao việc đích danh, không cần cân bằng chat giữa các tài khoản,
    # và bất kỳ tài khoản nào rảnh cũng chạy được bất kỳ việc nào.
    _ident = "LO:" + ",".join(sf_ids)
    _HOAN.pop(_ident, None)

    # REF THƯỜNG chỉ cần gửi một lần trong chat, nhưng MỖI NHÂN VẬT phải gửi lại
    # theo CẶP: PORTRAIT neo khuôn mặt + FULL neo đúng trang phục. Chỉ gửi portrait
    # làm model tự bịa áo (ca S5: Maya từ áo vàng HOME thành áo nâu dù mặt đúng).
    # CHAT TRẮNG THÌ ĐÍNH ĐỦ REF, không lọc gì. Trước đây board lọc bớt ref
    # "đã gửi rồi trong chat này" để đỡ upload; giờ không còn chat cũ nên phép
    # lọc đó vô nghĩa — và thiếu ref là model tự bịa mặt/trang phục, hỏng câm.
    # HẠ REF KHI TRÀN TRẦN: nhân vật từ thứ 5 trở đi chỉ gửi _FULL.
    #
    # Áp cho MỌI đường tạo, kể cả lô user tự tích — vì đây KHÔNG phải chẻ tin.
    # Luật "tích bao nhiêu gửi bấy nhiêu, trong đúng một tin" (2026-08-12) vẫn
    # nguyên: vẫn một tin, vẫn đủ từng ấy SF, chỉ nhẹ đi vài ảnh tham chiếu.
    # Log ALTAR 2026-08-15: lô 14-17 ref hỏng mọi lượt và tắt sạch 6 tài khoản,
    # trong khi lô 5 ref cùng phút chạy sạch.
    _giu = set(_ha_ref_nhan_vat_phu(attach_id, TRAN_REF))
    can_dinh = [x for x, r in zip(attach, attach_id) if r in _giu]
    if len(can_dinh) < len(attach):
        _LOG.info("lô %d ảnh: hạ %d→%d ref (nhân vật phụ chỉ gửi full-body)",
                  len(viec), len(attach), len(can_dinh))

    # Luật chung của địa điểm, gửi kèm mỗi lần vì lần nào cũng là chat mới.
    luat_chung = ""
    if master:
        m = BOARD.get_sf(master) or {}
        luat_chung = (m.get("luatchung") or "").strip()

    _dat_nhan_lo(viec, {"state": "running",
                        "msg": f"{len(viec)} ảnh{_acct_label()} · chat mới"
                               + (f" · đính {len(can_dinh)} ref" if can_dinh else "")})
    _gen0 = dung_gen()        # chụp thế hệ TRƯỚC khi đi vào lượt chạy dài
    sess = _session()
    srcs, url, ghi = sess.generate_lo(viec, can_dinh, chat_url="",
                                      # KHÔNG dán mã lên ảnh REF. Ảnh REF được
                                      # đính vào MỌI chat khác làm neo mặt và
                                      # trang phục — chữ nằm trong ảnh neo là
                                      # mời model chép chữ đó sang ảnh mới. Lô
                                      # REF cũng gần như luôn một ảnh nên chẳng
                                      # có thứ tự nào để mà lẫn.
                                      luat_chung=luat_chung,
                                      dan_ma=_dan_ma_doc() and not any(
                                          i.startswith("REF_") for i, _ in viec),
                                      nen_dung=lambda: any(i in DUNG_RIENG for i, _ in viec))

    port = int((getattr(_TL, "endpoint", "") or ":0").rsplit(":", 1)[1] or 0)
    # TÀI KHOẢN VỪA CHẠM TRẦN ĐÍNH TỆP trong chính lượt này — CHỈ GHI NHẬN.
    #
    # Bỏ đánh dấu nghỉ (user chốt 2026-08-14): không còn treo tài khoản tới giờ
    # ChatGPT hẹn. Cũng KHÔNG xoay cửa sổ ngay tại đây — chỗ này đứng TRƯỚC bước
    # tải ảnh về, đóng Chrome bây giờ là giết đúng loạt ảnh vừa vẽ xong (đã mất
    # một lô 10 ảnh kiểu đó lúc 10:26 ngày 2026-08-14). Cứ để lượt này tải nốt;
    # lô sau tài khoản này lỗi thì `_worker` xoay theo đường thường.
    _nghi = (ghi.get("nghi_den") or "").strip()
    if _nghi:
        _LOG.warning("%s chạm trần đính tệp (ChatGPT hẹn %s) — vẫn tải nốt lượt "
                     "này, lô sau lỗi sẽ tự xoay sang tài khoản khác.",
                     _TL.endpoint, _nghi)
    # KHÔNG lưu chat_url nữa (bỏ 2026-08-12): lần sau lại chat trắng.

    # TẢI HẾT VỀ TRƯỚC KHI PHÁN. Kể cả lượt thiếu, thừa, hay trả kèm chữ — ảnh
    # đã sinh là lượt đã tiêu, không được vứt vì một phép đếm.
    luot = _pl_tai_ve(sess, srcs, viec, master, port, url, ghi) if srcs else None
    n_ve = int((luot or {}).get("so_anh") or 0)
    loi_text = (ghi.get("loi_text") or "").strip()

    # ═══ LƯỢT KHÔNG TRỌN VẸN — user chốt 2026-08-12 ═════════════════════════
    #
    # MỌI ca không trọn vẹn (0 ảnh · thiếu ảnh · trả kèm chữ) đều xử như nhau:
    # gửi lại NGUYÊN TASK, tối đa `LO_THU_LAI` lần. Hết số lần thì
    #   · còn ảnh  → ghép bấy nhiêu về được, theo thứ tự;
    #   · 0 ảnh    → báo lỗi kèm hướng sửa prompt.
    #
    # Bỏ TÁCH CHẠY LẺ: bản cũ trượt 3 lần thì xé lô thành N việc một-ảnh. Chính
    # đường đó đang lỗi, và nó biến một lô hỏng thành N lượt hỏng.
    # Bỏ BẤM CHỌN TAY: ảnh không nằm chờ trong hộp nữa, ghép thẳng theo thứ tự.
    #
    # ⚠ ĐÁNH ĐỔI CÓ CHỦ Ý ở bước ghép cuối: nếu ChatGPT bỏ một ảnh ở GIỮA lô thì
    # mọi ảnh sau đó lệch một nấc và vào nhầm thẻ. Đây là điều bản cũ từ chối
    # làm. Bật "🔖 Mã SF" để mã in sẵn trong ảnh, nhìn là biết ảnh của thẻ nào.
    _bi_dung = [i for i, _ in viec if i in DUNG_RIENG]
    if _bi_dung:
        with HUY_LOCK:
            DUNG_RIENG.difference_update(i for i, _ in viec)
        for i, _ in viec:
            _dat_nhan_lo([(i, None)],
                         {"state": "error",
                          "msg": "đã dừng riêng" if i in _bi_dung
                                 else "dừng theo lô (một lô là một tin nhắn)"})
        _LOG.info("lô %d ảnh bị user dừng riêng — không thử lại", len(viec))
        return

    _gr = "GR:" + _ident
    if n_ve != len(viec) or loi_text:
        # PHÂN BIỆT "CHƯA GỬI ĐƯỢC" VỚI "GỬI RỒI MÀ KHÔNG CÓ ẢNH".
        #
        # `da_gui=False` nghĩa là board KHÔNG bấm nổi nút Send — draft còn nguyên
        # trong ô soạn, ChatGPT chưa hề nhận gì, KHÔNG tốn lượt nào. Bản cũ gộp
        # chung vào câu "ChatGPT không trả ảnh nào", nên user nhìn thấy chat đầy
        # ảnh (của lượt khác) mà board thì bảo không có — đi tìm lỗi nhận diện
        # ảnh suốt trong khi bệnh nằm ở cú bấm gửi.
        #
        # `chan_doan` = executor ĐÃ BIẾT chỗ hỏng và tự dừng trước khi gửi (chưa
        # mở được chat trắng · chưa đặt được chế độ High/Medium). Nó cụ thể hơn
        # mọi câu đoán bên dưới nên phải được nói NGUYÊN VĂN: gộp vào câu "nút
        # Send bị nuốt" là đẩy user đi đóng tab ChatGPT trong khi bệnh nằm chỗ khác.
        _chua_gui = not ghi.get("da_gui", True)
        _cd = (ghi.get("chan_doan") or "").strip()
        _vi = (_cd if _cd
               else "board CHƯA GỬI ĐƯỢC tin (nút Send bị nuốt, draft còn trong ô soạn) "
               "— chưa tốn lượt nào" if _chua_gui
               else "ChatGPT nhận tin nhưng không trả ảnh nào" if not n_ve
               else f"lượt trả kèm chữ ({loi_text[:50]}…)" if loi_text and n_ve == len(viec)
               else f"chỉ về {n_ve}/{len(viec)} ảnh" if n_ve < len(viec)
               else f"thừa {n_ve - len(viec)} ảnh")
        # USER ĐÃ BẤM DỪNG trong lúc lượt này chạy → KHÔNG được tự xếp lại. Thiếu
        # chốt này thì "Dừng tất cả" bị vô hiệu một cách im lặng: lô hỏng quay
        # lại hàng đợi rồi vẽ đè lên ảnh đang có.
        if dung_gen() != _gen0:
            _dat_nhan_lo(viec, {"state": "error", "msg": "đã dừng — không thử lại"})
            _LOG.info("lô %d ảnh xong sau khi user bấm dừng — bỏ, không xếp lại", len(viec))
            return
        _n = _HOAN.get(_gr, 0)
        if _n < LO_THU_LAI:
            _HOAN[_gr] = _n + 1
            _bo = _dat_nhan_lo(viec, {"state": "queued",
                                      "msg": f"{_vi} — gửi lại cả tin, "
                                             f"lần {_n + 1}/{LO_THU_LAI}"})
            if _bo:
                _LOG.info("gửi lại lô: giữ nguyên %d thẻ đã có ảnh từ lượt trước", _bo)
            _LOG.warning("lô %d ảnh: %s — gửi lại nguyên task, lần %d/%d",
                         len(viec), _vi, _n + 1, LO_THU_LAI)
            time.sleep(15)
            _xep(IMG_QUEUE, ("img", _ident, 0, tay))
            return
        _HOAN.pop(_gr, None)
        if not n_ve:
            _cach = ("" if _cd
                     else "Board không bấm nổi nút Send sau nhiều lần. Xem hộp 🐞 để biết ô "
                     "soạn và nút gửi lúc đó ra sao — thường là tab ChatGPT kẹt ở khung "
                     "cũ, đóng tab đó rồi bấm Tạo lại." if _chua_gui
                     else "Thường là guardrail chặn: sửa prompt — bớt chữ nhấn vào gương "
                          "mặt, đổi vài chi tiết bố cục, hoặc đổi ảnh ref rồi bấm Tạo lại.")
            _dat_nhan_lo(viec, {"state": "error",
                                "msg": f"{_vi} — sau {LO_THU_LAI} lần thử. "
                                       f"{_cach}".rstrip()})
            _LOG.warning("lô %d ảnh trượt cả %d lần — dừng, chờ user sửa prompt",
                         len(viec), LO_THU_LAI)
            _ghi_so_lo_hong(_ident, viec, _vi, loi_text, 0)
            return
        _LOG.warning("lô %d ảnh: %s sau %d lần gửi lại — thôi không thử nữa, ghép "
                     "bấy nhiêu về được", len(viec), _vi, LO_THU_LAI)
        _ghi_so_lo_hong(_ident, viec, _vi, loi_text, n_ve)

    _HOAN.pop(_gr, None)                 # có ảnh về = lượt đã xong, xoá đếm

    # ---- GHÉP TỰ ĐỘNG: có bao nhiêu ghép bấy nhiêu ------------------------
    # Ảnh đã nằm sẵn trong thư mục lượt, chỉ còn chép sang versions/. GHÉP RỒI
    # VẪN GIỮ thư mục lượt (xem PL_GIU_TOI_DA): lượt ghép đúng cũng phải còn
    # trong hộp chờ để dịch ảnh sang thẻ khác, không phải vẽ lại.
    hong, thieu = [], []
    for k, (i, _) in enumerate(viec, 1):
        _HOAN.pop("GR:LO:" + i, None)    # xoá đếm guardrail của bản chạy lẻ cũ
        # LỆCH SỐ THÌ MẤY THẺ CUỐI KHÔNG CÓ ẢNH.
        # Cờ `nhe` = báo ở NGĂN KÉO HÀNG ĐỢI và hộp 🐞, KHÔNG dán dải đỏ lên thẻ
        # (user chốt 2026-08-12). Thẻ trống đã tự nói lên nó chưa có ảnh; thêm
        # dải đỏ nữa chỉ làm bảng đầy cảnh báo. Nhưng cũng không được im lặng —
        # im thì thẻ hụt lẫn vào đám thẻ chưa chạy, không ai biết mà chạy lại.
        if k > n_ve:
            thieu.append(i)
            JOBS[i] = {"state": "error", "nhe": True,
                       "msg": f"lượt {luot['turn']} về {n_ve}/{len(viec)} ảnh sau "
                              f"{LO_THU_LAI} lần thử — thẻ này chưa có ảnh, bấm Tạo lại"}
            continue
        src = os.path.join(_pl_duong(luot["turn"]), luot["anh"][k - 1]["ten"])
        with BOARD_LOCK:
            out = BOARD.next_version_path(i, reserve=True)
        try:
            shutil.copy2(src, out)
        except OSError as e:
            _drop_reserved(out)
            hong.append(i)
            JOBS[i] = {"state": "error",
                       "msg": f"ảnh đã tải về nhưng chép vào bản lỗi: {e} "
                              f"— ảnh còn ở lượt {luot['turn']}"}
            continue
        # Ảnh này đã vào SF `i` → đánh dấu NGAY, trước nhánh "đã duyệt" ở dưới:
        # nhánh đó `continue`, đặt dấu sau nó là bỏ sót đúng những ảnh vào thẻ đã
        # duyệt. Hộp chờ đọc dấu này để hiện "→ đã gắn <SF>", và `_pl_don_bot()`
        # dựa vào nó để biết lượt nào đã xong mà dọn được.
        luot["anh"][k - 1]["gan"] = i
        BOARD.turn_log_ghi(os.path.basename(out),
                           {"turn": luot["turn"], "o": k, "port": port,
                            "at": luot.get("at") or ""})
        with BOARD_LOCK:
            # ẢNH MỚI VỀ THÌ ĐÈ, KỂ CẢ THẺ ĐÃ DUYỆT (user chốt 2026-08-14).
            # Bản cũ vẫn nằm nguyên trong `versions/` nên không mất gì — bấm lại
            # trong dãy bản là quay về được. Trước đây nhánh này giữ bản cũ và
            # đẩy bản mới xuống dãy bản: user chủ động bấm tạo lại mà thẻ không
            # đổi, tốn lượt mà nhìn như hỏng câm.
            BOARD.set_current(i, out)
            _mark_picked(i, "picked", os.path.basename(out))
        TAY_SF.discard(i)        # ảnh đã về → ý "tạo tay" coi như đã thực hiện
        JOBS[i] = {"state": "done", "msg": f"xong (lô · lượt {luot['turn']} #{k:02d})"}
    if hong:
        luot["ly_do"] = "chép vào versions/ lỗi ở " + ", ".join(hong[:4])
    elif thieu:
        luot["ly_do"] = (f"ghép {n_ve}/{len(viec)} ảnh theo thứ tự — thiếu ảnh cho "
                         + ", ".join(thieu[:4]))
        _LOG.warning("lượt %d về %d/%d ảnh — đã ghép theo thứ tự, %d thẻ chưa có ảnh: %s",
                     luot["turn"], n_ve, len(viec), len(thieu), ", ".join(thieu[:6]))
    else:
        luot["ly_do"] = (f"đã ghép tự động đủ {len(viec)} ảnh — giữ lại để "
                         f"kéo sang thẻ khác nếu thứ tự chưa đúng")
    # THỪA ảnh thì phần dôi nằm lại trong hộp chờ, không mất: nó vẫn ở
    # cho-phan-loai/turn-NNNN/ và tra được qua nhật ký lượt.
    if n_ve > len(viec):
        _LOG.info("lượt %d thừa %d ảnh — phần dôi giữ trong hộp chờ",
                  luot["turn"], n_ve - len(viec))
    _pl_ghi_meta(luot)
    _pl_don_bot()


# Giao diện nằm trong ui/: board.html (khung) · board.css · board.js.
# ĐỌC LẠI TỪ ĐĨA MỖI LẦN, không nạp sẵn lúc import: sửa giao diện xong chỉ cần
# F5, khỏi restart board — mà restart giữa chừng thì mất hàng đợi.
_UI_DIR = os.path.join(_HERE, "ui")


def _doc_ui(ten: str) -> str:
    # Chốt tên file trong danh sách trắng: đường dẫn từ URL mà ghép thẳng vào
    # os.path.join là mở cửa cho ../../ đọc trộm file ngoài thư mục ui/.
    if ten not in ("board.html", "board.css", "board.js", "job-request.js",
                   "job-projection.js"):
        raise ValueError(f"file giao diện lạ: {ten}")
    with open(os.path.join(_UI_DIR, ten), encoding="utf-8") as f:
        return f.read()



# ═══ BỘ CHỌN DỰ ÁN (ghép từ bản hook auto) ═══════════════════════════════
def _project_kind(proj_dir: str, data: dict | None = None) -> str:
    """'hook' hay 'phim'. Ưu tiên field kind trong sf-board.json, sau đó là tên thư mục."""
    if data and data.get("kind") in ("hook", "phim"):
        return data["kind"]
    return "hook" if os.path.basename(proj_dir).upper().startswith("PIPELINE-HOOK-") else "phim"


def _reg_path() -> str:
    return os.path.join(PROJECTS_ROOT, ".sfboard-running.json")


def _port_alive(port: int) -> bool:
    import socket
    with socket.socket() as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", int(port))) == 0


def _reg_read(prune: bool = True) -> dict:
    """{ten_du_an: {port, cdp, pid}} — bỏ luôn những mục có cổng đã chết."""
    try:
        with open(_reg_path(), encoding="utf-8") as f:
            reg = json.load(f)
    except Exception:
        return {}
    if not prune:
        return reg
    # Giữ mục của CHÍNH tiến trình này kể cả khi cổng chưa kịp lắng nghe — nếu không,
    # lần quét đầu (chạy trước serve_forever) sẽ tự xoá mất đăng ký của mình.
    me = os.getpid()
    live = {k: v for k, v in reg.items()
            if v.get("pid") == me or _port_alive(v.get("port", 0))}
    if len(live) != len(reg):
        _reg_save(live)
    return live


def _reg_save(reg: dict) -> None:
    try:
        with open(_reg_path(), "w", encoding="utf-8") as f:
            json.dump(reg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        _LOG.warning("không ghi được sổ đăng ký: %s", e)


def _reg_register(name: str, port: int) -> None:
    reg = _reg_read()
    reg[name] = {"port": port, "cdp": CDP_ENDPOINTS, "pid": os.getpid()}
    _reg_save(reg)


def _reg_unregister(name: str) -> None:
    reg = _reg_read(prune=False)
    if reg.pop(name, None) is not None:
        _reg_save(reg)


def _free_port(start: int = 8777) -> int:
    for p in range(start, start + 40):
        if not _port_alive(p):
            return p
    raise RuntimeError("không còn cổng trống trong khoảng 8777-8816")


def _open_project(name: str) -> tuple[bool, str, int]:
    """Trả về cổng phục vụ dự án này; chưa có tiến trình nào thì bật một cái mới."""
    if os.path.basename(name) != name or not name.endswith(".project"):
        return False, "tên dự án không hợp lệ", 0
    d = os.path.join(PROJECTS_ROOT, name)
    if not os.path.isfile(os.path.join(d, "sf-board.json")):
        return False, f"không thấy sf-board.json trong {name}", 0

    reg = _reg_read()
    if name in reg:
        return True, "", int(reg[name]["port"])

    port = _free_port()
    # Quy ước chia tài khoản Chrome: mỗi board SỞ HỮU endpoint đầu tiên trong danh sách
    # của nó, những cái sau chỉ là dự phòng khi hết lượt. Board mới vì thế nhận trước
    # các endpoint chưa ai sở hữu, rồi mới xếp phần dùng chung xuống cuối.
    owned = {v["cdp"][0] for v in reg.values() if v.get("cdp")}
    free = ([ep for ep in CDP_ENDPOINTS if ep not in owned]
            + [ep for ep in CDP_ENDPOINTS if ep in owned])
    if not free:
        free = list(CDP_ENDPOINTS)
    if free[0] in owned:
        _LOG.warning("Hết tài khoản Chrome riêng — %s sẽ dùng chung %s với board khác",
                     name, free[0])
    cmd = [sys.executable, "-u", os.path.abspath(__file__), d,
           "--port", str(port), "--cdp", ",".join(free), "--no-open"]
    log = open(os.path.join(PROJECTS_ROOT, f".sfboard-{port}.log"), "ab", buffering=0)
    subprocess.Popen(cmd, cwd=PROJECTS_ROOT, stdout=log, stderr=log,
                     start_new_session=True)
    for _ in range(60):
        if _port_alive(port):
            _LOG.info("Đã bật board cho %s ở cổng %d (cdp: %s)", name, port, ", ".join(free))
            return True, "", port
        time.sleep(0.25)
    return False, f"bật được tiến trình nhưng cổng {port} không lên", 0


def _scan_projects() -> list[dict]:
    """Mọi thư mục *.project trong PROJECTS_ROOT, kèm vài số đếm để hiện trên UI."""
    out = []
    if not PROJECTS_ROOT or not os.path.isdir(PROJECTS_ROOT):
        return out
    reg = _reg_read()
    for name in sorted(os.listdir(PROJECTS_ROOT)):
        d = os.path.join(PROJECTS_ROOT, name)
        board_path = os.path.join(d, "sf-board.json")
        if not name.endswith(".project") or not os.path.isfile(board_path):
            continue
        data, sfs, shots = {}, 0, 0
        try:
            with open(board_path, encoding="utf-8") as f:
                data = json.load(f)
            for sc in data.get("scenes", []):
                sfs += len(sc.get("sfs", []))
                shots += len(sc.get("shots", []))
        except Exception:
            pass
        assets = os.path.join(d, "assets")
        imgs = len([x for x in os.listdir(assets)
                    if os.path.splitext(x)[1].lower() in IMAGE_EXT]) if os.path.isdir(assets) else 0
        out.append({
            "name": name,
            "kind": _project_kind(d, data),
            "film": data.get("film") or name,
            "scenes": len(data.get("scenes", [])),
            "sfs": sfs, "shots": shots, "imgs": imgs,
            "current": BOARD is not None and os.path.abspath(d) == BOARD.dir,
            "port": reg.get(name, {}).get("port"),      # None = chưa mở board nào
        })
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body: bytes, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _giao_viec(self, yeu_cau, khoa, plan_factory, kind="img"):
        """Đưa một ý định tạo việc qua ĐÚNG MỘT cửa rồi giao xuống hàng đợi.

        Trả `(True, metadata)` khi giao xong — metadata là các field phụ
        (`job_id`, `job_ids`, `batch_id`, `replayed`) merge vào response cũ. Trả
        `(False, None)` khi đã tự trả lỗi cho client; caller chỉ việc `return`.

        Ở mode `legacy` (mặc định) không có core mới nào chạy: plan vẫn được
        giao bằng đúng callback legacy, metadata rỗng.
        """
        from jobs.store import ActiveJobConflict, IdempotencyConflict

        try:
            ket_qua = _producer_submit(yeu_cau, khoa, plan_factory)
        except IdempotencyConflict:
            self._json({"ok": False,
                        "err": "idempotency key đã dùng cho yêu cầu khác"}, 409)
            return False, None
        except ActiveJobConflict:
            self._json({"ok": False,
                        "err": "đã có việc đang hoạt động trong phạm vi này"}, 409)
            return False, None
        except (TypeError, ValueError) as exc:
            self._json({"ok": False, "err": str(exc)}, 400)
            return False, None
        except Exception as exc:            # noqa: BLE001
            try:
                # KHÔNG đưa prompt/key/request thô vào sổ lỗi.
                report_runtime_bug({
                    "reason_code": "producer_delivery",
                    "category": "producer_delivery",
                    "severity": "ERROR",
                    "job": {"kind": kind, "phase": "delivery"},
                    "exc": exc,
                })
            except Exception:               # noqa: BLE001
                pass
            _LOG.warning("không giao được việc sang hàng đợi: %s", type(exc).__name__)
            self._json({"ok": False, "err": "không giao được việc sang hàng đợi"}, 500)
            return False, None
        return True, _producer_metadata(ket_qua)

    def _dl_name(self, q, path) -> str:
        """Tên file khi tải về: ưu tiên ?name=<SF-ID>, giữ đúng phần mở rộng thật của file."""
        ext = os.path.splitext(path)[1] or ".bin"
        base = (q.get("name", [""])[0] or os.path.splitext(os.path.basename(path))[0])
        base = re.sub(r"[^A-Za-z0-9_.\-]", "_", base)
        return base + ext

    def _serve_img(self, folder, name, q=None):
        p = os.path.join(folder, unquote(os.path.basename(name)))
        if not os.path.isfile(p):
            self._send(404, b"not found", "text/plain")
            return
        q = q or {}
        # ?w=420 → trả bản thu nhỏ. Ảnh gốc là PNG ~2.8MB, cỡ 1672×941, mỗi ảnh
        # trình duyệt decode ra ~6MB bitmap; 200 thẻ trong lưới là hơn 1GB RAM.
        # Bản thu nhỏ JPEG hạ con số đó xuống khoảng một phần mười lăm.
        want = q.get("w")
        if want and not q.get("dl"):
            tp = _thumb(p, int(want[0]) if isinstance(want, list) else int(want))
            if tp:
                with open(tp, "rb") as f:
                    self._send(200, f.read(), "image/jpeg")
                return
        with open(p, "rb") as f:
            data = f.read()
        ctype = IMAGE_EXT.get(os.path.splitext(p)[1].lower(), "application/octet-stream")
        if q.get("dl"):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Disposition",
                             f'attachment; filename="{self._dl_name(q, p)}"')
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        self._send(200, data, ctype)

    def _serve_pl(self, path, q=None):
        """Ảnh trong hộp chờ: /pl/turn-0097/03.png

        Không dùng được `_serve_img` vì nó cắt `basename` (một tầng), còn hộp chờ
        có thư mục lượt. Đường dẫn dựng lại TỪNG MẢNH theo khuôn, không nối chuỗi
        thô: `/pl/../../` là đường đọc trộm cả đĩa.
        """
        m = re.match(r"^/pl/(turn-\d{1,6})/([0-9A-Za-z._-]{1,40})$", path)
        if not m:
            self._send(404, b"not found", "text/plain")
            return
        self._serve_img(os.path.join(BOARD.pl, m.group(1)), m.group(2), q)

    def _serve_video(self, folder, name, q=None):
        """Phát video có hỗ trợ Range để tua được; ?dl=1 thì ép tải về kèm tên file."""
        p = os.path.join(folder, unquote(os.path.basename(name)))
        if not os.path.isfile(p):
            self._send(404, b"not found", "text/plain")
            return
        q = q or {}
        if q.get("dl"):
            with open(p, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Disposition",
                             f'attachment; filename="{self._dl_name(q, p)}"')
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        size = os.path.getsize(p)
        rng = self.headers.get("Range")
        if rng and rng.startswith("bytes="):
            a, _, b = rng[6:].partition("-")
            start = int(a or 0)
            end = int(b) if b else size - 1
            end = min(end, size - 1)
            with open(p, "rb") as f:
                f.seek(start)
                chunk = f.read(end - start + 1)
            self.send_response(206)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(len(chunk)))
            self.end_headers()
            self.wfile.write(chunk)
        else:
            with open(p, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/":
            self._send(200, _doc_ui("board.html").encode("utf-8"),
                       "text/html; charset=utf-8")
        elif u.path in ("/ui/board.css", "/ui/board.js", "/ui/job-request.js",
                        "/ui/job-projection.js"):
            ten = u.path.rsplit("/", 1)[1]
            kieu = ("text/css" if ten.endswith(".css") else "application/javascript")
            self._send(200, _doc_ui(ten).encode("utf-8"), kieu + "; charset=utf-8")
        elif u.path == "/api/board":
            self._json(BOARD.read())
        elif u.path == "/api/jobs":
            # Kèm luôn NHÓM của từng việc: bảng hàng đợi phải xếp theo đoạn chat
            # thì mới đọc được "đang vẽ ai / còn nợ nhóm nào", chứ một danh sách
            # id phẳng thì nhìn cũng như không.
            _d = BOARD.read()
            _tat = {f["id"]: f for s in _d.get("scenes", []) for f in s.get("sfs", [])}
            _nh = {}
            for k in JOBS:
                if k.startswith("LO:"):
                    continue
                kh = _nhom_cua(k, _d)
                bt, ten = _ten_nhom(kh, _tat)
                _nh[k] = {"khoa": kh, "bieu_tuong": bt, "nhan": ten}
            # HÀNG ĐỢI THẬT + tình hình thợ, để giao diện nói được VÌ SAO một
            # việc đang chờ. Nhãn "chờ" tự nó là dấu vết đã ghi, không phải hàng
            # đợi — hai thứ lệch nhau được, và đúng lúc lệch là lúc user ngồi
            # nhìn Chrome rảnh mà việc không nhúc nhích.
            _hang = _runtime_queue_snapshot()
            _tho = {"img": {"song": 0, "ban": 0}, "vid": {"song": 0, "ban": 0}}
            for (_p, _k, _s), _t in list(WORKERS.items()):
                if _k in _tho and _t.is_alive():
                    _tho[_k]["song"] += 1
            for _id, _v in list(JOBS.items()):
                if _v.get("state") != "running":
                    continue
                # ident lô ("LO:a,b") là việc ảnh; ident shot (V-…) là việc video.
                _tho["vid" if _id.startswith("V-") else "img"]["ban"] += 1
            # DẤU VẾT từng việc — "việc này đã đi qua những đâu, tài khoản
            # nào, thử mấy lần". JOBS chỉ giữ trạng thái HIỆN TẠI nên không bao
            # giờ trả lời được câu đó; hộp 🐞 vì thế in dòng JOB không có giờ.
            vet_don()
            self._json({"jobs": JOBS, "auto": _auto_status(), "nhom": _nh,
                        "hang": _hang, "tho": _tho, "vet": VET,
                        "lifecycle": _runtime_lifecycle_snapshot(),
                        "pl": _pl_dem(), "dan_ma": _dan_ma_doc(),
                        # tổng số bản ghi lỗi từ lúc board chạy — giao diện so
                        # con số này để biết khi nào phải kéo phần mới về
                        "loi": _LOI_STT[0],
                        "auto_vid": _auto_vid_doc(),
                        "mtime": int(os.path.getmtime(BOARD.path))})
        elif u.path == "/api/chan-doan":
            # HÀNG ĐỢI ĐỨNG IM THÌ SOI Ở ĐÂY. Giao diện chỉ thấy JOBS, mà JOBS là
            # dấu vết đã ghi chứ không phải hiện trạng: việc có thể mang nhãn
            # "chờ" trong khi hàng đợi RAM đã rỗng (không ai nhấc nữa).
            _hang = _runtime_queue_snapshot()
            self._json({
                "hang_doi": {
                    "anh": len(_hang["anh"]),
                    "video": len(_hang["video"]),
                },
                "tho": {f"{p}·{k}·{s}": t.is_alive()
                        for (p, k, s), t in list(WORKERS.items())},
                "chet": dict(DEAD),
                "lo_dang_hoan": dict(_HOAN),
                "da_huy": sorted(DA_HUY)[:40],
                "dung_gen": dung_gen(),
                "job_cho": (
                    len(_runtime_labels_in_states(
                        "created", "queued", "retry_wait"))
                    if _JOB_MODE == "authoritative"
                    else sum(1 for v in JOBS.values()
                             if v.get("state") == "queued")
                ),
                "job_chay": (
                    len(_runtime_labels_in_states("running"))
                    if _JOB_MODE == "authoritative"
                    else sum(1 for v in JOBS.values()
                             if v.get("state") == "running")
                ),
                "bug_bridge": runtime_bug_diagnostics()["bug_bridge"],
                "job_shadow": _job_shadow_diagnostics(),
                "live_executor": _live_diagnostics(),
                "lich": _lich_diagnostics(),
                "invariants": _job_invariant_diagnostics(),
            })
        elif u.path == "/api/projects":
            self._json({
                "root": PROJECTS_ROOT,
                "current": os.path.basename(BOARD.dir),
                "kind": _project_kind(BOARD.dir, BOARD.read()),
                "port": SERVE_PORT,
                "cdp": CDP_ENDPOINTS,
                "items": _scan_projects(),
            })
        elif u.path == "/api/accounts":
            self._json({"accounts": _accounts_status(),
                        "tran_ref": TRAN_REF, "tran_ref_max": TRAN_REF_MAX})
        elif u.path == "/api/so-tk":
            self._json({"ok": True, "so": _so_tk_doc()})
        elif u.path == "/api/loi":
            # Sổ lỗi cho hộp 🐞. `tu` = số thứ tự bản ghi giao diện đã có, để mỗi
            # vòng poll chỉ tải phần MỚI thay vì cả 800 dòng.
            try:
                tu = int(q.get("tu", ["0"])[0] or 0)
            except ValueError:
                tu = 0
            with LOI_LOCK:
                ds = [m for m in LOI_SO if m["n"] > tu]
                tong = _LOI_STT[0]
            self._json({"loi": ds, "tong": tong})
        elif u.path == "/api/luot":
            # Hộp chờ. Giao diện chỉ gọi khi có việc lỗi mang số lượt, nên cứ trả
            # đủ — lượt đã gắn hết vẫn có ích để kéo ảnh sang thẻ khác.
            self._json({"luot": _pl_ds()})
        elif u.path.startswith("/pl/"):
            self._serve_pl(u.path, q)
        elif u.path.startswith("/assets/"):
            # PHẢI truyền q: '?w=' (bản thu nhỏ) và '?dl=1' (tải về đúng tên)
            # đều đọc từ đây. Thiếu nó thì mọi thumbnail lặng lẽ trả ảnh gốc
            # ~2.8MB — đúng thứ _thumb() sinh ra để tránh.
            self._serve_img(BOARD.assets, u.path, q)
        elif u.path.startswith("/versions/"):
            self._serve_img(BOARD.versions, u.path, q)
        elif u.path.startswith("/videos/"):
            self._serve_video(BOARD.videos, u.path)
        elif u.path.startswith("/vversions/"):
            self._serve_video(BOARD.vversions, u.path)
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n) if n else b""
        sf_id = q.get("sf", [""])[0]

        if u.path == "/api/board":
            data = json.loads(raw.decode("utf-8"))
            _sync_startframe(data)   # đổi SF trên board thì prompt phải đổi theo
            with BOARD_LOCK:
                _giu_dau_ban(data)
                BOARD.write(data)
            self._json({"ok": True, "mtime": int(os.path.getmtime(BOARD.path))})
        elif u.path == "/api/upload":
            if not re.match(r"^[A-Za-z0-9_\-]+$", sf_id):
                self._json({"ok": False, "err": "sf id không hợp lệ"}, 400); return
            _runtime_note_user_mutation(sf_id)
            BOARD.save_upload(sf_id, raw, q.get("name", ["x.png"])[0])
            self._json({"ok": True})
        elif u.path == "/api/open-project":
            ok, err, port = _open_project(q.get("dir", [""])[0])
            self._json({"ok": ok, "err": err, "port": port}, 200 if ok else 409)
        elif u.path == "/api/generate":
            # CHẶN CẢ 'queued', không riêng 'running'. Chỉ chặn 'running' thì bấm
            # Tạo lại lúc việc còn nằm chờ đẩy BẢN THỨ HAI cùng ident vào hàng:
            # thợ nhấc bản một làm xong, thợ khác nhấc bản hai chạy lại nguyên
            # lượt — với video là trừ credit lần nữa cho đúng shot vừa dựng xong.
            # `_auto_scene` đã chặn đúng cả hai nhãn từ trước; đây là áp lại luật
            # ấy cho đường tạo tay chứ không phải chính sách mới.
            _khoa = _request_idempotency_key(self, q, raw)
            _nhan = _job_state_for_asset(sf_id)
            if _nhan in ("running", "queued") and not _da_nhan_key(_khoa):
                self._json({"ok": False,
                            "err": "đang chạy" if _nhan == "running" else "đã nằm trong hàng chờ"})
                return
            _d0 = BOARD.read()
            if not _la_the_dia_diem(BOARD.get_sf(sf_id) or {"id": sf_id}):
                _ly = _cong_master(_nhom_cua(sf_id, _d0), _d0)
                if _ly:
                    self._json({"ok": False, "khoa": True,
                                "err": f"Chưa chạy được — {_ly}. Ảnh thẻ địa điểm là bản "
                                       f"neo khoá màu · ánh sáng · trục cho cả địa điểm; "
                                       f"chạy nó trước."}, 409)
                    return
            with BOARD_LOCK:                 # user chủ động tạo lại → bỏ khoá cũ
                data = BOARD.read(); ch = False
                for sc in data.get("scenes", []):
                    for sfd in sc.get("sfs", []):
                        if sfd.get("id") == sf_id and "picked" in sfd:
                            del sfd["picked"]; ch = True
                if ch:
                    BOARD.write(data)
            # MỘT BẢN THÌ ĐI ĐƯỜNG LÔ (lô một ảnh). Đường _generate đơn lẻ gọi
            # sess.generate() nên KHÔNG có chat_url và KHÔNG gửi luatchung —
            # prompt bây giờ đã cắt hết phần bối cảnh vì tin luatchung sẽ tới,
            # nên chạy đường đó là ra ảnh không có bối cảnh, không trục, không
            # luật chữ. Nhiều bản (n>1) vẫn đi đường cũ: mỗi bản một tài khoản
            # khác nhau, mà chat của địa điểm chỉ sống trên đúng một tài khoản.
            # MỌI ĐƯỜNG TẠO ẢNH ĐỀU ĐI CHUNG MỘT LỐI — kể cả tạo nhiều bản.
            # `prompt` của SF con chỉ còn máy quay và khung hình; bối cảnh, bảng
            # màu, ánh sáng, trục nằm trong `luatchung` gửi ở đầu tin. Đường cũ
            # (`sess.generate()`) không gửi luatchung nên ảnh mất hết neo look —
            # hỏng câm, nhìn ảnh vẫn đẹp.
            # `tay=True` nên KHÔNG bị bộ lọc "đã có ảnh" gạt đi.
            so_ban = max(1, min(int(q.get("n", ["1"])[0] or 1), 4))
            ident = "LO:" + sf_id
            nhan = {"state": "queued",
                    "msg": "chờ · 1 ảnh" if so_ban == 1
                           else f"chờ · {so_ban} bản song song"}
            bo_co_huy(ident, sf_id)   # user vừa bấm tạo → thắng cờ huỷ cũ
            TAY_SF.add(sf_id)
            yeu_cau = _yeu_cau_anh(sf_id, "http.generate")
            if so_ban > 1:
                # NHIỀU BẢN LÀ NHIỀU JOB CON, không phải một job xếp N lần —
                # mỗi bản có kết quả riêng nên phải mang định danh riêng.
                from jobs.models import BatchMode
                from jobs.producer import CreateBatchRequest
                yeu_cau = CreateBatchRequest(
                    tuple(yeu_cau for _ in range(so_ban)), BatchMode.MULTI_COPY)

            def _plan(ket_qua, _sf=sf_id, _ident=ident, _nhan=nhan, _n=so_ban):
                from jobs.compat import LegacyAction, LegacyPlan
                ids = tuple(job.job_id for job in ket_qua.jobs) if ket_qua else ()
                return LegacyPlan(tuple(
                    LegacyAction(
                        action_id=f"generate:{_ident}:{i}",
                        legacy_keys=(_sf, _ident),
                        job_ids=(ids[i],) if i < len(ids) else (),
                        queue_kind="img",
                        queue_ident=_ident,
                        manual=True,
                        # Chỉ bản đầu ghi nhãn gộp; N bản vẫn xếp đủ N lượt.
                        state=_nhan if i == 0 else None,
                        state_idents=(_sf,),
                        # Mỗi execution chỉ giữ một child, nhưng nhãn UI/shadow
                        # đại diện cho TOÀN BỘ batch multi-copy.
                        member_bindings=((_sf, ids), (_ident, ids)),
                    )
                    for i in range(_n)
                ))

            xong, meta = self._giao_viec(yeu_cau, _khoa, _plan)
            if not xong:
                return
            self._json({"ok": True, "qua_lo": True, "so_ban": so_ban, **meta})
        elif u.path == "/api/dung-het":
            # DỪNG TẤT CẢ: tắt mọi auto, vét sạch hàng đợi, và ĐÓNG CỬA SỔ CHROME
            # của những tài khoản ảnh đang bận. Đóng Chrome là cách DUY NHẤT cắt
            # được việc đang chạy: thợ đang nằm trong vòng chờ ChatGPT vẽ, không
            # có chỗ nào để nó ngó lại cờ huỷ giữa chừng.
            # Cùng critical section với chỗ auto COMMIT JOBS + queue. Nếu auto
            # commit trước thì cú vét bên dưới dọn nó; nếu stop vào trước thì
            # snapshot auto cũ thấy generation/identity lệch và tự bỏ.
            if _JOB_MODE == "authoritative":
                with AUTO_LOCK:
                    tang_dung_gen()
                    AUTO.clear()
                TAY_SF.clear()
                active_labels = _runtime_labels_in_states(
                    "created", "queued", "running", "retry_wait")
                cancelled, before = _runtime_cancel_labels(
                    active_labels, message="đã dừng")
                remaining = [
                    label for label in active_labels
                    if label not in cancelled
                    and any(
                        not _JOB_RUNTIME.job(job_id).state.is_terminal
                        for job_id in _runtime_job_ids_for_label(label)
                    )
                ]
                self._json({
                    "ok": True,
                    "bo": sum(before[label] == "queued" for label in cancelled),
                    "dung": sum(before[label] == "running" for label in cancelled),
                    "con_lai": remaining,
                    "dong_chrome": [],
                    "da_bam_stop": 0,
                })
                return
            with AUTO_LOCK:
                tang_dung_gen()  # thợ đang chạy dở soi số này, thấy đổi là không thử lại
                AUTO.clear()
            TAY_SF.clear()       # dừng hết = bỏ mọi ý định tạo tay còn treo
            bo = 0
            for Q in (IMG_QUEUE, VID_QUEUE):
                try:
                    while True:
                        it = Q.get_nowait()[2]           # (prio, seq, item) → item
                        _dat_job(it[1], {"state": "error", "msg": "đã dừng"})
                        Q.task_done(); bo += 1
                except queue.Empty:
                    pass
            dang = [k for k, v in JOBS.items() if v.get("state") in ("running", "queued")]
            with HUY_LOCK:
                # CHỈ đánh cờ việc ĐANG chờ/chạy. Bản cũ quét cả `JOBS` lấy mọi
                # ident "LO:…" — kể cả việc XONG TỪ LÂU — rồi nhét vào DA_HUY,
                # mà DA_HUY chỉ được dọn khi đúng thợ nhấc đúng ident đó. Hàng
                # đợi vừa bị vét xong nên chẳng ai nhấc, cờ nằm lại vĩnh viễn.
                # Ident giờ là danh sách SF user tích, nên lần sau tích lại đúng
                # nhóm ấy là ident TRÙNG y hệt → job mới bị ghi "đã huỷ" ngay
                # trong khi user vừa bấm tạo và không có lỗi gì.
                DA_HUY.update(dang)
                DA_HUY.update(k for k in dang if k.startswith("LO:"))
            for k in dang:
                JOBS[k] = {"state": "error", "msg": "đã dừng"}
            dong = []
            da_stop = 0
            with ACC_LOCK:
                ports = [a["port"] for a in ACCOUNTS if a.get("enabled")]
            # BẤM DỪNG LUÔN LUÔN, kể cả khi không đóng Chrome — đây mới là thứ
            # cắt thật. Lượt đang sinh chạy ở phía máy chủ OpenAI chứ không phải
            # trong trình duyệt: giết cửa sổ chỉ làm mình hết nhìn thấy, còn nó
            # vẫn vẽ tiếp và vẫn tính vào hạn mức.
            for pt in ports:
                try:
                    da_stop += _bam_stop_tren_tab(pt)
                except Exception as e:
                    _LOG.warning("không nối được %s để bấm dừng: %s", pt, e)
            if da_stop:
                _LOG.info("đã bấm dừng trên %d đoạn chat", da_stop)
            # ĐÓNG CHROME SAU khi đã bấm: đóng trước là mất luôn chỗ để bấm.
            if q.get("dong_chrome", ["1"])[0] == "1":
                for pt in ports:
                    try:
                        _kill_chrome(pt); dong.append(pt)
                    except Exception:
                        pass
            self._json({"ok": True, "bo": bo, "dung": len(dang),
                        "dong_chrome": dong, "da_bam_stop": da_stop})
        elif u.path == "/api/huy":
            # Chỉ vứt việc CHƯA chạy. Việc đang chạy phải để nó xong — cắt giữa
            # chừng là mất cả ảnh đã sinh mà không thu lại được.
            # VÉT CẢ HAI HÀNG. Bản cũ chỉ vét IMG_QUEUE, nên bấm "Huỷ việc đang
            # chờ" khi có 300 video xếp hàng thì báo "đã bỏ 0 việc" mà hàng video
            # vẫn chạy tiếp — lối duy nhất để dừng là "Dừng tất cả", kéo theo
            # đóng sạch Chrome và giết luôn việc ảnh đang chạy dở.
            if _JOB_MODE == "authoritative":
                queued = _runtime_labels_in_states(
                    "created", "queued", "retry_wait")
                cancelled, _before = _runtime_cancel_labels(
                    queued, message="đã huỷ khỏi hàng đợi")
                running = list(_runtime_labels_in_states("running"))
                self._json({
                    "ok": True,
                    "bo": len(cancelled),
                    "cho_da_huy": len(cancelled),
                    "dang_chay": running,
                })
                return
            bo = 0
            for Q in (IMG_QUEUE, VID_QUEUE):
                try:
                    while True:
                        it = Q.get_nowait()[2]           # (prio, seq, item) → item
                        _dat_job(it[1], {"state": "error", "msg": "đã huỷ khỏi hàng đợi"})
                        Q.task_done(); bo += 1
                except queue.Empty:
                    pass
            # việc đã ra khỏi hàng nhưng thợ chưa bắt tay làm: ghi vào DA_HUY để
            # thợ tự bỏ. Ident lô là "LO:a,b,c" nên phải suy ngược từ SF thành viên.
            cho = {k for k, v in JOBS.items() if v.get("state") == "queued"}
            with HUY_LOCK:
                for k in cho:
                    DA_HUY.add(k)
                for k in list(JOBS):
                    if k.startswith("LO:") and any(x in cho for x in k[3:].split(",")):
                        DA_HUY.add(k)
                DA_HUY.update("LO:" + ",".join(sorted(cho)) for _ in (0,))
            for k in cho:
                JOBS[k] = {"state": "error", "msg": "đã huỷ"}
            dang = [k for k, v in JOBS.items() if v.get("state") == "running"]
            self._json({"ok": True, "bo": bo, "cho_da_huy": len(cho), "dang_chay": dang})
        elif u.path == "/api/xoa-xong":
            # DỌN sổ việc ĐÃ XONG. Chỉ xoá dòng trạng thái — ảnh đã nằm trong
            # assets/ và versions/, nhật ký lượt vẫn còn trong cho-phan-loai/.
            bo = [k for k, v in JOBS.items() if v.get("state") == "done"]
            for k in bo:
                JOBS.pop(k, None)
            self._json({"ok": True, "bo": len(bo)})
        elif u.path == "/api/xoa-loi":
            # DỌN việc LỖI khỏi hàng đợi.
            #
            # Chỉ xoá DÒNG TRẠNG THÁI, không đụng ảnh hay prompt — việc lỗi đã
            # dừng rồi, giữ nó lại chỉ làm rối danh sách. Trước đây hàng lỗi không
            # có nút nào nên khi hàng đợi chỉ còn toàn lỗi, giao diện trông như
            # không cho thao tác gì.
            if (q.get("het", [""])[0] or "") in ("1", "true", "yes"):
                bo = [k for k, v in JOBS.items() if v.get("state") == "error"]
            else:
                sf = (q.get("sf", [""])[0] or "").strip()
                if JOBS.get(sf, {}).get("state") != "error":
                    self._json({"ok": False, "err": "việc này không ở trạng thái lỗi"}); return
                bo = [sf]
            for k in bo:
                JOBS.pop(k, None)
            self._json({"ok": True, "bo": len(bo)})
        elif u.path == "/api/dung-viec":
            # DỪNG RIÊNG một việc ĐANG CHẠY, không đụng các việc khác.
            # Thợ soi cờ này ở mỗi nhịp poll (5s) rồi bấm nút stop của ChatGPT và
            # thoát — nên chậm nhất vài giây là dừng thật.
            sf = (q.get("sf", [""])[0] or "").strip()
            if _JOB_MODE == "authoritative":
                raw_job_id = (q.get("job_id", [""])[0] or "").strip()
                try:
                    sf, requested_job_id, verdicts = _runtime_cancel_target(
                        sf, raw_job_id)
                except ValueError as exc:
                    self._json({"ok": False, "err": str(exc)}, 400)
                    return
                accepted = any(verdict.accepted for verdict in verdicts)
                if not accepted:
                    reason = (
                        verdicts[0].reason_code if verdicts
                        else "không tìm thấy durable job cho việc này")
                    self._json({"ok": False, "err": reason})
                    return
                is_video = BOARD.get_shot(sf)[0] is not None
                _runtime_project_state(
                    sf, {"state": "error", "msg": "đã dừng riêng"})
                self._json({"ok": True, "sf": sf,
                            "job_id": requested_job_id,
                            "video": is_video})
                return
            if JOBS.get(sf, {}).get("state") != "running":
                self._json({"ok": False, "err": "việc này không đang chạy"}); return
            with HUY_LOCK:
                DUNG_RIENG.add(sf)
            # VIDEO CHỈ DỪNG ĐƯỢC TRƯỚC KHI SUBMIT. Sau khi đã bấm gửi thì Grok
            # đã trừ credit — bỏ ngang là mất tiền mà không có clip, nên lượt đó
            # chạy nốt và lưu về. Nói thẳng trên nhãn để user không ngồi đợi một
            # cú dừng không tới.
            _la_vid = BOARD.get_shot(sf)[0] is not None
            JOBS[sf] = {"state": "running",
                        "msg": "đang dừng… (chỉ cắt được nếu Grok CHƯA submit; đã "
                               "submit thì chạy nốt vì credit đã trừ)" if _la_vid
                               else "đang dừng… (thợ soi cờ mỗi 5s)"}
            self._json({"ok": True, "sf": sf, "video": _la_vid})
        elif u.path == "/api/huy-viec":
            # HUỶ ĐÚNG MỘT VIỆC, không phải cả hàng đợi.
            #
            # Một lô là MỘT tin nhắn nên không cắt đôi được: cách làm là huỷ lô cũ
            # rồi xếp lại lô mới gồm các thành viên còn lại. Việc ĐANG CHẠY thì
            # không cắt được (thợ đang nằm trong lượt chờ ChatGPT vẽ) — chỉ có
            # "Dừng tất cả" mới cắt nổi, vì nó đóng Chrome.
            sf = (q.get("sf", [""])[0] or "").strip()
            if _JOB_MODE == "authoritative":
                raw_job_id = (q.get("job_id", [""])[0] or "").strip()
                try:
                    sf, requested_job_id, verdicts = _runtime_cancel_target(
                        sf, raw_job_id)
                except ValueError as exc:
                    self._json({"ok": False, "err": str(exc)}, 400)
                    return
                accepted = tuple(
                    verdict for verdict in verdicts if verdict.accepted)
                if not verdicts:
                    self._json({
                        "ok": False,
                        "err": "không tìm thấy durable job cho việc này",
                    })
                    return
                if not accepted:
                    self._json({
                        "ok": False,
                        "err": verdicts[0].reason_code,
                    })
                    return
                _runtime_project_state(
                    sf, {"state": "error", "msg": "đã huỷ riêng việc này"})
                if BOARD.get_shot(sf)[0] is not None:
                    self._json({"ok": True, "video": True,
                                "job_id": requested_job_id})
                else:
                    self._json({
                        "ok": True,
                        "bo_lo": len(accepted),
                        "con_lai": 0,
                        "job_id": requested_job_id,
                    })
                return
            if not sf:
                self._json({"ok": False, "err": "thiếu tham số sf"}); return
            if JOBS.get(sf, {}).get("state") == "running":
                self._json({"ok": False, "err": "việc này ĐANG CHẠY — không cắt giữa "
                                                "chừng được. Dùng '⏹ Dừng tất cả'."}); return
            # VIỆC VIDEO: một shot là một việc rời, không có lô để xé — chỉ cần
            # đánh cờ huỷ rồi thợ tự bỏ khi nhấc tới. Bản cũ không có nhánh này
            # nên mọi ident video rơi xuống vòng quét "LO:…" bên dưới, không khớp
            # gì cả và trả về "đã huỷ 0 lô" trong khi việc vẫn nằm nguyên.
            if BOARD.get_shot(sf)[0] is not None:
                with HUY_LOCK:
                    DA_HUY.add(sf)
                JOBS[sf] = {"state": "error", "msg": "đã huỷ riêng việc này"}
                self._json({"ok": True, "video": True}); return
            bo = _lo_chua(sf)
            con_lai = []
            for k in bo:
                con_lai = [x for x in k[3:].split(",") if x and x != sf]
            if _JOB_SCHEDULER is not None and bo:
                try:                        # lịch cũng phải biết lô này chết rồi
                    _JOB_SCHEDULER.cancel_member(sf)
                except Exception:           # noqa: BLE001
                    pass
            with HUY_LOCK:
                DA_HUY.update(bo)
            with _CR_LOCK:                       # gỡ khỏi hàng giao đích danh
                for p, ds in CHO_RIENG.items():
                    CHO_RIENG[p] = [i for i in ds if i not in set(bo)]
            for k in bo:
                JOBS.pop(k, None)
            if con_lai:                          # xếp lại phần còn lại thành lô mới
                mid = "LO:" + ",".join(con_lai)
                for i in con_lai:
                    JOBS[i] = {"state": "queued", "msg": f"chờ lô {len(con_lai)} ảnh (đã bớt 1)"}
                _xep(IMG_QUEUE, ("img", mid, 0, True))
            JOBS[sf] = {"state": "error", "msg": "đã huỷ riêng việc này"}
            self._json({"ok": True, "bo_lo": len(bo), "con_lai": len(con_lai)})
        elif u.path == "/api/master":
            # LIỆT KÊ / CHẠY HẾT THẺ ĐỊA ĐIỂM — đúng nếp cũ: xong toàn bộ ảnh gốc
            # rồi mới tới khung con. Không có tham số `chay` thì chỉ đếm để giao
            # diện hỏi trước; thẻ ĐÃ DUYỆT không bao giờ bị đụng tới.
            data = BOARD.read()
            ds = [f for s in data.get("scenes", []) for f in s.get("sfs", [])
                  if _la_the_dia_diem(f)]
            chua_anh = [f["id"] for f in ds if not BOARD.find_file(f["id"])]
            chua_duyet = [f["id"] for f in ds
                          if BOARD.find_file(f["id"]) and f.get("status") != "approved"]
            xong = [f["id"] for f in ds if f.get("status") == "approved"]
            if (q.get("chay", [""])[0] or "") not in ("1", "true", "yes"):
                self._json({"ok": True, "tong": len(ds), "chua_anh": chua_anh,
                            "chua_duyet": chua_duyet, "da_duyet": xong})
                return
            lai = (q.get("lai", [""])[0] or "") in ("1", "true", "yes")
            can = chua_anh + (chua_duyet if lai else [])
            if not can:
                self._json({"ok": False, "err": "không còn thẻ địa điểm nào cần chạy"})
                return
            # MỖI THẺ ĐỊA ĐIỂM MỘT LÔ RIÊNG. Chúng thuộc các địa điểm khác nhau
            # nên không chung chat được, và mỗi cái chạy chat trắng của chính nó.
            can = sorted(can, key=_uu_tien)
            for i in can:
                TAY_SF.add(i)
            from jobs.models import BatchMode
            from jobs.producer import CreateBatchRequest
            yeu_cau = CreateBatchRequest(
                tuple(_yeu_cau_anh(i, "http.master") for i in can),
                BatchMode.IMAGE_GROUP,
            )

            def _plan(ket_qua, _can=tuple(can)):
                from jobs.compat import LegacyAction, LegacyPlan
                return LegacyPlan(tuple(
                    LegacyAction(
                        action_id=f"master:{sf}",
                        legacy_keys=(sf, "LO:" + sf),
                        job_ids=_job_ids_cua(ket_qua, (i,)),
                        queue_kind="img",
                        queue_ident="LO:" + sf,
                        manual=True,
                        state={"state": "queued",
                               "msg": "chờ chạy ảnh gốc địa điểm"},
                        state_idents=(sf,),
                    )
                    for i, sf in enumerate(_can)
                ))

            xong, meta = self._giao_viec(
                yeu_cau, _request_idempotency_key(self, q, raw), _plan)
            if not xong:
                return
            _LOG.info("chạy %d thẻ địa điểm: %s", len(can), ", ".join(can))
            self._json({"ok": True, "so": len(can), "ds": can, **meta})
        elif u.path == "/api/xem-lo":
            # XEM TRƯỚC cách chia lô — KHÔNG xếp hàng, KHÔNG chạy gì.
            #
            # Đây là câu hỏi người dùng luôn phải đoán: "cái nào đi CHUNG một đoạn
            # chat, cái nào TÁCH?". Luật đã có sẵn trong code (đoạn chat = địa điểm
            # = thẻ master, leo theo refs.bg) nhưng không hiện ở đâu trên giao diện,
            # nên mỗi lần bấm Tạo là một lần đánh cược. Endpoint này chỉ tính đúng
            # phép chia mà /api/tao-lo sẽ làm, rồi trả về để giao diện bày ra trước.
            ids = [x for x in (q.get("sf", [""])[0] or "").split(",") if x.strip()]
            if not ids:
                self._json({"ok": False, "err": "chưa chọn SF nào"}); return
            data = BOARD.read()
            tat = {f["id"]: f for s in data.get("scenes", []) for f in s.get("sfs", [])}
            nhom: dict[str, list[str]] = {}
            for i in ids:
                nhom.setdefault(_nhom_cua(i, data), []).append(i)
            # đếm sẵn số ảnh đã có theo từng master để không leo lại cho mỗi nhóm
            dem_master: dict[str, int] = {}
            for f in tat.values():
                if BOARD.find_file(f["id"]):
                    m = _nhom_cua(f["id"], data)
                    dem_master[m] = dem_master.get(m, 0) + 1
            out = []
            for m, xs in nhom.items():
                xs.sort(key=_uu_tien)
                lo = [{"sf": x,
                       "ky_tu": sum(len((tat.get(i) or {}).get("prompt") or "")
                                    for i in x)}
                      for x in _chia_lo(
                          xs, lambda i: _ref_id_cua_sf(i, data),
                          TRAN_MAY_TU_GOM, TRAN_REF,
                          allow_internal_dependencies=_live_executor_enabled())]
                bieu_tuong, ten = _ten_nhom(m, tat)
                # Nhóm toàn thẻ địa điểm thì KHÔNG tự gác chính mình.
                _chi_goc = all(_la_the_dia_diem(tat.get(i) or {"id": i}) for i in xs)
                out.append({
                    "khoa": "" if _chi_goc else _cong_master(m, data),
                    "master": m,
                    "loai": ("dia_diem" if _khoa_la_the(m) else
                             "nhan_vat" if m.startswith("NV:") else
                             "dao_cu" if m == "PROP" else "le"),
                    "bieu_tuong": bieu_tuong,
                    "nhan": ten,
                    "da_co": dem_master.get(m, 0),
                    "lo": lo,
                })
            out.sort(key=lambda x: (x["master"] == "", x["master"]))
            self._json({"ok": True, "nhom": out,
                        "tran_may_tu_gom": TRAN_MAY_TU_GOM,
                        "tran_ky_tu_khuyen": 8000})
        elif u.path == "/api/tao-lo":
            # GOM THEO ĐỊA ĐIỂM rồi mới xếp hàng: mỗi địa điểm là một đoạn chat,
            # nên các SF cùng địa điểm phải đi CHUNG một tin nhắn. Tích 2 ảnh ở
            # Sảnh + 1 ở Bếp = 2 lô, không phải 3 lượt riêng.
            ids = [x for x in (q.get("sf", [""])[0] or "").split(",") if x.strip()]
            if not ids:
                self._json({"ok": False, "err": "chưa chọn SF nào"}); return
            data = BOARD.read()
            _khoa = _request_idempotency_key(self, q, raw)
            _lai_key = _da_nhan_key(_khoa)      # bấm lại đúng cùng một ý định
            nhom: dict[str, list[str]] = {}
            for i in ids:
                # Bỏ qua cả 'queued', không riêng 'running' — cùng lý do với
                # `/api/generate`: xếp thêm bản nữa cho việc đang chờ là bắt thợ
                # render hai lượt. `_auto_scene` đã dùng đúng cặp nhãn này.
                if _job_is_active(i) and not _lai_key:
                    continue
                nhom.setdefault(_nhom_cua(i, data), []).append(i)
            # TÍCH LẪN ĐỊA ĐIỂM → KHÔNG CHO CHẠY (2026-08-12, theo yêu cầu user).
            # Một tin nhắn chỉ mang được MỘT khối `luatchung`, mà luật chung tả
            # nguyên bối cảnh. Nhét chung thì ChatGPT không biết luật nào áp cho
            # ảnh nào — ảnh trong nhà mọc ra bậc thềm.
            _loi_lan = _lan_dia_diem(nhom, data)
            if _loi_lan:
                self._json({"ok": False, "lan": True, "err": _loi_lan}, 409)
                return

            # CHẶN NGAY TẠI CỬA. Thợ cũng chặn (đó mới là chốt thật), nhưng chặn
            # ở đây để user biết LIỀN thay vì thấy cả loạt job đỏ vài giây sau.
            _chan = []
            for m, xs in nhom.items():
                if all(_la_the_dia_diem(BOARD.get_sf(i, data) or {"id": i}) for i in xs):
                    continue                      # lô toàn thẻ địa điểm — không tự gác
                ly = _cong_master(m, data)
                if ly:
                    _chan.append(f"{_ten_gon(m, data)}: {ly}")
            if _chan:
                self._json({"ok": False, "khoa": True,
                            "err": "Chưa chạy được — " + " · ".join(_chan[:4])
                                   + ". Ảnh thẻ địa điểm là bản neo khoá màu · ánh sáng "
                                     "· trục cho cả địa điểm; chạy nó trước."},
                           409)
                return
            with BOARD_LOCK:                 # user chủ động tạo lại → bỏ khoá cũ
                ch = False
                for sc in data.get("scenes", []):
                    for sfd in sc.get("sfs", []):
                        if sfd.get("id") in ids and "picked" in sfd:
                            del sfd["picked"]; ch = True
                if ch:
                    BOARD.write(data)
            # ÉP TÀI KHOẢN (tham số tk=<cổng>) — chạy việc này trên đúng một
            # tài khoản do user chỉ định.
            #
            # Chat sống trong profile Chrome của đúng tài khoản đã mở nó, nên
            # KHÔNG thể bê chat cũ sang tài khoản khác. Vì vậy ép tài khoản luôn
            # kéo theo MỞ CHAT MỚI cho nhóm — và đó đúng là thứ cần khi chat cũ
            # hỏng. Đã đo: 2 prompt hỏng 3 lần liền trong chat cũ, đưa sang chat
            # trắng CÙNG tài khoản thì ra đủ 2/2.
            ep = 0
            try:
                ep = int((q.get("tk", [""])[0] or "0").strip() or 0)
            except ValueError:
                ep = 0
            # Cờ `moi=1` đã bỏ 2026-08-12: lần nào cũng là chat trắng.

            # CẮT THEO ĐÚNG TRẦN, kể cả lô user tự tích (đảo luật 2026-08-12).
            #
            # Luật cũ: tích bao nhiêu gửi bấy nhiêu trong ĐÚNG một tin, vì cắt hộ
            # thì user tưởng mình gửi một tin mà thực ra hai — hai tin là hai chat
            # trắng nên look có thể lệch.
            #
            # User chốt lại 2026-08-15: tích 15 thì cũng KHÔNG tạo được. Log
            # ALTAR cùng ngày cho thấy lô 14-17 ref hỏng MỌI lượt và tắt sạch 6
            # tài khoản vì "không đính được ảnh ref", trong khi lô 5 ref cùng phút
            # chạy sạch. Nên "một tin nhắn" ấy chỉ là một tin trên lý thuyết —
            # thực tế nó không bao giờ tới nơi. Chia ra thì còn chạy được.
            #
            # `/api/xem-lo` dùng CHUNG phép chia này, nên ô xem trước vẫn nói
            # đúng cái sắp xảy ra — đó là điều kiện để việc cắt không thành cắt
            # lén sau lưng user.
            cac_lo = []          # [(ident, (sf,…), nhãn)] — thứ tự = thứ tự xếp
            for m, xs in nhom.items():
                xs.sort(key=_uu_tien)
                for lo in _chia_lo(
                        xs, lambda i: _ref_id_cua_sf(i, data),
                        TRAN_MAY_TU_GOM, TRAN_REF,
                        allow_internal_dependencies=_live_executor_enabled()):
                    ident = "LO:" + ",".join(lo)
                    bo_co_huy(ident, *lo)   # user vừa bấm tạo → thắng cờ huỷ cũ
                    TAY_SF.update(lo)       # …và giữ cờ tạo-tay nếu phải xếp lại
                    cac_lo.append((ident, tuple(lo),
                                   {"state": "queued",
                                    "msg": f"chờ · {len(lo)} ảnh · {_ten_gon(m)}"
                                           + (f" · ép cổng {ep}" if ep else "")}))
            so_lo = len(cac_lo)
            if not cac_lo:      # mọi SF đã nằm trong hàng — không có gì để giao
                self._json({"ok": True, "so_lo": 0, "ep_tk": ep, "lo": {},
                            **_producer_metadata(None)})
                return
            thanh_vien = [sf for _, lo, _ in cac_lo for sf in lo]
            vi_tri = {sf: i for i, sf in enumerate(thanh_vien)}
            from jobs.models import BatchMode
            from jobs.producer import CreateBatchRequest
            yeu_cau = CreateBatchRequest(
                tuple(_yeu_cau_anh(sf, "http.tao-lo", ep=ep) for sf in thanh_vien),
                BatchMode.IMAGE_GROUP,
            )

            def _plan(ket_qua, _cac_lo=tuple(cac_lo), _vi_tri=vi_tri, _ep=ep):
                from jobs.compat import LegacyAction, LegacyPlan
                viec = []
                for ident, lo, nhan in _cac_lo:
                    ids = _job_ids_cua(ket_qua, [_vi_tri[sf] for sf in lo])
                    viec.append(LegacyAction(
                        action_id=f"tao-lo:{ident}",
                        legacy_keys=(ident,),
                        job_ids=ids,
                        queue_kind="img",
                        queue_ident=ident,
                        manual=True,
                        state=nhan,
                        state_idents=lo,
                        forced_account_id=str(_ep) if _ep else None,
                        # Mỗi SF thành viên trỏ vào ĐÚNG job của nó.
                        member_bindings=tuple(
                            (sf, (ids[k],)) for k, sf in enumerate(lo)
                            if k < len(ids)
                        ),
                    ))
                return LegacyPlan(tuple(viec))

            xong, meta = self._giao_viec(yeu_cau, _khoa, _plan)
            if not xong:
                return
            self._json({"ok": True, "so_lo": so_lo, "ep_tk": ep,
                        "lo": {m: len(x) for m, x in nhom.items()}, **meta})
        elif u.path == "/api/dan-ma":
            # Bật/tắt việc in mã SF vào góc ảnh. Chỉ ảnh render TỪ ĐÂY VỀ SAU
            # đổi theo — ảnh đã có trên đĩa giữ nguyên như lúc nó được vẽ.
            on = (q.get("on", [""])[0] or "") in ("1", "true", "yes")
            _dan_ma_ghi(on)
            _LOG.info("dán mã SF vào ảnh: %s", "BẬT" if on else "TẮT")
            self._json({"ok": True, "on": on})
        elif u.path == "/api/loi-xoa":
            with LOI_LOCK:
                so = len(LOI_SO)
                LOI_SO.clear()
            self._json({"ok": True, "so": so})
        elif u.path == "/api/gan-anh":
            # Gắn TAY một ảnh của hộp chờ vào thẻ. Đây là đường ra của lượt lệch:
            # ảnh đã tải về rồi, chỉ còn chỉ đúng nó thuộc thẻ nào.
            try:
                _t = int(q.get("turn", ["0"])[0] or 0)
                _o = int(q.get("o", ["0"])[0] or 0)
            except ValueError:
                self._json({"ok": False, "err": "turn/o phải là số"}, 400); return
            _sf = q.get("sf", [""])[0]
            ok, err = _pl_gan(_sf, _t, _o) if (_sf and _t and _o) else \
                (False, "thiếu sf/turn/o")
            self._json({"ok": ok, "err": err}, 200 if ok else 409)
        elif u.path == "/api/gan-lui":
            # HOÀN TÁC lần gắn gần nhất (hoặc n lần). Đây là lý do gắn tay không
            # đáng sợ: bấm nhầm thì lùi được, kể cả khi thẻ vốn chưa có ảnh.
            try:
                n = int(q.get("n", ["1"])[0] or 1)
            except ValueError:
                n = 1
            so, mo_ta = _ht_lui(n)
            self._json({"ok": so > 0, "so": so, "viec": mo_ta,
                        "con": len(HOAN_TAC),
                        "err": "" if so else "không còn lần gắn nào để lùi"})
        elif u.path == "/api/sf-doi":
            # TRÁO ĐỔI ảnh của HAI thẻ. Ca thật: ChatGPT vẽ đúng cả hai khung
            # nhưng trả ngược thứ tự, nên hai thẻ đeo ảnh của nhau — chép một
            # chiều thì phải làm hai lần và ở giữa có một khoảnh khắc cả hai
            # cùng một ảnh, rất dễ bấm nhầm tiếp.
            a, b = q.get("a", [""])[0], q.get("b", [""])[0]
            fa, fb = (BOARD.find_file(a) if a else None), (BOARD.find_file(b) if b else None)
            if a == b or not fa or not fb:
                self._json({"ok": False,
                            "err": "cần HAI thẻ khác nhau và cả hai đều đã có ảnh"}, 400)
                return
            # ẢNH ĐÃ DUYỆT KHÔNG BAO GIỜ BỊ THAY — tráo là ghi đè cả hai chiều,
            # nên chỉ cần một bên đã chốt là từ chối, đừng làm nửa vời.
            for i in (a, b):
                if (BOARD.get_sf(i) or {}).get("status") == "approved":
                    self._json({"ok": False,
                                "err": f"{i} ĐÃ DUYỆT — không tráo. Bỏ duyệt trước "
                                       f"nếu thật sự muốn đổi."}, 409)
                    return
            try:
                raw_a, raw_b = open(fa, "rb").read(), open(fb, "rb").read()
            except OSError as e:
                self._json({"ok": False, "err": str(e)[:120]}, 500); return
            cu_a, tao_a = _ban_dang_dung(a)
            cu_b, tao_b = _ban_dang_dung(b)
            with BOARD_LOCK:
                out_a = BOARD.next_version_path(a, reserve=True)
                out_b = BOARD.next_version_path(b, reserve=True)
            try:
                open(out_a, "wb").write(raw_b)      # a nhận ảnh của b
                open(out_b, "wb").write(raw_a)      # b nhận ảnh của a
            except OSError as e:
                _drop_reserved(out_a); _drop_reserved(out_b)
                self._json({"ok": False, "err": str(e)[:120]}, 500); return
            _runtime_note_user_mutation(a)
            _runtime_note_user_mutation(b)
            with BOARD_LOCK:
                BOARD.set_current(a, out_a)
                BOARD.set_current(b, out_b)
            _mark_picked(a, "picked", os.path.basename(out_a))
            _mark_picked(b, "picked", os.path.basename(out_b))
            # MỘT CÚ TRÁO = MỘT LẦN HOÀN TÁC. Ghi hai dòng cùng `cap` để nút ↩
            # lùi cả hai chiều trong một nhát; lùi nửa vời còn tệ hơn không lùi.
            cap = f"doi-{time.time():.3f}"
            _ht_ghi({"sf": a, "moi": os.path.basename(out_a), "cu": cu_a,
                     "cu_tu_tao": tao_a, "turn": 0, "ten": f"tráo với {b}",
                     "duyet": False, "cap": cap, "luc": time.strftime("%H:%M:%S")})
            _ht_ghi({"sf": b, "moi": os.path.basename(out_b), "cu": cu_b,
                     "cu_tu_tao": tao_b, "turn": 0, "ten": f"tráo với {a}",
                     "duyet": False, "cap": cap, "luc": time.strftime("%H:%M:%S")})
            _LOG.info("tráo ảnh %s ⇄ %s", a, b)
            self._json({"ok": True, "msg": f"đã tráo {a} ⇄ {b}"})
        elif u.path == "/api/sf-chuyen":
            # KÉO ảnh từ thẻ này sang thẻ kia — đường sửa khi ảnh nằm nhầm thẻ.
            # CHÉP chứ không chuyển: thẻ nguồn giữ nguyên. Chuyển thật thì thẻ
            # nguồn hoá trắng và không có gì hoàn tác được, trong khi bản thừa ở
            # thẻ đích thì chỉ cần xoá một bản trong dãy.
            tu, den = q.get("tu", [""])[0], q.get("den", [""])[0]
            src = BOARD.find_file(tu) if tu else None
            if not src:
                self._json({"ok": False, "err": f"{tu} chưa có ảnh nào"}, 404); return
            if not BOARD.get_sf(den):
                self._json({"ok": False, "err": f"không có SF {den}"}, 404); return
            cu, cu_tu_tao = _ban_dang_dung(den)   # chụp hiện trạng để còn lùi được
            with BOARD_LOCK:
                out = BOARD.next_version_path(den, reserve=True)
            try:
                shutil.copy2(src, out)
            except OSError as e:
                _drop_reserved(out)
                self._json({"ok": False, "err": str(e)[:120]}, 500); return
            nk = (BOARD.turn_log().get(
                (BOARD.get_sf(tu) or {}).get("picked") or "") or {})
            if nk.get("turn"):        # giữ vết lượt gốc để còn lần ngược được
                BOARD.turn_log_ghi(os.path.basename(out), {**nk, "chuyen_tu": tu})
            sf_den = BOARD.get_sf(den) or {}
            _duyet = sf_den.get("status") == "approved" and BOARD.find_file(den)
            _ht_ghi({"sf": den, "moi": os.path.basename(out), "cu": cu,
                     "cu_tu_tao": cu_tu_tao, "turn": 0, "ten": f"chép từ {tu}", "duyet": bool(_duyet),
                     "luc": time.strftime("%H:%M:%S")})
            if _duyet:
                self._json({"ok": True, "msg": f"{den} ĐÃ DUYỆT — chỉ thêm vào dãy bản"}); return
            _runtime_note_user_mutation(den)
            with BOARD_LOCK:
                BOARD.set_current(den, out)
            _mark_picked(den, "picked", os.path.basename(out))
            _LOG.info("chép ảnh %s → %s (%s)", tu, den, os.path.basename(out))
            self._json({"ok": True, "msg": "đã đặt làm ảnh chính"})
        elif u.path == "/api/pick-version":
            f = q.get("file", [""])[0]
            src = os.path.join(BOARD.versions, os.path.basename(f))
            if os.path.isfile(src):
                _runtime_note_user_mutation(sf_id)
                BOARD.set_current(sf_id, src)
                # GHI NHỚ lựa chọn của user: các lần render sau sẽ chỉ thêm bản
                # mới vào versions/, KHÔNG được ghi đè bản user đã chọn.
                with BOARD_LOCK:
                    data = BOARD.read()
                    for sc in data.get("scenes", []):
                        for sfd in sc.get("sfs", []):
                            if sfd.get("id") == sf_id:
                                sfd["picked"] = os.path.basename(src)
                    BOARD.write(data)
                self._json({"ok": True})
            else:
                self._json({"ok": False, "err": "không thấy bản này"}, 404)
        elif u.path == "/api/del-version":
            # Xoá MỘT bản trong versions/. Không cho xoá bản đang được dùng làm
            # ảnh chính — muốn bỏ thì chọn bản khác trước, hoặc dùng "xoá tất cả".
            f = os.path.basename(q.get("file", [""])[0])
            src = os.path.join(BOARD.versions, f)
            if not os.path.isfile(src):
                self._json({"ok": False, "err": "không thấy bản này"}, 404); return
            cur = BOARD.find_file(sf_id)
            if cur and os.path.getsize(cur) == os.path.getsize(src):
                try:
                    same = open(cur, "rb").read() == open(src, "rb").read()
                except Exception:
                    same = False
                if same:
                    self._json({"ok": False, "err": "Đây là bản ĐANG DÙNG làm ảnh "
                                "chính. Chọn bản khác trước rồi hãy xoá."}, 409); return
            os.remove(src)
            with BOARD_LOCK:                 # cờ picked trỏ vào bản vừa xoá thì gỡ
                data = BOARD.read(); ch = False
                for sc in data.get("scenes", []):
                    for sfd in sc.get("sfs", []):
                        if sfd.get("id") == sf_id and sfd.get("picked") == f:
                            del sfd["picked"]; ch = True
                if ch:
                    BOARD.write(data)
            _LOG.info("xoá bản %s của %s", f, sf_id)
            self._json({"ok": True})
        elif u.path == "/api/del-vversion":
            # Tương tự cho video.
            f = os.path.basename(q.get("file", [""])[0])
            src = os.path.join(BOARD.vversions, f)
            if not os.path.isfile(src):
                self._json({"ok": False, "err": "không thấy bản này"}, 404); return
            cur = BOARD.video_file(sf_id)
            if cur and os.path.getsize(cur) == os.path.getsize(src):
                self._json({"ok": False, "err": "Đây là bản ĐANG DÙNG. Chọn bản "
                            "khác trước rồi hãy xoá."}, 409); return
            os.remove(src)
            with BOARD_LOCK:
                data = BOARD.read(); ch = False
                for sc in data.get("scenes", []):
                    for shd in sc.get("shots", []):
                        if shd.get("id") == sf_id and shd.get("vpicked") == f:
                            del shd["vpicked"]; ch = True
                if ch:
                    BOARD.write(data)
            _LOG.info("xoá bản video %s của %s", f, sf_id)
            self._json({"ok": True})
        elif u.path == "/api/delete-files":
            _runtime_note_user_mutation(sf_id)
            BOARD.delete_sf_files(sf_id)
            with BOARD_LOCK:
                data = BOARD.read()
                for sc in data.get("scenes", []):
                    for sfd in sc.get("sfs", []):
                        if sfd.get("id") == sf_id and "picked" in sfd:
                            del sfd["picked"]
                BOARD.write(data)
            self._json({"ok": True})
        # ---------- accounts ----------
        elif u.path == "/api/auto-video":
            # Công tắc auto-video: CHỈ chi phối vòng quét tự động, không chặn nút tay.
            want = q.get("on", [""])[0]
            if want != "":
                _auto_vid_ghi(want == "1")
                _LOG.info("AUTO-VIDEO %s", "BẬT" if want == "1" else "TẮT")
            self._json({"ok": True, "on": _auto_vid_doc()}); return
        elif u.path == "/api/auto":
            # Bật/tắt chế độ chạy tự động cho một scene (hoặc tắt tất cả).
            op = q.get("op", ["toggle"])[0]
            sid = q.get("scene", [""])[0]
            if op == "offall":
                with AUTO_LOCK:
                    AUTO.clear()
                self._json({"ok": True, "auto": {}}); return
            if op == "onall":
                # Bật auto cho MỌI scene còn thiếu ảnh — nút "bố" của từng nút
                # "Chạy hết". Không đụng REF: thẻ nhân vật và đạo cụ là bản neo,
                # user tự chọn tự duyệt từng cái, không giao cho máy quét.
                # Scene đã đủ ảnh bị bỏ qua để auto khỏi tự tắt ngay vòng đầu.
                # KHÔNG GỒM REF (user chốt 2026-08-13). Thẻ nhân vật, đạo cụ
                # và thẻ địa điểm là BẢN NEO của cả phim: sai một cái là mọi
                # scene bám vào nó sai theo, nên chúng phải được nhìn và duyệt
                # từng cái. REF có nút "▶ Chạy hết" riêng ở header của nó cho ai
                # muốn chạy hàng loạt.
                _d = BOARD.read()
                _mo = []
                for sc in _d.get("scenes", []):
                    if sc["id"] == "REF":
                        continue
                    if any(not f.get("image") for f in sc.get("sfs", [])):
                        _mo.append(sc["id"])
                with AUTO_LOCK:
                    for sid2 in _mo:
                        AUTO.setdefault(sid2, {"try": {}, "last": {}, "stat": {}})
                _AUTO_WAKE.set()
                _LOG.info("bật auto cho %d scene: %s", len(_mo), ", ".join(_mo))
                self._json({"ok": True, "so": len(_mo), "scenes": _mo,
                            "auto": _auto_status()}); return
            if not sid:
                self._json({"ok": False, "err": "thiếu scene"}, 400); return
            with AUTO_LOCK:
                if op == "off" or (op == "toggle" and sid in AUTO):
                    AUTO.pop(sid, None)
                else:
                    AUTO[sid] = {"try": {}, "last": {}, "stat": {}}
                    _AUTO_WAKE.set()      # quét ngay, đừng bắt user đợi hết vòng
            self._json({"ok": True, "on": sid in AUTO, "auto": _auto_status()})

        elif u.path == "/api/so-tk":
            # Số tài khoản ChatGPT chạy ĐỒNG THỜI. Board tự bật/tắt để giữ đúng
            # con số này — kể cả khi một tài khoản bị chặn và phải nghỉ.
            want = (q.get("n", [""])[0] or "").strip()
            if want:
                _so_tk_ghi(want)
                _LOG.info("đặt số tài khoản chạy đồng thời: %s", _so_tk_doc())
                try:
                    _giu_du_tai_khoan()
                except Exception as e:
                    _LOG.warning("giữ đủ tài khoản lỗi: %s", str(e)[:90])
            self._json({"ok": True, "so": _so_tk_doc()})
        elif u.path == "/api/acct":
            op = q.get("op", [""])[0]
            port = int(q.get("port", ["0"])[0] or 0)
            if op == "tran-ref":
                # Trần chung cho cả board, không theo tài khoản — nó là giới hạn
                # của MỘT TIN NHẮN ChatGPT, tài khoản nào cũng vậy.
                self._json({"ok": True, "tran_ref": _dat_tran_ref(q.get("n", ["10"])[0])})
                return
            with ACC_LOCK:
                acc = next((a for a in ACCOUNTS if a["port"] == port), None)
            if op == "add":
                kind = q.get("kind", ["img"])[0]
                with ACC_LOCK:
                    new_port = max([a["port"] for a in ACCOUNTS], default=9221) + 1
                    prefix = "chrome" if kind == "img" else "grok"
                    n = sum(1 for a in ACCOUNTS if a["kind"] == kind) + 1
                    acc = {"id": f"{'gpt' if kind == 'img' else 'grok'}-{n}", "kind": kind,
                           "port": new_port, "profile": f"~/.grokpipe-{prefix}-p{new_port}",
                           "enabled": True}
                    ACCOUNTS.append(acc)
                _save_accounts()
                _launch_chrome(acc)
                self._json({"ok": True, "acct": acc}); return
            if not acc:
                self._json({"ok": False, "err": "không thấy tài khoản"}, 404); return
            if op == "ten":
                # TÊN GỌI RIÊNG, KHÔNG ĐỘNG VÀO `id`. `id` là khoá kỹ thuật: nó
                # nằm trong log, trong nhãn dán vào thông báo lỗi, và trong tên
                # thư mục profile. Đổi nó là làm đứt mọi dấu vết cũ. `ten` chỉ
                # để user nhận ra tài khoản nào là tài khoản nào.
                t = (q.get("v", [""])[0] or "").strip()[:40]
                with ACC_LOCK:
                    if t:
                        acc["ten"] = t
                    else:
                        acc.pop("ten", None)     # xoá trắng = trả về tên mặc định
                _save_accounts()
                _LOG.info("Tài khoản %s: đặt tên '%s'.", acc["id"], t or "(bỏ tên)")
                self._json({"ok": True, "ten": t}); return
            if op == "tabs":
                n = max(1, min(MAX_TABS, int(q.get("n", ["1"])[0] or 1)))
                with ACC_LOCK:
                    acc["tabs"] = n
                _save_accounts()
                _LOG.info("Tài khoản %s: đặt %d tab chạy đồng thời.", acc["id"], n)
                self._json({"ok": True, "tabs": n}); return
            if op == "toggle":
                with ACC_LOCK:
                    acc["enabled"] = not acc["enabled"]
                    now = acc["enabled"]
                # User tự bấm → xoá cờ "board tự tắt": từ giờ đây là ý user,
                # board không được coi nó là chỗ trống để bật lại tuỳ ý.
                with ACC_LOCK:
                    acc.pop("auto_off", None)
                _save_accounts()
                if now:
                    # Bật = mở lại Chrome (nếu chưa mở) + xóa dấu chết để chạy lại từ đầu
                    with _DEAD_LOCK:
                        DEAD.pop(_ep(acc), None)
                        DEAD_DEN.pop(_ep(acc), None)
                    if not _endpoint_alive(_ep(acc)):
                        _launch_chrome(acc)
                else:
                    # Tắt = đóng luôn cửa sổ Chrome; thợ tự nghỉ ở vòng lặp kế tiếp.
                    # Việc đã giao đích danh cho thợ này thì báo lỗi rõ ràng thay
                    # vì để mục rữa chờ một thợ không bao giờ quay lại.
                    with _CR_LOCK:
                        _mo_coi = CHO_RIENG.pop(acc["port"], [])
                    for _id in _mo_coi:
                        _dat_job(_id, {"state": "error",
                                       "msg": f"tài khoản giữ chat ({acc['id']}) vừa bị tắt "
                                              f"— bật lại nó rồi chạy lại"})
                    _kill_chrome(acc["port"])
                self._json({"ok": True, "enabled": now})
            elif op == "launch":
                ok = _launch_chrome(acc)
                self._json({"ok": ok, "err": "" if ok else "không tìm thấy Google Chrome"})
            elif op == "revive":
                with _DEAD_LOCK:
                    DEAD.pop(_ep(acc), None)
                    DEAD_DEN.pop(_ep(acc), None)
                # Board đóng cửa sổ Chrome mỗi khi xoay khỏi một tài khoản, nên
                # gỡ dấu chết thôi là chưa đủ — thợ mới sẽ chết ngay ở bước nối
                # CDP và tài khoản lại vào diện chết, vòng vo mà user không hiểu.
                if acc["enabled"] and not _endpoint_alive(_ep(acc)):
                    _launch_chrome(acc)
                    _LOG.info("Thử lại %s — mở lại cửa sổ Chrome.", acc["id"])
                self._json({"ok": True})
            elif op == "del":
                # Xóa hẳn tài khoản: đóng Chrome, bỏ khỏi danh sách, XÓA LUÔN
                # thư mục profile (mất phiên đăng nhập, không hoàn tác được).
                _kill_chrome(acc["port"])
                time.sleep(1.5)          # đợi Chrome nhả file trước khi xóa thư mục
                with _DEAD_LOCK:
                    DEAD.pop(_ep(acc), None)
                    DEAD_DEN.pop(_ep(acc), None)
                with ACC_LOCK:
                    ACCOUNTS[:] = [a for a in ACCOUNTS if a["port"] != port]
                _save_accounts()
                freed, err = _wipe_profile(acc["profile"])
                _LOG.info("Đã xóa tài khoản %s (:%s) · profile %s: %s",
                          acc["id"], acc["port"], acc["profile"], err or f"đã xóa {freed}")
                self._json({"ok": True, "deleted": acc["id"], "freed": freed, "err": err})
            else:
                self._json({"ok": False, "err": "op không hợp lệ"}, 400)
        # ---------- video ----------
        elif u.path == "/api/genvideo":
            _khoa = _request_idempotency_key(self, q, raw)
            if (_job_is_active(sf_id) and not _da_nhan_key(_khoa)):
                self._json({"ok": False, "err": "việc này đã ở trong hàng đợi"}); return
            # KIỂM TRƯỚC KHI XẾP, không để thợ phát hiện hộ. Ba lỗi dữ liệu dưới
            # đây đổi tài khoản không chữa được, mà thợ thì cứ xoay và thử lại —
            # trước khi có trần VID_MAX_TRY thì là thử lại vô hạn. Hai đường kia
            # (/api/video-lo và auto) đã lọc sẵn; riêng nút "Tạo lại" trên từng
            # dòng thì không, nên nó là lối duy nhất đẩy được rác vào hàng.
            _sh = BOARD.get_shot(sf_id)[0]
            if _sh is None:
                self._json({"ok": False, "err": f"không có dòng {sf_id}"}, 404); return
            if not (_sh.get("prompt") or "").strip():
                self._json({"ok": False, "err": "dòng này chưa có prompt video"}, 400); return
            if not BOARD.find_file(_sh.get("sf") or ""):
                self._json({"ok": False,
                            "err": f"start frame {_sh.get('sf') or '(chưa gán)'} chưa có ảnh"},
                           400); return
            bo_co_huy(sf_id)          # user vừa bấm tạo → thắng cờ huỷ cũ

            def _plan(ket_qua, _shot=sf_id):
                from jobs.compat import LegacyAction, LegacyPlan
                return LegacyPlan((
                    LegacyAction(
                        action_id=f"genvideo:{_shot}",
                        legacy_keys=(_shot,),
                        job_ids=_job_ids_cua(ket_qua, (0,)),
                        queue_kind="vid",
                        queue_ident=_shot,
                        manual=False,
                        state=_nhan_cho_video(0),
                    ),
                ))

            xong, meta = self._giao_viec(
                _yeu_cau_video(sf_id, "http.genvideo"), _khoa, _plan, kind="vid")
            if not xong:
                return
            self._json({"ok": True, **meta})
        elif u.path == "/api/video-lo":
            # XẾP HÀNG LOẠT VIDEO — một scene (`scene=S7`) hoặc cả phim (không
            # truyền gì). Mỗi video là MỘT việc riêng: Grok chỉ nhận một ảnh và
            # một prompt mỗi lượt, không gom lô như ảnh SF được.
            _sid = (q.get("scene", [""])[0] or "").strip()
            # `lai=1` — CHẾ ĐỘ TẠO LẠI: nhận cả shot ĐÃ CÓ video. Không có cờ này
            # thì phim dựng xong không còn lối làm lại hàng loạt, chỉ còn bấm
            # từng dòng một. Video mới đè lên bản đang dùng, bản cũ vẫn nằm trong
            # videos/versions/.
            _lai = (q.get("lai", [""])[0] or "") in ("1", "true", "yes")
            _khoa = _request_idempotency_key(self, q, raw)
            _lai_key = _da_nhan_key(_khoa)      # bấm lại đúng cùng một ý định
            _d = BOARD.read()
            # TÊN BIẾN KHÔNG ĐƯỢC TRÙNG HÀM `_xep()` Ở TẦNG MODULE. Gán ở đây là
            # Python coi `_xep` LÀ BIẾN CỤC BỘ CỦA CẢ `do_POST`, nên mọi nhánh
            # khác trong cùng hàm gọi `_xep(...)` đều nổ UnboundLocalError —
            # /api/tao-lo, /api/generate, /api/master chết câm suốt từ lúc thêm
            # nhánh này (2026-08-13), lỗi chỉ hiện trong log server.
            _ds, _bo = [], {"co_video": 0, "thieu_sf": 0, "thieu_prompt": 0, "dang_chay": 0}
            for sc in _d.get("scenes", []):
                if _sid and sc["id"] != _sid:
                    continue
                for sh in sc.get("shots", []):
                    if sh.get("video") and not _lai:
                        _bo["co_video"] += 1; continue
                    if not (sh.get("prompt") or "").strip():
                        _bo["thieu_prompt"] += 1; continue
                    # SF của shot có thể nằm ở scene khác (thẻ dùng lại), nên
                    # tra cả board chứ không chỉ trong scene này.
                    if not BOARD.find_file(sh.get("sf") or ""):
                        _bo["thieu_sf"] += 1; continue
                    if _job_is_active(sh["id"]) and not _lai_key:
                        _bo["dang_chay"] += 1; continue
                    _ds.append(sh["id"])
            meta = _producer_metadata(None)
            if _ds:
                from jobs.models import BatchMode
                from jobs.producer import CreateBatchRequest
                yeu_cau = CreateBatchRequest(
                    tuple(_yeu_cau_video(i, "http.video-lo") for i in _ds),
                    BatchMode.BULK_VIDEO,
                )

                def _plan(ket_qua, _shots=tuple(_ds)):
                    from jobs.compat import LegacyAction, LegacyPlan
                    return LegacyPlan(tuple(
                        LegacyAction(
                            action_id=f"video-lo:{shot}",
                            legacy_keys=(shot,),
                            job_ids=_job_ids_cua(ket_qua, (k,)),
                            queue_kind="vid",
                            queue_ident=shot,
                            manual=False,
                            state=_nhan_cho_video(k),
                        )
                        for k, shot in enumerate(_shots)
                    ))

                xong, meta = self._giao_viec(yeu_cau, _khoa, _plan, kind="vid")
                if not xong:
                    return
            _LOG.info("xếp %d video%s%s — bỏ qua: %d đã có video · %d thiếu ảnh SF · "
                      "%d thiếu prompt · %d đang chạy", len(_ds),
                      f" của {_sid}" if _sid else " (cả phim)",
                      " [TẠO LẠI]" if _lai else "", _bo["co_video"],
                      _bo["thieu_sf"], _bo["thieu_prompt"], _bo["dang_chay"])
            self._json({"ok": True, "so": len(_ds), "bo": _bo, **meta})
        elif u.path == "/api/upload-video":
            if not re.match(r"^[A-Za-z0-9_\-]+$", sf_id):
                self._json({"ok": False, "err": "id không hợp lệ"}, 400); return
            vp = BOARD.next_vversion(sf_id)
            with open(vp, "wb") as f:
                f.write(raw)
            _runtime_note_user_mutation(sf_id)
            BOARD.set_video(sf_id, vp)
            self._json({"ok": True})
        elif u.path == "/api/pick-vversion":
            f = q.get("file", [""])[0]
            src = os.path.join(BOARD.vversions, os.path.basename(f))
            if os.path.isfile(src):
                _runtime_note_user_mutation(sf_id)
                BOARD.set_video(sf_id, src)
                _mark_picked(sf_id, "vpicked", os.path.basename(src))
                self._json({"ok": True})
            else:
                self._json({"ok": False, "err": "không thấy bản này"}, 404)
        elif u.path == "/api/delete-video":
            _runtime_note_user_mutation(sf_id)
            BOARD.delete_video(sf_id)
            self._json({"ok": True})
        elif u.path == "/api/frame-to-sf":
            try:
                shot_id = q.get("shot", [""])[0]
                new_sf = q.get("sf", [""])[0].strip()
                t = float(q.get("t", ["0"])[0])
                if not re.match(r"^[A-Za-z0-9_\-]+$", new_sf or ""):
                    self._json({"ok": False, "err": "Mã SF không hợp lệ"}, 400); return
                src = BOARD.video_file(shot_id)
                if not src:
                    self._json({"ok": False, "err": "Shot này chưa có video"}, 400); return

                out = BOARD.next_version_path(new_sf)
                import subprocess
                r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}",
                                    "-i", src, "-frames:v", "1", out],
                                   capture_output=True, text=True, timeout=60)
                if r.returncode != 0 or not os.path.exists(out):
                    self._json({"ok": False, "err": "ffmpeg lỗi: " + (r.stderr or "")[:200]}, 500); return
                _runtime_note_user_mutation(new_sf)
                BOARD.set_current(new_sf, out)

                # thêm thẻ SF vào bảng nếu chưa có
                data = BOARD.read()
                exists = any(f["id"] == new_sf for sc in data["scenes"] for f in sc["sfs"])
                if not exists:
                    target = None
                    for sc in data["scenes"]:
                        if any(sh["id"] == shot_id for sh in sc.get("shots", [])):
                            target = sc; break
                    if target is None:
                        target = data["scenes"][-1]
                    target["sfs"].append({
                        "id": new_sf,
                        "label": f"(cắt từ {shot_id} @ {t:.1f}s)",
                        "desc": "Frame lấy lại từ video đã tạo — dùng làm start frame cho shot khác.",
                        "prompt": f"[Ảnh này được CẮT TỪ VIDEO {shot_id} tại giây {t:.1f}, không sinh từ prompt.]\n"
                                  f"Nếu cần tạo lại bằng AI, hãy viết prompt mô tả khung hình này.",
                        "status": "proposed", "notes": "", "usedBy": [],
                        "refs": {"chars": [], "bg": None},
                    })
                    BOARD.write(data)
                self._json({"ok": True, "sf": new_sf})
            except Exception as e:
                self._json({"ok": False, "err": str(e)[:300]}, 500)
        elif u.path == "/api/export-capcut":
            try:
                import capcut
                data = BOARD.read()
                only_ok = q.get("approved", ["1"])[0] == "1"
                paths, skipped = [], []
                for sc in data["scenes"]:
                    for sh in sc.get("shots", []):
                        p = BOARD.video_file(sh["id"])
                        if not p:
                            skipped.append(sh["id"]); continue
                        if only_ok and sh.get("vstatus") not in ("approved", None, "", "todo"):
                            skipped.append(sh["id"]); continue
                        if only_ok and sh.get("vstatus") == "rejected":
                            skipped.append(sh["id"]); continue
                        paths.append(p)
                if not paths:
                    self._json({"ok": False, "err": "Chưa có video nào để xuất"}); return
                name = (data.get("film") or "PHIM").split("—")[0].strip().replace(" ", "-")[:40]
                d = capcut.export_draft(paths, name)
                self._json({"ok": True, "path": d, "count": len(paths), "skipped": skipped})
            except Exception as e:
                self._json({"ok": False, "err": str(e)[:400]})
        else:
            self._json({"ok": False}, 404)


def _legacy_execution_enabled() -> bool:
    """Mode core-only không được tự khởi động bất kỳ authority legacy nào."""
    return _JOB_MODE != "authoritative"


def _live_executor_enabled() -> bool:
    configured = os.environ.get("GROKPIPE_LIVE_EXECUTOR")
    if configured is None:
        configured = "1"
    return (
        _JOB_MODE == "authoritative"
        and configured.strip().lower() in {"1", "true", "yes", "on"}
    )


def _live_diagnostics() -> dict:
    enabled = _live_executor_enabled()
    payload = {"enabled": enabled, "workers": 0, "grok": None}
    if not enabled:
        return payload
    with _LIVE_WORKERS_LOCK:
        payload["workers"] = sum(
            thread.is_alive() for thread in _LIVE_WORKERS.values())
    try:
        snapshot = _live_grok_budget().snapshot()
        payload["grok"] = {
            "scope": snapshot.scope,
            "limit": snapshot.limit,
            "reserved": snapshot.reserved,
            "remaining": snapshot.remaining,
        }
    except Exception as exc:                       # noqa: BLE001
        payload["grok"] = {"error": str(exc)[:180]}
    return payload


def _browser_execution_enabled() -> bool:
    return _legacy_execution_enabled() or _live_executor_enabled()


def _background_targets():
    targets = [_luu_ban_runner]
    if _legacy_execution_enabled():
        targets[0:0] = [_supervisor, _gac_hang_doi, _auto_runner]
    elif _live_executor_enabled():
        targets[0:0] = [_live_authoritative_supervisor, _auto_runner]
    return tuple(targets)


def _serve_board_http(port):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main():
    global BOARD, CDP_ENDPOINTS, GROK_ENDPOINTS, PROJECTS_ROOT, SERVE_PORT
    args = [a for a in sys.argv[1:]]
    if not args:
        print('Cách dùng: python3 sfboard.py "/duong/dan/THU-MUC-PHIM" '
              '[--cdp URL[,URL2,...]] [--cdp-grok URL[,URL2,...]] [--port N]')
        print('  --cdp      tài khoản ChatGPT để TẠO ẢNH (nhiều URL cách nhau bằng dấu phẩy)')
        print('  --cdp-grok tài khoản Grok để TẠO VIDEO; bỏ trống thì dùng chung --cdp')
        sys.exit(2)
    film = args[0]
    port = PORT
    if "--cdp" in args:
        raw = args[args.index("--cdp") + 1]
        eps = [u.strip() for u in raw.split(",") if u.strip()]
        if eps:
            CDP_ENDPOINTS = eps
    if "--cdp-grok" in args:
        raw = args[args.index("--cdp-grok") + 1]
        GROK_ENDPOINTS = [u.strip() for u in raw.split(",") if u.strip()]
    if "--port" in args:
        port = int(args[args.index("--port") + 1])
    if "--root" in args:
        PROJECTS_ROOT = os.path.abspath(args[args.index("--root") + 1])
    BOARD = Board(film)
    # hangdoi.py không biết Board là gì — nó chỉ cần đọc được shots[] để xếp
    # đúng thứ tự, và một mốc đổi để biết cache còn dùng được.
    hangdoi.gan_nguon_board(
        BOARD.read, lambda: os.path.getmtime(BOARD.path))
    _init_job_shadow()
    if not PROJECTS_ROOT:
        PROJECTS_ROOT = os.path.dirname(BOARD.dir)
    if "--port" not in args:
        port = _free_port(port)          # cổng bận thì tự nhảy sang cổng trống
    SERVE_PORT = port
    _reg_register(os.path.basename(BOARD.dir), port)
    atexit.register(_reg_unregister, os.path.basename(BOARD.dir))
    # Sổ lỗi runtime nằm ở REPO chứ không nằm trong thư mục phim: thư mục phim
    # là dữ liệu riêng, còn sổ lỗi là chuyện của công cụ.
    start_runtime_bug_service(REPO_ROOT, attach_logging=True)
    atexit.register(stop_runtime_bug_service)
    url = f"http://localhost:{port}"
    print(f"SF Board v2  →  {url}")
    print(f"Phim    : {BOARD.dir}")
    print(f"Dữ liệu : {BOARD.path}")
    _init_accounts()
    _sync_runtime_accounts()
    _dem_nap()
    print(f"Tài khoản: {ACC_PATH}  (quản lý bật/tắt/mở Chrome ngay trên board — nút ⚙ Tài khoản)")
    print(f"Đếm ngày : {DEM_PATH}  (số bản mỗi tài khoản làm được trong ngày — đọc cột 'cao nhất')")
    # Tài khoản đang BẬT mà chưa có cửa sổ Chrome → mở sẵn ngay lúc khởi động.
    # Chỉ làm một lần ở đây, không làm trong supervisor: nếu bạn cố ý đóng một
    # cửa sổ giữa chừng thì nó phải nằm im, không bị mở lại liên tục.
    opened = 0
    if _browser_execution_enabled():
        for a in ACCOUNTS:
            if a.get("enabled") and not _endpoint_alive(_ep(a)):
                if _launch_chrome(a):
                    opened += 1
        if opened:
            print(f"  → đang mở {opened} cửa sổ Chrome cho các tài khoản đang bật…")
            time.sleep(3 + opened)
    elif _JOB_MODE == "authoritative":
        print("  → authoritative core-only: không tự mở Chrome/provider")
    for a in ACCOUNTS:
        live = "sống" if _endpoint_alive(_ep(a)) else "chưa mở Chrome"
        onoff = "BẬT" if a.get("enabled") else "tắt"
        print(f"  · {a['id']:8s} {_KIND_NAME[a['kind']]:16s} port {a['port']}  [{onoff}, {live}]")
    # Supervisor tự mở/đóng luồng thợ theo trạng thái bật/tắt của từng tài khoản.
    for target in _background_targets():
        threading.Thread(target=target, daemon=True).start()
    atexit.register(_shutdown_job_lifecycle)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    _serve_board_http(port)


if __name__ == "__main__":
    main()
