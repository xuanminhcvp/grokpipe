"""HTTP smoke thật trên localhost, không khởi động browser/provider."""

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from helpers import load_sfboard, reset_legacy_state


class InertBoardSmokeTest(unittest.TestCase):
    def setUp(self):
        self.board = load_sfboard()
        reset_legacy_state(self.board)
        self.old_board = self.board.BOARD
        self.old_accounts = self.board.ACCOUNTS
        self.tmp = tempfile.TemporaryDirectory()
        project = Path(self.tmp.name) / "empty.project"
        self.board.BOARD = self.board.Board(str(project))
        self.board.ACCOUNTS = []
        self.board._init_job_shadow("authoritative")
        try:
            self.server = self.board.ThreadingHTTPServer(
                ("127.0.0.1", 0), self.board.Handler)
        except PermissionError as exc:
            self.board._shutdown_job_lifecycle()
            self.board.BOARD = self.old_board
            self.board.ACCOUNTS = self.old_accounts
            reset_legacy_state(self.board)
            self.tmp.cleanup()
            self.skipTest(f"sandbox không cho bind localhost: {exc}")
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.board._shutdown_job_lifecycle()
        self.board.BOARD = self.old_board
        self.board.ACCOUNTS = self.old_accounts
        reset_legacy_state(self.board)
        self.tmp.cleanup()

    def get(self, path):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=2)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            return response.status, response.read(), response.getheader(
                "Content-Type")
        finally:
            connection.close()

    def test_ui_jobs_va_diagnostics_len_cung_khong_goi_provider(self):
        forbidden = mock.Mock(side_effect=AssertionError("không được mở Chrome"))
        with mock.patch.object(self.board, "_launch_chrome", forbidden):
            ui_status, ui_body, ui_type = self.get("/")
            jobs_status, jobs_body, _ = self.get("/api/jobs")
            diag_status, diag_body, _ = self.get("/api/chan-doan")

        jobs = json.loads(jobs_body)
        diagnostics = json.loads(diag_body)
        self.assertEqual((ui_status, jobs_status, diag_status), (200, 200, 200))
        self.assertIn("text/html", ui_type)
        self.assertIn(b"<!doctype html", ui_body.lower())
        self.assertIn("jobs", jobs)
        self.assertEqual(diagnostics["job_shadow"]["mode"], "authoritative")
        self.assertEqual(diagnostics["hang_doi"], {"anh": 0, "video": 0})
        forbidden.assert_not_called()


if __name__ == "__main__":
    unittest.main()
