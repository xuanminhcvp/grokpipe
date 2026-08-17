"""Biên executor được test trực tiếp dưới namespace được đo coverage."""

import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from sfboard.jobs.compat import LegacyAction, LegacyPlan
from sfboard.jobs.errors import ErrorClass, ErrorFact
from sfboard.jobs.executor_adapter import (
    ExecutorAttemptResult, LegacyExecutorAdapter,
)
from sfboard.jobs.models import (
    AssetId, AttemptPhase, JobId, JobKind, JobOrigin, JobState,
)
from sfboard.jobs.producer import CreateJobRequest
from sfboard.jobs.runtime import LifecycleRuntime
from sfboard.jobs.sqlite_store import SQLiteLifecycleRepository


class ExecutorAdapterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repository = SQLiteLifecycleRepository(
            str(Path(self.tmp.name) / "lifecycle.db"))
        self.runtime = LifecycleRuntime(self.repository)
        self.runtime.accounts.register("9222", allow_video=True)
        request = CreateJobRequest(
            AssetId("SF-A"), JobKind.IMAGE, JobOrigin.MANUAL, "scope:A",
            manual=True, replace_current=True,
        )

        def plan(result):
            job_id = result.jobs[0].job_id
            return LegacyPlan((LegacyAction(
                "action:A", ("LO:A",), (job_id,), "img", "LO:A", True,
            ),))

        result = self.runtime.submit(request, "adapter-A", plan)
        self.job_id = result.jobs[0].job_id
        self.lease = self.runtime.lease_next(JobKind.IMAGE, now=0, ttl=30)

    def tearDown(self):
        self.repository.close()
        self.tmp.cleanup()

    def test_success_chi_phat_fact_vao_runtime(self):
        adapter = LegacyExecutorAdapter(self.runtime, clock=lambda: 1)

        outcome = adapter.run_once(
            self.lease,
            lambda _lease, _phase: ExecutorAttemptResult({
                self.job_id: ("/tmp/a.png",),
            }),
        )

        self.assertTrue(outcome.verdicts[self.job_id].ghi_de)
        self.assertEqual(self.runtime.job(self.job_id).state, JobState.COMPLETED)

    def test_cancel_trong_luc_execute_khong_finalize_lease_da_thu_hoi(self):
        adapter = LegacyExecutorAdapter(self.runtime, clock=lambda: 1)

        def cancel_during_execute(_lease, _phase):
            verdict = self.runtime.cancel(
                self.job_id, event_id=uuid4(), now=0.5)
            self.assertTrue(verdict.accepted)
            return ExecutorAttemptResult({})

        outcome = adapter.run_once(self.lease, cancel_during_execute)

        self.assertEqual(outcome.verdicts, {})
        self.assertIsNone(outcome.decision)
        self.assertEqual(self.runtime.job(self.job_id).state, JobState.CANCELLED)

    def test_exception_duoc_phan_loai_roi_runtime_quyet_dinh(self):
        def classify(exc, phase):
            return ErrorFact(ErrorClass.VALIDATION, str(exc), phase)

        adapter = LegacyExecutorAdapter(
            self.runtime, classify_exception=classify, clock=lambda: 1)

        def fail(_lease, _phase):
            raise RuntimeError("thiếu ref")

        outcome = adapter.run_once(self.lease, fail)

        self.assertEqual(outcome.decision.reason_code, "validation.permanent")
        self.assertEqual(self.runtime.job(self.job_id).state, JobState.FAILED)
        self.assertEqual(self.runtime.scheduler.ready(now=999), ())

    def test_zero_output_duoc_coi_la_partial_co_gioi_han(self):
        adapter = LegacyExecutorAdapter(self.runtime, clock=lambda: 1)

        outcome = adapter.run_once(
            self.lease,
            lambda _lease, _phase: ExecutorAttemptResult({}),
        )

        self.assertEqual(outcome.decision.reason_code, "batch.partial")
        self.assertEqual(
            self.runtime.job(self.job_id).state, JobState.RETRY_WAIT)

    def test_output_job_id_ngoai_execution_fail_closed(self):
        adapter = LegacyExecutorAdapter(self.runtime, clock=lambda: 1)

        outcome = adapter.run_once(
            self.lease,
            lambda _lease, _phase: ExecutorAttemptResult({
                JobId.new(): ("/tmp/wrong.png",),
            }),
        )

        self.assertEqual(outcome.decision.reason_code, "permanent")
        self.assertEqual(self.runtime.job(self.job_id).state, JobState.FAILED)
        self.assertEqual(self.runtime.scheduler.ready(now=999), ())


if __name__ == "__main__":
    unittest.main()
