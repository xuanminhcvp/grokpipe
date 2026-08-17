"""Mode gate và executor boundary mới; toàn bộ executor đều là fake."""

import ast
import importlib
import os
import tempfile
import threading
import time
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

    def test_production_default_la_authoritative_live_va_launcher_ghi_ro_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            runtime = self.board._init_job_shadow()

            self.assertIsNotNone(runtime)
            self.assertEqual(self.board._JOB_MODE, "authoritative")
            self.assertTrue(self.board._live_executor_enabled())
            targets = self.board._background_targets()

        self.assertIn(self.board._live_authoritative_supervisor, targets)
        self.assertNotIn(self.board._supervisor, targets)
        self.assertNotIn(self.board._gac_hang_doi, targets)
        launcher = (Path(__file__).resolve().parents[2] /
                    "chay-board.command").read_text(encoding="utf-8")
        self.assertIn(
            'GROKPIPE_JOB_MODE="${GROKPIPE_JOB_MODE:-authoritative}"',
            launcher,
        )
        self.assertIn(
            'GROKPIPE_LIVE_EXECUTOR="${GROKPIPE_LIVE_EXECUTOR:-1}"',
            launcher,
        )

    def test_explicit_legacy_van_la_rollback_path(self):
        with mock.patch.dict(os.environ, {
            "GROKPIPE_JOB_MODE": "legacy",
            "GROKPIPE_LIVE_EXECUTOR": "0",
        }, clear=True):
            runtime = self.board._init_job_shadow()

        self.assertIsNone(runtime)
        self.assertEqual(self.board._JOB_MODE, "legacy")
        self.assertFalse(self.board._live_executor_enabled())
        self.assertIn(self.board._supervisor, self.board._background_targets())

    def test_authoritative_startup_khong_mo_chrome_hay_legacy_services(self):
        with mock.patch.dict("os.environ", {
            "GROKPIPE_LIVE_EXECUTOR": "0",
        }, clear=True):
            self.board._init_job_shadow("authoritative")
            self.assertFalse(self.board._legacy_execution_enabled())
            self.assertFalse(self.board._live_executor_enabled())
            targets = self.board._background_targets()
            self.assertNotIn(self.board._supervisor, targets)
            self.assertNotIn(self.board._gac_hang_doi, targets)
            self.assertNotIn(self.board._auto_runner, targets)
            self.assertIn(self.board._luu_ban_runner, targets)

    def test_authoritative_live_bat_worker_moi_va_auto_producer_khong_bat_watchdog(self):
        with mock.patch.dict("os.environ", {
            "GROKPIPE_LIVE_EXECUTOR": "1",
            "GROKPIPE_LIVE_GROK_LIMIT": "20",
        }, clear=True):
            self.board._init_job_shadow("authoritative")
            targets = self.board._background_targets()

            self.assertTrue(self.board._live_executor_enabled())
            self.assertIn(self.board._live_authoritative_supervisor, targets)
            self.assertIn(self.board._auto_runner, targets)
            self.assertNotIn(self.board._supervisor, targets)
            self.assertNotIn(self.board._gac_hang_doi, targets)

    def test_live_supervisor_relaunch_chrome_enabled_chet_co_cooldown(self):
        self.board.ACCOUNTS = [{
            "id": "grok-test",
            "kind": "vid",
            "port": 9228,
            "profile": "/tmp/grok-test-profile",
            "enabled": True,
            "tabs": 1,
        }]
        self.board._LIVE_CHROME_RELAUNCH_AFTER.clear()
        launch = mock.Mock(return_value=True)

        with mock.patch.object(
            self.board, "_endpoint_alive", return_value=False,
        ), mock.patch.object(self.board, "_launch_chrome", launch):
            self.board._live_restore_enabled_chrome(now=100.0)
            self.board._live_restore_enabled_chrome(now=101.0)
            self.board._live_restore_enabled_chrome(now=131.0)

        self.assertEqual(launch.call_count, 2)
        self.assertEqual(launch.call_args_list[0].args[0]["port"], 9228)

    def test_shutdown_doi_live_worker_dung_truoc_khi_dong_runtime(self):
        """Restart không được xoá runtime khi worker idle còn đang thức."""
        entered = threading.Event()
        calls_saw_runtime = []

        def idle_once(_kind):
            calls_saw_runtime.append(self.board._JOB_RUNTIME is not None)
            entered.set()
            time.sleep(0.1)
            return None

        with mock.patch.dict(os.environ, {
            "GROKPIPE_LIVE_EXECUTOR": "1",
        }, clear=True), mock.patch.object(
            self.board, "_live_execute_once", side_effect=idle_once,
        ):
            self.board._init_job_shadow("authoritative")
            worker = threading.Thread(
                target=self.board._live_authoritative_worker,
                args=(self.models.JobKind.IMAGE,), daemon=True,
            )
            with self.board._LIVE_WORKERS_LOCK:
                self.board._LIVE_WORKERS[("image", 999)] = worker
            worker.start()
            self.assertTrue(entered.wait(1), "worker không bắt đầu")
            try:
                self.board._shutdown_job_lifecycle()
                worker.join(0.5)

                self.assertFalse(
                    worker.is_alive(),
                    "shutdown trả về khi live worker vẫn còn chạy",
                )
                self.assertEqual(calls_saw_runtime, [True])
            finally:
                setattr(self.board, "_JOB_MODE", "legacy")
                worker.join(1)
                with self.board._LIVE_WORKERS_LOCK:
                    self.board._LIVE_WORKERS.pop(("image", 999), None)

    def test_ctrl_c_dong_http_server_sach_khong_nem_traceback(self):
        server = mock.Mock()
        server.serve_forever.side_effect = KeyboardInterrupt

        with mock.patch.object(
            self.board, "ThreadingHTTPServer", return_value=server,
        ):
            self.board._serve_board_http(8794)

        server.server_close.assert_called_once_with()

    def test_auto_runner_authoritative_khong_bi_chan_boi_legacy_gate(self):
        source = function_source(
            Path(__file__).resolve().parents[2] / "sfboard/sfboard.py",
            "_auto_runner",
        )
        self.assertIn("_browser_execution_enabled()", source)
        self.assertNotIn("if not _legacy_execution_enabled()", source)

    def test_authoritative_fail_closed_khi_database_khong_mo_duoc(self):
        with mock.patch.object(
            self.board, "_make_lifecycle_repository",
            side_effect=PermissionError("read only"),
        ):
            with self.assertRaises(self.board.LifecycleStartupError):
                self.board._init_job_shadow("authoritative")

        self.assertEqual(self.board._JOB_MODE, "legacy")
        self.assertIsNone(self.board._JOB_RUNTIME)

    def test_grok_budget_cau_hinh_sai_fail_permanent_truoc_submit(self):
        budget = importlib.import_module("jobs.live_budget")

        fact = self.board._classify_live_exception(
            budget.BudgetConfigurationError("limit phải 1..20"),
            self.models.AttemptPhase.ATTACHING,
        )

        self.assertIs(fact.error_class, self.errors.ErrorClass.PERMANENT)

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

    def test_authoritative_diagnostics_khong_coi_queue_legacy_la_transport(self):
        self.board._init_job_shadow("authoritative")
        self.board._producer_submit(self.request(), "diag-A", self.plan)

        diagnostics = self.board._job_invariant_diagnostics(now=0)
        handler = make_handler(self.board, "/api/chan-doan")
        handler.do_GET()

        self.assertNotIn("lich.thieu", diagnostics["theo_ma"])
        self.assertNotIn("hang.thieu", diagnostics["theo_ma"])
        self.assertNotIn("nhan.mo_coi", diagnostics["theo_ma"])
        self.assertEqual(handler.captured[1]["hang_doi"]["anh"], 1)
        self.assertEqual(handler.captured[1]["hang_doi"]["video"], 0)

    def test_authoritative_diagnostics_dem_job_tu_runtime_khi_projection_rong(self):
        self.board._init_job_shadow("authoritative")
        self.board._producer_submit(self.request(), "diag-runtime-A", self.plan)
        self.board.JOBS.clear()
        handler = make_handler(self.board, "/api/chan-doan")

        handler.do_GET()

        self.assertEqual(handler.captured[1]["job_cho"], 1)
        self.assertEqual(handler.captured[1]["job_chay"], 0)
        self.assertEqual(handler.captured[1]["invariants"]["tong"], 0)

    def test_authoritative_api_jobs_hien_hang_durable_thay_queue_ram(self):
        self.board._init_job_shadow("authoritative")
        self.board._producer_submit(self.request(), "jobs-A", self.plan)
        handler = make_handler(self.board, "/api/jobs")

        with mock.patch.object(self.board, "_pl_dem", return_value={}), \
                mock.patch.object(self.board, "_dan_ma_doc", return_value=False):
            handler.do_GET()
        code, body = handler.captured

        self.assertEqual(code, 200)
        self.assertEqual(body["hang"]["anh"], ["LO:A"])
        self.assertEqual(body["hang"]["video"], [])
        self.assertEqual(self.board.IMG_QUEUE.qsize(), 0)

    def test_authoritative_api_jobs_tra_structured_lifecycle_tu_store(self):
        self.board._init_job_shadow("authoritative")
        result = self.board._producer_submit(
            self.request(), "structured-A", self.plan)
        self.board.JOBS.clear()  # API mới không được đọc projection để dựng job.
        handler = make_handler(self.board, "/api/jobs")

        with mock.patch.object(self.board, "_pl_dem", return_value={}), \
                mock.patch.object(self.board, "_dan_ma_doc", return_value=False):
            handler.do_GET()
        lifecycle = handler.captured[1]["lifecycle"]

        self.assertEqual(lifecycle["source"], "runtime")
        self.assertEqual(lifecycle["mode"], "authoritative")
        self.assertEqual(lifecycle["jobs"], [{
            "job_id": str(result.jobs[0].job_id),
            "asset_id": "SF-A",
            "kind": "image",
            "origin": "manual",
            "state": "queued",
            "version": 1,
            "batch_id": None,
            "rerun_of": None,
            "copy_index": None,
            "replace_current": True,
            "forced_account_id": None,
            "allow_account_fallback": False,
        }])
        self.assertEqual(len(lifecycle["executions"]), 1)
        self.assertEqual(
            lifecycle["executions"][0]["member_job_ids"],
            [str(result.jobs[0].job_id)],
        )
        self.assertEqual(lifecycle["attempts"], [])

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

    def test_authoritative_genvideo_cung_key_dang_active_replay_cung_job(self):
        self.board.BOARD = FakeBoard(scenes=[{
            "id": "S1",
            "sfs": [],
            "shots": [{
                "id": "V-S1-01",
                "sf": "SF-S1-01",
                "prompt": "chuyển động nhẹ",
                "dur": 5,
            }],
        }], files=["SF-S1-01"])
        self.board._init_job_shadow("authoritative")

        first = make_handler(
            self.board,
            "/api/genvideo?sf=V-S1-01&idempotency_key=video-active-A",
        )
        first.do_POST()
        replay = make_handler(
            self.board,
            "/api/genvideo?sf=V-S1-01&idempotency_key=video-active-A",
        )
        replay.do_POST()

        self.assertEqual(first.captured[0], 200)
        self.assertEqual(replay.captured[0], 200)
        self.assertTrue(replay.captured[1]["ok"])
        self.assertTrue(replay.captured[1]["replayed"])
        self.assertEqual(
            replay.captured[1]["job_id"], first.captured[1]["job_id"])
        self.assertEqual(
            len(self.board._runtime_lifecycle_snapshot()["jobs"]), 1)
        self.assertEqual(self.board.VID_QUEUE.qsize(), 0)

    def test_authoritative_live_tao_lo_gom_ref_phu_thuoc_mot_execution(self):
        portrait = "REF_DENISE_PORTRAIT"
        full = "REF_DENISE_UNIFORM_FULL"
        self.board.BOARD = FakeBoard(scenes=[{
            "id": "REF",
            "sfs": [
                {"id": portrait, "prompt": "portrait Denise", "refs": {}},
                {"id": full, "prompt": "full Denise",
                 "refs": {"chars": [portrait]}},
            ],
            "shots": [],
        }])
        with mock.patch.dict("os.environ", {
            "GROKPIPE_LIVE_EXECUTOR": "1",
            "GROKPIPE_LIVE_GROK_LIMIT": "20",
        }, clear=True):
            self.board._init_job_shadow("authoritative")
            handler = make_handler(
                self.board,
                f"/api/tao-lo?sf={portrait},{full}&idempotency_key=ref-group-A",
            )

            handler.do_POST()
            code, body = handler.captured
            executions = self.board._JOB_RUNTIME.scheduler.active_executions()

        self.assertEqual(code, 200)
        self.assertEqual(body["so_lo"], 1)
        self.assertEqual(len(executions), 1)
        self.assertEqual(
            set(executions[0].member_keys), set(body["job_ids"]))

    def test_auto_asset_dang_thieu_phai_thay_current_khi_ket_qua_ve(self):
        """Auto quét đúng asset đang thiếu, không phải yêu cầu thêm một bản phụ."""
        self.board._init_job_shadow("authoritative")
        scene = {"id": "REF"}

        image = self.board._auto_giao_anh(
            scene, "nhan-vat", ["REF_A_PORTRAIT"], {"scenes": []})
        video = self.board._auto_giao_video(scene, {"id": "V-S1-01"})

        self.assertTrue(image.jobs[0].replace_current)
        self.assertTrue(video.jobs[0].replace_current)

    def test_clear_done_an_projection_nhung_giu_nguyen_lifecycle(self):
        self.board.ACCOUNTS = [{
            "id": "fake", "port": 9222, "kind": "img",
            "enabled": True, "tabs": 1,
        }]
        self.board._init_job_shadow("authoritative")
        result = self.board._producer_submit(
            self.request(), "clear-done-A", self.plan)

        def execute(_lease, _phase):
            return self.executor_adapter.ExecutorAttemptResult({
                result.jobs[0].job_id: ("/tmp/a.png",),
            })

        self.board._run_authoritative_once(
            self.models.JobKind.IMAGE, execute, now=0, ttl=30)
        job_id = str(result.jobs[0].job_id)
        self.assertEqual(
            self.board._runtime_lifecycle_snapshot()["hidden_terminal_job_ids"],
            [],
        )

        clear = make_handler(self.board, "/api/xoa-xong")
        clear.do_POST()
        snapshot = self.board._runtime_lifecycle_snapshot()

        self.assertTrue(clear.captured[1]["ok"])
        self.assertIn(job_id, snapshot["hidden_terminal_job_ids"])
        self.assertEqual(
            self.board._JOB_RUNTIME.job(result.jobs[0].job_id).state,
            self.models.JobState.COMPLETED,
        )
        self.assertIn(job_id, {job["job_id"] for job in snapshot["jobs"]})

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

    def test_user_thay_current_sau_khi_lease_thi_late_result_chi_giu_version(self):
        self.board.ACCOUNTS = [{
            "id": "fake", "port": 9222, "kind": "img",
            "enabled": True, "tabs": 1,
        }]
        self.board._init_job_shadow("authoritative")
        result = self.board._producer_submit(
            self.request(), "user-wins-A", self.plan)
        lease = self.board._JOB_RUNTIME.lease_next(
            self.models.JobKind.IMAGE, now=10, ttl=30)

        self.board._runtime_note_user_mutation("SF-A", now=11)
        verdicts = self.board._JOB_RUNTIME.attempt_succeeded(
            lease.lease_id,
            outputs={result.jobs[0].job_id: ("/tmp/late.png",)},
            event_id=__import__("uuid").uuid4(), now=12,
        )

        commit_decision = importlib.import_module("jobs.results").CommitDecision
        self.assertIs(
            verdicts[result.jobs[0].job_id].decision,
            commit_decision.STORE_AS_VERSION,
        )

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

    def test_restart_khong_khoi_phuc_attention_cu_sau_rerun_da_terminal(self):
        self.board.ACCOUNTS = [{
            "id": "grok-test", "port": 9228, "kind": "vid",
            "enabled": True, "tabs": 1,
        }]
        self.board._init_job_shadow("authoritative")

        def request():
            return self.producer.CreateJobRequest(
                self.models.AssetId("V-A"), self.models.JobKind.VIDEO,
                self.models.JobOrigin.MANUAL, "scope:V-A",
                manual=True, replace_current=True,
            )

        def plan(result):
            return self.compat.LegacyPlan((self.compat.LegacyAction(
                "video:V-A", ("V-A",), (result.jobs[0].job_id,),
                "vid", "V-A", False,
            ),))

        first = self.board._producer_submit(
            request(), "restart-old-attention-1", plan)

        def unknown_after_submit(_lease, phase):
            phase(
                self.models.AttemptPhase.SUBMITTED,
                consumes_credit=self.models.CreditConsumption.UNKNOWN,
            )
            return self.executor_adapter.ExecutorAttemptResult({})

        self.board._run_authoritative_once(
            self.models.JobKind.VIDEO, unknown_after_submit, now=0, ttl=30)
        self.assertEqual(
            self.board._JOB_RUNTIME.job(first.jobs[0].job_id).state,
            self.models.JobState.NEEDS_ATTENTION,
        )

        failed = self.models.Job(
            self.models.JobId.new(), self.models.AssetId("V-A"),
            self.models.JobKind.VIDEO, self.models.JobOrigin.MANUAL,
            state=self.models.JobState.FAILED, version=1,
            rerun_of=first.jobs[0].job_id, replace_current=True,
        )
        self.board._JOB_REPOSITORY.create(
            failed,
            self.models.JobEvent(
                __import__("uuid").uuid4(), failed.job_id,
                self.models.EventActor.MANAGER, "attempt.failed",
                "validation.permanent", from_state=None,
                to_state=None,
            ),
        )

        self.board._shutdown_job_lifecycle()
        self.board.JOBS.clear()
        self.board._init_job_shadow("authoritative")

        self.assertNotIn("V-A", self.board.JOBS)
        self.assertEqual(self.board._job_invariant_diagnostics()["tong"], 0)

    def test_request_sau_shutdown_reopen_authoritative_khong_roi_ve_legacy(self):
        self.board._init_job_shadow("authoritative")
        first = self.board._producer_submit(
            self.request(), "shutdown-reopen-A", self.plan)
        self.board._shutdown_job_lifecycle()

        replay = self.board._producer_submit(
            self.request(), "shutdown-reopen-A", self.plan)

        self.assertTrue(replay.replayed)
        self.assertEqual(replay.jobs[0].job_id, first.jobs[0].job_id)
        self.assertEqual(self.board._JOB_MODE, "authoritative")
        self.assertIsNotNone(self.board._JOB_RUNTIME)
        self.assertEqual(self.board.IMG_QUEUE.qsize(), 0)

    def test_attention_van_hien_tren_ui_sau_nhieu_lan_restart(self):
        self.board.ACCOUNTS = [{
            "id": "fake", "port": 9222, "kind": "img",
            "enabled": True, "tabs": 1,
        }]
        self.board._init_job_shadow("authoritative")
        self.board._producer_submit(
            self.request(), "attention-restart-A", self.plan)
        lease = self.board._JOB_RUNTIME.lease_next(
            self.models.JobKind.IMAGE, now=0, ttl=30)
        self.board._JOB_RUNTIME.attempt_phase(
            lease.lease_id,
            self.models.AttemptPhase.SUBMITTED,
            now=1,
            consumes_credit=self.models.CreditConsumption.UNKNOWN,
        )

        for _ in range(2):
            self.board._shutdown_job_lifecycle()
            self.board.JOBS.clear()
            self.board._init_job_shadow("authoritative")
            self.assertEqual(self.board.JOBS["SF-A"]["state"], "error")
            self.assertIn("không tự gửi lại", self.board.JOBS["SF-A"]["msg"])

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

    def test_authoritative_huy_viec_bang_job_id_khong_can_jobs_projection(self):
        self.board._init_job_shadow("authoritative")
        create = make_handler(
            self.board,
            "/api/generate?sf=SF-A&idempotency_key=cancel-by-id-A",
        )
        create.do_POST()
        job_id = create.captured[1]["job_id"]
        self.board.JOBS.clear()
        cancel = make_handler(
            self.board, f"/api/huy-viec?job_id={job_id}")

        cancel.do_POST()

        self.assertTrue(cancel.captured[1]["ok"])
        self.assertEqual(cancel.captured[1]["job_id"], job_id)
        self.assertEqual(
            self.board._JOB_RUNTIME.job(
                self.models.JobId.parse(job_id)).state,
            self.models.JobState.CANCELLED,
        )

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

    def test_authoritative_dung_het_khong_can_jobs_projection(self):
        self.board._init_job_shadow("authoritative")
        job_ids = []
        for sf in ("SF-A", "SF-B"):
            create = make_handler(
                self.board,
                f"/api/generate?sf={sf}&idempotency_key=projectionless-{sf}",
            )
            create.do_POST()
            job_ids.append(create.captured[1]["job_id"])
        self.board.JOBS.clear()
        stop = make_handler(self.board, "/api/dung-het")

        stop.do_POST()

        self.assertEqual(stop.captured[1]["bo"], 2)
        self.assertEqual(stop.captured[1]["con_lai"], [])
        for job_id in job_ids:
            self.assertEqual(
                self.board._JOB_RUNTIME.job(
                    self.models.JobId.parse(job_id)).state,
                self.models.JobState.CANCELLED,
            )

    def test_dung_het_an_toan_bao_ro_video_da_submit_con_chay(self):
        self.board.ACCOUNTS = [{
            "id": "fake", "port": 9222, "kind": "vid",
            "enabled": True, "tabs": 1,
        }]
        self.board._init_job_shadow("authoritative")
        request = self.producer.CreateJobRequest(
            self.models.AssetId("V-A"), self.models.JobKind.VIDEO,
            self.models.JobOrigin.MANUAL, "scope:stop-video:A", manual=True,
        )

        def video_plan(result):
            return self.compat.LegacyPlan((self.compat.LegacyAction(
                "stop-video:A", ("V-A",), (result.jobs[0].job_id,),
                "vid", "V-A", True,
            ),))

        result = self.board._producer_submit(
            request, "stop-video-A", video_plan)
        lease = self.board._JOB_RUNTIME.lease_next(
            self.models.JobKind.VIDEO, now=0, ttl=30)
        self.board._JOB_RUNTIME.attempt_phase(
            lease.lease_id,
            self.models.AttemptPhase.SUBMITTED,
            now=1,
            consumes_credit=self.models.CreditConsumption.UNKNOWN,
        )
        self.board._runtime_project_jobs(lease.member_job_ids)
        stop = make_handler(self.board, "/api/dung-het")

        stop.do_POST()

        body = stop.captured[1]
        self.assertEqual(body["con_lai"], ["V-A"])
        self.assertEqual(body["dung"], 0)
        self.assertEqual(
            self.board._JOB_RUNTIME.job(result.jobs[0].job_id).state,
            self.models.JobState.RUNNING,
        )
        self.assertEqual(self.board.JOBS["V-A"]["state"], "running")

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

    def test_adapter_partial_group_chi_retry_member_thieu(self):
        self.board.ACCOUNTS = [{
            "id": "fake", "port": 9222, "kind": "img",
            "enabled": True, "tabs": 1,
        }]
        self.board._init_job_shadow("authoritative")
        members = tuple(
            self.producer.CreateJobRequest(
                self.models.AssetId(asset), self.models.JobKind.IMAGE,
                self.models.JobOrigin.MANUAL, f"scope:{asset}", manual=True,
                replace_current=True,
            )
            for asset in ("SF-A", "SF-B")
        )

        def grouped_plan(result):
            ids = tuple(job.job_id for job in result.jobs)
            return self.compat.LegacyPlan((self.compat.LegacyAction(
                "group:A:B", ("LO:SF-A,SF-B",), ids,
                "img", "LO:SF-A,SF-B", True,
                state_idents=("SF-A", "SF-B"),
                member_bindings=(("SF-A", (ids[0],)), ("SF-B", (ids[1],))),
            ),))

        request = self.producer.CreateBatchRequest(
            members, self.models.BatchMode.IMAGE_GROUP)
        result = self.board._producer_submit(
            request, "partial-adapter-A-B", grouped_plan)

        def execute(_lease, _phase):
            return self.executor_adapter.ExecutorAttemptResult({
                result.jobs[0].job_id: ("/tmp/A.png",),
            })

        outcome = self.board._run_authoritative_once(
            self.models.JobKind.IMAGE, execute, now=0, ttl=30)

        self.assertEqual(outcome.decision.reason_code, "batch.partial")
        self.assertEqual(
            self.board._JOB_RUNTIME.job(result.jobs[0].job_id).state,
            self.models.JobState.COMPLETED,
        )
        self.assertEqual(
            self.board._JOB_RUNTIME.job(result.jobs[1].job_id).state,
            self.models.JobState.RETRY_WAIT,
        )
        self.assertEqual(self.board.JOBS["SF-A"]["state"], "done")
        self.assertEqual(self.board.JOBS["SF-B"]["state"], "queued")

    def test_video_zero_output_sau_submit_vao_attention_khong_partial_retry(self):
        self.board.ACCOUNTS = [{
            "id": "fake", "port": 9222, "kind": "vid",
            "enabled": True, "tabs": 1,
        }]
        self.board._init_job_shadow("authoritative")
        request = self.producer.CreateJobRequest(
            self.models.AssetId("V-A"), self.models.JobKind.VIDEO,
            self.models.JobOrigin.MANUAL, "scope:video-zero:A", manual=True,
        )

        def video_plan(result):
            return self.compat.LegacyPlan((self.compat.LegacyAction(
                "video-zero:A", ("V-A",), (result.jobs[0].job_id,),
                "vid", "V-A", True,
            ),))

        result = self.board._producer_submit(
            request, "video-zero-A", video_plan)

        def execute(_lease, phase):
            phase(
                self.models.AttemptPhase.SUBMITTED,
                consumes_credit=self.models.CreditConsumption.UNKNOWN,
            )
            return self.executor_adapter.ExecutorAttemptResult({})

        outcome = self.board._run_authoritative_once(
            self.models.JobKind.VIDEO, execute, now=0, ttl=30)

        self.assertEqual(outcome.decision.reason_code, "outcome.unknown")
        self.assertEqual(
            self.board._JOB_RUNTIME.job(result.jobs[0].job_id).state,
            self.models.JobState.NEEDS_ATTENTION,
        )
        self.assertEqual(self.board._JOB_RUNTIME.scheduler.ready(now=999), ())

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
