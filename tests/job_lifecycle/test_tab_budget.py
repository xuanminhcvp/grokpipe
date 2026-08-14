"""Số tab user đặt chỉ áp cho VIỆC CHÍNH của tài khoản.

Lỗi thật 2026-08-14: cả 3 tài khoản đều `kind=img`, `tabs=2`, và không có tài
khoản Grok nào bật → thợ ảnh kiêm luôn video → số tab bị nhân cho cả hai loại
việc, Chrome mở 4 tab (`cgslot0/1` + `gpslot0/1`) thay vì 2. RAM nhân đôi, đúng
thứ đẩy máy tới "Aw, Snap!".
"""

import unittest
from pathlib import Path

from helpers import function_source, load_sfboard


ROOT = Path(__file__).resolve().parents[2]
BOARD_PATH = ROOT / "sfboard/sfboard.py"


class TabBudgetTest(unittest.TestCase):
    def setUp(self):
        self.m = load_sfboard()

    def tk(self, **kw):
        a = {"id": "gpt-1", "kind": "img", "port": 9222, "tabs": 2}
        a.update(kw)
        return a

    def test_viec_chinh_duoc_dung_so_tab_user_dat(self):
        self.assertEqual(self.m._so_tab_theo_viec(self.tk(tabs=2), "img"), 2)
        self.assertEqual(self.m._so_tab_theo_viec(self.tk(tabs=3), "img"), 3)

    def test_viec_kiem_nhiem_chi_duoc_mot_tab(self):
        self.assertEqual(self.m._so_tab_theo_viec(self.tk(tabs=2), "vid"), 1)
        self.assertEqual(self.m._so_tab_theo_viec(self.tk(tabs=4), "vid"), 1)

    def test_tong_tab_cua_mot_cua_so_khong_vuot_so_dat_cong_mot(self):
        """Đây là con số user nhìn thấy trên Chrome."""
        for tabs in (1, 2, 3, 4):
            a = self.tk(tabs=tabs)
            tong = self.m._so_tab_theo_viec(a, "img") + self.m._so_tab_theo_viec(a, "vid")
            self.assertEqual(tong, tabs + 1, f"tabs={tabs} phải ra {tabs}+1 tab, không phải {tabs}*2")

    def test_co_tai_khoan_grok_rieng_thi_dung_bang_so_user_dat(self):
        """Hết kiêm nhiệm thì `kinds` chỉ còn một loại → đúng bằng số đã đặt."""
        a = self.tk(tabs=2)

        self.assertEqual(self.m._so_tab_theo_viec(a, a["kind"]), 2)

    def test_tai_khoan_grok_cung_theo_dung_luat(self):
        a = self.tk(kind="vid", tabs=2)

        self.assertEqual(self.m._so_tab_theo_viec(a, "vid"), 2)
        self.assertEqual(self.m._so_tab_theo_viec(a, "img"), 1)

    def test_so_tab_luon_nam_trong_khoang_hop_le(self):
        self.assertEqual(self.m._so_tab_theo_viec(self.tk(tabs=0), "img"), 1)
        self.assertEqual(self.m._so_tab_theo_viec(self.tk(tabs=None), "img"), 1)
        self.assertEqual(self.m._so_tab_theo_viec(self.tk(tabs=-3), "img"), 1)
        self.assertEqual(
            self.m._so_tab_theo_viec(self.tk(tabs=999), "img"), self.m.MAX_TABS
        )

    def test_supervisor_tinh_so_tab_theo_tung_loai_viec(self):
        nguon = function_source(BOARD_PATH, "_supervisor")

        self.assertIn("so_tab = _so_tab_theo_viec(a, k)", nguon)
        # phải nằm TRONG vòng `for k in kinds`, nếu không lại nhân cho mọi loại
        vi_tri_for = nguon.index("for k in kinds:")
        self.assertGreater(nguon.index("so_tab = _so_tab_theo_viec(a, k)"), vi_tri_for)
        # dọn luồng thừa cũng phải dùng đúng con số theo loại việc đó
        self.assertIn("x[2] >= so_tab", nguon)

    def test_thay_doi_khong_dung_toi_luat_kiem_nhiem(self):
        nguon = function_source(BOARD_PATH, "_supervisor")

        self.assertIn('if a["kind"] == "img" and not has_vid:', nguon)
        self.assertIn('kinds.append("vid")', nguon)


if __name__ == "__main__":
    unittest.main()
