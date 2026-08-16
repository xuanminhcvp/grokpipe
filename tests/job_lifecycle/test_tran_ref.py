"""Trần REF mỗi lô, và cách hạ ref khi tràn.

Log ALTAR 2026-08-15 cho một tương phản rất sạch, cùng quãng 10:13–10:24, cùng
dàn tài khoản, cùng máy:

    lô 5 ref  (S13, Phòng chỉ huy)  → không hỏng lần nào
    lô 9 ref                        → hỏng 2/2
    lô 14 ref                       → hỏng 5/5, có lần trượt sạch 14/14
    lô 17 ref (S21, Nhà thờ)        → hỏng 2/2, có lần trượt sạch 17/17

Sáu lần xoay tài khoản trong 11 phút, cả sáu đều vì `không đính được ảnh ref`.
Số ref đi theo số SF trong lô, nên lô to là lô chết. Trần ref mới là trần ràng
buộc; số SF rơi ra từ đó (user chốt 2026-08-15).

Hạ ref khi tràn: nhân vật TỪ THỨ 5 TRỞ ĐI chỉ gửi `_FULL`, bỏ `_PORTRAIT`.
Ngược chiều ca S5 (`sfboard.py`: chỉ gửi portrait thì model tự bịa áo) — ở đây
giữ full nên trang phục và dáng còn nguyên, rủi ro dồn vào khuôn mặt, chấp nhận
được với nhân vật nền.
"""

import unittest

from helpers import load_sfboard


class HaRefTest(unittest.TestCase):
    def setUp(self):
        self.m = load_sfboard()

    def bo(self, *ten):
        """Bộ ref đủ cặp cho từng nhân vật, kèm bối cảnh."""
        ids = ["REF_NHATHO_CHIEU"]
        for t in ten:
            ids += [f"REF_{t}_PORTRAIT", f"REF_{t}_FULL"]
        return ids

    def test_duoi_tran_thi_khong_dung_toi(self):
        ids = self.bo("MAYA", "RYAN")            # 1 + 4 = 5
        self.assertEqual(self.m._ha_ref_nhan_vat_phu(ids, 10), ids)

    def test_tu_nhan_vat_thu_5_tro_di_bo_portrait_giu_full(self):
        ids = self.bo("A", "B", "C", "D", "E", "F")   # 1 + 12 = 13 > 10

        ra = self.m._ha_ref_nhan_vat_phu(ids, 10)

        self.assertIn("REF_D_PORTRAIT", ra, "bốn nhân vật đầu phải giữ đủ cặp")
        self.assertNotIn("REF_E_PORTRAIT", ra)
        self.assertNotIn("REF_F_PORTRAIT", ra)
        self.assertIn("REF_E_FULL", ra, "full mang trang phục — không được bỏ")
        self.assertIn("REF_F_FULL", ra)
        self.assertEqual(len(ra), 11)

    def test_nhan_vat_phu_khong_co_full_thi_giu_nguyen_portrait(self):
        """Bỏ nốt portrait là mất hẳn nhân vật khỏi tin — model tự bịa cả người."""
        ids = self.bo("A", "B", "C", "D") + ["REF_E_PORTRAIT"]

        ra = self.m._ha_ref_nhan_vat_phu(ids, 6)

        self.assertIn("REF_E_PORTRAIT", ra)

    def test_boi_canh_va_dao_cu_khong_bao_gio_bi_dung_toi(self):
        ids = ["REF_NHATHO_CHIEU", "REF_PROP_VONGCO"] + self.bo("A", "B", "C", "D", "E")[1:]

        ra = self.m._ha_ref_nhan_vat_phu(ids, 8)

        self.assertIn("REF_NHATHO_CHIEU", ra)
        self.assertIn("REF_PROP_VONGCO", ra)

    def test_ha_xong_van_tran_thi_tra_ve_nhung_gi_ha_duoc(self):
        """Hàm này chỉ HẠ; chốt lô sớm là việc của hàm chia lô."""
        ids = self.bo(*[chr(65 + i) for i in range(8)])   # 1 + 16 = 17

        ra = self.m._ha_ref_nhan_vat_phu(ids, 6)

        self.assertEqual(len(ra), 13)       # 1 bg + 4 cặp + 4 full
        self.assertGreater(len(ra), 6)

    def test_giu_nguyen_thu_tu(self):
        ids = self.bo("A", "B", "C", "D", "E")
        ra = self.m._ha_ref_nhan_vat_phu(ids, 8)
        self.assertEqual(ra, [x for x in ids if x in ra])


class ChiaLoTest(unittest.TestCase):
    def setUp(self):
        self.m = load_sfboard()

    def chia(self, ids, ref_cua, tran_sf=10, tran_ref=10):
        return self.m._chia_lo(ids, ref_cua, tran_sf, tran_ref)

    def test_tran_SF_van_con_hieu_luc(self):
        """ChatGPT chỉ nhận lô 10 — ref ít mấy cũng không được vượt."""
        ids = [f"SF-{i:02d}" for i in range(14)]

        lo = self.chia(ids, lambda i: ["REF_BG"])

        self.assertEqual([len(x) for x in lo], [10, 4])

    def test_tran_REF_cham_truoc_thi_chot_lo_som(self):
        """Đúng ý user: chạm 10 ref là chốt, dù chưa đủ 10 SF.

        Mỗi SF mang bối cảnh chung + một nhân vật riêng đủ cặp:

            4 SF → bg + 4×2 = 9 ref
            5 SF → 11 ref, TRÀN → hạ: nhân vật thứ 5 bỏ portrait → 10 → vừa khít
            6 SF → 13 ref, hạ được 2 portrait → 11 → vẫn tràn → CHỐT ở 5 SF

        Phép hạ chạy TRƯỚC khi quyết chốt, nên nó nhét thêm được đúng một SF nữa
        vào lô — đó là điểm của việc hạ ref, không phải hiệu ứng phụ.
        """
        def ref_cua(i):
            return ["REF_BG", f"REF_{i}_PORTRAIT", f"REF_{i}_FULL"]

        lo = self.chia([f"SF-{i}" for i in range(9)], ref_cua)

        self.assertEqual([len(x) for x in lo], [5, 4])

    def test_ref_dung_chung_khong_tinh_lai(self):
        """Thêm một SF dùng lại đúng ref cũ thì KHÔNG tốn thêm slot nào."""
        def ref_cua(i):
            return ["REF_BG", "REF_MAYA_PORTRAIT", "REF_MAYA_FULL"]

        lo = self.chia([f"SF-{i}" for i in range(10)], ref_cua)

        self.assertEqual([len(x) for x in lo], [10], "3 ref dùng chung cho cả 10 SF")

    def test_mot_SF_tu_no_vuot_tran_van_duoc_gui(self):
        """Lô 1 SF không chẻ nhỏ hơn được nữa — chặn là chặn việc của user."""
        def ref_cua(i):
            return [f"REF_{i}_{k}" for k in range(13)]

        lo = self.chia(["SF-A", "SF-B"], ref_cua)

        self.assertEqual(lo, [["SF-A"], ["SF-B"]])

    def test_giu_dung_thu_tu_shot(self):
        ids = [f"SF-{i:02d}" for i in range(12)]
        lo = self.chia(ids, lambda i: ["REF_BG"])
        self.assertEqual([x for l in lo for x in l], ids)

    def test_danh_sach_rong(self):
        self.assertEqual(self.chia([], lambda i: []), [])



class OChinhTranRefTest(unittest.TestCase):
    """Ô chỉnh trên board — trần ref là cài đặt CHUNG, không thuộc tài khoản nào."""

    def setUp(self):
        from helpers import make_handler
        self.m = load_sfboard()
        self.mk = make_handler
        self.cu = self.m.TRAN_REF
        self.luu_cu, self.m._save_accounts = self.m._save_accounts, lambda: None

    def tearDown(self):
        self.m.TRAN_REF = self.cu
        self.m._save_accounts = self.luu_cu

    def goi(self, path):
        h = self.mk(self.m, path)
        h.do_POST()
        return h.captured

    def test_dat_duoc_tran_ma_KHONG_can_chon_tai_khoan(self):
        """Không có `port` hợp lệ vẫn phải chạy — trần là của cả board.

        Nhánh này phải nằm TRƯỚC cổng `if not acc: 404` trong `/api/acct`, nếu
        không ô chỉnh im lặng không ăn.
        """
        code, body = self.goi("/api/acct?op=tran-ref&n=6")

        self.assertTrue(body["ok"])
        self.assertEqual(self.m.TRAN_REF, 6)

    def test_kep_ve_khoang_hop_le(self):
        for n, mong in ((0, 1), (-5, 1), (999, self.m.TRAN_REF_MAX)):
            self.goi(f"/api/acct?op=tran-ref&n={n}")
            self.assertEqual(self.m.TRAN_REF, mong, f"n={n}")

    def test_giao_dien_doc_duoc_tran_hien_tai(self):
        self.goi("/api/acct?op=tran-ref&n=7")

        h = self.mk(self.m, "/api/accounts")
        h.do_GET()
        self.assertEqual(h.captured[1]["tran_ref"], 7)
        self.assertIn("accounts", h.captured[1], "không được làm mất trường cũ")

if __name__ == "__main__":
    unittest.main()
