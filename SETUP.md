# SETUP — dựng lại môi trường trên máy mới

Repo chứa **SF Board** (công cụ duyệt) + **executor** ChatGPT/Grok + dữ liệu phim.
Luật làm việc nằm ở [CLAUDE.md](CLAUDE.md).

## 1. Phụ thuộc

```bash
python3 -m venv .venv && ./.venv/bin/pip install playwright pillow
./.venv/bin/playwright install chromium
```

Cần thêm `ffmpeg` (ghép video): `brew install ffmpeg`

## 2. Chrome debug + đăng nhập

Board điều khiển Chrome qua CDP. Mỗi tài khoản một cửa sổ, mỗi cửa sổ một cổng:

| Cổng | Dùng cho | Profile |
|---|---|---|
| 9222–9225 | ChatGPT (vẽ ảnh) | `~/.grokpipe-chrome*` |
| 9228 | Grok (dựng video) | `~/.grokpipe-grok-7` |

Bật/tắt và mở cửa sổ ngay trong board, mục **⚙ Tài khoản**.
**Việc đăng nhập do bạn tự làm trong cửa sổ Chrome** — AI không nhập tài khoản/mật khẩu.

⚠ **Tối đa 4 cửa sổ cùng lúc** — nhiều hơn là cạn RAM và sập hàng loạt.

## 3. Chạy board

```bash
./chay-board.command                              # mặc định RUTHS-HOUSE
./chay-board.command PIPELINE-8DOLLARS.project    # phim khác
```

Hoặc gọi thẳng: `python3 sfboard/sfboard.py <PROJECT> --port <PORT>`

## 4. Quy trình một phim

1. Viết kịch bản — skill `viet-kich-ban`
2. Tạo REF nhân vật rồi SF từng scene — skill `skills-film`
3. Duyệt ảnh trên board, bản nào bấm duyệt là **chốt**
4. Chia shot + viết prompt video
5. **Bạn tự bấm nút "Cho phép tạo video"** rồi render (AI không được bật)
6. Duyệt video, ghép bằng ffmpeg

## 5. Sao lưu

```bash
./luu-ban.sh "ghi chú"    # tạo bản chụp
./quay-lai.sh             # quay lại bản trước
```

Phim làm xong nên xoá `versions/` và `videos/versions/` — bản chính đã nằm ở
`assets/` và `videos/`.
