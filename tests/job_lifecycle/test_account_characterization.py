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

    @unittest.expectedFailure
    def test_forced_account_constraint_is_carried_by_every_retry_item(self):
        retry_source = function_source(BOARD, "_xep_lai_sau")
        self.assertIn("forced_account", retry_source)
