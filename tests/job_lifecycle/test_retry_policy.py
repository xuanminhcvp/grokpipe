"""Ma trận quyết định thử lại — một nơi, một ngân sách.

Luật đắt nhất ở đây: **không chắc đã tốn credit thì KHÔNG tự gửi lại**. Mất kết
nối sau khi đã bấm gửi cho Grok mà máy tự thử lại là trừ credit lần nữa cho đúng
shot có thể đã dựng xong — và không ai biết vì log chỉ thấy "lỗi rồi thử lại".
"""

import unittest

from sfboard.jobs.errors import ErrorClass, ErrorFact
from sfboard.jobs.models import AttemptPhase, JobKind, JobState
from sfboard.jobs.retry import (
    AttemptHistory, RetryAction, RetryPolicy, TRAN_GUI,
)


def loi(lop, phase=AttemptPhase.PREPARING, msg="hỏng"):
    return ErrorFact(lop, msg, phase)


class RetryPolicyTest(unittest.TestCase):
    def setUp(self):
        self.p = RetryPolicy()

    def quyet(self, lop, phase=AttemptPhase.PREPARING, kind=JobKind.IMAGE,
              attempts=0, submitted=0, ca_lo=0):
        return self.p.decide(
            loi(lop, phase),
            AttemptHistory(attempts, submitted, ca_lo),
            kind,
        )

    # ─────────────────────── không tự đốt credit ──────────────────────

    def test_khong_biet_ket_qua_thi_hoi_user_chu_khong_gui_lai(self):
        d = self.quyet(ErrorClass.UNKNOWN_OUTCOME, AttemptPhase.SUBMITTED,
                       JobKind.VIDEO)

        self.assertEqual(d.action, RetryAction.NEEDS_ATTENTION)
        self.assertEqual(d.to_state, JobState.NEEDS_ATTENTION)

    def test_mat_phien_SAU_khi_bam_gui_cung_la_khong_biet(self):
        """Rớt mạng lúc đang tải kết quả về — lượt kia có thể đã chạy xong."""
        d = self.quyet(ErrorClass.SESSION_TRANSIENT, AttemptPhase.DOWNLOADING,
                       JobKind.VIDEO)

        self.assertEqual(d.action, RetryAction.NEEDS_ATTENTION)

    def test_mat_tai_khoan_sau_submit_khong_duoc_gui_lai(self):
        d = self.quyet(ErrorClass.ACCOUNT_LOST, AttemptPhase.WAITING_PROVIDER,
                       JobKind.VIDEO)

        self.assertEqual(d.action, RetryAction.NEEDS_ATTENTION)

    def test_mat_phien_TRUOC_khi_bam_gui_thi_thu_lai_binh_thuong(self):
        d = self.quyet(ErrorClass.SESSION_TRANSIENT, AttemptPhase.ATTACHING)

        self.assertEqual(d.action, RetryAction.RETRY)
        self.assertEqual(d.delay, 0.0, "nối lại phiên thì thử ngay, khỏi chờ")
        self.assertFalse(d.rotate_account, "chưa cần bỏ chat cũ ngay lần đầu")

    # ─────────────────────────── lỗi dữ liệu ──────────────────────────

    def test_loi_du_lieu_dung_han_va_khong_phat_tai_khoan(self):
        d = self.quyet(ErrorClass.VALIDATION)

        self.assertEqual(d.action, RetryAction.FAIL)
        self.assertFalse(d.cooldown_account)
        self.assertFalse(d.rotate_account)

    def test_loi_vinh_vien_khong_thu_lai(self):
        self.assertEqual(self.quyet(ErrorClass.PERMANENT).action, RetryAction.FAIL)

    def test_user_huy_khong_phai_that_bai(self):
        d = self.quyet(ErrorClass.CANCELLED)

        self.assertEqual(d.action, RetryAction.CANCEL)
        self.assertEqual(d.to_state, JobState.CANCELLED)

    # ──────────────────────────── ngân sách ───────────────────────────

    def test_dem_theo_so_lan_DA_BAM_GUI_chu_khong_theo_so_loi(self):
        """Mười lần rớt mạng trước khi gửi không tốn gì — không được tính."""
        d = self.quyet(ErrorClass.PROVIDER_TRANSIENT, attempts=10, submitted=0)

        self.assertEqual(d.action, RetryAction.RETRY)

    def test_het_tran_gui_thi_dung(self):
        for kind, tran in TRAN_GUI.items():
            with self.subTest(kind=kind):
                d = self.quyet(ErrorClass.PROVIDER_TRANSIENT, kind=kind,
                               attempts=tran, submitted=tran)

                self.assertEqual(d.action, RetryAction.FAIL)
                self.assertIn(str(tran), d.reason_code)

    def test_video_co_tran_chat_hon_anh(self):
        self.assertLess(TRAN_GUI[JobKind.VIDEO], TRAN_GUI[JobKind.IMAGE])

    def test_chay_lai_nguyen_lo_toi_da_hai_lan(self):
        d = self.quyet(ErrorClass.PROVIDER_TRANSIENT, ca_lo=2)

        self.assertEqual(d.action, RetryAction.FAIL)
        self.assertEqual(d.reason_code, "budget.whole_execution")

    def test_partial_batch_dung_cung_tran_hai_lan_va_khong_xoay_account(self):
        first = self.p.decide_partial(
            AttemptHistory(attempts=1, submitted_attempts=1), JobKind.IMAGE)
        exhausted = self.p.decide_partial(
            AttemptHistory(
                attempts=3, submitted_attempts=3,
                whole_execution_retries=2,
            ),
            JobKind.IMAGE,
        )

        self.assertEqual(first.action, RetryAction.RETRY)
        self.assertEqual(first.reason_code, "batch.partial")
        self.assertFalse(first.rotate_account)
        self.assertEqual(exhausted.action, RetryAction.FAIL)
        self.assertEqual(exhausted.reason_code, "budget.whole_execution")

    # ───────────────────────────── giãn cách ──────────────────────────

    def test_gian_dan_roi_cham_tran(self):
        cho = [self.quyet(ErrorClass.PROVIDER_TRANSIENT, attempts=i).delay
               for i in range(1, 12)]

        self.assertEqual(cho, sorted(cho), "giãn cách phải không giảm")
        self.assertLessEqual(max(cho), 180.0)
        self.assertGreater(cho[0], 0)

    # ──────────────────────── phạt đúng đối tượng ─────────────────────

    def test_het_han_muc_thi_cho_TAI_KHOAN_nghi_chu_khong_bo_viec(self):
        d = self.quyet(ErrorClass.QUOTA_RATE_LIMIT)

        self.assertEqual(d.action, RetryAction.RETRY)
        self.assertTrue(d.cooldown_account)
        self.assertTrue(d.rotate_account)

    def test_moi_quyet_dinh_deu_co_ly_do_doc_duoc(self):
        for lop in ErrorClass:
            with self.subTest(lop=lop):
                phase = (AttemptPhase.SUBMITTED
                         if lop is ErrorClass.UNKNOWN_OUTCOME
                         else AttemptPhase.PREPARING)
                self.assertTrue(self.quyet(lop, phase).reason_code)

    def test_quyet_dinh_thuan_goi_lai_van_the(self):
        mot = self.quyet(ErrorClass.PROVIDER_TRANSIENT, attempts=3)
        hai = self.quyet(ErrorClass.PROVIDER_TRANSIENT, attempts=3)

        self.assertEqual(mot, hai)


if __name__ == "__main__":
    unittest.main()
