"""Lỗi LÔ phải vào sổ runtime, có phân loại — không chỉ nằm trong log Terminal.

Sổ runtime hôm 15/08 có đúng 15 sự kiện, cái gần nhất lúc 03:17 sáng, trong khi
log Terminal đặc kín lỗi suốt ngày. Lý do: `report_runtime_bug` chỉ được gọi ở
nhánh EXCEPTION của thợ (`_ly_do_loi`). Còn lô hỏng thì không ném lỗi — nó tính
ra một câu `_vi` rồi dán nhãn và tự gửi lại. Nên toàn bộ họ lỗi hay gặp nhất

    · nút Send bị nuốt          · ChatGPT không trả ảnh nào
    · lệch số ảnh (3/4, 5/10)   · lượt trả kèm chữ
    · chưa đặt được chế độ      · thừa ảnh

không có một dòng nào trong sổ. Muốn đọc sổ mà biết chuyện gì đang hỏng thì phải
phân loại được chúng, và phân loại phải TÁCH BẠCH vì hướng xử lý khác hẳn nhau:
quota thì đổi tài khoản, guardrail thì sửa prompt, Send bị nuốt thì đóng tab.
"""

import unittest

from helpers import load_sfboard


class LyDoLoTest(unittest.TestCase):
    def setUp(self):
        self.m = load_sfboard()

    def test_nut_send_bi_nuot(self):
        vi = ("board CHƯA GỬI ĐƯỢC tin (nút Send bị nuốt, draft còn trong ô soạn) "
              "— chưa tốn lượt nào")
        self.assertEqual(self.m._ly_do_lo(vi), "SEND_SWALLOWED")

    def test_het_quota_tao_anh(self):
        vi = ("ChatGPT nhận tin nhưng không trả ảnh nào")
        chi_tiet = ("You've hit the Plus plan limit for image generations requests. "
                    "You can create more images when the limit resets in 26 minutes.")
        self.assertEqual(self.m._ly_do_lo(vi, chi_tiet), "ACCOUNT_LOST")

    def test_guardrail_chan_noi_dung(self):
        vi = "ChatGPT nhận tin nhưng không trả ảnh nào"
        chi_tiet = ("We're so sorry, but the image we created may violate our "
                    "content policies.")
        self.assertEqual(self.m._ly_do_lo(vi, chi_tiet), "GUARDRAIL")

    def test_khong_tra_anh_ma_khong_ro_vi_sao(self):
        """Không đoán bừa: không có manh mối thì để loại chung, đừng đổ cho prompt."""
        self.assertEqual(
            self.m._ly_do_lo("ChatGPT nhận tin nhưng không trả ảnh nào"),
            "NO_IMAGES")

    def test_lech_so_anh(self):
        self.assertEqual(self.m._ly_do_lo("chỉ về 3/4 ảnh"), "COUNT_SHORT")
        self.assertEqual(self.m._ly_do_lo("chỉ về 1/10 ảnh"), "COUNT_SHORT")
        self.assertEqual(self.m._ly_do_lo("thừa 1 ảnh"), "COUNT_EXTRA")

    def test_chua_dat_duoc_che_do(self):
        """Ca này DỪNG TRƯỚC KHI GỬI nên không tốn lượt — nhưng là selector chết,
        loại đáng báo động nhất vì nó chặn cả board."""
        vi = ("chưa đặt được chế độ High/Medium (đang không đọc được) — dừng trước "
              "khi gửi để khỏi đốt một lượt lấy về ảnh ghép lưới")
        self.assertEqual(self.m._ly_do_lo(vi), "MODE_UNSET")

    def test_luot_tra_kem_chu(self):
        self.assertEqual(self.m._ly_do_lo("lượt trả kèm chữ (Share Share…)"),
                         "TEXT_INSTEAD_OF_IMAGE")

    def test_user_bam_dung_khong_phai_bug(self):
        """Ghi vào sổ là báo động giả — đúng lý do `_LY_DO_HUY` tồn tại."""
        self.assertEqual(self.m._ly_do_lo("đã dừng"), "CANCELLED")
        self.assertEqual(self.m._ly_do_lo("đã huỷ khỏi hàng đợi"), "CANCELLED")

    def test_cau_la_thi_ve_loai_chung_chu_khong_no(self):
        self.assertEqual(self.m._ly_do_lo("chuyện gì đó chưa từng gặp"), "LO_FAILED")
        self.assertEqual(self.m._ly_do_lo(""), "LO_FAILED")
        self.assertEqual(self.m._ly_do_lo(None), "LO_FAILED")



class GhiSoLoHongTest(unittest.TestCase):
    def setUp(self):
        self.m = load_sfboard()
        self.da_ghi = []
        self.cu = self.m.report_runtime_bug
        self.m.report_runtime_bug = lambda e: self.da_ghi.append(e)

    def tearDown(self):
        self.m.report_runtime_bug = self.cu

    def viec(self):
        return [("SF-S22-01", {}), ("SF-S22-02", {})]

    def test_ghi_dung_mot_su_kien_co_phan_loai(self):
        self.m._ghi_so_lo_hong("LO:SF-S22-01,SF-S22-02", self.viec(),
                               "ChatGPT nhận tin nhưng không trả ảnh nào",
                               "You've hit the Plus plan limit for image generations "
                               "requests. resets in 26 minutes.", 0)

        self.assertEqual(len(self.da_ghi), 1)
        e = self.da_ghi[0]
        self.assertEqual(e["reason_code"], "ACCOUNT_LOST")
        self.assertEqual(e["category"], "lo_that_bai")
        self.assertEqual(e["job"]["so_anh"], 2)
        self.assertEqual(e["job"]["ve_duoc"], 0)

    def test_user_bam_dung_thi_KHONG_ghi(self):
        """Sổ đầy báo động giả thì không ai đọc nữa."""
        self.m._ghi_so_lo_hong("LO:x", self.viec(), "đã dừng", "", 0)

        self.assertEqual(self.da_ghi, [])

    def test_so_hong_khong_duoc_lam_hong_lo(self):
        """Lô đã dán nhãn xong rồi mới ghi sổ — sổ nổ không được kéo lô theo."""
        self.m.report_runtime_bug = lambda e: (_ for _ in ()).throw(RuntimeError("sổ hỏng"))

        self.m._ghi_so_lo_hong("LO:x", self.viec(), "chỉ về 1/2 ảnh", "", 1)  # không được ném

    def test_ghi_ca_khi_ve_duoc_mot_phan(self):
        self.m._ghi_so_lo_hong("LO:x", self.viec(), "chỉ về 1/2 ảnh", "", 1)

        self.assertEqual(self.da_ghi[0]["reason_code"], "COUNT_SHORT")
        self.assertEqual(self.da_ghi[0]["job"]["ve_duoc"], 1)

if __name__ == "__main__":
    unittest.main()
