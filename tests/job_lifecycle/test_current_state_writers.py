import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class CurrentStateWriterInventoryTest(unittest.TestCase):
    def test_legacy_authority_markers_remain_visible_until_cutover(self):
        hangdoi = (ROOT / "sfboard/hangdoi.py").read_text(encoding="utf-8")
        board = (ROOT / "sfboard/sfboard.py").read_text(encoding="utf-8")
        required = {
            "JOBS writer hook": "class _Jobs(dict)",
            "group state spread": "def dat_job(",
            "image queue": "IMG_QUEUE",
            "video queue": "VID_QUEUE",
            "retry timer": "def _xep_lai_sau(",
            "retry guard": "_HOAN",
            "cancel flags": "DA_HUY",
            "forced account queue": "CHO_RIENG",
            "stop generation": "tang_dung_gen()",
            "auto producer": "def _auto_scene(",
            "worker assignment": "def _worker(",
        }
        combined = hangdoi + "\n" + board
        missing = [label for label, marker in required.items() if marker not in combined]
        self.assertEqual(missing, [], f"Authority marker biến mất: {missing}")

    # Hàm nào được phép GHI THẲNG vào `JOBS[...]`, và bao nhiêu chỗ trong mỗi hàm.
    # Đây là danh sách CHO PHÉP, không phải phép đếm tổng: `docs/JOB-LIFECYCLE-README.md`
    # nói mỗi lifecycle fact có đúng một authority, mà "tổng ≥ 20" thì thêm một
    # writer trái phép ở hàm hoàn toàn mới vẫn xanh — đúng bất biến nó mang tên
    # lại là thứ nó không canh nổi.
    #
    # Thêm/bớt chỗ ghi thì sửa bảng này VÀ nói rõ trong PR vì sao authority đổi.
    WRITER_CHO_PHEP = {
        "do_POST": 9,             # các endpoint tạo/huỷ/dừng
        "_generate_lo_ruot": 6,   # kết quả từng ảnh của một lô
        "_gen_video": 5,
        "_enqueue": 2,
        "_batch_tick": 2,
        "_gac_hang_doi": 2,
        "_pl_gan": 1,
        "_dat_nhan_lo": 1,        # nhãn CHUNG của lô, đi qua một cửa
        "_auto_scene": 1,
    }

    def test_every_direct_jobs_write_stays_auditable(self):
        """Đếm theo TỪNG HÀM bằng cây cú pháp, không đếm chuỗi `"JOBS["`.

        Đếm chuỗi thì trúng cả `JOBS[...]` trong phép ĐỌC, trong comment và
        trong docstring — và một writer mới thêm vào chỉ làm con số tăng, tức
        làm test càng xanh hơn.
        """
        import ast

        cay = ast.parse((ROOT / "sfboard/sfboard.py").read_text(encoding="utf-8"))
        trong_ham = {}
        for n in ast.walk(cay):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for con in ast.walk(n):
                    trong_ham.setdefault(id(con), n.name)

        thay = {}
        for n in ast.walk(cay):
            dich = (n.targets if isinstance(n, ast.Assign)
                    else [n.target] if isinstance(n, (ast.AugAssign, ast.AnnAssign)) else [])
            for t in dich:
                if isinstance(t, ast.Subscript) and getattr(t.value, "id", "") == "JOBS":
                    ten = trong_ham.get(id(n), "<module>")
                    thay[ten] = thay.get(ten, 0) + 1

        self.assertEqual(
            thay, self.WRITER_CHO_PHEP,
            "danh sách nơi ghi thẳng vào JOBS đã đổi — thêm writer là thêm một "
            "authority, phải sửa docs/JOB-LIFECYCLE-README.md trước rồi mới sửa bảng này")
