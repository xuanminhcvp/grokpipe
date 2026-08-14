import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class CurrentStateWriterInventoryTest(unittest.TestCase):
    def test_legacy_authority_markers_remain_visible_until_cutover(self):
        hangdoi = (ROOT / "sfboard/hangdoi.py").read_text(encoding="utf-8")
        board = (ROOT / "sfboard/sfboard.py").read_text(encoding="utf-8")
        required = {
            "JOBS writer hook": "class _Jobs(dict)",
            "group state spread": "def dat_job(",
            "image queue": "IMG_QUEUE",
            "video queue": "VID_QUEUE",
            "retry timer": "def _xep_lai_sau(",
            "retry guard": "_HOAN",
            "cancel flags": "DA_HUY",
            "forced account queue": "CHO_RIENG",
            "stop generation": "tang_dung_gen()",
            "auto producer": "def _auto_scene(",
            "worker assignment": "def _worker(",
        }
        combined = hangdoi + "\n" + board
        missing = [label for label, marker in required.items() if marker not in combined]
        self.assertEqual(missing, [], f"Authority marker biến mất: {missing}")

    def test_every_direct_jobs_write_stays_auditable(self):
        board = (ROOT / "sfboard/sfboard.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(board.count("JOBS["), 20)
        self.assertIn("_dat_job(", board)
