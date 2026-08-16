import queue
import unittest

from helpers import load_hangdoi, reset_legacy_state


class CancelCharacterizationTest(unittest.TestCase):
    def setUp(self):
        self.h = load_hangdoi()
        reset_legacy_state(self.h)

    def test_cancel_flag_can_be_peeked_without_consuming(self):
        self.h.DA_HUY.add("A")
        self.assertTrue(self.h.bi_huy("A", an=False))
        self.assertTrue(self.h.bi_huy("A", an=True))
        self.assertFalse(self.h.bi_huy("A", an=False))

    def test_new_manual_intent_clears_old_cancel_flag(self):
        self.h.DA_HUY.update({"A", "LO:A"})
        self.h.bo_co_huy("A", "LO:A")
        self.assertFalse(self.h.DA_HUY)

    def test_stop_generation_is_monotonic(self):
        before = self.h.dung_gen()
        self.assertEqual(self.h.tang_dung_gen(), before + 1)
        self.assertEqual(self.h.dung_gen(), before + 1)


class HuyMotThanhVienTest(unittest.TestCase):
    """Huỷ MỘT ảnh trong lô đang chờ phải tìm ra được lô VẬT LÝ.

    Lúc lô vừa xếp, `JOBS` chỉ có nhãn của từng thành viên — khoá `LO:a,b` chưa
    tồn tại (nó chỉ được ghi khi thợ nhấc việc hoặc khi lô phải chờ khoá địa
    điểm). Bản cũ tìm lô bằng cách QUÉT `JOBS` lấy khoá `LO:` đang `queued`, nên
    trong đúng khoảng đó nó không thấy gì: server trả "đã huỷ 0 lô" trong khi lô
    vẫn nằm nguyên trong hàng và vài giây sau vẫn chạy — user bấm huỷ mà ảnh
    vẫn ra, tốn lượt.

    Nguồn đúng là HÀNG ĐỢI THẬT (và scheduler khi bật shadow), không phải `JOBS`.
    """

    def setUp(self):
        from helpers import FakeBoard, load_sfboard
        self.m = load_sfboard()
        reset_legacy_state(self.m)
        self.board_cu, self.m.BOARD = self.m.BOARD, FakeBoard()

    def tearDown(self):
        self.m.BOARD = self.board_cu
        reset_legacy_state(self.m)

    def goi(self, path):
        from helpers import make_handler
        h = make_handler(self.m, path)
        h.do_POST()
        return h.captured

    def xep_lo(self):
        self.m._dat_job("A", {"state": "queued", "msg": "chờ · 2 ảnh"})
        self.m._dat_job("B", {"state": "queued", "msg": "chờ · 2 ảnh"})
        self.m._xep(self.m.IMG_QUEUE, ("img", "LO:A,B", 0, True))

    def test_huy_thanh_vien_tim_ra_lo_dang_cho_trong_hang(self):
        self.xep_lo()

        code, body = self.goi("/api/huy-viec?sf=A")

        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["bo_lo"], 1, "không tìm ra lô vật lý chứa A")
        self.assertEqual(body["con_lai"], 1)
        self.assertIn("LO:A,B", self.m.DA_HUY)
        self.assertEqual(self.m.JOBS["A"]["state"], "error")

    def test_phan_con_lai_duoc_xep_lai_thanh_lo_moi(self):
        self.xep_lo()

        self.goi("/api/huy-viec?sf=A")

        trong_hang = self.m._y_trong_hang(self.m.IMG_QUEUE)
        self.assertIn("LO:B", trong_hang)
        self.assertEqual(self.m.JOBS["B"]["state"], "queued")

    def test_lo_giao_dich_danh_cung_tim_ra_duoc(self):
        """Lô bị ép tài khoản nằm ở `CHO_RIENG`, không nằm trong hàng chung."""
        self.m._dat_job("A", {"state": "queued", "msg": "chờ · ép cổng 9225"})
        self.m._dat_job("B", {"state": "queued", "msg": "chờ · ép cổng 9225"})
        with self.m._CR_LOCK:
            self.m.CHO_RIENG[9225] = ["LO:A,B"]

        code, body = self.goi("/api/huy-viec?sf=A")

        self.assertEqual(body["bo_lo"], 1)
        self.assertEqual(self.m.CHO_RIENG[9225], [])

    def test_khong_dung_cham_lo_khong_chua_thanh_vien_do(self):
        self.xep_lo()
        self.m._dat_job("C", {"state": "queued", "msg": "chờ"})
        self.m._xep(self.m.IMG_QUEUE, ("img", "LO:C", 0, True))

        self.goi("/api/huy-viec?sf=A")

        self.assertNotIn("LO:C", self.m.DA_HUY)
        self.assertEqual(self.m.JOBS["C"]["state"], "queued")

    def test_khoa_lo_da_co_trong_JOBS_van_tim_ra_nhu_cu(self):
        """Đường cũ (lô đang chờ khoá địa điểm nên đã có khoá `LO:`) phải giữ."""
        self.m._dat_job("LO:A,B", {"state": "queued", "msg": "chờ khoá địa điểm"})

        code, body = self.goi("/api/huy-viec?sf=A")

        self.assertEqual(body["bo_lo"], 1)
        self.assertIn("LO:A,B", self.m.DA_HUY)
