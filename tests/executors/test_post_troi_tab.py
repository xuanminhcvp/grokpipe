"""Clip nhận về phải là clip của LƯỢT NÀY, không phải clip cũ trên trang post.

Bug thật, board ALTAR 2026-08-15 — user tả: "video tạo nhảy vào chỗ link video đã
tạo rồi xong đứng yên ở đấy, một lúc sau board tải đúng cái video ở link đó".

Đường đi: board phân biệt clip mới với clip cũ bằng cách đóng dấu `data-gp-cu`
lên mọi thẻ `<video>` trước khi submit (`dom_grok.py:JS_DONG_DAU_VIDEO_CU`). Dấu
đó là thuộc tính DOM — **tab điều hướng sang trang khác là DOM dựng lại, dấu mất
sạch**. Tab submit từ `/imagine` (trang trống: `before` rỗng, không có gì để đóng
dấu) rồi trôi sang một trang post cũ đang có 10 video: cả 10 đều `cu=false`, đều
không nằm trong `before`, đều đủ `dur` → board nhận `new[0]`, tải về, ghi đè lên
video của shot đang chạy. Im lặng tuyệt đối.

Không có phép kiểm URL nào sau submit: comment ở `video_grok.py` giải thích vì
sao đã bỏ (Grok render TẠI CHỖ khi tab đứng sẵn ở post, bắt phải nhảy post mới
là báo lỗi oan và mất trắng credit). Nên phép kiểm mới phải phân biệt được
"render tại chỗ" với "trôi sang post cũ" — không được chặn cái thứ nhất.
"""

import logging

import pytest

from grokpipe.executors import video_grok as V


IMAGINE = "https://grok.com/imagine"
POST_A = "https://grok.com/imagine/post/7c34a484-89db-4ad9-9693-58b2d16fe4af?con"
POST_B = "https://grok.com/imagine/post/aaaaaaaa-1111-2222-3333-444444444444"


@pytest.fixture(autouse=True)
def so_sach():
    V.quen_het_post()
    yield
    V.quen_het_post()


# ---- đọc ID post ---------------------------------------------------------

def test_doc_duoc_id_post_ke_ca_khi_co_query():
    """URL trong log thật có đuôi `?con` — cắt sai là hai lần cùng post ra hai ID."""
    assert V.id_post(POST_A) == "7c34a484-89db-4ad9-9693-58b2d16fe4af"
    assert V.id_post(POST_A.split("?")[0]) == V.id_post(POST_A)


def test_trang_soan_khong_co_id_post():
    assert V.id_post(IMAGINE) == ""
    assert V.id_post("") == ""


# ---- quyết định nhận clip ------------------------------------------------

def test_url_khong_doi_thi_nhan(   ):
    """Không điều hướng = dấu DOM còn nguyên, cứ tin dấu như cũ."""
    ok, _ = V.nhan_duoc_clip(IMAGINE, IMAGINE)
    assert ok is True


def test_render_tai_cho_tren_post_cu_van_nhan():
    """Ca mà comment trong mã đã dặn: đứng sẵn ở post thì Grok render TẠI CHỖ.

    Post ấy nằm sẵn trong sổ (board đã lấy clip ở đó lượt trước) nhưng URL KHÔNG
    đổi, nên dấu DOM còn nguyên và vẫn phân biệt được. Chặn ca này là báo lỗi oan
    trong khi clip đã render xong — mất trắng credit.
    """
    V.ghi_so_post(V.id_post(POST_A))

    ok, _ = V.nhan_duoc_clip(POST_A, POST_A)

    assert ok is True


def test_post_moi_thi_nhan_va_vao_so():
    ok, _ = V.nhan_duoc_clip(IMAGINE, POST_B)

    assert ok is True
    assert V.id_post(POST_B) in V.so_post_da_lay()


def test_troi_sang_post_da_lay_clip_thi_TU_CHOI():
    """Đúng ca của user: submit từ trang soạn, tỉnh dậy ở post cũ."""
    V.ghi_so_post(V.id_post(POST_A))

    ok, vi = V.nhan_duoc_clip(IMAGINE, POST_A)

    assert ok is False
    assert "7c34a484" in vi

def test_troi_sang_post_la_chua_tung_lay_thi_van_nhan():
    """User chốt: không phân định được thì vẫn tải như hiện nay.

    Sổ nằm trong bộ nhớ phiên nên post từ phiên TRƯỚC không có trong đó. Đây là
    lỗ hổng đã biết và đã báo, không phải sót.
    """
    ok, _ = V.nhan_duoc_clip(IMAGINE, POST_A)

    assert ok is True


# ---- một nhịp soi trang --------------------------------------------------

class TrangGia:
    """Phải phân biệt được từng đoạn JS: `_soi_clip_moi` gọi JS_VIDEO_THAT, còn
    câu báo lỗi của nó gọi JS_CHAN_DOAN. Trả chung một thứ cho cả hai là test tự
    dựng ra một ca không có thật."""

    def __init__(self, url, videos, chan_doan=None):
        self.url = url
        self._videos = videos
        self._chan_doan = chan_doan if chan_doan is not None else {"url": url}

    def evaluate(self, js):
        return self._videos if js is V.JS_VIDEO_THAT else self._chan_doan


def phien(url, videos, chan_doan=None):
    """GrokSession trần, không CDP — chỉ đủ để gọi `_soi_clip_moi`."""
    s = V.GrokSession.__new__(V.GrokSession)
    s.page = TrangGia(url, videos, chan_doan)
    s.logger = logging.getLogger("test")
    return s


def clip(src, cu=False, dur=10.0):
    return {"src": src, "dur": dur, "w": 800, "cu": cu}


def test_chua_co_clip_thi_tra_None():
    s = phien(IMAGINE, [])
    assert s._soi_clip_moi(set(), IMAGINE) is None


def test_clip_tren_post_moi_thi_nhan_ca_ban_thua():
    s = phien(POST_B, [clip("https://a/1.mp4"), clip("https://a/2.mp4")])

    chinh, thua = s._soi_clip_moi(set(), IMAGINE)

    assert chinh == "https://a/1.mp4"
    assert thua == ["https://a/2.mp4"]


def test_clip_tren_post_da_lay_thi_NEM_LOI_chu_khong_tra_ve():
    """Đúng ca của user. Trả về là board tải và ghi đè video sai lên shot."""
    V.ghi_so_post(V.id_post(POST_A))
    s = phien(POST_A, [clip("https://a/cu.mp4")])

    with pytest.raises(Exception) as e:
        s._soi_clip_moi(set(), IMAGINE)

    assert "không nhận clip" in str(e.value).lower()
    assert "7c34a484" in str(e.value)


def test_clip_mang_dau_cu_van_bi_bo_qua_nhu_truoc():
    """Phép cũ phải còn nguyên: dấu DOM vẫn là chốt thứ nhất."""
    s = phien(POST_B, [clip("https://a/cu.mp4", cu=True)])
    assert s._soi_clip_moi(set(), POST_B) is None


def test_chan_doan_hong_khong_duoc_lam_hong_loi():
    """Hàm chẩn đoán chỉ để ĐÍNH KÈM — nổ ở đó là nuốt mất lỗi thật.

    Bản cũ chỉ bọc `evaluate`, không bọc phần định dạng, nên trang trả về thứ
    không phải dict là `d.get(...)` nổ AttributeError ngay giữa lúc dựng câu báo
    lỗi. Nơi gọi bọc `except Exception` (để lượt render chập chờn không giết
    job) sẽ nuốt luôn — job quay tới hết 10 phút, log không một dòng.
    """
    V.ghi_so_post(V.id_post(POST_A))
    s = phien(POST_A, [clip("https://a/cu.mp4")], chan_doan=["không phải dict"])

    with pytest.raises(V.C.ExecutorError) as e:
        s._soi_clip_moi(set(), IMAGINE)

    assert "7c34a484" in str(e.value)
    assert "không đọc được hiện trạng" in str(e.value)
