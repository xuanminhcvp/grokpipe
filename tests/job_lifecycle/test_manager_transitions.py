import threading
import unittest
from uuid import uuid4

from sfboard.jobs.manager import (
    LEGAL_TRANSITIONS,
    IllegalTransition,
    JobManager,
    TransitionCommand,
)
from sfboard.jobs.models import (
    AssetId,
    EventActor,
    Job,
    JobId,
    JobKind,
    JobOrigin,
    JobState,
)
from sfboard.jobs.store import MemoryJobStore, VersionConflict


def seed_manager(state):
    store = MemoryJobStore()
    manager = JobManager(store)
    job = Job(
        JobId.new(),
        AssetId("SF-S1-1"),
        JobKind.IMAGE,
        JobOrigin.COMPATIBILITY,
        state=state,
    )
    manager.bootstrap_shadow(job, uuid4(), "test.seed")
    return manager, store, job


class JobManagerTransitionTest(unittest.TestCase):
    def test_transition_table_matches_approved_state_machine(self):
        expected = {
            JobState.CREATED: {
                JobState.QUEUED,
                JobState.FAILED,
                JobState.CANCELLED,
            },
            JobState.QUEUED: {
                JobState.RUNNING,
                JobState.FAILED,
                JobState.CANCELLED,
            },
            JobState.RUNNING: {
                JobState.COMPLETED,
                JobState.RETRY_WAIT,
                JobState.FAILED,
                JobState.CANCELLED,
                JobState.NEEDS_ATTENTION,
            },
            JobState.RETRY_WAIT: {
                JobState.QUEUED,
                JobState.FAILED,
                JobState.CANCELLED,
            },
            JobState.NEEDS_ATTENTION: {
                JobState.COMPLETED,
                JobState.FAILED,
                JobState.CANCELLED,
            },
            JobState.COMPLETED: set(),
            JobState.FAILED: set(),
            JobState.CANCELLED: set(),
        }
        self.assertEqual(LEGAL_TRANSITIONS, expected)

    def test_every_allowed_pair_applies_and_increments_version(self):
        for source, targets in LEGAL_TRANSITIONS.items():
            for target in targets:
                with self.subTest(source=source, target=target):
                    manager, _store, job = seed_manager(source)
                    result = manager.transition(
                        TransitionCommand(
                            job.job_id,
                            0,
                            target,
                            EventActor.MANAGER,
                            "test.transition",
                            "test.allowed",
                            uuid4(),
                        )
                    )
                    self.assertEqual(result.job.state, target)
                    self.assertEqual(result.job.version, 1)

    def test_every_disallowed_pair_is_rejected_without_write(self):
        for source in JobState:
            for target in JobState:
                if target in LEGAL_TRANSITIONS[source]:
                    continue
                with self.subTest(source=source, target=target):
                    manager, store, job = seed_manager(source)
                    before = store.events_for(job.job_id)
                    with self.assertRaises(IllegalTransition):
                        manager.transition(
                            TransitionCommand(
                                job.job_id,
                                0,
                                target,
                                EventActor.MANAGER,
                                "test.transition",
                                "test.denied",
                                uuid4(),
                            )
                        )
                    self.assertEqual(store.get(job.job_id), job)
                    self.assertEqual(store.events_for(job.job_id), before)

    def test_progress_event_does_not_fake_running_to_running(self):
        manager, store, job = seed_manager(JobState.RUNNING)
        result = manager.record_progress(
            job.job_id,
            uuid4(),
            EventActor.WORKER,
            "attempt.progress",
            "test.progress",
        )
        self.assertEqual(result.job.state, JobState.RUNNING)
        self.assertEqual(result.job.version, 0)
        self.assertIsNone(store.events_for(job.job_id)[-1].from_state)

    def test_complete_cancel_race_allows_exactly_one_cas_winner(self):
        manager, store, job = seed_manager(JobState.RUNNING)
        barrier = threading.Barrier(3)
        outcomes = []

        def run(target):
            barrier.wait()
            try:
                result = manager.transition(
                    TransitionCommand(
                        job.job_id,
                        0,
                        target,
                        EventActor.MANAGER,
                        "test.race",
                        "test.race",
                        uuid4(),
                    )
                )
                outcomes.append(("ok", result.job.state))
            except VersionConflict:
                outcomes.append(("conflict", target))

        threads = [
            threading.Thread(target=run, args=(JobState.COMPLETED,)),
            threading.Thread(target=run, args=(JobState.CANCELLED,)),
        ]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(2)
            self.assertFalse(thread.is_alive())
        self.assertEqual(sum(kind == "ok" for kind, _ in outcomes), 1)
        self.assertEqual(sum(kind == "conflict" for kind, _ in outcomes), 1)
        self.assertIn(
            store.get(job.job_id).state,
            {JobState.COMPLETED, JobState.CANCELLED},
        )
