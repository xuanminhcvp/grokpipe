import unittest
from pathlib import Path

from helpers import function_source

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "sfboard/sfboard.py"


class AccountCharacterizationTest(unittest.TestCase):
    def test_worker_is_bound_to_endpoint_before_queue_take(self):
        source = function_source(BOARD, "_worker")
        self.assertLess(source.index("_TL.endpoint = endpoint"), source.index("_lay(QUEUE"))

    def test_forced_image_work_uses_private_port_queue(self):
        source = function_source(BOARD, "_worker")
        self.assertIn("CHO_RIENG.get(_my_port)", source)
        self.assertIn("_rieng.pop(0)", source)


class EpTaiKhoanQuaRetryTest(unittest.TestCase):
    """Ép tài khoản phải sống qua MỌI lần thử lại.

    Chat sống trong profile Chrome của đúng tài khoản đã mở nó — không bê sang
    máy khác được. Nên user ép cổng chính là để mọi lượt của lô đó chạy ở đúng
    đó. Bản cũ xếp lại vào hàng CHUNG sau mỗi lỗi, tức lượt thứ hai mở chat
    trắng ở máy khác và ràng buộc bay mất trong im lặng — mà ép tài khoản
    thường là thao tác chữa cháy khi chat cũ đã hỏng.
    """

    def setUp(self):
        from helpers import FakeBoard, load_sfboard, make_handler, reset_legacy_state
        self.reset = reset_legacy_state
        self.m = load_sfboard()
        self.mk = make_handler
        self.reset(self.m)
        self.board_cu, self.m.BOARD = self.m.BOARD, FakeBoard()
        self.acc_cu, self.m.ACCOUNTS = self.m.ACCOUNTS, []

    def tearDown(self):
        self.m.BOARD = self.board_cu
        self.m.ACCOUNTS = self.acc_cu
        self.reset(self.m)

    def tao_lo_ep(self, cong=9225):
        h = self.mk(self.m, f"/api/tao-lo?sf=SF-S1-01,SF-S1-02&tk={cong}")
        h.do_POST()
        return "LO:SF-S1-01,SF-S1-02"

    def ban_lai(self, ident, tries=1):
        """Bắn thẳng thân bộ hẹn giờ — khỏi phải chờ đồng hồ thật."""
        dau = (self.m.JOBS.get(ident) or {}).get("t")
        return self.m._ban_xep_lai(
            "img", ("img", ident, tries, True), self.m.dung_gen(), dau)

    def test_xep_lai_sau_loi_van_ve_dung_cong_da_ep(self):
        ident = self.tao_lo_ep()
        with self.m._CR_LOCK:                      # thợ của cổng đó đã nhấc việc
            self.m.CHO_RIENG[9225].remove(ident)
        self.m._dat_job(ident, {"state": "running", "msg": "lỗi → thử lại sau 20s"})

        self.assertEqual(self.ban_lai(ident), "xep")

        self.assertEqual(self.m.CHO_RIENG[9225], [ident],
                         "việc bị ép đã rơi ra khỏi hàng riêng của cổng")
        self.assertEqual(self.m.IMG_QUEUE.qsize(), 0,
                         "xếp vào hàng chung là mở chat trắng ở máy khác")

    def test_rang_buoc_song_qua_nhieu_lan_thu(self):
        ident = self.tao_lo_ep()
        for lan in range(1, 4):
            with self.m._CR_LOCK:
                if ident in self.m.CHO_RIENG[9225]:
                    self.m.CHO_RIENG[9225].remove(ident)
            self.m._dat_job(ident, {"state": "running", "msg": f"thử lần {lan}"})

            self.ban_lai(ident, tries=lan)

            self.assertEqual(self.m.CHO_RIENG[9225], [ident], f"mất ép ở lần {lan}")
            self.assertEqual(self.m.IMG_QUEUE.qsize(), 0)

    def test_viec_khong_bi_ep_van_ve_hang_chung_nhu_cu(self):
        h = self.mk(self.m, "/api/tao-lo?sf=SF-S9-01")
        h.do_POST()
        ident = "LO:SF-S9-01"
        self.m.IMG_QUEUE.get_nowait()
        self.m._dat_job(ident, {"state": "running", "msg": "lỗi → thử lại"})

        self.ban_lai(ident)

        self.assertEqual(self.m.IMG_QUEUE.qsize(), 1)
        self.assertNotIn(ident, self.m.CHO_RIENG.get(9225, []))
