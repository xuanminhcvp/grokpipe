"""Chốt bất biến của người gác: cờ huỷ mà việc vẫn 'đang chạy'.

`/api/huy` và `/api/huy-viec` đều từ chối huỷ việc đang chạy, nên trạng thái này
không có đường hợp lệ nào sinh ra — thấy nó tức là thợ đã không soi được cờ.
"""

import pytest

from helpers import load_sfboard


@pytest.fixture(scope="module")
def board():
    return load_sfboard()


@pytest.fixture
def bo_nho():
    return {}, set()


def test_khong_co_gi_sai_thi_khong_bao(board, bo_nho):
    thay_tu, da_bao = bo_nho
    jobs = {"SF-S1-01": {"state": "running"}, "SF-S1-02": {"state": "queued"}}

    assert board._soat_co_huy(set(), jobs, thay_tu, da_bao) == []
    assert thay_tu == {}


@pytest.mark.parametrize("state", ["queued", "error", "done", None])
def test_co_huy_nhung_khong_chay_thi_khong_bao(board, bo_nho, state):
    thay_tu, da_bao = bo_nho
    jobs = {"SF-S1-01": {"state": state} if state else {}}

    assert board._soat_co_huy({"SF-S1-01"}, jobs, thay_tu, da_bao, bay_gio=10_000) == []


def test_lan_dau_thay_thi_im_lang_vi_con_trong_cua_so_dua(board, bo_nho):
    thay_tu, da_bao = bo_nho
    jobs = {"SF-S1-01": {"state": "running"}}

    assert board._soat_co_huy({"SF-S1-01"}, jobs, thay_tu, da_bao, bay_gio=1_000) == []
    assert thay_tu == {"SF-S1-01": 1_000}
    assert da_bao == set()


def test_giu_qua_nguong_thi_bao_dung_mot_lan(board, bo_nho):
    thay_tu, da_bao = bo_nho
    jobs = {"SF-S1-01": {"state": "running"}}
    huy = {"SF-S1-01"}
    board._soat_co_huy(huy, jobs, thay_tu, da_bao, bay_gio=1_000)

    vua_nguong = 1_000 + board.CHO_HUY_TOI_DA
    assert board._soat_co_huy(huy, jobs, thay_tu, da_bao, bay_gio=vua_nguong - 1) == []
    assert board._soat_co_huy(huy, jobs, thay_tu, da_bao, bay_gio=vua_nguong) == [
        ("SF-S1-01", board.CHO_HUY_TOI_DA)
    ]
    # các vòng sau KHÔNG báo lại — người gác chạy mỗi 30s, báo lại là spam
    assert board._soat_co_huy(huy, jobs, thay_tu, da_bao, bay_gio=vua_nguong + 600) == []


def test_tinh_trang_tu_het_thi_quen_va_cho_bao_lai_lan_sau(board, bo_nho):
    thay_tu, da_bao = bo_nho
    jobs = {"SF-S1-01": {"state": "running"}}
    huy = {"SF-S1-01"}
    board._soat_co_huy(huy, jobs, thay_tu, da_bao, bay_gio=0)
    board._soat_co_huy(huy, jobs, thay_tu, da_bao, bay_gio=board.CHO_HUY_TOI_DA)
    assert da_bao == {"SF-S1-01"}

    jobs["SF-S1-01"] = {"state": "done"}                 # việc đã xong
    assert board._soat_co_huy(huy, jobs, thay_tu, da_bao, bay_gio=500) == []
    assert thay_tu == {} and da_bao == set()

    jobs["SF-S1-01"] = {"state": "running"}              # tái diễn
    board._soat_co_huy(huy, jobs, thay_tu, da_bao, bay_gio=1_000)
    assert board._soat_co_huy(
        huy, jobs, thay_tu, da_bao, bay_gio=1_000 + board.CHO_HUY_TOI_DA
    ) == [("SF-S1-01", board.CHO_HUY_TOI_DA)]


def test_nhieu_ident_bao_theo_thu_tu_on_dinh(board, bo_nho):
    thay_tu, da_bao = bo_nho
    jobs = {name: {"state": "running"} for name in ("SF-S2-01", "SF-S1-01", "LO:SF-S3-01")}
    huy = set(jobs)
    board._soat_co_huy(huy, jobs, thay_tu, da_bao, bay_gio=0)

    ket_qua = board._soat_co_huy(huy, jobs, thay_tu, da_bao, bay_gio=board.CHO_HUY_TOI_DA)

    assert [ident for ident, _ in ket_qua] == ["LO:SF-S3-01", "SF-S1-01", "SF-S2-01"]


def test_nguong_phai_lon_hon_mot_nhip_nguoi_gac(board):
    assert board.CHO_HUY_TOI_DA > 30


def _ten_ham_duoc_goi(nguon: str) -> set:
    """Tên các hàm THỰC SỰ được gọi — đọc bằng AST, không khớp chuỗi.

    Khớp chuỗi ở đây sai: chính chú thích và docstring nhắc tới `bi_huy()` để
    cảnh báo không được gọi nó, nên phép kiểm bằng `in` sẽ tự bắt lời cảnh báo."""
    import ast
    import textwrap

    goi = set()
    for node in ast.walk(ast.parse(textwrap.dedent(nguon))):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            goi.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            goi.add(node.func.attr)
    return goi


def test_nguoi_gac_khong_bao_gio_an_co_huy(board):
    from pathlib import Path

    from helpers import function_source

    nguon = function_source(Path(board.__file__), "_gac_hang_doi")
    soat = function_source(Path(board.__file__), "_soat_co_huy")

    for ham in (nguon, soat):
        goi = _ten_ham_duoc_goi(ham)
        assert "bi_huy" not in goi, "người gác gọi bi_huy() là ĂN MẤT cờ của thợ"
        assert "bo_co_huy" not in goi
        # `da_bao.discard` (set cục bộ) thì được; đụng vào DA_HUY thật thì không.
        assert "DA_HUY.discard" not in ham and "DA_HUY.add" not in ham

    assert "_soat_co_huy(da_huy, JOBS, huy_ma_chay, da_bao_huy)" in nguon
    assert "INVARIANT_VIOLATION" in nguon
