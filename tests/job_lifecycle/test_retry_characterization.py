import unittest
from pathlib import Path

from helpers import function_source

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "sfboard/sfboard.py"


class RetryCharacterizationTest(unittest.TestCase):
    def test_retry_timer_checks_stop_generation_and_cancel_before_enqueue(self):
        source = function_source(BOARD, "_xep_lai_sau")
        self.assertIn("dung_gen() != gen", source)
        self.assertIn("_bi_huy(item[1], an=False)", source)
        self.assertIn("_xep(Q, item)", source)

    def test_retry_authorities_are_explicitly_counted(self):
        source = BOARD.read_text(encoding="utf-8")
        markers = ["_xep_lai_sau(", "_HOAN", "AUTO_MAX_TRY", "VID_MAX_TRY"]
        self.assertEqual([marker for marker in markers if marker not in source], [])

    def test_video_has_inner_session_reconnect_and_outer_retry_cap(self):
        video = function_source(BOARD, "_gen_video")
        worker = function_source(BOARD, "_worker")
        self.assertIn("for attempt in range(2)", video)
        self.assertIn("_is_dead_session_error(e)", video)
        self.assertIn("VID_MAX_TRY", worker)
        self.assertIn("_xep_lai_sau", worker)
