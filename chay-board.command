#!/bin/bash
# Mở SF Board. Bấm đúp file này, hoặc: ./chay-board.command <TÊN-PROJECT>
# macOS KHÔNG có setsid — phải bọc subshell + disown thì tiến trình mới sống sót.
cd "$(dirname "$0")"

# playwright chỉ cài trong .venv — `python3` trần là bản 3.9 của macOS, không có
# nó, và board sẽ chạy được nhưng mọi job chết với "No module named 'playwright'".
PY="./.venv/bin/python3"
[ -x "$PY" ] || { echo "Chưa có .venv — xem SETUP.md mục 1."; exit 1; }

PROJ="${1:-PIPELINE-RUTHS-HOUSE.project}"
case "$PROJ" in
  PIPELINE-RUTHS-HOUSE.project)  PORT=8779 ;;
  PIPELINE-8DOLLARS.project)     PORT=8778 ;;
  PIPELINE-PORCH-LIGHT.project)  PORT=8780 ;;
  PIPELINE-TAXI-DRIVER.project)  PORT=8781 ;;
  PIPELINE-LOOKING-POOR.project) PORT=8782 ;;
  *) echo "Chưa gán cổng cho $PROJ — sửa case trong file này."; exit 1 ;;
esac

if curl -s -o /dev/null --max-time 2 "http://localhost:$PORT"; then
  echo "Board đã chạy sẵn ở http://localhost:$PORT"
else
  ( nohup "$PY" -u sfboard/sfboard.py "$PROJ" --port "$PORT" \
      > "/tmp/sfboard-$PORT.log" 2>&1 < /dev/null & disown )
  until curl -s -o /dev/null --max-time 2 "http://localhost:$PORT"; do sleep 2; done
  echo "Board lên: http://localhost:$PORT  (log: /tmp/sfboard-$PORT.log)"
fi
open "http://localhost:$PORT"
