import threading
import unittest
from uuid import uuid4

from sfboard.jobs.manager import JobManager, TransitionCommand
from sfboard.jobs.models import (
    AssetId,
    BatchMode,
    EventActor,
    JobKind,
    JobOrigin,
    JobState,
)
from sfboard.jobs.producer import (
    CreateBatchRequest,
    CreateJobRequest,
    ProducerService,
)
from sfboard.jobs.store import IdempotencyConflict, MemoryJobStore


def image_request(asset="SF-S1-01", *, origin=JobOrigin.MANUAL, manual=True):
    return CreateJobRequest(
        asset_id=AssetId(asset),
        kind=JobKind.IMAGE,
        origin=origin,
        request_scope="project-a:http.generate",
        manual=manual,
    )


def terminal_job(job, store, target):
    manager = JobManager(store)
    current = job
    for state in (JobState.QUEUED, JobState.RUNNING, target):
        result = manager.transition(
            TransitionCommand(
                current.job_id,
                current.version,
                state,
                EventActor.MANAGER,
                "test.transition",
                "test.terminal",
                uuid4(),
            )
        )
        current = result.job
    return current


class InterleavingMemoryJobStore(MemoryJobStore):
    """Calls one test hook after a producer has read its scoped parent."""

    def __init__(self):
        super().__init__()
        self.after_scope_read = None
        self.before_intent_write = None

    def latest_for_scope(self, scope_fingerprint):
        latest = super().latest_for_scope(scope_fingerprint)
        hook = self.after_scope_read
        if hook is not None:
            self.after_scope_read = None
            hook()
        return latest

    def create_intent(self, *args, **kwargs):
        hook = self.before_intent_write
        if hook is not None:
            self.before_intent_write = None
            hook()
        return super().create_intent(*args, **kwargs)


class ProducerServiceTest(unittest.TestCase):
    def setUp(self):
        self.store = MemoryJobStore()
        self.service = ProducerService(self.store)

    def test_same_key_replays_same_job(self):
        first = self.service.create_job(image_request(), "key-1")
        replay = self.service.create_job(image_request(), "key-1")
        self.assertEqual(replay.jobs, first.jobs)
        self.assertTrue(replay.replayed)

    def test_same_key_changed_request_raises_idempotency_conflict(self):
        self.service.create_job(image_request("SF-S1-01"), "key-1")
        with self.assertRaises(IdempotencyConflict):
            self.service.create_job(image_request("SF-S1-02"), "key-1")

    def test_two_keys_same_active_scope_return_one_job(self):
        out = []
        barrier = threading.Barrier(2)

        def create(key):
            barrier.wait()
            out.append(self.service.create_job(image_request(), key))

        threads = [threading.Thread(target=create, args=(key,)) for key in ("a", "b")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(2)
        self.assertEqual(len({result.jobs[0].job_id for result in out}), 1)
        self.assertEqual(sum(not result.replayed for result in out), 1)

    def test_manual_after_terminal_creates_rerun_link(self):
        first = self.service.create_job(image_request(), "key-1")
        terminal_job(first.jobs[0], self.store, JobState.COMPLETED)
        rerun = self.service.create_job(image_request(), "key-2")
        self.assertNotEqual(rerun.jobs[0].job_id, first.jobs[0].job_id)
        self.assertEqual(rerun.jobs[0].rerun_of, first.jobs[0].job_id)

    def test_manual_rerun_rebuilds_parent_when_scope_changes_before_write(self):
        store = InterleavingMemoryJobStore()
        service = ProducerService(store)
        root = service.create_job(image_request(), "root")
        terminal_job(root.jobs[0], store, JobState.COMPLETED)

        middle = []

        def create_and_terminal_middle():
            created = service.create_job(image_request(), "middle")
            middle.append(terminal_job(created.jobs[0], store, JobState.COMPLETED))

        store.after_scope_read = create_and_terminal_middle
        late = service.create_job(image_request(), "late")

        self.assertEqual(late.jobs[0].rerun_of, middle[0].job_id)

    def test_manual_rerun_rebuilds_parent_when_existing_scope_turns_terminal(self):
        store = InterleavingMemoryJobStore()
        service = ProducerService(store)
        root = service.create_job(image_request(), "root")

        store.before_intent_write = lambda: terminal_job(
            root.jobs[0], store, JobState.COMPLETED
        )
        late = service.create_job(image_request(), "late")

        self.assertEqual(late.jobs[0].rerun_of, root.jobs[0].job_id)

    def test_auto_after_failed_replays_terminal_job(self):
        request = image_request(origin=JobOrigin.AUTO, manual=False)
        first = self.service.create_job(request)
        terminal_job(first.jobs[0], self.store, JobState.FAILED)
        replay = self.service.create_job(request)
        self.assertEqual(replay.jobs[0].job_id, first.jobs[0].job_id)
        self.assertTrue(replay.replayed)

    def test_multi_copy_creates_distinct_children_and_ordered_copy_indexes(self):
        member = image_request()
        result = self.service.create_batch(
            CreateBatchRequest((member, member, member), BatchMode.MULTI_COPY),
            "multi-1",
        )
        self.assertEqual(len({job.job_id for job in result.jobs}), 3)
        self.assertEqual(tuple(job.copy_index for job in result.jobs), (0, 1, 2))
        self.assertEqual(result.batch.member_job_ids, tuple(job.job_id for job in result.jobs))

    def test_image_group_rejects_duplicate_asset_without_store_write(self):
        member = image_request()
        with self.assertRaises(ValueError):
            self.service.create_batch(
                CreateBatchRequest((member, member), BatchMode.IMAGE_GROUP),
                "group-1",
            )
        self.assertIsNone(self.store.get_intent("group-1"))
