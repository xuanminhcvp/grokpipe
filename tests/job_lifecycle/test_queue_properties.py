"""Property-based: chuỗi xếp/nhấc/huỷ NGẪU NHIÊN trên hàng đợi thật.

Test ví dụ chỉ đi vài đường đã nghĩ ra trước. Hypothesis sinh chuỗi thao tác
ngẫu nhiên rồi tự thu nhỏ về ca nhỏ nhất còn hỏng — đúng loại lưới cần cho
retry/cancel/re-enqueue, nơi lỗi chỉ lộ ra ở một thứ tự thao tác hiếm gặp.

Không đụng vào 5 `xfail` đang khoá: đây là lưới ĐỘC LẬP, không phải bản sửa.
"""

import queue

from hypothesis import HealthCheck, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule

from helpers import load_hangdoi


IDENTS = st.sampled_from(
    [
        "SF-S1-01",
        "SF-S1-02",
        "SF-S2-01",
        "SF-S10-07",
        "V-S1-01",
        "V-S2-03",
        "LO:SF-S1-01,SF-S1-02",
        "the-cu-khong-theo-mau",
    ]
)


class QueueCancelMachine(RuleBasedStateMachine):
    """Mô hình song song: một list Python phản chiếu PriorityQueue thật."""

    def __init__(self):
        super().__init__()
        self.m = load_hangdoi()
        self.Q = queue.PriorityQueue()
        self.model = []          # [(ưu tiên, số thứ tự xếp, ident)]
        self.seq = 0
        self.m.DA_HUY.clear()
        self.m.JOBS.clear()

    def teardown(self):
        self.m.DA_HUY.clear()
        self.m.JOBS.clear()

    # ---- thao tác ---------------------------------------------------------

    @rule(ident=IDENTS)
    def xep(self, ident):
        self.m.xep(self.Q, ("img", ident, 0, False))
        self.model.append((self.m.uu_tien(ident), self.seq, ident))
        self.seq += 1

    @precondition(lambda self: self.model)
    @rule()
    def lay(self):
        expected = min(self.model)
        item = self.m.lay(self.Q)
        self.model.remove(expected)
        assert item[1] == expected[2], "nhấc sai thứ tự ưu tiên"

    @rule()
    def vet_hang(self):
        lay_ra = self.m.vet_hang(self.Q)
        assert {it[1] for it in lay_ra} == {row[2] for row in self.model}
        self.model.clear()

    @rule(ident=IDENTS)
    def danh_dau_huy(self, ident):
        with self.m.HUY_LOCK:
            self.m.DA_HUY.add(ident)

    @rule(ident=IDENTS)
    def doc_co_huy_khong_an(self, ident):
        with self.m.HUY_LOCK:
            co_co = ident in self.m.DA_HUY
        assert self.m.bi_huy(ident, an=False) is co_co
        with self.m.HUY_LOCK:
            assert (ident in self.m.DA_HUY) is co_co, "đọc mà không ăn phải giữ nguyên cờ"

    @rule(ident=IDENTS)
    def doc_co_huy_co_an(self, ident):
        with self.m.HUY_LOCK:
            co_co = ident in self.m.DA_HUY
        assert self.m.bi_huy(ident) is co_co
        assert self.m.bi_huy(ident) is False, "cờ huỷ chỉ được ăn đúng một lần"

    @rule(ident=IDENTS)
    def user_bam_tao_lai(self, ident):
        self.m.bo_co_huy(ident)
        with self.m.HUY_LOCK:
            assert ident not in self.m.DA_HUY

    @rule(ident=IDENTS, state=st.sampled_from(["queued", "running", "error", "done"]))
    def ghi_trang_thai(self, ident, state):
        self.m.dat_job(ident, {"state": state})
        assert self.m.JOBS[ident]["state"] == state
        if ident.startswith("LO:"):
            for thanh_vien in ident[3:].split(","):
                assert self.m.JOBS[thanh_vien]["state"] == state, "lô phải rải cho thành viên"

    # ---- bất biến ---------------------------------------------------------

    @invariant()
    def hang_doi_khop_mo_hinh(self):
        assert self.m.y_trong_hang(self.Q) == {row[2] for row in self.model}
        assert self.Q.qsize() == len(self.model)

    @invariant()
    def thu_tu_hien_ra_dung_thu_tu_se_nhac(self):
        assert self.m.thu_tu_hang(self.Q) == [row[2] for row in sorted(self.model)]

    # KHÔNG có bất biến "lô và thành viên luôn cùng trạng thái": `dat_job` chỉ
    # rải TẠI LÚC GHI. Sau đó một SF chạy riêng được phép lệch khỏi lô — đó là
    # hành vi đúng, Hypothesis đã dựng đúng chuỗi đó ngay lần chạy đầu.


QueueCancelTest = QueueCancelMachine.TestCase
QueueCancelTest.settings = settings(
    max_examples=60,
    stateful_step_count=25,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
