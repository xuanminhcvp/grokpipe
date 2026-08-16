"""Người gác chỉ được BÁO, không được sửa.

Người gác cũ vừa dò vừa vá: thấy việc "mồ côi" là tự xếp lại — và đúng cơ chế đó
đã xếp lại một lô đang chạy dở, làm nó render hai lượt. Ở đây phép kiểm là hàm
thuần: vào ba danh sách, ra danh sách lệch. Không có đường nào để nó mutate.
"""

import unittest

from sfboard.jobs.monitor import Finding, InvariantMonitor, Severity


class InvariantMonitorTest(unittest.TestCase):
    def setUp(self):
        self.m = InvariantMonitor()

    def ma(self, findings):
        return sorted(f.code for f in findings)

    def test_moi_thu_khop_thi_khong_bao_gi(self):
        ra = self.m.check(
            queue_idents=["LO:A,B"],
            scheduled_idents=["LO:A,B"],
            job_labels={"A": "queued", "B": "queued"},
        )

        self.assertEqual(ra, ())

    def test_viec_trong_hang_ma_lich_khong_biet(self):
        ra = self.m.check(["LO:A"], [], {"A": "queued"})

        self.assertEqual(self.ma(ra), ["lich.thieu"])

    def test_lich_con_cho_ma_hang_mat_viec_la_loi_nang(self):
        ra = self.m.check([], ["LO:A"], {})

        self.assertEqual(self.ma(ra), ["hang.thieu"])
        self.assertEqual(ra[0].severity, Severity.ERROR)

    def test_nhan_cho_mo_coi_bi_bao(self):
        """Nhãn 'chờ' cho thẻ không nằm trong việc nào = giao diện nói dối."""
        ra = self.m.check(["LO:A"], ["LO:A"], {"A": "queued", "Z": "queued"})

        self.assertEqual([f.subject for f in ra], ["Z"])
        self.assertEqual(ra[0].code, "nhan.mo_coi")

    def test_nhan_dang_chay_ma_khong_co_lease(self):
        ra = self.m.check([], [], {"A": "running"})

        self.assertEqual(self.ma(ra), ["chay.khong_lease"])

    def test_dang_chay_co_lease_thi_khong_bao(self):
        ra = self.m.check([], [], {"A": "running", "B": "running"},
                          leased_idents=["LO:A,B"])

        self.assertEqual(ra, ())

    def test_viec_dang_chay_khong_bi_coi_la_roi_khoi_hang(self):
        """Đây chính là chỗ người gác cũ đoán sai rồi xếp lại việc đang chạy."""
        ra = self.m.check([], ["LO:A"], {"A": "running"}, leased_idents=["LO:A"])

        self.assertEqual(ra, ())

    def test_khoa_lo_khong_bi_dem_nhu_mot_the(self):
        ra = self.m.check(["LO:A,B"], ["LO:A,B"],
                          {"LO:A,B": "queued", "A": "queued", "B": "queued"})

        self.assertEqual(ra, ())

    def test_tom_tat_dem_theo_ma(self):
        ra = self.m.check(["LO:A"], ["LO:B"], {"Z": "queued"})

        tom = self.m.summary(ra)

        self.assertEqual(tom["tong"], 3)
        self.assertEqual(tom["nang_nhat"], "error")
        self.assertEqual(set(tom["theo_ma"]),
                         {"lich.thieu", "hang.thieu", "nhan.mo_coi"})

    def test_khong_co_lech_thi_tom_tat_rong(self):
        self.assertEqual(self.m.summary(())["tong"], 0)

    def test_finding_la_bat_bien_khong_sua_duoc(self):
        f = Finding("x", Severity.INFO, "A", "chi tiết")

        with self.assertRaises(Exception):
            f.code = "y"


if __name__ == "__main__":
    unittest.main()
