#!/usr/bin/env bash
# Dựng lại môi trường grokpipe trên máy mới. Chạy: bash setup_new_machine.sh
# Chi tiết quy trình: SETUP.md · luật làm việc: CLAUDE.md
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
echo "== Project: $ROOT =="

command -v ffmpeg >/dev/null 2>&1 || echo "!! Thiếu ffmpeg (ghép video). macOS: brew install ffmpeg" >&2

echo "== Tạo .venv + cài phụ thuộc =="
python3 -m venv .venv
./.venv/bin/python -m pip install -q --upgrade pip
./.venv/bin/python -m pip install -q playwright pillow
./.venv/bin/python -m playwright install chromium

cat <<'MSG'

== XONG môi trường. Ba bước còn lại ==

1) Đăng nhập ChatGPT/Grok — BẠN tự làm, AI không nhập tài khoản:
   mở Chrome thường -> login -> đóng -> mở lại kèm cờ debug:
   --remote-debugging-port=9222 --user-data-dir=$HOME/.grokpipe-chrome
   (hoặc bấm "Bật" trong mục ⚙ Tài khoản trên board)
   ⚠ Tối đa 4 cửa sổ cùng lúc, nhiều hơn là cạn RAM.

2) Chạy board:
   ./chay-board.command

3) Video chỉ chạy khi BẠN tự bấm nút "Cho phép tạo video" trên board.
MSG
