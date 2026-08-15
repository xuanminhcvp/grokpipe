"""Board có THẬT SỰ ghi được vào sổ lỗi không?

Mọi test khác về phần này chỉ khớp chuỗi trong mã nguồn (`"report_runtime_bug("
in worker`). Chúng xanh kể cả khi dây nối đã đứt — mà sfboard.py có sẵn bản dự
phòng nuốt lỗi import và trả `False` im lặng, nên đứt dây là board ghi rỗng
trong khi cổng test vẫn báo PASS.

Ở đây gọi đúng hàm mà board dùng, cho lỗi nổ thật, rồi đọc file JSONL.
"""

import json

import pytest

from helpers import load_sfboard


@pytest.fixture(scope="module")
def board():
    return load_sfboard()


@pytest.fixture
def so_loi(board, tmp_path):
    """Khởi động sổ bằng CHÍNH tham chiếu của board, không phải bản import khác.

    `jobs.runtime_service` (board dùng) và `sfboard.jobs.runtime_service` (test
    hay import) là HAI module object riêng, mỗi cái một singleton. Khởi động
    nhầm cái là test xanh mà chẳng chứng minh gì."""
    board.start_runtime_bug_service(tmp_path)
    yield tmp_path / ".grokpipe" / "runtime-bugs" / "events.jsonl"
    board.stop_runtime_bug_service()


def doc(duong_dan):
    if not duong_dan.exists():
        return []
    return [json.loads(d) for d in duong_dan.read_text(encoding="utf-8").splitlines() if d]


def test_board_dung_facade_that_chu_khong_phai_ban_du_phong(board):
    """Bản dự phòng được định nghĩa NGAY TRONG sfboard.py — nhận ra qua __module__."""
    assert board.report_runtime_bug.__module__ == "jobs.runtime_service"
    assert board.runtime_bug_diagnostics.__module__ == "jobs.runtime_service"
    assert board.start_runtime_bug_service.__module__ == "jobs.runtime_service"


def test_worker_entry_ghi_so_khi_luong_tho_chet_that(board, so_loi, monkeypatch):
    def no_tung(*_a, **_k):
        raise RuntimeError("thợ chết giữa vòng lặp")

    monkeypatch.setattr(board, "_worker", no_tung)

    with pytest.raises(RuntimeError):          # lỗi vẫn phải nổi lên trên
        board._worker_entry("http://127.0.0.1:9222", "img", 0)

    su_kien = doc(so_loi)
    assert len(su_kien) == 1
    assert su_kien[0]["reason_code"] == "WORKER_CRASH"
    assert su_kien[0]["severity"] == "CRITICAL"
    assert su_kien[0]["job"]["kind"] == "img"
    assert su_kien[0]["exception"]["type"] == "RuntimeError"
    assert su_kien[0]["runtime"]["slot"] == 0
    # stack trace phải có thật, không phải chuỗi rỗng
    assert "thợ chết giữa vòng lặp" in su_kien[0]["exception"]["stacktrace"]


def test_worker_entry_khong_ghi_gi_khi_tho_nghi_binh_thuong(board, so_loi, monkeypatch):
    monkeypatch.setattr(board, "_worker", lambda *_a, **_k: None)

    board._worker_entry("http://127.0.0.1:9222", "img", 0)

    assert doc(so_loi) == []


def test_chan_doan_cua_board_doc_duoc_so_that(board, so_loi, monkeypatch):
    monkeypatch.setattr(board, "_worker", lambda *_a, **_k: (_ for _ in ()).throw(ValueError("x")))
    with pytest.raises(ValueError):
        board._worker_entry("http://127.0.0.1:9222", "vid", 1)

    chan_doan = board.runtime_bug_diagnostics()["bug_bridge"]

    assert chan_doan["pending"] == 1
    assert chan_doan["mode"] == "journal-only"


def test_bi_mat_trong_loi_khong_lot_xuong_so(board, so_loi, monkeypatch):
    def no_tung(*_a, **_k):
        raise RuntimeError("nối Chrome hỏng: https://u:pw@x.test/a?token=shhh9x7q")

    monkeypatch.setattr(board, "_worker", no_tung)
    with pytest.raises(RuntimeError):
        board._worker_entry("http://127.0.0.1:9222", "img", 0)

    noi_dung = so_loi.read_text(encoding="utf-8")

    assert "shhh9x7q" not in noi_dung
    assert "u:pw" not in noi_dung
