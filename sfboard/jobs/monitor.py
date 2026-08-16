"""Người gác CHỈ NHÌN — phát hiện lệch rồi báo, tuyệt đối không tự sửa.

Người gác hiện tại vừa dò vừa vá: thấy việc "mồ côi" là tự xếp lại. Nghe hợp lý,
nhưng nó biến người quan sát thành một người ghi nữa — và là người ghi nguy hiểm
nhất, vì nó hành động dựa trên PHỎNG ĐOÁN từ nhãn hiển thị. Đúng cơ chế đó đã
xếp lại một lô đang chạy dở và làm nó render hai lượt.

Ở đây chỉ có phép so sánh thuần. Ra là danh sách `Finding` để log/hiện lên board.
Không mutate gì, không nhận tham chiếu tới hàng đợi thật.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence, Tuple


class Severity(str, Enum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


@dataclass(frozen=True)
class Finding:
    code: str
    severity: Severity
    subject: str
    detail: str


def _tap_thanh_vien(idents: Sequence[str]) -> set:
    ra = set()
    for i in idents:
        ra.update(x for x in (i[3:].split(",") if i.startswith("LO:") else [i]) if x)
    return ra


class InvariantMonitor:
    """So ba nguồn với nhau: hàng đợi thật · lịch execution · nhãn hiển thị."""

    def check(
        self,
        queue_idents: Sequence[str],
        scheduled_idents: Sequence[str],
        job_labels: Mapping[str, str],
        leased_idents: Sequence[str] = (),
    ) -> Tuple[Finding, ...]:
        ra = []
        hang = set(queue_idents)
        lich = set(scheduled_idents)
        dang_chay = set(leased_idents)

        # 1. Việc nằm trong hàng mà lịch không biết → lịch bị bỏ sót.
        for ident in sorted(hang - lich - dang_chay):
            ra.append(Finding("lich.thieu", Severity.WARN, ident,
                              "việc nằm trong hàng nhưng lịch không có"))

        # 2. Lịch bảo còn chờ mà hàng không có → việc rơi mất.
        for ident in sorted(lich - hang - dang_chay):
            ra.append(Finding("hang.thieu", Severity.ERROR, ident,
                              "lịch còn chờ nhưng hàng đợi không có việc này"))

        # 3. Nhãn 'chờ' cho thẻ chẳng nằm trong hàng nào → nhãn nói dối.
        thanh_vien = _tap_thanh_vien(list(hang | dang_chay))
        for key, nhan in sorted(job_labels.items()):
            if nhan != "queued" or key.startswith("LO:"):
                continue
            if key not in thanh_vien:
                ra.append(Finding("nhan.mo_coi", Severity.WARN, key,
                                  "nhãn 'chờ' nhưng không có việc nào đang chờ"))

        # 4. Nhãn 'đang chạy' mà không có lease nào → hoặc thợ chết, hoặc nhãn cũ.
        chay = _tap_thanh_vien(list(dang_chay))
        for key, nhan in sorted(job_labels.items()):
            if nhan != "running" or key.startswith("LO:"):
                continue
            if key not in chay:
                ra.append(Finding("chay.khong_lease", Severity.WARN, key,
                                  "nhãn 'đang chạy' nhưng không có lease nào"))
        return tuple(ra)

    @staticmethod
    def summary(findings: Sequence[Finding]) -> dict:
        dem: dict = {}
        for f in findings:
            dem[f.code] = dem.get(f.code, 0) + 1
        # XẾP HẠNG TƯỜNG MINH, không `max` trên chuỗi: so chuỗi là so bảng chữ
        # cái, mà "warn" > "error" — mức nặng nhất sẽ bị báo thành mức nhẹ.
        thu_tu = {Severity.INFO: 0, Severity.WARN: 1, Severity.ERROR: 2}
        nang = max((f.severity for f in findings),
                   key=lambda s: thu_tu[s], default=None)
        return {
            "tong": len(findings),
            "theo_ma": dem,
            "nang_nhat": nang.value if nang else "",
        }
