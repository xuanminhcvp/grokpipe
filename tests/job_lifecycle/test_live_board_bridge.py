import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from helpers import FakeBoard, load_sfboard, reset_legacy_state


class LiveBoardBridgeTest(unittest.TestCase):
    def setUp(self):
        self.board = load_sfboard()
        reset_legacy_state(self.board)
        self.models = __import__("jobs.models", fromlist=["x"])
        self.results = __import__("jobs.results", fromlist=["x"])
        self.adapter = __import__("jobs.executor_adapter", fromlist=["x"])
        self.old_board = self.board.BOARD
        self.old_runtime = self.board._JOB_RUNTIME

    def tearDown(self):
        self.board.BOARD = self.old_board
        self.board._JOB_RUNTIME = self.old_runtime
        reset_legacy_state(self.board)

    def test_prepare_image_chi_lay_member_running_va_giu_thu_tu_lease(self):
        first_id = self.models.JobId.new()
        done_id = self.models.JobId.new()
        scenes = [{"id": "REF", "sfs": [
            {"id": "REF_A_PORTRAIT", "prompt": "portrait A",
             "refs": {"chars": [], "bg": None}},
            {"id": "REF_B_PORTRAIT", "prompt": "portrait B",
             "refs": {"chars": [], "bg": None}},
        ], "shots": []}]
        self.board.BOARD = FakeBoard(scenes=scenes)
        jobs = {
            first_id: SimpleNamespace(
                job_id=first_id, asset_id=self.models.AssetId("REF_A_PORTRAIT"),
                state=self.models.JobState.RUNNING),
            done_id: SimpleNamespace(
                job_id=done_id, asset_id=self.models.AssetId("REF_B_PORTRAIT"),
                state=self.models.JobState.COMPLETED),
        }
        self.board._JOB_RUNTIME = SimpleNamespace(job=lambda job_id: jobs[job_id])
        lease = SimpleNamespace(member_job_ids=(first_id, done_id))

        request = self.board._live_image_request(lease)

        self.assertEqual(
            [(item.job_id, item.asset_id) for item in request.items],
            [(first_id, "REF_A_PORTRAIT")],
        )
        self.assertFalse(request.stamp_codes)

    def test_prepare_image_gom_portrait_va_full_khong_doi_ref_noi_bo(self):
        portrait_id = self.models.JobId.new()
        full_id = self.models.JobId.new()
        scenes = [{"id": "REF", "sfs": [
            {"id": "REF_DENISE_PORTRAIT", "prompt": "portrait Denise",
             "refs": {"chars": [], "bg": None}},
            {"id": "REF_DENISE_UNIFORM_FULL", "prompt": "full Denise",
             "refs": {"chars": ["REF_DENISE_PORTRAIT"], "bg": None}},
        ], "shots": []}]
        self.board.BOARD = FakeBoard(scenes=scenes)
        jobs = {
            portrait_id: SimpleNamespace(
                job_id=portrait_id,
                asset_id=self.models.AssetId("REF_DENISE_PORTRAIT"),
                state=self.models.JobState.RUNNING),
            full_id: SimpleNamespace(
                job_id=full_id,
                asset_id=self.models.AssetId("REF_DENISE_UNIFORM_FULL"),
                state=self.models.JobState.RUNNING),
        }
        self.board._JOB_RUNTIME = SimpleNamespace(job=lambda job_id: jobs[job_id])

        request = self.board._live_image_request(
            SimpleNamespace(member_job_ids=(portrait_id, full_id)))

        self.assertEqual(
            [item.asset_id for item in request.items],
            ["REF_DENISE_PORTRAIT", "REF_DENISE_UNIFORM_FULL"],
        )
        self.assertEqual(request.attachments, ())

    def test_apply_chi_accept_moi_duoc_de_current(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            project = Path(tmp.name) / "project"
            self.board.BOARD = self.board.Board(str(project))
            accepted = Path(tmp.name) / "accepted.png"
            kept = Path(tmp.name) / "kept.png"
            accepted.write_bytes(b"accepted")
            kept.write_bytes(b"kept")
            job_id = self.models.JobId.new()
            job = SimpleNamespace(
                asset_id=self.models.AssetId("REF_A_PORTRAIT"),
                kind=self.models.JobKind.IMAGE,
            )
            self.board._JOB_RUNTIME = SimpleNamespace(
                job=lambda _job_id: job,
                results=SimpleNamespace(
                    last_user_mutation=lambda _asset_id: None),
            )
            outcome = self.adapter.ExecutorRunOutcome(verdicts={
                job_id: self.results.CommitVerdict(
                    self.results.CommitDecision.ACCEPT, "accepted",
                    (str(accepted),)),
            })

            self.board._live_apply_outcome(SimpleNamespace(), outcome)
            current = Path(self.board.BOARD.find_file("REF_A_PORTRAIT"))
            self.assertEqual(current.read_bytes(), b"accepted")

            store_only = self.adapter.ExecutorRunOutcome(verdicts={
                job_id: self.results.CommitVerdict(
                    self.results.CommitDecision.STORE_AS_VERSION,
                    "user_mutation_wins", (str(kept),)),
            })
            self.board._live_apply_outcome(SimpleNamespace(), store_only)
            self.assertEqual(current.read_bytes(), b"accepted")

            # Verdict có thể đã ACCEPT trước khi request upload/pick của user
            # kịp ghi dấu. Applier phải kiểm lại ngay lúc đụng current.
            self.board._JOB_RUNTIME = SimpleNamespace(
                job=lambda _job_id: job,
                results=SimpleNamespace(
                    last_user_mutation=lambda _asset_id: 11.0),
            )
            accepted_late = self.adapter.ExecutorRunOutcome(verdicts={
                job_id: self.results.CommitVerdict(
                    self.results.CommitDecision.ACCEPT, "accepted",
                    (str(kept),)),
            })
            self.board._live_apply_outcome(
                SimpleNamespace(started_at=10.0), accepted_late)
            self.assertEqual(current.read_bytes(), b"accepted")
        finally:
            tmp.cleanup()

    def test_video_session_loi_truoc_submit_xoa_placeholder_rong(self):
        live = __import__("live_executor", fromlist=["VideoAttemptRequest"])
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "V-A_v1.mp4"
            output.touch()
            request = live.VideoAttemptRequest(
                self.models.JobId.new(), "V-A", "motion",
                str(Path(tmp) / "start.png"), 5.0, str(output),
            )
            with mock.patch.object(
                self.board, "_live_bind_lease",
            ), mock.patch.object(
                self.board, "_live_video_request", return_value=request,
            ), mock.patch.object(
                self.board, "_grok", side_effect=RuntimeError("CDP chết"),
            ):
                with self.assertRaisesRegex(RuntimeError, "CDP chết"):
                    self.board._live_video_attempt(
                        SimpleNamespace(), lambda *_args, **_kwargs: None)

            self.assertFalse(output.exists())

    def test_startup_chi_don_placeholder_video_rong_do_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            self.board.BOARD = self.board.Board(str(project))
            empty = Path(self.board.BOARD.vversions) / "V-A_v1.mp4"
            valid = Path(self.board.BOARD.vversions) / "V-B_v1.mp4"
            empty.touch()
            valid.write_bytes(b"valid-video")

            removed = self.board._live_cleanup_empty_video_reservations()

            self.assertEqual(removed, 1)
            self.assertFalse(empty.exists())
            self.assertEqual(valid.read_bytes(), b"valid-video")


if __name__ == "__main__":
    unittest.main()
