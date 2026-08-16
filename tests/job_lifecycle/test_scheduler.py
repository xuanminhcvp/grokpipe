"""Scheduler giữ lịch theo `execution_id` và cho thuê việc bằng lease atomic.

Hàng đợi hiện tại mang TÊN ASSET, nên hai câu hỏi cơ bản không trả lời được:
"thành viên này thuộc lô vật lý nào" (huỷ một ảnh trong lô đang chờ) và "việc
này đã có ai nhận chưa" (khoảng giữa lúc nhấc và lúc kịp ghi nhãn `running`).

Module này thuần dữ liệu: không hàng đợi thật, không Chrome, không thời gian
thực — `now` luôn được truyền vào để test không phải ngủ.
"""

import threading
import unittest

from sfboard.jobs.models import ExecutionState, JobKind
from sfboard.jobs.scheduler import LeaseNotFound, Scheduler, StaleLease


class SchedulerTest(unittest.TestCase):
    def setUp(self):
        self.s = Scheduler()

    def xep(self, ident, members=None, *, kind=JobKind.IMAGE, priority=0,
            not_before=0.0, scope_key=None):
        return self.s.schedule(
            kind=kind,
            queue_ident=ident,
            member_keys=tuple(members if members is not None else [ident]),
            priority=priority,
            not_before=not_before,
            scope_key=scope_key,
        )

    # ───────────────────────────── lịch ──────────────────────────────

    def test_xep_tra_ve_execution_id_rieng(self):
        a = self.xep("LO:A,B", ["A", "B"])
        b = self.xep("V-S1-01")

        self.assertNotEqual(a.execution_id, b.execution_id)
        self.assertEqual(a.state, ExecutionState.READY)
        self.assertEqual(a.member_keys, ("A", "B"))

    def test_xep_trung_ident_khong_nhan_ban_execution(self):
        """Giao lại cùng một lô không được sinh execution thứ hai.

        Hai execution cùng ident nghĩa là hai lượt render cho cùng một tin —
        đúng thứ tầng producer vừa chặn ở Phase 3, không được mở lại ở đây."""
        a = self.xep("LO:A,B", ["A", "B"])
        b = self.xep("LO:A,B", ["A", "B"])

        self.assertEqual(a.execution_id, b.execution_id)
        self.assertEqual(len(self.s.ready(now=0)), 1)

    def test_xep_lai_duoc_sau_khi_da_xong(self):
        self.xep("LO:A", ["A"])
        lease = self.s.lease_next(JobKind.IMAGE, now=0, ttl=30)
        self.s.finish(lease.lease_id)

        moi = self.xep("LO:A", ["A"])

        self.assertEqual(moi.state, ExecutionState.READY)
        self.assertEqual(len(self.s.ready(now=0)), 1)

    def test_scope_active_chan_nhan_ban_du_queue_ident_khac(self):
        cu = self.xep("LO:A", ["A"], scope_key="asset:A")

        lap = self.xep("LO:A-rerun", ["A"], scope_key="asset:A")

        self.assertEqual(lap.execution_id, cu.execution_id)
        self.assertEqual(len(self.s.ready(now=0)), 1)

    def test_scope_terminal_cho_execution_rerun_identity_moi(self):
        cu = self.xep("LO:A", ["A"], scope_key="asset:A")
        lease = self.s.lease_next(JobKind.IMAGE, now=0, ttl=30)
        self.s.finish(lease.lease_id)

        moi = self.xep("LO:A-rerun", ["A"], scope_key="asset:A")

        self.assertNotEqual(moi.execution_id, cu.execution_id)

    # ───────────────────────────── lease ─────────────────────────────

    def test_hai_tho_khong_the_nhan_cung_mot_execution(self):
        self.xep("LO:A", ["A"])
        nhan, rao = [], threading.Barrier(2)

        def gianh():
            rao.wait()
            nhan.append(self.s.lease_next(JobKind.IMAGE, now=0, ttl=30))

        luong = [threading.Thread(target=gianh) for _ in range(2)]
        for t in luong:
            t.start()
        for t in luong:
            t.join(5)

        self.assertEqual(sum(1 for x in nhan if x is not None), 1)
        self.assertEqual(sum(1 for x in nhan if x is None), 1)

    def test_nhan_viec_la_MOT_thao_tac_khong_con_cua_so_queued(self):
        """Nhấc xong là LEASED ngay, không có nhịp trung gian nào còn READY."""
        self.xep("LO:A", ["A"])

        lease = self.s.lease_next(JobKind.IMAGE, now=0, ttl=30)

        self.assertEqual(self.s.get(lease.execution_id).state,
                         ExecutionState.LEASED)
        self.assertEqual(self.s.ready(now=0), ())

    def test_lease_het_han_thi_viec_quay_lai_hang(self):
        self.xep("LO:A", ["A"])
        self.s.lease_next(JobKind.IMAGE, now=0, ttl=30)

        self.assertIsNone(self.s.lease_next(JobKind.IMAGE, now=10, ttl=30))
        het = self.s.expire_leases(now=31)

        self.assertEqual(len(het), 1)
        self.assertIsNotNone(self.s.lease_next(JobKind.IMAGE, now=31, ttl=30))

    def test_heartbeat_giu_lease_song(self):
        self.xep("LO:A", ["A"])
        lease = self.s.lease_next(JobKind.IMAGE, now=0, ttl=30)

        self.s.heartbeat(lease.lease_id, now=20)

        self.assertEqual(self.s.expire_leases(now=31), ())

    def test_lease_cu_khong_ket_thuc_duoc_luot_moi(self):
        """Token cũ phải chết hẳn — nếu không, thợ zombie đóng nhầm lượt mới."""
        self.xep("LO:A", ["A"])
        cu = self.s.lease_next(JobKind.IMAGE, now=0, ttl=30)
        self.s.expire_leases(now=31)
        moi = self.s.lease_next(JobKind.IMAGE, now=31, ttl=30)

        with self.assertRaises(StaleLease):
            self.s.finish(cu.lease_id)
        self.s.finish(moi.lease_id)

    def test_finish_lease_khong_ton_tai_bi_tu_choi(self):
        with self.assertRaises(LeaseNotFound):
            self.s.finish("khong-co-that")

    def test_release_dat_lai_not_before(self):
        self.xep("LO:A", ["A"])
        lease = self.s.lease_next(JobKind.IMAGE, now=0, ttl=30)

        self.s.release(lease.lease_id, not_before=90)

        self.assertEqual(self.s.ready(now=60), ())
        self.assertEqual(len(self.s.ready(now=90)), 1)

    # ─────────────────────────── thứ tự ──────────────────────────────

    def test_uu_tien_nho_chay_truoc_cung_muc_thi_ai_xep_truoc_di_truoc(self):
        self.xep("LO:C", ["C"], priority=9)
        self.xep("LO:A", ["A"], priority=1)
        self.xep("LO:B", ["B"], priority=1)

        ra = [self.s.lease_next(JobKind.IMAGE, now=0, ttl=30).queue_ident
              for _ in range(3)]

        self.assertEqual(ra, ["LO:A", "LO:B", "LO:C"])

    def test_khong_cho_thue_viec_chua_toi_gio(self):
        self.xep("LO:A", ["A"], not_before=50)

        self.assertIsNone(self.s.lease_next(JobKind.IMAGE, now=10, ttl=30))
        self.assertIsNotNone(self.s.lease_next(JobKind.IMAGE, now=50, ttl=30))

    def test_moi_loai_viec_mot_hang_rieng(self):
        self.xep("LO:A", ["A"])
        self.xep("V-S1-01", kind=JobKind.VIDEO)

        anh = self.s.lease_next(JobKind.IMAGE, now=0, ttl=30)
        vid = self.s.lease_next(JobKind.VIDEO, now=0, ttl=30)

        self.assertEqual(anh.queue_ident, "LO:A")
        self.assertEqual(vid.queue_ident, "V-S1-01")

    # ─────────────────────── tra cứu thành viên ──────────────────────

    def test_tra_ra_lo_vat_ly_tu_mot_thanh_vien(self):
        """Đây là câu hỏi mà `JOBS` không trả lời được lúc lô mới xếp."""
        exe = self.xep("LO:A,B", ["A", "B"])

        self.assertEqual(self.s.execution_for_member("B").execution_id,
                         exe.execution_id)
        self.assertIsNone(self.s.execution_for_member("Z"))

    def test_huy_theo_thanh_vien_go_ca_lo_khoi_hang(self):
        self.xep("LO:A,B", ["A", "B"])

        bo = self.s.cancel_member("A")

        self.assertEqual([x.queue_ident for x in bo], ["LO:A,B"])
        self.assertEqual(self.s.ready(now=0), ())
        self.assertIsNone(self.s.lease_next(JobKind.IMAGE, now=0, ttl=30))

    def test_huy_thanh_vien_cua_lo_dang_chay_khong_go_ngam(self):
        """Lô đang chạy thì không cắt được — phải nói ra, không im lặng bỏ."""
        self.xep("LO:A,B", ["A", "B"])
        self.s.lease_next(JobKind.IMAGE, now=0, ttl=30)

        bo = self.s.cancel_member("A")

        self.assertEqual(bo, ())
        self.assertEqual(self.s.get_by_ident("LO:A,B").state,
                         ExecutionState.LEASED)


if __name__ == "__main__":
    unittest.main()
