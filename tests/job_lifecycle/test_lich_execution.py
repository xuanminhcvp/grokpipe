"""Lịch execution phải khớp với việc thật đang nằm trong hàng.

Đây là phần nối giữa `Scheduler` thuần và board thật: giao việc thì lịch có
execution, thợ nhấc thì lịch có lease, huỷ thì lịch gỡ. Lịch sai thì
`/api/huy-viec` tra ra lô sai — mà tra sai còn tệ hơn không tra.

Ở Phase 4 lịch CHỈ QUAN SÁT: hàng đợi legacy vẫn là thứ đưa việc tới thợ. Nên
mọi test dưới đây cũng khẳng định hàng đợi legacy không đổi hình dạng.
"""

import unittest

from helpers import FakeBoard, load_sfboard, make_handler, reset_legacy_state


class LichExecutionTest(unittest.TestCase):
    def setUp(self):
        self.m = load_sfboard()
        reset_legacy_state(self.m)
        self.board_cu, self.m.BOARD = self.m.BOARD, FakeBoard()
        self.acc_cu, self.m.ACCOUNTS = self.m.ACCOUNTS, []

    def tearDown(self):
        self.m.BOARD = self.board_cu
        self.m.ACCOUNTS = self.acc_cu
        reset_legacy_state(self.m)

    def goi(self, path):
        h = make_handler(self.m, path)
        h.do_POST()
        return h.captured

    def lich(self):
        return self.m._JOB_SCHEDULER

    # ─────────────────────────── đăng ký ──────────────────────────────

    def test_giao_lo_thi_lich_co_execution_dung_thanh_vien(self):
        self.goi("/api/tao-lo?sf=SF-S1-01,SF-S1-02")

        exe = self.lich().get_by_ident("LO:SF-S1-01,SF-S1-02")
        self.assertIsNotNone(exe, "giao việc xong mà lịch không biết gì")
        self.assertEqual(exe.member_keys, ("SF-S1-01", "SF-S1-02"))

    def test_lich_chay_ca_o_mode_legacy(self):
        """Lịch không cầm quyền gì, nên không có lý do bắt user bật shadow."""
        self.assertEqual(self.m._JOB_MODE, "legacy")

        self.goi("/api/generate?sf=SF-S1-01")

        self.assertIsNotNone(self.lich().get_by_ident("LO:SF-S1-01"))

    def test_tra_ra_lo_vat_ly_tu_mot_thanh_vien(self):
        self.goi("/api/tao-lo?sf=SF-S1-01,SF-S1-02")

        exe = self.lich().execution_for_member("SF-S1-02")

        self.assertEqual(exe.queue_ident, "LO:SF-S1-01,SF-S1-02")

    def test_video_vao_hang_rieng_cua_no(self):
        from jobs.models import JobKind

        self.m.BOARD = FakeBoard(
            [{"id": "S1", "sfs": [],
              "shots": [{"id": "V-S1-01", "sf": "SF-S1-01", "prompt": "a"}]}],
            files=["SF-S1-01"],
        )

        self.goi("/api/genvideo?sf=V-S1-01")

        self.assertIsNotNone(
            self.lich().get_by_ident("V-S1-01", JobKind.VIDEO))
        self.assertIsNone(self.lich().get_by_ident("V-S1-01"))   # không lẫn sang ảnh

    # ──────────────────────────── lease ───────────────────────────────

    def test_tho_nhan_viec_thi_lich_ghi_lease_va_nguoi_thu_hai_khong_nhan_duoc(self):
        self.goi("/api/tao-lo?sf=SF-S1-01,SF-S1-02")
        ident = "LO:SF-S1-01,SF-S1-02"

        lease = self.m._lich_nhan("img", ident)
        lease_2 = self.m._lich_nhan("img", ident)

        self.assertIsNotNone(lease)
        self.assertIsNone(lease_2, "hai thợ cùng cầm một lô")

    def test_xong_viec_thi_tra_lease_va_lich_khong_con_giu(self):
        from jobs.models import ExecutionState

        self.goi("/api/generate?sf=SF-S1-01")
        lease = self.m._lich_nhan("img", "LO:SF-S1-01")

        self.m._lich_tra(lease)

        self.assertEqual(self.lich().get_by_ident("LO:SF-S1-01").state,
                         ExecutionState.FINISHED)

    def test_lich_hong_khong_lam_hong_viec_giao(self):
        """Tầng quan sát hỏng thì việc vẫn phải vào hàng như thường."""
        class _LichHong:
            def schedule(self, **_kw):
                raise RuntimeError("lịch chết")

            def executions_for_member(self, _k):
                raise RuntimeError("lịch chết")

        cu, self.m._JOB_SCHEDULER = self.m._JOB_SCHEDULER, _LichHong()
        try:
            code, body = self.goi("/api/generate?sf=SF-S1-01")
        finally:
            self.m._JOB_SCHEDULER = cu

        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(self.m.IMG_QUEUE.qsize(), 1)

    def test_lease_khong_co_thi_tra_ve_None_chu_khong_no(self):
        self.assertIsNone(self.m._lich_nhan("img", "LO:chua-tung-xep"))
        self.m._lich_tra(None)          # không được ném lỗi

    # ───────────────────────────── huỷ ────────────────────────────────

    def test_huy_thanh_vien_go_execution_khoi_lich(self):
        self.goi("/api/tao-lo?sf=SF-S1-01,SF-S1-02")

        self.goi("/api/huy-viec?sf=SF-S1-01")

        self.assertIsNone(self.lich().execution_for_member("SF-S1-01"))

    # ───────────────────────── chẩn đoán ──────────────────────────────

    def test_chan_doan_dem_execution(self):
        self.goi("/api/tao-lo?sf=SF-S1-01,SF-S1-02")

        so = self.m._lich_diagnostics()

        self.assertEqual(so["executions"], 1)
        self.assertEqual(so["theo_trang_thai"], {"ready": 1})


if __name__ == "__main__":
    unittest.main()
