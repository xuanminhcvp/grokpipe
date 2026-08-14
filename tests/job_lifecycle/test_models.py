import dataclasses
import unittest
from uuid import UUID

from sfboard.jobs.models import AssetId, Job, JobId, JobKind, JobOrigin, JobState


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
