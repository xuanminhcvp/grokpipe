"""Hạ số tab trên giao diện phải có tác dụng NGAY, không đợi khởi động lại board.

Trước đây vòng dọn của supervisor chỉ xoá khoá khỏi sổ `WORKERS`; `_worker` lại
chỉ tự thoát khi tài khoản rời pool hoặc bị đánh dấu chết, nên luồng thừa cứ chạy
và giữ nguyên tab của nó.
"""

import unittest
from pathlib import Path

from helpers import function_source, load_sfboard


ROOT = Path(__file__).resolve().parents[2]
BOARD_PATH = ROOT / "sfboard/sfboard.py"


def tk(**kw):
    a = {"id": "gpt-1", "kind": "img", "port": 9222, "tabs": 2, "enabled": True}
    a.update(kw)
    return a


class FakeCtx:
    def __init__(self, so_tab):
        self.pages = list(range(so_tab))


class FakePage:
    def __init__(self, so_tab_trong_cua_so=2, closed=False):
        self.context = FakeCtx(so_tab_trong_cua_so)
        self._closed = closed
        self.da_dong = False
        self.ten_da_nha = False

    def is_closed(self):
        return self._closed

    def evaluate(self, *_a):
        self.ten_da_nha = True

    def close(self):
        self.da_dong = True


class FakeSess:
    def __init__(self, page):
        self.page = page


class ChoNgoiTest(unittest.TestCase):
    def setUp(self):
        self.m = load_sfboard()
        self.acc_cu = self.m.ACCOUNTS

    def tearDown(self):
        self.m.ACCOUNTS = self.acc_cu
        for ten in ("sess", "gsess"):
            if hasattr(self.m._TL, ten):
                setattr(self.m._TL, ten, None)

    def dat_tk(self, *accs):
        self.m.ACCOUNTS = list(accs)
        return self.m._ep(accs[0])

    # ---- chỗ ngồi còn đúng không ---------------------------------------

    def test_slot_trong_dinh_muc_thi_giu(self):
        ep = self.dat_tk(tk(tabs=2))

        self.assertTrue(self.m._cho_ngoi_con_dung(ep, "img", 0))
        self.assertTrue(self.m._cho_ngoi_con_dung(ep, "img", 1))

    def test_slot_ngoai_dinh_muc_thi_nghi(self):
        ep = self.dat_tk(tk(tabs=2))

        self.assertFalse(self.m._cho_ngoi_con_dung(ep, "img", 2))

    def test_ha_so_tab_lam_slot_cu_thanh_thua(self):
        ep = self.dat_tk(tk(tabs=2))
        self.assertTrue(self.m._cho_ngoi_con_dung(ep, "img", 1))

        self.m.ACCOUNTS = [tk(tabs=1)]                    # user hạ 2 → 1

        self.assertFalse(self.m._cho_ngoi_con_dung(ep, "img", 1))

    def test_viec_kiem_nhiem_chi_giu_mot_cho(self):
        ep = self.dat_tk(tk(tabs=2))

        self.assertTrue(self.m._cho_ngoi_con_dung(ep, "vid", 0))
        self.assertFalse(self.m._cho_ngoi_con_dung(ep, "vid", 1))

    def test_bat_tai_khoan_grok_thi_thoi_kiem_nhiem(self):
        ep = self.dat_tk(tk(tabs=2), tk(id="grok-1", kind="vid", port=9300))

        self.assertFalse(self.m._cho_ngoi_con_dung(ep, "vid", 0))
        self.assertTrue(self.m._cho_ngoi_con_dung(ep, "img", 1))

    def test_tai_khoan_tat_hoac_khong_con_thi_nghi(self):
        ep = self.dat_tk(tk(tabs=2))
        self.m.ACCOUNTS = [tk(tabs=2, enabled=False)]
        self.assertFalse(self.m._cho_ngoi_con_dung(ep, "img", 0))

        self.m.ACCOUNTS = []
        self.assertFalse(self.m._cho_ngoi_con_dung(ep, "img", 0))

    # ---- đóng tab: hai chốt an toàn -------------------------------------

    def test_slot_0_khong_bao_gio_dong_tab(self):
        page = FakePage()
        self.m._TL.sess = FakeSess(page)

        self.m._dong_tab_cho_ngoi(0)

        self.assertFalse(page.da_dong, "tab slot 0 thường là tab DUY NHẤT của cửa sổ")

    def test_khong_dong_tab_cuoi_cung_cua_cua_so(self):
        page = FakePage(so_tab_trong_cua_so=1)
        self.m._TL.sess = FakeSess(page)

        self.m._dong_tab_cho_ngoi(1)

        self.assertFalse(page.da_dong, "đóng tab cuối là tắt Chrome, mất phiên đăng nhập")

    def test_dong_dung_tab_thua_va_nha_dau_cho_ngoi(self):
        page = FakePage(so_tab_trong_cua_so=3)
        self.m._TL.sess = FakeSess(page)

        self.m._dong_tab_cho_ngoi(1)

        self.assertTrue(page.da_dong)
        self.assertTrue(page.ten_da_nha, "phải xoá window.name, không thì tab sau nhận nhầm chỗ")

    def test_dong_ca_tab_chatgpt_lan_grok(self):
        cg, gp = FakePage(so_tab_trong_cua_so=4), FakePage(so_tab_trong_cua_so=4)
        self.m._TL.sess, self.m._TL.gsess = FakeSess(cg), FakeSess(gp)

        self.m._dong_tab_cho_ngoi(1)

        self.assertTrue(cg.da_dong and gp.da_dong)

    def test_tab_da_dong_hoac_thieu_phien_khong_gay_loi(self):
        self.m._TL.sess = FakeSess(FakePage(closed=True))
        self.m._TL.gsess = None

        self.m._dong_tab_cho_ngoi(1)          # không được ném

    # ---- ràng buộc trong `_worker` -------------------------------------

    def test_worker_soi_cho_ngoi_giua_hai_viec(self):
        nguon = function_source(BOARD_PATH, "_worker")
        vi_tri = nguon.index("if not _cho_ngoi_con_dung(endpoint, kind, slot):")

        self.assertLess(vi_tri, nguon.index("QUEUE.get") if "QUEUE.get" in nguon else len(nguon),
                        "phải soi TRƯỚC khi nhấc việc, không bỏ dở việc đang chạy")
        self.assertIn("_dong_tab_cho_ngoi(slot)", nguon)
        self.assertIn("_release_tl()", nguon)


if __name__ == "__main__":
    unittest.main()
