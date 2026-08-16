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

from helpers import load_sfboard, reset_legacy_state


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

    # Hai test cũ ở đây khớp CHUỖI trong thân `_ban_xep_lai`
    # (`'_dat_job(item[1], {"state": "error",'` và `'        return\n' không có
    # mặt`). Chúng pin cách viết chứ không pin hành vi: bản vá thêm phép gác dấu
    # sở hữu — đúng hơn hẳn — vẫn phải đi vòng để không làm chúng đỏ. Đổi sang
    # kiểm hành vi từng nhánh quyết định (2026-08-15).

    def _ban(self, ident, kind="img", gen=None, dau=None):
        """Bắn chuông với dấu sở hữu ĐÚNG như `_xep_lai_sau` chụp lúc hẹn.

        `gen` mặc định là thế hệ HIỆN TẠI — nhưng chuông hẹn từ trước khi user
        bấm 'Dừng tất cả' thì phải truyền thế hệ CŨ vào, đó chính là thứ phân
        biệt "dừng rồi" với "chạy bình thường".
        """
        if dau is None:
            dau = (self.m.JOBS.get(ident) or {}).get("t")
        return self.m._ban_xep_lai(kind, (kind, ident, 1, False),
                                   self.m.dung_gen() if gen is None else gen, dau)

    def test_viec_bi_huy_thi_nhan_doi_thanh_da_huy(self):
        ident = "SF-S6-01"
        self.m._dat_job(ident, {"state": "running", "msg": "… thử lại sau 20s (lần 1)"})
        with self.m.HUY_LOCK:
            self.m.DA_HUY.add(ident)

        self._ban(ident)

        self.assertEqual(self.m.JOBS[ident]["state"], "error")
        self.assertEqual(self.m.JOBS[ident]["msg"], "đã huỷ")
        self.assertEqual(self.m.IMG_QUEUE.qsize(), 0)

    def test_binh_thuong_thi_viec_quay_lai_hang_va_nhan_khong_bi_doi(self):
        """Nhánh thường: không nhánh nào được lặng lẽ bỏ về, để lại nhãn 'đang chạy'."""
        ident = "SF-S6-01"
        self.m._dat_job(ident, {"state": "running", "msg": "… thử lại sau 20s (lần 1)"})

        quyet = self._ban(ident)

        self.assertEqual(quyet, "xep")
        self.assertEqual(self.m.IMG_QUEUE.qsize(), 1)
        self.assertEqual(self.m.JOBS[ident]["state"], "running",
                         "đang chờ tới lượt trong hàng thì nhãn 'đang chạy' là đúng")

    def test_dung_tat_ca_giua_chung_thi_nhan_doi_thanh_da_dung_that(self):
        """Đúng đường đã sinh ra 14 job ma — nhưng bắn THÂN hẹn giờ, không chờ đồng hồ.

        Đồng hồ thật chỉ cần cho ĐÚNG MỘT test (xem
        `test_hen_gio_cu_khong_boi_do_viec_tho_khac_vua_lam_xong`). Ở đây thứ cần
        kiểm là quyết định và cái nhãn nó dán — `_ban_xep_lai` cho cả hai một
        cách xác định. Chờ 1,4 giây ở ba test chỉ để xem `threading.Timer` có
        chạy không là mua cùng một thứ ba lần, và trả bằng thời gian của mọi
        người chạy test về sau.
        """
        ident = "LO:SF-S6-10,SF-S6-B2"
        gen = self.m.dung_gen()
        # thợ lỗi 'cửa sổ Chrome đã đóng' → dán nhãn chạy rồi hẹn xếp lại
        self.m._dat_job(ident, {"state": "running", "msg": "… thử lại sau 20s (lần 1)"})
        self.m.tang_dung_gen()                      # user bấm 'Dừng tất cả'
        self.assertNotEqual(self.m.dung_gen(), gen)

        self._ban(ident, gen=gen)          # chuông hẹn từ TRƯỚC cú dừng

        self.assertEqual(self.m.JOBS[ident]["state"], "error")
        self.assertEqual(self.m.JOBS[ident]["msg"], "đã dừng")
        # nhãn của TỪNG SF thành viên cũng phải theo, không chỉ ident lô
        self.assertEqual(self.m.JOBS["SF-S6-10"]["state"], "error")
        self.assertEqual(self.m.JOBS["SF-S6-B2"]["state"], "error")
        self.assertEqual(self.m.IMG_QUEUE.qsize(), 0, "đã dừng thì không được xếp lại")

    # ---- chuông cũ chỉ được đụng vào nhãn của CHÍNH NÓ ------------------

    def test_hen_gio_cu_khong_boi_do_viec_tho_khac_vua_lam_xong(self):
        """Chuông hẹn trước đó tới 180 giây; tới lúc reo, việc có thể đã đổi chủ.

        `cho = min(20 + 20*tries, 180)` nên một chuông sống rất lâu. Trong quãng
        đó user hoàn toàn có thể tạo lại và một thợ khác làm xong. Chuông cũ mà
        vẫn ghi trạng thái cuối thì nó bôi đỏ việc đã xong — và vì `_dat_job`
        rải cho thành viên `LO:`, nó bôi đỏ cả lô.
        """
        import time

        ident = "LO:SF-S6-10,SF-S6-B2"
        self.m._dat_job(ident, {"state": "running", "msg": "… thử lại sau 20s (lần 1)"})
        self.m._xep_lai_sau("img", ("img", ident, 1, False), 0)   # chuông lên nòng
        self.m.tang_dung_gen()                                    # user bấm Dừng tất cả
        # user tạo lại ngay; thợ khác nhận và làm XONG trước khi chuông reo
        self.m._dat_job(ident, {"state": "done", "msg": "xong"})

        time.sleep(1.4)

        self.assertEqual(self.m.JOBS[ident]["state"], "done",
                         "chuông cũ đã bôi đỏ việc thợ khác vừa làm xong")
        self.assertEqual(self.m.JOBS["SF-S6-10"]["state"], "done",
                         "và bôi đỏ lây sang từng SF thành viên của lô")

    def test_hen_gio_cu_khong_boi_do_viec_dang_chay_cua_tho_khac(self):
        """Ca đắt tiền nhất: nhãn bị bôi đỏ trong lúc Grok đang dựng thật.

        Từ lúc bị bôi, mọi chốt "việc này còn chạy không?" đều đọc ra `error`:
        `/api/generate`, nhánh tạo nhiều SF, và chốt video của auto. Cái cuối tự
        động `_enqueue("vid", …)` cho shot Grok đang dựng dở — submit trùng, trừ
        credit thật. Hai nhãn đều là `running`; thứ phân biệt chúng là DẤU `t`
        mà `_dong_dau` đóng lại mỗi lần ghi.

        Chụp dấu bằng tay ở đây thay vì chờ đồng hồ: phần "`_xep_lai_sau` có
        chụp dấu đúng lúc hẹn không" đã có test riêng chạy `threading.Timer`
        thật ngay bên trên, không cần mua lại.
        """
        ident = "SF-S6-10"
        gen = self.m.dung_gen()
        self.m._dat_job(ident, {"state": "running", "msg": "… thử lại sau 20s (lần 1)"})
        dau = self.m.JOBS[ident]["t"]          # dấu chuông cầm theo lúc hẹn
        self.m.tang_dung_gen()
        # user chạy lại đúng shot này; thợ mới đã submit sang Grok
        self.m._dat_job(ident, {"state": "running", "msg": "đang chạy"})

        self._ban(ident, gen=gen, dau=dau)

        self.assertEqual(self.m.JOBS[ident]["state"], "running",
                         "chuông cũ đã bôi đỏ việc đang render — mở lại chốt chống trùng")
        self.assertEqual(self.m.JOBS[ident]["msg"], "đang chạy")

    # Chốt "hai đường tạo bỏ qua việc đang chạy" từng được canh ở đây bằng cách
    # khớp CHUỖI MÃ NGUỒN. Nó vỡ ngay lần chốt ấy được sửa cho đúng hơn (chặn
    # thêm nhãn `queued`), dù hành vi nó định canh không suy suyển gì — test pin
    # cách viết thì cản đúng những bản vá cần làm. Đã chuyển sang kiểm hành vi
    # thật của cả hai đường tạo trong `test_create_endpoint.py` (2026-08-15).


if __name__ == "__main__":
    unittest.main()
