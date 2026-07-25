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
                out.append({"file": name, "url": f"/versions/{name}?t={int(os.path.getmtime(p))}",
                            "at": time.strftime("%d/%m %H:%M", time.localtime(os.path.getmtime(p)))})
        out.sort(key=lambda x: int(x["file"].rsplit("_v", 1)[1].split(".")[0]))
        return out

    def next_version_path(self, sf_id: str) -> str:
        n = len(self._versions(sf_id)) + 1
        while os.path.exists(os.path.join(self.versions, f"{sf_id}_v{n}.png")):
            n += 1
        return os.path.join(self.versions, f"{sf_id}_v{n}.png")

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
CDP_ENDPOINT = CDP

# ---------------------------------------------------------------- generation
JOBS: dict[str, dict] = {}          # id -> {"state": running|done|error, "msg": str}
QUEUE: "queue.Queue[tuple]" = queue.Queue()   # mọi việc Playwright chạy trong MỘT luồng thợ
_SESSION = None
_SESS_LOCK = threading.Lock()
_LOG = logging.getLogger("sfboard")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")


def _worker():
    """Luồng thợ duy nhất — Playwright yêu cầu phiên sống trong cùng một luồng."""
    while True:
        kind, ident = QUEUE.get()
        try:
            if kind == "img":
                _generate(ident)
            else:
                _gen_video(ident)
        except Exception as e:
            JOBS[ident] = {"state": "error", "msg": str(e)[:300]}
        finally:
            QUEUE.task_done()


def _enqueue(kind: str, ident: str):
    n = QUEUE.qsize()
    JOBS[ident] = {"state": "running",
                   "msg": "khởi động…" if n == 0 else f"đang xếp hàng ({n} việc trước)"}
    QUEUE.put((kind, ident))


def _alive(sess) -> bool:
    """Phiên còn sống thật không, hay chỉ còn cờ ready từ trước khi tab bị đóng."""
    try:
        return sess is not None and getattr(sess, "ready", False) and sess.page is not None \
               and not sess.page.is_closed()
    except Exception:
        return False


# Một Playwright/CDP DÙNG CHUNG cho cả ChatGPT lẫn Grok trong cùng luồng thợ —
# hai sync_playwright().start() độc lập trong cùng 1 luồng sẽ xung đột ngầm
# (bài học từ grokpipe/runner.py — GrokSession.start() fail âm thầm nếu chạy
# sau một ChatGPTSession đã tự mở playwright riêng).
_HUB_PW = None
_HUB_CTX = None


def _hub():
    global _HUB_PW, _HUB_CTX
    if _HUB_CTX is not None:
        try:
            _HUB_CTX.pages  # chạm vào để biết context còn sống
            return _HUB_CTX
        except Exception:
            _HUB_PW = None
            _HUB_CTX = None
    from playwright.sync_api import sync_playwright
    _HUB_PW = sync_playwright().start()
    browser = _HUB_PW.chromium.connect_over_cdp(CDP_ENDPOINT)
    _HUB_CTX = browser.contexts[0] if browser.contexts else browser.new_context()
    return _HUB_CTX


def _session():
    """Tạo/tái dùng một phiên ChatGPT qua CDP — tự mở lại nếu phiên cũ đã chết."""
    global _SESSION
    if _alive(_SESSION):
        return _SESSION
    _SESSION = None
    from grokpipe.executors.image_chatgpt import ChatGPTSession
    s = ChatGPTSession(user_data_dir=os.path.expanduser("~/.grokpipe-chrome"),
                       logger=_LOG, headless=False, cdp_endpoint=None, shared_ctx=_hub())
    if not s.start():
        raise RuntimeError("Không nối được ChatGPT. Mở Chrome debug rồi thử lại: "
                           "python3 grokpipe/grokpipe/../-m grokpipe chrome")
    _SESSION = s
    return s


_GSESSION = None
_GLOCK = threading.Lock()


def _grok():
    global _GSESSION
    if _alive(_GSESSION):
        return _GSESSION
    _GSESSION = None
    from grokpipe.executors.video_grok import GrokSession
    s = GrokSession(cdp_endpoint=None, logger=_LOG, resolution="720p", shared_ctx=_hub())
    if not s.start():
        raise RuntimeError("Không nối được Grok. Mở Chrome debug và đăng nhập grok.com rồi thử lại.")
    _GSESSION = s
    return s


def _gen_video(shot_id: str):
    try:
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
        JOBS[shot_id] = {"state": "running", "msg": f"Grok đang dựng {int(dur)}s…"}
        with _GLOCK:
            g = _grok()
            out = BOARD.next_vversion(shot_id)
            ok = g.generate(prompt, sf_file, out, duration_s=dur)
        if not ok or not os.path.exists(out):
            raise RuntimeError("Grok không trả về video")
        BOARD.set_video(shot_id, out)
        JOBS[shot_id] = {"state": "done", "msg": "xong"}
    except Exception as e:
        JOBS[shot_id] = {"state": "error", "msg": str(e)[:300]}


def _generate(sf_id: str):
    try:
        sf = BOARD.get_sf(sf_id)
        if not sf:
            raise RuntimeError("Không tìm thấy SF")
        prompt = (sf.get("prompt") or "").strip()
        if not prompt:
            raise RuntimeError("SF chưa có prompt")

        refs = sf.get("refs") or {}
        ids = list(refs.get("chars") or [])
        if refs.get("bg"):
            ids.append(refs["bg"])
        attach, missing = [], []
        for rid in ids:
            p = BOARD.find_file(rid)
            (attach.append(p) if p else missing.append(rid))
        if missing:
            raise RuntimeError("Thiếu ảnh tham chiếu: " + ", ".join(missing))

        JOBS[sf_id] = {"state": "running", "msg": f"đang tạo… ({len(attach)} ảnh ref)"}
        with _SESS_LOCK:
            sess = _session()
            out = BOARD.next_version_path(sf_id)
            ok = sess.generate(prompt, attach, out)
        if not ok or not os.path.exists(out):
            raise RuntimeError("ChatGPT không trả về ảnh (thử lại hoặc kiểm tra tab ChatGPT)")
        BOARD.set_current(sf_id, out)
        JOBS[sf_id] = {"state": "done", "msg": "xong"}
    except Exception as e:
        JOBS[sf_id] = {"state": "error", "msg": str(e)[:300]}


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

    def _serve_img(self, folder, name):
        p = os.path.join(folder, unquote(os.path.basename(name)))
        if not os.path.isfile(p):
            self._send(404, b"not found", "text/plain")
            return
        with open(p, "rb") as f:
            self._send(200, f.read(), IMAGE_EXT.get(os.path.splitext(p)[1].lower(), "application/octet-stream"))

    def _serve_video(self, folder, name):
        """Phát video có hỗ trợ Range để tua được."""
        p = os.path.join(folder, unquote(os.path.basename(name)))
        if not os.path.isfile(p):
            self._send(404, b"not found", "text/plain")
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
            self._json({"jobs": JOBS, "mtime": int(os.path.getmtime(BOARD.path))})
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
        elif u.path == "/api/generate":
            if JOBS.get(sf_id, {}).get("state") == "running":
                self._json({"ok": False, "err": "đang chạy"}); return
            _enqueue("img", sf_id)
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
#runall.on{background:var(--bad);border-color:var(--bad);color:#fff}
.chip.ai{color:var(--acc);border-color:var(--acc);cursor:pointer}
.aidone{font-size:11.5px;color:var(--ok);padding:2px 0}
</style></head><body>

<header>
  <h1>SF Board</h1><span class="film" id="film"></span>
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
  <button id="theme" title="Sáng / Tối">🌙</button>
  <span class="save" id="save"></span>
</header>

<main>
  <div class="toolbar">
    <button class="pri" onclick="addScene()">+ Thêm scene</button>
    <button onclick="exportCapCut()" id="cc">🎬 Xuất CapCut</button>
    <button onclick="toggleRunAll()" id="runall">▶ Chạy tuần tự</button>
    <span class="hint" id="hint"></span>
    <span class="hint" id="runstatus" style="color:var(--acc)"></span>
  </div>
  <div id="root"></div>
</main>

<dialog id="lightbox"><div class="dlg-h"><b id="lb-t"></b><span style="flex:1"></span>
<button onclick="lightbox.close()">Đóng</button></div><img id="lb-i"></dialog>

<script>
let DATA={scenes:[]},JOBS={},T=null,VIEW='script',DIRTY=false,MTIME=0;
const $=s=>document.querySelector(s);
const esc=s=>(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const ST={proposed:['pend','Chờ duyệt'],approved:['ok','ĐÃ DUYỆT'],revise:['warn','Cần sửa'],rejected:['bad','Loại']};

async function load(){
  DATA=await (await fetch('/api/board')).json();
  MTIME=DATA.mtime||0;DIRTY=false;
  $('#film').textContent='· '+(DATA.film||'');render();
}
async function poll(){
  const r=await (await fetch('/api/jobs')).json();
  const j=r.jobs||{};
  const changed=JSON.stringify(j)!==JSON.stringify(JOBS);
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
    $('#stats').innerHTML=aiChip()+`<span class="chip ok">Video duyệt ${ok}</span>
     <span class="chip pend">Có video ${has}</span><span class="chip">Tổng shot ${sh.length}</span>
     <span class="chip">${Math.floor(secs/60)}:${String(secs%60).padStart(2,'0')} phim</span>`;
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
  $('#cc').style.display = VIEW==='script'?'':'none';
  $('#runall').style.display = VIEW==='script'?'':'none';
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
    el.innerHTML=`<div class="scene-h"><span class="sid">${esc(sc.id)}</span><h2>${esc(sc.name)}</h2>
      <span style="flex:1"></span><span class="hint">${list.length}/${sc.sfs.length} SF</span>
      <button class="sm" onclick="addSF('${sc.id}')">+ SF</button>
      <button class="sm bad-b" onclick="delScene('${sc.id}')">Xóa scene</button></div><div class="grid"></div>`;
    const g=el.querySelector('.grid');
    g.appendChild(pasteBox(sc));
    list.forEach(f=>g.appendChild(card(sc,f)));
    root.appendChild(el);
  });
}

/* ---------------- CHẾ ĐỘ KỊCH BẢN ---------------- */
function sfById(id){const x=find(id);return x?x.f:null}

function renderScript(){
  const root=$('#root');root.innerHTML='';
  const scenes=DATA.scenes.filter(s=>s.id!=='REF');
  if(!scenes.length){root.innerHTML='<div class="empty-all">Chưa có scene.</div>';return}
  scenes.forEach(sc=>{
    const shots=sc.shots||[];
    const secs=shots.reduce((a,s)=>a+(s.dur||10),0);
    const done=shots.filter(s=>{const f=sfById(s.sf);return f&&f.image}).length;
    const el=document.createElement('section');el.className='scene';
    el.innerHTML=`<div class="scene-h"><span class="sid">${esc(sc.id)}</span><h2>${esc(sc.name)}</h2>
      <span style="flex:1"></span>
      <span class="scene-sum">${shots.length?`${done}/${shots.length} video có SF · ${Math.floor(secs/60)}:${String(secs%60).padStart(2,'0')}`:'chưa chia shot'}</span>
      <button class="sm" onclick="addShot('${sc.id}')">+ video</button></div>
      ${sc.script?`<details class="scr" ${shots.length?'':'open'}><summary>📖 Kịch bản gốc</summary>
        <pre>${esc(sc.script)}</pre></details>`:''}
      <div class="shots"></div>`;
    const box=el.querySelector('.shots');
    shots.forEach((sh,i)=>box.appendChild(shotRow(sc,sh,i)));
    root.appendChild(el);
  });
}

// ~3.0 từ/giây — đo theo tốc độ đọc thực tế của giọng AI (điều chỉnh sau thực nghiệm)
function estimate(text){
  const clean=(text||'').replace(/^[A-ZĐÂÊÔƠƯ][A-ZĐÂÊÔƠƯ\s.]*:/gm,' ')  // bỏ nhãn tên
                        .replace(/\([^)]*\)/g,' ')                       // bỏ chú thích trong ngoặc
                        .replace(/[—–-]{1,2}\s*[a-z, ]+:/g,' ');          // bỏ chỉ dẫn giọng
  const words=clean.trim().split(/\s+/).filter(w=>/[a-zA-ZÀ-ỹ']/.test(w));
  return {n:words.length, sec:words.length/3.0};
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
  d.className='shot'+(!f||!f.image?' warn-sf':'')+(sh.vstatus==='approved'?' vok':'');
  const st=f?(ST[f.status]||ST.proposed):null;
  d.innerHTML=`
    <div class="sf-side">
      <div class="fr">${f&&f.image?`<img src="${f.image}">
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
        ${sh.video?`<video src="${sh.video}" controls preload="metadata"></video>`
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
        ${sh.video?`<button class="sm" data-va="frame" title="Tua video tới khung ưng ý rồi bấm — lưu khung đó thành SF mới">📸→SF</button>`:''}
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
  return d;
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
     ${f.image?`<img src="${f.image}">`:`<div class="empty">Chưa có ảnh<br><b>Kéo–thả ảnh vào đây</b><br>hoặc bấm <b>Tạo ảnh</b></div>`}
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
       ${f.versions.map((v,i)=>`<img src="${v.url}" title="v${i+1} · ${v.at}" data-v="${v.file}">`).join('')}</div>`:''}
     <details><summary>Prompt (sửa được)</summary>
       <textarea data-k="prompt" spellcheck="false">${esc(f.prompt||'')}</textarea></details>
     <textarea class="notes" data-k="notes" placeholder="Ghi chú / yêu cầu chỉnh sửa…">${esc(f.notes||'')}</textarea>
     ${f.ai_done?`<div class="aidone">🤖 ${esc(f.ai_done)}</div>`:''}
   </div>
   ${job.state==='error'?`<div class="err">⚠ ${esc(job.msg)}</div>`:''}
   <div class="acts">
     <button class="sm pri" data-a="gen" ${running?'disabled':''}>${f.image?'Tạo lại':'Tạo ảnh'}</button>
     <button class="sm ok-b" data-a="approved">✓</button>
     <button class="sm warn-b" data-a="revise">✎</button>
     <button class="sm bad-b" data-a="rejected">✕</button>
     <span style="flex:1"></span>
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
  d.querySelectorAll('[data-a]').forEach(b=>b.onclick=()=>act(sc,f,b.dataset.a));
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

async function act(sc,f,a){
  if(a==='gen'){
    JOBS[f.id]={state:'running',msg:'khởi động…'};render();
    await fetch('/api/generate?sf='+encodeURIComponent(f.id),{method:'POST'});return}
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
document.querySelectorAll('#tabs button').forEach(b=>b.onclick=()=>{
  VIEW=b.dataset.v;
  document.querySelectorAll('#tabs button').forEach(x=>x.classList.toggle('on',x===b));
  render();
});
load();
</script></body></html>
"""


def main():
    global BOARD, CDP_ENDPOINT
    args = [a for a in sys.argv[1:]]
    if not args:
        print('Cách dùng: python3 sfboard.py "/duong/dan/THU-MUC-PHIM" [--cdp URL] [--port N]')
        sys.exit(2)
    film = args[0]
    port = PORT
    if "--cdp" in args:
        CDP_ENDPOINT = args[args.index("--cdp") + 1]
    if "--port" in args:
        port = int(args[args.index("--port") + 1])
    BOARD = Board(film)
    url = f"http://localhost:{port}"
    print(f"SF Board v2  →  {url}")
    print(f"Phim    : {BOARD.dir}")
    print(f"Dữ liệu : {BOARD.path}")
    print(f"ChatGPT : {CDP_ENDPOINT}  (cần Chrome debug đang mở & đã đăng nhập)")
    threading.Thread(target=_worker, daemon=True).start()
    try:
        webbrowser.open(url)
    except Exception:
        pass
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
