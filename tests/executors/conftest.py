"""Trang GIẢ thì không có gì để chờ — bỏ mọi `time.sleep` của executor.

`_chon_che_do` và các nhánh dựng lại DOM ngủ 0,5–1,2 giây mỗi bước để chờ SPA
thật vẽ xong. Với trang giả trong test, DOM đổi ngay trong lời gọi, nên mỗi giây
ngủ là một giây trắng: bộ test executor mất 26 giây, riêng file chế độ ChatGPT
chiếm 20 giây. Bộ test chậm là bộ test ít được chạy.

CHỈ thay `sleep`, giữ nguyên `time()` và `monotonic()`: mã sản xuất dùng chúng để
tính deadline, thay bừa là biến vòng chờ thành vòng lặp vô hạn.

Tác động chỉ trong `tests/executors`. Ba test bộ hẹn giờ ở `job_lifecycle` vẫn
chạy đồng hồ thật vì thứ chúng kiểm CHÍNH LÀ cái hẹn giờ.
"""

import time as _time
import types

import pytest

from grokpipe.executors import image_chatgpt, video_grok


def _dong_ho_khong_ngu():
    gia = types.SimpleNamespace(
        **{k: getattr(_time, k) for k in dir(_time) if not k.startswith("_")}
    )
    gia.sleep = lambda *_a, **_k: None
    return gia


@pytest.fixture(autouse=True)
def khong_ngu(monkeypatch):
    for mod in (image_chatgpt, video_grok):
        monkeypatch.setattr(mod, "time", _dong_ho_khong_ngu())
