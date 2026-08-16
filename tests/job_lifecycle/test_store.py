import unittest
from dataclasses import replace
from uuid import uuid4

from sfboard.jobs.models import (
    AssetId,
    EventActor,
    Job,
    JobEvent,
    JobId,
    JobKind,
    JobOrigin,
    JobState,
)
from sfboard.jobs.store import (
    EventConflict,
    JobAlreadyExists,
    MemoryJobStore,
    VersionConflict,
)


def make_job(state=JobState.CREATED, version=0):
    return Job(
        JobId.new(),
        AssetId("SF-S1-1"),
        JobKind.IMAGE,
        JobOrigin.MANUAL,
        state=state,
        version=version,
    )


def make_event(job, *, event_id=None, from_state=None, to_state=None, reason="test"):
    return JobEvent(
        event_id or uuid4(),
        job.job_id,
        EventActor.MANAGER,
        "test_event",
        reason,
        from_state=from_state,
        to_state=to_state,
    )


class MemoryJobStoreTest(unittest.TestCase):
    def setUp(self):
        self.store = MemoryJobStore()

    def test_create_writes_job_and_event_atomically(self):
        job = make_job()
        event = make_event(job, reason="created")
        result = self.store.create(job, event)
        self.assertTrue(result.applied)
        self.assertEqual(self.store.get(job.job_id), job)
        self.assertEqual(self.store.events_for(job.job_id), (event,))

    def test_duplicate_event_replays_without_second_append(self):
        job = make_job()
        event = make_event(job, reason="created")
        first = self.store.create(job, event)
        replay = self.store.create(job, event)
        self.assertTrue(first.applied)
        self.assertFalse(replay.applied)
        self.assertEqual(replay.job, first.job)
        self.assertEqual(self.store.events_for(job.job_id), (event,))

    def test_same_event_id_with_different_payload_is_conflict(self):
        job = make_job()
        event_id = uuid4()
        self.store.create(job, make_event(job, event_id=event_id, reason="one"))
        with self.assertRaises(EventConflict):
            self.store.append_event(
                job.job_id, make_event(job, event_id=event_id, reason="two")
            )

    def test_create_replay_rejects_changed_job_payload(self):
        job = make_job()
        event = make_event(job, reason="created")
        self.store.create(job, event)

        changed = replace(job, forced_account_id="account-two")
        with self.assertRaises(EventConflict):
            self.store.create(changed, event)

    def test_duplicate_job_with_new_event_is_rejected(self):
        job = make_job()
        self.store.create(job, make_event(job, reason="one"))
        with self.assertRaises(JobAlreadyExists):
            self.store.create(job, make_event(job, reason="two"))

    def test_transition_is_atomic_and_increments_version_once(self):
        job = make_job()
        self.store.create(job, make_event(job, reason="created"))
        event = make_event(
            job,
            from_state=JobState.CREATED,
            to_state=JobState.QUEUED,
            reason="scheduled",
        )
        result = self.store.transition(job.job_id, 0, JobState.QUEUED, event)
        self.assertEqual(result.job.state, JobState.QUEUED)
        self.assertEqual(result.job.version, 1)
        self.assertEqual(self.store.events_for(job.job_id)[-1], event)

    def test_cas_conflict_changes_neither_job_nor_events(self):
        job = make_job()
        created = make_event(job, reason="created")
        self.store.create(job, created)
        event = make_event(
            job,
            from_state=JobState.CREATED,
            to_state=JobState.QUEUED,
            reason="scheduled",
        )
        with self.assertRaises(VersionConflict):
            self.store.transition(job.job_id, 9, JobState.QUEUED, event)
        self.assertEqual(self.store.get(job.job_id), job)
        self.assertEqual(self.store.events_for(job.job_id), (created,))

    def test_progress_event_does_not_change_version(self):
        job = make_job(state=JobState.RUNNING, version=4)
        self.store.create(job, make_event(job, reason="bootstrap"))
        event = make_event(job, reason="progress")
        result = self.store.append_event(job.job_id, event)
        self.assertEqual(result.job.version, 4)
        self.assertEqual(result.job.state, JobState.RUNNING)
