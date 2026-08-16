"""Số tab user đặt chỉ áp cho VIỆC CHÍNH của tài khoản.

Lỗi thật 2026-08-14: cả 3 tài khoản đều `kind=img`, `tabs=2`, và không có tài
khoản Grok nào bật → thợ ảnh kiêm luôn video → số tab bị nhân cho cả hai loại
việc, Chrome mở 4 tab (`cgslot0/1` + `gpslot0/1`) thay vì 2. RAM nhân đôi, đúng
thứ đẩy máy tới "Aw, Snap!".
"""

import unittest
from pathlib import Path

from helpers import load_sfboard


ROOT = Path(__file__).resolve().parents[2]
BOARD_PATH = ROOT / "sfboard/sfboard.py"


class _LuongSong:
    """Bản giả của luồng thợ — phần sổ ghế chỉ hỏi `is_alive()`."""

    def is_alive(self):
        return True


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

    def test_ghe_duoc_cap_theo_TUNG_loai_viec_chu_khong_nhan_deu(self):
        """ĐẾM GHẾ THẬT, không tìm chuỗi trong mã.

        Bản cũ của test này khớp `"so_tab = _so_tab_theo_viec(a, k)"` trong thân
        `_supervisor` và so vị trí chuỗi để đoán nó nằm trong vòng `for k`. Nó
        vỡ ngay khi khối cấp ghế được TÁCH RA thành `_xep_ghe_cho_tai_khoan` —
        một thay đổi làm hành vi đúng hơn, không sai đi. Đếm ghế thì phép kiểm
        sống sót qua mọi lần dọn mã mà vẫn canh đúng con số user quan tâm.

        Tài khoản ảnh 3 tab, chưa có tài khoản Grok nào → kiêm nhiệm video.
        Đúng luật là 3 ghế ảnh + 1 ghế video (kiêm nhiệm là phương án chống cháy,
        được 1 tab), KHÔNG phải 3+3.
        """
        m = load_sfboard()
        workers_cu = dict(m.WORKERS)
        m.WORKERS.clear()
        try:
            a = {"id": "gpt", "kind": "img", "port": 9222, "tabs": 3, "enabled": True}

            m._xep_ghe_cho_tai_khoan(a, ["img", "vid"], lambda k, s: _LuongSong())

            ghe = sorted(k for k in m.WORKERS if k[0] == 9222)
            self.assertEqual(ghe, [(9222, "img", 0), (9222, "img", 1), (9222, "img", 2),
                                   (9222, "vid", 0)])
        finally:
            m.WORKERS.clear()
            m.WORKERS.update(workers_cu)

    def test_co_tai_khoan_grok_that_thi_tho_anh_thoi_kiem_nhiem(self):
        """Kiểm HÀNH VI của luật kiêm nhiệm, không kiểm hai dòng mã có còn không.

        Bản cũ khớp `'if a["kind"] == "img" and not has_vid:'` — hai dòng có sẵn
        từ trước loạt sửa này, nên nó xanh kể cả khi revert sạch mọi thay đổi
        về tab. Hỏi thẳng `_cho_ngoi_con_dung`: có tài khoản Grok bật thì thợ
        ảnh không được giữ ghế video nữa.
        """
        m = load_sfboard()
        acc_cu = m.ACCOUNTS
        try:
            anh = {"id": "gpt", "kind": "img", "port": 9222, "tabs": 2, "enabled": True}
            m.ACCOUNTS = [anh]
            self.assertTrue(m._cho_ngoi_con_dung("http://localhost:9222", "vid", 0),
                            "chưa có Grok thì thợ ảnh phải kiêm video")

            m.ACCOUNTS = [anh, {"id": "grok", "kind": "vid", "port": 9333,
                                "tabs": 1, "enabled": True}]
            self.assertFalse(m._cho_ngoi_con_dung("http://localhost:9222", "vid", 0),
                             "có Grok thật rồi mà thợ ảnh vẫn giữ ghế video")
            self.assertTrue(m._cho_ngoi_con_dung("http://localhost:9222", "img", 1),
                            "ghế ảnh của chính nó thì không được đụng tới")
        finally:
            m.ACCOUNTS = acc_cu


if __name__ == "__main__":
    unittest.main()
