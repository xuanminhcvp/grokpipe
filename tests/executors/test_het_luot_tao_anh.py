"""Hết lượt TẠO ẢNH phải xoay tài khoản ngay, không thử lại trên chính nó.

Log ALTAR 2026-08-15, tài khoản gpt-3 từ 14:36 đến 14:45: 7 lô × 2 lượt = 14 lần
submit, cả 14 lần ChatGPT trả về đúng một câu —

    You've hit the Plus plan limit for image generations requests.
    You can create more images when the limit resets in 26 minutes.

— và board vẫn giao tiếp lô mới cho nó, rồi dán lên thẻ câu "Thường là guardrail
chặn: sửa prompt". Lời khuyên đó SAI: prompt không việc gì, tài khoản hết quota.

Vì sao lọt: `_RE_HET_UPLOAD` chỉ bắt hết lượt ĐÍNH TỆP ("upload limit"), còn câu
này nói "image generations"; và `_RE_GIO_MO` chỉ đọc giờ tuyệt đối ("until 3:45
PM") chứ không đọc giờ tương đối ("resets in 26 minutes"). Trượt cả hai lớp nên
nó rơi xuống nhánh chung "không trả ảnh nào" → lô tự gửi lại 2 lần TRÊN CÙNG tài
khoản (đường `_HOAN`), thay vì ném lỗi để `_worker` xoay sang tài khoản khác.

Board đã bỏ hẳn cơ chế treo tài khoản (`sfboard.py`, user chốt 2026-08-14: mọi
lỗi đều xoay, không treo ai ngoài vòng). Nên bản vá KHÔNG dựng lại chuyện treo —
nó chỉ đưa ca này vào đúng đường xoay đang có sẵn.
"""

import pytest

from grokpipe.executors import image_chatgpt as I


QUOTA_EN = ("You've hit the Plus plan limit for image generations requests. "
            "You can create more images when the limit resets in 26 minutes.")
QUOTA_VI = ("You've hit the Plus plan limit for image generations requests. You can "
            "create more images when the limit resets in 25 minutes. Hiện tại mình "
            "không thể gọi công cụ tạo ảnh, nên chưa thể tạo 6 ảnh này ngay bây giờ.")
QUOTA_GIO = ("You've hit the Plus plan limit for image generations requests. "
             "You can create more images when the limit resets in 2 hours.")


# ---- nhận diện ------------------------------------------------------------

@pytest.mark.parametrize("txt, cho", [
    (QUOTA_EN, "+26"),
    (QUOTA_VI, "+25"),
    (QUOTA_GIO, "+120"),
])
def test_doc_duoc_han_muc_va_gio_mo_lai(txt, cho):
    assert I.het_luot_tao_anh(txt) == cho


def test_thay_chan_ma_khong_ro_gio_thi_van_bao_la_chan():
    """Không đọc được giờ KHÔNG được biến thành 'không có chặn' — đó là cách cũ
    làm mất dấu cả 14 lượt."""
    assert I.het_luot_tao_anh(
        "You've hit the Plus plan limit for image generations requests.") == ""


@pytest.mark.parametrize("txt", [
    "",
    "Ảnh 1 · Ảnh 2 · Ảnh 3",
    "Đã tách thành đúng 4 ảnh riêng biệt 16:9, theo đúng thứ tự",
    "We're so sorry, but the image we created may violate our content policies.",
    "You've added all available file uploads until 3:45 PM",
])
def test_khong_bat_nham_cac_cau_khac(txt):
    """Guardrail nội dung và hết lượt UPLOAD là hai chuyện khác — bắt nhầm thì
    xoay tài khoản trong khi bệnh nằm ở prompt hoặc ở hạn mức đính tệp."""
    assert I.het_luot_tao_anh(txt) is None


# ---- đường xoay -----------------------------------------------------------

def test_chan_neu_het_anh_nem_loi_de_worker_xoay():
    """Phải NÉM, không phải trả về. Trả về là rơi xuống nhánh 'không trả ảnh
    nào' → lô tự gửi lại trên chính tài khoản vừa hết quota."""
    s = I.ChatGPTSession.__new__(I.ChatGPTSession)
    s.logger = __import__("logging").getLogger("test")

    with pytest.raises(Exception) as e:
        s._chan_neu_het_anh(QUOTA_EN)

    loi = str(e.value)
    assert "hết lượt tạo ảnh" in loi.lower()
    assert "[NGHI-DEN:+26]" in loi, "board đọc nhãn này để ghi log giờ mở lại"
    assert "prompt" not in loi.lower(), "đừng đổ cho prompt — prompt không việc gì"


def test_chan_neu_het_anh_im_lang_khi_khong_phai_quota():
    s = I.ChatGPTSession.__new__(I.ChatGPTSession)
    s.logger = __import__("logging").getLogger("test")

    assert s._chan_neu_het_anh("Ảnh 1 · Ảnh 2") is None
