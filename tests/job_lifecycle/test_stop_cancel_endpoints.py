"""Hành vi THẬT của bốn đường dừng/huỷ, không phải khớp chuỗi mã nguồn.

Đây là nơi chính sách dừng và huỷ nằm, và cũng là nơi bug tối 2026-08-14 đi
xuyên qua: `/api/dung-het` đóng Chrome → thợ lỗi → dán nhãn 'running' cho việc
sẽ không chạy nữa → `/api/generate` thấy 'running' nên im lặng không tạo.

Không đụng Chrome: `_bam_stop_tren_tab` và `_kill_chrome` bị thay bằng bản ghi
sổ, đủ để kiểm THỨ TỰ gọi — bấm dừng trước, đóng cửa sổ sau.
"""

import unittest

from helpers import FakeBoard, load_sfboard, make_handler, reset_legacy_state


def tk(port=9222, **kw):
    a = {"id": f"gpt-{port}", "kind": "img", "port": port, "tabs": 1, "enabled": True}
    a.update(kw)
    return a


class DungHuyEndpointTest(unittest.TestCase):
    def setUp(self):
        self.m = load_sfboard()
        reset_legacy_state(self.m)
        self.board_cu, self.m.BOARD = self.m.BOARD, FakeBoard()
        self.acc_cu, self.m.ACCOUNTS = self.m.ACCOUNTS, [tk()]
        self.m.AUTO.clear()
        self.nhat_ky = []
        # `load_sfboard` giữ module trong `sys.modules`, nên thay hàm mà không
        # trả lại là rò sang MỌI file test chạy sau — và bản thay ở đây nuốt
        # luôn lệnh đóng Chrome thật.
        self.ham_cu = {ten: getattr(self.m, ten)
                       for ten in ("_bam_stop_tren_tab", "_kill_chrome")}
        self.m._bam_stop_tren_tab = lambda pt: (self.nhat_ky.append(("stop", pt)), 1)[1]
        self.m._kill_chrome = lambda pt: self.nhat_ky.append(("kill", pt))

    def tearDown(self):
        self.m.BOARD = self.board_cu
        self.m.ACCOUNTS = self.acc_cu
        for ten, ham in self.ham_cu.items():
            setattr(self.m, ten, ham)
        reset_legacy_state(self.m)
        self.m.AUTO.clear()

    def goi(self, path, raw=b""):
        h = make_handler(self.m, path, raw)
        h.do_POST()
        return h.captured

    # ───────────────────────────── /api/dung-het ─────────────────────────

    def test_dung_het_nang_the_he_dung_de_tho_dang_chay_khong_thu_lai(self):
        truoc = self.m.dung_gen()

        self.goi("/api/dung-het?dong_chrome=0")

        self.assertGreater(self.m.dung_gen(), truoc)

    def test_dung_het_vet_ca_hai_hang_doi(self):
        self.m._xep(self.m.IMG_QUEUE, ("img", "LO:SF-S1-01", 0, False))
        self.m._xep(self.m.VID_QUEUE, ("vid", "V-S1-01", 0, False))

        code, body = self.goi("/api/dung-het?dong_chrome=0")

        self.assertEqual(code, 200)
        self.assertEqual(body["bo"], 2)
        self.assertEqual(self.m.IMG_QUEUE.qsize(), 0)
        self.assertEqual(self.m.VID_QUEUE.qsize(), 0)
        self.assertEqual(self.m.JOBS["LO:SF-S1-01"]["msg"], "đã dừng")

    def test_dung_het_danh_dau_ca_viec_dang_chay_lan_dang_cho(self):
        self.m.JOBS["SF-S1-01"] = {"state": "running", "msg": "…"}
        self.m.JOBS["SF-S1-02"] = {"state": "queued", "msg": "…"}
        self.m.JOBS["SF-S1-03"] = {"state": "done", "msg": "xong"}

        self.goi("/api/dung-het?dong_chrome=0")

        self.assertEqual(self.m.JOBS["SF-S1-01"]["state"], "error")
        self.assertEqual(self.m.JOBS["SF-S1-02"]["state"], "error")
        self.assertEqual(self.m.JOBS["SF-S1-03"]["state"], "done", "việc XONG phải để yên")
        with self.m.HUY_LOCK:
            self.assertIn("SF-S1-01", self.m.DA_HUY)
            self.assertNotIn("SF-S1-03", self.m.DA_HUY)

    def test_dung_het_bo_moi_y_dinh_auto_va_tao_tay(self):
        self.m.AUTO["S1"] = {"chay": True}
        self.m.TAY_SF.add("SF-S1-01")

        self.goi("/api/dung-het?dong_chrome=0")

        self.assertEqual(dict(self.m.AUTO), {})
        self.assertEqual(set(self.m.TAY_SF), set())

    def test_dung_het_bam_dung_TRUOC_roi_moi_dong_cua_so(self):
        """Đóng trước là mất luôn chỗ để bấm — lượt vẫn vẽ tiếp và vẫn tính hạn mức."""
        self.goi("/api/dung-het?dong_chrome=1")

        self.assertEqual([viec for viec, _ in self.nhat_ky], ["stop", "kill"])

    def test_dung_het_khong_dong_chrome_khi_duoc_yeu_cau(self):
        code, body = self.goi("/api/dung-het?dong_chrome=0")

        self.assertEqual([viec for viec, _ in self.nhat_ky], ["stop"])
        self.assertEqual(body["dong_chrome"], [])
        self.assertEqual(body["da_bam_stop"], 1)

    # ─────────────────────────────── /api/huy ────────────────────────────

    def test_huy_khong_dung_toi_viec_dang_chay(self):
        """Cắt giữa chừng là mất ảnh đã sinh mà không thu lại được."""
        self.m.JOBS["SF-S1-01"] = {"state": "running", "msg": "đang vẽ"}
        self.m.JOBS["SF-S1-02"] = {"state": "queued", "msg": "chờ"}

        code, body = self.goi("/api/huy")

        self.assertEqual(self.m.JOBS["SF-S1-01"]["state"], "running")
        self.assertEqual(self.m.JOBS["SF-S1-02"]["state"], "error")
        self.assertEqual(body["dang_chay"], ["SF-S1-01"])
        self.assertEqual(body["cho_da_huy"], 1)

    def test_huy_khong_nang_the_he_dung(self):
        """Khác `dung-het`: huỷ hàng chờ không được chặn việc thử lại về sau."""
        truoc = self.m.dung_gen()

        self.goi("/api/huy")

        self.assertEqual(self.m.dung_gen(), truoc)

    def test_huy_danh_co_cho_ca_lo_chua_thanh_vien_bi_huy(self):
        self.m.JOBS["SF-S1-01"] = {"state": "queued", "msg": "chờ"}
        self.m.JOBS["LO:SF-S1-01,SF-S1-02"] = {"state": "queued", "msg": "chờ"}

        self.goi("/api/huy")

        with self.m.HUY_LOCK:
            self.assertIn("SF-S1-01", self.m.DA_HUY)
            self.assertIn("LO:SF-S1-01,SF-S1-02", self.m.DA_HUY)

    # ───────────────────────────── /api/huy-viec ─────────────────────────

    def test_huy_viec_tu_choi_khi_viec_dang_chay(self):
        """Chốt này chính là thứ giúp chẩn đoán được bug tối nay — phải giữ."""
        self.m.JOBS["SF-S1-01"] = {"state": "running", "msg": "đang vẽ"}

        code, body = self.goi("/api/huy-viec?sf=SF-S1-01")

        self.assertFalse(body["ok"])
        self.assertIn("ĐANG CHẠY", body["err"])
        self.assertEqual(self.m.JOBS["SF-S1-01"]["state"], "running")

    def test_huy_viec_thieu_tham_so_thi_bao_loi(self):
        code, body = self.goi("/api/huy-viec?sf=")

        self.assertFalse(body["ok"])

    def test_huy_viec_video_chi_danh_co_roi_thoi(self):
        self.m.BOARD.get_shot = lambda sid: ({"id": sid}, None)
        self.m.JOBS["V-S1-01"] = {"state": "queued", "msg": "chờ"}

        code, body = self.goi("/api/huy-viec?sf=V-S1-01")

        self.assertTrue(body["video"])
        self.assertEqual(self.m.JOBS["V-S1-01"]["state"], "error")
        with self.m.HUY_LOCK:
            self.assertIn("V-S1-01", self.m.DA_HUY)

    def test_huy_viec_anh_xe_lo_va_xep_lai_phan_con_lai(self):
        lo = "LO:SF-S1-01,SF-S1-02,SF-S1-03"
        self.m.JOBS[lo] = {"state": "queued", "msg": "chờ"}

        code, body = self.goi("/api/huy-viec?sf=SF-S1-02")

        self.assertEqual(body["bo_lo"], 1)
        self.assertEqual(body["con_lai"], 2)
        self.assertNotIn(lo, self.m.JOBS)
        self.assertEqual(self.m.JOBS["SF-S1-02"]["state"], "error")
        self.assertEqual(self.m.JOBS["SF-S1-01"]["state"], "queued")
        self.assertEqual(self.m.IMG_QUEUE.qsize(), 1, "phần còn lại phải thành lô mới")

    def test_huy_viec_go_luon_khoi_hang_giao_dich_danh(self):
        lo = "LO:SF-S1-01,SF-S1-02"
        self.m.JOBS[lo] = {"state": "queued", "msg": "chờ"}
        with self.m._CR_LOCK:
            self.m.CHO_RIENG[9222] = [lo]

        self.goi("/api/huy-viec?sf=SF-S1-01")

        with self.m._CR_LOCK:
            self.assertEqual(self.m.CHO_RIENG[9222], [])

    # ───────────────────────────── /api/generate ─────────────────────────

    def test_generate_tu_choi_khi_sf_dang_chay(self):
        """Nhãn 'running' nói dối là bấm Tạo lại im lặng không làm gì — bug tối nay."""
        self.m.JOBS["SF-S1-01"] = {"state": "running", "msg": "…"}

        code, body = self.goi("/api/generate?sf=SF-S1-01")

        self.assertFalse(body["ok"])
        self.assertEqual(body["err"], "đang chạy")
        self.assertEqual(self.m.IMG_QUEUE.qsize(), 0)

    def test_generate_xep_viec_va_go_co_huy_cu(self):
        with self.m.HUY_LOCK:
            self.m.DA_HUY.add("SF-S1-01")
            self.m.DA_HUY.add("LO:SF-S1-01")

        code, body = self.goi("/api/generate?sf=SF-S1-01")

        self.assertTrue(body["ok"])
        self.assertEqual(self.m.JOBS["SF-S1-01"]["state"], "queued")
        self.assertIn("SF-S1-01", self.m.TAY_SF)
        self.assertEqual(self.m.IMG_QUEUE.qsize(), 1)
        with self.m.HUY_LOCK:
            self.assertNotIn("SF-S1-01", self.m.DA_HUY, "ý định mới phải thắng cờ huỷ cũ")
            self.assertNotIn("LO:SF-S1-01", self.m.DA_HUY)

    def test_generate_nhieu_ban_xep_dung_so_luot(self):
        code, body = self.goi("/api/generate?sf=SF-S1-01&n=3")

        self.assertTrue(body["ok"])
        self.assertEqual(self.m.IMG_QUEUE.qsize(), 3)

    def test_generate_chan_tren_so_ban_de_khong_dot_han_muc(self):
        self.goi("/api/generate?sf=SF-S1-01&n=99")

        self.assertLessEqual(self.m.IMG_QUEUE.qsize(), 4)


if __name__ == "__main__":
    unittest.main()
