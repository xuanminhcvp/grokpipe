"""Client phải GỬI KÈM khoá ý định, và khoá phải ổn định đúng lúc cần.

Server đã chống trùng bằng `Idempotency-Key`, nhưng chốt đó chỉ có tác dụng khi
client thật sự gửi key — và gửi LẠI cùng key khi thử lại. Sinh key mới ở mỗi lần
gửi thì server thấy hai ý định khác nhau và xếp hai lượt render, đúng bug cũ.

Test gọi thẳng helper thật (Node cho trình duyệt, import module cho CLI) chứ
không đọc mã nguồn bằng regex: phép so chuỗi xanh cả khi hành vi đã hỏng.
"""

import importlib.util
import io
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_chay_anh():
    spec = importlib.util.spec_from_file_location(
        "_chay_anh_for_tests", ROOT / "sfboard/chay-anh.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)          # import KHÔNG được chạy vòng lặp
    return module


class BrowserHelperTest(unittest.TestCase):
    def setUp(self):
        if not shutil.which("node"):
            self.skipTest("máy này không có node")

    def test_helper_gui_dung_key_va_tra_ve_body(self):
        program = r"""
const { postJob } = require('./sfboard/ui/job-request.js');
const calls = [];
const fakeFetch = async (path, options) => {
  calls.push({ path, options });
  return { json: async () => ({ ok: true, job_id: 'job-1' }) };
};
(async () => {
  const result = await postJob('/api/generate?sf=A', 'stable-key', fakeFetch);
  if (calls.length !== 1) process.exit(10);
  if (calls[0].options.method !== 'POST') process.exit(11);
  if (calls[0].options.headers['Idempotency-Key'] !== 'stable-key') process.exit(12);
  if (result.body.job_id !== 'job-1' || result.key !== 'stable-key') process.exit(13);
})().catch(() => process.exit(14));
"""
        ket_qua = subprocess.run(["node", "-e", program], cwd=ROOT,
                                 capture_output=True, text=True)
        self.assertEqual(ket_qua.returncode, 0, ket_qua.stderr)

    def test_khong_truyen_key_thi_helper_tu_sinh_mot_key_khac_nhau(self):
        program = r"""
const { postJob } = require('./sfboard/ui/job-request.js');
const seen = [];
const fakeFetch = async (_path, options) => {
  seen.push(options.headers['Idempotency-Key']);
  return { json: async () => ({ ok: true }) };
};
(async () => {
  await postJob('/api/generate?sf=A', undefined, fakeFetch);
  await postJob('/api/generate?sf=A', undefined, fakeFetch);
  if (seen.length !== 2) process.exit(10);
  if (!seen[0] || !seen[1]) process.exit(11);
  if (seen[0] === seen[1]) process.exit(12);
})().catch(() => process.exit(13));
"""
        ket_qua = subprocess.run(["node", "-e", program], cwd=ROOT,
                                 capture_output=True, text=True)
        self.assertEqual(ket_qua.returncode, 0, ket_qua.stderr)


class BoardHtmlOrderTest(unittest.TestCase):
    def test_job_request_nap_truoc_board_js(self):
        html = (ROOT / "sfboard/ui/board.html").read_text(encoding="utf-8")
        self.assertLess(
            html.index("/ui/job-request.js"),
            html.index("/ui/board.js"),
            "sai thứ tự script thì board.js không có helper lúc chạy dòng đầu",
        )
        self.assertLess(
            html.index("/ui/job-projection.js"),
            html.index("/ui/board.js"),
            "sai thứ tự script thì board.js không có lifecycle projection",
        )

    def test_moi_script_trong_html_deu_duoc_board_phuc_vu(self):
        """Thêm file JS mà quên mở đường phục vụ nó = UI CHẾT TRẮNG.

        `board.js` đọc global helper ngay dòng đầu; helper không tải được thì
        cả file ném lỗi và không nút nào chạy. Board lại chốt tên file bằng
        danh sách trắng ở HAI chỗ (`_doc_ui` và nhánh `do_GET`), nên quên một
        chỗ là đủ hỏng — bắt được đúng ca này lúc smoke 2026-08-16.
        """
        html = (ROOT / "sfboard/ui/board.html").read_text(encoding="utf-8")
        board = (ROOT / "sfboard/sfboard.py").read_text(encoding="utf-8")
        srcs = re.findall(r'<script src="/ui/([^"]+)"', html)
        self.assertTrue(srcs, "không tìm thấy script nào trong board.html")
        for ten in srcs:
            self.assertIn(f'"{ten}"', board,
                          f"{ten} chưa nằm trong danh sách trắng của board")
            self.assertIn(f'"/ui/{ten}"', board,
                          f"/ui/{ten} chưa có đường phục vụ trong do_GET")

    def test_board_js_khong_con_fetch_tran_toi_duong_tao(self):
        js = (ROOT / "sfboard/ui/board.js").read_text(encoding="utf-8")
        for duong in ("/api/generate", "/api/tao-lo", "/api/genvideo",
                      "/api/video-lo", "/api/master?chay=1"):
            for dong in js.splitlines():
                if duong in dong and "fetch(" in dong and "postJob" not in dong:
                    self.fail(f"còn fetch trần tới {duong}: {dong.strip()[:90]}")

    def test_board_ui_doc_structured_lifecycle_va_khong_optimistic_ghi_jobs(self):
        js = (ROOT / "sfboard/ui/board.js").read_text(encoding="utf-8")
        self.assertIn("r.lifecycle", js)
        self.assertIn("SUBMITTING", js)
        self.assertNotRegex(js, r"JOBS\s*\[[^\]]+\]\s*=")
        self.assertIn("job_id=", js)


class CliKeyTest(unittest.TestCase):
    def setUp(self):
        self.m = load_chay_anh()

    def test_post_gui_dung_key(self):
        thay = []

        class _Tra(io.BytesIO):
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *_a):
                return False

        def fake_urlopen(request, timeout=None):
            thay.append(request)
            return _Tra(json.dumps({"ok": True, "job_id": "job-1"}).encode("utf-8"))

        cu = self.m.urllib.request.urlopen
        self.m.urllib.request.urlopen = fake_urlopen
        try:
            body = self.m.post("/api/generate?sf=A", "stable-key")
        finally:
            self.m.urllib.request.urlopen = cu

        self.assertEqual(thay[0].get_header("Idempotency-key"), "stable-key")
        self.assertEqual(body, {"ok": True, "job_id": "job-1"})

    def test_key_giu_nguyen_toi_khi_chu_dong_xoay(self):
        khoa = iter(("key-1", "key-2"))
        keys = self.m.RequestKeys(lambda: next(khoa))

        self.assertEqual(keys.for_asset("A"), "key-1")
        self.assertEqual(keys.for_asset("A"), "key-1")
        self.assertEqual(keys.rotate("A"), "key-2")
        self.assertEqual(keys.for_asset("A"), "key-2")

    def test_moi_asset_mot_khoa_rieng(self):
        keys = self.m.RequestKeys()
        self.assertNotEqual(keys.for_asset("A"), keys.for_asset("B"))


if __name__ == "__main__":
    unittest.main()
