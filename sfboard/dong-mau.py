#!/usr/bin/env python3
"""Đồng bảng màu cho các ảnh SF trong CÙNG một địa điểm.

VÌ SAO CẦN: ChatGPT vẽ mỗi lượt một kiểu ánh sáng. Cùng một căn phòng mà ảnh này
ám vàng, ảnh kia lạnh, chỗ sáng chỗ tối — dựng thành phim thì nhìn như quay ở hai
nơi khác nhau. Đây là bài toán xử lý ảnh có công thức đóng, KHÔNG cần AI nhìn:
đo phân bố màu của ảnh chuẩn, đo của ảnh cần sửa, kéo cái sau về cái trước.

CÁCH LÀM — Reinhard color transfer trong không gian Lab. Chọn Lab vì nó tách
ĐỘ SÁNG (L) khỏi MÀU (a: lục↔đỏ, b: lam↔vàng). Tách được hai thứ đó mới sửa
riêng được cái sai mà không phá cái đúng.

⛔ ĐỪNG ÉP KHỚP MÙ. Cận mặt và toàn cảnh nhìn ra cửa sổ VỐN phải khác độ sáng —
đó là ý đồ quay, không phải lỗi. Ép tất cả về cùng một mức là làm phẳng chính cái
mình đang cố giữ. Vì thế mặc định chỉ khớp TRỤC MÀU và để nguyên độ sáng; muốn
động vào độ sáng thì phải nói rõ, và vẫn có trần.

⛔ KHÔNG BAO GIỜ ghi đè ảnh trong assets/. Chỉ đọc vào, ghi ra thư mục riêng.
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

# Ma trận chuyển RGB↔LMS↔Lab của Reinhard (Ruderman). Dùng thẳng số cho gọn —
# đây là hằng số của thuật toán, không phải tham số để chỉnh.
_RGB2LMS = np.array([[0.3811, 0.5783, 0.0402],
                     [0.1967, 0.7244, 0.0782],
                     [0.0241, 0.1288, 0.8444]])
_LMS2LAB = (np.array([[1 / np.sqrt(3), 0, 0],
                      [0, 1 / np.sqrt(6), 0],
                      [0, 0, 1 / np.sqrt(2)]])
            @ np.array([[1, 1, 1], [1, 1, -2], [1, -1, 0]]))
_LAB2LMS = (np.array([[1, 1, 1], [1, 1, -1], [1, -2, 0]])
            @ np.array([[1 / np.sqrt(3), 0, 0],
                        [0, 1 / np.sqrt(6), 0],
                        [0, 0, 1 / np.sqrt(2)]]))
_LMS2RGB = np.linalg.inv(_RGB2LMS)


def _sang_lab(rgb: np.ndarray) -> np.ndarray:
    lms = rgb.reshape(-1, 3) @ _RGB2LMS.T
    # log của 0 là -inf và sẽ lan ra toàn ảnh: kẹp sàn TRƯỚC khi lấy log.
    lms = np.log10(np.maximum(lms, 1e-6))
    return (lms @ _LMS2LAB.T).reshape(rgb.shape)


def _ve_rgb(lab: np.ndarray) -> np.ndarray:
    lms = 10 ** (lab.reshape(-1, 3) @ _LAB2LMS.T)
    rgb = lms @ _LMS2RGB.T
    return np.clip(rgb, 0, 1).reshape(lab.shape)


def _doc(p: str) -> np.ndarray:
    return np.asarray(Image.open(p).convert("RGB"), dtype=np.float64) / 255.0


def do_mau(p: str) -> tuple:
    """(L, a, b) trung bình theo CIELAB THẬT — số để BÁO CÁO cho người đọc.

    ⛔ ĐỪNG thay bằng `np.asarray(im.convert("LAB"))`: Pillow lưu hai kênh a/b
    lệch chuẩn, đọc thô bằng numpy ra số sai hoàn toàn (đo một ảnh cho a=-51.7
    trong khi giá trị thật là +3.3). `ImageStat` thì đúng, nhưng tự tính theo
    công thức gốc là chắc nhất — đã đối chiếu với sRGB→XYZ→Lab, D65.

    L: 0–100 (độ sáng) · a: lục↔đỏ · b: lam↔vàng, cùng thang CIE.
    """
    im = Image.open(p).convert("RGB")
    im.thumbnail((256, 256))
    s = np.asarray(im, dtype=np.float64) / 255
    lin = np.where(s <= 0.04045, s / 12.92, ((s + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    t = (lin.reshape(-1, 3) @ M.T) / np.array([0.95047, 1.0, 1.08883])
    d = 6 / 29
    f = np.where(t > d ** 3, np.cbrt(t), t / (3 * d * d) + 4 / 29)
    return ((116 * f[:, 1] - 16).mean(),
            (500 * (f[:, 0] - f[:, 1])).mean(),
            (200 * (f[:, 1] - f[:, 2])).mean())


def khop(anh: np.ndarray, chuan_ms: tuple, muc: str, tran_L: float) -> np.ndarray:
    """Kéo màu của `anh` về thống kê `chuan_ms` = (mean, std) trong Lab-Reinhard."""
    lab = _sang_lab(anh)
    m, s = lab.reshape(-1, 3).mean(0), lab.reshape(-1, 3).std(0)
    cm, cs = chuan_ms
    s = np.where(s < 1e-6, 1e-6, s)          # ảnh một màu phẳng → khỏi chia cho 0
    ra = lab.copy()
    for k in (1, 2):                          # trục a, b — luôn khớp
        ra[..., k] = (lab[..., k] - m[k]) * (cs[k] / s[k]) + cm[k]
    if muc == "sang":
        moi = (lab[..., 0] - m[0]) * (cs[0] / s[0]) + cm[0]
        # TRẦN: chỉ cứu ảnh lệch hẳn, không kéo cảnh cố tình tối lên cho bằng
        # cảnh sáng. Trần tính trên mức dịch trung bình, không phải từng pixel.
        dich = np.clip(moi.mean() - lab[..., 0].mean(), -tran_L, tran_L)
        ra[..., 0] = lab[..., 0] + dich
    return _ve_rgb(ra)


def main() -> int:
    ap = argparse.ArgumentParser(description="Đồng bảng màu ảnh SF cùng địa điểm")
    ap.add_argument("project")
    ap.add_argument("--chuan", required=True, help="tên ảnh chuẩn trong assets/ (vd REF_LICAPT_DEM.png)")
    ap.add_argument("--loc", default="SF-S3-", help="tiền tố ảnh cần khớp")
    ap.add_argument("--ra", default="thu-dong-mau", help="thư mục xuất, nằm trong project")
    ap.add_argument("--muc", choices=["mau", "sang"], default="mau",
                    help="mau = chỉ khớp trục màu (mặc định, an toàn) · sang = khớp thêm độ sáng")
    ap.add_argument("--tran-L", type=float, default=10.0, help="trần dịch độ sáng khi --muc sang")
    ap.add_argument("--xem", action="store_true", help="chỉ in bảng lệch, KHÔNG ghi file")
    a = ap.parse_args()

    assets = os.path.join(a.project, "assets")
    chuan_p = os.path.join(assets, a.chuan)
    if not os.path.isfile(chuan_p):
        print(f"✗ không thấy ảnh chuẩn: {chuan_p}"); return 1
    fs = sorted(f for f in os.listdir(assets)
                if f.startswith(a.loc) and f.lower().endswith((".png", ".jpg", ".jpeg")))
    if not fs:
        print(f"✗ không có ảnh nào khớp tiền tố {a.loc!r} trong {assets}"); return 1

    lab_c = _sang_lab(_doc(chuan_p)).reshape(-1, 3)
    chuan_ms = (lab_c.mean(0), lab_c.std(0))
    cL, ca, cb = do_mau(chuan_p)
    print(f"ảnh chuẩn : {a.chuan}   L={cL:.1f}  a={ca:+.1f}  b={cb:+.1f}")
    print(f"mức        : {'chỉ trục màu, giữ nguyên độ sáng' if a.muc == 'mau' else f'màu + độ sáng (trần ±{a.tran_L:g})'}")
    print(f"{'ảnh':12} {'L trước':>8} {'a trước':>8} {'b trước':>8}   →  {'L sau':>7} {'a sau':>7} {'b sau':>7}")

    ra_dir = os.path.join(a.project, a.ra)
    if not a.xem:
        os.makedirs(ra_dir, exist_ok=True)
    ghi = []
    for f in fs:
        p = os.path.join(assets, f)
        L0, a0, b0 = do_mau(p)
        if a.xem:
            print(f"  {f:10} {L0:8.1f} {a0:+8.1f} {b0:+8.1f}")
            continue
        out = khop(_doc(p), chuan_ms, a.muc, a.tran_L)
        op = os.path.join(ra_dir, f)
        Image.fromarray((out * 255).round().astype(np.uint8)).save(op)
        L1, a1, b1 = do_mau(op)
        print(f"  {f:10} {L0:8.1f} {a0:+8.1f} {b0:+8.1f}   →  {L1:7.1f} {a1:+7.1f} {b1:+7.1f}")
        ghi.append({"anh": f, "truoc": [L0, a0, b0], "sau": [L1, a1, b1]})

    if a.xem:
        return 0
    with open(os.path.join(ra_dir, "_bao-cao.json"), "w", encoding="utf-8") as fh:
        json.dump({"chuan": a.chuan, "muc": a.muc, "tran_L": a.tran_L, "anh": ghi},
                  fh, ensure_ascii=False, indent=1)
    Ls = [x["sau"][0] for x in ghi]; bs = [x["sau"][2] for x in ghi]
    L0s = [x["truoc"][0] for x in ghi]; b0s = [x["truoc"][2] for x in ghi]
    print(f"\nđộ tản mạn ĐỘ SÁNG L : {max(L0s)-min(L0s):5.1f}  →  {max(Ls)-min(Ls):5.1f}")
    print(f"độ tản mạn ÁM VÀNG b : {max(b0s)-min(b0s):5.1f}  →  {max(bs)-min(bs):5.1f}")
    print(f"\n{len(ghi)} ảnh đã ghi vào {ra_dir}  (assets/ KHÔNG bị đụng)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
