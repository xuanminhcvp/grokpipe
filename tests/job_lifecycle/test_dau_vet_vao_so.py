"""Dấu vết từng bước phải ĐI TỚI sự kiện lỗi, không dừng ở trong executor.

Ghi được bước mà không đính vào sổ thì vẫn không trả lời được câu "bug video nằm
ở đâu" — dấu vết nằm trong RAM của phiên rồi mất theo tab.
"""

import unittest

from grokpipe.executors.common import DauVetBuoc
from helpers import load_sfboard


class PhienGia:
    def __init__(self, vet):
        self.vet = vet


class DauVetVaoSoTest(unittest.TestCase):
    def setUp(self):
        self.m = load_sfboard()
        self.cu = {k: getattr(self.m._TL, k, None) for k in ("sess", "gsess")}

    def tearDown(self):
        for k, v in self.cu.items():
            setattr(self.m._TL, k, v)

    def test_lay_duoc_dau_vet_cua_phien_video(self):
        v = DauVetBuoc()
        v.xong("mode_video")
        v.hong("chip_thoi_luong", "không chốt được '10s' sau 8s")
        self.m._TL.gsess = PhienGia(v)

        ra = self.m._dau_vet_buoc("vid")

        self.assertEqual([b["buoc"] for b in ra], ["mode_video", "chip_thoi_luong"])
        self.assertFalse(ra[-1]["ok"])
        self.assertIn("10s", ra[-1]["chi_tiet"])

    def test_anh_va_video_doc_dung_phien_cua_minh(self):
        va, vv = DauVetBuoc(), DauVetBuoc()
        va.xong("dinh_ref")
        vv.xong("upload_anh")
        self.m._TL.sess, self.m._TL.gsess = PhienGia(va), PhienGia(vv)

        self.assertEqual([b["buoc"] for b in self.m._dau_vet_buoc("img")], ["dinh_ref"])
        self.assertEqual([b["buoc"] for b in self.m._dau_vet_buoc("vid")], ["upload_anh"])

    def test_chua_co_phien_thi_tra_danh_sach_rong_chu_khong_no(self):
        self.m._TL.sess = None
        self.m._TL.gsess = None

        self.assertEqual(self.m._dau_vet_buoc("img"), [])
        self.assertEqual(self.m._dau_vet_buoc("vid"), [])

    def test_phien_khong_co_so_dau_vet_cung_khong_no(self):
        """Phiên cũ dựng trước bản vá này không có thuộc tính `vet`."""
        self.m._TL.gsess = object()

        self.assertEqual(self.m._dau_vet_buoc("vid"), [])


if __name__ == "__main__":
    unittest.main()
