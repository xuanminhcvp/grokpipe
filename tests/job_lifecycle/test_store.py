import unittest
from dataclasses import replace
from uuid import uuid4

from sfboard.jobs.models import (
    AssetId,
    Batch,
    BatchId,
    BatchMode,
    EventActor,
    Job,
    JobEvent,
    JobId,
    JobKind,
    JobOrigin,
    JobState,
)
from sfboard.jobs.store import (
    ActiveJobConflict,
    EventConflict,
    IdempotencyConflict,
    IdempotencyRecord,
    JobAlreadyExists,
    MemoryJobStore,
    StoreInvariantError,
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


def make_intent(key, fingerprint, scope, jobs, batch=None):
    return IdempotencyRecord(
        key=key,
        fingerprint=fingerprint,
        scope_fingerprint=scope,
        job_ids=tuple(job.job_id for job in jobs),
        batch_id=batch.batch_id if batch else None,
        delivered=False,
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

    def test_intent_same_key_and_fingerprint_replays_original_jobs(self):
        job = make_job()
        event = make_event(job, reason="producer.create")
        record = make_intent("key-1", "fp-1", "scope-1", (job,))
        first = self.store.create_intent(record, None, ((job, event),))
        replay = self.store.create_intent(record, None, ((job, event),))
        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.jobs, (job,))
        self.assertEqual(self.store.events_for(job.job_id), (event,))

    def test_intent_same_key_with_changed_fingerprint_conflicts_without_write(self):
        first = make_job()
        self.store.create_intent(
            make_intent("key-1", "fp-1", "scope-1", (first,)),
            None,
            ((first, make_event(first)),),
        )
        changed = make_job()
        with self.assertRaises(IdempotencyConflict):
            self.store.create_intent(
                make_intent("key-1", "fp-2", "scope-2", (changed,)),
                None,
                ((changed, make_event(changed)),),
            )
        self.assertIsNone(self.store.get(changed.job_id))

    def test_batch_validation_failure_writes_no_member(self):
        one, two = make_job(), make_job()
        batch = Batch(
            BatchId.new(), JobKind.IMAGE, BatchMode.IMAGE_GROUP,
            (one.job_id, two.job_id),
        )
        wrong_event = make_event(one)
        with self.assertRaises(StoreInvariantError):
            self.store.create_intent(
                make_intent("batch-1", "fp-b", "scope-b", (one, two), batch),
                batch,
                ((one, make_event(one)), (two, wrong_event)),
            )
        self.assertIsNone(self.store.get(one.job_id))
        self.assertIsNone(self.store.get(two.job_id))
        self.assertIsNone(self.store.get_batch(batch.batch_id))

    def test_mark_delivered_updates_original_key_and_scope_alias(self):
        job = make_job()
        first = make_intent("key-1", "fp-1", "scope-1", (job,))
        self.store.create_intent(first, None, ((job, make_event(job)),))
        alias_job = make_job()
        alias = make_intent("key-2", "fp-1", "scope-1", (alias_job,))
        replay = self.store.create_intent(alias, None, ((alias_job, make_event(alias_job)),))
        self.assertTrue(replay.replayed)
        self.store.mark_intent_delivered("key-2")
        self.assertTrue(self.store.get_intent("key-1").delivered)
        self.assertTrue(self.store.get_intent("key-2").delivered)

    def test_active_scope_with_changed_payload_is_conflict(self):
        first = make_job()
        self.store.create_intent(
            make_intent("key-1", "fp-1", "scope-1", (first,)),
            None,
            ((first, make_event(first)),),
        )
        changed = replace(make_job(), forced_account_id="account-two")
        with self.assertRaises(ActiveJobConflict):
            self.store.create_intent(
                make_intent("key-2", "fp-2", "scope-1", (changed,)),
                None,
                ((changed, make_event(changed)),),
            )
        self.assertIsNone(self.store.get(changed.job_id))
