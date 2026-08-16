"""`/api/generate` không được đẩy hai bản cùng một việc vào hàng.

Chốt ở sfboard.py chỉ từ chối nhãn `running`, nên bấm 'Tạo lại' lần nữa lúc việc
còn `queued` đẩy BẢN THỨ HAI cùng ident vào hàng. Hậu quả không dừng ở nhãn xấu:

  · thợ nhấc bản một, làm xong → `done`;
  · thợ khác nhấc bản hai → CHẠY LẠI cả lượt render, với video là trừ credit lần
    nữa cho đúng shot vừa dựng xong;
  · và mọi cú vét hàng (`/api/huy`, `/api/dung-het`) gặp bản thừa thì ghi đè lên
    trạng thái cuối.

`_auto_scene` đã chặn đúng cả hai nhãn `("running", "queued")` từ trước — đây chỉ
là áp lại luật ấy cho đường tạo tay, không phải chính sách mới.

Máy trạng thái Hypothesis trong `test_retry_properties.py` tìm ra chuỗi này
(2026-08-15) sau khi thêm bất biến "việc đã xong không bị bôi thành lỗi".
"""

import unittest

from helpers import FakeBoard, load_sfboard, make_handler, reset_legacy_state


class CreateEndpointTest(unittest.TestCase):
    def setUp(self):
        self.m = load_sfboard()
        reset_legacy_state(self.m)
        self.board_cu, self.m.BOARD = self.m.BOARD, FakeBoard()
        self.acc_cu, self.m.ACCOUNTS = self.m.ACCOUNTS, []   # rỗng = không đụng Chrome
        self.m.AUTO.clear()

    def tearDown(self):
        self.m.BOARD = self.board_cu
        self.m.ACCOUNTS = self.acc_cu
        reset_legacy_state(self.m)
        self.m.AUTO.clear()

    def goi(self, path):
        h = make_handler(self.m, path)
        h.do_POST()
        return h.captured

    def test_tao_lai_lan_hai_khi_viec_con_trong_hang_khong_day_them_ban_nua(self):
        self.goi("/api/generate?sf=SF-S1-01")
        sau_lan_dau = self.m.IMG_QUEUE.qsize()
        self.assertEqual(sau_lan_dau, 1, "lần đầu phải vào hàng")

        code, body = self.goi("/api/generate?sf=SF-S1-01")

        self.assertEqual(self.m.IMG_QUEUE.qsize(), sau_lan_dau,
                         "bản thứ hai cùng ident đã lọt vào hàng — thợ sẽ render hai lượt")
        self.assertFalse(body["ok"])

    def test_viec_dang_chay_van_bi_tu_choi_nhu_cu(self):
        """Chốt cũ phải còn nguyên — nới nó ra là mở lại đúng bug 14 job ma."""
        self.m._dat_job("SF-S1-01", {"state": "running", "msg": "đang vẽ"})

        code, body = self.goi("/api/generate?sf=SF-S1-01")

        self.assertFalse(body["ok"])
        self.assertEqual(self.m.IMG_QUEUE.qsize(), 0)

    def test_viec_da_xong_thi_tao_lai_duoc(self):
        """Chặn `queued` không được biến thành chặn nhầm việc đã kết thúc."""
        self.m._dat_job("SF-S1-01", {"state": "done", "msg": "xong"})

        self.goi("/api/generate?sf=SF-S1-01")

        self.assertEqual(self.m.IMG_QUEUE.qsize(), 1)

    def test_viec_loi_thi_tao_lai_duoc(self):
        self.m._dat_job("SF-S1-01", {"state": "error", "msg": "hỏng"})

        self.goi("/api/generate?sf=SF-S1-01")

        self.assertEqual(self.m.IMG_QUEUE.qsize(), 1)

    # ───────────────────────────── /api/tao-lo ────────────────────────────

    def test_tao_lo_bo_qua_sf_dang_cho_trong_hang(self):
        """Đường tạo nhiều SF dính đúng một lỗ với `/api/generate`."""
        self.m._dat_job("SF-S1-01", {"state": "queued", "msg": "chờ"})

        self.goi("/api/tao-lo?sf=SF-S1-01,SF-S1-02")

        trong_hang = self.m._y_trong_hang(self.m.IMG_QUEUE)
        con_lai = {x for i in trong_hang for x in (i[3:].split(",") if i.startswith("LO:") else [i])}
        self.assertNotIn("SF-S1-01", con_lai,
                         "SF đang nằm chờ bị xếp thêm lần nữa — thợ sẽ render hai lượt")
        self.assertIn("SF-S1-02", con_lai, "SF chưa có việc thì vẫn phải được xếp")

    def test_tao_lo_van_bo_qua_sf_dang_chay(self):
        self.m._dat_job("SF-S1-01", {"state": "running", "msg": "đang vẽ"})

        self.goi("/api/tao-lo?sf=SF-S1-01,SF-S1-02")

        trong_hang = self.m._y_trong_hang(self.m.IMG_QUEUE)
        con_lai = {x for i in trong_hang for x in (i[3:].split(",") if i.startswith("LO:") else [i])}
        self.assertNotIn("SF-S1-01", con_lai)
        self.assertIn("SF-S1-02", con_lai)



class ChiaLoTayTest(CreateEndpointTest):
    """Lô user TỰ TÍCH cũng phải chia — đảo luật 'KHÔNG CẮT' của 2026-08-12.

    Luật cũ: tích bao nhiêu gửi bấy nhiêu trong đúng một tin, vì cắt hộ thì user
    tưởng gửi một tin mà thực ra hai, và hai tin là hai chat trắng nên look có
    thể lệch. User chốt lại 2026-08-15: tích 15 thì cũng KHÔNG tạo được vì lỗi
    đính ref, nên "một tin" ấy chỉ là một tin trên lý thuyết. Chia ra còn chạy
    được, không chia thì hỏng cả loạt.
    """

    def ids(self, n):
        return ",".join(f"SF-S1-{i:02d}" for i in range(n))

    def lo_trong_hang(self):
        return sorted(self.m._y_trong_hang(self.m.IMG_QUEUE))

    def test_tich_qua_tran_SF_thi_chia_thanh_nhieu_lo(self):
        self.goi(f"/api/tao-lo?sf={self.ids(12)}")

        lo = self.lo_trong_hang()
        self.assertEqual(len(lo), 2, "tích 12 mà vẫn dồn vào một tin là lỗi cũ")
        self.assertEqual([len(x[3:].split(",")) for x in lo], [10, 2])

    def test_khong_mat_SF_nao_va_giu_dung_thu_tu(self):
        self.goi(f"/api/tao-lo?sf={self.ids(12)}")

        ra = [x for l in self.lo_trong_hang() for x in l[3:].split(",")]
        self.assertEqual(sorted(ra), sorted(self.ids(12).split(",")))

    def test_duoi_tran_thi_van_di_MOT_tin_nhu_cu(self):
        """Không được chẻ vụn cái đang chạy tốt — 4 SF vẫn là một lô."""
        self.goi(f"/api/tao-lo?sf={self.ids(4)}")

        self.assertEqual(len(self.lo_trong_hang()), 1)

    def test_xem_truoc_noi_DUNG_cai_ma_tao_lo_se_lam(self):
        """Ô xem trước và lệnh tạo phải dùng chung một phép chia.

        Lệch nhau thì user bấm Tạo dựa trên một bản đồ sai — đúng thứ endpoint
        xem-lo sinh ra để tránh.
        """
        h = self.mk_handler(f"/api/xem-lo?sf={self.ids(12)}")
        h.do_POST()
        xem = h.captured[1]
        so_lo_xem = sum(len(n["lo"]) for n in xem["nhom"])

        self.goi(f"/api/tao-lo?sf={self.ids(12)}")

        self.assertEqual(so_lo_xem, len(self.lo_trong_hang()))

    def mk_handler(self, path):
        from helpers import make_handler
        return make_handler(self.m, path)


class ProducerCommandEndpointTest(unittest.TestCase):
    """Phase 3 · năm đường tạo phải đi qua ĐÚNG MỘT command boundary.

    Bấm hai lần cùng một ý định (cùng `Idempotency-Key`) phải trả về đúng job
    cũ và KHÔNG xếp thêm bản nào — đây là chốt thay cho phép so nhãn
    `running/queued` vốn thua cuộc đua hai request cùng lúc.

    Mọi field cũ của response phải còn nguyên: giao diện hiện tại đọc chúng.
    """

    SHOT_SCENES = [
        {
            "id": "S1",
            "sfs": [],
            "shots": [
                {"id": "V-S1-01", "sf": "SF-S1-01", "prompt": "cận mặt", "dur": 6},
                {"id": "V-S1-02", "sf": "SF-S1-01", "prompt": "trung", "dur": 6},
            ],
        }
    ]

    def setUp(self):
        self.m = load_sfboard()
        reset_legacy_state(self.m)
        self.board_cu = self.m.BOARD
        self.m.BOARD = FakeBoard(self.SHOT_SCENES, files=["SF-S1-01"])
        self.acc_cu, self.m.ACCOUNTS = self.m.ACCOUNTS, []
        self.m.AUTO.clear()
        self.m._init_job_shadow("shadow")

    def tearDown(self):
        self.m._init_job_shadow("legacy")
        self.m.BOARD = self.board_cu
        self.m.ACCOUNTS = self.acc_cu
        reset_legacy_state(self.m)
        self.m.AUTO.clear()

    def goi(self, path, key=None):
        h = make_handler(self.m, path)
        if key:
            h.headers["Idempotency-Key"] = key
        h.do_POST()
        return h.captured

    # ───────────────────────────── /api/generate ──────────────────────────

    def test_generate_cung_key_tra_cung_job_va_chi_mot_lan_xep(self):
        code, dau = self.goi("/api/generate?sf=SF-S1-01&idempotency_key=click-1")
        _, lai = self.goi("/api/generate?sf=SF-S1-01&idempotency_key=click-1")

        self.assertEqual(code, 200)
        self.assertEqual(dau["job_id"], lai["job_id"])
        self.assertFalse(dau["replayed"])
        self.assertTrue(lai["replayed"])
        self.assertEqual(self.m.IMG_QUEUE.qsize(), 1)

    def test_generate_giu_nguyen_field_cu(self):
        _, body = self.goi("/api/generate?sf=SF-S1-01&idempotency_key=k1")

        self.assertTrue(body["ok"])
        self.assertTrue(body["qua_lo"])
        self.assertEqual(body["so_ban"], 1)
        self.assertEqual(self.m.JOBS["SF-S1-01"]["state"], "queued")
        self.assertNotIn("LO:SF-S1-01", self.m.JOBS)

    def test_key_o_header_thang_key_o_query(self):
        h = make_handler(self.m, "/api/generate?sf=SF-S1-01&idempotency_key=query")
        h.headers["Idempotency-Key"] = "header"
        h.do_POST()

        store = self.m._JOB_PRODUCER.store
        self.assertIsNotNone(store.get_intent("header"))
        self.assertIsNone(store.get_intent("query"))

    def test_generate_nhieu_ban_ra_nhieu_job_id_trong_mot_batch(self):
        code, body = self.goi("/api/generate?sf=SF-S1-01&n=3&idempotency_key=multi")

        self.assertEqual(code, 200)
        self.assertEqual(len(body["job_ids"]), 3)
        self.assertEqual(len(set(body["job_ids"])), 3)
        self.assertIsNotNone(body["batch_id"])
        self.assertEqual(self.m.IMG_QUEUE.qsize(), 3)

    def test_hai_request_song_song_cung_key_chi_xep_mot_lan(self):
        import threading

        ket_qua = []
        rao = threading.Barrier(2)

        def bam():
            rao.wait()
            ket_qua.append(self.goi("/api/generate?sf=SF-S1-01", key="double"))

        luong = [threading.Thread(target=bam) for _ in range(2)]
        for t in luong:
            t.start()
        for t in luong:
            t.join(5)

        self.assertEqual(len(ket_qua), 2)
        self.assertEqual(ket_qua[0][1]["job_ids"], ket_qua[1][1]["job_ids"])
        self.assertEqual(self.m.IMG_QUEUE.qsize(), 1)

    def test_cung_key_cho_hai_y_dinh_khac_nhau_bi_tu_choi_409(self):
        self.goi("/api/generate?sf=SF-S1-01&idempotency_key=dung-chung")
        code, body = self.goi("/api/generate?sf=SF-S1-02&idempotency_key=dung-chung")

        self.assertEqual(code, 409)
        self.assertFalse(body["ok"])
        self.assertEqual(self.m.IMG_QUEUE.qsize(), 1)

    # ───────────────────────────── /api/master ────────────────────────────

    def test_master_chay_giu_field_cu_va_them_job_ids(self):
        self.m.BOARD = FakeBoard([
            {
                "id": "S1",
                "sfs": [
                    {"id": "SF-S1-01", "luatchung": "sảnh"},
                    {"id": "SF-S2-01", "luatchung": "bếp"},
                ],
                "shots": [],
            }
        ])

        code, body = self.goi("/api/master?chay=1&idempotency_key=master-1")

        self.assertEqual(code, 200)
        self.assertEqual(body["so"], 2)
        self.assertEqual(sorted(body["ds"]), ["SF-S1-01", "SF-S2-01"])
        self.assertEqual(len(body["job_ids"]), 2)
        self.assertEqual(
            sorted(self.m._y_trong_hang(self.m.IMG_QUEUE)),
            ["LO:SF-S1-01", "LO:SF-S2-01"],
        )

    # ───────────────────────────── /api/tao-lo ────────────────────────────

    def test_tao_lo_giu_field_cu_va_them_job_ids(self):
        code, body = self.goi("/api/tao-lo?sf=SF-S9-01,SF-S9-02&idempotency_key=lo-1")

        self.assertEqual(code, 200)
        self.assertEqual(body["so_lo"], 1)
        self.assertEqual(body["ep_tk"], 0)
        self.assertIn("lo", body)
        self.assertEqual(len(body["job_ids"]), 2)
        self.assertEqual(
            self.m._y_trong_hang(self.m.IMG_QUEUE), {"LO:SF-S9-01,SF-S9-02"}
        )
        self.assertEqual(self.m.JOBS["SF-S9-01"]["state"], "queued")

    def test_tao_lo_cung_key_khong_xep_lo_thu_hai(self):
        self.goi("/api/tao-lo?sf=SF-S9-01,SF-S9-02", key="lo-double")
        self.goi("/api/tao-lo?sf=SF-S9-01,SF-S9-02", key="lo-double")

        self.assertEqual(self.m.IMG_QUEUE.qsize(), 1)

    def test_tao_lo_ep_tai_khoan_van_giao_dich_danh(self):
        code, body = self.goi(
            "/api/tao-lo?sf=SF-S9-01,SF-S9-02&tk=9225&idempotency_key=lo-ep"
        )

        self.assertEqual(code, 200)
        self.assertEqual(body["ep_tk"], 9225)
        self.assertEqual(self.m.CHO_RIENG[9225], ["LO:SF-S9-01,SF-S9-02"])
        self.assertEqual(self.m.IMG_QUEUE.qsize(), 0)

    # ──────────────────────── /api/genvideo · /api/video-lo ───────────────

    def test_genvideo_tra_job_id_va_xep_dung_mot_viec(self):
        code, body = self.goi("/api/genvideo?sf=V-S1-01&idempotency_key=vid-1")

        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertIsNotNone(body["job_id"])
        self.assertEqual(self.m.VID_QUEUE.qsize(), 1)
        self.assertEqual(self.m.JOBS["V-S1-01"]["state"], "queued")

    def test_genvideo_cung_key_khong_tru_credit_lan_hai(self):
        self.goi("/api/genvideo?sf=V-S1-01", key="vid-double")
        self.goi("/api/genvideo?sf=V-S1-01", key="vid-double")

        self.assertEqual(self.m.VID_QUEUE.qsize(), 1)

    def test_video_lo_giu_field_cu_va_them_job_ids(self):
        code, body = self.goi("/api/video-lo?scene=S1&idempotency_key=vlo-1")

        self.assertEqual(code, 200)
        self.assertEqual(body["so"], 2)
        self.assertEqual(set(body["bo"]),
                         {"co_video", "thieu_sf", "thieu_prompt", "dang_chay"})
        self.assertEqual(len(body["job_ids"]), 2)
        self.assertEqual(self.m.VID_QUEUE.qsize(), 2)


class LegacyModeUnchangedTest(CreateEndpointTest):
    """Mode mặc định `legacy` không được đổi hình dạng response hay hàng đợi."""

    def test_generate_legacy_khong_kem_job_id(self):
        _, body = self.goi("/api/generate?sf=SF-S1-01")

        self.assertTrue(body["ok"])
        self.assertIsNone(body["job_id"])
        self.assertEqual(body["job_ids"], [])
        self.assertFalse(body["replayed"])
        self.assertEqual(self.m.IMG_QUEUE.qsize(), 1)

    def test_generate_legacy_giu_dung_tuple_hang_doi_cu(self):
        self.goi("/api/generate?sf=SF-S1-01")

        item = self.m.IMG_QUEUE.get_nowait()[2]
        self.assertEqual(item, ("img", "LO:SF-S1-01", 0, True))


if __name__ == "__main__":
    unittest.main()
