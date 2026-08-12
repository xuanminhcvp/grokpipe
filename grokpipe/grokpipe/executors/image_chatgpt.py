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
import re
import tempfile
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


# DOM CỦA CHATGPT NẰM Ở dom_chatgpt.py (tách 2026-08-12) — selector và mọi đoạn
# JS chạy trong trang. ChatGPT đổi giao diện liên tục; gom một chỗ thì lần sau
# chỉ phải mở một file, còn đây giữ thuần phần điều phối lô.
from .dom_chatgpt import (      # noqa: F401
    SELECTORS, _JS_O_SOAN,
    JS_CHON_CHE_DO, JS_CHON_CHE_DO_2, JS_DOWNLOAD, JS_DOWNLOAD_2,
    JS_ANH_DANG_CO, JS_DANH_SACH_ID, JS_DANH_SACH_REF_ID, JS_ANH_SAU_MOC_TURN,
    JS_QUET_CUON, JS_DEM_TU_CHOI, JS_TIN_NHAN_TEXT_TRO_LY, JS_TRANG_THAI_O_SOAN,
    JS_TAI_VE, JS_MOC_TURN_TRO_LY, JS_TEN_DA_LEN,
)

# ─────────────── HẾT LƯỢT ĐÍNH TỆP (khác hẳn hết lượt TẠO ẢNH) ───────────────
# ChatGPT có một trần RIÊNG cho việc ĐÍNH TỆP, và nó chặn theo GIỜ:
#   "You've added all your available file uploads until 3:45 PM"
# Trần này chặn ở bước upload, tức ta chưa đốt lượt tạo ảnh nào. Trước đây board
# chỉ thấy "upload ref THIẾU" → coi là lỗi thường, xếp lại hàng và tài khoản đó
# thử lại mãi cho tới khi hết lượt thử, trong khi nó CHẮC CHẮN không up được gì
# cho tới giờ ghi trên màn hình. Vì vậy phải nhận ra chữ này và ném lên board
# kèm ĐÚNG GIỜ MỞ LẠI, để board cho tài khoản nghỉ tới giờ đó rồi chạy tiếp bằng
# tài khoản khác.
#
# Nhãn máy đọc `[NGHI-DEN:HH:MM]` (24h) nằm trong chuỗi lỗi — sfboard.py bắt bằng
# regex. Không đổi định dạng nhãn này ở một đầu mà quên đầu kia.
_RE_HET_UPLOAD = re.compile(
    r"(?:added all (?:of )?(?:your |the )?available file uploads?"
    r"|(?:reached|hit) (?:your |the )?(?:daily )?(?:file )?upload limit"
    r"|no more file uploads?)([^.\n]{0,80})", re.I)
# Giờ mở lại: "until 3:45 PM" · "until 15:45" · "until 3 PM".
_RE_GIO_MO = re.compile(
    r"(?:until|till)\s+(\d{1,2})(?::(\d{2}))?\s*([AaPp])?\.?[Mm]?\.?", re.I)


def _gio_24(h: str, p: str | None, ap: str | None) -> str:
    """('3', '45', 'P') → '15:45'. Không có AM/PM thì coi là giờ 24h sẵn."""
    gio, phut = int(h), int(p or 0)
    if ap:
        gio = gio % 12 + (12 if ap.lower() == "p" else 0)
    return f"{gio % 24:02d}:{phut:02d}"


# Ảnh ref quá nặng bị ChatGPT nuốt LẶNG LẼ khi up cả loạt: đo trên UI thật, hai
# file ~3MB trong một lượt 7 file không bao giờ lên, ba file nhỏ lên bình thường.
# Nên thu nhỏ ra BẢN TẠM rồi mới up.
#
# ẢNH GỐC TUYỆT ĐỐI KHÔNG BỊ ĐỘNG TỚI — nhiều ảnh trong assets/ là bản user đã
# duyệt. Bản tạm nằm ngoài project và luôn là JPEG, nên phép đối chiếu theo tên
# file phải so PHẦN TÊN (bỏ đuôi) — 'SF-M-FOYER.png' và 'SF-M-FOYER.jpg' là một.
_REF_TRAN_KB = 1200          # nặng hơn mức này thì mới thu nhỏ
_REF_CANH_MAX = 1600         # cạnh dài tối đa của bản tạm
_REF_TAM = os.path.join(tempfile.gettempdir(), "grokpipe-ref-nhe")


def _nhe_hoa(paths: list[str], logger) -> list[str]:
    """Trả về danh sách đường dẫn để up: ảnh nặng thay bằng bản tạm nhẹ hơn."""
    ra = []
    for p in paths:
        try:
            if os.path.getsize(p) <= _REF_TRAN_KB * 1024:
                ra.append(p); continue
            from PIL import Image
            os.makedirs(_REF_TAM, exist_ok=True)
            dich = os.path.join(_REF_TAM, os.path.splitext(os.path.basename(p))[0] + ".jpg")
            # dùng lại bản tạm nếu còn mới hơn ảnh gốc
            if os.path.exists(dich) and os.path.getmtime(dich) >= os.path.getmtime(p):
                ra.append(dich); continue
            with Image.open(p) as im:
                im = im.convert("RGB")
                if max(im.size) > _REF_CANH_MAX:
                    r = _REF_CANH_MAX / max(im.size)
                    im = im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))),
                                   Image.LANCZOS)
                im.save(dich, "JPEG", quality=88)
            logger.info(f"ref nặng {os.path.basename(p)}: "
                        f"{os.path.getsize(p)//1024}KB → {os.path.getsize(dich)//1024}KB")
            ra.append(dich)
        except Exception as e:
            logger.warning(f"không thu nhỏ được {os.path.basename(p)}: {str(e)[:60]}")
            ra.append(p)
    return ra


_TAG_TAB = "cgslot"          # window.name của tab: mỗi thợ một chỗ ngồi riêng
_HOST_CHATGPT = ("chatgpt.com", "chat.openai.com")


def _LA_TAB_CHATGPT(pg) -> bool:
    try:
        return any(h in (pg.url or "") for h in _HOST_CHATGPT)
    except Exception:
        return False


class ChatGPTSession:
    """Giữ 1 phiên trình duyệt xuyên suốt pipeline."""

    def __init__(self, user_data_dir: str, logger, headless: bool = False,
                 url: str = "https://chatgpt.com/", gen_timeout: float = 300.0,
                 cdp_endpoint: str | None = None, shared_ctx=None, slot: int = 0):
        self.user_data_dir = os.path.abspath(user_data_dir)
        self.logger = logger
        self.headless = headless
        self.url = url
        self.gen_timeout = gen_timeout
        self.cdp_endpoint = cdp_endpoint    # nối vào Chrome thật (vd http://localhost:9222)
        self.shared_ctx = shared_ctx        # context CDP dùng chung (do runner tạo)
        self.slot = int(slot)               # chỗ ngồi: mỗi thợ một TAB riêng
        self._pw = None
        self._ctx = None
        self._browser = None
        self._is_cdp = False
        self.page = None
        self.ready = False
        self.loi_cuoi = ""      # lý do thật của lần start() hỏng gần nhất

    def start(self) -> bool:
        if not _HAS_PW and self.shared_ctx is None:
            self.logger.warning("Playwright chưa cài — dùng chế độ thủ công cho ảnh.")
            return False
        try:
            if self.shared_ctx is not None:
                # dùng chung kết nối CDP với executor khác (1 Playwright/tiến trình)
                self._is_cdp = True
                self._ctx = self.shared_ctx
                self.page = self._tim_tab()
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
            # Giữ lại lý do THẬT: bên gọi chỉ nhận False, không có nó thì board
            # phải đoán bừa và hay đổ oan cho "chưa đăng nhập".
            self.loi_cuoi = f"{type(e).__name__}: {e}"
            self.logger.warning(f"Không khởi động được Playwright ({e}) — dùng thủ công.")
            self.close()
            return False

    def _tim_tab(self):
        """Tab riêng của luồng này, nhận ra qua window.name = 'cgslot<N>'.

        MỖI THỢ MỘT TAB, KHÔNG DÙNG CHUNG. Bản cũ (`_pick_page`) vớ lấy tab đầu
        tiên thấy chatgpt.com, nên đặt tabs>1 cho một tài khoản là mấy luồng thợ
        cùng trỏ vào MỘT tab: cùng gõ vào một ô soạn, cùng bấm submit, cùng đợi
        ảnh — prompt đè lên nhau và ảnh lô này gán cho lô kia. Grok đã có cơ chế
        này từ trước; đây là bản cho ChatGPT.

        `window.name` sống theo tab và qua cả điều hướng, nên đánh dấu ở đây là
        đủ để nhận lại đúng tab của mình sau khi trang tải lại."""
        tag = f"{_TAG_TAB}{self.slot}"

        def ten(pg):
            try:
                return pg.evaluate("window.name") or ""
            except Exception:
                return ""

        if self.page is not None and not self.page.is_closed() and ten(self.page) == tag:
            return self.page
        mo = [pg for pg in self._ctx.pages if not pg.is_closed()]
        for pg in mo:
            if _LA_TAB_CHATGPT(pg) and ten(pg) == tag:
                return pg
        # Slot 0 nhận nuôi một tab chatgpt CHƯA ai đánh dấu — để dùng lại tab
        # user đang mở sẵn (đã đăng nhập, đã qua Cloudflare), khỏi đẻ tab thừa.
        # Slot khác LUÔN mở tab mới của riêng nó.
        if self.slot == 0:
            for pg in mo:
                if _LA_TAB_CHATGPT(pg) and not ten(pg).startswith(_TAG_TAB):
                    pg.evaluate("n => { window.name = n }", tag)
                    return pg
        pg = self._ctx.new_page()
        pg.goto(self.url, wait_until="domcontentloaded")
        pg.evaluate("n => { window.name = n }", tag)
        return pg

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

    def _dang_sinh(self) -> bool:
        """ChatGPT còn đang trả lời không — căn cứ DUY NHẤT là nút stop.

        ĐỪNG lấy 'nút gửi đã quay lại' làm dấu hiệu xong: nút gửi chỉ hiện khi ô
        soạn CÓ CHỮ; ô trống thì nó đổi thành nút micro, nên điều kiện đó không
        bao giờ đúng và vòng chờ treo vĩnh viễn."""
        try:
            return self.page.locator(SELECTORS["stop_button"]).count() > 0
        except Exception:
            return False

    def _cho_ranh(self, giay: float = 240, yen: float = 6) -> bool:
        """Chờ tới khi hết nút stop và YÊN liên tục `yen` giây."""
        het = time.time() + giay
        im = 0.0
        while time.time() < het:
            if self._dang_sinh():
                im = 0.0
            else:
                im += 1.0
                if im >= yen:
                    return True
            time.sleep(1)
        return False

    def _chon_che_do(self, ten: str = "High") -> str:
        """Chọn chế độ trả lời (Instant · Medium · High).

        ĐÂY LÀ THỨ QUYẾT ĐỊNH khi xin nhiều ảnh trong một lượt. Instant chắc chắn
        hay ghép lưới; ca S5 ngày 2026-08-07 cho thấy Medium cũng có thể trả một
        contact sheet 2×3. Vì vậy đường tạo theo lô phải dùng High và kiểm tra lại
        hiện trạng trước khi gửi."""
        try:
            dang = self.page.evaluate(
                JS_CHON_CHE_DO)
            if not dang or dang.startswith(ten):
                return dang
            self.page.get_by_role("button", name=dang).first.click(timeout=5000)
            time.sleep(1.5)

            # HAI KIỂU GIAO DIỆN CÙNG TỒN TẠI — đã đo: tài khoản này một kiểu, tài
            # khoản kia kiểu khác, nên phải thử CẢ HAI chứ đừng chọn theo phiên bản.
            #   cũ : menu ba mục  role=menuitemradio  (Instant · Medium · High)
            #   mới: MỘT THANH TRƯỢT ba nấc — span role=slider, aria-valuenow 0/1/2
            # Không bắt kiểu mới thì hàm nuốt lỗi và chạy nguyên ở Instant, mà
            # Instant gói cả lô vào MỘT ảnh ghép lưới; board đếm 1 ảnh cho N prompt
            # rồi vứt cả lô. Hỏng hoàn toàn im lặng.
            try:
                self.page.get_by_role("menuitemradio", name=ten).first.click(timeout=3000)
            except Exception:
                NAC = {"Instant": 0, "Medium": 1, "High": 2}
                dich = NAC.get(ten)
                th = self.page.locator("[role=slider]").first
                if dich is None or not th.is_visible(timeout=3000):
                    raise
                th.click(timeout=3000)                 # lấy focus vào thanh trượt
                for _ in range(6):                     # 6 nhịp là quá đủ cho 3 nấc
                    nay = th.get_attribute("aria-valuenow") or "0"
                    nay = int(nay) if nay.lstrip("-").isdigit() else 0
                    if nay == dich:
                        break
                    self.page.keyboard.press("ArrowRight" if nay < dich else "ArrowLeft")
                    time.sleep(0.5)
                self.logger.info("giao diện THANH TRƯỢT — kéo tới nấc %d (%s)", dich, ten)
                self.page.keyboard.press("Escape")
            time.sleep(1.5)

            # KIỂM LẠI THEO HIỆN TRẠNG, không theo ý định. Bản cũ coi như đã đổi
            # ngay sau cú bấm, nên chạy cả buổi ở Instant mà log vẫn sạch bong.
            sau = self.page.evaluate(
                JS_CHON_CHE_DO_2)
            if not sau.startswith(ten):
                self.logger.warning("ĐỔI CHẾ ĐỘ THẤT BẠI — vẫn đang %r, cần %r. "
                                    "Lô nhiều ảnh sẽ ra MỘT ảnh ghép lưới.", sau, ten)
                return sau
            self.logger.info(f"chuyển chế độ {dang} → {ten}")
            return ten
        except Exception as e:
            self.logger.warning(f"không chọn được chế độ {ten}: {str(e)[:60]}")
            return ""

    def _che_do_tot_nhat(self) -> str:
        """Đẩy lên chế độ tốt nhất còn với được: High → Medium → chạy tiếp.

        High bám yêu cầu "nhiều ảnh độc lập" tốt nhất, nhưng KHÔNG được vì thế
        mà dừng cả lô. User chốt 2026-08-08: không lên được High thì Medium cũng
        được. Bỏ nguyên một lô đắt hơn hẳn rủi ro thỉnh thoảng ra ảnh ghép lưới —
        mà lô ghép lưới thì board đã có đường xử (đếm lệch → hộp chờ phân loại).
        Trả về chế độ ĐỌC ĐƯỢC sau cùng, chuỗi rỗng nghĩa là không đọc được nút."""
        che = self._chon_che_do("High")
        if (che or "").startswith("High"):
            return che
        che2 = self._chon_che_do("Medium")
        if (che2 or "").startswith("Medium"):
            self.logger.warning("không lên được High (đang %r) — chạy ở Medium.", che)
            return che2
        self.logger.warning(
            "không đọc được nút chế độ (thử High → %r, Medium → %r) — vẫn chạy "
            "tiếp bằng chế độ hiện có; lô nhiều ảnh có thể ra ảnh ghép lưới.",
            che, che2)
        return che2 or che

    def _anh_dang_co(self) -> list[str]:
        """src ảnh của trợ lý theo ĐÚNG THỨ TỰ hiển thị, đã bỏ trùng."""
        try:
            return self.page.evaluate(
                JS_ANH_DANG_CO) or []
        except Exception:
            return []

    # ---- GIAO DIỆN CAROUSEL MỚI (2026-08, "estuary") — đếm theo ID, theo LƯỢT.
    # Hai bài học trả giá bằng cả buổi render, đừng quay lại cách cũ:
    # · Đếm bằng src là SAI: URL ảnh mang chữ ký (`sig`/`ts`) ký lại mỗi lần tải
    #   trang, nên ảnh CŨ của các lô trước hoá "ảnh mới" sau mỗi page.goto —
    #   lô 5 prompt đếm ra 7 ảnh. Danh tính thật là tham số `id=file_…`.
    # · Phải THU HẸP THEO LƯỢT trả lời mới (sau mốc lượt chụp trước khi gửi),
    #   vì cả trang lúc nào cũng đầy ảnh của các lô cũ.
    # Carousel: ảnh chính chỉ là slide ĐANG CHỌN (nhân 2-3 phần tử DOM); dàn
    # thumbnail nhỏ mới liệt kê ĐỦ ảnh của lượt theo thứ tự sinh — nên khi lượt
    # có thumbnail thì tin thumbnail, giao diện cũ không thumbnail thì lấy cả.

    # ---- ĐẾM ẢNH: HIỆU TẬP ID TOÀN TRANG (2026-08-06, lần đổi thứ ba).
    # Ba cách trước đều gãy vì DOM ChatGPT không có gì bền:
    #   · đếm theo src — URL ký lại (sig/ts) sau mỗi page.goto, ảnh cũ hoá "mới";
    #   · đếm theo CHỈ SỐ lượt — hội thoại dài bị ảo hoá, lượt cũ unmount, chỉ số xê dịch;
    #   · đọc LƯỢT CUỐI theo data-message-id — có lượt không mang mid, và có lô
    #     render ảnh trong container KHÔNG mang thuộc tính lượt nào cả.
    # Thứ duy nhất bền là tham số `id=file_…` của ảnh. Nên: chụp TẬP id trước khi
    # gửi, ảnh mới = id chưa từng thấy, theo đúng thứ tự DOM (= thứ tự sinh).
    # Ảnh trong lượt USER (ref mình tự đính) bị loại để không đếm nhầm.

    def _danh_sach_id(self) -> list:
        """[[id, src], …] các ảnh SINH trên trang theo thứ tự DOM, mỗi id một lần.

        Giao diện mới không còn bọc ref trong `[data-turn=user]`, nên phải nhận
        diện trực tiếp: ref có alt là tên file và nằm trong nút `Open image …`;
        output thật có alt `Generated image` hoặc alt rỗng.
        """
        try:
            return self.page.evaluate(
                JS_DANH_SACH_ID) or []
        except Exception:
            return []

    def _danh_sach_ref_id(self) -> list[str]:
        """ID estuary của ảnh REF do user/code đính vào lượt gửi hiện có."""
        try:
            return self.page.evaluate(
                JS_DANH_SACH_REF_ID) or []
        except Exception:
            return []

    def _moc_turn_tro_ly(self) -> int:
        """Số `conversation-turn-N` lớn nhất của assistant trước cú gửi.

        Đây là cái neo gọn và bền hơn việc cuộn toàn bộ chat để chụp mọi ảnh cũ:
        turn mới luôn có N lớn hơn, kể cả ChatGPT gỡ/mount lại các turn cũ.
        """
        try:
            return int(self.page.evaluate(
                JS_MOC_TURN_TRO_LY) or -1)
        except Exception:
            return -1

    def _anh_sau_moc_turn(self, moc: int, quet_thumbnail: bool = False) -> list:
        """[[turn_no, image_id, src], …] chỉ từ các lượt assistant MỚI.

        Không cuộn trang chính. Khi cần chốt, chỉ cuộn cột thumbnail bên trong
        các turn sau `moc`, rồi trả nó về đúng vị trí cũ. Poll liên tục sẽ tích
        luỹ ảnh của turn mới trước khi ChatGPT kịp ảo hoá chúng khỏi DOM.
        """
        try:
            return self.page.evaluate(
                JS_ANH_SAU_MOC_TURN, {"moc": moc, "quet": quet_thumbnail}) or []
        except Exception:
            return []

    # ---- NGHE MẠNG: nguồn sự thật thay cho DOM -----------------------------
    # DOM là HỆ QUẢ, mạng là NGUỒN. Mọi ảnh hiện lên đều phải qua một request
    # `/backend-api/estuary/content?id=file_…`; ghi lại lúc nó về thì sau đó DOM
    # có gỡ mount, tải lười, hay ChatGPT có đổi tên thuộc tính cũng không ảnh
    # hưởng. Đã trả giá hai lần cho bài học này:
    #   · ảnh cuộn khỏi tầm nhìn bị gỡ khỏi DOM → đếm hụt → vứt cả lô;
    #   · `data-message-author-role='assistant'` BIẾN MẤT khỏi giao diện mới nên
    #     mọi phép lọc theo nhãn lượt trả về rỗng, im lặng.
    # Mạng chỉ dùng để giữ ĐỦ id + URL. KHÔNG dùng thứ tự response để gán SF:
    # ảnh nhẹ tải xong trước ảnh nặng, nên thứ tự mạng có thể khác thứ tự prompt.
    def _nghe_mang(self) -> None:
        """Gắn tai nghe vào trang. Gọi nhiều lần vô hại — chỉ gắn đúng một lần."""
        if getattr(self, "_da_nghe", None) is self.page:
            return
        self._mang_ids: list[str] = []
        # Giữ luôn URL ngay lúc response đi qua. DOM ChatGPT có thể gỡ ảnh khỏi
        # cây khi cuộn hội thoại dài; chỉ giữ id rồi đợi DOM đưa src trở lại sẽ
        # biến một lượt đã có đủ ảnh thành 0/N.
        self._mang_urls: dict[str, str] = {}

        def _ghi(r):
            try:
                u = r.url or ""
                if "estuary/content" not in u:
                    return
                m = re.search(r"[?&]id=(file_[0-9A-Za-z]+)", u)
                if m:
                    k = m.group(1)
                    if k not in self._mang_ids:
                        self._mang_ids.append(k)
                    self._mang_urls[k] = u
            except Exception:
                pass

        try:
            self.page.on("response", _ghi)
            self._da_nghe = self.page
        except Exception as e:
            self.logger.warning("không gắn được tai nghe mạng: %s", str(e)[:70])

    def _mang_xoa(self) -> None:
        """Xoá sổ ghi ngay TRƯỚC khi bấm gửi — sau mốc này id nào về là ảnh mới."""
        self._nghe_mang()
        try:
            self._mang_ids.clear()
            self._mang_urls.clear()
        except Exception:
            self._mang_ids = []
            self._mang_urls = {}

    def _mang_moi(self) -> list[str]:
        return list(getattr(self, "_mang_ids", []))

    def _mang_url(self, ident: str) -> str:
        return (getattr(self, "_mang_urls", {}) or {}).get(ident, "")

    def _quet_cuon(self) -> list:
        """Cuộn hết thread và TRẢ LẠI ảnh đã thấy theo thứ tự từ trên xuống.

        ChatGPT ảo hoá hội thoại dài: ảnh cuộn ra ngoài tầm nhìn bị GỠ khỏi DOM,
        nên `_danh_sach_id()` (chạy querySelectorAll) chỉ thấy phần đang mount.
        Lô prompt dài làm trang cao gấp mấy lần, ảnh đầu lô rơi khỏi DOM và lô bị
        đếm non — đúng ảnh vẫn hiện đủ trên màn hình mà board báo 2/6 hay 4/6.

        Quan trọng: phải gom NGAY Ở MỖI NẤC CUỘN. Cuộn xong mới query DOM chỉ thấy
        vùng cuối, còn lấy thứ tự response mạng thì ảnh nhẹ tải xong trước ảnh
        nặng và bị gắn sai SF.
        """
        try:
            return self.page.evaluate(
                JS_QUET_CUON) or []
        except Exception:
            return []

    def _dem_tu_choi(self) -> int:
        """Số lần chữ từ chối (guardrail / went wrong) xuất hiện trên trang.
        So TRƯỚC/SAU khi gửi — chữ từ chối của các lượt cũ còn nằm lại trong chat
        nên đếm tuyệt đối là báo chặn oan."""
        try:
            return self.page.evaluate(
                JS_DEM_TU_CHOI) or 0
        except Exception:
            return 0

    def _tin_nhan_text_tro_ly(self) -> dict[str, str]:
        """{message_id: text} của các phản hồi assistant đang có trên trang.

        Với imagegen High hiện tại, lượt thành công chỉ trả các attachment ảnh;
        thẻ message vẫn tồn tại nhưng text rỗng. Nếu thẻ của LƯỢT MỚI có text,
        ChatGPT đã trả lời bằng lời / đổi yêu cầu thay vì hoàn tất đúng lô ảnh.
        Dùng `data-message-id`, không so số thứ tự DOM: hội thoại dài bị ảo hoá
        nên các message cũ có thể mount/unmount trong lúc đang chờ.
        """
        try:
            return self.page.evaluate(
                JS_TIN_NHAN_TEXT_TRO_LY) or {}
        except Exception:
            return {}

    def _o_soan(self):
        """Ô soạn ĐANG HIỆN, không phải cái đầu tiên khớp selector.

        Đã trả giá 2026-08-07 (lô SF-S7-02..07): trang có `#prompt-textarea`
        mang `aria-hidden="true"` — Playwright coi là không thao tác được nên
        `click()` treo đủ 30 giây rồi chết cả lô. Trang ChatGPT có lúc giữ nhiều
        ô soạn (khung cũ chưa gỡ, panel ẩn), nên phải LỌC THEO CÁI ĐANG HIỆN.
        Không thấy cái nào hiện thì trả cái đầu để lỗi vẫn nói được hiện trạng.

        Lọc bằng `filter(visible=True)`, KHÔNG bằng `nth(i)` sau khi tự gọi
        `is_visible()`: locator Playwright giải lại ở thời điểm THAO TÁC, nên chỉ
        số đo lúc kiểm có thể trỏ sang ô khác nếu ChatGPT dựng lại DOM giữa hai
        bước — vẫn là con đường quay về đúng ô ẩn cũ. Bộ lọc thì được đánh giá
        lại ngay lúc click/fill nên không có kẽ hở đó."""
        ds = self.page.locator(
            f'{SELECTORS["composer"]}:not([aria-hidden="true"])').filter(visible=True)
        try:
            if ds.count():
                return ds.first
        except Exception:
            pass
        return self.page.locator(SELECTORS["composer"]).first

    def _trang_thai_o_soan(self) -> str:
        """Mô tả mọi ô soạn đang có trên trang — nhét vào thông báo lỗi.

        Lỗi chỉ nói 'timeout' bắt người sau phải mở Chrome soi tay; lỗi kèm hiện
        trạng thì đọc log là biết ngay ô nào bị ẩn."""
        try:
            ds = self.page.evaluate(
                JS_TRANG_THAI_O_SOAN) or []
            if not ds:
                return "KHÔNG có ô soạn nào trên trang"
            return f"{len(ds)} ô soạn: " + " · ".join(
                f"[{i}] {d['w']}×{d['h']}"
                f"{' aria-hidden' if d.get('hidden') == 'true' else ''}"
                f"{' không sửa được' if d.get('disabled') else ''}"
                for i, d in enumerate(ds))
        except Exception as e:
            return f"không đọc được trạng thái ô soạn ({str(e)[:50]})"

    def _tai_ve(self, src: str, out_path: str, lan: int = 3) -> bool:
        """Tải ảnh bằng fetch trong trang. KHÔNG dùng canvas: sau khi trang từng
        điều hướng sang origin khác thì canvas bị 'tainted' và toDataURL ném lỗi.

        THỬ LẠI vài lần, vì hỏng ở đây gần như luôn là hỏng NHẤT THỜI: `TypeError:
        Failed to fetch` xảy ra khi trang đang điều hướng/ổn định lại, trong khi
        ảnh vẫn nằm nguyên trong chat. Đã trả giá 2026-08-07 (lượt 2 của S7):
        ChatGPT trả đủ 6/6, một cú fetch hụt làm mất ảnh thứ 2, cả lô rơi xuống
        chờ phân loại. Thử lại KHÔNG tốn lượt tạo ảnh nào — đừng bỏ qua nó."""
        import base64
        for i in range(max(1, lan)):
            try:
                b64 = self.page.evaluate(
                    JS_TAI_VE, src)
                if b64:
                    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
                    with open(out_path, "wb") as f:
                        f.write(base64.b64decode(b64))
                    if os.path.getsize(out_path) > 1024:
                        if i:
                            self.logger.info("tải ảnh được ở lần thử %d", i + 1)
                        return True
                ly_do = "fetch trả rỗng/không ok"
            except Exception as e:
                ly_do = str(e).splitlines()[0][:80]
            if i < lan - 1:
                self.logger.info("tải ảnh hụt (%s) — thử lại %d/%d", ly_do, i + 2, lan)
                time.sleep(2 + 2 * i)
        self.logger.warning("tải ảnh LỖI sau %d lần: %s · %s", lan, ly_do, src[:90])
        return False

    # NHÃN MÃ SF IN THẲNG VÀO ẢNH — ngoại lệ có tên của luật "không chữ".
    #
    # Vì sao cần: khi một lượt trả về lệch số ảnh, KHÔNG có cách nào biết ảnh nào
    # của thẻ nào ngoài thứ tự — mà thứ tự chính là thứ vừa hỏng. Mã in trong ảnh
    # là bằng chứng tự mang theo, nhìn phát biết ngay, kể cả khi tải về lộn xộn.
    #
    # Vì sao phải khai là NGOẠI LỆ: `luatchung` của mọi địa điểm đều có câu "mọi
    # nhãn, biển hiệu, giấy tờ trong khung đều để chữ NHOÈ, không một chữ nào
    # đánh vần ra được". Xin thêm chữ mà không nói rõ đây là ngoại lệ thì model
    # làm nhoè đúng cái mã ta cần đọc — hai câu đá nhau, câu nào thắng tuỳ lúc.
    #
    # ⚠ Nhãn NẰM TRONG ẢNH, nên nó sẽ theo start frame vào video. Tắt trước khi
    # render bản cuối (công tắc trên board).
    _NHAN_MA = (
        "NHÃN NHẬN DIỆN — NGOẠI LỆ DUY NHẤT của luật “không chữ nào đọc được”: "
        "mỗi ảnh phải in MÃ của chính nó ở GÓC DƯỚI BÊN TRÁI, sans-serif, màu "
        "trắng trên một mảng nền tối mờ, ĐỌC RÕ TỪNG KÝ TỰ. Đây là nhãn kỹ thuật "
        "CHỒNG LÊN ảnh như watermark — KHÔNG phải vật thể trong cảnh: không viết "
        "nó lên tường, biển hiệu, giấy tờ hay quần áo, không nhân vật nào nhìn "
        "vào nó. Mọi chữ KHÁC trong khung vẫn phải nhoè như luật chung. "
        "Overlay each image's own code as legible white text in the BOTTOM-LEFT "
        "corner, over a dark translucent patch; it is a technical label on top of "
        "the picture, not an object inside the scene.")

    def generate_lo(self, viec: list[tuple[str, str]], attach_paths: list[str],
                    chat_url: str = "", luat_chung: str = "",
                    cho_moi_anh: float = 180,
                    nen_dung=None, dan_ma: bool = True) -> tuple[list[str], str, dict]:
        """Xin NHIỀU ảnh trong MỘT lượt của MỘT đoạn chat.

        viec       = [(nhãn, prompt), …] theo đúng thứ tự muốn nhận
        chat_url   = chat của địa điểm; rỗng thì mở chat mới rồi trả url về để lưu
        luat_chung = khối LUẬT CHUNG của địa điểm, CHỈ gửi khi mở chat mới
        Trả (danh sách src ảnh theo thứ tự hiển thị, chat_url, ghi_chu).
        ghi_chu = {"loi_text": chữ assistant trả kèm (rỗng nếu không có),
                   "da_gui": lượt đã gửi đi thật hay chưa}

        Ba điều đã đo trên UI thật, đừng đổi nếu không đo lại:
        · Chế độ NÊN là 'High': Medium đã từng gói 6 prompt S5 vào MỘT contact
          sheet 2×3, High bám yêu cầu nhiều output độc lập tốt hơn. Nhưng không
          lên được High thì HẠ XUỐNG MEDIUM và vẫn chạy (user chốt 2026-08-08),
          không dừng lô nữa — xem `_che_do_tot_nhat`.
        · XONG = hết nút stop và YÊN liên tục. Trước đó ảnh vừa thiếu vừa đổi ID;
          khi xong mới được đọc thứ tự dãy thumbnail (không đọc ảnh preview lớn).
        · Số ảnh nhận về KHÁC số prompt thì KHÔNG được ghép theo thứ tự — lệch một
          nấc là ảnh gắn nhầm SF và sai kiểu đó hoàn toàn im lặng.

        HÀM NÀY KHÔNG PHÁN XÉT NỮA — nó chỉ TRẢ VỀ TẤT CẢ những gì lượt này sinh
        ra, kể cả khi thiếu, thừa, hay có chữ trả kèm. Việc quyết định "ghép hay
        đưa vào Chờ phân loại" nằm ở board, vì chỉ board mới tải được ảnh về đĩa.
        Trước đây hàm tự trả rỗng khi thấy chữ trả kèm → ảnh ĐÃ SINH bị vứt, phải
        đốt lại cả lượt. Ảnh đã sinh là tiền đã tiêu: luôn giao lên trên."""
        page = self.page
        if self._dang_sinh():
            self.logger.info("chat còn đang sinh — chờ xong rồi mới gửi lô mới")
            self._cho_ranh(600, 10)
        moi = not chat_url
        page.goto(chat_url or self.url, wait_until="domcontentloaded")
        page.wait_for_selector(SELECTORS["composer"], timeout=30000)
        time.sleep(2)
        self._che_do_tot_nhat()

        tu_choi_0 = self._dem_tu_choi()
        # ĐÍNH REF CẢ KHI DÙNG LẠI CHAT CŨ. Board đã lọc sẵn: attach_paths lúc này
        # chỉ còn những ref CHƯA từng gửi vào chat này. Bỏ qua chúng vì "chat cũ"
        # là để nhân vật mới của lô này không có ảnh nào để bám, và model sẽ tự
        # bịa ra một người khác — sai câm, không có thông báo nào.
        if attach_paths:
            if not self._dinh_ref(attach_paths):
                return [], ("" if moi else chat_url), {"loi_text": "", "da_gui": False}

        # CHỤP ẢNH CŨ SAU KHI ĐÍNH REF, không phải trước.
        #
        # Ảnh ref đính vào composer cũng dùng URL `estuary/content?id=file_…` y hệt
        # ảnh sinh, nên chụp trước khi đính là ref bị coi là "ảnh mới của lô".
        # Đã trả giá: lô S2-08..13 (2026-08-07) UI trả về đúng 6, code đếm 7, cắt
        # "6 id cuối" làm lô lệch một nấc, ảnh gắn nhầm SF câm.
        # Đứng sau _dinh_ref → ref là "cũ", chỉ ID sinh từ cú gửi mới đếm.
        truoc_ids = {k for k, _ in self._danh_sach_id()}
        ref_ids = set(self._danh_sach_ref_id())
        moc_turn = self._moc_turn_tro_ly()
        # Chat trắng chưa có bất kỳ lượt assistant nào, nên -1 là mốc hợp lệ:
        # lượt sinh đầu tiên chắc chắn có số turn > -1. Chỉ coi -1 là lỗi khi
        # đang mở LẠI một chat cũ; khi đó nó có nghĩa selector/DOM đã lệch và
        # tiếp tục quét sẽ có nguy cơ nhận nhầm ảnh của lượt trước.
        if moc_turn < 0 and not moi:
            raise RuntimeError("không đọc được mốc conversation-turn của ChatGPT — "
                               "dừng lô để tránh quét/gắn nhầm ảnh cũ")
        if moc_turn < 0:
            self.logger.info("chat trắng chưa có assistant turn — dùng mốc khởi đầu -1")
        text_ids_truoc = set(self._tin_nhan_text_tro_ly())
        self.logger.info("trước khi gửi: mốc assistant turn %d · %d ảnh đang mount · "
                         "%d ref hiện có", moc_turn, len(truoc_ids), len(ref_ids))

        than = [f"Tạo ĐÚNG {len(viec)} ẢNH RIÊNG BIỆT (16:9) tương ứng {len(viec)} prompt dưới đây. "
                "CẤM GỘP ẢNH (no grid, no collage, no contact sheet). Thứ tự ảnh đúng như thứ tự prompt tôi gửi"]
        # MỞ KHOÁ CÁC HƯỚNG CÒN LẠI CỦA CĂN PHÒNG.
        #
        # Model bám rất chặt vào hướng máy của ẢNH BỐI CẢNH được đính kèm: cả lô
        # ra cùng một phía, chỉ đổi cỡ cảnh. Đo trên lô S7 (2026-08-07): 12/12
        # khung đều đứng cùng một bên quầy. Câu này nói rõ ảnh bối cảnh là để
        # KHOÁ LOOK, không phải để khoá hướng.
        #
        # Mệnh đề sau là bắt buộc, đừng bỏ: nó cho model quyền chọn góc, mà quyền
        # đó phải dừng lại trước những khung tác giả đã chốt góc bằng số — không
        # có nó thì mọi khối MÁY QUAY đã viết kỹ đều có thể bị model tự đổi.
        than.append(
            "ẢNH BỐI CẢNH DÙNG ĐỂ KHOÁ LOOK: Bắt buộc lấy y hệt bảng màu, nhiệt độ, "
            "hướng sáng từ ảnh đính kèm. "
            "TUY NHIÊN, KHÔNG KHOÁ GÓC MÁY. Hãy tự do quay các hướng khác nhau trong phòng. "
            "LƯU Ý: Nếu prompt nào đã ghi rõ góc máy thì PHẢI tuân thủ 100%.")
        if moi and luat_chung:
            than.append(luat_chung)
        # Nhãn mã đứng SAU luatchung, vì nó là ngoại lệ của chính luật vừa gửi —
        # đặt trước thì model đọc luật chữ sau cùng và làm nhoè mã.
        if dan_ma:
            than.append(self._NHAN_MA)
        for i, (nhan, pr) in enumerate(viec, 1):
            than.append(f"── ẢNH {i} ({nhan}) ──\n{pr}"
                        + (f"\nText góc dưới bên trái: {nhan}" if dan_ma else ""))
        txt = "\n\n".join(than)

        # REPLACE, KHÔNG APPEND. Ở High, sau khi gửi xong đôi lúc ProseMirror giữ
        # nguyên draft cũ trong #prompt-textarea. `insertText` khi đó chèn lô mới
        # vào giữa lô cũ (đã xảy ra ở S5: prompt 07–12 nằm lọt trong prompt 01–06).
        # `fill` phát đúng input event và thay toàn bộ text nhưng không đụng các
        # chip ảnh tham chiếu nằm ngoài editor.
        editor = self._o_soan()
        try:
            editor.click(timeout=15000)
        except Exception as e:
            raise RuntimeError(
                f"không bấm được vào ô soạn ChatGPT: {str(e).splitlines()[0]} · "
                f"{self._trang_thai_o_soan()} · {page.url}") from e
        try:
            editor.fill(txt)
        except Exception:
            # Đường dự phòng cho biến thể ProseMirror không nhận fill: chọn đúng
            # nội dung BÊN TRONG editor, xoá rồi mới insert — không select cả trang.
            page.evaluate("t => { const e = " + _JS_O_SOAN + """;
                if (!e) return; e.focus();
                const s = window.getSelection(), r = document.createRange();
                r.selectNodeContents(e); s.removeAllRanges(); s.addRange(r);
                document.execCommand('delete', false);
                document.execCommand('insertText', false, t); }""", txt)
        time.sleep(0.5)

        # Không tin thao tác vừa làm: đọc ngược lại và so nguyên văn sau khi gom
        # whitespace. Sai một ký tự cấu trúc, còn sót draft cũ hay bị chèn đôi đều
        # phải dừng TRƯỚC cú gửi — không đốt thêm một lượt ảnh.
        trong_o = page.evaluate("() => { const e = " + _JS_O_SOAN + """;
            return e ? (e.innerText || e.textContent || '') : ''; }""") or ""
        chuan = lambda s: re.sub(r"\s+", " ", s or "").strip()
        if chuan(trong_o) != chuan(txt):
            raise RuntimeError(f"ô prompt không sạch/không khớp sau khi thay nội dung "
                               f"({len(trong_o)} ký tự thực tế, cần {len(txt)}) — không gửi")
        self.logger.info("đã thay sạch ô prompt và đối chiếu khớp %d ký tự", len(txt))
        time.sleep(1.5)
        # XOÁ SỔ NGHE MẠNG ngay trước cú gửi — sau mốc này id nào về là ảnh MỚI,
        # không cần biết DOM đang mount cái gì.
        self._mang_xoa()
        if not self._gui():
            return [], page.url, {"loi_text": "", "da_gui": False}
        self.logger.info(f"đã gửi lô {len(viec)} khung ({len(txt):,} ký tự)")

        # Chờ theo SỐ ẢNH ĐÃ VỀ, không chỉ theo nút stop: giao diện carousel hiện
        # từng ảnh khi ảnh đó xong, và chỉ báo "yên" là chưa đủ bằng chứng — lô
        # từng bị đếm non lúc 2/5 vì thoát sớm. Ba lối ra:
        #   đủ ảnh + đã yên → xong · có ảnh mà đứng im quá lâu → kẹt giữa chừng ·
        #   0 ảnh + đứng im → cả lượt bị chặn (guardrail), thoát sớm cho board xử.
        # Chờ theo SỐ ID MỚI đã xuất hiện. Ba lối ra: đủ ảnh · trang mọc thêm
        # chữ từ chối (guardrail) · đứng im quá lâu.
        het = time.time() + cho_moi_anh * len(viec) + 420
        n_truoc, doi_tu = -1, time.time()

        # TÍCH LUỸ id qua MỌI vòng poll, KHÔNG chụp lại ảnh chụp DOM mỗi vòng.
        # ChatGPT gỡ mount ảnh cuộn khỏi tầm nhìn, nên một snapshot đơn lẻ luôn
        # có thể thiếu ảnh đã vẽ xong từ trước. Thấy một lần là ghi nhớ vĩnh viễn.
        thay: dict[str, str] = {}
        theo_turn: dict[int, dict[str, str]] = {}
        loi_text = ""

        def _gom(quet_thumbnail: bool = False) -> int:
            # Chỉ ID nằm trong assistant turn có số LỚN HƠN mốc mới được nhận.
            # Network không tự thêm ID nữa: request ref/ảnh cũ lazy-load cũng đi
            # qua estuary và từng làm bộ đếm nhảy thành 14 cho lô 6 ảnh. Network
            # giờ chỉ cung cấp URL mới nhất cho ID đã được DOM turn mới xác nhận.
            doc = self._anh_sau_moc_turn(moc_turn, quet_thumbnail)
            hien_tai: dict[int, dict[str, str]] = {}
            for turn_no, k, s in doc:
                o = hien_tai.setdefault(int(turn_no), {})
                o[k] = self._mang_url(k) or s
            # Mỗi turn đang mount được coi theo SNAPSHOT MỚI NHẤT, không hợp
            # union vĩnh viễn. Trong lúc sinh ChatGPT có thể dùng một file ID
            # preview rồi thay bằng ID hoàn chỉnh; union từng làm lô đúng 6 bị
            # đếm thành 7. Turn đã unmount thì vẫn giữ bucket đã chụp trước đó.
            for turn_no, o in hien_tai.items():
                theo_turn[turn_no] = o
            thay.clear()
            for turn_no in sorted(theo_turn):
                thay.update(theo_turn[turn_no])
            return len(thay)

        while time.time() < het:
            # DỪNG RIÊNG MỘT VIỆC — không phải đóng cả Chrome.
            #
            # Vòng này vốn chỉ chờ ChatGPT vẽ, poll 5 giây một nhịp, nên có thừa
            # chỗ để soi cờ dừng. Trước đây không soi nên giao diện phải khoá nút
            # dừng của từng việc và bắt user chọn giữa "để chạy nốt" hay "đóng
            # Chrome giết sạch mọi việc trên tài khoản đó" — một lựa chọn giả.
            # Bấm luôn nút stop của ChatGPT để cắt THẬT, không chỉ bỏ chờ.
            if nen_dung and nen_dung():
                try:
                    if self.page.locator(SELECTORS["stop_button"]).count() > 0:
                        self.page.locator(SELECTORS["stop_button"]).first.click(timeout=3000)
                        self.logger.info("user dừng việc này — đã bấm stop trên ChatGPT")
                    else:
                        self.logger.info("user dừng việc này — ChatGPT đã vẽ xong, chỉ bỏ chờ")
                except Exception:
                    pass
                return [], page.url, {"loi_text": "", "da_gui": True, "user_dung": True}
            n = _gom()
            dang = self._dang_sinh()
            # ĐỒNG HỒ ĐỨNG-IM CHỈ CHẠY KHI CHATGPT ĐÃ NGỪNG. Giao diện agent mới
            # nghĩ/vẽ ngầm rất lâu rồi mới hiện ảnh một lượt ("Worked for 8m 38s");
            # tính đứng-im trong lúc nó còn chạy thì board bỏ cuộc ở phút thứ năm,
            # báo 0/N rồi gửi lại — đã đốt lượt hai lần vì chỗ này.
            if dang or n != n_truoc:
                doi_tu = time.time()
            n_truoc = n
            # Imagegen thành công chỉ để message rỗng và trả attachment ảnh.
            # Nếu LƯỢT MỚI mọc text thì đó là phản hồi lỗi/đổi yêu cầu, kể cả
            # carousel bên trên tình cờ chứa đủ N thumbnail. Không được nhận số
            # ảnh ấy rồi gắn vào SF — chính ca S5 đã trả một contact sheet kèm
            # câu "Chỉ tạo ẢNH 1..." nhưng bộ đếm cũ vẫn tưởng là output hợp lệ.
            if not dang:
                tin_moi = {
                    mid: text for mid, text in self._tin_nhan_text_tro_ly().items()
                    if mid not in text_ids_truoc and (text or "").strip()
                }
                if tin_moi:
                    loi_text = list(tin_moi.values())[-1]
                    self.logger.warning("lượt imagegen trả kèm TEXT — coi là lỗi: %s",
                                        re.sub(r"\s+", " ", loi_text)[:240])
                    break
            if n >= len(viec) and not dang:
                # CHỜ TRANG ỔN ĐỊNH HẲN RỒI MỚI ĐỌC THỨ TỰ.
                #
                # Đủ ảnh + hết nút stop VẪN CHƯA phải là xong: trong lúc ChatGPT
                # còn đang chốt lượt, ảnh trên trang vừa thiếu vừa SẮP XẾP LỘN XỘN.
                # Chỉ khi trang yên liên tục vài chục giây thì dãy thumbnail và
                # file ID mới ổn định. Thứ tự đó là thứ board zip với danh sách SF;
                # đọc sớm hoặc lấy ảnh preview đang chọn là gắn ảnh lộn thẻ.
                # Đã trả giá: lô 4 bộ đồ Brianna về đủ 4 mà ô 4 lại là ảnh ô 2.
                YEN = 25.0                     # giây phải yên LIÊN TỤC
                moc, truoc_yen = time.time(), len(thay)
                while time.time() - moc < YEN:
                    time.sleep(5)
                    _gom()
                    if self._dang_sinh() or len(thay) != truoc_yen:
                        # còn động đậy → đếm lại từ đầu, chưa được đọc thứ tự
                        moc, truoc_yen = time.time(), len(thay)
                self.logger.info("trang đã yên %.0fs — chốt thứ tự", YEN)
                _gom(quet_thumbnail=True)
                break
            im_lau = 0.0 if dang else time.time() - doi_tu
            if im_lau > 45 and self._dem_tu_choi() > tu_choi_0:
                self.logger.info("lượt bị ChatGPT từ chối (guardrail) — thoát sớm")
                break
            if im_lau > 300:
                # Nút Stop KHÔNG tồn tại xuyên suốt lúc ChatGPT xếp hàng/nghĩ
                # ngầm. Vì vậy 300 giây không thấy nút + chưa có ảnh KHÔNG có
                # nghĩa là lượt đã chết. Đây chính là ca UI về đủ 2/2 ngay sau
                # khi board đã kết luận 0/2 rồi tự gửi lại.
                #
                # Quét để vớt ảnh ngoài DOM; nếu vẫn chưa thấy thì tiếp tục chờ
                # tới hạn tổng `het`. Chỉ chữ từ chối rõ ràng ở nhánh trên mới
                # được phép thoát sớm.
                truoc_quet = len(thay)
                if _gom(quet_thumbnail=True) > truoc_quet:
                    self.logger.info("quét thumbnail lượt mới thấy thêm %d ảnh — chờ tiếp",
                                     len(thay) - truoc_quet)
                else:
                    self.logger.info("chưa thấy ảnh sau 300s nhưng không có lỗi rõ ràng "
                                     "— tiếp tục chờ tới hạn tổng")
                n_truoc, doi_tu = len(thay), time.time()
                continue
            time.sleep(5)

        # Text của assistant trong lượt mới là tín hiệu KHÔNG ĐƯỢC TỰ GHÉP: ảnh
        # có thể là contact sheet, có thể lệch, không có ánh xạ đáng tin với danh
        # sách SF. Nhưng KHÔNG vứt: ảnh vẫn được quét, tải về và đưa vào Chờ phân
        # loại để user tự gắn. Cờ báo lên trên là `ghi_chu["loi_text"]`.
        # (Bản cũ trả rỗng ở đây — mỗi lần ChatGPT lỡ mồm nói một câu là mất
        # trắng cả lượt ảnh đã vẽ xong.)

        # QUÉT CHỐT đúng thumbnail của CÁC TURN MỚI rồi xếp theo số turn.
        #
        # Thứ tự ở đây quyết định ảnh nào gắn vào SF nào: board zip thẳng danh sách
        # này với danh sách prompt. `thay` là dict nên thứ tự của nó là thứ tự THẤY
        # LẦN ĐẦU qua các vòng poll — mà giữa các vòng có thao tác cuộn, làm ảnh
        # mount lên theo thứ tự bất kỳ. Lấy thẳng dict ra là ảnh gắn lộn thẻ, và
        # ảnh cùng một nhân vật trông na ná nhau nên mắt rất khó bắt.
        # Vì vậy: DOM quyết định THỨ TỰ, dict chỉ bù những ảnh DOM đã gỡ mount.
        _gom(quet_thumbnail=True)

        # HAI NGUỒN, HAI VAI — đừng đổi chỗ cho nhau, đã trả giá hai lần:
        #   · DOM  → THỨ TỰ. Vị trí trong hội thoại chính là thứ tự hiển thị, mà
        #            ChatGPT vẽ theo đúng thứ tự prompt. Đây là thứ board zip với
        #            danh sách prompt nên nó phải chuẩn tuyệt đối.
        #   · MẠNG → ĐỦ SỐ. Chỉ dùng để vớt id mà DOM không còn hiện (gỡ mount,
        #            tải lười, đổi thuộc tính).
        # KHÔNG dùng thứ tự mạng làm chuẩn: sự kiện `response` bắn lúc ảnh TẢI
        # XONG, không phải lúc vẽ xong — ảnh nhẹ về trước ảnh nặng, nên thứ tự đến
        # là thứ tự kích thước file chứ không phải thứ tự khung hình. Đã đo: lô 4
        # bộ đồ Brianna về đủ 4 nhưng ô 4 lại là ảnh của ô 2.
        # Kết quả quét từ TRÊN XUỐNG là nguồn thứ tự đầy đủ nhất khi hội thoại
        # bị ảo hoá. Snapshot DOM ở đáy chỉ là đường dự phòng cho chat ngắn.
        thu_tu = []
        for turn_no in sorted(theo_turn):
            for k in theo_turn[turn_no]:
                if k in thay and k not in thu_tu:
                    thu_tu.append(k)
        # Request mạng không thuộc turn mới bị bỏ có chủ ý: đó thường là 8 ref
        # lazy-load hoặc ảnh cũ. Chỉ cảnh báo các ID chưa phân loại để debug.
        con = [k for k in self._mang_moi()
               if k not in ref_ids and k not in truoc_ids and k not in set(thu_tu)]
        if con:
            self.logger.info("bỏ %d request estuary không thuộc assistant turn mới "
                             "(ref/ảnh cũ lazy-load)", len(con))
        moi = [(k, thay.get(k) or "") for k in thu_tu]
        # id có trong sổ mà chưa kịp có src (ảnh về nhưng DOM chưa gắn) thì bỏ —
        # không tải được, và giữ lại chỉ làm lệch phép đếm.
        thieu_src = [k for k, v in moi if not v]
        if thieu_src:
            self.logger.warning("%d id chưa có src để tải: %s", len(thieu_src), ", ".join(thieu_src))
            moi = [(k, v) for k, v in moi if v]
        # THỪA ID KHÔNG ĐƯỢC ĐOÁN.
        #
        # ChatGPT thi thoảng vẽ THÊM một biến thể ngoài số prompt đã xin. Bản cũ
        # cắt "lấy N id cuối" với giả định biến thể ở ĐẦU (kiểu preview/thinking).
        # Sai: đã đo trên lô S2-08..13 (2026-08-07) — 7 id cho 6 prompt, biến thể
        # nằm ở giữa nên cắt đầu làm cả lô lệch một nấc, ảnh gắn nhầm SF câm.
        # Không có tín hiệu đáng tin nào để chỉ ra id THỪA giữa dàn ảnh estuary
        # (kích thước · aspect · id đều giống hệt bản chính).
        # Nên: để len lệch propagate lên sfboard.py — nó tải HẾT về thư mục Chờ
        # phân loại rồi để user gắn tay. Chi phí: một cú bấm; đổi lại đảm bảo
        # tuyệt đối ảnh gắn đúng SF, và không lượt nào bị đốt lại.
        if len(moi) > len(viec):
            self.logger.warning(f"{len(moi)} id mới cho {len(viec)} prompt — "
                                f"KHÔNG ĐOÁN, giao cả lượt cho board phân loại")
        moi_src = [src for _, src in moi]
        # Log ĐỦ SỐ để lần sau không phải đoán: tổng ảnh trên trang · ảnh cũ đã chụp
        # · ảnh mới tính ra · số prompt đã xin. Lệch ở đâu nhìn là ra ngay.
        self.logger.info("lô trả về %d/%d ảnh · mạng ghi %d · DOM có %d · chụp trước %d",
                         len(moi_src), len(viec), len(self._mang_moi()),
                         len(self._danh_sach_id()), len(truoc_ids))
        # KHÔNG cắt bớt, kể cả lô một ảnh trả về hai bản. Bản cũ lấy "id cuối" cho
        # lô một ảnh — đúng phần lớn lần, nhưng khi sai thì sai câm. Giao cả lượt
        # lên board: đủ đúng số thì board ghép, lệch thì vào Chờ phân loại.
        return moi_src, page.url, {"loi_text": loi_text, "da_gui": True}

    def _gui(self) -> bool:
        def _da_roi_o_soan() -> bool:
            """Send thật thì nội dung text rời composer; click bị nuốt thì còn nguyên.

            PHẢI đọc đúng ô ĐANG HIỆN và phải fail-closed. Bản cũ đọc bằng
            `querySelector` rồi `return not txt`: gặp ô ẩn (rỗng) hoặc không thấy
            ô nào thì cùng ra `True` — tức báo ĐÃ GỬI trong khi draft còn nguyên
            trong ô thật. Đó là lỗi tệ hơn timeout, vì lô chết mà log vẫn sạch."""
            try:
                txt = self.page.evaluate(
                    "() => { const e = " + _JS_O_SOAN + """;
                        return e ? (e.innerText || e.textContent || '').trim() : null; }""")
                return txt == ""       # None = không thấy ô hiện → KHÔNG coi là đã gửi
            except Exception:
                return False

        # Chat dài đôi khi nuốt cú click đầu: nút nhận click nhưng draft vẫn nằm
        # nguyên trong composer, không mọc user turn. Chỉ báo thành công sau khi
        # đọc ngược thấy draft đã rời ô; nếu còn thì bấm lại đúng một lần.
        for lan in range(2):
            try:
                # Cùng bệnh với ô soạn: trang có lúc giữ nút gửi của khung cũ đã
                # ẩn. `.first` trúng cái ẩn thì vòng này bỏ qua im lặng và luôn
                # rơi xuống đường Enter, nên lọc theo cái đang hiện.
                nut = self.page.locator(
                    SELECTORS["send_button"]).filter(visible=True).first
                if nut.is_visible() and nut.is_enabled():
                    nut.click(timeout=4000)
                    time.sleep(1.5)
                    if _da_roi_o_soan():
                        if lan:
                            self.logger.info("cú Send đầu bị nuốt — bấm lại lần 2 đã nhận")
                        return True
            except Exception:
                pass
        try:
            self._o_soan().click(timeout=15000)
            self.page.keyboard.press("Enter")
            time.sleep(1.5)
            return _da_roi_o_soan()
        except Exception:
            return False

    def _het_luot_upload(self) -> str | None:
        """Trang có đang báo HẾT LƯỢT ĐÍNH TỆP không?

        Trả 'HH:MM' (24h) khi đọc được giờ mở lại · '' khi thấy chặn mà không có
        giờ · None khi không có chặn nào. Đọc innerText cả trang vì chữ này nằm
        trong toast/banner của composer, không có testid ổn định."""
        try:
            txt = self.page.evaluate("() => document.body.innerText || ''") or ""
        except Exception:
            return None
        m = _RE_HET_UPLOAD.search(txt)
        if not m:
            return None
        g = _RE_GIO_MO.search(m.group(0))
        return _gio_24(g.group(1), g.group(2), g.group(3)) if g else ""

    def _chan_neu_het_upload(self) -> None:
        """Thấy chặn upload thì ném lỗi kèm nhãn `[NGHI-DEN:…]` cho board."""
        gio = self._het_luot_upload()
        if gio is None:
            return
        # Không đọc được giờ thì hẹn 60 phút — vẫn hơn hẳn việc thử lại liên tục.
        nhan = f"[NGHI-DEN:{gio}]" if gio else "[NGHI-DEN:+60]"
        self.logger.warning("ChatGPT chặn đính tệp — hết lượt upload %s",
                            f"tới {gio}" if gio else "(không rõ giờ mở lại)")
        raise RuntimeError(
            "ChatGPT hết lượt đính tệp (upload) "
            + (f"— mở lại lúc {gio}" if gio else "— không đọc được giờ mở lại")
            + f" {nhan}")

    def _dinh_ref(self, attach_paths: list[str]) -> bool:
        """Đính ảnh tham chiếu và XÁC MINH đủ. False = thiếu, KHÔNG được tạo ảnh.

        Dùng chung cho cả đường một-ảnh lẫn đường lô, để phép kiểm chỉ có MỘT
        bản — hai bản kiểm khác nhau là bug đang chờ."""
        page = self.page
        if not attach_paths:
            return True
        attach_paths = _nhe_hoa(attach_paths, self.logger)
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

        def _ten_da_len() -> list[str]:
            """Tên file đã đính XONG, đọc từ nhãn nút gỡ file. [] = không đọc được."""
            try:
                return page.evaluate(
                    JS_TEN_DA_LEN) or []
            except Exception:
                return []

        def _thieu_theo_ten() -> list[str] | None:
            """Ảnh chưa lên, đối chiếu theo TÊN FILE. None = không đọc được nhãn."""
            co = _ten_da_len()
            if not co:
                return None
            def _goc(x):        # bỏ đuôi: bản tạm là .jpg, ảnh gốc có thể .png
                return os.path.splitext(os.path.basename(x))[0].lower()
            con = [_goc(x) for x in co]
            lack = []
            for path in attach_paths:
                g = _goc(path)
                if g in con:
                    con.remove(g)
                else:
                    lack.append(path)
            return lack

        def _which_missing(base_shapes: list[float]) -> list[str]:
            """Ghép thumbnail hiện có với danh sách cần đính; trả về ảnh CHƯA lên.

            Chỉ dùng khi KHÔNG đọc được tên file (giao diện đổi). Cách này
            đoán bằng tỉ lệ khung nên có thể chọn nhầm ảnh — xem chú thích ở
            đầu khối."""
            theo_ten = _thieu_theo_ten()
            if theo_ten is not None:
                return theo_ten
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

        def _dem() -> int:
            """Số ảnh ĐÃ LÊN XONG.

            KHÔNG dùng 'form img' làm mốc chờ: selector đó đếm cả ô ảnh ĐANG
            TẢI DỞ. Đo trên UI thật: nó báo đủ 7/7 sau 8 giây trong khi 2 file
            nặng còn đang bay, bấm gửi thì ChatGPT lặng lẽ không nhận và prompt
            nằm lại trong ô soạn. Nút gỡ file chỉ mọc khi file đã lên xong."""
            ten = _ten_da_len()
            return len(ten) if ten else len(_shapes())

        def _wait(target: int, secs: float) -> int:
            end_t = time.time() + secs
            n = _dem()
            while time.time() < end_t and n < target:
                time.sleep(1)
                n = _dem()
            return n

        finp.set_input_files(attach_paths)              # 1 phát cả loạt
        n_att = _wait(want, 8 + 3 * total)

        for _ in range(3):
            if n_att >= want:
                break
            # KIỂM TRẦN UPLOAD TRƯỚC KHI UP BÙ. Hết lượt đính tệp thì up bù chỉ
            # là ba vòng chờ vô ích (~30s) rồi báo "thiếu ref" — một lỗi nói sai
            # nguyên nhân, và board sẽ xếp lại hàng cho chính tài khoản đang bị
            # chặn. Ném sớm để board cho tài khoản nghỉ tới giờ mở lại.
            self._chan_neu_het_upload()
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
            self._chan_neu_het_upload()      # chặn muộn: banner mọc sau lượt up bù
            self.logger.warning(
                "upload ref THIẾU sau khi up bù: "
                + ", ".join(m.split('/')[-1] for m in still)
                + " — hủy lượt, KHÔNG tạo ảnh khi thiếu tham chiếu")
            return False
        self.logger.info(f"đã đính đủ {total} ảnh tham chiếu")
        time.sleep(1.5)

        return True

    def generate(self, prompt: str, attach_paths: list[str], out_path: str) -> bool:
        """Tạo 1 ảnh, lưu ra out_path. Trả True nếu thành công."""
        page = self.page
        # KHÔNG điều hướng khi lượt trước còn đang sinh — rời trang giữa chừng là
        # mất cả lô đang chạy, và ảnh đã sinh cũng không thu lại được.
        if self._dang_sinh():
            self.logger.info("lượt trước còn đang sinh — chờ xong rồi mới mở chat mới")
            self._cho_ranh(300)
        # chat mới cho sạch context (goto ổn định hơn click nút). MỌI đường tạo
        # ảnh đều bị khoá ở High: nếu giao diện đổi hoặc không xác nhận được nấc
        # High thì dừng, tuyệt đối không âm thầm gửi bằng Medium/Instant.
        page.goto(self.url, wait_until="domcontentloaded")
        page.wait_for_selector(SELECTORS["composer"], timeout=20000)
        self._che_do_tot_nhat()

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
        # ẢNH để biết CHÍNH XÁC cái nào chưa lên, và chỉ up bù ĐÚNG những ảnh đó.
        #
        # ĐỐI CHIẾU THEO TÊN FILE, KHÔNG THEO TỈ LỆ KHUNG. Tỉ lệ khung không phân
        # biệt được các ref cùng dạng: đo trên một bộ 7 ref thật thì 3 ảnh toàn
        # thân đều đúng 0.563, hai ảnh chân dung là 0.666 và 0.667 — lệch 0.001
        # trong khi ngưỡng khớp là 0.02. Khi đó một ảnh rớt sẽ làm hàm ghép chọn
        # NHẦM ảnh để up bù: up lên một bản trùng, số lượng khớp nên phép kiểm
        # PASS, mà bộ ref thật thì thừa một cái và thiếu hẳn một cái. Lỗi im lặng.
        #
        # Nút gỡ file mang THEO TÊN FILE trong aria-label và chỉ hiện khi file đã
        # lên XONG. Ta chỉ bắt phần tên file trong nhãn (khớp đuôi ảnh) chứ không
        # bắt chữ "Remove file" — giao diện đổi theo ngôn ngữ tài khoản, còn tên
        # file thì không.
        if attach_paths and not self._dinh_ref(attach_paths):
            return False
        # nhập prompt
        editor = self._o_soan()
        try:
            editor.click(timeout=15000)
        except Exception as e:
            raise RuntimeError(
                f"không bấm được vào ô soạn ChatGPT: {str(e).splitlines()[0]} · "
                f"{self._trang_thai_o_soan()} · {page.url}") from e
        try:
            editor.fill(prompt)
        except Exception:
            page.keyboard.insert_text(prompt)
        time.sleep(0.5)
        page.keyboard.press("Enter")
        time.sleep(0.5)
        # `.first` là BẮT BUỘC, không phải cho gọn: locator trần ở chế độ strict
        # sẽ NÉM LỖI khi trang có 2 nút gửi (khung cũ chưa gỡ) — và ném ngay ở
        # `is_visible()`, ngoài mọi try/except.
        nut_gui = page.locator(SELECTORS["send_button"]).filter(visible=True).first
        try:
            if nut_gui.is_visible():
                nut_gui.click(timeout=1000)
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
                JS_DOWNLOAD, src)
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
                JS_DOWNLOAD_2, src)
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
