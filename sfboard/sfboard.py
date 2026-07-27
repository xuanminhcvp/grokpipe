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
import subprocess
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
        os.makedirs(self.assets, exist_ok=True)
        os.makedirs(self.versions, exist_ok=True)
        os.makedirs(self.videos, exist_ok=True)
        os.makedirs(self.vversions, exist_ok=True)
        if not os.path.exists(self.path):
            self._write({"film": os.path.basename(self.dir), "updated_at": "", "scenes": []})

    def read(self) -> dict:
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["mtime"] = int(os.path.getmtime(self.path))
        for sc in data.get("scenes", []):
            sc.setdefault("shots", [])
            for sf in sc.get("sfs", []):
                sf["image"] = self._img_url(self.assets, sf["id"])
                sf["versions"] = self._versions(sf["id"])
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
        shutil.copy2(src, os.path.join(self.videos, sid + ".mp4"))

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

    def _versions(self, sf_id: str) -> list[dict]:
        out = []
        for name in sorted(os.listdir(self.versions)):
            s, ext = os.path.splitext(name)
            if ext.lower() in IMAGE_EXT and re.match(rf"^{re.escape(sf_id)}_v\d+$", s):
                p = os.path.join(self.versions, name)
                if os.path.getsize(p) < 1024:
                    continue      # file rỗng đang được một luồng khác giữ chỗ
                out.append({"file": name, "url": f"/versions/{name}?t={int(os.path.getmtime(p))}",
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
        shutil.copy2(src, os.path.join(self.assets, sf_id + ext))

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
ACCOUNTS: list[dict] = []      # {id, kind: img|vid, port, profile, enabled}
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
    ACCOUNTS = accs
    _save_accounts()


def _pool(kind: str) -> list[str]:
    """Endpoint các tài khoản ĐANG BẬT cho loại việc này.

    Video fallback sang tài khoản ChatGPT nếu chưa khai báo tài khoản Grok nào."""
    with ACC_LOCK:
        pool = [_ep(a) for a in ACCOUNTS if a["kind"] == kind and a["enabled"]]
        if kind == "vid" and not pool:
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
    "--js-flags=--max-old-space-size=512",
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


def _kill_chrome(port: int):
    """Đóng cửa sổ Chrome của tài khoản này.

    Mỗi tài khoản là một tiến trình Chrome riêng (user-data-dir riêng), nhận diện
    được qua cờ --remote-debugging-port nên không đụng vào Chrome cá nhân của user.
    Phiên đăng nhập nằm trong profile trên đĩa, đóng cửa sổ không mất."""
    import subprocess
    subprocess.run(["pkill", "-f", f"remote-debugging-port={port}"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


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
    ))


def _is_dead_session_error(e: Exception) -> bool:
    """Tab/cửa sổ Chrome đã đóng — nhả phiên rồi thử lại trên CÙNG tài khoản."""
    m = str(e).lower()
    return any(k in m for k in (
        "has been closed", "target closed", "browser has been closed",
        "connection closed", "websocket", "target page, context or browser",
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
IMG_QUEUE: "queue.Queue[tuple]" = queue.Queue()
VID_QUEUE: "queue.Queue[tuple]" = queue.Queue()
BOARD_LOCK = threading.RLock()      # nhiều thợ cùng ghi sf-board.json
_LOG = logging.getLogger("sfboard")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")

# Mỗi luồng thợ giữ Playwright + phiên RIÊNG của nó (sync_playwright không dùng chung
# được giữa các luồng, nhưng mỗi luồng có một instance riêng thì hoàn toàn hợp lệ).
_TL = threading.local()

DEAD: dict[str, str] = {}           # endpoint -> lý do (hết lượt / cửa sổ Chrome đã đóng)
_DEAD_LOCK = threading.Lock()


def _mark_dead(endpoint: str, reason: str, kind: str = "img"):
    pool = _pool(kind)
    with _DEAD_LOCK:
        DEAD[endpoint] = reason
        alive = [e for e in pool if e not in DEAD]
    _LOG.warning("%s ở %s — còn %d/%d tài khoản %s chạy được",
                 reason, endpoint, len(alive), len(pool),
                 "Grok" if kind == "vid" else "ChatGPT")


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


def _worker(endpoint: str, kind: str):
    """Một luồng thợ gắn cứng với MỘT tài khoản.

    kind='img' → lấy việc từ IMG_QUEUE, chạy trên tài khoản ChatGPT.
    kind='vid' → lấy việc từ VID_QUEUE, chạy trên tài khoản Grok.
    Tự nghỉ khi tài khoản bị tắt trên giao diện hoặc bị đánh dấu chết;
    supervisor sẽ mở thợ mới khi tài khoản được bật/hồi sinh."""
    _TL.endpoint = endpoint
    _TL.kind = kind
    QUEUE = IMG_QUEUE if kind == "img" else VID_QUEUE
    while True:
        if endpoint not in _pool(kind) or DEAD.get(endpoint):
            _release_tl()
            return
        try:
            _, ident, tries = QUEUE.get(timeout=2)
        except queue.Empty:
            continue
        stop = False
        try:
            if kind == "img":
                _generate(ident)
            else:
                _gen_video(ident)
        except Exception as e:
            fatal = _is_quota_error(e) or (
                _is_dead_session_error(e) and not _endpoint_alive(endpoint))
            if fatal:
                reason = "hết lượt" if _is_quota_error(e) else "cửa sổ Chrome đã đóng"
                _mark_dead(endpoint, reason, kind)
                _release_tl()
                stop = True
                if tries < len(_pool(kind)) and _alive_count(kind) > 0:
                    JOBS[ident] = {"state": "running",
                                   "msg": f"{reason} → chuyển sang tài khoản khác…"}
                    QUEUE.put((kind, ident, tries + 1))
                else:
                    JOBS[ident] = {"state": "error",
                                   "msg": f"{reason}; không còn tài khoản nào khả dụng"}
            else:
                JOBS[ident] = {"state": "error", "msg": str(e)[:300]}
        finally:
            QUEUE.task_done()
        if stop:
            _LOG.warning("Thợ %s (%s) dừng.", endpoint, kind)
            return


def _enqueue(kind: str, ident: str, copies: int = 1):
    """Xếp việc vào hàng. copies>1 = tạo nhiều bản SONG SONG cho cùng một SF,
    mỗi bản chạy trên một tài khoản khác nhau, kết quả vào versions/ để chọn."""
    _wake_all()
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
        q.put((kind, ident, 0))


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


# ─────────────────── NGỦ KHI RẢNH (tiết kiệm RAM) ───────────────────────────
# Không có việc trong IDLE_SLEEP_SEC giây thì đóng hết cửa sổ Chrome (vẫn giữ
# tài khoản ở trạng thái BẬT). Có việc mới thì tự mở lại. Đăng nhập nằm trong
# profile trên đĩa nên đóng/mở không mất phiên.
IDLE_SLEEP_SEC = 600            # 10 phút
SLEEPING = {"on": False}
_LAST_BUSY = {"at": time.time()}


def _wake_all():
    """Có việc mới → mở lại Chrome cho mọi tài khoản đang bật."""
    if not SLEEPING["on"]:
        return
    SLEEPING["on"] = False
    _LAST_BUSY["at"] = time.time()
    with ACC_LOCK:
        accs = [dict(a) for a in ACCOUNTS if a["enabled"]]
    for a in accs:
        if not _endpoint_alive(_ep(a)):
            _launch_chrome(a)
    _LOG.info("Có việc mới → đánh thức %d cửa sổ Chrome.", len(accs))


def _idle_sleeper():
    while True:
        time.sleep(30)
        try:
            busy = (not IMG_QUEUE.empty() or not VID_QUEUE.empty()
                    or any(j.get("state") == "running" for j in JOBS.values()))
            if busy:
                _LAST_BUSY["at"] = time.time()
                continue
            if SLEEPING["on"] or time.time() - _LAST_BUSY["at"] < IDLE_SLEEP_SEC:
                continue
            with ACC_LOCK:
                ports = [a["port"] for a in ACCOUNTS if a["enabled"]]
            if not ports:
                continue
            for port in ports:
                _kill_chrome(port)
            SLEEPING["on"] = True
            _LOG.info("Rảnh %d phút → đóng %d cửa sổ Chrome để tiết kiệm RAM. "
                      "Có việc mới sẽ tự mở lại.", IDLE_SLEEP_SEC // 60, len(ports))
        except Exception:
            pass


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
                if SLEEPING["on"]:
                    continue            # đang ngủ: đừng đánh thức, đợi có việc
                if DEAD.get(ep) == "cửa sổ Chrome đã đóng" and _endpoint_alive(ep):
                    with _DEAD_LOCK:
                        DEAD.pop(ep, None)
                    _LOG.info("Chrome %s đã mở lại — hồi sinh tài khoản.", ep)
                if DEAD.get(ep):
                    continue
                kinds = [a["kind"]]
                if a["kind"] == "img" and not has_vid:
                    kinds.append("vid")     # chưa có tài khoản Grok → thợ ảnh kiêm video
                for k in kinds:
                    key = (a["port"], k)
                    th = WORKERS.get(key)
                    if th is None or not th.is_alive():
                        t = threading.Thread(target=_worker, args=(ep, k), daemon=True)
                        WORKERS[key] = t
                        t.start()
        except Exception:
            pass
        time.sleep(4)


# ───────────────────────── CHẠY TỰ ĐỘNG CẢ SCENE ─────────────────────────────
# Bật cho một scene rồi để đó: thiếu ảnh SF nào thì tạo ảnh, ảnh xong tới đâu
# thì đẩy video tới đó, cái nào lỗi thì tự bắn lại. Xong cả scene thì tự tắt.

AUTO: dict[str, dict] = {}       # scene_id -> {"try": {ident: số lần}, "last": {ident: vòng}}
AUTO_LOCK = threading.Lock()
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

    # 1) ảnh SF còn thiếu
    miss_img = [f["id"] for f in sfs if not BOARD.find_file(f["id"])]
    for sid in miss_img:
        if JOBS.get(sid, {}).get("state") == "running":
            continue
        if _auto_allow(st, sid, cyc):
            _enqueue("img", sid)
            _LOG.info("[auto %s] tạo lại ảnh %s (lần %d)", sc["id"], sid, st["try"][sid])

    # 2) video còn thiếu, nhưng chỉ khi ảnh SF của shot đó đã có
    miss_vid = [sh["id"] for sh in shots if not BOARD.video_file(sh["id"])]
    for sh in shots:
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


def _accounts_status() -> list[dict]:
    """Trạng thái từng tài khoản cho giao diện."""
    out = []
    with ACC_LOCK:
        accs = [dict(a) for a in ACCOUNTS]
    for a in accs:
        ep = _ep(a)
        chrome = _endpoint_alive(ep)
        worker = any(k[0] == a["port"] and t.is_alive() for k, t in WORKERS.items())
        out.append({**a, "endpoint": ep, "chrome": chrome, "sleeping": SLEEPING["on"],
                    "dead": DEAD.get(ep, ""), "worker": worker})
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


def _hub():
    ctx = getattr(_TL, "ctx", None)
    if ctx is not None:
        try:
            ctx.pages  # chạm vào để biết context còn sống
            return ctx
        except Exception:
            _TL.pw = None
            _TL.ctx = None
    from playwright.sync_api import sync_playwright
    _TL.pw = sync_playwright().start()
    browser = _TL.pw.chromium.connect_over_cdp(_TL.endpoint)
    _TL.ctx = browser.contexts[0] if browser.contexts else browser.new_context()
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
    s = GrokSession(cdp_endpoint=None, logger=_LOG, resolution="720p", shared_ctx=_hub())
    if not s.start():
        raise RuntimeError(f"Không nối được Grok ở {_TL.endpoint}. "
                           "Mở Chrome debug và đăng nhập grok.com rồi thử lại.")
    _TL.gsess = s
    return s


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
    requested: list[str] = []
    for rid in chars:
        requested.append(rid)
        if rid.endswith("_PORTRAIT") and person(rid) not in explicit_full:
            full_id = rid.removesuffix("_PORTRAIT") + "_FULL"
            if BOARD.find_file(full_id):
                requested.append(full_id)
    if refs.get("bg"):
        requested.append(refs["bg"])

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
            ok = g.generate(prompt, sf_file, out, duration_s=dur)
            if ok and os.path.exists(out):
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
        BOARD.set_video(shot_id, out)
    JOBS[shot_id] = {"state": "done", "msg": "xong"}


def _generate(sf_id: str):
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
    for attempt in range(2):        # 1 lần mở lại phiên nếu tab (không phải cửa sổ) chết
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
                break
            raise RuntimeError("ChatGPT không trả về ảnh (thử lại hoặc kiểm tra tab ChatGPT)")
        except Exception as e:
            _drop_reserved(out); out = None
            if attempt == 0 and _is_dead_session_error(e) and _endpoint_alive(_TL.endpoint):
                _release_tl()
                if not in_batch:
                    JOBS[sf_id] = {"state": "running", "msg": "tab đã đóng → mở lại phiên…"}
                continue
            if _batch_tick(sf_id, ok=False):
                return              # lô tự tổng kết, không ném lỗi ra worker
            raise
    if not ok or not out or not os.path.exists(out):
        if _batch_tick(sf_id, ok=False):
            return
        raise RuntimeError("ChatGPT không trả về ảnh (thử lại hoặc kiểm tra tab ChatGPT)")
    with BOARD_LOCK:
        # trong một lô, chỉ bản XONG ĐẦU TIÊN được đặt làm ảnh đang dùng;
        # các bản sau chỉ nằm trong versions/ để bạn bấm chọn
        if not (in_batch and BOARD.find_file(sf_id)):
            BOARD.set_current(sf_id, out)
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
            self._json({"jobs": JOBS, "auto": _auto_status(),
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
            self._serve_img(BOARD.assets, u.path)
        elif u.path.startswith("/versions/"):
            self._serve_img(BOARD.versions, u.path)
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
            BOARD.write(json.loads(raw.decode("utf-8")))
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
            _enqueue("img", sf_id, int(q.get("n", ["1"])[0] or 1))
            self._json({"ok": True})
        elif u.path == "/api/pick-version":
            f = q.get("file", [""])[0]
            src = os.path.join(BOARD.versions, os.path.basename(f))
            if os.path.isfile(src):
                BOARD.set_current(sf_id, src)
                self._json({"ok": True})
            else:
                self._json({"ok": False, "err": "không thấy bản này"}, 404)
        elif u.path == "/api/delete-files":
            BOARD.delete_sf_files(sf_id)
            self._json({"ok": True})
        # ---------- accounts ----------
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
            if op == "toggle":
                with ACC_LOCK:
                    acc["enabled"] = not acc["enabled"]
                    now = acc["enabled"]
                _save_accounts()
                if now:
                    # Bật = mở lại Chrome (nếu chưa mở) + xóa dấu chết để chạy lại từ đầu
                    with _DEAD_LOCK:
                        DEAD.pop(_ep(acc), None)
                    if not _endpoint_alive(_ep(acc)):
                        _launch_chrome(acc)
                else:
                    # Tắt = đóng luôn cửa sổ Chrome; thợ tự nghỉ ở vòng lặp kế tiếp
                    _kill_chrome(acc["port"])
                self._json({"ok": True, "enabled": now})
            elif op == "launch":
                ok = _launch_chrome(acc)
                self._json({"ok": ok, "err": "" if ok else "không tìm thấy Google Chrome"})
            elif op == "revive":
                with _DEAD_LOCK:
                    DEAD.pop(_ep(acc), None)
                self._json({"ok": True})
            elif op == "del":
                # Xóa hẳn tài khoản: đóng Chrome, bỏ khỏi danh sách, XÓA LUÔN
                # thư mục profile (mất phiên đăng nhập, không hoàn tác được).
                _kill_chrome(acc["port"])
                time.sleep(1.5)          # đợi Chrome nhả file trước khi xóa thư mục
                with _DEAD_LOCK:
                    DEAD.pop(_ep(acc), None)
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
HTML = r"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SF Board</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root,:root[data-theme="dark"]{
--bg:#0f1115;--panel:#171a21;--panel2:#1e222b;--line:#2a2f3a;--linehi:#3a4152;--hover:#242936;
--deep:#0b0d11;--tx:#e6e9ef;--tx2:#98a1b3;--acc:#5b8cff;--ok:#2ecc71;--warn:#f0b429;--bad:#ef4444;
--okline:#1e5c3a;--warnline:#5c4a13;--badline:#5c1f1f;--tagbg:#1b2540;--tagtx:#9db4ee;
--tagbg2:#2a2140;--tagtx2:#c8a8ee;--hdr:rgba(15,17,21,.93);--overlay:rgba(11,13,17,.86);
--badgebg:rgba(0,0,0,.68);--shadow:none}
:root[data-theme="light"]{
--bg:#f4f6f9;--panel:#ffffff;--panel2:#eef1f6;--line:#dde2ea;--linehi:#b9c2d0;--hover:#e4e9f1;
--deep:#f7f9fc;--tx:#161a20;--tx2:#5f6b7d;--acc:#2f6bed;--ok:#129a55;--warn:#b8760a;--bad:#d92d20;
--okline:#8ad9ae;--warnline:#e6c07a;--badline:#f0a9a3;--tagbg:#e5edff;--tagtx:#2f5fd0;
--tagbg2:#f0e7ff;--tagtx2:#7b4fd0;--hdr:rgba(255,255,255,.93);--overlay:rgba(255,255,255,.88);
--badgebg:rgba(255,255,255,.85);--shadow:0 1px 2px rgba(16,24,40,.06)}
body{background:var(--bg);color:var(--tx);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
header{position:sticky;top:0;z-index:60;background:var(--hdr);backdrop-filter:blur(10px);
border-bottom:1px solid var(--line);padding:11px 18px;display:flex;align-items:center;gap:14px;flex-wrap:wrap}
h1{font-size:15px;font-weight:650}.film{color:var(--tx2);font-size:13px}
.stats{display:flex;gap:7px;margin-left:auto;flex-wrap:wrap}
.chip{padding:4px 10px;border-radius:999px;font-size:12px;font-weight:600;border:1px solid var(--line);background:var(--panel)}
.chip.ok{color:var(--ok);border-color:var(--okline)}.chip.warn{color:var(--warn);border-color:var(--warnline)}
.chip.bad{color:var(--bad);border-color:var(--badline)}.chip.pend{color:var(--tx2)}
button{font:inherit;cursor:pointer;border:1px solid var(--line);background:var(--panel2);color:var(--tx);
padding:6px 11px;border-radius:8px;transition:.12s}
button:hover{border-color:var(--linehi);background:var(--hover)}
button.pri{background:var(--acc);border-color:var(--acc);color:#fff}button.pri:hover{background:#4a7bee}
button.sm{padding:4px 9px;font-size:12px}button:disabled{opacity:.45;cursor:not-allowed}
.stale{font-size:11px;font-weight:600;color:#b45309;background:#fef3c7;border:1px solid #fcd34d;
  padding:2px 8px;border-radius:999px;white-space:nowrap}
a.sm.dl{display:inline-flex;align-items:center;padding:4px 9px;font-size:12px;text-decoration:none;
  border:1px solid var(--line,#d5d8de);border-radius:7px;background:var(--card,#fff);color:inherit;cursor:pointer}
a.sm.dl:hover{background:var(--acc,#2563eb);color:#fff;border-color:var(--acc,#2563eb)}
.save{font-size:12px;color:var(--tx2);min-width:82px}.save.on{color:var(--ok)}
main{padding:18px;max-width:1700px;margin:0 auto}
.scene{margin-bottom:30px}
.scene-h{display:flex;align-items:center;gap:11px;margin-bottom:13px;padding-bottom:9px;border-bottom:1px solid var(--line)}
.scene-h h2{font-size:15px;font-weight:650}
.sid{color:var(--acc);font-weight:700;font-size:12px;background:var(--tagbg);padding:3px 8px;border-radius:6px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:15px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden;display:flex;flex-direction:column;box-shadow:var(--shadow)}
.card.approved{border-color:var(--okline);box-shadow:inset 0 0 0 1px var(--okline)}
.card.rejected{opacity:.5;border-color:var(--badline)}.card.revise{border-color:var(--warnline)}
.thumb{position:relative;aspect-ratio:16/9;background:var(--deep);display:flex;align-items:center;justify-content:center;
cursor:pointer;border-bottom:1px solid var(--line)}
.thumb img{width:100%;height:100%;object-fit:cover}
.thumb.drop{outline:2px dashed var(--acc);outline-offset:-8px}
.empty{color:var(--tx2);font-size:12.5px;text-align:center;padding:16px;line-height:1.7}
.badge{position:absolute;top:8px;left:8px;font-size:11px;font-weight:700;padding:3px 8px;border-radius:6px;
background:var(--badgebg);backdrop-filter:blur(4px)}
.badge.ok{color:var(--ok)}.badge.warn{color:var(--warn)}.badge.bad{color:var(--bad)}.badge.pend{color:var(--tx2)}
.run{position:absolute;inset:0;background:var(--overlay);display:flex;flex-direction:column;gap:9px;
align-items:center;justify-content:center;font-size:12.5px;color:var(--tx2);text-align:center;padding:14px}
.spin{width:26px;height:26px;border:3px solid var(--line);border-top-color:var(--acc);border-radius:50%;animation:sp 1s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
.body{padding:11px;display:flex;flex-direction:column;gap:8px;flex:1}
.sfid{font-family:ui-monospace,Menlo,monospace;font-size:12px;color:var(--acc);font-weight:700}
input.ed,textarea.ed{width:100%;background:transparent;border:1px solid transparent;border-radius:7px;color:var(--tx);
padding:4px 6px;font:inherit}
input.ed{font-weight:600;font-size:13.5px}
textarea.ed{font-size:12.5px;color:var(--tx2);resize:vertical;min-height:36px;line-height:1.55}
input.ed:hover,textarea.ed:hover{border-color:var(--line)}
input.ed:focus,textarea.ed:focus{outline:none;border-color:var(--acc);background:var(--panel2)}
.vers{display:flex;gap:5px;overflow-x:auto;padding:2px 0}
.vers img{width:52px;height:30px;object-fit:cover;border-radius:5px;border:2px solid transparent;cursor:pointer;flex:none}
.vers img:hover{border-color:var(--acc)}
.vlab{font-size:10.5px;color:var(--tx2);align-self:center;flex:none;padding-right:3px}
.refrow{display:flex;gap:6px;align-items:flex-start;font-size:12px}
.refrow b{color:var(--tx2);font-weight:600;min-width:52px;padding-top:5px}
.picker{flex:1;display:flex;gap:4px;flex-wrap:wrap}
.pill{font-size:11px;background:var(--tagbg);color:var(--tagtx);padding:3px 7px;border-radius:5px;
font-family:ui-monospace,monospace;cursor:pointer;border:1px solid transparent}
.pill:hover{border-color:var(--bad);color:var(--bad)}
.pill.add{background:var(--panel2);color:var(--tx2);border:1px dashed var(--line)}
.pill.add:hover{border-color:var(--acc);color:var(--acc)}
.pill.bg{background:var(--tagbg2);color:var(--tagtx2)}
details{border:1px solid var(--line);border-radius:8px;background:var(--panel2)}
summary{cursor:pointer;padding:6px 9px;font-size:12px;color:var(--tx2);user-select:none}
summary:hover{color:var(--tx)}
details textarea{width:100%;background:var(--deep);border:none;border-top:1px solid var(--line);color:var(--tx);
padding:10px;font:12px/1.6 ui-monospace,Menlo,monospace;resize:vertical;min-height:190px}
details textarea:focus{outline:none}
.notes{background:var(--panel2);border:1px solid var(--line);border-radius:8px;color:var(--tx);
padding:7px;font:inherit;font-size:12.5px;resize:vertical;min-height:44px;width:100%}
.notes:focus{outline:none;border-color:var(--warn)}
.acts{display:flex;gap:5px;flex-wrap:wrap;padding:9px 11px;border-top:1px solid var(--line);background:var(--panel2)}
.ok-b:hover{border-color:var(--ok);color:var(--ok)}.warn-b:hover{border-color:var(--warn);color:var(--warn)}
.bad-b:hover{border-color:var(--bad);color:var(--bad)}
.err{color:var(--bad);font-size:11.5px;padding:0 11px 8px}
dialog{border:1px solid var(--line);background:var(--panel);color:var(--tx);border-radius:14px;padding:0;max-width:min(1300px,95vw)}
dialog::backdrop{background:rgba(0,0,0,.82)}dialog img{max-width:100%;max-height:84vh;display:block}
.dlg-h{padding:10px 14px;display:flex;gap:10px;align-items:center;border-bottom:1px solid var(--line)}
.toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:15px}
.hint{color:var(--tx2);font-size:12px}
select{font:inherit;background:var(--panel2);color:var(--tx);border:1px solid var(--line);border-radius:8px;padding:6px 9px}
.empty-all{text-align:center;color:var(--tx2);padding:60px 20px}
/* ---- chế độ Kịch bản ---- */
.tabs{display:flex;gap:4px;background:var(--panel2);border:1px solid var(--line);border-radius:9px;padding:3px}
.tabs button{border:none;background:transparent;padding:5px 13px;border-radius:6px;font-size:12.5px;color:var(--tx2)}
.tabs button.on{background:var(--acc);color:#fff;font-weight:600}
.shot{display:flex;gap:13px;background:var(--panel);border:1px solid var(--line);border-radius:11px;
padding:11px;margin-bottom:10px;box-shadow:var(--shadow)}
.shot.warn-sf{border-color:var(--badline)}
.sf-side{flex:none;width:200px;display:flex;flex-direction:column;gap:6px}
.sf-side .fr{aspect-ratio:16/9;background:var(--deep);border-radius:8px;overflow:hidden;border:1px solid var(--line);
display:flex;align-items:center;justify-content:center;cursor:pointer;position:relative}
.sf-side .fr img{width:100%;height:100%;object-fit:cover}
.sf-side .fr .no{color:var(--bad);font-size:11.5px;text-align:center;padding:8px;line-height:1.5}
.sf-side .pick{display:flex;gap:5px;align-items:center}
.sf-side select{flex:1;font-size:11.5px;padding:4px 6px;font-family:ui-monospace,monospace}
.sf-badge{position:absolute;bottom:5px;left:5px;font-size:10px;font-weight:700;padding:2px 6px;border-radius:5px;
background:var(--badgebg)}
.sh-main{flex:1;display:flex;flex-direction:column;gap:7px;min-width:0}
.sh-head{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.vid{font-family:ui-monospace,monospace;font-size:12px;font-weight:700;color:var(--acc)}
.dur{background:var(--panel2);border:1px solid var(--line);border-radius:6px;color:var(--tx);font-size:11.5px;padding:2px 6px}
.script{width:100%;background:var(--deep);border:1px solid var(--line);border-radius:8px;color:var(--tx);
padding:9px 11px;font:13px/1.75 ui-monospace,Menlo,monospace;resize:vertical;min-height:62px;white-space:pre-wrap}
.script:focus{outline:none;border-color:var(--acc)}
.sh-acts{display:flex;gap:5px;flex-wrap:wrap;align-items:center}
.scene-sum{color:var(--tx2);font-size:12px}
select.ncopy{padding:3px 4px;font-size:12px;border-radius:7px;border:1px solid var(--line,#d5d8de);
  background:var(--card,#fff);color:var(--tx2);cursor:pointer}
.sfdens{font-size:12px;padding:2px 9px;border-radius:999px;border:1px solid var(--line,#d5d8de);
  color:var(--tx2);background:var(--card,#fff);white-space:nowrap}
.sfdens.ok{color:#166534;background:#dcfce7;border-color:#86efac}
.sfdens.few{color:#b45309;background:#fef3c7;border-color:#fcd34d}
.sfdens.many{color:#9a3412;background:#ffedd5;border-color:#fdba74}
/* ---- đo lời thoại ---- */
.est{font-size:11px;font-weight:600;padding:2px 7px;border-radius:5px;font-family:ui-monospace,monospace;
white-space:nowrap;border:1px solid transparent}
.est.ok{color:var(--ok);border-color:var(--okline);background:transparent}
.est.over{color:var(--bad);border-color:var(--badline)}
.est.thin{color:var(--warn);border-color:var(--warnline)}
.est.empty{color:var(--tx2);border-color:var(--line)}
.shot-tools{display:flex;gap:4px}
details.scr{margin-bottom:11px;border:1px solid var(--line);border-radius:9px;background:var(--panel)}
details.scr summary{padding:8px 11px;font-size:12.5px;color:var(--tx2)}
details.scr pre{white-space:pre-wrap;word-break:break-word;margin:0;padding:12px 14px;
border-top:1px solid var(--line);font:12.5px/1.85 ui-monospace,Menlo,monospace;color:var(--tx);
max-height:420px;overflow:auto;background:var(--deep);border-radius:0 0 9px 9px}
/* ---- lớp video ---- */
.shot.vok{border-color:var(--okline)}
.v-side{flex:none;width:230px;display:flex;flex-direction:column;gap:6px}
.vbox{position:relative;aspect-ratio:16/9;background:var(--deep);border:1px solid var(--line);
border-radius:8px;overflow:hidden;display:flex;align-items:center;justify-content:center}
.vbox.drop{outline:2px dashed var(--acc);outline-offset:-6px}
.vbox video{width:100%;height:100%;object-fit:cover;display:block;background:#000}
.vempty{color:var(--tx2);font-size:11.5px;text-align:center;line-height:1.6;padding:10px}
.vempty span{font-size:10.5px;opacity:.75}
.vacts{display:flex;gap:4px;flex-wrap:wrap}
.v-side .vers{display:flex;gap:3px;flex-wrap:wrap}
/* ---- dán ảnh ---- */
.card.sel{outline:2px solid var(--acc);outline-offset:2px}
.pastebox{border:2px dashed var(--line);border-radius:12px;background:var(--panel);
display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;
min-height:190px;padding:16px;text-align:center;color:var(--tx2);font-size:12.5px;
cursor:pointer;transition:.15s}
.pastebox:hover,.pastebox.on{border-color:var(--acc);color:var(--acc);background:var(--panel2)}
.pastebox b{font-size:13px;color:var(--tx)}
.pastebox .big{font-size:26px;line-height:1}
/* ---- yêu cầu AI ---- */
button.ai{border-color:var(--acc);color:var(--acc)}
button.ai.on{background:var(--acc);color:#fff;border-color:var(--acc)}
.shot.vbad{border-left:3px solid var(--bad)}
.shot.vnew{border-left:3px solid var(--warn)}
#vfilter.act{background:var(--acc);color:#fff;border-color:var(--acc)}
#vbulk{background:var(--warn,#c77);color:#fff;border-color:var(--warn,#c77)}
button.auto-b.on{background:#1f6f3f;color:#fff;border-color:#2a8a50;animation:autopulse 2s ease-in-out infinite}
@keyframes autopulse{0%,100%{opacity:1}50%{opacity:.68}}
#runall.on{background:var(--bad);border-color:var(--bad);color:#fff}
.chip.ai{color:var(--acc);border-color:var(--acc);cursor:pointer}
.aidone{font-size:11.5px;color:var(--ok);padding:2px 0}
</style></head><body>

<header>
  <h1>SF Board</h1>
  <span class="kind" id="kind"></span>
  <span class="film" id="film"></span>
  <div class="tabs" id="tabs">
    <button data-v="script" class="on">Kịch bản</button>
    <button data-v="sf">Start frames</button>
  </div>
  <div class="stats" id="stats"></div>
  <select id="filter">
    <option value="all">Tất cả</option><option value="pending">Chờ duyệt</option>
    <option value="revise">Cần sửa</option><option value="approved">Đã duyệt</option>
    <option value="noimg">Chưa có ảnh</option>
  </select>
  <select id="vfilter" title="Lọc video theo trạng thái — chỉ hiện những dòng cần xử lý">
    <option value="all">Tất cả video</option>
    <option value="pending">⬜ Chưa duyệt</option>
    <option value="approved">✓ Đã duyệt</option>
    <option value="rejected">✕ Bị loại</option>
    <option value="novid">Chưa có video</option>
    <option value="multi">⧉ Nhiều bản — cần chọn</option>
    <option value="err">⚠ Lỗi khi tạo</option>
    <option value="gap">⏱ Trống thời lượng</option>
    <option value="stale">⚠ Prompt lệch thoại</option>
    <option value="nosf">Thiếu ảnh SF</option>
    <option value="beat">▶ Nhịp không thoại</option>
    <option value="talk">💬 Cảnh có thoại</option>
  </select>
  <button id="vbulk" style="display:none" title="Tạo lại toàn bộ video đang hiện sau bộ lọc"></button>
  <button id="theme" title="Sáng / Tối">🌙</button>
  <span class="save" id="save"></span>
</header>

<main>
  <div class="toolbar">
    <button class="pri" onclick="addScene()">+ Thêm scene</button>
    <button onclick="exportCapCut()" id="cc">🎬 Xuất CapCut</button>
    <button onclick="toggleRunAll()" id="runall">▶ Chạy tuần tự</button>
    <button onclick="toggleAccts()" id="acctbtn">⚙ Tài khoản</button>
    <span class="hint" id="hint"></span>
    <span class="hint" id="runstatus" style="color:var(--acc)"></span>
  </div>
  <div id="acctpanel" style="display:none;margin:8px 0;padding:10px 12px;border:1px solid var(--line,#ddd);border-radius:10px;background:var(--card,#fff)">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
      <b>Tài khoản Chrome</b>
      <button onclick="acctAdd('img')">+ ChatGPT</button>
      <button onclick="acctAdd('vid')">+ Grok</button>
      <span class="hint">Bật = mở Chrome + đưa vào vòng chạy · Tắt = đóng Chrome + ngừng dùng · login thì bạn tự làm trong cửa sổ</span>
    </div>
    <div id="acctrows" style="display:flex;flex-direction:column;gap:4px"></div>
  </div>
  <div id="root"></div>
</main>

<dialog id="lightbox"><div class="dlg-h"><b id="lb-t"></b><span style="flex:1"></span>
<button onclick="lightbox.close()">Đóng</button></div><img id="lb-i"></dialog>

<script>
let DATA={scenes:[]},JOBS={},AUTO={},T=null,VIEW='script',DIRTY=false,MTIME=0;
const $=s=>document.querySelector(s);
const esc=s=>(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const ST={proposed:['pend','Chờ duyệt'],approved:['ok','ĐÃ DUYỆT'],revise:['warn','Cần sửa'],rejected:['bad','Loại']};

async function loadProjects(){
  let d; try{ d = await (await fetch('/api/projects')).json(); }catch(e){ return; }
  const k=$('#kind'); k.textContent=d.kind==='hook'?'HOOK':'PHIM'; k.className='kind '+d.kind;
  document.title = (d.kind==='hook'?'[HOOK] ':'[PHIM] ') + 'SF Board :' + d.port;
  $('#film').title = 'Cổng '+d.port+' · Chrome: '+(d.cdp||[]).join(', ');
}

async function load(){
  DATA=await (await fetch('/api/board')).json();
  MTIME=DATA.mtime||0;DIRTY=false;
  $('#film').textContent='· '+(DATA.film||'');render();
}
async function poll(){
  const r=await (await fetch('/api/jobs')).json();
  const j=r.jobs||{};
  const a=r.auto||{};
  const changed=JSON.stringify(j)!==JSON.stringify(JOBS)||JSON.stringify(a)!==JSON.stringify(AUTO);
  AUTO=a;
  const wasRunning=Object.values(JOBS).some(x=>x.state==='running');
  JOBS=j;
  if(changed){
    const nowRunning=Object.values(j).some(x=>x.state==='running');
    if(wasRunning&&!nowRunning){await load();return}else{render()}
  }
  // file bị sửa từ bên ngoài (AI cập nhật prompt/kịch bản) → nạp lại
  if(r.mtime&&r.mtime!==MTIME&&!DIRTY){
    await load();
    $('#save').textContent='đã đồng bộ ↻';$('#save').className='save on';
    setTimeout(()=>$('#save').textContent='',2200);
  }
}
setInterval(poll,1500);

// ---------------------------------------------------------------- accounts
let ACCT_OPEN=false,ACCT_TIMER=null;
function toggleAccts(){
  ACCT_OPEN=!ACCT_OPEN;
  $('#acctpanel').style.display=ACCT_OPEN?'block':'none';
  $('#acctbtn').classList.toggle('on',ACCT_OPEN);
  if(ACCT_OPEN){pollAccts();ACCT_TIMER=setInterval(pollAccts,4000)}
  else if(ACCT_TIMER){clearInterval(ACCT_TIMER);ACCT_TIMER=null}
}
async function pollAccts(){
  try{
    const r=await (await fetch('/api/accounts')).json();
    const rows=(r.accounts||[]).map(a=>{
      const dot=a.chrome?'🟢':'🔴';
      const kind=a.kind==='img'?'ChatGPT · ảnh':'Grok · video';
      const st=!a.enabled?'<span style="color:#999">đang tắt</span>'
        :a.dead?`<span style="color:#c00">${esc(a.dead)}</span>`
        :a.worker?'<span style="color:var(--acc)">sẵn sàng</span>'
        :'<span style="color:#999">chờ thợ…</span>';
      return `<div style="display:flex;align-items:center;gap:8px;font-size:13px">
        <span>${dot}</span><b style="width:64px">${esc(a.id)}</b>
        <span style="width:96px">${kind}</span>
        <span style="width:76px">:${a.port}</span>
        <span style="flex:1">${st}</span>
        ${a.chrome?'':`<button onclick="acctOp('launch',${a.port})">Mở Chrome</button>`}
        ${a.dead?`<button onclick="acctOp('revive',${a.port})">Thử lại</button>`:''}
        <button onclick="acctOp('toggle',${a.port})">${a.enabled?'Tắt':'Bật'}</button>
        <button class="bad-b" title="Xóa hẳn tài khoản này khỏi danh sách (dữ liệu đăng nhập trong profile Chrome vẫn giữ)" onclick="acctDel('${esc(a.id)}',${a.port},${a.enabled})">🗑</button>
      </div>`});
    $('#acctrows').innerHTML=rows.join('')||'<span class="hint">chưa có tài khoản nào</span>';
  }catch(e){}
}
async function acctOp(op,port){
  await fetch(`/api/acct?op=${op}&port=${port}`,{method:'POST'});
  setTimeout(pollAccts,400);
}
async function acctDel(id,port,enabled){
  const busy = enabled ? `\n\n⚠ Tài khoản này ĐANG BẬT và có thể đang chạy việc dở.` : '';
  if(!confirm(
    `XÓA HẲN tài khoản ${id}?`+busy+
    `\n\nSẽ xóa LUÔN thư mục profile Chrome:`+
    `\n· mất phiên đăng nhập, lần sau phải đăng nhập lại`+
    `\n· KHÔNG hoàn tác được`
  ))return;
  const r=await (await fetch(`/api/acct?op=del&port=${port}`,{method:'POST'})).json();
  if(r.err) alert('Đã xóa tài khoản, nhưng không xóa được profile:\n'+r.err);
  else if(r.freed) $('#runstatus').textContent=`đã xóa ${id} · giải phóng ${r.freed}`;
  setTimeout(pollAccts,400);
  setTimeout(()=>$('#runstatus').textContent='',5000);
}
async function acctAdd(kind){
  await fetch(`/api/acct?op=add&kind=${kind}`,{method:'POST'});
  setTimeout(pollAccts,600);
}

function save(){
  DIRTY=true;clearTimeout(T);$('#save').textContent='đang lưu…';$('#save').className='save';
  T=setTimeout(async()=>{
    const r=await (await fetch('/api/board',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(DATA)})).json();
    if(r.mtime)MTIME=r.mtime;
    DIRTY=false;
    $('#save').textContent='đã lưu ✓';$('#save').className='save on';
    setTimeout(()=>$('#save').textContent='',1600);
  },450);
}
const allSF=()=>DATA.scenes.flatMap(s=>s.sfs.map(f=>({sc:s,f})));
const find=id=>allSF().find(x=>x.f.id===id);

function allShots(){return DATA.scenes.flatMap(s=>(s.shots||[]).map(x=>({sc:s,sh:x})))}

function stats(){
  if(VIEW==='sf'){
    const a=allSF().map(x=>x.f),c=k=>a.filter(f=>f.status===k).length;
    $('#stats').innerHTML=aiChip()+`<span class="chip ok">Duyệt ${c('approved')}</span>
     <span class="chip warn">Sửa ${c('revise')}</span><span class="chip pend">Chờ ${c('proposed')}</span>
     <span class="chip bad">Loại ${c('rejected')}</span><span class="chip">Tổng ${a.length}</span>`;
  }else{
    const sh=allShots().map(x=>x.sh);
    const has=sh.filter(s=>s.video).length;
    const ok=sh.filter(s=>s.vstatus==='approved').length;
    const secs=sh.filter(s=>s.vstatus==='approved').reduce((a,s)=>a+(s.dur||10),0);
    const st=sh.filter(stale).length;
    $('#stats').innerHTML=aiChip()+`<span class="chip ok">Video duyệt ${ok}</span>
     <span class="chip pend">Có video ${has}</span><span class="chip">Tổng shot ${sh.length}</span>
     <span class="chip">${Math.floor(secs/60)}:${String(secs%60).padStart(2,'0')} phim</span>
     ${st?`<span class="chip" style="background:#fef3c7;border-color:#fcd34d;color:#b45309;font-weight:600"
       title="Có ${st} video mà lời thoại đã sửa sau khi prompt được viết — bảo AI viết lại prompt cho khớp">⚠ ${st} prompt lệch thoại</span>`:''}`;
  }
}

function aiReqs(){
  const out=[];
  allSF().forEach(x=>{if(x.f.ai_request)out.push({kind:'SF',id:x.f.id,note:x.f.notes||''})});
  allShots().forEach(x=>{if(x.sh.ai_request)out.push({kind:'VIDEO',id:x.sh.id,note:x.sh.notes||''})});
  return out;
}
function aiChip(){
  const n=aiReqs().length;
  return n?`<span class="chip ai" onclick="showAI()">🤖 ${n} yêu cầu cho AI</span>`:'';
}
function showAI(){
  const r=aiReqs();
  const txt=r.map(x=>`${x.kind} ${x.id}: ${x.note||'(chưa ghi chú)'}`).join('\n');
  navigator.clipboard.writeText(txt);
  alert('Đã copy danh sách yêu cầu:\n\n'+txt+'\n\nDán vào chat, hoặc chỉ cần nhắn AI \"xử lý yêu cầu trên bảng\".');
}

let RUNALL={active:false,stop:false};

function allShotsOrdered(){
  return DATA.scenes.flatMap(sc=>(sc.shots||[]).map(sh=>({sc,sh})));
}

async function waitJob(id){
  while(true){
    const r=await (await fetch('/api/jobs')).json();
    const j=(r.jobs||r)[id];   // tương thích cả 2 dạng response cũ/mới
    if(!j||j.state!=='running')return j;
    await new Promise(res=>setTimeout(res,4000));
    if(RUNALL.stop)return j;
  }
}

async function toggleRunAll(){
  if(RUNALL.active){RUNALL.stop=true;$('#runstatus').textContent='đang dừng…';return}

  if(VIEW==='sf'){
    const all=allSF().filter(x=>x.f.prompt && !x.f.image);
    if(!all.length){alert('Không có ảnh SF/Ref nào cần chạy (tất cả đã có ảnh hoặc thiếu prompt).');return}
    if(!confirm(`Sẽ chạy tuần tự ${all.length} ảnh CHƯA có sẵn.\nCó thể bấm lại nút để DỪNG giữa chừng.\n\nBắt đầu?`))return;

    RUNALL={active:true,stop:false};
    $('#runall').textContent='■ Dừng';$('#runall').classList.add('on');

    let done=0,failed=[];
    for(const {f} of all){
      if(RUNALL.stop)break;
      $('#runstatus').textContent=`Đang tạo ảnh ${done+1}/${all.length}: ${f.id}…`;
      JOBS[f.id]={state:'running',msg:'khởi động…'};render();
      await fetch('/api/generate?sf='+encodeURIComponent(f.id),{method:'POST'});
      const j=await waitJob(f.id);
      if(RUNALL.stop)break;
      done++;
      if(j&&j.state==='error')failed.push(f.id+': '+j.msg);
      await load();
    }
    RUNALL.active=false;
    $('#runall').textContent='▶ Chạy tuần tự';$('#runall').classList.remove('on');
    $('#runstatus').textContent='';
    alert(`Xong. Đã tạo ${done}/${all.length} ảnh.`+(failed.length?`\n\nLỗi (${failed.length}):\n`+failed.join('\n'):''));
    return;
  }

  const all=allShotsOrdered().filter(x=>{
    const f=sfById(x.sh.sf);
    return f && f.image && (x.sh.prompt||'').trim() && !x.sh.video;
  });
  if(!all.length){alert('Không có video nào cần chạy (mọi dòng đã có video, hoặc thiếu SF/prompt).');return}
  if(!confirm(`Sẽ chạy tuần tự ${all.length} video CHƯA có sẵn (bỏ qua dòng đã có video).\nCó thể bấm lại nút để DỪNG giữa chừng.\n\nBắt đầu?`))return;

  RUNALL={active:true,stop:false};
  $('#runall').textContent='■ Dừng';$('#runall').classList.add('on');

  let done=0,failed=[];
  for(const {sh} of all){
    if(RUNALL.stop)break;
    $('#runstatus').textContent=`Đang chạy ${done+1}/${all.length}: ${sh.id}…`;
    JOBS[sh.id]={state:'running',msg:'khởi động…'};render();
    await fetch('/api/genvideo?sf='+encodeURIComponent(sh.id),{method:'POST'});
    const j=await waitJob(sh.id);
    if(RUNALL.stop)break;
    done++;
    if(j&&j.state==='error')failed.push(sh.id+': '+j.msg);
    await load();
  }

  RUNALL.active=false;
  $('#runall').textContent='▶ Chạy tuần tự';$('#runall').classList.remove('on');
  $('#runstatus').textContent='';
  alert(`Xong. Đã chạy ${done}/${all.length} video.`+(failed.length?`\n\nLỗi (${failed.length}):\n`+failed.join('\n'):''));
}

async function exportCapCut(){
  const b=$('#cc');b.disabled=true;b.textContent='đang xuất…';
  try{
    const r=await (await fetch('/api/export-capcut?approved=1',{method:'POST'})).json();
    if(r.ok){alert(`Đã tạo project CapCut!\n\n${r.count} video đã ghép theo thứ tự.\n`+
      (r.skipped.length?`Bỏ qua ${r.skipped.length} shot chưa có video/bị loại.\n`:'')+
      `\nMở CapCut → project mới nằm ở đầu danh sách.`);}
    else alert('Lỗi: '+r.err);
  }catch(e){alert('Lỗi: '+e)}
  b.disabled=false;b.textContent='🎬 Xuất CapCut';
}

function render(){
  stats();
  $('#filter').style.display = VIEW==='sf'?'':'none';
  $('#vfilter').style.display = VIEW==='script'?'':'none';
  $('#vfilter').className = $('#vfilter').value==='all'?'':'act';
  if(VIEW!=='script')$('#vbulk').style.display='none';
  $('#cc').style.display = VIEW==='script'?'':'none';
  $('#runall').style.display = '';
  $('#hint').innerHTML = VIEW==='script'
    ? 'Badge <b>≈Xs / Ys</b> = ước lượng thời lượng thoại so với độ dài video — <b style="color:var(--bad)">đỏ = thừa lời</b>, <b style="color:var(--warn)">cam = trống</b> · <b>＋ Thêm dưới</b> để chèn video rồi tự copy–paste thoại sang'
    : 'Kéo–thả hoặc <b>Ctrl+V</b> ảnh vào ô “Tạo SF mới” để dùng lại frame · bấm thẻ SF (Shift+bấm nếu đã có ảnh) rồi Ctrl+V để thay ảnh · <b>Tạo ảnh</b> để ChatGPT vẽ';
  if(VIEW==='script'){renderScript();return}
  const fl=$('#filter').value;
  const keep=f=>fl==='all'?1:fl==='noimg'?!f.image:fl==='pending'?f.status==='proposed':f.status===fl;
  const root=$('#root');root.innerHTML='';
  if(!DATA.scenes.length){root.innerHTML='<div class="empty-all">Chưa có scene. Bấm “+ Thêm scene”.</div>';return}
  DATA.scenes.forEach(sc=>{
    const list=sc.sfs.filter(keep);
    const el=document.createElement('section');el.className='scene';
    // tổng thời lượng scene + mật độ SF, để căn xem scene này cần bao nhiêu góc
    const shs=sc.shots||[];
    const secs=shs.reduce((a,s)=>a+(s.dur||10),0);
    const mm=`${Math.floor(secs/60)}:${String(secs%60).padStart(2,'0')}`;
    const nsf=sc.sfs.length;
    const per=nsf?Math.round(secs/nsf):0;
    const sug=secs?(secs<20?'2–3':secs<40?'3–5':secs<70?'5–7':secs<110?'7–9':'9–12'):'—';
    const okn=!secs||!nsf?'':(nsf<+String(sug).split('–')[0]?'few':(nsf>+String(sug).split('–')[1]?'many':'ok'));
    el.innerHTML=`<div class="scene-h"><span class="sid">${esc(sc.id)}</span><h2>${esc(sc.name)}</h2>
      <span style="flex:1"></span>
      ${secs?`<span class="scene-sum" title="Tổng thời lượng ${shs.length} shot của scene này">⏱ ${mm} · ${shs.length} shot</span>
      <span class="sfdens ${okn}" title="Trung bình ${per}s phim cho mỗi SF. Với ${mm} thì nên có khoảng ${sug} SF — ít quá thì góc bị lặp, nhiều quá thì thừa ảnh phải render.">${nsf} SF · gợi ý ${sug}</span>`
      :`<span class="hint">chưa chia shot</span>`}
      <span class="hint">${list.length}/${nsf} hiện</span>
      ${sc.id!=='REF'?autoBtn(sc):''}
      <button class="sm" onclick="addSF('${sc.id}')">+ SF</button>
      <button class="sm bad-b" onclick="delScene('${sc.id}')">Xóa scene</button></div><div class="grid"></div>`;
    const g=el.querySelector('.grid');
    g.appendChild(pasteBox(sc));
    list.forEach(f=>g.appendChild(card(sc,f)));
    root.appendChild(el);
  });
}

/* --- CHẠY TỰ ĐỘNG: bật cho scene rồi để đó, board tự tạo ảnh SF còn thiếu,
   ảnh xong tới đâu đẩy video tới đó, cái nào lỗi tự bắn lại, xong thì tự tắt --- */
async function toggleAuto(id){
  const r=await (await fetch('/api/auto?op=toggle&scene='+encodeURIComponent(id),
    {method:'POST'})).json();
  AUTO=r.auto||{};render();
}
function autoBtn(sc){
  const on=AUTO.hasOwnProperty(sc.id);
  const st=AUTO[sc.id]||{};
  const lab=on?(st.img&&st.vid?`⏳ ${st.img[0]}/${st.img[1]} ảnh · ${st.vid[0]}/${st.vid[1]} video`
                              :'⏳ đang quét…'):'▶ Chạy hết';
  const tip=on?'Đang tự chạy scene này. Bấm để dừng (việc đã xếp hàng vẫn chạy nốt).'
              :'Tự tạo mọi ảnh SF còn thiếu của scene, ảnh xong tới đâu đẩy video tới đó, '
              +'cái nào lỗi tự bắn lại. Xong cả scene thì tự tắt.';
  return `<button class="sm auto-b ${on?'on':''}" title="${tip}" `
        +`onclick="toggleAuto('${sc.id}')">${lab}</button>`;
}

/* ---------------- CHẾ ĐỘ KỊCH BẢN ---------------- */
function sfById(id){const x=find(id);return x?x.f:null}

function renderScript(){
  const root=$('#root');root.innerHTML='';
  const scenes=DATA.scenes.filter(s=>s.id!=='REF');
  if(!scenes.length){root.innerHTML='<div class="empty-all">Chưa có scene.</div>';return}
  const flt=$('#vfilter').value;
  let shown=0,hidden=0;
  scenes.forEach(sc=>{
    const all=sc.shots||[];
    const shots=all.filter(vkeep);
    shown+=shots.length; hidden+=all.length-shots.length;
    if(flt!=='all'&&!shots.length)return;          // scene không còn gì để xử lý → ẩn
    const secs=all.reduce((a,s)=>a+(s.dur||10),0);
    const done=all.filter(s=>{const f=sfById(s.sf);return f&&f.image}).length;
    const el=document.createElement('section');el.className='scene';
    el.innerHTML=`<div class="scene-h"><span class="sid">${esc(sc.id)}</span><h2>${esc(sc.name)}</h2>
      <span style="flex:1"></span>
      <span class="scene-sum">${all.length?`${done}/${all.length} video có SF · ${Math.floor(secs/60)}:${String(secs%60).padStart(2,'0')}`:'chưa chia shot'}</span>
      ${autoBtn(sc)}
      <button class="sm" onclick="addShot('${sc.id}')">+ video</button></div>
      ${sc.script?`<details class="scr" ${shots.length?'':'open'}><summary>📖 Kịch bản gốc</summary>
        <pre>${esc(sc.script)}</pre></details>`:''}
      <div class="shots"></div>`;
    const box=el.querySelector('.shots');
    shots.forEach(sh=>box.appendChild(shotRow(sc,sh,all.indexOf(sh))));
    root.appendChild(el);
  });
  vbulkBar(shown,hidden);
  if(flt!=='all'&&!shown)
    root.innerHTML='<div class="empty-all">Không có video nào ở trạng thái này ✓</div>';
}

/* Nút thao tác hàng loạt trên đúng nhóm đang lọc */
// Chỉ ba nhóm này thì "tạo lại" mới đúng là việc cần làm. "Trống thời lượng" và
// "prompt lệch thoại" phải sửa chia thoại / viết lại prompt TRƯỚC — render lại ngay
// chỉ dựng lại đúng cái sai cũ.
const VBULK_OK={novid:'chưa có video',err:'lỗi khi tạo',rejected:'bị loại'};
function vbulkBar(shown,hidden){
  const b=$('#vbulk'), fl=$('#vfilter').value;
  // chỉ cho tạo lại hàng loạt ở những nhóm thật sự cần render lại —
  // "chưa duyệt"/"đã duyệt"/"nhiều bản" là nhóm để XEM, bấm nhầm thì rất tốn
  if(!VBULK_OK[fl]||!shown){b.style.display='none';return}
  b.style.display='';
  b.textContent=`↻ Tạo lại ${shown} video đang hiện`;
  b.onclick=async()=>{
    if(!confirm(`Tạo lại ${shown} video thuộc nhóm “${VBULK_OK[fl]}”?\n\n`
      +`Bản cũ vẫn giữ lại thành version để so sánh.`))return;
    const list=allShots().map(x=>x.sh).filter(vkeep);
    for(const sh of list) await fetch('/api/genvideo?sf='+encodeURIComponent(sh.id),{method:'POST'});
    $('#runstatus').textContent=`đã xếp ${list.length} video vào hàng đợi`;
    setTimeout(()=>$('#runstatus').textContent='',4000);
  };
}

// ~3.0 từ/giây — đo theo tốc độ đọc thực tế của giọng AI (điều chỉnh sau thực nghiệm)
function estimate(text){
  const clean=(text||'').replace(/^[A-ZĐÂÊÔƠƯ][A-ZĐÂÊÔƠƯ\s.]*:/gm,' ')  // bỏ nhãn tên
                        .replace(/\([^)]*\)/g,' ')                       // bỏ chú thích trong ngoặc
                        .replace(/[—–-]{1,2}\s*[a-z, ]+:/g,' ');          // bỏ chỉ dẫn giọng
  const words=clean.trim().split(/\s+/).filter(w=>/[a-zA-ZÀ-ỹ']/.test(w));
  return {n:words.length, sec:words.length/3.0};
}
// Thoại đã bị sửa sau khi prompt video được viết → prompt đang mô tả bản thoại cũ.
// prompt_text là ảnh chụp lời thoại tại lúc AI viết prompt; shot chưa có mốc thì bỏ qua.
/* Nhóm trạng thái của một video, dùng cho bộ lọc ở chế độ Kịch bản */
function vcat(sh){
  const f=sfById(sh.sf);
  const {sec}=estimate(sh.text);
  return {
    novid:!sh.video,
    approved:sh.vstatus==='approved',
    rejected:sh.vstatus==='rejected',
    pending:sh.vstatus!=='approved'&&sh.vstatus!=='rejected',
    multi:(sh.vversions||[]).length>1,
    err:(JOBS[sh.id]||{}).state==='error',
    gap:((sh.dur||10)-sec)>3.2,
    stale:stale(sh),
    nosf:!f||!f.image,
    beat:/-B\d+$/.test(sh.id),          // nhịp không thoại: id kết thúc bằng -B<số>
    talk:!/-B\d+$/.test(sh.id),
  };
}
function vkeep(sh){
  const fl=$('#vfilter').value;
  return fl==='all'?true:!!vcat(sh)[fl];
}

/* Bản thu nhỏ cho lưới — ảnh gốc chỉ nạp khi phóng to (lightbox) hoặc tải về */
function thumb(u,w){ return u ? u + (u.includes('?')?'&':'?') + 'w=' + (w||420) : u }

function stale(sh){
  if(!sh.prompt||!sh.prompt.trim())return false;
  if(sh.prompt_text===undefined||sh.prompt_text===null)return false;
  return (sh.prompt_text||'').trim()!==(sh.text||'').trim();
}
function estBadge(sh){
  const {n,sec}=estimate(sh.text);
  const dur=sh.dur||10;
  if(!n)return `<span class="est empty" title="Chưa có lời thoại">— / ${dur}s</span>`;
  let cls='ok',tip=`${n} từ · vừa khít ${dur}s`;
  if(sec>dur){cls='over';tip=`${n} từ ≈ ${sec.toFixed(1)}s — THỪA LỜI so với ${dur}s. Hãy tách bớt sang video khác hoặc đổi lên 10s.`}
  else if(sec<dur*0.35){cls='thin';tip=`${n} từ ≈ ${sec.toFixed(1)}s — hơi trống so với ${dur}s. Có thể gộp với dòng kế hoặc hạ xuống 6s.`}
  return `<span class="est ${cls}" title="${tip}">≈${sec.toFixed(1)}s / ${dur}s</span>`;
}
function newVidId(){
  let mx=0;
  DATA.scenes.forEach(s=>(s.shots||[]).forEach(x=>{
    const m=/(\d+)/.exec(x.id); if(m) mx=Math.max(mx,+m[1]);
  }));
  return 'VID_'+String(mx+1).padStart(3,'0');
}

function shotRow(sc,sh,idx){
  const f=sfById(sh.sf);
  const opts=allSF().map(x=>x.f).filter(x=>!x.id.startsWith('REF_'));
  const vjob=JOBS[sh.id]||{};const vrun=vjob.state==='running';
  const d=document.createElement('div');
  d.className='shot'+(!f||!f.image?' warn-sf':'')
    +(sh.vstatus==='approved'?' vok':sh.vstatus==='rejected'?' vbad':sh.video?' vnew':'');
  const st=f?(ST[f.status]||ST.proposed):null;
  d.innerHTML=`
    <div class="sf-side">
      <div class="fr">${f&&f.image?`<img src="${thumb(f.image,320)}" loading="lazy" decoding="async">
          <span class="sf-badge ${st[0]}">${st[1]}</span>`
        :`<div class="no">${f?'SF chưa có ảnh':'chưa gán SF'}</div>`}</div>
      <div class="pick">
        <select data-sf>${opts.map(o=>`<option value="${o.id}" ${o.id===sh.sf?'selected':''}>${o.id}</option>`).join('')}</select>
      </div>
      ${f?`<div class="hint" style="font-size:11px">${esc(f.label||'')}</div>`:''}
    </div>
    <div class="sh-main">
      <div class="sh-head">
        <span class="vid">${esc(sh.id)}</span>
        <select class="dur" data-dur>
          <option value="6" ${sh.dur==6?'selected':''}>6s</option>
          <option value="10" ${sh.dur==10?'selected':''}>10s</option>
        </select>
        ${estBadge(sh)}
        ${stale(sh)?`<span class="stale" title="Bạn đã sửa lời thoại sau khi prompt video được viết. Prompt hiện tại mô tả bản thoại cũ — bảo AI viết lại prompt cho khớp, rồi bấm ✓ đã khớp.">⚠ thoại đã đổi — prompt video chưa viết lại</span>
        <button class="sm" data-sync title="Đánh dấu prompt đã khớp với thoại hiện tại">✓ đã khớp</button>`:''}
        <span style="flex:1"></span>
        <button class="sm" data-ins title="Thêm một video trống ngay dưới dòng này">＋ Thêm dưới</button>
        <button class="sm" data-mv="-1">↑</button><button class="sm" data-mv="1">↓</button>
        <button class="sm bad-b" data-del title="Xóa video này khỏi kịch bản">🗑</button>
      </div>
      <textarea class="script" data-k="text" spellcheck="false" placeholder="Lời thoại / hành động trong kịch bản…">${esc(sh.text||'')}</textarea>
      <details><summary>Prompt video (sửa được)</summary>
        <textarea data-k="prompt" spellcheck="false" placeholder="Prompt gửi Grok…">${esc(sh.prompt||'')}</textarea></details>
    </div>
    <div class="v-side">
      <div class="vbox">
        ${sh.video?`<video src="${sh.video}" controls preload="none"></video>`
          :`<div class="vempty">chưa có video<br><span>kéo–thả .mp4 vào đây<br>hoặc bấm Tạo video</span></div>`}
        ${vrun?`<div class="run"><div class="spin"></div><div>${esc(vjob.msg||'')}</div></div>`:''}
        ${sh.vstatus==='approved'?'<span class="badge ok">DUYỆT</span>':sh.vstatus==='rejected'?'<span class="badge bad">LOẠI</span>':''}
      </div>
      ${(sh.vversions&&sh.vversions.length>1)?`<div class="vers">${sh.vversions.map((v,i)=>
        `<button class="sm" data-vv="${v.file}" title="${v.at}">v${i+1}</button>`).join('')}</div>`:''}
      <div class="vacts">
        <button class="sm pri" data-va="gen" ${vrun?'disabled':''}>${sh.video?'Tạo lại':'Tạo video'}</button>
        <button class="sm ok-b" data-va="approved">✓</button>
        <button class="sm bad-b" data-va="rejected">✕</button>
        <button class="sm ai ${sh.ai_request?'on':''}" data-va="ai" title="Nhờ AI viết lại prompt / sửa lời thoại">🤖</button>
        ${sh.video?`<button class="sm" data-va="frame" title="Tua video tới khung ưng ý rồi bấm — lưu khung đó thành SF mới (tự chọn dòng dùng sau)">📸→SF</button>`:''}
        ${sh.video?`<button class="sm" data-va="framedown" title="Tua video tới khung cuối rồi bấm — cắt khung đó thành SF và GÁN LUÔN cho video ngay bên dưới, để hai clip nối liền không bị khựng">📸↓</button>`:''}
        ${sh.video?`<a class="sm dl" href="${sh.video}?dl=1&name=${encodeURIComponent(sh.id)}" download="${sh.id}.mp4" title="Tải video về máy">⬇</a>`:''}
        ${sh.video?'<button class="sm bad-b" data-va="delv">🗑</button>':''}
      </div>
      ${vjob.state==='error'?`<div class="err" style="padding:0">⚠ ${esc(vjob.msg)}</div>`:''}
      ${sh.ai_done?`<div class="aidone">🤖 ${esc(sh.ai_done)}</div>`:''}
    </div>`;
  d.querySelector('.fr').onclick=()=>{if(f&&f.image){$('#lb-t').textContent=f.id+' — '+(f.label||'');
    $('#lb-i').src=f.image;lightbox.showModal()}};
  const vbox=d.querySelector('.vbox');
  vbox.ondragover=e=>{e.preventDefault();vbox.classList.add('drop')};
  vbox.ondragleave=()=>vbox.classList.remove('drop');
  vbox.ondrop=async e=>{e.preventDefault();vbox.classList.remove('drop');
    const file=e.dataTransfer.files[0];if(!file)return;
    await fetch('/api/upload-video?sf='+encodeURIComponent(sh.id),{method:'POST',body:file});
    await load();};
  d.querySelectorAll('[data-vv]').forEach(el=>el.onclick=async()=>{
    await fetch(`/api/pick-vversion?sf=${encodeURIComponent(sh.id)}&file=${encodeURIComponent(el.dataset.vv)}`,{method:'POST'});
    await load();});
  d.querySelectorAll('[data-va]').forEach(b=>b.onclick=async()=>{
    const a=b.dataset.va;
    if(a==='gen'){JOBS[sh.id]={state:'running',msg:'khởi động…'};render();
      await fetch('/api/genvideo?sf='+encodeURIComponent(sh.id),{method:'POST'});return}
    if(a==='ai'){sh.ai_request=!sh.ai_request;save();render();return}
    if(a==='frame'){await frameToSF(sc,sh,d);return}
    if(a==='framedown'){await frameToNextShot(sc,sh,idx,d);return}
    if(a==='delv'){if(!confirm('Xóa video '+sh.id+' (cả lịch sử)?'))return;
      await fetch('/api/delete-video?sf='+encodeURIComponent(sh.id),{method:'POST'});await load();return}
    sh.vstatus=a;save();render();});
  d.querySelector('[data-sf]').onchange=e=>{sh.sf=e.target.value;save();render()};
  d.querySelector('[data-dur]').onchange=e=>{sh.dur=+e.target.value;save();render()};
  d.querySelectorAll('[data-k]').forEach(el=>el.oninput=e=>{
    sh[e.target.dataset.k]=e.target.value;save();
    if(e.target.dataset.k==='text'){
      const badge=d.querySelector('.sh-head .est');
      if(badge)badge.outerHTML=estBadge(sh);
    }
  });
  d.querySelectorAll('[data-mv]').forEach(b=>b.onclick=()=>{
    const j=idx+(+b.dataset.mv);if(j<0||j>=sc.shots.length)return;
    [sc.shots[idx],sc.shots[j]]=[sc.shots[j],sc.shots[idx]];save();render()});
  d.querySelector('[data-del]').onclick=()=>{
    if(!confirm('Xóa '+sh.id+'?'))return;
    sc.shots.splice(idx,1);save();render()};

  d.querySelector('[data-ins]').onclick=()=>{
    sc.shots.splice(idx+1,0,{id:newVidId(),sf:sh.sf,dur:10,text:'',
      prompt:'',status:'todo',notes:''});
    save();render();
  };
  const syncb=d.querySelector('[data-sync]');
  if(syncb)syncb.onclick=()=>{sh.prompt_text=sh.text||'';save();render()};
  return d;
}

// Cắt khung hiện tại của video này thành SF rồi GÁN LUÔN cho shot ngay bên dưới —
// dùng khi muốn hai clip nối liền: frame cuối clip trước = frame đầu clip sau.
async function frameToNextShot(sc,sh,idx,rowEl){
  const next=sc.shots[idx+1];
  if(!next){alert('Đây là video cuối của scene, không có dòng nào bên dưới để gán.');return}
  const v=rowEl.querySelector('.vbox video');
  if(!v){alert('Chưa có video');return}
  const t=v.currentTime;
  if(!t||t<0.05){
    alert('Hãy TUA video tới đúng khung hình muốn lấy (thường là khung CUỐI), bấm tạm dừng, rồi mới bấm 📸↓.\n\nHiện con trỏ đang ở giây '+t.toFixed(2));
    return;
  }
  const used=new Set(sc.sfs.map(f=>f.id));
  let suggest='';
  for(let i=0;i<26;i++){
    const c=String.fromCharCode(65+i);
    const cand=`SF-${sc.id}-${c}`;
    if(!used.has(cand)){suggest=cand;break}
  }
  const old=next.sf||'(chưa có)';
  if(!confirm(`Cắt khung tại giây ${t.toFixed(2)} của ${sh.id}\n→ tạo SF "${suggest}"\n→ GÁN cho ${next.id} (đang dùng ${old}).\n\nTiếp tục?`))return;
  const r=await (await fetch(`/api/frame-to-sf?shot=${encodeURIComponent(sh.id)}&t=${t}&sf=${encodeURIComponent(suggest)}`,
    {method:'POST'})).json();
  if(!r.ok){alert('Lỗi: '+r.err);return}
  await load();
  // gán cho shot dưới sau khi board đã nạp lại (next là tham chiếu cũ nên tìm lại theo id)
  const sc2=DATA.scenes.find(s=>s.id===sc.id);
  const n2=sc2&&sc2.shots.find(x=>x.id===next.id);
  if(n2){n2.sf=r.sf;save();render();}
  alert(`Đã tạo ${r.sf} và gán cho ${next.id}.\n\nNhớ bảo AI viết lại prompt video của ${next.id} cho khớp khung mới.`);
}

async function frameToSF(sc,sh,rowEl){
  const v=rowEl.querySelector('.vbox video');
  if(!v){alert('Chưa có video');return}
  const t=v.currentTime;
  if(!t||t<0.05){
    alert('Hãy TUA video tới đúng khung hình bạn muốn giữ (bấm play rồi tạm dừng), sau đó mới bấm 📸→SF.\n\nHiện con trỏ đang ở giây '+t.toFixed(2));
    return;
  }
  // gợi ý mã SF kế tiếp trong scene
  const used=new Set(sc.sfs.map(f=>f.id));
  let suggest='';
  for(let i=0;i<26;i++){
    const c=String.fromCharCode(65+i);
    const cand=`SF-${sc.id}-${c}`;
    if(!used.has(cand)){suggest=cand;break}
  }
  const id=prompt(`Lưu khung hình tại giây ${t.toFixed(2)} của ${sh.id} thành SF mới.\n\nNhập mã SF (để trống = huỷ):`,suggest);
  if(!id)return;
  const r=await (await fetch(`/api/frame-to-sf?shot=${encodeURIComponent(sh.id)}&t=${t}&sf=${encodeURIComponent(id.trim())}`,
    {method:'POST'})).json();
  if(r.ok){await load();alert('Đã tạo '+r.sf+' từ khung hình này.\nXem ở tab "Start frames", và nó đã có trong dropdown chọn SF của mọi dòng.');}
  else alert('Lỗi: '+r.err);
}

function addShot(sid){
  const sc=DATA.scenes.find(s=>s.id===sid);
  const n=sc.shots.length+1;
  const id=prompt('Mã video:','VID_'+String(n).padStart(3,'0'));
  if(!id)return;
  sc.shots.push({id:id.trim(),sf:(sc.sfs[0]||{}).id||'',dur:10,text:'',prompt:'',status:'todo',notes:''});
  save();render();
}

/* ---------------- DÁN ẢNH ---------------- */
let SEL=null;   // SF đang được chọn để Ctrl+V đè ảnh

function nextSFId(sc){
  const used=new Set(sc.sfs.map(f=>f.id));
  for(let i=0;i<26;i++){
    const c=`SF-${sc.id}-${String.fromCharCode(65+i)}`;
    if(!used.has(c))return c;
  }
  return `SF-${sc.id}-${Date.now()%1000}`;
}

async function uploadTo(sfId,blob,name){
  await fetch(`/api/upload?sf=${encodeURIComponent(sfId)}&name=${encodeURIComponent(name||'paste.png')}`,
    {method:'POST',body:blob});
}

async function createSFfromBlob(sc,blob,name){
  const id=prompt('Tạo SF mới từ ảnh này.\n\nNhập mã SF:',nextSFId(sc));
  if(!id)return;
  const key=id.trim();
  if(find(key)){alert('Mã '+key+' đã tồn tại. Chọn mã khác.');return}
  sc.sfs.push({id:key,label:'(ảnh dán vào)',desc:'Frame lấy lại / ảnh dán từ ngoài.',
    prompt:'',status:'proposed',notes:'',usedBy:[],refs:{chars:[],bg:null}});
  await fetch('/api/board',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(DATA)});
  await uploadTo(key,blob,name);
  await load();
  alert('Đã tạo '+key+'.\nSang tab "Kịch bản" là chọn được nó trong dropdown SF của mọi dòng video.');
}

function pasteBox(sc){
  const d=document.createElement('div');
  d.className='pastebox';
  d.innerHTML=`<div class="big">＋</div><b>Tạo SF mới từ ảnh</b>
    <div>Bấm vào đây rồi <b>Ctrl+V</b> để dán ảnh trong clipboard<br>hoặc kéo–thả file ảnh vào ô này</div>`;
  d.onclick=()=>{SEL={scene:sc,sf:null};document.querySelectorAll('.pastebox').forEach(x=>x.classList.remove('on'));
    d.classList.add('on');document.querySelectorAll('.card').forEach(c=>c.classList.remove('sel'));};
  d.ondragover=e=>{e.preventDefault();d.classList.add('on')};
  d.ondragleave=()=>d.classList.remove('on');
  d.ondrop=async e=>{e.preventDefault();d.classList.remove('on');
    const f=e.dataTransfer.files[0];if(f)await createSFfromBlob(sc,f,f.name);};
  return d;
}

// Ctrl+V toàn trang
window.addEventListener('paste',async e=>{
  if(VIEW!=='sf')return;
  const items=[...(e.clipboardData?.items||[])].filter(i=>i.type.startsWith('image/'));
  if(!items.length)return;
  e.preventDefault();
  const blob=items[0].getAsFile();
  if(!SEL){alert('Hãy bấm chọn một thẻ SF (để thay ảnh) hoặc ô "Tạo SF mới từ ảnh" trước, rồi Ctrl+V.');return}
  if(SEL.sf){await uploadTo(SEL.sf,blob,'paste.png');await load();}
  else if(SEL.scene){await createSFfromBlob(SEL.scene,blob,'paste.png');}
});

/* ---------------- CHẾ ĐỘ START FRAME ---------------- */
function card(sc,f){
  const [cls,txt]=ST[f.status]||ST.proposed;
  const job=JOBS[f.id]||{};const running=job.state==='running';
  const refs=f.refs||{chars:[],bg:null};
  const d=document.createElement('div');
  d.className='card '+(f.status==='approved'?'approved':f.status==='rejected'?'rejected':f.status==='revise'?'revise':'');
  d.innerHTML=`
   <div class="thumb" data-sf="${f.id}">
     ${f.image?`<img src="${thumb(f.image,320)}" loading="lazy" decoding="async">`:`<div class="empty">Chưa có ảnh<br><b>Kéo–thả ảnh vào đây</b><br>hoặc bấm <b>Tạo ảnh</b></div>`}
     <span class="badge ${cls}">${txt}</span>
     ${running?`<div class="run"><div class="spin"></div><div>${esc(job.msg||'đang tạo…')}</div></div>`:''}
   </div>
   <div class="body">
     <div class="sfid">${esc(f.id)}</div>
     <input class="ed" data-k="label" value="${esc(f.label||'')}" placeholder="Tên góc máy…">
     <textarea class="ed" data-k="desc" placeholder="Mô tả / dùng cho beat nào…">${esc(f.desc||'')}</textarea>
     <div class="refrow"><b>Nhân vật</b><div class="picker" data-p="chars">
       ${(refs.chars||[]).map(r=>`<span class="pill" data-rm="${esc(r)}">${esc(r)} ✕</span>`).join('')}
       <span class="pill add" data-add="chars">+ thêm</span></div></div>
     <div class="refrow"><b>Bối cảnh</b><div class="picker" data-p="bg">
       ${refs.bg?`<span class="pill bg" data-rmbg="1">${esc(refs.bg)} ✕</span>`:`<span class="pill add" data-add="bg">+ chọn</span>`}
       </div></div>
     ${(f.versions&&f.versions.length>1)?`<div class="vers"><span class="vlab">bản:</span>
       ${f.versions.map((v,i)=>`<img src="${thumb(v.url,240)}" loading="lazy" decoding="async" title="v${i+1} · ${v.at}" data-v="${v.file}">`).join('')}</div>`:''}
     <details><summary>Prompt (sửa được)</summary>
       <textarea data-k="prompt" spellcheck="false">${esc(f.prompt||'')}</textarea></details>
     <textarea class="notes" data-k="notes" placeholder="Ghi chú / yêu cầu chỉnh sửa…">${esc(f.notes||'')}</textarea>
     ${f.ai_done?`<div class="aidone">🤖 ${esc(f.ai_done)}</div>`:''}
   </div>
   ${job.state==='error'?`<div class="err">⚠ ${esc(job.msg)}</div>`:''}
   <div class="acts">
     <button class="sm pri" data-a="gen" ${running?'disabled':''}>${f.image?'Tạo lại':'Tạo ảnh'}</button>
     <select class="ncopy" data-n title="Số bản tạo cùng lúc — mỗi bản chạy trên một tài khoản khác nhau, xong rồi bấm v1/v2… để chọn bản ưng ý" ${running?'disabled':''}>
       <option value="1">×1</option><option value="2">×2</option>
       <option value="3">×3</option><option value="4">×4</option></select>
     <button class="sm ok-b" data-a="approved">✓</button>
     <button class="sm warn-b" data-a="revise">✎</button>
     <button class="sm bad-b" data-a="rejected">✕</button>
     <span style="flex:1"></span>
     ${f.image?`<a class="sm dl" href="${f.image}?dl=1&name=${encodeURIComponent(f.id)}" download="${f.id}.png" title="Tải ảnh về máy">⬇</a>`:''}
     <button class="sm ai ${f.ai_request?'on':''}" data-a="ai" title="Đánh dấu nhờ AI xử lý (ghi rõ ở ô ghi chú)">🤖</button>
     <button class="sm" data-a="dup">Nhân bản</button>
     <button class="sm" data-a="copy">Copy →</button>
     <button class="sm bad-b" data-a="del">🗑</button>
   </div>`;

  const th=d.querySelector('.thumb');
  th.onclick=e=>{
    if(e.shiftKey||!f.image){   // chọn thẻ để dán đè (hoặc thẻ chưa có ảnh)
      SEL={scene:sc,sf:f.id};
      document.querySelectorAll('.card').forEach(c=>c.classList.remove('sel'));
      document.querySelectorAll('.pastebox').forEach(x=>x.classList.remove('on'));
      d.classList.add('sel');
      return;
    }
    $('#lb-t').textContent=f.id+' — '+(f.label||'');$('#lb-i').src=f.image;lightbox.showModal();
  };
  th.ondragover=e=>{e.preventDefault();th.classList.add('drop')};
  th.ondragleave=()=>th.classList.remove('drop');
  th.ondrop=async e=>{e.preventDefault();th.classList.remove('drop');
    const file=e.dataTransfer.files[0];if(!file)return;
    await fetch(`/api/upload?sf=${encodeURIComponent(f.id)}&name=${encodeURIComponent(file.name)}`,{method:'POST',body:file});
    await load();};

  d.querySelectorAll('[data-k]').forEach(el=>el.oninput=e=>{f[e.target.dataset.k]=e.target.value;save()});
  d.querySelectorAll('[data-v]').forEach(el=>el.onclick=async e=>{
    e.stopPropagation();
    await fetch(`/api/pick-version?sf=${encodeURIComponent(f.id)}&file=${encodeURIComponent(el.dataset.v)}`,{method:'POST'});
    await load();});
  d.querySelectorAll('[data-rm]').forEach(el=>el.onclick=()=>{
    f.refs.chars=f.refs.chars.filter(x=>x!==el.dataset.rm);save();render()});
  const rmbg=d.querySelector('[data-rmbg]');
  if(rmbg)rmbg.onclick=()=>{f.refs.bg=null;save();render()};
  d.querySelectorAll('[data-add]').forEach(el=>el.onclick=()=>addRef(f,el.dataset.add));
  d.querySelectorAll('[data-a]').forEach(b=>b.onclick=()=>{
    const sel=d.querySelector('[data-n]');
    act(sc,f,b.dataset.a, sel?sel.value:1);
  });
  return d;
}

function addRef(f,kind){
  const opts=allSF().map(x=>x.f.id);
  const pick=prompt(`Chọn ảnh ${kind==='bg'?'BỐI CẢNH':'NHÂN VẬT'} — nhập mã:\n\n`+opts.join('\n'));
  if(!pick)return;const id=pick.trim();
  if(!opts.includes(id)){alert('Không có mã '+id);return}
  f.refs=f.refs||{chars:[],bg:null};
  if(kind==='bg')f.refs.bg=id;
  else if(!f.refs.chars.includes(id))f.refs.chars.push(id);
  save();render();
}

async function act(sc,f,a,n){
  if(a==='gen'){
    n=Math.max(1,Math.min(+n||1,4));
    JOBS[f.id]={state:'running',msg:n>1?`đang tạo 0/${n} bản…`:'khởi động…'};render();
    await fetch(`/api/generate?sf=${encodeURIComponent(f.id)}&n=${n}`,{method:'POST'});return}
  if(a==='del'){
    if(!confirm('Xóa '+f.id+' (kèm mọi ảnh & phiên bản)?'))return;
    await fetch('/api/delete-files?sf='+encodeURIComponent(f.id),{method:'POST'});
    sc.sfs=sc.sfs.filter(x=>x.id!==f.id);save();render();return}
  if(a==='ai'){f.ai_request=!f.ai_request;save();render();return}
  if(a==='dup'){
    let nid=f.id+'-B',k=2;while(find(nid)){nid=f.id+'-B'+k;k++}
    sc.sfs.splice(sc.sfs.indexOf(f)+1,0,{...f,id:nid,status:'proposed',notes:'',image:null,versions:[]});
    save();render();return}
  if(a==='copy'){
    const t=prompt('Copy sang scene nào?\n\n'+DATA.scenes.map(s=>s.id+' — '+s.name).join('\n'),sc.id);
    if(!t)return;const dst=DATA.scenes.find(s=>s.id===t.trim());
    if(!dst){alert('Không có scene '+t);return}
    let nid=f.id+'-COPY',k=2;while(find(nid)){nid=f.id+'-COPY'+k;k++}
    dst.sfs.push({...f,id:nid,status:'proposed',notes:'',usedBy:[],image:null,versions:[]});
    save();render();return}
  f.status=a;save();render();
}

function addSF(sid){
  const sc=DATA.scenes.find(s=>s.id===sid);
  const id=prompt('Mã SF mới:','SF-'+sid+'-'+String.fromCharCode(65+sc.sfs.length));
  if(!id)return;if(find(id.trim())){alert('Mã đã tồn tại');return}
  sc.sfs.push({id:id.trim(),label:'',desc:'',prompt:'',status:'proposed',notes:'',usedBy:[],refs:{chars:[],bg:null}});
  save();render();
}
function addScene(){
  const id=prompt('Mã scene:','S'+(DATA.scenes.length+1));if(!id)return;
  DATA.scenes.push({id:id.trim(),name:prompt('Tên scene:','')||'',sfs:[]});save();render();
}
function delScene(sid){
  if(!confirm('Xóa scene '+sid+' và toàn bộ SF?'))return;
  DATA.scenes=DATA.scenes.filter(s=>s.id!==sid);save();render();
}
/* ---- sáng / tối ---- */
function setTheme(t){
  document.documentElement.dataset.theme=t;
  localStorage.setItem('sfboard-theme',t);
  $('#theme').textContent = t==='dark'?'🌙':'☀️';
}
setTheme(localStorage.getItem('sfboard-theme') ||
  (window.matchMedia('(prefers-color-scheme: light)').matches?'light':'dark'));
$('#theme').onclick=()=>setTheme(document.documentElement.dataset.theme==='dark'?'light':'dark');

$('#filter').onchange=render;
$('#vfilter').onchange=render;
document.querySelectorAll('#tabs button').forEach(b=>b.onclick=()=>{
  VIEW=b.dataset.v;
  document.querySelectorAll('#tabs button').forEach(x=>x.classList.toggle('on',x===b));
  render();
});
loadProjects();
load();
</script></body></html>
"""



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
    print(f"Tài khoản: {ACC_PATH}  (quản lý bật/tắt/mở Chrome ngay trên board — nút ⚙ Tài khoản)")
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
    threading.Thread(target=_idle_sleeper, daemon=True).start()
    try:
        webbrowser.open(url)
    except Exception:
        pass
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
