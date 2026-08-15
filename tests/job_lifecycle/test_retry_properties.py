"""Property-based: KHÔNG ĐƯỢC CÓ JOB MA, dù thao tác đi theo thứ tự nào.

Job ma = ident mang nhãn `running` mà chẳng có gì đỡ phía sau: không thợ nào
giữ, không nằm trong hàng đợi, cũng không có hẹn giờ xếp lại nào chờ bắn. Board
hiện "đang chạy" vĩnh viễn cho việc sẽ không bao giờ chạy, và cả hai đường tạo
đều bỏ qua ident đang `running` nên bấm Tạo lại cũng im lặng.

Đó đúng là thứ đã xảy ra tối 2026-08-14 với 14 thẻ scene 6. Test ví dụ bắt được
MỘT đường đi tới đó; Hypothesis sinh chuỗi thao tác ngẫu nhiên để bắt cả họ.

Mọi bước đều gọi mã production: handler HTTP thật cho dừng/huỷ, `_ban_xep_lai`
thật cho bộ hẹn giờ, hàng đợi thật. Không có bản mô phỏng nào để mà lệch.
"""

import queue

from hypothesis import HealthCheck, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule

from helpers import FakeBoard, load_sfboard, make_handler, reset_legacy_state


# CHỈ HAI IDENT. Bất biến nói về vòng đời của MỘT ident; thêm ident chỉ pha
# loãng phép tìm kiếm — đo tay: 4 ident bắt được bug 3/5 lần ở ngân sách 200×40,
# 2 ident bắt 5/5 ở cùng ngân sách. Hai cái vẫn đủ để hai việc giẫm lên nhau.
SF = st.sampled_from(["SF-S1-01", "SF-S1-02"])
KIND = st.sampled_from(["img", "vid"])


class KhongCoJobMaMachine(RuleBasedStateMachine):
    def __init__(self):
        super().__init__()
        self.m = load_sfboard()
        reset_legacy_state(self.m)
        self.board_cu, self.m.BOARD = self.m.BOARD, FakeBoard()
        self.acc_cu, self.m.ACCOUNTS = self.m.ACCOUNTS, []   # rỗng = không đụng Chrome
        self.m.AUTO.clear()
        self.giu = set()      # ident đang có một thợ cầm
        self.hen = []         # hẹn giờ đã đặt, chưa bắn: (kind, item, gen)

    def teardown(self):
        self.m.BOARD = self.board_cu
        self.m.ACCOUNTS = self.acc_cu
        reset_legacy_state(self.m)
        self.m.AUTO.clear()

    def goi(self, path):
        h = make_handler(self.m, path)
        h.do_POST()
        return h.captured

    # ───────────────────────────── thao tác ──────────────────────────────

    @rule(sf=SF, kind=KIND)
    def user_tao_viec(self, sf, kind):
        Q = self.m.IMG_QUEUE if kind == "img" else self.m.VID_QUEUE
        self.m._dat_job(sf, {"state": "queued", "msg": "chờ"})
        self.m.bo_co_huy(sf)
        self.m._xep(Q, (kind, sf, 0, True))

    @precondition(lambda self: self.m.IMG_QUEUE.qsize() or self.m.VID_QUEUE.qsize())
    @rule(kind=KIND)
    def tho_nhac_viec(self, kind):
        Q = self.m.IMG_QUEUE if kind == "img" else self.m.VID_QUEUE
        try:
            item = self.m._lay(Q, block=False)
        except queue.Empty:
            return
        ident = item[1]
        if self.m._bi_huy(ident):          # thợ soi cờ NGAY TRƯỚC khi bắt tay làm
            self.m._dat_job(ident, {"state": "error", "msg": "đã huỷ"})
            return
        self.giu.add(ident)
        self.m._dat_job(ident, {"state": "running", "msg": "đang chạy"})

    @precondition(lambda self: self.giu)
    @rule()
    def tho_xong_viec(self):
        ident = sorted(self.giu)[0]
        self.giu.discard(ident)
        self.m._dat_job(ident, {"state": "done", "msg": "xong"})

    @precondition(lambda self: self.giu)
    @rule(kind=KIND)
    def tho_gap_loi(self, kind):
        """Đúng nhánh `except` của `_worker`: dán nhãn chạy rồi hẹn xếp lại."""
        ident = sorted(self.giu)[0]
        self.giu.discard(ident)
        self.m._dat_job(ident, {"state": "running", "msg": "lỗi → thử lại sau 20s"})
        self.hen.append((kind, (kind, ident, 1, False), self.m.dung_gen()))

    @precondition(lambda self: self.hen)
    @rule()
    def bo_hen_gio_ban(self):
        """Tới giờ — gọi ĐÚNG thân bộ hẹn giờ của production."""
        kind, item, gen = self.hen.pop(0)
        self.m._ban_xep_lai(kind, item, gen)

    @rule()
    def user_huy_hang_cho(self):
        self.goi("/api/huy")

    @rule(kind=KIND)
    def user_dung_tat_ca(self, kind):
        """Đóng Chrome GÂY RA lỗi cho mọi thợ đang cầm việc — không phải trùng hợp.

        Thợ đang nằm trong lượt vẽ thì lệnh CDP kế tiếp hỏng ngay khi cửa sổ
        đóng, nên nó chạy nhánh `except` ngay sau cú dừng: dán nhãn 'đang chạy ·
        thử lại sau 20s' rồi hẹn giờ. Đúng thứ tự đó đẻ ra 14 job ma tối
        2026-08-14. Mô hình cho hai việc này rời nhau là tự bịt đường tới bug —
        và đo tay cho thấy nó thật sự bịt: 4/5 lần không tìm ra."""
        self.goi("/api/dung-het?dong_chrome=0")
        for ident in sorted(self.giu):
            self.m._dat_job(ident, {"state": "running", "msg": "lỗi → thử lại sau 20s"})
            self.hen.append((kind, (kind, ident, 1, False), self.m.dung_gen()))
        self.giu.clear()

    @rule(sf=SF)
    def user_bam_tao_lai(self, sf):
        self.goi(f"/api/generate?sf={sf}")

    # ───────────────────────────── bất biến ──────────────────────────────

    @invariant()
    def khong_co_job_ma(self):
        trong_hang = self.m._y_trong_hang(self.m.IMG_QUEUE) | self.m._y_trong_hang(
            self.m.VID_QUEUE
        )
        dang_hen = {item[1] for _, item, _ in self.hen}
        co_do = self.giu | trong_hang | dang_hen
        # Thành viên của một lô đang được đỡ thì cũng được đỡ theo lô.
        for ident in list(co_do):
            if ident.startswith("LO:"):
                co_do.update(x for x in ident[3:].split(",") if x)

        ma = [
            ident
            for ident, v in list(self.m.JOBS.items())
            if v.get("state") == "running" and ident not in co_do
        ]
        assert not ma, (
            f"job ma: {ma} mang nhãn 'running' mà không thợ nào giữ, không nằm "
            f"trong hàng đợi, cũng không có hẹn giờ nào chờ bắn"
        )

    @invariant()
    def viec_da_huy_khong_con_nam_trong_hang(self):
        """Cờ huỷ đã đánh thì việc không được vẫn xếp hàng chờ tới lượt chạy."""
        with self.m.HUY_LOCK:
            da_huy = set(self.m.DA_HUY)
        trong_hang = self.m._y_trong_hang(self.m.IMG_QUEUE) | self.m._y_trong_hang(
            self.m.VID_QUEUE
        )
        van_cho = da_huy & trong_hang
        # Nằm trong hàng vẫn được, MIỄN LÀ thợ soi cờ lúc nhấc — điều đó có test
        # riêng. Ở đây chỉ chặn ca vô lý: vừa bị huỷ vừa mang nhãn đang chạy.
        for ident in van_cho:
            assert self.m.JOBS.get(ident, {}).get("state") != "running", (
                f"{ident} vừa mang cờ huỷ, vừa nằm trong hàng, vừa gắn nhãn đang chạy"
            )


KhongCoJobMaTest = KhongCoJobMaMachine.TestCase
KhongCoJobMaTest.settings = settings(
    max_examples=100,
    stateful_step_count=30,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)
