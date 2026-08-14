import dataclasses
import unittest
from datetime import datetime, timezone
from uuid import UUID

from sfboard.jobs.models import (
    AssetId,
    Attempt,
    AttemptId,
    AttemptPhase,
    Batch,
    BatchId,
    BatchMode,
    CreditConsumption,
    Execution,
    ExecutionId,
    ExecutionState,
    Job,
    JobId,
    JobKind,
    JobOrigin,
    JobState,
)


class JobModelTest(unittest.TestCase):
    def test_typed_identity_round_trip(self):
        job_id = JobId.new()
        self.assertEqual(JobId.parse(str(job_id)), job_id)
        UUID(str(job_id))

    def test_asset_id_cannot_be_used_as_job_id(self):
        with self.assertRaises(ValueError):
            JobId.parse("SF-S1-1")

    def test_job_defaults_to_created_and_is_immutable(self):
        job = Job(
            job_id=JobId.new(),
            asset_id=AssetId("SF-S1-1"),
            kind=JobKind.IMAGE,
            origin=JobOrigin.MANUAL,
        )
        self.assertEqual(job.state, JobState.CREATED)
        self.assertEqual(job.version, 0)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            job.state = JobState.RUNNING

    def test_terminal_predicate_is_exact(self):
        self.assertEqual(
            {state for state in JobState if state.is_terminal},
            {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED},
        )
        self.assertFalse(JobState.NEEDS_ATTENTION.is_terminal)


class ExecutionModelTest(unittest.TestCase):
    def test_execution_rejects_empty_or_duplicate_members(self):
        with self.assertRaises(ValueError):
            Execution(ExecutionId.new(), JobKind.IMAGE, (), ExecutionState.READY, 1)
        job_id = JobId.new()
        with self.assertRaises(ValueError):
            Execution(
                ExecutionId.new(),
                JobKind.IMAGE,
                (job_id, job_id),
                ExecutionState.READY,
                1,
            )

    def test_attempt_before_submit_cannot_consume_credit(self):
        attempt = Attempt(
            AttemptId.new(),
            ExecutionId.new(),
            1,
            "acct-1",
            "lease-1",
            AttemptPhase.READY_TO_SUBMIT,
            CreditConsumption.FALSE,
        )
        self.assertIsNone(attempt.submitted_at)

    def test_submitted_attempt_requires_timestamp_and_credit_classification(self):
        with self.assertRaises(ValueError):
            Attempt(
                AttemptId.new(),
                ExecutionId.new(),
                1,
                "acct-1",
                "lease-1",
                AttemptPhase.SUBMITTED,
                CreditConsumption.FALSE,
            )
        now = datetime.now(timezone.utc)
        valid = Attempt(
            AttemptId.new(),
            ExecutionId.new(),
            1,
            "acct-1",
            "lease-1",
            AttemptPhase.SUBMITTED,
            CreditConsumption.UNKNOWN,
            submitted_at=now,
        )
        self.assertEqual(valid.submitted_at, now)

    def test_finished_attempt_requires_outcome_and_finished_at(self):
        now = datetime.now(timezone.utc)
        with self.assertRaises(ValueError):
            Attempt(
                AttemptId.new(),
                ExecutionId.new(),
                1,
                "acct-1",
                "lease-1",
                AttemptPhase.FINISHED,
                CreditConsumption.TRUE,
                submitted_at=now,
            )

    def test_batch_mode_must_match_kind(self):
        with self.assertRaises(ValueError):
            Batch(
                BatchId.new(),
                JobKind.VIDEO,
                BatchMode.IMAGE_GROUP,
                (JobId.new(),),
            )
