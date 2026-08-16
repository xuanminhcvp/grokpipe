"""Tài khoản: ép là RÀNG BUỘC CỦA CẢ JOB, không phải của riêng lần chạy đầu.

Ba luật ở đây đều là thứ đã cắn thật:

  · ép tài khoản rồi việc lỗi → lần thử sau phải VẪN ở tài khoản đó. Chat sống
    trong profile Chrome của đúng tài khoản đã mở nó, nên xếp lại vào hàng chung
    là mở chat trắng ở máy khác — đúng thứ user ép tài khoản để tránh;
  · video KHÔNG được rơi vào profile chưa mở Grok. Board từng định tuyến việc
    video sang tài khoản ChatGPT rồi báo "Không nối được Grok";
  · lỗi dữ liệu (prompt sai, thiếu ref) KHÔNG được làm tài khoản bị phạt — nó
    hỏng ở đâu cũng hỏng, cho nghỉ tài khoản chỉ làm mất chỗ chạy.
"""

import unittest

from sfboard.jobs.accounts import (
    AccountAllocator, AccountHealth, NoAccountAvailable,
)
from sfboard.jobs.models import JobKind


class AccountAllocatorTest(unittest.TestCase):
    def setUp(self):
        self.a = AccountAllocator()
        self.a.register("9222", allow_video=False, max_slots=2)
        self.a.register("9223", allow_video=True, max_slots=1)

    # ─────────────────────────── ép tài khoản ─────────────────────────

    def test_ep_tai_khoan_giu_qua_moi_lan_thu(self):
        self.a.force("LO:A,B", "9222")

        for lan in range(3):
            lease = self.a.allocate(JobKind.IMAGE, "LO:A,B", now=lan * 10)
            self.assertEqual(lease.account_id, "9222", f"mất ràng buộc ở lần {lan}")
            self.a.release(lease.lease_id)

    def test_ep_tai_khoan_dang_ban_thi_CHO_chu_khong_nhay_may_khac(self):
        self.a.register("9224", allow_video=False, max_slots=1)
        self.a.force("LO:A", "9224")
        giu = self.a.allocate(JobKind.IMAGE, "LO:A", now=0)

        self.assertEqual(giu.account_id, "9224")
        with self.assertRaises(NoAccountAvailable):
            self.a.allocate(JobKind.IMAGE, "LO:A", now=0)

    def test_cho_phep_fallback_thi_moi_duoc_nhay_may_khac(self):
        self.a.register("9224", allow_video=False, max_slots=1)
        self.a.force("LO:A", "9224", allow_fallback=True)
        self.a.allocate(JobKind.IMAGE, "LO:A", now=0)

        lease = self.a.allocate(JobKind.IMAGE, "LO:A", now=0)

        self.assertNotEqual(lease.account_id, "9224")

    def test_bo_ep_thi_ve_hang_chung(self):
        self.a.force("LO:A", "9222")
        self.a.unforce("LO:A")

        self.assertIsNone(self.a.forced_account_for("LO:A"))

    def test_tra_ra_tai_khoan_bi_ep_de_tang_tren_xep_lai_dung_cho(self):
        """Đây là thứ `_xep_lai_sau` cần: xếp lại vào hàng riêng của cổng nào."""
        self.a.force("LO:A", "9222")

        self.assertEqual(self.a.forced_account_for("LO:A"), "9222")
        self.assertIsNone(self.a.forced_account_for("LO:khac"))

    # ──────────────────────────── capability ──────────────────────────

    def test_video_chi_dung_profile_da_opt_in(self):
        lease = self.a.allocate(JobKind.VIDEO, "V-S1-01", now=0)

        self.assertEqual(lease.account_id, "9223")

    def test_khong_co_profile_video_thi_bao_ro_chu_khong_dung_bua(self):
        a = AccountAllocator()
        a.register("9222", allow_video=False, max_slots=1)

        with self.assertRaises(NoAccountAvailable):
            a.allocate(JobKind.VIDEO, "V-S1-01", now=0)

    def test_ep_vao_tai_khoan_khong_lam_video_bi_tu_choi(self):
        self.a.force("V-S1-01", "9222")

        with self.assertRaises(NoAccountAvailable):
            self.a.allocate(JobKind.VIDEO, "V-S1-01", now=0)

    # ───────────────────────────── sức khoẻ ───────────────────────────

    def test_qua_han_muc_thi_nghi_mot_lat_chu_khong_tat_han(self):
        """Cooldown là của hệ thống; `enabled` là công tắc của USER — hai thứ khác nhau."""
        self.a.cooldown("9222", until=100)

        self.assertEqual(self.a.health("9222"), AccountHealth.COOLDOWN)
        self.assertNotEqual(
            self.a.allocate(JobKind.IMAGE, "LO:A", now=50).account_id, "9222")
        self.assertTrue(self.a.enabled("9222"))

    def test_het_gio_nghi_thi_tu_khoe_lai(self):
        self.a.cooldown("9222", until=100)

        self.assertEqual(self.a.health("9222", now=100), AccountHealth.HEALTHY)

    def test_user_tat_tai_khoan_thi_khong_ai_duoc_dung(self):
        self.a.set_enabled("9222", False)
        self.a.set_enabled("9223", False)

        with self.assertRaises(NoAccountAvailable):
            self.a.allocate(JobKind.IMAGE, "LO:A", now=0)

    def test_loi_du_lieu_khong_phat_tai_khoan(self):
        self.a.report_error("9222", fatal=False, now=0)

        self.assertEqual(self.a.health("9222"), AccountHealth.HEALTHY)

    def test_mat_phien_thi_tai_khoan_bi_danh_dau_hong(self):
        self.a.report_error("9222", fatal=True, now=0)

        self.assertEqual(self.a.health("9222"), AccountHealth.UNAVAILABLE)
        self.assertNotEqual(
            self.a.allocate(JobKind.IMAGE, "LO:A", now=0).account_id, "9222")

    def test_hoi_phuc_sau_khi_mo_lai_cua_so(self):
        self.a.report_error("9222", fatal=True, now=0)
        self.a.recover("9222")

        self.assertEqual(self.a.health("9222"), AccountHealth.HEALTHY)

    # ───────────────────────────── chỗ ngồi ───────────────────────────

    def test_khong_cap_qua_so_cho_cua_mot_tai_khoan(self):
        a = AccountAllocator()
        a.register("9222", allow_video=False, max_slots=2)

        a.allocate(JobKind.IMAGE, "LO:A", now=0)
        a.allocate(JobKind.IMAGE, "LO:B", now=0)

        with self.assertRaises(NoAccountAvailable):
            a.allocate(JobKind.IMAGE, "LO:C", now=0)

    def test_tra_cho_thi_dung_lai_duoc(self):
        a = AccountAllocator()
        a.register("9222", allow_video=False, max_slots=1)
        lease = a.allocate(JobKind.IMAGE, "LO:A", now=0)

        a.release(lease.lease_id)

        self.assertIsNotNone(a.allocate(JobKind.IMAGE, "LO:B", now=0))

    def test_moi_lease_mang_dung_mot_tai_khoan_va_mot_cho(self):
        lease = self.a.allocate(JobKind.IMAGE, "LO:A", now=0)

        self.assertEqual(lease.account_id, "9222")
        self.assertIn(lease.slot, (0, 1))
        self.assertEqual(lease.work_key, "LO:A")

    def test_rai_deu_thay_vi_don_het_vao_may_dau(self):
        a = AccountAllocator()
        a.register("9222", allow_video=False, max_slots=2)
        a.register("9223", allow_video=False, max_slots=2)

        chon = [a.allocate(JobKind.IMAGE, f"LO:{i}", now=0).account_id
                for i in range(2)]

        self.assertEqual(sorted(chon), ["9222", "9223"])


if __name__ == "__main__":
    unittest.main()
