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
from .dom_grok import (
    DAU_TRANG_POST, JS_CHAN_DOAN, JS_CHU_TRONG_O_SOAN, JS_CLICK_LUOT_MOI,
    JS_CLICK_RADIO, JS_CLICK_TEXT, JS_CO_MODE_VIDEO, JS_CO_NUT_GUI,
    JS_DAT_TEN_TAB, JS_DAU_VET_PHIEN, JS_DONG_DAU_VIDEO_CU, JS_HET_CREDIT, JS_NUT_DANG_CO,
    JS_RADIO_DA_CHON, JS_VIDEO_THAT, NHOM_PHAN_GIAI, NHOM_THOI_LUONG,
    SELECTORS, URL_IMAGINE, loi_mang,
)

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

    URL = URL_IMAGINE

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
            ma = loi_mang(e)
            self.logger.warning(
                "Không nối được Grok qua CDP (%s)%s — chạy thủ công.", str(e)[:120],
                f" · LỖI MẠNG {ma}: chữa ở tầng Chrome/mạng, không phải selector" if ma else "")
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
                    pg.evaluate(JS_DAT_TEN_TAB, tag)
                    return pg
        pg = self._ctx.new_page()
        pg.goto(self.URL, wait_until="domcontentloaded")
        pg.evaluate(JS_DAT_TEN_TAB, tag)
        return pg

    def _ensure_ready(self) -> bool:
        """Trang imagine có ô nhập ('Ask Grok anything'). Cloudflare/chưa login → nhờ người."""
        for _ in range(3):
            try:
                title = (self.page.title() or "").lower()
                if "just a moment" in title:
                    raise RuntimeError("cloudflare")
                self.page.wait_for_selector(SELECTORS["composer"], timeout=12000)
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
        return bool(self.page.evaluate(JS_CLICK_TEXT, label))

    def _click_radio(self, name: str) -> bool:
        """Click nút role=radio theo aria-label HOẶC text (mode Video/Image là icon
        chỉ có aria-label; 480p/720p/6s/10s có text)."""
        return bool(self.page.evaluate(JS_CLICK_RADIO, name))

    def _chot_radio(self, name: str, nhom: list, giay: float = 10) -> bool:
        """Bấm chip rồi KIỂM LẠI THEO HIỆN TRẠNG, không theo ý định.

        Mặc định của Grok là 10s/720p. Bấm "6s" mà trượt — nút chưa dựng xong,
        hoặc upload ảnh làm Grok dựng lại hàng chip và reset về mặc định — thì
        clip ra 10s: không lỗi, không log, chỉ có hoá đơn dài hơn và một clip sai
        thời lượng nằm trong versions/. Đúng thứ user bắt được 2026-08-12.
        """
        het = time.time() + giay
        lan = 0
        while time.time() < het:
            lan += 1
            self._click_radio(name)
            time.sleep(0.6)
            try:
                dang = self.page.evaluate(JS_RADIO_DA_CHON, nhom)
            except Exception:
                dang = ""
            if dang == name:
                if lan > 1:
                    self.logger.info("Grok: chốt được %s ở lần bấm thứ %d", name, lan)
                return True
            time.sleep(0.4)
        try:
            dang = self.page.evaluate(JS_RADIO_DA_CHON, nhom)
        except Exception:
            dang = "(không đọc được)"
        self.logger.warning(
            "Grok: KHÔNG chốt được chip %r sau %.0fs — đang chọn %r. Clip sẽ ra "
            "theo %r chứ không phải %r. %s", name, giay, dang, dang, name,
            self._chan_doan())
        return False

    def _cho_radio(self, name: str, giay: float = 20) -> bool:
        """Chờ nút xuất hiện rồi mới bấm. Grok là SPA: sau goto, hàng nút mất vài
        giây mới dựng — chạy nhiều tab song song thì càng lâu. sleep cứng là sai."""
        het = time.time() + giay
        while time.time() < het:
            if self._click_radio(name):
                return True
            time.sleep(0.5)
        return False

    def _nut_dang_co(self) -> str:
        """Liệt kê nút đang hiện — để thông báo lỗi nói được MÀN HÌNH ĐANG Ở ĐÂU."""
        try:
            return ", ".join(self.page.evaluate(JS_NUT_DANG_CO))
        except Exception as e:
            # Đọc không được cũng phải nói VÌ SAO. "(không đọc được)" trơ trọi là
            # đúng thứ làm mọi báo lỗi bên dưới thành vô dụng: tab crash, trang
            # trắng, hay CDP đứt đều ra chung một câu.
            return f"(không đọc được: {str(e)[:60]})"

    def _chan_doan(self) -> str:
        """Một dòng mô tả ĐẦY ĐỦ hiện trạng tab — đính vào MỌI lỗi của executor.

        Có URL · ngôn ngữ giao diện · ô soạn · nút gửi · mode Video · nút mở lượt
        mới · số video · danh sách nút. Đủ để phân biệt ba ca trông giống hệt
        nhau trong log cũ: kẹt trang post · Grok đổi giao diện · tab chết.
        """
        try:
            d = self.page.evaluate(JS_CHAN_DOAN)
        except Exception as e:
            return f"không đọc được hiện trạng ({str(e)[:70]})"
        return (f"URL {str(d.get('url'))[:70]} · lang={d.get('lang') or '?'} · "
                f"ô soạn {d.get('o_soan')} · nút gửi {d.get('nut_gui')} · "
                f"mode Video {'CÓ' if d.get('co_mode_video') else 'KHÔNG'} · "
                f"lượt mới {d.get('co_luot_moi') or 'không có'} · "
                f"{d.get('so_video')} video | nút: {', '.join(d.get('nut') or [])[:140]}")

    def _thay_tab(self) -> bool:
        """Đóng tab đang kẹt, mở tab TRẮNG khác trên cùng cửa sổ Chrome.

        Đường thoát cuối khi SPA cứ dựng lại lượt cũ: state đó sống trong tab,
        nên đổi tab là mất sạch. Cookie đăng nhập nằm ở profile Chrome nên tab
        mới vẫn đăng nhập — KHÔNG đụng gì tới cookie hay localStorage của phiên,
        vì xoá nhầm là đăng xuất và board không được phép đăng nhập lại.

        KHÔNG đi qua `_tim_tab()`: hàm đó cho slot 0 "nhận nuôi" một tab grok
        chưa đánh dấu, mà tab đó rất có thể chính là tab đang kẹt của user.
        """
        if self._ctx is None:
            return False
        tag = f"{_TAG}{self.slot}"
        cu = self.page
        try:
            pg = self._ctx.new_page()
            pg.evaluate(JS_DAT_TEN_TAB, tag)
        except Exception as e:
            self.logger.warning("Grok: không mở được tab thay thế (%s)", str(e)[:80])
            return False
        self.page = pg
        try:
            if cu is not None and not cu.is_closed():
                cu.evaluate(JS_DAT_TEN_TAB, "")   # nhả dấu, khỏi bị nhận lại
                cu.close()
        except Exception:
            pass
        self.logger.info("Grok: tab cũ kẹt ở lượt cũ → đã thay bằng tab mới (%s)", tag)
        return True

    def _ve_trang_imagine(self) -> bool:
        """Đưa tab về ĐÚNG trang /imagine. Trang post KHÔNG có nút mode 'Video'
        (nó chỉ có 'Make video'), nên đứng nhầm trang là hỏng cả job.

        HAI ĐƯỜNG VỀ, thử lần lượt — bản cũ chỉ có đường thứ nhất nên tab kẹt ở
        trang post của video TRƯỚC là chết cả job, đúng triệu chứng "chạy được
        vài video rồi lỗi liên tục":
          1. `goto` — nhanh, nhưng Grok là SPA và hay khôi phục phiên cũ, kéo tab
             ngược về /imagine/post/ ngay sau khi tải xong.
          2. BẤM NÚT 'New Generation' — đi đúng luồng của chính giao diện, nên
             không bị khôi phục đè. Đây là đường thoát thật khi (1) trượt.

          3. THAY TAB — đóng tab đang kẹt, mở tab trắng khác trên CÙNG cửa sổ.
             Đây là đường chữa cho ca user báo 2026-08-14: "cứ treo ở một link
             tạo video/ảnh cũ, reload xong cũng quay lại đó". Hai đường trên đều
             thao tác TRÊN CHÍNH cái tab đã kẹt, nên mọi thứ SPA giữ trong bộ nhớ
             tab (route đang xem, state của app) vẫn còn nguyên và nó dựng lại
             đúng trang cũ. Tab mới không mang theo thứ gì trong số đó, mà cookie
             đăng nhập nằm ở profile nên vẫn đăng nhập — không phải làm gì thêm.

        Lỗi MẠNG được tách riêng: ERR_QUIC_PROTOCOL_ERROR và họ hàng không phải
        chuyện selector, thử lại bao nhiêu lần cũng vô ích nếu không chữa đúng
        chỗ — nên nó được nêu đích danh trong log kèm cách chữa.
        """
        ma_mang = ""
        for lan in range(3):
            # Lượt 2 (lượt cuối): đổi hẳn tab trước khi thử lại. Lượt 1: thêm một
            # tham số vô hại vào URL — SPA khôi phục route theo đường dẫn, query
            # lạ thường đủ để nó dựng trang trắng thay vì kéo lại lượt cũ.
            dich = self.URL
            if lan == 1:
                dich = f"{self.URL}?gp={int(time.time())}"
            elif lan == 2 and self._thay_tab():
                dich = self.URL
            try:
                self.page.goto(dich, wait_until="domcontentloaded")
            except Exception as e:
                ma = loi_mang(e)
                if ma:
                    ma_mang = ma
                    self.logger.warning(
                        "Grok: LỖI MẠNG %s ở lượt %d/3 — Chrome không với tới "
                        "grok.com. Đây KHÔNG phải lỗi giao diện: chữa bằng cách mở "
                        "lại Chrome debug (board thêm cờ --disable-quic từ "
                        "2026-08-12), hoặc kiểm mạng/VPN.", ma, lan + 1)
                else:
                    self.logger.warning("Grok: goto lần %d hỏng (%s)", lan + 1, str(e)[:70])
            for _ in range(24):                      # chờ tối đa ~12s cho SPA dựng
                time.sleep(0.5)
                try:
                    if DAU_TRANG_POST in (self.page.url or ""):
                        break                        # SPA nhảy lại post → thử đường 2
                    if self.page.evaluate(JS_CO_MODE_VIDEO):
                        return True
                except Exception:
                    pass
            # ĐƯỜNG 2 — bấm nút mở lượt mới ngay trên trang post đang kẹt.
            try:
                ten = self.page.evaluate(JS_CLICK_LUOT_MOI)
            except Exception as e:
                ten = ""
                self.logger.warning("Grok: không bấm được nút mở lượt mới (%s)",
                                    str(e)[:70])
            if ten:
                self.logger.info("Grok: kẹt ở trang post → bấm '%s' (lượt %d/3)",
                                 ten, lan + 1)
                for _ in range(20):                  # ~10s cho SPA dựng lại
                    time.sleep(0.5)
                    try:
                        if self.page.evaluate(JS_CO_MODE_VIDEO):
                            return True
                    except Exception:
                        pass
            # CHỤP DẤU VẾT PHIÊN khi kẹt. Không có nó thì lần sau vẫn chỉ có mỗi
            # câu "chưa về được trang soạn" và lại phải ngồi đoán Grok nhớ lượt
            # cũ ở đâu.
            try:
                _dv = self.page.evaluate(JS_DAU_VET_PHIEN)
                self.logger.warning(
                    "Grok: kẹt — url=%s · sessionStorage[%s] · localStorage[%s]",
                    (_dv.get("url") or "")[:90], ",".join(_dv.get("ss") or []) or "-",
                    ",".join(_dv.get("ls") or []) or "-")
            except Exception:
                pass
            self.logger.warning("Grok: chưa về được trang soạn (lượt %d/3) — %s",
                                lan + 1, self._chan_doan())
        if ma_mang:
            self.logger.warning(
                "Grok: bỏ cuộc sau 3 lượt, nguyên nhân gốc là LỖI MẠNG %s "
                "(không phải selector).", ma_mang)
        return False

    def _bam_submit(self, giay: float = 15) -> bool:
        """Bấm nút gửi — ĐÚNG MỘT LẦN, không bao giờ bấm lại.

        ⛔ CẤM THÊM ĐƯỜNG THỬ LẠI VÀO ĐÂY (luật user đặt 2026-08-09).
        Bấm gửi xong trang nhảy sang /imagine/post/ và Grok hay ĐƠ vài giây mới
        phản hồi, nên Playwright có thể ném lỗi DÙ CÚ BẤM ĐÃ ĂN. Bản trước có
        đường dự phòng: gặp đúng cảnh đó là bấm lần hai → Grok render hai clip,
        trừ hai lượt credit, và bản thứ hai đi lúc ô soạn đã bị xoá nên KHÔNG
        mang prompt (chính là clip "nói linh tinh" user thấy).

        Thực tế đo được: hầu như cú bấm nào Grok cũng nhận. Nên đánh đổi ở đây
        là CỐ Ý — thà một lần hiếm hoi trượt rồi chết ở bước chờ render (mất
        thời gian, không mất tiền) còn hơn bấm chồng (mất tiền thật).

        Chọn nút: ưu tiên tên 'Submit' như bản đã chạy ổn trên git; không thấy
        thì lấy `button[type=submit]` để còn chạy được khi giao diện đổi sang
        tiếng khác. Cả hai đều chỉ ra MỘT cú bấm.

        Phân biệt HAI ca hỏng — trước đây gộp làm một nên ca đầu bị treo oan:
          · KHÔNG TÌM RA NÚT  → chắc chắn chưa gửi gì → trả False, chết ngay.
          · TÌM RA nhưng click ném lỗi → cú bấm CÓ THỂ đã ăn → trả True, để
            bước chờ post-mới phán quyết. Tuyệt đối không bấm lại.
        """
        nut = None
        try:
            ten = self.page.get_by_role("button", name="Submit").first
            if ten.count():
                nut = ten
            else:
                kieu = self.page.locator("button[type=submit]").first
                if kieu.count():
                    nut = kieu
        except Exception as e:
            self.logger.warning("Grok: dò nút gửi hỏng (%s)", str(e)[:80])

        if nut is None:
            # Không có nút nào để bấm → KHÔNG hề gửi đi. Báo hỏng luôn cho thợ
            # chuyển việc, đừng ôm trọn gen_timeout rồi mới kêu "hết giờ render".
            self.logger.warning(
                "Grok: KHÔNG thấy nút gửi — coi như chưa gửi. URL: %s | Nút: %s",
                (self.page.url or "")[:60], self._nut_dang_co()[:110])
            return False

        try:
            # Chờ rộng: đơ vài giây là chuyện thường, chờ hẹp thì báo hỏng oan.
            nut.click(timeout=max(15000, int(giay * 1000)))
            return True
        except Exception as e:
            self.logger.warning(
                "Grok: bấm gửi báo lỗi (%s) — KHÔNG bấm lại, để bước chờ post mới "
                "phán. Nút đang thấy: %s", str(e)[:90], self._nut_dang_co()[:110])
            return True

    def _out_of_credits(self) -> bool:
        try:
            return bool(self.page.evaluate(JS_HET_CREDIT))
        except Exception:
            return False

    # Chỉ tính KHUNG PHÁT THẬT, bỏ thumbnail thanh bên. Đo 2026-08-09: trang
    # /imagine/post/ kèm một dãy video cũ 50×50 ở thanh bên, bản thật ~1131×644.
    # Không lọc thì hai chuyện xảy ra cùng lúc: (1) log báo "Grok trả về 2-3
    # clip" trong khi thật ra chỉ có một, (2) `new[-1]` bốc trúng thumbnail của
    # video CŨ và board tải nhầm bản — sai kiểu đó hoàn toàn im lặng.

    def _video_srcs(self) -> list[str]:
        return [v["src"] for v in self.page.evaluate(JS_VIDEO_THAT)]

    # ------------------------------------------------------------------
    def generate(self, prompt: str, image_path: str, out_path: str,
                 duration_s: float = 10.0, duong_them=None, nen_dung=None) -> bool:
        """Tạo video image-to-video, lưu mp4 ra out_path.

        MỘT submit của Grok đẻ ra NHIỀU clip (đo 2026-08-09: một lần bấm ra 3
        bản), và mỗi bản trừ một lượt credit. Trước đây chỉ giữ bản cuối rồi
        vứt phần còn lại — tiền đã tiêu mà không có gì để so.

        `duong_them` là hàm không tham số, gọi một lần trả về một đường dẫn mới
        để lưu bản THỪA (board truyền `BOARD.next_vversion`). Không truyền thì
        giữ nguyên hành vi cũ: chỉ lấy một bản.

        `nen_dung` là hàm không tham số trả bool — board truyền cờ "user bấm
        dừng riêng". CHỈ SOI TRƯỚC KHI SUBMIT. Sau submit thì credit đã bị trừ
        rồi, bỏ ngang là mất tiền mà không có clip: lượt đó cứ chạy nốt và lưu
        về, còn cờ dừng chặn lượt SAU."""
        page = self.page
        if nen_dung and nen_dung():
            self.logger.info("Grok: user bấm dừng trước khi submit — không tiêu credit")
            return False
        dur_label = "10s" if duration_s >= 8 else "6s"

        # CHỌN MODE TRƯỚC, UPLOAD SAU — thứ tự này quan trọng.
        # Mọi nút (Image/Video · 480p/720p/1080p · 6s/10s/15s) đều có sẵn trên trang
        # /imagine TRỐNG. Bấm chúng trước rồi mới upload thì khe hở để tab trôi sang
        # trang post gần như bằng không. Làm ngược lại (upload trước) là bug đã gặp:
        # chạy nhiều tab song song, tab nào chậm chân là bị đẩy sang /imagine/post/…
        # và ở đó KHÔNG có nút mode 'Video', chỉ có 'Make video'.
        xong = False
        for lan in range(3):
            if not self._ve_trang_imagine():
                raise C.ExecutorError(
                    "Không về được trang grok.com/imagine sau 3 lượt (goto lẫn nút "
                    f"'New Generation' đều không đưa tab về trang soạn). {self._chan_doan()}")
            self._dismiss_popups()

            if not self._cho_radio("Video", 15):
                self.logger.warning("Grok: chưa thấy nút mode 'Video' (lượt %d/3)", lan + 1)
                continue
            self._chot_radio(self.resolution, NHOM_PHAN_GIAI, 8)
            self._chot_radio(dur_label, NHOM_THOI_LUONG, 8)

            page.locator(SELECTORS["file_input"]).first.set_input_files(image_path)
            time.sleep(4)

            if DAU_TRANG_POST in (page.url or ""):
                # Tab bị đẩy sang trang post giữa chừng — làm lại từ đầu, đừng cố chữa
                self.logger.warning("Grok: tab trôi sang trang post sau khi upload "
                                    "(lượt %d/3), làm lại", lan + 1)
                continue
            # UPLOAD DỰNG LẠI HÀNG CHIP và Grok reset về mặc định 10s — nên đây
            # KHÔNG phải "bấm lại cho chắc" mà là cú bấm quyết định. Phải chốt
            # bằng aria-checked, bấm suông rồi đi tiếp là ra clip sai thời lượng.
            if not self._chot_radio(dur_label, NHOM_THOI_LUONG, 10):
                self.logger.warning(
                    "Grok: bỏ qua và gửi tiếp — clip có thể dài hơn %s đã xin.", dur_label)

            # DỌN Ô SOẠN TRƯỚC KHI GÕ. Tab dùng lại cho việc kế tiếp vẫn còn
            # nguyên prompt của lượt trước (thấy trên UI 2026-08-09) — gõ chồng
            # lên là prompt mới dính đuôi prompt cũ, model đọc ra một thứ lai.
            try:
                page.locator(SELECTORS["composer"]).last.click()
                page.keyboard.press("Meta+A")
                page.keyboard.press("Backspace")
                time.sleep(0.3)
            except Exception as e:
                self.logger.warning("Grok: không dọn được ô soạn (%s)", str(e)[:70])

            # CHỐT CUỐI TRƯỚC KHI GÕ: phải ĐANG Ở /imagine và PHẢI THẤY nút gửi.
            # Trang post không có nút này — trước đây code cứ thế gõ rồi bấm vào
            # hư không, hết 15s timeout, job treo tới lúc hết giờ render. Kiểm ở
            # đây thì còn nằm trong vòng lặp, làm lại sạch từ đầu được.
            if DAU_TRANG_POST in (page.url or "") or not page.evaluate(JS_CO_NUT_GUI):
                self.logger.warning(
                    "Grok: chưa về đúng trang soạn (lượt %d/3) — URL %s · nút: %s",
                    lan + 1, (page.url or "")[:55], self._nut_dang_co()[:90])
                continue
            xong = True
            break
        if not xong:
            raise C.ExecutorError(
                "Không về được trang soạn có nút gửi sau 3 lượt (tab hay kẹt lại "
                f"trang kết quả của video trước). {self._chan_doan()}")

        # hết credit -> fail nhanh, không chờ 10 phút vô ích
        if self._out_of_credits():
            raise C.ExecutorError("Grok đã dùng 100% credit — không tạo được video.")

        # ⚠ ĐỪNG nhận clip chỉ vì "src chưa từng thấy". Trang post giữ SẴN một
        # thẻ <video> cỡ lớn có src RỖNG (biến thể thứ hai chưa nạp) — nó không
        # lọt vào ảnh chụp `before`, vài giây sau src nạp xong là bị chấm nhầm
        # thành clip mới. Trên tab dùng lại, cái đó là clip của LƯỢT TRƯỚC:
        # board tải video shot cũ gán cho shot mới, im lặng tuyệt đối.
        # Neo đúng theo ID POST: chỉ clip nằm trong post do CHÍNH lượt này mở ra
        # mới được nhận.
        before = set(self._video_srcs())
        # ĐÓNG DẤU mọi <video> đang có — kể cả cái src RỖNG. Sau submit chỉ nhận
        # thẻ KHÔNG mang dấu. Đây là thứ duy nhất phân biệt được "biến thể chưa
        # nạp của lượt TRƯỚC" với "clip của lượt NÀY": so theo src thì cái rỗng
        # lọt lưới, so theo URL post thì hụt vì Grok render tại chỗ không đổi URL.
        try:
            page.evaluate(JS_DONG_DAU_VIDEO_CU)
        except Exception as e:
            self.logger.warning("Grok: không đóng dấu được video cũ (%s)", str(e)[:70])

        # prompt + submit
        ed = page.locator(SELECTORS["composer"]).last
        ed.click()
        page.keyboard.insert_text(prompt)
        time.sleep(0.5)
        # Gõ xong phải THẤY CHỮ MÌNH VỪA GÕ. Ô soạn mất focus hoặc trang vừa
        # dựng lại thì insert_text rơi vào hư không, submit đi tay không và
        # Grok tự bịa nội dung — hỏng câm, không lỗi nào nổ ra.
        try:
            trong_o = page.evaluate(JS_CHU_TRONG_O_SOAN)
            if trong_o < min(40, len(prompt)):
                raise C.ExecutorError(
                    f"Prompt không vào được ô soạn (ô đang có {trong_o} ký tự, "
                    f"prompt {len(prompt)}). {self._chan_doan()}")
        except C.ExecutorError:
            raise
        except Exception:
            pass
        # CỬA CUỐI TRƯỚC KHI TIÊU TIỀN. Từ dòng dưới trở đi credit đã trừ, nên
        # đây là chỗ cuối cùng cờ dừng còn cứu được gì.
        if nen_dung and nen_dung():
            self.logger.info("Grok: user bấm dừng ngay trước submit — không tiêu credit")
            return False
        if not self._bam_submit(15):
            raise C.ExecutorError(f"Không bấm được nút gửi. {self._chan_doan()}")
        self.logger.info("Grok: đã submit, chờ render...")

        # ⛔ ĐỪNG BẮT TRANG PHẢI NHẢY SANG POST MỚI. Đã thử 2026-08-09 và HỎNG:
        # tab đang đứng sẵn ở một trang post thì Grok render TẠI CHỖ, URL không
        # đổi — job báo "không mở post mới" trong khi clip đã render xong, mất
        # trắng credit. Danh tính lượt lấy bằng DẤU trên thẻ <video>, không lấy
        # bằng URL.
        deadline = time.time() + self.gen_timeout
        vid_src = None
        du: list[str] = []          # các bản THỪA cùng một lượt submit
        while time.time() < deadline:
            time.sleep(5)
            try:
                infos = page.evaluate(JS_VIDEO_THAT)
                new = [v for v in infos
                       if not v["cu"] and v["src"] and v["src"] not in before
                       and v["dur"] and v["dur"] >= 3]
                if new:
                    # Grok trả 2 biến thể cho một submit (nút Thumbnail 1/2 trên
                    # trang post), cả hai đều đã trừ credit — giữ hết để user so.
                    if len(new) > 1:
                        self.logger.info(
                            "Grok trả %d biến thể cho lượt này (đã trừ %d credit) "
                            "— giữ hết, bản thừa vào versions/", len(new), len(new))
                    vid_src = new[0]["src"]
                    du = [v["src"] for v in new[1:]]
                    break
            except Exception:
                pass
        if not vid_src:
            raise C.ExecutorError(
                f"Hết {int(self.gen_timeout)}s chờ Grok render. {self._chan_doan()}")
        self.logger.info(f"Grok: video xong ({vid_src[:70]}...), đang tải")

        data = self._tai_ve(vid_src)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(data)

        # Bản THỪA của cùng lượt submit: đã trả tiền rồi, lưu lại để user chọn.
        # Hỏng ở đây KHÔNG được làm hỏng cả job — bản chính đã nằm trên đĩa.
        for i, src in enumerate(du, 1):
            if not duong_them:
                break
            try:
                p2 = duong_them()
                with open(p2, "wb") as f:
                    f.write(self._tai_ve(src))
                self.logger.info("Grok: lưu thêm bản %d → %s", i, os.path.basename(p2))
            except Exception as e:
                self.logger.warning("Grok: bỏ bản thừa %d (%s)", i, str(e)[:90])
        return True

    def _tai_ve(self, src: str) -> bytes:
        """Tải một clip. CDN của Grok hay chậm hoặc ngắt giữa chừng nên timeout
        rộng và thử lại vài lần — video đã render xong, hỏng ở bước tải mà bỏ
        luôn thì rất phí."""
        last_err = None
        for attempt in range(1, 5):
            try:
                resp = self._ctx.request.get(src, timeout=180_000)
                if not resp.ok:
                    raise C.ExecutorError(f"Tải video lỗi HTTP {resp.status}.")
                body = resp.body()
                if len(body) < 100_000:
                    raise C.ExecutorError(f"Video tải về quá nhỏ ({len(body)} bytes).")
                return body
            except Exception as e:
                last_err = e
                self.logger.warning(
                    "Grok: tải video hỏng (lần %d/4): %s", attempt, str(e)[:120])
                if attempt < 4:
                    time.sleep(3 * attempt)
        raise C.ExecutorError(f"Tải video thất bại sau 4 lần thử: {str(last_err)[:200]}")

    def close(self) -> None:
        # (bỏ 2026-08-12) chỗ này từng `with _CLAIM_LOCK: pass` — tàn dư của cơ
        # chế giữ chỗ đã xoá. Khối rỗng nên không làm gì, nhưng cái tên thì không
        # còn tồn tại: mỗi lần đóng phiên Grok là một NameError nuốt vào except.
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
