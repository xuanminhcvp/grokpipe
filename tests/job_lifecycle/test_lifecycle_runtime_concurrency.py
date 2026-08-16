"""Race ở coordinator phải kết thúc bằng đúng một authority decision."""

import tempfile
import threading
import unittest
from pathlib import Path
from uuid import uuid4

from sfboard.jobs.compat import LegacyAction, LegacyPlan
from sfboard.jobs.models import AssetId, JobKind, JobOrigin, JobState
from sfboard.jobs.producer import CreateJobRequest
from sfboard.jobs.runtime import LifecycleRuntime
from sfboard.jobs.sqlite_store import SQLiteLifecycleRepository


class LifecycleRuntimeConcurrencyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repository = SQLiteLifecycleRepository(
            str(Path(self.tmp.name) / "lifecycle.db"))
        self.runtime = LifecycleRuntime(self.repository)
        self.runtime.accounts.register("9222", allow_video=True, max_slots=2)
        request = CreateJobRequest(
            AssetId("SF-A"), JobKind.IMAGE, JobOrigin.MANUAL, "scope:A",
            manual=True)

        def plan(result):
            job_ids = tuple(job.job_id for job in result.jobs)
            return LegacyPlan((LegacyAction(
                "action:A", ("LO:A",), job_ids, "img", "LO:A", True),))

        self.runtime.submit(request, "click-A", plan)

    def tearDown(self):
        self.repository.close()
        self.tmp.cleanup()

    def test_hai_worker_chi_mot_ben_lease_duoc_execution(self):
        barrier = threading.Barrier(2)
        leases = []

        def lease():
            barrier.wait()
            leases.append(self.runtime.lease_next(
                JobKind.IMAGE, now=0, ttl=30))

        threads = [threading.Thread(target=lease) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3)

        self.assertEqual(sum(item is not None for item in leases), 1)
        self.assertEqual(sum(item is None for item in leases), 1)

    def test_cancel_dua_success_chi_mot_terminal_quyet_dinh(self):
        lease = self.runtime.lease_next(JobKind.IMAGE, now=0, ttl=30)
        job_id = lease.member_job_ids[0]
        barrier = threading.Barrier(2)
        outcomes = []

        def cancel():
            barrier.wait()
            try:
                outcomes.append(("cancel", self.runtime.cancel(
                    job_id, event_id=uuid4(), now=1)))
            except Exception as exc:
                outcomes.append(("cancel-error", type(exc).__name__))

        def succeed():
            barrier.wait()
            try:
                outcomes.append(("success", self.runtime.attempt_succeeded(
                    lease.lease_id, outputs=("/tmp/a.png",),
                    event_id=uuid4(), now=1)))
            except Exception as exc:
                outcomes.append(("success-error", type(exc).__name__))

        threads = [threading.Thread(target=cancel), threading.Thread(target=succeed)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3)

        self.assertIn(
            self.runtime.job(job_id).state,
            {JobState.CANCELLED, JobState.COMPLETED},
        )
        accepted = 0
        for name, value in outcomes:
            if name == "success":
                accepted += 1
            elif name == "cancel" and value.accepted:
                accepted += 1
        self.assertEqual(accepted, 1)


if __name__ == "__main__":
    unittest.main()
