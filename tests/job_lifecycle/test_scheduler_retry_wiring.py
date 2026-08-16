"""Retry legacy là transport; Scheduler phải giữ cùng durable execution."""

import unittest

from helpers import FakeBoard, load_sfboard, make_handler, reset_legacy_state
from sfboard.jobs.models import ExecutionState


class SchedulerRetryWiringTest(unittest.TestCase):
    def setUp(self):
        self.m = load_sfboard()
        reset_legacy_state(self.m)
        self.board_old, self.m.BOARD = self.m.BOARD, FakeBoard()
        self.accounts_old, self.m.ACCOUNTS = self.m.ACCOUNTS, []

    def tearDown(self):
        self.m.BOARD = self.board_old
        self.m.ACCOUNTS = self.accounts_old
        reset_legacy_state(self.m)

    def enqueue(self, ident="SF-S1-01"):
        handler = make_handler(self.m, f"/api/generate?sf={ident}")
        handler.do_POST()
        self.assertEqual(handler.captured[0], 200)
        return f"LO:{ident}"

    def test_failure_releases_same_execution_instead_of_finishing(self):
        ident = self.enqueue()
        lease = self.m._lich_nhan("img", ident)

        self.m._lich_tra(lease, outcome="retry", not_before=90.0)

        execution = self.m._JOB_SCHEDULER.get(lease.execution_id)
        self.assertEqual(execution.state, ExecutionState.READY)
        self.assertEqual(execution.not_before, 90.0)
        self.assertEqual(
            self.m._JOB_SCHEDULER.get_by_ident(ident).execution_id,
            lease.execution_id,
        )

    def test_retry_timer_requeues_transport_without_new_execution(self):
        ident = self.enqueue()
        lease = self.m._lich_nhan("img", ident)
        self.m._lich_tra(lease, outcome="retry", not_before=0.0)
        execution_id = lease.execution_id
        self.m._dat_job(ident, {"state": "running", "msg": "retry"})
        stamp = self.m.JOBS[ident]["t"]

        decision = self.m._ban_xep_lai(
            "img", ("img", ident, 1, False),
            self.m.dung_gen(), stamp,
        )

        self.assertEqual(decision, "xep")
        self.assertEqual(
            self.m._JOB_SCHEDULER.get_by_ident(ident).execution_id,
            execution_id,
        )
        self.assertEqual(
            self.m._JOB_SCHEDULER.get(execution_id).state,
            ExecutionState.READY,
        )

    def test_retry_bi_stop_thi_execution_ket_thuc(self):
        ident = self.enqueue()
        lease = self.m._lich_nhan("img", ident)
        self.m._lich_tra(lease, outcome="retry", not_before=90.0)
        self.m._dat_job(ident, {"state": "running", "msg": "retry"})
        stamp = self.m.JOBS[ident]["t"]
        generation = self.m.dung_gen()
        self.m.tang_dung_gen()

        decision = self.m._ban_xep_lai(
            "img", ("img", ident, 1, False), generation, stamp,
        )

        self.assertEqual(decision, "dung")
        self.assertEqual(
            self.m._JOB_SCHEDULER.get(lease.execution_id).state,
            ExecutionState.FINISHED,
        )


if __name__ == "__main__":
    unittest.main()
