"""Recovery chỉ dùng fake lifecycle; không mở browser/provider."""

import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from sfboard.jobs.compat import LegacyAction, LegacyPlan
from sfboard.jobs.models import (
    AssetId, AttemptPhase, CreditConsumption, JobKind, JobOrigin, JobState,
)
from sfboard.jobs.producer import CreateJobRequest
from sfboard.jobs.runtime import LifecycleRuntime
from sfboard.jobs.sqlite_store import SQLiteLifecycleRepository


def request(kind=JobKind.IMAGE, forced=None):
    return CreateJobRequest(
        AssetId("SF-A"), kind, JobOrigin.MANUAL, f"scope:{kind.value}:A",
        manual=True, replace_current=True, forced_account_id=forced,
    )


def plan(result):
    job = result.jobs[0]
    kind = "img" if job.kind is JobKind.IMAGE else "video"
    ident = "LO:A" if kind == "img" else "V-A"
    return LegacyPlan((LegacyAction(
        f"action:{kind}:A", (ident,), (job.job_id,), kind, ident, True,
        forced_account_id=job.forced_account_id,
    ),))


class RecoveryWiringTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "lifecycle.db")

    def tearDown(self):
        self.tmp.cleanup()

    def runtime(self):
        repository = SQLiteLifecycleRepository(self.path)
        runtime = LifecycleRuntime(repository)
        runtime.accounts.register("9222", allow_video=True)
        runtime.accounts.register("9223", allow_video=True)
        return repository, runtime

    def test_queued_song_qua_restart_va_same_key_khong_giao_lan_hai(self):
        repository, runtime = self.runtime()
        first = runtime.submit(request(), "same-key", plan)
        execution_id = runtime.scheduler.ready(now=0)[0].execution_id
        repository.close()

        repository, restarted = self.runtime()
        replay = restarted.submit(request(), "same-key", plan)

        self.assertTrue(replay.replayed)
        self.assertEqual(replay.jobs[0].job_id, first.jobs[0].job_id)
        self.assertEqual(
            restarted.scheduler.ready(now=0)[0].execution_id, execution_id)
        self.assertEqual(len(repository.all_execution_records()), 1)
        repository.close()

    def test_lease_truoc_submit_duoc_tra_ve_retry_wait(self):
        repository, runtime = self.runtime()
        result = runtime.submit(request(), "pre-submit", plan)
        job_id = result.jobs[0].job_id
        lease = runtime.lease_next(JobKind.IMAGE, now=10, ttl=30)
        repository.close()

        repository, restarted = self.runtime()
        summary = restarted.recover(now=20, event_id=uuid4())

        self.assertEqual(summary.retried, 1)
        self.assertEqual(restarted.job(job_id).state, JobState.RETRY_WAIT)
        self.assertEqual(
            restarted.scheduler.ready(now=20)[0].execution_id,
            lease.execution_id,
        )
        repository.close()

    def test_lease_sau_submit_vao_attention_khong_tu_gui_lai(self):
        repository, runtime = self.runtime()
        result = runtime.submit(request(JobKind.VIDEO), "post-submit", plan)
        job_id = result.jobs[0].job_id
        lease = runtime.lease_next(JobKind.VIDEO, now=10, ttl=30)
        runtime.attempt_phase(
            lease.lease_id, AttemptPhase.SUBMITTED, now=11,
            consumes_credit=CreditConsumption.UNKNOWN,
        )
        repository.close()

        repository, restarted = self.runtime()
        summary = restarted.recover(now=20, event_id=uuid4())

        self.assertEqual(summary.needs_attention, 1)
        self.assertEqual(restarted.job(job_id).state, JobState.NEEDS_ATTENTION)
        self.assertEqual(restarted.scheduler.ready(now=999), ())
        repository.close()

    def test_lease_mat_attempt_vao_attention_khong_tu_gui_lai(self):
        repository, runtime = self.runtime()
        result = runtime.submit(request(JobKind.VIDEO), "missing-attempt", plan)
        job_id = result.jobs[0].job_id
        lease = runtime.lease_next(JobKind.VIDEO, now=10, ttl=30)
        repository._conn.execute(
            "DELETE FROM lifecycle_attempts WHERE lease_id = ?",
            (lease.lease_id,),
        )
        repository._conn.commit()
        repository.close()

        repository, restarted = self.runtime()
        summary = restarted.recover(now=20, event_id=uuid4())

        self.assertEqual(summary.needs_attention, 1)
        self.assertEqual(summary.retried, 0)
        self.assertEqual(restarted.job(job_id).state, JobState.NEEDS_ATTENTION)
        self.assertEqual(restarted.scheduler.ready(now=999), ())
        repository.close()

    def test_forced_account_giu_qua_restart(self):
        repository, runtime = self.runtime()
        runtime.submit(request(forced="9223"), "forced", plan)
        repository.close()

        repository, restarted = self.runtime()
        lease = restarted.lease_next(JobKind.IMAGE, now=0, ttl=30)

        self.assertEqual(lease.account_id, "9223")
        repository.close()


if __name__ == "__main__":
    unittest.main()
