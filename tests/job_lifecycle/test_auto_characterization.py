import unittest
from pathlib import Path

from helpers import function_source

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "sfboard/sfboard.py"


class AutoCharacterizationTest(unittest.TestCase):
    @unittest.expectedFailure
    def test_auto_video_blocks_both_running_and_queued(self):
        source = function_source(BOARD, "_auto_scene")
        normalized = " ".join(source.split())
        self.assertIn(
            'JOBS.get(sh["id"], {}).get("state") in ("running", "queued")',
            normalized,
        )

    def test_auto_image_checks_running_and_queued(self):
        source = function_source(BOARD, "_auto_scene")
        self.assertIn('not in ("running", "queued")', source)

    @unittest.expectedFailure
    def test_auto_producer_observes_same_stop_barrier_as_retry_timer(self):
        source = function_source(BOARD, "_auto_scene")
        self.assertTrue("dung_gen()" in source or "stop_barrier" in source)

    @unittest.expectedFailure
    def test_multi_copy_enqueue_uses_distinct_job_identity_per_copy(self):
        source = BOARD.read_text(encoding="utf-8")
        generate_route = source[
            source.index('elif u.path == "/api/generate"') :
            source.index('elif u.path == "/api/dung-het"')
        ]
        self.assertTrue("copy_index" in generate_route or "job_id" in generate_route)
