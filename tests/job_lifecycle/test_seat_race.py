"""Hạ rồi nâng số tab KHÔNG được đẻ hai thợ trên một chỗ ngồi.

Chỗ ngồi không phải sổ sách: nó LÀ danh tính tab. `image_chatgpt.py` và
`video_grok.py` tìm tab của thợ bằng `window.name == "cgslot<N>"` / `"gpslot<N>"`.
Hai luồng cùng slot nghĩa là hai thợ gõ vào CÙNG MỘT tab Chrome — và khi luồng cũ
tới lượt nghỉ, nó gọi `_dong_tab_cho_ngoi` để `window.name = ""` rồi `pg.close()`,
giật tab khỏi tay luồng mới đang làm dở. Nó cũng vượt trần tab mà `_so_tab_theo_viec`
sinh ra để canh RAM.

Đường đi: supervisor `pop()` khoá của ghế dôi ra NGAY, trong khi `_worker` chỉ soi
`_cho_ngoi_con_dung` ở ĐẦU VÒNG — tức tới 2 giây nếu đang rỗi, tới vài PHÚT nếu
đang giữa lượt vẽ. Nâng số tab lại trong quãng đó thì `WORKERS.get(key)` trả None
và supervisor mở thêm một luồng nữa cho đúng ghế ấy.
"""

import threading
import unittest

from helpers import load_sfboard, reset_legacy_state


def tk(port=9222, tabs=2, **kw):
    a = {"id": f"gpt-{port}", "kind": "img", "port": port, "tabs": tabs, "enabled": True}
    a.update(kw)
    return a


class LuongGia:
    """Đủ giống `threading.Thread` cho phần sổ sách: chỉ cần `is_alive()`."""

    def __init__(self, kind, slot):
        self.kind, self.slot = kind, slot
        self.song = True

    def is_alive(self):
        return self.song


class SeatRaceTest(unittest.TestCase):
    def setUp(self):
        self.m = load_sfboard()
        reset_legacy_state(self.m)
        self.workers_cu = dict(self.m.WORKERS)
        self.m.WORKERS.clear()
        self.acc_cu, self.m.ACCOUNTS = self.m.ACCOUNTS, []

    def tearDown(self):
        self.m.WORKERS.clear()
        self.m.WORKERS.update(self.workers_cu)
        self.m.ACCOUNTS = self.acc_cu
        reset_legacy_state(self.m)

    def xep(self, a):
        """Chạy đúng một vòng sắp ghế của supervisor cho tài khoản này."""
        self.da_mo = getattr(self, "da_mo", [])

        def mo_tho(kind, slot):
            th = LuongGia(kind, slot)
            self.da_mo.append((kind, slot))
            return th

        self.m._xep_ghe_cho_tai_khoan(a, ["img"], mo_tho)

    def test_ha_roi_nang_so_tab_khong_de_them_tho_cho_ghe_con_nguoi_ngoi(self):
        a = tk(tabs=2)
        self.xep(a)
        self.assertEqual(self.da_mo, [("img", 0), ("img", 1)])
        tho_ghe_1 = self.m.WORKERS[(9222, "img", 1)]

        a["tabs"] = 1           # user hạ số tab
        self.xep(a)             # luồng ghế 1 CHƯA kịp thấy — vẫn đang vẽ
        a["tabs"] = 2           # user nâng lại ngay
        self.xep(a)

        self.assertEqual(self.da_mo, [("img", 0), ("img", 1)],
                         "đã mở thêm một thợ nữa cho ghế 1 trong khi thợ cũ còn sống")
        self.assertIs(self.m.WORKERS[(9222, "img", 1)], tho_ghe_1)

    def test_tho_da_chet_that_thi_ghe_duoc_cap_lai(self):
        """Không được gác chặt tới mức ghế chết cứng — thợ chết là phải thay."""
        a = tk(tabs=2)
        self.xep(a)
        self.m.WORKERS[(9222, "img", 1)].song = False

        self.xep(a)

        self.assertEqual(self.da_mo.count(("img", 1)), 2)

    def test_ghe_doi_ra_chi_bi_xoa_khoi_so_khi_luong_da_chet(self):
        a = tk(tabs=2)
        self.xep(a)

        a["tabs"] = 1
        self.xep(a)
        self.assertIn((9222, "img", 1), self.m.WORKERS,
                      "xoá khoá lúc luồng còn sống là mất tay cầm — nguồn của cả lỗi này")

        self.m.WORKERS[(9222, "img", 1)].song = False
        self.xep(a)
        self.assertNotIn((9222, "img", 1), self.m.WORKERS,
                         "chết rồi mà vẫn giữ khoá thì sổ phình mãi")

    def test_hai_luong_that_khong_bao_gio_cung_ngoi_mot_ghe(self):
        """Luồng THẬT, không phải sổ sách: chốt cuối cùng là số thợ sống trên ghế.

        MỌI phép chờ ở đây đều có hạn giờ. Bản đầu dùng `while len(song) < 2: pass`
        — một thợ không khởi động được vì regression thì pytest TREO thay vì đỏ,
        và treo trong CI thì không ai đọc ra nguyên nhân. Test đồng thời mà thiếu
        deadline là tự biến lỗi thành im lặng.
        """
        a = tk(tabs=2)
        cho_nghi = threading.Event()
        du_hai = threading.Event()
        song = []
        khoa = threading.Lock()

        def mo_tho(kind, slot):
            def than():
                with khoa:
                    song.append(slot)
                    if len(song) >= 2:
                        du_hai.set()
                cho_nghi.wait(5)
                with khoa:
                    song.remove(slot)
            th = threading.Thread(target=than, daemon=True)
            th.start()
            return th

        try:
            self.m._xep_ghe_cho_tai_khoan(a, ["img"], mo_tho)
            self.assertTrue(du_hai.wait(5), "hai thợ đầu không khởi động nổi trong 5 giây")

            a["tabs"] = 1
            self.m._xep_ghe_cho_tai_khoan(a, ["img"], mo_tho)
            a["tabs"] = 2
            self.m._xep_ghe_cho_tai_khoan(a, ["img"], mo_tho)

            with khoa:
                self.assertEqual(song.count(1), 1, "hai thợ thật đang cùng ngồi ghế 1")
        finally:
            # PHẢI nằm trong `finally`: assert đỏ ở trên mà không thả cờ thì bốn
            # luồng còn treo tới hết 5 giây, và test sau chạy chồng lên chúng.
            cho_nghi.set()


if __name__ == "__main__":
    unittest.main()
