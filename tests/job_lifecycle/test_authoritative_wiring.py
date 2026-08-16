"""Mode gate và executor boundary mới; toàn bộ executor đều là fake."""

import ast
import importlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import (
    FakeBoard, function_source, load_sfboard, make_handler, reset_legacy_state,
)


class AuthoritativeWiringTest(unittest.TestCase):
    def setUp(self):
        self.board = load_sfboard()
        self.compat = importlib.import_module("jobs.compat")
        self.errors = importlib.import_module("jobs.errors")
        self.executor_adapter = importlib.import_module("jobs.executor_adapter")
        self.models = importlib.import_module("jobs.models")
        self.producer = importlib.import_module("jobs.producer")
        reset_legacy_state(self.board)
        self.old_board = self.board.BOARD
        self.old_accounts = self.board.ACCOUNTS
        self.board.BOARD = FakeBoard()
        self.board.ACCOUNTS = []
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "lifecycle.db")
        self.path_patch = mock.patch.object(
            self.board, "_lifecycle_db_path", return_value=self.db_path)
        self.path_patch.start()

    def tearDown(self):
        self.board._shutdown_job_lifecycle()
        self.path_patch.stop()
        self.board.BOARD = self.old_board
        self.board.ACCOUNTS = self.old_accounts
        reset_legacy_state(self.board)
        self.tmp.cleanup()

    def request(self):
        return self.producer.CreateJobRequest(
            self.models.AssetId("SF-A"), self.models.JobKind.IMAGE,
            self.models.JobOrigin.MANUAL, "scope:A",
            manual=True, replace_current=True,
        )

    def plan(self, result):
        job_ids = tuple(job.job_id for job in result.jobs) if result else ()
        return self.compat.LegacyPlan((self.compat.LegacyAction(
            "action:A", ("LO:A",), job_ids, "img", "LO:A", True,
            state_idents=("A",),
        ),))

    def test_legacy_mode_khong_mo_lifecycle_database(self):
        with mock.patch.object(
            self.board, "_make_lifecycle_repository",
        ) as repository_factory:
            self.board._init_job_shadow("legacy")

        repository_factory.assert_not_called()
        self.assertIsNone(self.board._JOB_RUNTIME)
        self.assertIsNone(self.board._JOB_REPOSITORY)

    def test_authoritative_fail_closed_khi_database_khong_mo_duoc(self):
        with mock.patch.object(
            self.board, "_make_lifecycle_repository",
            side_effect=PermissionError("read only"),
        ):
            with self.assertRaises(self.board.LifecycleStartupError):
                self.board._init_job_shadow("authoritative")

        self.assertEqual(self.board._JOB_MODE, "legacy")
        self.assertIsNone(self.board._JOB_RUNTIME)

    def test_authoritative_submit_khong_cham_priority_queue_legacy(self):
        self.board._init_job_shadow("authoritative")

        result = self.board._producer_submit(
            self.request(), "click-A", self.plan)

        self.assertEqual(self.board._JOB_MODE, "authoritative")
        self.assertEqual(self.board.IMG_QUEUE.qsize(), 0)
        self.assertEqual(self.board.VID_QUEUE.qsize(), 0)
        self.assertEqual(
            self.board._JOB_RUNTIME.job(result.jobs[0].job_id).state,
            self.models.JobState.QUEUED,
        )
        self.assertEqual(self.board.JOBS["A"]["state"], "queued")

    def test_authoritative_http_fake_tra_durable_id_khong_enqueue_legacy(self):
        self.board._init_job_shadow("authoritative")
        handler = make_handler(
            self.board,
            "/api/generate?sf=SF-A&idempotency_key=http-A",
        )

        handler.do_POST()
        code, body = handler.captured

        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertIsNotNone(body["job_id"])
        self.assertEqual(len(body["job_ids"]), 1)
        self.assertFalse(body["replayed"])
        self.assertEqual(self.board.IMG_QUEUE.qsize(), 0)

    def test_authoritative_multi_copy_moi_ban_mot_execution_ui_van_gop(self):
        self.board.ACCOUNTS = [{
            "id": "fake", "port": 9222, "kind": "img",
            "enabled": True, "tabs": 1,
        }]
        self.board._init_job_shadow("authoritative")
        create = make_handler(
            self.board,
            "/api/generate?sf=SF-A&n=3&idempotency_key=multi-A",
        )

        create.do_POST()
        code, body = create.captured
        executions = self.board._JOB_RUNTIME.scheduler.active_executions()

        self.assertEqual(code, 200)
        self.assertEqual(len(body["job_ids"]), 3)
        self.assertEqual(len(executions), 3)
        self.assertEqual(
            {tuple(execution.member_keys) for execution in executions},
            {(job_id,) for job_id in body["job_ids"]},
        )
        self.assertEqual(
            set(self.board.JOBS["SF-A"]["job_ids"]), set(body["job_ids"]))

        def execute(lease, _phase):
            return self.executor_adapter.ExecutorAttemptResult({
                job_id: (f"/tmp/{job_id}.png",)
                for job_id in lease.member_job_ids
            })

        for index in range(3):
            self.board._run_authoritative_once(
                self.models.JobKind.IMAGE, execute, now=index, ttl=30)
            expected = "done" if index == 2 else "queued"
            self.assertEqual(self.board.JOBS["SF-A"]["state"], expected)

    def test_authoritative_restart_dung_lai_projection_cho_ui(self):
        self.board._init_job_shadow("authoritative")
        create = make_handler(
            self.board,
            "/api/generate?sf=SF-A&idempotency_key=restart-ui-A",
        )
        create.do_POST()
        job_id = create.captured[1]["job_id"]
        self.board._shutdown_job_lifecycle()
        self.board.JOBS.clear()

        self.board._init_job_shadow("authoritative")

        self.assertEqual(self.board.JOBS["SF-A"]["state"], "queued")
        self.assertEqual(self.board.JOBS["SF-A"]["job_id"], job_id)
        self.assertEqual(self.board.IMG_QUEUE.qsize(), 0)

    def test_authoritative_giu_fallback_video_sang_tai_khoan_anh(self):
        self.board.ACCOUNTS = [{
            "id": "fake", "port": 9222, "kind": "img",
            "enabled": True, "tabs": 1,
        }]
        self.board._init_job_shadow("authoritative")
        request = self.producer.CreateJobRequest(
            self.models.AssetId("V-A"), self.models.JobKind.VIDEO,
            self.models.JobOrigin.MANUAL, "scope:video:A", manual=True,
        )

        def video_plan(result):
            return self.compat.LegacyPlan((self.compat.LegacyAction(
                "action:video:A", ("V-A",), (result.jobs[0].job_id,),
                "vid", "V-A", True,
            ),))

        result = self.board._JOB_RUNTIME.submit(
            request, "video-fallback-A", video_plan)
        lease = self.board._JOB_RUNTIME.lease_next(
            self.models.JobKind.VIDEO, now=0, ttl=30)

        self.assertEqual(len(result.jobs), 1)
        self.assertEqual(lease.account_id, "9222")

    def test_dung_het_multi_copy_giu_ban_xong_va_huy_phan_con_lai(self):
        self.board.ACCOUNTS = [{
            "id": "fake", "port": 9222, "kind": "img",
            "enabled": True, "tabs": 1,
        }]
        self.board._init_job_shadow("authoritative")
        create = make_handler(
            self.board,
            "/api/generate?sf=SF-A&n=3&idempotency_key=partial-stop-A",
        )
        create.do_POST()
        job_ids = tuple(
            self.models.JobId.parse(value)
            for value in create.captured[1]["job_ids"]
        )

        def execute(lease, _phase):
            return self.executor_adapter.ExecutorAttemptResult({
                job_id: (f"/tmp/{job_id}.png",)
                for job_id in lease.member_job_ids
            })

        self.board._run_authoritative_once(
            self.models.JobKind.IMAGE, execute, now=0, ttl=30)
        stop = make_handler(self.board, "/api/dung-het")
        stop.do_POST()

        states = tuple(
            self.board._JOB_RUNTIME.job(job_id).state for job_id in job_ids)
        self.assertEqual(stop.captured[1]["bo"], 1)
        self.assertEqual(states.count(self.models.JobState.COMPLETED), 1)
        self.assertEqual(states.count(self.models.JobState.CANCELLED), 2)
        self.assertEqual(self.board.JOBS["SF-A"]["state"], "error")

    def test_khong_rollback_legacy_khi_con_execution_active(self):
        self.board._init_job_shadow("authoritative")
        self.board._producer_submit(self.request(), "active-A", self.plan)

        with self.assertRaises(self.board.LifecycleStartupError):
            self.board._init_job_shadow("legacy")

        self.assertEqual(self.board._JOB_MODE, "authoritative")
        self.assertIsNotNone(self.board._JOB_RUNTIME)

    def test_authoritative_http_huy_viec_chuyen_job_cancelled(self):
        self.board._init_job_shadow("authoritative")
        create = make_handler(
            self.board,
            "/api/generate?sf=SF-A&idempotency_key=cancel-A",
        )
        create.do_POST()
        job_id = create.captured[1]["job_id"]
        cancel = make_handler(self.board, "/api/huy-viec?sf=SF-A")

        cancel.do_POST()
        code, body = cancel.captured

        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(
            self.board._JOB_RUNTIME.job(
                self.models.JobId.parse(job_id)).state,
            self.models.JobState.CANCELLED,
        )
        self.assertEqual(self.board.IMG_QUEUE.qsize(), 0)
        self.assertEqual(self.board.JOBS["SF-A"]["state"], "error")

    def test_authoritative_dung_het_cancel_durable_khong_dong_chrome(self):
        self.board._init_job_shadow("authoritative")
        job_ids = []
        for sf in ("SF-A", "SF-B"):
            create = make_handler(
                self.board,
                f"/api/generate?sf={sf}&idempotency_key=stop-{sf}",
            )
            create.do_POST()
            job_ids.append(create.captured[1]["job_id"])
        stop_chat = mock.Mock(return_value=1)
        kill_chrome = mock.Mock()

        with mock.patch.object(self.board, "_bam_stop_tren_tab", stop_chat), \
                mock.patch.object(self.board, "_kill_chrome", kill_chrome):
            stop = make_handler(
                self.board, "/api/dung-het?dong_chrome=1")
            stop.do_POST()

        code, body = stop.captured
        self.assertEqual(code, 200)
        self.assertEqual(body["bo"], 2)
        self.assertEqual(body["dong_chrome"], [])
        self.assertEqual(body["da_bam_stop"], 0)
        stop_chat.assert_not_called()
        kill_chrome.assert_not_called()
        for job_id in job_ids:
            self.assertEqual(
                self.board._JOB_RUNTIME.job(
                    self.models.JobId.parse(job_id)).state,
                self.models.JobState.CANCELLED,
            )

    def test_authoritative_dung_viec_anh_dang_chay_huy_runtime_lease(self):
        self.board.ACCOUNTS = [{
            "id": "fake", "port": 9222, "kind": "img",
            "enabled": True, "tabs": 1,
        }]
        self.board._init_job_shadow("authoritative")
        create = make_handler(
            self.board,
            "/api/generate?sf=SF-A&idempotency_key=running-A",
        )
        create.do_POST()
        job_id = create.captured[1]["job_id"]
        self.board._JOB_RUNTIME.lease_next(
            self.models.JobKind.IMAGE, now=0, ttl=30)
        self.board._runtime_project_state(
            "SF-A", {"state": "running", "msg": "đang chạy"})
        stop = make_handler(self.board, "/api/dung-viec?sf=SF-A")

        stop.do_POST()

        self.assertTrue(stop.captured[1]["ok"])
        self.assertEqual(
            self.board._JOB_RUNTIME.job(
                self.models.JobId.parse(job_id)).state,
            self.models.JobState.CANCELLED,
        )

    def test_executor_adapter_phat_phase_va_success_fact(self):
        self.board._init_job_shadow("authoritative")
        runtime = self.board._JOB_RUNTIME
        runtime.accounts.register("9222", allow_video=True)
        result = runtime.submit(self.request(), "fake-success", self.plan)
        lease = runtime.lease_next(self.models.JobKind.IMAGE, now=0, ttl=30)
        adapter = self.executor_adapter.LegacyExecutorAdapter(
            runtime, clock=lambda: 1)

        def execute(_lease, phase):
            phase(
                self.models.AttemptPhase.SUBMITTED,
                consumes_credit=self.models.CreditConsumption.UNKNOWN,
            )
            return self.executor_adapter.ExecutorAttemptResult({
                result.jobs[0].job_id: ("/tmp/a.png",),
            })

        outcome = adapter.run_once(lease, execute)

        self.assertEqual(
            runtime.job(result.jobs[0].job_id).state,
            self.models.JobState.COMPLETED)
        self.assertTrue(outcome.verdicts[result.jobs[0].job_id].ghi_de)

    def test_board_run_once_di_qua_runtime_lease_va_adapter(self):
        self.board.ACCOUNTS = [{
            "id": "fake", "port": 9222, "kind": "img",
            "enabled": True, "tabs": 1,
        }]
        self.board._init_job_shadow("authoritative")
        runtime = self.board._JOB_RUNTIME
        result = self.board._producer_submit(
            self.request(), "board-run-once", self.plan)

        def execute(_lease, _phase):
            self.assertEqual(self.board.JOBS["A"]["state"], "running")
            return self.executor_adapter.ExecutorAttemptResult({
                result.jobs[0].job_id: ("/tmp/a.png",),
            })

        outcome = self.board._run_authoritative_once(
            self.models.JobKind.IMAGE, execute, now=0, ttl=30)

        self.assertTrue(outcome.verdicts[result.jobs[0].job_id].ghi_de)
        self.assertEqual(
            runtime.job(result.jobs[0].job_id).state,
            self.models.JobState.COMPLETED,
        )
        self.assertEqual(self.board.JOBS["A"]["state"], "done")

        replay = self.board._producer_submit(
            self.request(), "board-run-once", self.plan)

        self.assertTrue(replay.replayed)
        self.assertEqual(runtime.scheduler.active_executions(), ())
        self.assertEqual(self.board.JOBS["A"]["state"], "done")

    def test_executor_adapter_loi_chi_phat_fact_khong_tu_retry(self):
        self.board._init_job_shadow("authoritative")
        runtime = self.board._JOB_RUNTIME
        runtime.accounts.register("9222", allow_video=True)
        result = runtime.submit(self.request(), "fake-fail", self.plan)
        lease = runtime.lease_next(self.models.JobKind.IMAGE, now=0, ttl=30)

        def classify(exc, phase):
            return self.errors.ErrorFact(
                self.errors.ErrorClass.VALIDATION, str(exc), phase)

        adapter = self.executor_adapter.LegacyExecutorAdapter(
            runtime, classify_exception=classify, clock=lambda: 1)

        def execute(_lease, _phase):
            raise RuntimeError("thiếu ref")

        outcome = adapter.run_once(lease, execute)

        self.assertEqual(outcome.decision.reason_code, "validation.permanent")
        self.assertEqual(
            runtime.job(result.jobs[0].job_id).state,
            self.models.JobState.FAILED)
        self.assertEqual(runtime.scheduler.ready(now=999), ())

    def test_executor_adapter_ast_khong_biet_queue_browser_provider(self):
        path = Path(__file__).resolve().parents[2] / "sfboard/jobs/executor_adapter.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        forbidden = {"queue", "playwright", "browser", "provider", "JOBS", "_xep"}
        seen = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in forbidden:
                seen.add(node.id)
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    seen.update(set(alias.name.lower().split(".")) & forbidden)
        self.assertEqual(seen, set())

    def test_authoritative_submit_ast_khong_enqueue_hay_ghi_jobs_truc_tiep(self):
        root = Path(__file__).resolve().parents[2]
        source = function_source(
            root / "sfboard/sfboard.py", "_authoritative_submit")
        tree = ast.parse(source)
        forbidden_calls = {"_xep", "put", "put_nowait", "deliver_legacy"}
        calls = set()
        direct_jobs_writes = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr)
            if (isinstance(node, ast.Subscript)
                    and isinstance(node.ctx, ast.Store)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "JOBS"):
                direct_jobs_writes += 1
        self.assertEqual(calls & forbidden_calls, set())
        self.assertEqual(direct_jobs_writes, 0)


if __name__ == "__main__":
    unittest.main()
