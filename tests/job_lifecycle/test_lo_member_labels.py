"""Thẻ ĐÃ CÓ ẢNH không bị lượt sau của cùng một lô kéo ngược lại.

Dấu vết thật, board ALTAR 2026-08-15 — cả 8 thẻ scene 21 đều đi đúng đường này:

    SF-S21-11  10:24:00  done    xong (lô · lượt 227 #01)
               10:49:43  queued  không trả ảnh nào — gửi lại cả tin, lần 2/2
               10:50:14  error   board CHƯA GỬI ĐƯỢC tin

Thẻ có ảnh lúc 10:24, 25 phút sau bị kéo về hàng chờ rồi chết đỏ. `_generate_lo_ruot`
dán nhãn của LÔ cho MỌI thành viên ở năm chỗ, không hỏi thành viên nào đã xong.
User nhìn thấy thẻ đỏ cho ảnh đang nằm trong `assets/`.

Chiều `done → error` đã bị chặn ở `hangdoi.py::__setitem__`, nhưng `done → queued`
là chiều HỢP LỆ (user bấm Tạo lại đi đúng đường đó) nên nó lọt — phải chặn ở đây,
nơi biết được đây là lượt sau của cùng một lô chứ không phải ý định mới của user.
"""

import unittest

from helpers import load_sfboard, reset_legacy_state


class LoMemberLabelTest(unittest.TestCase):
    def setUp(self):
        self.m = load_sfboard()
        reset_legacy_state(self.m)

    def tearDown(self):
        reset_legacy_state(self.m)

    def viec(self):
        return [("SF-S21-11", {}), ("SF-S21-12", {}), ("SF-S21-13", {})]

    def test_thanh_vien_da_xong_khong_bi_keo_ve_hang_cho(self):
        self.m._dat_job("SF-S21-11", {"state": "done", "msg": "xong (lô · lượt 227 #01)"})
        self.m._dat_job("SF-S21-12", {"state": "running", "msg": "đang chạy"})
        self.m._dat_job("SF-S21-13", {"state": "running", "msg": "đang chạy"})

        bo_qua = self.m._dat_nhan_lo(self.viec(),
                                     {"state": "queued", "msg": "gửi lại cả tin, lần 2/2"})

        self.assertEqual(bo_qua, 1)
        self.assertEqual(self.m.JOBS["SF-S21-11"]["state"], "done")
        self.assertEqual(self.m.JOBS["SF-S21-11"]["msg"], "xong (lô · lượt 227 #01)")
        self.assertEqual(self.m.JOBS["SF-S21-12"]["state"], "queued")
        self.assertEqual(self.m.JOBS["SF-S21-13"]["state"], "queued")

    def test_thanh_vien_chua_xong_van_nhan_du_nhan(self):
        for i, _ in self.viec():
            self.m._dat_job(i, {"state": "queued", "msg": "chờ"})

        bo_qua = self.m._dat_nhan_lo(self.viec(), {"state": "running", "msg": "3 ảnh · chat mới"})

        self.assertEqual(bo_qua, 0)
        for i, _ in self.viec():
            self.assertEqual(self.m.JOBS[i]["state"], "running")

    def test_ca_nam_cho_dan_nhan_lo_deu_di_qua_mot_cua(self):
        """Năm nhánh dán nhãn CHUNG cho cả lô: bắt đầu lượt · dừng riêng · dừng
        tất cả · gửi lại · trượt hết lượt. Sót một nhánh là lỗi quay lại.

        Chỉ đếm, không soi hình dạng mã: vòng gán KẾT QUẢ TỪNG ẢNH cho từng thẻ
        vẫn phải ghi thẳng vào `JOBS` — đó là nơi `done` được đặt, và là nơi duy
        nhất biết thẻ nào thật sự có ảnh.
        """
        from pathlib import Path

        from helpers import function_source

        nguon = function_source(Path(__file__).resolve().parents[2] / "sfboard/sfboard.py",
                                "_generate_lo_ruot")

        self.assertEqual(nguon.count("_dat_nhan_lo("), 5,
                         "số nhánh dán nhãn lô đã đổi — nhánh mới có bỏ qua thẻ đã xong không?")


if __name__ == "__main__":
    unittest.main()
