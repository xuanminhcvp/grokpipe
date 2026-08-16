"""Chọn chế độ (Instant · Medium · High) phải SỐNG SÓT khi ChatGPT đổi ngôn ngữ.

Ca thật 2026-08-15: tài khoản để giao diện tiếng Việt hiện nút "Tức thì", bản cũ
dò bằng regex `^(Instant|Medium|High)` nên đọc ra chuỗi rỗng, `_chon_che_do`
thoát ngay ở dòng đầu và CẢ BUỔI RENDER chạy ở Instant — Instant gói cả lô vào
MỘT ảnh ghép lưới, board đếm 1 ảnh cho N prompt rồi vứt cả lô. Log chỉ có đúng
một dòng "không đọc được nút chế độ".

Trang giả ở đây bắt chước đúng DOM đã đo trên UI thật (xem hộp thoại của
`composer-intelligence-picker-content`): nút pill mang `aria-haspopup=menu`, mở
ra một THANH TRƯỢT `role=slider` với `aria-valuenow` 0/1/2 — và nhãn thì dịch.
"""
import logging
import re

import pytest

from grokpipe.executors.dom_chatgpt import JS_DOC_NAC, JS_NHAN_CHE_DO, SELECTORS
from grokpipe.executors.image_chatgpt import ChatGPTSession

NHAN = {
    "vi": {0: "Tức thì", 1: "Vừa", 2: "Cao"},
    "en": {0: "Instant", 1: "Medium", 2: "High"},
}


class FakeLocator:
    def __init__(self, page, hien: bool, bam=None):
        self.page = page
        self.hien = hien
        self._bam = bam

    @property
    def first(self):
        return self

    def filter(self, **kw):
        return self

    def is_visible(self, timeout=None):
        return self.hien

    def click(self, timeout=None):
        if not self.hien:
            raise RuntimeError("locator không hiện")
        if self._bam:
            self._bam()


class FakeKeyboard:
    def __init__(self, page):
        self.page = page

    def press(self, key):
        p = self.page
        if key == "Escape":
            p.menu = False
        elif p.menu and key == "ArrowRight":
            p.nac = min(p.nac + 1, p.toida)
        elif p.menu and key == "ArrowLeft":
            p.nac = max(p.nac - 1, 0)


class FakePage:
    """Giao diện THANH TRƯỢT (2026-08) — nhãn theo `lang`."""

    url = "https://chatgpt.com/c/test"

    def __init__(self, lang="vi", nac=0, toida=2, co_pill=True):
        self.lang, self.nac, self.toida = lang, nac, toida
        self.co_pill = co_pill
        self.menu = False
        self.keyboard = FakeKeyboard(self)

    # -- những gì code thật gọi ------------------------------------------
    def evaluate(self, js, *a):
        if js is JS_NHAN_CHE_DO:
            return NHAN[self.lang][self.nac] if self.co_pill else ""
        if js is JS_DOC_NAC:
            return {"nac": self.nac, "toida": self.toida} if self.menu else None
        raise AssertionError(f"đoạn JS lạ: {js[:40]}")

    def locator(self, sel):
        if sel in (SELECTORS["mode_pill"], SELECTORS["mode_pill_alt"]):
            return FakeLocator(self, self.co_pill, self._mo_menu)
        if sel == "[role=slider]":
            return FakeLocator(self, self.menu)
        if "radix-menu-content" in sel:
            return FakeLocator(self, self.menu)
        if sel == "form button":
            return FakeLocator(self, False)
        raise AssertionError(f"selector lạ: {sel}")

    def _mo_menu(self):
        self.menu = not self.menu


class FakePageRadio(FakePage):
    """Giao diện CŨ: menu ba mục role=menuitemradio, không có thanh trượt."""

    def evaluate(self, js, *a):
        if js is JS_DOC_NAC:
            return None                      # kiểu cũ KHÔNG có thanh trượt
        return super().evaluate(js, *a)

    def get_by_role(self, role, name=None):
        assert role == "menuitemradio"
        dich = next((n for n, nhan in NHAN[self.lang].items()
                     if name.match(nhan)), None)

        def chon():
            if dich is None:
                raise RuntimeError("không có mục khớp")
            self.nac, self.menu = dich, False

        return FakeLocator(self, True, chon)


def phien(page):
    s = ChatGPTSession.__new__(ChatGPTSession)
    s.logger = logging.getLogger("test-che-do")
    s.page = page
    return s


@pytest.mark.parametrize("lang", ["vi", "en"])
def test_len_duoc_high_du_giao_dien_ngon_ngu_nao(lang):
    p = FakePage(lang=lang, nac=0)
    assert phien(p)._chon_che_do("High") == "High"
    assert p.nac == 2
    assert p.menu is False, "menu bỏ mở là che ô soạn, prompt gõ vào hư không"


@pytest.mark.parametrize("lang", ["vi", "en"])
def test_che_do_tot_nhat_tra_ve_high(lang):
    p = FakePage(lang=lang, nac=0)
    assert phien(p)._che_do_tot_nhat() == "High"
    assert p.nac == 2


def test_dang_dung_che_do_van_xac_nhan_bang_so():
    p = FakePage(lang="vi", nac=2)
    assert phien(p)._chon_che_do("High") == "High"
    assert p.nac == 2


def test_ha_xuong_medium_khi_tran_tai_khoan_chi_toi_1():
    """Trần thấp thì KHÔNG được báo thành công — `_che_do_tot_nhat` hạ Medium."""
    p = FakePage(lang="vi", nac=0, toida=1)
    assert phien(p)._chon_che_do("High") != "High"
    assert phien(p)._che_do_tot_nhat() == "Medium"
    assert p.nac == 1


def test_khong_thay_nut_thi_bao_rong_chu_khong_ngam_bao_xong():
    p = FakePage(lang="vi", nac=0, co_pill=False)
    assert phien(p)._chon_che_do("High") == ""
    assert p.nac == 0


@pytest.mark.parametrize("lang", ["vi", "en"])
def test_giao_dien_cu_menu_ba_muc_van_chay(lang):
    p = FakePageRadio(lang=lang, nac=0)
    assert phien(p)._chon_che_do("High") == "High"
    assert p.nac == 2


@pytest.mark.parametrize("che, chan", [
    ("High", False), ("Medium", False),
    ("Instant", True), ("", True),
])
def test_chi_instant_va_khong_doc_duoc_moi_bi_chan(che, chan):
    """Lô gửi ở Instant = đốt một lượt lấy về ảnh ghép lưới. Medium thì vẫn chạy."""
    ly_do = phien(FakePage())._chan_neu_che_do_kem(che)
    assert bool(ly_do) is chan
    if chan:
        assert "High/Medium" in ly_do        # câu báo phải nói rõ thiếu gì


def test_nhan_tieng_viet_khop_bi_danh():
    """Chốt bảng bí danh: thiếu một nhãn là lặp lại đúng lỗi 2026-08-15."""
    from grokpipe.executors.image_chatgpt import _BI_DANH, _RE_NHAN_CHE_DO
    for ten, nhan in (("Instant", "Tức thì"), ("Medium", "Vừa"), ("High", "Cao")):
        assert _BI_DANH[ten].match(nhan), f"{ten} không nhận ra nhãn {nhan!r}"
        assert re.match(_RE_NHAN_CHE_DO, nhan)
