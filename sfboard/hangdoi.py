"""Cơ khí hàng đợi của SF Board — tách khỏi sfboard.py 2026-08-12.

Ở đây CHỈ có phần điều phối: xếp/nhấc việc, thứ tự ưu tiên, trạng thái job, cờ
huỷ. KHÔNG có Playwright, không đọc DOM, không biết ChatGPT hay
Grok là gì — nhờ vậy viết được phép thử cho nó mà không cần dựng cả board lẫn
Chrome, và ba lỗi hàng đợi gần đây đều thuộc loại lẽ ra một phép thử nhỏ đã bắt
được:

  · nhãn 'chờ' lệch hàng đợi thật (giao diện báo 22 việc, hàng đợi còn 3)
  · thứ tự xếp đọc TÊN SF nên trượt hậu tố chữ, mọi thẻ B rơi xuống cuối
  · người gác cứu việc lên sau khi user đã bấm "Dừng tất cả"

`sfboard.py` import thẳng các tên trong này. Dict/set/Queue là đối tượng dùng
chung nên `from hangdoi import JOBS` vẫn trỏ đúng một chỗ — không phải sửa 71
điểm gọi. Riêng số nguyên thì không chia sẻ được kiểu đó, nên thế hệ dừng gói
trong dict `GEN` (xem `dung_gen()`).
"""

from __future__ import annotations   # python3.9 của macOS: cần cho `dict | None`

import itertools
import queue
import re
import threading

# ───────────────────────────── hàng đợi ──────────────────────────────────────
IMG_QUEUE: "queue.PriorityQueue" = queue.PriorityQueue()   # việc vẽ ảnh
VID_QUEUE: "queue.PriorityQueue" = queue.PriorityQueue()   # việc dựng video
_HANG_SEQ = itertools.count()

# ───────────────────────────── trạng thái job ────────────────────────────────
# ident -> {"state": queued|running|done|error, "msg": str}
# ĐÂY LÀ DẤU VẾT ĐÃ GHI, KHÔNG PHẢI HÀNG ĐỢI. Hai thứ lệch nhau được: việc rơi
# khỏi hàng vẫn để lại nhãn 'chờ' nằm đó vĩnh viễn. Muốn biết hàng đợi thật thì
# gọi `y_trong_hang()`, đừng đọc JOBS.
class _Jobs(dict):
    """dict trạng thái việc — GỌI MÓC mỗi khi một việc chuyển sang lỗi.

    Trạng thái lỗi được đặt ở hơn hai chục nhánh rải khắp `sfboard.py`, phần lớn
    KHÔNG kèm log. Hộp 🐞 trên board và log Terminal vì thế thiếu đúng thứ hay
    hỏng nhất, còn thẻ trên board chỉ hiện một dòng cụt. Chặn ở đây là chặn một
    lần cho tất cả, khỏi phải nhớ log ở từng nhánh mới thêm sau này.

    Móc chỉ bắn khi NỘI DUNG lỗi đổi — vòng gác đặt lại cùng một trạng thái mỗi
    vài giây, ghi hết thì sổ lỗi ngập một dòng lặp.
    """

    khi_loi = None          # sfboard.py gắn hàm log vào đây lúc khởi động
    dan_nhan = None         # …và hàm dán nhãn tài khoản vào thông báo lỗi

    def __setitem__(self, k, v):
        try:
            if isinstance(v, dict) and v.get("state") == "error":
                # DÁN TÊN TÀI KHOẢN + CỔNG VÀO MỌI THÔNG BÁO LỖI.
                #
                # Lỗi Chrome ("ô soạn aria-hidden", "Page crashed") chỉ nói URL
                # chatgpt.com — mà bốn cửa sổ đều cùng URL đó, nên nhìn hộp 🐞
                # không biết phải đi chữa cửa sổ nào. Dán ở đây là bao trọn hơn
                # hai chục nhánh báo lỗi rải khắp sfboard.py, khỏi phải nhớ sửa
                # từng chỗ.
                if self.dan_nhan:
                    v = dict(v)
                    v["msg"] = self.dan_nhan(str(v.get("msg") or ""))
                if self.khi_loi and (self.get(k) or {}).get("msg") != v.get("msg"):
                    self.khi_loi(k, str(v.get("msg") or ""))
        except Exception:
            pass                # móc hỏng KHÔNG được làm hỏng việc đặt trạng thái
        super().__setitem__(k, v)


JOBS: dict[str, dict] = _Jobs()

DA_HUY: set[str] = set()          # ident user đã huỷ, thợ phải bỏ qua
HUY_LOCK = threading.Lock()

# SF id user CHỦ ĐỘNG bấm tạo (nút Tạo trên thẻ · Tạo ảnh đã chọn · Tạo lại hết).
# Cờ này quyết định `tay=True` ở tầng gửi, tức lô KHÔNG bị bộ lọc "đã có ảnh"
# gạt đi. Phải nhớ THEO SF chứ không giữ trong tuple hàng đợi: việc có thể rơi
# khỏi hàng (bug, restart, lỗi HTTP) rồi được người gác xếp lại — bản cũ xếp lại
# với `tay=False` cứng, nên đúng lô user vừa bấm tạo lại bị gạt sạch và nhảy
# thẳng sang "Đã xong · đã có ảnh — bỏ qua". Bắt tận tay 2026-08-14 với lô
# SF-S23-01..10.
TAY_SF: set[str] = set()

# SF id user bấm DỪNG RIÊNG (nút ■ trên từng việc trong ngăn kéo hàng đợi).
# ĐÁNH CỜ THEO SF ID, KHÔNG THEO IDENT LÔ: trạng thái được rải cho từng SF thành
# viên chứ không giữ khoá "LO:a,b,c", nên tra ident lô là tra vào chỗ trống.
DUNG_RIENG: set[str] = set()

# Số THẾ HỆ, tăng mỗi lần user bấm "Dừng tất cả". Gói trong dict vì số nguyên
# import sang module khác là bản sao, sửa một bên bên kia không thấy.
GEN = {"dung": 0}

CHO_RIENG: dict[int, list[str]] = {}   # port -> ident GIAO ĐÍCH DANH cho thợ đó
CR_LOCK = threading.Lock()

_HOAN: dict[str, int] = {}      # ident -> số lần đã thử lại (guardrail, người gác)

# Hàm đọc board, `sfboard.py` gắn vào lúc khởi động. Để ở đây thì module này
# không phải biết gì về Board, mà vẫn tra được thứ tự shot.
_doc_board = None
_moc_board = None


def gan_nguon_board(fn_doc, fn_moc=None) -> None:
    """Gắn hàm đọc sf-board.json (trả dict) và hàm lấy mốc đổi (mtime).

    `fn_moc` là thứ giữ cho cache dùng được. Thiếu nó thì mỗi lần xếp hàng lại
    đọc lại file 900KB — mà xếp hàng nằm trên đường nóng nhất của board."""
    global _doc_board, _moc_board
    _doc_board = fn_doc
    _moc_board = fn_moc


def dung_gen() -> int:
    return GEN["dung"]


def tang_dung_gen() -> int:
    GEN["dung"] += 1
    return GEN["dung"]


# ───────────────────────────── thứ tự ưu tiên ────────────────────────────────
# TRẦN CHO MÁY TỰ GOM — auto quét cả scene, và người gác cứu việc rơi khỏi hàng.
# KHÔNG áp cho bạn: bạn tích bao nhiêu thì gửi bấy nhiêu trong đúng một tin nhắn
# (bỏ cắt 2026-08-12). Trần này chỉ để máy đừng tự dồn cả scene vào một tin khi
# không có ai nhìn.
TRAN_MAY_TU_GOM = 10

_TT_CACHE: dict = {"khoa": None, "map": {}}
_TT_LOCK = threading.Lock()


def thu_tu_shot(khoa=None) -> dict:
    """SF id → vị trí của nó trong DÒNG PHIM, tức thứ tự shot ở tab video.

    Phải đọc `shots[]` chứ KHÔNG suy từ tên: tên SF không phải lúc nào cũng là
    số. Chèn thêm nhịp giữa chừng thì shot mang hậu tố chữ (`V-S3-B1`, `-B2`),
    và bản cũ khớp tên bằng regex `-(\\d+)` nên mọi thẻ B trượt khớp, rơi hết
    xuống mức 999999 — vẽ sau cùng dù trong phim B1 là shot MỞ cảnh.

    `khoa` là mốc để biết cache còn dùng được (sfboard truyền mtime của file).
    """
    if _doc_board is None:
        return {}
    if khoa is None and _moc_board is not None:
        try:
            khoa = _moc_board()
        except Exception:
            khoa = None
    with _TT_LOCK:
        if khoa is not None and _TT_CACHE["khoa"] == khoa:
            return _TT_CACHE["map"]
    try:
        d = _doc_board()
    except Exception:
        return {}
    m = {}
    for si, s in enumerate(d.get("scenes", [])):
        for i, sh in enumerate(s.get("shots", [])):
            v = si * 1000 + i
            # VÀO SỔ CẢ HAI TÊN: id của SHOT và id của SF nó dùng.
            #
            # Bản cũ chỉ vào sổ SF id, nên việc VIDEO (ident là shot id) luôn tra
            # trượt và rơi xuống phép đoán theo tên ở `uu_tien` — mà phép đoán đó
            # đọc `-(\d+)` nên mọi shot mang hậu tố chữ (`V-S1-B1`, `V-S3-B2`)
            # trượt nốt và nhận mức 999999. Đo trên ALTAR 2026-08-14: 62/438 shot
            # dính, trong đó có shot MỞ CẢNH của gần như mọi scene — chúng bị đẩy
            # xuống cuối hàng đợi video, dựng sau cùng.
            # Hai không gian tên không giẫm nhau (`V-…` với `SF-…`/`REF_…`).
            sid = (sh.get("id") or "").strip()
            if sid and sid not in m:
                m[sid] = v
            sf = (sh.get("sf") or "").strip()
            if sf and sf not in m:
                m[sf] = v
    with _TT_LOCK:
        _TT_CACHE["khoa"] = khoa
        _TT_CACHE["map"] = m
    return m


def uu_tien(ident: str, tt: dict | None = None) -> int:
    """Vị trí sớm nhất trong dòng phim của các SF trong ident. Nhỏ = làm trước."""
    ids = ident[3:].split(",") if ident.startswith("LO:") else [ident]
    if tt is None:
        tt = thu_tu_shot()

    def _n(sf: str) -> int:
        sf = sf.strip()
        if sf.startswith("SF-M-") or sf.startswith("REF_"):
            return 0            # ref nhân vật và thẻ master luôn đi trước
        if sf in tt:
            return tt[sf] + 1   # +1 để không giẫm lên mức 0 ở trên
        # Không shot nào dùng SF này (thẻ mồ côi, hoặc board chưa chia shot):
        # quay về cách đọc tên như cũ để thứ tự vẫn hợp lý thay vì ngẫu nhiên.
        m = re.match(r"(?:SF|V)-S(\d+)-(\d+)", sf)
        if m:
            return int(m.group(1)) * 1000 + int(m.group(2))
        return 999999
    return min((_n(x) for x in ids), default=999999)


# ───────────────────────────── xếp / nhấc ────────────────────────────────────
def xep(Q, item: tuple) -> None:
    """Xếp một việc vào PriorityQueue theo ưu tiên (thứ tự shot trong phim)."""
    Q.put((uu_tien(item[1]), next(_HANG_SEQ), item))


def lay(Q, **kw):
    """Nhấc item ra khỏi PriorityQueue, gỡ bỏ khoá ưu tiên."""
    return Q.get(**kw)[2]


def y_trong_hang(Q) -> set:
    """Tập ident ĐANG THẬT SỰ nằm trong hàng đợi.

    PriorityQueue không có API duyệt, nhưng `.queue` là list nội bộ và đọc nó
    dưới `mutex` là an toàn — rẻ hơn nhiều so với nhấc hết ra rồi xếp lại."""
    with Q.mutex:
        return {it[2][1] for it in list(Q.queue) if len(it) > 2 and len(it[2]) > 1}


def thu_tu_hang(Q) -> list[str]:
    """Ident theo ĐÚNG thứ tự sẽ được nhấc — cái đầu danh sách chạy trước.

    Sắp theo chính khoá của PriorityQueue `(ưu tiên, số thứ tự xếp)`: cùng mức
    ưu tiên thì ai xếp trước đi trước. KHÔNG đọc thẳng `Q.queue` theo thứ tự
    list: đó là mảng heap, phần tử đầu đúng là cái nhỏ nhất nhưng phần còn lại
    KHÔNG hề có thứ tự — hiện thẳng ra là bảng nói dối người đọc.
    """
    with Q.mutex:
        it = [x for x in list(Q.queue) if len(x) > 2 and len(x[2]) > 1]
    return [x[2][1] for x in sorted(it, key=lambda x: (x[0], x[1]))]


def vet_hang(Q) -> list:
    """Nhấc sạch hàng đợi, trả về danh sách item đã lấy ra."""
    ra = []
    try:
        while True:
            ra.append(Q.get_nowait()[2])
            Q.task_done()
    except queue.Empty:
        pass
    return ra


# ───────────────────────────── trạng thái & huỷ ──────────────────────────────
def dat_job(ident: str, st: dict) -> None:
    """Ghi trạng thái job. Với ident lô ("LO:a,b,c") thì RẢI cho TỪNG SF thành viên.

    Không rải thì lô lỗi xong các SF vẫn kẹt ở 'running' vĩnh viễn — giao diện
    quay vòng mà chẳng có gì đang chạy."""
    JOBS[ident] = st
    if ident.startswith("LO:"):
        for i in ident[3:].split(","):
            if i:
                JOBS[i] = dict(st)


def bo_co_huy(*idents: str) -> None:
    """Xoá cờ huỷ của các ident này — USER VỪA CHỦ ĐỘNG BẤM TẠO.

    Ý định mới phải thắng cờ cũ. `DA_HUY` chỉ được dọn khi đúng thợ nhấc đúng
    ident, nên cờ của việc bị huỷ lúc hàng đợi đang bị vét sẽ nằm lại vĩnh viễn.
    Mà ident là danh sách SF user tích — tích lại đúng nhóm đó là ident TRÙNG y
    hệt, và job mới bị ghi "đã huỷ" ngay dù chẳng có lỗi gì."""
    with HUY_LOCK:
        for i in idents:
            DA_HUY.discard(i)


def bi_huy(ident: str, an: bool = True) -> bool:
    """Việc này đã bị huỷ chưa? Kiểm NGAY TRƯỚC khi bắt tay làm.

    Chỉ vứt hàng đợi là không đủ: thợ nhấc việc ra khỏi hàng trong vòng 2 giây,
    nên phần lớn cú bấm Huỷ sẽ trượt nếu không có chốt này.

    `an=False` là ĐỌC MÀ KHÔNG ĂN CỜ. Cờ vốn bị xoá ngay khi đọc (để lần chạy
    sau của cùng ident không bị chặn oan), nhưng có HAI nơi cùng đọc: thợ lúc
    nhấc việc, và bộ hẹn giờ xếp-lại-sau-khi-lỗi. Ai đọc trước thì người kia
    thấy sạch — nên một việc vừa bị thợ bỏ vì đã huỷ vẫn được bộ hẹn giờ xếp lại
    vài giây sau, và nó chạy thật. Bộ hẹn giờ phải gọi với `an=False`.
    """
    with HUY_LOCK:
        if ident in DA_HUY:
            if an:
                DA_HUY.discard(ident)
            return True
    return False
