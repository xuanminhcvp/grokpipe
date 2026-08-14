"""Việc bị TỪ CHỐI xếp lại không được để lại nhãn 'đang chạy'.

Lỗi thật gặp 2026-08-14 trên board ALTAR: bấm 'Dừng tất cả' giữa lúc hai lô đang
vẽ → Chrome bị đóng → thợ lỗi 'cửa sổ Chrome đã đóng' → dán nhãn 'đang chạy ·
thử lại sau 20s' rồi hẹn giờ. Bộ hẹn giờ đúng luật nên KHÔNG xếp lại, nhưng nhãn
nằm lại vĩnh viễn: 14 dòng 'đang chạy' cho việc không bao giờ chạy, và bấm Tạo
lại đúng những SF đó thì bị bỏ qua im lặng vì cả hai đường tạo đều chặn ident
mang nhãn 'running'.
"""

import unittest
from pathlib import Path

from helpers import function_source, load_sfboard, reset_legacy_state


ROOT = Path(__file__).resolve().parents[2]
BOARD_PATH = ROOT / "sfboard/sfboard.py"


class RetryLabelConsistencyTest(unittest.TestCase):
    def setUp(self):
        self.m = load_sfboard()
        reset_legacy_state(self.m)

    def tearDown(self):
        reset_legacy_state(self.m)

    # ---- quyết định xếp lại -------------------------------------------

    def test_binh_thuong_thi_van_xep_lai(self):
        self.assertEqual(self.m._quyet_xep_lai("SF-S6-01", self.m.dung_gen()), "xep")

    def test_dung_tat_ca_thi_khong_xep_lai(self):
        gen = self.m.dung_gen()
        self.m.tang_dung_gen()

        self.assertEqual(self.m._quyet_xep_lai("SF-S6-01", gen), "dung")

    def test_viec_bi_huy_thi_khong_xep_lai(self):
        with self.m.HUY_LOCK:
            self.m.DA_HUY.add("SF-S6-01")

        self.assertEqual(self.m._quyet_xep_lai("SF-S6-01", self.m.dung_gen()), "huy")

    def test_doc_co_huy_ma_khong_an_mat_co(self):
        with self.m.HUY_LOCK:
            self.m.DA_HUY.add("SF-S6-01")

        self.m._quyet_xep_lai("SF-S6-01", self.m.dung_gen())

        with self.m.HUY_LOCK:
            self.assertIn("SF-S6-01", self.m.DA_HUY,
                          "ăn cờ ở đây thì thợ nhấc việc lên sẽ chạy thật việc đã huỷ")

    # ---- nhãn phải khớp hàng đợi --------------------------------------

    def test_bo_hen_gio_doi_nhan_khi_tu_choi_xep_lai(self):
        nguon = function_source(BOARD_PATH, "_xep_lai_sau")

        self.assertIn("_quyet_xep_lai(item[1], gen)", nguon)
        self.assertIn('_dat_job(item[1], {"state": "error",', nguon)
        self.assertIn('"đã dừng" if quyet == "dung" else "đã huỷ"', nguon)

    def test_khong_con_duong_nao_bo_ve_lang_le_de_lai_nhan_chay(self):
        nguon = function_source(BOARD_PATH, "_xep_lai_sau")
        than_ban = nguon[nguon.index("def _ban():"):]

        # mọi nhánh thoát của `_ban` đều phải hoặc xếp lại, hoặc sửa nhãn
        self.assertEqual(than_ban.count("return"), 2)
        self.assertIn("_xep(Q, item)", than_ban)
        self.assertIn("_dat_job(", than_ban)

    def test_dung_tat_ca_giua_chung_thi_nhan_doi_thanh_da_dung_that(self):
        """Chạy đồng hồ THẬT — đây là đúng đường đã sinh ra 14 job ma."""
        import time

        ident = "LO:SF-S6-10,SF-S6-B2"
        gen = self.m.dung_gen()
        # thợ lỗi 'cửa sổ Chrome đã đóng' → dán nhãn chạy rồi hẹn xếp lại
        self.m._dat_job(ident, {"state": "running", "msg": "… thử lại sau 20s (lần 1)"})
        self.m._xep_lai_sau("img", ("img", ident, 1, False), 0)
        self.m.tang_dung_gen()                      # user bấm 'Dừng tất cả'
        self.assertNotEqual(self.m.dung_gen(), gen)

        time.sleep(1.4)                             # bộ hẹn giờ tối thiểu 1 giây

        self.assertEqual(self.m.JOBS[ident]["state"], "error")
        self.assertEqual(self.m.JOBS[ident]["msg"], "đã dừng")
        # nhãn của TỪNG SF thành viên cũng phải theo, không chỉ ident lô
        self.assertEqual(self.m.JOBS["SF-S6-10"]["state"], "error")
        self.assertEqual(self.m.JOBS["SF-S6-B2"]["state"], "error")
        self.assertEqual(self.m.IMG_QUEUE.qsize(), 0, "đã dừng thì không được xếp lại")

    def test_hai_duong_tao_van_chan_viec_dang_chay(self):
        """Chốt này ĐÚNG — nó chỉ hỏng khi nhãn nói dối, nên phải giữ nguyên."""
        nguon = BOARD_PATH.read_text(encoding="utf-8")

        self.assertIn('if JOBS.get(sf_id, {}).get("state") == "running":', nguon)
        self.assertIn('if JOBS.get(i, {}).get("state") == "running":', nguon)


if __name__ == "__main__":
    unittest.main()
