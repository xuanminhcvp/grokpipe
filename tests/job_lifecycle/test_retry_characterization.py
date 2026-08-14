import unittest
from pathlib import Path

from helpers import function_source

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "sfboard/sfboard.py"


class RetryCharacterizationTest(unittest.TestCase):
    def test_retry_timer_checks_stop_generation_and_cancel_before_enqueue(self):
        # Hai phép soi này đã tách sang `_quyet_xep_lai` (2026-08-14) để thử được
        # mà không phải chờ đồng hồ thật. Hợp đồng KHÔNG đổi: vẫn phải soi thế hệ
        # dừng và cờ huỷ — và vẫn phải ĐỌC MÀ KHÔNG ĂN cờ — trước khi xếp lại.
        quyet = function_source(BOARD, "_quyet_xep_lai")
        self.assertIn("dung_gen() != gen", quyet)
        self.assertIn("_bi_huy(ident, an=False)", quyet)

        source = function_source(BOARD, "_xep_lai_sau")
        self.assertIn("_quyet_xep_lai(item[1], gen)", source)
        self.assertIn("_xep(Q, item)", source)
        # Bị từ chối xếp lại thì PHẢI sửa nhãn, không được bỏ về lặng lẽ:
        # nhãn 'đang chạy' còn lại là job ma, và nó chặn luôn nút Tạo lại.
        self.assertIn("_dat_job(item[1]", source)

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
