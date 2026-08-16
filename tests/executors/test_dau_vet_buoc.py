"""Ghi lại TỪNG BƯỚC của một lượt, để lỗi nói được nó chết ở đâu.

Sổ lỗi hiện chỉ ghi KẾT CỤC ("không trả ảnh nào", "hết 600s chờ render"), không
ghi HÀNH TRÌNH. Nên khi user nói "có bug video", đọc sổ vẫn không biết nó chết ở
bước nào: chưa về được trang soạn? không bấm được mode Video? chip thời lượng
không chốt? upload rơi? submit không ăn? hay render xong mà tải hỏng?

Mỗi bước là một dòng gọn; toàn bộ dấu vết đính vào sự kiện lỗi. Không ghi khi
mọi thứ trôi chảy — dấu vết chỉ có giá trị lúc mổ xẻ một lượt đã hỏng.
"""

import pytest

from grokpipe.executors.common import DauVetBuoc


def test_ghi_theo_dung_thu_tu():
    d = DauVetBuoc(dong_ho=iter([0.0, 0.5, 0.5, 2.0]).__next__)
    d.xong("ve_trang")
    d.xong("mode_video")

    assert [b["buoc"] for b in d.lay()] == ["ve_trang", "mode_video"]
    assert all(b["ok"] for b in d.lay())


def test_do_duoc_thoi_gian_tung_buoc():
    """Bước nào ngốn thời gian cũng là manh mối — 'chờ render 600s' khác hẳn
    'chưa về được trang soạn 600s'."""
    d = DauVetBuoc(dong_ho=iter([10.0, 13.5]).__next__)

    d.xong("cho_render")

    assert d.lay()[0]["giay"] == 3.5


def test_buoc_hong_mang_ly_do():
    d = DauVetBuoc(dong_ho=iter([0.0, 1.0]).__next__)

    d.hong("chip_thoi_luong", "không chốt được '10s' sau 8s — đang chọn ''")

    b = d.lay()[0]
    assert b["ok"] is False
    assert "10s" in b["chi_tiet"]


def test_moi_luot_bat_dau_bang_dau_vet_trong():
    """Tab dùng lại cho việc kế tiếp — sót dấu vết lượt trước là chẩn đoán sai
    lượt này."""
    d = DauVetBuoc(dong_ho=iter([0.0, 1.0, 5.0, 6.0]).__next__)
    d.xong("ve_trang")

    d.bat_dau()
    d.xong("mode_video")

    assert [b["buoc"] for b in d.lay()] == ["mode_video"]


def test_cat_bot_khi_qua_dai():
    """Vòng chờ render soi mỗi 5 giây suốt 10 phút — không được để nó phình sổ."""
    d = DauVetBuoc(gioi_han=5)
    for i in range(20):
        d.xong(f"b{i}")

    ra = d.lay()
    assert len(ra) == 5
    assert ra[-1]["buoc"] == "b19", "giữ khúc CUỐI — chỗ gần lỗi nhất"


def test_chi_tiet_bi_cat_ngan():
    d = DauVetBuoc()
    d.hong("submit", "x" * 500)

    assert len(d.lay()[0]["chi_tiet"]) <= 200


def test_ghi_hong_khong_bao_gio_lam_hong_luot():
    """Bộ ghi dấu vết là thứ phụ trợ — nó nổ thì cả lượt render chết oan."""
    d = DauVetBuoc(dong_ho=lambda: (_ for _ in ()).throw(RuntimeError("đồng hồ hỏng")))

    d.xong("ve_trang")          # không được ném
    d.hong("submit", "gì đó")   # cũng không

    assert isinstance(d.lay(), list)


def test_xong_va_hong_cung_chu_ky():
    """Nơi gọi CHỌN HÀM rồi mới truyền tham số — lệch chữ ký là nổ nửa số nhánh.

    Ca thật 2026-08-15: `(vet.xong if ok else vet.hong)("nhan_anh", "về 4/4")`.
    `hong` nhận 2 tham số, `xong` chỉ nhận 1 → mọi lô về ĐỦ ảnh chết TypeError,
    11 tài khoản bị xoay tắt trong 7 phút. Test đường lỗi không thấy gì vì nhánh
    nổ chính là nhánh THÀNH CÔNG.
    """
    import inspect

    d = DauVetBuoc()
    assert (inspect.signature(d.xong).parameters.keys()
            == inspect.signature(d.hong).parameters.keys())

    for ham in (d.xong, d.hong):
        ham("b")                 # gọi kiểu một tham số
        ham("b", "chi tiết")     # …và kiểu hai tham số


def test_moi_cho_goi_vet_trong_executor_deu_dung_so_tham_so():
    """Quét THẬT các lời gọi trong executor — chỗ tôi đã sai một lần.

    Kiểm bằng cây cú pháp thay vì tin vào mắt: hai file executor có gần 30 lời
    gọi `self.vet.…`, và chỉ cần một chỗ lệch là hỏng đúng nhánh chạy tốt.
    """
    import ast
    import inspect
    from pathlib import Path

    goc = Path(__file__).resolve().parents[2] / "grokpipe/grokpipe/executors"
    toi_da = {ten: len(inspect.signature(getattr(DauVetBuoc, ten)).parameters) - 1
              for ten in ("xong", "hong", "bat_dau", "lay")}

    sai = []
    for f in ("image_chatgpt.py", "video_grok.py"):
        cay = ast.parse((goc / f).read_text(encoding="utf-8"))
        for n in ast.walk(cay):
            if not isinstance(n, ast.Call):
                continue
            fn = n.func
            # bắt cả `self.vet.xong(...)` lẫn `(a if c else b)(...)`
            tens = []
            if isinstance(fn, ast.Attribute) and getattr(fn.value, "attr", "") == "vet":
                tens = [fn.attr]
            elif isinstance(fn, ast.IfExp):
                tens = [x.attr for x in (fn.body, fn.orelse)
                        if isinstance(x, ast.Attribute) and getattr(x.value, "attr", "") == "vet"]
            for ten in tens:
                if ten in toi_da and len(n.args) > toi_da[ten]:
                    sai.append(f"{f}:{n.lineno} {ten}() nhận tối đa {toi_da[ten]}, "
                               f"truyền {len(n.args)}")
    assert sai == [], "lời gọi sai số tham số: " + "; ".join(sai)
