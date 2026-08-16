"""Một lô không được chứa cả thẻ A lẫn thẻ PHỤ THUỘC vào A.

Đo trên AISLE-SEVEN 2026-08-15: 67 thẻ REF, 14 thẻ trang phục đính ref vào một
chân dung CHƯA có ảnh — và board gom chúng vào CÙNG task với chính chân dung ấy
(T11–T24). Hậu quả không phải chậm mà là KẸT VĨNH VIỄN:

    `_sf_attachments` báo thiếu ref → `_generate_lo_ruot` dán lỗi cho CẢ LÔ và
    ném → chân dung chết theo → lần sau chạy lại vẫn thiếu đúng chân dung đó.

Board đã có cổng phụ thuộc cho ĐỊA ĐIỂM (`_cong_master`: SF con chờ thẻ địa điểm
duyệt xong). Nhân vật có quan hệ y hệt — trang phục cần chân dung — nhưng không
có cổng nào. Đây là lấp chỗ đó, ở tầng chia lô nên áp cho mọi loại phụ thuộc.
"""

import unittest

from helpers import load_sfboard, load_hangdoi


def ref_cua(i):
    """Thẻ trang phục đính chân dung của chính nhân vật đó."""
    return [i.rsplit("_", 2)[0] + "_PORTRAIT"] if i.endswith("_FULL") else []


class TachLoTheoPhuThuocTest(unittest.TestCase):
    def setUp(self):
        self.m = load_sfboard()

    def chia(self, ids):
        return self.m._chia_lo(ids, ref_cua, 10, 10)

    def test_chan_dung_va_trang_phuc_KHONG_di_chung_mot_lo(self):
        lo = self.chia(["REF_LORETTA_PORTRAIT", "REF_LORETTA_NHA_FULL"])

        self.assertEqual(lo, [["REF_LORETTA_PORTRAIT"], ["REF_LORETTA_NHA_FULL"]])

    def test_chan_dung_luon_o_lo_TRUOC(self):
        """Ngược lại là vô nghĩa: trang phục chạy trước thì vẫn thiếu ref."""
        lo = self.chia(["REF_COLIN_PORTRAIT", "REF_COLIN_CONGSO_FULL"])

        self.assertIn("REF_COLIN_PORTRAIT", lo[0])

    def test_nhieu_trang_phuc_cua_cung_nguoi_van_di_CHUNG_mot_lo(self):
        """Chúng không phụ thuộc lẫn nhau — chẻ nhỏ là tốn lượt vô ích."""
        lo = self.chia(["REF_KEISHA_PORTRAIT", "REF_KEISHA_GRAYWAY_FULL",
                        "REF_KEISHA_NHA_FULL", "REF_KEISHA_RAPHO_FULL"])

        self.assertEqual(len(lo), 2)
        self.assertEqual(len(lo[1]), 3, "ba bộ trang phục phải đi chung một tin")

    def test_the_khong_phu_thuoc_nhau_van_gom_binh_thuong(self):
        lo = self.m._chia_lo([f"SF-S1-{i:02d}" for i in range(6)],
                             lambda i: ["REF_BG"], 10, 10)

        self.assertEqual(len(lo), 1)


class ThuTuRefTest(unittest.TestCase):
    def setUp(self):
        self.h = load_hangdoi()

    def test_chan_dung_uu_tien_hon_trang_phuc(self):
        """Cả hai từng cùng mức 0 — hàng đợi không có cớ gì xếp đúng thứ tự."""
        self.assertLess(self.h.uu_tien("REF_COLIN_PORTRAIT"),
                        self.h.uu_tien("REF_COLIN_CONGSO_FULL"))

    def test_moi_the_REF_van_di_truoc_moi_SF_cua_scene(self):
        """REF là neo của cả phim — kể cả thẻ trang phục cũng phải xong trước."""
        self.assertLess(self.h.uu_tien("REF_COLIN_CONGSO_FULL"),
                        self.h.uu_tien("SF-S1-01"))

    def test_the_dia_diem_van_di_dau(self):
        self.assertLessEqual(self.h.uu_tien("SF-M-BEP"), self.h.uu_tien("SF-S1-01"))

    def test_thu_tu_giua_cac_SF_trong_scene_khong_doi(self):
        self.assertLess(self.h.uu_tien("SF-S1-01"), self.h.uu_tien("SF-S1-02"))
        self.assertLess(self.h.uu_tien("SF-S1-09"), self.h.uu_tien("SF-S2-01"))


if __name__ == "__main__":
    unittest.main()
