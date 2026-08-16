"""Cùng JobStore contract phải sống qua SQLite/restart."""

from dataclasses import replace
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from uuid import uuid4

from sfboard.jobs.models import EventActor, JobEvent, JobKind, JobState
from sfboard.jobs.scheduler import Scheduler
from sfboard.jobs.sqlite_store import (
    LifecycleDatabaseBusy,
    SQLiteLifecycleRepository,
    UnsupportedSchemaVersion,
)
from sfboard.jobs.store import VersionConflict
from test_store import JobStoreContract, make_event, make_intent, make_job


class SQLiteJobStoreContract(JobStoreContract, unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "lifecycle.db")
        super().setUp()

    def make_store(self):
        return SQLiteLifecycleRepository(self.path)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()


class SQLiteLifecycleRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "lifecycle.db")
        self.store = SQLiteLifecycleRepository(self.path)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_job_event_va_intent_song_qua_restart(self):
        job = make_job()
        event = make_event(job, reason="created")
        self.store.create(job, event)
        self.store.close()
        self.store = SQLiteLifecycleRepository(self.path)

        self.assertEqual(self.store.get(job.job_id), job)
        self.assertEqual(self.store.events_for(job.job_id), (event,))

    def test_transaction_rollback_job_va_event_cung_nhau(self):
        job = make_job()
        event = make_event(job, reason="created")

        with self.assertRaises(RuntimeError):
            with self.store.transaction():
                self.store.create(job, event)
                raise RuntimeError("fault injection")

        self.assertIsNone(self.store.get(job.job_id))
        self.assertEqual(self.store.events_for(job.job_id), ())

    def test_hai_connection_cas_cung_version_chi_mot_ben_thang(self):
        job = make_job()
        self.store.create(job, make_event(job, reason="created"))
        other = SQLiteLifecycleRepository(self.path)
        barrier = threading.Barrier(2)
        outcomes = []

        def transition(store, reason):
            barrier.wait()
            event = JobEvent(
                uuid4(), job.job_id, EventActor.MANAGER, "scheduled", reason,
                from_state=JobState.CREATED, to_state=JobState.QUEUED,
            )
            try:
                store.transition(job.job_id, 0, JobState.QUEUED, event)
                outcomes.append("ok")
            except VersionConflict:
                outcomes.append("stale")

        threads = [
            threading.Thread(target=transition, args=(self.store, "one")),
            threading.Thread(target=transition, args=(other, "two")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3)
        other.close()

        self.assertEqual(sorted(outcomes), ["ok", "stale"])

    def test_hai_connection_cung_intent_chi_tao_mot_job(self):
        other = SQLiteLifecycleRepository(self.path)
        barrier = threading.Barrier(2)
        results = []

        def create(store):
            job = make_job()
            record = make_intent("same-key", "same-fp", "same-scope", (job,))
            barrier.wait()
            results.append(store.create_intent(
                record, None, ((job, make_event(job)),)))

        threads = [
            threading.Thread(target=create, args=(self.store,)),
            threading.Thread(target=create, args=(other,)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3)
        other.close()

        self.assertEqual(sum(not result.replayed for result in results), 1)
        self.assertEqual(sum(result.replayed for result in results), 1)
        self.assertEqual(results[0].jobs[0].job_id, results[1].jobs[0].job_id)

    def test_unknown_schema_version_fails_closed(self):
        self.store.close()
        connection = sqlite3.connect(self.path)
        connection.execute("UPDATE lifecycle_schema_version SET version=999")
        connection.commit()
        connection.close()

        with self.assertRaises(UnsupportedSchemaVersion):
            SQLiteLifecycleRepository(self.path)

        connection = sqlite3.connect(self.path)
        connection.execute("UPDATE lifecycle_schema_version SET version=1")
        connection.commit()
        connection.close()
        self.store = SQLiteLifecycleRepository(self.path)

    def test_locked_database_reports_explicit_error(self):
        other = sqlite3.connect(self.path, timeout=0.01)
        other.execute("BEGIN IMMEDIATE")
        try:
            with self.assertRaises(LifecycleDatabaseBusy):
                with self.store.transaction():
                    self.store.create(
                        make_job(), make_event(make_job(), reason="unused"))
        finally:
            other.rollback()
            other.close()

    def test_scheduler_dung_cung_repository_va_khoi_phuc_ready(self):
        scheduler = Scheduler(self.store)
        execution = scheduler.schedule(
            JobKind.IMAGE, "LO:A", ("A",), scope_key="asset:A")
        self.store.close()
        self.store = SQLiteLifecycleRepository(self.path)

        restored = Scheduler(self.store)

        ready = restored.ready(now=0)
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0].execution_id, execution.execution_id)
        self.assertEqual(ready[0].queue_ident, "LO:A")

    def test_scheduler_rerun_terminal_giu_hai_execution_identity(self):
        scheduler = Scheduler(self.store)
        old = scheduler.schedule(
            JobKind.IMAGE, "LO:A", ("A",), scope_key="asset:A")
        lease = scheduler.lease_next(JobKind.IMAGE, now=0, ttl=30)
        scheduler.finish(lease.lease_id)
        new = scheduler.schedule(
            JobKind.IMAGE, "LO:A-rerun", ("A",), scope_key="asset:A")

        self.assertNotEqual(old.execution_id, new.execution_id)
        self.assertEqual(
            {row.execution_id for row in self.store.all_execution_records()},
            {str(old.execution_id), str(new.execution_id)},
        )


if __name__ == "__main__":
    unittest.main()
