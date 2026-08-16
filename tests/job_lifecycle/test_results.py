"""Kết quả về muộn KHÔNG được đè lên thứ user đã chọn.

Ca thật: một lượt render treo, user sốt ruột tự dán ảnh khác vào thẻ, rồi lượt
cũ tỉnh dậy và ghi đè. Không có lỗi nào in ra — về mặt kỹ thuật lượt đó "thành
công". `CLAUDE.md` ghi rõ: ảnh user tự dán là bản chuẩn tuyệt đối.

Nhưng cũng KHÔNG vứt kết quả đó đi: nó đã tốn lượt thật, giữ lại làm bản để so.
"""

import unittest

from sfboard.jobs.models import JobState
from sfboard.jobs.results import CommitDecision, ResultCommit, ResultFact


class ResultCommitTest(unittest.TestCase):
    def setUp(self):
        self.c = ResultCommit()
        self.c.open_lease("lease-1")

    def fact(self, **kw):
        base = dict(work_key="SF-S1-01", lease_id="lease-1",
                    outputs=("anh.png",), job_state=JobState.RUNNING,
                    replace_current=True, started_at=100.0)
        base.update(kw)
        return ResultFact(**base)

    def test_ket_qua_binh_thuong_thi_ghi_de_ban_dang_dung(self):
        v = self.c.commit(self.fact())

        self.assertEqual(v.decision, CommitDecision.ACCEPT)
        self.assertTrue(v.ghi_de)
        self.assertEqual(v.outputs, ("anh.png",))

    def test_user_da_tu_thay_anh_thi_ket_qua_cu_chi_lam_ban_de_so(self):
        self.c.note_user_mutation("SF-S1-01", now=150.0)

        v = self.c.commit(self.fact(started_at=100.0))

        self.assertEqual(v.decision, CommitDecision.STORE_AS_VERSION)
        self.assertEqual(v.reason_code, "user_mutation_wins")
        self.assertFalse(v.ghi_de)
        self.assertEqual(v.outputs, ("anh.png",), "không được vứt lượt đã tốn")

    def test_user_sua_TRUOC_khi_luot_nay_bat_dau_thi_khong_can(self):
        self.c.note_user_mutation("SF-S1-01", now=50.0)

        v = self.c.commit(self.fact(started_at=100.0))

        self.assertEqual(v.decision, CommitDecision.ACCEPT)

    def test_tho_zombie_khong_ghi_duoc_nua(self):
        """Lease đã thu hồi = việc đã giao cho người khác."""
        self.c.revoke_lease("lease-1")

        v = self.c.commit(self.fact())

        self.assertEqual(v.decision, CommitDecision.REJECT)
        self.assertEqual(v.reason_code, "lease.revoked")

    def test_lease_la_khoa_chinh_khong_phai_ten_the(self):
        v = self.c.commit(self.fact(lease_id="lease-bia"))

        self.assertEqual(v.decision, CommitDecision.REJECT)

    def test_job_da_ket_thuc_thi_khong_nhan_them(self):
        for state in (JobState.CANCELLED, JobState.FAILED, JobState.COMPLETED):
            with self.subTest(state=state):
                v = self.c.commit(self.fact(job_state=state))

                self.assertEqual(v.decision, CommitDecision.REJECT)
                self.assertEqual(v.reason_code, "job.terminal")

    def test_ban_chay_them_de_so_thi_khong_de_len_ban_dang_dung(self):
        v = self.c.commit(self.fact(replace_current=False))

        self.assertEqual(v.decision, CommitDecision.STORE_AS_VERSION)
        self.assertEqual(v.reason_code, "extra_copy")

    def test_khong_co_output_thi_khong_phai_thanh_cong(self):
        v = self.c.commit(self.fact(outputs=()))

        self.assertEqual(v.decision, CommitDecision.REJECT)

    def test_dong_lease_xong_thi_ket_qua_toi_sau_bi_loai(self):
        self.c.close_lease("lease-1")

        self.assertEqual(self.c.commit(self.fact()).decision,
                         CommitDecision.REJECT)

    def test_chan_doan_dem_dung(self):
        self.c.note_user_mutation("SF-S1-02", now=10.0)

        so = self.c.diagnostics()

        self.assertEqual(so["lease_dang_mo"], 1)
        self.assertEqual(so["the_user_da_sua"], 1)


if __name__ == "__main__":
    unittest.main()
