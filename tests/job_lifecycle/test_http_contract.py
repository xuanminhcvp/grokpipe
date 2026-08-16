import unittest
from pathlib import Path

from helpers import FakeBoard, load_sfboard, make_handler, reset_legacy_state

ROOT = Path(__file__).resolve().parents[2]


class HttpContractTest(unittest.TestCase):
    def setUp(self):
        self.m = load_sfboard()
        reset_legacy_state(self.m)
        self.old_board = self.m.BOARD
        self.m.BOARD = FakeBoard()
        self.old_helpers = {
            name: getattr(self.m, name)
            for name in ("_auto_status", "_pl_dem", "_dan_ma_doc", "_auto_vid_doc")
        }
        self.m._auto_status = lambda: {}
        self.m._pl_dem = lambda: 0
        self.m._dan_ma_doc = lambda: {}
        self.m._auto_vid_doc = lambda: False

    def tearDown(self):
        self.m.BOARD = self.old_board
        for name, value in self.old_helpers.items():
            setattr(self.m, name, value)

    def test_jobs_response_keeps_legacy_top_level_schema(self):
        handler = make_handler(self.m, "/api/jobs")
        handler.do_GET()
        code, body = handler.captured
        self.assertEqual(code, 200)
        self.assertEqual(
            set(body),
            {
                "jobs",
                "auto",
                "nhom",
                "hang",
                "tho",
                "vet",
                "pl",
                "dan_ma",
                "loi",
                "auto_vid",
                "mtime",
            },
        )
        self.assertEqual(set(body["hang"]), {"anh", "video"})
        self.assertEqual(set(body["tho"]), {"img", "vid"})

    def test_diagnostics_keeps_legacy_keys_and_adds_shadow_status(self):
        handler = make_handler(self.m, "/api/chan-doan")
        handler.do_GET()
        code, body = handler.captured
        self.assertEqual(code, 200)
        self.assertEqual(
            set(body),
            {
                "hang_doi",
                "tho",
                "chet",
                "lo_dang_hoan",
                "da_huy",
                "dung_gen",
                "job_cho",
                "job_chay",
                "bug_bridge",
                "job_shadow",
                "lich",
                "invariants",
            },
        )
        self.assertEqual(set(body["lich"]), {"executions", "theo_trang_thai"})
        self.assertEqual(
            set(body["bug_bridge"]),
            {"mode", "pending", "last_sync_at", "last_error", "created", "updated"},
        )
        self.assertIn(body["job_shadow"]["mode"], {"legacy", "shadow"})
        self.assertEqual(
            set(body["invariants"]),
            {"tong", "nang_nhat", "theo_ma", "findings"},
        )

    def test_cancel_route_keeps_response_keys(self):
        """GỌI handler thật, so status + khoá của body.

        Bản cũ mang tên contract test nhưng chỉ tìm literal trong file nguồn
        (`'"cho_da_huy": len(cho)'` có nằm đâu đó không). Chuỗi ấy có thể nằm
        trong code chết, trong comment, hay trong một nhánh không bao giờ chạy —
        test vẫn xanh trong khi endpoint đã trả về hình dạng khác. Hợp đồng HTTP
        chỉ chứng minh được bằng cách gọi rồi nhìn thứ đi ra.
        """
        self.m._dat_job("SF-S1-01", {"state": "queued", "msg": "chờ"})
        self.m._dat_job("SF-S1-02", {"state": "running", "msg": "đang vẽ"})

        handler = make_handler(self.m, "/api/huy")
        handler.do_POST()
        code, body = handler.captured

        self.assertEqual(code, 200)
        self.assertEqual(set(body), {"ok", "bo", "cho_da_huy", "dang_chay"})
        self.assertIs(body["ok"], True)
        self.assertEqual(body["cho_da_huy"], 1, "đúng một việc đang chờ bị huỷ")
        self.assertEqual(body["dang_chay"], ["SF-S1-02"],
                         "việc đang chạy phải được LIỆT KÊ, không bị huỷ")

    def test_create_route_keeps_response_keys(self):
        acc_cu, self.m.ACCOUNTS = self.m.ACCOUNTS, []
        try:
            handler = make_handler(self.m, "/api/tao-lo?sf=SF-S1-01,SF-S1-02")
            handler.do_POST()
            code, body = handler.captured

            self.assertEqual(code, 200)
            self.assertIs(body["ok"], True)
            self.assertIn("so_lo", body, "giao diện in 'đã xếp N tin nhắn' từ khoá này")
            self.assertEqual(body["so_lo"], 1)
        finally:
            self.m.ACCOUNTS = acc_cu
