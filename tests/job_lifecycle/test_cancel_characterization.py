import queue
import unittest

from helpers import load_hangdoi, reset_legacy_state


class CancelCharacterizationTest(unittest.TestCase):
    def setUp(self):
        self.h = load_hangdoi()
        reset_legacy_state(self.h)

    def test_cancel_flag_can_be_peeked_without_consuming(self):
        self.h.DA_HUY.add("A")
        self.assertTrue(self.h.bi_huy("A", an=False))
        self.assertTrue(self.h.bi_huy("A", an=True))
        self.assertFalse(self.h.bi_huy("A", an=False))

    def test_new_manual_intent_clears_old_cancel_flag(self):
        self.h.DA_HUY.update({"A", "LO:A"})
        self.h.bo_co_huy("A", "LO:A")
        self.assertFalse(self.h.DA_HUY)

    def test_stop_generation_is_monotonic(self):
        before = self.h.dung_gen()
        self.assertEqual(self.h.tang_dung_gen(), before + 1)
        self.assertEqual(self.h.dung_gen(), before + 1)

    @unittest.expectedFailure
    def test_member_only_jobs_can_resolve_physical_group_queue_identity(self):
        q = queue.PriorityQueue()
        self.h.JOBS["A"] = {"state": "queued", "msg": "chờ"}
        self.h.JOBS["B"] = {"state": "queued", "msg": "chờ"}
        self.h.xep(q, ("img", "LO:A,B", 0, False))
        queued_members = {
            key for key, value in self.h.JOBS.items() if value["state"] == "queued"
        }
        cancel_tokens = set(queued_members)
        cancel_tokens.update(
            key
            for key in self.h.JOBS
            if key.startswith("LO:")
            and any(member in queued_members for member in key[3:].split(","))
        )
        self.assertIn("LO:A,B", cancel_tokens)
