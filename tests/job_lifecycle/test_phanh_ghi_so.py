"""Phanh `min_repeats` phải theo LOẠI VIỆC — video đắt hơn ảnh.

`min_repeats=3` nghĩa là chỉ ghi sổ ở lần lỗi thứ 3. Với ẢNH thì hợp lý: xoay
tài khoản là chuyện thường ngày, ghi hết thì sổ thành rác.

Với VIDEO thì con số ấy sai về bản chất: Grok trừ credit theo TỪNG submit, nên
chờ hỏng 3 lần mới ghi là đã đốt 3 lần tiền rồi mới có dòng đầu tiên trong sổ.
Đúng cái đã xảy ra với bug tab-trôi-sang-post-cũ: nó ném lỗi, nhưng phải lặp 3
lần mới được ghi, nên sổ im lặng suốt.
"""

import unittest

from helpers import load_sfboard


class PhanhGhiSoTest(unittest.TestCase):
    def setUp(self):
        self.m = load_sfboard()

    def test_anh_van_giu_phanh_3(self):
        self.assertEqual(self.m._phanh_ghi_so("img"), self.m.LAP_MOI_GHI)
        self.assertGreaterEqual(self.m.LAP_MOI_GHI, 2)

    def test_video_ghi_ngay_lan_dau(self):
        self.assertEqual(self.m._phanh_ghi_so("vid"), 1)

    def test_loai_la_thi_theo_phanh_chung(self):
        self.assertEqual(self.m._phanh_ghi_so("gi-do"), self.m.LAP_MOI_GHI)
