#!/usr/bin/env bash
# Khôi phục môi trường grokpipe trên máy mới: venv + deps + Chromium + memory.
# Chạy: bash setup_new_machine.sh  (từ thư mục gốc repo)
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
echo "== Project: $ROOT =="

# 1) ffmpeg?
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "!! Thiếu ffmpeg. macOS: brew install ffmpeg" >&2
fi

# 2) venv + deps + Chromium
echo "== Tạo .venv + cài phụ thuộc =="
cd "$ROOT/grokpipe"
python3 -m venv .venv
./.venv/bin/python -m pip install -q --upgrade pip
./.venv/bin/python -m pip install -q -r requirements.txt || true
./.venv/bin/python -m playwright install chromium
cd "$ROOT"

# 3) Phục hồi memory + lịch sử chat vào ~/.claude/projects/<mã-đường-dẫn>/
ENC="$(printf '%s' "$ROOT" | sed 's#/#-#g')"
PROJ="$HOME/.claude/projects/$ENC"
if [ -d "$ROOT/_claude/memory" ]; then
  echo "== Phục hồi memory -> $PROJ/memory =="
  mkdir -p "$PROJ/memory"
  cp -R "$ROOT/_claude/memory/"* "$PROJ/memory/"
fi
if ls "$ROOT/_claude/sessions/"*.jsonl >/dev/null 2>&1; then
  echo "== Phục hồi lịch sử chat -> $PROJ/ =="
  mkdir -p "$PROJ"
  cp "$ROOT/_claude/sessions/"*.jsonl "$PROJ/"
  echo "   (mở Claude Code trong thư mục này rồi 'claude --resume' để tiếp tục chat)"
fi

echo ""
echo "== XONG môi trường. Bước tiếp theo (xem SETUP.md mục 4-5): =="
echo "  1) Đăng nhập ChatGPT + Grok theo mẹo 2 bước (mở Chrome không cờ debug -> login -> mở lại có cờ debug --remote-debugging-port=9222 --user-data-dir=\$HOME/.grokpipe-chrome)"
echo "  2) cd grokpipe && ./.venv/bin/python -m grokpipe run ../PIPELINE-BANHMI-VID001-028.txt --chrome-cdp http://localhost:9222 --auto"
