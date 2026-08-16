"""Restart board KHÔNG được làm bốc hơi hàng chờ.

Hôm nay hàng đợi nằm trong RAM, nên `CLAUDE.md` phải dặn "kiểm /api/jobs trước
khi khởi động lại board" — một lời dặn như thế là dấu hiệu của lỗ hổng chưa vá.

Hai luật ở đây:

  · việc CÒN CHỜ phải quay lại đúng thứ tự cũ;
  · việc ĐANG CHẠY lúc board chết thì **không tự chạy lại** — với video, lượt cũ
    có thể đã bấm gửi rồi, tự gửi lại là trừ credit lần nữa.
"""

import tempfile
import threading
import unittest
from pathlib import Path

from sfboard.jobs.persistence import (
    DurableExecution, ScheduleConflict, ScheduleVersionConflict,
    SqliteSchedule, build_recovery_plan,
)


def exe(ident, *, kind="img", state="ready", priority=0, members=None,
        not_before=0.0, forced=None, execution_id=None, scope_key=None,
        version=0):
    return DurableExecution(
        execution_id=execution_id or f"exe-{kind}-{ident}",
        kind=kind, queue_ident=ident,
        member_keys=tuple(members or [ident]), priority=priority,
        not_before=not_before, state=state, forced_account=forced,
        scope_key=scope_key or ident, version=version,
    )


class SqliteScheduleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "lich.db")
        self.s = SqliteSchedule(self.path)

    def tearDown(self):
        self.s.close()
        self.tmp.cleanup()

    def mo_lai(self):
        """Đóng và mở lại — mô phỏng đúng cú restart board."""
        self.s.close()
        self.s = SqliteSchedule(self.path)
        return self.s

    # ───────────────────────── sống qua restart ───────────────────────

    def test_hang_cho_con_nguyen_sau_khi_mo_lai(self):
        self.s.upsert(exe("LO:A,B", members=["A", "B"]))
        self.s.upsert(exe("V-S1-01", kind="vid"))

        con = self.mo_lai().pending()

        self.assertEqual({e.queue_ident for e in con}, {"LO:A,B", "V-S1-01"})
        self.assertEqual(con[0].member_keys, ("A", "B"))

    def test_giu_dung_thu_tu_uu_tien(self):
        self.s.upsert(exe("LO:C", priority=9), now=1)
        self.s.upsert(exe("LO:A", priority=1), now=2)
        self.s.upsert(exe("LO:B", priority=1), now=3)

        ra = [e.queue_ident for e in self.mo_lai().pending()]

        self.assertEqual(ra, ["LO:A", "LO:B", "LO:C"])

    def test_giu_ca_moc_not_before_va_rang_buoc_ep(self):
        self.s.upsert(exe("LO:A", not_before=1234.5, forced="9225"))

        e = self.mo_lai().pending()[0]

        self.assertEqual(e.not_before, 1234.5)
        self.assertEqual(e.forced_account, "9225")

    def test_viec_dang_chay_khong_nam_trong_hang_cho(self):
        self.s.upsert(exe("LO:A", state="leased"))

        self.assertEqual(self.mo_lai().pending(), ())
        self.assertEqual(len(self.s.in_flight()), 1)

    def test_xong_thi_go_khoi_lich(self):
        self.s.upsert(exe("LO:A"))
        self.s.remove("img", "LO:A")

        self.assertEqual(self.mo_lai().pending(), ())

    def test_xep_lai_cung_ident_khong_nhan_ban_thanh_hai_dong(self):
        self.s.upsert(exe("LO:A"))
        self.s.upsert(exe("LO:A", priority=5))

        con = self.mo_lai().pending()

        self.assertEqual(len(con), 1)
        self.assertEqual(con[0].priority, 5)

    def test_rerun_cung_queue_ident_giu_execution_identity_moi(self):
        """Compatibility label không được biến thành identity bền vững."""
        self.s.upsert(exe(
            "SF-A", execution_id="exec-old", state="finished"))
        self.s.upsert(exe(
            "SF-A", execution_id="exec-rerun", state="ready"))

        rows = self.s.all_executions()

        self.assertEqual(
            {(row.execution_id, row.state) for row in rows},
            {("exec-old", "finished"), ("exec-rerun", "ready")},
        )

    def test_hai_execution_active_cung_scope_bi_chan(self):
        self.s.insert(exe(
            "LO:A", execution_id="exec-1", scope_key="asset:A"))

        with self.assertRaises(ScheduleConflict):
            self.s.insert(exe(
                "LO:A-rerun", execution_id="exec-2", scope_key="asset:A"))

    def test_compare_and_set_tu_choi_version_cu(self):
        self.s.insert(exe("LO:A", execution_id="exec-1"))
        updated = self.s.compare_and_set(
            "exec-1", expected_version=0, state="leased",
            lease_id="lease-1", lease_expires_at=100.0)

        self.assertEqual(updated.version, 1)
        with self.assertRaises(ScheduleVersionConflict):
            self.s.compare_and_set(
                "exec-1", expected_version=0, state="finished")

    def test_hai_thread_cas_cung_version_chi_mot_ben_thang(self):
        self.s.insert(exe("LO:A", execution_id="exec-1"))
        barrier = threading.Barrier(2)
        outcomes = []

        def update(state):
            barrier.wait()
            try:
                self.s.compare_and_set(
                    "exec-1", expected_version=0, state=state)
                outcomes.append("ok")
            except ScheduleVersionConflict:
                outcomes.append("stale")

        threads = [
            threading.Thread(target=update, args=("leased",)),
            threading.Thread(target=update, args=("finished",)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)

        self.assertEqual(sorted(outcomes), ["ok", "stale"])

    def test_anh_va_video_cung_ten_khong_dam_nhau(self):
        self.s.upsert(exe("X", kind="img"))
        self.s.upsert(exe("X", kind="vid"))

        self.assertEqual(len(self.mo_lai().pending()), 2)

    # ───────────────────── khoá ý định qua restart ────────────────────

    def test_khoa_y_dinh_song_qua_restart(self):
        self.assertTrue(self.s.remember_intent("click-1", "vantay-A"))

        s2 = self.mo_lai()

        self.assertTrue(s2.remember_intent("click-1", "vantay-A"),
                        "gửi lại đúng ý định cũ phải được nhận là replay")
        self.assertFalse(s2.remember_intent("click-1", "vantay-KHAC"),
                         "mượn khoá cũ cho nội dung khác phải bị từ chối")

    def test_danh_dau_da_giao(self):
        self.s.remember_intent("k", "vt")
        self.s.mark_intent_delivered("k")

        self.assertTrue(self.mo_lai().intent_delivered("k"))
        self.assertIsNone(self.s.intent_delivered("chua-tung-co"))

    # ─────────────────────────── kế hoạch hồi phục ────────────────────

    def test_ke_hoach_tach_viec_cho_va_viec_dang_do(self):
        self.s.upsert(exe("LO:A"))
        self.s.upsert(exe("V-S1-01", kind="vid", state="leased"))

        ke = build_recovery_plan(self.mo_lai())

        self.assertEqual([e.queue_ident for e in ke.requeue], ["LO:A"])
        self.assertEqual([e.queue_ident for e in ke.needs_attention], ["V-S1-01"])

    def test_ke_hoach_khong_tu_chay_lai_video_dang_do(self):
        """Đây là chốt chống trừ credit hai lần sau một cú restart."""
        self.s.upsert(exe("V-S1-01", kind="vid", state="leased"))

        ke = build_recovery_plan(self.mo_lai())

        self.assertEqual(ke.requeue, ())

    def test_ke_hoach_mang_theo_rang_buoc_ep_tai_khoan(self):
        self.s.upsert(exe("LO:A", forced="9225"))

        ke = build_recovery_plan(self.mo_lai())

        self.assertEqual(ke.forced, (("LO:A", "9225"),))

    def test_db_moi_thi_ke_hoach_rong_chu_khong_no(self):
        ke = build_recovery_plan(self.s)

        self.assertEqual((ke.requeue, ke.needs_attention, ke.forced), ((), (), ()))


if __name__ == "__main__":
    unittest.main()
