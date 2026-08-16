import importlib
import os
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

from sfboard.jobs.manager import JobManager, TransitionCommand
from sfboard.jobs.models import (
    AssetId,
    EventActor,
    Job,
    JobId,
    JobKind,
    JobOrigin,
    JobState,
)
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


def make_domain_job(asset):
    return Job(
        JobId.new(), AssetId(asset), JobKind.IMAGE, JobOrigin.MANUAL,
    )


def make_and_create(manager, asset):
    job = make_domain_job(asset)
    manager.create_job(job, uuid4(), EventActor.MANAGER, "producer.accepted")
    return job


def make_runtime_request(asset="A"):
    models = importlib.import_module("jobs.models")
    producer = importlib.import_module("jobs.producer")

    return producer.CreateJobRequest(
        models.AssetId(asset),
        models.JobKind.IMAGE,
        models.JobOrigin.MANUAL,
        "test:runtime",
        manual=True,
    )


def make_runtime_plan(result, *, ident="A", forced_account_id=None):
    compat = importlib.import_module("jobs.compat")

    job_ids = tuple(job.job_id for job in result.jobs) if result else ()
    return compat.LegacyPlan((
        compat.LegacyAction(
            action_id="runtime-image",
            legacy_keys=(ident,),
            job_ids=job_ids,
            queue_kind="img",
            queue_ident=ident,
            manual=True,
            state={"state": "queued", "msg": "chờ"},
            forced_account_id=forced_account_id,
        ),
    ))


class LegacyProjectionTest(unittest.TestCase):
    def setUp(self):
        self.store = MemoryJobStore()
        self.manager = JobManager(self.store)
        self.projection = LegacyShadowProjection(
            self.manager,
            lambda key: JobKind.VIDEO if key.startswith("V-") else JobKind.IMAGE,
        )

    def test_bind_reuses_command_created_job(self):
        job = make_domain_job("A")
        self.manager.create_job(job, uuid4(), EventActor.MANAGER, "producer.accepted")
        self.projection.bind("A", (job.job_id,))
        self.projection.observe("A", None, {"state": "queued", "msg": "chờ"})
        self.assertEqual(self.projection.job_for("A").job_id, job.job_id)

    def test_group_binding_projects_write_to_each_member(self):
        jobs = tuple(make_and_create(self.manager, asset) for asset in ("A", "B"))
        self.projection.bind("LO:A,B", tuple(job.job_id for job in jobs))
        self.projection.observe(
            "LO:A,B", None, {"state": "queued", "msg": "chờ"}
        )
        self.assertEqual(
            tuple(job.state for job in self.projection.jobs_for("LO:A,B")),
            (JobState.QUEUED, JobState.QUEUED),
        )

    def test_active_binding_collision_records_mismatch_and_keeps_original(self):
        first = make_and_create(self.manager, "A")
        second = make_and_create(self.manager, "A")
        self.projection.bind("A", (first.job_id,))
        self.projection.bind("A", (second.job_id,))
        self.assertEqual(self.projection.job_for("A").job_id, first.job_id)
        self.assertEqual(self.projection.diagnostics()["mismatches"], 1)

    def test_group_member_conflict_does_not_block_other_member_projection(self):
        first, second = (
            make_and_create(self.manager, asset) for asset in ("A", "B")
        )
        self.projection.bind("LO:A,B", (first.job_id, second.job_id))
        self.manager.transition(
            TransitionCommand(
                first.job_id,
                first.version,
                JobState.QUEUED,
                EventActor.MANAGER,
                "test.transition",
                "test.queued",
                uuid4(),
            )
        )
        first = self.manager.get(first.job_id)
        self.manager.transition(
            TransitionCommand(
                first.job_id,
                first.version,
                JobState.RUNNING,
                EventActor.MANAGER,
                "test.transition",
                "test.running",
                uuid4(),
            )
        )

        self.projection.observe(
            "LO:A,B", None, {"state": "queued", "msg": "chờ"}
        )

        self.assertEqual(self.manager.get(first.job_id).state, JobState.RUNNING)
        self.assertEqual(self.manager.get(second.job_id).state, JobState.QUEUED)
        self.assertEqual(self.projection.diagnostics()["mismatches"], 1)

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

    def test_shadow_runtime_shares_store_between_producer_and_projection(self):
        projection = self.m._init_job_shadow("shadow")
        self.assertIs(projection._manager.store, self.m._JOB_PRODUCER.store)
        self.assertIsNotNone(self.m._JOB_ADAPTER)

    def test_legacy_runtime_has_adapter_but_no_producer_intent_service(self):
        self.m._init_job_shadow("legacy")
        self.assertIsNotNone(self.m._JOB_ADAPTER)
        self.assertIsNone(self.m._JOB_PRODUCER)

    def test_unknown_mode_fails_safe_to_legacy(self):
        self.assertIsNone(self.m._init_job_shadow("future-mode"))
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

    def test_reinit_failure_clears_all_shadow_components(self):
        self.m._init_job_shadow("shadow")
        with patch("jobs.producer.ProducerService", side_effect=RuntimeError("no core")):
            self.assertIsNone(self.m._init_job_shadow("shadow"))
        self.assertEqual(self.m._JOB_MODE, "legacy")
        self.assertIsNone(self.m._JOB_PRODUCER)
        self.assertIsNone(self.m.hangdoi.JOBS.shadow_observer)
        self.assertIsNotNone(self.m._JOB_ADAPTER)

    def test_main_initializes_shadow_before_worker_threads(self):
        source = function_source(ROOT / "sfboard/sfboard.py", "main")
        self.assertLess(
            source.index("_init_job_shadow()"),
            source.index("threading.Thread(target=_supervisor"),
        )

    def test_reset_helper_initializes_legacy_adapter_for_import_harness(self):
        self.m._JOB_ADAPTER = None
        self.m.CHO_RIENG[9222] = ["A"]
        reset_legacy_state(self.m)
        self.assertIsNotNone(self.m._JOB_ADAPTER)
        self.assertIsNone(self.m._JOB_PRODUCER)
        self.assertEqual(self.m.CHO_RIENG, {})


class RuntimeProducerBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.m = load_sfboard()
        self.board_old = self.m.BOARD
        self.m.BOARD = FakeBoard()
        reset_legacy_state(self.m)

    def tearDown(self):
        reset_legacy_state(self.m)
        self.m.BOARD = self.board_old

    @staticmethod
    def _handler(headers=None):
        return type("Request", (), {"headers": headers or {}})()

    def test_idempotency_header_precedes_query_and_json_body(self):
        key = self.m._request_idempotency_key(
            self._handler({"Idempotency-Key": " header-key "}),
            {"idempotency_key": ["query-key"]},
            b'{"idempotency_key":"body-key"}',
        )
        self.assertEqual(key, "header-key")

    def test_idempotency_query_precedes_json_body(self):
        key = self.m._request_idempotency_key(
            self._handler(),
            {"idempotency_key": [" query-key "]},
            b'{"idempotency_key":"body-key"}',
        )
        self.assertEqual(key, "query-key")

    def test_idempotency_uses_json_body_and_rejects_malformed_bytes(self):
        self.assertEqual(
            self.m._request_idempotency_key(
                self._handler(), {}, b'{"idempotency_key":" body-key "}'
            ),
            "body-key",
        )
        self.assertIsNone(
            self.m._request_idempotency_key(self._handler(), {}, b"\xff")
        )

    def test_legacy_adapter_callbacks_resolve_runtime_queue_late(self):
        calls = []
        with patch.object(
            self.m,
            "_xep",
            side_effect=lambda queue, item: calls.append((queue, item)),
        ):
            self.m._JOB_ADAPTER.deliver_legacy(make_runtime_plan(None))
        self.assertEqual(
            calls,
            [(self.m.IMG_QUEUE, ("img", "A", 0, True))],
        )

    def test_private_image_callback_keeps_port_to_sorted_ident_list(self):
        self.m._legacy_enqueue_private_image("9222", "SF-S1-02", True, "one")
        self.m._legacy_enqueue_private_image(9222, "SF-S1-01", True, "two")
        self.assertEqual(
            self.m.CHO_RIENG,
            {9222: ["SF-S1-01", "SF-S1-02"]},
        )

    def test_legacy_submit_delivers_plan_without_creating_intent(self):
        result = self.m._producer_submit(
            make_runtime_request(),
            "legacy-key",
            make_runtime_plan,
        )
        self.assertIsNone(result)
        self.assertEqual(self.m.JOBS["A"]["state"], "queued")
        item = self.m._lay(self.m.IMG_QUEUE, timeout=0.1)
        self.m.IMG_QUEUE.task_done()
        self.assertEqual(item, ("img", "A", 0, True))

    def test_shadow_submit_creates_and_delivers_through_shared_runtime(self):
        projection = self.m._init_job_shadow("shadow")
        result = self.m._producer_submit(
            make_runtime_request(),
            "shadow-key",
            make_runtime_plan,
        )
        self.assertEqual(projection.job_for("A").job_id, result.jobs[0].job_id)
        intent = self.m._JOB_PRODUCER.store.get_intent("shadow-key")
        self.assertTrue(intent.delivered)
        item = self.m._lay(self.m.IMG_QUEUE, timeout=0.1)
        self.m.IMG_QUEUE.task_done()
        self.assertEqual(item, ("img", "A", 0, True))

    def test_submit_lazily_initializes_adapter_in_import_harness(self):
        self.m._JOB_ADAPTER = None
        result = self.m._producer_submit(
            make_runtime_request(),
            None,
            make_runtime_plan,
        )
        self.assertIsNone(result)
        self.assertIsNotNone(self.m._JOB_ADAPTER)

    def test_producer_metadata_is_additive_in_legacy_and_stringifies_shadow_ids(self):
        models = importlib.import_module("jobs.models")
        producer = importlib.import_module("jobs.producer")

        self.assertEqual(
            self.m._producer_metadata(None),
            {"job_id": None, "job_ids": [], "batch_id": None, "replayed": False},
        )
        self.m._init_job_shadow("shadow")
        request = make_runtime_request()
        result = self.m._JOB_PRODUCER.create_batch(
            producer.CreateBatchRequest(
                (request, request), models.BatchMode.MULTI_COPY
            ),
            "batch-key",
        )
        metadata = self.m._producer_metadata(result)
        self.assertIsNone(metadata["job_id"])
        self.assertEqual(metadata["job_ids"], [str(job.job_id) for job in result.jobs])
        self.assertEqual(metadata["batch_id"], str(result.batch.batch_id))
        self.assertFalse(metadata["replayed"])
