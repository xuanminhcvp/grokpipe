"""Fake E2E cho authority mới; tuyệt đối không mở provider."""

from contextlib import contextmanager
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from sfboard.jobs.compat import LegacyAction, LegacyPlan
from sfboard.jobs.errors import ErrorClass, ErrorFact
from sfboard.jobs.models import (
    AssetId, AttemptPhase, BatchMode, CreditConsumption, JobKind, JobOrigin,
    JobId, JobState,
)
from sfboard.jobs.producer import CreateBatchRequest, CreateJobRequest
from sfboard.jobs.results import CommitDecision
from sfboard.jobs.retry import RetryAction
from sfboard.jobs.runtime import LifecycleRuntime
from sfboard.jobs.sqlite_store import SQLiteLifecycleRepository


class LifecycleRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "lifecycle.db")
        self.repository = SQLiteLifecycleRepository(self.path)
        self.runtime = LifecycleRuntime(self.repository)
        self.runtime.accounts.register("9222", allow_video=True, max_slots=1)
        self.runtime.accounts.register("9223", allow_video=True, max_slots=1)

    def tearDown(self):
        self.repository.close()
        self.tmp.cleanup()

    @staticmethod
    def request(*, forced=None, fallback=False):
        return CreateJobRequest(
            AssetId("SF-S1-01"), JobKind.IMAGE, JobOrigin.MANUAL,
            "board:SF-S1-01", manual=True, replace_current=True,
            forced_account_id=forced, allow_account_fallback=fallback,
        )

    @staticmethod
    def plan(result):
        job_ids = tuple(job.job_id for job in result.jobs)
        return LegacyPlan((LegacyAction(
            action_id="image:SF-S1-01",
            legacy_keys=("LO:SF-S1-01",),
            job_ids=job_ids,
            queue_kind="img",
            queue_ident="LO:SF-S1-01",
            manual=True,
            state_idents=("SF-S1-01",),
            forced_account_id=result.jobs[0].forced_account_id,
        ),))

    def submit(self, key="click-1", **request_kw):
        return self.runtime.submit(
            self.request(**request_kw), key, self.plan)

    def test_create_lease_success_di_qua_mot_runtime(self):
        result = self.submit()
        job_id = result.jobs[0].job_id
        self.assertEqual(self.runtime.job(job_id).state, JobState.QUEUED)

        lease = self.runtime.lease_next(JobKind.IMAGE, now=10, ttl=30)
        self.assertEqual(self.runtime.job(job_id).state, JobState.RUNNING)
        self.assertEqual(lease.account_id, "9222")

        verdicts = self.runtime.attempt_succeeded(
            lease.lease_id, outputs=("/tmp/a.png",), event_id=uuid4())

        self.assertEqual(self.runtime.job(job_id).state, JobState.COMPLETED)
        self.assertTrue(verdicts[job_id].ghi_de)
        self.assertEqual(self.runtime.scheduler.ready(now=100), ())

    def test_lease_mang_dung_slot_da_duoc_allocator_cap(self):
        result = self.submit()

        lease = self.runtime.lease_next(JobKind.IMAGE, now=10, ttl=30)

        seats = self.runtime.accounts.seats_of(lease.account_id)
        self.assertEqual(len(seats), 1)
        self.assertEqual(lease.account_seat_id, seats[0].lease_id)
        self.assertEqual(lease.account_slot, seats[0].slot)

    def test_validation_error_dung_han_khong_retry(self):
        result = self.submit()
        job_id = result.jobs[0].job_id
        lease = self.runtime.lease_next(JobKind.IMAGE, now=0, ttl=30)

        decision = self.runtime.attempt_failed(
            lease.lease_id,
            ErrorFact(ErrorClass.VALIDATION, "thiếu ref", AttemptPhase.ATTACHING),
            event_id=uuid4(), now=1,
        )

        self.assertEqual(self.runtime.job(job_id).state, JobState.FAILED)
        self.assertEqual(decision.reason_code, "validation.permanent")
        self.assertEqual(self.runtime.scheduler.ready(now=999), ())

    def test_provider_transient_release_cung_execution_voi_not_before(self):
        result = self.submit()
        job_id = result.jobs[0].job_id
        lease = self.runtime.lease_next(JobKind.IMAGE, now=10, ttl=30)
        execution_id = lease.execution_id

        decision = self.runtime.attempt_failed(
            lease.lease_id,
            ErrorFact(
                ErrorClass.PROVIDER_TRANSIENT, "provider bận",
                AttemptPhase.ATTACHING),
            event_id=uuid4(), now=20,
        )

        self.assertEqual(self.runtime.job(job_id).state, JobState.RETRY_WAIT)
        self.assertEqual(
            self.runtime.scheduler.get(execution_id).not_before,
            20 + decision.delay,
        )
        self.assertEqual(self.runtime.scheduler.ready(now=20), ())
        self.assertEqual(
            self.runtime.scheduler.ready(now=20 + decision.delay)[0].execution_id,
            execution_id,
        )

    def test_mat_ket_noi_sau_submit_vao_attention_khong_gui_lai(self):
        result = self.submit()
        job_id = result.jobs[0].job_id
        lease = self.runtime.lease_next(JobKind.IMAGE, now=10, ttl=30)
        self.runtime.attempt_phase(
            lease.lease_id, AttemptPhase.SUBMITTED, now=11,
            consumes_credit=CreditConsumption.UNKNOWN,
        )

        decision = self.runtime.attempt_failed(
            lease.lease_id,
            ErrorFact(
                ErrorClass.SESSION_TRANSIENT, "mất cửa sổ",
                AttemptPhase.SUBMITTED),
            event_id=uuid4(), now=12,
        )

        self.assertEqual(decision.to_state, JobState.NEEDS_ATTENTION)
        self.assertEqual(self.runtime.job(job_id).state, JobState.NEEDS_ATTENTION)
        self.assertEqual(self.runtime.scheduler.ready(now=999), ())

    def test_forced_account_ap_dung_cho_attempt(self):
        self.submit(forced="9223")

        lease = self.runtime.lease_next(JobKind.IMAGE, now=0, ttl=30)

        self.assertEqual(lease.account_id, "9223")

    def test_same_idempotency_key_khong_tao_execution_thu_hai(self):
        first = self.submit("same-key")
        second = self.submit("same-key")

        self.assertTrue(second.replayed)
        self.assertEqual(first.jobs, second.jobs)
        self.assertEqual(len(self.repository.all_execution_records()), 1)

    def test_same_key_sau_completed_khong_tao_execution_moi(self):
        first = self.submit("completed-key")
        lease = self.runtime.lease_next(JobKind.IMAGE, now=0, ttl=30)
        self.runtime.attempt_succeeded(
            lease.lease_id,
            outputs=("/tmp/a.png",),
            event_id=uuid4(),
            now=1,
        )

        replay = self.submit("completed-key")

        self.assertTrue(replay.replayed)
        self.assertEqual(replay.jobs[0].job_id, first.jobs[0].job_id)
        self.assertEqual(self.runtime.scheduler.active_executions(), ())
        self.assertEqual(len(self.repository.all_execution_records()), 1)

    def test_partial_batch_chi_retry_member_thieu_khong_regress_member_xong(self):
        members = tuple(
            CreateJobRequest(
                AssetId(f"SF-{index}"), JobKind.IMAGE, JobOrigin.MANUAL,
                f"scope:partial:{index}", manual=True, replace_current=True,
            )
            for index in range(3)
        )

        def grouped_plan(result):
            return LegacyPlan((LegacyAction(
                "partial-group", ("LO:SF-0,SF-1,SF-2",),
                tuple(job.job_id for job in result.jobs),
                "img", "LO:SF-0,SF-1,SF-2", True,
                state_idents=("SF-0", "SF-1", "SF-2"),
            ),))

        result = self.runtime.submit(
            CreateBatchRequest(members, BatchMode.IMAGE_GROUP),
            "partial-group", grouped_plan)
        first_lease = self.runtime.lease_next(JobKind.IMAGE, now=0, ttl=30)
        outputs = {
            result.jobs[0].job_id: ("/tmp/0.png",),
            result.jobs[1].job_id: ("/tmp/1.png",),
        }

        verdicts, decision = self.runtime.attempt_partially_succeeded(
            first_lease.lease_id, outputs=outputs,
            event_id=uuid4(), now=1)

        self.assertEqual(set(verdicts), set(outputs))
        self.assertEqual(decision.to_state, JobState.RETRY_WAIT)
        self.assertEqual(
            tuple(self.runtime.job(job.job_id).state for job in result.jobs),
            (JobState.COMPLETED, JobState.COMPLETED, JobState.RETRY_WAIT),
        )
        versions = tuple(
            self.runtime.job(job.job_id).version for job in result.jobs[:2])

        second_lease = self.runtime.lease_next(
            JobKind.IMAGE, now=decision.delay + 1, ttl=30)
        final = self.runtime.attempt_succeeded(
            second_lease.lease_id,
            outputs={result.jobs[2].job_id: ("/tmp/2.png",)},
            event_id=uuid4(), now=decision.delay + 2,
        )

        self.assertEqual(set(final), {result.jobs[2].job_id})
        self.assertEqual(
            tuple(self.runtime.job(job.job_id).state for job in result.jobs),
            (JobState.COMPLETED,) * 3,
        )
        self.assertEqual(
            tuple(self.runtime.job(job.job_id).version
                  for job in result.jobs[:2]),
            versions,
        )

    def test_mat_phien_truoc_submit_noi_lai_ngay_tren_cung_account(self):
        self.submit()
        first = self.runtime.lease_next(JobKind.IMAGE, now=0, ttl=30)

        decision = self.runtime.attempt_failed(
            first.lease_id,
            ErrorFact(
                ErrorClass.SESSION_TRANSIENT, "mất cửa sổ",
                AttemptPhase.ATTACHING),
            event_id=uuid4(), now=1,
        )
        second = self.runtime.lease_next(JobKind.IMAGE, now=1, ttl=30)

        self.assertEqual(decision.reason_code, "session.reconnect")
        self.assertEqual(second.execution_id, first.execution_id)
        self.assertEqual(second.account_id, first.account_id)

    def test_provider_transient_xoay_sang_account_khac(self):
        self.submit()
        first = self.runtime.lease_next(JobKind.IMAGE, now=0, ttl=30)
        decision = self.runtime.attempt_failed(
            first.lease_id,
            ErrorFact(
                ErrorClass.PROVIDER_TRANSIENT, "provider bận",
                AttemptPhase.ATTACHING),
            event_id=uuid4(), now=1,
        )

        second = self.runtime.lease_next(
            JobKind.IMAGE, now=1 + decision.delay, ttl=30)

        self.assertTrue(decision.rotate_account)
        self.assertNotEqual(second.account_id, first.account_id)

    def test_forced_account_khong_bi_xoay_sau_retry(self):
        self.submit(forced="9223")
        first = self.runtime.lease_next(JobKind.IMAGE, now=0, ttl=30)
        decision = self.runtime.attempt_failed(
            first.lease_id,
            ErrorFact(
                ErrorClass.PROVIDER_TRANSIENT, "provider bận",
                AttemptPhase.ATTACHING),
            event_id=uuid4(), now=1,
        )

        second = self.runtime.lease_next(
            JobKind.IMAGE, now=1 + decision.delay, ttl=30)

        self.assertEqual(first.account_id, "9223")
        self.assertEqual(second.account_id, "9223")

    def test_khong_co_account_thi_execution_van_cho(self):
        runtime = LifecycleRuntime(self.repository)
        runtime.submit(self.request(), "no-seat", self.plan)

        self.assertIsNone(runtime.lease_next(JobKind.IMAGE, now=0, ttl=30))
        self.assertEqual(len(runtime.scheduler.ready(now=0)), 1)
        self.assertEqual(self.repository.attempts_for_execution(
            runtime.scheduler.ready(now=0)[0].execution_id), ())

    def test_user_mutation_khong_bi_ket_qua_muon_ghi_de(self):
        result = self.submit()
        lease = self.runtime.lease_next(JobKind.IMAGE, now=10, ttl=30)
        self.runtime.note_user_mutation("SF-S1-01", now=11)

        verdicts = self.runtime.attempt_succeeded(
            lease.lease_id, outputs=("/tmp/a.png",),
            event_id=uuid4(), now=12)

        self.assertEqual(
            verdicts[result.jobs[0].job_id].decision,
            CommitDecision.STORE_AS_VERSION,
        )

    def test_success_fact_trung_khong_transition_hai_lan(self):
        result = self.submit()
        job_id = result.jobs[0].job_id
        lease = self.runtime.lease_next(JobKind.IMAGE, now=0, ttl=30)
        fact_id = uuid4()

        first = self.runtime.attempt_succeeded(
            lease.lease_id, outputs=("/tmp/a.png",),
            event_id=fact_id, now=1)
        second = self.runtime.attempt_succeeded(
            lease.lease_id, outputs=("/tmp/a.png",),
            event_id=fact_id, now=2)

        self.assertEqual(first, second)
        self.assertEqual(self.runtime.job(job_id).version, 3)

    def test_cancel_queued_khoa_execution_va_job(self):
        result = self.submit()
        job_id = result.jobs[0].job_id

        verdict = self.runtime.cancel(job_id, event_id=uuid4(), now=1)

        self.assertTrue(verdict.accepted)
        self.assertEqual(verdict.cancelled_job_ids, (job_id,))
        self.assertEqual(self.runtime.job(job_id).state, JobState.CANCELLED)
        self.assertEqual(self.runtime.scheduler.ready(now=999), ())

    def test_cancel_anh_dang_chay_huy_ca_execution(self):
        result = self.submit()
        job_id = result.jobs[0].job_id
        lease = self.runtime.lease_next(JobKind.IMAGE, now=0, ttl=30)

        verdict = self.runtime.cancel(job_id, event_id=uuid4(), now=1)

        self.assertTrue(verdict.accepted)
        self.assertEqual(self.runtime.job(job_id).state, JobState.CANCELLED)
        attempt = self.repository.attempt_for_lease(lease.lease_id)
        self.assertEqual(attempt.outcome.value, "cancelled")
        self.assertEqual(self.runtime.scheduler.ready(now=999), ())

    def test_cancel_video_sau_submit_bi_tu_choi(self):
        request = CreateJobRequest(
            AssetId("SF-S1-01"), JobKind.VIDEO, JobOrigin.MANUAL,
            "board:video:SF-S1-01", manual=True, replace_current=True,
        )

        def plan(result):
            return LegacyPlan((LegacyAction(
                "video:SF-S1-01", ("SF-S1-01",),
                tuple(job.job_id for job in result.jobs),
                "video", "SF-S1-01", True,
            ),))

        result = self.runtime.submit(request, "video-1", plan)
        job_id = result.jobs[0].job_id
        lease = self.runtime.lease_next(JobKind.VIDEO, now=0, ttl=30)
        self.runtime.attempt_phase(
            lease.lease_id, AttemptPhase.SUBMITTED, now=1,
            consumes_credit=CreditConsumption.UNKNOWN,
        )

        verdict = self.runtime.cancel(job_id, event_id=uuid4(), now=2)

        self.assertFalse(verdict.accepted)
        self.assertEqual(verdict.reason_code, "video.already_submitted")
        self.assertEqual(self.runtime.job(job_id).state, JobState.RUNNING)

    def test_success_khong_output_bi_tu_choi_va_job_van_running(self):
        result = self.submit()
        job_id = result.jobs[0].job_id
        lease = self.runtime.lease_next(JobKind.IMAGE, now=0, ttl=30)

        with self.assertRaises(ValueError):
            self.runtime.attempt_succeeded(
                lease.lease_id, outputs=(), event_id=uuid4(), now=1)

        self.assertEqual(self.runtime.job(job_id).state, JobState.RUNNING)
        self.assertEqual(
            self.repository.attempt_for_lease(lease.lease_id).phase,
            AttemptPhase.PREPARING,
        )

    def test_success_khong_duoc_bo_qua_output_job_ngoai_execution(self):
        result = self.submit()
        job_id = result.jobs[0].job_id
        lease = self.runtime.lease_next(JobKind.IMAGE, now=0, ttl=30)

        with self.assertRaisesRegex(ValueError, "JobId ngoài execution"):
            self.runtime.attempt_succeeded(
                lease.lease_id,
                outputs={
                    job_id: ("/tmp/a.png",),
                    JobId.new(): ("/tmp/wrong.png",),
                },
                event_id=uuid4(), now=1,
            )

        self.assertEqual(self.runtime.job(job_id).state, JobState.RUNNING)

    def test_commit_success_loi_thi_scheduler_duoc_nap_lai_de_thu_lai(self):
        result = self.submit()
        job_id = result.jobs[0].job_id
        lease = self.runtime.lease_next(JobKind.IMAGE, now=0, ttl=30)
        original_transaction = self.repository.transaction

        @contextmanager
        def fail_commit():
            outer = self.repository._tx_depth == 0
            with original_transaction():
                yield self.repository
                if outer:
                    raise RuntimeError("simulated commit failure")

        with patch.object(self.repository, "transaction", fail_commit):
            with self.assertRaisesRegex(RuntimeError, "commit failure"):
                self.runtime.attempt_succeeded(
                    lease.lease_id, outputs=("/tmp/a.png",),
                    event_id=uuid4(), now=1)

        self.assertEqual(self.runtime.job(job_id).state, JobState.RUNNING)
        verdicts = self.runtime.attempt_succeeded(
            lease.lease_id, outputs=("/tmp/a.png",),
            event_id=uuid4(), now=2)
        self.assertIn(job_id, verdicts)
        self.assertEqual(self.runtime.job(job_id).state, JobState.COMPLETED)

    def test_commit_retry_loi_thi_scheduler_duoc_nap_lai_de_thu_lai(self):
        result = self.submit()
        job_id = result.jobs[0].job_id
        lease = self.runtime.lease_next(JobKind.IMAGE, now=0, ttl=30)
        error = ErrorFact(
            ErrorClass.PROVIDER_TRANSIENT, "provider bận",
            AttemptPhase.ATTACHING,
        )
        original_transaction = self.repository.transaction

        @contextmanager
        def fail_commit():
            outer = self.repository._tx_depth == 0
            with original_transaction():
                yield self.repository
                if outer:
                    raise RuntimeError("simulated commit failure")

        with patch.object(self.repository, "transaction", fail_commit):
            with self.assertRaisesRegex(RuntimeError, "commit failure"):
                self.runtime.attempt_failed(
                    lease.lease_id, error, event_id=uuid4(), now=1)

        self.assertEqual(self.runtime.job(job_id).state, JobState.RUNNING)
        decision = self.runtime.attempt_failed(
            lease.lease_id, error, event_id=uuid4(), now=2)
        self.assertEqual(decision.action, RetryAction.RETRY)
        self.assertEqual(self.runtime.job(job_id).state, JobState.RETRY_WAIT)

    def test_commit_cancel_loi_thi_scheduler_duoc_nap_lai_de_thu_lai(self):
        result = self.submit()
        job_id = result.jobs[0].job_id
        original_transaction = self.repository.transaction

        @contextmanager
        def fail_commit():
            outer = self.repository._tx_depth == 0
            with original_transaction():
                yield self.repository
                if outer:
                    raise RuntimeError("simulated commit failure")

        with patch.object(self.repository, "transaction", fail_commit):
            with self.assertRaisesRegex(RuntimeError, "commit failure"):
                self.runtime.cancel(job_id, event_id=uuid4(), now=1)

        self.assertEqual(self.runtime.job(job_id).state, JobState.QUEUED)
        verdict = self.runtime.cancel(job_id, event_id=uuid4(), now=2)
        self.assertTrue(verdict.accepted)
        self.assertEqual(self.runtime.job(job_id).state, JobState.CANCELLED)

    def test_cung_queue_ident_khac_scope_lease_dung_execution_dau_tien(self):
        first = self.submit("scope-1")
        second_request = CreateJobRequest(
            AssetId("SF-S1-02"), JobKind.IMAGE, JobOrigin.MANUAL,
            "board:SF-S1-02", manual=True, replace_current=True,
        )

        def same_ident_plan(result):
            return LegacyPlan((LegacyAction(
                "image:SF-S1-02", ("LO:SF-S1-01",),
                tuple(job.job_id for job in result.jobs),
                "img", "LO:SF-S1-01", True,
            ),))

        second = self.runtime.submit(
            second_request, "scope-2", same_ident_plan)

        active = tuple(
            record for record in self.repository.all_execution_records()
            if record.state != "finished"
        )
        self.assertEqual(len(active), 2)
        self.assertEqual(
            {record.member_keys for record in active},
            {(str(first.jobs[0].job_id),), (str(second.jobs[0].job_id),)},
        )

        lease = self.runtime.lease_next(JobKind.IMAGE, now=0, ttl=30)
        execution = self.runtime.scheduler.get(lease.execution_id)

        self.assertEqual(lease.member_job_ids, (first.jobs[0].job_id,))
        self.assertEqual(
            execution.member_keys, (str(first.jobs[0].job_id),))
        self.assertEqual(
            self.runtime.job(second.jobs[0].job_id).state, JobState.QUEUED)

    def test_cancel_trong_retry_wait_chan_lan_lease_tiep(self):
        result = self.submit()
        job_id = result.jobs[0].job_id
        lease = self.runtime.lease_next(JobKind.IMAGE, now=0, ttl=30)
        decision = self.runtime.attempt_failed(
            lease.lease_id,
            ErrorFact(
                ErrorClass.PROVIDER_TRANSIENT, "provider bận",
                AttemptPhase.ATTACHING),
            event_id=uuid4(), now=1,
        )

        verdict = self.runtime.cancel(job_id, event_id=uuid4(), now=2)

        self.assertTrue(verdict.accepted)
        self.assertEqual(self.runtime.job(job_id).state, JobState.CANCELLED)
        self.assertIsNone(self.runtime.lease_next(
            JobKind.IMAGE, now=2 + decision.delay, ttl=30))


class DonLoiNeedsAttentionTest(LifecycleRuntimeTest):
    """Gỡ `needs_attention` là QUYẾT ĐỊNH CỦA USER, không phải retry tự động.

    Không có đường này thì job đứng ở `needs_attention` vĩnh viễn: `cancel` từ
    chối nó (`job.not_cancellable`) và auto không được phép tự đưa nó về
    `retry_wait`. Board thật đã kẹt đúng như vậy — 25 REF nằm im, nút "Dọn lỗi"
    bấm bao nhiêu lần cũng không đổi được gì.
    """

    def _job_cho_kiem_tra(self):
        result = self.submit()
        job_id = result.jobs[0].job_id
        lease = self.runtime.lease_next(JobKind.IMAGE, now=10, ttl=30)
        self.runtime.attempt_phase(
            lease.lease_id, AttemptPhase.SUBMITTED, now=11,
            consumes_credit=CreditConsumption.UNKNOWN,
        )
        self.runtime.attempt_failed(
            lease.lease_id,
            ErrorFact(
                ErrorClass.SESSION_TRANSIENT, "mất cửa sổ",
                AttemptPhase.SUBMITTED),
            event_id=uuid4(), now=12,
        )
        assert self.runtime.job(job_id).state is JobState.NEEDS_ATTENTION
        return job_id

    def test_don_loi_dua_job_ve_cancelled(self):
        job_id = self._job_cho_kiem_tra()

        verdict = self.runtime.resolve_needs_attention(
            job_id, event_id=uuid4(), now=30)

        self.assertTrue(verdict.accepted)
        self.assertEqual(verdict.reason_code, "user.resolved_needs_attention")
        self.assertEqual(self.runtime.job(job_id).state, JobState.CANCELLED)


if __name__ == "__main__":
    unittest.main()
