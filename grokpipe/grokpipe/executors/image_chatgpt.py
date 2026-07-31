"""Executor IMAGE — ChatGPT tạo ảnh.

Hai chế độ:
  • AUTO: Playwright điều khiển chatgpt.com (phiên đăng nhập lưu ở user-data-dir).
  • MANUAL (fallback): tool in prompt + danh sách ảnh đính, chờ bạn thả .png/.jpg
    vào inbox/ — dùng khi thiếu Playwright, chưa đăng nhập, hoặc UI đổi làm auto gãy.

LƯU Ý: Web UI của ChatGPT hay đổi. Các selector gom trong SELECTORS để chỉnh nhanh.
Bất kỳ lỗi nào ở chế độ AUTO đều tự rơi về MANUAL để pipeline không đứng.
"""
from __future__ import annotations

import filecmp
import os
import time

from ..models import Task
from ..state import Store
from . import common as C

try:
    from playwright.sync_api import sync_playwright  # type: ignore
    _HAS_PW = True
except Exception:
    _HAS_PW = False


# Đính ảnh: BASE_IMAGE trước, rồi REF_IMAGES theo thứ tự (theo hướng dẫn tool mục 4).
def _ordered_attachments(task: Task, store: Store) -> list[str]:
    ids: list[str] = []
    if task.base_image:
        ids.append(task.base_image)
    ids.extend(task.ref_images)
    paths: list[str] = []
    for i in ids:
        p = store.resolve_input(i)
        if p:
            paths.append(p)
    return paths


# ----------------------------------------------------------------------------
# Selector — chỉnh ở đây khi ChatGPT đổi giao diện.
# ----------------------------------------------------------------------------
SELECTORS = {
    "composer": "#prompt-textarea",
    "file_input": "input[type=file]",
    "send_button": "button[data-testid='send-button']",
    "stop_button": "button[data-testid='stop-button']",
    # UI mới dùng data-turn=assistant trên <section>; giữ selector cũ để tương
    # thích. generate() sẽ loại toàn bộ URL đã có trước khi gửi prompt.
    "assistant_turn": "[data-turn='assistant'], [data-message-author-role='assistant']",
    "assistant_image": "[data-turn='assistant'] img, [data-message-author-role='assistant'] img",
    # khối overlay Edit/tải xuất hiện khi ảnh đã sinh xong
    "image_done": "[data-testid='image-gen-overlay-actions']",
    # thumbnail ảnh đính kèm hiện trong ô soạn (đếm để XÁC MINH upload đủ)
    # Thumbnail ảnh đính kèm nằm trong <form> của ô soạn. Đã đo trên UI thật:
    # "form img" = đúng số ảnh đang đính, và = 0 khi chưa đính gì.
    "composer_attachment": "form img",
}


class ChatGPTSession:
    """Giữ 1 phiên trình duyệt xuyên suốt pipeline."""

    def __init__(self, user_data_dir: str, logger, headless: bool = False,
                 url: str = "https://chatgpt.com/", gen_timeout: float = 300.0,
                 cdp_endpoint: str | None = None, shared_ctx=None):
        self.user_data_dir = os.path.abspath(user_data_dir)
        self.logger = logger
        self.headless = headless
        self.url = url
        self.gen_timeout = gen_timeout
        self.cdp_endpoint = cdp_endpoint    # nối vào Chrome thật (vd http://localhost:9222)
        self.shared_ctx = shared_ctx        # context CDP dùng chung (do runner tạo)
        self._pw = None
        self._ctx = None
        self._browser = None
        self._is_cdp = False
        self.page = None
        self.ready = False

    def start(self) -> bool:
        if not _HAS_PW and self.shared_ctx is None:
            self.logger.warning("Playwright chưa cài — dùng chế độ thủ công cho ảnh.")
            return False
        try:
            if self.shared_ctx is not None:
                # dùng chung kết nối CDP với executor khác (1 Playwright/tiến trình)
                self._is_cdp = True
                self._ctx = self.shared_ctx
                self.page = self._pick_page(self._ctx, ("chatgpt.com", "chat.openai.com"))
            elif self.cdp_endpoint:
                self._pw = sync_playwright().start()
                self._start_cdp()
            else:
                self._pw = sync_playwright().start()
                self._start_profile()
            self.page.goto(self.url, wait_until="domcontentloaded")
            self._ensure_login()
            self.ready = True
            return True
        except Exception as e:
            self.logger.warning(f"Không khởi động được Playwright ({e}) — dùng thủ công.")
            self.close()
            return False

    @staticmethod
    def _pick_page(ctx, hosts):
        for p in ctx.pages:
            try:
                if any(h in (p.url or "") for h in hosts):
                    return p
            except Exception:
                pass
        return ctx.new_page()

    def _start_profile(self) -> None:
        """Mở profile riêng (bạn tự đăng nhập + qua Cloudflare một lần)."""
        os.makedirs(self.user_data_dir, exist_ok=True)
        self._ctx = self._pw.chromium.launch_persistent_context(
            self.user_data_dir, headless=self.headless,
            viewport={"width": 1400, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        self.page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()

    def _start_cdp(self) -> None:
        """Nối vào Chrome thật đang mở (đã đăng nhập, đã qua Cloudflare)."""
        self._is_cdp = True
        self.logger.info(f"Nối vào Chrome thật qua CDP: {self.cdp_endpoint}")
        self._browser = self._pw.chromium.connect_over_cdp(self.cdp_endpoint)
        ctx = self._browser.contexts[0] if self._browser.contexts \
            else self._browser.new_context()
        self._ctx = ctx
        # tái dùng tab ChatGPT đang mở nếu có, không thì mở tab mới
        for p in ctx.pages:
            try:
                if "chatgpt.com" in (p.url or "") or "chat.openai.com" in (p.url or ""):
                    self.page = p
                    break
            except Exception:
                pass
        if self.page is None:
            self.page = ctx.new_page()

    def _ensure_login(self) -> None:
        """Chờ ô chat hiện. Nếu còn Cloudflare/đăng nhập, để BẠN tự xử lý tay."""
        for _ in range(3):
            try:
                self.page.wait_for_selector(SELECTORS["composer"], timeout=15000)
                return
            except Exception:
                print("\n  >>> Trong cửa sổ Chrome: hãy tự QUA 'Verify you are human'"
                      " (nếu có) và ĐĂNG NHẬP ChatGPT.")
                print("      (Tôi không tự làm bước xác minh người thật / đăng nhập này.)")
                C.ask("      Khi thấy ô chat ChatGPT hiện ra thì Enter để tiếp tục")
        # thử lần cuối
        self.page.wait_for_selector(SELECTORS["composer"], timeout=120000)

    def generate(self, prompt: str, attach_paths: list[str], out_path: str) -> bool:
        """Tạo 1 ảnh, lưu ra out_path. Trả True nếu thành công."""
        page = self.page
        # chat mới cho sạch context (goto ổn định hơn click nút)
        try:
            page.goto(self.url, wait_until="domcontentloaded")
            page.wait_for_selector(SELECTORS["composer"], timeout=20000)
        except Exception:
            pass

        # Ghi nhận ảnh đã có TRƯỚC lượt mới. ChatGPT đôi khi giữ nguyên chat cũ
        # nếu điều hướng về trang chủ bị chậm/lỗi; nếu không có mốc này, ảnh cũ
        # có thể bị hiểu nhầm là kết quả vừa sinh.
        old_img_srcs: set[str] = set()
        try:
            old_img_srcs = set(page.locator(SELECTORS["assistant_image"]).evaluate_all(
                """imgs => imgs.map(i => i.currentSrc || i.src || '').filter(Boolean)"""
            ))
        except Exception:
            pass
        try:
            old_assistant_messages = page.locator(SELECTORS["assistant_turn"]).count()
        except Exception:
            old_assistant_messages = 0

        # ĐÍNH ẢNH THAM CHIẾU: up CẢ LOẠT một lần cho nhanh, rồi ĐỐI CHIẾU TỪNG
        # ẢNH để biết CHÍNH XÁC cái nào chưa lên (so tỉ lệ khung của thumbnail với
        # tỉ lệ khung ảnh gốc), và chỉ up bù ĐÚNG những ảnh đó.
        if attach_paths:
            finp = page.locator(SELECTORS["file_input"]).first

            def _shapes() -> list[float]:
                """Tỉ lệ w/h của từng thumbnail đang có trong ô soạn."""
                try:
                    return [r for r in page.locator(
                        SELECTORS["composer_attachment"]).evaluate_all(
                        "els=>els.map(e=>e.naturalHeight?e.naturalWidth/e.naturalHeight:0)")
                        if r and r > 0]
                except Exception:
                    return []

            def _ratio_of(path: str) -> float:
                try:
                    from PIL import Image
                    with Image.open(path) as im:
                        w, h = im.size
                    return w / h if h else 0.0
                except Exception:
                    return 0.0

            want_r = [_ratio_of(x) for x in attach_paths]

            def _which_missing(base_shapes: list[float]) -> list[str]:
                """Ghép thumbnail hiện có với danh sách cần đính; trả về ảnh CHƯA lên."""
                pool = list(_shapes())
                for b in base_shapes:                     # bỏ thumbnail có từ trước
                    m = min(range(len(pool)), key=lambda i: abs(pool[i] - b), default=None)
                    if m is not None and pool and abs(pool[m] - b) < 0.02:
                        pool.pop(m)
                lack = []
                for path, r in zip(attach_paths, want_r):
                    if not pool:
                        lack.append(path); continue
                    m = min(range(len(pool)), key=lambda i: abs(pool[i] - r))
                    if abs(pool[m] - r) < 0.02:           # khớp tỉ lệ → ảnh này đã lên
                        pool.pop(m)
                    else:
                        lack.append(path)
                return lack

            base_shapes = _shapes()
            total = len(attach_paths)
            want = len(base_shapes) + total

            def _wait(target: int, secs: float) -> int:
                end_t = time.time() + secs
                n = len(_shapes())
                while time.time() < end_t and n < target:
                    time.sleep(1)
                    n = len(_shapes())
                return n

            finp.set_input_files(attach_paths)              # 1 phát cả loạt
            n_att = _wait(want, 8 + 3 * total)

            for _ in range(3):
                if n_att >= want:
                    break
                lack = _which_missing(base_shapes)
                if not lack:                                # đếm lệch nhưng ghép đủ
                    break
                self.logger.warning(
                    f"upload ref thiếu {len(lack)}/{total} — up bù ĐÚNG ảnh thiếu: "
                    + ", ".join(m.split('/')[-1] for m in lack))
                try:
                    finp.set_input_files(lack)
                except Exception as e:
                    self.logger.warning(f"up bù lỗi: {str(e)[:60]}")
                n_att = _wait(want, 6 + 3 * len(lack))

            still = _which_missing(base_shapes)
            if still:
                self.logger.warning(
                    "upload ref THIẾU sau khi up bù: "
                    + ", ".join(m.split('/')[-1] for m in still)
                    + " — hủy lượt, KHÔNG tạo ảnh khi thiếu tham chiếu")
                return False
            self.logger.info(f"đã đính đủ {total} ảnh tham chiếu")
            time.sleep(1.5)

        # nhập prompt
        editor = page.locator(SELECTORS["composer"])
        editor.click()
        try:
            editor.fill(prompt)
        except Exception:
            page.keyboard.insert_text(prompt)
        time.sleep(0.5)
        page.keyboard.press("Enter")
        time.sleep(0.5)
        if page.locator(SELECTORS["send_button"]).is_visible():
            try:
                page.locator(SELECTORS["send_button"]).click(timeout=1000)
            except Exception:
                pass

        # chờ sinh ảnh: có <img alt="Generated image"> src hợp lệ + đã sinh xong
        deadline = time.time() + self.gen_timeout
        img_src = None
        saw_generating = False   # đã từng thấy nút stop (đang sinh)
        idle_no_img = 0.0        # thời gian đã dừng sinh mà vẫn chưa có ảnh
        candidate_src = None
        candidate_stable = 0
        while time.time() < deadline:
            time.sleep(2)
            try:
                generating = page.locator(SELECTORS["stop_button"]).count() > 0
                if generating:
                    saw_generating = True
                imgs = page.locator(SELECTORS["assistant_image"])
                n = imgs.count()
                new_src = None
                for i in range(n - 1, -1, -1):
                    src = imgs.nth(i).evaluate(
                        """img => img.currentSrc || img.src || ''"""
                    )
                    if (src.startswith("http") or src.startswith("blob:")) \
                            and src not in old_img_srcs:
                        new_src = src
                        break

                # Chỉ nhận URL ảnh mới, đã tải đủ kích thước và ổn định qua
                # ít nhất hai nhịp kiểm tra sau khi ChatGPT ngừng trả lời.
                if new_src:
                    if new_src == candidate_src:
                        candidate_stable += 1
                    else:
                        candidate_src = new_src
                        candidate_stable = 1
                    if not generating and candidate_stable >= 2:
                        img_src = new_src
                        break
                else:
                    candidate_src = None
                    candidate_stable = 0

                # fail nhanh: đã sinh xong (nút stop tắt) nhưng KHÔNG ra ảnh
                # -> thường là hết lượt tạo ảnh / bị từ chối, khỏi chờ hết timeout
                assistant_messages = page.locator(SELECTORS["assistant_turn"]).count()
                response_started = saw_generating or assistant_messages > old_assistant_messages
                if response_started and not generating and not new_src:
                    idle_no_img += 2
                    if idle_no_img >= 12:
                        raise C.ExecutorError(
                            "ChatGPT kết thúc lượt nhưng không sinh ảnh "
                            "(có thể HẾT LƯỢT tạo ảnh trong ngày / bị từ chối).")
                else:
                    idle_no_img = 0.0
            except C.ExecutorError:
                raise
            except Exception:
                pass
        if not img_src:
            raise C.ExecutorError("Hết thời gian chờ ChatGPT sinh ảnh.")

        ok = self._download(img_src, out_path)
        if ok:
            # Hàng rào cuối: tuyệt đối không nhận một file giống hệt ảnh ref.
            # Trường hợp này chứng tỏ UI/selector đã lấy nhầm ảnh đính kèm.
            for ref_path in attach_paths:
                try:
                    if filecmp.cmp(out_path, ref_path, shallow=False):
                        os.remove(out_path)
                        raise C.ExecutorError(
                            "ChatGPT trả về đúng file ảnh tham chiếu thay vì ảnh mới; "
                            "đã hủy file để không ghi đè SF."
                        )
                except C.ExecutorError:
                    raise
                except OSError:
                    pass
        return ok

    def _download(self, src: str, out_path: str) -> bool:
        """Tải bytes ảnh từ src (dùng HTML Canvas hoặc fetch)."""
        # cách 1: vẽ ra canvas trong DOM rồi lấy base64 (chống lỗi CORS/backend-api 422)
        try:
            b64 = self.page.evaluate(
                """(u) => {
                    const imgs = Array.from(document.querySelectorAll(
                        "[data-turn='assistant'] img, [data-message-author-role='assistant'] img"
                    ));
                    const img = imgs.find(i => (i.currentSrc || i.src || '') === u);
                    if (!img || !img.complete || !img.naturalWidth) return null;
                    const canvas = document.createElement('canvas');
                    canvas.width = img.naturalWidth;
                    canvas.height = img.naturalHeight;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0);
                    return canvas.toDataURL('image/png').split(',')[1];
                }""", src)
            if b64:
                import base64
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                with open(out_path, "wb") as f:
                    f.write(base64.b64decode(b64))
                if os.path.getsize(out_path) > 1000:
                    return True
        except Exception:
            pass

        # cách 2: fetch trực tiếp trong page
        try:
            b64 = self.page.evaluate(
                """async (u) => {
                    const r = await fetch(u, {credentials: 'include'});
                    const b = await r.blob();
                    return await new Promise(res => {
                        const fr = new FileReader();
                        fr.onloadend = () => res(fr.result.split(',')[1]);
                        fr.readAsDataURL(b);
                    });
                }""", src)
            if b64:
                import base64
                with open(out_path, "wb") as f:
                    f.write(base64.b64decode(b64))
                if os.path.getsize(out_path) > 1000:
                    return True
        except Exception:
            pass

        # cách 3: request API của context
        try:
            resp = self._ctx.request.get(src)
            if resp.ok:
                with open(out_path, "wb") as f:
                    f.write(resp.body())
                return os.path.getsize(out_path) > 1000
        except Exception:
            pass
        return False

    def close(self) -> None:
        # context dùng chung do runner quản lý — không đụng gì
        if self.shared_ctx is not None:
            self.ready = False
            return
        # CDP: KHÔNG đóng Chrome của bạn — chỉ đóng tab tool tạo (nếu tự mở) + ngắt kết nối
        if self._is_cdp:
            try:
                if self._browser:
                    self._browser.close()   # chỉ ngắt CDP, Chrome vẫn chạy
            except Exception:
                pass
        else:
            try:
                if self._ctx:
                    self._ctx.close()
            except Exception:
                pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self.ready = False


# ----------------------------------------------------------------------------
def run_image(task: Task, store: Store, logger,
              session: ChatGPTSession | None) -> str:
    """Tạo ảnh cho task. Trả path try trong tries/. Raise nếu skip/quit."""
    attach = _ordered_attachments(task, store)

    # AUTO — khi có session: chỉ chạy tự động. Lỗi/timeout thì RAISE để runner
    # thử lại (chat mới) — ChatGPT hay treo "One last tweak", chat mới thường sinh
    # nhanh. KHÔNG rớt thủ công (chế độ thuần không có stdin).
    if session is not None and session.ready:
        try_path, _ = store.next_try_path(task.output_id, ".png")
        logger.info(f"{task.id} [AUTO] tạo ảnh, đính {len(attach)} ảnh tham chiếu")
        ok = session.generate(task.prompt, attach, try_path)
        if ok and os.path.exists(try_path) and os.path.getsize(try_path) > 0:
            return try_path
        raise C.ExecutorError("ChatGPT không trả ảnh (sẽ thử lại chat mới).")

    # MANUAL (chỉ khi KHÔNG có session — vd --manual-image)
    return _manual_image(task, store, attach, logger)


def _manual_image(task: Task, store: Store, attach: list[str], logger) -> str:
    prompt_file = os.path.join(store.inbox, f"{task.output_id}.prompt.txt")
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(task.prompt + "\n")
    for p in attach:
        C.open_file(p)

    print("\n" + "=" * 66)
    print(f"  IMAGE {task.output_id}  ({task.name})   [THỦ CÔNG]")
    print("-" * 66)
    if attach:
        print("  ĐÍNH ẢNH (đúng thứ tự — BASE trước, rồi REF):")
        for i, p in enumerate(attach, 1):
            print(f"    {i}. {p}")
    else:
        print("  (không có ảnh đính — text-to-image)")
    print(f"  PROMPT (đã lưu): {prompt_file}")
    print("-" * 66)
    for line in task.prompt.splitlines():
        print("    " + line)
    print("-" * 66)
    print(f"  → Tạo ảnh trên chatgpt.com, tải về, thả vào: {store.inbox}")
    print(f"    (đặt tên {task.output_id}.png để nhận đúng; .jpg cũng được)")
    print("=" * 66)

    while True:
        a = C.ask("  Xong thì Enter (p=in prompt, s=Skip, q=Quit)").lower()
        if a in ("s", "skip"):
            raise C.UserSkip()
        if a in ("q", "quit"):
            raise C.UserQuit()
        if a == "p":
            print(task.prompt)
            continue
        dropped = C.find_dropped(store.inbox, task.output_id,
                                 (".png", ".jpg", ".jpeg", ".webp"))
        if not dropped:
            print(f"    Chưa thấy ảnh trong {store.inbox}. Thả file rồi Enter lại.")
            continue
        try_path, _ = store.next_try_path(task.output_id, ".png")
        C.copy_to(dropped, try_path)
        try:
            os.remove(dropped)
        except OSError:
            pass
        logger.info(f"{task.id} nhận ảnh {os.path.basename(dropped)} (thủ công)")
        return try_path
