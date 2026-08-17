import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sfboard.jobs.live_budget import (
    BudgetConfigurationError,
    BudgetExhausted,
    BudgetScopeConflict,
    PersistentSubmitBudget,
)


class PersistentSubmitBudgetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "grok-budget.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_limit_phai_duong_de_live_grok_fail_closed(self):
        for value in (None, 0, -1, ""):
            with self.subTest(value=value):
                with self.assertRaises(BudgetConfigurationError):
                    PersistentSubmitBudget(
                        self.path, scope="canary-2026-08-17", limit=value)

    def test_reserve_tang_counter_va_restart_khong_reset(self):
        budget = PersistentSubmitBudget(
            self.path, scope="canary-2026-08-17", limit=20)

        first = budget.reserve()
        restarted = PersistentSubmitBudget(
            self.path, scope="canary-2026-08-17", limit=20)
        second = restarted.reserve()

        self.assertEqual((first.reserved, first.remaining), (1, 19))
        self.assertEqual((second.reserved, second.remaining), (2, 18))
        self.assertEqual(json.loads(self.path.read_text())["reserved"], 2)

    def test_cung_file_khong_duoc_doi_scope_hoac_limit(self):
        PersistentSubmitBudget(
            self.path, scope="canary-A", limit=20).reserve()

        with self.assertRaises(BudgetScopeConflict):
            PersistentSubmitBudget(
                self.path, scope="canary-B", limit=20).snapshot()
        with self.assertRaises(BudgetScopeConflict):
            PersistentSubmitBudget(
                self.path, scope="canary-A", limit=21).snapshot()

    def test_concurrent_reserve_khong_vuot_limit(self):
        def reserve_once(_index):
            try:
                return PersistentSubmitBudget(
                    self.path, scope="canary", limit=5).reserve().reserved
            except BudgetExhausted:
                return None

        with ThreadPoolExecutor(max_workers=12) as pool:
            results = tuple(pool.map(reserve_once, range(30)))

        accepted = sorted(value for value in results if value is not None)
        self.assertEqual(accepted, [1, 2, 3, 4, 5])
        self.assertEqual(
            PersistentSubmitBudget(
                self.path, scope="canary", limit=5).snapshot().reserved,
            5,
        )

    def test_exhausted_khong_lam_counter_tang_them(self):
        budget = PersistentSubmitBudget(
            self.path, scope="canary", limit=1)
        budget.reserve()

        with self.assertRaises(BudgetExhausted):
            budget.reserve()

        self.assertEqual(budget.snapshot().reserved, 1)


if __name__ == "__main__":
    unittest.main()
