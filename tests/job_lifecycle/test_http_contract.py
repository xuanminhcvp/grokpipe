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

    def test_diagnostics_keeps_legacy_keys_and_adds_only_bug_bridge(self):
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
            },
        )
        self.assertEqual(
            set(body["bug_bridge"]),
            {"mode", "pending", "last_sync_at", "last_error", "created", "updated"},
        )

    def test_create_and_cancel_routes_keep_response_keys(self):
        source = (ROOT / "sfboard/sfboard.py").read_text(encoding="utf-8")
        self.assertIn('{"ok": True, "qua_lo": True, "so_ban": so_ban}', source)
        self.assertIn('"cho_da_huy": len(cho)', source)
        self.assertIn('"dang_chay": dang', source)
        self.assertIn('{"ok": True, "video": True}', source)
