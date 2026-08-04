"""Executor VIDEO — Grok Imagine (image-to-video).

Hai chế độ:
  • AUTO: điều khiển grok.com/imagine qua CDP (Chrome thật, phiên đã đăng nhập):
    upload ảnh start-frame → chọn Video + 720p + 10s → dán prompt → Submit →
    chờ render → tải mp4 qua request API (kèm cookie).
  • MANUAL (fallback): tool in prompt + đường dẫn ảnh, chờ bạn tự chạy trên
    grok.com rồi thả video vào inbox/.

Ghi chú kỹ thuật (dò từ UI thật 2026-07):
  - Chip "Video"/"720p"/"10s" click bằng JS theo text (locator click hay trượt).
  - Video sinh ra là <video src="https://assets.grok.com/.../generated_video.mp4">.
    KHÔNG fetch trong page (khác origin → CORS/lỗi query); dùng ctx.request.get.
  - Trước khi Submit phải chụp danh sách src video CŨ trên trang — chỉ nhận src MỚI
    (tránh vớ nhầm video của lần chạy trước).
"""
from __future__ import annotations

import os
import threading
import time

from ..models import Task
from ..state import Store
from . import common as C

try:
    from playwright.sync_api import sync_playwright  # type: ignore
    _HAS_PW = True
except Exception:  # pragma: no cover
    _HAS_PW = False


# ĐÁNH DẤU TAB BẰNG window.name, KHÔNG dùng id() của đối tượng page.
# Mỗi luồng thợ mở một kết nối CDP RIÊNG, nên cùng một tab thật là hai đối tượng
# Python khác nhau ở hai luồng — id() không bao giờ khớp, mọi cách giữ chỗ dựa
# trên id() đều vô dụng. window.name nằm trong chính trang web nên đọc được từ
# mọi kết nối, và sống qua các lần điều hướng cùng origin.
_TAG = "gpslot"


class GrokSession:
    """Phiên grok.com/imagine qua CDP, giữ xuyên suốt pipeline."""

    URL = "https://grok.com/imagine"

    def __init__(self, cdp_endpoint: str | None, logger, gen_timeout: float = 600.0,
                 resolution: str = "720p", shared_ctx=None, slot: int = 0):
        self.cdp_endpoint = cdp_endpoint
        self.logger = logger
        self.gen_timeout = gen_timeout
        self.resolution = resolution
        self.shared_ctx = shared_ctx        # context CDP dùng chung (do runner tạo)
        self.slot = int(slot)               # chỗ ngồi: mỗi thợ một tab riêng
        self._pw = None
        self._browser = None
        self._ctx = None
        self.page = None
        self.ready = False

    # ------------------------------------------------------------------
    def start(self) -> bool:
        if not _HAS_PW and self.shared_ctx is None:
            self.logger.warning("Playwright chưa cài — Grok chạy thủ công.")
            return False
        try:
            if self.shared_ctx is not None:
                # dùng chung 1 Playwright/CDP với executor ảnh (tránh lỗi sync-in-asyncio)
                self._ctx = self.shared_ctx
            else:
                self._pw = sync_playwright().start()
                self._browser = self._pw.chromium.connect_over_cdp(self.cdp_endpoint)
                self._ctx = self._browser.contexts[0] if self._browser.contexts \
                    else self._browser.new_context()
            # MỖI PHIÊN GIỮ RIÊNG MỘT TAB. Nhiều thợ có thể chạy song song trên
            # CÙNG một cửa sổ Chrome (xem "số tab" trong mục Tài khoản của board),
            # nên tuyệt đối không được vớ lấy tab mà luồng khác đang dùng — hai
            # luồng chung một tab thì cái này submit đè lên cái kia và cả hai hỏng.
            self.page = self._tim_tab()
            self.page.goto(self.URL, wait_until="domcontentloaded")
            time.sleep(4)
            if not self._ensure_ready():
                return False
            self._dismiss_popups()
            self.ready = True
            self.logger.info("Grok session sẵn sàng.")
            return True
        except Exception as e:
            self.logger.warning(f"Không nối được Grok qua CDP ({e}) — chạy thủ công.")
            self.close()
            return False

    def _tim_tab(self):
        """Tab riêng của luồng này, nhận ra qua window.name = 'gpslot<N>'."""
        tag = f"{_TAG}{self.slot}"

        def ten(pg):
            try:
                return pg.evaluate("window.name") or ""
            except Exception:
                return ""

        if self.page is not None and not self.page.is_closed() and ten(self.page) == tag:
            return self.page
        mo = [pg for pg in self._ctx.pages if not pg.is_closed()]
        for pg in mo:
            if "grok.com" in (pg.url or "") and ten(pg) == tag:
                return pg
        # Slot 0 nhận nuôi một tab grok CHƯA ai đánh dấu — để dùng lại tab user đang
        # mở sẵn, khỏi đẻ tab thừa. Slot khác LUÔN mở tab mới của riêng nó.
        if self.slot == 0:
            for pg in mo:
                if "grok.com" in (pg.url or "") and not ten(pg).startswith(_TAG):
                    pg.evaluate("n => { window.name = n }", tag)
                    return pg
        pg = self._ctx.new_page()
        pg.goto(self.URL, wait_until="domcontentloaded")
        pg.evaluate("n => { window.name = n }", tag)
        return pg

    def _ensure_ready(self) -> bool:
        """Trang imagine có ô nhập ('Ask Grok anything'). Cloudflare/chưa login → nhờ người."""
        for _ in range(3):
            try:
                title = (self.page.title() or "").lower()
                if "just a moment" in title:
                    raise RuntimeError("cloudflare")
                self.page.wait_for_selector("[contenteditable='true']", timeout=12000)
                return True
            except Exception:
                print("\n  >>> Trong cửa sổ Chrome: hãy tự qua 'Verify you are human'"
                      " (nếu có) và ĐĂNG NHẬP Grok, mở trang grok.com/imagine.")
                print("      (Tôi không tự làm bước xác minh người thật / đăng nhập.)")
                try:
                    C.ask("      Xong thì Enter để tiếp tục")
                except C.UserQuit:
                    return False
                try:
                    self.page.goto(self.URL, wait_until="domcontentloaded")
                    time.sleep(3)
                except Exception:
                    pass
        return False

    def _dismiss_popups(self) -> None:
        """Đóng cookie banner (chọn phương án ít theo dõi nhất) + popup giới thiệu."""
        for lab in ("Reject All", "Close preference center"):
            try:
                btn = self.page.get_by_role("button", name=lab)
                if btn.count():
                    btn.first.click(timeout=2000)
                    time.sleep(0.5)
            except Exception:
                pass
        try:
            btn = self.page.get_by_role("button", name="Close")
            if btn.count():
                btn.first.click(timeout=1500)
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _jclick(self, label: str) -> bool:
        """Click button theo text CHÍNH XÁC bằng JS (dùng cho nút có text)."""
        r = self.page.evaluate(
            """(lab) => {
              const cands=[...document.querySelectorAll('button')].filter(b=>{
                const t=(b.textContent||'').trim();
                return b.getBoundingClientRect().width>0 && t===lab;});
              if(!cands.length) return false;
              cands[0].click(); return true;
            }""", label)
        return bool(r)

    def _click_radio(self, name: str) -> bool:
        """Click nút role=radio theo aria-label HOẶC text (mode Video/Image là icon
        chỉ có aria-label; 480p/720p/6s/10s có text)."""
        r = self.page.evaluate(
            """(name) => {
              const els=[...document.querySelectorAll('[role=radio],button')].filter(e=>{
                if (e.getBoundingClientRect().width===0) return false;
                const a=(e.getAttribute('aria-label')||'').trim();
                const t=(e.textContent||'').trim();
                return a===name || t===name;});
              if(!els.length) return false;
              els[0].click(); return true;
            }""", name)
        return bool(r)

    def _out_of_credits(self) -> bool:
        try:
            return self.page.evaluate(
                """() => [...document.querySelectorAll('[aria-label]')]
                     .some(e => /100% credits used/i.test(e.getAttribute('aria-label')||''))""")
        except Exception:
            return False

    def _video_srcs(self) -> list[str]:
        return self.page.evaluate(
            """() => [...document.querySelectorAll('video')]
                 .map(v => v.currentSrc || v.src || '')
                 .filter(s => s.startsWith('http'))""")

    # ------------------------------------------------------------------
    def generate(self, prompt: str, image_path: str, out_path: str,
                 duration_s: float = 10.0) -> bool:
        """Tạo 1 video image-to-video, lưu mp4 ra out_path."""
        page = self.page
        # về trang imagine sạch
        page.goto(self.URL, wait_until="domcontentloaded")
        time.sleep(4)
        self._dismiss_popups()

        # upload ảnh
        page.locator("input[type=file]").first.set_input_files(image_path)
        time.sleep(4)

        # cảnh báo hết credit -> fail nhanh, không chờ 10 phút vô ích
        if self._out_of_credits():
            raise C.ExecutorError("Grok đã dùng 100% credit — không tạo được video.")

        # mode Video: là icon role=radio aria-label='Video' (KHÔNG có text)
        if not self._click_radio("Video"):
            raise C.ExecutorError("Không thấy nút mode 'Video' trên Grok Imagine.")
        time.sleep(1)
        # xác nhận đã sang mode video: phải thấy chip thời lượng '10s'/'6s'
        dur_label = "10s" if duration_s >= 8 else "6s"
        self._click_radio(self.resolution)     # 720p (role=radio, có text)
        time.sleep(0.4)
        if not self._click_radio(dur_label):
            raise C.ExecutorError(f"Không thấy chip thời lượng '{dur_label}' "
                                  f"(mode Video chưa bật đúng?).")
        time.sleep(0.4)

        # chụp src video CŨ trước khi submit — chỉ nhận src MỚI
        before = set(self._video_srcs())

        # prompt + submit
        ed = page.locator("[contenteditable='true']").last
        ed.click()
        page.keyboard.insert_text(prompt)
        time.sleep(0.5)
        page.get_by_role("button", name="Submit").first.click(timeout=5000)
        self.logger.info("Grok: đã submit, chờ render...")

        # chờ render
        deadline = time.time() + self.gen_timeout
        vid_src = None
        while time.time() < deadline:
            time.sleep(5)
            try:
                infos = page.evaluate(
                    """() => [...document.querySelectorAll('video')]
                         .map(v => ({src: v.currentSrc || v.src || '',
                                     dur: v.duration || 0}))
                         .filter(v => v.src.startsWith('http'))""")
                new = [v for v in infos
                       if v["src"] not in before and v["dur"] and v["dur"] >= 3]
                if new:
                    vid_src = new[-1]["src"]
                    break
            except Exception:
                pass
        if not vid_src:
            raise C.ExecutorError("Hết thời gian chờ Grok render video.")
        self.logger.info(f"Grok: video xong ({vid_src[:70]}...), đang tải")

        # Tải qua request API (kèm cookie, không dính CORS). CDN của Grok hay chậm
        # hoặc ngắt giữa chừng nên phải cho timeout rộng và thử lại vài lần —
        # video đã render xong rồi, hỏng ở bước tải mà bỏ luôn thì rất phí.
        data = None
        last_err = None
        for attempt in range(1, 5):
            try:
                resp = self._ctx.request.get(vid_src, timeout=180_000)
                if not resp.ok:
                    raise C.ExecutorError(f"Tải video lỗi HTTP {resp.status}.")
                body = resp.body()
                if len(body) < 100_000:
                    raise C.ExecutorError(f"Video tải về quá nhỏ ({len(body)} bytes).")
                data = body
                break
            except Exception as e:
                last_err = e
                self.logger.warning(
                    "Grok: tải video hỏng (lần %d/4): %s", attempt, str(e)[:120])
                if attempt < 4:
                    time.sleep(3 * attempt)
        if data is None:
            raise C.ExecutorError(
                f"Tải video thất bại sau 4 lần thử: {str(last_err)[:200]}")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(data)
        return True

    def close(self) -> None:
        with _CLAIM_LOCK:
            pass
        if self.shared_ctx is not None:   # context dùng chung do runner quản lý
            self.ready = False
            return
        try:
            if self._browser:
                self._browser.close()   # chỉ ngắt CDP, Chrome vẫn chạy
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self.ready = False


# ----------------------------------------------------------------------------
def run_video(task: Task, store: Store, start_frame_path: str, logger,
              session: GrokSession | None = None,
              duration_tol: float = 2.5) -> str:
    """Tạo video cho task. AUTO nếu có session, không thì cổng thủ công.
    Trả path try trong tries/."""
    if session is not None and session.ready:
        try:
            try_path, _ = store.next_try_path(task.output_id, ".mp4")
            logger.info(f"{task.id} [AUTO] Grok tạo video từ "
                        f"{os.path.basename(start_frame_path)}")
            session.generate(task.prompt, start_frame_path, try_path,
                             duration_s=task.duration_s)
            dur = C.ffprobe_duration(try_path)
            if dur is None:
                raise C.ExecutorError("Không đọc được thời lượng video tải về.")
            target = round(task.duration_s)
            if abs(dur - target) > duration_tol:
                logger.warning(f"{task.id} thời lượng {dur:.1f}s lệch mục tiêu "
                               f"{target}s (vẫn đưa duyệt).")
            logger.info(f"{task.id} nhận video AUTO ({dur:.1f}s)")
            return try_path
        except C.ExecutorError as e:
            logger.warning(f"{task.id} Grok auto lỗi: {e} — chuyển thủ công.")
        except Exception as e:
            logger.warning(f"{task.id} Grok auto lỗi bất ngờ ({e}) — chuyển thủ công.")

    return _manual_video(task, store, start_frame_path, logger, duration_tol)


def _manual_video(task: Task, store: Store, start_frame_path: str,
                  logger, duration_tol: float) -> str:
    """Cổng thủ công (bản gốc): in prompt, chờ thả mp4 vào inbox/."""
    prompt_file = os.path.join(store.inbox, f"{task.output_id}.prompt.txt")
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(task.prompt + "\n")

    C.open_file(start_frame_path)

    target = round(task.duration_s)
    print("\n" + "=" * 66)
    print(f"  VIDEO {task.output_id}  ({task.name})   [THỦ CÔNG]")
    print(f"  SRT: {task.srt_range or '-'}   |   Thời lượng đặt: {target}s")
    print("-" * 66)
    print(f"  START FRAME (upload làm ảnh khởi đầu):\n    {start_frame_path}")
    print(f"  PROMPT (đã lưu để copy):\n    {prompt_file}")
    print("-" * 66)
    print("  PROMPT:\n")
    for line in task.prompt.splitlines():
        print("    " + line)
    print("-" * 66)
    print(f"  → Chạy trên grok.com (image-to-video, {target}s), tải video về,")
    print(f"    thả vào:  {store.inbox}")
    print(f"    (đặt tên {task.output_id}.mp4 để tool nhận đúng; tên khác cũng được"
          f" — tool lấy .mp4 mới nhất).")
    print("=" * 66)

    while True:
        a = C.ask("  Xong thì Enter để nhận file (p=in lại prompt, s=Skip, q=Quit)").lower()
        if a in ("s", "skip"):
            raise C.UserSkip()
        if a in ("q", "quit"):
            raise C.UserQuit()
        if a == "p":
            print(task.prompt)
            continue

        dropped = C.find_dropped(store.inbox, task.output_id, (".mp4", ".mov", ".webm"))
        if not dropped:
            print(f"    Chưa thấy video trong {store.inbox}. Thả file rồi Enter lại.")
            continue

        dur = C.ffprobe_duration(dropped)
        if dur is None:
            print(f"    ! Không đọc được thời lượng của {os.path.basename(dropped)} "
                  f"(file hỏng?). Thử lại.")
            continue
        if abs(dur - target) > duration_tol:
            print(f"    ! Thời lượng {dur:.1f}s lệch nhiều so với {target}s "
                  f"(cho phép ±{duration_tol}s).")
            keep = C.ask("      Vẫn dùng file này? (y/N)").lower()
            if keep not in ("y", "yes"):
                continue

        logger.info(f"{task.id} nhận video {os.path.basename(dropped)} "
                    f"({dur:.1f}s) từ inbox")

        try_path, n = store.next_try_path(task.output_id, ".mp4")
        C.copy_to(dropped, try_path)
        try:
            os.remove(dropped)
        except OSError:
            pass
        return try_path
