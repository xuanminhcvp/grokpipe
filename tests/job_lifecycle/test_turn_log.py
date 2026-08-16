"""Sổ lượt phải chịu được NHIỀU THỢ ghi cùng lúc.

Log thật 2026-08-15 trên board ALTAR, lặp 7 lần trong hai phút:

    không ghi được sổ lượt: [Errno 2] No such file or directory:
    '…/cho-phan-loai/nhat-ky.json.tmp' -> '…/cho-phan-loai/nhat-ky.json'

`turn_log_ghi` dùng MỘT tên tạm cố định cho mọi luồng. Bốn thợ ghi cùng lúc thì
thợ nào `os.replace` trước sẽ mang file tạm đi, thợ sau `replace` vào chỗ trống →
ENOENT. Cái tệ hơn không hiện trong log: cả hai đều `dict(self.turn_log())` từ
trước rồi ghi đè cả file, nên dòng của thợ này XOÁ dòng của thợ kia — mất sổ mà
im lặng. Sổ lượt là thứ trả lời "bản này ra từ lượt ChatGPT nào", mất là mất hẳn.
"""

import threading
import unittest

from helpers import load_sfboard


class TurnLogTest(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.m = load_sfboard()
        self.tmpdir = tempfile.mkdtemp()
        self.board = self.m.Board(self.tmpdir)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_ghi_tuan_tu_van_giu_du_moi_dong(self):
        for i in range(5):
            self.board.turn_log_ghi(f"SF-{i}.png", {"luot": i})

        self.assertEqual(len(self.board.turn_log()), 5)

    def test_bon_tho_ghi_cung_luc_khong_mat_dong_nao_va_khong_loi(self):
        """Bốn thợ = bốn cửa sổ Chrome, đúng trần user đặt."""
        loi = []
        xong = threading.Barrier(4)

        def tho(n):
            try:
                xong.wait(5)                       # ép bốn luồng vào cùng một nhịp
                for i in range(15):
                    self.board.turn_log_ghi(f"SF-{n}-{i}.png", {"tho": n, "luot": i})
            except Exception as e:                 # noqa: BLE001
                loi.append(f"{type(e).__name__}: {e}")

        ts = [threading.Thread(target=tho, args=(n,)) for n in range(4)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(20)

        self.assertEqual(loi, [])
        so = self.board.turn_log()
        self.assertEqual(len(so), 60, f"mất {60 - len(so)} dòng sổ vì các thợ đè lên nhau")
        # và đọc lại TỪ ĐĨA, không phải từ bộ nhớ đệm
        tuoi = self.m.Board(self.tmpdir)
        self.assertEqual(len(tuoi.turn_log()), 60)

    def test_khong_de_lai_file_tam(self):
        """File tạm rơi vãi làm bẩn thư mục ảnh chờ phân loại."""
        import os

        for i in range(5):
            self.board.turn_log_ghi(f"SF-{i}.png", {"luot": i})

        con = [x for x in os.listdir(self.board.pl) if x.endswith(".tmp")]
        self.assertEqual(con, [])


if __name__ == "__main__":
    unittest.main()
