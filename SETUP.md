# SETUP — dựng grokpipe trên máy mới

Tài liệu này dành cho macOS và repo hiện tại. Không xoá hoặc thay asset/version
để “làm sạch” môi trường.

## 1. Phụ thuộc hệ thống

- Python 3 có `venv`
- Google Chrome
- `ffmpeg` cho xử lý/ghép video
- Git; `bd` và ast-grep chỉ cần cho phát triển

Trên macOS có Homebrew:

```bash
brew install python ffmpeg
```

## 2. Tạo môi trường Python

Cách nhanh:

```bash
bash setup_new_machine.sh
./.venv/bin/python3 -m pip install -r requirements-test.txt
```

Hoặc cài rõ từng bước:

```bash
python3 -m venv .venv
./.venv/bin/python3 -m pip install --upgrade pip
./.venv/bin/python3 -m pip install -r requirements-test.txt
./.venv/bin/python3 -m pip install playwright pillow
./.venv/bin/python3 -m playwright install chromium
```

Script bootstrap cài Playwright/Pillow; lệnh tiếp theo bổ sung gate và runtime
dependencies. `requirements-test.txt` kéo theo `requirements-runtime.txt`.
Luôn chạy board và test bằng Python trong `.venv`; Python hệ thống có thể thiếu
Playwright.

## 3. Đăng nhập tài khoản

Người dùng tự đăng nhập ChatGPT/Grok trong Chrome; không chia sẻ mật khẩu, OTP,
cookie hoặc profile. Có thể mở Chrome debug riêng:

```bash
open -na "Google Chrome" --args \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.grokpipe-chrome"
```

Đăng nhập một lần trong cửa sổ đó rồi giữ profile. Các account bổ sung dùng
profile/cổng riêng và được quản lý trong mục Tài khoản của board.

## 4. Kiểm tra trước khi chạy

```bash
./test-job-lifecycle.command
```

Gate không gọi provider thật. Nếu gate thiếu dependency, cài lại bước 2 thay vì
chạy bằng Python hệ thống.

## 5. Chạy board

```bash
./chay-board.command PIPELINE-AISLE-SEVEN.project
```

Production mặc định dùng lifecycle authoritative + live executor. Script chọn
cổng theo project; AISLE SEVEN dùng `8784`. Log ví dụ:

```bash
tail -f /tmp/sfboard-8784.log
```

Health tối thiểu cần thấy trên `/api/chan-doan`:

- mode `authoritative`;
- live executor enabled;
- invariant violations bằng 0;
- số worker/account seat hợp lý.

## 6. Khôi phục và sao lưu

- Queue/lifecycle nằm trong SQLite và được recover khi restart; không xoá DB để
  chữa lỗi queue.
- Project `*.project` chứa dữ liệu phim và media, phải sao lưu riêng.
- Profile Chrome, runtime DB, log và cấu hình tài khoản là dữ liệu local nhạy
  cảm; không commit lên repo public.
- Trước thao tác phục hồi bằng `quay-lai.sh`, đọc script và xác nhận snapshot
  đích vì thao tác có thể ghi đè file.

## 7. Rollback lifecycle

Chỉ rollback khi đã dừng/giải quyết mọi execution đang active:

```bash
GROKPIPE_JOB_MODE=legacy GROKPIPE_LIVE_EXECUTOR=0 \
  ./chay-board.command PIPELINE-AISLE-SEVEN.project
```

Sau rollback, lưu diagnostics/log và sửa nguyên nhân gốc bằng regression test.
