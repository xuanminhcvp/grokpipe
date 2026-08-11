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
        d = dict(self.turn_log())
        d[ten_file] = info
        # Cắt bớt dòng của file đã biến mất, để sổ không phình mãi.
        if len(d) > 4000:
            con = set(os.listdir(self.versions))
            d = {k: v for k, v in d.items() if k in con}
        tmp = self.nk_path + ".tmp"
        try:
            os.makedirs(self.pl, exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=1, sort_keys=True)
            os.replace(tmp, self.nk_path)
            self._nk = {"mtime": os.path.getmtime(self.nk_path), "data": d}
        except OSError as e:
            _LOG.warning("không ghi được sổ lượt: %s", e)

    def read(self) -> dict:
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["mtime"] = int(os.path.getmtime(self.path))
        nk = self.turn_log()
        for sc in data.get("scenes", []):
            sc.setdefault("shots", [])
            for sf in sc.get("sfs", []):
                sf["image"] = self._img_url(self.assets, sf["id"])
                sf["versions"] = self._versions(sf["id"], nk)
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
                sh["video"] = self._vid_url(sh["id"])
                sh["vversions"] = self._vversions(sh["id"])
        return data

    # ---- video
    def _vid_url(self, sid: str) -> str | None:
        for name in sorted(os.listdir(self.videos)):
            s, ext = os.path.splitext(name)
            if s == sid and ext.lower() == ".mp4":
                p = os.path.join(self.videos, name)
                return f"/videos/{name}?t={int(os.path.getmtime(p))}"
        return None

    def video_file(self, sid: str) -> str | None:
        p = os.path.join(self.videos, sid + ".mp4")
        return p if os.path.isfile(p) else None

    def _vversions(self, sid: str) -> list[dict]:
        out = []
        for name in sorted(os.listdir(self.vversions)):
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
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    # ---- ảnh
    def _img_url(self, folder: str, stem: str) -> str | None:
        for name in sorted(os.listdir(folder)):
            s, ext = os.path.splitext(name)
            if s == stem and ext.lower() in IMAGE_EXT:
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

    def _versions(self, sf_id: str, nk: dict | None = None) -> list[dict]:
        nk = self.turn_log() if nk is None else nk
        out = []
        for name in sorted(os.listdir(self.versions)):
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

    def get_sf(self, sf_id: str):
        data = self.read()
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
ACC_PATH = os.path.expanduser("~/.grokpipe-accounts.json")
PROJECTS_ROOT = ""       # thư mục chứa các *.project (bộ chọn dự án)
SERVE_PORT = 0           # cổng board này đang phục vụ
ACC_LOCK = threading.RLock()
WORKERS: dict[tuple, threading.Thread] = {}   # (port, kind) -> luồng thợ

_CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
_KIND_URL = {"img": "https://chatgpt.com/", "vid": "https://grok.com/"}
_KIND_NAME = {"img": "ChatGPT (ảnh)", "vid": "Grok (video)"}


def _ep(a: dict) -> str:
    return f"http://localhost:{a['port']}"


def _save_accounts():
    with ACC_LOCK:
        with open(ACC_PATH, "w", encoding="utf-8") as f:
            json.dump({"accounts": ACCOUNTS}, f, ensure_ascii=False, indent=2)


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
    global ACCOUNTS
    if os.path.exists(ACC_PATH):
        try:
            ACCOUNTS = json.load(open(ACC_PATH, encoding="utf-8"))["accounts"]
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
            # profile đó CŨNG đã đăng nhập grok.com — nên phải kêu to, đừng lặng
            # lẽ đẩy việc video sang Chrome ChatGPT rồi để user tự đoán.
            pool = [_ep(a) for a in ACCOUNTS if a["kind"] == "img" and a["enabled"]]
            if pool:
                _LOG.warning(
                    "KHÔNG có tài khoản Grok nào đang BẬT — việc tạo video sẽ chạy nhờ trong "
                    "cửa sổ Chrome ChatGPT (%s). Muốn dùng đúng Chrome Grok thì vào mục Tài "
                    "khoản trên board và BẬT tài khoản grok.", ", ".join(pool))
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
]


def _launch_chrome(a: dict) -> bool:
    """Mở cửa sổ Chrome cho tài khoản này (kèm tab đệm about:blank)."""
    import subprocess
    if not os.path.exists(_CHROME_BIN):
        return False
    profile = os.path.abspath(os.path.expanduser(a["profile"]))
    os.makedirs(profile, exist_ok=True)
    subprocess.Popen([_CHROME_BIN, f"--remote-debugging-port={a['port']}",
                      f"--user-data-dir={profile}", *_LOW_RAM_FLAGS,
                      "about:blank", _KIND_URL[a["kind"]]],
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


def _kill_chrome(port: int):
    """Đóng cửa sổ Chrome của tài khoản này.

    Mỗi tài khoản là một tiến trình Chrome riêng (user-data-dir riêng), nhận diện
    được qua cờ --remote-debugging-port nên không đụng vào Chrome cá nhân của user.
    Phiên đăng nhập nằm trong profile trên đĩa, đóng cửa sổ không mất."""
    import subprocess
    subprocess.run(["pkill", "-f", f"remote-debugging-port={port}"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    CHROME_GEN["n"] += 1


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


# ---- NGHỈ TỚI GIỜ (hết lượt có hạn) -------------------------------------
# ChatGPT chặn ĐÍNH TỆP theo giờ và nói thẳng giờ mở lại ("…until 3:45 PM").
# image_chatgpt.py nhét giờ đó vào chuỗi lỗi dưới dạng nhãn máy đọc
# `[NGHI-DEN:HH:MM]` (hoặc `[NGHI-DEN:+<phút>]` khi không đọc được giờ).
# Ở đây đổi nhãn thành mốc thời gian: tài khoản nghỉ tới đúng mốc rồi TỰ chạy
# lại, không bắt user nhớ bấm 'Thử lại'.
_RE_NGHI = re.compile(r"\[NGHI-DEN:(?:(\d{1,2}):(\d{2})|\+(\d+))\]")
NGHI_BU = 60          # nghỉ thêm 60s sau giờ ChatGPT ghi, cho chắc


def _moc_nghi(e: Exception) -> float:
    """Mốc epoch được phép chạy lại; 0 = lỗi này không kèm hẹn giờ."""
    m = _RE_NGHI.search(str(e))
    if not m:
        return 0.0
    now = time.time()
    if m.group(3):
        return now + int(m.group(3)) * 60
    gio, phut = int(m.group(1)), int(m.group(2))
    t = time.localtime(now)
    moc = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, gio, phut, 0, 0, 0, -1))
    if moc < now - 60:          # giờ đã trôi qua → mốc của ngày mai
        moc += 86400
    return moc + NGHI_BU


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


def _endpoint_alive(url: str) -> bool:
    """Cửa sổ Chrome debug ở endpoint này còn mở không."""
    import urllib.request
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/json/version", timeout=3):
            return True
    except Exception:
        return False


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
    _TL.ctx = None
    _TL.sess = None
    _TL.gsess = None

# ---------------------------------------------------------------- generation
JOBS: dict[str, dict] = {}          # id -> {"state": running|done|error, "msg": str}
# Hai hàng đợi tách biệt: ảnh chạy trên tài khoản ChatGPT, video trên tài khoản Grok.
# TRẦN ẢNH TRONG MỘT TIN NHẮN — GIỮ Ở 6, đã thử 8 rồi bỏ (2026-08-07).
# Cơ chế "tải về trước, phân loại sau" đã gỡ được cái giá cũ của lô to (lệch một
# ảnh là mất NGUYÊN lô), nhưng còn một cái giá nó không gỡ được: lô càng to, một
# lượt lỗi càng kéo theo nhiều SF phải soi và gắn tay. Sáu ảnh chỉnh nhanh hơn
# tám. Đừng nâng lại chỉ vì "giờ an toàn rồi".
TOI_DA_ANH_MOT_LO = 6

# ---- ƯU TIÊN THEO SF ID -------------------------------------------------
# Hàng đợi FIFO thuần thì thứ tự chạy phụ thuộc thời điểm xếp vào — hai lô cùng
# một địa điểm ra ở hai vòng auto khác nhau sẽ chạy theo giờ vào, không theo id.
# Đã thấy: S2-08..13 xếp SAU S2-14..17 nên chạy sau, dù id nhỏ hơn.
# Đổi sang PriorityQueue, khoá ưu tiên = SF id NHỎ NHẤT trong ident:
#   · SF-M-…  và REF_…  → 0 (làm trước hết, vì SF con lấy master làm bối cảnh)
#   · SF-S<a>-<b> / V-S<a>-<b> → a*1000 + b (S1 trước S2; trong scene, id nhỏ trước)
#   · còn lại → 999999 (rơi xuống đáy)
# Tiebreaker là seq đơn điệu → cùng ưu tiên thì giữ FIFO, và hai item ngang ưu
# tiên không phải so tuple con (tránh phụ thuộc thứ tự trường bên trong).
_HANG_SEQ = itertools.count()


def _uu_tien(ident: str) -> int:
    """SF id số nhỏ nhất trong ident. Nhỏ hơn = làm trước."""
    ids = ident[3:].split(",") if ident.startswith("LO:") else [ident]

    def _n(sf: str) -> int:
        sf = sf.strip()
        if sf.startswith("SF-M-") or sf.startswith("REF_"):
            return 0
        m = re.match(r"(?:SF|V)-S(\d+)-(\d+)", sf)
        if m:
            return int(m.group(1)) * 1000 + int(m.group(2))
        return 999999
    return min((_n(x) for x in ids), default=999999)


def _xep(Q, item: tuple) -> None:
    """Xếp một việc vào PriorityQueue theo ưu tiên."""
    Q.put((_uu_tien(item[1]), next(_HANG_SEQ), item))


def _lay(Q, **kw):
    """Nhấc item ra khỏi PriorityQueue, gỡ bỏ khoá ưu tiên."""
    return Q.get(**kw)[2]


IMG_QUEUE: "queue.PriorityQueue" = queue.PriorityQueue()
VID_QUEUE: "queue.PriorityQueue" = queue.PriorityQueue()
BOARD_LOCK = threading.RLock()      # nhiều thợ cùng ghi sf-board.json
_LOG = logging.getLogger("sfboard")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")

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
            DEAD_DEN[endpoint] = den
        else:
            DEAD_DEN.pop(endpoint, None)
        alive = [e for e in pool if e not in DEAD]
    _LOG.warning("%s ở %s — còn %d/%d tài khoản %s chạy được",
                 reason, endpoint, len(alive), len(pool),
                 "Grok" if kind == "vid" else "ChatGPT")


def _dang_nghi(endpoint: str) -> float:
    """Mốc epoch tài khoản này được chạy lại; 0 = không phải đang nghỉ có hẹn."""
    with _DEAD_LOCK:
        return DEAD_DEN.get(endpoint, 0.0) if DEAD.get(endpoint) else 0.0


def _mo_chrome_du_phong(kind: str, tru: str = "") -> int:
    """Bật Chrome cho các tài khoản CÙNG LOẠI đang bật mà cửa sổ chưa mở.

    Gọi khi một tài khoản vừa bị chặn: việc đã được chuyển sang tài khoản khác,
    nhưng tài khoản khác chỉ nhận được việc nếu cửa sổ Chrome của nó đang chạy.
    Chỉ mở tài khoản user ĐÃ BẬT — không tự thêm tài khoản mới, không đụng tới
    trần RAM mà user tự đặt bằng danh sách tài khoản."""
    with ACC_LOCK:
        accs = [dict(a) for a in ACCOUNTS if a["enabled"] and a["kind"] == kind]
    n = 0
    for a in accs:
        ep = _ep(a)
        if ep == tru or DEAD.get(ep) or _endpoint_alive(ep):
            continue
        if _launch_chrome(a):
            n += 1
            _LOG.info("mở Chrome cho tài khoản %s (:%s) để chạy tiếp.", a["id"], a["port"])
    return n


def _alive_count(kind: str = "img") -> int:
    with _DEAD_LOCK:
        return len([e for e in _pool(kind) if e not in DEAD])


def _acct_label() -> str:
    """Nhãn '[tk 2/6]' của luồng thợ đang chạy, để hiện lên board."""
    ep = getattr(_TL, "endpoint", None)
    pool = _pool(getattr(_TL, "kind", "img"))
    if ep is None or ep not in pool or len(pool) < 2:
        return ""
    return f" [tk {pool.index(ep) + 1}/{len(pool)}]"


def _worker(endpoint: str, kind: str, slot: int = 0):
    """Một luồng thợ gắn cứng với MỘT tài khoản.

    kind='img' → lấy việc từ IMG_QUEUE, chạy trên tài khoản ChatGPT.
    kind='vid' → lấy việc từ VID_QUEUE, chạy trên tài khoản Grok.
    Tự nghỉ khi tài khoản bị tắt trên giao diện hoặc bị đánh dấu chết;
    supervisor sẽ mở thợ mới khi tài khoản được bật/hồi sinh."""
    _TL.endpoint = endpoint
    _TL.kind = kind
    _TL.slot = slot          # chỗ ngồi: quyết định thợ này lái TAB NÀO
    QUEUE = IMG_QUEUE if kind == "img" else VID_QUEUE
    while True:
        if endpoint not in _pool(kind) or DEAD.get(endpoint):
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
        # Chrome đã bị đóng/mở lại từ lần chạy trước (ngủ khi rảnh, user tắt-bật,
        # supervisor hồi sinh)? Nhả sạch Playwright của luồng này rồi nối lại từ
        # đầu — nếu không, mọi job sẽ chết ở bước mở tab.
        if getattr(_TL, "gen", None) != CHROME_GEN["n"]:
            _release_tl()
            _TL.gen = CHROME_GEN["n"]
        stop = False
        try:
            if kind == "img":
                # ident "LO:sf1,sf2,…" = một LÔ ảnh cùng địa điểm, gửi trong MỘT
                # lượt của MỘT đoạn chat. Đường lô nằm cạnh đường một-ảnh, không
                # thay thế nó: sửa lẻ vẫn phải dùng đường một-ảnh.
                if _bi_huy(ident):
                    _dat_job(ident, {"state": "error", "msg": "đã huỷ"})
                elif ident.startswith("LO:"):
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
                    _generate(ident, manual=manual)
            else:
                _gen_video(ident)
        except Exception as e:
            fatal = _is_quota_error(e) or (
                _is_dead_session_error(e) and not _endpoint_alive(endpoint))
            if fatal:
                reason = "hết lượt" if _is_quota_error(e) else "cửa sổ Chrome đã đóng"
                # Chặn CÓ HẸN GIỜ (hết lượt đính tệp): cho tài khoản nghỉ tới
                # đúng giờ mở lại rồi tự sống lại, đồng thời bảo đảm còn Chrome
                # khác đang mở để chạy tiếp phần việc còn lại.
                den = _moc_nghi(e)
                if den:
                    reason = ("hết lượt đính tệp — nghỉ tới "
                              + time.strftime("%H:%M", time.localtime(den)))
                _mark_dead(endpoint, reason, kind, den)
                _release_tl()
                if den:
                    _mo_chrome_du_phong(kind, tru=endpoint)
                stop = True
                if tries < len(_pool(kind)) and _alive_count(kind) > 0:
                    _dat_job(ident, {"state": "running",
                                     "msg": f"{reason} → chuyển sang tài khoản khác…"})
                    _xep(QUEUE, (kind, ident, tries + 1, manual))
                else:
                    _dat_job(ident, {"state": "error",
                                     "msg": f"{reason}; không còn tài khoản nào khả dụng"})
            else:
                _dat_job(ident, {"state": "error", "msg": str(e)[:300]})
        finally:
            if tu_hang:                 # việc lấy từ CHO_RIENG không qua queue
                QUEUE.task_done()
        if stop:
            _LOG.warning("Thợ %s (%s) dừng.", endpoint, kind)
            return


_HOAN: dict[str, int] = {}        # lô bị hoãn (chờ khoá địa điểm) -> số lần
_MASTER_LOCKS: dict[str, threading.Lock] = {}   # mỗi địa điểm một khoá lô
_ML_LOCK = threading.Lock()
CHO_RIENG: dict[int, list[str]] = {}   # port -> idents GIAO ĐÍCH DANH cho thợ đó
_CR_LOCK = threading.Lock()
DA_HUY: set[str] = set()          # ident user đã huỷ, thợ phải bỏ qua
HUY_LOCK = threading.Lock()

# Số THẾ HỆ, tăng mỗi lần user bấm "Dừng tất cả".
#
# Vì sao cần, dù đã có DA_HUY: DA_HUY chỉ được soi lúc thợ NHẤC việc ra khỏi hàng,
# và nó là chốt dùng một lần (soi xong là xoá). Thợ đang nằm giữa chừng trong
# generate_lo thì không cắt được; khi nó chạy xong và thấy lô thiếu ảnh, đường thử
# lại TỰ ĐẨY lô vào hàng đợi — bước đó không kiểm cờ huỷ nào cả. Kết quả: bấm dừng,
# hàng đợi sạch, nhưng vài phút sau đúng lô đó chạy lại như chưa hề bị dừng.
# Thợ chụp lại số này lúc bắt đầu, và chỉ được tự xếp hàng nếu số chưa đổi.
DUNG_GEN = 0

# SF id user bấm DỪNG RIÊNG (nút ■ trên từng việc trong ngăn kéo hàng đợi).
# Thợ đang chạy soi tập này ở mỗi nhịp poll rồi tự thoát — nhờ vậy dừng được MỘT
# việc mà không phải đóng Chrome, tức không giết oan các việc khác cùng tài khoản.
#
# ĐÁNH CỜ THEO SF ID, KHÔNG THEO IDENT LÔ: _dat_job() rải trạng thái cho từng SF
# thành viên và KHÔNG giữ khoá "LO:a,b,c" trong JOBS, nên tra ident trong JOBS là
# tra vào chỗ trống — bản đầu viết theo ident nên bấm dừng không ăn gì.
DUNG_RIENG: set[str] = set()


def _bi_huy(ident: str) -> bool:
    """Việc này đã bị huỷ chưa? Kiểm NGAY TRƯỚC khi bắt tay làm.

    Chỉ vứt hàng đợi là không đủ: thợ nhấc việc ra khỏi hàng trong vòng 2 giây,
    nên phần lớn cú bấm Huỷ sẽ trượt nếu không có chốt này."""
    with HUY_LOCK:
        if ident in DA_HUY:
            DA_HUY.discard(ident)
            return True
    return False


def _dat_job(ident: str, st: dict) -> None:
    """Ghi trạng thái job. Với ident lô ("LO:a,b,c") thì RẢI cho TỪNG SF thành viên.

    Không rải thì lô lỗi xong các SF vẫn kẹt ở 'running' vĩnh viễn — giao diện
    quay vòng mà chẳng có gì đang chạy."""
    JOBS[ident] = st
    if ident.startswith("LO:"):
        for i in ident[3:].split(","):
            if i:
                JOBS[i] = dict(st)


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
        JOBS[ident] = {"state": "running",
                       "msg": "khởi động…" if n == 0 else f"đang xếp hàng ({n} việc trước)"}
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


def _supervisor():
    """Bảo đảm mỗi tài khoản đang bật luôn có luồng thợ sống.

    - Tài khoản bật mà chưa có thợ (mới bật lại, hoặc thợ đã chết) → mở thợ mới.
    - Tài khoản 'cửa sổ Chrome đã đóng' mà Chrome đã mở lại → tự hồi sinh.
    - Tài khoản 'hết lượt' giữ nguyên đến khi user bấm 'Thử lại' trên giao diện."""
    while True:
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
                # Hết giờ nghỉ (trần đính tệp theo giờ của ChatGPT) → tự sống lại.
                # Chrome có thể đã bị user đóng trong lúc nghỉ nên mở lại luôn,
                # nếu không thợ mới sẽ chết ngay ở bước nối CDP.
                _den = _dang_nghi(ep)
                if _den and time.time() >= _den:
                    with _DEAD_LOCK:
                        DEAD.pop(ep, None)
                        DEAD_DEN.pop(ep, None)
                    _LOG.info("Tài khoản %s đã hết giờ nghỉ — chạy lại.", a["id"])
                    if not _endpoint_alive(ep):
                        _launch_chrome(a)
                if DEAD.get(ep):
                    continue
                kinds = [a["kind"]]
                if a["kind"] == "img" and not has_vid:
                    kinds.append("vid")     # chưa có tài khoản Grok → thợ ảnh kiêm video
                # Một tài khoản có thể chạy NHIỀU TAB song song: mỗi tab một luồng
                # thợ riêng, cùng trỏ vào một cửa sổ Chrome. Số tab do user đặt ở
                # mục Tài khoản trên board (mặc định 1 = như cũ).
                so_tab = max(1, min(MAX_TABS, int(a.get("tabs") or 1)))
                for k in kinds:
                    for slot in range(so_tab):
                        key = (a["port"], k, slot)
                        th = WORKERS.get(key)
                        if th is None or not th.is_alive():
                            t = threading.Thread(target=_worker, args=(ep, k, slot), daemon=True)
                            WORKERS[key] = t
                            t.start()
                    # hạ số tab thì cho các luồng thừa tự nghỉ ở vòng lặp kế tiếp
                    for key in [x for x in list(WORKERS)
                                if x[0] == a["port"] and x[1] == k and len(x) > 2 and x[2] >= so_tab]:
                        WORKERS.pop(key, None)
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
AUTO_MAX_TRY = 40                # số lần bắn lại tối đa cho một ident
AUTO_COOLDOWN = 6                # số vòng phải chờ trước khi bắn lại cùng ident (~2 phút)


def _auto_allow(st: dict, ident: str, cyc: int) -> bool:
    """Còn lượt thử và đã hết thời gian chờ thì cho bắn."""
    if st["try"].get(ident, 0) >= AUTO_MAX_TRY:
        return False
    if cyc - st["last"].get(ident, -999) < AUTO_COOLDOWN:
        return False
    st["try"][ident] = st["try"].get(ident, 0) + 1
    st["last"][ident] = cyc
    return True


def _auto_scene(sc: dict, st: dict, cyc: int) -> tuple[int, int, int, int]:
    """Quét một scene, xếp việc còn thiếu. Trả (ảnh thiếu, ảnh tổng, video thiếu, video tổng)."""
    sfs, shots = sc.get("sfs", []), sc.get("shots", [])

    # 1) ảnh SF còn thiếu — CHẠY THEO LÔ, GOM THEO ĐỊA ĐIỂM.
    #    Đường _enqueue đơn lẻ không có chat_url nên KHÔNG gửi luatchung; prompt
    #    bây giờ đã cắt hết phần bối cảnh nên chạy kiểu đó là ảnh mất bối cảnh.
    #    ẢNH GỐC TRƯỚC: SF con đính master làm refs.bg, master chưa có ảnh thì cả
    #    lô dừng vì "thiếu ref". Nên vòng này chỉ xếp master còn thiếu; SF con bám
    #    nó đợi vòng sau, lúc master đã có ảnh.
    thieu_bg = {(f.get("refs") or {}).get("bg") for f in sfs}
    thieu_bg = sorted(b for b in thieu_bg if b and not BOARD.find_file(b))
    san_sang = [f["id"] for f in sfs
                if not BOARD.find_file(f["id"])
                and not ((f.get("refs") or {}).get("bg") in thieu_bg)]
    miss_img = [f["id"] for f in sfs if not BOARD.find_file(f["id"])]
    xep = [i for i in (thieu_bg + san_sang)
           if JOBS.get(i, {}).get("state") not in ("running", "queued")
           and _auto_allow(st, i, cyc)]
    if xep:
        _data = BOARD.read()
        nhom: dict[str, list[str]] = {}
        for i in xep:
            nhom.setdefault(_nhom_cua(i, _data), []).append(i)
        for m, xs in nhom.items():
            xs.sort(key=_uu_tien)
            for k in range(0, len(xs), TOI_DA_ANH_MOT_LO):
                lo = xs[k:k + TOI_DA_ANH_MOT_LO]
                for i in lo:
                    JOBS[i] = {"state": "queued",
                               "msg": f"chờ lô {len(lo)} ảnh · {_ten_gon(m, _data)}"}
                _xep(IMG_QUEUE, ("img", "LO:" + ",".join(lo), 0, False))
                _LOG.info("[auto %s] xếp lô %d ảnh · %s", sc["id"], len(lo), m)

    # 2) video còn thiếu, nhưng chỉ khi ảnh SF của shot đó đã có
    #    VÀ chỉ khi công tắc auto-video đang bật (mặc định tắt).
    miss_vid = [sh["id"] for sh in shots if not BOARD.video_file(sh["id"])]
    for sh in (shots if _auto_vid_doc() else []):
        if BOARD.video_file(sh["id"]) or not BOARD.find_file(sh.get("sf", "")):
            continue
        if JOBS.get(sh["id"], {}).get("state") == "running":
            continue
        if _auto_allow(st, sh["id"], cyc):
            _enqueue("vid", sh["id"])
            _LOG.info("[auto %s] video %s (lần %d)", sc["id"], sh["id"], st["try"][sh["id"]])

    return len(miss_img), len(sfs), len(miss_vid), len(shots)


def _auto_runner():
    cyc = 0
    while True:
        time.sleep(AUTO_PERIOD)
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
    _TL.ctx = None
    _TL.sess = None
    _TL.gsess = None


def _hub():
    ctx = getattr(_TL, "ctx", None)
    if ctx is not None:
        try:
            ctx.pages  # chạm vào để biết context còn sống
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
        _TL.ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    except Exception as e:
        # Trả luồng về trạng thái sạch rồi mới ném, để lần bấm sau còn báo đúng
        # bệnh chứ không đổ sang lỗi asyncio loop khó hiểu.
        _bo_hub()
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
    s = ChatGPTSession(user_data_dir=os.path.expanduser("~/.grokpipe-chrome"),
                       logger=_LOG, headless=False, cdp_endpoint=None, shared_ctx=_hub())
    if not s.start():
        raise RuntimeError(f"Không nối được ChatGPT ở {_TL.endpoint}. "
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


def _sf_attachments(sf: dict) -> tuple[list[str], list[str], list[str]]:
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
    ids = list(dict.fromkeys(requested))
    attach, missing = [], []
    for rid in ids:
        p = BOARD.find_file(rid)
        (attach.append(p) if p else missing.append(rid))
    return attach, missing, ids


def _gen_video(shot_id: str):
    """Chạy trong một luồng thợ. Lỗi hết lượt / cửa sổ chết được ném lên cho
    worker phân loại và chuyển việc sang tài khoản khác."""
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
                            duong_them=_duong_them)
            if ok and os.path.exists(out):
                _dem_cong()
                break
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
        # BẢN ĐÃ DUYỆT LÀ BẢN CHỐT: user bấm duyệt tức là chốt đúng bản đó để
        # hiển thị và tải về. Bản render sau chỉ nằm trong versions/ để so, tuyệt
        # đối không đè. Muốn thay thì user bỏ duyệt trước.
        cur = BOARD.get_shot(shot_id)[0] or {}
        if cur.get("vstatus") == "approved" and BOARD.video_file(shot_id):
            _LOG.info("%s ĐÃ DUYỆT — giữ nguyên bản chốt, bản mới nằm ở versions/%s",
                      shot_id, os.path.basename(out))
            JOBS[shot_id] = {"state": "done",
                             "msg": "xong — đã duyệt nên giữ bản cũ, bản mới ở dãy bản"}
            return
        BOARD.set_video(shot_id, out)
        _mark_picked(shot_id, "vpicked", os.path.basename(out))
    JOBS[shot_id] = {"state": "done", "msg": "xong"}


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
    
    if not f.get("picked"):
        return f"thẻ địa điểm {master} CHƯA CÓ ẢNH (picked)"
    
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


def _chat_cua_master(master: str) -> dict:
    """{url, port} của đoạn chat gắn với NHÓM này. Rỗng = chưa có chat.

    Nhóm ĐỊA ĐIỂM lưu chat ngay trên THẺ ĐỊA ĐIỂM. Nhóm NHÂN VẬT và ĐẠO CỤ
    không có thẻ nào để bám nên lưu ở gốc file, mục 'chats'."""
    d = BOARD.read()
    if not _khoa_la_the(master):
        return dict((d.get("chats") or {}).get(master) or {})
    for s in d.get("scenes", []):
        for f in s.get("sfs", []):
            if f["id"] == master:
                return dict(f.get("chat") or {})
    return {}


def _luu_chat(master: str, url: str, port: int, refs: set | None = None) -> None:
    """Ghi chat_url vào master.

    PHẢI lưu: mở chatgpt.com là ra chat TRẮNG, không phải chat cũ. Mà ChatGPT có
    bộ nhớ xuyên chat nên chat trắng vẫn trả lời trôi chảy — hỏng kiểu đó hoàn
    toàn im lặng, mỗi ảnh một chat trắng mà nhìn vẫn như đang chạy đúng."""
    if not url or "/c/" not in url:
        return
    ban = {"url": url, "port": port, "refs": sorted(refs or set())}
    with BOARD_LOCK:
        d = BOARD.read()
        if not _khoa_la_the(master):                     # nhóm nhân vật / đạo cụ
            d.setdefault("chats", {})[master] = ban
            BOARD.write(d)
            return
        for s in d.get("scenes", []):
            for f in s.get("sfs", []):
                if f["id"] == master:
                    f["chat"] = ban
                    BOARD.write(d)
                    return


def _lo_id_thap_hon_dang_cho(master: str, sf_ids: list[str], data: dict) -> str:
    """Trả ID nhỏ nhất đang chờ/chạy trước lô hiện tại trong cùng nhóm.

    PriorityQueue không đủ khi nhiều worker đã đồng thời nhấc nhiều lô khỏi hàng;
    trạng thái JOBS là phần còn nhìn thấy được để giữ thứ tự tại cửa lấy khoá.
    """
    cua_minh = set(sf_ids)
    uu_tien_hien_tai = min((_uu_tien(i) for i in sf_ids), default=999999)
    dang_chan: list[str] = []
    for scene in data.get("scenes", []):
        for sf in scene.get("sfs", []):
            sf_id = sf.get("id") or ""
            if not sf_id or sf_id in cua_minh or _uu_tien(sf_id) >= uu_tien_hien_tai:
                continue
            if JOBS.get(sf_id, {}).get("state") not in ("queued", "running"):
                continue
            if _nhom_cua(sf_id, data) == master:
                dang_chan.append(sf_id)
    return min(dang_chan, key=_uu_tien) if dang_chan else ""


# ======================================================================= CHỜ PHÂN LOẠI
# TẢI VỀ TRƯỚC, PHÂN LOẠI SAU.
#
# Mọi ảnh của một lượt ChatGPT đều được tải xuống `cho-phan-loai/turn-NNNN/`
# theo đúng thứ tự hiển thị (`01.png`, `02.png`, …) TRƯỚC khi board quyết định
# ảnh nào của SF nào. Chỉ khi số ảnh khớp đúng số prompt VÀ lượt không trả kèm
# chữ thì board mới tự ghép — nhưng ghép rồi VẪN GIỮ thư mục lượt, xem
# `PL_GIU_TOI_DA` bên dưới.
#
# Vì sao đổi: bộ dò DOM của ChatGPT hỏng lại sau mỗi lần họ đổi giao diện, và
# bản cũ phản ứng bằng cách VỨT cả lượt ảnh đã vẽ xong rồi gửi lại từ đầu — mất
# lượt tạo ảnh (thứ có trần theo ngày) chỉ vì một phép đếm sai. Tải về trước thì
# giao diện có đổi kiểu gì, ảnh vẫn nằm trên đĩa: hỏng nặng nhất cũng chỉ còn là
# việc gắn tay, không còn là mất ảnh.
#
# Ba luật của khối này:
#   1. KHÔNG BAO GIỜ vứt ảnh đã tải, kể cả lượt trả kèm chữ hay thừa ảnh.
#   2. Lệch tới PL_LECH_TOI_DA ảnh thì coi LƯỢT ĐÃ XONG — không gửi lại, không
#      đốt thêm lượt. User gắn tay trong bảng "Chờ phân loại".
#   3. Số lượt ĐƠN ĐIỆU, không bao giờ dùng lại — nó là thứ user đọc trong log
#      để lần ngược một ảnh về đúng lượt đã sinh ra nó.
#   4. LƯỢT CÒN ẢNH CHƯA GẮN KHÔNG BAO GIỜ BỊ DỌN. Mức giữ chỉ chạm những lượt
#      đã gắn hết — thứ duy nhất chắc chắn còn bản trong `versions/`.
PL_LECH_TOI_DA = 2

# HỘP CHỜ LUÔN TỒN TẠI, KỂ CẢ KHI LƯỢT ĐÃ GHÉP ĐÚNG (đổi 2026-08-07).
# Trước đây ghép đủ số là xoá thư mục lượt ngay, nên lượt "chuẩn" biến mất khỏi
# hộp chờ và muốn dịch một ảnh sang thẻ khác thì chỉ còn cách vẽ lại. Giờ giữ
# lại: ảnh nằm nguyên trên đĩa, thanh chờ hiện đủ với dấu "→ đã gắn <SF>", kéo
# thả sang thẻ khác được bất cứ lúc nào.
#
# Đổi lại là dung lượng: mỗi lượt giữ thêm một bản của chính những ảnh đã có
# trong `versions/`. Nên chặn bằng mức giữ — chỉ dọn lượt ĐÃ GẮN HẾT, cũ nhất
# trước, và ảnh của lượt đó vẫn còn nguyên trong `versions/` nên không mất gì.
# Muốn giữ nhiều/ít hơn thì sửa đúng con số này.
PL_GIU_TOI_DA = 40

PL_LOCK = threading.RLock()

# DÁN MÃ SF VÀO GÓC ẢNH — bật thì ChatGPT in mã (vd `SF-S7-03`) ở góc dưới-trái
# của chính ảnh đó. Đây là cách DUY NHẤT nhận ra ảnh nào của thẻ nào khi một lượt
# trả về lệch số ảnh: lúc ấy thứ tự — thứ duy nhất ta có để ghép — chính là thứ
# vừa hỏng. Mã in trong ảnh là bằng chứng ảnh tự mang theo.
#
# ⚠ Nhãn NẰM TRONG ẢNH nên nó theo start frame vào video. Bật lúc dựng nháp, TẮT
# trước khi render bản cuối. Lưu ở HOME chứ không trong project: đây là thói quen
# làm việc của user, không phải thuộc tính của một bộ phim.
MA_PATH = os.path.expanduser("~/.grokpipe-dan-ma.json")


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


def _pl_dem() -> dict:
    """{số lần gắn còn lùi được} — nút ↩ trên giao diện bật/tắt theo con số này.

    Trước 2026-08-09 hàm còn trả số lượt và số ảnh chưa gắn cho dải phân loại;
    dải đó đã bỏ nên chỉ còn phần hoàn tác (dùng chung cho tráo/chuyển ảnh)."""
    with HT_LOCK:
        ht = len(HOAN_TAC)
        cuoi = dict(HOAN_TAC[-1]) if HOAN_TAC else {}
    return {"ht": ht, "ht_cuoi": f"{cuoi.get('sf','')} · {cuoi.get('luc','')}" if cuoi else ""}


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


# _pl_gan() (gắn TAY ảnh của lượt vào SF) đã bỏ 2026-08-09 cùng dải phân loại.
# Việc ghép TỰ ĐỘNG khi tạo ảnh theo lô vẫn giữ nguyên trong _pl_tai_ve().


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
    """Tạo NHIỀU ảnh trong MỘT lượt của MỘT đoạn chat (cùng địa điểm).

    Dùng khi user tích chọn vài SF rồi bấm 'Tạo lại đã chọn'. Board gom theo địa
    điểm trước khi xếp hàng, nên hàm này luôn nhận đúng một nhóm cùng chat."""
    # Không tin thứ tự checkbox/request: chính thứ tự này quyết định cả cách chia
    # lô lẫn thứ tự ghép ảnh ChatGPT trả về. Luôn chuẩn hoá theo ID ngay tại cửa
    # cuối để mọi đường gọi (auto, tạo tay, retry, chạy lẻ) cùng một hành vi.
    sf_ids = sorted((i for i in sf_ids if i), key=_uu_tien)
    if not sf_ids:
        return
    data = BOARD.read()
    master = _nhom_cua(sf_ids[0], data) or None
    _ident = "LO:" + ",".join(sf_ids)

    # MỘT ĐỊA ĐIỂM = MỘT LÔ TẠI MỘT THỜI ĐIỂM — chặn bằng KHOÁ THẬT, không phải
    # bằng đọc JOBS: hai thợ nhấc hai lô cùng giây thì cả hai đều đọc thấy "chưa
    # ai chạy" rồi cùng mở chat mới trên hai tài khoản (đã xảy ra 2 lần). Khoá
    # theo master, giữ suốt từ lúc đọc chat tới lúc chốt chat; lô đến sau không
    # lấy được khoá thì trả về hàng đợi thử lại.
    # Lô toàn THẺ ĐỊA ĐIỂM chạy chat trắng, không đụng chat → không cần khoá.
    if master and not all(_la_the_dia_diem(BOARD.get_sf(i) or {"id": i}) for i in sf_ids):
        # PriorityQueue chỉ bảo đảm thứ tự NHẤC việc. Khi có nhiều worker, 02–07,
        # 08–13 và 14–15 có thể bị ba thợ nhấc cùng lúc rồi 14–15 thắng cuộc đua
        # lấy khoá master. Soi toàn bộ SF đang queued/running trước khi lấy khoá
        # để lô ID lớn phải nhường lô ID nhỏ của CÙNG nhóm/chat.
        with _ML_LOCK:
            khoa = _MASTER_LOCKS.setdefault(master, threading.Lock())
            _truoc = _lo_id_thap_hon_dang_cho(master, sf_ids, data)
            _da_khoa = not _truoc and khoa.acquire(blocking=False)
        if not _da_khoa:
            _n = _HOAN.get(_ident, 0)
            if _n < 240:                      # 240 × 5s = 20 phút, đủ cho lô trước
                _HOAN[_ident] = _n + 1
                _dat_job(_ident, {"state": "queued",
                                  "msg": (f"chờ {_truoc} chạy trước"
                                          if _truoc else
                                          f"chờ lô trước của {_ten_gon(master)} xong")})
                time.sleep(5)
                _xep(IMG_QUEUE, ("img", _ident, 0, tay))
                return
            raise RuntimeError(f"chờ lô trước của {master} quá lâu — chạy lại tay")
        _HOAN.pop(_ident, None)
        try:
            return _generate_lo_ruot(sf_ids, data, master, tay)
        finally:
            khoa.release()
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

    viec, attach, thieu = [], [], []
    for i in sf_ids:
        sf = BOARD.get_sf(i)
        if not sf or not (sf.get("prompt") or "").strip():
            thieu.append(i); continue
        viec.append((i, sf["prompt"].strip()))
        a, mis, _ = _sf_attachments(sf)
        if mis:
            thieu.append(f"{i}(thiếu ref)"); continue
        for x in a:
            if x not in attach:
                attach.append(x)
    if thieu:
        for i in sf_ids:
            JOBS[i] = {"state": "error", "msg": "lô dừng: " + ", ".join(thieu[:4])}
        raise RuntimeError("lô có SF hỏng: " + ", ".join(thieu[:4]))

    # LÔ CHỈ CÓ ẢNH GỐC thì chạy CHAT TRẮNG và KHÔNG chốt chat của địa điểm.
    # Chat của một địa điểm chỉ được chốt khi bắt đầu chạy SF CON, vì lúc đó mới
    # có ảnh master ĐÃ DUYỆT để đính làm bối cảnh. Chốt từ lô master là gắn cả
    # địa điểm vào một tài khoản trước khi biết bản master nào được chọn, và để
    # lại trong chat những bản master hỏng.
    chi_anh_goc = all(_la_the_dia_diem(BOARD.get_sf(i) or {"id": i}) for i in sf_ids)

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

    chat = _chat_cua_master(master) if (master and not chi_anh_goc) else {}

    # MỘT ĐỊA ĐIỂM = MỘT CHAT = MỘT TÀI KHOẢN. Chat sống trong profile Chrome của
    # đúng tài khoản đã mở nó; tài khoản khác mở URL đó thì ChatGPT báo
    # "Something went wrong", mà vì là 'chat cũ' nên board cũng không gửi lại
    # luatchung và không đính lại ref — hỏng câm. Gặp lô lạc tài khoản thì trả về
    # hàng đợi cho đúng thợ nhặt; chỉ khi tài khoản đó đã tắt mới mở chat mới.
    _ident = "LO:" + ",".join(sf_ids)
    _port_nay = int((getattr(_TL, "endpoint", "") or ":0").rsplit(":", 1)[1] or 0)
    _port_chat = int(chat.get("port") or 0)
    if chat.get("url") and _port_chat and _port_chat != _port_nay:
        # GIAO ĐÍCH DANH cho thợ giữ chat, không thả về hàng chung: hàng chung là
        # trò xổ số — hai thợ sai chuyền nhau nhặt-thả, thợ đúng đói vĩnh viễn.
        # Tài khoản giữ chat đang NGHỈ CÓ HẸN (trần đính tệp của ChatGPT) vẫn là
        # tài khoản đúng — giữ việc trong hàng riêng của nó, tới giờ thợ sống lại
        # là chạy tiếp. Đừng rơi xuống nhánh "đang TẮT" ở dưới: nhánh đó báo lỗi
        # và bắt user chạy tay, trong khi chỉ cần chờ.
        _nghi = _dang_nghi(f"http://localhost:{_port_chat}")
        if _nghi or _endpoint_alive(f"http://127.0.0.1:{_port_chat}"):
            with _CR_LOCK:
                o = CHO_RIENG.setdefault(_port_chat, [])
                if _ident not in o:
                    o.append(_ident)
                    o.sort(key=_uu_tien)     # id nhỏ chạy trước trong hàng riêng
            _dat_job(_ident, {"state": "queued",
                              "msg": f"đã giao cho tài khoản giữ chat (cổng {_port_chat})"
                                     + (f" · đang nghỉ tới "
                                        f"{time.strftime('%H:%M', time.localtime(_nghi))}, "
                                        f"tự chạy lại" if _nghi else "")})
            return
        # Tài khoản giữ chat CÒN TRONG DANH SÁCH nhưng Chrome chưa mở (vd vừa
        # khởi động lại máy) → DỪNG và bảo user bật nó, TUYỆT ĐỐI không lẳng
        # lặng mở chat mới: chat mới là mất trí nhớ bối cảnh của cả địa điểm.
        # Chỉ khi tài khoản đã bị XOÁ hẳn khỏi danh sách mới đành mở chat mới.
        with ACC_LOCK:
            _con = any(a["port"] == _port_chat for a in ACCOUNTS)
        if _con:
            _HOAN.pop(_ident, None)
            _acc_id = next((a["id"] for a in ACCOUNTS if a["port"] == _port_chat), "?")
            _dat_job(_ident, {
                "state": "error",
                "msg": f"chat của {_ten_gon(master)} nằm ở tài khoản {_acc_id} "
                       f"(cổng {_port_chat}) đang TẮT. Mở nó ở ⚙ Tài khoản rồi chạy lại "
                       f"— đừng chạy bằng tài khoản khác kẻo mất trí nhớ bối cảnh."})
            raise RuntimeError(f"{master}: tài khoản giữ chat (cổng {_port_chat}) đang tắt")
        _LOG.warning("[%s] tài khoản giữ chat (cổng %s) không dùng được — mở chat MỚI ở cổng %s",
                     master, _port_chat, _port_nay)
        chat = {}
    _HOAN.pop(_ident, None)

    # REF THƯỜNG chỉ cần gửi một lần trong chat, nhưng MỖI NHÂN VẬT phải gửi lại
    # theo CẶP: PORTRAIT neo khuôn mặt + FULL neo đúng trang phục. Chỉ gửi portrait
    # làm model tự bịa áo (ca S5: Maya từ áo vàng HOME thành áo nâu dù mặt đúng).
    # Bối cảnh và đạo cụ vẫn tận dụng bộ nhớ chat để tránh upload quá nhiều.
    da_gui = set(chat.get("refs") or [])
    def _loai_neo_nhan_vat(path: str) -> str:
        stem = os.path.splitext(os.path.basename(path))[0]
        if stem.endswith("_PORTRAIT"):
            return "portrait"
        if stem.endswith("_FULL"):
            return "full"
        return ""
    neo_lap = [x for x in attach if _loai_neo_nhan_vat(x)] if chat.get("url") else []
    can_dinh = ([x for x in attach
                 if _loai_neo_nhan_vat(x) or os.path.basename(x) not in da_gui]
                if chat.get("url") else attach)
    so_portrait = sum(_loai_neo_nhan_vat(x) == "portrait" for x in neo_lap)
    so_full = sum(_loai_neo_nhan_vat(x) == "full" for x in neo_lap)

    # Khối luật chung của địa điểm, nếu master có. Chỉ gửi khi MỞ CHAT MỚI.
    luat_chung = ""
    if master:
        m = BOARD.get_sf(master) or {}
        luat_chung = (m.get("luatchung") or "").strip()

    for i, _ in viec:
        JOBS[i] = {"state": "running",
                   "msg": f"lô {len(viec)} ảnh{_acct_label()}"
                          f" · {'chat cũ' if chat.get('url') else 'mở chat mới'}"
                          + (f" · đính {len(can_dinh)} ref"
                             + (f" ({so_portrait} mặt + {so_full} trang phục)"
                                if neo_lap else "")
                             if chat.get('url') and can_dinh else "")}
    _gen0 = DUNG_GEN          # chụp thế hệ TRƯỚC khi đi vào lượt chạy dài
    sess = _session()
    srcs, url, ghi = sess.generate_lo(viec, can_dinh, chat_url=chat.get("url", ""),
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
    if master and url and not chi_anh_goc:
        _luu_chat(master, url, port, da_gui | {os.path.basename(x) for x in can_dinh})

    # TẢI HẾT VỀ TRƯỚC KHI PHÁN. Kể cả lượt thiếu, thừa, hay trả kèm chữ — ảnh
    # đã sinh là lượt đã tiêu, không được vứt vì một phép đếm.
    luot = _pl_tai_ve(sess, srcs, viec, master, port, url, ghi) if srcs else None
    n_ve = int((luot or {}).get("so_anh") or 0)
    loi_text = (ghi.get("loi_text") or "").strip()

    # SỐ ẢNH KHÁC SỐ PROMPT THÌ KHÔNG GHÉP. Lệch một nấc là ảnh gắn nhầm SF, và
    # các ảnh cùng một địa điểm trông na ná nhau nên mắt rất khó bắt.
    # Nguyên nhân hay gặp: guardrail ChatGPT từ chối MỘT ảnh giữa lô ("may
    # violate our guardrails…"), thường chỉ cần xin lại là qua. Cơ chế tiếp tục:
    #   · lệch tới PL_LECH_TOI_DA ảnh → coi LƯỢT ĐÃ XONG, ảnh nằm sẵn trên đĩa,
    #     hiện thẳng lên thẻ để user bấm chọn. KHÔNG gửi lại: gửi lại là đốt
    #     thêm một lượt để mua lại thứ đã có trong tay.
    #   · lệch nhiều hơn thế (hoặc về 0 ảnh) → gần như chắc cả lượt bị chặn,
    #     gửi lại cả lô 3 lần rồi mới tách chạy lẻ để cô lập prompt phạm.
    _bi_dung = [i for i, _ in viec if i in DUNG_RIENG]
    if _bi_dung:
        with HUY_LOCK:
            DUNG_RIENG.difference_update(i for i, _ in viec)
        for i, _ in viec:
            JOBS[i] = {"state": "error",
                       "msg": "đã dừng riêng" if i in _bi_dung
                              else "dừng theo lô (một lô là một tin nhắn)"}
        _LOG.info("lô %d ảnh bị user dừng riêng — không thử lại", len(viec))
        return

    # ---- LƯỢT LỆCH: giữ nguyên ảnh, để user gắn tay ngay trên thẻ ----------
    if luot and (n_ve != len(viec) or loi_text) and abs(n_ve - len(viec)) <= PL_LECH_TOI_DA:
        _ly = (f"lượt trả kèm chữ ({loi_text[:60]}…)" if loi_text and n_ve == len(viec)
               else f"thiếu {len(viec) - n_ve} ảnh" if n_ve < len(viec)
               else f"thừa {n_ve - len(viec)} ảnh")
        if loi_text and n_ve != len(viec):
            _ly += " · lượt còn trả kèm chữ"
        luot["ly_do"] = _ly
        _pl_ghi_meta(luot)
        _HOAN.pop("GR:" + _ident, None)
        for i, _ in viec:
            JOBS[i] = {"state": "error",
                       "msg": f"lượt {luot['turn']}: {_ly} — {n_ve} ảnh ĐÃ TẢI VỀ, "
                              f"bấm chọn ngay trên thẻ (không gửi lại, không mất ảnh)"}
        _LOG.warning("lượt %d LỆCH (%d ảnh / %d prompt · %s) — giữ nguyên cho user chọn tay",
                     luot["turn"], n_ve, len(viec), _ly)
        return

    if n_ve != len(viec):
        # USER ĐÃ BẤM DỪNG trong lúc lượt này đang chạy → KHÔNG được tự xếp hàng lại.
        # Không có chốt này thì cú "Dừng tất cả" bị vô hiệu một cách im lặng: lô hỏng
        # quay lại hàng đợi rồi vẽ đè lên ảnh đang có.
        if DUNG_GEN != _gen0:
            for i, _ in viec:
                JOBS[i] = {"state": "error", "msg": "đã dừng — không thử lại"}
            _LOG.info("lô %d ảnh xong sau khi user bấm dừng — bỏ, không xếp hàng lại", len(viec))
            return
        # Guardrail chặn là chặn CẢ LƯỢT (thường về 0 ảnh) và phần lớn chỉ cần
        # GỬI LẠI NGUYÊN LÔ là qua — đó là đường chính, giữ nguyên tốc độ lô.
        # Tách chạy lẻ CHỈ là đường cùng sau 3 lần cả lô đều trượt: lúc đó gần
        # như chắc có một prompt phạm thật, và chạy lẻ là cách duy nhất chỉ ra nó.
        _gr = "GR:" + _ident
        _n = _HOAN.get(_gr, 0)
        if _n < 3:
            _HOAN[_gr] = _n + 1
            _con = (f" · {n_ve} ảnh vớt được đã để ở lượt {luot['turn']}"
                    if luot and n_ve else "")
            for i, _ in viec:
                JOBS[i] = {"state": "queued",
                           "msg": f"ChatGPT chặn/thiếu ảnh ({n_ve}/{len(viec)}) "
                                  f"— gửi lại cả lô, lần {_n + 1}/3{_con}"}
            time.sleep(15)
            _xep(IMG_QUEUE, ("img", _ident, 0, tay))
            return
        _HOAN.pop(_gr, None)
        if len(viec) > 1:
            _LOG.warning("lô %d ảnh trượt 3 lần liền — tách chạy lẻ để cô lập prompt bị chặn",
                         len(viec))
            for i, _ in viec:
                JOBS[i] = {"state": "queued", "msg": "cả lô trượt 3 lần → chạy lẻ tìm prompt bị chặn"}
                _xep(IMG_QUEUE, ("img", "LO:" + i, 0, tay))
            return
        i = viec[0][0]
        JOBS[i] = {"state": "error",
                   "msg": "ChatGPT chặn đúng ảnh này nhiều lần (guardrail 'similarity to "
                          "third-party content'). Cách chữa: sửa prompt — bớt chữ nhấn "
                          "vào gương mặt/người nổi tiếng, đổi vài chi tiết bố cục; hoặc "
                          "đổi ảnh ref của nhân vật rồi chạy lại."}
        raise RuntimeError(f"{i}: guardrail chặn nhiều lần")

    # ---- ĐỦ ĐÚNG SỐ VÀ KHÔNG KÈM CHỮ → GHÉP TỰ ĐỘNG ----------------------
    # Ảnh đã nằm sẵn trong thư mục lượt, chỉ còn chép sang versions/. GHÉP RỒI
    # VẪN GIỮ thư mục lượt (xem PL_GIU_TOI_DA): lượt ghép đúng cũng phải còn
    # trong hộp chờ để dịch ảnh sang thẻ khác, không phải vẽ lại.
    hong = []
    for k, (i, _) in enumerate(viec, 1):
        _HOAN.pop("GR:" + _ident, None)  # về đủ ảnh thì xoá đếm guardrail của lô
        _HOAN.pop("GR:LO:" + i, None)    # và của bản chạy lẻ nếu từng tách
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
            sf_now = BOARD.get_sf(i) or {}
            if sf_now.get("status") == "approved" and BOARD.find_file(i):
                JOBS[i] = {"state": "done",
                           "msg": f"xong (lượt {luot['turn']}) — đã duyệt nên giữ bản cũ, "
                                  f"bản mới ở dãy bản"}
                continue
            BOARD.set_current(i, out)
            _mark_picked(i, "picked", os.path.basename(out))
        JOBS[i] = {"state": "done", "msg": f"xong (lô · lượt {luot['turn']} #{k:02d})"}
    if hong:
        luot["ly_do"] = "chép vào versions/ lỗi ở " + ", ".join(hong[:4])
    else:
        luot["ly_do"] = (f"đã ghép tự động đủ {len(viec)} ảnh — giữ lại để "
                         f"kéo sang thẻ khác nếu thứ tự chưa đúng")
    _pl_ghi_meta(luot)
    _pl_don_bot()


def _generate(sf_id: str, manual: bool = False):
    """Chạy trong một luồng thợ. Lỗi hết lượt / cửa sổ chết được ném lên cho
    worker phân loại và chuyển việc sang tài khoản khác."""
    sf = BOARD.get_sf(sf_id)
    if not sf:
        raise RuntimeError("Không tìm thấy SF")
    prompt = (sf.get("prompt") or "").strip()
    if not prompt:
        raise RuntimeError("SF chưa có prompt")

    attach, missing, ref_ids = _sf_attachments(sf)
    if missing:
        raise RuntimeError("Thiếu ảnh tham chiếu: " + ", ".join(missing))

    in_batch = sf_id in BATCH
    ok, out = False, None
    for attempt in range(4):        # 3 lần mở lại phiên nếu tab crash / bị đóng
        if not in_batch:            # đang chạy theo lô thì để _batch_tick lo thông báo
            JOBS[sf_id] = {
                "state": "running",
                "msg": f"đang tạo…{_acct_label()} ({len(attach)} ảnh ref: {', '.join(ref_ids)})",
            }
        try:
            sess = _session()
            with BOARD_LOCK:
                # giữ chỗ file ngay, để các bản chạy song song không đè tên nhau
                out = BOARD.next_version_path(sf_id, reserve=True)
            ok = sess.generate(prompt, attach, out)
            if ok and os.path.exists(out) and os.path.getsize(out) > 1024:
                _dem_cong()
                break
            raise RuntimeError("ChatGPT không trả về ảnh (thử lại hoặc kiểm tra tab ChatGPT)")
        except Exception as e:
            _drop_reserved(out); out = None
            if attempt < 3 and _is_dead_session_error(e) and _endpoint_alive(_TL.endpoint):
                _release_tl()
                time.sleep(4 + 4 * attempt)   # cho Chrome kịp thu hồi bộ nhớ
                if not in_batch:
                    JOBS[sf_id] = {"state": "running",
                                   "msg": f"tab chết → mở lại phiên (lần {attempt + 2})…"}
                continue
            if _batch_tick(sf_id, ok=False):
                return              # lô tự tổng kết, không ném lỗi ra worker
            raise
    if not ok or not out or not os.path.exists(out):
        if _batch_tick(sf_id, ok=False):
            return
        raise RuntimeError("ChatGPT không trả về ảnh (thử lại hoặc kiểm tra tab ChatGPT)")
    with BOARD_LOCK:
        # TÔN TRỌNG LỰA CHỌN CỦA USER: nếu user đã bấm chọn một bản (picked)
        # hoặc đã DUYỆT SF này, bản render mới chỉ nằm trong versions/ để
        # user tự so — TUYỆT ĐỐI không ghi đè ảnh chính.
        sf_now = BOARD.get_sf(sf_id) or {}
        # Khoá chỉ chặn render TỰ ĐỘNG (auto-run, guard, lô nền) đè lên bản user
        # đã chọn. User tự bấm "Tạo ảnh" là chủ động muốn bản mới → phải đè,
        # nếu không thì nhìn như "tạo xong mà không tải về".
        # ĐÃ DUYỆT = chốt tuyệt đối, kể cả user tự bấm "Tạo lại" (muốn thay thì
        # bỏ duyệt trước). Chỉ "picked" mới nhường cho cú bấm tay.
        user_locked = (sf_now.get("status") == "approved") or (
            (not manual) and bool(sf_now.get("picked")))
        if user_locked and BOARD.find_file(sf_id):
            if sf_now.get("status") == "approved":
                _LOG.info("%s ĐÃ DUYỆT — giữ nguyên bản chốt, bản mới ở versions/%s",
                          sf_id, os.path.basename(out))
                JOBS[sf_id] = {"state": "done",
                               "msg": "xong — đã duyệt nên giữ bản cũ, bản mới ở dãy bản"}
        elif not (in_batch and BOARD.find_file(sf_id)):
            BOARD.set_current(sf_id, out)
            _mark_picked(sf_id, "picked", os.path.basename(out))
    if _batch_tick(sf_id, ok=True):
        return
    JOBS[sf_id] = {"state": "done", "msg": "xong"}


# ---------------------------------------------------------------- http
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
            self._send(200, HTML.encode("utf-8"), "text/html; charset=utf-8")
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
            self._json({"jobs": JOBS, "auto": _auto_status(), "nhom": _nh,
                        "pl": _pl_dem(), "dan_ma": _dan_ma_doc(),
                        "auto_vid": _auto_vid_doc(),
                        "mtime": int(os.path.getmtime(BOARD.path))})
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
            self._json({"accounts": _accounts_status()})
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
            BOARD.write(data)
            self._json({"ok": True, "mtime": int(os.path.getmtime(BOARD.path))})
        elif u.path == "/api/upload":
            if not re.match(r"^[A-Za-z0-9_\-]+$", sf_id):
                self._json({"ok": False, "err": "sf id không hợp lệ"}, 400); return
            BOARD.save_upload(sf_id, raw, q.get("name", ["x.png"])[0])
            self._json({"ok": True})
        elif u.path == "/api/open-project":
            ok, err, port = _open_project(q.get("dir", [""])[0])
            self._json({"ok": ok, "err": err, "port": port}, 200 if ok else 409)
        elif u.path == "/api/generate":
            if JOBS.get(sf_id, {}).get("state") == "running":
                self._json({"ok": False, "err": "đang chạy"}); return
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
            so_ban = int(q.get("n", ["1"])[0] or 1)
            if so_ban <= 1:
                JOBS[sf_id] = {"state": "queued", "msg": "chờ lô 1 ảnh"}
                _xep(IMG_QUEUE, ("img", "LO:" + sf_id, 0, True))
            else:
                _enqueue("img", sf_id, so_ban, manual=True)
            self._json({"ok": True, "qua_lo": so_ban <= 1})
        elif u.path == "/api/dung-het":
            # DỪNG TẤT CẢ: tắt mọi auto, vét sạch hàng đợi, và ĐÓNG CỬA SỔ CHROME
            # của những tài khoản ảnh đang bận. Đóng Chrome là cách DUY NHẤT cắt
            # được việc đang chạy: thợ đang nằm trong vòng chờ ChatGPT vẽ, không
            # có chỗ nào để nó ngó lại cờ huỷ giữa chừng.
            global DUNG_GEN
            DUNG_GEN += 1        # thợ đang chạy dở soi số này, thấy đổi là không thử lại
            AUTO.clear()
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
                DA_HUY.update(dang)
                DA_HUY.update(k for k in JOBS if k.startswith("LO:"))
            for k in dang:
                JOBS[k] = {"state": "error", "msg": "đã dừng"}
            dong = []
            if q.get("dong_chrome", ["1"])[0] == "1":
                with ACC_LOCK:
                    ports = [a["port"] for a in ACCOUNTS if a.get("enabled")]
                for pt in ports:
                    try:
                        _kill_chrome(pt); dong.append(pt)
                    except Exception:
                        pass
            self._json({"ok": True, "bo": bo, "dung": len(dang), "dong_chrome": dong})
        elif u.path == "/api/huy":
            # Chỉ vứt việc CHƯA chạy. Việc đang chạy phải để nó xong — cắt giữa
            # chừng là mất cả ảnh đã sinh mà không thu lại được.
            bo = 0
            try:
                while True:
                    it = IMG_QUEUE.get_nowait()[2]       # (prio, seq, item) → item
                    _dat_job(it[1], {"state": "error", "msg": "đã huỷ khỏi hàng đợi"})
                    IMG_QUEUE.task_done(); bo += 1
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
            if JOBS.get(sf, {}).get("state") != "running":
                self._json({"ok": False, "err": "việc này không đang chạy"}); return
            with HUY_LOCK:
                DUNG_RIENG.add(sf)
            JOBS[sf] = {"state": "running", "msg": "đang dừng… (thợ soi cờ mỗi 5s)"}
            self._json({"ok": True, "sf": sf})
        elif u.path == "/api/huy-viec":
            # HUỶ ĐÚNG MỘT VIỆC, không phải cả hàng đợi.
            #
            # Một lô là MỘT tin nhắn nên không cắt đôi được: cách làm là huỷ lô cũ
            # rồi xếp lại lô mới gồm các thành viên còn lại. Việc ĐANG CHẠY thì
            # không cắt được (thợ đang nằm trong lượt chờ ChatGPT vẽ) — chỉ có
            # "Dừng tất cả" mới cắt nổi, vì nó đóng Chrome.
            sf = (q.get("sf", [""])[0] or "").strip()
            if not sf:
                self._json({"ok": False, "err": "thiếu tham số sf"}); return
            if JOBS.get(sf, {}).get("state") == "running":
                self._json({"ok": False, "err": "việc này ĐANG CHẠY — không cắt giữa "
                                                "chừng được. Dùng '⏹ Dừng tất cả'."}); return
            bo, con_lai = [], []
            for k, v in list(JOBS.items()):
                if not k.startswith("LO:") or v.get("state") != "queued":
                    continue
                tv = [x for x in k[3:].split(",") if x]
                if sf not in tv:
                    continue
                bo.append(k)
                con_lai = [x for x in tv if x != sf]
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
            for i in sorted(can, key=_uu_tien):
                JOBS[i] = {"state": "queued", "msg": "chờ chạy ảnh gốc địa điểm"}
                _xep(IMG_QUEUE, ("img", "LO:" + i, 0, True))
            _LOG.info("chạy %d thẻ địa điểm: %s", len(can), ", ".join(can))
            self._json({"ok": True, "so": len(can), "ds": can})
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
                chat = _chat_cua_master(m) if m else {}
                lo = []
                for k in range(0, len(xs), TOI_DA_ANH_MOT_LO):
                    phan = xs[k:k + TOI_DA_ANH_MOT_LO]
                    lo.append({"sf": phan,
                               "ky_tu": sum(len((tat.get(i) or {}).get("prompt") or "")
                                            for i in phan)})
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
                    "chat_mo": bool(chat.get("url")),
                    "chat_url": chat.get("url", ""),
                    "da_co": dem_master.get(m, 0),
                    "lo": lo,
                })
            out.sort(key=lambda x: (x["master"] == "", x["master"]))
            self._json({"ok": True, "nhom": out,
                        "tran_anh_mot_lo": TOI_DA_ANH_MOT_LO,
                        "tran_ky_tu_khuyen": 8000})
        elif u.path == "/api/tao-lo":
            # GOM THEO ĐỊA ĐIỂM rồi mới xếp hàng: mỗi địa điểm là một đoạn chat,
            # nên các SF cùng địa điểm phải đi CHUNG một tin nhắn. Tích 2 ảnh ở
            # Sảnh + 1 ở Bếp = 2 lô, không phải 3 lượt riêng.
            ids = [x for x in (q.get("sf", [""])[0] or "").split(",") if x.strip()]
            if not ids:
                self._json({"ok": False, "err": "chưa chọn SF nào"}); return
            data = BOARD.read()
            nhom: dict[str, list[str]] = {}
            for i in ids:
                if JOBS.get(i, {}).get("state") == "running":
                    continue
                nhom.setdefault(_nhom_cua(i, data), []).append(i)
            # CHẶN NGAY TẠI CỬA. Thợ cũng chặn (đó mới là chốt thật), nhưng chặn
            # ở đây để user biết LIỀN thay vì thấy cả loạt job đỏ vài giây sau.
            _chan = []
            for m, xs in nhom.items():
                if all(_la_the_dia_diem(BOARD.get_sf(i) or {"id": i}) for i in xs):
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
            # CẮT LÔ Ở TOI_DA_ANH_MOT_LO ẢNH. Trần này từng phải để thấp vì lệch
            # một ảnh là bỏ nguyên lô; nay ảnh luôn được tải về trước nên lô to
            # chỉ còn phải trả giá bằng thời gian chờ (~180s/ảnh).
            # ÉP TÀI KHOẢN (tham số tk=<cổng>) — cũng chính là đường THOÁT khỏi
            # một đoạn chat hỏng.
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
            chat_moi = (q.get("moi", [""])[0] or "") in ("1", "true", "yes")
            if ep or chat_moi:
                with BOARD_LOCK:
                    dl = BOARD.read(); doi = False
                    for m in nhom:
                        if not m:
                            continue
                        if _khoa_la_the(m):
                            for sc in dl.get("scenes", []):
                                for sfd in sc.get("sfs", []):
                                    if sfd.get("id") == m and sfd.pop("chat", None) is not None:
                                        doi = True
                        elif (dl.get("chats") or {}).pop(m, None) is not None:
                            doi = True
                    if doi:
                        BOARD.write(dl)
                        _LOG.info("mở chat mới cho %d nhóm%s", len(nhom),
                                  f" · ép cổng {ep}" if ep else "")

            so_lo = 0
            for m, xs in nhom.items():
                xs.sort(key=_uu_tien)
                for k in range(0, len(xs), TOI_DA_ANH_MOT_LO):
                    lo = xs[k:k + TOI_DA_ANH_MOT_LO]
                    so_lo += 1
                    ident = "LO:" + ",".join(lo)
                    for i in lo:
                        JOBS[i] = {"state": "queued",
                                   "msg": f"chờ lô {len(lo)} ảnh · {_ten_gon(m)}"
                                          + (f" · ép cổng {ep}" if ep else "")}
                    if ep:
                        with _CR_LOCK:           # giao ĐÍCH DANH cho thợ của cổng đó
                            o = CHO_RIENG.setdefault(ep, [])
                            o.append(ident)
                            o.sort(key=_uu_tien)
                    else:
                        _xep(IMG_QUEUE, ("img", ident, 0, True))
            self._json({"ok": True, "so_lo": so_lo, "ep_tk": ep,
                        "lo": {m: len(x) for m, x in nhom.items()}})
        elif u.path == "/api/dan-ma":
            # Bật/tắt việc in mã SF vào góc ảnh. Chỉ ảnh render TỪ ĐÂY VỀ SAU
            # đổi theo — ảnh đã có trên đĩa giữ nguyên như lúc nó được vẽ.
            on = (q.get("on", [""])[0] or "") in ("1", "true", "yes")
            _dan_ma_ghi(on)
            _LOG.info("dán mã SF vào ảnh: %s", "BẬT" if on else "TẮT")
            self._json({"ok": True, "on": on})
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
            with BOARD_LOCK:
                BOARD.set_current(den, out)
            _mark_picked(den, "picked", os.path.basename(out))
            _LOG.info("chép ảnh %s → %s (%s)", tu, den, os.path.basename(out))
            self._json({"ok": True, "msg": "đã đặt làm ảnh chính"})
        elif u.path == "/api/pick-version":
            f = q.get("file", [""])[0]
            src = os.path.join(BOARD.versions, os.path.basename(f))
            if os.path.isfile(src):
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
            if not sid:
                self._json({"ok": False, "err": "thiếu scene"}, 400); return
            with AUTO_LOCK:
                if op == "off" or (op == "toggle" and sid in AUTO):
                    AUTO.pop(sid, None)
                else:
                    AUTO[sid] = {"try": {}, "last": {}, "stat": {}}
            self._json({"ok": True, "on": sid in AUTO, "auto": _auto_status()})

        elif u.path == "/api/acct":
            op = q.get("op", [""])[0]
            port = int(q.get("port", ["0"])[0] or 0)
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
            if JOBS.get(sf_id, {}).get("state") == "running":
                self._json({"ok": False, "err": "đang chạy"}); return
            _enqueue("vid", sf_id)
            self._json({"ok": True})
        elif u.path == "/api/upload-video":
            if not re.match(r"^[A-Za-z0-9_\-]+$", sf_id):
                self._json({"ok": False, "err": "id không hợp lệ"}, 400); return
            vp = BOARD.next_vversion(sf_id)
            with open(vp, "wb") as f:
                f.write(raw)
            BOARD.set_video(sf_id, vp)
            self._json({"ok": True})
        elif u.path == "/api/pick-vversion":
            f = q.get("file", [""])[0]
            src = os.path.join(BOARD.vversions, os.path.basename(f))
            if os.path.isfile(src):
                BOARD.set_video(sf_id, src)
                _mark_picked(sf_id, "vpicked", os.path.basename(src))
                self._json({"ok": True})
            else:
                self._json({"ok": False, "err": "không thấy bản này"}, 404)
        elif u.path == "/api/delete-video":
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


# ---------------------------------------------------------------- ui
# Giao diện board tách sang ui/board.html (2026-08-09) — sfboard.py từ 6.231 còn ~3.400
# dòng. SỬA GIAO DIỆN THÌ SỬA FILE ĐÓ, không dán HTML/CSS/JS ngược vào đây.
HTML = open(os.path.join(_HERE, "ui", "board.html"), encoding="utf-8").read()



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
    if not PROJECTS_ROOT:
        PROJECTS_ROOT = os.path.dirname(BOARD.dir)
    if "--port" not in args:
        port = _free_port(port)          # cổng bận thì tự nhảy sang cổng trống
    SERVE_PORT = port
    _reg_register(os.path.basename(BOARD.dir), port)
    atexit.register(_reg_unregister, os.path.basename(BOARD.dir))
    url = f"http://localhost:{port}"
    print(f"SF Board v2  →  {url}")
    print(f"Phim    : {BOARD.dir}")
    print(f"Dữ liệu : {BOARD.path}")
    _init_accounts()
    _dem_nap()
    print(f"Tài khoản: {ACC_PATH}  (quản lý bật/tắt/mở Chrome ngay trên board — nút ⚙ Tài khoản)")
    print(f"Đếm ngày : {DEM_PATH}  (số bản mỗi tài khoản làm được trong ngày — đọc cột 'cao nhất')")
    # Tài khoản đang BẬT mà chưa có cửa sổ Chrome → mở sẵn ngay lúc khởi động.
    # Chỉ làm một lần ở đây, không làm trong supervisor: nếu bạn cố ý đóng một
    # cửa sổ giữa chừng thì nó phải nằm im, không bị mở lại liên tục.
    opened = 0
    for a in ACCOUNTS:
        if a.get("enabled") and not _endpoint_alive(_ep(a)):
            if _launch_chrome(a):
                opened += 1
    if opened:
        print(f"  → đang mở {opened} cửa sổ Chrome cho các tài khoản đang bật…")
        time.sleep(3 + opened)
    for a in ACCOUNTS:
        live = "sống" if _endpoint_alive(_ep(a)) else "chưa mở Chrome"
        onoff = "BẬT" if a.get("enabled") else "tắt"
        print(f"  · {a['id']:8s} {_KIND_NAME[a['kind']]:16s} port {a['port']}  [{onoff}, {live}]")
    # Supervisor tự mở/đóng luồng thợ theo trạng thái bật/tắt của từng tài khoản.
    threading.Thread(target=_supervisor, daemon=True).start()
    threading.Thread(target=_auto_runner, daemon=True).start()
    threading.Thread(target=_luu_ban_runner, daemon=True).start()
    try:
        webbrowser.open(url)
    except Exception:
        pass
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
