import tempfile
import unittest
from pathlib import Path

from sfboard.jobs.executor_adapter import ExecutorAttemptResult
from sfboard.jobs.models import AttemptPhase, CreditConsumption, JobId
from sfboard.live_executor import (
    ImageAttemptItem,
    ImageAttemptRequest,
    ImageProviderResponse,
    LivePreSubmitError,
    VideoAttemptRequest,
    run_image_attempt,
    run_video_attempt,
)


class LiveExecutorTest(unittest.TestCase):
    def setUp(self):
        self.a = JobId.new()
        self.b = JobId.new()
        self.phases = []

    def emit(self, phase, **kwargs):
        self.phases.append((phase, kwargs.get("consumes_credit")))

    def image_request(self):
        return ImageAttemptRequest((
            ImageAttemptItem(self.a, "REF_A", "prompt A"),
            ImageAttemptItem(self.b, "REF_B", "prompt B"),
        ), ("/ref/a.png",), "luật chung", False)

    def test_image_exact_count_map_theo_job_id_va_phase(self):
        callbacks_seen = []

        def provider(request, *, on_submitted, on_waiting_provider):
            self.assertEqual(len(request.items), 2)
            on_submitted(); callbacks_seen.append("submitted")
            on_waiting_provider(); callbacks_seen.append("waiting")
            return ImageProviderResponse(
                ("src-a", "src-b"), "chat", {"da_gui": True})

        result = run_image_attempt(
            self.image_request(), self.emit,
            provider=provider,
            downloader=lambda response: ("/turn/01.png", "/turn/02.png"),
            saver=lambda item, path: f"/versions/{item.asset_id}.png",
        )

        self.assertIsInstance(result, ExecutorAttemptResult)
        self.assertEqual(result.outputs, {
            self.a: ("/versions/REF_A.png",),
            self.b: ("/versions/REF_B.png",),
        })
        self.assertEqual(callbacks_seen, ["submitted", "waiting"])
        self.assertEqual([phase for phase, _ in self.phases], [
            AttemptPhase.ATTACHING,
            AttemptPhase.SUBMITTED,
            AttemptPhase.WAITING_PROVIDER,
            AttemptPhase.DOWNLOADING,
            AttemptPhase.SAVING,
        ])
        self.assertEqual(
            self.phases[1][1], CreditConsumption.TRUE)

    def test_image_lech_so_hoac_co_text_giu_turn_nhung_khong_doan_mapping(self):
        saved = []

        def provider(_request, *, on_submitted, on_waiting_provider):
            on_submitted(); on_waiting_provider()
            return ImageProviderResponse(
                ("src-a",), "chat", {"da_gui": True, "loi_text": "xin lỗi"})

        result = run_image_attempt(
            self.image_request(), self.emit,
            provider=provider,
            downloader=lambda _response: ("/turn/01.png",),
            saver=lambda item, path: saved.append((item, path)),
        )

        self.assertEqual(result.outputs, {})
        self.assertEqual(saved, [])
        self.assertIn(AttemptPhase.DOWNLOADING, [p for p, _ in self.phases])
        self.assertNotIn(AttemptPhase.SAVING, [p for p, _ in self.phases])

    def test_image_chua_submit_nem_loi_pre_submit_de_runtime_tu_quyet_retry(self):
        def provider(_request, **_callbacks):
            return ImageProviderResponse((), "", {"da_gui": False})

        with self.assertRaises(LivePreSubmitError):
            run_image_attempt(
                self.image_request(), self.emit,
                provider=provider,
                downloader=lambda _response: (),
                saver=lambda _item, _path: "",
            )
        self.assertEqual(
            [phase for phase, _ in self.phases], [AttemptPhase.ATTACHING])

    def test_video_reserve_truoc_submit_va_tra_ca_ban_phu(self):
        order = []

        def provider(request, *, before_submit, on_submitted,
                     on_waiting_provider, on_downloading, on_saving):
            self.assertEqual(request.shot_id, "S1-01")
            before_submit(); order.append("submit")
            on_submitted(); on_waiting_provider()
            on_downloading(); on_saving()
            return (request.output_path, "/versions/S1-01_v2.mp4")

        request = VideoAttemptRequest(
            self.a, "S1-01", "camera moves", "/assets/SF.png", 10,
            "/versions/S1-01_v1.mp4")
        result = run_video_attempt(
            request, self.emit, provider=provider,
            reserve_submit=lambda: order.append("reserve"))

        self.assertEqual(order, ["reserve", "submit"])
        self.assertEqual(result.outputs[self.a], (
            "/versions/S1-01_v1.mp4", "/versions/S1-01_v2.mp4"))
        self.assertEqual([phase for phase, _ in self.phases], [
            AttemptPhase.ATTACHING,
            AttemptPhase.SUBMITTED,
            AttemptPhase.WAITING_PROVIDER,
            AttemptPhase.DOWNLOADING,
            AttemptPhase.SAVING,
        ])


if __name__ == "__main__":
    unittest.main()
