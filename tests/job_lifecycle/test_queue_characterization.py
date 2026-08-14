import queue
import unittest

from helpers import load_hangdoi, reset_legacy_state


class QueueCharacterizationTest(unittest.TestCase):
    def setUp(self):
        self.h = load_hangdoi()
        reset_legacy_state(self.h)
        self.h.gan_nguon_board(
            lambda: {
                "scenes": [
                    {
                        "shots": [
                            {"id": "V-S1-1", "sf": "SF-S1-1"},
                            {"id": "V-S1-B1", "sf": "SF-S1-B1"},
                            {"id": "V-S1-2", "sf": "SF-S1-2"},
                        ]
                    }
                ]
            },
            lambda: 1,
        )

    def test_order_uses_board_shot_order_including_suffix(self):
        q = queue.PriorityQueue()
        self.h.xep(q, ("img", "SF-S1-2", 0, False))
        self.h.xep(q, ("img", "SF-S1-B1", 0, False))
        self.h.xep(q, ("img", "SF-S1-1", 0, False))
        self.assertEqual(
            self.h.thu_tu_hang(q),
            ["SF-S1-1", "SF-S1-B1", "SF-S1-2"],
        )

    def test_queue_identity_and_take_round_trip(self):
        q = queue.PriorityQueue()
        item = ("img", "LO:SF-S1-1,SF-S1-2", 0, True)
        self.h.xep(q, item)
        self.assertEqual(self.h.y_trong_hang(q), {item[1]})
        self.assertEqual(self.h.lay(q, timeout=0.1), item)

    def test_dat_job_spreads_group_state_to_members(self):
        state = {"state": "queued", "msg": "chờ"}
        self.h.dat_job("LO:A,B", state)
        self.assertEqual(self.h.JOBS["LO:A,B"]["state"], "queued")
        self.assertEqual(self.h.JOBS["A"]["state"], "queued")
        self.assertEqual(self.h.JOBS["B"]["state"], "queued")
        self.assertIsNot(self.h.JOBS["A"], self.h.JOBS["B"])
