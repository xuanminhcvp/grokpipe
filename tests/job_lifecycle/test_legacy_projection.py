import os
import threading
import unittest
from unittest.mock import patch

from sfboard.jobs.manager import JobManager
from sfboard.jobs.models import JobKind, JobState
from sfboard.jobs.projection import LegacyShadowProjection
from sfboard.jobs.store import MemoryJobStore
from helpers import (
    FakeBoard,
    ROOT,
    function_source,
    load_hangdoi,
    load_sfboard,
    reset_legacy_state,
)


class LegacyProjectionTest(unittest.TestCase):
    def setUp(self):
        self.store = MemoryJobStore()
        self.manager = JobManager(self.store)
        self.projection = LegacyShadowProjection(
            self.manager,
            lambda key: JobKind.VIDEO if key.startswith("V-") else JobKind.IMAGE,
        )

    def test_first_write_bootstraps_current_legacy_state(self):
        self.projection.observe("A", None, {"state": "queued", "msg": "chờ"})
        job = self.projection.job_for("A")
        self.assertEqual(job.state, JobState.QUEUED)
        self.assertEqual(job.version, 1)

    def test_legal_legacy_sequence_uses_manager_transitions(self):
        self.projection.observe("A", None, {"state": "queued", "msg": "chờ"})
        self.projection.observe("A", {"state": "queued"}, {"state": "running"})
        self.projection.observe("A", {"state": "running"}, {"state": "done"})
        job = self.projection.job_for("A")
        self.assertEqual(job.state, JobState.COMPLETED)
        self.assertEqual(job.version, 3)

    def test_same_state_write_is_progress_event_without_version_change(self):
        self.projection.observe("A", None, {"state": "queued", "msg": "chờ"})
        self.projection.observe(
            "A", {"state": "queued"}, {"state": "running", "msg": "step 1"}
        )
        before = self.projection.job_for("A")
        event_count = len(self.store.events_for(before.job_id))
        self.projection.observe(
            "A", {"state": "running"}, {"state": "running", "msg": "step 2"}
        )
        after = self.projection.job_for("A")
        self.assertEqual(after.version, before.version)
        self.assertEqual(
            len(self.store.events_for(after.job_id)),
            event_count + 1,
        )

    def test_cancel_words_project_legacy_error_to_cancelled(self):
        self.projection.observe(
            "A", None, {"state": "error", "msg": "đã huỷ riêng"}
        )
        self.assertEqual(self.projection.job_for("A").state, JobState.CANCELLED)

    def test_plain_legacy_error_projects_to_failed(self):
        self.projection.observe(
            "A", None, {"state": "error", "msg": "selector lỗi"}
        )
        self.assertEqual(self.projection.job_for("A").state, JobState.FAILED)

    def test_terminal_to_active_creates_new_job_with_rerun_link(self):
        self.projection.observe("A", None, {"state": "queued", "msg": "chờ"})
        self.projection.observe(
            "A", {"state": "queued"}, {"state": "running", "msg": "chạy"}
        )
        self.projection.observe(
            "A", {"state": "running"}, {"state": "done", "msg": "xong"}
        )
        old = self.projection.job_for("A")
        self.projection.observe(
            "A", {"state": "done"}, {"state": "queued", "msg": "tạo lại"}
        )
        new = self.projection.job_for("A")
        self.assertNotEqual(new.job_id, old.job_id)
        self.assertEqual(new.rerun_of, old.job_id)
        self.assertEqual(new.state, JobState.QUEUED)
        self.assertEqual(new.version, 1)

    def test_first_running_write_is_reported_as_created_to_running_mismatch(self):
        self.projection.observe(
            "A", None, {"state": "running", "msg": "chạy thẳng"}
        )
        self.assertEqual(self.projection.job_for("A").state, JobState.CREATED)
        self.assertEqual(self.projection.diagnostics()["mismatches"], 1)

    def test_illegal_legacy_transition_records_mismatch_without_shadow_write(self):
        self.projection.observe("A", None, {"state": "queued", "msg": "chờ"})
        before = self.projection.job_for("A")
        self.projection.observe(
            "A", {"state": "queued"}, {"state": "done", "msg": "xong"}
        )
        self.assertEqual(self.projection.job_for("A"), before)
        diagnostics = self.projection.diagnostics()
        self.assertEqual(diagnostics["mismatches"], 1)
        self.assertEqual(
            diagnostics["recent_mismatches"][0]["legacy_key"],
            "A",
        )
        self.assertNotIn("xong", str(diagnostics))


class LegacyObserverBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.h = load_hangdoi()
        reset_legacy_state(self.h)

    def tearDown(self):
        self.h.gan_shadow_observer(None)
        reset_legacy_state(self.h)

    def test_observer_runs_after_stamped_legacy_write(self):
        seen = []
        self.h.gan_shadow_observer(
            lambda key, old, new: seen.append((key, old, new))
        )
        self.h.JOBS["A"] = {"state": "queued", "msg": "chờ"}
        self.assertEqual(seen[0][0], "A")
        self.assertIsNone(seen[0][1])
        self.assertIn("t", seen[0][2])
        self.assertEqual(self.h.JOBS["A"], seen[0][2])

    def test_observer_exception_never_blocks_legacy_write(self):
        def broken(_key, _old, _new):
            raise RuntimeError("shadow down")

        self.h.gan_shadow_observer(broken)
        self.h.JOBS["A"] = {"state": "queued", "msg": "chờ"}
        self.assertEqual(self.h.JOBS["A"]["state"], "queued")

    def test_done_to_error_guard_does_not_emit_fake_shadow_write(self):
        seen = []
        self.h.gan_shadow_observer(lambda *args: seen.append(args))
        self.h.JOBS["A"] = {"state": "done", "msg": "xong"}
        seen.clear()
        self.h.JOBS["A"] = {"state": "error", "msg": "late"}
        self.assertEqual(seen, [])
        self.assertEqual(self.h.JOBS["A"]["state"], "done")

    def test_concurrent_callbacks_follow_legacy_commit_order(self):
        first_entered = threading.Event()
        release_first = threading.Event()
        second_attempting = threading.Event()
        second_entered = threading.Event()
        seen = []

        def observer(_key, _old, new):
            state = new["state"]
            if state == "queued":
                first_entered.set()
                release_first.wait(2)
            elif state == "running":
                second_entered.set()
            seen.append(state)

        def write_running():
            second_attempting.set()
            self.h.JOBS["A"] = {"state": "running", "msg": "chạy"}

        self.h.gan_shadow_observer(observer)
        first = threading.Thread(
            target=lambda: self.h.JOBS.__setitem__(
                "A", {"state": "queued", "msg": "chờ"}
            )
        )
        second = threading.Thread(target=write_running)
        first.start()
        self.assertTrue(first_entered.wait(1))
        second.start()
        self.assertTrue(second_attempting.wait(1))

        running_overtook_queued = second_entered.wait(0.3)
        release_first.set()
        for thread in (first, second):
            thread.join(2)
            self.assertFalse(thread.is_alive())

        self.assertFalse(running_overtook_queued)
        self.assertEqual(seen, ["queued", "running"])
        self.assertEqual(self.h.JOBS["A"]["state"], "running")


class ShadowStartupTest(unittest.TestCase):
    def setUp(self):
        self.m = load_sfboard()
        self.board_old = self.m.BOARD
        self.m.BOARD = FakeBoard()
        self.m._init_job_shadow("legacy")

    def tearDown(self):
        self.m._init_job_shadow("legacy")
        self.m.BOARD = self.board_old

    def test_default_legacy_mode_has_no_observer(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GROKPIPE_JOB_MODE", None)
            result = self.m._init_job_shadow()
        self.assertIsNone(result)
        self.assertIsNone(self.m.hangdoi.JOBS.shadow_observer)
        self.assertEqual(self.m._job_shadow_diagnostics()["mode"], "legacy")

    def test_shadow_mode_attaches_projection_without_queue_dependency(self):
        with patch.dict(os.environ, {"GROKPIPE_JOB_MODE": "shadow"}):
            projection = self.m._init_job_shadow()
        self.assertIsNotNone(projection)
        self.m.JOBS["A"] = {"state": "queued", "msg": "chờ"}
        diagnostics = self.m._job_shadow_diagnostics()
        self.assertEqual(diagnostics["mode"], "shadow")
        self.assertEqual(diagnostics["tracked_jobs"], 1)

    def test_authoritative_or_unknown_mode_fails_safe_to_legacy(self):
        for mode in ("authoritative", "future-mode"):
            with self.subTest(mode=mode):
                self.assertIsNone(self.m._init_job_shadow(mode))
                self.assertIsNone(self.m.hangdoi.JOBS.shadow_observer)
                self.assertEqual(
                    self.m._job_shadow_diagnostics()["mode"],
                    "legacy",
                )

    def test_shadow_init_failure_falls_back_to_legacy(self):
        self.assertIsNotNone(self.m._init_job_shadow("shadow"))
        with patch(
            "jobs.projection.LegacyShadowProjection",
            side_effect=RuntimeError("shadow unavailable"),
        ):
            result = self.m._init_job_shadow("shadow")
        self.assertIsNone(result)
        self.assertIsNone(self.m.hangdoi.JOBS.shadow_observer)
        self.assertEqual(self.m._job_shadow_diagnostics()["mode"], "legacy")

    def test_main_initializes_shadow_before_worker_threads(self):
        source = function_source(ROOT / "sfboard/sfboard.py", "main")
        self.assertLess(
            source.index("_init_job_shadow()"),
            source.index("threading.Thread(target=_supervisor"),
        )
